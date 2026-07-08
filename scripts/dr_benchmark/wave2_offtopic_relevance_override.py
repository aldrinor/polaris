"""I-deepfix-001 drb_72: prove the off-topic/relevance-conflict fix on the FROZEN box2 corpus.

BUG: _is_confirmed_offtopic buried sources with content_relevance_label='relevant' (weight 1.0)
whenever topic_offtopic_demoted=True — burying the SEMINAL papers (GPTs-are-GPTs, World Bank,
Humlum). FIX (PG_OFFTOPIC_RELEVANCE_OVERRIDE, default ON): a positive content-relevance verdict
overrides the conflicting off-topic flag => KEEP.

GREEN iff: with the flag ON, the seminal relevant-but-topic-demoted papers are NO LONGER
confirmed-off-topic (un-buried); a GENUINE off-topic row (demoted label, no positive relevance)
is STILL confirmed-off-topic; flag OFF reproduces the legacy (buried) behaviour byte-identically.
Deterministic, seconds, no LLM. Usage: PYTHONPATH=/c/POLARIS python <this> <corpus_snapshot.json>
"""
import json
import os
import sys

sys.path.insert(0, os.getcwd())
from src.polaris_graph.generator import weighted_enrichment as we  # noqa: E402

SNAP = sys.argv[1] if len(sys.argv) > 1 else "corpus_snapshot.json"
rows = {r.get("evidence_id"): r for r in (json.load(open(SNAP, encoding="utf-8")).get("evidence_for_gen") or [])}

# seminal papers: content-relevance RELEVANT but topic_offtopic_demoted=True (must UN-bury)
SEMINAL = ["ev_882", "ev_1018", "ev_1153", "ev_894", "ev_914"]
# genuine off-topic control: content_relevance_label demoted, NOT positive (must stay suppressed)
CONTROL_OFFTOPIC = [
    eid for eid, r in rows.items()
    if str(r.get("content_relevance_label", "")).lower() in ("demoted", "escalated_demoted")
    and str(r.get("content_relevance_label", "")).lower() not in ("relevant", "escalated_relevant")
    and r.get("topic_offtopic_demoted") is not True
][:5]

fails = []


def check(flag_val):
    os.environ["PG_OFFTOPIC_RELEVANCE_OVERRIDE"] = flag_val
    seminal_buried = [e for e in SEMINAL if e in rows and we._is_confirmed_offtopic(rows[e])]
    control_suppressed = [e for e in CONTROL_OFFTOPIC if we._is_confirmed_offtopic(rows[e])]
    return seminal_buried, control_suppressed


on_buried, on_ctrl = check("1")
off_buried, off_ctrl = check("0")

present = [e for e in SEMINAL if e in rows]
print("seminal present:", present)
print(f"FLAG ON : seminal still buried={on_buried}  genuine-offtopic still suppressed={len(on_ctrl)}/{len(CONTROL_OFFTOPIC)}")
print(f"FLAG OFF: seminal still buried={off_buried}  (legacy: these SHOULD be buried)")

if on_buried:
    fails.append(f"ON still buries seminal {on_buried}")
if len(on_ctrl) != len(CONTROL_OFFTOPIC):
    fails.append(f"ON let genuine off-topic through ({len(on_ctrl)}/{len(CONTROL_OFFTOPIC)} suppressed)")
# the fix must MATTER: OFF must bury at least one seminal that ON keeps
if set(off_buried) <= set(on_buried):
    fails.append("no-op: OFF does not bury more than ON (fix has no effect)")

print("\nRESULT:", "GREEN" if not fails else "FAILS=" + "; ".join(fails))
sys.exit(1 if fails else 0)
