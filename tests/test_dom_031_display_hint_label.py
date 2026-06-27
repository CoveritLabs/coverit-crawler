from src.utils.dom import element_display_hint


def test_element_display_hint_uses_label():
    assert element_display_hint({"label": "Email"}) == "'Email'"
