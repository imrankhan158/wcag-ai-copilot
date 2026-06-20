# ADR 001: RabbitMQ / SQS Over Kafka for Async Messaging

- **Status**: Accepted
- **Date**: 2026-06-11
- **Decision Makers**: Architecture Team

## Context

The WCAG AI Copilot platform requires an asynchronous message queue to decouple the API Gateway and Scraper Worker service. When a user submits a URL for accessibility auditing, the gateway enqueues a scrape request, and the worker processes it asynchronously.

We evaluated three options:

| Option | Pros | Cons |
|---|---|---|
| **RabbitMQ** | Mature, lightweight, excellent single-queue routing, low latency | Not designed for event streaming / replay |
| **Apache Kafka** | High throughput, event replay, log compaction | Operational complexity (ZooKeeper/KRaft), overkill for task queues |
| **AWS SQS** | Fully managed, zero ops, pay-per-use, built-in DLQ | Vendor lock-in, no local dev parity without emulators |

## Decision

**Use SQS-compatible messaging** (AWS SQS in production, LocalStack or ElasticMQ for local development).

For our use case, messages are **tasks** (scrape this URL), not **events** (something happened). We need:
- At-least-once delivery with visibility timeouts
- Dead-letter queues for poison messages
- Simple point-to-point consumption (one worker processes each message)

Kafka's event streaming, log retention, and consumer group rebalancing add unnecessary operational complexity for a task queue pattern. RabbitMQ would work but adds another stateful service to manage — SQS eliminates this.

## Consequences

### Positive
- Zero infrastructure to manage for the message queue layer
- Built-in dead-letter queue support via `RedrivePolicy`
- Local development uses `boto3` against LocalStack with identical API
- Cost scales linearly with usage (no idle broker costs)

### Negative
- Maximum message size is 256 KB (mitigated by storing HTML payloads in S3)
- No built-in message replay (acceptable — scrape tasks are idempotent)
- Vendor coupling to AWS SDK (`boto3`) — abstracted behind `wcag-common` wrappers

### Mitigations
- HTML content stored in S3 with presigned URLs, keeping SQS messages small
- `wcag-common.sqs` wrapper abstracts the queue interface for future portability
- `wcag-common.s3` wrapper does the same for object storage
