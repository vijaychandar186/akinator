import psycopg
from loguru import logger
from psycopg.rows import DictRow

from app.db.conn import get_conn


def save_game(
    dsn: str,
    guessed_wikidata_id: str | None,
    correct_wikidata_id: str | None,
    was_correct: bool,
    answers: dict[int, float],
    confidence: float | None = None,
) -> int:
    """Persist a completed game session and return its database ID."""
    with get_conn(dsn) as conn:
        guessed_db_id = _lookup_char_id(conn, guessed_wikidata_id)
        correct_db_id = _lookup_char_id(conn, correct_wikidata_id)

        row = conn.execute(
            """
            INSERT INTO games (ended_at, guessed_character_id, correct_character_id, was_correct, confidence)
            VALUES (NOW(), %s, %s, %s, %s)
            RETURNING id
            """,
            (guessed_db_id, correct_db_id, was_correct, confidence),
        ).fetchone()
        assert row is not None
        game_id: int = row["id"]

        for q_id, answer_val in answers.items():
            conn.execute(
                "INSERT INTO game_answers (game_id, question_id, answer) VALUES (%s, %s, %s)",
                (game_id, q_id, answer_val),
            )
        conn.commit()

    logger.debug("Saved game id={} was_correct={}", game_id, was_correct)
    return game_id


def load_feedback_games(
    dsn: str,
) -> list[tuple[str, dict[int, float]]]:
    """Return games that have correct-character feedback.

    Each entry is (correct_wikidata_id, {question_id: answer}).
    """
    with get_conn(dsn) as conn:
        rows = conn.execute(
            """
            SELECT g.id AS game_id, c.wikidata_id,
                   ga.question_id, ga.answer
            FROM games g
            JOIN characters c ON c.id = g.correct_character_id
            JOIN game_answers ga ON ga.game_id = g.id
            WHERE g.correct_character_id IS NOT NULL
            ORDER BY g.id
            """
        ).fetchall()

    games: dict[int, tuple[str, dict[int, float]]] = {}
    for row in rows:
        gid: int = row["game_id"]
        if gid not in games:
            games[gid] = (row["wikidata_id"], {})
        games[gid][1][row["question_id"]] = row["answer"]

    return list(games.values())


def fetch_games_for_table(dsn: str) -> list[dict[str, object]]:
    with get_conn(dsn) as conn:
        rows = conn.execute(
            """
            SELECT g.id,
                   TO_CHAR(g.ended_at AT TIME ZONE 'UTC', 'YYYY-MM-DD HH24:MI') AS ended_at,
                   gc.name AS guessed,
                   cc.name AS correct,
                   g.was_correct,
                   ROUND((g.confidence * 100)::numeric, 1) AS confidence,
                   COUNT(ga.id) AS questions
            FROM games g
            LEFT JOIN characters gc ON gc.id = g.guessed_character_id
            LEFT JOIN characters cc ON cc.id = g.correct_character_id
            LEFT JOIN game_answers ga ON ga.game_id = g.id
            GROUP BY g.id, gc.name, cc.name
            ORDER BY g.id DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_game_detail(dsn: str, game_id: int) -> list[dict[str, object]]:
    """Return the Q&A log for a single game — question text, answer value, and label."""
    with get_conn(dsn) as conn:
        rows = conn.execute(
            """
            SELECT q.text AS question,
                   ga.answer,
                   CASE
                     WHEN ga.answer = 1.0  THEN 'yes'
                     WHEN ga.answer = 0.75 THEN 'probably'
                     WHEN ga.answer = 0.5  THEN 'maybe'
                     WHEN ga.answer = 0.25 THEN 'probably not'
                     WHEN ga.answer = 0.0  THEN 'no'
                     ELSE ROUND(ga.answer::numeric, 2)::text
                   END AS answer_label
            FROM game_answers ga
            JOIN questions q ON q.id = ga.question_id
            WHERE ga.game_id = %s
            ORDER BY ga.id
            """,
            (game_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_game(dsn: str, game_id: int) -> bool:
    with get_conn(dsn) as conn:
        cur = conn.execute("DELETE FROM games WHERE id=%s", (game_id,))
        conn.commit()
    return (cur.rowcount or 0) > 0


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _lookup_char_id(
    conn: "psycopg.Connection[DictRow]",
    wikidata_id: str | None,
) -> int | None:
    if wikidata_id is None:
        return None
    row = conn.execute(
        "SELECT id FROM characters WHERE wikidata_id = %s", (wikidata_id,)
    ).fetchone()
    return row["id"] if row else None
