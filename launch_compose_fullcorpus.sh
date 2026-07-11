#!/bin/bash
# FULL-CORPUS render of THIS worktree's off-loop fix (bot/compose-fix @ HEAD), with the heartbeat +
# phase-2 concurrency probe attached to take the top-line corpus number AND prove achieved
# concurrency at scale (loop-gap < 2s, all sections' phase-2 interleaving).
#
# NB: launch_compose_gear_iter5.sh cds to /workspace/compose_wt — a SEPARATE worktree pinned at the
# PRE-FIX commit eff82fb (branch bot/sec-s5-compose-loop). Running THAT would NOT exercise this fix.
# This launcher runs MY worktree only.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
WT=/home/polaris/wt/compose_fix
cd "$WT" || exit 9
export PYTHONPATH="$WT" PYTHONIOENCODING=utf-8

# -- activation flags (ghost-free slate, iter-5 identical) --
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1 PG_SECTION_BASKET_MAP=1 PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1 PG_VERIFIED_COMPOSE=1 PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1 PG_RENDER_SEAM_SANITIZE=1
export PG_WRITER_WALL_BASKET_SCALED=1 PG_WRITER_KSPAN_RECOVERY_PASS=1

# -- throughput/reliability knobs (iter-5 proven) --
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=12 PG_MAX_CONCURRENT_LLM=16
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=300 PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=1400
export PG_ENTAILMENT_TOTAL_S=300
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16 PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 PG_PARALLEL_VERIFY=8

# -- §9.1.8 always-MAX token slate (z-ai/glm-5.2 real caps) --
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072 PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000

# -- THE LEVER UNDER TEST: lift section parallelism 2 -> 4 (Fable: lift parallelism first) --
export PG_MAX_PARALLEL_SECTIONS="${PG_MAX_PARALLEL_SECTIONS:-4}"

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
OUT="$WT/outputs/s5_fullcorpus"
mkdir -p "$OUT"
LOG="$OUT/fullcorpus.log"

# heartbeat probe attached (offloop = real to_thread; measures loop-gap + phase2 concurrency + wall)
export HB_MODE=offloop
echo "=== fullcorpus launch $(date -u) commit=$(git rev-parse HEAD) PG_MAX_PARALLEL_SECTIONS=$PG_MAX_PARALLEL_SECTIONS ===" | tee "$LOG"
exec python -u scripts/_hb_probe_run.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" --cap-primary 0 >> "$LOG" 2>&1
