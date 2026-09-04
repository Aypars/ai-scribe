"""Background transcription, speaker match, and analysis jobs."""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.meeting import Meeting
from app.repositories import meetings as meetings_repo
from app.schemas.meeting import TranscriptionProgressOut
from app.services.analysis import AnalysisError, analyze_transcript
from app.services.llm import _is_transient_gemini
from app.services.meeting_lang import current_lang, normalize_lang
from app.services.storage import (
    absolute_audio_path,
    is_video_file,
    stored_relative_path,
)
from app.services.transcription import (
    TranscriptionCancelled,
    clear_transcription,
    extract_audio_from_video,
    fail_job,
    finish_job,
    get_job,
    start_job,
    transcribe_audio,
    update_job,
)

logger = logging.getLogger(__name__)

_running: set[int] = set()
_analyzing: set[int] = set()
_matching: set[int] = set()
_analysis_failed: dict[int, str] = {}
_analysis_retry_at: dict[int, float] = {}
_analysis_message: dict[int, str] = {}
_matching_message: dict[int, str] = {}
_running_lock = threading.Lock()


def clear_analysis_failure(meeting_id: int) -> None:
    _analysis_failed.pop(meeting_id, None)
    _analysis_retry_at.pop(meeting_id, None)


def remember_analysis_error(meeting_id: int, error: str) -> None:
    _analysis_failed.setdefault(meeting_id, error)


def progress_out(meeting: Meeting) -> TranscriptionProgressOut | None:
    if meeting.meeting_id in _analyzing:
        return TranscriptionProgressOut(
            progress=90,
            message=_analysis_message.get(meeting.meeting_id) or "Analiz ediliyor…",
            elapsed_seconds=0,
        )
    if meeting.meeting_id in _matching:
        return TranscriptionProgressOut(
            progress=85,
            message=_matching_message.get(meeting.meeting_id) or "Konuşmacılar eşleniyor…",
            elapsed_seconds=0,
        )
    if meeting.status == "transcribed":
        err = _analysis_failed.get(meeting.meeting_id) or (meeting.analysis_error or "").strip() or None
        if err:
            return TranscriptionProgressOut(
                progress=100, message="Analiz başarısız", error=err, elapsed_seconds=0
            )
        return None
    job = get_job(meeting.meeting_id)
    if job is not None and job.state == "running":
        return TranscriptionProgressOut(
            progress=job.progress,
            message=job.message,
            error=job.error,
            elapsed_seconds=max(0, int(time.time() - job.started_at)),
        )
    if meeting.status == "uploaded":
        return TranscriptionProgressOut(progress=0, message="Sıraya alındı…", elapsed_seconds=0)
    if meeting.status == "failed":
        return TranscriptionProgressOut(
            progress=0,
            message="Yazıya çevirme başarısız",
            error="Yazıya çevirme başarısız. Tekrar deneyebilirsiniz.",
            elapsed_seconds=0,
        )
    return None

def transcribe_meeting_job(meeting_id: int) -> None:
    start_job(meeting_id)
    path = None
    db = SessionLocal()
    named_attendees = None
    language = "tr"
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None and meeting.audio_path:
            path = absolute_audio_path(meeting.audio_path)
            named_attendees = meeting.named_attendees
            language = getattr(meeting, "language", None) or "tr"
        else:
            fail_job(meeting_id, "Toplantı veya ses dosyası bulunamadı")
    finally:
        db.close()

    if path is None:
        with _running_lock:
            _running.discard(meeting_id)
        return

    db = None
    lang_token = current_lang.set(normalize_lang(language))
    try:
        if is_video_file(path):
            update_job(meeting_id, progress=3, message="Videodan ses çıkarılıyor…")
            source = path
            path = extract_audio_from_video(source)
            db = SessionLocal()
            try:
                meeting = db.get(Meeting, meeting_id)
                if meeting is not None:
                    meeting.audio_path = stored_relative_path(path)
                    db.commit()
            finally:
                db.close()
                db = None
            try:
                source.unlink(missing_ok=True)
            except OSError:
                logger.warning("Video silinemedi: %s", source)
        logger.warning("Whisper job started for meeting %s (%s)", meeting_id, path)
        from app.services.speakers import parse_named_attendees

        names = parse_named_attendees(named_attendees)
        named_count = len(names)
        result = transcribe_audio(
            path,
            on_progress=lambda progress, message: update_job(
                meeting_id, progress=progress, message=message
            ),
            meeting_id=meeting_id,
            min_speakers=2,
            max_speakers=max(8, named_count + 4) if named_count else 12,
            hint_names=names,
            language=language,
        )
        db = SessionLocal()
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            fail_job(meeting_id, "Toplantı bulunamadı")
            return
        meetings_repo.replace_transcript(db, meeting, result.segments, result.duration_seconds)
        meeting = meetings_repo.get_for_user(db, meeting.user_id, meeting_id) or meeting
        logger.warning("Whisper job finished for meeting %s", meeting_id)
        _run_speaker_match(db, meeting)
        finish_job(meeting_id)
    except TranscriptionCancelled:
        logger.warning("Whisper cancelled for meeting %s", meeting_id)
        if db is not None:
            db.rollback()
    except Exception as exc:
        logger.exception("Whisper failed for meeting %s", meeting_id)
        fail_job(meeting_id, str(exc) or "Whisper başarısız oldu")
        if db is None:
            db = SessionLocal()
        else:
            db.rollback()
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None:
            meetings_repo.mark_failed(db, meeting)
    finally:
        current_lang.reset(lang_token)
        clear_transcription(meeting_id)
        if db is not None:
            db.close()
        with _running_lock:
            _running.discard(meeting_id)


def schedule_transcription(meeting_id: int) -> None:
    with _running_lock:
        if meeting_id in _running:
            return
        job = get_job(meeting_id)
        if job is not None and job.state == "running":
            return
        _running.add(meeting_id)
    threading.Thread(
        target=transcribe_meeting_job,
        args=(meeting_id,),
        name=f"whisper-{meeting_id}",
        daemon=True,
    ).start()


def _persist_analysis_error(db: Session, user_id: int, meeting_id: int, error: str) -> None:
    meeting = meetings_repo.get_for_user(db, user_id, meeting_id)
    if meeting is None:
        return
    meeting.analysis_error = error[:1000]
    db.commit()


def _run_analysis(db: Session, meeting: Meeting) -> None:
    if not meeting.transcripts:
        return
    _analyzing.add(meeting.meeting_id)
    _analysis_failed.pop(meeting.meeting_id, None)
    _analysis_retry_at.pop(meeting.meeting_id, None)
    _analysis_message[meeting.meeting_id] = "Analiz ediliyor…"
    update_job(meeting.meeting_id, progress=90, message="Analiz ediliyor…")
    lines = list(meeting.transcripts)
    title = meeting.title
    attendees = meetings_repo.attendees_from_speakers(meeting.transcripts) or meeting.attendees
    named_attendees = meeting.named_attendees
    meeting_date = meeting.date.isoformat() if meeting.date else None
    description = meeting.description
    language = getattr(meeting, "language", None)
    meeting_id = meeting.meeting_id
    user_id = meeting.user_id
    db.commit()
    try:
        result = analyze_transcript(
            lines,
            title=title,
            attendees=attendees,
            meeting_date=meeting_date,
            description=description,
            named_attendees=named_attendees,
            language=language,
            on_busy=lambda wait: _analysis_message.__setitem__(
                meeting_id, f"Gemini yoğun, {wait} sn sonra tekrar…"
            ),
            on_progress=lambda msg: _analysis_message.__setitem__(meeting_id, msg),
        )
        meeting = meetings_repo.get_for_user(db, user_id, meeting_id) or meeting
        meetings_repo.replace_analysis(db, meeting, result)
        logger.warning("Analysis finished for meeting %s", meeting_id)
    except AnalysisError as exc:
        logger.exception("Analysis failed for meeting %s", meeting_id)
        _analysis_failed[meeting_id] = str(exc)
        _persist_analysis_error(db, user_id, meeting_id, str(exc))
        if _is_transient_gemini(str(exc)):
            _analysis_retry_at[meeting_id] = time.time() + 20
    except Exception as exc:
        logger.exception("Analysis failed for meeting %s", meeting_id)
        message = str(exc) or "Analiz başarısız"
        _analysis_failed[meeting_id] = message
        _persist_analysis_error(db, user_id, meeting_id, message)
    finally:
        _analyzing.discard(meeting_id)
        _analysis_message.pop(meeting_id, None)
        finish_job(meeting_id)


def _run_speaker_match(db: Session, meeting: Meeting) -> None:
    if meeting.speakers_matched:
        return
    if not meeting.transcripts:
        meeting.speakers_matched = True
        db.commit()
        return
    meeting_id = meeting.meeting_id
    user_id = meeting.user_id
    token = current_lang.set(normalize_lang(getattr(meeting, "language", None)))
    _matching.add(meeting_id)
    _matching_message[meeting_id] = "Konuşmacılar eşleniyor…"
    update_job(meeting_id, progress=85, message="Konuşmacılar eşleniyor…")
    lines = list(meeting.transcripts)
    title = meeting.title
    named_attendees = meeting.named_attendees
    db.commit()
    try:
        from app.services.speakers import parse_named_attendees, resolve_speaker_map

        mapping = resolve_speaker_map(
            lines,
            title=title,
            names=parse_named_attendees(named_attendees),
        )
        meeting = meetings_repo.get_for_user(db, user_id, meeting_id) or meeting
        if mapping:
            meetings_repo.apply_speaker_map(db, meeting, mapping)
            meeting = meetings_repo.get_for_user(db, user_id, meeting_id) or meeting
        meeting.speakers_matched = True
        db.commit()
        logger.warning("Speaker match finished for meeting %s (%s names)", meeting_id, len(mapping))
    except Exception:
        logger.exception("Speaker match failed for meeting %s", meeting_id)
        meeting = meetings_repo.get_for_user(db, user_id, meeting_id) or meeting
        if meeting is not None:
            meeting.speakers_matched = True
            db.commit()
    finally:
        current_lang.reset(token)
        _matching.discard(meeting_id)
        _matching_message.pop(meeting_id, None)


def match_speakers_job(meeting_id: int) -> None:
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return
        meeting = meetings_repo.get_for_user(db, meeting.user_id, meeting_id)
        if meeting is None or meeting.speakers_matched:
            return
        _run_speaker_match(db, meeting)
    finally:
        db.close()
        with _running_lock:
            _matching.discard(meeting_id)
        _matching_message.pop(meeting_id, None)


def schedule_speaker_match(meeting_id: int) -> None:
    with _running_lock:
        if meeting_id in _matching or meeting_id in _running or meeting_id in _analyzing:
            return
        _matching.add(meeting_id)
    threading.Thread(
        target=match_speakers_job,
        args=(meeting_id,),
        name=f"speakers-{meeting_id}",
        daemon=True,
    ).start()


def analyze_meeting_job(meeting_id: int) -> None:
    db = SessionLocal()
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            return
        meeting = meetings_repo.get_for_user(db, meeting.user_id, meeting_id)
        if meeting is None:
            return
        _run_analysis(db, meeting)
    finally:
        db.close()
        with _running_lock:
            _analyzing.discard(meeting_id)


def schedule_analysis(meeting_id: int) -> None:
    with _running_lock:
        if meeting_id in _analyzing or meeting_id in _running or meeting_id in _matching:
            return
        failed = _analysis_failed.get(meeting_id)
        if failed:
            retry_at = _analysis_retry_at.get(meeting_id, 0)
            if _is_transient_gemini(failed):
                if time.time() < retry_at:
                    return
            else:
                return
        _analyzing.add(meeting_id)
    threading.Thread(
        target=analyze_meeting_job,
        args=(meeting_id,),
        name=f"gemini-{meeting_id}",
        daemon=True,
    ).start()
