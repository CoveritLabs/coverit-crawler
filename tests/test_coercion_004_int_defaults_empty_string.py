from src.utils.coercion import coerce_int


def test_coerce_int_defaults_for_empty_string():
    assert coerce_int("   ", 3) == 3
