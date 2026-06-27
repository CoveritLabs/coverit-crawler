from src.utils.url import is_non_http_href


def test_non_http_href_accepts_mailto_href():
    assert is_non_http_href("mailto:test@example.com")
