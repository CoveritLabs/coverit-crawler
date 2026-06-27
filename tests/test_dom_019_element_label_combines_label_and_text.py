from src.utils.dom import element_label


def test_element_label_combines_label_and_distinct_text():
    assert element_label({"label": "Name", "text": "Continue"}) == "Name Continue"
