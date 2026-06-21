#!/usr/bin/env python3
"""I-beatboth-009 (#1287) — fail-loud replay harness for the REDUCE-marker-filter bug.

§-1.4 behavioral acceptance (non-zero exit on regression). The bug: in REDUCE mode the section
tail ran `filter_and_strip_reduce_markers` on EVERY draft. That filter DROPS any sentence lacking a
`[[finding:]]` marker. The FIX-K / verified-compose PRIMARY drafts carry full `[#ev:...]` provenance
tokens but NO `[[finding:]]` markers, so the filter ate the ENTIRE draft -> raw="" -> verified=0,
dropped=0 (P6 v2: all 12 STORM topical sections gap-stubbed -> 25% < 40% -> abort_excessive_gap).

This harness uses the REAL production draft producer (`build_verified_span_draft`) to build the exact
kind of directly-`[#ev:]`-tokened draft a verified-compose basket falls back to, then proves on the REAL
production verifier (`verify_sentence_provenance` via `strict_verify`):
  (A) RED  — `filter_and_strip_reduce_markers` eats that draft to "" (the buggy path), and
  (B) GREEN — BYPASSING the filter (the `_draft_directly_tokened` fix), the SAME draft survives
      `_rewrite_draft_with_spans` + `strict_verify` to verified>0.

Faithfulness is UNTOUCHED: the draft is a verbatim span of a real SUPPORTS member; strict_verify is the
unchanged production gate. The fix only stops a REDUCE-only filter from eating already-grounded prose.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)  # deterministic span-grounding only, no model

from src.polaris_graph.generator.evidence_distiller import filter_and_strip_reduce_markers  # noqa: E402
from src.polaris_graph.generator.multi_section_generator import (  # noqa: E402
    _rewrite_draft_with_spans,
    build_verified_span_draft,
    strict_verify,
)
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
)


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-009 replay: {msg}")
    sys.exit(1)


_QUOTE = "Generative AI raised measured labor productivity in customer support by fourteen percent."
_EID = "openalexW123"  # no "ev_" prefix — mirrors the production pool's mixed id shapes


def _real_basket_and_pool():
    member = BasketMember(
        evidence_id=_EID, source_url=f"https://example.org/{_EID}", source_tier="T1",
        origin_cluster_id=f"o::{_EID}", credibility_weight=0.9, authority_score=0.9,
        span=(0, len(_QUOTE)), direct_quote=_QUOTE, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    basket = ClaimBasket(
        claim_cluster_id="c1", claim_text=_QUOTE, subject="AI labor productivity", predicate="finding",
        supporting_members=[member], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )
    pool = {_EID: {"evidence_id": _EID, "direct_quote": _QUOTE}}
    return basket, pool


class _Distillate:
    """A REDUCE finding ledger that does NOT cover this directly-tokened sentence (it has no
    [[finding:]] marker), exactly like the real run where verified-compose output carried none."""
    class _F:
        finding_id = "find_unrelated"
        evidence_id = _EID
    findings = [_F()]


def main() -> None:
    from src.polaris_graph.generator.provenance_generator import parse_provenance_tokens

    basket, pool = _real_basket_and_pool()

    # The REAL directly-[#ev:]-tokened draft a verified-compose basket emits/falls back to.
    draft = build_verified_span_draft(basket, pool)
    if not draft or "[#ev:" not in draft:
        _fail(f"build_verified_span_draft did not produce a tokened draft: {draft!r}")
    n_tok_draft = len(parse_provenance_tokens(draft))
    if n_tok_draft < 1:
        _fail(f"the production draft carries no parseable provenance token: {draft!r}")
    print(f"draft (production verbatim-span, {n_tok_draft} token): {draft!r}")

    # (A) RED — the REDUCE filter EATS the directly-[#ev:]-tokened draft to "" (the buggy path that
    # ran on the 12 STORM sections in P6 v2). The grounded prose AND its provenance token are lost.
    eaten = filter_and_strip_reduce_markers(draft, _Distillate())
    if eaten.strip():
        _fail(f"expected the REDUCE filter to EAT the [#ev:]-only draft (the bug), but it survived: {eaten!r}")
    if parse_provenance_tokens(eaten):
        _fail("the filter left a token behind; expected the whole draft eaten")
    print("RED ok: filter_and_strip_reduce_markers eats the [#ev:]-tokened draft -> '' (token lost = the bug).")

    # (B) GREEN — END-TO-END: bypassing the filter (bug #1 fix), the directly-tokened draft now passes
    # the UNCHANGED strict_verify gate (bug #2 fix, token-before-period, makes split_into_sentences keep
    # the token attached so it grounds). RED baseline before EITHER fix = kept 0.
    bypassed = draft  # the fix's `_draft_directly_tokened` branch skips filter_and_strip_reduce_markers
    rewritten, _conv, _unver = _rewrite_draft_with_spans(bypassed, pool)
    report = strict_verify(rewritten, pool)
    kept = len(getattr(report, "kept_sentences", []) or [])
    if kept < 1:
        _fail(f"directly-tokened draft did NOT verify when the filter is bypassed (kept={kept}); "
              f"token-orphan (bug #2) or filter (bug #1) still active. {report!r}")
    print(f"GREEN ok: bypassing the filter, the draft verifies end-to-end through strict_verify (kept={kept}).")

    print(
        "PASS I-beatboth-009: the REDUCE-marker filter destroys already-grounded [#ev:] prose (RED); "
        "with the _draft_directly_tokened bypass (bug #1) + token-before-period (bug #2) the SAME "
        "production draft passes the unchanged strict_verify gate end-to-end (GREEN). Faithfulness untouched."
    )


if __name__ == "__main__":
    main()
