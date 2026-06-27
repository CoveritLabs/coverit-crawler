from src.utils.url import is_http_url


def test_http_url_accepts_plain_http_scheme():
    assert is_http_url("http://example.com")
