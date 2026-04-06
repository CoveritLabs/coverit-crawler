"""Utility functions for the crawler."""

import hashlib
from typing import Dict, Any


def normalize_url(url: str) -> str:
    """Normalize URL for comparison."""
    url = url.rstrip("/").split("#")[0]
    return url


def extract_selector_id(element) -> str:
    """Extract a unique selector from an element."""
    if hasattr(element, "get_attribute"):
        elem_id = element.get_attribute("id")
        if elem_id:
            return f"#{elem_id}"

        classes = element.get_attribute("class")
        if classes:
            return f".{classes.split()[0]}"

    return element.tag_name


def merge_metadata(meta1: Dict[str, Any], meta2: Dict[str, Any]) -> Dict[str, Any]:
    """Merge two metadata dictionaries."""
    result = meta1.copy()
    result.update(meta2)
    return result


def format_error_message(error: Exception) -> str:
    """Format error for logging."""
    return f"{type(error).__name__}: {str(error)}"
