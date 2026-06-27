from src.utils.dom import supports_enter_submission


def test_supports_enter_submission_rejects_textarea():
    assert not supports_enter_submission({"tag": "textarea", "type": "text"})
