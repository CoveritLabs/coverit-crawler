from src.crawler.input_defaults import normalize_input_defaults


def test_normalize_input_defaults_discards_non_mapping_sections():
    assert normalize_input_defaults({"field_patterns": [], "type_fallbacks": "x"}) == {"field_patterns": {}, "type_fallbacks": {}}
