#!/bin/bash
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# Full ghost-free flag slate (launch_gear_iter2 slate + iter3 model pins)
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1
export PG_SECTION_BASKET_MAP=1
export PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1
export PG_VERIFIED_COMPOSE=1
export PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce
export PG_WRITER_DEADLINE_TRANSPORT_AWARE=1
export PG_CROSS_SECTION_REPETITION_GUARD=1
export PG_ABSTRACTIVE_WRITER_CONCURRENCY=3
export PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S=90
export PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S=420
export PG_ABSTRACTIVE_WRITER_MAX_TOKENS=131072
export PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS=65536
export PG_S5_SPAN_CHAR_CAP=8000
export PG_MAX_PARALLEL_SECTIONS=2
export PG_GENERATOR_MODEL=z-ai/glm-5.2
export PG_ENTAILMENT_MODEL=z-ai/glm-5.2
export PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1
# PINNED inputs (best signed-off; also == newest per gear-rule)
CP4=/workspace/POLARIS/outputs/s4_gear/cp4_outline_snapshot.json
CP3=/workspace/POLARIS/outputs/s3_gear/cp3_basket_snapshot.json
CP2=/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json
OUT=/workspace/compose_wt/outputs/s5_gear_iter1_pinned
mkdir -p "$OUT/ckpt"
echo "USING CP4=$CP4" > "$OUT/inputs.txt"
echo "USING CP3=$CP3" >> "$OUT/inputs.txt"
echo "USING CP2=$CP2" >> "$OUT/inputs.txt"
# FAIL-LOUD preflight: synth_primary must be enabled AND ghost must be absent
python3 -c 'import sys; from src.polaris_graph.generator.verified_compose import _synth_primary_enabled as f; sys.exit(0 if f() else 42)' || { echo FAILLOUD_SYNTH_OFF; exit 42; }
GHOST=$(grep -c writer_numeric_dropped src/polaris_graph/generator/abstractive_writer.py)
if [ "$GHOST" != "0" ]; then echo FAILLOUD_GHOST_PRESENT=$GHOST; exit 43; fi
echo "PREFLIGHT_OK synth_enabled=1 ghost_hits=$GHOST"
setsid python -u scripts/run_s5_i3.py   --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4"   --out "$OUT/cp5_generation_snapshot.json"   --ckpt-dir "$OUT/ckpt"   --cap-primary 0   < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
