from src.models import AbstractState


def test_abstract_state_not_equal_to_other_type():
    assert AbstractState(state_hash="s") != "s"
