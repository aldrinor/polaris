#!/usr/bin/env bash
# Post-phase RACE measurement: K3 champion generator, same harness, two arms.
#   full    = all retained levers ON  (the "after")
#   current = all retained levers OFF (same-harness baseline, the "before")
# Each arm = 3 independent generator draws, each scored once via the real RACE judge.
set -uo pipefail
cd "$(cd "$(dirname "$0")/.." && pwd)"

export PYTHON_BIN=/home/polaris/conda_cu128/bin/python
# baseline_triple.sh pre-checks OPENROUTER_API_KEY is already in env (the runner re-reads .env too).
export OPENROUTER_API_KEY="$("$PYTHON_BIN" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env')['OPENROUTER_API_KEY'])")"
export DRAW_TIMEOUT_SECONDS=2700

CORPUS=data/cp4_corpus_s3gear_329.json
TASK=72
RUNNER=scripts/run_k3.sh
OUT=outputs/race_7phase

run_arm() {
  local arm="$1"; shift
  echo "======== ARM: $arm ($(date -u +%H:%M:%SZ)) ========"
  env "$@" \
    PYTHON_BIN="$PYTHON_BIN" OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
    DRAW_TIMEOUT_SECONDS="$DRAW_TIMEOUT_SECONDS" \
    scripts/baseline_triple.sh \
      --corpus "$CORPUS" --task-id "$TASK" --label "7phase_${arm}" \
      --out-root "$OUT" --runner "$RUNNER"
  echo "======== ARM $arm DONE ($(date -u +%H:%M:%SZ)) ========"
}

# AFTER: all retained levers on
run_arm full \
  PG_SECTION_STRUCTURE=1 \
  PG_SYNTHESIS_TABLE_CONSTRUCT=1 \
  PG_SUMMARY_TABLE_COMPOSE=1 \
  PG_PROMPT_SCOPE_WEIGHTING=1 \
  PG_NARRATIVE_ATTRIBUTION=1 \
  PG_FACET_EVIDENCE_PACKS=1 \
  PG_BASKET_SYNTHESIS=1 \
  PG_COVERAGE_OBLIGATIONS=1

# BEFORE: same harness, every new lever explicitly off
run_arm current \
  PG_SECTION_STRUCTURE=0 \
  PG_SYNTHESIS_TABLE_CONSTRUCT=0 \
  PG_SUMMARY_TABLE_COMPOSE=0 \
  PG_PROMPT_SCOPE_WEIGHTING=0 \
  PG_NARRATIVE_ATTRIBUTION=0 \
  PG_FACET_EVIDENCE_PACKS=0 \
  PG_BASKET_SYNTHESIS=0 \
  PG_COVERAGE_OBLIGATIONS=0

echo "ALL_ARMS_COMPLETE"
