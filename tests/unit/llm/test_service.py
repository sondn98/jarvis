from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel

from llm.config import LLMConfig
from llm.models import ChatResponse, Message, MessageRole, ToolCall
from llm.service import LLMService


@pytest.fixture
def config():
    return LLMConfig(default_model="llama3.2")


@pytest.fixture
def mock_provider():
    return MagicMock()


@pytest.fixture
def service(config, mock_provider):
    return LLMService(config, provider=mock_provider)


class TestChat:
    def test_chat_returns_response(self, service, mock_provider, user_message):
        expected = ChatResponse(content="Hi!", finish_reason="stop")
        mock_provider.chat.return_value = expected

        result = service.chat([user_message])

        mock_provider.chat.assert_called_once_with(
            [user_message], tools=None, response_model=None
        )
        assert result.content == "Hi!"

    def test_chat_with_tools(self, service, mock_provider, user_message, search_tool):
        expected = ChatResponse(
            tool_calls=[
                ToolCall(id="1", name="search_docs", arguments={"query": "test"})
            ],
            finish_reason="tool_calls",
        )
        mock_provider.chat.return_value = expected

        result = service.chat([user_message], tools=[search_tool])

        mock_provider.chat.assert_called_once_with(
            [user_message], tools=[search_tool], response_model=None
        )
        assert len(result.tool_calls) == 1

    def test_chat_with_response_model(self, service, mock_provider, user_message):
        class MyModel(BaseModel):
            answer: str

        expected = ChatResponse(content='{"answer": "42"}', finish_reason="stop")
        mock_provider.chat.return_value = expected

        result = service.chat([user_message], response_model=MyModel)

        mock_provider.chat.assert_called_once_with(
            [user_message], tools=None, response_model=MyModel
        )
        assert result.content == '{"answer": "42"}'


class TestAchat:
    @pytest.mark.asyncio
    async def test_achat_returns_response(self, service, mock_provider, user_message):
        expected = ChatResponse(content="Async hello!", finish_reason="stop")
        mock_provider.achat = AsyncMock(return_value=expected)

        result = await service.achat([user_message])

        mock_provider.achat.assert_called_once_with(
            [user_message], tools=None, response_model=None
        )
        assert result.content == "Async hello!"


class TestGenerate:
    def test_generate_wraps_prompt(self, service, mock_provider):
        expected = ChatResponse(content="Answer", finish_reason="stop")
        mock_provider.chat.return_value = expected

        result = service.generate("What is 2+2?")

        call_args = mock_provider.chat.call_args
        messages: list[Message] = call_args[0][0]
        assert len(messages) == 1
        assert messages[0].role == MessageRole.USER
        assert messages[0].content == "What is 2+2?"
        assert result.content == "Answer"

    @pytest.mark.asyncio
    async def test_agenerate_wraps_prompt(self, service, mock_provider):
        expected = ChatResponse(content="Async answer", finish_reason="stop")
        mock_provider.achat = AsyncMock(return_value=expected)

        result = await service.agenerate("What is the capital of France?")

        call_args = mock_provider.achat.call_args
        messages: list[Message] = call_args[0][0]
        assert messages[0].role == MessageRole.USER
        assert messages[0].content == "What is the capital of France?"
        assert result.content == "Async answer"
