from src.utils.serialization import stable_json_dumps


def test_stable_json_dumps_keeps_unicode_characters():
    assert stable_json_dumps({"city": "Zürich"}) == '{"city":"Zürich"}'
