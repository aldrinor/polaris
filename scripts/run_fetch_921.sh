#!/usr/bin/env bash
# Crash-resilient full-corpus (921 URL) fetch junk read (runs on VM box2). Runs the replay scanner
# with --resume in a retry loop: the scanner writes results.jsonl incrementally, so a crawler EPIPE
# crash can't kill the run — each retry picks up where it left off. Arg1 = parallelism (default 48).
set -uo pipefail
cd /workspace/POLARIS
git pull --ff-only origin bot/I-deepfix-relaunch 2>&1 | tail -1
set -a; . ./.env 2>/dev/null; set +a
export PYTHONPATH=/workspace/POLARIS PYTHONIOENCODING=utf-8
SNAP=outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json
OUT="outputs/fetch_921_$(date -u +%Y%m%dT%H%M%SZ)"
PAR="${1:-48}"
mkdir -p "$OUT"
echo "OUT=$OUT parallel=$PAR"
for attempt in 1 2 3 4 5 6 7 8; do
  echo "=== attempt $attempt (parallel=$PAR) ==="
  python3 scripts/fetch_corpus_replay.py --snapshot "$SNAP" --parallel "$PAR" --max-chars 8000 \
      --out "$OUT" --resume 2>&1 | grep -E "\[LEAK\]|\[replay\] (DONE|SUMMARY|resume|[0-9]+/[0-9])" | tail -30 || true
  if [ -f "$OUT/summary.json" ]; then echo "=== COMPLETE at attempt $attempt ==="; break; fi
  DONE=$(wc -l < "$OUT/results.jsonl" 2>/dev/null || echo 0)
  echo "=== crashed before summary; $DONE done so far; resuming ==="
  if [ "$PAR" -gt 16 ]; then PAR=$((PAR-8)); fi   # back off parallelism on repeated crashes
  sleep 2
done
echo "===SUMMARY_JSON==="
cat "$OUT/summary.json" 2>/dev/null || echo NO_SUMMARY
echo "OUT=$OUT"
