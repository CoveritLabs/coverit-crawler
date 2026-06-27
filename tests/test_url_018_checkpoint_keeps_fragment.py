from src.utils.url import normalize_checkpoint_url


def test_checkpoint_url_keeps_fragment():
    assert normalize_checkpoint_url("https://example.com/#home") == "https://example.com/#home"
