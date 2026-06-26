from __future__ import annotations

import heapq
import logging

from src.graph.test_flow_generation.graph import TestFlow

logger = logging.getLogger(__name__)

MAX_TF_TAKEN = 10000


def select_tfs(
    candidates: list[TestFlow],
    *,
    transition_count: int,
    convergence_threshold: float | None = None,
    min_num_of_tf: int | None = None,
    max_num_of_tf: int | None = None,
    min_num_of_states_per_tf: int | None = None,
) -> list[TestFlow]:
    max_num_of_tf=min(max_num_of_tf, MAX_TF_TAKEN) if max_num_of_tf is not None else MAX_TF_TAKEN
    
    if transition_count <= 0:
        logger.warning("transition_count <= 0; nothing to cover")
        return []

    eligible: list[TestFlow] = []
    eligible_sets: list[set[str]] = []

    for tf in candidates:
        if min_num_of_states_per_tf is None or len(tf) >= min_num_of_states_per_tf:
            eligible.append(tf)
            eligible_sets.append(set(tf.transition_ids))

    if not eligible:
        logger.warning("No eligible candidates after length filtering")
        return []

    selected: list[TestFlow] = []
    union_ids: set[str] = set()

    heap = [(-len(es), i) for i, es in enumerate(eligible_sets)]
    heapq.heapify(heap)

    while heap:
        while heap:
            neg_gain, idx = heapq.heappop(heap)
            real_gain = len(eligible_sets[idx] - union_ids)

            if real_gain == -neg_gain:
                candidate_idx, best_gain = idx, real_gain
                break
            heapq.heappush(heap, (-real_gain, idx))
        else:
            break

        if best_gain == 0:
            if min_num_of_tf is None or len(selected) >= min_num_of_tf:
                break

        candidate = eligible[candidate_idx]
        selected.append(candidate)
        union_ids.update(candidate.transition_ids)

        current_count = len(selected)
        current_coverage = len(union_ids) / transition_count

        if max_num_of_tf is not None and current_count >= max_num_of_tf:
            logger.info("Target reached: hit max_num_of_tf limit (%d)", max_num_of_tf)
            break

        if min_num_of_tf is not None and current_count < min_num_of_tf:
            continue

        if convergence_threshold is not None:
            if current_coverage >= convergence_threshold:
                logger.info(
                    "Target reached: coverage %.2f%% >= %.2f%% (TFs: %d)", 
                    current_coverage * 100, convergence_threshold * 100, current_count
                )
                break
        else:
            if min_num_of_tf is not None:
                break

    logger.info(
        "Stage 2: selected %d/%d eligible TFs, coverage=%.2f%%",
        len(selected),
        len(eligible),
        (len(union_ids) / transition_count) * 100,
    )
    return selected
