from src.utils.coercion import coerce_bool


def test_coerce_bool_accepts_false_words():
    assert coerce_bool(" off ", True) is False
