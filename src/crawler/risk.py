from dataclasses import dataclass
from typing import Optional

from src.config import Config, config
from src.models import CrawlAction


@dataclass(frozen=True)
class RiskClassifier:
    keywords: tuple[str, ...]

    @staticmethod
    def from_settings(settings: Config) -> "RiskClassifier":
        raw = str(getattr(settings, "DESTRUCTIVE_KEYWORDS", "") or "")
        parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
        return RiskClassifier(keywords=tuple(parts))

    @staticmethod
    def from_config() -> "RiskClassifier":
        return RiskClassifier.from_settings(config)

    def is_risky(self, action: CrawlAction, *, element: Optional[dict] = None) -> bool:
        text_bits: list[str] = [
            str(action.action_type or ""),
            str(action.description or ""),
            str(action.selector or ""),
            str(action.value or ""),
        ]
        if action.metadata:
            for k, v in action.metadata.items():
                text_bits.append(str(k))
                text_bits.append(str(v))
        if element:
            for k in ("text", "href", "tag", "type", "name", "aria_label"):
                if k in element:
                    text_bits.append(str(element.get(k) or ""))

        haystack = " ".join(text_bits).lower()
        return any(kw and kw in haystack for kw in self.keywords)
