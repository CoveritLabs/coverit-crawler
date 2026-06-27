from src.utils.url import is_http_url


def test_http_url_accepts_https_scheme():
    assert is_http_url("https://example.com/path")
