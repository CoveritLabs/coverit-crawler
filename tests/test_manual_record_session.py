from types import SimpleNamespace

import pytest

from src.workers.jobs.manual_record_session import (
    ANNOTATED_PAGE_CONTENT_SCRIPT,
    STATE_HASH_SCRIPT,
    _capture_manual_state,
)


class FakePage:
    def __init__(
        self,
        *,
        annotated_html: str = "",
        fallback_html: str = "",
        fail_annotation: bool = False,
    ) -> None:
        self.annotated_html = annotated_html
        self.fallback_html = fallback_html
        self.fail_annotation = fail_annotation
        self.url = "https://example.test/manual?"
        self.evaluated_scripts: list[str] = []
        self.content_calls = 0

    async def wait_for_load_state(self, *_args, **_kwargs) -> None:
        return None

    async def evaluate(self, script: str):
        self.evaluated_scripts.append(script)
        if script == STATE_HASH_SCRIPT:
            return {"state": "manual"}
        if script == ANNOTATED_PAGE_CONTENT_SCRIPT:
            if self.fail_annotation:
                raise RuntimeError("annotation failed")
            return self.annotated_html
        raise AssertionError("unexpected script")

    async def content(self) -> str:
        self.content_calls += 1
        return self.fallback_html

    async def title(self) -> str:
        return "Manual Page"


def _job():
    return SimpleNamespace(page_load_state="networkidle", timeout_ms=3000)


@pytest.mark.asyncio
async def test_capture_manual_state_uses_annotated_html_with_bounding_boxes():
    annotated_html = (
        '<html><body><button data-x="10" data-y="20" '
        'data-width="100" data-height="40">Save</button></body></html>'
    )
    page = FakePage(annotated_html=annotated_html)

    state = await _capture_manual_state(page, _job())

    assert state.html == annotated_html
    assert 'data-x="10"' in state.html
    assert 'data-y="20"' in state.html
    assert 'data-width="100"' in state.html
    assert 'data-height="40"' in state.html
    assert page.content_calls == 0
    assert page.evaluated_scripts == [STATE_HASH_SCRIPT, ANNOTATED_PAGE_CONTENT_SCRIPT]
    assert state.url == "https://example.test/manual"
    assert state.dom_snapshot == {"content_length": len(annotated_html)}


@pytest.mark.asyncio
async def test_capture_manual_state_falls_back_to_page_content_when_annotation_fails():
    fallback_html = "<html><body><button>Save</button></body></html>"
    page = FakePage(fallback_html=fallback_html, fail_annotation=True)

    state = await _capture_manual_state(page, _job())

    assert state.html == fallback_html
    assert page.content_calls == 1
    assert page.evaluated_scripts == [STATE_HASH_SCRIPT, ANNOTATED_PAGE_CONTENT_SCRIPT]
    assert state.dom_snapshot == {"content_length": len(fallback_html)}
