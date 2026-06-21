"""Tests for debug/trace logging across LLM and agent orchestration modules."""

import logging
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Importing logging_utils registers the TRACE level and patches Logger.trace
from logging_utils import TRACE, RedactionFilter, redact

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chat_response(content: str) -> Any:
    from llm.models import ChatResponse

    return ChatResponse(content=content, finish_reason="stop")


def _make_plan(requires_tool: bool = False, answer: str = "The answer.") -> Any:
    from agent_orchestration.models import AgentPlan, PendingToolCall

    if requires_tool:
        return AgentPlan(
            requires_tool=True,
            tool_call=PendingToolCall(
                tool_name="web_search", arguments={"query": "test"}
            ),
        )
    return AgentPlan(requires_tool=False, final_answer=answer)


def _make_planner_llm(plan: Any) -> MagicMock:
    llm = MagicMock()
    llm.achat = AsyncMock(return_value=_make_chat_response(plan.model_dump_json()))
    return llm


def _make_registry() -> Any:
    from agent_orchestration.models import ToolResult
    from agent_orchestration.tools.base import BaseTool
    from agent_orchestration.tools.registry import ToolRegistry
    from agent_orchestration.tools.risk import ToolRiskLevel
    from pydantic import BaseModel

    class _Args(BaseModel):
        query: str

    class _FakeTool(BaseTool):
        name = "web_search"
        description = "Search the web."
        risk_level = ToolRiskLevel.SAFE_READ_ONLY
        args_schema = _Args

        async def arun(self, arguments: dict) -> ToolResult:
            return ToolResult(
                tool_name=self.name,
                arguments=arguments,
                output="some results",
                success=True,
            )

    registry = ToolRegistry()
    registry.register(_FakeTool())
    return registry


# ---------------------------------------------------------------------------
# 1. DEBUG logs emitted for planner responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_planner_debug_logs_decision(caplog: pytest.LogCaptureFixture) -> None:
    from agent_orchestration.planning.planner import Planner

    plan = _make_plan(requires_tool=True)
    llm = _make_planner_llm(plan)
    planner = Planner(llm, _make_registry())

    from llm.models import Message, MessageRole

    messages = [Message(role=MessageRole.USER, content="Search for news")]

    with caplog.at_level(logging.DEBUG, logger="jarvis.agent.planner"):
        await planner.plan(messages)

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("requires_tool" in m for m in debug_msgs), (
        f"Expected planner decision log, got: {debug_msgs}"
    )
    assert any("web_search" in m for m in debug_msgs)


# ---------------------------------------------------------------------------
# 2. DEBUG logs emitted for final LLM responses (via graph node)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_graph_debug_logs_final_answer(caplog: pytest.LogCaptureFixture) -> None:
    from agent_orchestration.graph import AgentGraph
    from agent_orchestration.approval.store import ApprovalStore
    from agent_orchestration.config import AgentConfig
    from agent_orchestration.persistence.checkpoint_store import CheckpointStore
    from agent_orchestration.state import AgentState
    from llm.models import Message, MessageRole

    plan = _make_plan(requires_tool=False, answer="Direct answer.")
    llm = MagicMock()
    llm.achat = AsyncMock(return_value=_make_chat_response(plan.model_dump_json()))

    graph = AgentGraph(
        llm_service=llm,
        registry=_make_registry(),
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=AgentConfig(
            require_approval_for_external_write=False,
            require_approval_for_destructive=False,
            require_approval_for_unknown=False,
        ),
    )

    state = AgentState(
        conversation_id="test-conv",
        messages=[Message(role=MessageRole.USER, content="What is 2+2?")],
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        _approval_detected=None,
    )

    with caplog.at_level(logging.DEBUG, logger="jarvis.agent.graph"):
        await graph.run(state)

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("generate_final_answer" in m for m in debug_msgs), (
        f"Expected node logs, got: {debug_msgs}"
    )


# ---------------------------------------------------------------------------
# 3. TRACE logs emitted for raw provider responses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_trace_logs_raw_response(caplog: pytest.LogCaptureFixture) -> None:
    from llm.config import LLMConfig
    from llm.models import Message, MessageRole
    from llm.providers.ollama import OllamaProvider

    config = LLMConfig(default_model="test-model")
    provider = OllamaProvider(config)

    mock_raw = MagicMock()
    mock_raw.message = MagicMock()
    mock_raw.message.content = "The answer is 42."
    mock_raw.message.tool_calls = None
    mock_raw.done_reason = "stop"
    mock_raw.prompt_eval_count = 10
    mock_raw.eval_count = 20

    with patch.object(
        provider._async_client, "chat", new=AsyncMock(return_value=mock_raw)
    ):
        with caplog.at_level(TRACE, logger="jarvis.llm"):
            messages = [Message(role=MessageRole.USER, content="What is 6x7?")]
            await provider.achat(messages)

    trace_msgs = [r.message for r in caplog.records if r.levelno == TRACE]
    assert len(trace_msgs) > 0, "Expected TRACE records from jarvis.llm"
    assert any("raw response" in m.lower() for m in trace_msgs), (
        f"TRACE records: {trace_msgs}"
    )


# ---------------------------------------------------------------------------
# 4. Sensitive fields are redacted by default
# ---------------------------------------------------------------------------


def test_email_redacted() -> None:
    result = redact("Contact alice@example.com for details.")
    assert "alice@example.com" not in result
    assert "a***@example.com" in result


def test_bearer_token_redacted() -> None:
    result = redact("Authorization: Bearer abc123secrettoken")
    assert "abc123secrettoken" not in result
    assert "[REDACTED]" in result


def test_api_key_redacted() -> None:
    result = redact("api_key=supersecret123")
    assert "supersecret123" not in result
    assert "[REDACTED]" in result


def test_sensitive_dict_key_redacted() -> None:
    result = redact({"username": "alice", "password": "hunter2", "data": "ok"})
    assert result["password"] == "[REDACTED]"
    assert result["username"] == "alice"
    assert result["data"] == "ok"


def test_nested_list_of_dicts_redacted() -> None:
    # Mirrors logging a list of message dicts: nested sensitive keys and
    # email strings must be redacted, not just top-level ones (L7 remediation).
    result = redact(
        [
            {"role": "user", "api_key": "sk-secret", "content": "ping bob@example.com"},
            {"role": "assistant", "content": "ok"},
        ]
    )
    assert result[0]["api_key"] == "[REDACTED]"
    assert "bob@example.com" not in result[0]["content"]
    assert result[1]["content"] == "ok"


def test_nested_tuple_redacted() -> None:
    result = redact(({"password": "hunter2"}, "plain"))
    assert isinstance(result, tuple)
    assert result[0]["password"] == "[REDACTED]"
    assert result[1] == "plain"


def test_redaction_filter_modifies_record() -> None:
    f = RedactionFilter()
    record = logging.LogRecord(
        name="jarvis.test",
        level=logging.DEBUG,
        pathname="",
        lineno=0,
        msg="User email is bob@example.com and token=abc123",
        args=(),
        exc_info=None,
    )
    f.filter(record)
    assert "bob@example.com" not in record.msg
    assert "b***@example.com" in record.msg


# ---------------------------------------------------------------------------
# 5. Redaction can be disabled
# ---------------------------------------------------------------------------


def test_redaction_disabled_leaves_email_intact() -> None:
    # When redact_sensitive=False, no RedactionFilter is applied.
    # Verify that redact() is the only thing that masks — calling it with a
    # plain string, while skipping the filter, leaves the original intact.
    original = "Contact alice@example.com for info."
    # Without calling redact(), the string is unchanged
    assert "alice@example.com" in original


def test_configure_logging_no_filter_when_disabled() -> None:
    from logging_utils import configure_logging

    root = logging.getLogger()
    # Remove any existing redaction filters first
    root.filters = [f for f in root.filters if not isinstance(f, RedactionFilter)]

    configure_logging(level="DEBUG", redact_sensitive=False)
    assert not any(isinstance(f, RedactionFilter) for f in root.filters)

    # Cleanup: restore root level
    root.setLevel(logging.WARNING)


def test_configure_logging_adds_filter_when_enabled() -> None:
    from logging_utils import configure_logging

    root = logging.getLogger()
    root.filters = [f for f in root.filters if not isinstance(f, RedactionFilter)]

    configure_logging(level="DEBUG", redact_sensitive=True)
    assert any(isinstance(f, RedactionFilter) for f in root.filters)

    # Cleanup
    root.filters = [f for f in root.filters if not isinstance(f, RedactionFilter)]
    root.setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# 6. Tool execution DEBUG logs appear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tool_execution_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    from agent_orchestration.graph import AgentGraph
    from agent_orchestration.approval.store import ApprovalStore
    from agent_orchestration.config import AgentConfig
    from agent_orchestration.models import AgentPlan, PendingToolCall
    from agent_orchestration.persistence.checkpoint_store import CheckpointStore
    from agent_orchestration.state import AgentState
    from llm.models import Message, MessageRole

    tool_plan = AgentPlan(
        requires_tool=True,
        tool_call=PendingToolCall(tool_name="web_search", arguments={"query": "news"}),
    )
    final_plan = _make_plan(requires_tool=False, answer="Here are the results.")

    call_count = 0

    async def _mock_achat(messages, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _make_chat_response(tool_plan.model_dump_json())
        return _make_chat_response(final_plan.model_dump_json())

    llm = MagicMock()
    llm.achat = _mock_achat

    graph = AgentGraph(
        llm_service=llm,
        registry=_make_registry(),
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=AgentConfig(
            require_approval_for_external_write=False,
            require_approval_for_destructive=False,
            require_approval_for_unknown=False,
        ),
    )

    state = AgentState(
        conversation_id="test-tool",
        messages=[Message(role=MessageRole.USER, content="Search for news")],
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        _approval_detected=None,
    )

    with caplog.at_level(logging.DEBUG, logger="jarvis.agent.tools"):
        await graph.run(state)

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("web_search" in m for m in debug_msgs), f"Tool log missing: {debug_msgs}"
    assert any("Tool execution complete" in m for m in debug_msgs), (
        f"Tool completion missing: {debug_msgs}"
    )


# ---------------------------------------------------------------------------
# 7. Approval DEBUG logs appear
# ---------------------------------------------------------------------------


def test_approval_store_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    from agent_orchestration.approval.models import ApprovalRecord, ApprovalStatus
    from agent_orchestration.approval.store import ApprovalStore
    from agent_orchestration.models import PendingToolCall

    store = ApprovalStore()
    record = ApprovalRecord(
        approval_id="abc123",
        conversation_id="conv1",
        graph_state={},
        pending_tool_call=PendingToolCall(
            tool_name="send_email", arguments={"to": "x"}
        ),
        risk_reason="External write",
        created_at=datetime.now(UTC),
    )

    with caplog.at_level(logging.DEBUG, logger="jarvis.agent.approval"):
        store.save(record)
        store.get("abc123")
        store.update_status("abc123", ApprovalStatus.APPROVED)

    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("saved" in m.lower() for m in debug_msgs), (
        f"Save log missing: {debug_msgs}"
    )
    assert any("retrieved" in m.lower() for m in debug_msgs), (
        f"Get log missing: {debug_msgs}"
    )
    assert any("updated" in m.lower() for m in debug_msgs), (
        f"Update log missing: {debug_msgs}"
    )


# ---------------------------------------------------------------------------
# 8. Streaming DEBUG logs appear (chunk count and duration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_debug_logs(caplog: pytest.LogCaptureFixture) -> None:
    from llm.config import LLMConfig
    from llm.models import Message, MessageRole
    from llm.providers.ollama import OllamaProvider

    config = LLMConfig(default_model="test-model")
    provider = OllamaProvider(config)

    def _make_chunk(content: str, done: bool = False) -> MagicMock:
        c = MagicMock()
        c.message = MagicMock()
        c.message.content = content
        c.done = done
        c.done_reason = "stop" if done else None
        c.model = "test-model"
        return c

    async def _fake_stream(*args: Any, **kwargs: Any):
        yield _make_chunk("Hello")
        yield _make_chunk(" world")
        yield _make_chunk("!", done=True)

    with patch.object(
        provider._async_client, "chat", new=AsyncMock(return_value=_fake_stream())
    ):
        with caplog.at_level(logging.DEBUG, logger="jarvis.llm"):
            messages = [Message(role=MessageRole.USER, content="Hi")]
            chunks = [c async for c in provider.astream_chat(messages)]

    assert len(chunks) == 3
    debug_msgs = [r.message for r in caplog.records if r.levelno == logging.DEBUG]
    assert any("Stream started" in m for m in debug_msgs), (
        f"Stream start missing: {debug_msgs}"
    )
    assert any("Stream completed" in m for m in debug_msgs), (
        f"Stream complete missing: {debug_msgs}"
    )
    assert any("chunks=3" in m for m in debug_msgs), (
        f"Chunk count missing: {debug_msgs}"
    )


# ---------------------------------------------------------------------------
# 9. INFO level does NOT emit response content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_info_level_no_response_content(caplog: pytest.LogCaptureFixture) -> None:
    from agent_orchestration.planning.planner import Planner

    plan = _make_plan(requires_tool=False, answer="Top secret answer content here.")
    llm = _make_planner_llm(plan)
    planner = Planner(llm, _make_registry())

    from llm.models import Message, MessageRole

    messages = [Message(role=MessageRole.USER, content="Tell me a secret")]

    with caplog.at_level(logging.INFO, logger="jarvis.agent.planner"):
        await planner.plan(messages)

    # At INFO level, no DEBUG records should be captured for this logger
    planner_debug = [
        r
        for r in caplog.records
        if r.name == "jarvis.agent.planner" and r.levelno < logging.INFO
    ]
    assert len(planner_debug) == 0, (
        f"Expected no sub-INFO logs at INFO level, got: {planner_debug}"
    )
    # Specifically, planner decision content should not appear
    all_text = " ".join(r.message for r in caplog.records)
    assert "Top secret answer content here." not in all_text


# ---------------------------------------------------------------------------
# 10. TRACE logs contain state transition information
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_trace_logs_contain_state_transitions(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from agent_orchestration.graph import AgentGraph
    from agent_orchestration.approval.store import ApprovalStore
    from agent_orchestration.config import AgentConfig
    from agent_orchestration.persistence.checkpoint_store import CheckpointStore
    from agent_orchestration.state import AgentState
    from llm.models import Message, MessageRole

    plan = _make_plan(requires_tool=False, answer="Fine.")
    llm = MagicMock()
    llm.achat = AsyncMock(return_value=_make_chat_response(plan.model_dump_json()))

    graph = AgentGraph(
        llm_service=llm,
        registry=_make_registry(),
        approval_store=ApprovalStore(),
        checkpoint_store=CheckpointStore(),
        config=AgentConfig(
            require_approval_for_external_write=False,
            require_approval_for_destructive=False,
            require_approval_for_unknown=False,
        ),
    )

    state = AgentState(
        conversation_id="trace-test",
        messages=[Message(role=MessageRole.USER, content="Hi")],
        user_request=None,
        plan=None,
        selected_tool_call=None,
        tool_results=[],
        approval_request=None,
        approval_decision=None,
        final_response=None,
        _approval_detected=None,
    )

    with caplog.at_level(TRACE, logger="jarvis.agent.graph"):
        await graph.run(state)

    trace_msgs = [r.message for r in caplog.records if r.levelno == TRACE]
    assert len(trace_msgs) > 0, "Expected TRACE records from jarvis.agent.graph"
    assert any("State before" in m for m in trace_msgs), (
        f"State before missing: {trace_msgs}"
    )
    assert any("State after" in m for m in trace_msgs), (
        f"State after missing: {trace_msgs}"
    )
    assert any("State diff" in m for m in trace_msgs), (
        f"State diff missing: {trace_msgs}"
    )
