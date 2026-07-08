"""wave-2 DEPTH disclosed-analyst harness — box2's REAL analytical block through the D3 screen.
RED (PG_ANALYST_SYNTHESIS_DISCLOSED_KEEP=0): the 31 uncited interpretive sentences DROP (disclosed=0).
GREEN (=1): they render under the disclosure label (disclosed>=25), a PLANTED numeric fabrication still
DROPS. Frozen input, deterministic, seconds. Usage: PYTHONPATH=/c/POLARIS python <this>
"""
import os, json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.update(PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED="1", PG_ANALYST_SYNTHESIS_BASKET_MODE="1",
                  PG_ANALYST_SYNTHESIS_BASKET_FULLTEXT="1")
from src.polaris_graph.generator.analyst_synthesis_deviation_check import screen_synthesis_against_baskets as screen
SC=r"C:\Users\msn\AppData\Local\Temp\claude\C--POLARIS\dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391\scratchpad"
biblio=json.load(open(SC+r"\box2_bibliography.json",encoding="utf-8"))
rows=json.load(open(SC+r"\box2_evidence_pool.json",encoding="utf-8"))
block=open(SC+r"\box2_synth_block.txt",encoding="utf-8",errors="replace").read()
# PLANTED fabrications (Codex+Fable depth-gate) — EVERY one must DROP even under disclosed-keep:
PLANTS={
 "numeric":       "This framework implies that generative AI eliminates 40% of all jobs by 2030.",
 "unhedged":      "Generative AI will replace all lawyers by the end of the decade.",
 "num_header":    "### Generative AI eliminates 40 percent of all jobs",
 "fake_author":   "Consistent with Fakenamez and Nobodyson, this suggests a complementary shift.",
 "cat_header":    "### Generative AI will replace all human workers",
 "spelled_pct":   "The literature suggests generative AI could eliminate forty percent of all jobs.",
 "spelled_teen":  "Evidence suggests generative AI may displace fifteen percent of all jobs.",
 "fraction":      "Evidence suggests a fifth of all jobs may be displaced.",
 "one_in_n":      "The literature suggests one in five workers could be affected.",
 "magnitude":     "This framework implies millions of workers may lose their roles.",
 "bare_half":     "Evidence suggests half of all jobs may be automated.",
 "bare_quarter":  "The literature implies a quarter of workers could be displaced.",
}
block=block+"\n\n"+"\n\n".join(PLANTS.values())
stub=lambda c,s: True
fails=[]
for flag,want_disc in (("0",False),("1",True)):
    os.environ["PG_ANALYST_SYNTHESIS_DISCLOSED_KEEP"]=flag
    body,tel=screen(block,biblio,rows,judge_fn=stub)
    disc=tel.get("synthesis_deviation_disclosed_count",0)
    framework="relative magnitudes of substitution and complementarity" in body
    plant_leaks=[k for k,v in PLANTS.items() if v.lstrip("#").strip()[:40] in body]
    print(f"DISCLOSED_KEEP={flag}: promoted={tel.get('synthesis_deviation_promoted_count',0)} disclosed={disc} dropped={tel.get('synthesis_deviation_dropped_count',0)} framework={framework} plant_leaks={plant_leaks}")
    if want_disc and not (disc>=25 and framework): fails.append(f"flag{flag}:depth-not-recovered(disc={disc})")
    if not want_disc and (disc>0 or framework): fails.append(f"flag{flag}:leaked-when-off")
    if plant_leaks: fails.append(f"flag{flag}:FABRICATION-LEAKED:{plant_leaks}")
print("\nRESULT:", "ALL_PASS" if not fails else "FAILS="+",".join(fails))
sys.exit(1 if fails else 0)
