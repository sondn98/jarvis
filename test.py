import asyncio
import ollama as ollama_sdk
from typing import Any

from pydantic import BaseModel
from agent_orchestration.models import AgentPlan
from agent_orchestration.planning.prompts import (
    PLANNER_SYSTEM_PROMPT,
    PLANNER_USER_TEMPLATE,
    format_tool_descriptions,
)
from agent_orchestration.tools.web_search import WebSearchTool
from agent_orchestration.tools.web_fetch import WebFetchTool
from agent_orchestration.tools.gmail import (
    GmailSearchMessagesTool,
    GmailReadMessageTool,
    GmailSendEmailTool,
)
from agent_orchestration.tools.calendar import (
    CalendarSearchEventsTool,
    CalendarCreateEventTool,
    CalendarUpdateEventTool,
    CalendarDeleteEventTool,
)
from unittest.mock import MagicMock


def _build_format(response_model: type[BaseModel] | None) -> dict[str, Any] | None:
    if response_model is None:
        return None
    return response_model.model_json_schema()


# Build tool list exactly as the real planner does
_tools = [
    WebSearchTool(MagicMock()),
    WebFetchTool(MagicMock()),
    GmailSearchMessagesTool(MagicMock()),
    GmailReadMessageTool(MagicMock()),
    GmailSendEmailTool(MagicMock()),
    CalendarSearchEventsTool(MagicMock()),
    CalendarCreateEventTool(MagicMock()),
    CalendarUpdateEventTool(MagicMock()),
    CalendarDeleteEventTool(MagicMock()),
]

SYS_PROMPT = PLANNER_SYSTEM_PROMPT.format(
    tool_descriptions=format_tool_descriptions(_tools)
)

USER_PROMPT = PLANNER_USER_TEMPLATE.format(
    history="(none)",
    user_request="Access and summary this page for me **https://en.wikipedia.org/wiki/X-ray**",
)


async def achat():
    cli = ollama_sdk.AsyncClient(host="http://localhost:11434")
    print("=== Prompts ===")
    print(SYS_PROMPT)
    print(USER_PROMPT)

    raw = await cli.chat(
        model="qwen3:1.7b",
        messages=[
            {"role": "system", "content": SYS_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        tools=None,
        format=_build_format(AgentPlan),
    )

    content = raw.message.content
    print("=== Raw LLM response ===")
    print(content)
    print()

    plan = AgentPlan.model_validate_json(content)
    print("=== Parsed AgentPlan ===")
    print(f"  requires_tool   : {plan.requires_tool}")
    print(f"  tool_call       : {plan.tool_call}")
    print(f"  final_answer    : {plan.final_answer!r}")
    print(f"  reasoning       : {plan.reasoning_summary!r}")
    print()

    # Validate the business-logic constraints the planner enforces
    if plan.requires_tool and plan.tool_call is None:
        print(
            "FAIL — requires_tool=True but tool_call is None (original bug reproduced)"
        )
    elif not plan.requires_tool and plan.final_answer is None:
        print("FAIL — requires_tool=False but final_answer is None")
    else:
        print("PASS — plan is valid")


asyncio.run(achat())
