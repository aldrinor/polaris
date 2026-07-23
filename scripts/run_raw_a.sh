#!/usr/bin/env bash
# One clean, reproducible command to run the raw-A pipeline (the champion recipe:
# compose_agentic_report_s3gear329.py over the frozen cp4 corpus, GLM 5.2), with
# every fragile knob captured so a run is never a coin flip.
#
# FAITHFULNESS IS TURNED FULLY OFF HERE (operator decision, 2026-07-20 — scoring experiment):
#   PG_STRICT_VERIFY_OFF=1           -> the MASTER kill-switch. verify_sentence_provenance
#   short-circuits at the TOP and returns EVERY composed sentence as VERIFIED with no drop:
#   NO drop path runs (no_provenance_token, span-bounds, number/integer/percent-not-in-span,
#   binding_qualifier_dropped, no_content_word_overlap, trial_name_mismatch, entailment_failed,
#   the B16 overstatement guards, judge-error fail-closed). 100% of composed sentences survive.
#   PG_STRICT_VERIFY_ENTAILMENT=off  -> kept for belt-and-braces (the NLI entailment gate is a
#   subset of what the master switch already bypasses); with the master switch on it is redundant.
#   Set PG_STRICT_VERIFY_OFF back to empty/0 (and entailment back to "enforce") to restore the gate.
#   NOTE: this is scoped to THIS run recipe only — it does NOT touch .env or the code default
#   (PG_STRICT_VERIFY_OFF defaults OFF/empty), so other pipelines and concurrent bots keep
#   faithfulness fully ON. The switch is default-off => unset == today's byte-identical behavior.
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
export PG_STRICT_VERIFY_OFF=1                    # <-- MASTER FAITHFULNESS KILL-SWITCH (see header): drops NOTHING
export PG_STRICT_VERIFY_ENTAILMENT=off          # <-- ENTAILMENT OFF (redundant under the master switch; see header)
# PG_ROUTE_ALL_BASKETS is intentionally not exported here.  Its champion value
# is single-sourced in config_defaults.py, so the resolved run state cannot
# disagree with the central setting.

# --- STEP-1 render/format cleanups (RENDER ONLY — no faithfulness surface touched) ---
# Each flag is central-config-gated (config_defaults.py) and DEFAULTS to today's behavior;
# these lines OPT THIS RECIPE into the cleaner render. Faithfulness engine is untouched.
export PG_MIRROR_CITE_COLLAPSE=0                 # #1 fold same-origin mirror cites to clean [11][12], drop the "(also mirrored)" note
export PG_ANTI_VERBOSITY=on                      # #2 concise-writing mode ON (denser prose)
export PG_REFERENCE_TIER_LABELS=0                # #3 omit the "(tier X)" label from the References block
export PG_CITATION_INLINE_GLUE_COLLAPSE=1        # #4 collapse the malformed "].[" citation glue -> "]["
# Residual verified prose is never removed after generation. Under
# PG_FACET_EVIDENCE_PACKS it is folded into topical sections before writing.
# Token-repair OFF: with strict-verify off, _repair_llm_draft_untokened misfires and 4 sections start
# mid-word / with BibTeX; '0' disables the repair so those sections render cleanly (Sol token fix).
export PG_NO_TOKEN_SENTENCE_REPAIR=0

# --- API keys via dotenv (NEVER bash-source .env: line 304 breaks bash) ---
export OPENROUTER_API_KEY="$("$PY" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env')['OPENROUTER_API_KEY'])")"
export SERPER_API_KEY="$("$PY" -c "from dotenv import dotenv_values; print(dotenv_values('/workspace/POLARIS/.env').get('SERPER_API_KEY',''))")"

unset PYTHONPATH
export PYTHONUNBUFFERED=1
mkdir -p "$OUT"

echo "run_raw_a: strict_verify_off=$PG_STRICT_VERIFY_OFF entailment=$PG_STRICT_VERIFY_ENTAILMENT corpus=$CORPUS task=$TASK out=$OUT"
exec "$PY" scripts/compose_agentic_report_s3gear329.py \
  --corpus "$CORPUS" --rq-drb-task "$TASK" --out-dir "$OUT"
