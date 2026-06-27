from src.utils.dom import text_input_label


def test_text_input_label_mentions_contenteditable():
    assert text_input_label({"contenteditable": True}) == "contenteditable"
