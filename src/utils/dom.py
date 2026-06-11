import re

from src.crawler import HtmlTag, InputType
from typing import Optional


def css_escape(value: str) -> str:
    if not value:
        return value

    value = value.replace("\\", "\\\\")
    value = value.replace('"', '\\"')
    value = value.replace("'", "\\'")

    return re.sub(r'([#.;:[\]()=+>*~|^$ ])', r'\\\1', value)


def element_tag(element: dict) -> str:
    return str(element.get("tag", "") or "").lower()


def element_type(element: dict) -> str:
    return str(element.get("type", "") or "").lower()


def is_text_input(element: dict) -> bool:
    tag = element_tag(element)

    return (
        tag in (HtmlTag.INPUT, HtmlTag.TEXTAREA)
        or element.get("contenteditable")
    )


def is_button(element: dict) -> bool:
    tag = element_tag(element)
    input_type = element_type(element)

    return (
        tag == HtmlTag.BUTTON
        or element.get("role") == "button"
        or (
            tag == HtmlTag.INPUT
            and input_type in (InputType.SUBMIT, InputType.BUTTON)
        )
    )

def supports_enter_submission(element: dict) -> bool:
    return (
        element_tag(element) == HtmlTag.INPUT
        and element_type(element)
        in (
            "text",
            "search",
            "email",
            "tel",
            "url",
            "number",
        )
    )


def element_tag_hint(element: dict) -> str:
    tag = element_tag(element)
    input_type = element_type(element)

    if (
        tag == HtmlTag.INPUT
        and input_type
        and input_type not in ("text", "search")
    ):
        return f"{tag}[{input_type}] "

    return f"{tag} " if tag else ""


def text_input_label(element: dict) -> str:
    input_type = element_type(element)

    if input_type:
        return input_type

    if element.get("contenteditable"):
        return "contenteditable"

    return "field"

def element_label(element: dict, selector: str | None = None) -> str:
    parts: list[str] = []

    label = (
        element.get("aria-label")
        or element.get("label")
        or element.get("name")
        or element.get("title")
    )

    text = element.get("innerText") or element.get("text")

    if label:
        label_str = str(label).strip()
        if label_str:
            parts.append(label_str)

    if text:
        text_str = str(text).strip()
        if text_str and text_str != label:
            parts.append(text_str)

    if selector:
        parts.append(f"[{selector}]")

    return " ".join(parts).strip()

def build_selector(element: dict) -> str | None:
    selector_candidates = element.get("selector_candidates") or []

    if selector_candidates:
        return selector_candidates[0]

    tag = element_tag(element)
    element_id = element.get("id")
    name = element.get("name")
    text = str(element.get("text") or "").strip()
    value = element.get("value")
    input_type = element_type(element)

    if element_id and not str(element_id).isdigit():
        return f"#{css_escape(str(element_id))}"

    if name:
        return f'[name="{css_escape(str(name))}"]'

    if (
        tag == HtmlTag.INPUT
        and input_type in (InputType.SUBMIT, InputType.BUTTON)
        and value
    ):
        return (
            f'input[type="{input_type}"]'
            f'[value="{css_escape(str(value))}"]'
        )

    if tag in (HtmlTag.BUTTON, HtmlTag.ANCHOR) and text:
        safe_text = css_escape(text[:80])
        return f'{tag}:has-text("{safe_text}")'

    return None

def attach_selectors_to_forms(forms: list[dict]) -> list[dict]:
    for form in forms:
        for field in form.get("fields", []):
            field["selector"] = build_selector(field)

        if form.get("submit"):
            form["submit"]["selector"] = build_selector(form["submit"])
    return forms

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