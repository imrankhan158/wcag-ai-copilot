import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, status, Header
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from wcag_common import BaseServiceSettings
from wcag_common.auth import (
    create_access_token,
    hash_password,
    verify_password,
    decode_access_token,
)
from wcag_common.models.auth import TokenResponse, UserCreate

from prometheus_client import make_asgi_app
from wcag_common.observability.logging import setup_json_logging, CorrelationMiddleware
from wcag_common.observability.metrics import PrometheusMetricsMiddleware
from wcag_common.observability.tracing import setup_opentelemetry

from session import Base, get_async_db, sync_engine
from models import User

# Logging setup
setup_json_logging("auth-service")
logger = logging.getLogger("auth-service")

# Settings
class AuthSettings(BaseServiceSettings):
    service_name: str = "auth-service"
    jwt_algorithm: str = "RS256"  # Enforce asymmetric signature
    jwt_access_token_expire_minutes: int = 60 * 24  # 1 day

settings = AuthSettings()
redis_client: aioredis.Redis | None = None

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_client
    logger.info("Initializing Auth Database schema...")
    # Synchronously check and create tables for simplicity
    Base.metadata.create_all(bind=sync_engine)
    logger.info("Auth Database tables checked/created.")

    logger.info("Connecting to Redis...")
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    logger.info("Connected to Redis successfully.")
    yield
    logger.info("Closing connections...")
    if redis_client:
        await redis_client.aclose()
    logger.info("Auth Service shut down complete.")


app = FastAPI(
    title="WCAG AI Copilot Auth Service",
    version="1.0.0",
    lifespan=lifespan,
)

# Instrument the app for observability
app.add_middleware(PrometheusMetricsMiddleware, service_name="auth-service")
app.add_middleware(CorrelationMiddleware)

# Initialize OpenTelemetry
setup_opentelemetry(app, "auth-service")

# Mount Prometheus metrics endpoint
app.mount("/metrics", make_asgi_app())



# Helper to get Redis client
async def get_redis() -> aioredis.Redis:
    if redis_client is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Redis client not initialized",
        )
    return redis_client


# Helper to calculate token hash/signature key for blacklist
def get_blacklist_key(token: str) -> str:
    # We can use the last signature portion or the whole token
    return f"blacklist:{token[-30:]}"


@app.post("/auth/register", response_model=TokenResponse)
async def register(req: UserCreate, db: AsyncSession = Depends(get_async_db)):
    # Check if user already exists
    result = await db.execute(select(User).where(User.email == req.email))
    existing_user = result.scalars().first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )

    # Hash password & create user
    hashed = hash_password(req.password)
    user = User(email=req.email, hashed_password=hashed)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Issue RS256 token containing email & id claims
    token = create_access_token(
        data={"sub": user.id, "email": user.email},
        secret_key=settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": user.id, "email": user.email, "created_at": user.created_at},
    )


@app.post("/auth/login", response_model=TokenResponse)
async def login(req: UserCreate, db: AsyncSession = Depends(get_async_db)):
    result = await db.execute(select(User).where(User.email == req.email))
    user = result.scalars().first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    token = create_access_token(
        data={"sub": user.id, "email": user.email},
        secret_key=settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
        expires_minutes=settings.jwt_access_token_expire_minutes,
    )
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user={"id": user.id, "email": user.email, "created_at": user.created_at},
    )


@app.post("/auth/logout")
async def logout(
    authorization: str | None = Header(None),
    redis: aioredis.Redis = Depends(get_redis)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Authorization header format",
        )
    token = authorization.split(" ")[1]
    
    # Decode token to check expiration time
    try:
        payload = decode_access_token(
            token,
            settings.jwt_public_key,
            algorithm=settings.jwt_algorithm
        )
        exp = payload.get("exp")
        if exp:
            now = datetime.now(timezone.utc).timestamp()
            ttl = int(exp - now)
            if ttl > 0:
                # Add to Redis blacklist with expiration matching the remaining token life
                blacklist_key = get_blacklist_key(token)
                await redis.set(blacklist_key, "1", ex=ttl)
                logger.info("Blacklisted token ending in %s for %d seconds", token[-10:], ttl)
    except Exception:
        # If decode fails, it is already expired or invalid
        pass

    return {"detail": "Successfully logged out"}


@app.get("/auth/validate")
async def validate_token(
    token: str,
    redis: aioredis.Redis = Depends(get_redis)
):
    """Internal validation route called by the API Gateway to verify RS256 JWTs."""
    # 1. Check blacklist first
    blacklist_key = get_blacklist_key(token)
    is_blacklisted = await redis.get(blacklist_key)
    if is_blacklisted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been blacklisted/logged out",
        )

    try:
        payload = decode_access_token(
            token,
            settings.jwt_public_key,
            algorithm=settings.jwt_algorithm,
        )
        return {
            "valid": True,
            "id": payload.get("sub"),
            "email": payload.get("email"),
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(exc)}",
        )


@app.get("/auth/me")
async def get_me(
    authorization: str | None = Header(None),
    db: AsyncSession = Depends(get_async_db),
    redis: aioredis.Redis = Depends(get_redis)
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credentials missing or invalid",
        )
    token = authorization.split(" ")[1]

    # Validate token
    val_resp = await validate_token(token, redis)
    user_id = val_resp["id"]

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return {"id": user.id, "email": user.email, "created_at": user.created_at.isoformat()}


@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_async_db)):
    """Service health check for container orchestration and docker compose."""
    try:
        # 1. Check database connection
        await db.execute(select(User).limit(1))
        # 2. Check Redis connection
        if redis_client:
            await redis_client.ping()
        return {
            "status": "healthy",
            "service": settings.service_name,
            "version": settings.service_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "service": settings.service_name,
                "detail": str(exc),
            },
        )
