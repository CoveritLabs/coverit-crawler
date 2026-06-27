from src.utils.dom import build_selector


def test_build_selector_uses_anchor_text():
    assert build_selector({"tag": "a", "text": "Details"}) == 'a:has-text("Details")'
