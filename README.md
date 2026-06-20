# 🤖 WCAG AI Copilot: Enterprise-Grade Microservices Accessibility Advisor

A premium, production-grade, horizontally-scalable AI platform designed to audit web code markup and live public URLs against the official **WCAG 2.2 guidelines**. Decomposed into containerized microservices utilizing a conversational RAG pipeline, a custom multi-step LangGraph agent, hybrid dense-sparse vector search, and a unified primary-replica PostgreSQL storage layer.

---

## 📐 1. System Architecture

The WCAG AI Copilot operates on a modern, decoupled microservices topology. All incoming traffic routes through the API Gateway, which manages JWT authentication, token-bucket rate limiting, and request proxying downstream.

```mermaid
graph TD
    subgraph "Edge & Edge Proxy Layer"
        UI[React Frontend Dashboard<br/>Port 3001]
        GW[API Gateway<br/>Port 8000]
    end

    subgraph "Core Microservices"
        AuthSvc[🔐 Auth Service<br/>Port 8001]
        AuditSvc[🤖 Audit Service<br/>Port 8003]
        QASvc[💬 QA Service<br/>Port 8004]
        HistSvc[📚 History Service<br/>Port 8005]
        CritSvc[📋 Criteria Service<br/>Port 8006]
        IngSvc[📥 Ingestion Service<br/>Port 8007]
    end

    subgraph "Asynchronous Workers & Queues"
        SQS["Amazon SQS Queues<br/>scrape-requests · scrape-results"]
        S3["Amazon S3 Bucket<br/>wcag-scraper-cache"]
        Worker["🕷️ Scraper Worker<br/>Playwright Context Pool"]
        Redis["Redis Cache & Pub/Sub<br/>Rate limits · Caches · SSE"]
    end

    subgraph "Data & Vector Layer"
        PGB_W["primary-bouncer (PgBouncer)<br/>Port 6432 (Write)"]
        PGB_R["replica-bouncer (PgBouncer)<br/>Port 6433 (Read-Only)"]

        DB_P[(postgres-primary<br/>wcag_copilot)]
        DB_R[(postgres-replica)]
        
        Qdrant[(Qdrant Vector DB Cluster<br/>wcag_criteria)]
    end

    %% Connections
    UI -->|HTTP / SSE| GW
    GW -->|/api/auth/*| AuthSvc
    GW -->|/api/check, /api/chat| AuditSvc
    GW -->|/api/chat/qa| QASvc
    GW -->|/api/history/*| HistSvc
    GW -->|/api/criteria/*| CritSvc

    %% Core Services DB Links
    AuthSvc -->|Verify Credentials| PGB_W --> DB_P
    AuthSvc -->|Blacklist Check| Redis
    
    AuditSvc -->|Save Audits (Write)| PGB_W --> DB_P
    AuditSvc -->|Read Audits| PGB_R --> DB_R
    AuditSvc -->|Query Criteria| CritSvc
    AuditSvc -->|Async Scrape Job| SQS
    
    Worker -->|Read Jobs| SQS
    Worker -->|Save Scraped HTML| S3
    Worker -->|Update Job State| Redis
    
    QASvc -->|Save Conversations (Write)| PGB_W --> DB_P
    QASvc -->|Query Context| Qdrant
    QASvc -->|Publish SSE Stream Tokens| Redis
    
    HistSvc -->|Aggregate Reads| PGB_R --> DB_R
    
    CritSvc -->|Cache Hits| Redis
    CritSvc -->|Get Vector Data| Qdrant
    
    IngSvc -->|Upsert Chunks & Vectors| Qdrant
```

---

## 🚀 2. Core Service Catalog

| Service | Port | Database | Key Responsibility |
|---|---|---|---|
| **API Gateway** | `8000` | — | Edge routing, JWT validation, Redis token-bucket rate limiting |
| **Auth Service** | `8001` | `wcag_copilot` (PG 5432/5442) | User registration, login, and RS256 token signing |
| **Audit Service** | `8003` | `wcag_copilot` (PG 5432/5442) | LangGraph accessibility agent (`analyze` → `evaluate` → `suggest`) |
| **QA Service** | `8004` | `wcag_copilot` (PG 5432/5442) | RAG-based conversational chat via Server-Sent Events (SSE) |
| **History Service** | `8005` | `wcag_copilot` (PG 5432/5442) | Aggregated audits + conversation session retrieval and search |
| **Criteria Service** | `8006` | Qdrant | Reads criteria from vector index with Redis caching |
| **Ingestion Service** | `8007` | Qdrant | Headless W3C specification crawler and vector database seeder |
| **Scraper Worker** | — | — | Headless Playwright crawling consumer polling SQS queues |

---

## 🛠 3. Technical Implementation Details

### Database Consolidation & High-Scale Caching
*   **Unified postgres Storage**: All core services leverage a single database instance (`wcag_copilot`). Decoupling is maintained in code via unique table configurations (`users`, `audits`, `audit_violations`, `conversations`, `messages`).
*   **Composite monthly Partitioning**: Composite primary keys on `created_at` timestamp support PostgreSQL range partitioning on high-volume tables (`audits`, `audit_violations`, `messages`).
*   **PgBouncer Poolers**: Traffic spikes are mitigated via PgBouncer connections:
    - `primary-bouncer` on port `6432` manages write transactions targeting `postgres-primary`.
    - `replica-bouncer` on port `6433` manages read-only transactions targeting the standby `postgres-replica` (port `5442`).
*   **Raft Consensus Vector Cluster**: A 3-node Qdrant consensus cluster handles vector storage.
*   **Hybrid Dense-Sparse Retrievals**: Semantic dense embeddings (FastEmbed) are combined with precise token sparse representations (SPLADE) via Reciprocal Rank Fusion (RRF) inside the Criteria Service.

---

## 📦 4. Installation & Local Setup

### Prerequisites
Make sure you have Docker, Node.js (v20+), and Python 3.12+ (with the `uv` package manager) installed.

### 1. Boot up Infrastructure and Microservices
Start all containers (Postgres primary/standby, PgBouncers, Redis, Qdrant cluster, AWS LocalStack/Floci clone, workers, and microservices):
```bash
docker compose up -d
```

### 2. Seeding WCAG Guidance Chunks
Seeding is handled by a standalone Ingestion Service. Trigger a full crawling run:
```bash
# Verify the ingestion service is healthy
curl http://localhost:8007/health

# Trigger 50-page crawl and seed
curl -X POST http://localhost:8007/ingest \
  -H "Content-Type: application/json" \
  -d '{"max_pages": 50, "batch_size": 32}'
```

### 3. Run Smoke Tests
Verify the overall platform status, API routing, streaming, and database scaling layers:
```bash
# Project workspace setup
uv sync

# Run the unified platform smoke test
uv run scratch/smoke_test.py
```
The smoke test automatically validates:
- **Database Scaling (Phase 6)**: Replication synchronization, standby read-only constraints, Range Partition routing, and bouncer connection pools.
- **Vector DB Health**: Qdrant 3-node Raft consensus cluster peer checks.
- **Edge Gateway & API (Phase 5)**: Auth logins/registrations, LangGraph audit checks, SSE chatbot token streaming, history logs, and success criteria mapping.

### 4. Run the React Dashboard
Navigate to the frontend folder, install dependencies, and start Vite:
```bash
cd frontend
npm install
npm run dev
```
*Access the user interface dashboard at `http://localhost:3001`.*

---

## ♿ 5. UI Accessibility Conformance
The frontend complies with WCAG 2.2 accessibility guidelines:
*   **Aria Log Announcers**: Live audit logs and streaming responses use `role="log"` and `aria-live="polite"`.
*   **Accessible Controls**: Forms and search inputs are bound to visually hidden but accessible `<label>` attributes.
*   **Keyboard Navigation**: Highly visible focus indicators (`focus:ring-blue-500`) are active across all selectable controls.
