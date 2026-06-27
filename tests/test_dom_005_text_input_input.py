from src.utils.dom import is_text_input


def test_is_text_input_accepts_input_tag():
    assert is_text_input({"tag": "input"})
