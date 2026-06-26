import re
from typing import Any

from src.models import CrawlAction


_SELECTOR_KEYS = (
    "interactiveSelector",
    "interactive_selector",
    "element",
    "selector",
    "targetSelector",
    "target_selector",
)
_DYNAMIC_ID_PATTERNS = (
    re.compile(r"^_r_[a-z0-9_]+(?:--[a-z0-9_-]+)?$", re.IGNORECASE),
    re.compile(r"^[0-9]+$"),
    re.compile(r"^[a-f0-9]{8,}(?:-[a-f0-9]{4,})*$", re.IGNORECASE),
)
_CSS_ID_RE = re.compile(r"#([^\s\.#:\[>]+)")
_CSS_CLASS_RE = re.compile(r"\.([^\s\.#:\[>]+)")
_DYNAMIC_CLASS_PREFIXES = ("css-", "sc-", "prc-")
_GENERATED_CLASS_SUFFIX_RE = re.compile(
    r"(?:^|[-_])([A-Z]*[a-z]+[A-Z]+[A-Za-z0-9]*\d*|\w*\d+\w*)-?$"
)
_STABLE_SELECTOR_ATTRS = (
    "data-testid",
    "data-test",
    "data-cy",
    "data-qa",
    "name",
    "aria-label",
    "placeholder",
    "href",
)


def map_steps_to_actions(
    raw_steps: list[dict[str, Any]],
    fallback_url: str = "",
) -> list[CrawlAction]:
    """
    Maps raw browser recording steps to CrawlActions"""
    if not raw_steps:
        return []

    deduped: list[dict[str, Any]] = []
    for step in raw_steps:
        action = str(step.get("action") or "")
        selector = _selector(step)
        if (
            action in {"input", "change"}
            and deduped
            and deduped[-1].get("action") in {"input", "change"}
            and _selector(deduped[-1]) == selector
        ):
            deduped[-1] = step
        else:
            deduped.append(step)

    actions = []
    for step in deduped:
        action = _map_step(step)
        if action:
            actions.append(action)

    return [action for action in actions if _is_labelable(action)]


def _map_step(step: dict[str, Any]) -> CrawlAction | None:
    action_type = step.get("action", "")
    selector = _selector(step)

    if action_type == "click":
        return _map_click(step, selector)

    if action_type == "hover":
        return _map_hover(step, selector)

    if action_type in {"input", "change"}:
        return _map_input(step, selector)

    if action_type == "keypress" and step.get("key"):
        if not selector:
            return None
        return CrawlAction(
            action_type="press",
            selector=selector,
            value=step.get("key") or "",
            description=f"Press {step.get('key')} in {selector}",
            metadata={
                "manual": True,
                "selector_candidates": _selector_candidates(step),
            },
        )

    if action_type == "navigate_back":
        return None

    return None


def _selector(step: dict[str, Any]) -> str:
    candidates = _selector_candidates(step)
    return candidates[0] if candidates else ""


def selector_candidates_for_step(step: dict[str, Any]) -> list[str]:
    return _selector_candidates(step)


def _selector_candidates(step: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    raw_candidates = step.get("selectorCandidates") or step.get("selector_candidates") or []
    if isinstance(raw_candidates, str):
        raw_candidates = [raw_candidates]
    if isinstance(raw_candidates, list):
        for candidate in raw_candidates:
            _append_selector_candidate(candidates, candidate)

    for key in _SELECTOR_KEYS:
        _append_selector_candidate(candidates, step.get(key))

    return candidates


def _append_selector_candidate(candidates: list[str], value: Any) -> None:
    selector = str(value or "").strip()
    if not selector:
        return

    for candidate in _selector_expansions(selector):
        _append_candidate(candidates, candidate)


def _append_candidate(candidates: list[str], selector: str) -> None:
    if selector and selector not in candidates:
        candidates.append(selector)


def _selector_expansions(selector: str) -> list[str]:
    if not selector:
        return []

    expansions: list[str] = []
    if _selector_is_stable(selector):
        _append_candidate(expansions, selector)

    parts = [part.strip() for part in selector.split(">") if part.strip()]
    if len(parts) > 1:
        for tail_len in range(1, min(3, len(parts)) + 1):
            tail = " > ".join(parts[-tail_len:])
            if _selector_is_stable(tail):
                _append_candidate(expansions, tail)

    if not expansions and not _selector_has_unstable_tokens(selector):
        _append_candidate(expansions, selector)

    return expansions


def _selector_is_stable(selector: str) -> bool:
    selector = selector.strip()
    if not selector:
        return False
    if _selector_has_unstable_tokens(selector):
        return False
    if ">" in selector and selector.count(">") > 2:
        return False
    if ":nth-of-type" in selector and not _selector_has_stable_attr(selector):
        return False
    return True


def _selector_has_stable_attr(selector: str) -> bool:
    return any(f"[{attribute}" in selector for attribute in _STABLE_SELECTOR_ATTRS)


def _selector_has_unstable_tokens(selector: str) -> bool:
    for raw_id in _CSS_ID_RE.findall(selector):
        if _is_dynamic_id(raw_id):
            return True

    for class_name in _CSS_CLASS_RE.findall(selector):
        if _is_dynamic_class(class_name):
            return True

    return False


def _normalize_css_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", value.replace("\\", ""))


def _is_dynamic_id(raw_id: str) -> bool:
    token = _normalize_css_token(raw_id)
    if not token:
        return True
    if any(pattern.fullmatch(token) for pattern in _DYNAMIC_ID_PATTERNS):
        return True
    if len(token) >= 6 and "-" not in token and "_" not in token:
        has_upper = any(char.isupper() for char in token)
        has_lower = any(char.islower() for char in token)
        has_digit = any(char.isdigit() for char in token)
        if has_digit and (has_upper or has_lower):
            return True
    return False


def _is_dynamic_class(raw_class: str) -> bool:
    class_name = _normalize_css_token(raw_class)
    if not class_name:
        return True
    if class_name.startswith(_DYNAMIC_CLASS_PREFIXES):
        return True

    tail = class_name.rsplit("__", 1)[-1].rsplit("-", 1)[-1]
    if len(tail) >= 5:
        has_upper = any(char.isupper() for char in tail)
        has_lower = any(char.islower() for char in tail)
        has_digit = any(char.isdigit() for char in tail)
        if has_upper and (has_lower or has_digit):
            return True

    return bool(
        _GENERATED_CLASS_SUFFIX_RE.search(class_name)
        and any(char.isupper() for char in class_name)
    )


def _is_labelable(action: CrawlAction) -> bool:
    return bool(str(action.selector or "").strip())


def _map_click(step: dict[str, Any], selector: str) -> CrawlAction | None:
    tag = str(step.get("tag") or "").lower()
    label = (
        step.get("label")
        or step.get("accessibleName")
        or step.get("targetAccessibleName")
        or step.get("text")
        or step.get("targetText")
        or ""
    ).strip()
    href = (step.get("href") or "").strip()

    if not selector:
        return None

    if tag == "a" or href:
        element_hint = "link"
    elif tag in ("button", "input", "submit"):
        element_hint = "button"
    else:
        element_hint = tag or "element"

    label_part = f" {label}" if label else ""
    selector_part = f" [{selector}]"
    href_part = f" ({href})" if href else ""
    description = f"Click {element_hint}{label_part}{selector_part}{href_part}"

    return CrawlAction(
        action_type="click",
        selector=selector,
        value="",
        description=description,
        metadata={
            "manual": True,
            "selector_candidates": _selector_candidates(step),
            "target_selector": step.get("targetSelector") or step.get("target_selector") or "",
            "target_tag": step.get("targetTag") or step.get("target_tag") or "",
        },
    )


def _map_hover(step: dict[str, Any], selector: str) -> CrawlAction | None:
    if not selector:
        return None

    label = (
        step.get("label")
        or step.get("accessibleName")
        or step.get("text")
        or ""
    ).strip()
    tag = str(step.get("tag") or "").lower()
    target = label or tag or "element"

    return CrawlAction(
        action_type="hover",
        selector=selector,
        value="",
        description=f"Hover {target} [{selector}]",
        metadata={
            "manual": True,
            "selector_candidates": _selector_candidates(step),
        },
    )


def _map_input(step: dict[str, Any], selector: str) -> CrawlAction | None:
    if not selector:
        return None

    value = "" if step.get("value") is None else str(step.get("value", ""))
    label = (
        step.get("label")
        or step.get("accessibleName")
        or step.get("text")
        or ""
    ).strip()
    input_type = (step.get("inputType") or "text").lower()
    tag = str(step.get("tag") or "").lower()

    label_hint = f" {label}" if label else f" {selector}"

    if tag == "select":
        return CrawlAction(
            action_type="select",
            selector=selector,
            value=value,
            description=f"Select {value or input_type}{label_hint}",
            metadata={
                "type": input_type,
                "manual": True,
                "selector_candidates": _selector_candidates(step),
            },
        )

    description = f"Type into {input_type}{label_hint}"

    return CrawlAction(
        action_type="type",
        selector=selector,
        value=value,
        description=description,
        metadata={
            "type": input_type,
            "manual": True,
            "selector_candidates": _selector_candidates(step),
        },
    )
