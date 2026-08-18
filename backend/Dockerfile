# ── Base ──────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencies ──────────────────────────────────────────────────────────────
FROM base AS deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Production ────────────────────────────────────────────────────────────────
FROM deps AS production
ENV ENV=production

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# ⚠️ `alembic/` AND `alembic.ini` MUST travel in the image. The sister product shipped a
# container that could not migrate because the Dockerfile copied only `app/`; the failure
# only shows on the first release that carries a migration, which is the worst moment to
# find out. `COPY . .` covers it, and `.dockerignore` is what keeps the image small.
COPY . .
RUN chown -R appuser:appgroup /app

USER appuser

# 🔴 THE SCHEMA IS APPLIED BY THE DEPLOYMENT, AND A FAILURE IS LOUD. `app/main.py` refuses
# to run migrations in its lifespan on purpose: the sister product does it there and
# swallows the error, so a broken chain is invisible twice — no test replays it and no
# alert follows it. Here `alembic upgrade head` runs BEFORE uvicorn and its failure stops
# the container, which restart-loops in plain sight rather than serving an old schema.
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8001 --workers 2"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1
