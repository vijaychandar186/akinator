"""Game-play API routes."""

from __future__ import annotations

from typing import Annotated

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api import deps
from app.db import save_game
from app.game.engine import AkinatorEngine

router = APIRouter()

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartResponse(BaseModel):
    session_id: int
    question_id: int
    question_text: str


class AnswerRequest(BaseModel):
    session_id: int
    question_id: int
    # Accepted values: "yes" | "probably" | "maybe" | "probably not" | "no"
    answer: str


class AnswerResponse(BaseModel):
    done: bool
    next_question_id: int | None = None
    next_question_text: str | None = None
    guess_name: str | None = None
    guess_wikidata_id: str | None = None
    confidence: float | None = None


class ContinueRequest(BaseModel):
    session_id: int


class ContinueResponse(BaseModel):
    next_question_id: int
    next_question_text: str


class FeedbackRequest(BaseModel):
    session_id: int
    was_correct: bool
    correct_name: str | None = None


class FeedbackResponse(BaseModel):
    message: str


_FUZZY_MAP: dict[str, float] = {
    "yes": 1.0,
    "probably": 0.75,
    "maybe": 0.5,
    "probably not": 0.25,
    "no": 0.0,
}


def _parse_answer(raw: str) -> float:
    value = _FUZZY_MAP.get(raw.strip().lower())
    if value is None:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid answer '{raw}'. Use: yes / probably / maybe / probably not / no",
        )
    return value


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/game/start", response_model=StartResponse)
def start_game(
    engine: Annotated[AkinatorEngine, Depends(deps.require_engine)],
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> StartResponse:
    """Create a new game session and return the first question."""
    session_id = deps._next_session_id
    deps._next_session_id += 1

    n = len(engine.characters)
    deps._sessions[session_id] = {
        "probs": np.full(n, 1.0 / n, dtype=np.float32),
        "asked": set(),
        "answers": {},
    }

    # Temporarily swap engine state to pick the first question cleanly
    saved_probs = engine._probs.copy()
    saved_asked = engine.asked.copy()
    engine._probs = deps._sessions[session_id]["probs"]
    engine.asked = deps._sessions[session_id]["asked"]

    q_idx = engine.best_question()

    engine._probs = saved_probs
    engine.asked = saved_asked

    deps._sessions[session_id]["current_question"] = q_idx

    return StartResponse(
        session_id=session_id,
        question_id=q_idx,
        question_text=engine.questions[q_idx].text,
    )


@router.post("/game/answer", response_model=AnswerResponse)
def answer_question(
    body: AnswerRequest,
    engine: Annotated[AkinatorEngine, Depends(deps.require_engine)],
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> AnswerResponse:
    """Submit an answer and get the next question (or a guess)."""
    session = deps._sessions.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    answer_value = _parse_answer(body.answer)

    # Apply update within the session's isolated state
    saved_probs = engine._probs.copy()
    saved_asked = engine.asked.copy()
    engine._probs = session["probs"]
    engine.asked = session["asked"]

    engine.update(body.question_id, answer_value)
    session["answers"][body.question_id] = answer_value
    session["probs"] = engine._probs.copy()
    session["asked"] = engine.asked.copy()

    if engine.should_guess():
        guess, confidence = engine.top_guess()
        session["guess"] = guess
        session["confidence"] = confidence
        engine._probs = saved_probs
        engine.asked = saved_asked
        return AnswerResponse(
            done=True,
            guess_name=guess.name,
            guess_wikidata_id=guess.wikidata_id,
            confidence=confidence,
        )

    q_idx = engine.best_question()
    session["current_question"] = q_idx
    engine._probs = saved_probs
    engine.asked = saved_asked

    return AnswerResponse(
        done=False,
        next_question_id=q_idx,
        next_question_text=engine.questions[q_idx].text,
    )


@router.post("/game/continue", response_model=ContinueResponse)
def continue_game(
    body: ContinueRequest,
    engine: Annotated[AkinatorEngine, Depends(deps.require_engine)],
) -> ContinueResponse:
    """Penalise the wrong guess and return the next question."""
    session = deps._sessions.get(body.session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    wrong_guess = session.get("guess")
    if wrong_guess is not None:
        wrong_idx = engine.character_index(wrong_guess.wikidata_id)
        if wrong_idx is not None:
            session["probs"][wrong_idx] = 0.0
            total = float(session["probs"].sum())
            if total > 0:
                session["probs"] /= total

    saved_probs = engine._probs.copy()
    saved_asked = engine.asked.copy()
    engine._probs = session["probs"]
    engine.asked = session["asked"]

    try:
        q_idx = engine.best_question()
    except RuntimeError:
        engine._probs = saved_probs
        engine.asked = saved_asked
        raise HTTPException(status_code=409, detail="No more questions available")

    session["current_question"] = q_idx
    session["guess"] = None
    engine._probs = saved_probs
    engine.asked = saved_asked

    return ContinueResponse(
        next_question_id=q_idx,
        next_question_text=engine.questions[q_idx].text,
    )


@router.post("/game/feedback", response_model=FeedbackResponse)
def submit_feedback(
    body: FeedbackRequest,
    engine: Annotated[AkinatorEngine, Depends(deps.require_engine)],
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> FeedbackResponse:
    """Record whether the guess was right and save the game for retraining."""
    session = deps._sessions.pop(body.session_id, None)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    guessed = session.get("guess")
    guessed_id = guessed.wikidata_id if guessed else None

    correct_wikidata_id: str | None = guessed_id if body.was_correct else None
    if not body.was_correct and body.correct_name:
        from rapidfuzz import process as fuzz_process

        names = [c.name for c in engine.characters]
        result = fuzz_process.extractOne(body.correct_name, names, score_cutoff=80)
        if result is not None:
            matched_idx = names.index(result[0])
            correct_wikidata_id = engine.characters[matched_idx].wikidata_id

    save_game(
        dsn=dsn,
        guessed_wikidata_id=guessed_id,
        correct_wikidata_id=correct_wikidata_id,
        was_correct=body.was_correct,
        answers=session.get("answers", {}),
        confidence=session.get("confidence"),
    )

    return FeedbackResponse(message="Feedback recorded. Thank you!")


@router.get("/characters/count")
def character_count(
    engine: Annotated[AkinatorEngine, Depends(deps.require_engine)],
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> dict[str, int]:
    return {"count": len(engine.characters)}


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
