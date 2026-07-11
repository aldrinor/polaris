#!/bin/bash
# Compose gear-loop iter 5 — builds on iter 4 (section-level crash RESUME + self-relaunch). Two changes,
# both faithfulness-NEUTRAL (numeric forward-match + context-level NLI entailment UNCHANGED; the lexical
# >=2-word overlap gate stays DELETED at this branch head; nothing question-tuned):
#   (A) GEAR RULE (operator 2026-07-10): iter-4 HARDCODED the pinned cp3/cp4 paths. iter-5 RESOLVES the
#       NEWEST outline cp4 AND newest corpus cp3 at launch (ls -t) so the compose gear auto-picks up new
#       S3/S4 rounds as they land — the gears turn into each other. The pinned s4_gear/s3_gear ARE the
#       newest today, so pin + newest coincide; the dynamic resolve keeps that true on the NEXT S3/S4 round
#       without a launcher edit. Both resolved paths are PRINTED for the round report.
#   (B) 429 SELF-CONTENTION (observed in the iter-4 run 08:33-09:02: repeated OpenRouter 429 backoff +
#       a 3-min stall while a second heavy OpenRouter job ran in a sibling worktree). Drop the compose's
#       OpenRouter concurrency (PG_MAX_CONCURRENT_LLM 30->16, writer 24->12) so the gear loop coexists with
#       sibling jobs on the shared OpenRouter rate limit with FEWER backoffs -> sections FINALIZE and reach
#       the iter-4 per-section checkpoint sooner (a kill then loses less work). max_tokens slate unchanged
#       (a CAP, not a target -> reasoning is never starved; §9.1.8).
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt || exit 9
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# -- activation flags (ghost-free slate, iter-4 identical) --
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
# -- B4 resilience levers + throughput (iter-4 proven) --
export PG_WRITER_WALL_BASKET_SCALED=1
export PG_WRITER_KSPAN_RECOVERY_PASS=1
# iter-5 (B): lower concurrency to cut 429 self-contention with sibling OpenRouter jobs.
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=12
export PG_MAX_CONCURRENT_LLM=16
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=300
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=1400
export PG_ENTAILMENT_TOTAL_S=300
# iter-5 (Fable P0): the NLI verify pre-pass speedup (0615bc5) is capped at 4 by the process-global
# side-judge semaphore (judge_concurrency.py DEFAULT_MAX_CONCURRENCY=4, tuned for a credibility-burst
# 429 storm, not compose). 0 429s at 128-way proves rate limit is not the ceiling; raise the cap so
# verify threads don't queue behind 4 slots. Transport-only, faithfulness-NEUTRAL.
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16
# iter-5 (Fable P1): a hung judge POST holds a semaphore slot for the full PG_ENTAILMENT_TOTAL_S. The
# code comment (entailment_judge.py:196) prescribes the run slate set this to 1 (=> up to 2 attempts on
# a hang vs the default 2 => 3x total_s of dead slot-hold). Faithfulness-NEUTRAL (same fail-closed sentinel).
export PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1
# -- §9.1.8 always-MAX token slate (z-ai/glm-5.2 real caps) --
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=2
# -- iter-5 (A): PINNED best inputs are the DEFAULT; the GEAR RULE resolves the NEWEST cp4+cp3 and uses
#    them when they are newer than the pin. Today pin == newest, so both resolve to s4_gear/s3_gear. --
CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
PIN_CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
PIN_CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
NEW_CP4=$(ls -t /workspace/POLARIS/outputs/s4_*/cp4_outline_snapshot.json 2>/dev/null | head -1)
NEW_CP3=$(ls -t /workspace/POLARIS/outputs/s3_*/cp3_basket_snapshot.json 2>/dev/null | head -1)
CP4=${NEW_CP4:-$PIN_CP4}
CP3=${NEW_CP3:-$PIN_CP3}
OUT=/workspace/compose_wt/outputs/s5_gear_iter5
CKPT=$OUT/ckpt
LOG=$OUT/compose.log
mkdir -p "$CKPT"
# -- FAIL-LOUD ghost-free pre-flight (operator P0 wiring lock) --
GHOST=$(grep -c writer_numeric_dropped src/polaris_graph/generator/abstractive_writer.py || true)
if [ "$GHOST" != "0" ]; then
  echo "[ABORT] ghost present: writer_numeric_dropped count=$GHOST" | tee -a "$LOG"; exit 3
fi
if ! python -u -c "from src.polaris_graph.generator.multi_section_generator import _synth_primary_enabled; import sys; sys.exit(0 if _synth_primary_enabled() else 7)"; then
  echo "[ABORT] _synth_primary_enabled() is False under this env slate" | tee -a "$LOG"; exit 4
fi
echo "[preflight] ghost_absent(writer_numeric_dropped=0) AND synth_primary_enabled=True -> OK" | tee -a "$LOG"
{
  echo "=== iter-5 launch $(date -u) ==="
  echo "CP2=$CP2"; echo "CP3(resolved)=$CP3"; echo "CP4(resolved)=$CP4"
  echo "pin_cp3=$PIN_CP3 newest_cp3=$NEW_CP3"; echo "pin_cp4=$PIN_CP4 newest_cp4=$NEW_CP4"
  echo "commit=$(git rev-parse HEAD)"
  echo "PG_MAX_CONCURRENT_LLM=$PG_MAX_CONCURRENT_LLM PG_ABSTRACTIVE_WRITER_CONCURRENCY=$PG_ABSTRACTIVE_WRITER_CONCURRENCY"
} | tee -a "$LOG"
for attempt in $(seq 1 8); do
  [ -f "$OUT/cp5_generation_snapshot.json" ] && { echo "[loop] cp5 present -> DONE" | tee -a "$LOG"; break; }
  echo "=== [loop] attempt $attempt START $(date -u) ===" | tee -a "$LOG"
  python -u scripts/run_s5_i3.py     --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4"     --out "$OUT/cp5_generation_snapshot.json"     --ckpt-dir "$CKPT"     --cap-primary 0 < /dev/null >> "$LOG" 2>&1
  echo "=== [loop] attempt $attempt EXIT rc=$? $(date -u) ===" | tee -a "$LOG"
  [ -f "$OUT/cp5_generation_snapshot.json" ] && { echo "[loop] cp5 written -> DONE" | tee -a "$LOG"; break; }
  sleep 5
done
echo "=== iter-5 loop finished $(date -u) cp5_exists=$([ -f "$OUT/cp5_generation_snapshot.json" ] && echo yes || echo no) ===" | tee -a "$LOG"
