import json

from src.crawler.input_defaults import resolve_input_defaults


def test_resolve_input_defaults_merges_file_and_override(tmp_path):
    path = tmp_path / "defaults.json"
    path.write_text(json.dumps({"field_patterns": {"email": "old"}}), encoding="utf-8")
    assert resolve_input_defaults(str(path), {"email": "new"})["field_patterns"]["email"] == "new"
