#!/usr/bin/env bash
set -o pipefail
cd /workspace/s2s3_wt
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
export PYTHONPATH=/workspace/s2s3_wt PYTHONIOENCODING=utf-8 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=0
export PG_CONSOLIDATION_NLI_DEVICE=cuda:0 PG_CONSOLIDATION_NLI_EMBED_DEVICE=cuda:0
export PG_FINDING_DEDUP_NLI_DEVICE=cuda:0 PG_FINDING_DEDUP_NLI_EMBED_DEVICE=cuda:0
export PG_CONSOLIDATION_NLI_MAX_PAIRS=200000 PG_CONSOLIDATION_NLI_WALL_SECONDS=900
export PG_FINDING_DEDUP_NLI_MAX_PAIRS=200000 PG_FINDING_DEDUP_NLI_WALL_SECONDS=900
echo "[s3gpu] $(date -u) start cuda:0 wall=900/leg"
python3 scripts/s3_consolidate_replay.py --cp2 outputs/s2s3_repass/s2/cp2_corpus_snapshot.json --out outputs/s2s3_repass/s3 > outputs/s2s3_repass/s3_run_iter3.log 2>&1
echo "[s3gpu] $(date -u) rc=$? DONE"
