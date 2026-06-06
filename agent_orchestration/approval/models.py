from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel

from agent_orchestration.models import PendingToolCall


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ApprovalRecord(BaseModel):
    approval_id: str
    conversation_id: str
    graph_state: dict[str, Any]
    pending_tool_call: PendingToolCall
    risk_reason: str
    created_at: datetime
    expires_at: datetime | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
