from __future__ import annotations

import json
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
import redis as sync_redis_lib

from session import settings, sync_engine, async_session_maker, Base, get_async_db
from models import Conversation, Message
from retrieval.retriever import retrieve
from retrieval.embedder import set_redis_client

from wcag_common.models.chat import QARequest, MessageItem

from prometheus_client import make_asgi_app
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

# Setup logging
setup_json_logging("qa-service")
logger = logging.getLogger("qa-service")

# Initialize ChatOpenAI client
api_key = (
    os.getenv("LLM_API_KEY")
    or os.getenv("OPENAI_API_KEY")
    or os.getenv("NVIDIA_API_KEY")
)
base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")

if not base_url and os.getenv("NVIDIA_API_KEY") and not os.getenv("OPENAI_API_KEY"):
    base_url = "https://integrate.api.nvidia.com/v1"
    default_model = "meta/llama-3.3-70b-instruct"
else:
    default_model = "gpt-4o"

model_name = os.getenv("LLM_MODEL", default_model)

from langchain_openai import ChatOpenAI
llm = ChatOpenAI(
    model=model_name,
    api_key=api_key,
    base_url=base_url,
    temperature=0,
    streaming=True,
)


redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    # Create database tables with partitioning support
    logger.info("Creating partitioned database tables...")
    from sqlalchemy import text
    try:
        with sync_engine.begin() as conn:
            # Create conversations table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id VARCHAR(36) NOT NULL,
                    user_id VARCHAR(36) NOT NULL,
                    title VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (id)
                );
            """))
            # Create messages partitioned table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS messages (
                    id VARCHAR(36) NOT NULL,
                    conversation_id VARCHAR(36) NOT NULL,
                    role VARCHAR(50) NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (id, created_at),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
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
                    CREATE TABLE IF NOT EXISTS messages_{partition_suffix} PARTITION OF messages
                    FOR VALUES FROM ('{start_date}') TO ('{end_date}');
                """))

        Base.metadata.create_all(sync_engine)
        logger.info("Database tables and partitions initialized successfully.")
    except Exception as e:
        logger.error(f"Failed to initialize database tables or partitions: {e}", exc_info=True)

    # Initialize Async Redis client
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Async Redis connected.")
    except Exception as e:
        logger.warning(f"Async Redis connection failed: {e}")
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

    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="WCAG AI Copilot — QA Service",
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
app.add_middleware(PrometheusMetricsMiddleware, service_name="qa-service")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "qa-service")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


# ── Helpers ──────────────────────────────────────────

async def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Redis client not initialized",
        )
    return redis_client


def get_user_from_headers(request: Request) -> str:
    """Extract user identity from gateway-injected headers."""
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-ID header"
        )
    return user_id


async def stream_qa(
    message: str,
    history: list[MessageItem],
    conversation_id: str | None = None,
    user_id: str | None = None,
    db: AsyncSession | None = None,
):
    """Conversational RAG Q&A stream with database logging."""
    from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
    from sqlalchemy import select

    conv_id = conversation_id
    if user_id and db:
        if conv_id:
            # Check conversation exists and belongs to user
            res = await db.execute(
                select(Conversation).where(Conversation.id == conv_id, Conversation.user_id == user_id)
            )
            conv = res.scalars().first()
            if not conv:
                yield f"data: {json.dumps({'type': 'error', 'content': 'Conversation not found'})}\n\n"
                return
        else:
            # Create a new conversation
            title = message[:50] + "..." if len(message) > 50 else message
            conv = Conversation(user_id=user_id, title=title)
            db.add(conv)
            await db.commit()
            await db.refresh(conv)
            conv_id = conv.id
            yield f"data: {json.dumps({'type': 'conversation_id', 'id': conv_id})}\n\n"

        # Log user message
        user_msg = Message(conversation_id=conv_id, role="user", content=message)
        db.add(user_msg)
        await db.commit()

    # Retrieve context
    criteria = retrieve(message, top_k=5)
    context_items = []
    for c in criteria:
        doc_type = c.get("doc_type") or "document"
        crit_id = c.get("criterion_id") or c.get("technique_id") or "n/a"
        title = c.get("title") or "Untitled"
        text = c.get("text") or ""
        context_items.append(f"[{doc_type.upper()}] {crit_id} {title}\n{text}")

    criteria_context = "\n\n".join(context_items)

    system_msg = SystemMessage(
        content=f"You are WCAG AI Copilot, a senior accessibility advisor. "
        f"Answer the user's questions about web accessibility and the WCAG 2.2 guidelines. "
        f"Use the following WCAG Criteria Context to ground your answer. Always cite specific Success Criteria IDs and Techniques where applicable. "
        f"Provide clear, copy-paste-ready code examples where helpful. Keep your tone professional, helpful, and concise.\n\n"
        f"WCAG CRITERIA CONTEXT:\n{criteria_context}"
    )

    messages = [system_msg]
    for h in history:
        if h.role == "user":
            messages.append(HumanMessage(content=h.content))
        elif h.role == "assistant":
            messages.append(AIMessage(content=h.content))

    messages.append(HumanMessage(content=message))

    accumulated = []
    async for chunk in llm.astream(messages):
        token = chunk.content
        if token:
            accumulated.append(token)
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"

    # Save assistant message to DB
    if user_id and db and conv_id:
        assistant_text = "".join(accumulated)
        assistant_msg = Message(conversation_id=conv_id, role="assistant", content=assistant_text)
        db.add(assistant_msg)
        await db.commit()

    yield "data: [DONE]\n\n"


# ── Endpoints ────────────────────────────────────────

@app.get("/health")
async def health():
    checks = {"service": settings.service_name, "version": settings.service_version}

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


@app.post("/chat/qa")
async def chat_qa(
    req: QARequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    user_id = get_user_from_headers(request)
    return StreamingResponse(
        stream_qa(req.message, req.history, req.conversation_id, user_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── WebSockets support (Phase 5) ───────────────────────

from fastapi import WebSocket, WebSocketDisconnect
import asyncio

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

manager = ConnectionManager()

@app.websocket("/ws/qa")
async def websocket_endpoint(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_async_db),
    redis: aioredis.Redis = Depends(get_redis)
):
    await manager.connect(websocket)
    user_id = "anonymous"

    # Try optional token authentication via query parameter
    token = websocket.query_params.get("token")
    if token:
        try:
            from wcag_common.auth import decode_access_token
            # Retrieve public key from environment
            public_key = os.getenv("JWT_PUBLIC_KEY")
            if public_key:
                payload = decode_access_token(token, public_key, algorithm="RS256")
                user_id = payload.get("sub", "anonymous")
        except Exception as e:
            logger.warning(f"WebSocket auth failed: {e}")
            await websocket.close(code=1008) # Policy Violation
            manager.disconnect(websocket)
            return

    pubsub = None
    listener_task = None
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                payload = json.loads(data)
                
                # Check for subscription message to bind client to a conversation Redis channel
                if payload.get("type") == "subscribe":
                    conv_id = payload.get("conversation_id")
                    if conv_id:
                        if pubsub:
                            await pubsub.unsubscribe()
                        pubsub = redis.pubsub()
                        await pubsub.subscribe(f"conv:{conv_id}")
                        
                        async def redis_listener():
                            try:
                                async for msg in pubsub.listen():
                                    if msg["type"] == "message":
                                        await websocket.send_text(msg["data"])
                            except Exception as pub_err:
                                logger.debug(f"Redis pubsub connection closed: {pub_err}")
                        
                        if listener_task:
                            listener_task.cancel()
                        listener_task = asyncio.create_task(redis_listener())
                        await websocket.send_json({"type": "subscribed", "conversation_id": conv_id})
                    continue

                message = payload.get("message")
                conversation_id = payload.get("conversation_id")
                history_raw = payload.get("history", [])
                
                # Format history
                history = [MessageItem(**h) for h in history_raw]
                
                if not message:
                    await websocket.send_json({"type": "error", "content": "Message is empty"})
                    continue

                # Stream RAG assistant tokens back
                # Also publish events to Redis Pub/Sub channel if conversation ID exists
                channel = f"conv:{conversation_id}" if conversation_id else None
                
                async for event in stream_qa(message, history, conversation_id, user_id, db):
                    if event.startswith("data: "):
                        clean_data = event[6:].strip()
                        if clean_data == "[DONE]":
                            done_msg = json.dumps({"type": "done"})
                            await websocket.send_text(done_msg)
                            if channel:
                                await redis.publish(channel, done_msg)
                        else:
                            await websocket.send_text(clean_data)
                            if channel:
                                await redis.publish(channel, clean_data)
                                
            except Exception as inner_e:
                logger.error(f"Error processing message: {inner_e}")
                await websocket.send_json({"type": "error", "content": str(inner_e)})
                
    except WebSocketDisconnect:
        logger.info("WebSocket connection closed by client")
    finally:
        if listener_task:
            listener_task.cancel()
        if pubsub:
            await pubsub.close()
        manager.disconnect(websocket)

