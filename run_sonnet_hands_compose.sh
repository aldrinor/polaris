#!/bin/bash
# Sonnet-hands compose run: signed-off compose_wt code, cp2/cp3/cp4 from outline step,
# cap-primary 8 (bounded, disclosed), foreground with hard timeout, NO nohup/tail -f.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt || exit 9
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# -- activation flags (ghost-free slate, matches iter-5 signed-off launcher) --
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
export PG_WRITER_WALL_BASKET_SCALED=1
export PG_WRITER_KSPAN_RECOVERY_PASS=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=12
export PG_MAX_CONCURRENT_LLM=16
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=300
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=1400
export PG_ENTAILMENT_TOTAL_S=300
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=2

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
OUT=/workspace/compose_wt/outputs/s5_sonnet_hands
CKPT=$OUT/ckpt
LOG=$OUT/compose.log
mkdir -p "$CKPT"

# fail-loud ghost-free preflight (same as signed-off launcher)
GHOST=$(grep -c writer_numeric_dropped src/polaris_graph/generator/abstractive_writer.py || true)
if [ "$GHOST" != "0" ]; then
  echo "[ABORT] ghost present: writer_numeric_dropped count=$GHOST" | tee -a "$LOG"; exit 3
fi
if ! python -u -c "from src.polaris_graph.generator.multi_section_generator import _synth_primary_enabled; import sys; sys.exit(0 if _synth_primary_enabled() else 7)"; then
  echo "[ABORT] _synth_primary_enabled() is False under this env slate" | tee -a "$LOG"; exit 4
fi
echo "[preflight] ghost_absent AND synth_primary_enabled=True -> OK" | tee -a "$LOG"

{
  echo "=== sonnet-hands compose launch $(date -u) ==="
  echo "CP2=$CP2"; echo "CP3=$CP3"; echo "CP4=$CP4"
  echo "commit=$(git rev-parse HEAD)"
  echo "cap_primary=8 (BOUNDED per section -- disclosed subset, not maximal depth)"
} | tee -a "$LOG"

timeout 2700 python -u scripts/run_s5_i3.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" \
  --ckpt-dir "$CKPT" \
  --cap-primary 8 < /dev/null >> "$LOG" 2>&1
RC=$?
echo "EXIT=$RC" | tee -a "$LOG"
echo "cp5_exists=$([ -f "$OUT/cp5_generation_snapshot.json" ] && echo yes || echo no)" | tee -a "$LOG"
