from src.utils.dom import element_identity_key


def test_element_identity_key_prefers_first_selector_candidate():
    key = element_identity_key({"selector_candidates": ["#first", "#second"]})
    assert "#first" in key
