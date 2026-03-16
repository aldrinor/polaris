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
    research)
        echo "Running research pipeline..."
        shift
        exec python -m scripts.full_cycle "$@"
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
        echo "Usage: docker run polaris [serve|research|preflight|shell]"
        exit 1
        ;;
esac
