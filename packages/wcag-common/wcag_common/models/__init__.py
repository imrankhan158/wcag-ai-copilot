"""Pydantic v2 schemas shared across all WCAG AI Copilot services.

Sub-modules
-----------
- **auth** — User, token, and authentication schemas.
- **audit** — WCAG audit request/response and violation schemas.
- **chat** — Conversation and Q&A schemas.
- **queue** — Message-queue task and result schemas.
"""

from wcag_common.models.auth import (
    TokenPayload,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from wcag_common.models.audit import (
    AuditRequest,
    AuditResponse,
    ScoreSchema,
    ViolationSchema,
)
from wcag_common.models.chat import (
    ChatRequest,
    ConversationResponse,
    MessageItem,
    QARequest,
)
from wcag_common.models.queue import (
    AuditResult,
    AuditTask,
    NotificationTask,
    ScrapeRequest,
    ScrapeResult,
)

__all__ = [
    # auth
    "TokenPayload",
    "TokenResponse",
    "UserCreate",
    "UserResponse",
    # audit
    "AuditRequest",
    "AuditResponse",
    "ScoreSchema",
    "ViolationSchema",
    # chat
    "ChatRequest",
    "ConversationResponse",
    "MessageItem",
    "QARequest",
    # queue
    "AuditResult",
    "AuditTask",
    "NotificationTask",
    "ScrapeRequest",
    "ScrapeResult",
]
