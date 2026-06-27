from src.utils.coercion import coerce_str


def test_coerce_str_accepts_string_and_strips():
    assert coerce_str(" hello ", "fallback") == "hello"
