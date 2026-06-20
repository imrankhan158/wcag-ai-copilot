"""Chat and conversation schemas.

Used by the Q&A / chat microservice and the API gateway for
conversation CRUD and real-time messaging.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MessageItem",
    "ChatRequest",
    "QARequest",
    "ConversationResponse",
]


class MessageItem(BaseModel):
    """A single message in a conversation."""

    role: Literal["user", "assistant", "system"] = Field(
        ..., description="Who sent the message."
    )
    content: str = Field(..., description="Message body (Markdown supported).")


class ChatRequest(BaseModel):
    """Simple chat/audit request sent from the frontend."""

    input: str = Field(
        ..., description="User's message or question."
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier to resume a conversation.",
    )


class QARequest(BaseModel):
    """Request sent to the WCAG Q&A engine."""

    message: str = Field(
        ..., description="The user's question about WCAG."
    )
    conversation_id: str | None = Field(
        default=None,
        description="Existing conversation ID to continue, or None for new.",
    )
    history: list[MessageItem] = Field(
        default_factory=list,
        description="Prior messages for multi-turn context.",
    )


class ConversationResponse(BaseModel):
    """A full conversation with its messages."""

    id: str = Field(..., description="Conversation UUID.")
    title: str = Field(..., description="Auto-generated or user-set title.")
    created_at: datetime
    messages: list[MessageItem] = Field(
        default_factory=list,
        description="Ordered list of messages in the conversation.",
    )

    model_config = ConfigDict(from_attributes=True)
