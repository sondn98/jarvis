from typing import TYPE_CHECKING, Any

from typing_extensions import TypedDict

from agent_orchestration.models import (
    AgentPlan,
    ApprovalDecision,
    ApprovalRequest,
    PendingToolCall,
    ToolResult,
)
from llm.models import Message

if TYPE_CHECKING:
    pass


class AgentState(TypedDict):
    conversation_id: str
    messages: list[Message]
    user_request: str | None
    plan: AgentPlan | None
    selected_tool_call: PendingToolCall | None
    tool_results: list[ToolResult]
    approval_request: ApprovalRequest | None
    approval_decision: ApprovalDecision | None
    final_response: str | None
    errors: list[str]
    # Internal routing hint; not part of the public state contract
    _approval_detected: dict[str, Any] | None
