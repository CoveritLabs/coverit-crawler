from src.utils.url import is_non_http_href


def test_non_http_href_rejects_empty_href():
    assert not is_non_http_href("")
