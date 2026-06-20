# ADR 005: Database-Per-Service with Replication and Partitioning

- **Status**: Accepted
- **Date**: 2026-06-13
- **Decision Makers**: Architecture Team

## Context

The monolith used a single PostgreSQL database (`wcag_db`) for all data. As services were extracted, each needed independent data ownership to avoid cross-service coupling and enable independent scaling of read/write workloads.

## Decision

**Each service owns its own database**, with replication for read scaling and range partitioning for high-growth tables.

### Database Topology

| Service | Database | Primary Port | Replica Port | Purpose |
|---|---|---|---|---|
| Auth Service | `wcag_auth` | 5434 | — | User credentials, sessions |
| Audit Service | `wcag_audits` | 5435 | 5437 | Audit results, violations |
| QA Service | `wcag_conversations` | 5436 | 5438 | Chat messages, sessions |
| History Service | (aggregates above) | — | — | Cross-DB reads via dual sessions |
| Criteria Service | (Qdrant) | 6333 | — | WCAG criteria vector index |

### Replication Strategy

```
Primary (read-write) ──streaming replication──▶ Replica (read-only hot standby)
         │                                              │
    PgBouncer (writes)                           PgBouncer (reads)
    transaction mode                             transaction mode
```

- Audit DB: 1 primary + 2 replicas (highest write volume)
- Conversations DB: 1 primary + 1 replica
- Auth DB: 1 primary only (low volume, high consistency requirements)

### Partitioning Strategy

High-growth tables use **monthly range partitioning** on `created_at`:

```sql
-- Parent table
CREATE TABLE audits (
    id VARCHAR(36) PRIMARY KEY,
    created_at TIMESTAMP NOT NULL,
    ...
) PARTITION BY RANGE (created_at);

-- Dynamic child partitions (auto-created at startup)
CREATE TABLE audits_2026_06 PARTITION OF audits
    FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
```

Partitioned tables:
- `audits` (Audit DB)
- `audit_violations` (Audit DB)
- `messages` (Conversations DB)

### PgBouncer Connection Pooling

All database connections route through PgBouncer sidecars in **transaction-level pooling** mode:

| Pooler | Upstream | Port | Mode |
|---|---|---|---|
| `auth-bouncer` | auth-postgres | 6434 | transaction |
| `audit-primary-bouncer` | audit-postgres-primary | 6435 | transaction |
| `conversations-primary-bouncer` | conv-postgres-primary | 6436 | transaction |
| `audit-replica-bouncer` | audit-postgres-replica | 6437 | transaction |
| `conversations-replica-bouncer` | conv-postgres-replica | 6438 | transaction |

## Consequences

### Positive
- **Independent scaling**: Audit writes can scale separately from chat reads
- **Query isolation**: Heavy history aggregations don't affect auth latency
- **Partition pruning**: Queries with date filters scan only relevant monthly partitions
- **Connection efficiency**: PgBouncer reduces PostgreSQL connection overhead by 10-50× at high concurrency

### Negative
- **Cross-service joins impossible**: History Service must query multiple databases sequentially
- **Operational complexity**: 3 database clusters + 5 PgBouncer instances to manage
- **Partition maintenance**: New partitions must be created before each month boundary

### Mitigations
- History Service uses Redis caching (5-min TTL) to reduce cross-DB query frequency
- FastAPI lifespan hooks auto-create partitions for current + next month at startup
- PgBouncer is deployed as a sidecar container — no additional infrastructure to manage
- Kubernetes CronJob can trigger partition creation as a safety net
