"""Message-queue task and result schemas.

These schemas define the canonical payloads exchanged between services
via Redis queues, SQS, or any other message broker.  They are designed
for reliable JSON serialisation with timezone-aware timestamps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

__all__ = [
    "ScrapeRequest",
    "ScrapeResult",
    "AuditTask",
    "AuditResult",
    "NotificationTask",
]


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(timezone.utc)


class ScrapeRequest(BaseModel):
    """Task submitted to the web-scraping worker."""

    job_id: str = Field(..., description="Unique job identifier (UUID).")
    url: str = Field(..., description="URL to scrape.")
    user_id: str = Field(..., description="Requesting user's ID.")
    priority: int = Field(
        default=0,
        ge=0,
        description="Priority level — higher values are processed first.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        description="Timestamp when the task was created.",
    )


class ScrapeResult(BaseModel):
    """Result returned by the web-scraping worker."""

    job_id: str = Field(..., description="Matches the originating ScrapeRequest.")
    url: str = Field(..., description="The URL that was scraped.")
    s3_key: str | None = Field(
        default=None,
        description="S3 object key where the scraped HTML is stored.",
    )
    html_content: str | None = Field(
        default=None,
        description="Inline HTML content (used for small pages or local dev).",
    )
    status: Literal["success", "error"] = Field(
        ..., description="Outcome of the scraping attempt."
    )
    error_message: str | None = Field(
        default=None,
        description="Error details when status is 'error'.",
    )
    scraped_at: datetime = Field(
        default_factory=_utcnow,
        description="Timestamp when scraping completed.",
    )


class AuditTask(BaseModel):
    """Task submitted to the accessibility-audit worker."""

    job_id: str = Field(..., description="Unique job identifier (UUID).")
    user_id: str = Field(..., description="Requesting user's ID.")
    input_type: Literal["url", "code"] = Field(
        ..., description="Whether the input is a URL or raw code."
    )
    input_content: str = Field(
        ..., description="The URL or code to audit."
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        description="Timestamp when the task was created.",
    )


class AuditResult(BaseModel):
    """Result returned by the accessibility-audit worker."""

    job_id: str = Field(..., description="Matches the originating AuditTask.")
    audit_id: str = Field(
        ..., description="ID of the created audit record in the database."
    )
    status: Literal["success", "error"] = Field(
        ..., description="Outcome of the audit."
    )
    error_message: str | None = Field(
        default=None,
        description="Error details when status is 'error'.",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        description="Timestamp when the result was produced.",
    )


class NotificationTask(BaseModel):
    """Task dispatched to the notification service."""

    user_id: str = Field(..., description="Target user's ID.")
    notification_type: Literal["audit_complete", "error"] = Field(
        ..., description="Type of notification to send."
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary notification data (audit_id, message, etc.).",
    )
    created_at: datetime = Field(
        default_factory=_utcnow,
        description="Timestamp when the notification was created.",
    )
