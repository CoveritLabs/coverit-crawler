from src.utils.dom import is_text_input


def test_is_text_input_accepts_textarea_tag():
    assert is_text_input({"tag": "textarea"})
