from src.utils.url import is_same_domain


def test_same_domain_treats_port_as_part_of_netloc():
    assert not is_same_domain("http://localhost:3000", "http://localhost:4000")
