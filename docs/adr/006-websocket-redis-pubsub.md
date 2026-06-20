# ADR 006: WebSocket + Redis Pub/Sub for Real-Time Chat

- **Status**: Accepted
- **Date**: 2026-06-13
- **Decision Makers**: Architecture Team

## Context

The QA Service provides a conversational RAG chatbot for WCAG accessibility questions. Initially, the service only supported HTTP SSE (Server-Sent Events) for streaming responses. However, SSE has limitations:

| Aspect | SSE | WebSocket |
|---|---|---|
| Direction | Server → Client only | Full duplex |
| Connection | HTTP/1.1 long-poll | Persistent TCP upgrade |
| Multi-instance sync | ❌ Not possible | ✅ Via Pub/Sub backplane |
| Client sends during stream | ❌ New HTTP request needed | ✅ Same connection |

With horizontal pod autoscaling (HPA), the QA Service runs multiple replicas. A user connected to Pod A cannot see messages from Pod B unless there's a synchronization mechanism.

## Decision

**Implement WebSocket endpoints with Redis Pub/Sub** as the multi-instance message backplane.

### Architecture

```
Client A ──ws──▶ QA Pod 1 ──publish──▶ Redis Channel (conv:{id})
Client B ──ws──▶ QA Pod 2 ◀─subscribe── Redis Channel (conv:{id})
```

### Flow

1. Client connects to `WS /ws/qa`
2. Client sends `{"type": "subscribe", "conversation_id": "..."}`
3. Server spawns an async task that subscribes to `conv:{conversation_id}` Redis channel
4. When a message is sent, the handling pod:
   a. Streams response tokens directly to the connected WebSocket
   b. Publishes each token chunk to the Redis channel
5. Other pods subscribed to the same channel forward tokens to their connected clients

### Connection Manager

A `ConnectionManager` class tracks active WebSocket connections per pod:
- `connect(websocket)` — registers and accepts
- `disconnect(websocket)` — removes from active set
- `send_personal_message(message, websocket)` — unicast
- `broadcast(message)` — fan-out to all connections on this pod

## Consequences

### Positive
- **True real-time**: Sub-second message delivery across pods
- **Scalable**: Adding QA pods doesn't break chat coherence
- **SSE preserved**: Existing SSE endpoints remain for backward compatibility
- **Efficient**: Redis Pub/Sub is fire-and-forget with minimal overhead (~0.1ms per publish)

### Negative
- **Sticky sessions not guaranteed**: Load balancer may route reconnects to different pods (acceptable — Redis syncs state)
- **No message persistence in Pub/Sub**: If a pod is down during publish, it misses the message. Historical messages are loaded from PostgreSQL on reconnect
- **WebSocket connection management**: Need graceful handling of disconnects, timeouts, and heartbeats

### Mitigations
- Kubernetes Ingress routes `/ws` paths directly to QA Service (bypassing API Gateway for persistent connections)
- Client-side reconnection logic with exponential backoff
- PostgreSQL `messages` table provides durable message history independent of Pub/Sub
