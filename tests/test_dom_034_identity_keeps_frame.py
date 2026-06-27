from src.utils.dom import element_identity_key


def test_element_identity_key_includes_frame_details():
    left = element_identity_key({"tag": "button", "frame": {"name": "main"}})
    right = element_identity_key({"tag": "button", "frame": {"name": "modal"}})
    assert left != right
