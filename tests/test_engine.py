"""Tests for the Bayesian inference engine — no database required."""

import numpy as np
import pytest

from app.game.engine import AkinatorEngine, _entropy_cols
from app.models import Character
from app.game.questions import (
    QuestionDef,
    generate_question_specs,
    specs_to_question_defs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_characters() -> list[Character]:
    return [
        Character(
            wikidata_id="Q1",
            name="Alice",
            gender="Q6581072",  # female
            citizenship_ids=["Q30"],  # USA
            occupation_ids=["Q639669"],  # musician
            series_ids=["Q8337"],  # Harry Potter
            birth_year=1985,
            death_year=None,
        ),
        Character(
            wikidata_id="Q2",
            name="Bob",
            gender="Q6581097",  # male
            citizenship_ids=["Q145"],  # UK
            occupation_ids=["Q82955"],  # politician
            series_ids=["Q8337"],  # Harry Potter
            birth_year=1950,
            death_year=None,
        ),
        Character(
            wikidata_id="Q3",
            name="Charlie",
            gender="Q6581097",  # male
            citizenship_ids=["Q142"],  # France
            occupation_ids=["Q36180"],  # writer
            series_ids=[],
            birth_year=1820,
            death_year=1895,
        ),
    ]


def make_questions(characters: list[Character] | None = None) -> list[QuestionDef]:
    chars = characters or make_characters()
    specs = generate_question_specs(chars, {})
    return specs_to_question_defs(specs)


def _find_q(
    questions: list[QuestionDef],
    question_type: str,
    qid: str | None = None,
) -> int:
    for i, q in enumerate(questions):
        if q.question_type == question_type and (qid is None or q.qid == qid):
            return i
    raise KeyError(f"No question: type={question_type!r}, qid={qid!r}")


@pytest.fixture
def engine() -> AkinatorEngine:
    chars = make_characters()
    questions = make_questions(chars)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)
    return AkinatorEngine(
        chars, questions, likelihoods, guess_threshold=0.5, max_questions=len(questions)
    )


# ---------------------------------------------------------------------------
# build_likelihoods
# ---------------------------------------------------------------------------


def test_likelihoods_shape() -> None:
    chars = make_characters()
    questions = make_questions(chars)
    mat = AkinatorEngine.build_likelihoods(chars, questions)
    assert mat.shape == (3, len(questions))
    assert mat.dtype == np.float32


def test_likelihoods_clipped_away_from_zero_and_one() -> None:
    chars = make_characters()
    questions = make_questions(chars)
    mat = AkinatorEngine.build_likelihoods(chars, questions)
    assert float(mat.min()) > 0.0
    assert float(mat.max()) < 1.0


def test_likelihoods_female_predicate() -> None:
    chars = make_characters()
    questions = make_questions(chars)
    mat = AkinatorEngine.build_likelihoods(chars, questions)
    female_idx = _find_q(questions, "gender", "Q6581072")
    assert mat[0, female_idx] > 0.9  # Alice is female → near 1
    assert mat[1, female_idx] < 0.1  # Bob is male → near 0
    assert mat[2, female_idx] < 0.1  # Charlie is male → near 0


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_restores_uniform_prior(engine: AkinatorEngine) -> None:
    engine.update(0, 1.0)
    engine.update(1, 0.0)
    engine.reset()

    n = len(engine.characters)
    expected = np.full(n, 1.0 / n, dtype=np.float32)
    np.testing.assert_allclose(engine._probs, expected, rtol=1e-5)
    assert len(engine.asked) == 0
    assert len(engine.session_answers) == 0


# ---------------------------------------------------------------------------
# update (Bayesian inference)
# ---------------------------------------------------------------------------


def test_update_yes_raises_probability_of_matching_character(
    engine: AkinatorEngine,
) -> None:
    female_idx = _find_q(engine.questions, "gender", "Q6581072")
    engine.update(female_idx, 1.0)
    assert engine._probs[0] > engine._probs[1]
    assert engine._probs[0] > engine._probs[2]


def test_update_no_lowers_probability_of_matching_character(
    engine: AkinatorEngine,
) -> None:
    female_idx = _find_q(engine.questions, "gender", "Q6581072")
    engine.update(female_idx, 0.0)
    assert engine._probs[0] < engine._probs[1]


def test_update_probs_sum_to_one(engine: AkinatorEngine) -> None:
    engine.update(0, 1.0)
    engine.update(1, 0.0)
    assert abs(float(engine._probs.sum()) - 1.0) < 1e-5


def test_update_records_asked_and_session_answers(engine: AkinatorEngine) -> None:
    engine.update(3, 0.75)
    assert 3 in engine.asked
    assert engine.session_answers[3] == pytest.approx(0.75)


def test_update_fuzzy_maybe_has_smaller_effect_than_yes(engine: AkinatorEngine) -> None:
    chars = make_characters()
    questions = make_questions(chars)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)

    e_yes = AkinatorEngine(chars, questions, likelihoods.copy())
    e_maybe = AkinatorEngine(chars, questions, likelihoods.copy())

    female_idx = _find_q(questions, "gender", "Q6581072")
    e_yes.update(female_idx, 1.0)
    e_maybe.update(female_idx, 0.5)

    diff_yes = abs(float(e_yes._probs[0]) - 1.0 / 3)
    diff_maybe = abs(float(e_maybe._probs[0]) - 1.0 / 3)
    assert diff_yes > diff_maybe


# ---------------------------------------------------------------------------
# best_question
# ---------------------------------------------------------------------------


def test_best_question_returns_valid_index(engine: AkinatorEngine) -> None:
    q_idx = engine.best_question()
    assert 0 <= q_idx < len(engine.questions)


def test_best_question_excludes_already_asked(engine: AkinatorEngine) -> None:
    first = engine.best_question()
    engine.update(first, 1.0)
    second = engine.best_question()
    assert second != first


def test_best_question_raises_when_all_asked(engine: AkinatorEngine) -> None:
    for i in range(len(engine.questions)):
        engine.asked.add(i)
    with pytest.raises(RuntimeError, match="All questions have been asked"):
        engine.best_question()


def test_best_question_top_k_returns_valid_index() -> None:
    chars = make_characters()
    questions = make_questions(chars)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)
    eng = AkinatorEngine(chars, questions, likelihoods, top_k=3)
    q_idx = eng.best_question()
    assert 0 <= q_idx < len(questions)


def test_best_question_top_k_produces_variety() -> None:
    """With top_k>1 the engine should not always pick the same first question."""
    chars = make_characters()
    questions = make_questions(chars)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)
    eng = AkinatorEngine(chars, questions, likelihoods, top_k=len(questions))
    seen = {eng.best_question() for _ in range(30)}
    assert len(seen) > 1, "top_k randomisation should produce varied question choices"


# ---------------------------------------------------------------------------
# is_fictional question type
# ---------------------------------------------------------------------------


def make_mixed_characters() -> list[Character]:
    """Three real + two fictional characters for is_fictional/is_animated tests."""
    real = make_characters()
    fictional = [
        Character(
            wikidata_id="Q101",
            name="Spider-Man",
            gender="Q6581097",
            citizenship_ids=[],
            occupation_ids=["Q188784"],  # superhero
            series_ids=["Q574"],  # Marvel Universe
            birth_year=None,
            death_year=None,
            is_fictional=True,
            is_animated=False,
        ),
        Character(
            wikidata_id="Q102",
            name="Pikachu",
            gender=None,
            citizenship_ids=[],
            occupation_ids=["Q1798981"],  # video game character
            series_ids=["Q399"],  # Pokémon
            birth_year=None,
            death_year=None,
            is_fictional=True,
            is_animated=True,
        ),
    ]
    return real + fictional


def test_is_fictional_question_generated() -> None:
    chars = make_mixed_characters()
    specs = generate_question_specs(chars, {})
    types = [s["question_type"] for s in specs]
    assert "is_fictional" in types


def test_is_fictional_predicate_true_for_fictional(engine: AkinatorEngine) -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("is_fictional", None, None, None)
    fictional_char = Character(
        wikidata_id="Q999",
        name="Fake",
        is_fictional=True,
    )
    real_char = Character(wikidata_id="Q998", name="Real", is_fictional=False)
    assert pred(fictional_char) is True
    assert pred(real_char) is False


def test_is_fictional_bayesian_update() -> None:
    chars = make_mixed_characters()
    specs = generate_question_specs(chars, {})
    questions = specs_to_question_defs(specs)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)
    eng = AkinatorEngine(chars, questions, likelihoods)

    fictional_idx = next(
        i for i, q in enumerate(questions) if q.question_type == "is_fictional"
    )
    eng.update(fictional_idx, 1.0)  # "yes, fictional"
    top, _ = eng.top_guess()
    assert top.is_fictional


# ---------------------------------------------------------------------------
# is_animated question type
# ---------------------------------------------------------------------------


def test_is_animated_question_generated() -> None:
    chars = make_mixed_characters()
    specs = generate_question_specs(chars, {})
    types = [s["question_type"] for s in specs]
    assert "is_animated" in types


def test_is_animated_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("is_animated", None, None, None)
    assert pred(Character(wikidata_id="Q1", name="A", is_animated=True)) is True
    assert pred(Character(wikidata_id="Q2", name="B", is_animated=False)) is False


def test_is_animated_bayesian_update() -> None:
    chars = make_mixed_characters()
    specs = generate_question_specs(chars, {})
    questions = specs_to_question_defs(specs)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)
    eng = AkinatorEngine(chars, questions, likelihoods)

    animated_idx = next(
        i for i, q in enumerate(questions) if q.question_type == "is_animated"
    )
    eng.update(animated_idx, 1.0)  # "yes, animated"
    top, _ = eng.top_guess()
    assert top.is_animated


# ---------------------------------------------------------------------------
# franchise question type
# ---------------------------------------------------------------------------


def test_franchise_question_generated() -> None:
    chars = make_characters()  # Alice + Bob share Q8337 (Harry Potter)
    specs = generate_question_specs(chars, {"Q8337": "Harry Potter"})
    types = [s["question_type"] for s in specs]
    assert "franchise" in types


def test_franchise_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("franchise", "Q8337", None, None)
    in_series = Character(wikidata_id="Q1", name="A", series_ids=["Q8337"])
    not_in_series = Character(wikidata_id="Q2", name="B", series_ids=[])
    assert pred(in_series) is True
    assert pred(not_in_series) is False


def test_franchise_bayesian_update() -> None:
    chars = make_characters()  # Alice + Bob have Q8337; Charlie doesn't
    specs = generate_question_specs(chars, {"Q8337": "Harry Potter"})
    questions = specs_to_question_defs(specs)
    likelihoods = AkinatorEngine.build_likelihoods(chars, questions)
    eng = AkinatorEngine(chars, questions, likelihoods)

    franchise_idx = next(
        i for i, q in enumerate(questions) if q.question_type == "franchise"
    )
    eng.update(franchise_idx, 0.0)  # "no, not from this franchise"
    # Charlie (no series) should now be most probable
    top, _ = eng.top_guess()
    assert top.wikidata_id == "Q3"


# ---------------------------------------------------------------------------
# top_guess / should_guess
# ---------------------------------------------------------------------------


def test_top_guess_returns_character_and_probability(engine: AkinatorEngine) -> None:
    char, prob = engine.top_guess()
    assert isinstance(char, Character)
    assert 0.0 <= prob <= 1.0


def test_should_guess_false_at_start(engine: AkinatorEngine) -> None:
    assert not engine.should_guess()


def test_should_guess_true_after_convergence(engine: AkinatorEngine) -> None:
    female_idx = _find_q(engine.questions, "gender", "Q6581072")
    uk_idx = _find_q(engine.questions, "citizenship", "Q145")
    fr_idx = _find_q(engine.questions, "citizenship", "Q142")
    engine.update(female_idx, 1.0)
    engine.update(uk_idx, 0.0)
    engine.update(fr_idx, 0.0)
    assert engine.should_guess()


def test_should_guess_true_after_max_questions(engine: AkinatorEngine) -> None:
    chars = make_characters()
    questions = make_questions(chars)
    engine_short = AkinatorEngine(
        chars,
        questions,
        AkinatorEngine.build_likelihoods(chars, questions),
        max_questions=1,
    )
    engine_short.update(0, 0.5)
    assert engine_short.should_guess()


# ---------------------------------------------------------------------------
# absorb_feedback
# ---------------------------------------------------------------------------


def test_absorb_feedback_nudges_likelihood(engine: AkinatorEngine) -> None:
    female_idx = _find_q(engine.questions, "gender", "Q6581072")
    engine.update(female_idx, 1.0)
    original = float(engine.likelihoods[0, female_idx])
    engine.absorb_feedback(correct_char_idx=0, learning_rate=0.1)
    assert float(engine.likelihoods[0, female_idx]) >= original


def test_absorb_feedback_keeps_likelihoods_in_bounds(engine: AkinatorEngine) -> None:
    for q_idx in range(len(engine.questions)):
        engine.session_answers[q_idx] = 1.0
    engine.absorb_feedback(0, learning_rate=0.9)
    assert float(engine.likelihoods.min()) > 0.0
    assert float(engine.likelihoods.max()) < 1.0


# ---------------------------------------------------------------------------
# character_index
# ---------------------------------------------------------------------------


def test_character_index_found(engine: AkinatorEngine) -> None:
    assert engine.character_index("Q2") == 1


def test_character_index_not_found(engine: AkinatorEngine) -> None:
    assert engine.character_index("Q999") is None


# ---------------------------------------------------------------------------
# _entropy_cols
# ---------------------------------------------------------------------------


def test_entropy_cols_uniform_is_maximum() -> None:
    uniform = np.full((4, 2), 0.25, dtype=np.float32)
    skewed = np.array(
        [[0.9, 0.1], [0.9, 0.1], [0.9, 0.1], [0.9, 0.1]], dtype=np.float32
    )
    assert float(_entropy_cols(uniform)[0]) > float(_entropy_cols(skewed)[0])


def test_entropy_cols_output_shape() -> None:
    mat = np.random.rand(100, 5).astype(np.float32)
    assert _entropy_cols(mat).shape == (5,)


# ---------------------------------------------------------------------------
# genre / member_of / award / country_of_origin / hair_color question types
# ---------------------------------------------------------------------------


def make_rich_characters() -> list[Character]:
    """Characters with genre, member_of, award, country_of_origin, hair_color for coverage."""
    base = [
        Character(
            wikidata_id=f"Q{i}",
            name=f"Char{i}",
            genre_ids=["Q11401"] if i < 2 else [],
            member_of_ids=["Q2735"] if i < 2 else [],
            award_ids=["Q38104"] if i < 2 else [],
            country_of_origin_ids=["Q17"] if i < 2 else [],
            hair_color="Q1068878" if i < 2 else None,
        )
        for i in range(3)
    ]
    return base


def test_genre_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("genre", "Q11401", None, None)
    assert pred(Character(wikidata_id="Q1", name="A", genre_ids=["Q11401"])) is True
    assert pred(Character(wikidata_id="Q2", name="B", genre_ids=[])) is False


def test_member_of_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("member_of", "Q2735", None, None)
    assert pred(Character(wikidata_id="Q1", name="A", member_of_ids=["Q2735"])) is True
    assert pred(Character(wikidata_id="Q2", name="B", member_of_ids=[])) is False


def test_award_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("award", "Q38104", None, None)
    assert pred(Character(wikidata_id="Q1", name="A", award_ids=["Q38104"])) is True
    assert pred(Character(wikidata_id="Q2", name="B", award_ids=[])) is False


def test_country_of_origin_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("country_of_origin", "Q17", None, None)
    assert (
        pred(Character(wikidata_id="Q1", name="A", country_of_origin_ids=["Q17"]))
        is True
    )
    assert (
        pred(Character(wikidata_id="Q2", name="B", country_of_origin_ids=[])) is False
    )


def test_hair_color_predicate() -> None:
    from app.game.questions import make_predicate

    pred = make_predicate("hair_color", "Q1068878", None, None)
    assert pred(Character(wikidata_id="Q1", name="A", hair_color="Q1068878")) is True
    assert pred(Character(wikidata_id="Q2", name="B", hair_color=None)) is False
    assert pred(Character(wikidata_id="Q3", name="C", hair_color="Q167475")) is False


def test_genre_question_generated() -> None:
    chars = make_rich_characters()
    specs = generate_question_specs(chars, {"Q11401": "rock music"})
    types = [s["question_type"] for s in specs]
    assert "genre" in types


def test_member_of_question_generated() -> None:
    chars = make_rich_characters()
    specs = generate_question_specs(chars, {"Q2735": "The Beatles"})
    types = [s["question_type"] for s in specs]
    assert "member_of" in types


def test_award_question_generated() -> None:
    chars = make_rich_characters()
    specs = generate_question_specs(chars, {"Q38104": "Grammy Award"})
    types = [s["question_type"] for s in specs]
    assert "award" in types


def test_country_of_origin_question_generated() -> None:
    chars = make_rich_characters()
    specs = generate_question_specs(chars, {"Q17": "Japan"})
    types = [s["question_type"] for s in specs]
    assert "country_of_origin" in types


def test_hair_color_question_generated() -> None:
    chars = make_rich_characters()
    specs = generate_question_specs(chars, {"Q1068878": "blond"})
    types = [s["question_type"] for s in specs]
    assert "hair_color" in types
