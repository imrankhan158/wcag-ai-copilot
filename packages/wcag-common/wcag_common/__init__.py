"""wcag-common — Shared library for the WCAG AI Copilot microservice platform.

Provides reusable Pydantic schemas, JWT / password auth utilities,
centralised configuration via pydantic-settings, and a pluggable
health-check system for FastAPI services.

Quick-start
-----------
>>> from wcag_common import BaseServiceSettings
>>> from wcag_common.auth import create_access_token, hash_password
>>> from wcag_common.models.auth import UserCreate, TokenResponse
"""

from wcag_common.config.settings import BaseServiceSettings
from wcag_common.aws import S3ClientWrapper, SQSClientWrapper

__all__ = [
    "BaseServiceSettings",
    "S3ClientWrapper",
    "SQSClientWrapper",
]

__version__ = "0.1.0"

