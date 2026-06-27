import pytest

from src.utils.coercion import coerce_float


def test_coerce_float_invalid_string_raises_value_error():
    with pytest.raises(ValueError):
        coerce_float("abc", 1.0)
