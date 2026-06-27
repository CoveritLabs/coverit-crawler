from src.utils.dom import element_identity_key


def test_element_identity_key_ignores_numeric_id():
    assert element_identity_key({"tag": "input", "id": "123"}) == element_identity_key({"tag": "input", "id": "456"})
