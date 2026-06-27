from src.utils.url import normalize_url


def test_normalize_url_keeps_non_empty_query_string():
    assert normalize_url("https://example.com/path?q=1") == "https://example.com/path?q=1"
