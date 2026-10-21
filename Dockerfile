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
    UV_LINK_MODE=copy

WORKDIR /app

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
CMD ["sh", "-c", "uv run --no-sync uvicorn disputepilot.web:app --host 0.0.0.0 --port ${PORT:-8000}"]

