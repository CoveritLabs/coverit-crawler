from src.utils.url import is_http_url


def test_http_url_rejects_empty_values():
    assert not is_http_url("")
