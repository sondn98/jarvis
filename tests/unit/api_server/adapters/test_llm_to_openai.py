import json


from api_server.adapters.llm_to_openai import (
    convert_chat_response,
    convert_finish_reason,
    convert_tool_call,
    convert_tool_calls,
)
from llm.models import ChatResponse, ToolCall


class TestConvertFinishReason:
    def test_stop(self):
        assert convert_finish_reason("stop") == "stop"

    def test_length(self):
        assert convert_finish_reason("length") == "length"

    def test_tool_calls(self):
        assert convert_finish_reason("tool_calls") == "tool_calls"

    def test_tool_call_singular_maps_to_tool_calls(self):
        assert convert_finish_reason("tool_call") == "tool_calls"

    def test_none_maps_to_stop(self):
        assert convert_finish_reason(None) == "stop"

    def test_unknown_passthrough(self):
        assert convert_finish_reason("some_custom_reason") == "some_custom_reason"

    def test_case_insensitive(self):
        assert convert_finish_reason("STOP") == "stop"


class TestConvertToolCall:
    def test_basic_tool_call(self):
        tc = ToolCall(id="call_1", name="search", arguments={"query": "hello"})
        result = convert_tool_call(tc)
        assert result.id == "call_1"
        assert result.type == "function"
        assert result.function.name == "search"
        assert json.loads(result.function.arguments) == {"query": "hello"}

    def test_arguments_serialized_as_json(self):
        tc = ToolCall(id="x", name="fn", arguments={"a": 1, "b": [1, 2]})
        result = convert_tool_call(tc)
        parsed = json.loads(result.function.arguments)
        assert parsed == {"a": 1, "b": [1, 2]}

    def test_empty_arguments(self):
        tc = ToolCall(id="x", name="fn", arguments={})
        result = convert_tool_call(tc)
        assert result.function.arguments == "{}"


class TestConvertToolCalls:
    def test_empty_list(self):
        assert convert_tool_calls([]) == []

    def test_multiple_calls(self):
        calls = [
            ToolCall(id="1", name="a", arguments={}),
            ToolCall(id="2", name="b", arguments={"x": 1}),
        ]
        result = convert_tool_calls(calls)
        assert len(result) == 2
        assert result[0].function.name == "a"
        assert result[1].function.name == "b"


class TestConvertChatResponse:
    def test_text_response(self):
        llm_resp = ChatResponse(content="Hello", finish_reason="stop")
        result = convert_chat_response(llm_resp, model="llama3.2")
        assert result.object == "chat.completion"
        assert result.model == "llama3.2"
        assert len(result.choices) == 1
        choice = result.choices[0]
        assert choice.index == 0
        assert choice.message.role == "assistant"
        assert choice.message.content == "Hello"
        assert choice.finish_reason == "stop"
        assert choice.message.tool_calls is None

    def test_tool_call_response(self):
        llm_resp = ChatResponse(
            tool_calls=[ToolCall(id="c1", name="search", arguments={"q": "x"})],
            finish_reason="tool_calls",
        )
        result = convert_chat_response(llm_resp, model="llama3.2")
        choice = result.choices[0]
        assert choice.finish_reason == "tool_calls"
        assert choice.message.tool_calls is not None
        assert len(choice.message.tool_calls) == 1
        assert choice.message.tool_calls[0].id == "c1"

    def test_request_id_is_used_when_provided(self):
        llm_resp = ChatResponse(content="ok", finish_reason="stop")
        result = convert_chat_response(llm_resp, model="m", request_id="chatcmpl-abc")
        assert result.id == "chatcmpl-abc"

    def test_request_id_is_generated_when_absent(self):
        llm_resp = ChatResponse(content="ok", finish_reason="stop")
        result = convert_chat_response(llm_resp, model="m")
        assert result.id.startswith("chatcmpl-")

    def test_created_is_unix_timestamp(self):
        import time

        before = int(time.time())
        result = convert_chat_response(ChatResponse(content="ok"), model="m")
        after = int(time.time())
        assert before <= result.created <= after
