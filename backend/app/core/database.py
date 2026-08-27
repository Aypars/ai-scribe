"""SQLAlchemy engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=8,
    max_overflow=16,
    pool_timeout=10,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> None:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))


def _existing_columns(conn) -> set[tuple[str, str]]:
    rows = conn.execute(
        text(
            """
            SELECT table_name, column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
            """
        )
    )
    return {(str(table), str(column)) for table, column in rows}


def ensure_schema() -> None:
    """Add missing columns without taking an exclusive lock on every reload."""
    wanted: list[tuple[str, str, str]] = [
        ("transcripts", "flags", "TEXT"),
        ("actions", "notes", "TEXT"),
        ("actions", "dismissed", "BOOLEAN NOT NULL DEFAULT FALSE"),
        ("meetings", "description", "TEXT"),
        ("actions", "assignee_id", "INTEGER REFERENCES people (person_id) ON DELETE SET NULL"),
        ("tasks", "assignee_id", "INTEGER REFERENCES people (person_id) ON DELETE SET NULL"),
        ("decisions", "source_seq", "INTEGER"),
        ("decisions", "source_end_seq", "INTEGER"),
        ("meetings", "named_attendees", "TEXT"),
        ("meetings", "analysis_error", "TEXT"),
        ("meetings", "speakers_matched", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ]
    with engine.begin() as conn:
        conn.execute(text("SET lock_timeout = '2s'"))
        existing = _existing_columns(conn)
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS people (
                    person_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                    name VARCHAR(255) NOT NULL,
                    note VARCHAR(255)
                );
                CREATE TABLE IF NOT EXISTS meeting_people (
                    meeting_id INTEGER NOT NULL REFERENCES meetings (meeting_id) ON DELETE CASCADE,
                    person_id INTEGER NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
                    speaker_label VARCHAR(64),
                    PRIMARY KEY (meeting_id, person_id)
                );
                """
            )
        )
        for table, column, ddl in wanted:
            if (table, column) in existing:
                continue
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            except Exception:
                continue
