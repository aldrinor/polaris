#!/usr/bin/env bash
# Three-draw measurement recipe. Each score is produced from a distinct generator
# invocation; this script never scores one frozen report three times.
set -uo pipefail

CORPUS=""
TASK_ID=""
LABEL=""
OUT_ROOT="outputs/generator_draws"
RUNNER="scripts/run_raw_a.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"
DRAW_TIMEOUT_SECONDS="${DRAW_TIMEOUT_SECONDS:-2700}"

while [ $# -gt 0 ]; do
  case "$1" in
    --corpus) CORPUS="$2"; shift 2 ;;
    --task-id) TASK_ID="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --out-root) OUT_ROOT="$2"; shift 2 ;;
    --runner) RUNNER="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$CORPUS" ] || [ -z "$TASK_ID" ] || [ -z "$LABEL" ]; then
  echo "usage: $0 --corpus PATH --task-id ID --label NAME [--out-root DIR] [--runner PATH]" >&2
  exit 2
fi
if [ ! -f "$CORPUS" ] || [ ! -x "$RUNNER" ]; then
  echo "missing corpus or executable runner" >&2
  exit 2
fi
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
  echo "OPENROUTER_API_KEY must already be present in the environment" >&2
  exit 2
fi

RUN_ROOT="$OUT_ROOT/$LABEL-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$RUN_ROOT"
LOG="$RUN_ROOT/measurement.log"
SCORES=()

log() { echo "$*" | tee -a "$LOG"; }

for draw in 1 2 3; do
  DRAW_DIR="$RUN_ROOT/draw_$draw"
  MODEL_NAME="${LABEL}_draw_${draw}"
  log "generator draw $draw -> $DRAW_DIR"
  if ! timeout "$DRAW_TIMEOUT_SECONDS" "$RUNNER" \
      --corpus "$CORPUS" --rq-drb-task "$TASK_ID" --out-dir "$DRAW_DIR" \
      >>"$LOG" 2>&1; then
    log "draw $draw generation failed"
    SCORES+=("FAIL")
    continue
  fi
  if [ ! -s "$DRAW_DIR/report.md" ]; then
    log "draw $draw produced no report"
    SCORES+=("FAIL")
    continue
  fi
  if ! "$PYTHON_BIN" scripts/score_report_race.py \
      --report "$DRAW_DIR/report.md" --task-id "$TASK_ID" --model-name "$MODEL_NAME" \
      >>"$LOG" 2>&1; then
    log "draw $draw scoring failed"
    SCORES+=("FAIL")
    continue
  fi
  RESULT="third_party/deep_research_bench/results/race/$MODEL_NAME/race_result.txt"
  SCORE="$(awk '/Overall Score:/ {value=$NF} END {print value}' "$RESULT" 2>/dev/null)"
  SCORE="${SCORE:-FAIL}"
  SCORES+=("$SCORE")
  log "draw $draw score=$SCORE"
done

"$PYTHON_BIN" - "${SCORES[@]}" <<'PYEOF' | tee -a "$LOG"
import statistics
import sys

values = []
for raw in sys.argv[1:]:
    try:
        values.append(float(raw))
    except ValueError:
        pass
if len(values) != 3:
    print(f"measurement incomplete: valid_draws={len(values)}/3")
    raise SystemExit(1)
mean = statistics.fmean(values)
spread = max(values) - min(values)
print(f"independent_draws={values}")
print(f"mean={mean:.6f} spread={spread:.6f}")
print("interpretation: <=0.007 is noise; call a gain real only when the replicated mean clears ~+0.014")
PYEOF
