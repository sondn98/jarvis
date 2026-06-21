from typing import Any
from uuid import uuid4

from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.config import AgentConfig
from agent_orchestration.graph import AgentGraph
from agent_orchestration.models import AgentResponse
from agent_orchestration.persistence.checkpoint_store import CheckpointStore
from agent_orchestration.state import AgentState
from agent_orchestration.tools.registry import ToolRegistry
from llm.models import Message
from llm.service import LLMService


class AgentService:
    """Public entry point for the agent orchestration module.

    Wraps AgentGraph and handles conversation ID assignment.
    """

    def __init__(
        self,
        llm_service: LLMService,
        registry: ToolRegistry,
        approval_store: ApprovalStore,
        checkpoint_store: CheckpointStore,
        config: AgentConfig,
    ) -> None:
        self._graph = AgentGraph(
            llm_service=llm_service,
            registry=registry,
            approval_store=approval_store,
            checkpoint_store=checkpoint_store,
            config=config,
        )

    async def achat(
        self,
        messages: list[Message],
        tools_enabled: bool = True,
        conversation_id: str | None = None,
        **kwargs: Any,
    ) -> AgentResponse:
        cid = conversation_id or uuid4().hex

        initial_state = AgentState(
            conversation_id=cid,
            messages=messages,
            user_request=None,
            plan=None,
            selected_tool_call=None,
            tool_results=[],
            approval_request=None,
            approval_decision=None,
            final_response=None,
            llm_kwargs=kwargs,
            _approval_detected=None,
        )

        final_state = await self._graph.run(initial_state)

        approval_request = final_state.get("approval_request")
        requires_approval = (
            approval_request is not None
            and final_state.get("approval_decision") is None
        )

        return AgentResponse(
            content=final_state.get("final_response") or "",
            requires_approval=requires_approval,
            approval_request=approval_request,
        )
