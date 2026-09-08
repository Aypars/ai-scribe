from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.person import PersonOut


class DecisionOut(BaseModel):
    seq: int | None = None
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
    named_attendees: str | None = None
    description: str | None = None
    language: str = "tr"
    audio_path: str | None


class TranscriptFlagOut(BaseModel):
    original: str
    suggestion: str
    reason: str = ""


class TranscriptLineOut(BaseModel):
    seq: int
    timestamp: int
    text: str
    speaker: str | None = None
    speaker_origin: str | None = None
    flags: list[TranscriptFlagOut] = Field(default_factory=list)


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
    speaker_label: str | None = None
    due_date: str | None = None
    notes: str | None = None


class TranscriptEditIn(BaseModel):
    seq: int
    text: str = Field(..., min_length=1, max_length=8000)
    flags: list[TranscriptFlagOut] | None = None


class TranscriptMergeIn(BaseModel):
    seq: int


class DecisionPatchIn(BaseModel):
    seq: int
    text: str = Field(..., min_length=1, max_length=4000)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    date: str | None = None
    attendees: str | None = None
    named_attendees: str | None = None
    description: str | None = Field(default=None, max_length=4000)
    analyze: bool = False
    dismiss_action: int | None = None
    update_action: ActionPatchIn | None = None
    update_transcript: TranscriptEditIn | None = None
    update_decision: DecisionPatchIn | None = None
    summary: str | None = Field(default=None, max_length=20000)


class SpeakerRenameIn(BaseModel):
    speaker: str | None = Field(default=None, max_length=64)
    seq: int | None = None
    from_speaker: str | None = Field(default=None, max_length=64)
    action: Literal["confirm", "reject"] | None = None


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class AskCiteOut(BaseModel):
    seq: int
    timestamp: int
    speaker: str | None = None
    text: str


class AskOut(BaseModel):
    answer: str
    cites: list[AskCiteOut] = Field(default_factory=list)
