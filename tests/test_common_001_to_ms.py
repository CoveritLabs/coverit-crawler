from src.utils.common import to_ms


def test_to_ms_converts_seconds_to_milliseconds():
    assert to_ms(1.25) == 1250
