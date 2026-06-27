from src.utils.coercion import coerce_bool


def test_coerce_bool_accepts_bool():
    assert coerce_bool(False, True) is False
