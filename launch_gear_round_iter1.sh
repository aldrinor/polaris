#!/bin/bash
# Compose gear-loop iter 1 (fresh session 2026-07-10): run ghost-free worktree code on
# PINNED best inputs (s4_gear outline + s3_gear cleaned corpus). Full ghost-free flag slate,
# all-GLM-5.2 (same-family permit per pinned goal), token-MAX (no truncation->fallback).
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# --- FULL ghost-free flag slate ---
export PG_SECTION_BASKET_MAP=1
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1
export PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1
export PG_VERIFIED_COMPOSE=1
export PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce
export PG_CROSS_SECTION_REPETITION_GUARD=1
# --- all-GLM-5.2 (pinned goal) + same-family permit ---
export PG_GENERATOR_MODEL=z-ai/glm-5.2
export PG_ENTAILMENT_MODEL=z-ai/glm-5.2
export PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1
# --- writer reliability + token MAX (avoid truncation->fallback, §9.1.8) ---
export PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=3
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=90
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=420
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=2
export PG_JUDGE_PROVIDER_ROTATE=1
export PG_ENTAILMENT_TOTAL_S=600
# --- PINNED inputs (also the NEWEST s4_*/s3_* per GEAR RULE) ---
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
OUT=/workspace/compose_wt/outputs/s5_gear_round_iter1
mkdir -p "$OUT/ckpt"
echo "USING CP4=$CP4" | tee "$OUT/inputs.txt"
echo "USING CP3=$CP3" | tee -a "$OUT/inputs.txt"
echo "USING CP2=$CP2" | tee -a "$OUT/inputs.txt"
# --- FAIL-LOUD preflight: synth_primary ON + ghost absent, else ABORT (no cp5) ---
python3 - <<'PY'
import os, sys
sys.path.insert(0, "/workspace/compose_wt")
from src.polaris_graph.generator.verified_compose import _synth_primary_enabled
import src.polaris_graph.generator.abstractive_writer as aw
if not _synth_primary_enabled():
    sys.stderr.write("ABORT: _synth_primary_enabled() is False\n"); sys.exit(3)
src = open(aw.__file__, encoding="utf-8").read()
if src.count("writer_numeric_dropped") != 0:
    sys.stderr.write("ABORT: ghost present (writer_numeric_dropped in abstractive_writer)\n"); sys.exit(4)
print("[preflight] synth_primary ON, ghost absent -- OK")
PY
if [ $? -ne 0 ]; then echo "PREFLIGHT FAILED -- aborting, no cp5"; exit 1; fi
setsid python -u scripts/run_s5_i3.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" \
  --ckpt-dir "$OUT/ckpt" \
  --cap-primary 5 \
  < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
