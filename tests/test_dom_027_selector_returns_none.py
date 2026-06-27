from src.utils.dom import build_selector


def test_build_selector_returns_none_without_stable_attributes():
    assert build_selector({"tag": "div"}) is None
