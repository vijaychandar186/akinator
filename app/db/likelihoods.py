import numpy as np
from loguru import logger

from app.db.conn import get_conn
from app.game.questions import QuestionDef, make_predicate
from app.models import Character


def save_likelihoods(
    dsn: str,
    characters: list[Character],
    questions: list[QuestionDef],
    likelihoods: np.ndarray,
) -> None:
    """Persist the full likelihood matrix, keyed by Wikidata ID."""
    n_questions = len(questions)
    with get_conn(dsn) as conn:
        rows = conn.execute(
            "SELECT id, wikidata_id FROM characters WHERE wikidata_id = ANY(%s)",
            ([c.wikidata_id for c in characters],),
        ).fetchall()
        wikidata_to_db: dict[str, int] = {r["wikidata_id"]: r["id"] for r in rows}

        for ci, char in enumerate(characters):
            db_id = wikidata_to_db.get(char.wikidata_id)
            if db_id is None:
                continue
            for qi in range(n_questions):
                conn.execute(
                    """
                    INSERT INTO likelihoods (character_id, question_id, probability)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (character_id, question_id)
                    DO UPDATE SET probability = EXCLUDED.probability
                    """,
                    (db_id, qi, float(likelihoods[ci, qi])),
                )
        conn.commit()
    logger.info("Saved likelihood matrix ({} characters)", len(characters))


def load_characters_and_likelihoods(
    dsn: str,
) -> tuple[list[Character], list[QuestionDef], np.ndarray]:
    """Load characters, questions, and the likelihood matrix from the database."""
    with get_conn(dsn) as conn:
        char_rows = conn.execute(
            """
            SELECT id, wikidata_id, name, gender,
                   citizenship_ids, occupation_ids, series_ids,
                   genre_ids, member_of_ids, award_ids, country_of_origin_ids,
                   hair_color, birth_year, death_year, is_fictional, is_animated
            FROM characters
            ORDER BY id
            """
        ).fetchall()

        q_rows = conn.execute(
            """
            SELECT id, text, question_type, qid, threshold_low, threshold_high
            FROM questions
            ORDER BY id
            """
        ).fetchall()

        questions = [
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
            for r in q_rows
        ]
        n_questions = len(questions)

        if not char_rows:
            return [], questions, np.empty((0, n_questions), dtype=np.float32)

        characters = [
            Character(
                wikidata_id=r["wikidata_id"],
                name=r["name"],
                gender=r["gender"],
                citizenship_ids=r["citizenship_ids"] or [],
                occupation_ids=r["occupation_ids"] or [],
                series_ids=r["series_ids"] or [],
                genre_ids=r["genre_ids"] or [],
                member_of_ids=r["member_of_ids"] or [],
                award_ids=r["award_ids"] or [],
                country_of_origin_ids=r["country_of_origin_ids"] or [],
                hair_color=r.get("hair_color"),
                birth_year=r["birth_year"],
                death_year=r["death_year"],
                is_fictional=bool(r.get("is_fictional", False)),
                is_animated=bool(r.get("is_animated", False)),
            )
            for r in char_rows
        ]
        db_ids = [r["id"] for r in char_rows]
        id_to_idx: dict[int, int] = {db_id: i for i, db_id in enumerate(db_ids)}

        likelihoods = np.full(
            (len(characters), n_questions), fill_value=1e-6, dtype=np.float32
        )

        like_rows = conn.execute(
            """
            SELECT character_id, question_id, probability
            FROM likelihoods
            WHERE character_id = ANY(%s)
              AND question_id < %s
            """,
            (db_ids, n_questions),
        ).fetchall()

        for row in like_rows:
            ci = id_to_idx.get(row["character_id"])
            if ci is not None:
                likelihoods[ci, row["question_id"]] = row["probability"]

        # Auto-fix: characters added after the last full build have all-epsilon rows.
        # Recompute their likelihoods from question predicates and persist.
        EPS = np.float32(1e-6)
        missing_idxs = [
            i for i in range(len(characters)) if np.all(likelihoods[i] <= EPS * 2)
        ]
        if missing_idxs:
            logger.info(
                "Backfilling likelihoods for {} character(s) missing from matrix",
                len(missing_idxs),
            )
            for i in missing_idxs:
                for qi, qdef in enumerate(questions):
                    likelihoods[i, qi] = 1.0 if qdef.predicate(characters[i]) else 0.0
            likelihoods[missing_idxs] = np.clip(
                likelihoods[missing_idxs], EPS, np.float32(1.0 - 1e-6)
            )
            for i in missing_idxs:
                db_id = db_ids[i]
                for qi in range(n_questions):
                    conn.execute(
                        """
                        INSERT INTO likelihoods (character_id, question_id, probability)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (character_id, question_id)
                        DO UPDATE SET probability = EXCLUDED.probability
                        """,
                        (db_id, qi, float(likelihoods[i, qi])),
                    )
            conn.commit()

    logger.info(
        "Loaded {} characters, {} questions from database", len(characters), n_questions
    )
    return characters, questions, likelihoods
