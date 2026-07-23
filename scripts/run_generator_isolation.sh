#!/usr/bin/env bash
# Causal isolation recipe. Every arm delegates to baseline_triple.sh, which
# performs three independent generator draws and scores each generated report once.
set -uo pipefail

CORPUS=""
TASK_ID=""
LABEL_PREFIX="isolation"
OUT_ROOT="outputs/generator_isolation"

while [ $# -gt 0 ]; do
  case "$1" in
    --corpus) CORPUS="$2"; shift 2 ;;
    --task-id) TASK_ID="$2"; shift 2 ;;
    --label-prefix) LABEL_PREFIX="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$CORPUS" ] || [ -z "$TASK_ID" ]; then
  echo "usage: $0 --corpus PATH --task-id ID [--label-prefix NAME] [--out-root DIR]" >&2
  exit 2
fi

DRAW_SCRIPT="scripts/baseline_triple.sh"
COMMON=(--corpus "$CORPUS" --task-id "$TASK_ID" --out-root "$OUT_ROOT")

run_arm() {
  local arm="$1"
  shift
  env \
    PG_SECTION_STRUCTURE=0 \
    PG_SYNTHESIS_TABLE_CONSTRUCT=0 \
    PG_SUMMARY_TABLE_COMPOSE=0 \
    PG_PROMPT_SCOPE_WEIGHTING=0 \
    PG_NARRATIVE_ATTRIBUTION=0 \
    PG_FACET_EVIDENCE_PACKS=0 \
    PG_BASKET_SYNTHESIS=0 \
    "$@" \
    "$DRAW_SCRIPT" "${COMMON[@]}" --label "${LABEL_PREFIX}_${arm}"
}

# Current package, with every new implementation gate explicitly off.
run_arm current

# K3 reasoning-model plumbing is committed in the current base; this arm
# isolates only the whole-basket prompt/density change on that same model.
run_arm k3_prompt PG_BASKET_SYNTHESIS=1

# Deterministic structure/table artifacts only.
run_arm artifacts \
  PG_SECTION_STRUCTURE=1 \
  PG_SYNTHESIS_TABLE_CONSTRUCT=1 \
  PG_SUMMARY_TABLE_COMPOSE=1

# Prompt-scope weights and narrative source metadata only.
run_arm scope_weighting \
  PG_PROMPT_SCOPE_WEIGHTING=1 \
  PG_NARRATIVE_ATTRIBUTION=1

# Full package, including complete facet packs and residual fold-in.
run_arm full \
  PG_SECTION_STRUCTURE=1 \
  PG_SYNTHESIS_TABLE_CONSTRUCT=1 \
  PG_SUMMARY_TABLE_COMPOSE=1 \
  PG_PROMPT_SCOPE_WEIGHTING=1 \
  PG_NARRATIVE_ATTRIBUTION=1 \
  PG_FACET_EVIDENCE_PACKS=1 \
  PG_BASKET_SYNTHESIS=1
