from src.utils.serialization import stable_json_dumps


def test_stable_json_dumps_sorts_keys():
    assert stable_json_dumps({"b": 2, "a": 1}) == '{"a":1,"b":2}'
