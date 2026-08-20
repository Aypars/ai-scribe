from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Decision(Base):
    __tablename__ = "decisions"

    meeting_id: Mapped[int] = mapped_column(
        ForeignKey("analyses.meeting_id", ondelete="CASCADE"),
        primary_key=True,
    )
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    source_seq: Mapped[int | None] = mapped_column(Integer)
    source_end_seq: Mapped[int | None] = mapped_column(Integer)
