ADD_STATE = """
MERGE (s:State {session_id: $session_id, state_hash: $state_hash})
ON CREATE SET s.url = $url, s.title = $title, s.first_seen = timestamp(), s.last_seen = timestamp()
ON MATCH SET s.url = $url, s.title = $title, s.last_seen = timestamp()
"""

SET_STATE_PROPS = """
MATCH (s:State {session_id: $session_id, state_hash: $state_hash})
SET s += $props
"""

ADD_TRANSITION = """
MATCH (source:State {session_id: $session_id, state_hash: $source_hash})
MATCH (target:State {session_id: $session_id, state_hash: $target_hash})
MERGE (source)-[t:TRANSITION {session_id: $session_id, transition_id: $transition_id}]->(target)
ON CREATE SET t += $props, t.first_seen = timestamp(), t.last_seen = timestamp()
ON MATCH SET t += $props, t.last_seen = timestamp()
"""

GET_GRAPH = """
MATCH (s:State {session_id: $session_id})
OPTIONAL MATCH (s)-[t:TRANSITION]->(target:State)
RETURN collect(DISTINCT s) AS states,
collect(DISTINCT {transition_id: t.transition_id, source_hash: s.state_hash, target_hash: target.state_hash, action_type: t.action_type, action_value: t.action_value, action_fingerprint: t.action_fingerprint}) AS transitions
"""

GET_ACTIONS = """
MATCH (s:State {session_id: $session_id, state_hash: $state_hash})-[t:TRANSITION]->(target:State)
RETURN t.transition_id AS transition_id,
target.state_hash AS target_state_hash,
t.action_type AS action_type,
t.action_description AS action_description,
t.locator_value AS locator_value,
t.action_value AS action_value,
t.action_fingerprint AS action_fingerprint
"""

CLEAR_SESSION = """
MATCH (s:State {session_id: $session_id})
DETACH DELETE s
"""

GET_STATES_WITH_CHECKPOINTS = """
MATCH (s:State {session_id: $session_id})
OPTIONAL MATCH (s)-[t:TRANSITION]->(target:State {session_id: $session_id})
RETURN
    collect(DISTINCT {
        state_hash:                     s.state_hash,
        url:                            s.url,
        title:                          s.title,
        first_seen:                     s.first_seen,
        is_checkpoint:                  s.is_checkpoint,
        checkpoint_kind:                s.checkpoint_kind,
        checkpoint_url:                 s.checkpoint_url,
        checkpoint_state_hash:          s.checkpoint_state_hash,
        replay_actions_json:            s.replay_actions_json,
        fallback_checkpoint_url:        s.fallback_checkpoint_url,
        fallback_checkpoint_state_hash: s.fallback_checkpoint_state_hash,
        fallback_actions_json:          s.fallback_actions_json,
        checkpoint_storage_state_json:  s.checkpoint_storage_state_json
    }) AS states,
    collect(DISTINCT {
        transition_id:      t.transition_id,
        source_hash:        s.state_hash,
        target_hash:        target.state_hash,
        action_type:        t.action_type,
        action_description: t.action_description,
        action_value:       t.action_value,
        action_fingerprint: t.action_fingerprint,
        locator_value:      t.locator_value
    }) AS transitions
"""