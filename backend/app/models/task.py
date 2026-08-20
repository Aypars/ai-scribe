from datetime import date

from sqlalchemy import Date, ForeignKey, ForeignKeyConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["meeting_id", "action_seq"],
            ["actions.meeting_id", "actions.seq"],
            ondelete="CASCADE",
        ),
    )

    meeting_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    assignee: Mapped[str | None] = mapped_column(String(255))
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("people.person_id", ondelete="SET NULL"))
    due_date: Mapped[date | None] = mapped_column(Date)
