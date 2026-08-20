from datetime import date, datetime
import json
import logging

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

logger = logging.getLogger(__name__)


def parse_flags(raw: str | None) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    flags: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        original = str(item.get("original") or "").strip()
        suggestion = str(item.get("suggestion") or "").strip()
        if not original or not suggestion:
            continue
        flags.append(
            {
                "original": original,
                "suggestion": suggestion,
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    return flags


def dump_flags(flags: list[dict[str, str]] | None) -> str | None:
    cleaned = parse_flags(json.dumps(flags, ensure_ascii=False)) if flags else []
    return json.dumps(cleaned, ensure_ascii=False) if cleaned else None


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
                speaker_origin=segment.speaker,
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
    row.speaker_origin = None
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
            row.speaker_origin = None
    _apply_attendees(meeting, meeting.transcripts)
    from app.repositories import people as people_repo

    people_repo.rename_speaker_person(db, meeting, from_speaker, speaker)
    db.commit()
    db.refresh(meeting)
    return meeting


def apply_speaker_map(db: Session, meeting: Meeting, mapping: dict[str, str] | None = None) -> Meeting:
    mapping = {key: _strip_guess_mark(value) for key, value in (mapping or {}).items()}
    from app.services.speakers import is_generic_label

    for row in meeting.transcripts:
        speaker = (row.speaker or "").strip()
        if is_generic_label(speaker) and speaker in mapping:
            if not row.speaker_origin:
                row.speaker_origin = speaker
            row.speaker = mapping[speaker]
        elif speaker.endswith("?"):
            row.speaker = _strip_guess_mark(speaker)
    _apply_attendees(meeting, meeting.transcripts)
    from app.repositories import people as people_repo

    people_repo.sync_speakers_for_meeting(db, meeting, meeting.transcripts, commit=False)
    db.commit()
    db.refresh(meeting)
    return meeting


def fix_transcript_sentence_i(db: Session, meeting: Meeting) -> Meeting:
    from app.services.turkish import fix_sentence_i

    changed = False
    for row in meeting.transcripts:
        text = row.text or ""
        fixed = fix_sentence_i(text)
        if fixed != text:
            row.text = fixed
            changed = True
    if not changed:
        return meeting
    db.commit()
    db.refresh(meeting)
    return meeting


def _strip_guess_mark(name: str) -> str:
    return name.strip().removesuffix("?").strip()


def resolve_speaker_guess(db: Session, meeting: Meeting, pending_name: str, *, confirm: bool) -> Meeting:
    target = pending_name.strip()
    if not target:
        return meeting
    for row in meeting.transcripts:
        speaker = (row.speaker or "").strip()
        if speaker != target:
            continue
        origin = (row.speaker_origin or "").strip()
        if confirm:
            row.speaker = _strip_guess_mark(speaker)
        else:
            row.speaker = origin or speaker
        row.speaker_origin = None
    _apply_attendees(meeting, meeting.transcripts)
    from app.repositories import people as people_repo

    people_repo.sync_speakers_for_meeting(db, meeting, meeting.transcripts, commit=False)
    db.commit()
    db.refresh(meeting)
    return meeting


def update_transcript_text(
    db: Session,
    meeting: Meeting,
    seq: int,
    text: str,
    flags: list[dict[str, str]] | None = None,
) -> Meeting | None:
    row = db.get(Transcript, (meeting.meeting_id, seq))
    if row is None:
        return None
    row.text = text
    if flags is not None:
        row.flags = dump_flags(flags)
    else:
        kept = [item for item in parse_flags(row.flags) if item["original"] in text]
        row.flags = dump_flags(kept)
    db.commit()
    return get_for_user(db, meeting.user_id, meeting.meeting_id) or meeting


def apply_transcript_review(db: Session, meeting: Meeting, items: list) -> Meeting:
    from app.services.transcript_review import is_case_only, replace_ci

    by_seq = {row.seq: row for row in meeting.transcripts}
    for item in items:
        row = by_seq.get(item.seq)
        if row is None:
            continue
        original = item.original.strip()
        suggestion = item.suggestion.strip()
        if item.kind == "proper_name" or is_case_only(original, suggestion):
            updated = replace_ci(row.text, original, suggestion)
            if updated is not None:
                from app.services.turkish import fix_sentence_i

                row.text = fix_sentence_i(updated)
            continue
        flags = parse_flags(row.flags)
        if any(flag["original"] == original for flag in flags):
            continue
        flags.append(
            {
                "original": original,
                "suggestion": suggestion,
                "reason": (item.reason or "").strip(),
            }
        )
        row.flags = dump_flags(flags)
    db.commit()
    db.refresh(meeting)
    return meeting


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

    existing = list(
        db.scalars(select(Action).where(Action.meeting_id == meeting.meeting_id).order_by(Action.seq)).all()
    )
    task_seqs = set(
        db.scalars(select(Task.action_seq).where(Task.meeting_id == meeting.meeting_id)).all()
    )
    keep_seqs = {row.seq for row in existing if row.dismissed or row.seq in task_seqs}
    for row in existing:
        if row.seq not in keep_seqs:
            db.delete(row)
    db.flush()
    existing_keys = {
        " ".join((row.description or "").lower().split())
        for row in existing
        if row.seq in keep_seqs
    }

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
    logger.warning(
        "Replaced analysis for meeting %s: decisions=%s actions_in=%s actions_saved=%s",
        meeting.meeting_id,
        len(result.decisions),
        len(result.actions),
        added,
    )
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
