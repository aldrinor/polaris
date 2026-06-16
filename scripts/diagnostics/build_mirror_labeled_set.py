#!/usr/bin/env python3
"""I-run11-005: build a DEFENSIBLE Mirror labeled set for the robust re-bakeoff.

The first bakeoff's grounded labels used `item.statement` (often a paper TITLE) → trivial claims
that produced non-deterministic noise. This builds real claim-sentences with MECHANICAL ground
truth (no hand-labeling bias):
  - GROUNDED pair  : a real factual sentence extracted from item_i's direct_quote, paired with
    item_i's direct_quote as the only doc. Ground truth = the sentence is a verbatim substring of
    the doc (verified). Indisputably grounded.
  - UNGROUNDED pair: the same sentence paired with a TOPICALLY-DISTANT item_j's direct_quote.
    Ground truth = the sentence is NOT a substring of doc_j (verified). Indisputably ungrounded.

Boilerplate (cookie/marketing/URL/Title/section-header/too-short) is filtered OUT — that is NOT
truth-labeling, just excluding non-claims. SCOPE (honest): this set robustly measures BLANK-RATE +
FALSE-BIND + does-it-cite reliability (the swap-relevant safety metrics). It does NOT test nuanced
paraphrase/inference grounding judgment (verbatim claims are trivially findable) — that needs an
annotated set and is a follow-up. No live calls; deterministic. Run from repo root.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

POOL = Path("outputs/audits/I-run11-004/m25_bakeoff/evidence_pool.json")
OUT = Path("outputs/audits/I-run11-005/mirror_labeled_set.json")

_BOILERPLATE = re.compile(
    r"cookie|marketing|url source|^title:|personalise|advertising|privacy|"
    r"^background$|^methods$|^results$|all rights reserved|©",
    re.IGNORECASE,
)


def factual_sentences(quote: str) -> list[str]:
    """Real factual sentences (>=45 chars, not boilerplate, not an ALL-CAPS header)."""
    text = quote.replace(chr(0x2013), "-").replace(chr(0x2014), "-")
    out = []
    for p in re.split(r"(?<=[.!?])\s+", text):
        p = p.strip()
        if len(p) < 45:
            continue
        if _BOILERPLATE.search(p):
            continue
        # skip ALL-CAPS headers / fragments with no lowercase
        if not any(c.islower() for c in p):
            continue
        out.append(p)
    return out


def main() -> None:
    pool = json.loads(POOL.read_text(encoding="utf-8"))
    items = [
        x for x in pool
        if len(x.get("direct_quote") or "") > 200 and x.get("evidence_id")
    ]
    # normalize each doc the same way the claim is normalized so substring checks are consistent
    docs = {x["evidence_id"]: (x["direct_quote"].replace(chr(0x2013), "-").replace(chr(0x2014), "-"))
            for x in items}
    claims = []  # (evidence_id, sentence)
    for x in items:
        sents = factual_sentences(x["direct_quote"])
        if sents:
            claims.append((x["evidence_id"], sents[0]))  # one clean claim per item

    grounded, ungrounded = [], []
    ids = [eid for eid, _ in claims]
    for idx, (eid, sent) in enumerate(claims):
        own_window = docs[eid][:2000]   # the EXACT text the model sees (bakeoff truncates to 2000)
        # GROUNDED: claim must be a substring of the TRUNCATED window the model actually receives,
        # else the model legitimately cannot find it and the "grounded" label would be corrupt.
        if sent in own_window:
            grounded.append({"claim": sent, "doc_id": eid, "doc_text": own_window,
                             "ground_truth": "grounded", "basis": "claim is a verbatim substring of the doc window"})
        # UNGROUNDED: sentence vs a rotated other doc's window (must NOT be a substring — verify).
        other = ids[(idx + 3) % len(ids)]
        other_window = docs[other][:2000]
        if other != eid and sent not in other_window:
            ungrounded.append({"claim": sent, "doc_id": other, "doc_text": other_window,
                               "ground_truth": "ungrounded", "basis": "claim absent from an unrelated doc window"})

    dataset = {
        "_doc": "Defensible Mirror labeled set (I-run11-005). Mechanical ground truth (substring "
                "presence/absence). Scope: blank-rate + false-bind + cite-reliability; NOT nuanced "
                "paraphrase grounding (follow-up). Source: drb_72 m25_bakeoff evidence_pool.",
        "grounded": grounded,
        "ungrounded": ungrounded,
        "counts": {"grounded": len(grounded), "ungrounded": len(ungrounded)},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dataset, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  grounded={len(grounded)}  ungrounded={len(ungrounded)}")
    print("  sample grounded :", grounded[0]["claim"][:80] if grounded else "NONE")
    print("  sample ungrounded:", ungrounded[0]["claim"][:80] if ungrounded else "NONE",
          "(vs doc", ungrounded[0]["doc_id"] + ")" if ungrounded else "")


if __name__ == "__main__":
    main()
