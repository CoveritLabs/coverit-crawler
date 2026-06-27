from src.utils.coercion import coerce_bool


def test_coerce_bool_converts_numeric_zero():
    assert coerce_bool(0, True) is False
