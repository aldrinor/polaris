#!/bin/bash
# Compose gear-loop iter 3 — relaunch after the iter-2 span-dump kill (section 4 = 276 baskets @
# concurrency 4 -> ~4h makespan vs a flat 1400s wall -> ~250/276 abandoned to K-span). Fable fix wave:
#   * PG_ABSTRACTIVE_WRITER_CONCURRENCY 4 -> 24  (B4 env-value lever; box runs verify at 30)
#   * PG_MAX_CONCURRENT_LLM 5(default) -> 30     (REQUIRED: the writer LLM call acquires the GLOBAL
#       provider semaphore at openrouter_client.py:1889-1891; leaving it at 5 caps effective writer
#       concurrency at min(24,5)=5 AND makes the conc=24 scaled wall (7200s) undershoot the real
#       conc=5 makespan (~12000s) -> the wave abandons AGAIN. 30 == the proven verify configuration.)
#   * PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S 120 -> 300 (healthy calls measured 197-234s incl reasoning)
#   * PG_WRITER_WALL_BASKET_SCALED=1  (size the wall from the code makespan on the ACTUAL basket count)
#   * PG_WRITER_KSPAN_RECOVERY_PASS=1 (one bounded 2nd pass before any K-span dump)
#   * PG_WRITER_DEADLINE_TRANSPORT_AWARE=1 (default-ON; explicit)
# NOTHING drb_72-specific. Faithfulness gates UNCHANGED (numeric forward-match + context-level NLI;
# the lexical >=2-word overlap gate stays DELETED at this branch head). Same pinned checkpoints.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# ── activation flags (ghost-free slate, identical to iter-2) ──
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1
export PG_SECTION_BASKET_MAP=1
export PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1
export PG_VERIFIED_COMPOSE=1
export PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce
export PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1
export PG_RENDER_SEAM_SANITIZE=1
# ── B4 resilience levers (default-OFF -> ON) + throughput ──
export PG_WRITER_WALL_BASKET_SCALED=1
export PG_WRITER_KSPAN_RECOVERY_PASS=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=24
export PG_MAX_CONCURRENT_LLM=30
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=300
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=1400
export PG_ENTAILMENT_TOTAL_S=300
# ── §9.1.8 always-MAX token slate (z-ai/glm-5.2 real caps) ──
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=3
# ── SAME pinned checkpoints (cp2 s2_hamster_i1, cp3 s3_gear, cp4 s4_gear) ──
CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
OUT=/workspace/compose_wt/outputs/s5_gear_iter3
mkdir -p "$OUT/ckpt"
{
  echo "CP2=$CP2"; echo "CP3=$CP3"; echo "CP4=$CP4"
  echo "commit=$(git rev-parse HEAD)"
  echo "PG_ABSTRACTIVE_WRITER_CONCURRENCY=$PG_ABSTRACTIVE_WRITER_CONCURRENCY"
  echo "PG_MAX_CONCURRENT_LLM=$PG_MAX_CONCURRENT_LLM"
  echo "PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=$PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S"
  echo "PG_WRITER_WALL_BASKET_SCALED=$PG_WRITER_WALL_BASKET_SCALED"
  echo "PG_WRITER_KSPAN_RECOVERY_PASS=$PG_WRITER_KSPAN_RECOVERY_PASS"
} > "$OUT/inputs.txt"
setsid python -u scripts/run_s5_i3.py \
  --cp2 "$CP2" \
  --cp3 "$CP3" \
  --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" \
  --ckpt-dir "$OUT/ckpt" \
  --cap-primary 0 \
  < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
