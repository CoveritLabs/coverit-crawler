from src.utils.serialization import stable_json_dumps


def test_stable_json_dumps_stringifies_unknown_objects():
    assert stable_json_dumps({"value": object()}).startswith('{"value":"<object object')
