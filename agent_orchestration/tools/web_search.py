import json
from typing import Any

from pydantic import BaseModel

from agent_orchestration.exceptions import ToolExecutionError
from agent_orchestration.models import ToolResult
from agent_orchestration.tools.backends import WebSearchBackend
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.risk import ToolRiskLevel


class _WebSearchArgs(BaseModel):
    query: str
    max_results: int = 5


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web for information on a given query."
    risk_level = ToolRiskLevel.SAFE_READ_ONLY
    args_schema = _WebSearchArgs

    def __init__(self, backend: WebSearchBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _WebSearchArgs(**arguments)
        try:
            results = await self._backend.search(
                args.query, max_results=args.max_results
            )
            output = json.dumps([r.model_dump() for r in results], ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"web_search failed: {exc}") from exc
