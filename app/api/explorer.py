"""Data explorer API routes."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel

from app.api import deps
from app.db import (
    create_character,
    delete_character,
    delete_game,
    delete_question,
    fetch_characters_for_table,
    fetch_game_detail,
    fetch_games_for_table,
    fetch_questions_for_table,
    update_character,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Engine management
# ---------------------------------------------------------------------------


@router.post("/engine/reload")
def reload_engine() -> dict[str, str]:
    """Drop the cached engine so the next game request rebuilds it from the DB."""
    deps.clear_engine()
    logger.info("Engine cache cleared — will reload on next request")
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Data explorer — read endpoints
# ---------------------------------------------------------------------------


@router.get("/data/characters")
def data_characters(dsn: Annotated[str, Depends(deps.get_dsn)]) -> list[dict[str, Any]]:
    return fetch_characters_for_table(dsn)  # type: ignore[return-value]


@router.get("/data/questions")
def data_questions(dsn: Annotated[str, Depends(deps.get_dsn)]) -> list[dict[str, Any]]:
    return fetch_questions_for_table(dsn)  # type: ignore[return-value]


@router.get("/data/games")
def data_games(dsn: Annotated[str, Depends(deps.get_dsn)]) -> list[dict[str, Any]]:
    return fetch_games_for_table(dsn)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Data explorer — CRUD endpoints
# ---------------------------------------------------------------------------


class CreateCharacterRequest(BaseModel):
    wikidata_id: str
    name: str
    gender: str | None = None
    citizenship_ids: list[str] = []
    occupation_ids: list[str] = []
    series_ids: list[str] = []
    genre_ids: list[str] = []
    member_of_ids: list[str] = []
    award_ids: list[str] = []
    country_of_origin_ids: list[str] = []
    hair_color: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    is_fictional: bool = False
    is_animated: bool = False


class UpdateCharacterRequest(BaseModel):
    name: str
    gender: str | None = None
    citizenship_ids: list[str] = []
    occupation_ids: list[str] = []
    series_ids: list[str] = []
    genre_ids: list[str] = []
    member_of_ids: list[str] = []
    award_ids: list[str] = []
    country_of_origin_ids: list[str] = []
    hair_color: str | None = None
    birth_year: int | None = None
    death_year: int | None = None
    is_fictional: bool = False
    is_animated: bool = False


@router.post("/data/characters", status_code=201)
def create_character_endpoint(
    body: CreateCharacterRequest,
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> dict[str, str]:
    try:
        create_character(
            dsn,
            body.wikidata_id,
            body.name,
            body.gender,
            body.citizenship_ids,
            body.occupation_ids,
            body.series_ids,
            body.genre_ids,
            body.member_of_ids,
            body.award_ids,
            body.country_of_origin_ids,
            body.hair_color,
            body.birth_year,
            body.death_year,
            body.is_fictional,
            body.is_animated,
        )
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"status": "created"}


@router.put("/data/characters/{wikidata_id}")
def update_character_endpoint(
    wikidata_id: str,
    body: UpdateCharacterRequest,
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> dict[str, str]:
    found = update_character(
        dsn,
        wikidata_id,
        body.name,
        body.gender,
        body.citizenship_ids,
        body.occupation_ids,
        body.series_ids,
        body.genre_ids,
        body.member_of_ids,
        body.award_ids,
        body.country_of_origin_ids,
        body.hair_color,
        body.birth_year,
        body.death_year,
        body.is_fictional,
        body.is_animated,
    )
    if not found:
        raise HTTPException(status_code=404, detail="Character not found")
    return {"status": "updated"}


@router.delete("/data/characters/{wikidata_id}")
def delete_character_endpoint(
    wikidata_id: str,
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> dict[str, str]:
    if not delete_character(dsn, wikidata_id):
        raise HTTPException(status_code=404, detail="Character not found")
    return {"status": "deleted"}


@router.delete("/data/questions/{question_id}")
def delete_question_endpoint(
    question_id: int,
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> dict[str, str]:
    if not delete_question(dsn, question_id):
        raise HTTPException(status_code=404, detail="Question not found")
    return {"status": "deleted"}


@router.get("/data/games/{game_id}/detail")
def game_detail(
    game_id: int,
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> list[dict[str, Any]]:
    return fetch_game_detail(dsn, game_id)  # type: ignore[return-value]


@router.delete("/data/games/{game_id}")
def delete_game_endpoint(
    game_id: int,
    dsn: Annotated[str, Depends(deps.get_dsn)],
) -> dict[str, str]:
    if not delete_game(dsn, game_id):
        raise HTTPException(status_code=404, detail="Game not found")
    return {"status": "deleted"}
