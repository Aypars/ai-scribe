from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.action import Action
from app.models.task import Task
from app.models.user import User
from app.repositories import meetings as meetings_repo
from app.repositories import people as people_repo
from app.repositories import tasks as tasks_repo
from app.schemas.task import SuggestionOut, TaskCreate, TaskListOut, TaskOut, TaskUpdate

router = APIRouter()

ALLOWED_STATUS = {"in_progress", "done"}


def _reject_past_due(value: date | None, *, required: bool) -> date | None:
    if value is None:
        if required:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Teslim tarihi gerekli",
            )
        return None
    if value < date.today():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Teslim tarihi geçmiş olamaz",
        )
    return value


def _to_out(task: Task, meeting_title: str, description: str, notes: str | None = None) -> TaskOut:
    return TaskOut(
        meeting_id=task.meeting_id,
        action_seq=task.action_seq,
        title=task.title,
        status=task.status,
        assignee=task.assignee,
        assignee_id=task.assignee_id,
        due_date=task.due_date,
        description=description,
        notes=notes or "",
        meeting_title=meeting_title,
    )


@router.get("", response_model=TaskListOut)
def list_tasks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskListOut:
    rows = tasks_repo.list_for_user(db, current_user.user_id)
    suggestions = tasks_repo.list_suggestions_for_user(db, current_user.user_id)
    return TaskListOut(
        items=[_to_out(task, meeting_title, description, notes) for task, meeting_title, description, notes in rows],
        suggestions=[
            SuggestionOut(
                meeting_id=action.meeting_id,
                action_seq=action.seq,
                title=action.description,
                assignee=action.assignee,
                assignee_id=action.assignee_id,
                due_date=action.due_date,
                description=action.notes or "",
                meeting_title=meeting_title,
            )
            for action, meeting_title in suggestions
        ],
        people=people_repo.list_out_for_user(db, current_user.user_id),
    )


@router.post("", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(
    body: TaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskOut:
    meeting = meetings_repo.get_for_user(db, current_user.user_id, body.meeting_id)
    if meeting is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Toplantı bulunamadı")
    due = _reject_past_due(body.due_date, required=True)

    if body.action_seq is not None:
        action = db.get(Action, (meeting.meeting_id, body.action_seq))
        if action is None or action.dismissed:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aksiyon bulunamadı")
        existing = db.get(Task, (meeting.meeting_id, body.action_seq))
        if existing is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Bu aksiyon zaten görev")
        task = tasks_repo.create_from_action(
            db,
            meeting=meeting,
            action=action,
            title=body.title.strip(),
            assignee=body.assignee.strip() if body.assignee else None,
            assignee_id=body.assignee_id,
            speaker_label=body.speaker_label,
            due_date=due,
        )
        return _to_out(task, meeting.title, action.description, action.notes)

    task = tasks_repo.create_for_meeting(
        db,
        meeting=meeting,
        title=body.title.strip(),
        assignee=body.assignee.strip() if body.assignee else None,
        assignee_id=body.assignee_id,
        speaker_label=body.speaker_label,
        due_date=due,
        description=body.description.strip(),
    )
    return _to_out(task, meeting.title, body.description.strip() or task.title, body.description.strip())


@router.patch("/{meeting_id}/{action_seq}", response_model=TaskOut)
def update_task(
    meeting_id: int,
    action_seq: int,
    body: TaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TaskOut:
    task = tasks_repo.get_for_user(db, current_user.user_id, meeting_id, action_seq)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Görev bulunamadı")
    if body.status is not None and body.status not in ALLOWED_STATUS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Geçersiz durum")
    due = task.due_date
    if "due_date" in body.model_fields_set:
        if body.due_date is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Teslim tarihi gerekli",
            )
        if body.due_date != task.due_date:
            due = _reject_past_due(body.due_date, required=True)

    task = tasks_repo.update_task(
        db,
        task,
        title=body.title.strip() if body.title is not None else None,
        status=body.status,
        assignee_set="assignee" in body.model_fields_set or "assignee_id" in body.model_fields_set,
        assignee=body.assignee.strip() or None if body.assignee is not None else None,
        assignee_id=body.assignee_id,
        speaker_label=body.speaker_label,
        due_date_set="due_date" in body.model_fields_set,
        due_date=due,
        description=body.description,
    )
    return _to_out(
        task,
        tasks_repo.meeting_title(db, task.meeting_id),
        tasks_repo.action_description(db, task.meeting_id, task.action_seq),
        tasks_repo.action_notes(db, task.meeting_id, task.action_seq),
    )


@router.delete("/{meeting_id}/{action_seq}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    meeting_id: int,
    action_seq: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    task = tasks_repo.get_for_user(db, current_user.user_id, meeting_id, action_seq)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Görev bulunamadı")
    tasks_repo.delete_task(db, task)
