from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Transcript(Base):
    __tablename__ = "transcripts"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("meetings.meeting_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    timestamp: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str | None] = mapped_column(String(64))

    meeting: Mapped["Meeting"] = relationship(back_populates="transcripts")
