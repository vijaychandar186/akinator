from app.core import add_random_offset


def test_add_random_offset_within_bounds() -> None:
    result = add_random_offset(0)
    assert 0 <= result <= 100


def test_add_random_offset_custom_max() -> None:
    result = add_random_offset(10, max_offset=50)
    assert 10 <= result <= 60


def test_add_random_offset_preserves_base() -> None:
    result = add_random_offset(500)
    assert result >= 500
