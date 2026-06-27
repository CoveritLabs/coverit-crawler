from src.utils.dom import element_display_hint


def test_element_display_hint_prefers_text():
    assert element_display_hint({"text": "  Save   now  "}) == "'Save now'"
