# ADR 003: Strangler Fig Migration Pattern

- **Status**: Accepted
- **Date**: 2026-06-11
- **Decision Makers**: Architecture Team

## Context

The WCAG AI Copilot platform needed to transition from a single FastAPI monolith to a distributed microservices architecture. Two primary migration strategies were considered:

| Strategy | Description | Risk |
|---|---|---|
| **Big Bang** | Build all services in parallel, test in staging, cut over in one deployment | 🔴 High — single point of failure, extended feature freeze |
| **Strangler Fig** | Incrementally extract services, routing traffic gradually via an API Gateway | 🟢 Low — each phase is independently deployable and reversible |

## Decision

**Use the Strangler Fig pattern** with an 8-phase incremental migration plan.

Each phase extracts one or more bounded contexts from the monolith into standalone services. The API Gateway acts as the routing façade — the frontend client always hits the same base URL, and the gateway transparently routes to either the monolith or the new service.

## Migration Phases

```
Phase 1: Foundation (Redis, SQS, S3, wcag-common)
    ↓
Phase 2: Scraper Worker (async, decoupled)
    ↓
Phase 3: Auth Service + API Gateway
    ↓
Phase 4: Audit Engine (LangGraph)
    ↓
Phase 5: QA + History + Criteria Services
    ↓
Phase 6: Database Strategy (replication, partitioning)
    ↓
Phase 7: Ingestion Service
    ↓
Phase 8: Production Hardening (K8s, CI/CD, observability)
```

## Consequences

### Positive
- **Zero-downtime migration**: Each phase can be deployed independently
- **Reversibility**: If a new service fails, the gateway can route back to the monolith endpoint
- **Incremental testing**: Each service is tested in isolation before going live
- **Team parallelism**: Different teams can work on different phases concurrently
- **Risk isolation**: A failure in Phase 4 (Audit Engine) does not block Phase 5 (QA Service)

### Negative
- **Longer timeline**: 18-20 weeks vs. potentially 8-10 weeks for Big Bang
- **Temporary complexity**: During transition, both monolith and microservice code exists simultaneously
- **Gateway routing logic**: The API Gateway needs careful per-phase route configuration

### Mitigations
- Legacy monolith `app/` directory was fully deleted after Phase 5 completion (all routes migrated)
- Gateway routing is declarative (path-based prefix matching) — no complex logic
- Each phase has a dedicated walkthrough document for operational knowledge transfer
