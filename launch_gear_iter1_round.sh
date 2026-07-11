#!/bin/bash
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
cd /workspace/compose_wt
export PYTHONPATH=/workspace/compose_wt PYTHONIOENCODING=utf-8
# --- current committed gear-loop config (HEAD, Fable fix waves) ---
export PG_SECTION_BASKET_MAP=1
export PG_COMPOSE_NO_RAW_SPAN_FALLBACK=1
export PG_SYNTH_PRIMARY=1
export PG_ABSTRACTIVE_WRITER=1
export PG_VERIFIED_COMPOSE=1
export PG_VERIFIED_COMPOSE_MULTICITED=1
export PG_STRICT_VERIFY_ENTAILMENT=enforce
export PG_CROSS_SECTION_REPETITION_GUARD=1
export PG_GENERATOR_MODEL=z-ai/glm-5.2
export PG_ENTAILMENT_MODEL=z-ai/glm-5.2
export PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY=1
CP4=$(ls -t /workspace/POLARIS/outputs/s4_*/cp4_outline_snapshot.json | head -1)
CP3=$(ls -t /workspace/POLARIS/outputs/s3_*/cp3_basket_snapshot.json | head -1)
CP2=$(ls -t /workspace/POLARIS/outputs/s2_*/cp2_corpus_snapshot.json | head -1)
OUT=/workspace/compose_wt/outputs/s5_gear_iter1
mkdir -p "$OUT/ckpt"
echo "USING CP4=$CP4" > "$OUT/inputs.txt"
echo "USING CP3=$CP3" >> "$OUT/inputs.txt"
echo "USING CP2=$CP2" >> "$OUT/inputs.txt"
cat "$OUT/inputs.txt"
setsid python -u scripts/run_s5_i3.py \
  --cp2 "$CP2" --cp3 "$CP3" --cp4 "$CP4" \
  --out "$OUT/cp5_generation_snapshot.json" \
  --ckpt-dir "$OUT/ckpt" \
  --cap-primary 5 \
  < /dev/null > "$OUT/compose.log" 2>&1 &
echo "PID=$!"
