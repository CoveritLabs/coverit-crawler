from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

__all__ = [
	"attach_selectors_to_forms",
	"build_selector",
	"coerce_bool",
	"coerce_int",
	"coerce_str",
	"element_display_hint",
	"element_label",
	"element_tag",
	"element_tag_hint",
	"element_type",
	"is_button",
	"is_http_url",
	"is_non_http_href",
	"is_same_domain",
	"is_supported_form_element",
	"is_text_input",
	"normalize_checkpoint_url",
	"normalize_url",
	"read_file",
	"stable_json_dumps",
	"supports_enter_submission",
	"text_input_label",
	"to_ms",
]

_EXPORTS: dict[str, tuple[str, str]] = {
	"attach_selectors_to_forms": ("src.utils.dom", "attach_selectors_to_forms"),
	"build_selector": ("src.utils.dom", "build_selector"),
	"coerce_bool": ("src.utils.coercion", "coerce_bool"),
	"coerce_int": ("src.utils.coercion", "coerce_int"),
	"coerce_str": ("src.utils.coercion", "coerce_str"),
	"element_display_hint": ("src.utils.dom", "element_display_hint"),
	"element_label": ("src.utils.dom", "element_label"),
	"element_tag": ("src.utils.dom", "element_tag"),
	"element_tag_hint": ("src.utils.dom", "element_tag_hint"),
	"element_type": ("src.utils.dom", "element_type"),
	"is_button": ("src.utils.dom", "is_button"),
	"is_http_url": ("src.utils.url", "is_http_url"),
	"is_non_http_href": ("src.utils.url", "is_non_http_href"),
	"is_same_domain": ("src.utils.url", "is_same_domain"),
	"is_supported_form_element": ("src.utils.dom", "is_supported_form_element"),
	"is_text_input": ("src.utils.dom", "is_text_input"),
	"normalize_checkpoint_url": ("src.utils.url", "normalize_checkpoint_url"),
	"normalize_url": ("src.utils.url", "normalize_url"),
	"read_file": ("src.utils.common", "read_file"),
	"stable_json_dumps": ("src.utils.serialization", "stable_json_dumps"),
	"supports_enter_submission": ("src.utils.dom", "supports_enter_submission"),
	"text_input_label": ("src.utils.dom", "text_input_label"),
	"to_ms": ("src.utils.common", "to_ms"),
}


def __getattr__(name: str) -> Any:
	target = _EXPORTS.get(name)
	if target is None:
		raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
	module_name, attr = target
	value = getattr(import_module(module_name), attr)
	globals()[name] = value
	return value


def __dir__() -> list[str]:
	return sorted(set(globals().keys()) | set(_EXPORTS.keys()))


if TYPE_CHECKING:
	from src.utils.coercion import coerce_bool, coerce_int, coerce_str
	from src.utils.common import read_file, to_ms
	from src.utils.dom import (
		attach_selectors_to_forms,
		build_selector,
		element_display_hint,
		element_label,
		element_tag,
		element_tag_hint,
		element_type,
		is_button,
		is_supported_form_element,
		is_text_input,
		supports_enter_submission,
		text_input_label,
	)
	from src.utils.serialization import stable_json_dumps
	from src.utils.url import (
		is_http_url,
		is_non_http_href,
		is_same_domain,
		normalize_checkpoint_url,
		normalize_url,
	)
