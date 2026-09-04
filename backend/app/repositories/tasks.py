from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.action import Action
from app.models.analysis import Analysis
from app.models.meeting import Meeting
from app.models.task import Task


def list_for_user(db: Session, user_id: int) -> list[tuple[Task, str, str, str | None]]:
    stmt = (
        select(Task, Meeting.title, Action.description, Action.notes)
        .join(Meeting, Meeting.meeting_id == Task.meeting_id)
        .join(Action, (Action.meeting_id == Task.meeting_id) & (Action.seq == Task.action_seq))
        .where(Meeting.user_id == user_id)
        .order_by(Task.due_date.asc().nullslast(), Task.meeting_id.desc())
    )
    return list(db.execute(stmt).all())


def list_suggestions_for_user(db: Session, user_id: int) -> list[tuple[Action, str]]:
    stmt = (
        select(Action, Meeting.title)
        .join(Meeting, Meeting.meeting_id == Action.meeting_id)
        .outerjoin(Task, (Task.meeting_id == Action.meeting_id) & (Task.action_seq == Action.seq))
        .where(
            Meeting.user_id == user_id,
            Action.dismissed.is_(False),
            Task.meeting_id.is_(None),
        )
        .order_by(Meeting.date.desc().nullslast(), Action.seq)
    )
    return list(db.execute(stmt).all())


def get_for_user(db: Session, user_id: int, meeting_id: int, action_seq: int) -> Task | None:
    task = db.get(Task, (meeting_id, action_seq))
    if task is None:
        return None
    meeting = db.get(Meeting, meeting_id)
    if meeting is None or meeting.user_id != user_id:
        return None
    return task


def meeting_title(db: Session, meeting_id: int) -> str:
    meeting = db.get(Meeting, meeting_id)
    return meeting.title if meeting else ""


def action_description(db: Session, meeting_id: int, seq: int) -> str:
    action = db.get(Action, (meeting_id, seq))
    return action.description if action else ""


def action_notes(db: Session, meeting_id: int, seq: int) -> str:
    action = db.get(Action, (meeting_id, seq))
    return (action.notes or "") if action else ""


def _ensure_analysis(db: Session, meeting_id: int) -> None:
    if db.get(Analysis, meeting_id) is None:
        db.add(Analysis(meeting_id=meeting_id, summary="(manuel görevler)"))
        db.flush()


def _next_seq(db: Session, meeting_id: int) -> int:
    current = db.scalar(select(func.max(Action.seq)).where(Action.meeting_id == meeting_id))
    return int(current or 0) + 1


def create_for_meeting(
    db: Session,
    *,
    meeting: Meeting,
    title: str,
    assignee: str | None,
    assignee_id: int | None = None,
    speaker_label: str | None = None,
    due_date: date | None,
    description: str,
) -> Task:
    from app.repositories import people as people_repo

    _ensure_analysis(db, meeting.meeting_id)
    name, person_id = people_repo.resolve_assignee(
        db,
        user_id=meeting.user_id,
        meeting=meeting,
        assignee_id=assignee_id,
        assignee_name=assignee,
        speaker_label=speaker_label,
    )
    seq = _next_seq(db, meeting.meeting_id)
    db.add(
        Action(
            meeting_id=meeting.meeting_id,
            seq=seq,
            description=description or title,
            assignee=name,
            assignee_id=person_id,
            due_date=due_date,
        )
    )
    db.flush()
    task = Task(
        meeting_id=meeting.meeting_id,
        action_seq=seq,
        title=title,
        status="in_progress",
        assignee=name,
        assignee_id=person_id,
        due_date=due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def create_from_action(
    db: Session,
    *,
    meeting: Meeting,
    action: Action,
    title: str,
    assignee: str | None,
    assignee_id: int | None = None,
    speaker_label: str | None = None,
    due_date: date | None,
) -> Task:
    from app.repositories import people as people_repo

    existing = db.get(Task, (meeting.meeting_id, action.seq))
    if existing is not None:
        return existing
    if assignee_id is not None or (assignee or "").strip():
        name, person_id = people_repo.resolve_assignee(
            db,
            user_id=meeting.user_id,
            meeting=meeting,
            assignee_id=assignee_id,
            assignee_name=assignee,
            speaker_label=speaker_label,
        )
    else:
        name, person_id = action.assignee, action.assignee_id
    action.assignee = name
    action.assignee_id = person_id
    if due_date is not None:
        action.due_date = due_date
    task = Task(
        meeting_id=meeting.meeting_id,
        action_seq=action.seq,
        title=title,
        status="in_progress",
        assignee=name,
        assignee_id=person_id,
        due_date=due_date or action.due_date,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def by_meeting(db: Session, meeting_id: int) -> dict[int, Task]:
    rows = db.scalars(select(Task).where(Task.meeting_id == meeting_id)).all()
    return {row.action_seq: row for row in rows}


def update_task(
    db: Session,
    task: Task,
    *,
    title: str | None = None,
    status: str | None = None,
    assignee_set: bool = False,
    assignee: str | None = None,
    assignee_id: int | None = None,
    speaker_label: str | None = None,
    due_date_set: bool = False,
    due_date: date | None = None,
    description: str | None = None,
) -> Task:
    if title is not None:
        task.title = title
    if status is not None:
        task.status = status
    if assignee_set:
        from app.models.meeting import Meeting
        from app.repositories import people as people_repo

        meeting = db.get(Meeting, task.meeting_id)
        if meeting is not None:
            name, person_id = people_repo.resolve_assignee(
                db,
                user_id=meeting.user_id,
                meeting=meeting,
                assignee_id=assignee_id,
                assignee_name=assignee,
                speaker_label=speaker_label,
            )
            task.assignee = name
            task.assignee_id = person_id
            action = db.get(Action, (task.meeting_id, task.action_seq))
            if action is not None:
                action.assignee = name
                action.assignee_id = person_id
        else:
            task.assignee = assignee
    if due_date_set:
        task.due_date = due_date
        action = db.get(Action, (task.meeting_id, task.action_seq))
        if action is not None:
            action.due_date = due_date
    if description is not None:
        action = db.get(Action, (task.meeting_id, task.action_seq))
        if action is not None:
            action.description = description
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, task: Task) -> None:
    action = db.get(Action, (task.meeting_id, task.action_seq))
    db.delete(task)
    if action is not None:
        action.dismissed = True
    db.commit()
