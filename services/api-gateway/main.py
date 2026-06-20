import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.background import BackgroundTask
import redis.asyncio as aioredis
import httpx
from prometheus_client import make_asgi_app

from wcag_common import BaseServiceSettings
from wcag_common.auth import decode_access_token
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

# Setup logging
setup_json_logging("api-gateway")
logger = logging.getLogger("api-gateway")


class GatewaySettings(BaseServiceSettings):
    service_name: str = "api-gateway"
    jwt_algorithm: str = "RS256"
    
    # Microservices URLs
    auth_service_url: str = "http://localhost:8001"
    audit_service_url: str = "http://localhost:8003"
    qa_service_url: str = "http://localhost:8004"
    history_service_url: str = "http://localhost:8005"
    criteria_service_url: str = "http://localhost:8006"
    
    # Rate Limiting
    rate_limit_enabled: bool = True
    rate_limit_capacity: float = 100.0  # Max request tokens in the bucket
    rate_limit_refill_rate: float = 2.0  # Tokens refilled per second (e.g., 2 req/sec = 120 req/min)


settings = GatewaySettings()

redis_client: aioredis.Redis | None = None
http_client: httpx.AsyncClient | None = None
rate_limit_script = None

# Lua script for token bucket rate limiting
# Key elements:
# KEYS[1]: client rate limiting key
# ARGV[1]: bucket capacity
# ARGV[2]: bucket refill rate (per second)
# ARGV[3]: current timestamp in seconds
LUA_RATE_LIMITER = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = 1

-- Fetch existing bucket state
local data = redis.call("HMGET", key, "tokens", "last_updated")
local tokens = tonumber(data[1])
local last_updated = tonumber(data[2])

if not tokens then
    -- Initialize the bucket
    tokens = capacity
    last_updated = now
else
    -- Refill tokens based on time elapsed
    local elapsed = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
    last_updated = now
end

-- Check if bucket has enough tokens
if tokens >= requested then
    tokens = tokens - requested
    redis.call("HMSET", key, "tokens", tokens, "last_updated", last_updated)
    -- Expire bucket state after it's fully refilled
    local ttl = math.ceil(capacity / refill_rate)
    redis.call("EXPIRE", key, ttl)
    return 0 -- NOT rate limited
else
    -- Save latest state even when rate-limited to avoid losing elapsed time
    redis.call("HMSET", key, "tokens", tokens, "last_updated", last_updated)
    local ttl = math.ceil(capacity / refill_rate)
    redis.call("EXPIRE", key, ttl)
    return 1 -- Rate limited
end
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client, http_client, rate_limit_script
    
    logger.info("Connecting to Redis...")
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    logger.info("Connected to Redis successfully.")
    
    # Register Lua Script
    rate_limit_script = redis_client.register_script(LUA_RATE_LIMITER)
    logger.info("Registered rate limiter Lua script on Redis client.")
    
    logger.info("Initializing HTTPX AsyncClient connection pool...")
    http_client = httpx.AsyncClient(
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=50),
        timeout=httpx.Timeout(180.0, connect=5.0)
    )
    
    yield
    
    logger.info("Shutting down API Gateway resources...")
    if redis_client:
        await redis_client.aclose()
    if http_client:
        await http_client.aclose()
    logger.info("API Gateway shut down complete.")


app = FastAPI(
    title="WCAG AI Copilot API Gateway",
    description="Edge API Gateway handles authentication token validation and rate-limiting",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware to allow React frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrument the app for observability
app.add_middleware(PrometheusMetricsMiddleware, service_name="api-gateway")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "api-gateway")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())


async def get_http_client() -> httpx.AsyncClient:
    if http_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="HTTP client pool not initialized",
        )
    return http_client


async def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Redis client not initialized",
        )
    return redis_client


# Helper function to extract user details if token is valid
async def authenticate_request(request: Request, redis: aioredis.Redis) -> tuple[str | None, str | None]:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None, None
        
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Must start with 'Bearer '.",
        )
        
    token = auth_header.split(" ")[1]
    
    # 1. Check Redis Token Blacklist
    # Note: Use last 30 characters of signature/token as the blacklist lookup key
    blacklist_key = f"blacklist:{token[-30:]}"
    try:
        is_blacklisted = await redis.get(blacklist_key)
        if is_blacklisted:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has been blacklisted/logged out",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Error checking token blacklist in Redis: {exc}")
        
    # 2. Decode and Validate RS256 token
    try:
        payload = decode_access_token(
            token,
            settings.jwt_public_key,
            algorithm=settings.jwt_algorithm
        )
        user_id = payload.get("sub")
        email = payload.get("email")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token missing subject ('sub') claim",
            )
        return str(user_id), email
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(exc)}",
        )


async def check_rate_limit(request: Request, user_id: str | None, redis: aioredis.Redis):
    if not settings.rate_limit_enabled:
        return
        
    if user_id:
        key = f"rate_limit:user:{user_id}"
    else:
        ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:ip:{ip}"
        
    try:
        now = time.time()
        is_limited = await rate_limit_script(
            keys=[key],
            args=[settings.rate_limit_capacity, settings.rate_limit_refill_rate, now]
        )
        if is_limited == 1:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
            )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(f"Rate limiting failure (failing open): {exc}")


async def forward_request(
    request: Request,
    target_url: str,
    client: httpx.AsyncClient,
    user_id: str | None = None,
    user_email: str | None = None
) -> Response:
    # Build proxy headers
    headers = dict(request.headers)
    headers.pop("host", None)  # Let HTTPX set host header dynamically
    
    # Inject X-User-ID and X-User-Email if authenticated
    if user_id:
        headers["X-User-ID"] = user_id
    if user_email:
        headers["X-User-Email"] = user_email
        
    # Extract request body
    body = await request.body()
    
    try:
        # Build request to forward
        req = client.build_request(
            method=request.method,
            url=target_url,
            headers=headers,
            params=request.query_params,
            content=body
        )
        
        # Stream response back
        resp = await client.send(req, stream=True)
        
        # Prepare response headers, stripping hop-by-hop ones
        resp_headers = {}
        for k, v in resp.headers.items():
            if k.lower() not in ("content-length", "transfer-encoding", "connection"):
                resp_headers[k] = v
                
        return StreamingResponse(
            resp.aiter_raw(),
            status_code=resp.status_code,
            headers=resp_headers,
            background=BackgroundTask(resp.aclose)
        )
    except httpx.HTTPError as exc:
        logger.error(f"Failed to proxy request to {target_url}: {exc}")
        return Response(
            content=f"Gateway Error: Target service unavailable ({str(exc)})",
            status_code=status.HTTP_502_BAD_GATEWAY
        )


# Local endpoints
@app.get("/health")
async def health(redis: aioredis.Redis = Depends(get_redis)):
    try:
        await redis.ping()
        return {
            "status": "healthy",
            "service": settings.service_name,
            "version": settings.service_version,
            "redis": "healthy",
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": settings.service_name,
                "redis": f"unhealthy: {str(exc)}",
            }
        )


# Proxy auth-service endpoints (e.g. POST /api/auth/login -> POST /auth/login)
@app.api_route("/api/auth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def route_auth(
    path: str,
    request: Request,
    client: httpx.AsyncClient = Depends(get_http_client),
    redis: aioredis.Redis = Depends(get_redis)
):
    # Determine if authentication validation is needed (skip for login / register)
    is_public = path in ("login", "register")
    
    user_id, user_email = None, None
    if not is_public:
        user_id, user_email = await authenticate_request(request, redis)
        
    # Apply Rate Limiting
    await check_rate_limit(request, user_id, redis)
    
    # Map external URL path `/api/auth/...` to downstream `/auth/...`
    target_url = f"{settings.auth_service_url}/auth/{path}"
    logger.info(f"Routing request to Auth Service: {request.method} {target_url}")
    return await forward_request(request, target_url, client, user_id, user_email)


# Proxy audit endpoints to audit-service (e.g. POST /api/check -> POST /check)
AUDIT_PATHS = {"check", "chat"}

@app.api_route("/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"])
async def route_api(
    path: str,
    request: Request,
    client: httpx.AsyncClient = Depends(get_http_client),
    redis: aioredis.Redis = Depends(get_redis)
):
    # Authenticate
    user_id, user_email = await authenticate_request(request, redis)
    
    # Apply Rate Limiting
    await check_rate_limit(request, user_id, redis)
    
    # Determine target service based on path
    root_path = path.split("/")[0] if path else ""
    
    if path == "chat/qa":
        target_url = f"{settings.qa_service_url}/{path}"
        logger.info(f"Routing request to QA Service: {request.method} {target_url}")
    elif root_path in AUDIT_PATHS:
        target_url = f"{settings.audit_service_url}/{path}"
        logger.info(f"Routing request to Audit Service: {request.method} {target_url}")
    elif root_path == "history":
        target_url = f"{settings.history_service_url}/{path}"
        logger.info(f"Routing request to History Service: {request.method} {target_url}")
    elif root_path == "criteria":
        target_url = f"{settings.criteria_service_url}/{path}"
        logger.info(f"Routing request to Criteria Service: {request.method} {target_url}")
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Route '/api/{path}' not found on gateway."
        )
    
    return await forward_request(request, target_url, client, user_id, user_email)
