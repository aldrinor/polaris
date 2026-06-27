"""I-wire-014 #1335 — validate the REAL in-tree _build_nli_prose_groups (post FIX-D guard)
against dedup_gold via the harness. Confirms the production code (not a standalone candidate)
matches the benchmarked-safe winner: distinct_claims_preserved_rate MUST = 1.0.

Run ON THE VM:  cd /root/polaris/outputs/audits/iwire014/benchmark && \
  PYTHONPATH=/root/polaris PG_CONSOLIDATION_NLI_PROSE=1 /opt/conda/bin/python dedup_intree_validate.py
"""
import os
import sys

sys.path.insert(0, ".")
import dedup_benchmark as db  # noqa: E402

os.environ.setdefault("PG_CONSOLIDATION_NLI_PROSE", "1")
from src.polaris_graph.generator.fact_dedup import _build_nli_prose_groups  # noqa: E402


def candidate_intree_nli(items):
    sections = {}
    idxmap = {}
    for it in sorted(items, key=lambda x: x["idx"]):
        cites = "".join(f"[{c}]" for c in (it.get("citations") or []))
        sent = (it["sentence"] + " " + cites).strip()
        lst = sections.setdefault(it["section"], [])
        idxmap[(it["section"], len(lst))] = it["idx"]
        lst.append(sent)
    section_order = list(sections.keys())
    groups = _build_nli_prose_groups(sections, section_order)
    dropped = set()
    for g in groups:
        for r in g.redundants:
            dropped.add(idxmap[(r.section, r.index)])
    return {it["idx"] for it in items if it["idx"] not in dropped}


def main():
    gold = db.load_gold()
    items = db.candidate_view(gold)
    print("=== IN-TREE _build_nli_prose_groups (guarded) vs dedup_gold ===")
    db.report("in-tree NLI prose dedup (PG_CONSOLIDATION_NLI_PROSE, guarded)", gold,
              candidate_intree_nli(items))


if __name__ == "__main__":
    main()
