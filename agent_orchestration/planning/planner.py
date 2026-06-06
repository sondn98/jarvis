from agent_orchestration.exceptions import PlanningError
from agent_orchestration.models import AgentPlan
from agent_orchestration.planning.prompts import (
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_TEMPLATE,
    format_tool_descriptions,
)
from agent_orchestration.tools.registry import ToolRegistry
from llm.models import Message, MessageRole
from llm.service import LLMService


class Planner:
    def __init__(self, llm_service: LLMService, registry: ToolRegistry) -> None:
        self._llm = llm_service
        self._registry = registry

    async def plan(self, messages: list[Message]) -> AgentPlan:
        tools = self._registry.list_tools()
        tool_desc = format_tool_descriptions(tools)

        system_content = PLANNER_SYSTEM_PROMPT.format(tool_descriptions=tool_desc)

        history_lines = []
        user_request = ""
        for msg in messages:
            if msg.role == MessageRole.USER:
                user_request = msg.content
                history_lines.append(f"User: {msg.content}")
            elif msg.role == MessageRole.ASSISTANT:
                history_lines.append(f"Assistant: {msg.content}")

        history = "\n".join(history_lines[:-1]) if len(history_lines) > 1 else "(none)"
        user_content = PLANNER_USER_TEMPLATE.format(
            history=history, user_request=user_request
        )

        llm_messages = [
            Message(role=MessageRole.SYSTEM, content=system_content),
            Message(role=MessageRole.USER, content=user_content),
        ]

        try:
            response = await self._llm.achat(llm_messages, response_model=AgentPlan)
        except Exception as exc:
            raise PlanningError(f"LLM call failed during planning: {exc}") from exc

        if response.content is None:
            raise PlanningError("Planner returned no content.")

        try:
            plan = AgentPlan.model_validate_json(response.content)
        except Exception as exc:
            raise PlanningError(
                f"Planner output failed Pydantic validation: {exc}"
            ) from exc

        if plan.requires_tool and plan.tool_call is None:
            raise PlanningError("Plan requires_tool=True but tool_call is None.")
        if not plan.requires_tool and plan.final_answer is None:
            raise PlanningError("Plan requires_tool=False but final_answer is None.")

        return plan
