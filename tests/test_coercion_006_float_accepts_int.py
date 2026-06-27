from src.utils.coercion import coerce_float


def test_coerce_float_accepts_int():
    assert coerce_float(5, 1.5) == 5.0
