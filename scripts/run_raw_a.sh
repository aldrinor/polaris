#!/usr/bin/env bash
# One clean, reproducible command to run the raw-A pipeline (the champion recipe:
# compose_agentic_report_s3gear329.py over the frozen cp4 corpus, GLM 5.2), with
# every fragile knob captured so a run is never a coin flip.
#
# FAITHFULNESS / ENTAILMENT IS TURNED OFF HERE (operator decision, 2026-07-20):
#   PG_STRICT_VERIFY_ENTAILMENT=off  -> the NLI entailment gate does not run, so
#   sentences are no longer dropped for "NEUTRAL" (the tail-gate ghost that was
#   cutting ~half the composed sentences, most of them true cross-source
#   synthesis, not false claims). Set it back to "enforce" to restore the gate.
#   NOTE: this is scoped to THIS run recipe only — it does not touch .env or the
#   code default, so other pipelines and concurrent bots keep entailment ON.
#
# Usage: scripts/run_raw_a.sh [--corpus PATH] [--rq-drb-task N] [--out-dir DIR]
set -uo pipefail

CORPUS="data/cp4_corpus_s3gear_329.json"
TASK="72"
OUT="outputs/run_raw_a"
while [ $# -gt 0 ]; do
  case "$1" in
    --corpus)      CORPUS="$2"; shift 2 ;;
    --rq-drb-task) TASK="$2"; shift 2 ;;
    --out-dir)     OUT="$2"; shift 2 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

PY=/home/polaris/pipeline-env/bin/python   # torch cu128; drives the Blackwell GPU
LDP_FILE=/tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/browserlibs/LDPATH.txt

# --- browser libs so the agentic outliner's live fetch works (userspace fix) ---
[ -f "$LDP_FILE" ] && export LD_LIBRARY_PATH="$(cat "$LDP_FILE"):${LD_LIBRARY_PATH:-}"

# --- run knobs ---
export PG_LOOPBACK_MODE=0                      # .env pins =1 which hangs forever
export PG_OUTLINE_AGENT=1                       # agentic outliner ON (champion recipe)
export PG_CONTENT_RELEVANCE_SCORE_CHUNK=16      # chunk the reranker so it fits the shared GPU
export PYTORCH_ALLOC_CONF=expandable_segments:True
export PG_OUTLINE_MAX_TOKENS=131072             # prevents the deepseek truncation crash
export PG_OUTLINE_REASONING_MAX_TOKENS=32768
export PG_STRICT_VERIFY_ENTAILMENT=off          # <-- ENTAILMENT OFF (see header)

# --- API keys via dotenv (NEVER bash-source .env: line 304 breaks bash) ---
export OPENROUTER_API_KEY="$("$PY" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env')['OPENROUTER_API_KEY'])")"
export SERPER_API_KEY="$("$PY" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env').get('SERPER_API_KEY',''))")"

unset PYTHONPATH
export PYTHONUNBUFFERED=1
mkdir -p "$OUT"

echo "run_raw_a: entailment=$PG_STRICT_VERIFY_ENTAILMENT corpus=$CORPUS task=$TASK out=$OUT"
exec "$PY" scripts/compose_agentic_report_s3gear329.py \
  --corpus "$CORPUS" --rq-drb-task "$TASK" --out-dir "$OUT"
