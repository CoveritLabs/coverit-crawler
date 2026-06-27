from src.utils.coercion import coerce_int


def test_coerce_int_defaults_for_bool():
    assert coerce_int(True, 3) == 3
