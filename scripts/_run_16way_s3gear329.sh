#!/usr/bin/env bash
# A/B CERTIFICATION HARNESS (NOT a normal launch) — the KNOWN-DEADLOCKING 16-way compose config.
# This config (PG_COMPOSE_BASKET_WORKERS=16 + PG_SIDE_JUDGE_MAX_CONCURRENCY=48) is the one that
# WEDGED 19/20 threads in futex_wait and was SIGKILLed at 328-basket scale. The P0 startup guard
# (src/polaris_graph/generator/compose_config_guard.py) now REFUSES it: this script will raise
# UnsafeComposeConfigError and exit UNLESS you set PG_COMPOSE_DEADLOCK_CONFIG_AB_CERTIFIED=1 to
# attest that a FULL-328 verdict-identity A/B (both no-hang AND verdict-identical) has passed. Do
# NOT set that flag casually — it is the contract that certifies the deadlock config safe to ship.
# For a NORMAL safe run use scripts/compose_agentic_report_s3gear329.py (pins the confirmed-safe
# config: PG_COMPOSE_BASKET_WORKERS=1 + side-judge 4-8 + PG_PARALLEL_SECTIONS=3 + off-loop).
cd "$(dirname "$0")/.."
set -a; . ./.env 2>/dev/null || true; set +a
set -uo pipefail

export PG_OUTLINE_AGENT=1
# SPEED knobs (this round's port + verify-lane env win):
export PG_COMPOSE_BASKET_WORKERS=16          # NEW: intra-section basket map-then-reduce (16-way)
export PG_PARALLEL_VERIFY=8                   # verify-lane workers
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16       # side-judge concurrency
export PG_JUDGE_BURST_SPREAD=lb               # load-balance judge burst
export PG_MAX_CONCURRENT_LLM=48               # global LLM semaphore (compose_fix: 0 429s @48)
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=24   # writer pre-pass concurrency
export PG_COMPOSE_TIMING=1                    # within-run effective-parallelism measurement

OUT="${1:-outputs/step_speed_16way}"
python scripts/compose_agentic_report_s3gear329.py \
  --corpus data/cp4_corpus_s3gear_329.corrected.json \
  --out-dir "$OUT" \
  --max-parallel 4 \
  --rq-drb-task 72
