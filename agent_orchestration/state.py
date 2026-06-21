from typing import TYPE_CHECKING, Any

from typing_extensions import NotRequired, TypedDict

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
    # Generation kwargs (temperature/top_p/max_tokens/model) threaded from the
    # API request to the planner and final-answer LLM calls. Optional so existing
    # state constructions stay valid; defaults to {} when absent.
    llm_kwargs: NotRequired[dict[str, Any]]
    # Internal routing hint; not part of the public state contract
    _approval_detected: dict[str, Any] | None
