"""In-memory approval store.

WARNING: Not production-safe.
- State is lost on process restart.
- Not safe for multi-worker deployments.
Future implementations may use PostgreSQL, Redis, or SQLite.
"""

from agent_orchestration.approval.models import ApprovalRecord, ApprovalStatus
from agent_orchestration.exceptions import ApprovalNotFoundError


class ApprovalStore:
    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}

    def save(self, record: ApprovalRecord) -> None:
        self._records[record.approval_id] = record

    def get(self, approval_id: str) -> ApprovalRecord:
        record = self._records.get(approval_id)
        if record is None:
            raise ApprovalNotFoundError(f"Approval '{approval_id}' not found.")
        return record

    def update_status(self, approval_id: str, status: ApprovalStatus) -> ApprovalRecord:
        record = self.get(approval_id)
        updated = record.model_copy(update={"status": status})
        self._records[approval_id] = updated
        return updated
