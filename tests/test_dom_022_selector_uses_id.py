from src.utils.dom import build_selector


def test_build_selector_uses_non_numeric_id():
    assert build_selector({"tag": "input", "id": "email"}) == "#email"
