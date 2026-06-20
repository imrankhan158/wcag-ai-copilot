# WCAG AI Copilot — API Contracts

> Complete API reference for all microservices. All endpoints use JSON unless otherwise noted.

---

## Table of Contents

- [Authentication](#authentication)
- [API Gateway (Port 8000)](#api-gateway)
- [Auth Service (Port 8001)](#auth-service)
- [Audit Service (Port 8003)](#audit-service)
- [QA Service (Port 8004)](#qa-service)
- [History Service (Port 8005)](#history-service)
- [Criteria Service (Port 8006)](#criteria-service)
- [Ingestion Service (Port 8007)](#ingestion-service)
- [Scraper Worker (SQS)](#scraper-worker)
- [Shared Models](#shared-models)
- [Error Responses](#error-responses)

---

## Authentication

All authenticated endpoints require a valid RS256 JWT in the `Authorization` header:

```
Authorization: Bearer <access_token>
```

The API Gateway validates the JWT, checks the Redis blacklist, and injects identity headers to downstream services:

| Header | Value | Description |
|---|---|---|
| `X-User-ID` | UUID string | Authenticated user's ID |
| `X-User-Email` | Email string | Authenticated user's email |

Downstream services trust these headers — they do **not** re-validate the JWT.

### Rate Limiting

The API Gateway applies a **token bucket** rate limiter:
- **Capacity**: 100 tokens
- **Refill rate**: 2 tokens/second
- **Key**: `user_id` (authenticated) or client IP (unauthenticated)

Rate-limited responses return:
```json
{"detail": "Rate limit exceeded. Try again later."}
```
with HTTP status `429 Too Many Requests`.

---

## API Gateway

**Base URL**: `http://localhost:8000`

The gateway reverse-proxies all requests to downstream services. It does not serve its own business logic.

### Routes

| Frontend Path | Downstream Service | Downstream Path |
|---|---|---|
| `/api/auth/*` | Auth Service (8001) | `/auth/*` |
| `/api/check` | Audit Service (8003) | `/check` |
| `/api/chat` (non-QA) | Audit Service (8003) | `/chat` |
| `/api/chat/qa` | QA Service (8004) | `/chat/qa` |
| `/api/history/*` | History Service (8005) | `/history/*` |
| `/api/criteria/*` | Criteria Service (8006) | `/criteria/*` |

### Health Check

```
GET /health
```

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "redis": "connected"
}
```

---

## Auth Service

**Internal URL**: `http://auth-service:8001`

### POST /auth/register

Create a new user account.

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

| Field | Type | Constraints |
|---|---|---|
| `email` | `EmailStr` | Valid email format |
| `password` | `string` | 8-128 characters |

**Response** `201 Created`:
```json
{
  "access_token": "eyJhbGciOiJSUzI1NiIs...",
  "refresh_token": null,
  "token_type": "bearer",
  "user": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "email": "user@example.com",
    "created_at": "2026-06-14T10:00:00Z"
  }
}
```

**Errors**: `400 Email already registered`

---

### POST /auth/login

Authenticate and receive a JWT token.

**Request Body**: Same as `/auth/register`

**Response** `200 OK`: Same as `/auth/register` response

**Errors**: `401 Invalid email or password`

---

### POST /auth/logout

Blacklist the current access token.

**Headers**: `Authorization: Bearer <token>` (required)

**Response** `200 OK`:
```json
{"detail": "Successfully logged out"}
```

---

### GET /auth/me

Get the current authenticated user's profile.

**Headers**: `Authorization: Bearer <token>` (required)

**Response** `200 OK`:
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com",
  "created_at": "2026-06-14T10:00:00Z"
}
```

---

### GET /auth/validate

Internal endpoint for token validation (used by API Gateway).

**Query Parameters**: `token` (required)

**Response** `200 OK`:
```json
{
  "valid": true,
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "email": "user@example.com"
}
```

---

## Audit Service

**Internal URL**: `http://audit-service:8003`

### POST /check

Run an accessibility audit through the LangGraph pipeline (analyze → evaluate → suggest).

**Headers**: `X-User-ID` (required, injected by gateway)

**Request Body**:
```json
{
  "input": "<html><head><title>My Page</title></head><body><img src='photo.jpg'></body></html>",
  "session_id": "optional-session-uuid"
}
```

| Field | Type | Description |
|---|---|---|
| `input` | `string` | HTML code or URL to audit |
| `session_id` | `string?` | Optional session identifier |

**Response** `200 OK`:
```json
{
  "violations": [
    {
      "criterion_id": "1.1.1",
      "title": "Non-text Content",
      "level": "A",
      "issue": "Image missing alt attribute",
      "element": "<img src='photo.jpg'>",
      "fix": "Add alt='Description of photo' attribute",
      "explanation": "WCAG 1.1.1 requires all non-text content to have a text alternative"
    }
  ],
  "summary": "Found 1 accessibility violation...",
  "score": {
    "A": 85,
    "AA": 90,
    "AAA": 95,
    "total": 88
  }
}
```

---

### POST /chat

Streaming audit with SSE (Server-Sent Events).

**Headers**: `X-User-ID` (required)

**Request Body**: Same as `/check`

**Response**: `text/event-stream`

```
data: {"type": "token", "content": "Analyzing"}
data: {"type": "token", "content": " your"}
data: {"type": "token", "content": " code..."}
data: {"type": "node_done", "node": "analyze"}
data: {"type": "node_done", "node": "evaluate"}
data: {"type": "result", "data": {"violations": [...], "summary": "...", "score": {...}}}
data: [DONE]
```

---

### GET /history/audits

List the authenticated user's past audits.

**Headers**: `X-User-ID` (required)

**Response** `200 OK`:
```json
[
  {
    "id": "audit-uuid",
    "input_type": "code",
    "input_content": "<html>...</html>",
    "summary": "Found 3 violations...",
    "score": {"A": 80, "AA": 85, "AAA": 90, "total": 83},
    "created_at": "2026-06-14T10:00:00Z"
  }
]
```

---

### GET /history/audits/{id}

Get a single audit with its violations.

**Headers**: `X-User-ID` (required)

**Response** `200 OK`:
```json
{
  "id": "audit-uuid",
  "input_type": "code",
  "input_content": "<html>...</html>",
  "summary": "Found 3 violations...",
  "score": {"A": 80, "AA": 85, "AAA": 90, "total": 83},
  "created_at": "2026-06-14T10:00:00Z",
  "violations": [
    {
      "criterion_id": "1.1.1",
      "title": "Non-text Content",
      "level": "A",
      "issue": "Image missing alt attribute",
      "element": "<img>",
      "fix": "Add alt text",
      "explanation": "..."
    }
  ]
}
```

---

## QA Service

**Internal URL**: `http://qa-service:8004`

### POST /chat/qa

RAG-based conversational Q&A with SSE streaming.

**Headers**: `X-User-ID` (required)

**Request Body**:
```json
{
  "message": "What does WCAG 2.1 say about keyboard navigation?",
  "conversation_id": "optional-conv-uuid",
  "history": [
    {"role": "user", "content": "Previous question"},
    {"role": "assistant", "content": "Previous answer"}
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `message` | `string` | User's question |
| `conversation_id` | `string?` | Continue existing conversation |
| `history` | `MessageItem[]` | Conversation context |

**Response**: `text/event-stream`

```
data: {"conversation_id": "conv-uuid"}
data: {"type": "token", "content": "WCAG"}
data: {"type": "token", "content": " 2.1"}
data: {"type": "token", "content": " requires..."}
data: [DONE]
```

---

### WebSocket /ws/qa

Full-duplex real-time Q&A with Redis Pub/Sub synchronization.

**Connection**: `ws://localhost:8000/ws/qa?token=<jwt>`

#### Client → Server Messages

**Subscribe to conversation**:
```json
{
  "type": "subscribe",
  "conversation_id": "conv-uuid"
}
```

**Send message**:
```json
{
  "message": "What is WCAG 1.1.1?",
  "conversation_id": "conv-uuid",
  "history": [{"role": "user", "content": "..."}]
}
```

#### Server → Client Messages

**Subscription confirmed**:
```json
{"type": "subscribed", "conversation_id": "conv-uuid"}
```

**Streaming token**:
```json
{"type": "token", "content": "WCAG"}
```

**Stream complete**:
```json
{"type": "done"}
```

**Error**:
```json
{"type": "error", "content": "Error description"}
```

---

## History Service

**Internal URL**: `http://history-service:8005`

### GET /history/chats

List paginated conversations.

**Headers**: `X-User-ID` (required)

**Query Parameters**:

| Param | Type | Default | Max | Description |
|---|---|---|---|---|
| `page` | `int` | 1 | — | Page number |
| `per_page` | `int` | 20 | 100 | Items per page |

**Response** `200 OK`:
```json
[
  {
    "id": "conv-uuid",
    "title": "WCAG keyboard navigation",
    "created_at": "2026-06-14T10:00:00Z"
  }
]
```

---

### GET /history/chats/{id}

Get a conversation with all messages.

**Response** `200 OK`:
```json
{
  "id": "conv-uuid",
  "title": "WCAG keyboard navigation",
  "created_at": "2026-06-14T10:00:00Z",
  "messages": [
    {"role": "user", "content": "What is WCAG?", "created_at": "2026-06-14T10:00:00Z"},
    {"role": "assistant", "content": "WCAG stands for...", "created_at": "2026-06-14T10:00:01Z"}
  ]
}
```

---

### GET /history/audits

List paginated audits (reads from audit replica database).

**Query Parameters**: Same as `/history/chats`

**Response**: Same format as Audit Service `/history/audits`

---

### GET /history/audits/{id}

Get audit with violations (reads from audit replica database).

**Response**: Same format as Audit Service `/history/audits/{id}`

---

### GET /history/search

Full-text search across audits and conversations.

**Headers**: `X-User-ID` (required)

**Query Parameters**: `q` (required) — search term

**Response** `200 OK`:
```json
{
  "query": "keyboard",
  "audits": [
    {"id": "audit-uuid", "input_content": "...", "summary": "...keyboard...", "created_at": "..."}
  ],
  "chats": [
    {"id": "conv-uuid", "title": "keyboard navigation", "created_at": "..."}
  ]
}
```

---

### GET /history/stats

Dashboard aggregate statistics.

**Headers**: `X-User-ID` (required)

**Response** `200 OK`:
```json
{
  "total_audits": 42,
  "average_score": 78.5,
  "trend": [
    {"score": 75, "date": "2026-06-10"},
    {"score": 80, "date": "2026-06-11"},
    {"score": 82, "date": "2026-06-12"}
  ]
}
```

---

## Criteria Service

**Internal URL**: `http://criteria-service:8006`

### GET /criteria

List all WCAG criteria from Qdrant vector store.

**Query Parameters**:

| Param | Type | Description |
|---|---|---|
| `level` | `string?` | Filter by level: `A`, `AA`, `AAA` |
| `principle` | `string?` | Filter by principle |

**Response** `200 OK`:
```json
{
  "criteria": [
    {
      "criterion_id": "1.1.1",
      "title": "Non-text Content",
      "level": "A",
      "text": "All non-text content...",
      "principle": "Perceivable"
    }
  ],
  "total": 78
}
```

---

### GET /criteria/search

Keyword search across WCAG criteria in Qdrant.

**Query Parameters**: `q` (required)

**Response** `200 OK`:
```json
{
  "criteria": [...],
  "total": 5
}
```

---

### GET /criteria/{id}

Get a single WCAG criterion by ID (e.g., `1.1.1`).

**Response** `200 OK`:
```json
{
  "criterion_id": "1.1.1",
  "title": "Non-text Content",
  "level": "A",
  "text": "All non-text content that is presented to the user...",
  "principle": "Perceivable"
}
```

---

### POST /criteria/ingest

Admin endpoint to trigger WCAG criteria re-ingestion (proxies to Ingestion Service).

**Request Body**: Optional (forwarded as-is to ingestion service)

**Response**: Proxied response from Ingestion Service `/ingest`

---

## Ingestion Service

**Internal URL**: `http://ingestion-service:8007`

### POST /ingest

Trigger the WCAG document ingestion pipeline.

**Request Body**:
```json
{
  "max_pages": 50,
  "batch_size": 32,
  "refresh_cache": false,
  "dry_run": false,
  "include_apg": false
}
```

| Field | Type | Default | Range | Description |
|---|---|---|---|---|
| `max_pages` | `int` | 50 | 1-1000 | Maximum pages to crawl |
| `batch_size` | `int` | 32 | 1-256 | Embedding batch size |
| `refresh_cache` | `bool` | false | — | Bypass local HTML cache |
| `dry_run` | `bool` | false | — | Parse without upserting to Qdrant |
| `include_apg` | `bool` | false | — | Include APG (ARIA Practices Guide) |

**Response** `200 OK`:
```json
{
  "status": "completed",
  "message": "Ingestion completed successfully",
  "documents_parsed": 118,
  "chunks_ingested": 403,
  "doc_type_counts": {
    "guideline": 13,
    "success_criterion": 78,
    "technique": 27
  },
  "chunk_type_counts": {
    "criterion": 234,
    "technique": 169
  }
}
```

---

## Scraper Worker

**Not an HTTP service** — runs as an async SQS consumer process.

### SQS Message: Scrape Request

**Queue**: `scrape-requests`

```json
{
  "job_id": "job-uuid",
  "url": "https://example.com",
  "user_id": "user-uuid",
  "priority": 0,
  "created_at": "2026-06-14T10:00:00Z"
}
```

### SQS Message: Scrape Result

**Queue**: `scrape-results`

```json
{
  "job_id": "job-uuid",
  "url": "https://example.com",
  "s3_key": "scrapes/job-uuid.html",
  "html_content": null,
  "status": "success",
  "error_message": null,
  "scraped_at": "2026-06-14T10:00:05Z"
}
```

### Redis Job Status

**Key**: `job:{job_id}` (TTL: 1 hour)

```json
{
  "status": "success",
  "url": "https://example.com",
  "s3_key": "scrapes/job-uuid.html",
  "updated_at": "2026-06-14T10:00:05Z"
}
```

---

## Shared Models

All shared Pydantic models are defined in `packages/wcag-common/wcag_common/models/`:

### Auth Models (`models/auth.py`)

| Model | Fields |
|---|---|
| `UserCreate` | `email: EmailStr`, `password: str(8-128)` |
| `UserResponse` | `id: str`, `email: EmailStr`, `created_at: datetime` |
| `TokenResponse` | `access_token: str`, `refresh_token: str?`, `token_type: str`, `user: UserResponse` |
| `TokenPayload` | `sub: str`, `exp: datetime`, `iat: datetime`, `token_type: "access" \| "refresh"` |

### Audit Models (`models/audit.py`)

| Model | Fields |
|---|---|
| `AuditRequest` | `input: str`, `session_id: str?` |
| `ViolationSchema` | `criterion_id: str`, `title: str`, `level: "A"\|"AA"\|"AAA"`, `issue: str`, `element: str?`, `fix: str?`, `explanation: str?` |
| `ScoreSchema` | `A: int`, `AA: int`, `AAA: int`, `total: int` |
| `AuditResponse` | `id: str`, `input_type: str`, `input_content: str`, `summary: str`, `score: ScoreSchema`, `violations: ViolationSchema[]`, `created_at: datetime` |

### Chat Models (`models/chat.py`)

| Model | Fields |
|---|---|
| `MessageItem` | `role: "user"\|"assistant"\|"system"`, `content: str` |
| `ChatRequest` | `input: str`, `session_id: str?` |
| `QARequest` | `message: str`, `conversation_id: str?`, `history: MessageItem[]` |
| `ConversationResponse` | `id: str`, `title: str`, `created_at: datetime`, `messages: MessageItem[]` |

### Queue Models (`models/queue.py`)

| Model | Fields |
|---|---|
| `ScrapeRequest` | `job_id: str`, `url: str`, `user_id: str`, `priority: int`, `created_at: datetime` |
| `ScrapeResult` | `job_id: str`, `url: str`, `s3_key: str?`, `html_content: str?`, `status: str`, `error_message: str?`, `scraped_at: datetime` |
| `AuditTask` | `job_id: str`, `user_id: str`, `input_type: str`, `input_content: str`, `created_at: datetime` |
| `AuditResult` | `job_id: str`, `audit_id: str`, `status: str`, `error_message: str?`, `created_at: datetime` |
| `NotificationTask` | `user_id: str`, `notification_type: str`, `payload: dict`, `created_at: datetime` |

---

## Error Responses

All services return errors in the standard format:

```json
{
  "detail": "Human-readable error message"
}
```

### Common HTTP Status Codes

| Code | Meaning | Typical Causes |
|---|---|---|
| `400` | Bad Request | Invalid input, missing fields, validation error |
| `401` | Unauthorized | Missing/invalid/expired JWT |
| `403` | Forbidden | Insufficient permissions |
| `404` | Not Found | Resource doesn't exist |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Unexpected server error |
| `502` | Bad Gateway | Downstream service unavailable |

---

## Health Checks

All services expose a `GET /health` endpoint returning:

```json
{
  "status": "healthy",
  "service": "service-name",
  "dependencies": {
    "redis": "connected",
    "postgres": "connected",
    "qdrant": "connected"
  }
}
```

Kubernetes liveness/readiness probes target this endpoint.
