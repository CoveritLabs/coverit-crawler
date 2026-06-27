from src.utils.coercion import coerce_float


def test_coerce_float_parses_string():
    assert coerce_float(" 2.5 ", 1.5) == 2.5
