"""wave-2 DEPTH stage-harness — run the D3 basket grounding on box2's REAL analytical-synthesis
block (frozen box2_synth_block.txt = the full 19k-char "Mechanism Interpretation" block with all
[N] markers intact), narrow-slice vs whole-basket full-text. Deterministic, seconds, no LLM.

KEY EMPIRICAL FINDING (this harness): the whole-basket full-text fix recovers ZERO on box2 —
the CITED synthesis sentences already ground on their direct_quote; the dropped "depth" is the
UNCITED interpretive connective tissue (the analytical framework), which the anti-fabrication floor
correctly refuses. So the real depth lever is NOT whole-basket grounding — it is either making the
composer ATTACH citations to interpretive synthesis, or a DISCLOSED analyst layer. This harness is
the seconds-level oracle that proves whichever real depth fix lands.

Usage: PYTHONPATH=/c/POLARIS python scripts/dr_benchmark/wave2_stage_depth.py
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ["PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED"] = "1"
os.environ["PG_ANALYST_SYNTHESIS_BASKET_MODE"] = "1"

from src.polaris_graph.generator.analyst_synthesis_deviation_check import (  # noqa: E402
    _resolve_sentence_span as resolve,
    _span_grounds_sentence as grounds,
)

SC = r"C:\Users\msn\AppData\Local\Temp\claude\C--POLARIS\dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391\scratchpad"
biblio = json.load(open(f"{SC}\\box2_bibliography.json", encoding="utf-8"))
rows = json.load(open(f"{SC}\\box2_evidence_pool.json", encoding="utf-8"))
block = open(f"{SC}\\box2_synth_block.txt", encoding="utf-8", errors="replace").read()

sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+(?=[A-Z"\[])', block) if len(s.strip()) >= 30]
cited = [s for s in sents if re.search(r"\[\d+\]", s)]
uncited = [s for s in sents if not re.search(r"\[\d+\]", s)]

narrow_ok = full_ok = recovered = 0
for s in cited:
    n = resolve(s, biblio, rows, full_text=False)
    f = resolve(s, biblio, rows, full_text=True)
    ng = bool(n.strip()) and grounds(s, n)
    fg = bool(f.strip()) and grounds(s, f)
    narrow_ok += ng
    full_ok += fg
    recovered += (not ng) and fg

print(f"synthesis sentences: {len(sents)}  cited: {len(cited)}  uncited: {len(uncited)}")
print(f"GROUND under NARROW (current): {narrow_ok}")
print(f"GROUND under WHOLE-BASKET FULLTEXT (committed fix): {full_ok}")
print(f"RECOVERED by whole-basket fix: {recovered}  <- 0 on box2: cited already ground on direct_quote")
print(f"UNCITED interpretive sentences (the real lost depth): {len(uncited)}  <- need composer-citations OR disclosed-analyst-layer")
print(f"\nbox2 real run dropped 38 = {len(uncited)} uncited + {38-len(uncited)} cited-ungrounded; promoted 42 ~ {narrow_ok} grounded.")
