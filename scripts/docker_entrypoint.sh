#!/bin/bash
set -e

echo "=== POLARIS Sovereign Deep Research Platform ==="
echo "Version: ${POLARIS_VERSION:-0.9.0}"
echo "Mode: ${POLARIS_DEPLOYMENT_MODE:-cloud}"
echo "================================================"

# Verify required environment variables
REQUIRED_VARS=""
if [ "${POLARIS_DEPLOYMENT_MODE}" != "sovereign" ]; then
    REQUIRED_VARS="OPENROUTER_API_KEY"
fi

for var in $REQUIRED_VARS; do
    if [ -z "${!var}" ]; then
        echo "ERROR: Required environment variable $var is not set"
        exit 1
    fi
done

# Create necessary directories
mkdir -p /app/outputs/polaris_graph /app/logs /app/state /app/data

case "${1:-serve}" in
    serve)
        echo "Starting POLARIS web server on port 8000..."
        exec python -m uvicorn scripts.live_server:app --host 0.0.0.0 --port 8000 --workers 1
        ;;
    sweep)
        # Pipeline A — the hardened honest-rebuild sweep orchestrator.
        # See BUG-B-1..B-5 in logs/bug_log.md for the 5-round audit history.
        echo "Running POLARIS pipeline A (honest-rebuild sweep)..."
        shift
        exec python -m scripts.run_honest_sweep_r3 "$@"
        ;;
    research)
        # BUG-M-208 (open, 2026-04-18): pipeline C is frozen and this
        # entry point is broken. scripts/full_cycle.py imports
        # scripts/run_ragas_v3.py and scripts/final_audit.py which
        # no longer exist. Disposition (retire/repair/leave) tracked
        # in src/orchestration/FROZEN_SINCE_2026-03-16.md.
        # Until that decision is made, refuse this command loudly
        # rather than hand users a broken crash.
        cat >&2 <<'DEPRECATION'
ERROR: The 'research' subcommand routes through pipeline C
(scripts/full_cycle.py) which is FROZEN and PARTIALLY BROKEN as of
2026-04-18. It imports scripts/run_ragas_v3.py and scripts/final_audit.py
which do not exist in this repo.

Use instead:
    docker run polaris sweep --only <query_slug>     # pipeline A (hardened)
    docker run polaris serve                          # pipeline B (UI)

Or if you truly need the legacy research CLI, see
    src/orchestration/FROZEN_SINCE_2026-03-16.md
for the retire/repair/leave decision tree.
DEPRECATION
        exit 2
        ;;
    preflight)
        echo "Running preflight checks..."
        exec python -m scripts.pg_preflight_v2
        ;;
    shell)
        echo "Starting interactive shell..."
        exec /bin/bash
        ;;
    *)
        echo "Unknown command: $1"
        echo "Usage: docker run polaris [serve|sweep|preflight|shell]"
        echo "  serve     — pipeline B (FastAPI UI, default)"
        echo "  sweep     — pipeline A (honest-rebuild sweep; pass --only <slug> for a single query)"
        echo "  preflight — environment check"
        echo "  shell     — interactive bash"
        echo ""
        echo "NOTE: the legacy 'research' subcommand is frozen and broken;"
        echo "      see src/orchestration/FROZEN_SINCE_2026-03-16.md"
        exit 1
        ;;
esac
