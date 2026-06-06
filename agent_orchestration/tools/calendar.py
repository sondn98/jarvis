import json
from typing import Any

from pydantic import BaseModel

from agent_orchestration.exceptions import ToolExecutionError
from agent_orchestration.models import ToolResult
from agent_orchestration.tools.backends import (
    CalendarBackend,
    CalendarEventCreate,
    CalendarEventUpdate,
)
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.risk import ToolRiskLevel


class _SearchArgs(BaseModel):
    query: str | None = None
    time_min: str | None = None
    time_max: str | None = None


class _CreateArgs(BaseModel):
    title: str
    start: str
    end: str
    description: str | None = None


class _UpdateArgs(BaseModel):
    event_id: str
    title: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None


class _DeleteArgs(BaseModel):
    event_id: str


class CalendarSearchEventsTool(BaseTool):
    name = "calendar_search_events"
    description = "Search calendar events by query or time range."
    risk_level = ToolRiskLevel.SENSITIVE_READ
    args_schema = _SearchArgs

    def __init__(self, backend: CalendarBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _SearchArgs(**arguments)
        try:
            events = await self._backend.search_events(
                query=args.query, time_min=args.time_min, time_max=args.time_max
            )
            output = json.dumps([e.model_dump() for e in events], ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"calendar_search_events failed: {exc}") from exc


class CalendarCreateEventTool(BaseTool):
    name = "calendar_create_event"
    description = "Create a new calendar event."
    risk_level = ToolRiskLevel.EXTERNAL_WRITE
    args_schema = _CreateArgs

    def __init__(self, backend: CalendarBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _CreateArgs(**arguments)
        try:
            event = await self._backend.create_event(
                CalendarEventCreate(**args.model_dump())
            )
            output = json.dumps(event.model_dump(), ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"calendar_create_event failed: {exc}") from exc


class CalendarUpdateEventTool(BaseTool):
    name = "calendar_update_event"
    description = "Update an existing calendar event."
    risk_level = ToolRiskLevel.EXTERNAL_WRITE
    args_schema = _UpdateArgs

    def __init__(self, backend: CalendarBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _UpdateArgs(**arguments)
        event_id = args.event_id
        payload = CalendarEventUpdate(
            title=args.title,
            start=args.start,
            end=args.end,
            description=args.description,
        )
        try:
            event = await self._backend.update_event(event_id, payload)
            output = json.dumps(event.model_dump(), ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"calendar_update_event failed: {exc}") from exc


class CalendarDeleteEventTool(BaseTool):
    name = "calendar_delete_event"
    description = "Permanently delete a calendar event."
    risk_level = ToolRiskLevel.DESTRUCTIVE
    args_schema = _DeleteArgs

    def __init__(self, backend: CalendarBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _DeleteArgs(**arguments)
        try:
            result = await self._backend.delete_event(args.event_id)
            output = json.dumps(result.model_dump(), ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"calendar_delete_event failed: {exc}") from exc
