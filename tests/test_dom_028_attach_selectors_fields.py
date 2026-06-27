from src.utils.dom import attach_selectors_to_forms


def test_attach_selectors_to_forms_adds_field_selector():
    forms = [{"fields": [{"tag": "input", "name": "email"}]}]
    assert attach_selectors_to_forms(forms)[0]["fields"][0]["selector"] == '[name="email"]'
