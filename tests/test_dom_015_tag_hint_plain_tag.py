from src.utils.dom import element_tag_hint


def test_element_tag_hint_returns_plain_tag():
    assert element_tag_hint({"tag": "button"}) == "button "
