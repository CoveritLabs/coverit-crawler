from src.utils.dom import attach_selectors_to_forms


def test_attach_selectors_to_forms_adds_submit_selector():
    forms = [{"fields": [], "submit": {"tag": "button", "text": "Send"}}]
    assert attach_selectors_to_forms(forms)[0]["submit"]["selector"] == 'button:has-text("Send")'
