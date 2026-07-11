#!/bin/bash
# Compose gear-loop iter 1 — run on base ghost-free code, MAX-token slate (§9.1.8),
# pinned best inputs (s4_gear cp4 + s3_gear cp3), which also == gear-rule NEWEST.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1
export PG_SECTION_BASKET_MAP=1
export PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1
export PG_VERIFIED_COMPOSE=1
export PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce
export PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=3
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=90
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=420
# §9.1.8 always-MAX: z-ai/glm-5.2 real caps (context 1048576, max_completion 131072).
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=2
# PINNED best inputs (LOCK step 2). Confirmed == gear-rule newest (ls -t head -1).
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
NEWEST_CP4=$(ls -t /workspace/POLARIS/outputs/s4_*/cp4_outline_snapshot.json | head -1)
NEWEST_CP3=$(ls -t /workspace/POLARIS/outputs/s3_*/cp3_basket_snapshot.json | head -1)
OUT=/workspace/compose_wt/outputs/s5_gear_iter1
mkdir -p "$OUT/ckpt"
{
  echo "PINNED CP4=$CP4"
  echo "PINNED CP3=$CP3"
  echo "NEWEST CP4=$NEWEST_CP4"
  echo "NEWEST CP3=$NEWEST_CP3"
  echo "pinned==newest cp4: $([ "$CP4" = "$NEWEST_CP4" ] && echo YES || echo NO)"
  echo "pinned==newest cp3: $([ "$CP3" = "$NEWEST_CP3" ] && echo YES || echo NO)"
} > "$OUT/inputs.txt"
setsid python -u scripts/run_s5_i3.py \
  --cp2 /workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json \
  --cp3 "$CP3" \
  --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" \
  --ckpt-dir "$OUT/ckpt" \
  --cap-primary 5 \
  < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
