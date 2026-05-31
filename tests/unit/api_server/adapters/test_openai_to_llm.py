from api_server.adapters.openai_to_llm import (
    build_llm_kwargs,
    convert_message,
    convert_messages,
    convert_role,
    convert_tool,
    convert_tools,
)
from api_server.schemas.openai import (
    ChatCompletionRequest,
    ChatMessage,
    Tool,
    ToolFunction,
)
from llm.models import MessageRole


class TestConvertRole:
    def test_user(self):
        assert convert_role("user") == MessageRole.USER

    def test_assistant(self):
        assert convert_role("assistant") == MessageRole.ASSISTANT

    def test_system(self):
        assert convert_role("system") == MessageRole.SYSTEM

    def test_tool(self):
        assert convert_role("tool") == MessageRole.TOOL

    def test_function_maps_to_tool(self):
        assert convert_role("function") == MessageRole.TOOL

    def test_unknown_role_falls_back_to_user(self):
        assert convert_role("unknown_role") == MessageRole.USER

    def test_case_insensitive(self):
        assert convert_role("USER") == MessageRole.USER
        assert convert_role("ASSISTANT") == MessageRole.ASSISTANT


class TestConvertMessage:
    def test_user_message(self):
        msg = ChatMessage(role="user", content="Hello")
        result = convert_message(msg)
        assert result.role == MessageRole.USER
        assert result.content == "Hello"

    def test_system_message(self):
        msg = ChatMessage(role="system", content="You are helpful.")
        result = convert_message(msg)
        assert result.role == MessageRole.SYSTEM

    def test_none_content_becomes_empty_string(self):
        msg = ChatMessage(role="user", content=None)
        result = convert_message(msg)
        assert result.content == ""

    def test_tool_result_message(self):
        msg = ChatMessage(role="tool", content="result text", tool_call_id="call_1")
        result = convert_message(msg)
        assert result.role == MessageRole.TOOL
        assert result.content == "result text"


class TestConvertMessages:
    def test_converts_list(self):
        msgs = [
            ChatMessage(role="system", content="Sys"),
            ChatMessage(role="user", content="Hi"),
        ]
        result = convert_messages(msgs)
        assert len(result) == 2
        assert result[0].role == MessageRole.SYSTEM
        assert result[1].role == MessageRole.USER

    def test_empty_list(self):
        assert convert_messages([]) == []


class TestConvertTool:
    def test_basic_tool(self):
        tool = Tool(
            type="function",
            function=ToolFunction(
                name="search",
                description="Search the web",
                parameters={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                },
            ),
        )
        result = convert_tool(tool)
        assert result.name == "search"
        assert result.description == "Search the web"
        assert result.parameters == {
            "type": "object",
            "properties": {"query": {"type": "string"}},
        }

    def test_tool_with_no_description(self):
        tool = Tool(
            type="function", function=ToolFunction(name="noop", description=None)
        )
        result = convert_tool(tool)
        assert result.description == ""

    def test_tool_with_no_parameters(self):
        tool = Tool(
            type="function", function=ToolFunction(name="ping", description="Ping")
        )
        result = convert_tool(tool)
        assert result.parameters == {}


class TestConvertTools:
    def test_converts_list(self):
        tools = [
            Tool(type="function", function=ToolFunction(name="a", description="A")),
            Tool(type="function", function=ToolFunction(name="b", description="B")),
        ]
        result = convert_tools(tools)
        assert len(result) == 2
        assert result[0].name == "a"
        assert result[1].name == "b"


class TestBuildLlmKwargs:
    def _make_request(self, **kwargs) -> ChatCompletionRequest:
        return ChatCompletionRequest(
            model=kwargs.pop("model", "llama3.2"),
            messages=[ChatMessage(role="user", content="Hi")],
            **kwargs,
        )

    def test_model_from_request(self):
        req = self._make_request(model="my-model")
        kwargs = build_llm_kwargs(req, default_model=None)
        assert kwargs["model"] == "my-model"

    def test_temperature_included_when_set(self):
        req = self._make_request(temperature=0.5)
        kwargs = build_llm_kwargs(req, default_model=None)
        assert kwargs["temperature"] == 0.5

    def test_top_p_included_when_set(self):
        req = self._make_request(top_p=0.8)
        kwargs = build_llm_kwargs(req, default_model=None)
        assert kwargs["top_p"] == 0.8

    def test_max_tokens_included_when_set(self):
        req = self._make_request(max_tokens=512)
        kwargs = build_llm_kwargs(req, default_model=None)
        assert kwargs["max_tokens"] == 512

    def test_none_params_omitted(self):
        req = self._make_request()
        kwargs = build_llm_kwargs(req, default_model=None)
        assert "temperature" not in kwargs
        assert "top_p" not in kwargs
        assert "max_tokens" not in kwargs
