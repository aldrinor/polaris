#!/bin/bash
# I-carney-005 — POLARIS v6 container entrypoint.
#
# Subcommands: api | worker | migrate | preflight | shell
#
# Broker init (P1-001) happens IN-PROCESS at top of polaris_v6.queue.actors —
# this script does NOT call a separate init helper because that would run in
# a different Python interpreter than the uvicorn/dramatiq process. See
# .codex/I-carney-005/brief_iter_3.md.

set -euo pipefail

echo "=== POLARIS v6 (${POLARIS_VERSION:-dev}) ==="
echo "Mode: ${1:-api}"
echo "Redis: ${POLARIS_V6_REDIS_URL:-redis://localhost:6379/0}"
echo "GPG_KEY_ID: ${POLARIS_GPG_KEY_ID:-<unset>}"
echo "==============================================="

mkdir -p /app/outputs /app/logs /app/state /app/data

wait_for_redis() {
    # P1-001 safety net: don't crashloop the worker while redis comes up.
    # 10s timeout per acceptance criterion 4.
    local deadline=$(( $(date +%s) + 10 ))
    while [ "$(date +%s)" -lt "$deadline" ]; do
        if python -c "
import os, sys
import redis
try:
    r = redis.from_url(os.environ.get('POLARIS_V6_REDIS_URL', 'redis://redis:6379/0'))
    r.ping()
    sys.exit(0)
except Exception as exc:
    sys.exit(1)
" 2>/dev/null; then
            echo "[entrypoint] redis reachable"
            return 0
        fi
        sleep 1
    done
    echo "[entrypoint] ERROR: redis unreachable after 10s — failing loud per LAW II" >&2
    return 1
}

case "${1:-api}" in
    api)
        wait_for_redis
        echo "[entrypoint] starting uvicorn polaris_v6.api.app:app on 0.0.0.0:8000"
        # --no-access-log: SSE auth (I-rdy-004) carries the JWT as the
        # ?access_token= query param on /stream/* (native EventSource cannot
        # set headers). uvicorn's access log would write that full URL —
        # including a live 12h token — to container stdout. Access logging is
        # off so tokens never reach logs; the app's structured logging stays.
        exec python -m uvicorn polaris_v6.api.app:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
        ;;
    worker)
        wait_for_redis
        echo "[entrypoint] starting dramatiq worker (polaris_v6.queue.actors)"
        exec python -m dramatiq polaris_v6.queue.actors --processes 1 --threads 2
        ;;
    migrate)
        echo "[entrypoint] running run_store.init_db (idempotent migration)"
        exec python -c "from polaris_v6.queue.run_store import init_db; init_db(); print('[migrate] OK')"
        ;;
    preflight)
        echo "[entrypoint] running preflight diagnostics"
        exec python scripts/v6_preflight.py
        ;;
    shell)
        exec /bin/bash
        ;;
    *)
        echo "Unknown command: ${1:-}" >&2
        echo "Usage: ${0} [api|worker|migrate|preflight|shell]" >&2
        echo "  api       — FastAPI server on :8000 (default)" >&2
        echo "  worker    — Dramatiq worker consuming polaris_v6.queue.actors" >&2
        echo "  migrate   — Idempotent run_store sqlite schema migration" >&2
        echo "  preflight — Env-var + redis-ping + GPG keyring sanity" >&2
        echo "  shell     — Interactive bash" >&2
        exit 1
        ;;
esac
