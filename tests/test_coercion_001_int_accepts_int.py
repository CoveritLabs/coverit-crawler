from src.utils.coercion import coerce_int


def test_coerce_int_accepts_int():
    assert coerce_int(7, 3) == 7
