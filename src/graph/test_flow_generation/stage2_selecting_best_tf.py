from __future__ import annotations

import heapq
import logging

from graph import TestFlow

logger = logging.getLogger(__name__)

MAX_TF_TAKEN = 10000

def select_tfs(
    candidates: list[TestFlow],
    *,
    transition_count: int,
    convergence_threshold: float | None = None,
    min_num_of_tf: int | None = None,
    min_num_of_states_per_tf: int | None = None,
) -> list[TestFlow]:
    
    if transition_count <= 0:
        logger.warning("transition_count <= 0; nothing to cover")
        return []

    eligible: list[TestFlow] = []
    eligible_sets: list[set[str]] = []  

    for tf in candidates:
        length = len(tf)
        if (min_num_of_states_per_tf is None or length >= min_num_of_states_per_tf):
            eligible.append(tf)
            eligible_sets.append(set(tf.transition_ids))

    if not eligible:
        logger.warning("No eligible candidates after length filtering")
        return []

    selected: list[TestFlow] = []
    union_ids: set[str] = set()

    heap = [(-len(es), i) for i, es in enumerate(eligible_sets)]
    heapq.heapify(heap)

    while heap and len(selected) < MAX_TF_TAKEN:
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

        current_coverage = len(union_ids) / transition_count

        if min_num_of_tf is not None:
            if len(selected) >= min_num_of_tf:
                if convergence_threshold is None:
                    break
                elif current_coverage >= convergence_threshold:
                    logger.info(
                        "Target reached: within (%d) and coverage (%.2f%% >= %.2f%%)", 
                        len(selected), current_coverage * 100, convergence_threshold * 100
                    )
                    break
        else:
            if convergence_threshold is not None and current_coverage >= convergence_threshold:
                logger.info(
                    "Target reached: coverage %.2f%% >= %.2f%%", 
                    current_coverage * 100, convergence_threshold * 100
                )
                break

    logger.info(
        "Stage 2: selected %d/%d eligible TFs, coverage=%.2f%%",
        len(selected),
        len(eligible),
        (len(union_ids) / transition_count) * 100,
    )
    return selected