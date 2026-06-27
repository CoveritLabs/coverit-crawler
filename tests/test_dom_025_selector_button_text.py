from src.utils.dom import build_selector


def test_build_selector_uses_button_text():
    assert build_selector({"tag": "button", "text": "Save"}) == 'button:has-text("Save")'
