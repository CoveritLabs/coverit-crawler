from src.utils.dom import element_label


def test_element_label_adds_selector_hint():
    assert element_label({"name": "email"}, "#email") == "email [#email]"
