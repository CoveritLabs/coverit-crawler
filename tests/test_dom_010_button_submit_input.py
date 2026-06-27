from src.utils.dom import is_button


def test_is_button_accepts_submit_input():
    assert is_button({"tag": "input", "type": "submit"})
