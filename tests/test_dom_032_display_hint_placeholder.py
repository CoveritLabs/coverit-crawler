from src.utils.dom import element_display_hint


def test_element_display_hint_uses_placeholder_in_brackets():
    assert element_display_hint({"placeholder": "Email"}) == "[Email]"
