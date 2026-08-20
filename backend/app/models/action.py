from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Action(Base):
    __tablename__ = "actions"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.meeting_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("people.person_id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    dismissed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
