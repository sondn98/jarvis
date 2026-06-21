"""Stub backend implementations for the agent tools.

These return empty results or ``not_configured`` placeholders so the agent graph
can be exercised end-to-end without real Web/Gmail/Calendar integrations. They
are the default backend set (selected via ``AgentConfig.agent_backend``); real
backends are a separate feature.
"""

from agent_orchestration.tools.backends import (
    CalendarDeleteResult,
    CalendarEvent,
    CalendarEventCreate,
    CalendarEventUpdate,
    GmailMessage,
    GmailMessageSummary,
    GmailSendResult,
    WebFetchResult,
    WebSearchResult,
)


class StubWebSearchBackend:
    async def search(self, query: str, max_results: int = 5) -> list[WebSearchResult]:
        return []


class StubWebFetchBackend:
    async def fetch(self, url: str) -> WebFetchResult:
        return WebFetchResult(
            url=url, content="(web_fetch not configured)", status_code=200
        )


class StubGmailBackend:
    async def search_messages(
        self, query: str, max_results: int = 10
    ) -> list[GmailMessageSummary]:
        return []

    async def read_message(self, message_id: str) -> GmailMessage:
        return GmailMessage(
            message_id=message_id, subject="", sender="", body="", date=""
        )

    async def send_email(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> GmailSendResult:
        return GmailSendResult(message_id="stub", status="not_configured")


class StubCalendarBackend:
    async def search_events(
        self,
        query: str | None = None,
        time_min: str | None = None,
        time_max: str | None = None,
    ) -> list[CalendarEvent]:
        return []

    async def create_event(self, payload: CalendarEventCreate) -> CalendarEvent:
        return CalendarEvent(
            event_id="stub",
            title=payload.title,
            start=payload.start,
            end=payload.end,
        )

    async def update_event(
        self, event_id: str, payload: CalendarEventUpdate
    ) -> CalendarEvent:
        return CalendarEvent(
            event_id=event_id,
            title=payload.title or "",
            start=payload.start or "",
            end=payload.end or "",
        )

    async def delete_event(self, event_id: str) -> CalendarDeleteResult:
        return CalendarDeleteResult(event_id=event_id, status="not_configured")
