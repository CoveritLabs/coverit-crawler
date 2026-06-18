from typing import Any

from src.models import CrawlAction


def map_steps_to_actions(
    raw_steps: list[dict[str, Any]],
    fallback_url: str = "",
) -> list[CrawlAction]:
    """
    Maps raw browser recording steps to CrawlActions"""
    if not raw_steps:
        return [CrawlAction(
            action_type="navigate",
            selector="",
            value=fallback_url,
            description=f"Navigate to {fallback_url}" if fallback_url else "System or URL redirect",
        )]

    deduped: list[dict[str, Any]] = []
    for step in raw_steps:
        if (
            step.get("action") == "input"
            and deduped
            and deduped[-1].get("action") == "input"
            and deduped[-1].get("element") == step.get("element")
        ):
            deduped[-1] = step
        else:
            deduped.append(step)

    actions = []
    for step in deduped:
        action = _map_step(step)
        if action:
            actions.append(action)

    if not actions:
        return [CrawlAction(
            action_type="navigate",
            selector="",
            value=fallback_url,
            description=f"Navigate to {fallback_url}" if fallback_url else "System or URL redirect",
        )]

    return actions


def _map_step(step: dict[str, Any]) -> CrawlAction | None:
    action_type = step.get("action", "")
    selector = step.get("element", "")

    if action_type == "click":
        return _map_click(step, selector)

    if action_type == "input":
        return _map_input(step, selector)

    if action_type == "keypress" and step.get("key"):
        return CrawlAction(
            action_type="press",
            selector=selector,
            value=step.get("key") or "",
            description=f"Press {step.get('key')} in {selector}",
        )

    return None


def _map_click(step: dict[str, Any], selector: str) -> CrawlAction:
    tag = step.get("tag", "")
    label = (step.get("label") or "").strip()
    href = (step.get("href") or "").strip()

    if label and tag:
        playwright_selector = f'{tag}:has-text("{label}")'
    else:
        playwright_selector = selector

    if tag == "a":
        element_hint = "link"
    elif tag in ("button", "input", "submit"):
        element_hint = "button"
    else:
        element_hint = tag or "element"

    label_part = f" {label}" if label else ""
    selector_part = f" [{playwright_selector}]"
    href_part = f" ({href})" if href else ""
    description = f"Click {element_hint}{label_part}{selector_part}{href_part}"

    return CrawlAction(
        action_type="click",
        selector=playwright_selector,
        value="",
        description=description,
    )


def _map_input(step: dict[str, Any], selector: str) -> CrawlAction:
    value = step.get("value", "")
    label = (step.get("label") or "").strip()
    input_type = (step.get("inputType") or "text").lower()

    label_hint = f" {label}" if label else f" {selector}"

    description = f"Type into {input_type}{label_hint}"

    return CrawlAction(
        action_type="type",
        selector=selector,
        value=value,
        description=description,
        metadata={"type": input_type, "manual": True},
    )