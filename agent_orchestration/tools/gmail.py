import json
from typing import Any

from pydantic import BaseModel

from agent_orchestration.exceptions import ToolExecutionError
from agent_orchestration.models import ToolResult
from agent_orchestration.tools.backends import GmailBackend
from agent_orchestration.tools.base import BaseTool
from agent_orchestration.tools.risk import ToolRiskLevel


class _SearchArgs(BaseModel):
    query: str
    max_results: int = 10


class _ReadArgs(BaseModel):
    message_id: str


class _SendArgs(BaseModel):
    to: str
    subject: str
    body: str
    cc: str | None = None


class GmailSearchMessagesTool(BaseTool):
    name = "gmail_search_messages"
    description = "Search Gmail messages matching a query."
    risk_level = ToolRiskLevel.SENSITIVE_READ
    args_schema = _SearchArgs

    def __init__(self, backend: GmailBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _SearchArgs(**arguments)
        try:
            results = await self._backend.search_messages(
                args.query, max_results=args.max_results
            )
            output = json.dumps([r.model_dump() for r in results], ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"gmail_search_messages failed: {exc}") from exc


class GmailReadMessageTool(BaseTool):
    name = "gmail_read_message"
    description = "Read the full content of a Gmail message by ID."
    risk_level = ToolRiskLevel.SENSITIVE_READ
    args_schema = _ReadArgs

    def __init__(self, backend: GmailBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _ReadArgs(**arguments)
        try:
            msg = await self._backend.read_message(args.message_id)
            output = json.dumps(msg.model_dump(), ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"gmail_read_message failed: {exc}") from exc


class GmailSendEmailTool(BaseTool):
    name = "gmail_send_email"
    description = "Send an email from the user's Gmail account."
    risk_level = ToolRiskLevel.EXTERNAL_WRITE
    args_schema = _SendArgs

    def __init__(self, backend: GmailBackend) -> None:
        self._backend = backend

    async def arun(self, arguments: dict[str, Any]) -> ToolResult:
        args = _SendArgs(**arguments)
        try:
            result = await self._backend.send_email(
                to=args.to, subject=args.subject, body=args.body, cc=args.cc
            )
            output = json.dumps(result.model_dump(), ensure_ascii=False)
            return ToolResult(
                tool_name=self.name, arguments=arguments, output=output, success=True
            )
        except Exception as exc:
            raise ToolExecutionError(f"gmail_send_email failed: {exc}") from exc
