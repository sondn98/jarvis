import pytest

from agent_orchestration.exceptions import CheckpointNotFoundError
from agent_orchestration.persistence.checkpoint_store import CheckpointStore


def test_save_and_load():
    store = CheckpointStore()
    state = {"key": "value"}
    store.save("conv1", state)
    assert store.load("conv1") == state


def test_load_missing_raises():
    store = CheckpointStore()
    with pytest.raises(CheckpointNotFoundError):
        store.load("missing")


def test_delete():
    store = CheckpointStore()
    store.save("conv1", {"x": 1})
    store.delete("conv1")
    with pytest.raises(CheckpointNotFoundError):
        store.load("conv1")
