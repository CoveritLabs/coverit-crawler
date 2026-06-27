from src.utils.url import normalize_url


def test_normalize_url_converts_none_to_empty_string():
    assert normalize_url(None) == ""
