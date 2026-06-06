"""In-memory session store.

WARNING: Not production-safe.
- State is lost on process restart.
- Not safe for multi-worker deployments.
Future implementations may use PostgreSQL, Redis, or SQLite.
"""

from typing import Any


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        return self._sessions.get(conversation_id)

    def save(self, conversation_id: str, data: dict[str, Any]) -> None:
        self._sessions[conversation_id] = data

    def delete(self, conversation_id: str) -> None:
        self._sessions.pop(conversation_id, None)
