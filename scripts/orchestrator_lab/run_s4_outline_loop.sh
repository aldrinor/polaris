#!/usr/bin/env bash
# S4 OUTLINE gear-loop runner (bot/sec-s4-outline-loop).
# GEAR RULE: every round resolve + use the NEWEST corpus cp3 so the outline auto-re-runs
# on the cleaned S2+S3 corpus the moment it lands. Two deterministic-then-live steps:
#   (1) build_bank.py : newest cp3 (+ paired cp2 enrichment) -> bank_plan.json  [offline, pure]
#   (2) outline_lab.py --mode plan : bank_plan.json -> cp4_outline_snapshot.json [ONE live GLM call]
# cp4.payload.final_plans carry title + focus + basket_ids + ev_ids.
set -euo pipefail

POLARIS=${POLARIS_ROOT:-/workspace/POLARIS}
# GEAR: newest cp3 by mtime (auto-picks the freshest cleaned S3 basket snapshot).
CP3=${CP3:-$(ls -t "$POLARIS"/outputs/s3_*/cp3_basket_snapshot.json | head -1)}
# cp2 corpus that cp3's basket members enrich against (paired; override CP2 when a new S2 lands).
CP2=${CP2:-$POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json}
DELIVERABLE=${DELIVERABLE:-$POLARIS/outputs/s4_vm_iter5/deliverable.json}
SCOPE=${SCOPE:-$POLARIS/outputs/s4_vm_iter5/scope.json}
MODEL=${PG_S4_OUTLINE_MODEL:-z-ai/glm-5.2}
RUN_DIR=${RUN_DIR:-outputs/s4_outline_loop_i1}

echo "[gear] newest cp3 = $CP3"
echo "[gear] paired cp2 = $CP2"
echo "[gear] run_dir    = $RUN_DIR  model=$MODEL"
mkdir -p "$RUN_DIR"

python scripts/orchestrator_lab/build_bank.py   --cp2 "$CP2" --cp3 "$CP3" --out "$RUN_DIR/bank_plan.json"   --deliverable "$DELIVERABLE" --scope "$SCOPE"

python scripts/orchestrator_lab/outline_lab.py   --bank "$RUN_DIR/bank_plan.json" --mode plan --model "$MODEL" --run-dir "$RUN_DIR"

echo "[gear] cp4 = $RUN_DIR/cp4_outline_snapshot.json"
