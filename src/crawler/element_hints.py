from __future__ import annotations

from typing import Optional


def element_display_hint(
    element: dict,
    *,
    label_keys: tuple[str, ...] = ("label", "aria_label"),
    max_len: int = 80,
) -> str:
    def pick(*values: Optional[str]) -> str:
        for v in values:
            s = str(v or "").strip()
            if s:
                return s
        return ""

    text = pick(element.get("text"))
    if text:
        text = " ".join(text.split())
        return f"'{text[:max_len]}'"

    for key in label_keys:
        v = pick(element.get(key))
        if v:
            v = " ".join(v.split())
            return f"'{v[:max_len]}'"

    placeholder = pick(element.get("placeholder"))
    name = pick(element.get("name"))
    el_id = pick(element.get("id"))
    hint = placeholder or name or el_id
    return f"[{hint[:max_len]}]" if hint else ""
