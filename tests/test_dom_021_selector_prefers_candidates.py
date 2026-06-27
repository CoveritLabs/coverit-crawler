from src.utils.dom import build_selector


def test_build_selector_prefers_selector_candidates():
    assert build_selector({"selector_candidates": [".primary", "#fallback"]}) == ".primary"
