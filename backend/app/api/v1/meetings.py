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
from app.services.storage import (
    AUDIO_MEDIA_TYPES,
    StorageError,
    absolute_audio_path,
    delete_audio,
    save_audio,
)
from app.services.transcription import (
    TranscriptionCancelled,
    cancel_transcription,
    clear_transcription,
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
_analysis_failed: dict[int, str] = {}
_analysis_retry_at: dict[int, float] = {}
_analysis_message: dict[int, str] = {}
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
    if meeting.status == "transcribed":
        err = _analysis_failed.get(meeting.meeting_id)
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
        attendees=meetings_repo.attendees_from_speakers(meeting.transcripts) or meeting.attendees,
        description=meeting.description,
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
    try:
        meeting = db.get(Meeting, meeting_id)
        if meeting is not None and meeting.audio_path:
            path = absolute_audio_path(meeting.audio_path)
        else:
            fail_job(meeting_id, "Toplantı veya ses dosyası bulunamadı")
    finally:
        db.close()

    if path is None:
        with _running_lock:
            _running.discard(meeting_id)
        return

    db = None
    try:
        logger.warning("Whisper job started for meeting %s (%s)", meeting_id, path)
        result = transcribe_audio(
            path,
            on_progress=lambda progress, message: update_job(
                meeting_id, progress=progress, message=message
            ),
            meeting_id=meeting_id,
        )
        db = SessionLocal()
        meeting = db.get(Meeting, meeting_id)
        if meeting is None:
            fail_job(meeting_id, "Toplantı bulunamadı")
            return
        meetings_repo.replace_transcript(db, meeting, result.segments, result.duration_seconds)
        meeting = meetings_repo.get_for_user(db, meeting.user_id, meeting_id) or meeting
        logger.warning("Whisper job finished for meeting %s", meeting_id)
        _run_analysis(db, meeting)
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
    meeting_date = meeting.date.isoformat() if meeting.date else None
    description = meeting.description
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
            on_busy=lambda wait: _analysis_message.__setitem__(
                meeting_id, f"Gemini yoğun, {wait} sn sonra tekrar…"
            ),
        )
        meeting = meetings_repo.get_for_user(db, user_id, meeting_id) or meeting
        meetings_repo.replace_analysis(db, meeting, result)
        logger.warning("Gemini analysis finished for meeting %s", meeting_id)
    except AnalysisError as exc:
        logger.exception("Gemini analysis failed for meeting %s", meeting.meeting_id)
        _analysis_failed[meeting.meeting_id] = str(exc)
        if _is_transient_gemini(str(exc)):
            _analysis_retry_at[meeting.meeting_id] = time.time() + 20
        return
    except Exception as exc:
        logger.exception("Gemini analysis failed for meeting %s", meeting.meeting_id)
        _analysis_failed[meeting.meeting_id] = str(exc) or "Analiz başarısız"
        return
    finally:
        _analyzing.discard(meeting.meeting_id)
        _analysis_message.pop(meeting.meeting_id, None)


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
        if meeting_id in _analyzing or meeting_id in _running:
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
    schedule_analysis(meeting_id)
    return _detail_out(db, meeting)


@router.get("", response_model=MeetingListOut)
def list_meetings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingListOut:
    items = meetings_repo.list_for_user(db, current_user.user_id)
    return MeetingListOut(items=[MeetingOut.model_validate(item) for item in items])


@router.post("", response_model=MeetingOut, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    title: str = Form(..., min_length=1, max_length=255),
    date: str = Form(...),
    attendees: str = Form(""),
    description: str = Form(""),
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingOut:
    filename = audio.filename or ""
    data = await audio.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ses dosyası boş")

    try:
        audio_path = save_audio(current_user.user_id, filename, data)
    except StorageError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    meeting = meetings_repo.create_meeting(
        db,
        user_id=current_user.user_id,
        title=title.strip(),
        date=_reject_future_meeting(_parse_date(date)),
        attendees=attendees.strip() or None,
        description=description.strip() or None,
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
    joined = meetings_repo.attendees_from_speakers(meeting.transcripts)
    if joined and meeting.attendees != joined:
        meeting.attendees = joined
        db.commit()
    job = get_job(meeting.meeting_id)
    if meeting.status == "uploaded" and (job is None or job.state != "running"):
        schedule_transcription(meeting.meeting_id)
    elif meeting.status == "transcribed":
        schedule_analysis(meeting.meeting_id)
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
    attendees_set = False
    attendees = None
    description_set = "description" in body.model_fields_set
    description = (body.description or "").strip() or None if description_set else None

    meeting = meetings_repo.update_meeting(
        db,
        meeting,
        title=title,
        date=parsed_date,
        attendees=attendees,
        attendees_set=attendees_set,
        description=description,
        description_set=description_set,
    )
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
    if body.analyze:
        if meeting.status not in {"transcribed", "analyzed"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Analiz için önce transkript gerekir",
            )
        _analysis_failed.pop(meeting_id, None)
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
