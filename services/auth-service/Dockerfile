# =============================================================================
# WCAG AI Copilot — Auth Service Dockerfile
# =============================================================================
FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install system dependencies needed for compiling and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

# Copy workspace configuration and code
COPY pyproject.toml uv.lock ./
COPY packages/wcag-common/ packages/wcag-common/
COPY services/auth-service/ services/auth-service/

# Sync python dependencies into virtualenv
RUN uv sync --frozen --no-dev

# Set working directory to auth service folder
WORKDIR /app/services/auth-service

EXPOSE 8001

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# Start the FastAPI application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
