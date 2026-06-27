from src.utils.dom import text_input_label


def test_text_input_label_prefers_type():
    assert text_input_label({"type": "email"}) == "email"
