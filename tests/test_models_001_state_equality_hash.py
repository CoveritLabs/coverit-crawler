from src.models import AbstractState


def test_abstract_state_equality_uses_state_hash():
    assert AbstractState(state_hash="same", url="/a") == AbstractState(state_hash="same", url="/b")
