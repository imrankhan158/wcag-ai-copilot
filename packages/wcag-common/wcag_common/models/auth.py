"""Authentication and user schemas.

These schemas are the canonical wire-format definitions for user
registration, login responses, and JWT token payloads across every
microservice in the WCAG AI Copilot platform.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

__all__ = [
    "UserCreate",
    "UserResponse",
    "TokenResponse",
    "TokenPayload",
]


class UserCreate(BaseModel):
    """Schema for user registration requests."""

    email: EmailStr = Field(..., description="User email address.")
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Plain-text password (will be hashed server-side).",
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"email": "user@example.com", "password": "secureP@ss1"}
            ]
        },
    )


class UserResponse(BaseModel):
    """Public user representation returned by API endpoints."""

    id: str = Field(..., description="Unique user identifier (UUID).")
    email: EmailStr
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    """Response returned after a successful login or token refresh."""

    access_token: str = Field(..., description="JWT access token.")
    refresh_token: str | None = Field(
        default=None,
        description="JWT refresh token (included on login, omitted on refresh).",
    )
    token_type: str = Field(default="bearer", description="OAuth2 token type.")
    user: UserResponse = Field(..., description="Authenticated user details.")


class TokenPayload(BaseModel):
    """Decoded JWT token payload.

    Used internally to type-check the claims extracted from a JWT.
    """

    sub: str = Field(..., description="Subject — the user ID.")
    exp: datetime = Field(..., description="Expiration timestamp.")
    iat: datetime = Field(..., description="Issued-at timestamp.")
    token_type: Literal["access", "refresh"] = Field(
        ..., description="Discriminator for access vs. refresh tokens."
    )
