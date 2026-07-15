#!/bin/bash
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/clean_compose_wt
export PYTHONPATH=/workspace/clean_compose_wt PYTHONIOENCODING=utf-8
export PG_STRICT_VERIFY_ENTAILMENT=enforce PG_SYNTH_PRIMARY=1 PG_ABSTRACTIVE_WRITER=1
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1 PG_VERIFIED_COMPOSE=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=3 PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=90
export PG_ABSTRACTIVE_WRITER_MAX_RETRIES=1 PG_ABSTRACTIVE_WRITER_MAX_TOKENS=6000
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=3000 PG_S5_SPAN_CHAR_CAP=6000 MAXB=6
setsid python -u compose_small.py < /dev/null > /workspace/POLARIS/outputs/s5_clean_compose_opus/small.log 2>&1 &
echo PID=$!
