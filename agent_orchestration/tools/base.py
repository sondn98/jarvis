from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from agent_orchestration.models import ToolResult
from agent_orchestration.tools.risk import ToolRiskLevel


class BaseTool(ABC):
    name: str
    description: str
    risk_level: ToolRiskLevel
    args_schema: type[BaseModel]

    @abstractmethod
    async def arun(self, arguments: dict[str, Any]) -> ToolResult: ...
