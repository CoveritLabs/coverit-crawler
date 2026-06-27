from src.utils.dom import text_input_label


def test_text_input_label_defaults_to_field():
    assert text_input_label({}) == "field"
