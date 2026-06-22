from src.crawler.input_defaults import merge_input_defaults, normalize_input_defaults


def test_user_input_defaults_override_matching_file_keys_and_keep_missing_file_keys():
    merged = merge_input_defaults(
        {
            "field_patterns": {
                "email": "file@example.com",
                "username": "file-user",
            },
            "type_fallbacks": {
                "email": "file@example.com",
                "text": "file text",
            },
        },
        {
            "field_patterns": {
                "email": "user@example.com",
            },
            "type_fallbacks": {
                "text": "user text",
            },
        },
    )

    assert merged == {
        "field_patterns": {
            "email": "user@example.com",
            "username": "file-user",
        },
        "type_fallbacks": {
            "email": "file@example.com",
            "text": "user text",
        },
    }


def test_flat_user_defaults_are_treated_as_field_patterns():
    assert normalize_input_defaults({"email": "user@example.com"}) == {
        "field_patterns": {"email": "user@example.com"},
        "type_fallbacks": {},
    }
