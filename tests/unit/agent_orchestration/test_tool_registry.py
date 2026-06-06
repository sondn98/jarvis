import pytest

from agent_orchestration.exceptions import ToolNotFoundError
from agent_orchestration.models import ToolResult
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.registry import ToolRegistry
from agent_orchestration.tools.risk import ToolRiskLevel
from pydantic import BaseModel


class _FakeArgs(BaseModel):
    value: str


class _FakeTool(BaseTool):
    name = "fake_tool"
    description = "A fake tool."
    risk_level = ToolRiskLevel.SAFE_READ_ONLY
    args_schema = _FakeArgs

    async def arun(self, arguments):
        return ToolResult(
            tool_name=self.name, arguments=arguments, output="ok", success=True
        )


def test_register_and_get():
    registry = ToolRegistry()
    tool = _FakeTool()
    registry.register(tool)
    assert registry.get("fake_tool") is tool


def test_list_tools():
    registry = ToolRegistry()
    tool = _FakeTool()
    registry.register(tool)
    assert tool in registry.list_tools()


def test_get_unknown_raises():
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError):
        registry.get("does_not_exist")
