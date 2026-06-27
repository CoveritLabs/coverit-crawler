from src.utils.coercion import coerce_str


def test_coerce_str_converts_number():
    assert coerce_str(123, "fallback") == "123"
