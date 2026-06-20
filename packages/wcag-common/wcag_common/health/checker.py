"""Pluggable health-check system for FastAPI microservices.

Provides a :class:`HealthChecker` that aggregates multiple async health
probes and a :func:`create_health_router` factory that returns a
ready-to-mount ``APIRouter`` with a ``GET /health`` endpoint.

Built-in check factories
------------------------
- :func:`check_postgres` — verifies a PostgreSQL connection via asyncpg.
- :func:`check_redis` — pings a Redis server via ``redis.asyncio``.
- :func:`check_qdrant` — hits the Qdrant ``/readyz`` HTTP endpoint.

Example
-------
>>> from wcag_common.health import HealthChecker, create_health_router, check_postgres
>>>
>>> checker = HealthChecker(service_name="audit-worker", service_version="0.2.0")
>>> checker.add_check("postgres", check_postgres("postgresql+asyncpg://..."))
>>> app.include_router(create_health_router(checker))
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

__all__ = [
    "HealthCheckResult",
    "HealthChecker",
    "check_postgres",
    "check_redis",
    "check_qdrant",
    "create_health_router",
]


# ── Data models ──────────────────────────────────────────────────────────


class HealthCheckResult(BaseModel):
    """Outcome of a single health probe."""

    name: str = Field(..., description="Logical name of the dependency.")
    status: str = Field(
        ..., description="'healthy' or 'unhealthy'."
    )
    latency_ms: float = Field(
        ..., ge=0, description="Round-trip time in milliseconds."
    )
    details: str | None = Field(
        default=None,
        description="Optional diagnostic message (errors, versions, …).",
    )


class _HealthResponse(BaseModel):
    """Top-level response body for ``GET /health``."""

    service: str
    version: str
    status: str
    uptime_seconds: float
    timestamp: datetime
    checks: list[HealthCheckResult]


# ── Type alias for check functions ───────────────────────────────────────

HealthCheckFn = Callable[[], Awaitable[HealthCheckResult]]


# ── HealthChecker ────────────────────────────────────────────────────────


class HealthChecker:
    """Registry of async health-check probes.

    Parameters
    ----------
    service_name:
        Human-readable name shown in the response body.
    service_version:
        SemVer version shown in the response body.
    """

    def __init__(self, service_name: str, service_version: str) -> None:
        self.service_name = service_name
        self.service_version = service_version
        self._checks: dict[str, HealthCheckFn] = {}
        self._start_time = time.monotonic()

    def add_check(self, name: str, check_fn: HealthCheckFn) -> None:
        """Register an async health probe under *name*."""
        self._checks[name] = check_fn

    async def run_checks(self) -> _HealthResponse:
        """Execute all registered probes and return the aggregate result."""
        results: list[HealthCheckResult] = []
        for _name, fn in self._checks.items():
            try:
                result = await fn()
            except Exception as exc:
                result = HealthCheckResult(
                    name=_name,
                    status="unhealthy",
                    latency_ms=0.0,
                    details=str(exc),
                )
            results.append(result)

        overall = (
            "healthy"
            if all(r.status == "healthy" for r in results)
            else "unhealthy"
        )

        return _HealthResponse(
            service=self.service_name,
            version=self.service_version,
            status=overall,
            uptime_seconds=round(time.monotonic() - self._start_time, 2),
            timestamp=datetime.now(timezone.utc),
            checks=results,
        )


# ── Built-in check factories ────────────────────────────────────────────


def check_postgres(database_url: str) -> HealthCheckFn:
    """Return a health-check coroutine for a PostgreSQL database.

    Uses ``asyncpg`` directly (not SQLAlchemy) to keep the probe
    lightweight and independent of the ORM session pool.

    Parameters
    ----------
    database_url:
        An asyncpg-compatible connection URL, e.g.
        ``postgresql+asyncpg://user:pass@host/db`` or
        ``postgresql://user:pass@host/db``.
    """

    async def _check() -> HealthCheckResult:
        import asyncpg  # lazy import — optional dependency

        # Strip the SQLAlchemy dialect prefix if present.
        url = database_url.replace("postgresql+asyncpg://", "postgresql://")
        start = time.monotonic()
        try:
            conn = await asyncpg.connect(url, timeout=5)
            try:
                await conn.fetchval("SELECT 1")
            finally:
                await conn.close()
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                name="postgres", status="healthy", latency_ms=round(latency, 2)
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                name="postgres",
                status="unhealthy",
                latency_ms=round(latency, 2),
                details=str(exc),
            )

    return _check


def check_redis(redis_url: str) -> HealthCheckFn:
    """Return a health-check coroutine for a Redis server.

    Parameters
    ----------
    redis_url:
        A Redis connection URL, e.g. ``redis://localhost:6379/0``.
    """

    async def _check() -> HealthCheckResult:
        import redis.asyncio as aioredis  # lazy import — optional dependency

        start = time.monotonic()
        try:
            client = aioredis.from_url(redis_url, socket_connect_timeout=5)
            try:
                await client.ping()
            finally:
                await client.aclose()
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                name="redis", status="healthy", latency_ms=round(latency, 2)
            )
        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                name="redis",
                status="unhealthy",
                latency_ms=round(latency, 2),
                details=str(exc),
            )

    return _check


def check_qdrant(qdrant_url: str) -> HealthCheckFn:
    """Return a health-check coroutine for a Qdrant vector database.

    Uses a simple HTTP GET to ``/readyz`` — no Qdrant client library
    required.

    Parameters
    ----------
    qdrant_url:
        Base URL of the Qdrant instance, e.g. ``http://localhost:6333``.
    """

    async def _check() -> HealthCheckResult:
        from urllib.request import urlopen
        from urllib.error import URLError
        import asyncio

        url = f"{qdrant_url.rstrip('/')}/readyz"

        def _probe() -> None:
            with urlopen(url, timeout=5):
                pass

        start = time.monotonic()
        try:
            await asyncio.to_thread(_probe)
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                name="qdrant", status="healthy", latency_ms=round(latency, 2)
            )
        except (URLError, OSError, Exception) as exc:
            latency = (time.monotonic() - start) * 1000
            return HealthCheckResult(
                name="qdrant",
                status="unhealthy",
                latency_ms=round(latency, 2),
                details=str(exc),
            )

    return _check


# ── FastAPI router factory ───────────────────────────────────────────────


def create_health_router(
    checker: HealthChecker,
    *,
    prefix: str = "/health",
    tags: list[str] | None = None,
) -> Any:
    """Create a FastAPI ``APIRouter`` with a ``GET /health`` endpoint.

    Parameters
    ----------
    checker:
        A configured :class:`HealthChecker` instance.
    prefix:
        URL prefix for the router (default ``/health``).
    tags:
        OpenAPI tags for the endpoint.

    Returns
    -------
    fastapi.APIRouter
        Ready to mount on a FastAPI ``app``.
    """
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix=prefix, tags=tags or ["health"])

    @router.get(
        "",
        summary="Health Check",
        description="Aggregated health status of the service and its dependencies.",
    )
    async def health_check() -> JSONResponse:
        result = await checker.run_checks()
        status_code = 200 if result.status == "healthy" else 503
        return JSONResponse(
            content=result.model_dump(mode="json"),
            status_code=status_code,
        )

    return router
