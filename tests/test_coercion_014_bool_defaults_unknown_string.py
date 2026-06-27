from src.utils.coercion import coerce_bool


def test_coerce_bool_defaults_for_unknown_string():
    assert coerce_bool("maybe", True) is True
