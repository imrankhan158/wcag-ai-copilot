from __future__ import annotations

import json
import logging
import sys
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query, status, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
import redis.asyncio as aioredis

from retrieval.vector_store import QdrantVectorStore

from prometheus_client import make_asgi_app
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

# Setup logging
setup_json_logging("criteria-service")
logger = logging.getLogger("criteria-service")


class CriteriaServiceSettings(BaseSettings):
    service_name: str = "criteria-service"
    service_version: str = "0.1.0"
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = CriteriaServiceSettings()

store = QdrantVectorStore()
qdrant = store.client
COLLECTION = store.collection

redis_client: aioredis.Redis | None = None
CRITERIA_CACHE_TTL = 3600  # 1 hour


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected.")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}. Caching disabled.")
        redis_client = None
    yield
    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="WCAG AI Copilot — Criteria Service",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument the app for observability
app.add_middleware(PrometheusMetricsMiddleware, service_name="criteria-service")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "criteria-service")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


def _criteria_cache_key(level: str | None, principle: str | None) -> str:
    return f"criteria:{level or '_all'}:{principle or '_all'}"


# ── Endpoints ────────────────────────────────────────

@app.get("/health")
async def health():
    checks = {"service": settings.service_name, "version": settings.service_version}

    # Qdrant
    try:
        qdrant.get_collections()
        checks["qdrant"] = "healthy"
    except Exception as e:
        checks["qdrant"] = f"unhealthy: {e}"

    # Redis
    try:
        if redis_client:
            await redis_client.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "not connected"
    except Exception as e:
        checks["redis"] = f"unhealthy: {e}"

    all_healthy = all(
        v == "healthy" for k, v in checks.items() if k not in ("service", "version")
    )
    checks["status"] = "healthy" if all_healthy else "degraded"
    status_code = 200 if all_healthy else 503
    return JSONResponse(content=checks, status_code=status_code)


@app.get("/criteria")
async def list_criteria(
    level: str | None = Query(None, description="A, AA, or AAA"),
    principle: str | None = Query(None, description="Perceivable, Operable, etc."),
):
    cache_key = _criteria_cache_key(level, principle)

    # --- Try Redis cache first ---
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached is not None:
                logger.info("Criteria cache HIT for %s", cache_key)
                return json.loads(cached)
        except Exception as e:
            logger.warning("Redis read failed for %s – querying Qdrant: %s", cache_key, e)

    # --- Fall back to Qdrant ---
    try:
        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            limit=1000,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query criteria from Qdrant: {str(e)}"
        )

    # Filter for success criteria (those with doc_type success_criterion and a valid criterion_id)
    criteria = [
        r.payload
        for r in results
        if r.payload
        and r.payload.get("doc_type") == "success_criterion"
        and r.payload.get("criterion_id")
    ]

    # Map database keys to frontend expected keys if different (e.g. source_url to url)
    for c in criteria:
        if "url" not in c and "source_url" in c:
            c["url"] = c["source_url"]

    if level:
        criteria = [c for c in criteria if c.get("level") == level]
    if principle:
        criteria = [c for c in criteria if c.get("principle") == principle]

    # Sort criteria numerically by ID (e.g., "1.1.1" -> [1, 1, 1])
    try:
        criteria.sort(key=lambda c: [int(x) for x in c["criterion_id"].split(".")])
    except Exception:
        pass

    response = {"criteria": criteria, "total": len(criteria)}

    # --- Write through to cache ---
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(response), ex=CRITERIA_CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed for %s: %s", cache_key, e)

    return response


# ── Search & Ingest endpoints ──────────────────────────
# NOTE: These MUST be defined BEFORE /criteria/{id} to prevent
# FastAPI from matching "search" or "ingest" as an {id} parameter.

from qdrant_client.models import Filter, FieldCondition, MatchText, MatchValue
import httpx

@app.get("/criteria/search")
async def search_criteria(
    q: str = Query(..., description="Full-text search term"),
):
    """Keyword search across the WCAG criteria stored in Qdrant."""
    cache_key = f"criteria_search:{q}"

    # Try cache lookup
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached is not None:
                logger.info("Criteria search cache HIT for %s", cache_key)
                return json.loads(cached)
        except Exception as e:
            logger.warning("Redis read failed for %s: %s", cache_key, e)

    try:
        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="text", match=MatchText(text=q))
                ]
            ),
            limit=20,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute criteria search in Qdrant: {str(e)}"
        )

    criteria = [r.payload for r in results if r.payload]
    
    # Map database keys to frontend expected keys if different (e.g. source_url to url)
    for c in criteria:
        if "url" not in c and "source_url" in c:
            c["url"] = c["source_url"]

    response = {"criteria": criteria, "total": len(criteria)}

    # Write cache
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(response), ex=CRITERIA_CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed for search %s: %s", cache_key, e)

    return response


@app.post("/criteria/ingest")
async def trigger_ingest(
    request: Request,
):
    """Admin endpoint to trigger re-ingestion by proxying to the standalone Ingestion Service."""
    try:
        body = await request.json()
    except Exception:
        body = {}
        
    ingestion_url = os.getenv("INGESTION_SERVICE_URL", "http://ingestion-service:8007/ingest")
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(ingestion_url, json=body)
            return JSONResponse(status_code=resp.status_code, content=resp.json())
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with ingestion service: {e}"
        )


# ── Parameterized route (MUST be last) ─────────────────

@app.get("/criteria/{id}")
async def get_criterion(id: str):
    """Retrieve details for a specific WCAG criterion by ID."""
    cache_key = f"criteria_detail:{id}"

    # Try Redis cache first
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached is not None:
                logger.info("Criteria detail cache HIT for %s", cache_key)
                return json.loads(cached)
        except Exception as e:
            logger.warning("Redis read failed for %s: %s", cache_key, e)

    # Fall back to Qdrant query
    try:
        results, _ = qdrant.scroll(
            collection_name=COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="doc_type", match=MatchValue(value="success_criterion")),
                    FieldCondition(key="criterion_id", match=MatchValue(value=id))
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query criteria detail from Qdrant: {str(e)}"
        )

    if not results:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Criterion {id} not found"
        )

    payload = results[0].payload
    if payload:
        if "url" not in payload and "source_url" in payload:
            payload["url"] = payload["source_url"]

    # Write to Redis cache
    if redis_client and payload:
        try:
            await redis_client.set(cache_key, json.dumps(payload), ex=CRITERIA_CACHE_TTL)
        except Exception as e:
            logger.warning("Redis write failed for %s: %s", cache_key, e)

    return payload
