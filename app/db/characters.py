import json

from loguru import logger

from app.db.conn import get_conn
from app.models import Character


def upsert_characters(dsn: str, characters: list[Character]) -> None:
    with get_conn(dsn) as conn:
        for char in characters:
            conn.execute(
                """
                INSERT INTO characters
                    (wikidata_id, name, gender, citizenship_ids, occupation_ids,
                     series_ids, genre_ids, member_of_ids, award_ids,
                     country_of_origin_ids, hair_color,
                     birth_year, death_year, is_fictional, is_animated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (wikidata_id) DO UPDATE SET
                    name                  = EXCLUDED.name,
                    gender                = EXCLUDED.gender,
                    citizenship_ids       = EXCLUDED.citizenship_ids,
                    occupation_ids        = EXCLUDED.occupation_ids,
                    series_ids            = EXCLUDED.series_ids,
                    genre_ids             = EXCLUDED.genre_ids,
                    member_of_ids         = EXCLUDED.member_of_ids,
                    award_ids             = EXCLUDED.award_ids,
                    country_of_origin_ids = EXCLUDED.country_of_origin_ids,
                    hair_color            = EXCLUDED.hair_color,
                    birth_year            = EXCLUDED.birth_year,
                    death_year            = EXCLUDED.death_year,
                    is_fictional          = EXCLUDED.is_fictional,
                    is_animated           = EXCLUDED.is_animated
                """,
                (
                    char.wikidata_id,
                    char.name,
                    char.gender,
                    json.dumps(char.citizenship_ids),
                    json.dumps(char.occupation_ids),
                    json.dumps(char.series_ids),
                    json.dumps(char.genre_ids),
                    json.dumps(char.member_of_ids),
                    json.dumps(char.award_ids),
                    json.dumps(char.country_of_origin_ids),
                    char.hair_color,
                    char.birth_year,
                    char.death_year,
                    char.is_fictional,
                    char.is_animated,
                ),
            )
        conn.commit()
    logger.info("Upserted {} characters", len(characters))


def fetch_characters_for_table(dsn: str) -> list[dict[str, object]]:
    with get_conn(dsn) as conn:
        rows = conn.execute(
            """
            SELECT wikidata_id, name, gender,
                   citizenship_ids, occupation_ids, series_ids,
                   genre_ids, member_of_ids, award_ids, country_of_origin_ids,
                   hair_color, birth_year, death_year, is_fictional, is_animated
            FROM characters
            ORDER BY name
            """
        ).fetchall()
    return [dict(r) for r in rows]


def create_character(
    dsn: str,
    wikidata_id: str,
    name: str,
    gender: str | None,
    citizenship_ids: list[str],
    occupation_ids: list[str],
    series_ids: list[str],
    genre_ids: list[str],
    member_of_ids: list[str],
    award_ids: list[str],
    country_of_origin_ids: list[str],
    hair_color: str | None,
    birth_year: int | None,
    death_year: int | None,
    is_fictional: bool = False,
    is_animated: bool = False,
) -> None:
    with get_conn(dsn) as conn:
        conn.execute(
            """
            INSERT INTO characters
                (wikidata_id, name, gender, citizenship_ids, occupation_ids,
                 series_ids, genre_ids, member_of_ids, award_ids,
                 country_of_origin_ids, hair_color,
                 birth_year, death_year, is_fictional, is_animated)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                wikidata_id,
                name,
                gender,
                json.dumps(citizenship_ids),
                json.dumps(occupation_ids),
                json.dumps(series_ids),
                json.dumps(genre_ids),
                json.dumps(member_of_ids),
                json.dumps(award_ids),
                json.dumps(country_of_origin_ids),
                hair_color,
                birth_year,
                death_year,
                is_fictional,
                is_animated,
            ),
        )
        conn.commit()


def update_character(
    dsn: str,
    wikidata_id: str,
    name: str,
    gender: str | None,
    citizenship_ids: list[str],
    occupation_ids: list[str],
    series_ids: list[str],
    genre_ids: list[str],
    member_of_ids: list[str],
    award_ids: list[str],
    country_of_origin_ids: list[str],
    hair_color: str | None,
    birth_year: int | None,
    death_year: int | None,
    is_fictional: bool = False,
    is_animated: bool = False,
) -> bool:
    with get_conn(dsn) as conn:
        cur = conn.execute(
            """
            UPDATE characters
            SET name=%s, gender=%s, citizenship_ids=%s, occupation_ids=%s,
                series_ids=%s, genre_ids=%s, member_of_ids=%s, award_ids=%s,
                country_of_origin_ids=%s, hair_color=%s,
                birth_year=%s, death_year=%s, is_fictional=%s, is_animated=%s
            WHERE wikidata_id=%s
            """,
            (
                name,
                gender,
                json.dumps(citizenship_ids),
                json.dumps(occupation_ids),
                json.dumps(series_ids),
                json.dumps(genre_ids),
                json.dumps(member_of_ids),
                json.dumps(award_ids),
                json.dumps(country_of_origin_ids),
                hair_color,
                birth_year,
                death_year,
                is_fictional,
                is_animated,
                wikidata_id,
            ),
        )
        conn.commit()
    return (cur.rowcount or 0) > 0


def load_character_wikidata_ids(dsn: str) -> list[str]:
    """Return all wikidata_ids currently in the characters table."""
    with get_conn(dsn) as conn:
        rows = conn.execute("SELECT wikidata_id FROM characters ORDER BY id").fetchall()
    return [r["wikidata_id"] for r in rows]


def fill_character_properties(dsn: str, updates: list[Character]) -> int:
    """Overwrite only the enrichment columns for existing characters.

    Leaves name, gender, citizenship, occupation, birth/death year, and the
    is_* flags untouched — only series, genre, member_of, award, country_of_origin,
    and hair_color are updated.
    """
    updated = 0
    with get_conn(dsn) as conn:
        for char in updates:
            cur = conn.execute(
                """
                UPDATE characters
                SET series_ids            = %s,
                    genre_ids             = %s,
                    member_of_ids         = %s,
                    award_ids             = %s,
                    country_of_origin_ids = %s,
                    hair_color            = COALESCE(%s, hair_color)
                WHERE wikidata_id = %s
                """,
                (
                    json.dumps(char.series_ids),
                    json.dumps(char.genre_ids),
                    json.dumps(char.member_of_ids),
                    json.dumps(char.award_ids),
                    json.dumps(char.country_of_origin_ids),
                    char.hair_color,
                    char.wikidata_id,
                ),
            )
            updated += cur.rowcount or 0
        conn.commit()
    logger.info("Filled enrichment columns for {} characters", updated)
    return updated


def delete_character(dsn: str, wikidata_id: str) -> bool:
    with get_conn(dsn) as conn:
        cur = conn.execute(
            "DELETE FROM characters WHERE wikidata_id=%s", (wikidata_id,)
        )
        conn.commit()
    return (cur.rowcount or 0) > 0
