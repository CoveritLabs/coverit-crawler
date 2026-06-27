from src.utils.url import is_http_url


def test_http_url_rejects_ftp_scheme():
    assert not is_http_url("ftp://example.com")
