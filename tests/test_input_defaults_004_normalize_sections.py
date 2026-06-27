from src.crawler.input_defaults import normalize_input_defaults


def test_normalize_input_defaults_keeps_known_sections():
    value = normalize_input_defaults({"field_patterns": {"email": "a"}, "type_fallbacks": {"email": "b"}})
    assert value == {"field_patterns": {"email": "a"}, "type_fallbacks": {"email": "b"}}
