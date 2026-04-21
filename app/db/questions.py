from loguru import logger

from app.db.conn import get_conn
from app.game.questions import QuestionDef, make_predicate


def upsert_questions(dsn: str, specs: list[dict]) -> None:
    """Replace all question definitions with a freshly generated set.

    Deletes stale questions (cascading to likelihoods) then inserts the new
    batch so question IDs always match the current character corpus.
    """
    new_ids = [spec["id"] for spec in specs]
    with get_conn(dsn) as conn:
        if new_ids:
            conn.execute("DELETE FROM questions WHERE id != ALL(%s)", (new_ids,))
        else:
            conn.execute("DELETE FROM questions")
        for spec in specs:
            conn.execute(
                """
                INSERT INTO questions
                    (id, text, question_type, qid, threshold_low, threshold_high)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    text           = EXCLUDED.text,
                    question_type  = EXCLUDED.question_type,
                    qid            = EXCLUDED.qid,
                    threshold_low  = EXCLUDED.threshold_low,
                    threshold_high = EXCLUDED.threshold_high
                """,
                (
                    spec["id"],
                    spec["text"],
                    spec["question_type"],
                    spec.get("qid"),
                    spec.get("threshold_low"),
                    spec.get("threshold_high"),
                ),
            )
        conn.commit()
    logger.info("Upserted {} question definitions", len(specs))


def load_questions(dsn: str) -> list[QuestionDef]:
    """Load all questions from the database and reconstruct their predicates."""
    with get_conn(dsn) as conn:
        rows = conn.execute(
            """
            SELECT id, text, question_type, qid, threshold_low, threshold_high
            FROM questions
            ORDER BY id
            """
        ).fetchall()
    return [
        QuestionDef(
            id=r["id"],
            text=r["text"],
            predicate=make_predicate(
                r["question_type"],
                r.get("qid"),
                r.get("threshold_low"),
                r.get("threshold_high"),
            ),
            question_type=r["question_type"],
            qid=r.get("qid"),
            threshold_low=r.get("threshold_low"),
            threshold_high=r.get("threshold_high"),
        )
        for r in rows
    ]


def fetch_questions_for_table(dsn: str) -> list[dict[str, object]]:
    with get_conn(dsn) as conn:
        rows = conn.execute(
            """
            SELECT id, text, question_type, qid
            FROM questions
            ORDER BY id
            """
        ).fetchall()
    return [dict(r) for r in rows]


def delete_question(dsn: str, question_id: int) -> bool:
    with get_conn(dsn) as conn:
        cur = conn.execute("DELETE FROM questions WHERE id=%s", (question_id,))
        conn.commit()
    return (cur.rowcount or 0) > 0
