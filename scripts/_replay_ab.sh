#!/bin/bash
# Record/replay A/B: certify kept/dropped verdict-set IDENTITY between a SERIAL control and the
# CONCURRENT (worker-thread) treatment created by the off-loop fix — at ZERO LLM cost on replay.
#   Phase 1 RECORD   : real LLM, 2 sections, capture judge+writer answers by content hash.
#   Phase 2 CONTROL  : replay, PG_MAX_PARALLEL_SECTIONS=1 + to_thread INLINED  (fully serial).
#   Phase 3 TREATMENT: replay, PG_MAX_PARALLEL_SECTIONS=2 + real to_thread     (concurrent threads).
#   Phase 4 COMPARE  : assert byte-identical verified_text + verified/dropped counts per section.
# Runs MY worktree code only.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
WT=/home/polaris/wt/compose_fix
cd "$WT" || exit 9
export PYTHONPATH="$WT" PYTHONIOENCODING=utf-8

# activation flag slate (identical to the compose launcher)
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1 PG_SECTION_BASKET_MAP=1 PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1 PG_VERIFIED_COMPOSE=1 PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1 PG_RENDER_SEAM_SANITIZE=1
export PG_WRITER_WALL_BASKET_SCALED=1 PG_WRITER_KSPAN_RECOVERY_PASS=1
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16 PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 PG_PARALLEL_VERIFY=8
# SMALL/FAST caps (do not affect the verdict mechanism; keep budget low)
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=8 PG_MAX_CONCURRENT_LLM=16
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=120 PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=400
export PG_ENTAILMENT_TOTAL_S=90 PG_ABSTRACTIVE_WRITER_MAX_TOKENS=8000
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=4000 PG_SECTION_MAX_TOKENS=8000 PG_S5_SPAN_CHAR_CAP=8000

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
SECTIONS="${SECTIONS:-0,1}"
CAP="${CAP:-1}"
D="$WT/.replay_ab"
mkdir -p "$D"
STORE="$D/rr_store.pkl"

run() {  # $1=out $2=mode-desc ; env HB_* already set by caller
  python scripts/_hb_probe_run.py --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
    --out "$1" --sections "$SECTIONS" --cap-primary "$CAP"
}

echo "===================== PHASE 1: RECORD (real LLM) ====================="
export HB_REPLAY_MODE=record HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=0
export PG_MAX_PARALLEL_SECTIONS=2
run "$D/cp5_record.json" "record" || { echo "RECORD FAILED"; exit 2; }
[ -s "$STORE" ] || { echo "NO STORE WRITTEN"; exit 2; }

echo "===================== PHASE 2: CONTROL (serial replay) ====================="
export HB_REPLAY_MODE=replay HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=1
export PG_MAX_PARALLEL_SECTIONS=1
run "$D/cp5_control.json" "control" || { echo "CONTROL FAILED"; exit 3; }

echo "===================== PHASE 3: TREATMENT (concurrent replay) ====================="
export HB_REPLAY_MODE=replay HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=0
export PG_MAX_PARALLEL_SECTIONS=2
run "$D/cp5_treatment.json" "treatment" || { echo "TREATMENT FAILED"; exit 4; }

echo "===================== PHASE 4: COMPARE ====================="
python scripts/_replay_compare.py "$D/cp5_control.json" "$D/cp5_treatment.json"
RC=$?
echo "=== replay A/B rc=$RC ==="
exit $RC
