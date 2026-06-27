from src.utils.dom import is_button


def test_is_button_accepts_button_role():
    assert is_button({"tag": "div", "role": "button"})
