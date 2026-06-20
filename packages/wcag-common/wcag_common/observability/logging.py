from __future__ import annotations

import contextvars
import json
import logging
import sys
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from uuid import uuid4

# Context variables for tracing request context in async logs
request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="")


class JSONFormatter(logging.Formatter):
    """Logging Formatter that outputs JSON strings."""
    
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "filename": record.filename,
            "line_number": record.lineno,
            "service": self.service_name,
        }
        
        # Pull correlation variables from ContextVar
        req_id = request_id_ctx.get()
        usr_id = user_id_ctx.get()
        
        if req_id:
            log_data["request_id"] = req_id
        if usr_id:
            log_data["user_id"] = usr_id
            
        # Add dynamic log record arguments if present
        if hasattr(record, "extra") and isinstance(record.extra, dict):
            log_data.update(record.extra)
            
        return json.dumps(log_data)


def setup_json_logging(service_name: str, log_level: str = "INFO") -> None:
    """Configures the root logger to output structured JSON."""
    logger = logging.getLogger()
    logger.setLevel(log_level)
    
    handler = logging.StreamHandler(sys.stdout)
    formatter = JSONFormatter(service_name)
    handler.setFormatter(formatter)
    
    logger.handlers.clear()
    logger.addHandler(handler)


class CorrelationMiddleware(BaseHTTPMiddleware):
    """FastAPI Middleware to intercept and populate correlation IDs in async contexts."""
    
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid4())
        usr_id = request.headers.get("X-User-ID") or "anonymous"
        
        token_req = request_id_ctx.set(req_id)
        token_usr = user_id_ctx.set(usr_id)
        
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_ctx.reset(token_req)
            user_id_ctx.reset(token_usr)
