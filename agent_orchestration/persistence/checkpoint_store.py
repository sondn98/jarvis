"""In-memory checkpoint store for LangGraph approval resume.

WARNING: Not production-safe.
- State is lost on process restart.
- Not safe for multi-worker deployments.
Future implementations may use PostgreSQL, Redis, or SQLite.
"""

from typing import Any

from agent_orchestration.exceptions import CheckpointNotFoundError


class CheckpointStore:
    def __init__(self) -> None:
        self._checkpoints: dict[str, dict[str, Any]] = {}

    def save(self, conversation_id: str, state: dict[str, Any]) -> None:
        self._checkpoints[conversation_id] = state

    def load(self, conversation_id: str) -> dict[str, Any]:
        checkpoint = self._checkpoints.get(conversation_id)
        if checkpoint is None:
            raise CheckpointNotFoundError(
                f"No checkpoint found for conversation '{conversation_id}'."
            )
        return checkpoint

    def delete(self, conversation_id: str) -> None:
        self._checkpoints.pop(conversation_id, None)
