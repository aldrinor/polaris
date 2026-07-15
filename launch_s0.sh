#!/bin/bash
set -a
. /workspace/POLARIS/.env 2>/dev/null
set +a
cd /workspace/clean_compose_wt
export PYTHONPATH=/workspace/clean_compose_wt
export PYTHONIOENCODING=utf-8
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1
export PG_SECTION_BASKET_MAP=1
export PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1
export PG_VERIFIED_COMPOSE=1
export PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=2
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=90
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=420
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=6000
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=3000
export PG_S5_SPAN_CHAR_CAP=8000
OUT=/workspace/POLARIS/outputs/s5_clean_compose_opus
mkdir -p "$OUT"
SECTIONS="${1:-}"
setsid python -u scripts/run_s5_live_compose.py \
  --cp2 /workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json \
  --cp3 /workspace/POLARIS/outputs/s3_hamster_i1/cp3_basket_snapshot.json \
  --cp4 /workspace/POLARIS/outputs/s4_downstream_iter2/cp4_outline_snapshot.json \
  --out "$OUT/cp5_generation_snapshot.json" $SECTIONS \
  < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
sleep 1
