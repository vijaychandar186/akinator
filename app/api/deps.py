"""Module-level shared state for the API.

game.py and explorer.py access these singletons via `from app.api import deps`
and then reference `deps._engine`, `deps._sessions`, etc.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException
from loguru import logger

from app.db import load_characters_and_likelihoods
from app.game.engine import AkinatorEngine

# ---------------------------------------------------------------------------
# Shared engine — loaded once at startup, shared across requests.
# ---------------------------------------------------------------------------

_engine: AkinatorEngine | None = None
_dsn: str = ""

# Active game sessions keyed by a simple integer session ID.
_sessions: dict[int, dict] = {}
_next_session_id = 1


def get_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    return dsn


def require_engine(dsn: Annotated[str, Depends(get_dsn)]) -> AkinatorEngine:
    global _engine, _dsn
    if _engine is None or _dsn != dsn:
        characters, questions, likelihoods = load_characters_and_likelihoods(dsn)
        if not characters:
            raise HTTPException(
                status_code=503,
                detail="No characters in database — run 'fetch' first",
            )
        _engine = AkinatorEngine(
            characters,
            questions,
            likelihoods,
            guess_threshold=0.80,
            max_questions=30,
            top_k=3,
        )
        _dsn = dsn
        logger.info(
            "Engine loaded with {} characters, {} questions",
            len(characters),
            len(questions),
        )
    return _engine


def clear_engine() -> None:
    global _engine
    _engine = None
