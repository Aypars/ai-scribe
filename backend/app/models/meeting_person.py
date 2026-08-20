from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class MeetingPerson(Base):
    """Links a person to a meeting as an attendee (optionally tied to a speaker label)."""

    __tablename__ = "meeting_people"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.meeting_id", ondelete="CASCADE"),
        primary_key=True,
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("people.person_id", ondelete="CASCADE"),
        primary_key=True,
    )
    speaker_label: Mapped[str | None] = mapped_column(String(64))
