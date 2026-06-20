# WCAG AI Copilot — Operations Runbook

> Standard operating procedures for deploying, monitoring, and troubleshooting the WCAG AI Copilot platform.

---

## Table of Contents

- [Local Development Setup](#local-development-setup)
- [Docker Compose Operations](#docker-compose-operations)
- [Local Kubernetes (Kind + Skaffold)](#local-kubernetes)
- [Production Deployment (Kubernetes)](#production-deployment)
- [CI/CD Pipeline (Jenkins)](#cicd-pipeline)
- [Database Operations](#database-operations)
- [Monitoring & Observability](#monitoring--observability)
- [Troubleshooting Guide](#troubleshooting-guide)
- [Incident Response](#incident-response)

---

## Local Development Setup

### Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12+ | Runtime |
| uv | Latest | Python package manager |
| Docker | 24+ | Container runtime |
| Docker Compose | v2.20+ | Local orchestration |
| Node.js | 20+ | Frontend build |
| Kind | Latest | Local Kubernetes (optional) |
| Skaffold | v2.x | K8s dev workflow (optional) |
| kubectl | Latest | K8s CLI (optional) |
| Helm | v3.x | Chart management (optional) |

### Initial Setup

```bash
# Clone the repository
git clone <repo-url>
cd wcag-ai-copilot

# Create .env file from template
cp .env.example .env
# Edit .env with your API keys (OPENAI_API_KEY, etc.)

# Install Python dependencies (workspace mode)
uv sync

# Start all infrastructure + services
docker compose up -d

# Verify all services are healthy
curl http://localhost:8000/health    # API Gateway
curl http://localhost:8007/health    # Ingestion Service (only other exposed port)
```

### Required Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key for LLM calls |
| `POSTGRES_USER` | — | `admin` | Database username |
| `POSTGRES_PASSWORD` | — | `admin123` | Database password |
| `REDIS_URL` | — | `redis://localhost:6379/0` | Redis connection URL |
| `QDRANT_URL` | — | `http://localhost:6333` | Qdrant vector DB URL |
| `JWT_PRIVATE_KEY` | — | Dev key | RSA private key for Auth Service |
| `JWT_PUBLIC_KEY` | — | Dev key | RSA public key for JWT verification |
| `AWS_ENDPOINT_URL` | — | `http://localhost:4566` | LocalStack/Floci endpoint |

### Seed WCAG Data

After first startup, seed the Qdrant vector store:

```bash
# Trigger ingestion (dry run first)
curl -X POST http://localhost:8007/ingest \
  -H "Content-Type: application/json" \
  -d '{"dry_run": true, "max_pages": 5}'

# Full ingestion
curl -X POST http://localhost:8007/ingest \
  -H "Content-Type: application/json" \
  -d '{"max_pages": 50, "batch_size": 32}'
```

---

## Docker Compose Operations

### Service Management

```bash
# Start all services
docker compose up -d

# Start specific services
docker compose up -d api-gateway auth-service audit-service

# View logs (follow mode)
docker compose logs -f api-gateway
docker compose logs -f audit-service qa-service

# Restart a service
docker compose restart audit-service

# Rebuild and restart a service after code changes
docker compose up -d --build audit-service

# Stop all services
docker compose down

# Stop and remove volumes (⚠️ destroys data)
docker compose down -v
```

### Service Health Checks

```bash
# Check all services
for port in 8000 8001 8003 8004 8005 8006 8007; do
  echo "Port $port: $(curl -s http://localhost:$port/health | jq -r '.status // .detail // "ERROR"')"
done
```

### Port Reference

| Port | Service |
|---|---|
| 3001 | Frontend (NGINX) |
| 4566 | Floci/LocalStack (SQS, S3) |
| 5432 | PostgreSQL primary (master) |
| 5442 | PostgreSQL replica (standby) |
| 6333 | Qdrant HTTP |
| 6379 | Redis |
| 6432 | PgBouncer primary pool (write) |
| 6433 | PgBouncer replica pool (read-only) |
| 8000 | API Gateway |
| 8007 | Ingestion Service |

---

## Local Kubernetes

### Setup Kind Cluster

```bash
# Create a Kind cluster
kind create cluster --name wcag-copilot

# Verify the cluster is running
kubectl cluster-info --context kind-wcag-copilot

# Load pre-built images into Kind (if not using Skaffold)
kind load docker-image api-gateway:latest --name wcag-copilot
```

### Deploy with Skaffold

```bash
# Dev mode (auto-rebuild on file changes)
skaffold dev

# One-shot deploy
skaffold run

# Port forwarding (automatic in dev mode)
# api-gateway → localhost:8000
# frontend → localhost:3001

# Cleanup
skaffold delete
```

### Deploy with Helm (Manual)

```bash
# Install the chart
helm install wcag-copilot deploy/charts/wcag-copilot \
  --namespace wcag-production \
  --create-namespace \
  --values deploy/charts/wcag-copilot/values.yaml

# Upgrade after changes
helm upgrade wcag-copilot deploy/charts/wcag-copilot \
  --namespace wcag-production

# Check status
helm status wcag-copilot -n wcag-production

# Uninstall
helm uninstall wcag-copilot -n wcag-production
```

### Kubernetes Debugging

```bash
# List all pods
kubectl get pods -n wcag-production

# Check pod logs
kubectl logs -f deployment/api-gateway -n wcag-production

# Describe a failing pod
kubectl describe pod <pod-name> -n wcag-production

# Exec into a pod
kubectl exec -it deployment/audit-service -n wcag-production -- /bin/sh

# Check HPA status
kubectl get hpa -n wcag-production

# Check network policies
kubectl get networkpolicy -n wcag-production
```

---

## Production Deployment

### Pre-Deployment Checklist

- [ ] All tests pass in CI (`uv run pytest` per service)
- [ ] Docker images built and pushed to ECR
- [ ] Database migrations reviewed (`alembic upgrade head` runs as pre-install hook)
- [ ] Environment secrets updated in AWS Secrets Manager
- [ ] Helm values reviewed for correct replica counts and resource limits
- [ ] Network policies verified (no unintended exposure)

### Rolling Deployment

```bash
# Update the Helm release
helm upgrade wcag-copilot deploy/charts/wcag-copilot \
  --namespace wcag-production \
  --set global.image.tag=v1.2.3

# Monitor the rollout
kubectl rollout status deployment/api-gateway -n wcag-production
kubectl rollout status deployment/audit-service -n wcag-production

# Rollback if needed
kubectl rollout undo deployment/api-gateway -n wcag-production
helm rollback wcag-copilot 1 -n wcag-production
```

### Scaling

```bash
# Manual scaling
kubectl scale deployment audit-service --replicas=10 -n wcag-production

# HPA handles automatic scaling based on CPU:
# api-gateway: 3→20 pods (60% CPU target)
# audit-service: 3→30 pods (70% CPU target)
# scraper-worker: 2→50 pods (80% CPU target)
# See values.yaml for full HPA configuration
```

---

## CI/CD Pipeline

### Jenkins Pipeline Stages

```
1. Detect Changes
   └── Git diff against origin/main
   └── Determines which services need rebuild
   └── Changes to wcag-common → rebuild ALL services

2. Parallel Verification (per changed service)
   └── uv run --project services/<service> pytest

3. Docker Compilation & Push
   └── Build multi-stage Docker images
   └── Push to ECR: <account>.dkr.ecr.us-east-1.amazonaws.com/<service>
   └── Tags: build number + latest
```

### Triggering a Build

- **Automatic**: Push to `main` or open a PR
- **Manual**: Jenkins UI → Build with Parameters

### Debugging Failed Builds

1. Check Jenkins console output for the failing stage
2. Common failures:
   - **Test failures**: Fix tests, push, re-trigger
   - **Docker build failures**: Check Dockerfile and dependencies
   - **ECR push failures**: Verify AWS credentials and ECR repository existence

---

## Database Operations

### Partition Maintenance

Partitions are auto-created at service startup for current + next month. As a safety net:

```sql
-- Create next month's partition manually (example for July 2026)
CREATE TABLE IF NOT EXISTS audits_2026_07
  PARTITION OF audits
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS audit_violations_2026_07
  PARTITION OF audit_violations
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

CREATE TABLE IF NOT EXISTS messages_2026_07
  PARTITION OF messages
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');
```

### Replication Status Check

```sql
-- On primary: check replication slots
SELECT * FROM pg_replication_slots;

-- On primary: check streaming status
SELECT client_addr, state, sent_lsn, write_lsn, replay_lsn
FROM pg_stat_replication;

-- On replica: verify standby mode
SELECT pg_is_in_recovery();  -- Should return true
```

### PgBouncer Status

```bash
# Connect to Primary PgBouncer admin console
psql -h localhost -p 6432 -U admin pgbouncer

# Connect to Replica PgBouncer admin console
psql -h localhost -p 6433 -U admin pgbouncer

# Check connection pools (inside PgBouncer CLI)
SHOW POOLS;

# Check active clients
SHOW CLIENTS;

# Check server connections
SHOW SERVERS;
```

### Backup & Restore

```bash
# Backup the consolidated database
pg_dump -h localhost -p 5432 -U admin wcag_copilot > backup_copilot_$(date +%Y%m%d).sql

# Restore
psql -h localhost -p 5432 -U admin wcag_copilot < backup_copilot_20260614.sql
```

---

## Monitoring & Observability

### Prometheus Metrics

All services expose `/metrics` with:

| Metric | Type | Description |
|---|---|---|
| `http_requests_total` | Counter | Total HTTP requests by method, path, status |
| `http_request_duration_seconds` | Histogram | Request latency distribution |
| `http_requests_in_progress` | Gauge | Currently active requests |

### Structured Logging

All services emit structured JSON logs with correlation IDs:

```json
{
  "timestamp": "2026-06-14T10:00:00.000Z",
  "level": "INFO",
  "service": "audit-service",
  "request_id": "abc-123-def",
  "message": "Audit completed",
  "user_id": "user-uuid",
  "duration_ms": 3450
}
```

**Correlation tracing**: The `request_id` header propagates across services via the `CorrelationMiddleware`, enabling end-to-end request tracing.

### OpenTelemetry

Traces are exported to the OTEL collector at `http://otel-collector:4317` (configurable via Helm values).

### Key Dashboards to Build

1. **Request Rate**: `rate(http_requests_total[5m])` by service
2. **Error Rate**: `rate(http_requests_total{status=~"5.."}[5m])`
3. **P99 Latency**: `histogram_quantile(0.99, http_request_duration_seconds_bucket)`
4. **HPA Scale Events**: `kube_hpa_status_current_replicas`

---

## Troubleshooting Guide

### Service Won't Start

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Connection refused` on DB port | PgBouncer or PostgreSQL not ready | Check `docker compose logs <db-service>` |
| `Redis connection error` | Redis not running | `docker compose up -d redis` |
| `Qdrant connection refused` | Qdrant cluster unhealthy | Check `docker compose logs qdrant-node-1` |
| `ModuleNotFoundError: wcag_common` | Dependencies not installed | `uv sync` from root |
| `JWT decode error` | Public/private key mismatch | Regenerate RS256 keys, update `.env` |

### Audit Returns Empty Results

1. Check Qdrant has data: `curl http://localhost:6333/collections/wcag_criteria`
2. If empty, run ingestion: `curl -X POST http://localhost:8007/ingest -H "Content-Type: application/json" -d '{}'`
3. Check LLM API key: Verify `OPENAI_API_KEY` is set and valid
4. Check circuit breaker: Look for "circuit open" in audit-service logs

### WebSocket Connection Drops

1. Check Ingress routes `/ws` to QA Service (not through API Gateway)
2. Verify Redis is running (Pub/Sub backplane)
3. Check client-side reconnection logic
4. Review `qa-service` logs for error traces

### High Latency

1. Check HPA: `kubectl get hpa -n wcag-production` — is it scaling?
2. Check PgBouncer pool saturation: `SHOW POOLS;` — look for `sv_active` = `sv_used`
3. Check Redis memory: `redis-cli INFO memory`
4. Check LLM API latency: Look for `duration_ms` in structured logs

### Database Replication Lag

```sql
-- Check lag in bytes
SELECT pg_wal_lsn_diff(sent_lsn, replay_lsn) AS lag_bytes
FROM pg_stat_replication;
```

If lag > 100MB:
1. Check replica CPU/IO
2. Consider adding more replicas
3. Temporarily redirect reads to primary

---

## Incident Response

### Severity Levels

| Level | Description | Response Time | Examples |
|---|---|---|---|
| **P1 - Critical** | Service fully down | < 15 min | API Gateway crash, all DBs down |
| **P2 - Major** | Feature degraded | < 1 hour | Audit service errors, WebSocket down |
| **P3 - Minor** | Non-critical issue | < 4 hours | Slow queries, cache misses |
| **P4 - Low** | Cosmetic/minor | Next business day | Log noise, metric gaps |

### P1 Playbook

1. **Identify**: Check health endpoints and pod status
2. **Mitigate**: Scale up healthy instances, failover if needed
3. **Communicate**: Alert stakeholders
4. **Investigate**: Check logs with correlation ID
5. **Resolve**: Deploy fix or rollback
6. **Post-mortem**: Document root cause and preventive actions

### Rollback Procedure

```bash
# Kubernetes rollback
kubectl rollout undo deployment/<service> -n wcag-production

# Helm rollback to previous revision
helm rollback wcag-copilot <revision> -n wcag-production

# Docker Compose rollback
git checkout <previous-tag>
docker compose up -d --build
```
