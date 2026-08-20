-- AI-SCRIBE schema
-- Strong: users, meetings
-- Weak (identifying): transcripts, analyses, decisions, actions, tasks

DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS actions CASCADE;
DROP TABLE IF EXISTS decisions CASCADE;
DROP TABLE IF EXISTS analyses CASCADE;
DROP TABLE IF EXISTS meeting_people CASCADE;
DROP TABLE IF EXISTS transcripts CASCADE;
DROP TABLE IF EXISTS meetings CASCADE;
DROP TABLE IF EXISTS people CASCADE;
DROP TABLE IF EXISTS users CASCADE;

CREATE TABLE users (
    user_id  SERIAL PRIMARY KEY,
    name     VARCHAR(255) NOT NULL,
    email    VARCHAR(255) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE meetings (
    meeting_id SERIAL PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    title      VARCHAR(255) NOT NULL,
    date       TIMESTAMPTZ,
    status     VARCHAR(32) NOT NULL DEFAULT 'uploaded'
               CHECK (status IN ('uploaded', 'transcribed', 'analyzed', 'failed')),
    duration   INTEGER CHECK (duration IS NULL OR duration >= 0),
    attendees  TEXT,
    description TEXT,
    audio_path VARCHAR(1024)
);

CREATE INDEX meetings_user_id_idx ON meetings (user_id);

CREATE TABLE people (
    person_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    note VARCHAR(255)
);

CREATE TABLE meeting_people (
    meeting_id INTEGER NOT NULL REFERENCES meetings (meeting_id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people (person_id) ON DELETE CASCADE,
    speaker_label VARCHAR(64),
    PRIMARY KEY (meeting_id, person_id)
);

-- Weak of meetings. PK = (meeting_id, seq). timestamp = saniye (00:30 → 30)
CREATE TABLE transcripts (
    meeting_id INTEGER NOT NULL REFERENCES meetings (meeting_id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL CHECK (seq >= 1),
    text       TEXT NOT NULL,
    timestamp  INTEGER NOT NULL CHECK (timestamp >= 0),
    speaker    VARCHAR(64),
    PRIMARY KEY (meeting_id, seq)
);

-- Weak of meetings, 1:1. PK = meeting_id
CREATE TABLE analyses (
    meeting_id INTEGER PRIMARY KEY REFERENCES meetings (meeting_id) ON DELETE CASCADE,
    summary    TEXT NOT NULL,
    date       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Weak of analyses. PK = (meeting_id, seq)
CREATE TABLE decisions (
    meeting_id INTEGER NOT NULL REFERENCES analyses (meeting_id) ON DELETE CASCADE,
    seq        INTEGER NOT NULL CHECK (seq >= 1),
    text       TEXT NOT NULL,
    source_seq INTEGER,
    source_end_seq INTEGER,
    PRIMARY KEY (meeting_id, seq)
);

-- Weak of analyses. PK = (meeting_id, seq)
CREATE TABLE actions (
    meeting_id  INTEGER NOT NULL REFERENCES analyses (meeting_id) ON DELETE CASCADE,
    seq         INTEGER NOT NULL CHECK (seq >= 1),
    description TEXT NOT NULL,
    assignee    VARCHAR(255),
    due_date    DATE,
    notes       TEXT,
    dismissed   BOOLEAN NOT NULL DEFAULT FALSE,
    assignee_id INTEGER REFERENCES people (person_id) ON DELETE SET NULL,
    PRIMARY KEY (meeting_id, seq)
);

-- Weak of actions, 1:1. PK = (meeting_id, action_seq)
CREATE TABLE tasks (
    meeting_id INTEGER NOT NULL,
    action_seq INTEGER NOT NULL,
    title      VARCHAR(255) NOT NULL,
    status     VARCHAR(32) NOT NULL DEFAULT 'in_progress'
               CHECK (status IN ('in_progress', 'done')),
    assignee   VARCHAR(255),
    assignee_id INTEGER REFERENCES people (person_id) ON DELETE SET NULL,
    due_date   DATE,
    PRIMARY KEY (meeting_id, action_seq),
    FOREIGN KEY (meeting_id, action_seq)
        REFERENCES actions (meeting_id, seq) ON DELETE CASCADE
);
