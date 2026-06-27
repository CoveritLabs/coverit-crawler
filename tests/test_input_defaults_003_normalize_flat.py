from src.crawler.input_defaults import normalize_input_defaults


def test_normalize_input_defaults_treats_flat_mapping_as_field_patterns():
    assert normalize_input_defaults({"email": "a@example.com"})["field_patterns"] == {"email": "a@example.com"}
