from src.utils.url import is_http_url


def test_http_url_rejects_relative_path():
    assert not is_http_url("/relative")
