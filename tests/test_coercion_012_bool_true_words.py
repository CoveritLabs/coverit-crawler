from src.utils.coercion import coerce_bool


def test_coerce_bool_accepts_true_words():
    assert coerce_bool(" YES ", False) is True
