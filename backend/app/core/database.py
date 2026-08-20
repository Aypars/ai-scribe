"""SQLAlchemy engine and session factory."""

from collections.abc import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, pool_pre_ping=True)
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


def ensure_schema() -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DO $$ BEGIN
                    ALTER TABLE transcripts ADD COLUMN speaker VARCHAR(64);
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                DO $$ BEGIN
                    ALTER TABLE actions ADD COLUMN notes TEXT;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                DO $$ BEGIN
                    ALTER TABLE actions ADD COLUMN dismissed BOOLEAN NOT NULL DEFAULT FALSE;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                DO $$ BEGIN
                    ALTER TABLE meetings ADD COLUMN description TEXT;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
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
                DO $$ BEGIN
                    ALTER TABLE actions ADD COLUMN assignee_id INTEGER REFERENCES people (person_id) ON DELETE SET NULL;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                DO $$ BEGIN
                    ALTER TABLE tasks ADD COLUMN assignee_id INTEGER REFERENCES people (person_id) ON DELETE SET NULL;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                DO $$ BEGIN
                    ALTER TABLE decisions ADD COLUMN source_seq INTEGER;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                DO $$ BEGIN
                    ALTER TABLE decisions ADD COLUMN source_end_seq INTEGER;
                EXCEPTION
                    WHEN duplicate_column THEN NULL;
                END $$;
                """
            )
        )
