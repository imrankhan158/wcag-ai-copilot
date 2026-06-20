"""Pluggable health-check system for FastAPI services.

Usage
-----
>>> from wcag_common.health import HealthChecker, create_health_router
>>>
>>> checker = HealthChecker(service_name="api-gateway", service_version="0.1.0")
>>> checker.add_check("postgres", check_postgres(settings.async_database_url))
>>> app.include_router(create_health_router(checker))
"""

from wcag_common.health.checker import (
    HealthCheckResult,
    HealthChecker,
    check_postgres,
    check_qdrant,
    check_redis,
    create_health_router,
)

__all__ = [
    "HealthCheckResult",
    "HealthChecker",
    "check_postgres",
    "check_qdrant",
    "check_redis",
    "create_health_router",
]
