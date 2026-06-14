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

GET_LIGHTWEIGHT_FLOW_GRAPH = """
MATCH (s:State {session_id: $session_id})
OPTIONAL MATCH (s)-[t:TRANSITION]->(target:State)
RETURN 
    collect(DISTINCT {
        state_hash: s.state_hash,
        is_checkpoint: s.is_checkpoint,
        checkpoint_kind: s.checkpoint_kind
    }) AS states,
    collect(DISTINCT {
        source_hash: s.state_hash,
        target_hash: target.state_hash,
        transition_id: t.transition_id
    }) AS transitions
"""