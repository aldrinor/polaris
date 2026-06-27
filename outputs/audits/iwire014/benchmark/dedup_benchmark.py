"""DEDUP scoring harness for the iwire014 benchmark.

Given a candidate dedup function (pluggable slot), scores it against dedup_gold.json:

  paraphrase_repeats_collapsed_rate
      = (paraphrase_repeat items the candidate DROPPED) / (total paraphrase_repeat items)
      How well the candidate removes true paraphrase-repeats. Higher is better.

  distinct_claims_preserved_rate
      = (keep items the candidate KEPT) / (total keep items)
      FAITHFULNESS GATE. MUST equal 1.0. Any value < 1.0 means the candidate
      dropped a distinct claim/number/entity -> a faithfulness violation.

FAITHFULNESS LAW: dropping a 'keep' item is a hard failure regardless of how
many repeats were collapsed. The harness prints both metrics and flags loudly
if distinct_claims_preserved_rate < 1.0.

The candidate slot signature:
    candidate(items: list[dict]) -> set[int]
        items: the gold rows WITHOUT the 'label'/'reason'/'cluster_id' fields
               (i.e. {idx, section, sentence, citations}); idx is the gold index.
        returns: the SET OF idx values the candidate decided to KEEP.

A trivial keep-all baseline is wired in the slot so this file runs standalone:
    python dedup_benchmark.py

Dependency-free. Does NOT import production dedup or load any model.
"""
import json
import os
import re

GOLD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dedup_gold.json")


# --------------------------------------------------------------------------- #
# Gold loading + candidate input view
# --------------------------------------------------------------------------- #
def load_gold(path=GOLD):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def candidate_view(gold):
    """The information a candidate dedup function is allowed to see:
    the rendered sentence, its citations, section, and a stable index.
    It must NOT see the gold label."""
    return [
        {
            "idx": i,
            "section": g["section"],
            "sentence": g["sentence"],
            "citations": list(g["citations"]),
        }
        for i, g in enumerate(gold)
    ]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score(gold, kept_idx):
    """kept_idx: iterable of gold indices the candidate decided to KEEP."""
    kept = set(kept_idx)
    total = len(gold)
    keep_idx = {i for i, g in enumerate(gold) if g["label"] == "keep"}
    repeat_idx = {i for i, g in enumerate(gold) if g["label"] == "paraphrase_repeat"}

    # collapsed = a paraphrase_repeat that the candidate did NOT keep (dropped)
    repeats_dropped = {i for i in repeat_idx if i not in kept}
    # preserved = a keep that the candidate DID keep
    keeps_preserved = {i for i in keep_idx if i in kept}
    # the faithfulness violations: keeps the candidate dropped
    keeps_dropped = {i for i in keep_idx if i not in kept}

    collapsed_rate = (len(repeats_dropped) / len(repeat_idx)) if repeat_idx else 1.0
    preserved_rate = (len(keeps_preserved) / len(keep_idx)) if keep_idx else 1.0

    return {
        "total_items": total,
        "n_keep": len(keep_idx),
        "n_paraphrase_repeat": len(repeat_idx),
        "paraphrase_repeats_collapsed_rate": collapsed_rate,
        "distinct_claims_preserved_rate": preserved_rate,
        "repeats_dropped": len(repeats_dropped),
        "keeps_preserved": len(keeps_preserved),
        "faithfulness_violations": sorted(keeps_dropped),
    }


def report(name, gold, kept_idx):
    s = score(gold, kept_idx)
    print(f"\n=== candidate: {name} ===")
    print(f"  items={s['total_items']}  keep={s['n_keep']}  paraphrase_repeat={s['n_paraphrase_repeat']}")
    print(f"  paraphrase_repeats_collapsed_rate = {s['paraphrase_repeats_collapsed_rate']:.4f}"
          f"  ({s['repeats_dropped']}/{s['n_paraphrase_repeat']} dropped)")
    print(f"  distinct_claims_preserved_rate    = {s['distinct_claims_preserved_rate']:.4f}"
          f"  ({s['keeps_preserved']}/{s['n_keep']} preserved)")
    if s["distinct_claims_preserved_rate"] < 1.0:
        viol = s["faithfulness_violations"]
        print(f"  *** FAITHFULNESS VIOLATION *** candidate dropped {len(viol)} distinct claim(s):")
        for i in viol:
            print(f"        idx {i}: {gold[i]['sentence'][:90]!r}  cites={gold[i]['citations']}")
        print("  *** distinct_claims_preserved_rate MUST be 1.0; this candidate FAILS the faithfulness gate.")
    else:
        print("  OK: faithfulness gate passed (no distinct claim dropped).")
    return s


# --------------------------------------------------------------------------- #
# Candidate slots
# --------------------------------------------------------------------------- #
def candidate_keep_all(items):
    """Trivial baseline: keep everything. collapsed=0.0, preserved=1.0."""
    return {it["idx"] for it in items}


def candidate_oracle(items, gold):
    """Self-check candidate: replays the gold's own labels.
    MUST score collapsed=1.0 AND preserved=1.0."""
    return {it["idx"] for it in items if gold[it["idx"]]["label"] == "keep"}


def candidate_naive_text_dedup(items):
    """Illustrative WRONG candidate: drops any sentence whose normalized text is
    a near-duplicate of an earlier one IGNORING citations. This is the failure
    mode the gold is designed to catch -- but here it stays faithful because
    paraphrases differ lexically; included only to show the slot is pluggable.
    Drops only EXACT normalized-text repeats."""
    seen = {}
    kept = set()
    for it in items:
        key = re.sub(r"\s+", " ", it["sentence"].lower()).strip()
        if key in seen:
            continue  # drop exact repeat (ignores citations -> dangerous)
        seen[key] = it["idx"]
        kept.add(it["idx"])
    return kept


def _norm_text(s):
    return re.sub(r"\s+", " ", s.lower()).strip()


def candidate_exact_text_ordered_cites(items):
    """Illustrative candidate that dedups on (normalized text, ORDERED citation
    list). It is the TRAP the Stable-Diffusion cluster is designed to expose:
    those repeats have IDENTICAL text but the citation group is shuffled
    ([156,157,158] -> [157,156,158] -> [158,156,157]), so an ordered-list key
    treats them as distinct and FAILS to collapse them. Compare against
    candidate_exact_text_set_cites below, which keys on the citation SET and
    DOES collapse them. The gap between the two on this fixture proves the gold
    requires order-independent (set) citation comparison."""
    seen = set()
    kept = set()
    for it in items:
        key = (_norm_text(it["sentence"]), tuple(it["citations"]))
        if key in seen:
            continue
        seen.add(key)
        kept.add(it["idx"])
    return kept


def candidate_exact_text_set_cites(items):
    """Illustrative candidate that dedups on (normalized text, citation SET).
    Order-independent: it collapses the shuffled-citation Stable-Diffusion
    repeats that the ordered-list candidate above misses, while staying faithful
    (it never drops a distinct claim/number/entity, because exact-text repeats
    by construction add nothing new)."""
    seen = set()
    kept = set()
    for it in items:
        key = (_norm_text(it["sentence"]), frozenset(it["citations"]))
        if key in seen:
            continue
        seen.add(key)
        kept.add(it["idx"])
    return kept


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    gold = load_gold()
    items = candidate_view(gold)

    # Self-check: oracle MUST be 1.0 / 1.0
    oracle_score = report("oracle (gold labels replayed) [self-check]", gold,
                          candidate_oracle(items, gold))
    assert abs(oracle_score["paraphrase_repeats_collapsed_rate"] - 1.0) < 1e-9, \
        "ORACLE collapsed_rate != 1.0 -- harness math is wrong"
    assert abs(oracle_score["distinct_claims_preserved_rate"] - 1.0) < 1e-9, \
        "ORACLE preserved_rate != 1.0 -- harness math is wrong"

    # Baseline candidate in the pluggable slot
    report("keep_all (baseline)", gold, candidate_keep_all(items))

    # Illustrative naive candidate
    report("naive_exact_text_dedup (illustrative)", gold,
           candidate_naive_text_dedup(items))

    # Discriminator pair: ordered-list cites (TRAP) vs set cites (correct).
    ord_s = report("exact_text + ORDERED cites (trap: misses shuffled-cite repeats)",
                   gold, candidate_exact_text_ordered_cites(items))
    set_s = report("exact_text + SET cites (collapses shuffled-cite repeats)",
                   gold, candidate_exact_text_set_cites(items))
    if set_s["repeats_dropped"] <= ord_s["repeats_dropped"]:
        print("\n[WARN] set-cites candidate did not beat ordered-cites candidate; "
              "the order-independent discriminator is not exercised by this gold.")
    else:
        print(f"\n[discriminator OK] set-cites collapsed "
              f"{set_s['repeats_dropped']} repeats vs ordered-cites "
              f"{ord_s['repeats_dropped']} -> gold requires order-independent "
              f"citation-set comparison.")

    print("\n[self-check passed] oracle scored collapsed=1.0 and preserved=1.0.")
    print("Plug a real dedup function into a candidate_* slot and call report(...).")


if __name__ == "__main__":
    main()
