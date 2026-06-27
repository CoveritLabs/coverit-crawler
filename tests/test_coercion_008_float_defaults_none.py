from src.utils.coercion import coerce_float


def test_coerce_float_defaults_for_none():
    assert coerce_float(None, 1.5) == 1.5
