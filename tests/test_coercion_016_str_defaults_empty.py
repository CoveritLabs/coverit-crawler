from src.utils.coercion import coerce_str


def test_coerce_str_defaults_for_empty_string():
    assert coerce_str(" ", "fallback") == "fallback"
