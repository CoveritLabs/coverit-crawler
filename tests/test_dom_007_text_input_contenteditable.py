from src.utils.dom import is_text_input


def test_is_text_input_accepts_contenteditable():
    assert is_text_input({"tag": "div", "contenteditable": True})
