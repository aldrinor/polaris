#!/bin/bash
# ZERO-LLM replay-only isolation: reuse the ALREADY-RECORDED store and re-run only the two replay arms
# (PG_PARALLEL_VERIFY=1 control vs =8 treatment) + compare. Fast (no LLM). Used to localize the
# PG_PARALLEL_VERIFY divergence (my synth loop vs the pre-existing provenance findings loop).
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
WT=/home/polaris/wt/compose_fix
cd "$WT" || exit 9
export PYTHONPATH="$WT" PYTHONIOENCODING=utf-8
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
export PG_MAX_PARALLEL_SECTIONS=1 PG_COMPOSE_BASKET_WORKERS=1

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
SECTIONS="${SECTIONS:-0,1}"; CAP="${CAP:-8}"
D="$WT/.replay_ab_pverify"; STORE="$D/rr_store.pkl"
TAG="${TAG:-x}"
[ -s "$STORE" ] || { echo "NO STORE at $STORE — run _replay_ab_pverify.sh first"; exit 9; }

run() { python scripts/_hb_probe_run.py --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$1" --sections "$SECTIONS" --cap-primary "$CAP"; }

export HB_REPLAY_MODE=replay HB_REPLAY_FILE="$STORE" HB_INLINE_TO_THREAD=0
export PG_PARALLEL_VERIFY=1; run "$D/cp5_control_$TAG.json"  || { echo CONTROL FAILED; exit 3; }
export PG_PARALLEL_VERIFY=8; run "$D/cp5_treatment_$TAG.json" || { echo TREATMENT FAILED; exit 4; }
python scripts/_replay_compare.py "$D/cp5_control_$TAG.json" "$D/cp5_treatment_$TAG.json"
echo "=== replay-only ($TAG) rc=$? ==="
