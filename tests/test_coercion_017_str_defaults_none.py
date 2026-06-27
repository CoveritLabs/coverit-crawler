from src.utils.coercion import coerce_str


def test_coerce_str_defaults_for_none():
    assert coerce_str(None, "fallback") == "fallback"
