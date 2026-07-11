#!/bin/bash
# LEVER A/B (isolated section-4-only, NON-ACCEPTANCE lever-isolation): measure phase-2 dt for a FIXED
# section-4 basket subset (--cap-primary $CAP, deterministic first-N primary views => identical
# basket-id subset in both arms) at two global LLM-concurrency widths. Arm value comes from env
# PG_MAX_CONCURRENT_LLM. Everything else identical to launch_compose_fullcorpus.sh activation slate.
# Confound note: run ISOLATED (no other section, no live render) so section 4 owns the whole global
# LLM semaphore — this is the valid 16-arm the in-run overlap could not provide.
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
WT=/home/polaris/wt/compose_fix
cd "$WT" || exit 9
export PYTHONPATH="$WT" PYTHONIOENCODING=utf-8

export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1 PG_SECTION_BASKET_MAP=1 PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1 PG_VERIFIED_COMPOSE=1 PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1 PG_RENDER_SEAM_SANITIZE=1
export PG_WRITER_WALL_BASKET_SCALED=1 PG_WRITER_KSPAN_RECOVERY_PASS=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=12
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=300 PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=1400
export PG_ENTAILMENT_TOTAL_S=300
export PG_SIDE_JUDGE_MAX_CONCURRENCY=16 PG_ENTAILMENT_TOTAL_DEADLINE_RETRIES=1 PG_PARALLEL_VERIFY=8
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072 PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=1

# THE LEVER: global LLM concurrency width (arm passed via env, default 16)
export PG_MAX_CONCURRENT_LLM="${PG_MAX_CONCURRENT_LLM:-16}"
CAP="${CAP:-68}"

CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
OUT="$WT/outputs/s5_lever_llm${PG_MAX_CONCURRENT_LLM}"
mkdir -p "$OUT"
LOG="$OUT/lever.log"

export HB_MODE=offloop
echo "=== lever launch $(date -u) commit=$(git rev-parse HEAD) PG_MAX_CONCURRENT_LLM=$PG_MAX_CONCURRENT_LLM CAP=$CAP sections=4 ===" | tee "$LOG"
exec python -u scripts/_hb_probe_run.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" --sections 4 --cap-primary "$CAP" >> "$LOG" 2>&1
