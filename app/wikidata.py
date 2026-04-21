import time

import requests
from loguru import logger

from app.models import Character

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
_USER_AGENT = "AkinatorGame/0.1 (educational; contact via github)"

# Phase 1a: one query per occupation group (real people, P31=Q5).
# Each tuple is (label, [occupation_QIDs], per_group_limit).
_OCCUPATION_GROUPS: list[tuple[str, list[str], int]] = [
    ("politicians", ["Q82955", "Q48352", "Q2285706"], 300),
    ("actors", ["Q33999", "Q10798782"], 300),
    ("musicians", ["Q639669", "Q177220", "Q488205"], 300),
    ("scientists", ["Q901", "Q1650915"], 200),
    ("writers", ["Q36180", "Q482980", "Q49757"], 200),
    ("athletes", ["Q2066131", "Q3665646"], 250),
    ("directors", ["Q2526255", "Q3455803"], 150),
    ("businesspeople", ["Q43845", "Q131524"], 150),
    ("comedians", ["Q245068"], 150),
    ("youtubers", ["Q17125263", "Q15214752"], 200),
    ("wrestlers", ["Q13474373"], 150),
    ("tv_presenters", ["Q2405480"], 150),
    ("chefs_designers", ["Q3499072", "Q3501317"], 100),
    ("voice_actors", ["Q18336849"], 100),
    ("social_media", ["Q15214752", "Q28504003"], 100),
]

# Phase 1b: fictional character groups queried by P31 (instance of).
# Each tuple: (label, [instance_QIDs], primary_tag_qid, per_group_limit, is_animated).
# primary_tag_qid is stamped into occupation_ids for question generation.
# is_animated marks cartoon/anime/animated groups so the engine can ask "Is your character animated?"
_FICTIONAL_GROUPS: list[tuple[str, list[str], str, int, bool]] = [
    ("comic_book_characters", ["Q1114461"], "Q1114461", 300, False),
    ("cartoon_characters", ["Q15773317"], "Q15773317", 250, True),
    ("animated_characters", ["Q15632617"], "Q15632617", 200, True),
    ("anime_characters", ["Q1335688"], "Q1335688", 300, True),
    ("video_game_characters", ["Q1798981"], "Q1798981", 300, False),
    ("fictional_humans", ["Q1168287"], "Q1168287", 150, False),
]

# Per-group query for real people (requires P31=Q5).
_GROUP_QUERY = """
SELECT ?person ?personLabel WHERE {{
  VALUES ?occ {{ {occ_list} }}
  ?person wdt:P31 wd:Q5 ;
          wdt:P106 ?occ .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {limit}
"""

# Per-group query for fictional characters (uses P31 instance-of, no Q5 filter).
_FICTIONAL_QUERY = """
SELECT ?person ?personLabel WHERE {{
  VALUES ?type {{ {type_list} }}
  ?person wdt:P31 ?type .
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
LIMIT {limit}
"""

# Phase 2: fetch all properties for a known set of QIDs using VALUES.
# P179 = part of the series/franchise
# P136 = genre (rock, pop, action, drama, ...)
# P463 = member of (bands, organisations, groups)
# P166 = award received (Oscar, Nobel, Grammy, ...)
# P495 = country of origin (for fictional characters / works)
# P1884 = hair colour
_PROPS_QUERY = """
SELECT ?person ?gender ?citizenship ?occupation ?series
       ?genre ?memberOf ?award ?countryOfOrigin ?hairColor
       ?birthYear ?deathYear WHERE {{
  VALUES ?person {{ {qid_list} }}
  OPTIONAL {{ ?person wdt:P21   ?gender }}
  OPTIONAL {{ ?person wdt:P27   ?citizenship }}
  OPTIONAL {{ ?person wdt:P106  ?occupation }}
  OPTIONAL {{ ?person wdt:P179  ?series }}
  OPTIONAL {{ ?person wdt:P136  ?genre }}
  OPTIONAL {{ ?person wdt:P463  ?memberOf }}
  OPTIONAL {{ ?person wdt:P166  ?award }}
  OPTIONAL {{ ?person wdt:P495  ?countryOfOrigin }}
  OPTIONAL {{ ?person wdt:P1884 ?hairColor }}
  OPTIONAL {{
    ?person wdt:P569 ?birthDate .
    BIND(YEAR(?birthDate) AS ?birthYear)
  }}
  OPTIONAL {{
    ?person wdt:P570 ?deathDate .
    BIND(YEAR(?deathDate) AS ?deathYear)
  }}
}}
"""

_BATCH_SIZE = 250
_LABEL_BATCH_SIZE = 500
_INTER_QUERY_DELAY = 1.5  # seconds between queries to be polite to Wikidata

_LABELS_QUERY = """
SELECT ?item ?itemLabel WHERE {{
  VALUES ?item {{ {qid_list} }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
}}
"""


def _extract_qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def _sparql(
    query: str, timeout: int, retry_delay: float, max_attempts: int = 5
) -> list[dict]:
    """Execute a SPARQL query and return the bindings list."""
    for attempt in range(max_attempts):
        try:
            resp = requests.get(
                SPARQL_ENDPOINT,
                params={"query": query, "format": "json"},
                headers={
                    "User-Agent": _USER_AGENT,
                    "Accept": "application/sparql-results+json",
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp.json()["results"]["bindings"]  # type: ignore[no-any-return]
        except requests.RequestException as exc:
            logger.warning(
                "Wikidata request failed (attempt {}/{}): {}",
                attempt + 1,
                max_attempts,
                exc,
            )
            if attempt == max_attempts - 1:
                raise
            delay = retry_delay * (attempt + 1)  # back-off: 1x, 2x, 3x …
            logger.info("Retrying in {:.0f}s…", delay)
            time.sleep(delay)
    return []


def fetch_labels(
    qids: list[str],
    request_timeout: int = 60,
    retry_delay: float = 10.0,
) -> dict[str, str]:
    """Fetch English labels for a list of Wikidata QIDs.

    Returns a mapping of QID → label; QIDs without an English label are omitted.
    """
    if not qids:
        return {}

    labels: dict[str, str] = {}
    total_batches = (len(qids) + _LABEL_BATCH_SIZE - 1) // _LABEL_BATCH_SIZE
    logger.info("Fetching labels for {} QIDs in {} batch(es)", len(qids), total_batches)

    for batch_num, start in enumerate(range(0, len(qids), _LABEL_BATCH_SIZE), start=1):
        batch = qids[start : start + _LABEL_BATCH_SIZE]
        qid_list = " ".join(f"wd:{q}" for q in batch)
        query = _LABELS_QUERY.format(qid_list=qid_list)
        try:
            rows = _sparql(query, timeout=request_timeout, retry_delay=retry_delay)
            for row in rows:
                qid = _extract_qid(row["item"]["value"])
                label = row.get("itemLabel", {}).get("value", qid)
                if not (label.startswith("Q") and label[1:].isdigit()):
                    labels[qid] = label
        except requests.RequestException as exc:
            logger.warning("Label fetch failed for batch {}: {}", batch_num, exc)
        if batch_num < total_batches:
            time.sleep(_INTER_QUERY_DELAY)

    logger.info("Fetched {} labels", len(labels))
    return labels


def fetch_characters(
    target_count: int = 2000,
    min_sitelinks: int = 50,  # kept for API compatibility, no longer used in query
    request_timeout: int = 60,
    retry_delay: float = 10.0,
) -> list[Character]:
    """Fetch famous people and fictional characters from Wikidata.

    Phase 1a: one query per occupation group (real people, P31=Q5).
    Phase 1b: one query per fictional group (P31=instance type).
    Phase 2:  batch-fetch all properties for every discovered QID.
    """
    # ---- Phase 1a: real people by occupation ---------------------------
    persons: dict[str, str] = {}  # qid -> label
    total_groups = len(_OCCUPATION_GROUPS)

    for group_num, (label, occ_ids, per_group_limit) in enumerate(
        _OCCUPATION_GROUPS, start=1
    ):
        if len(persons) >= target_count:
            break
        occ_list = " ".join(f"wd:{q}" for q in occ_ids)
        query = _GROUP_QUERY.format(occ_list=occ_list, limit=per_group_limit)
        logger.info(
            "Phase 1a [{}/{}] fetching {} (limit {})",
            group_num,
            total_groups,
            label,
            per_group_limit,
        )
        rows = _sparql(query, timeout=request_timeout, retry_delay=retry_delay)
        added = 0
        for row in rows:
            qid = _extract_qid(row["person"]["value"])
            name = row.get("personLabel", {}).get("value", qid)
            if name.startswith("Q") and name[1:].isdigit():
                continue
            if qid not in persons:
                persons[qid] = name
                added += 1
        logger.info("  → {} new, {} total", added, len(persons))
        if group_num < total_groups:
            time.sleep(_INTER_QUERY_DELAY)

    order = list(persons.keys())[:target_count]
    logger.info("Phase 1a complete: {} unique real people", len(order))

    # ---- Phase 1b: fictional characters by instance type ---------------
    # fictional_tag: qid -> primary_tag_qid (stamped into occupation_ids)
    # fictional_animated: qids whose group is animated (cartoon/anime/animated)
    fictional_tag: dict[str, str] = {}
    fictional_animated: set[str] = set()
    total_fictional = len(_FICTIONAL_GROUPS)

    for group_num, (
        label,
        type_ids,
        primary_tag,
        per_group_limit,
        animated,
    ) in enumerate(_FICTIONAL_GROUPS, start=1):
        type_list = " ".join(f"wd:{q}" for q in type_ids)
        query = _FICTIONAL_QUERY.format(type_list=type_list, limit=per_group_limit)
        logger.info(
            "Phase 1b [{}/{}] fetching {} (limit {})",
            group_num,
            total_fictional,
            label,
            per_group_limit,
        )
        rows = _sparql(query, timeout=request_timeout, retry_delay=retry_delay)
        added = 0
        for row in rows:
            qid = _extract_qid(row["person"]["value"])
            name = row.get("personLabel", {}).get("value", qid)
            if name.startswith("Q") and name[1:].isdigit():
                continue
            # Real people take priority; don't overwrite with fictional tag
            if qid not in persons and qid not in fictional_tag:
                persons[qid] = name
                fictional_tag[qid] = primary_tag
                if animated:
                    fictional_animated.add(qid)
                added += 1
        logger.info("  → {} new fictional, {} total", added, len(fictional_tag))
        if group_num < total_fictional:
            time.sleep(_INTER_QUERY_DELAY)

    # Merge fictional into the full ordered list (real people first, then fictional)
    fictional_order = [q for q in fictional_tag if q not in set(order)]
    all_order = order + fictional_order
    logger.info(
        "Phase 1 complete: {} real + {} fictional = {} total",
        len(order),
        len(fictional_order),
        len(all_order),
    )

    # ---- Phase 2: fetch properties for all QIDs ------------------------
    records: dict[str, dict] = {
        qid: {
            "wikidata_id": qid,
            "name": persons[qid],
            "gender": None,
            "citizenship_ids": set(),
            "occupation_ids": set(),
            "series_ids": set(),
            "genre_ids": set(),
            "member_of_ids": set(),
            "award_ids": set(),
            "country_of_origin_ids": set(),
            "hair_color": None,
            "birth_year": None,
            "death_year": None,
            "is_fictional": qid in fictional_tag,
            "is_animated": qid in fictional_animated,
        }
        for qid in all_order
    }

    # Pre-stamp the primary type tag into occupation_ids for fictional chars
    for qid, tag in fictional_tag.items():
        if qid in records:
            records[qid]["occupation_ids"].add(tag)

    total_batches = (len(all_order) + _BATCH_SIZE - 1) // _BATCH_SIZE
    logger.info(
        "Phase 2: {} QIDs in {} batch(es) of up to {}",
        len(all_order),
        total_batches,
        _BATCH_SIZE,
    )

    for batch_num, start in enumerate(range(0, len(all_order), _BATCH_SIZE), start=1):
        batch = all_order[start : start + _BATCH_SIZE]
        qid_list = " ".join(f"wd:{q}" for q in batch)
        query2 = _PROPS_QUERY.format(qid_list=qid_list)

        logger.info("  batch {}/{} ({} QIDs)", batch_num, total_batches, len(batch))
        rows2 = _sparql(query2, timeout=request_timeout, retry_delay=retry_delay)

        for row in rows2:
            qid = _extract_qid(row["person"]["value"])
            rec = records.get(qid)
            if rec is None:
                continue
            if "gender" in row and rec["gender"] is None:
                rec["gender"] = _extract_qid(row["gender"]["value"])
            if "citizenship" in row:
                rec["citizenship_ids"].add(_extract_qid(row["citizenship"]["value"]))
            if "occupation" in row:
                rec["occupation_ids"].add(_extract_qid(row["occupation"]["value"]))
            if "series" in row:
                rec["series_ids"].add(_extract_qid(row["series"]["value"]))
            if "genre" in row:
                rec["genre_ids"].add(_extract_qid(row["genre"]["value"]))
            if "memberOf" in row:
                rec["member_of_ids"].add(_extract_qid(row["memberOf"]["value"]))
            if "award" in row:
                rec["award_ids"].add(_extract_qid(row["award"]["value"]))
            if "countryOfOrigin" in row:
                rec["country_of_origin_ids"].add(
                    _extract_qid(row["countryOfOrigin"]["value"])
                )
            if "hairColor" in row and rec["hair_color"] is None:
                rec["hair_color"] = _extract_qid(row["hairColor"]["value"])
            if "birthYear" in row and rec["birth_year"] is None:
                try:
                    rec["birth_year"] = int(row["birthYear"]["value"])
                except ValueError:
                    pass
            if "deathYear" in row and rec["death_year"] is None:
                try:
                    rec["death_year"] = int(row["deathYear"]["value"])
                except ValueError:
                    pass

        if batch_num < total_batches:
            time.sleep(_INTER_QUERY_DELAY)

    # ---- Assemble Character objects ------------------------------------
    characters = [
        Character(
            wikidata_id=rec["wikidata_id"],
            name=rec["name"],
            gender=rec["gender"],
            citizenship_ids=sorted(rec["citizenship_ids"]),
            occupation_ids=sorted(rec["occupation_ids"]),
            series_ids=sorted(rec["series_ids"]),
            genre_ids=sorted(rec["genre_ids"]),
            member_of_ids=sorted(rec["member_of_ids"]),
            award_ids=sorted(rec["award_ids"]),
            country_of_origin_ids=sorted(rec["country_of_origin_ids"]),
            hair_color=rec["hair_color"],
            birth_year=rec["birth_year"],
            death_year=rec["death_year"],
            is_fictional=rec["is_fictional"],
            is_animated=rec["is_animated"],
        )
        for qid in all_order
        if (rec := records.get(qid)) is not None
    ]

    real_count = sum(1 for c in characters if not c.is_fictional)
    fictional_count = sum(1 for c in characters if c.is_fictional)
    animated_count = sum(1 for c in characters if c.is_animated)
    logger.info(
        "Fetch complete: {} real + {} fictional ({} animated) = {} total characters",
        real_count,
        fictional_count,
        animated_count,
        len(characters),
    )
    return characters
