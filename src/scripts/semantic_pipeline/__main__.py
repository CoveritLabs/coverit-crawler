from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from src.scripts.semantic_pipeline.pipeline import (
    PipelineSettings,
    run_pipeline,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-websites", type=int, default=0)
    parser.add_argument("--max-pages-per-domain", type=int, default=3)
    parser.add_argument("--max-actions-per-page", type=int, default=5)
    parser.add_argument("--max-pairs", type=int, default=1000)
    parser.add_argument("--timeout-ms", type=int, default=15000)
    parser.add_argument("--visible", action="store_true")
    parser.add_argument("--model", default="all-mpnet-base-v2")
    parser.add_argument("--reuse-collected", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[3]
    logging.basicConfig(level=logging.INFO)
    asyncio.run(
        run_pipeline(
            PipelineSettings(
                workspace=root / "data" / "semantic_pipeline",
                artifacts=root / "src" / "models" / "semantic",
                input_config=root / "src" / "configs" / "input_defaults.json",
                max_websites=args.max_websites,
                max_pages_per_domain=args.max_pages_per_domain,
                max_actions_per_page=args.max_actions_per_page,
                max_pairs=args.max_pairs,
                timeout_ms=args.timeout_ms,
                headless=not args.visible,
                labeling_model=args.model,
                reuse_collected=args.reuse_collected,
            )
        )
    )


if __name__ == "__main__":
    main()
