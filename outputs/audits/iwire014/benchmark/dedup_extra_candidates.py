"""I-wire-014 FIX-D dedup candidate bake-off (run directly after the workflow agent
timed out). Plugs Jaccard, mutual-entailment-NLI, and a naive-cosine over-merge
comparison into the existing dedup_benchmark harness. Faithfulness gate:
distinct_claims_preserved_rate MUST = 1.0; winner = highest collapse with preserved = 1.0.

Run ON THE VM:  cd /root/polaris/outputs/audits/iwire014/benchmark && \
  PYTHONPATH=/root/polaris /opt/conda/bin/python dedup_extra_candidates.py
"""
import re
import sys

sys.path.insert(0, ".")
import dedup_benchmark as db  # noqa: E402


def _shingles(s, n=3):
    toks = re.findall(r"[a-z]+", s.lower())
    return {tuple(toks[i:i + n]) for i in range(max(0, len(toks) - n + 1))}


def _jaccard(a, b):
    return len(a & b) / len(a | b) if (a and b) else 0.0


def _nums(s):
    return set(re.findall(r"\d[\d,.]*", s))


def _citeset(it):
    return frozenset(it.get("citations") or [])


def _group_keepfirst(items, is_dup):
    """Within-section, keep the first member of each duplicate group (lowest idx),
    drop later members the candidate judges a repeat of an already-kept rep."""
    by_sec = {}
    for it in items:
        by_sec.setdefault(it["section"], []).append(it)
    dropped = set()
    for its in by_sec.values():
        its = sorted(its, key=lambda x: x["idx"])
        reps = []
        for it in its:
            if any(is_dup(rep, it) for rep in reps):
                dropped.add(it["idx"])
            else:
                reps.append(it)
    return {it["idx"] for it in items if it["idx"] not in dropped}


# ---- Candidate 1: content-word shingle Jaccard 0.82 + same-cite-set + number guard ----
def candidate_jaccard_setcites(items):
    def is_dup(a, b):
        if _citeset(a) != _citeset(b):
            return False
        if _nums(b["sentence"]) - _nums(a["sentence"]):
            return False  # b introduces a new number -> distinct claim, KEEP
        return _jaccard(_shingles(a["sentence"]), _shingles(b["sentence"])) >= 0.82
    return _group_keepfirst(items, is_dup)


# ---- Candidate 2: mutual-entailment NLI (deBERTa) + same-cite-set + number guard ----
def candidate_nli_mutual(items):
    import numpy as np
    from sentence_transformers import CrossEncoder
    model = CrossEncoder("cross-encoder/nli-deberta-v3-base", device="cuda")
    ENTAIL = 1  # label order: [contradiction, entailment, neutral]
    cache = {}

    def entail(p, h):
        key = (p, h)
        if key not in cache:
            logits = model.predict([(p, h)])[0]
            cache[key] = int(np.argmax(logits)) == ENTAIL
        return cache[key]

    def is_dup(a, b):
        if _citeset(a) != _citeset(b):
            return False
        if _nums(b["sentence"]) - _nums(a["sentence"]):
            return False
        # merge ONLY on proven semantic EQUIVALENCE: entailment both directions
        return entail(a["sentence"], b["sentence"]) and entail(b["sentence"], a["sentence"])
    return _group_keepfirst(items, is_dup)


# ---- Candidate 3 (COMPARISON, expected to OVER-MERGE): naive embedding cosine, NO guards ----
def candidate_cosine_naive(items, threshold=0.82):
    from sentence_transformers import SentenceTransformer, util
    m = SentenceTransformer("all-MiniLM-L6-v2", device="cuda")
    emb = {it["idx"]: m.encode(it["sentence"], convert_to_tensor=True) for it in items}

    def is_dup(a, b):  # deliberately NO cite-set / number guard -> can over-merge distinct claims
        return float(util.cos_sim(emb[a["idx"]], emb[b["idx"]])) >= threshold
    return _group_keepfirst(items, is_dup)


def main():
    gold = db.load_gold()
    items = db.candidate_view(gold)
    print("=" * 72)
    print("DEDUP candidate bake-off (faithfulness gate: preserved MUST = 1.0)")
    print("=" * 72)
    db.report("keep_all (baseline)", gold, db.candidate_keep_all(items))
    db.report("exact_text + SET cites (in-harness)", gold, db.candidate_exact_text_set_cites(items))
    db.report("jaccard_0.82 + set-cites + number-guard (PG_FACT_DEDUP_PROSE)", gold,
              candidate_jaccard_setcites(items))
    db.report("mutual_entailment_NLI + set-cites + number-guard (PG_CONSOLIDATION_NLI_PROSE)", gold,
              candidate_nli_mutual(items))
    db.report("naive_cosine_0.82 (COMPARISON: no guards, expect OVER-MERGE)", gold,
              candidate_cosine_naive(items))


if __name__ == "__main__":
    main()
