"""Core graph behavioral tests including critical safety test."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from agent_orchestration.approval.store import ApprovalStore
from agent_orchestration.config import AgentConfig
from agent_orchestration.exceptions import ToolExecutionError, ToolNotFoundError
from agent_orchestration.graph import AgentGraph
from agent_orchestration.models import AgentPlan, PendingToolCall, ToolResult
from agent_orchestration.persistence.checkpoint_store import CheckpointStore
from agent_orchestration.tools.backends import GmailSendResult
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.registry import ToolRegistry
from agent_orchestration.tools.risk import ToolRiskLevel
from llm.models import ChatResponse, Message, MessageRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _messages(text: str) -> list[Message]:
    return [Message(role=MessageRole.USER, content=text)]


def _plan_json(plan: AgentPlan) -> str:
    return plan.model_dump_json()


def _llm_for_plan(
    plan: AgentPlan, final_answer: str = "Here is your answer."
) -> MagicMock:
    """Return mock LLMService that returns plan on first call, final answer on subsequent."""
    call_count = 0

    async def _achat(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        response_model = kwargs.get("response_model")
        if response_model is not None:
            return ChatResponse(content=_plan_json(plan), finish_reason="stop")
        return ChatResponse(content=final_answer, finish_reason="stop")

    llm = MagicMock()
    llm.achat = AsyncMock(side_effect=_achat)
    return llm


class _FakeArgs(BaseModel):
    query: str


class _SafeTool(BaseTool):
    name = "web_search"
    description = "Search the web."
    risk_level = ToolRiskLevel.SAFE_READ_ONLY
    args_schema = _FakeArgs

    def __init__(self, backend):
        self._backend = backend

    async def arun(self, arguments):
        result = await self._backend.search(arguments["query"])
        return ToolResult(
            tool_name=self.name,
            arguments=arguments,
            output=json.dumps(result),
            success=True,
        )


class _GmailSendArgs(BaseModel):
    to: str
    subject: str
    body: str
    cc: str | None = None


class _GmailSendTool(BaseTool):
    name = "gmail_send_email"
    description = "Send email."
    risk_level = ToolRiskLevel.EXTERNAL_WRITE
    args_schema = _GmailSendArgs

    def __init__(self, backend):
        self._backend = backend

    async def arun(self, arguments):
        result = await self._backend.send_email(**arguments)
        return ToolResult(
            tool_name=self.name,
            arguments=arguments,
            output=json.dumps(result.model_dump()),
            success=True,
        )


class _CalendarDeleteArgs(BaseModel):
    event_id: str


class _CalendarDeleteTool(BaseTool):
    name = "calendar_delete_event"
    description = "Delete calendar event."
    risk_level = ToolRiskLevel.DESTRUCTIVE
    args_schema = _CalendarDeleteArgs

    def __init__(self, backend):
        self._backend = backend

    async def arun(self, arguments):
        result = await self._backend.delete_event(arguments["event_id"])
        return ToolResult(
            tool_name=self.name,
            arguments=arguments,
            output=json.dumps(result.model_dump()),
            success=True,
        )


class _SensitiveReadArgs(BaseModel):
    query: str


class _SensitiveReadTool(BaseTool):
    name = "gmail_search_messages"
    description = "Search Gmail."
    risk_level = ToolRiskLevel.SENSITIVE_READ
    args_schema = _SensitiveReadArgs

    def __init__(self, backend):
        self._backend = backend

    async def arun(self, arguments):
        return ToolResult(
            tool_name=self.name, arguments=arguments, output="[]", success=True
        )


def _graph(
    llm,
    registry: ToolRegistry,
    config: AgentConfig | None = None,
    approval_store: ApprovalStore | None = None,
    checkpoint_store: CheckpointStore | None = None,
) -> AgentGraph:
    return AgentGraph(
        llm_service=llm,
        registry=registry,
        approval_store=approval_store or ApprovalStore(),
        checkpoint_store=checkpoint_store or CheckpointStore(),
        config=config or AgentConfig(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_answer_without_tools():
    plan = AgentPlan(requires_tool=False, final_answer="42")
    registry = ToolRegistry()
    g = _graph(_llm_for_plan(plan), registry)
    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c1",
        messages=_messages("What is the answer?"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)
    assert result["final_response"] == "42"


@pytest.mark.asyncio
async def test_safe_tool_executes_without_approval():
    web_backend = MagicMock()
    web_backend.search = AsyncMock(return_value=["result1"])

    registry = ToolRegistry()
    registry.register(_SafeTool(web_backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(tool_name="web_search", arguments={"query": "AI"}),
    )
    g = _graph(_llm_for_plan(plan, "Found results."), registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c2",
        messages=_messages("Search for AI"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)
    web_backend.search.assert_called_once_with("AI")
    assert result["final_response"] == "Found results."
    assert result["approval_request"] is None


@pytest.mark.asyncio
async def test_sensitive_read_no_approval_by_default():
    backend = MagicMock()
    registry = ToolRegistry()
    registry.register(_SensitiveReadTool(backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="gmail_search_messages", arguments={"query": "invoice"}
        ),
    )
    config = AgentConfig(require_approval_for_sensitive_read=False)
    g = _graph(_llm_for_plan(plan), registry, config=config)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c3",
        messages=_messages("Search Gmail for invoices"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)
    assert result["approval_request"] is None


@pytest.mark.asyncio
async def test_sensitive_read_requires_approval_when_configured():
    backend = MagicMock()
    registry = ToolRegistry()
    registry.register(_SensitiveReadTool(backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="gmail_search_messages", arguments={"query": "invoice"}
        ),
    )
    config = AgentConfig(require_approval_for_sensitive_read=True)
    g = _graph(_llm_for_plan(plan), registry, config=config)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c4",
        messages=_messages("Search Gmail for invoices"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)
    assert result["approval_request"] is not None


@pytest.mark.asyncio
async def test_risky_tool_returns_approval_request_gmail_backend_zero_calls():
    """Critical safety test: gmail backend must NOT be called before approval."""
    gmail_backend = MagicMock()
    gmail_backend.send_email = AsyncMock(
        return_value=GmailSendResult(message_id="msg1", status="sent")
    )

    registry = ToolRegistry()
    registry.register(_GmailSendTool(gmail_backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="gmail_send_email",
            arguments={"to": "alice@example.com", "subject": "Hi", "body": "Hello"},
        ),
    )
    g = _graph(_llm_for_plan(plan), registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c5",
        messages=_messages("Send an email to alice"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)

    assert result["approval_request"] is not None
    # CRITICAL: backend must NOT have been called
    gmail_backend.send_email.assert_not_called()


@pytest.mark.asyncio
async def test_approve_resumes_and_calls_gmail_backend_once():
    """After APPROVE reply, gmail backend must be called exactly once."""
    gmail_backend = MagicMock()
    gmail_backend.send_email = AsyncMock(
        return_value=GmailSendResult(message_id="msg1", status="sent")
    )

    registry = ToolRegistry()
    registry.register(_GmailSendTool(gmail_backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="gmail_send_email",
            arguments={"to": "alice@example.com", "subject": "Hi", "body": "Hello"},
        ),
    )
    approval_store = ApprovalStore()
    checkpoint_store = CheckpointStore()
    g = _graph(
        _llm_for_plan(plan, "Email sent."),
        registry,
        approval_store=approval_store,
        checkpoint_store=checkpoint_store,
    )

    from agent_orchestration.state import AgentState

    # Request #1 — get approval request
    state1 = AgentState(
        conversation_id="c6",
        messages=_messages("Send an email to alice"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result1 = await g.run(state1)
    approval_id = result1["approval_request"].approval_id
    assert gmail_backend.send_email.call_count == 0

    # Request #2 — user approves
    state2 = AgentState(
        conversation_id="c6",
        messages=_messages(f"APPROVE {approval_id}"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result2 = await g.run(state2)
    assert gmail_backend.send_email.call_count == 1
    assert result2["final_response"] == "Email sent."


@pytest.mark.asyncio
async def test_reject_skips_tool_execution():
    gmail_backend = MagicMock()
    gmail_backend.send_email = AsyncMock(
        return_value=GmailSendResult(message_id="msg1", status="sent")
    )

    registry = ToolRegistry()
    registry.register(_GmailSendTool(gmail_backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="gmail_send_email",
            arguments={"to": "alice@example.com", "subject": "Hi", "body": "Hello"},
        ),
    )
    approval_store = ApprovalStore()
    checkpoint_store = CheckpointStore()
    g = _graph(
        _llm_for_plan(plan, "Cancelled."),
        registry,
        approval_store=approval_store,
        checkpoint_store=checkpoint_store,
    )

    from agent_orchestration.state import AgentState

    state1 = AgentState(
        conversation_id="c7",
        messages=_messages("Send an email to alice"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result1 = await g.run(state1)
    approval_id = result1["approval_request"].approval_id

    state2 = AgentState(
        conversation_id="c7",
        messages=_messages(f"REJECT {approval_id}"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result2 = await g.run(state2)
    gmail_backend.send_email.assert_not_called()
    assert result2["final_response"] == "Cancelled."


@pytest.mark.asyncio
async def test_unknown_tool_raises():
    registry = ToolRegistry()
    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(tool_name="nonexistent_tool", arguments={"x": 1}),
    )
    g = _graph(_llm_for_plan(plan), registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c8",
        messages=_messages("Do something"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    with pytest.raises(ToolNotFoundError):
        await g.run(state)


@pytest.mark.asyncio
async def test_tool_execution_failure_raises():
    backend = MagicMock()
    backend.search = AsyncMock(side_effect=RuntimeError("network error"))

    registry = ToolRegistry()
    registry.register(_SafeTool(backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(tool_name="web_search", arguments={"query": "AI"}),
    )
    g = _graph(_llm_for_plan(plan), registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c9",
        messages=_messages("Search for AI"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    with pytest.raises(ToolExecutionError):
        await g.run(state)


@pytest.mark.asyncio
async def test_calendar_delete_requires_approval():
    backend = MagicMock()
    registry = ToolRegistry()
    registry.register(_CalendarDeleteTool(backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(
            tool_name="calendar_delete_event", arguments={"event_id": "evt1"}
        ),
    )
    g = _graph(_llm_for_plan(plan), registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c10",
        messages=_messages("Delete my meeting"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)
    assert result["approval_request"] is not None
    backend.delete_event.assert_not_called() if hasattr(
        backend, "delete_event"
    ) else None


@pytest.mark.asyncio
async def test_web_search_no_approval_required():
    web_backend = MagicMock()
    web_backend.search = AsyncMock(return_value=["r1"])

    registry = ToolRegistry()
    registry.register(_SafeTool(web_backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(tool_name="web_search", arguments={"query": "news"}),
    )
    g = _graph(_llm_for_plan(plan, "Done."), registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c11",
        messages=_messages("Latest news"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)
    web_backend.search.assert_called_once()
    assert result["approval_request"] is None


@pytest.mark.asyncio
async def test_final_answer_receives_tool_results_as_context():
    """Final answer LLM call must receive tool results in its messages."""
    web_backend = MagicMock()
    web_backend.search = AsyncMock(return_value=["AI news item"])

    registry = ToolRegistry()
    registry.register(_SafeTool(web_backend))

    plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(tool_name="web_search", arguments={"query": "AI"}),
    )

    captured_messages = []

    async def _achat(messages, **kwargs):
        response_model = kwargs.get("response_model")
        if response_model is not None:
            return ChatResponse(content=_plan_json(plan), finish_reason="stop")
        captured_messages.extend(messages)
        return ChatResponse(content="Grounded answer.", finish_reason="stop")

    llm = MagicMock()
    llm.achat = AsyncMock(side_effect=_achat)

    g = _graph(llm, registry)

    from agent_orchestration.state import AgentState

    state = AgentState(
        conversation_id="c12",
        messages=_messages("Search for AI"),
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        errors=[],
        _approval_detected=None,
    )
    result = await g.run(state)

    # Verify tool results were injected into the final answer LLM call
    all_content = " ".join(m.content for m in captured_messages)
    assert "web_search" in all_content or "AI news item" in all_content
    assert result["final_response"] == "Grounded answer."
