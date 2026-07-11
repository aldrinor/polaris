#!/bin/bash
# Compose gear-loop iter 4 — builds on iter 3. The iter-3 run (PID 768574) drafted 3/5 sections with
# abandoned=0 (iter-3 throughput fix WORKS) but was externally SIGKILLed at 08:19:57 ~1 min into a
# section finalization after 1h15m; the per-section checkpoints were never READ BACK, so the whole wave
# was lost. iter-4 fix (run_s5_i3.py "Fix 9"): SECTION-LEVEL crash RESUME — load any completed per-section
# checkpoint and skip recomposing it, SHA-gated on the three inputs (a corpus/outline change invalidates
# stale drafts => recompose = gear rule honored). This launcher wraps the compose in a self-relaunch loop
# so an external kill AUTO-RESUMES at the closest checkpoint (operator ground rule 2026-07-01) — the gear
# loop makes guaranteed forward progress. MAX_PARALLEL_SECTIONS 3->2 staggers section completion so more
# sections checkpoint before any kill. Faithfulness UNCHANGED (numeric forward-match + context-level NLI;
# the lexical >=2-word overlap gate stays DELETED at this branch head). NOTHING question-tuned.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt || exit 9
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# ── activation flags (ghost-free slate, iter-3 identical) ──
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
# ── B4 resilience levers + throughput (iter-3 proven) ──
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
# iter-4: stagger section completion so finished sections checkpoint before any external kill.
export PG_MAX_PARALLEL_SECTIONS=2
# ── PINNED-INPUTS lock (operator 2026-07-10): the best signed-off outline + cleaned corpus. These ARE
#    also the newest s4_*/s3_* rounds (verified by ls -t at launch), so the gear rule + the pin coincide.
CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
OUT=/workspace/compose_wt/outputs/s5_gear_iter4
CKPT=$OUT/ckpt
LOG=$OUT/compose.log
mkdir -p "$CKPT"

# ── FAIL-LOUD ghost-free pre-flight (operator P0 wiring lock): never produce a cp5 unless the ghost is
#    absent AND synth_primary is the primary body producer. ──
GHOST=$(grep -c writer_numeric_dropped src/polaris_graph/generator/abstractive_writer.py || true)
if [ "$GHOST" != "0" ]; then
  echo "[ABORT] ghost present: writer_numeric_dropped count=$GHOST in imported abstractive_writer.py" | tee -a "$LOG"
  exit 3
fi
if ! python -u -c "from src.polaris_graph.generator.multi_section_generator import _synth_primary_enabled; import sys; sys.exit(0 if _synth_primary_enabled() else 7)"; then
  echo "[ABORT] _synth_primary_enabled() is False under this env slate" | tee -a "$LOG"
  exit 4
fi
echo "[preflight] ghost_absent(writer_numeric_dropped=0) AND synth_primary_enabled=True -> OK" | tee -a "$LOG"

{
  echo "=== iter-4 launch $(date -u) ==="
  echo "CP2=$CP2"; echo "CP3=$CP3"; echo "CP4=$CP4"
  echo "newest_cp4=$(ls -t /workspace/POLARIS/outputs/s4_*/cp4_outline_snapshot.json 2>/dev/null | head -1)"
  echo "newest_cp3=$(ls -t /workspace/POLARIS/outputs/s3_*/cp3_basket_snapshot.json 2>/dev/null | head -1)"
  echo "commit=$(git rev-parse HEAD)"
  echo "PG_MAX_PARALLEL_SECTIONS=$PG_MAX_PARALLEL_SECTIONS"
} | tee -a "$LOG"

# ── self-relaunch loop: each attempt RESUMES finished sections (Fix 9) + composes the rest; stops when
#    cp5 is written. Bounded attempts so a genuinely-failing section can't loop forever. One python at a
#    time (§8.4 resource discipline). ──
for attempt in $(seq 1 8); do
  if [ -f "$OUT/cp5_generation_snapshot.json" ]; then
    echo "[loop] cp5 present -> DONE (attempt $attempt not needed)" | tee -a "$LOG"; break
  fi
  echo "=== [loop] attempt $attempt START $(date -u) ===" | tee -a "$LOG"
  python -u scripts/run_s5_i3.py \
    --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
    --out "$OUT/cp5_generation_snapshot.json" \
    --ckpt-dir "$CKPT" \
    --cap-primary 0 < /dev/null >> "$LOG" 2>&1
  rc=$?
  echo "=== [loop] attempt $attempt EXIT rc=$rc $(date -u) ===" | tee -a "$LOG"
  if [ -f "$OUT/cp5_generation_snapshot.json" ]; then
    echo "[loop] cp5 written -> DONE" | tee -a "$LOG"; break
  fi
  sleep 5
done
echo "=== iter-4 loop finished $(date -u) cp5_exists=$([ -f "$OUT/cp5_generation_snapshot.json" ] && echo yes || echo no) ===" | tee -a "$LOG"
