from typing import Any, Optional
"""Utility functions."""

def read_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        js_code = f.read()
    return js_code


def to_ms(seconds: Optional[Any]) -> Optional[int]:
    if seconds is None:
        return None
    try:
        return int(float(seconds) * 1000)
    except Exception:
        return None

def coerce_int(value: Any, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return default
        return int(s)
    return default


def coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        s = value.strip().lower()
        if s in {"true", "1", "yes", "y", "on"}:
            return True
        if s in {"false", "0", "no", "n", "off"}:
            return False
    return default


def coerce_str(value: Any, default: str) -> str:
    if value is None:
        return default
    if isinstance(value, str):
        s = value.strip()
        return s if s else default
    return str(value)