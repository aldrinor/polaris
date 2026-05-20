#!/usr/bin/env bash
# I-cd-015 (GH#611) acceptance: harness routes return 404 in prod.
#
# Usage:  bash web/scripts/verify_harness_404.sh
#
# Builds the Next.js production bundle, starts the server in production
# mode (with POLARIS_TEST_HARNESS_ENABLED UNSET), then curls each harness
# path + asserts HTTP 404 + asserts `x-harness-blocked: 1` header
# (differentiates middleware 404 from default Next.js not-found).
# Finally curls non-harness routes + asserts 2xx/3xx.
set -euo pipefail

# Self-locate: this script lives at web/scripts/, operate from web/.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${PORT:-3738}"

echo "==> npm run build (production)"
NODE_ENV=production npm run build

echo "==> next start -p $PORT (POLARIS_TEST_HARNESS_ENABLED UNSET)"
NODE_ENV=production npx next start -p "$PORT" &
SERVER_PID=$!
trap "kill -TERM $SERVER_PID 2>/dev/null || true" EXIT

# Poll until server ready.
for i in $(seq 1 30); do
  if curl -sS -o /dev/null "http://localhost:$PORT/sign-in" 2>/dev/null; then
    break
  fi
  sleep 1
done

# Harness paths — mix of base + REAL existing descendants. Each must
# return HTTP 404 AND the x-harness-blocked: 1 header (differentiates
# middleware 404 from a generic Next not-found).
HARNESS_PATHS=(
  /charts_test
  /charts_test/click_through
  /charts_test/forest_plot
  /sentence_hover_test
  /sentence_hover_test/coverage
  /sentence_hover_test/perf
  /sentence_hover_test/evidence_tooltip
  /disambiguation_modal_preview
  /generation
  /retrieval
  /sse
)

fail=0
for path in "${HARNESS_PATHS[@]}"; do
  read -r status header < <(
    curl -sS -o /dev/null -w "%{http_code} " -D - "http://localhost:$PORT$path" \
      | awk 'NR==1 {next} /^x-harness-blocked:/ {h=tolower($2); gsub(/[\r\n]/, "", h); print "HAS"} END{}' \
      | xargs
  )
  status=$(curl -sS -o /dev/null -w "%{http_code}" "http://localhost:$PORT$path")
  has_header=$(curl -sS -o /dev/null -D - "http://localhost:$PORT$path" \
    | grep -i '^x-harness-blocked:' | head -1 | awk '{print $2}' | tr -d '\r')
  if [ "$status" != "404" ]; then
    echo "FAIL: $path returned HTTP $status (expected 404)"
    fail=1
    continue
  fi
  if [ "$has_header" != "1" ]; then
    echo "FAIL: $path missing x-harness-blocked: 1 header (got '$has_header')"
    fail=1
    continue
  fi
  echo "OK:   $path → 404 (middleware-blocked)"
done

# Non-harness paths must remain reachable.
NON_HARNESS_PATHS=(/sign-in /dashboard /)
for path in "${NON_HARNESS_PATHS[@]}"; do
  status=$(curl -sS -o /dev/null -w "%{http_code}" "http://localhost:$PORT$path")
  case "$status" in
    2*|3*) echo "OK:   $path → HTTP $status (non-harness reachable)" ;;
    *) echo "FAIL: $path returned HTTP $status (expected 2xx/3xx)"; fail=1 ;;
  esac
done

if [ "$fail" = "1" ]; then
  echo "harness 404 verification FAILED"
  exit 1
fi
echo "harness 404 verification PASSED"
