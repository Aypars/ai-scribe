from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Meeting(Base):
    __tablename__ = "meetings"

    meeting_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    duration: Mapped[int | None] = mapped_column(Integer)
    attendees: Mapped[str | None] = mapped_column(Text)
    named_attendees: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    analysis_error: Mapped[str | None] = mapped_column(Text)
    speakers_matched: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="tr")
    audio_path: Mapped[str | None] = mapped_column(String(1024))

    transcripts: Mapped[list["Transcript"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="Transcript.seq",
    )
