# =============================================================================
# WCAG AI Copilot — Frontend Dockerfile
# Multi-stage build: Node builder → NGINX runtime
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Build the React + Vite application
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

# Copy dependency manifests first (maximise Docker layer cache)
COPY package.json package-lock.json ./

# Install dependencies with a clean, reproducible install
RUN npm ci

# Copy the rest of the frontend source
COPY . .

# Build for production
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Serve with NGINX
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

# Remove default nginx site config
RUN rm /etc/nginx/conf.d/default.conf

# Copy custom NGINX config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built static files from builder stage
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:80/ || exit 1

# NGINX runs in foreground by default with the official image's CMD
