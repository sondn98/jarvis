from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.config import AgentConfig
from agent_orchestration.models import AgentPlan, AgentResponse, PendingToolCall
from agent_orchestration.persistence.checkpoint_store import CheckpointStore
from agent_orchestration.service import AgentService
from agent_orchestration.tools.registry import ToolRegistry
from llm.models import ChatResponse, Message, MessageRole


def _make_service(plan: AgentPlan, final: str = "answer") -> AgentService:
    async def _achat(messages, **kwargs):
        if kwargs.get("response_model"):
            return ChatResponse(content=plan.model_dump_json(), finish_reason="stop")
        return ChatResponse(content=final, finish_reason="stop")

    llm = MagicMock()
    llm.achat = AsyncMock(side_effect=_achat)
    return AgentService(
        llm_service=llm,
        registry=ToolRegistry(),
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=AgentConfig(),
    )


@pytest.mark.asyncio
async def test_achat_returns_agent_response():
    plan = AgentPlan(requires_tool=False, final_answer="Hello!")
    service = _make_service(plan, "Hello!")
    messages = [Message(role=MessageRole.USER, content="Hi")]
    result = await service.achat(messages)
    assert isinstance(result, AgentResponse)
    assert result.content == "Hello!"
    assert result.requires_approval is False


@pytest.mark.asyncio
async def test_achat_with_risky_tool_sets_requires_approval():
    from agent_orchestration.models import ToolResult
    from agent_orchestration.tools.base import BaseTool
    from agent_orchestration.tools.risk import ToolRiskLevel
    from pydantic import BaseModel

    class _Args(BaseModel):
        to: str
        subject: str
        body: str

    class _RiskyTool(BaseTool):
        name = "gmail_send_email"
        description = "Send email."
        risk_level = ToolRiskLevel.EXTERNAL_WRITE
        args_schema = _Args

        async def arun(self, arguments):
            return ToolResult(
                tool_name=self.name, arguments=arguments, output="ok", success=True
            )

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="gmail_send_email",
            arguments={"to": "a@b.com", "subject": "x", "body": "y"},
        ),
    )

    async def _achat(messages, **kwargs):
        if kwargs.get("response_model"):
            return ChatResponse(content=plan.model_dump_json(), finish_reason="stop")
        return ChatResponse(content="approval prompt", finish_reason="stop")

    llm = MagicMock()
    llm.achat = AsyncMock(side_effect=_achat)
    registry = ToolRegistry()
    registry.register(_RiskyTool())

    service = AgentService(
        llm_service=llm,
        registry=registry,
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=AgentConfig(),
    )
    messages = [Message(role=MessageRole.USER, content="Send email to alice")]
    result = await service.achat(messages)
    assert result.requires_approval is True
    assert result.approval_request is not None
