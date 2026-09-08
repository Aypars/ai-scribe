import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.meeting import Meeting
from app.models.user import User
from app.repositories import meetings as meetings_repo
from app.repositories import people as people_repo
from app.repositories import tasks as tasks_repo
from app.schemas.meeting import (
    ActionOut,
    AskCiteOut,
    AskIn,
    AskOut,
    DecisionOut,
    MeetingDetailOut,
    MeetingListOut,
    MeetingOut,
    MeetingUpdate,
    SpeakerRenameIn,
    TranscriptEditIn,
    TranscriptLineOut,
    TranscriptMergeIn,
)
from app.services.analysis import match_decision_span
from app.services.meeting_jobs import (
    clear_analysis_failure,
    progress_out,
    remember_analysis_error,
    schedule_analysis,
    schedule_speaker_match,
    schedule_transcription,
)
from app.services.ask import AskError, ask_transcript
from app.services.storage import (
    AUDIO_MEDIA_TYPES,
    StorageError,
    absolute_audio_path,
    delete_audio,
    save_audio,
)
from app.services.transcription import cancel_transcription, get_job, playback_audio_path

logger = logging.getLogger(__name__)

router = APIRouter()

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
        transcription=progress_out(meeting),
    )


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
    clear_analysis_failure(meeting_id)
    meeting.analysis_error = None
    db.commit()
    schedule_analysis(meeting_id)
    return _detail_out(db, meeting)


@router.post("/{meeting_id}/ask", response_model=AskOut)
def ask_meeting(
    meeting_id: int,
    body: AskIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AskOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    if not meeting.transcripts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Soru için önce transkript gerekir",
        )
    try:
        result = ask_transcript(
            list(meeting.transcripts),
            body.question,
            language=getattr(meeting, "language", None),
        )
    except AskError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    return AskOut(
        answer=result.answer,
        cites=[
            AskCiteOut(seq=row.seq, timestamp=row.timestamp, speaker=row.speaker, text=row.text)
            for row in result.cites
        ],
    )


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
    try:
        meeting = meetings_repo.rename_speaker_all(db, meeting, from_speaker, speaker)
    except people_repo.PersonNameConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.detail) from exc
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


@router.post("/{meeting_id}/transcript/merge", response_model=MeetingDetailOut)
def merge_transcript_line(
    meeting_id: int,
    body: TranscriptMergeIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MeetingDetailOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    meeting = meetings_repo.merge_transcript_with_next(db, meeting, body.seq)
    if meeting is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Birleştirilecek sonraki satır yok",
        )
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
    path = playback_audio_path(path)
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
    if meeting.transcripts:
        meeting = meetings_repo.smooth_transcript_if_needed(db, meeting)
    job = get_job(meeting.meeting_id)
    if meeting.status == "uploaded" and (job is None or job.state != "running"):
        schedule_transcription(meeting.meeting_id)
    elif meeting.status == "transcribed":
        persisted = (meeting.analysis_error or "").strip()
        if persisted:
            remember_analysis_error(meeting.meeting_id, persisted)
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
            speaker_label=patch.speaker_label,
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
        clear_analysis_failure(meeting_id)
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
