from src.utils.url import is_http_url


def test_http_url_trims_surrounding_whitespace():
    assert is_http_url("  HTTPS://example.com  ")
