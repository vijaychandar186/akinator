"""Standalone batch retraining script.

Reads all game sessions that have correct-character feedback from the
database and nudges the likelihood matrix toward the observed answers.

Run with:
    uv run python -m app.learning --dsn postgresql://...
or via:
    just retrain
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict

import numpy as np
from loguru import logger

from app.db import (
    load_characters_and_likelihoods,
    load_feedback_games,
    save_likelihoods,
)
from app.game.engine import _EPS


def retrain(dsn: str, learning_rate: float = 0.1) -> None:
    """Load game feedback and update the likelihood matrix in the database."""
    characters, questions, likelihoods = load_characters_and_likelihoods(dsn)
    if not characters:
        logger.error("No characters in database — run fetch first")
        sys.exit(1)

    wikidata_to_idx: dict[str, int] = {
        c.wikidata_id: i for i, c in enumerate(characters)
    }

    feedback_games = load_feedback_games(dsn)
    if not feedback_games:
        logger.info("No feedback games found — nothing to retrain")
        return

    logger.info("Processing {} feedback games", len(feedback_games))

    # Accumulate observed answers per (character, question) across all games.
    # Each entry is a list of answer values [0..1] from game sessions.
    observations: dict[tuple[int, int], list[float]] = defaultdict(list)
    for wikidata_id, answers in feedback_games:
        char_idx = wikidata_to_idx.get(wikidata_id)
        if char_idx is None:
            logger.debug("Unknown wikidata_id {} — skipping", wikidata_id)
            continue
        question_ids = {q.id for q in questions}
        for q_id, answer_val in answers.items():
            if q_id in question_ids:
                observations[(char_idx, q_id)].append(answer_val)

    if not observations:
        logger.info("No usable observations after filtering — nothing to retrain")
        return

    updated_cells = 0
    for (char_idx, q_id), answer_list in observations.items():
        target = sum(answer_list) / len(answer_list)
        old = float(likelihoods[char_idx, q_id])
        likelihoods[char_idx, q_id] = np.float32(old + learning_rate * (target - old))
        updated_cells += 1

    likelihoods = np.clip(likelihoods, _EPS, 1.0 - _EPS)
    save_likelihoods(dsn, characters, questions, likelihoods)
    logger.info(
        "Retrain complete — updated {} likelihood cells across {} characters",
        updated_cells,
        len({ci for ci, _ in observations}),
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Batch-retrain the Akinator likelihood matrix from game feedback"
    )
    parser.add_argument(
        "--dsn",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL DSN (default: $DATABASE_URL)",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.1,
        metavar="LR",
        help="Step size for likelihood nudge (default: 0.1)",
    )
    return parser


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stderr, level="INFO")

    args = _build_arg_parser().parse_args()
    if not args.dsn:
        logger.error("Provide --dsn or set DATABASE_URL")
        sys.exit(1)

    retrain(dsn=args.dsn, learning_rate=args.learning_rate)
