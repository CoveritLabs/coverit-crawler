import json

from src.crawler.input_defaults import load_input_defaults


def test_load_input_defaults_reads_json_file(tmp_path):
    path = tmp_path / "defaults.json"
    path.write_text(json.dumps({"email": "a@example.com"}), encoding="utf-8")
    assert load_input_defaults(str(path))["field_patterns"]["email"] == "a@example.com"
