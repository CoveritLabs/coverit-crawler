from src.crawler.input_defaults import merge_input_defaults


def test_merge_input_defaults_preserves_type_fallbacks():
    merged = merge_input_defaults({"type_fallbacks": {"email": "a"}}, {"field_patterns": {"name": "b"}})
    assert merged["type_fallbacks"] == {"email": "a"}
