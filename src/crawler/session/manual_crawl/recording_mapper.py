from typing import Any

from src.models import CrawlAction


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


def _selector_candidates(step: dict[str, Any]) -> list[str]:
    candidates: list[str] = []

    raw_candidates = step.get("selectorCandidates") or step.get("selector_candidates") or []
    if isinstance(raw_candidates, str):
        raw_candidates = [raw_candidates]
    if isinstance(raw_candidates, list):
        for candidate in raw_candidates:
            _append_candidate(candidates, candidate)

    for key in (
        "interactiveSelector",
        "interactive_selector",
        "element",
        "selector",
        "targetSelector",
        "target_selector",
    ):
        _append_candidate(candidates, step.get(key))

    return candidates


def _append_candidate(candidates: list[str], value: Any) -> None:
    selector = str(value or "").strip()
    if selector and selector not in candidates:
        candidates.append(selector)


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
