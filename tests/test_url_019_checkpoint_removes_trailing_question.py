from src.utils.url import normalize_checkpoint_url


def test_checkpoint_url_removes_trailing_question_mark():
    assert normalize_checkpoint_url("https://example.com?") == "https://example.com"
