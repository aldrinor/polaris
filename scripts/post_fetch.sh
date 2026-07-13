#!/usr/bin/env bash
# Runs the moment wp_fetch exits. Order matters:
#   1. MERGE  — two fetchers wrote the same file; last writer wins, so merge by DOI keeping the most text
#   2. TRUTH  — re-derive every label FROM ITS CONTENT (14 labels were lying: Frey & Osborne was a
#               548-word abstract stamped FULLTEXT; 12 papers held ZERO WORDS and counted as evidence)
set -uo pipefail
cd /home/polaris/wt/flywheel
while pgrep -f 'python.*wp_fetch' >/dev/null; do sleep 30; done
echo "=== wp_fetch finished ==="
tail -2 outputs/wp_fetch.log
echo; echo "=== merge (postdeep snapshot + wp_fetch result) ==="
python scripts/merge_corpus.py outputs/journal_corpus_content.postdeep.json outputs/journal_corpus_content.json | tail -8
echo; echo "=== corpus truth ==="
python scripts/corpus_truth.py --fix | tail -10
git add -A && git commit -q -m "corpus after working-paper recovery: labels re-derived from content" && git push -q origin flywheel-v1 && echo "PUSHED $(git rev-parse --short HEAD)"
