#!/usr/bin/env python3
"""I-beatboth-011 §3.1 ROUTE C (#1289) — fail-loud harness for the abstractive-writer INPUT chrome screen.

§-1.4 behavioral acceptance (non-zero exit on regression). The defect the §3.1 input-screen fixes: when
PG_ABSTRACTIVE_WRITER is ON the writer paraphrases each SUPPORTS member's verified span; a member whose
span is scraped CHROME (Scribd / Facebook / YouTube boilerplate that self-entailed to SUPPORTS) would be
PARAPHRASED into the report. An OUTPUT screen cannot catch it — a paraphrase mangles the multi-word chrome
markers ("Like Comment Share" -> "users were invited to like, comment and share") — so the screen MUST run
on the writer INPUT, before the LLM call (advisor 2026-06-21).

FIX (§3.1): in ``_pre_pass_one_basket`` (the per-basket writer driver), drop members whose verified span
text is chrome via the §3.4 ``_compose_junk_screen`` BEFORE ``_call_writer``. Faithfulness-safe (§-1.3):
boilerplate is not a corroborating source. A MIXED basket keeps its real members + citations; an
ALL-chrome basket leaves zero members -> writer skipped (None) -> the loop K-span-falls-back.

Asserts (fail-loud):
  (1) INPUT-SCREEN PRECISION — an ALL-chrome basket returns None and NEVER calls the writer LLM.
  (2) MIXED basket — the writer LLM is called with ONLY the real member (chrome filtered out), and the
      real member's citation is preserved into the writer input.
  (3) NO-CASCADE — abstractive_pre_pass over [all-chrome basket, real basket] drafts the real basket
      (its key present) while the all-chrome basket is simply absent: the all-chrome basket dropping out
      does NOT remove the real basket's content (the §-1.3 "screen chrome, never drop a real corroborator"
      breadth-preservation line; a real SECTION is not cascaded to empty by one all-chrome basket).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 §3.1 abstractive input-screen: {msg}")
    sys.exit(1)


def _make_basket(claim_id: str, quotes: list[str]):
    """A ClaimBasket whose SUPPORTS members carry the given verified-span quotes (one member each)."""
    from src.polaris_graph.synthesis.credibility_pass import (
        BasketMember,
        ClaimBasket,
        MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    members = []
    for i, q in enumerate(quotes):
        eid = f"{claim_id}_m{i}"
        members.append(BasketMember(
            evidence_id=eid, source_url=f"https://example.org/{eid}", source_tier="T6",
            origin_cluster_id=f"o::{eid}", credibility_weight=0.3, authority_score=0.3,
            span=(0, len(q)), direct_quote=q, span_verdict="SUPPORTS",
            member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
        ))
    basket = ClaimBasket(
        claim_cluster_id=claim_id, claim_text=quotes[0] if quotes else "", subject="s", predicate="finding",
        supporting_members=members, refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=len(members), verified_support_origin_count=len(members),
        basket_verdict="full",
    )
    pool = {m.evidence_id: {"evidence_id": m.evidence_id, "direct_quote": m.direct_quote} for m in members}
    return basket, pool


_CHROME = "World Summit AI 2.75K subscribers Subscribed 0 Share Save Download"
_REAL = "Generative AI raised measured customer-support productivity by fourteen percent [#ev:REAL:0-60]."


async def main_async() -> None:
    import src.polaris_graph.generator.abstractive_writer as aw

    # Capture what members (if any) reach the writer LLM, and stub the LLM + the verify wrapper so the
    # test is offline + deterministic (we are testing the INPUT screen, not the LLM or the verifier).
    captured: dict = {"members": None, "calls": 0}

    async def _capture_writer(members, evidence_pool, **kwargs):
        captured["members"] = list(members)
        captured["calls"] += 1
        # Echo a faithful one-sentence draft carrying the (first) real member's citation token.
        q = str(getattr(members[0], "direct_quote", "") or "")
        return q

    def _always_pass(draft, basket, evidence_pool, writer_verify_fn):
        return True, []

    orig_call, orig_pass = aw._call_writer, aw._draft_passes_wrapper
    aw._call_writer = _capture_writer
    aw._draft_passes_wrapper = _always_pass
    try:
        # (1) ALL-chrome basket -> writer skipped (None), LLM never called.
        captured["members"], captured["calls"] = None, 0
        chrome_basket, chrome_pool = _make_basket("c_chrome", [_CHROME, "Like Comment Share"])
        draft = await aw._pre_pass_one_basket(
            chrome_basket, chrome_pool, writer_verify_fn=lambda *a, **k: None,
            model="x", max_retries=0, max_tokens=10, reasoning_max_tokens=0,
            temperature=0.0, call_deadline_s=5.0,
        )
        if draft is not None:
            _fail(f"(1) an ALL-chrome basket should be writer-skipped (None), got draft={draft!r}")
        if captured["calls"] != 0:
            _fail("(1) the writer LLM was called for an ALL-chrome basket (input screen did not fire)")
        print("(1) ok: all-chrome basket -> writer skipped, LLM never called.")

        # (2) MIXED basket -> writer called with ONLY the real member; chrome filtered.
        captured["members"], captured["calls"] = None, 0
        mixed_basket, mixed_pool = _make_basket("c_mixed", [_CHROME, _REAL])
        draft = await aw._pre_pass_one_basket(
            mixed_basket, mixed_pool, writer_verify_fn=lambda *a, **k: None,
            model="x", max_retries=0, max_tokens=10, reasoning_max_tokens=0,
            temperature=0.0, call_deadline_s=5.0,
        )
        if captured["calls"] != 1:
            _fail(f"(2) expected exactly 1 writer call for the mixed basket, got {captured['calls']}")
        got = captured["members"] or []
        quotes = [str(getattr(m, "direct_quote", "") or "") for m in got]
        if any("World Summit AI" in q or "Like Comment Share" in q for q in quotes):
            _fail(f"(2) CHROME leaked into the writer INPUT: {quotes!r}")
        if not any("raised measured customer-support productivity" in q for q in quotes):
            _fail(f"(2) the REAL member was wrongly dropped from the writer INPUT: {quotes!r}")
        if "[#ev:REAL:0-60]" not in (draft or ""):
            _fail(f"(2) the real member's citation did not survive into the writer draft: {draft!r}")
        print("(2) ok: mixed basket -> writer got ONLY the real member; chrome screened; citation kept.")

        # (3) NO-CASCADE: pre-pass over [all-chrome, real] drafts the real basket; chrome basket absent.
        real_basket, real_pool = _make_basket("c_real", [_REAL])
        all_pool = {**chrome_pool, **real_pool}
        out = await aw.abstractive_pre_pass(
            [chrome_basket, real_basket], all_pool, writer_verify_fn=lambda *a, **k: None,
        )
        if "c_real" not in out:
            _fail(f"(3) the REAL basket lost its draft (cascade!) — pre_pass keys={list(out)}")
        if "c_chrome" in out:
            _fail(f"(3) the all-chrome basket wrongly produced a draft: {out.get('c_chrome')!r}")
        print("(3) ok: real basket drafted; all-chrome basket absent — no cascade to empty.")
    finally:
        aw._call_writer = orig_call
        aw._draft_passes_wrapper = orig_pass

    print(
        "PASS I-beatboth-011 §3.1: the abstractive-writer INPUT chrome screen drops all-chrome members "
        "before the LLM call (1), keeps the real member + citation in a mixed basket (2), and never "
        "cascades a real basket to empty when a sibling all-chrome basket drops out (3). Faithfulness "
        "engine untouched; input-hygiene only."
    )


if __name__ == "__main__":
    asyncio.run(main_async())
