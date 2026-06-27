from src.utils.coercion import coerce_int


def test_coerce_int_parses_string():
    assert coerce_int(" 42 ", 3) == 42
