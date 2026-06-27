from src.utils.url import is_same_domain


def test_same_domain_matches_same_host():
    assert is_same_domain("https://example.com/a", "https://example.com/b")
