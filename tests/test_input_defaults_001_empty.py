from src.crawler.input_defaults import empty_input_defaults


def test_empty_input_defaults_has_expected_sections():
    assert empty_input_defaults() == {"field_patterns": {}, "type_fallbacks": {}}
