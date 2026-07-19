#!/usr/bin/env python3
"""I-beatboth-011 §3.4 (#1289) — fail-loud harness for the per-unit compose junk screen.

§-1.4 behavioral acceptance (non-zero exit on regression). The defect: the verified-compose verbatim
path applied NO boilerplate/junk screen, so a chrome ``direct_quote`` (Scribd / Facebook / YouTube /
journal masthead) that self-entailed to SUPPORTS was dumped VERBATIM into the report as "verified" prose.

FIX (§3.4): a per-sentence-unit ALLOWLIST chrome screen (``_compose_boilerplate_screen``, reusing the shared
``weighted_enrichment._make_chrome_screen`` = is_boilerplate_or_nonassertional + the high-precision
multi-word chrome list) applied at the verbatim-emit consumers (build_verified_span_draft /
build_short_member_sentence). P1-4: ALLOWLIST-anchored only — a real SHORT sentence is KEPT (no length
drop). Faithfulness-safe: boilerplate is not a corroborating source, so removing it is not a §-1.3 DROP.

Asserts:
  (A) UNIT PRECISION — the screen drops high-precision chrome markers (incl. the idx68 social-chrome) but
      KEEPS a real SHORT content sentence (<40 chars). This is the P1-4 "not a min-length drop" proof.
  (B) BEHAVIORAL — build_verified_span_draft / build_short_member_sentence on a basket whose member
      direct_quote is "<chrome>. <real finding>." emit ONLY the real finding, with the chrome screened OUT.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 §3.4 junk screen: {msg}")
    sys.exit(1)


def main() -> None:
    from src.polaris_graph.generator.verified_compose import (
        _compose_boilerplate_screen,
        build_short_member_sentence,
        build_verified_span_draft,
    )

    # (A) UNIT PRECISION: chrome dropped, real short content KEPT (P1-4 — not a min-length drop).
    chrome_units = [
        "Like Comment Share",                       # Facebook
        "Download free for 30 days",                 # Scribd
        "World Summit AI 2.75K subscribers Subscribed 0 Share Save Download",  # YouTube
        "Tap to unmute",                             # YouTube player
        "Skip navigation Search",                    # nav
        "Cite this paper as",                        # masthead
        "URL Source: https://example.org/x",         # crawl header (boilerplate helper)
        "Accept all cookies",                        # cookie consent
    ]
    for u in chrome_units:
        if not _compose_boilerplate_screen(u):
            _fail(f"chrome unit NOT screened (should be dropped): {u!r}")
    real_short = [
        "AI cut 14% of jobs.",                       # 20 chars — real content, MUST be kept
        "GDP rose 2%.",                              # 12 chars — real content, MUST be kept
        "Wages fell.",                               # 11 chars — real content, MUST be kept
        "Generative AI raised measured labor productivity in customer support by fourteen percent.",
    ]
    for u in real_short:
        if _compose_boilerplate_screen(u):
            _fail(f"real content unit WRONGLY screened (P1-4 violation — looks like a min-length drop): {u!r}")
    print(f"(A) ok: {len(chrome_units)} chrome units dropped; {len(real_short)} real units (incl. <20-char) KEPT.")

    # (B) BEHAVIORAL: a basket whose member's verified span is "<chrome>. <finding>." emits ONLY the finding.
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    _FINDING = "Generative AI raised measured labor productivity in customer support by fourteen percent."
    _CHROME = "Like Comment Share"
    quote = f"{_CHROME}. {_FINDING}"
    eid = "ev_junk_demo"
    member = BasketMember(
        evidence_id=eid, source_url=f"https://facebook.com/{eid}", source_tier="T6",
        origin_cluster_id=f"o::{eid}", credibility_weight=0.3, authority_score=0.3,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    basket = ClaimBasket(
        claim_cluster_id="c1", claim_text=_FINDING, subject="AI labor productivity", predicate="finding",
        supporting_members=[member], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )
    pool = {eid: {"evidence_id": eid, "direct_quote": quote}}

    draft = build_verified_span_draft(basket, pool)
    if draft is None:
        _fail("build_verified_span_draft returned None — the real finding unit was wrongly dropped with the chrome")
    if _CHROME.lower() in draft.lower():
        _fail(f"chrome '{_CHROME}' leaked into build_verified_span_draft output: {draft!r}")
    if "labor productivity" not in draft.lower():
        _fail(f"the real finding is missing from build_verified_span_draft output: {draft!r}")
    if "[#ev:" not in draft:
        _fail(f"build_verified_span_draft output carries no provenance token: {draft!r}")
    print(f"(B1) ok: build_verified_span_draft emitted the finding, chrome screened: {draft[:90]!r}…")

    short = build_short_member_sentence(basket, pool)
    if _CHROME.lower() in short.lower():
        _fail(f"chrome '{_CHROME}' leaked into build_short_member_sentence output: {short!r}")
    if "labor productivity" not in short.lower():
        _fail(f"build_short_member_sentence dropped the real finding too: {short!r}")
    print(f"(B2) ok: build_short_member_sentence emitted the finding, chrome screened: {short[:90]!r}…")

    print(
        "PASS I-beatboth-011 §3.4: the per-unit allowlist chrome screen drops crawl/social/masthead chrome "
        "(incl. idx68 Scribd/FB/YouTube) while KEEPING real short content (A, the P1-4 no-length-drop proof); "
        "the verbatim-emit functions screen chrome out of the composed output and keep the real finding (B). "
        "Input-hygiene only — faithfulness engine untouched."
    )


if __name__ == "__main__":
    main()
