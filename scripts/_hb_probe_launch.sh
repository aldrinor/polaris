#!/bin/bash
# SMALL heartbeat/phase-2 concurrency probe launcher (compose off-loop fix).
# Runs 2 sections, cap-primary 1, small token caps + short deadlines to conserve budget.
# HB_MODE (offloop|onloop) chooses treatment vs control. Runs MY worktree code only.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
WT=/home/polaris/wt/compose_fix
cd "$WT" || exit 9
export PYTHONPATH="$WT" PYTHONIOENCODING=utf-8

# activation flag slate (from launch_compose_gear_iter5.sh)
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

# the P0/P1 knobs under test
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16
export PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1
export PG_PARALLEL_VERIFY=8
export PG_MAX_PARALLEL_SECTIONS=2

# SMALL/FAST transport caps (do NOT affect the concurrency mechanism; keep budget low + run short)
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=8
export PG_MAX_CONCURRENT_LLM=16
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=90
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=300
export PG_ENTAILMENT_TOTAL_S=60
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=8000
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=4000
export PG_SECTION_MAX_TOKENS=8000
export PG_S5_SPAN_CHAR_CAP=8000

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json

MODE="${HB_MODE:-offloop}"
OUT="$WT/.probe_out_${MODE}.json"

export HB_MODE="$MODE"
exec python scripts/_hb_probe_run.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT" --sections 0,1 --cap-primary "${CAP:-1}"
