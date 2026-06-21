"""Direct tests for the agent tool implementations (arun success + failure).

The graph tests use mock tools, so these cover the real arun paths: argument
parsing, JSON serialization, and the ToolExecutionError wrapping on failure.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_orchestration.exceptions import ToolExecutionError
from agent_orchestration.tools.backends import (
    CalendarDeleteResult,
    CalendarEvent,
    GmailMessage,
    GmailMessageSummary,
    GmailSendResult,
    WebFetchResult,
    WebSearchResult,
)
from agent_orchestration.tools.calendar import (
    CalendarCreateEventTool,
    CalendarDeleteEventTool,
    CalendarSearchEventsTool,
    CalendarUpdateEventTool,
)
from agent_orchestration.tools.gmail import (
    GmailReadMessageTool,
    GmailSearchMessagesTool,
    GmailSendEmailTool,
)
from agent_orchestration.tools.web_fetch import WebFetchTool
from agent_orchestration.tools.web_search import WebSearchTool


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------


async def test_web_search_success():
    backend = MagicMock()
    backend.search = AsyncMock(
        return_value=[WebSearchResult(title="t", url="u", snippet="s")]
    )
    result = await WebSearchTool(backend).arun({"query": "ai", "max_results": 3})
    assert result.success is True
    assert result.error is None
    assert json.loads(result.output)[0]["url"] == "u"
    backend.search.assert_awaited_once_with("ai", max_results=3)


async def test_web_fetch_success():
    backend = MagicMock()
    backend.fetch = AsyncMock(
        return_value=WebFetchResult(url="u", content="hello", status_code=200)
    )
    result = await WebFetchTool(backend).arun({"url": "u"})
    assert result.success is True
    assert result.output == "hello"


async def test_gmail_search_success():
    backend = MagicMock()
    backend.search_messages = AsyncMock(
        return_value=[
            GmailMessageSummary(
                message_id="1", subject="hi", sender="a@b.com", snippet="x", date="d"
            )
        ]
    )
    result = await GmailSearchMessagesTool(backend).arun({"query": "invoice"})
    assert result.success is True
    assert json.loads(result.output)[0]["message_id"] == "1"


async def test_gmail_read_success():
    backend = MagicMock()
    backend.read_message = AsyncMock(
        return_value=GmailMessage(
            message_id="1", subject="s", sender="a@b.com", body="body", date="d"
        )
    )
    result = await GmailReadMessageTool(backend).arun({"message_id": "1"})
    assert result.success is True
    assert json.loads(result.output)["body"] == "body"


async def test_gmail_send_success():
    backend = MagicMock()
    backend.send_email = AsyncMock(
        return_value=GmailSendResult(message_id="m1", status="sent")
    )
    result = await GmailSendEmailTool(backend).arun(
        {"to": "a@b.com", "subject": "s", "body": "b"}
    )
    assert result.success is True
    assert json.loads(result.output)["status"] == "sent"
    backend.send_email.assert_awaited_once_with(
        to="a@b.com", subject="s", body="b", cc=None
    )


async def test_calendar_search_success():
    backend = MagicMock()
    backend.search_events = AsyncMock(
        return_value=[CalendarEvent(event_id="e1", title="t", start="s", end="e")]
    )
    result = await CalendarSearchEventsTool(backend).arun({"query": "meeting"})
    assert result.success is True
    assert json.loads(result.output)[0]["event_id"] == "e1"


async def test_calendar_create_success():
    backend = MagicMock()
    backend.create_event = AsyncMock(
        return_value=CalendarEvent(event_id="e1", title="t", start="s", end="e")
    )
    result = await CalendarCreateEventTool(backend).arun(
        {"title": "t", "start": "s", "end": "e"}
    )
    assert result.success is True
    assert json.loads(result.output)["event_id"] == "e1"


async def test_calendar_update_success():
    backend = MagicMock()
    backend.update_event = AsyncMock(
        return_value=CalendarEvent(event_id="e1", title="t2", start="s", end="e")
    )
    result = await CalendarUpdateEventTool(backend).arun(
        {"event_id": "e1", "title": "t2"}
    )
    assert result.success is True
    assert json.loads(result.output)["title"] == "t2"


async def test_calendar_delete_success():
    backend = MagicMock()
    backend.delete_event = AsyncMock(
        return_value=CalendarDeleteResult(event_id="e1", status="deleted")
    )
    result = await CalendarDeleteEventTool(backend).arun({"event_id": "e1"})
    assert result.success is True
    assert json.loads(result.output)["status"] == "deleted"


# ---------------------------------------------------------------------------
# Failure paths — every tool wraps backend errors in ToolExecutionError
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_factory, method, arguments",
    [
        (WebSearchTool, "search", {"query": "ai"}),
        (WebFetchTool, "fetch", {"url": "u"}),
        (GmailSearchMessagesTool, "search_messages", {"query": "q"}),
        (GmailReadMessageTool, "read_message", {"message_id": "1"}),
        (
            GmailSendEmailTool,
            "send_email",
            {"to": "a@b.com", "subject": "s", "body": "b"},
        ),
        (CalendarSearchEventsTool, "search_events", {"query": "q"}),
        (
            CalendarCreateEventTool,
            "create_event",
            {"title": "t", "start": "s", "end": "e"},
        ),
        (CalendarUpdateEventTool, "update_event", {"event_id": "e1", "title": "t"}),
        (CalendarDeleteEventTool, "delete_event", {"event_id": "e1"}),
    ],
)
async def test_tool_backend_failure_raises_tool_execution_error(
    tool_factory, method, arguments
):
    backend = MagicMock()
    setattr(backend, method, AsyncMock(side_effect=RuntimeError("boom")))
    with pytest.raises(ToolExecutionError):
        await tool_factory(backend).arun(arguments)
