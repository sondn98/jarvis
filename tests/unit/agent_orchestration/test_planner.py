from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_orchestration.exceptions import PlanningError
from agent_orchestration.models import AgentPlan, PendingToolCall
from agent_orchestration.planning.planner import Planner
from agent_orchestration.tools.registry import ToolRegistry
from llm.models import ChatResponse, Message, MessageRole


def _make_llm(plan: AgentPlan) -> MagicMock:
    llm = MagicMock()
    llm.achat = AsyncMock(
        return_value=ChatResponse(content=plan.model_dump_json(), finish_reason="stop")
    )
    return llm


def _make_registry() -> ToolRegistry:
    registry = ToolRegistry()
    from agent_orchestration.models import ToolResult
    from agent_orchestration.tools.base import BaseTool
    from agent_orchestration.tools.risk import ToolRiskLevel
    from pydantic import BaseModel

    class _Args(BaseModel):
        query: str

    class _FakeTool(BaseTool):
        name = "web_search"
        description = "Search the web."
        risk_level = ToolRiskLevel.SAFE_READ_ONLY
        args_schema = _Args

        async def arun(self, arguments):
            return ToolResult(
                tool_name=self.name, arguments=arguments, output="", success=True
            )

    registry.register(_FakeTool())
    return registry


@pytest.mark.asyncio
async def test_planner_produces_valid_plan():
    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="web_search", arguments={"query": "AI news"}
        ),
    )
    llm = _make_llm(plan)
    planner = Planner(llm, _make_registry())
    messages = [Message(role=MessageRole.USER, content="Search for AI news")]
    result = await planner.plan(messages)
    assert result.requires_tool is True
    assert result.tool_call.tool_name == "web_search"


@pytest.mark.asyncio
async def test_planner_direct_answer():
    plan = AgentPlan(requires_tool=False, final_answer="The sky is blue.")
    llm = _make_llm(plan)
    planner = Planner(llm, _make_registry())
    messages = [Message(role=MessageRole.USER, content="What colour is the sky?")]
    result = await planner.plan(messages)
    assert result.requires_tool is False
    assert result.final_answer == "The sky is blue."


@pytest.mark.asyncio
async def test_planner_raises_on_llm_failure():
    llm = MagicMock()
    llm.achat = AsyncMock(side_effect=RuntimeError("LLM down"))
    planner = Planner(llm, _make_registry())
    messages = [Message(role=MessageRole.USER, content="hello")]
    with pytest.raises(PlanningError):
        await planner.plan(messages)


@pytest.mark.asyncio
async def test_planner_raises_on_bad_json():
    llm = MagicMock()
    llm.achat = AsyncMock(
        return_value=ChatResponse(content="not valid json", finish_reason="stop")
    )
    planner = Planner(llm, _make_registry())
    messages = [Message(role=MessageRole.USER, content="hello")]
    with pytest.raises(PlanningError):
        await planner.plan(messages)
