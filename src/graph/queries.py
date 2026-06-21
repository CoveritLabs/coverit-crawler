ADD_STATE = """
MERGE (s:State {graph_id: $session_id, state_hash: $state_hash})
ON CREATE SET
    s.url = $url,
    s.title = $title,
    s.html = $html,
    s.session_id = $crawl_session_id,
    s.session_ids = CASE WHEN $crawl_session_id = '' THEN [] ELSE [$crawl_session_id] END,
    s.first_seen = timestamp(),
    s.last_seen = timestamp(),
    s._was_created = true
ON MATCH SET
    s.url = $url,
    s.title = $title,
    s.html = $html,
    s.session_id = CASE WHEN $crawl_session_id = '' THEN s.session_id ELSE $crawl_session_id END,
    s.last_seen = timestamp(),
    s._was_created = false
WITH s, s._was_created AS created
SET s.session_ids = CASE
    WHEN $crawl_session_id = '' THEN coalesce(s.session_ids, [])
    WHEN $crawl_session_id IN coalesce(s.session_ids, []) THEN coalesce(s.session_ids, [])
    ELSE coalesce(s.session_ids, []) + [$crawl_session_id]
END
REMOVE s._was_created
WITH s, created
FOREACH (_ IN CASE WHEN $enqueue AND $crawl_session_id <> '' THEN [1] ELSE [] END |
    MERGE (f:StateFrontier {
        graph_id: $session_id,
        crawl_session_id: $crawl_session_id,
        state_hash: $state_hash
    })
    ON CREATE SET
        f.created_at = timestamp(),
        f.status = 'pending',
        f.order = timestamp(),
        f.semantic_priority_penalty = coalesce($semantic_priority_penalty, 0.0)
    ON MATCH SET f.status = CASE
        WHEN coalesce(f.status, 'seen') = 'explored' THEN f.status
        ELSE 'pending'
    END
    SET f.order = coalesce(f.order, timestamp()),
        f.semantic_priority_penalty = coalesce(
            $semantic_priority_penalty,
            f.semantic_priority_penalty,
            0.0
        ),
        f.semantic_duplicate_of = CASE
            WHEN $semantic_duplicate_of = '' THEN f.semantic_duplicate_of
            ELSE $semantic_duplicate_of
        END,
        f.semantic_confidence = coalesce($semantic_confidence, f.semantic_confidence),
        f.semantic_reason = CASE
            WHEN $semantic_reason = '' THEN f.semantic_reason
            ELSE $semantic_reason
        END,
        f.semantic_scores_json = CASE
            WHEN $semantic_scores_json = '' THEN f.semantic_scores_json
            ELSE $semantic_scores_json
        END,
        f.updated_at = timestamp()
)
RETURN created
"""

CLAIM_NEXT_PENDING_STATE = """
MATCH (f:StateFrontier {graph_id: $session_id, crawl_session_id: $crawl_session_id, status: 'pending'})
MATCH (s:State {graph_id: $session_id, state_hash: f.state_hash})
WITH f, s, properties(s) AS props
ORDER BY coalesce(f.semantic_priority_penalty, 0.0) ASC,
         coalesce(f.order, props.first_seen, timestamp()) ASC
LIMIT 1
SET f.status = 'exploring',
    f.claimed_at = timestamp(),
    f.updated_at = timestamp()
RETURN props.state_hash AS state_hash,
       props.url AS url,
       props.title AS title
"""

MARK_STATE_PENDING = """
MATCH (s:State {graph_id: $session_id, state_hash: $state_hash})
MERGE (f:StateFrontier {
    graph_id: $session_id,
    crawl_session_id: $crawl_session_id,
    state_hash: $state_hash
})
ON CREATE SET
    f.created_at = timestamp(),
    f.semantic_priority_penalty = coalesce($semantic_priority_penalty, 0.0)
WITH f
WHERE coalesce(f.status, 'seen') <> 'explored'
SET f.status = 'pending',
    f.order = coalesce(f.order, timestamp()),
    f.semantic_priority_penalty = coalesce(
        $semantic_priority_penalty,
        f.semantic_priority_penalty,
        0.0
    ),
    f.semantic_duplicate_of = CASE
        WHEN $semantic_duplicate_of = '' THEN f.semantic_duplicate_of
        ELSE $semantic_duplicate_of
    END,
    f.semantic_confidence = coalesce($semantic_confidence, f.semantic_confidence),
    f.semantic_reason = CASE
        WHEN $semantic_reason = '' THEN f.semantic_reason
        ELSE $semantic_reason
    END,
    f.semantic_scores_json = CASE
        WHEN $semantic_scores_json = '' THEN f.semantic_scores_json
        ELSE $semantic_scores_json
    END,
    f.updated_at = timestamp()
RETURN count(f) AS count
"""

MARK_STATE_EXPLORED = """
MERGE (f:StateFrontier {
    graph_id: $session_id,
    crawl_session_id: $crawl_session_id,
    state_hash: $state_hash
})
SET f.status = 'explored',
    f.explored_at = timestamp(),
    f.updated_at = timestamp()
"""

SET_STATE_FRONTIER_PRIORITY = """
MATCH (s:State {graph_id: $session_id, state_hash: $state_hash})
MERGE (f:StateFrontier {
    graph_id: $session_id,
    crawl_session_id: $crawl_session_id,
    state_hash: $state_hash
})
ON CREATE SET
    f.created_at = timestamp(),
    f.status = 'pending',
    f.order = timestamp()
SET f.status = CASE
        WHEN coalesce(f.status, 'seen') = 'explored' THEN f.status
        ELSE 'pending'
    END,
    f.semantic_priority_penalty = coalesce($semantic_priority_penalty, 0.0),
    f.semantic_duplicate_of = $matched_state_hash,
    f.semantic_confidence = $confidence,
    f.semantic_reason = $reason,
    f.semantic_scores_json = $scores_json,
    f.updated_at = timestamp()
RETURN count(f) AS count
"""

SET_STATE_PROPS = """
MATCH (s:State {graph_id: $session_id, state_hash: $state_hash})
SET s += $props
"""

ADD_TRANSITION = """
MATCH (source:State {graph_id: $session_id, state_hash: $source_hash})
MATCH (target:State {graph_id: $session_id, state_hash: $target_hash})
MERGE (source)-[t:TRANSITION {graph_id: $session_id, transition_id: $transition_id}]->(target)
ON CREATE SET t += $props, t.first_seen = timestamp(), t.last_seen = timestamp(), t._was_created = true
ON MATCH SET t += $props, t.last_seen = timestamp(), t._was_created = false
WITH t, t._was_created AS created
REMOVE t._was_created
RETURN created
"""

FIND_EQUIVALENT_TRANSITION = """
MATCH (source:State {graph_id: $session_id, state_hash: $source_hash})
MATCH (target:State {graph_id: $session_id, state_hash: $target_hash})
MATCH (source)-[t:TRANSITION {graph_id: $session_id}]->(target)
WITH properties(t) AS props
WHERE props.action_stable_key = $action_stable_key
   OR (
        coalesce(props.action_stable_key, '') = ''
        AND props.action_type = $action_type
        AND coalesce(props.action_value, '') = $action_value
        AND coalesce(props.locator_value, '') = $locator_value
   )
ORDER BY coalesce(props.first_seen, 0) ASC
RETURN props.transition_id AS transition_id
LIMIT 1
"""

UPDATE_TRANSITION = """
MATCH ()-[t:TRANSITION {graph_id: $session_id, transition_id: $transition_id}]->()
SET t += $props,
    t.last_seen = timestamp()
"""

MARK_ACTION_ATTEMPTED = """
MERGE (a:ActionAttempt {
    graph_id: $session_id,
    crawl_session_id: $crawl_session_id,
    state_hash: $state_hash,
    attempt_fingerprint: $attempt_fingerprint
})
ON CREATE SET a.created_at = timestamp(), a._was_created = true
ON MATCH SET a._was_created = false
WITH a, a._was_created AS created
REMOVE a._was_created
RETURN created
"""

TRY_INCREMENT_ACTION_REPEAT = """
MERGE (c:ActionRepeatCounter {
    graph_id: $session_id,
    crawl_session_id: $crawl_session_id,
    scope: $scope,
    action_key: $action_key
})
ON CREATE SET c.count = 0, c.created_at = timestamp()
WITH c
WHERE c.count < $max_repeats
SET c.count = c.count + 1,
    c.updated_at = timestamp()
RETURN c.count AS count
"""

UPSERT_REPLAY_INFO_IF_BETTER = """
MATCH (s:State {graph_id: $session_id, state_hash: $state_hash})
WITH s, properties(s) AS props
WITH s,
     coalesce(props.replay_score_self_checkpoint, 999999) AS old_self,
     coalesce(props.replay_score_action_count, 999999) AS old_actions,
     coalesce(props.replay_score_fallback_count, 999999) AS old_fallbacks,
     coalesce(props.replay_score_kind_rank, 999999) AS old_kind,
     coalesce(props.replay_score_checkpoint_url, '') AS old_url
WHERE old_self > $score_self_checkpoint
   OR (old_self = $score_self_checkpoint AND old_actions > $score_action_count)
   OR (old_self = $score_self_checkpoint AND old_actions = $score_action_count AND old_fallbacks > $score_fallback_count)
   OR (old_self = $score_self_checkpoint AND old_actions = $score_action_count AND old_fallbacks = $score_fallback_count AND old_kind > $score_kind_rank)
   OR (old_self = $score_self_checkpoint AND old_actions = $score_action_count AND old_fallbacks = $score_fallback_count AND old_kind = $score_kind_rank AND old_url > $score_checkpoint_url)
SET s += $props,
    s.replay_score_self_checkpoint = $score_self_checkpoint,
    s.replay_score_action_count = $score_action_count,
    s.replay_score_fallback_count = $score_fallback_count,
    s.replay_score_kind_rank = $score_kind_rank,
    s.replay_score_checkpoint_url = $score_checkpoint_url
RETURN count(s) AS count
"""

GET_REPLAY_INFO = """
MATCH (s:State {graph_id: $session_id, state_hash: $state_hash})
WITH properties(s) AS props
RETURN props.checkpoint_url AS checkpoint_url,
       props.checkpoint_state_hash AS checkpoint_state_hash,
       props.checkpoint_kind AS checkpoint_kind,
       props.replay_actions_json AS replay_actions_json,
       props.checkpoint_storage_state_json AS checkpoint_storage_state_json,
       props.fallback_checkpoint_url AS fallback_checkpoint_url,
       props.fallback_checkpoint_state_hash AS fallback_checkpoint_state_hash,
       props.fallback_actions_json AS fallback_actions_json,
       props.fallback_storage_state_json AS fallback_storage_state_json
"""

ADD_DEFERRED_WORK = """
MERGE (d:DeferredWork {graph_id: $session_id, crawl_session_id: $crawl_session_id, work_id: $work_id})
ON CREATE SET
    d.source_state_hash = $source_state_hash,
    d.actions_json = $actions_json,
    d.element_json = $element_json,
    d.status = 'pending',
    d.created_at = timestamp()
RETURN d.status AS status
"""

CLAIM_DEFERRED_WORK = """
MATCH (d:DeferredWork {graph_id: $session_id, crawl_session_id: $crawl_session_id, status: 'pending'})
WITH d
ORDER BY d.created_at ASC
LIMIT 1
SET d.status = 'processing',
    d.claimed_at = timestamp()
RETURN d.work_id AS work_id,
       d.source_state_hash AS source_state_hash,
       d.actions_json AS actions_json,
       d.element_json AS element_json
"""

MARK_DEFERRED_WORK_PROCESSED = """
MATCH (d:DeferredWork {graph_id: $session_id, crawl_session_id: $crawl_session_id, work_id: $work_id})
SET d.status = 'processed',
    d.processed_at = timestamp()
"""

UPSERT_SEMANTIC_PROFILE = """
MERGE (p:SemanticProfile {graph_id: $session_id, state_hash: $state_hash})
ON CREATE SET p.created_at = timestamp()
SET p.payload_json = $payload_json,
    p.updated_at = timestamp()
"""

GET_SEMANTIC_PROFILE = """
MATCH (p:SemanticProfile {graph_id: $session_id, state_hash: $state_hash})
RETURN properties(p).payload_json AS payload_json
"""

ITER_SEMANTIC_PROFILES = """
MATCH (p:SemanticProfile {graph_id: $session_id})
MATCH (f:StateFrontier {
    graph_id: $session_id,
    crawl_session_id: $crawl_session_id,
    state_hash: p.state_hash
})
WHERE p.state_hash <> $state_hash
  AND f.status IN $frontier_statuses
RETURN properties(p).payload_json AS payload_json
ORDER BY coalesce(properties(p).created_at, 0) DESC
SKIP $skip
LIMIT $limit
"""

GET_GRAPH = """
MATCH (s:State {graph_id: $session_id})
OPTIONAL MATCH (s)-[t:TRANSITION {graph_id: $session_id}]->(target:State)
RETURN collect(DISTINCT s) AS states,
collect(DISTINCT {
    transition_id: properties(t).transition_id,
    source_hash: properties(s).state_hash,
    target_hash: properties(target).state_hash,
    action_type: properties(t).action_type,
    action_value: properties(t).action_value,
    action_fingerprint: properties(t).action_fingerprint
}) AS transitions
"""

GET_ACTIONS = """
MATCH (s:State {graph_id: $session_id, state_hash: $state_hash})-[t:TRANSITION {graph_id: $session_id}]->(target:State)
WITH properties(t) AS t_props, properties(target) AS target_props
RETURN t_props.transition_id AS transition_id,
target_props.state_hash AS target_state_hash,
t_props.action_type AS action_type,
t_props.action_description AS action_description,
t_props.locator_value AS locator_value,
t_props.action_value AS action_value,
t_props.action_fingerprint AS action_fingerprint
"""

CLEAR_SESSION = """
MATCH (n)
WHERE n.graph_id = $session_id
  AND (
    n:State
    OR n:StateFrontier
    OR n:ActionAttempt
    OR n:ActionRepeatCounter
    OR n:DeferredWork
    OR n:SemanticProfile
  )
DETACH DELETE n
"""

GET_LIGHTWEIGHT_FLOW_GRAPH = """
MATCH (s:State {graph_id: $session_id})
OPTIONAL MATCH (s)-[t:TRANSITION {graph_id: $session_id}]->(target:State)
WITH properties(s) AS s_props, properties(t) AS t_props, properties(target) AS target_props
RETURN
    collect(DISTINCT {
        state_hash: s.state_hash,
        first_seen: s.first_seen
    }) AS states,
    collect(DISTINCT {
        source_hash: s_props.state_hash,
        target_hash: target_props.state_hash,
        transition_id: t_props.transition_id
    }) AS transitions
"""

GET_DATA_FROM_FLOW_QUERY = """
MATCH (s:State {graph_id: $session_id, state_hash: $checkpoint_hash})
WITH properties(s) AS s_props,
     $transition_refs AS refs
UNWIND range(0, size(refs) - 1) AS idx
WITH s_props.checkpoint_url AS checkpoint_url,
     s_props.checkpoint_storage_state_json AS checkpoint_storage_state_json,
     idx,
     refs[idx] AS ref
MATCH (source:State)-[t:TRANSITION {graph_id: $session_id, transition_id: ref}]->(target:State)
WITH checkpoint_url,
     checkpoint_storage_state_json,
     idx,
     properties(source) AS source_props,
     properties(t) AS t_props,
     properties(target) AS target_props
RETURN checkpoint_url,
       checkpoint_storage_state_json,
       collect({
         order: idx,
         transition_id: t_props.transition_id,
         source_state_hash: source_props.state_hash,
         target_state_hash: target_props.state_hash,
         action_type: t_props.action_type,
         action_description: t_props.action_description,
         action_fingerprint: t_props.action_fingerprint,
         selector: t_props.locator_value,
         value: t_props.action_value,
         checkpoint_url: checkpoint_url
       }) AS transitions
"""
