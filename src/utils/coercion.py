from typing import Any


def coerce_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    if isinstance(value, str):
        stripped = value.strip()

        if not stripped:
            return default

        return int(stripped)

    return default


def coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        stripped = value.strip().lower()

        if stripped in {"true", "1", "yes", "y", "on"}:
            return True

        if stripped in {"false", "0", "no", "n", "off"}:
            return False

    return default


def coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default

    if isinstance(value, str):
        stripped = value.strip()
        return stripped or default

    return str(value)
