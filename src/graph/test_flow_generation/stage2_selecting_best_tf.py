from __future__ import annotations

import heapq
import logging

from graph import TestFlow

logger = logging.getLogger(__name__)

MAX_TF_TAKEN = 100000000000000

def select_tfs(
    candidates: list[TestFlow],
    *,
    transition_count: int,
    convergence_threshold: float | None = None,
    min_num_of_tf: int | None = None,
    min_num_of_states_per_tf: int | None = None,
    max_num_of_states_per_tf: int | None = None,
) -> list[TestFlow]:
    
    if transition_count <= 0:
        logger.warning("transition_count <= 0; nothing to cover")
        return []

    eligible: list[TestFlow] = []
    eligible_sets: list[set[str]] = []  

    for tf in candidates:
        length = len(tf)
        if (min_num_of_states_per_tf is None or length >= min_num_of_states_per_tf) and \
           (max_num_of_states_per_tf is None or length <= max_num_of_states_per_tf):
            eligible.append(tf)
            eligible_sets.append(set(tf.transition_ids))

    if not eligible:
        logger.warning("No eligible candidates after length filtering")
        return []

    target_count = min(MAX_TF_TAKEN, min_num_of_tf or MAX_TF_TAKEN)
    
    selected: list[TestFlow] = []
    union_ids: set[str] = set()

    heap = [(-len(es), i) for i, es in enumerate(eligible_sets)]
    heapq.heapify(heap)

    while heap and len(selected) < target_count:
        while heap:
            neg_gain, idx = heapq.heappop(heap)
            real_gain = len(eligible_sets[idx] - union_ids)

            if real_gain == -neg_gain:
                candidate_idx, best_gain = idx, real_gain
                break
            heapq.heappush(heap, (-real_gain, idx))
        else:
            break

        gain_fraction = best_gain / transition_count

        if min_num_of_tf is None and convergence_threshold is not None:
            if gain_fraction < convergence_threshold:
                logger.info("Convergence reached: gain %.4f < threshold %.4f", gain_fraction, convergence_threshold)
                break

        if best_gain == 0 and min_num_of_tf is None:
            break  
        candidate = eligible[candidate_idx]
        selected.append(candidate)
        union_ids.update(candidate.transition_ids)

    logger.info(
        "Stage 2: selected %d/%d eligible TFs, coverage=%.2f%%",
        len(selected),
        len(eligible),
        (len(union_ids) / transition_count) * 100,
    )
    return selected