#!/usr/bin/env bash
# Deadline-focused RACE measurement: the MAX candidate arm only, generous per-draw timeout so
# a draw completes instead of timing out. Optionally a baseline arm if ARMS="max baseline".
#   max      = 8 retained champion levers + Batch 3 (contradiction mining + relation-evidence packs)
#   baseline = every new lever off (same-harness drift control)
# Compare max's replicated mean to the established champion 0.5084 and field top ADORE 0.5265.
set -uo pipefail
cd /home/polaris/wt/faithoff

export PYTHON_BIN=/home/polaris/conda_cu128/bin/python
export OPENROUTER_API_KEY="$("$PYTHON_BIN" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env')['OPENROUTER_API_KEY'])")"
export DRAW_TIMEOUT_SECONDS="${DRAW_TIMEOUT_SECONDS:-5400}"   # 90 min/draw (Fable: K3 provider degraded tonight; 1.4x headroom too thin)

CORPUS=data/cp4_corpus_s3gear_329.json
TASK=72
RUNNER=scripts/run_k3.sh
OUT=outputs/race_max_focus
ARMS="${ARMS:-max}"

FULL_LEVERS=(
  PG_SECTION_STRUCTURE=1 PG_SYNTHESIS_TABLE_CONSTRUCT=1 PG_SUMMARY_TABLE_COMPOSE=1
  PG_PROMPT_SCOPE_WEIGHTING=1 PG_NARRATIVE_ATTRIBUTION=1 PG_FACET_EVIDENCE_PACKS=1
  PG_BASKET_SYNTHESIS=1 PG_COVERAGE_OBLIGATIONS=1
)
OFF_LEVERS=(
  PG_SECTION_STRUCTURE=0 PG_SYNTHESIS_TABLE_CONSTRUCT=0 PG_SUMMARY_TABLE_COMPOSE=0
  PG_PROMPT_SCOPE_WEIGHTING=0 PG_NARRATIVE_ATTRIBUTION=0 PG_FACET_EVIDENCE_PACKS=0
  PG_BASKET_SYNTHESIS=0 PG_COVERAGE_OBLIGATIONS=0
)
BATCH3_LEVERS=( PG_CONTRADICTION_MINING=1 PG_RELATION_EVIDENCE_PACKS=1 )

run_arm() {
  local arm="$1"; shift
  echo "======== ARM: $arm ($(date -u +%H:%M:%SZ)) DRAW_TIMEOUT=${DRAW_TIMEOUT_SECONDS}s ========"
  env "$@" PYTHON_BIN="$PYTHON_BIN" OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
    DRAW_TIMEOUT_SECONDS="$DRAW_TIMEOUT_SECONDS" \
    scripts/baseline_triple.sh --corpus "$CORPUS" --task-id "$TASK" \
      --label "mf_${arm}" --out-root "$OUT" --runner "$RUNNER"
  echo "======== ARM $arm DONE ($(date -u +%H:%M:%SZ)) ========"
}

for arm in $ARMS; do
  case "$arm" in
    max)      run_arm max      "${FULL_LEVERS[@]}" "${BATCH3_LEVERS[@]}" ;;
    full)     run_arm full     "${FULL_LEVERS[@]}" ;;
    baseline) run_arm baseline "${OFF_LEVERS[@]}" ;;
    *) echo "unknown arm: $arm" >&2 ;;
  esac
done
echo "ALL_ARMS_COMPLETE"
