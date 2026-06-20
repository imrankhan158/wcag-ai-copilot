from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import redis as sync_redis_lib
from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from session import settings, sync_engine, async_session_maker, Base, get_async_db
from models import Audit, AuditViolation
from agent.graph import advisor_graph
from sqs_client import get_sqs_client, get_queue_url
from scraper_s3 import download_html
from scraper import resolve_input
from retrieval.embedder import set_redis_client

from prometheus_client import make_asgi_app
from wcag_common.models import AuditRequest
from wcag_common.models.audit import ViolationSchema, ScoreSchema
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

# Setup logging
setup_json_logging("audit-service")
logger = logging.getLogger("audit-service")

redis_client: aioredis.Redis | None = None
AUDIT_CACHE_TTL = 24 * 3600  # 24 hours


class CheckResponse(BaseModel):
    violations: list[ViolationSchema]
    summary: str
    score: ScoreSchema


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    # Create database tables with partitioning support
    logger.info("Creating partitioned database tables...")
    from sqlalchemy import text
    try:
        with sync_engine.begin() as conn:
            # Create audits partitioned table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS audits (
                    id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    input_type VARCHAR(50) NOT NULL,
                    input_content TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    score_a INTEGER DEFAULT 0,
                    score_aa INTEGER DEFAULT 0,
                    score_aaa INTEGER DEFAULT 0,
                    score_total INTEGER DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (id, created_at)
                ) PARTITION BY RANGE (created_at);
            """))
            # Create audit_violations partitioned table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS audit_violations (
                    id VARCHAR(36) NOT NULL,
                    audit_id VARCHAR(36) NOT NULL,
                    criterion_id VARCHAR(50) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    level VARCHAR(10) NOT NULL,
                    issue TEXT NOT NULL,
                    element TEXT,
                    fix TEXT,
                    explanation TEXT,
                    created_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (id, created_at),
                    FOREIGN KEY (audit_id, created_at) REFERENCES audits(id, created_at) ON DELETE CASCADE
                ) PARTITION BY RANGE (created_at);
            """))

            # Dynamically create monthly partitions for current and next 3 months
            from datetime import datetime
            now = datetime.utcnow()
            current_year = now.year
            current_month = now.month
            for i in range(4):
                year = current_year + (current_month + i - 1) // 12
                month = (current_month + i - 1) % 12 + 1
                start_date = f"{year}-{month:02d}-01 00:00:00"
                next_year = year + month // 12
                next_month = month % 12 + 1
                end_date = f"{next_year}-{next_month:02d}-01 00:00:00"
                partition_suffix = f"y{year}m{month:02d}"

                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS audits_{partition_suffix} PARTITION OF audits
                    FOR VALUES FROM ('{start_date}') TO ('{end_date}');
                """))
                conn.execute(text(f"""
                    CREATE TABLE IF NOT EXISTS audit_violations_{partition_suffix} PARTITION OF audit_violations
                    FOR VALUES FROM ('{start_date}') TO ('{end_date}');
                """))

        Base.metadata.create_all(sync_engine)
        logger.info("Database tables and partitions initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables or partitions: {e}", exc_info=True)

    # Initialize Async Redis for Audit Caching
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Async Redis connected.")
    except Exception as e:
        logger.warning(f"Async Redis connection failed: {e}. Audit caching disabled.")
        redis_client = None

    # Initialize Sync Redis for Embeddings Cache
    try:
        sync_redis_client = sync_redis_lib.from_url(settings.redis_url, decode_responses=True)
        sync_redis_client.ping()
        set_redis_client(sync_redis_client)
        logger.info("Sync Redis connected for embedding caching.")
    except Exception as e:
        logger.warning(f"Sync Redis connection failed: {e}. Embedding caching disabled.")
        set_redis_client(None)

    yield

    # Cleanup
    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="WCAG AI Copilot — Audit Service",
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
app.add_middleware(PrometheusMetricsMiddleware, service_name="audit-service")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "audit-service")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


# ── Helpers ──────────────────────────────────────────

def get_user_from_headers(request: Request) -> tuple[str, str]:
    """Extract user identity from gateway-injected headers."""
    user_id = request.headers.get("X-User-ID")
    user_email = request.headers.get("X-User-Email")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header"
        )
    return user_id, user_email or ""


def content_hash(text: str) -> str:
    """SHA-256 hash of normalized input for caching."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode()).hexdigest()


async def get_cached_result(input_text: str) -> dict | None:
    if redis_client is None:
        return None
    cache_key = f"audit_result:{content_hash(input_text)}"
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            logger.info(f"Audit cache HIT for hash {cache_key[-12:]}")
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Failed to fetch cached audit result: {e}")
    return None


async def cache_result(input_text: str, result: dict):
    if redis_client is None:
        return
    cache_key = f"audit_result:{content_hash(input_text)}"
    try:
        await redis_client.set(cache_key, json.dumps(result), ex=AUDIT_CACHE_TTL)
    except Exception as e:
        logger.warning(f"Failed to cache audit result: {e}")


async def persist_audit(
    db: AsyncSession, user_id: str, input_text: str, result: dict
) -> str:
    """Persist audit and violations to database. Returns audit ID."""
    input_type = "url" if input_text.strip().startswith(("http://", "https://")) else "code"
    score = result.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0})

    audit = Audit(
        user_id=user_id,
        input_type=input_type,
        input_content=input_text,
        summary=result.get("summary", ""),
        score_a=score.get("A", 0),
        score_aa=score.get("AA", 0),
        score_aaa=score.get("AAA", 0),
        score_total=score.get("total", 0),
    )
    db.add(audit)
    await db.commit()
    await db.refresh(audit)

    for v in result.get("violations", []):
        violation = AuditViolation(
            audit_id=audit.id,
            criterion_id=v.get("criterion_id", "n/a"),
            title=v.get("title", "Untitled"),
            level=v.get("level", "A"),
            issue=v.get("issue", ""),
            element=v.get("element"),
            fix=v.get("fix"),
            explanation=v.get("explanation"),
        )
        db.add(violation)
    await db.commit()
    return audit.id


# ── Endpoints ────────────────────────────────────────

@app.get("/health")
async def health():
    checks = {"service": settings.service_name, "version": settings.service_version}
    
    # Redis
    try:
        if redis_client:
            await redis_client.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "not connected"
    except Exception as e:
        checks["redis"] = f"unhealthy: {e}"
        
    # Postgres
    try:
        from sqlalchemy import text
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "healthy"
    except Exception as e:
        checks["postgres"] = f"unhealthy: {e}"
        
    # Qdrant
    try:
        from retrieval.vector_store import QdrantVectorStore
        qs = QdrantVectorStore()
        # Ping Qdrant
        qs.client.get_collections()
        checks["qdrant"] = "healthy"
    except Exception as e:
        checks["qdrant"] = f"unhealthy: {e}"

    all_healthy = all(
        v == "healthy" for k, v in checks.items() if k not in ("service", "version")
    )
    checks["status"] = "healthy" if all_healthy else "degraded"
    status_code = 200 if all_healthy else 503
    return JSONResponse(content=checks, status_code=status_code)


@app.post("/check", response_model=CheckResponse)
async def check_accessibility(
    req: AuditRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user_id, user_email = get_user_from_headers(request)

    # Check audit result cache
    cached = await get_cached_result(req.input)
    if cached:
        # Still persist to DB for history tracking
        try:
            await persist_audit(db, user_id, req.input, cached)
        except Exception as e:
            logger.error(f"Failed to persist cached audit: {e}", exc_info=True)
        return CheckResponse(**cached)

    # Resolve input (URL scraping via SQS/S3 if needed)
    sqs = get_sqs_client()
    queue_url = await get_queue_url("scrape-requests")
    resolved = await resolve_input(
        req.input,
        user_id=user_id,
        redis=redis_client,
        sqs_client=sqs,
        queue_url=queue_url,
    )

    # Run LangGraph audit pipeline
    result = await advisor_graph.ainvoke({
        "user_input": resolved,
        "retrieved_criteria": [],
        "messages": [],
        "violations": [],
        "summary": "",
        "score": {},
    })

    output = {
        "violations": result.get("violations", []),
        "summary": result.get("summary", ""),
        "score": result.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0}),
    }

    # Persist and cache
    try:
        await persist_audit(db, user_id, req.input, output)
    except Exception as e:
        logger.error(f"Failed to persist audit: {e}", exc_info=True)
    await cache_result(req.input, output)

    return CheckResponse(**output)


@app.post("/chat")
async def chat_stream(
    req: AuditRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user_id, _ = get_user_from_headers(request)

    async def stream():
        sqs = get_sqs_client()
        queue_url = await get_queue_url("scrape-requests")
        resolved = await resolve_input(
            req.input,
            user_id=user_id,
            redis=redis_client,
            sqs_client=sqs,
            queue_url=queue_url,
        )

        clean_output = None
        async for event in advisor_graph.astream_events(
            {
                "user_input": resolved,
                "retrieved_criteria": [],
                "messages": [],
                "violations": [],
                "summary": "",
                "score": {},
            },
            version="v1",
        ):
            kind = event.get("event")

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"].content
                if chunk:
                    yield f"data: {json.dumps({'type': 'token', 'content': chunk})}\n\n"

            elif kind == "on_chain_end":
                name = event.get("name", "")
                if name in ("analyze", "evaluate", "suggest"):
                    yield f"data: {json.dumps({'type': 'node_done', 'node': name})}\n\n"

            if kind == "on_chain_end" and event.get("name") == "LangGraph":
                output = event["data"].get("output", {})
                final_data = output.get("suggest", output) if isinstance(output, dict) else {}
                clean_output = {
                    "violations": final_data.get("violations", []),
                    "summary": final_data.get("summary", ""),
                    "score": final_data.get("score", {"A": 0, "AA": 0, "AAA": 0, "total": 0}),
                }
                yield f"data: {json.dumps({'type': 'result', 'data': clean_output})}\n\n"

        # Persist to DB
        if clean_output:
            try:
                async with async_session_maker() as persist_db:
                    await persist_audit(persist_db, user_id, req.input, clean_output)
                    await cache_result(req.input, clean_output)
            except Exception as e:
                logger.error(f"Failed to persist audit: {e}", exc_info=True)

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/history/audits")
async def get_audits(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """List all past accessibility audits for the current user."""
    from sqlalchemy import select
    user_id, _ = get_user_from_headers(request)
    result = await db.execute(
        select(Audit)
        .where(Audit.user_id == user_id)
        .order_by(Audit.created_at.desc())
    )
    audits = result.scalars().all()
    return [
        {
            "id": a.id,
            "input_type": a.input_type,
            "input_content": a.input_content,
            "summary": a.summary,
            "score": {
                "A": a.score_a,
                "AA": a.score_aa,
                "AAA": a.score_aaa,
                "total": a.score_total,
            },
            "created_at": a.created_at,
        }
        for a in audits
    ]


@app.get("/history/audits/{id}")
async def get_audit_details(
    id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """Retrieve details and specific violations list for a past audit."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    user_id, _ = get_user_from_headers(request)
    result = await db.execute(
        select(Audit)
        .options(selectinload(Audit.violations))
        .where(Audit.id == id, Audit.user_id == user_id)
    )
    audit = result.scalars().first()
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit not found or access denied",
        )
    return {
        "id": audit.id,
        "input_type": audit.input_type,
        "input_content": audit.input_content,
        "summary": audit.summary,
        "score": {
            "A": audit.score_a,
            "AA": audit.score_aa,
            "AAA": audit.score_aaa,
            "total": audit.score_total,
        },
        "created_at": audit.created_at,
        "violations": [
            {
                "criterion_id": v.criterion_id,
                "title": v.title,
                "level": v.level,
                "issue": v.issue,
                "element": v.element,
                "fix": v.fix,
                "explanation": v.explanation,
            }
            for v in audit.violations
        ],
    }

