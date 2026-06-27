from src.utils.dom import supports_enter_submission


def test_supports_enter_submission_for_text_input():
    assert supports_enter_submission({"tag": "input", "type": "text"})
