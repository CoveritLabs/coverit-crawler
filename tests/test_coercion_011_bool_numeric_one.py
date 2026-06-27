from src.utils.coercion import coerce_bool


def test_coerce_bool_converts_numeric_one():
    assert coerce_bool(1, False) is True
