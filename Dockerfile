# Stage 1: Build React SPA frontend
FROM node:20-bookworm-slim AS frontend-builder
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend Application
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    DATA_DIR=/var/data/disputepilot \
    FRONTEND_DIST=/app/frontend/dist

WORKDIR /app

# Ensure persistent volume mount point exists
RUN mkdir -p /var/data/disputepilot && chmod 700 /var/data/disputepilot
VOLUME /var/data/disputepilot

COPY pyproject.toml uv.lock README.md CONTEXT.md ./
COPY src ./src
# Include only synthetic fixture inputs. Never bake runtime databases, user accounts,
# approvals, audit logs, drafts, or evidence into a production image.
COPY data/cases ./data/cases
COPY data/cases_messy ./data/cases_messy
COPY data/org_settings.json ./data/org_settings.json
COPY --from=frontend-builder /build/dist ./frontend/dist

RUN uv sync --frozen --no-dev

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request, os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/api/v1/health')" || exit 1

CMD ["sh", "-c", "uv run --no-sync uvicorn disputepilot.web:app --host 0.0.0.0 --port ${PORT:-8000}"]


