from src.models import AbstractTransition


def test_abstract_transition_defaults_to_empty_strings():
    transition = AbstractTransition()
    assert transition.graph_id == ""
    assert transition.action_value == ""
