#!/usr/bin/env bash
# Fetch-junk hamster-loop retest step (runs on VM box2). Pulls the latest fix, re-fetches the
# leaking-URL subset with the fix ON, and prints the LEAK lines + summary.json (real_junk vs
# legit-reference FP). Arg 1 = round tag (e.g. r0). Read-only vs the pipeline; input hygiene test.
set -uo pipefail
cd /workspace/POLARIS
git pull --ff-only origin bot/I-deepfix-relaunch 2>&1 | tail -1
pkill -f fetch_corpus_replay 2>/dev/null || true
sleep 1
set -a; . ./.env 2>/dev/null; set +a
export PYTHONPATH=/workspace/POLARIS PYTHONIOENCODING=utf-8
SNAP=outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json
OUT="outputs/fetch_hamster_${1:-r}"
PAR="${2:-6}"
python3 scripts/fetch_corpus_replay.py --snapshot "$SNAP" --urls-file leak_urls.txt \
    --parallel "$PAR" --max-chars 8000 --out "$OUT" 2>&1 \
    | grep -E "\[LEAK\]|\[replay\] (DONE|SUMMARY)" | tail -80
echo "===SUMMARY_JSON==="
cat "$OUT/summary.json" 2>/dev/null || echo NO_SUMMARY
