from src.crawler.input_defaults import merge_input_defaults


def test_merge_input_defaults_override_wins():
    merged = merge_input_defaults({"field_patterns": {"email": "old"}}, {"field_patterns": {"email": "new"}})
    assert merged["field_patterns"]["email"] == "new"
