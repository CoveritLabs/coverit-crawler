from src.utils.dom import element_tag


def test_element_tag_lowercases_tag():
    assert element_tag({"tag": "INPUT"}) == "input"
