from datetime import UTC, datetime

import pytest

from agent_orchestration.approval.models import ApprovalRecord, ApprovalStatus
from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.exceptions import ApprovalNotFoundError
from agent_orchestration.models import PendingToolCall


def _record(approval_id: str = "abc123") -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=approval_id,
        conversation_id="conv1",
        graph_state={},
        pending_tool_call=PendingToolCall(
            tool_name="web_search", arguments={"query": "test"}
        ),
        risk_reason="test",
        created_at=datetime.now(UTC),
    )


def test_save_and_get():
    store = ApprovalStore()
    record = _record()
    store.save(record)
    assert store.get("abc123") == record


def test_get_missing_raises():
    store = ApprovalStore()
    with pytest.raises(ApprovalNotFoundError):
        store.get("missing")


def test_update_status():
    store = ApprovalStore()
    store.save(_record())
    updated = store.update_status("abc123", ApprovalStatus.APPROVED)
    assert updated.status == ApprovalStatus.APPROVED
    assert store.get("abc123").status == ApprovalStatus.APPROVED
