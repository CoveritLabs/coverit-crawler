from src.utils.dom import is_button


def test_is_button_accepts_button_tag():
    assert is_button({"tag": "button"})
