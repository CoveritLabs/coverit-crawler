from src.utils.url import is_non_http_href


def test_non_http_href_accepts_tel_href():
    assert is_non_http_href("tel:+15551234567")
