from src.crawler.input_defaults import normalize_input_defaults


def test_normalize_input_defaults_none_returns_empty():
    assert normalize_input_defaults(None) == {"field_patterns": {}, "type_fallbacks": {}}
