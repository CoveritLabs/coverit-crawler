from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from src.config import config
from src.graph.factory import create_graph
from src.replay_assertions.core import run_interactive_replay

logger = logging.getLogger(__name__)


async def fetch_flow_data(
    repo: Any,
    checkpoint_hash: str,
    transition_refs: list[str],
) -> tuple[str | None, Any, list[dict[str, Any]]]:
    """Fetches the starting checkpoint URL and all step details from Neo4j in one shot."""
    checkpoint_url, checkpoint_storage_state_json, raw_transitions = await repo.get_data_from_flow_query(
        checkpoint_hash,
        transition_refs,
    )
    ref_map = {t["transition_id"]: t for t in raw_transitions}
    ordered_transitions = [ref_map[ref] for ref in transition_refs if ref in ref_map]

    return checkpoint_url, checkpoint_storage_state_json, ordered_transitions


async def _run(args: argparse.Namespace) -> int:
    client, repo = await create_graph(config.NEO4J_URI, config.NEO4J_USER, config.NEO4J_PASSWORD)

    try:
        transition_refs = [ref.strip() for ref in args.transition_refs.split(",") if ref.strip()]

        logger.info("Fetching checkpoint URL and hydrating %d steps from Neo4j...", len(transition_refs))
        checkpoint_url, checkpoint_storage_state_json, hydrated_transitions = await fetch_flow_data(
            repo,
            args.checkpoint_hash,
            transition_refs,
        )

        if not checkpoint_url:
            logger.error("Could not find a checkpoint state or 'checkpoint_url' matching hash: %s", args.checkpoint_hash)
            return 1

        if not hydrated_transitions:
            logger.error("Could not find action data for the provided transition references.")
            return 1

        logger.info("Flow resolved successfully. Starting browser replay...")
        await run_interactive_replay(
            checkpoint_url=checkpoint_url,
            storage_state=checkpoint_storage_state_json,
            transitions=hydrated_transitions,
            output_file=args.output_file,
        )

        return 0
    finally:
        await client.close()


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Hydrate a flow fully from Neo4j using hashes and refs.")
    parser.add_argument("--checkpoint-hash", required=True, help="The starting state hash from your Postgres database")
    parser.add_argument("--transition-refs", required=True, help="Comma-separated list of transition IDs (e.g. 'id1,id2')")
    parser.add_argument("--output-file", default="artifacts/assertions.json", help="Where to save the assertions")

    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
