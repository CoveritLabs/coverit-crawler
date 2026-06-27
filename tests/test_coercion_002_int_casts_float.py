from src.utils.coercion import coerce_int


def test_coerce_int_casts_float():
    assert coerce_int(7.9, 3) == 7
