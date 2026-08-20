from datetime import date

from pydantic import BaseModel, Field

from app.schemas.person import PersonOut


class TaskOut(BaseModel):
    meeting_id: int
    action_seq: int
    title: str
    status: str
    assignee: str | None
    assignee_id: int | None = None
    due_date: date | None
    description: str
    notes: str = ""
    meeting_title: str


class SuggestionOut(BaseModel):
    meeting_id: int
    action_seq: int
    title: str
    assignee: str | None
    assignee_id: int | None = None
    due_date: date | None
    description: str
    meeting_title: str


class TaskListOut(BaseModel):
    items: list[TaskOut]
    suggestions: list[SuggestionOut] = []
    people: list[PersonOut] = []


class TaskCreate(BaseModel):
    meeting_id: int
    title: str = Field(min_length=1, max_length=255)
    assignee: str | None = None
    assignee_id: int | None = None
    due_date: date
    description: str = ""
    action_seq: int | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    assignee: str | None = None
    assignee_id: int | None = None
    due_date: date | None = None
    description: str | None = None
