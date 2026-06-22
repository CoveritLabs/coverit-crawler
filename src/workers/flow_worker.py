from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

from src.db.repositories.crawl_sessions import fetch_job_inputs
from src.graph.test_flow_generation.graph import TestFlow
from src.graph.test_flow_generation.stage2_selecting_best_tf import MAX_TF_TAKEN
from src.graph.test_flow_generation.test_flow_gen import find_all_flows
from src.utils.coercion import coerce_float, coerce_int

logger = logging.getLogger(__name__)

DEFAULT_TEST_FLOW_GENERATION_CONFIG = {
    "coverage_percentage": 100.0,
    "num_of_tf": 1,
    "num_of_states": 20,
    "min_num_of_states_per_tf": 3,
}


def _internal_api_base_url() -> str:
    return os.getenv("COVERIT_API_INTERNAL_URL", "http://localhost:3000/api/v1").rstrip("/")


def _pick(source: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in source:
            return source.get(key)
    return None


def _test_flow_generation_config(config_json: dict[str, Any]) -> dict[str, float | int]:
    raw = _pick(config_json, "testFlowGeneration", "test_flow_generation")
    if not isinstance(raw, dict):
        raw = {}

    coverage_percentage = coerce_float(
        _pick(raw, "coverage_percentage", "coveragePercentage"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["coverage_percentage"],
    )
    num_of_tf = coerce_int(
        _pick(raw, "num_of_tf", "numOfTf"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["num_of_tf"],
    )
    num_of_states = coerce_int(
        _pick(raw, "num_of_states", "numOfStates"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["num_of_states"],
    )
    min_num_of_states_per_tf = coerce_int(
        _pick(raw, "min_num_of_states_per_tf", "minNumOfStatesPerTf"),
        DEFAULT_TEST_FLOW_GENERATION_CONFIG["min_num_of_states_per_tf"],
    )

    return {
        "coverage_percentage": min(100.0, max(0.0, coverage_percentage)),
        "num_of_tf": min(MAX_TF_TAKEN, max(1, num_of_tf)),
        "num_of_states": max(1, num_of_states),
        "min_num_of_states_per_tf": max(1, min_num_of_states_per_tf),
    }


async def _post_flows(session_id: str, flows: dict[str, list[dict[str, Any]]]) -> None:
    url = f"{_internal_api_base_url()}/internal/sessions/{session_id}/flows"
    async with aiohttp.ClientSession() as client:
        async with client.post(url, json={"flows": flows}) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"Failed to save flows for session {session_id}: {response.status} {text}")


async def _serialize_selected_flows(
    graph_repo,
    session_id: str,
    selected_flows: list[TestFlow],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}

    for flow in selected_flows:
        if not flow.node_path or not flow.transition_ids:
            continue

        checkpoint_hash = flow.node_path[0]
        target_hash = flow.node_path[-1]
        checkpoint_url, _, transitions = await graph_repo.get_data_from_flow_query(
            session_id,
            checkpoint_hash,
            flow.transition_ids,
        )

        path = [{"state_hash": checkpoint_hash, "transition": None}]
        for transition in transitions:
            target_state_hash = transition.pop("target_state_hash", None)
            transition.pop("source_state_hash", None)
            transition.pop("order", None)
            if target_state_hash:
                path.append({"state_hash": target_state_hash, "transition": transition})

        result.setdefault(target_hash, []).append(
            {
                "checkpoint": checkpoint_hash,
                "checkpoint_url": checkpoint_url or "",
                "is_clipped": len(transitions) != len(flow.transition_ids),
                "path": path,
            }
        )

    return result


async def generate_flows_for_session(ctx: dict, session_id: str) -> dict[str, Any]:
    db = ctx["db"]
    crawler_worker = ctx.get("crawler_worker")
    graph_builder = getattr(crawler_worker, "_graph_builder", None)
    if graph_builder is None:
        raise RuntimeError("crawler graph builder is not available")

    async with db() as s:
        config_json, _, graph_id = await fetch_job_inputs(s, session_id)

    generation_config = _test_flow_generation_config(config_json)

    selected_flows = await find_all_flows(
        graph_builder,
        session_id=graph_id,
        min_num_of_states_per_tf=int(generation_config["min_num_of_states_per_tf"]),
        max_num_of_states_per_tf=int(generation_config["num_of_states"]),
        convergence_threshold=float(generation_config["coverage_percentage"]) / 100,
        min_num_of_tf=int(generation_config["num_of_tf"]),
    )
    serialized = await _serialize_selected_flows(graph_builder, graph_id, selected_flows)
    await _post_flows(session_id, serialized)

    flow_count = sum(len(flows) for flows in serialized.values())
    logger.info(
        "Generated %d test flows for session %s from graph %s",
        flow_count,
        session_id,
        graph_id,
    )
    return {
        "status": "completed",
        "session_id": session_id,
        "graph_id": graph_id,
        "target_state_count": len(serialized),
        "flow_count": flow_count,
        "config": generation_config,
    }
