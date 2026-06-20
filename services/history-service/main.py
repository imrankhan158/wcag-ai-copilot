from __future__ import annotations

import json
import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, status, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
import redis.asyncio as aioredis

from models import Audit, Conversation, Message

from prometheus_client import make_asgi_app
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

# Setup logging
setup_json_logging("history-service")
logger = logging.getLogger("history-service")


class HistoryServiceSettings(BaseSettings):
    service_name: str = "history-service"
    service_version: str = "0.1.0"
    redis_url: str = "redis://localhost:6379/0"

    # Audit DB details
    audit_db_host: str = "localhost"
    audit_db_port: int = 6432
    audit_db_db: str = "wcag_copilot"
    audit_db_user: str = "admin"
    audit_db_password: str = "admin123"

    # Conversations DB details
    conv_db_host: str = "localhost"
    conv_db_port: int = 6432
    conv_db_db: str = "wcag_copilot"
    conv_db_user: str = "admin"
    conv_db_password: str = "admin123"

    @property
    def audit_database_url(self) -> str:
        from urllib.parse import quote_plus
        password = quote_plus(self.audit_db_password)
        return f"postgresql+asyncpg://{self.audit_db_user}:{password}@{self.audit_db_host}:{self.audit_db_port}/{self.audit_db_db}"

    @property
    def conv_database_url(self) -> str:
        from urllib.parse import quote_plus
        password = quote_plus(self.conv_db_password)
        return f"postgresql+asyncpg://{self.conv_db_user}:{password}@{self.conv_db_host}:{self.conv_db_port}/{self.conv_db_db}"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = HistoryServiceSettings()

audit_engine = create_async_engine(settings.audit_database_url, echo=False)
audit_session_maker = async_sessionmaker(audit_engine, class_=AsyncSession, expire_on_commit=False)

conv_engine = create_async_engine(settings.conv_database_url, echo=False)
conv_session_maker = async_sessionmaker(conv_engine, class_=AsyncSession, expire_on_commit=False)

redis_client: aioredis.Redis | None = None
LIST_CACHE_TTL = 300  # 5 minutes


async def get_audit_db():
    async with audit_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_conv_db():
    async with conv_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


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
    title="WCAG AI Copilot — History Service",
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
app.add_middleware(PrometheusMetricsMiddleware, service_name="history-service")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "history-service")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


# ── Helpers ──────────────────────────────────────────

def get_user_from_headers(request: Request) -> str:
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header"
        )
    return user_id


# ── Endpoints ────────────────────────────────────────

@app.get("/health")
async def health():
    checks = {"service": settings.service_name, "version": settings.service_version}

    # Audit DB
    try:
        from sqlalchemy import text
        async with audit_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres_audits"] = "healthy"
    except Exception as e:
        checks["postgres_audits"] = f"unhealthy: {e}"

    # Conversation DB
    try:
        from sqlalchemy import text
        async with conv_session_maker() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres_conversations"] = "healthy"
    except Exception as e:
        checks["postgres_conversations"] = f"unhealthy: {e}"

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


@app.get("/history/chats")
async def get_chats(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_conv_db),
):
    """List all past conversations for the current authenticated user (paginated)."""
    user_id = get_user_from_headers(request)
    cache_key = f"hist_chats:{user_id}:{page}:{per_page}"

    # Try cache lookup
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT for history chats ({user_id}) page {page}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Failed to fetch cached history chats: {e}")

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    chats = result.scalars().all()
    output = [{"id": c.id, "title": c.title, "created_at": str(c.created_at)} for c in chats]

    # Write cache
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(output), ex=LIST_CACHE_TTL)
        except Exception as e:
            logger.warning(f"Failed to cache history chats: {e}")

    return output


@app.get("/history/chats/{id}")
async def get_chat_details(
    id: str,
    request: Request,
    db: AsyncSession = Depends(get_conv_db),
):
    """Retrieve detailed messages for a specific conversation."""
    user_id = get_user_from_headers(request)
    result = await db.execute(
        select(Conversation)
        .options(selectinload(Conversation.messages))
        .where(Conversation.id == id, Conversation.user_id == user_id)
    )
    conv = result.scalars().first()
    if not conv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found or access denied",
        )
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": str(conv.created_at),
        "messages": [
            {"role": m.role, "content": m.content, "created_at": str(m.created_at)}
            for m in conv.messages
        ],
    }


@app.get("/history/audits")
async def get_audits(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_audit_db),
):
    """List all past accessibility audits for the current user (paginated)."""
    user_id = get_user_from_headers(request)
    cache_key = f"hist_audits:{user_id}:{page}:{per_page}"

    # Try cache lookup
    if redis_client:
        try:
            cached = await redis_client.get(cache_key)
            if cached:
                logger.info(f"Cache HIT for history audits ({user_id}) page {page}")
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"Failed to fetch cached history audits: {e}")

    offset = (page - 1) * per_page
    result = await db.execute(
        select(Audit)
        .where(Audit.user_id == user_id)
        .order_by(Audit.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    audits = result.scalars().all()
    output = [
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
            "created_at": str(a.created_at),
        }
        for a in audits
    ]

    # Write cache
    if redis_client:
        try:
            await redis_client.set(cache_key, json.dumps(output), ex=LIST_CACHE_TTL)
        except Exception as e:
            logger.warning(f"Failed to cache history audits: {e}")

    return output


@app.get("/history/audits/{id}")
async def get_audit_details(
    id: str,
    request: Request,
    db: AsyncSession = Depends(get_audit_db),
):
    """Retrieve details and specific violations list for a past audit."""
    user_id = get_user_from_headers(request)
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
        "created_at": str(audit.created_at),
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


# ── Search & Stats endpoints (Phase 5) ─────────────────

from sqlalchemy import func

@app.get("/history/search")
async def search_history(
    q: str = Query(..., description="Search query term"),
    request: Request = None,
    audit_db: AsyncSession = Depends(get_audit_db),
    conv_db: AsyncSession = Depends(get_conv_db),
):
    """Full-text search across past audits and chats using database LIKE matching."""
    user_id = get_user_from_headers(request)
    like_query = f"%{q}%"
    
    # Query audits matching criteria
    audit_stmt = (
        select(Audit)
        .where(
            Audit.user_id == user_id,
            (Audit.input_content.like(like_query) | Audit.summary.like(like_query))
        )
        .limit(20)
    )
    audit_res = await audit_db.execute(audit_stmt)
    audits = audit_res.scalars().all()
    
    # Query chats matching criteria
    conv_stmt = (
        select(Conversation)
        .join(Message, Conversation.id == Message.conversation_id)
        .where(
            Conversation.user_id == user_id,
            (Conversation.title.like(like_query) | Message.content.like(like_query))
        )
        .distinct()
        .limit(20)
    )
    conv_res = await conv_db.execute(conv_stmt)
    conversations = conv_res.scalars().all()
    
    return {
        "query": q,
        "audits": [
            {
                "id": a.id,
                "input_type": a.input_type,
                "input_content": a.input_content,
                "summary": a.summary,
                "created_at": str(a.created_at)
            }
            for a in audits
        ],
        "chats": [
            {
                "id": c.id,
                "title": c.title,
                "created_at": str(c.created_at)
            }
            for c in conversations
        ]
    }


@app.get("/history/stats")
async def get_stats(
    request: Request,
    db: AsyncSession = Depends(get_audit_db),
):
    """Retrieve aggregate stats for the user dashboard."""
    user_id = get_user_from_headers(request)
    
    # Total audits and average score
    stmt = (
        select(
            func.count(Audit.id).label("total"),
            func.avg(Audit.score_total).label("avg_score")
        )
        .where(Audit.user_id == user_id)
    )
    res = await db.execute(stmt)
    row = res.first()
    total = row.total if row else 0
    avg_score = float(row.avg_score) if row and row.avg_score is not None else 0.0
    
    # Last 10 audits for trend
    trend_stmt = (
        select(Audit.score_total, Audit.created_at)
        .where(Audit.user_id == user_id)
        .order_by(Audit.created_at.asc())
        .limit(10)
    )
    trend_res = await db.execute(trend_stmt)
    trend = [{"score": r[0], "date": str(r[1])} for r in trend_res.all()]
    
    return {
        "total_audits": total,
        "average_score": round(avg_score, 2),
        "trend": trend,
    }

