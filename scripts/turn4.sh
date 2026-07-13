#!/usr/bin/env bash
# TURN 4 — the evidence turn.
#
# Turn 3 shipped 8,012 words carrying TWO quantitative findings. Cellcog ships 202. The judge, on the
# criterion where we score 4.0 against its 9.2: "rarely presents quantitative evidence clearly...
# citations are named but findings are missing."
#
# Four stacked bugs caused it, and each one alone would have been survivable:
#   FETCH    asked for the published article, so Autor/Levy/Murnane (4,743 cites) came back "paywalled"
#            while its free NBER working-paper version sat there unrequested.
#   EXTRACT  never asked for numbers: 1,825 figures in text we already held became 31 card-spans.
#   WRITE    walked past even those -- six verified findings sat in the cards and never reached the page.
#   GATE     then correctly deleted whatever numbers survived, because it could not find them in spans
#            that never contained them. The gate was STARVING, not censoring. Relaxing it -- which was
#            on the table -- would have "fixed" this by shipping fabrications.
#
# This turn changes ONE thing in kind: THE REPORT NOW CARRIES ITS EVIDENCE. Nothing about the
# faithfulness contract is relaxed; every figure is still checked against its own source span, and the
# canary must stay green or nothing composes.
set -euo pipefail
cd /home/polaris/wt/flywheel
set -a && . ./.env && set +a

echo "=== [0/5] the door must be shut before anything ships ==="
python scripts/test_gate_is_wired.py | tail -2

echo
echo "=== [1/5] merge the corpora (two fetchers, one file, last writer wins -- so merge, do not trust) ==="
cp -n outputs/evidence_cards.json outputs/evidence_cards.turn3.json 2>/dev/null || true
cp -n outputs/cellcog_arm/report.md outputs/cellcog_arm/report_turn3.md 2>/dev/null || true
python scripts/merge_corpus.py outputs/journal_corpus_content.postdeep.json outputs/journal_corpus_content.json

echo
echo "=== [2/5] re-extract evidence cards -- NUMBERS FIRST, figure must be IN its own span ==="
python -u scripts/cellcog_composer.py --extract

echo
echo "=== [3/5] what did we actually harvest? ==="
python - <<'PY'
import json, re
c = json.load(open('outputs/evidence_cards.json'))
NUM = re.compile(r'\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b|\b\d{2,}\b')
YEAR = re.compile(r'\b(?:1[89]|20)\d\d\b')
q = [x for x in c if NUM.findall(YEAR.sub(' ', x.get('claim') or ''))]
print(f'  cards            : {len(c)}      (turn 3: 133)')
print(f'  QUANTITATIVE cards: {len(q)}      (turn 3: 31 spans with any digit; 2 reached the page)')
print(f'  papers represented: {len({x["doi"] for x in c})}')
PY

echo
echo "=== [4/5] compose ==="
python -u scripts/cellcog_composer.py --write

echo
echo "=== [5/5] did the evidence reach the page? ==="
python - <<'PY'
import re
t = re.sub(r'(?m)^#.*$', '', open('outputs/cellcog_arm/report.md').read())
n = re.findall(r'\b\d+(?:\.\d+)?\s*(?:percent|%|percentage points|pp)\b|\b\d+\.\d+\b', t)
w = len(t.split())
print(f'  words                : {w:,}')
print(f'  QUANTITATIVE CLAIMS  : {len(n)}   ({1000*len(n)/max(w,1):.1f} per 1,000 words)')
print(f'      turn 3: 2 (0.2/1k)  |  bodhi: 43 (9.9/1k)  |  CELLCOG: 202 (12.4/1k)')
print(f'  table rows           : {open("outputs/cellcog_arm/report.md").read().count(chr(10)+"|") - 2}')
PY
echo
echo "TURN 4 COMPOSED. Score it against the pinned baseline before believing anything."
