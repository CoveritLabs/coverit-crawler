from src.utils.url import normalize_url


def test_normalize_url_removes_trailing_question_mark():
    assert normalize_url("https://example.com/path?") == "https://example.com/path"
