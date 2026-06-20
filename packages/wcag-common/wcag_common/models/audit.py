"""WCAG accessibility audit schemas.

Covers the request/response cycle for running an accessibility audit
against a URL or raw HTML/code snippet, as well as the structured
violation and score representations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ViolationSchema",
    "ScoreSchema",
    "AuditRequest",
    "AuditResponse",
]


class ViolationSchema(BaseModel):
    """A single WCAG criterion violation found during an audit."""

    criterion_id: str = Field(
        ...,
        description="WCAG criterion identifier, e.g. '1.1.1'.",
        examples=["1.1.1"],
    )
    title: str = Field(
        ...,
        description="Human-readable criterion title.",
        examples=["Non-text Content"],
    )
    level: Literal["A", "AA", "AAA"] = Field(
        ..., description="WCAG conformance level."
    )
    issue: str = Field(..., description="Description of the violation.")
    element: str | None = Field(
        default=None,
        description="The HTML element that triggered the violation.",
    )
    fix: str | None = Field(
        default=None,
        description="Suggested remediation.",
    )
    explanation: str | None = Field(
        default=None,
        description="Detailed explanation of why this is a violation.",
    )

    model_config = ConfigDict(from_attributes=True)


class ScoreSchema(BaseModel):
    """Conformance score breakdown by WCAG level."""

    A: int = Field(default=0, ge=0, description="Level A violation count.")
    AA: int = Field(default=0, ge=0, description="Level AA violation count.")
    AAA: int = Field(default=0, ge=0, description="Level AAA violation count.")
    total: int = Field(default=0, ge=0, description="Total violation count.")


class AuditRequest(BaseModel):
    """Payload sent by the client to initiate an accessibility audit."""

    input: str = Field(
        ...,
        description="A URL to audit or raw HTML/code snippet.",
    )
    session_id: str | None = Field(
        default=None,
        description="Optional session identifier to group related audits.",
    )


class AuditResponse(BaseModel):
    """Full audit result returned to the client."""

    id: str = Field(..., description="Unique audit identifier (UUID).")
    input_type: Literal["url", "code"] = Field(
        ..., description="Whether the input was a URL or raw code."
    )
    input_content: str = Field(
        ..., description="The original input that was audited."
    )
    summary: str = Field(
        ..., description="Human-readable audit summary."
    )
    score: ScoreSchema = Field(
        ..., description="Violation counts per WCAG level."
    )
    violations: list[ViolationSchema] = Field(
        default_factory=list,
        description="Individual violations found.",
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
