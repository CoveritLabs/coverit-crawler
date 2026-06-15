import json
from typing import Any


def parse_storage_state(storage_state: Any) -> dict | None:
    if storage_state is None:
        return None

    if isinstance(storage_state, dict):
        return storage_state

    if isinstance(storage_state, (bytes, bytearray)):
        storage_state = storage_state.decode("utf-8")

    if isinstance(storage_state, str):
        raw = storage_state.strip()

        if not raw:
            return None

        try:
            parsed = json.loads(raw)

        except json.JSONDecodeError as e:
            raise ValueError("Invalid storage_state JSON") from e

        if parsed is None:
            return None

        if not isinstance(parsed, dict):
            raise ValueError("storage_state JSON must decode to an object")

        return parsed

    raise TypeError("storage_state must be a dict, JSON string, or bytes")


def normalize_storage_state(
    storage_state: Any,
) -> dict | None:
    parsed = parse_storage_state(storage_state)

    if parsed is None:
        return None

    cookies = parsed.get("cookies")
    origins = parsed.get("origins")

    if cookies is not None and not isinstance(cookies, list):
        raise ValueError("storage_state.cookies must be a list")

    if origins is not None and not isinstance(origins, list):
        raise ValueError("storage_state.origins must be a list")

    return parsed
