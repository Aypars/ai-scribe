from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.person import PersonOut


class DecisionOut(BaseModel):
    text: str
    source_seq: int | None = None
    source_end_seq: int | None = None
    timestamp: int | None = None
    end_timestamp: int | None = None
    speaker: str | None = None


class TranscriptionProgressOut(BaseModel):
    progress: int = 0
    message: str = ""
    error: str | None = None
    elapsed_seconds: int = 0


class MeetingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    meeting_id: int
    title: str
    date: datetime | None
    status: str
    duration: int | None
    attendees: str | None
    description: str | None = None
    audio_path: str | None


class TranscriptLineOut(BaseModel):
    seq: int
    timestamp: int
    text: str
    speaker: str | None = None


class ActionOut(BaseModel):
    seq: int
    description: str
    assignee: str | None = None
    assignee_id: int | None = None
    due_date: str | None = None
    notes: str = ""
    task_status: str | None = None


class MeetingDetailOut(MeetingOut):
    transcript: list[TranscriptLineOut] = Field(default_factory=list)
    summary: str | None = None
    decisions: list[DecisionOut] = Field(default_factory=list)
    actions: list[ActionOut] = Field(default_factory=list)
    people: list[PersonOut] = Field(default_factory=list)
    transcription: TranscriptionProgressOut | None = None


class MeetingListOut(BaseModel):
    items: list[MeetingOut]


class ActionPatchIn(BaseModel):
    seq: int
    description: str | None = Field(default=None, min_length=1)
    assignee: str | None = None
    assignee_id: int | None = None
    due_date: str | None = None
    notes: str | None = None


class TranscriptEditIn(BaseModel):
    seq: int
    text: str = Field(..., min_length=1, max_length=8000)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    date: str | None = None
    attendees: str | None = None
    description: str | None = Field(default=None, max_length=4000)
    analyze: bool = False
    dismiss_action: int | None = None
    update_action: ActionPatchIn | None = None
    update_transcript: TranscriptEditIn | None = None


class SpeakerRenameIn(BaseModel):
    speaker: str = Field(..., min_length=1, max_length=64)
    seq: int | None = None
    from_speaker: str | None = Field(default=None, max_length=64)
