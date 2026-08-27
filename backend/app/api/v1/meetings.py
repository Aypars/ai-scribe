import logging
import threading
import time
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.security import get_current_user
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories import meetings as meetings_repo
from app.repositories import people as people_repo
from app.repositories import tasks as tasks_repo
from app.schemas.meeting import (
    ActionOut,
    DecisionOut,
    MeetingDetailOut,
    MeetingListOut,
    MeetingOut,
    MeetingUpdate,
    SpeakerRenameIn,
    TranscriptEditIn,
    TranscriptLineOut,
    TranscriptionProgressOut,
)
from app.services.analysis import AnalysisError, analyze_transcript, match_decision_span, _is_transient_gemini
from app.services.meeting_lang import current_lang, normalize_lang
from app.services.storage import (
    AUDIO_MEDIA_TYPES,
    StorageError,
    absolute_audio_path,
    delete_audio,
    is_video_file,
    save_audio,
    stored_relative_path,
)
from app.services.transcription import (
    TranscriptionCancelled,
    cancel_transcription,
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

router = APIRouter()
_running: set[int] = set()
_analyzing: set[int] = set()
_matching: set[int] = set()
_analysis_failed: dict[int, str] = {}
_analysis_retry_at: dict[int, float] = {}
_analysis_message: dict[int, str] = {}
_matching_message: dict[int, str] = {}
_running_lock = threading.Lock()


def _parse_date(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Tarih biçimi geçersiz",
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed


def _reject_future_meeting(value: datetime) -> datetime:
    now = datetime.now(value.tzinfo)
    if value > now + timedelta(minutes=1):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Toplantı tarihi şu andan ileri olamaz",
        )
    return value


def _progress_out(meeting: Meeting) -> TranscriptionProgressOut | None:
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


def _detail_out(db: Session, meeting: Meeting) -> MeetingDetailOut:
    summary, decisions, actions = meetings_repo.analysis_payload(db, meeting.meeting_id)
    task_map = tasks_repo.by_meeting(db, meeting.meeting_id)
    unique_actions: list = []
    seen: dict[str, int] = {}
    for row in actions:
        key = " ".join((row.description or "").lower().split())
        if not key:
            continue
        prev = seen.get(key)
        if prev is None:
            seen[key] = len(unique_actions)
            unique_actions.append(row)
            continue
        prev_row = unique_actions[prev]
        if row.seq in task_map and prev_row.seq not in task_map:
            unique_actions[prev] = row

    by_seq = {item.seq: item for item in meeting.transcripts}
    decision_out: list[DecisionOut] = []
    for row in decisions:
        if isinstance(row, str):
            text = row
            start_hint = None
            end_hint = None
        else:
            text = row.text
            start_hint = row.source_seq
            end_hint = getattr(row, "source_end_seq", None)
        start_seq, end_seq = match_decision_span(text, meeting.transcripts, start_hint, end_hint)
        start_line = by_seq.get(start_seq) if start_seq is not None else None
        end_line = by_seq.get(end_seq) if end_seq is not None else start_line
        decision_out.append(
            DecisionOut(
                seq=None if isinstance(row, str) else row.seq,
                text=text,
                source_seq=start_line.seq if start_line else None,
                source_end_seq=end_line.seq if end_line else None,
                timestamp=start_line.timestamp if start_line else None,
                end_timestamp=end_line.timestamp if end_line else None,
                speaker=start_line.speaker if start_line else None,
            )
        )

    return MeetingDetailOut(
        meeting_id=meeting.meeting_id,
        title=meeting.title,
        date=meeting.date,
        status=meeting.status,
        duration=meeting.duration,
        attendees=meetings_repo.display_attendees(meeting, meeting.transcripts),
        named_attendees=meeting.named_attendees,
        description=meeting.description,
        language=getattr(meeting, "language", None) or "tr",
        audio_path=meeting.audio_path,
        transcript=[
            TranscriptLineOut(
                seq=row.seq,
                timestamp=row.timestamp,
                text=row.text,
                speaker=row.speaker,
                speaker_origin=row.speaker_origin,
                flags=meetings_repo.parse_flags(getattr(row, "flags", None)),
            )
            for row in meeting.transcripts
        ],
        summary=summary,
        decisions=decision_out,
        actions=[
            ActionOut(
                seq=row.seq,
                description=row.description,
                assignee=row.assignee,
                assignee_id=row.assignee_id,
                due_date=row.due_date.isoformat() if row.due_date else None,
                notes=row.notes or "",
                task_status=task_map[row.seq].status if row.seq in task_map else None,
            )
            for row in unique_actions
        ],
        people=people_repo.list_out_for_meeting(db, meeting.user_id, meeting.meeting_id),
        transcription=_progress_out(meeting),
    )


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


@router.post("/{meeting_id}/analyze", response_model=MeetingDetailOut)
def retry_analysis(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingDetailOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    if meeting.status not in {"transcribed", "analyzed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Analiz için önce transkript gerekir",
        )
    _analysis_failed.pop(meeting_id, None)
    _analysis_retry_at.pop(meeting_id, None)
    meeting.analysis_error = None
    db.commit()
    schedule_analysis(meeting_id)
    return _detail_out(db, meeting)


@router.get("", response_model=MeetingListOut)
def list_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingListOut:
    items = meetings_repo.list_for_user(db, current_user.user_id)
    return MeetingListOut(
        items=[
            MeetingOut.model_validate(item).model_copy(
                update={"attendees": meetings_repo.display_attendees(item)}
            )
            for item in items
        ]
    )


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    title: str = Form(..., min_length=1, max_length=255),
    date: str = Form(...),
    attendees: str = Form(""),
    description: str = Form(""),
    language: str = Form("tr"),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingOut:
    filename = audio.filename or ""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Dosya boş")

    try:
        audio_path = save_audio(current_user.user_id, filename, data)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    named = attendees.strip() or None
    meeting = meetings_repo.create_meeting(
        db,
        user_id=current_user.user_id,
        title=title.strip(),
        date=_reject_future_meeting(_parse_date(date)),
        attendees=named,
        named_attendees=named,
        description=description.strip() or None,
        language=language,
        audio_path=audio_path,
    )
    schedule_transcription(meeting.meeting_id)
    return MeetingOut.model_validate(meeting)


@router.patch("/{meeting_id}/speakers", response_model=MeetingDetailOut)
def rename_speaker(
    meeting_id: int,
    body: SpeakerRenameIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingDetailOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")

    if body.action in {"confirm", "reject"}:
        pending = (body.from_speaker or body.speaker or "").strip()
        if not pending:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Onaylanacak konuşmacı adı gerekli",
            )
        meeting = meetings_repo.resolve_speaker_guess(
            db, meeting, pending, confirm=body.action == "confirm"
        )
        return _detail_out(db, meeting)

    speaker = (body.speaker or "").strip()
    if not speaker:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Konuşmacı adı boş olamaz")

    if body.seq is not None:
        meeting = meetings_repo.rename_speaker_line(db, meeting, body.seq, speaker)
        if meeting is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transkript satırı bulunamadı")
        return _detail_out(db, meeting)

    from_speaker = (body.from_speaker or "").strip()
    if not from_speaker:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Satır veya mevcut konuşmacı adı gerekli",
        )
    meeting = meetings_repo.rename_speaker_all(db, meeting, from_speaker, speaker)
    return _detail_out(db, meeting)


@router.patch("/{meeting_id}/transcript", response_model=MeetingDetailOut)
def edit_transcript_line(
    meeting_id: int,
    body: TranscriptEditIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingDetailOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Metin boş olamaz")
    meeting = meetings_repo.update_transcript_text(
        db, meeting, body.seq, text, flags=[item.model_dump() for item in body.flags] if body.flags is not None else None
    )
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transkript satırı bulunamadı")
    return _detail_out(db, meeting)


@router.get("/{meeting_id}/audio")
def get_meeting_audio(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FileResponse:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    if not meeting.audio_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ses kaydı bulunamadı")
    path = absolute_audio_path(meeting.audio_path)
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ses kaydı bulunamadı")
    media_type = AUDIO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(
        path,
        media_type=media_type,
        filename=path.name,
        content_disposition_type="inline",
    )


@router.get("/{meeting_id}", response_model=MeetingDetailOut)
def get_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingDetailOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    job = get_job(meeting.meeting_id)
    if meeting.status == "uploaded" and (job is None or job.state != "running"):
        schedule_transcription(meeting.meeting_id)
    elif meeting.status == "transcribed":
        persisted = (meeting.analysis_error or "").strip()
        if persisted:
            _analysis_failed.setdefault(meeting.meeting_id, persisted)
        if not meeting.speakers_matched:
            schedule_speaker_match(meeting.meeting_id)
    return _detail_out(db, meeting)


@router.patch("/{meeting_id}", response_model=MeetingOut)
def update_meeting(
    meeting_id: int,
    body: MeetingUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")

    title = body.title.strip() if body.title is not None else None
    parsed_date = _reject_future_meeting(_parse_date(body.date)) if body.date else None
    named_set = "named_attendees" in body.model_fields_set or "attendees" in body.model_fields_set
    named = None
    if named_set:
        raw = body.named_attendees if "named_attendees" in body.model_fields_set else body.attendees
        named = (raw or "").strip() or None
    description_set = "description" in body.model_fields_set
    description = (body.description or "").strip() or None if description_set else None

    meeting = meetings_repo.update_meeting(
        db,
        meeting,
        title=title,
        date=parsed_date,
        named_attendees=named,
        named_attendees_set=named_set,
        description=description,
        description_set=description_set,
    )
    if named_set and meeting.status in {"transcribed", "analyzed"}:
        schedule_speaker_match(meeting_id)
    if body.dismiss_action is not None:
        if not meetings_repo.dismiss_action(db, meeting, body.dismiss_action):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aksiyon bulunamadı")
    if body.update_transcript is not None:
        text = body.update_transcript.text.strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Metin boş olamaz")
        updated_line = meetings_repo.update_transcript_text(
            db,
            meeting,
            body.update_transcript.seq,
            text,
            flags=[item.model_dump() for item in body.update_transcript.flags]
            if body.update_transcript.flags is not None
            else None,
        )
        if updated_line is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transkript satırı bulunamadı")
        meeting = updated_line
    if body.update_action is not None:
        patch = body.update_action
        due_set = "due_date" in patch.model_fields_set
        due: date | None = None
        if due_set and patch.due_date:
            try:
                due = date.fromisoformat(patch.due_date[:10])
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Tarih biçimi geçersiz",
                ) from exc
        updated = meetings_repo.update_action(
            db,
            meeting,
            patch.seq,
            description=patch.description.strip() if patch.description is not None else None,
            assignee_set="assignee" in patch.model_fields_set or "assignee_id" in patch.model_fields_set,
            assignee=patch.assignee.strip() or None if patch.assignee is not None else None,
            assignee_id=patch.assignee_id,
            due_date_set=due_set,
            due_date=due,
            notes_set="notes" in patch.model_fields_set,
            notes=patch.notes,
        )
        if updated is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aksiyon bulunamadı")
    if "summary" in body.model_fields_set and body.summary is not None:
        meetings_repo.update_summary(db, meeting, body.summary)
    if body.update_decision is not None:
        text = body.update_decision.text.strip()
        if not text:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Karar boş olamaz")
        updated_decision = meetings_repo.update_decision(
            db,
            meeting,
            body.update_decision.seq,
            text,
        )
        if updated_decision is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Karar bulunamadı")
    if body.analyze:
        if meeting.status not in {"transcribed", "analyzed"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analiz için önce transkript gerekir",
            )
        _analysis_failed.pop(meeting_id, None)
        _analysis_retry_at.pop(meeting_id, None)
        meeting.analysis_error = None
        db.commit()
        schedule_analysis(meeting_id)
    return MeetingOut.model_validate(meeting)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    audio_path = meeting.audio_path
    cancel_transcription(meeting_id, audio_path)
    meetings_repo.delete_meeting(db, meeting)
    delete_audio(audio_path)
