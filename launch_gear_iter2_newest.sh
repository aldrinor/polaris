#!/bin/bash
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
# Fix 9 (2026-07-10 compose gear-loop iter 2): §9.1.8 always-MAX. The iter-1 run truncated GLM-5.2's
# reasoning at the 6000/3000 caps (ReasoningFirstTruncationError at ~24795 chars) -> empty group draft ->
# deterministic whole-span fallback. Raise to the model's REAL OpenRouter cap (z-ai/glm-5.2:
# context_length=1048576, top_provider.max_completion_tokens=131072). max_tokens is a CAP billed by
# actual usage, so a generous cap is free insurance and can never truncate a paragraph draft.
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=2
CP4=$(ls -t /workspace/POLARIS/outputs/s4_*/cp4_outline_snapshot.json | head -1)
CP3=$(ls -t /workspace/POLARIS/outputs/s3_*/cp3_basket_snapshot.json | head -1)
OUT=/workspace/compose_wt/outputs/s5_gear_iter2_newest
mkdir -p "$OUT/ckpt"
echo "USING CP4=$CP4" > "$OUT/inputs.txt"
echo "USING CP3=$CP3" >> "$OUT/inputs.txt"
setsid python -u scripts/run_s5_i3.py \
  --cp2 /workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json \
  --cp3 "$CP3" \
  --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" \
  --ckpt-dir "$OUT/ckpt" \
  --cap-primary 5 \
  < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
