#!/usr/bin/env bash
# LangAlpha sandbox installer.
#
# This script clones https://github.com/Chen-zexi/LangAlpha.git into ~/LangAlpha,
# applies the sandbox-specific Dockerfile patches in ./sandbox-patches.diff
# (CA bundle injection + Debian apt mirror bypass + Starlette<1.0 pin),
# then runs `docker compose up --build -d`.
#
# Prereqs on the host: docker + docker compose plugin, ip forwarding, and a
# CA bundle at /etc/ssl/certs/ca-certificates.crt that matches the TLS proxy
# the build will pass through. Network mode where containers can reach PyPI /
# Docker Hub is required.
#
# This is the procedure used to install LangAlpha inside the sandboxed dev
# environment on 2026-05-13. Re-run end-to-end on a fresh box; idempotent.

set -euo pipefail

LANGALPHA_DIR="${LANGALPHA_DIR:-$HOME/LangAlpha}"
PATCH_FILE="$(cd "$(dirname "$0")" && pwd)/sandbox-patches.diff"

if [ ! -d "$LANGALPHA_DIR/.git" ]; then
    git clone https://github.com/Chen-zexi/LangAlpha.git "$LANGALPHA_DIR"
fi

cd "$LANGALPHA_DIR"

# 1. Env file (placeholder API keys; user must edit before real use).
[ -f .env ] || cp .env.example .env

# 2. Empty file the compose mount expects (valuation-api binds it read-only).
[ -f gcp_credential.json ] || : > gcp_credential.json

# 3. CA bundle copied into the build context so the patched Dockerfiles can
#    COPY it. The sandbox proxy uses a self-signed root that containers
#    otherwise reject during `pip install`.
cp /etc/ssl/certs/ca-certificates.crt ./ca-certificates.crt

# 4. Apply Dockerfile + requirements patches if not already applied.
if ! git apply --check "$PATCH_FILE" 2>/dev/null; then
    if git apply --reverse --check "$PATCH_FILE" 2>/dev/null; then
        echo "Patches already applied; continuing."
    else
        echo "Patch does not apply cleanly — upstream LangAlpha probably moved."
        echo "Inspect $PATCH_FILE and reconcile manually before re-running."
        exit 1
    fi
else
    git apply "$PATCH_FILE"
fi

# 5. Build + start. langgraph-api healthcheck reports "unhealthy" because
#    of a missing /health route, but /ok returns 200. Same story for
#    valuation-api: /health works, the healthcheck command does not.
docker compose up --build -d

cat <<'NOTE'

LangAlpha is up. Endpoints:
  - Web UI:        http://localhost:80/        (redirects to /login)
  - LangGraph API: http://localhost:8123/ok    (and /docs for OpenAPI)
  - Valuation API: http://localhost:8001/health
  - MongoDB:       localhost:27017             (admin / password)
  - Postgres:      localhost:5433              (postgres / postgres)
  - Redis:         internal only (langgraph-redis)

Before doing real analysis, edit ~/LangAlpha/.env and fill in:
  POLYGON_API_KEY, TAVILY_API_KEY, FINANCIALMODELINGPREP_API_KEY,
  and at least one of OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY.
Then `docker compose restart langgraph-api web-api`.
NOTE
