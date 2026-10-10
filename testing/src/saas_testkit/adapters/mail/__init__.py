"""MailHog inbox. The integration stack publishes the API on :8026."""

from typing import cast

import httpx
from pydantic import BaseModel, ConfigDict, Field


class MailMessage:
    """One captured message. `body` is the raw MIME body."""

    __slots__ = ("body", "subject")

    def __init__(self, *, subject: str, body: str) -> None:
        self.subject = subject
        self.body = body


class MailHogInbox:
    def __init__(self, base_url: str) -> None:
        self._base = base_url.rstrip("/")

    async def containing(self, text: str) -> tuple[MailMessage, ...]:
        """Messages whose subject or body contains `text`."""
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(f"{self._base}/api/v2/messages")
        response.raise_for_status()
        listing = _Messages.model_validate(cast(object, response.json()))
        found: list[MailMessage] = []
        for item in listing.items:
            subject = item.content.headers.subject[0] if item.content.headers.subject else ""
            body = item.content.body
            if text in subject or text in body:
                found.append(MailMessage(subject=subject, body=body))
        return tuple(found)


class _Headers(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    subject: list[str] = Field(default_factory=list, alias="Subject")


class _Content(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    headers: _Headers = Field(default_factory=_Headers, alias="Headers")
    body: str = Field(default="", alias="Body")


class _Item(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    content: _Content = Field(default_factory=_Content, alias="Content")


def _no_items() -> list[_Item]:
    return []


class _Messages(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[_Item] = Field(default_factory=_no_items)
