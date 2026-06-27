from src.utils.url import normalize_url


def test_normalize_url_removes_fragment():
    assert normalize_url("https://example.com/path#section") == "https://example.com/path"
