import pytest

from src.utils.coercion import coerce_int


def test_coerce_int_invalid_string_raises_value_error():
    with pytest.raises(ValueError):
        coerce_int("abc", 1)
