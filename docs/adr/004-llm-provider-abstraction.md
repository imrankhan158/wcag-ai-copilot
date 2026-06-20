# ADR 004: LLM Provider Abstraction with Circuit-Breaker Failover

- **Status**: Accepted
- **Date**: 2026-06-12
- **Decision Makers**: Architecture Team

## Context

The Audit Engine Service makes 3 sequential LLM calls per audit (analyze → evaluate → suggest). At scale (500K audits/day), this represents ~1.5M LLM API calls daily. A single provider outage would render the entire audit pipeline non-functional.

## Decision

**Implement a multi-provider LLM abstraction layer** with automatic failover using a simple circuit-breaker pattern.

### Provider Priority Chain

```
OpenAI (GPT-4o) → NVIDIA NIM → Local/Fallback
```

### Circuit-Breaker Logic

Each provider tracks:
- **Failure count**: Number of consecutive failures
- **Failure window**: 60-second sliding window
- **Trip threshold**: 5 failures within the window
- **Cooldown period**: 5 minutes after tripping

```python
# Simplified circuit-breaker state machine
CLOSED  ──(5 failures in 60s)──▶  OPEN  ──(5 min cooldown)──▶  HALF-OPEN
   ▲                                                              │
   └──────────────(success)──────────────────────────────────────┘
```

When a provider's circuit is OPEN, the system automatically falls through to the next provider in the chain.

## Consequences

### Positive
- **High availability**: Single provider outage does not break audits
- **Cost optimization**: Can route cheaper queries to NVIDIA/local models
- **Transparent switching**: Caller code uses `get_llm()` — unaware of provider selection
- **Token usage logging**: Each call logs model, token count, and estimated cost

### Negative
- **Response quality variance**: Different providers may produce different quality results
- **Configuration complexity**: Three sets of API keys and base URLs
- **No request-level retry**: Circuit breaker operates at the provider level, not per-request

### Mitigations
- Suggest node always uses the highest-quality available provider (GPT-4o preferred)
- Response caching (Redis, SHA-256 content hash, 24h TTL) reduces duplicate LLM calls by ~30%
- Embedding caching (Redis, 7-day TTL) eliminates redundant dense embedding API calls
