#!/usr/bin/env bash
# Four-class prompt-scope generality replay.  The TSV manifest contains:
#   constraint_kind<TAB>corpus_path<TAB>task_id
# where constraint_kind is hard, soft, mixed, or none.  Every case gets three
# independent generator draws through baseline_triple.sh; no live run is started
# merely by installing this recipe.
set -euo pipefail

MANIFEST=""
OUT_ROOT="outputs/scope_generality"
LABEL_PREFIX="scope_generality"
DRAW_SCRIPT="scripts/baseline_triple.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"

while [ $# -gt 0 ]; do
  case "$1" in
    --manifest) MANIFEST="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --label-prefix) LABEL_PREFIX="$2"; shift 2 ;;
    --draw-script) DRAW_SCRIPT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$MANIFEST" ] || [ ! -f "$MANIFEST" ]; then
  echo "usage: $0 --manifest CASES.tsv [--out-root DIR] [--label-prefix NAME]" >&2
  exit 2
fi
if [ ! -x "$DRAW_SCRIPT" ]; then
  echo "draw script is not executable: $DRAW_SCRIPT" >&2
  exit 2
fi
if [[ ! "$LABEL_PREFIX" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "label prefix may contain only letters, digits, dot, underscore, and hyphen" >&2
  exit 2
fi

declare -A SEEN=()
CASE_INDEX=0
while IFS=$'\t' read -r KIND CORPUS TASK_ID REST; do
  KIND="${KIND%$'\r'}"
  CORPUS="${CORPUS%$'\r'}"
  TASK_ID="${TASK_ID%$'\r'}"
  if [ -z "$KIND" ] || [[ "$KIND" == \#* ]]; then
    continue
  fi
  case "$KIND" in
    hard|soft|mixed|none) ;;
    *) echo "invalid constraint kind '$KIND' (expected hard, soft, mixed, or none)" >&2; exit 2 ;;
  esac
  if [ -z "$CORPUS" ] || [ -z "$TASK_ID" ]; then
    echo "manifest row for '$KIND' is missing corpus_path or task_id" >&2
    exit 2
  fi

  SEEN["$KIND"]=1
  CASE_INDEX=$((CASE_INDEX + 1))
  LABEL="${LABEL_PREFIX}_${KIND}_${CASE_INDEX}"
  env \
    PG_PROMPT_SCOPE_WEIGHTING=1 \
    PG_NARRATIVE_ATTRIBUTION=1 \
    "$DRAW_SCRIPT" \
      --corpus "$CORPUS" --task-id "$TASK_ID" --label "$LABEL" --out-root "$OUT_ROOT"

  shopt -s nullglob
  RUNS=("$OUT_ROOT/$LABEL"-*)
  shopt -u nullglob
  if [ "${#RUNS[@]}" -eq 0 ]; then
    echo "no run directory found for $LABEL" >&2
    exit 1
  fi
  LATEST="${RUNS[${#RUNS[@]} - 1]}"
  shopt -s nullglob
  SUMMARIES=("$LATEST"/draw_*/compose_summary.json)
  shopt -u nullglob

  "$PYTHON_BIN" - "$KIND" "${SUMMARIES[@]}" <<'PYEOF'
import json
import pathlib
import sys

kind = sys.argv[1]
paths = [pathlib.Path(raw) for raw in sys.argv[2:]]
if len(paths) != 3:
    raise SystemExit(f"{kind}: expected 3 independent compose summaries, found {len(paths)}")
for path in paths:
    summary = json.loads(path.read_text(encoding="utf-8"))
    states = summary.get("resolved_lever_states") or {}
    if states.get("PG_PROMPT_SCOPE_WEIGHTING") != "1":
        raise SystemExit(f"{path}: prompt-scope gate did not resolve ON")
    ledger = summary.get("prompt_scope_weight_ledger") or {}
    if ledger.get("input_count") != ledger.get("output_count"):
        raise SystemExit(f"{path}: evidence count changed under scope weighting")
    if kind == "none":
        if ledger.get("active"):
            raise SystemExit(f"{path}: unconstrained prompt was over-weighted")
    else:
        if not ledger.get("active") or not ledger.get("constraints"):
            raise SystemExit(f"{path}: constrained prompt produced no traceable weighting plan")
        if len(ledger.get("rows") or []) != ledger.get("output_count"):
            raise SystemExit(f"{path}: weighting ledger does not cover the complete evidence stream")
print(f"{kind}: three-draw scope ledger PASS")
PYEOF
done < "$MANIFEST"

for REQUIRED in hard soft mixed none; do
  if [ -z "${SEEN[$REQUIRED]:-}" ]; then
    echo "manifest omitted required generality class: $REQUIRED" >&2
    exit 2
  fi
done

echo "scope generality PASS: hard, soft, mixed, and unconstrained prompts all replayed"
