from agent_orchestration.adapters.openai_adapter import agent_response_to_openai
from agent_orchestration.models import AgentResponse


def test_agent_response_to_openai_basic():
    resp = agent_response_to_openai(AgentResponse(content="hello"), "qwen3:1.7b")
    assert resp.object == "chat.completion"
    assert resp.model == "qwen3:1.7b"
    assert resp.id.startswith("chatcmpl-")
    assert len(resp.choices) == 1
    choice = resp.choices[0]
    assert choice.index == 0
    assert choice.finish_reason == "stop"
    assert choice.message.role == "assistant"
    assert choice.message.content == "hello"


def test_agent_response_to_openai_preserves_approval_message():
    resp = agent_response_to_openai(
        AgentResponse(content="APPROVE abc123 to continue", requires_approval=True),
        "model-x",
    )
    assert resp.choices[0].message.content == "APPROVE abc123 to continue"
