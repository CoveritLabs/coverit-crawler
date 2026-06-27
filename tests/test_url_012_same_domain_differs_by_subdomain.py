from src.utils.url import is_same_domain


def test_same_domain_treats_subdomain_as_different_netloc():
    assert not is_same_domain("https://example.com", "https://app.example.com")
