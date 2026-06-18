from typing import Any

from pydantic import BaseModel

from agent_orchestration.exceptions import ToolExecutionError
from agent_orchestration.models import ToolResult
from agent_orchestration.tools.backends import WebFetchBackend
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.risk import ToolRiskLevel


class _WebFetchArgs(BaseModel):
    url: str


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch the content of a specific URL and return its text."
    risk_level = ToolRiskLevel.SAFE_READ_ONLY
    args_schema = _WebFetchArgs

    def __init__(self, backend: WebFetchBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _WebFetchArgs(**arguments)
        try:
            result = await self._backend.fetch(args.url)
            return ToolResult(
                tool_name=self.name,
                arguments=arguments,
                output=result.content,
                success=True,
            )
        except Exception as exc:
            raise ToolExecutionError(f"web_fetch failed: {exc}") from exc
