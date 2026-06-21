#!/usr/bin/env python3
"""I-beatboth-011 Tier3 idx 62/36/33 (#1289) — render/log honesty harness (fail-loud).

All three are render/log honesty in scripts/run_honest_sweep_r3.py, faithfulness-neutral (no
strict_verify/NLI/4-role/span-grounding touched, no source/member dropped):

  idx 62 (BEHAVIORAL): the per-claim corroboration block (_basket_corroboration_block) cleaned its
      header with _normalize_claim_summary + a chrome screen, so a scraped cookie/consent/biblio line
      is NOT titled as a "verified claim"; it falls back to subject-predicate / cluster id. A real
      claim header is rendered unchanged, and the source/count are untouched.
  idx 33 (SOURCE): the stale hardcoded "DeepSeek V3.2-Exp" generator log string is GONE; the live
      PG_GENERATOR_MODEL is logged instead.
  idx 36 (SOURCE): the false "match exactly" comment is gone and the disclosure text carries the
      "need not sum to the claim count" bidirectional clause.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_RHS = _REPO / "scripts" / "run_honest_sweep_r3.py"


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 Tier3 render-honesty: {msg}")
    sys.exit(1)


def main() -> None:
    import scripts.run_honest_sweep_r3 as rhs

    # ── idx 62 (behavioral): chrome header is cleaned + falls back; real claim header is kept ────────
    bib = [{
        "baskets": [
            {
                "claim_cluster_id": "c_chrome",
                "claim_text": "This website uses cookies to improve your experience. Accept all cookies",
                "subject": "GDP", "predicate": "rose two percent",
                "verified_support_origin_count": 2, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://a.org",
                     "source_tier": "T2", "credibility_weight": 0.8},
                ],
            },
            {
                "claim_cluster_id": "c_real",
                "claim_text": "Generative AI raised measured labor productivity by fourteen percent",
                "subject": "AI", "predicate": "raised productivity",
                "verified_support_origin_count": 1, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://b.org",
                     "source_tier": "T1", "credibility_weight": 0.9},
                ],
            },
        ],
    }]
    out = rhs._basket_corroboration_block(bib)
    if "uses cookies" in out.lower():
        _fail(f"(62) scraped cookie-consent chrome surfaced as a verified-claim header:\n{out}")
    if "GDP rose two percent" not in out:
        _fail(f"(62) the chrome header did not fall back to subject-predicate ('GDP rose two percent'):\n{out}")
    if "Generative AI raised measured labor productivity by fourteen percent" not in out:
        _fail(f"(62) the REAL claim header was lost:\n{out}")
    # source + count untouched (faithfulness-neutral): both sources + both counts still rendered.
    if "https://a.org" not in out or "https://b.org" not in out:
        _fail(f"(62) a supporting source was dropped from the render (must be header-text-only):\n{out}")
    if "2 verified independent source(s)" not in out or "1 verified independent source(s)" not in out:
        _fail(f"(62) a verified-source count changed — the fix must touch HEADER TEXT ONLY:\n{out}")
    print("(62) ok: chrome header cleaned + fell back to subject-predicate; real claim kept; sources/counts untouched.")

    # ── idx 33 (source): stale model string gone, live env slug logged ───────────────────────────────
    src = _RHS.read_text(encoding="utf-8", errors="replace")
    if "DeepSeek V3.2-Exp" in src:
        _fail("(33) the stale 'DeepSeek V3.2-Exp' generator log string still present")
    if 'f"[generation]  multi-section {os.environ.get(\'PG_GENERATOR_MODEL\')' not in src:
        _fail("(33) the [generation] log does not use the live PG_GENERATOR_MODEL slug")
    if '"generator": os.environ.get("PG_GENERATOR_MODEL"' not in src:
        _fail("(33) the postgen checkpoint model_pin was not populated with the generator slug")
    print("(33) ok: stale model string gone; live PG_GENERATOR_MODEL logged + recorded in model_pin.")

    # ── idx 36 (source): false 'match exactly' gone, bidirectional clause present ─────────────────────
    if "match exactly" in src:
        _fail("(36) the false 'so the disclosed count and reasons match exactly' comment still present")
    if "need not sum to the claim count" not in src:
        _fail("(36) the bidirectional 'need not sum to the claim count' disclosure clause is missing")
    if "may exceed" in src:
        _fail("(36) used the banned 'may exceed' phrasing instead of the bidirectional 'need not sum to'")
    print("(36) ok: false 'match exactly' removed; bidirectional 'need not sum to the claim count' clause present.")

    print(
        "PASS I-beatboth-011 Tier3: the corroboration-block header no longer titles scraped chrome as a "
        "verified claim (62, behavioral; sources/counts untouched); the generator log + model_pin name the "
        "live model not a stale string (33); the drop-disclosure states the per-check vs per-claim "
        "relationship honestly (36). Faithfulness engine untouched."
    )


if __name__ == "__main__":
    main()
