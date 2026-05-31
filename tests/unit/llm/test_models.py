import pytest
from pydantic import ValidationError

from llm.models import ChatResponse, Message, MessageRole, ToolCall, ToolDefinition


class TestMessage:
    def test_valid_user_message(self):
        msg = Message(role=MessageRole.USER, content="Hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello"

    def test_valid_system_message(self):
        msg = Message(role=MessageRole.SYSTEM, content="You are an assistant.")
        assert msg.role == MessageRole.SYSTEM

    def test_valid_assistant_message(self):
        msg = Message(role=MessageRole.ASSISTANT, content="Hi there!")
        assert msg.role == MessageRole.ASSISTANT

    def test_valid_tool_message(self):
        msg = Message(role=MessageRole.TOOL, content='{"result": 42}')
        assert msg.role == MessageRole.TOOL

    def test_invalid_role_raises(self):
        with pytest.raises(ValidationError):
            Message(role="invalid_role", content="Hello")

    def test_missing_content_raises(self):
        with pytest.raises(ValidationError):
            Message(role=MessageRole.USER)


class TestToolDefinition:
    def test_valid_tool(self):
        tool = ToolDefinition(
            name="search_docs",
            description="Search internal documentation",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        assert tool.name == "search_docs"
        assert tool.description == "Search internal documentation"
        assert "properties" in tool.parameters

    def test_default_empty_parameters(self):
        tool = ToolDefinition(name="noop", description="Does nothing")
        assert tool.parameters == {}

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ToolDefinition(description="Missing name")

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            ToolDefinition(name="tool_without_desc")


class TestToolCall:
    def test_valid_tool_call(self):
        tc = ToolCall(id="abc123", name="search_docs", arguments={"query": "hello"})
        assert tc.id == "abc123"
        assert tc.name == "search_docs"
        assert tc.arguments == {"query": "hello"}

    def test_default_empty_arguments(self):
        tc = ToolCall(id="x", name="noop")
        assert tc.arguments == {}

    def test_missing_id_raises(self):
        with pytest.raises(ValidationError):
            ToolCall(name="tool")

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            ToolCall(id="x")


class TestChatResponse:
    def test_text_response(self):
        resp = ChatResponse(content="Hello!", finish_reason="stop")
        assert resp.content == "Hello!"
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"

    def test_tool_call_response(self):
        tc = ToolCall(id="1", name="search_docs", arguments={"query": "q"})
        resp = ChatResponse(tool_calls=[tc], finish_reason="tool_calls")
        assert resp.content is None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "search_docs"

    def test_defaults(self):
        resp = ChatResponse()
        assert resp.content is None
        assert resp.tool_calls == []
        assert resp.finish_reason is None
