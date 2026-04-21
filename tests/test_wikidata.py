"""Tests for Wikidata parsing logic — no network calls made."""

from unittest.mock import MagicMock, patch

from app.wikidata import _extract_qid, fetch_characters


def test_extract_qid_from_full_uri() -> None:
    assert _extract_qid("http://www.wikidata.org/entity/Q42") == "Q42"


def test_extract_qid_from_bare_value() -> None:
    assert _extract_qid("Q42") == "Q42"


def _make_binding(
    person_uri: str,
    label: str,
    gender_uri: str | None = None,
    citizenship_uri: str | None = None,
    occupation_uri: str | None = None,
    series_uri: str | None = None,
    genre_uri: str | None = None,
    member_of_uri: str | None = None,
    award_uri: str | None = None,
    country_of_origin_uri: str | None = None,
    hair_color_uri: str | None = None,
    birth_year: int | None = None,
    death_year: int | None = None,
) -> dict:
    row: dict = {
        "person": {"value": person_uri},
        "personLabel": {"value": label},
    }
    if gender_uri:
        row["gender"] = {"value": gender_uri}
    if citizenship_uri:
        row["citizenship"] = {"value": citizenship_uri}
    if occupation_uri:
        row["occupation"] = {"value": occupation_uri}
    if series_uri:
        row["series"] = {"value": series_uri}
    if genre_uri:
        row["genre"] = {"value": genre_uri}
    if member_of_uri:
        row["memberOf"] = {"value": member_of_uri}
    if award_uri:
        row["award"] = {"value": award_uri}
    if country_of_origin_uri:
        row["countryOfOrigin"] = {"value": country_of_origin_uri}
    if hair_color_uri:
        row["hairColor"] = {"value": hair_color_uri}
    if birth_year is not None:
        row["birthYear"] = {"value": str(birth_year)}
    if death_year is not None:
        row["deathYear"] = {"value": str(death_year)}
    return row


_FAKE_BINDINGS = [
    # Marie Curie — two occupation rows, one series
    _make_binding(
        "http://www.wikidata.org/entity/Q7186",
        "Marie Curie",
        gender_uri="http://www.wikidata.org/entity/Q6581072",
        citizenship_uri="http://www.wikidata.org/entity/Q142",
        occupation_uri="http://www.wikidata.org/entity/Q901",
        series_uri="http://www.wikidata.org/entity/Q8337",
        genre_uri="http://www.wikidata.org/entity/Q11401",
        member_of_uri="http://www.wikidata.org/entity/Q2735",
        award_uri="http://www.wikidata.org/entity/Q38104",
        country_of_origin_uri="http://www.wikidata.org/entity/Q17",
        hair_color_uri="http://www.wikidata.org/entity/Q1068878",
        birth_year=1867,
        death_year=1934,
    ),
    _make_binding(
        "http://www.wikidata.org/entity/Q7186",
        "Marie Curie",
        occupation_uri="http://www.wikidata.org/entity/Q1650915",
    ),
    # Einstein — alive? No, death_year given
    _make_binding(
        "http://www.wikidata.org/entity/Q937",
        "Albert Einstein",
        gender_uri="http://www.wikidata.org/entity/Q6581097",
        citizenship_uri="http://www.wikidata.org/entity/Q183",
        occupation_uri="http://www.wikidata.org/entity/Q901",
        birth_year=1879,
        death_year=1955,
    ),
    # Entry with no real English label — should be filtered out
    _make_binding(
        "http://www.wikidata.org/entity/Q999999",
        "Q999999",
    ),
]


def _mock_response() -> MagicMock:
    mock = MagicMock()
    mock.json.return_value = {"results": {"bindings": _FAKE_BINDINGS}}
    mock.raise_for_status = MagicMock()
    return mock


@patch("app.wikidata.requests.get")
def test_fetch_returns_correct_count(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    # Q999999 is filtered; two real people remain
    assert len(chars) == 2


@patch("app.wikidata.requests.get")
def test_fetch_aggregates_multiple_occupation_rows(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert "Q901" in curie.occupation_ids
    assert "Q1650915" in curie.occupation_ids


@patch("app.wikidata.requests.get")
def test_fetch_extracts_gender(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert curie.gender == "Q6581072"


@patch("app.wikidata.requests.get")
def test_fetch_extracts_birth_and_death_year(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    einstein = next(c for c in chars if c.wikidata_id == "Q937")
    assert einstein.birth_year == 1879
    assert einstein.death_year == 1955


@patch("app.wikidata.requests.get")
def test_fetch_filters_unlabelled_entries(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    ids = [c.wikidata_id for c in chars]
    assert "Q999999" not in ids


@patch("app.wikidata.requests.get")
def test_fetch_respects_target_count(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=1)
    assert len(chars) == 1


@patch("app.wikidata.requests.get")
def test_fetch_extracts_series_ids(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert "Q8337" in curie.series_ids


@patch("app.wikidata.requests.get")
def test_fetch_extracts_genre_ids(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert "Q11401" in curie.genre_ids


@patch("app.wikidata.requests.get")
def test_fetch_extracts_member_of_ids(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert "Q2735" in curie.member_of_ids


@patch("app.wikidata.requests.get")
def test_fetch_extracts_award_ids(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert "Q38104" in curie.award_ids


@patch("app.wikidata.requests.get")
def test_fetch_extracts_country_of_origin_ids(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert "Q17" in curie.country_of_origin_ids


@patch("app.wikidata.requests.get")
def test_fetch_extracts_hair_color(mock_get: MagicMock) -> None:
    mock_get.return_value = _mock_response()
    chars = fetch_characters(target_count=10)
    curie = next(c for c in chars if c.wikidata_id == "Q7186")
    assert curie.hair_color == "Q1068878"
