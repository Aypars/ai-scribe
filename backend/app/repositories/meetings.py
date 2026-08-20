from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.action import Action
from app.models.analysis import Analysis
from app.models.decision import Decision
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.transcript import Transcript
from app.services.analysis import AnalysisResult
from app.services.transcription import TranscriptSegment


def speaker_names(rows: list) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        name = (getattr(row, "speaker", None) or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def attendees_from_speakers(rows: list) -> str | None:
    names = speaker_names(rows)
    return ", ".join(names) if names else None


def _apply_attendees(meeting: Meeting, rows: list) -> None:
    joined = attendees_from_speakers(rows)
    if joined:
        meeting.attendees = joined


def list_for_user(db: Session, user_id: int) -> list[Meeting]:
    stmt = (
        select(Meeting)
        .where(Meeting.user_id == user_id)
        .order_by(Meeting.date.desc().nullslast(), Meeting.meeting_id.desc())
    )
    items = list(db.scalars(stmt).all())
    if not items:
        return items
    ids = [item.meeting_id for item in items]
    rows = db.execute(
        select(Transcript.meeting_id, Transcript.speaker)
        .where(Transcript.meeting_id.in_(ids))
        .order_by(Transcript.meeting_id, Transcript.seq)
    ).all()
    grouped: dict[int, list[str]] = {}
    seen: dict[int, set[str]] = {}
    for meeting_id, speaker in rows:
        name = (speaker or "").strip()
        if not name:
            continue
        used = seen.setdefault(meeting_id, set())
        if name in used:
            continue
        used.add(name)
        grouped.setdefault(meeting_id, []).append(name)
    dirty = False
    for item in items:
        names = grouped.get(item.meeting_id)
        if not names:
            continue
        joined = ", ".join(names)
        if item.attendees != joined:
            item.attendees = joined
            dirty = True
    if dirty:
        db.commit()
    return items


def get_for_user(db: Session, user_id: int, meeting_id: int) -> Meeting | None:
    stmt = (
        select(Meeting)
        .options(selectinload(Meeting.transcripts))
        .where(Meeting.meeting_id == meeting_id, Meeting.user_id == user_id)
    )
    return db.scalars(stmt).first()


def create_meeting(
    db: Session,
    *,
    user_id: int,
    title: str,
    date: datetime | None,
    attendees: str | None,
    description: str | None,
    audio_path: str,
) -> Meeting:
    meeting = Meeting(
        user_id=user_id,
        title=title,
        date=date,
        status="uploaded",
        attendees=attendees,
        description=description,
        audio_path=audio_path,
    )
    db.add(meeting)
    db.commit()
    db.refresh(meeting)
    return meeting


def update_meeting(
    db: Session,
    meeting: Meeting,
    *,
    title: str | None = None,
    date: datetime | None = None,
    attendees: str | None = None,
    attendees_set: bool = False,
    description: str | None = None,
    description_set: bool = False,
) -> Meeting:
    if title is not None:
        meeting.title = title
    if date is not None:
        meeting.date = date
    if attendees_set:
        meeting.attendees = attendees
    if description_set:
        meeting.description = description
    db.commit()
    db.refresh(meeting)
    return meeting


def delete_meeting(db: Session, meeting: Meeting) -> None:
    db.delete(meeting)
    db.commit()


def replace_transcript(
    db: Session,
    meeting: Meeting,
    segments: list[TranscriptSegment],
    duration_seconds: int,
) -> Meeting:
    db.execute(delete(Transcript).where(Transcript.meeting_id == meeting.meeting_id))
    for seq, segment in enumerate(segments, start=1):
        db.add(
            Transcript(
                meeting_id=meeting.meeting_id,
                seq=seq,
                text=segment.text,
                timestamp=segment.timestamp,
                speaker=segment.speaker,
            )
        )
    _apply_attendees(meeting, segments)
    meeting.duration = duration_seconds
    meeting.status = "transcribed"
    from app.repositories import people as people_repo

    people_repo.sync_speakers_for_meeting(db, meeting, segments, commit=False)
    db.commit()
    db.refresh(meeting)
    return meeting


def mark_failed(db: Session, meeting: Meeting) -> Meeting:
    meeting.status = "failed"
    db.commit()
    db.refresh(meeting)
    return meeting


def rename_speaker_line(db: Session, meeting: Meeting, seq: int, speaker: str) -> Meeting | None:
    row = next((item for item in meeting.transcripts if item.seq == seq), None)
    if row is None:
        return None
    row.speaker = speaker
    _apply_attendees(meeting, meeting.transcripts)
    from app.repositories import people as people_repo

    people_repo.sync_speakers_for_meeting(db, meeting, meeting.transcripts, commit=False)
    db.commit()
    db.refresh(meeting)
    return meeting


def rename_speaker_all(db: Session, meeting: Meeting, from_speaker: str, speaker: str) -> Meeting:
    for row in meeting.transcripts:
        if row.speaker == from_speaker:
            row.speaker = speaker
    _apply_attendees(meeting, meeting.transcripts)
    from app.repositories import people as people_repo

    people_repo.rename_speaker_person(db, meeting, from_speaker, speaker)
    db.commit()
    db.refresh(meeting)
    return meeting


def update_transcript_text(db: Session, meeting: Meeting, seq: int, text: str) -> Meeting | None:
    row = db.get(Transcript, (meeting.meeting_id, seq))
    if row is None:
        return None
    row.text = text
    db.commit()
    return get_for_user(db, meeting.user_id, meeting.meeting_id) or meeting


def replace_analysis(db: Session, meeting: Meeting, result: AnalysisResult) -> Meeting:
    analysis = db.get(Analysis, meeting.meeting_id)
    if analysis is None:
        db.add(Analysis(meeting_id=meeting.meeting_id, summary=result.summary))
        db.flush()
    else:
        analysis.summary = result.summary

    db.execute(delete(Decision).where(Decision.meeting_id == meeting.meeting_id))
    for seq, item in enumerate(result.decisions, start=1):
        db.add(
            Decision(
                meeting_id=meeting.meeting_id,
                seq=seq,
                text=item.text,
                source_seq=item.source_seq,
                source_end_seq=item.source_end_seq,
            )
        )

    has_tasks = db.scalar(select(Task.meeting_id).where(Task.meeting_id == meeting.meeting_id).limit(1))
    existing = list(
        db.scalars(select(Action).where(Action.meeting_id == meeting.meeting_id).order_by(Action.seq)).all()
    )
    dismissed_keys = {
        " ".join((row.description or "").lower().split()) for row in existing if row.dismissed
    }
    existing_keys = {" ".join((row.description or "").lower().split()) for row in existing}

    if has_tasks is None:
        db.execute(
            delete(Action).where(Action.meeting_id == meeting.meeting_id, Action.dismissed.is_(False))
        )
        existing_keys = dismissed_keys

    current = db.scalar(
        select(Action.seq).where(Action.meeting_id == meeting.meeting_id).order_by(Action.seq.desc()).limit(1)
    )
    start = int(current or 0) + 1

    added = 0
    for item in result.actions:
        key = " ".join(item.description.lower().split())
        if not key or key in existing_keys:
            continue
        existing_keys.add(key)
        db.add(
            Action(
                meeting_id=meeting.meeting_id,
                seq=start + added,
                description=item.description,
                assignee=(item.assignee or "").strip() or None,
                due_date=item.due_date,
                notes=item.notes or None,
            )
        )
        added += 1

    meeting.status = "analyzed"
    db.commit()
    db.refresh(meeting)
    return meeting


def analysis_payload(db: Session, meeting_id: int) -> tuple[str | None, list[Decision], list[Action]]:
    analysis = db.get(Analysis, meeting_id)
    if analysis is None:
        return None, [], []
    summary = None if analysis.summary == "(manuel görevler)" else analysis.summary
    decisions = list(
        db.scalars(select(Decision).where(Decision.meeting_id == meeting_id).order_by(Decision.seq)).all()
    )
    actions = list(
        db.scalars(
            select(Action)
            .where(Action.meeting_id == meeting_id, Action.dismissed.is_(False))
            .order_by(Action.seq)
        ).all()
    )
    return summary, decisions, actions


def dismiss_action(db: Session, meeting: Meeting, seq: int) -> bool:
    action = db.get(Action, (meeting.meeting_id, seq))
    if action is None:
        return False
    action.dismissed = True
    task = db.get(Task, (meeting.meeting_id, seq))
    if task is not None:
        db.delete(task)
    db.commit()
    return True


def update_action(
    db: Session,
    meeting: Meeting,
    seq: int,
    *,
    description: str | None = None,
    assignee_set: bool = False,
    assignee: str | None = None,
    assignee_id: int | None = None,
    due_date_set: bool = False,
    due_date: date | None = None,
    notes_set: bool = False,
    notes: str | None = None,
) -> Action | None:
    action = db.get(Action, (meeting.meeting_id, seq))
    if action is None or action.dismissed:
        return None
    if description is not None:
        action.description = description
    if assignee_set:
        task = db.get(Task, (meeting.meeting_id, seq))
        if task is None:
            action.assignee = (assignee or "").strip() or None
            action.assignee_id = None
        else:
            from app.repositories import people as people_repo

            name, person_id = people_repo.resolve_assignee(
                db,
                user_id=meeting.user_id,
                meeting=meeting,
                assignee_id=assignee_id,
                assignee_name=assignee,
            )
            action.assignee = name
            action.assignee_id = person_id
            task.assignee = name
            task.assignee_id = person_id
    if due_date_set:
        action.due_date = due_date
    if notes_set:
        action.notes = notes or None
    db.commit()
    db.refresh(action)
    return action
