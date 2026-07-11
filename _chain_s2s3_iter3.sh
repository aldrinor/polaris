#!/usr/bin/env bash
set -o pipefail
cd /workspace/s2s3_wt
set -a; . /workspace/POLARIS/.env 2>/dev/null; set +a
export PYTHONPATH=/workspace/s2s3_wt PYTHONIOENCODING=utf-8
export PG_CONSOLIDATION_NLI_DEVICE=cuda:0 PG_CONSOLIDATION_NLI_EMBED_DEVICE=cuda:0
export PG_CONSOLIDATION_NLI_MAX_PAIRS=200000 PG_CONSOLIDATION_NLI_WALL_SECONDS=1800
export PG_FINDING_DEDUP_NLI_MAX_PAIRS=200000 PG_FINDING_DEDUP_NLI_WALL_SECONDS=1800
RAW=/workspace/POLARIS/outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json
echo "[chain] $(date -u) S2 start — regenerate cp2 (P0-2 question-deliverable anchors default ON), parallel=16"
python3 scripts/s2_select_replay.py --snapshot "$RAW" --out outputs/s2s3_repass/s2 --parallel 16 > outputs/s2s3_repass/s2_run_iter3.log 2>&1
rc=$?; echo "[chain] $(date -u) S2 rc=$rc"
if [ $rc -ne 0 ]; then echo "[chain] S2 FAILED rc=$rc — aborting chain (S3 not run)"; exit $rc; fi
echo "[chain] $(date -u) S3 start — full NLI on cuda:0 (embed-block + numeric-strict + title-union + nonclaim-fold)"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python3 scripts/s3_consolidate_replay.py --cp2 outputs/s2s3_repass/s2/cp2_corpus_snapshot.json --out outputs/s2s3_repass/s3 > outputs/s2s3_repass/s3_run_iter3.log 2>&1
rc=$?; echo "[chain] $(date -u) S3 rc=$rc DONE"
