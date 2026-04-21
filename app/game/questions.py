from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Callable

from app.models import Character


@dataclass(frozen=True)
class QuestionDef:
    id: int
    text: str
    predicate: Callable[[Character], bool]
    question_type: str
    qid: str | None = None
    threshold_low: int | None = None
    threshold_high: int | None = None


def make_predicate(
    question_type: str,
    qid: str | None,
    threshold_low: int | None,
    threshold_high: int | None,
) -> Callable[[Character], bool]:
    """Reconstruct a character predicate from serialised question metadata."""
    if question_type == "gender":
        assert qid is not None
        _qid = qid
        return lambda c: c.gender == _qid
    if question_type == "citizenship":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.citizenship_ids
    if question_type == "occupation":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.occupation_ids
    if question_type == "birth_before":
        assert threshold_high is not None
        _th = threshold_high
        return lambda c: c.birth_year is not None and c.birth_year < _th
    if question_type == "birth_range":
        assert threshold_low is not None and threshold_high is not None
        _lo, _hi = threshold_low, threshold_high
        return lambda c: c.birth_year is not None and _lo <= c.birth_year < _hi
    if question_type == "alive":
        return lambda c: c.death_year is None
    if question_type == "is_fictional":
        return lambda c: c.is_fictional
    if question_type == "is_animated":
        return lambda c: c.is_animated
    if question_type == "franchise":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.series_ids
    if question_type == "genre":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.genre_ids
    if question_type == "member_of":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.member_of_ids
    if question_type == "award":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.award_ids
    if question_type == "country_of_origin":
        assert qid is not None
        _qid = qid
        return lambda c: _qid in c.country_of_origin_ids
    if question_type == "hair_color":
        assert qid is not None
        _qid = qid
        return lambda c: c.hair_color == _qid
    raise ValueError(f"Unknown question_type: {question_type!r}")


def generate_question_specs(
    characters: list[Character],
    labels: dict[str, str],
    min_prevalence: float = 0.02,
    max_prevalence: float = 0.98,
) -> list[dict]:
    """Generate binary question definitions from the character corpus.

    Only questions whose positive rate falls in [min_prevalence, max_prevalence]
    are kept — ensuring every question has meaningful information-gain potential.
    """
    n = len(characters)
    if n == 0:
        return []

    specs: list[dict] = []
    seen: set[tuple] = set()

    def _add(spec: dict) -> None:
        key = (
            spec["question_type"],
            spec.get("qid"),
            spec.get("threshold_low"),
            spec.get("threshold_high"),
        )
        if key not in seen:
            seen.add(key)
            specs.append(spec)

    def _prev(count: int) -> float:
        return count / n

    def _ok(count: int) -> bool:
        return min_prevalence <= _prev(count) <= max_prevalence

    # Alive
    alive_count = sum(1 for c in characters if c.death_year is None)
    if _ok(alive_count):
        _add(
            {
                "question_type": "alive",
                "qid": None,
                "threshold_low": None,
                "threshold_high": None,
                "text": "Is this person still alive?",
                "prevalence": _prev(alive_count),
            }
        )

    # Fictional vs real
    fictional_count = sum(1 for c in characters if c.is_fictional)
    if _ok(fictional_count):
        _add(
            {
                "question_type": "is_fictional",
                "qid": None,
                "threshold_low": None,
                "threshold_high": None,
                "text": "Is this a fictional character?",
                "prevalence": _prev(fictional_count),
            }
        )

    # Animated — the real Akinator's #1 opening question (avg position 0.45)
    animated_count = sum(1 for c in characters if c.is_animated)
    if _ok(animated_count):
        _add(
            {
                "question_type": "is_animated",
                "qid": None,
                "threshold_low": None,
                "threshold_high": None,
                "text": "Is your character animated?",
                "prevalence": _prev(animated_count),
            }
        )

    # Franchise/series — e.g. Harry Potter (853 games), Star Wars, Dragon Ball Z
    series_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for sid in c.series_ids:
            series_counts[sid] += 1
    for sid, count in sorted(series_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(sid, sid)
        _add(
            {
                "question_type": "franchise",
                "qid": sid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Is your character from {label}?",
                "prevalence": _prev(count),
            }
        )

    # Gender (most common first for stable ordering)
    gender_counts: Counter[str] = Counter(
        c.gender for c in characters if c.gender is not None
    )
    for gender_qid, count in gender_counts.most_common():
        if not _ok(count):
            continue
        if gender_qid == "Q6581072":
            text = "Is this person a woman?"
        elif gender_qid == "Q6581097":
            text = "Is this person a man?"
        else:
            text = f"Is this person {labels.get(gender_qid, gender_qid)}?"
        _add(
            {
                "question_type": "gender",
                "qid": gender_qid,
                "threshold_low": None,
                "threshold_high": None,
                "text": text,
                "prevalence": _prev(count),
            }
        )

    # Citizenship — most frequent countries first
    citizenship_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for cid in c.citizenship_ids:
            citizenship_counts[cid] += 1
    for cid, count in sorted(citizenship_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(cid, cid)
        _add(
            {
                "question_type": "citizenship",
                "qid": cid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Is this person from {label}?",
                "prevalence": _prev(count),
            }
        )

    # Occupation — most frequent roles first
    occupation_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for oid in c.occupation_ids:
            occupation_counts[oid] += 1
    for oid, count in sorted(occupation_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(oid, oid)
        _add(
            {
                "question_type": "occupation",
                "qid": oid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Is this person a {label}?",
                "prevalence": _prev(count),
            }
        )

    # Genre (rock, pop, drama, action, …)
    genre_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for gid in c.genre_ids:
            genre_counts[gid] += 1
    for gid, count in sorted(genre_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(gid, gid)
        _add(
            {
                "question_type": "genre",
                "qid": gid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Is your character associated with {label}?",
                "prevalence": _prev(count),
            }
        )

    # Member of (bands, organisations, groups)
    member_of_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for mid in c.member_of_ids:
            member_of_counts[mid] += 1
    for mid, count in sorted(member_of_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(mid, mid)
        _add(
            {
                "question_type": "member_of",
                "qid": mid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Is your character a member of {label}?",
                "prevalence": _prev(count),
            }
        )

    # Award received (Oscar, Nobel, Grammy, …)
    award_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for aid in c.award_ids:
            award_counts[aid] += 1
    for aid, count in sorted(award_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(aid, aid)
        _add(
            {
                "question_type": "award",
                "qid": aid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Has your character won {label}?",
                "prevalence": _prev(count),
            }
        )

    # Country of origin — for fictional works (Japanese anime, American cartoon, …)
    coo_counts: dict[str, int] = defaultdict(int)
    for c in characters:
        for cid in c.country_of_origin_ids:
            coo_counts[cid] += 1
    for cid, count in sorted(coo_counts.items(), key=lambda x: -x[1]):
        if not _ok(count):
            continue
        label = labels.get(cid, cid)
        _add(
            {
                "question_type": "country_of_origin",
                "qid": cid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Is your character originally from {label}?",
                "prevalence": _prev(count),
            }
        )

    # Hair colour (blonde, brunette, red-haired, …)
    hair_counts: Counter[str] = Counter(
        c.hair_color for c in characters if c.hair_color is not None
    )
    for hid, count in hair_counts.most_common():
        if not _ok(count):
            continue
        label = labels.get(hid, hid)
        _add(
            {
                "question_type": "hair_color",
                "qid": hid,
                "threshold_low": None,
                "threshold_high": None,
                "text": f"Does your character have {label} hair?",
                "prevalence": _prev(count),
            }
        )

    # Birth decades
    birth_years = [c.birth_year for c in characters if c.birth_year is not None]
    if birth_years:
        min_year = min(birth_years)
        max_year = max(birth_years)
        for decade in range((min_year // 10) * 10, ((max_year // 10) + 1) * 10, 10):
            count = sum(1 for y in birth_years if decade <= y < decade + 10)
            if not _ok(count):
                continue
            _add(
                {
                    "question_type": "birth_range",
                    "qid": None,
                    "threshold_low": decade,
                    "threshold_high": decade + 10,
                    "text": f"Was this person born in the {decade}s?",
                    "prevalence": _prev(count),
                }
            )
        # Half-century cutoffs for coarser discrimination
        for year in [1800, 1850, 1900, 1950]:
            count = sum(1 for y in birth_years if y < year)
            if not _ok(count):
                continue
            _add(
                {
                    "question_type": "birth_before",
                    "qid": None,
                    "threshold_low": None,
                    "threshold_high": year,
                    "text": f"Was this person born before {year}?",
                    "prevalence": _prev(count),
                }
            )

    for i, spec in enumerate(specs):
        spec["id"] = i

    return specs


def specs_to_question_defs(specs: list[dict]) -> list[QuestionDef]:
    """Convert serialisable specs to QuestionDef objects with live predicates."""
    return [
        QuestionDef(
            id=spec["id"],
            text=spec["text"],
            predicate=make_predicate(
                spec["question_type"],
                spec.get("qid"),
                spec.get("threshold_low"),
                spec.get("threshold_high"),
            ),
            question_type=spec["question_type"],
            qid=spec.get("qid"),
            threshold_low=spec.get("threshold_low"),
            threshold_high=spec.get("threshold_high"),
        )
        for spec in specs
    ]
