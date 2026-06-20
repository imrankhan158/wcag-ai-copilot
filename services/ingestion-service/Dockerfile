# =============================================================================
# WCAG AI Copilot — Ingestion Service Dockerfile
# =============================================================================
FROM python:3.12-slim

# Avoid interactive prompts and unbuffer output
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install system dependencies needed for installation and curl
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

# Copy workspaces manifests
COPY pyproject.toml uv.lock ./
COPY packages/wcag-common/ packages/wcag-common/
COPY services/ingestion-service/ services/ingestion-service/

# Sync python dependencies into virtualenv
RUN uv sync --frozen --no-dev

# Install Playwright Chromium binaries and its system dependencies
RUN uv run playwright install chromium
RUN uv run playwright install-deps chromium

# Set working directory to ingestion service folder
WORKDIR /app/services/ingestion-service

# Run uvicorn server on port 8007
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8007"]
