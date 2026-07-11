#!/bin/bash
# Record/replay A/B for PG_PARALLEL_VERIFY on the compose-SYNTH strict_verify tail
# (_verify_all_sentences_synth in verified_compose.py): certify kept/dropped verdict-set IDENTITY
# between the SERIAL per-sentence verify loop (PG_PARALLEL_VERIFY=1 => original loop) and the
# bounded, order-preserving map-then-reduce ThreadPoolExecutor (PG_PARALLEL_VERIFY=8) at ZERO LLM
# cost on replay. Both replay arms hold PG_MAX_PARALLEL_SECTIONS=1 + PG_COMPOSE_BASKET_WORKERS=1, so
# the ONLY difference is the verify-parallelism knob. Any output divergence would be a shared-state
# race in the new parallel synth-verify path or a reduce-ordering bug. Runs MY worktree code only.
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
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16 PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=2
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=8 PG_MAX_CONCURRENT_LLM=16
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=120 PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=400
export PG_ENTAILMENT_TOTAL_S=120 PG_ABSTRACTIVE_WRITER_MAX_TOKENS=8000
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=4000 PG_SECTION_MAX_TOKENS=8000 PG_S5_SPAN_CHAR_CAP=8000
export PG_JUDGE_PROVIDER_ROTATE=1

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
SECTIONS="${SECTIONS:-0,1}"
CAP="${CAP:-8}"                  # >1 primary baskets/section so the synth-verify loop genuinely runs
D="$WT/.replay_ab_pverify"
mkdir -p "$D"
STORE="$D/rr_store.pkl"

run() {  # $1=out ; env HB_* + PG_PARALLEL_VERIFY set by caller
  python scripts/_hb_probe_run.py --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
    --out "$1" --sections "$SECTIONS" --cap-primary "$CAP"
}

# Both replay arms: fully serial section + serial baskets so ONLY verify-parallelism differs.
export PG_MAX_PARALLEL_SECTIONS=1
export PG_COMPOSE_BASKET_WORKERS=1

echo "===================== PHASE 1: RECORD (real LLM, PG_PARALLEL_VERIFY=8 to capture every path) ====="
export HB_REPLAY_MODE=record HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=0
export PG_PARALLEL_VERIFY=8
run "$D/cp5_record.json" || { echo "RECORD FAILED"; exit 2; }
[ -s "$STORE" ] || { echo "NO STORE WRITTEN"; exit 2; }

echo "===================== PHASE 2: CONTROL (PG_PARALLEL_VERIFY=1, serial verify) ====================="
export HB_REPLAY_MODE=replay HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=0
export PG_PARALLEL_VERIFY=1
run "$D/cp5_control.json" || { echo "CONTROL FAILED"; exit 3; }

echo "===================== PHASE 3: TREATMENT (PG_PARALLEL_VERIFY=8, parallel verify) ================="
export HB_REPLAY_MODE=replay HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=0
export PG_PARALLEL_VERIFY=8
run "$D/cp5_treatment.json" || { echo "TREATMENT FAILED"; exit 4; }

echo "===================== PHASE 4: COMPARE ====================="
python scripts/_replay_compare.py "$D/cp5_control.json" "$D/cp5_treatment.json"
RC=$?
echo "=== PG_PARALLEL_VERIFY replay A/B rc=$RC ==="
exit $RC
