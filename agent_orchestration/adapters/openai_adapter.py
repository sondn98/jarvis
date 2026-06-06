from time import time
from uuid import uuid4

from agent_orchestration.models import AgentResponse
from api_server.schemas.openai import (
    ChatCompletionChoice,
    ChatCompletionMessage,
    ChatCompletionResponse,
)


def agent_response_to_openai(
    response: AgentResponse, model: str
) -> ChatCompletionResponse:
    """Convert an AgentResponse to an OpenAI-compatible ChatCompletionResponse."""
    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid4().hex}",
        object="chat.completion",
        created=int(time()),
        model=model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content=response.content,
                ),
                finish_reason="stop",
            )
        ],
    )
