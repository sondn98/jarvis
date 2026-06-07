"""In-memory approval store.

WARNING: Not production-safe.
- State is lost on process restart.
- Not safe for multi-worker deployments.
Future implementations may use PostgreSQL, Redis, or SQLite.
"""

import logging

from agent_orchestration.approval.models import ApprovalRecord, ApprovalStatus
from agent_orchestration.exceptions import ApprovalNotFoundError

logger = logging.getLogger("jarvis.agent.approval")


class ApprovalStore:
    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    def save(self, record: ApprovalRecord) -> None:
        self._records[record.approval_id] = record
        logger.debug(
            "Approval record saved: id=%s, tool=%s",
            record.approval_id,
            record.pending_tool_call.tool_name if record.pending_tool_call else None,
            extra={"approval_id": record.approval_id},
        )

    def get(self, approval_id: str) -> ApprovalRecord:
        record = self._records.get(approval_id)
        if record is None:
            raise ApprovalNotFoundError(f"Approval '{approval_id}' not found.")
        logger.debug(
            "Approval record retrieved: id=%s, status=%s", approval_id, record.status
        )
        return record

    def update_status(self, approval_id: str, status: ApprovalStatus) -> ApprovalRecord:
        record = self.get(approval_id)
        updated = record.model_copy(update={"status": status})
        self._records[approval_id] = updated
        logger.debug(
            "Approval status updated: id=%s, status=%s",
            approval_id,
            status.value,
            extra={"approval_id": approval_id, "status": status.value},
        )
        return updated
