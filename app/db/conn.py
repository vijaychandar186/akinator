from contextlib import contextmanager
from typing import Generator

import psycopg
from loguru import logger
from psycopg.rows import DictRow, dict_row

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS characters (
    id          SERIAL PRIMARY KEY,
    wikidata_id TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    gender      TEXT,
    citizenship_ids JSONB    NOT NULL DEFAULT '[]',
    occupation_ids  JSONB    NOT NULL DEFAULT '[]',
    series_ids           JSONB    NOT NULL DEFAULT '[]',
    genre_ids            JSONB    NOT NULL DEFAULT '[]',
    member_of_ids        JSONB    NOT NULL DEFAULT '[]',
    award_ids            JSONB    NOT NULL DEFAULT '[]',
    country_of_origin_ids JSONB   NOT NULL DEFAULT '[]',
    hair_color           TEXT,
    birth_year  INTEGER,
    death_year  INTEGER,
    is_fictional BOOLEAN NOT NULL DEFAULT FALSE,
    is_animated  BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS questions (
    id             INTEGER PRIMARY KEY,
    text           TEXT    NOT NULL,
    question_type  TEXT    NOT NULL DEFAULT 'legacy',
    qid            TEXT,
    threshold_low  INTEGER,
    threshold_high INTEGER
);

CREATE TABLE IF NOT EXISTS likelihoods (
    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    question_id  INTEGER NOT NULL REFERENCES questions(id)  ON DELETE CASCADE,
    probability  REAL    NOT NULL DEFAULT 0.000001,
    PRIMARY KEY (character_id, question_id)
);

CREATE TABLE IF NOT EXISTS games (
    id                   SERIAL PRIMARY KEY,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at             TIMESTAMPTZ,
    guessed_character_id INTEGER REFERENCES characters(id),
    correct_character_id INTEGER REFERENCES characters(id),
    was_correct          BOOLEAN
);

CREATE TABLE IF NOT EXISTS game_answers (
    id          SERIAL PRIMARY KEY,
    game_id     INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id),
    answer      REAL    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_game_answers_game
    ON game_answers(game_id);
CREATE INDEX IF NOT EXISTS idx_likelihoods_char
    ON likelihoods(character_id);
"""

# Add metadata columns to an existing questions table that only has id + text.
_MIGRATE_QUESTIONS = """
ALTER TABLE questions ADD COLUMN IF NOT EXISTS question_type  TEXT    NOT NULL DEFAULT 'legacy';
ALTER TABLE questions ADD COLUMN IF NOT EXISTS qid            TEXT;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS threshold_low  INTEGER;
ALTER TABLE questions ADD COLUMN IF NOT EXISTS threshold_high INTEGER;
"""

_MIGRATE_CHARACTERS = """
ALTER TABLE characters ADD COLUMN IF NOT EXISTS is_fictional          BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE characters ADD COLUMN IF NOT EXISTS series_ids            JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS is_animated           BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE characters ADD COLUMN IF NOT EXISTS genre_ids             JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS member_of_ids         JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS award_ids             JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS country_of_origin_ids JSONB   NOT NULL DEFAULT '[]';
ALTER TABLE characters ADD COLUMN IF NOT EXISTS hair_color            TEXT;
"""

_MIGRATE_GAMES = """
ALTER TABLE games ADD COLUMN IF NOT EXISTS confidence REAL;
"""


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


@contextmanager
def get_conn(dsn: str) -> Generator["psycopg.Connection[DictRow]", None, None]:
    with psycopg.connect(dsn, row_factory=dict_row) as conn:  # type: ignore[misc]
        yield conn


# ---------------------------------------------------------------------------
# Schema + seed
# ---------------------------------------------------------------------------


def init_schema(dsn: str) -> None:
    with get_conn(dsn) as conn:
        conn.execute(_DDL)
        conn.execute(_MIGRATE_QUESTIONS)
        conn.execute(_MIGRATE_CHARACTERS)
        conn.execute(_MIGRATE_GAMES)
        conn.commit()
    logger.info("Database schema ready")
