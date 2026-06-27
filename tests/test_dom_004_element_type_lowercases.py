from src.utils.dom import element_type


def test_element_type_lowercases_type():
    assert element_type({"type": "EMAIL"}) == "email"
