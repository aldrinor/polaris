#!/usr/bin/env bash
# Overnight RACE measurement: does Batch 3 (contradiction mining + relation-evidence packs)
# added on top of the 8 retained levers beat the champion, and beat the field?
# Three arms, 3 independent K3 draws each, each scored once via the real RACE judge.
#   max      = 8 retained levers + Batch 3   (the candidate: best config)
#   full     = 8 retained levers             (champion, isolates Batch 3's marginal effect)
#   baseline = every new lever off           (same-harness drift control)
set -uo pipefail
cd /home/polaris/wt/faithoff

export PYTHON_BIN=/home/polaris/conda_cu128/bin/python
export OPENROUTER_API_KEY="$("$PYTHON_BIN" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env')['OPENROUTER_API_KEY'])")"
export DRAW_TIMEOUT_SECONDS=2700

CORPUS=data/cp4_corpus_s3gear_329.json
TASK=72
RUNNER=scripts/run_k3.sh
OUT=outputs/race_batch3

# the 8 retained champion levers
FULL_LEVERS=(
  PG_SECTION_STRUCTURE=1
  PG_SYNTHESIS_TABLE_CONSTRUCT=1
  PG_SUMMARY_TABLE_COMPOSE=1
  PG_PROMPT_SCOPE_WEIGHTING=1
  PG_NARRATIVE_ATTRIBUTION=1
  PG_FACET_EVIDENCE_PACKS=1
  PG_BASKET_SYNTHESIS=1
  PG_COVERAGE_OBLIGATIONS=1
)
# the 8 levers, explicitly off (baseline)
OFF_LEVERS=(
  PG_SECTION_STRUCTURE=0
  PG_SYNTHESIS_TABLE_CONSTRUCT=0
  PG_SUMMARY_TABLE_COMPOSE=0
  PG_PROMPT_SCOPE_WEIGHTING=0
  PG_NARRATIVE_ATTRIBUTION=0
  PG_FACET_EVIDENCE_PACKS=0
  PG_BASKET_SYNTHESIS=0
  PG_COVERAGE_OBLIGATIONS=0
)
# Batch 3 levers (scope-deepening left OFF: it needs live network + is slow/expensive)
BATCH3_LEVERS=(
  PG_CONTRADICTION_MINING=1
  PG_RELATION_EVIDENCE_PACKS=1
)

run_arm() {
  local arm="$1"; shift
  echo "======== ARM: $arm ($(date -u +%H:%M:%SZ)) ========"
  env "$@" \
    PYTHON_BIN="$PYTHON_BIN" OPENROUTER_API_KEY="$OPENROUTER_API_KEY" \
    DRAW_TIMEOUT_SECONDS="$DRAW_TIMEOUT_SECONDS" \
    scripts/baseline_triple.sh \
      --corpus "$CORPUS" --task-id "$TASK" --label "b3_${arm}" \
      --out-root "$OUT" --runner "$RUNNER"
  echo "======== ARM $arm DONE ($(date -u +%H:%M:%SZ)) ========"
}

# headline candidate first, so an interruption still leaves the best-config number
run_arm max      "${FULL_LEVERS[@]}" "${BATCH3_LEVERS[@]}"
run_arm full     "${FULL_LEVERS[@]}"
run_arm baseline "${OFF_LEVERS[@]}"

echo "ALL_ARMS_COMPLETE"
