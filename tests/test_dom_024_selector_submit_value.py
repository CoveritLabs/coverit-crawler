from src.utils.dom import build_selector


def test_build_selector_uses_submit_value():
    assert build_selector({"tag": "input", "type": "submit", "value": "Go"}) == 'input[type="submit"][value="Go"]'
