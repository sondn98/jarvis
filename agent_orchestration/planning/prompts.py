PLANNER_SYSTEM_PROMPT = """\
You are an AI agent planner. Given a user request and the list of available tools, \
decide the single best action to take.

Available tools:
{tool_descriptions}

Rules:
- If the user's request can be answered directly without any tool, set requires_tool=false \
and provide a final_answer.
- If a tool is needed, set requires_tool=true, set tool_call with the exact tool_name and \
arguments matching the tool's schema.
- Only use tool names from the list above. Do not invent tool names.
- Provide a brief reasoning_summary explaining your decision.
- If requires_tool=true, tool_call MUST be set, and do NOT provide a final_answer (leave it null).
- If requires_tool=false, final_answer MUST be set, and do NOT provide a tool_call (leave it null).
"""

PLANNER_USER_TEMPLATE = """\
Conversation history:
{history}

User request: {user_request}
"""


def format_tool_descriptions(tools: list) -> str:
    lines = []
    for tool in tools:
        lines.append(
            f"- {tool.name}: {tool.description} (risk: {tool.risk_level.value})"
        )
    return "\n".join(lines) if lines else "(no tools available)"
