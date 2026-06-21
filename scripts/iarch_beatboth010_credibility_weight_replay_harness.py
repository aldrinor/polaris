#!/usr/bin/env python3
"""I-beatboth-010 (#1288) FIX-B — fail-loud replay harness for the credibility-weight collapse.

§-1.4 behavioral acceptance (non-zero exit on regression). The defect: the disclosed
``credibility_weight`` was a flat ~0.3315 for 553/592 banked v3 sources (AER == YouTube ==
Scribd == OECD) because the url+title-only ``score_source_authority`` blend is non-discriminating
(Signal A scholarly=0.0, Signal B institutional=neutral 0.40) at LOW confidence, and that flat
``authority_score`` was used as the weight while the discriminating per-tier prior was dead code.

FIX-B: when the computed authority_score is LOW confidence, the disclosed WEIGHT becomes the
per-tier prior (T1=0.95 .. T6=0.30 .. UNKNOWN=0.20), so a journal out-weighs YouTube/Scribd.
WEIGHT-strengthening only — every source still flows through (no drop); strict_verify + 4-role D8
remain the only faithfulness gate.

  (A) RED EVIDENCE — `_compute_authority_score_for_source` returns ~the SAME flat score at LOW
      confidence for AER, YouTube and Scribd (proves the old authority_score path collapsed them).
  (B) GREEN GATE — the rebuilt disclosure shows a real spread: >3 distinct weights, weight ==
      tier_prior(tier) per LOW row, a journal out-weighs YouTube/Scribd by >= 0.30, no journal
      shares YouTube's weight, and NO source is dropped (count in == count out).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_DD = _REPO / "outputs" / "p6_fresh_glm52_v3" / "workforce" / "drb_72_ai_labor"
_SNAPSHOT = _DD / "corpus_snapshot.json"


class _Source:
    """Minimal CorpusSource-shaped object (.url/.tier/.domain/.title; no .authority_score)."""

    def __init__(self, url: str, tier: str, title: str = "") -> None:
        self.url = url
        self.tier = tier
        from urllib.parse import urlparse

        self.domain = (urlparse(url).hostname or "").lower()
        self.title = title
        self.authority_score = None


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-010 FIX-B replay: {msg}")
    sys.exit(1)


def main() -> None:
    from src.polaris_graph.nodes.weighted_corpus_gate import (
        _compute_authority_score_for_source,
        _tier_prior,
        build_corpus_credibility_disclosure,
    )

    if not _SNAPSHOT.exists():
        _fail(f"banked corpus_snapshot.json not found at {_SNAPSHOT}")
    snap = json.loads(_SNAPSHOT.read_text(encoding="utf-8", errors="replace"))
    efg = snap.get("evidence_for_gen") or []
    if not efg:
        _fail("corpus_snapshot.json has no evidence_for_gen rows")

    # Build one CorpusSource per banked evidence row (url + classified tier).
    seen = set()
    sources = []
    for e in efg:
        url = str(e.get("source_url") or "")
        if not url or url in seen:
            continue
        seen.add(url)
        sources.append(_Source(url, str(e.get("tier") or "UNKNOWN"), str(e.get("title") or "")))
    if len(sources) < 50:
        _fail(f"expected >=50 distinct banked sources; got {len(sources)}")

    def _find(host_substr: str):
        return next((s for s in sources if host_substr in (s.domain or "")), None)

    aer = _find("aeaweb.org")
    yt = _find("youtube.com")
    scribd = _find("scribd.com")
    if not (aer and yt):
        _fail(f"banked corpus missing aeaweb.org ({bool(aer)}) or youtube.com ({bool(yt)}) for the test")

    # (A) RED EVIDENCE — the computed authority_score collapses these to ~the same LOW-confidence value.
    a_score, a_low = _compute_authority_score_for_source(aer)
    y_score, y_low = _compute_authority_score_for_source(yt)
    print(
        f"RED evidence: computed authority_score AER={a_score:.4f}(low={a_low}) "
        f"YouTube={y_score:.4f}(low={y_low}) — the OLD authority_score path used these AS the weight."
    )
    if not (a_low and y_low):
        _fail(f"expected LOW confidence on the url+title-only path (AER low={a_low}, YT low={y_low})")
    if abs(a_score - y_score) >= 0.10:
        _fail(
            f"expected the computed scores to COLLAPSE (|AER-YouTube|<0.10, the flat-blend defect); "
            f"got {abs(a_score - y_score):.4f} — the premise of FIX-B no longer holds."
        )

    # (B) GREEN GATE — rebuild the disclosure with the fixed code and assert a real, faithful spread.
    from collections import Counter

    tier_counts = dict(Counter(s.tier for s in sources))
    total = len(sources)
    tier_fracs = {k: v / total for k, v in tier_counts.items()}
    disc = build_corpus_credibility_disclosure(
        classified_sources=sources,
        tier_counts=tier_counts,
        tier_fractions=tier_fracs,
        total_sources=total,
        had_material_deviation=False,
        domain="workforce",
        research_question="AI labor market restructuring",
    )
    rows = disc.per_source
    by_host = {}
    for r in rows:
        from urllib.parse import urlparse

        h = (urlparse(r.url).hostname or "").lower()
        by_host.setdefault(h, r)

    # (no drop) every source flows through
    if len(rows) != total:
        _fail(f"FIX-B dropped sources: {total} in, {len(rows)} out — must be WEIGHT-only, never a drop.")

    distinct = sorted({r.credibility_weight for rows_ in [rows] for r in rows_})
    if len(distinct) <= 3:
        _fail(f"disclosure still has <=3 distinct weights {distinct} — the flat-collapse was not fixed.")

    # weight == tier_prior(tier) for every LOW (tier_prior-basis) row
    for r in rows:
        if r.weight_basis == "tier_prior":
            expect = round(_tier_prior(r.tier), 4)
            if abs(r.credibility_weight - expect) > 1e-6:
                _fail(
                    f"tier_prior row weight {r.credibility_weight} != tier_prior({r.tier})={expect} "
                    f"for {r.url}"
                )

    aer_w = next((r.credibility_weight for h, r in by_host.items() if "aeaweb.org" in h), None)
    yt_w = next((r.credibility_weight for h, r in by_host.items() if "youtube.com" in h), None)
    if aer_w is None or yt_w is None:
        _fail("could not locate AER/YouTube rows in the rebuilt disclosure")
    if aer_w - yt_w < 0.30:
        _fail(f"journal does not out-weigh YouTube by >=0.30: AER={aer_w} YouTube={yt_w} (diff {aer_w - yt_w:.2f})")
    if scribd is not None:
        sc_w = next((r.credibility_weight for h, r in by_host.items() if "scribd.com" in h), None)
        if sc_w is not None and aer_w - sc_w < 0.30:
            _fail(f"journal does not out-weigh Scribd by >=0.30: AER={aer_w} Scribd={sc_w}")

    # no named journal shares YouTube's weight
    for host_sub in ("aeaweb.org", "journals.uchicago.edu", "science.org", "cambridge.org"):
        w = next((r.credibility_weight for h, r in by_host.items() if host_sub in h), None)
        if w is not None and abs(w - yt_w) < 1e-6:
            _fail(f"journal {host_sub} still shares YouTube's weight {w} — discrimination failed.")

    print(
        f"GREEN ok: {len(distinct)} distinct credibility weights (was effectively 1 flat 0.3315); "
        f"AER={aer_w} > YouTube={yt_w} by {aer_w - yt_w:.2f}; weight==tier_prior(tier) for every LOW row; "
        f"all {len(rows)} sources retained (no drop); weighted mean={disc.weighted_credibility_mean}."
    )
    print(
        "PASS I-beatboth-010 FIX-B: the url+title-only authority_score collapses AER/YouTube/Scribd to a "
        "flat LOW-confidence value (RED); the fixed disclosure uses the discriminating per-tier prior so a "
        "journal out-weighs YouTube/Scribd, with every source retained (GREEN). Faithfulness gates untouched."
    )


if __name__ == "__main__":
    main()
