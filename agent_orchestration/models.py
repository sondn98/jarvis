from typing import Any

from pydantic import BaseModel


class PendingToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]


class AgentPlan(BaseModel):
    requires_tool: bool
    tool_call: PendingToolCall | None = None
    final_answer: str | None = None
    reasoning_summary: str | None = None


class ToolResult(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    output: str
    success: bool
    error: str | None = None


class ApprovalRequest(BaseModel):
    approval_id: str
    tool_name: str
    arguments: dict[str, Any]
    risk_reason: str
    message: str


class ApprovalDecision(BaseModel):
    approval_id: str
    approved: bool


class AgentResponse(BaseModel):
    content: str
    requires_approval: bool = False
    approval_request: ApprovalRequest | None = None
