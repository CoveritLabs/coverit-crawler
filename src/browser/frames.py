from __future__ import annotations

from typing import Optional

from playwright.async_api import Frame, Page


class FrameResolver:
    def __init__(self, page_provider):
        self._page_provider = page_provider

    def resolve(
        self,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> Frame | Page:
        return (
            self._resolve_frame(
                frame_url=frame_url,
                frame_name=frame_name,
            )
            or self._page
        )

    def _resolve_frame(
        self,
        *,
        frame_url: Optional[str] = None,
        frame_name: Optional[str] = None,
    ) -> Optional[Frame]:
        if frame_name:
            try:
                frame = self._page.frame(name=frame_name)

                if frame:
                    return frame

            except Exception:
                pass

        if frame_url:
            try:
                for frame in self._page.frames:
                    if frame.url == frame_url or frame.url.startswith(frame_url):
                        return frame

            except Exception:
                return None

        return None

    @property
    def _page(self) -> Page:
        return self._page_provider()
