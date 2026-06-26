from typing import Any

from src import config
from src.crawler.input_defaults import resolve_input_defaults
from src.crawler.semantic_engine.engine import SemanticEngine


class InputValueResolver:
    def __init__(
        self,
        config_path: str | None = None,
        input_defaults: dict[str, Any] | None = None,
        confidence_threshold: float = 0.4,
        semantic_engine: SemanticEngine | None = None,
    ):
        self._config = resolve_input_defaults(config_path, input_defaults)
        self._confidence_threshold = confidence_threshold

        field_patterns = self._config.get("field_patterns", {})
        if semantic_engine is not None:
            semantic_engine.configure_input_defaults(field_patterns)
            self._semantic_engine = semantic_engine
        else:
            self._semantic_engine = SemanticEngine(
                input_defaults=field_patterns,
                artifact_dir=config.SEMANTIC_ARTIFACT_DIR,
                enabled=False,
            )

    def resolve(self, element: dict) -> str:
        resolved = self._semantic_engine.resolve_input_value(element)

        best_value = None
        if (
            resolved
            and not resolved.abstained
            and resolved.value is not None
            and resolved.confidence >= self._confidence_threshold
        ):
            best_value = str(resolved.value)

        if best_value is not None:
            return self._apply_constraints(best_value, element)

        fallbacks = self._config.get("type_fallbacks", {})
        fallback = str(fallbacks.get(element.get("type", "text"), "test"))

        tag = str(element.get("tag", "") or element.get("type", "")).lower()
        if tag == "select":
            options = element.get("options", [])
            if options:
                for opt in options:
                    val = str(opt if isinstance(opt, str) else opt.get("value", ""))
                    if val and val.strip() and val.lower() not in ("none", "null", ""):
                        return val

                first = options[0]
                return str(first if isinstance(first, str) else first.get("value", ""))

        return self._apply_constraints(fallback, element)

    def _apply_constraints(self, value: str, element: dict) -> str:
        t = str(element.get("type", "") or "").lower()
        maxlength = element.get("maxlength")

        if maxlength is not None:
            try:
                ml = int(maxlength)
                if ml >= 0:
                    value = value[:ml]
            except Exception:
                pass

        if t in ("number", "range"):
            chosen = None
            min_v = element.get("min")
            max_v = element.get("max")
            try:
                if min_v is not None:
                    chosen = str(int(float(min_v)))
            except Exception:
                chosen = None

            if chosen is None:
                try:
                    if max_v is not None:
                        chosen = str(int(float(max_v)))
                except Exception:
                    chosen = None

            if chosen is not None:
                value = chosen

        return value
