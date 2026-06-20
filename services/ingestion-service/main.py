from __future__ import annotations

import logging
import sys
from collections import Counter
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import redis.asyncio as aioredis

from chunker import chunk_documents
from embedder import EmbeddingProvider
from fetcher import PlaywrightFetcher
from models import IngestDocument, SourceDefinition
from parsers.w3c import parse_source
from source_registry import APG_SOURCE, DEFAULT_SOURCES, canonical_url, source_priority
from vector_store import QdrantVectorStore, batched

from prometheus_client import make_asgi_app
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

# Setup logging
setup_json_logging("ingestion-service")
logger = logging.getLogger("ingestion-service")


class IngestionServiceSettings(BaseSettings):
    service_name: str = "ingestion-service"
    service_version: str = "0.1.0"
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = IngestionServiceSettings()
redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    try:
        redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connected.")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}.")
        redis_client = None
    yield
    if redis_client:
        await redis_client.close()


app = FastAPI(
    title="WCAG AI Copilot — Ingestion Service",
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
app.add_middleware(PrometheusMetricsMiddleware, service_name="ingestion-service")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "ingestion-service")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


# ── Request / Response Models ────────────────────────

class IngestRequest(BaseModel):
    max_pages: int = Field(default=50, ge=1, le=1000)
    batch_size: int = Field(default=32, ge=1, le=256)
    refresh_cache: bool = Field(default=False)
    dry_run: bool = Field(default=False)
    include_apg: bool = Field(default=False)


class IngestResponse(BaseModel):
    status: str
    message: str
    documents_parsed: int
    chunks_ingested: int
    doc_type_counts: dict[str, int]
    chunk_type_counts: dict[str, int]


# ── Internal Seeding Logic ───────────────────────────

def run_collection(max_pages: int, refresh_cache: bool, include_apg: bool) -> list[IngestDocument]:
    fetcher = PlaywrightFetcher(refresh=refresh_cache)
    seed_sources = [*DEFAULT_SOURCES, APG_SOURCE] if include_apg else DEFAULT_SOURCES
    
    # We use list to implement a simple FIFO deque
    queue = list(seed_sources)
    seen_sources: set[str] = set()
    documents: list[IngestDocument] = []

    while queue and len(seen_sources) < max_pages:
        source = queue.pop(0)
        source_key = canonical_url(source.url)
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)

        logger.info(f"Fetching [{len(seen_sources)}/{max_pages}] {source.source_type}: {source.url}")
        try:
            html = fetcher.fetch(source.url)
            parsed = parse_source(html, source)
        except Exception as exc:
            logger.error(f"Skipped {source.url}: {exc}")
            continue

        documents.extend(parsed.documents)
        discovered_sources = sorted(parsed.discovered_sources, key=source_priority)
        for discovered in discovered_sources:
            if discovered.source_type == "aria_apg" and not include_apg:
                continue
            discovered_key = canonical_url(discovered.url)
            if discovered_key not in seen_sources:
                queue.append(discovered)

        logger.info(f"Parsed {len(parsed.documents)} docs, queued {len(queue)} sources")

    return documents


# ── Endpoints ────────────────────────────────────────

@app.get("/health")
async def health():
    checks = {"service": settings.service_name, "version": settings.service_version}

    # Qdrant
    try:
        from vector_store import QdrantVectorStore
        store = QdrantVectorStore()
        store.client.get_collections()
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


@app.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(req: IngestRequest):
    try:
        # 1. Fetch W3C pages
        documents = run_collection(
            max_pages=req.max_pages,
            refresh_cache=req.refresh_cache,
            include_apg=req.include_apg
        )
        
        # 2. Chunk documents
        chunks = chunk_documents(documents)

        doc_counts = Counter(doc.doc_type for doc in documents)
        chunk_counts = Counter(chunk.payload.get("doc_type") for chunk in chunks)

        if req.dry_run:
            return IngestResponse(
                status="success",
                message="Dry run ingestion completed. No writes committed.",
                documents_parsed=len(documents),
                chunks_ingested=0,
                doc_type_counts=dict(doc_counts),
                chunk_type_counts=dict(chunk_counts),
            )

        # 3. Generate embeddings and upsert
        embedder = EmbeddingProvider()
        store = QdrantVectorStore(dense_dim=embedder.dense_dim)
        store.ensure_collection()

        batch_count = 0
        for chunk_batch in batched(chunks, req.batch_size):
            texts = [chunk.text for chunk in chunk_batch]
            dense_vectors = embedder.embed_dense(texts)
            sparse_vectors = embedder.embed_sparse(texts)
            store.upsert_chunks(chunk_batch, dense_vectors, sparse_vectors)
            batch_count += 1
            logger.info(f"Ingested batch {batch_count}: {len(chunk_batch)} chunks")

        return IngestResponse(
            status="success",
            message=f"Successfully seeded {len(chunks)} chunks into Qdrant in {batch_count} batches.",
            documents_parsed=len(documents),
            chunks_ingested=len(chunks),
            doc_type_counts=dict(doc_counts),
            chunk_type_counts=dict(chunk_counts),
        )

    except Exception as e:
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )
