from __future__ import annotations

import time
from fastapi import Request
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

# HTTP metrics
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total number of HTTP requests processed",
    ["method", "endpoint", "status_code", "service"]
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint", "service"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 30.0)
)

# LLM metrics
LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total input and output LLM tokens used",
    ["provider", "model", "token_type", "service"]
)


class PrometheusMetricsMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware to track HTTP request rates and latencies."""
    
    def __init__(self, app, service_name: str) -> None:
        super().__init__(app)
        self.service_name = service_name

    async def dispatch(self, request: Request, call_next):
        method = request.method
        endpoint = request.url.path
        start_time = time.time()
        
        try:
            response = await call_next(request)
            duration = time.time() - start_time
            status_code = str(response.status_code)
            
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code=status_code,
                service=self.service_name
            ).inc()
            
            HTTP_REQUEST_DURATION_SECONDS.labels(
                method=method,
                endpoint=endpoint,
                service=self.service_name
            ).observe(duration)
            
            return response
            
        except Exception as e:
            HTTP_REQUESTS_TOTAL.labels(
                method=method,
                endpoint=endpoint,
                status_code="500",
                service=self.service_name
            ).inc()
            raise e
