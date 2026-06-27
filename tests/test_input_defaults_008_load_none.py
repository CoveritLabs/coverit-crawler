from src.crawler.input_defaults import load_input_defaults


def test_load_input_defaults_without_path_returns_empty():
    assert load_input_defaults(None) == {"field_patterns": {}, "type_fallbacks": {}}
