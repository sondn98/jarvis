from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class GmailMessageSummary(BaseModel):
    message_id: str
    subject: str
    sender: str
    snippet: str
    date: str


class GmailMessage(BaseModel):
    message_id: str
    subject: str
    sender: str
    body: str
    date: str


class GmailSendResult(BaseModel):
    message_id: str
    status: str


class CalendarEvent(BaseModel):
    event_id: str
    title: str
    start: str
    end: str
    description: str | None = None


class CalendarEventCreate(BaseModel):
    title: str
    start: str
    end: str
    description: str | None = None


class CalendarEventUpdate(BaseModel):
    title: str | None = None
    start: str | None = None
    end: str | None = None
    description: str | None = None


class CalendarDeleteResult(BaseModel):
    event_id: str
    status: str


@runtime_checkable
class WebSearchBackend(Protocol):
    async def search(
        self, query: str, max_results: int = 5
    ) -> list[WebSearchResult]: ...


@runtime_checkable
class GmailBackend(Protocol):
    async def search_messages(
        self, query: str, max_results: int = 10
    ) -> list[GmailMessageSummary]: ...

    async def read_message(self, message_id: str) -> GmailMessage: ...

    async def send_email(
        self, to: str, subject: str, body: str, cc: str | None = None
    ) -> GmailSendResult: ...


@runtime_checkable
class CalendarBackend(Protocol):
    async def search_events(
        self,
        query: str | None,
        time_min: str | None,
        time_max: str | None,
    ) -> list[CalendarEvent]: ...

    async def create_event(self, payload: CalendarEventCreate) -> CalendarEvent: ...

    async def update_event(
        self, event_id: str, payload: CalendarEventUpdate
    ) -> CalendarEvent: ...

    async def delete_event(self, event_id: str) -> CalendarDeleteResult: ...
