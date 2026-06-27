from src.utils.dom import element_tag_hint


def test_element_tag_hint_includes_non_default_input_type():
    assert element_tag_hint({"tag": "input", "type": "email"}) == "input[email] "
