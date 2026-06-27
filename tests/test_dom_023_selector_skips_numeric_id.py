from src.utils.dom import build_selector


def test_build_selector_skips_numeric_id_and_uses_name():
    assert build_selector({"tag": "input", "id": "123", "name": "email"}) == '[name="email"]'
