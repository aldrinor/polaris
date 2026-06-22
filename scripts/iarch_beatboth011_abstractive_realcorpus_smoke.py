#!/usr/bin/env python3
"""I-beatboth-011 §3.1 ROUTE C — REAL-CORPUS SMOKE (#1289; the §-1.4 behavioral DoD, advisor 2026-06-21).

The gate before the paid run: prove the abstractive writer ACTUALLY FIRES FAST through the PRODUCTION
path ("wired + green ≠ fired in the output"). STRENGTHENED after a Codex re-gate (4 P1):
  - it exercises the PRODUCTION path (abstractive_pre_pass -> make_abstractive_writer_fn ->
    _compose_section_per_basket), NOT the raw _call_writer helper;
  - the positive call is wrapped in asyncio.wait_for so the deadline is ENFORCED (fail loud), not
    checked after the fact;
  - a REAL banked span is REQUIRED (no synthetic fallback that false-greens the DoD);
  - the degrade leg runs the REAL compose fallback loop;
  - the resolved model is asserted to be z-ai/glm-5.2.

It also pins the (a) writer tuning (reasoning_max_tokens=2048) and asserts the production pre-pass
COMPLETES FAST (well under the deadline) — the proof that the (a) fix cures the 120s-timeout that made
Route C fall back to K-span on the real resume run.

HONEST SCOPE: the base verify here is a deterministic real-SHAPED stub (token + numeric-preserving =
pass). This smoke proves the WRITER FIRES FAST + the production pre-pass/compose WIRING emits the
abstractive draft (and degrades to K-span on failure). The full strict_verify + NLI-entailment
ACCEPTANCE is exercised by the dedicated strict_verify tests + the end-to-end resume run, NOT this unit
smoke. FAIL LOUD (non-zero exit) on any leg — INCLUDING a missing OPENROUTER_API_KEY: this is a
mandatory real-GLM DoD smoke, so an absent key is a hard failure, never a silent exit-0 skip.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_POOL = _REPO / "outputs" / "p6_fresh_glm52_v3" / "workforce" / "drb_72_ai_labor" / "evidence_pool.json"
_DEADLINE_S = 180.0
_FAST_S = 90.0  # the (a) proof: the production pre-pass must complete WELL under the deadline


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 §3.1 real-corpus smoke: {msg}")
    sys.exit(1)


def _load_env() -> None:
    if not (_REPO / ".env").exists():
        return
    for ln in (_REPO / ".env").read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _pick_banked_span() -> tuple[str, str] | None:
    """A CLEAN labor-content sentence (with a number) from the post-clean_fetch_body banked pool."""
    from src.tools.access_bypass import clean_fetch_body  # noqa: PLC0415
    if not _POOL.exists():
        return None
    pool = json.loads(_POOL.read_text(encoding="utf-8", errors="replace"))
    rows = pool if isinstance(pool, list) else (pool.get("evidence") or list(pool.values()))
    chrome = re.compile(
        r"security (check|verification)|unusual activity|cookies|favicon|!\[Image|Markdown Content|"
        r"URL Source|ISSN|subscribers|captcha|cloudflare|verify you are|enable javascript", re.I)
    labor = re.compile(r"\b(wage|employ|labor|labour|automat|productivit|worker|occupation|generative|AI)\b", re.I)
    sent = re.compile(r"[A-Z][^.!?]{70,240}[.!?]")
    for r in (rows if isinstance(rows, list) else []):
        if not isinstance(r, dict):
            continue
        body = clean_fetch_body(r.get("direct_quote") or r.get("statement") or "").cleaned_text
        for m in sent.finditer(body):
            s = " ".join(m.group(0).split())
            if re.search(r"\d", s) and labor.search(s) and not chrome.search(s) and "[" not in s and "](" not in s:
                return s, str(r.get("evidence_id") or "?")
    return None


@dataclasses.dataclass
class _SmokeVerify:
    """Real-SHAPED verify result so make_writer_verify_fn (which dataclasses.replace()s it) works."""
    is_verified: bool
    sentence: str
    failure_reasons: list
    judge_error: bool = False


def _base_verify(sentence, scoped_pool, *args, **kwargs):
    """Deterministic real-shaped base verify (token-carrying -> pass). NOT a re-test of strict_verify /
    NLI (those have dedicated tests + the resume run); this smoke tests the writer + compose WIRING."""
    ok = "[#ev:" in str(sentence or "")
    return _SmokeVerify(is_verified=ok, sentence=str(sentence or ""),
                        failure_reasons=[] if ok else ["smoke_no_token"])


def _norm(s: str) -> str:
    """Normalize for comparison: STRIP [#ev:...] provenance tokens, collapse whitespace, strip trailing
    punctuation, lowercase. Codex re-gate P1: the old `replace(token,' ').rstrip('.')` left a verbatim
    `span [#ev:...].` as `'span .'` (!= 'span'), false-greening a verbatim/K-span output as 'paraphrased'.
    Removing the token entirely + stripping trailing punct makes a verbatim output normalize EXACTLY to
    the span, so the byte-identical (NOT-paraphrased) check is correct."""
    s = re.sub(r"\[#ev:[^\]]*\]", " ", s or "")
    s = " ".join(s.split())
    return re.sub(r"[\s.,;:!?\-—–]+$", "", s).lower()


async def main() -> None:
    _load_env()
    os.environ["PG_ABSTRACTIVE_WRITER"] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ.setdefault("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    # Pin the (a) tuning so the smoke proves it keeps the production pre-pass FAST.
    os.environ["PG_ABSTRACTIVE_WRITER_REASONING_MAX_TOKENS"] = "2048"
    os.environ["PG_ABSTRACTIVE_WRITER_CONCURRENCY"] = "4"
    os.environ["PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S"] = "180"
    os.environ["PG_ABSTRACTIVE_WRITER_MAX_RETRIES"] = "0"
    if not os.environ.get("OPENROUTER_API_KEY"):
        # Codex re-gate P1: a MANDATORY real-GLM DoD smoke must NOT exit 0 without the key — that
        # false-greens it. Fail loud. Do not run this smoke where the key is absent; it is the cert
        # gate, and "no key" means the DoD was not proven, not that it passed.
        _fail("OPENROUTER_API_KEY absent — this MANDATORY real-GLM DoD smoke cannot pass without it "
              "(refusing to exit 0 and false-green the cert gate)")

    import src.polaris_graph.generator.abstractive_writer as aw  # noqa: PLC0415
    from src.polaris_graph.generator import verified_compose as vc  # noqa: PLC0415
    from src.polaris_graph.synthesis.credibility_pass import (  # noqa: PLC0415
        BasketMember, ClaimBasket, MEMBER_TIER_ENTAILMENT_VERIFIED,
    )

    # (P1-1) a REAL banked span is REQUIRED — no synthetic fallback that false-greens the DoD.
    picked = _pick_banked_span()
    if not picked:
        _fail("no CLEAN banked span found in the drb_72 evidence_pool — the DoD requires a real banked "
              "span; refusing to false-green on a synthetic fallback")
    span, src_eid = picked
    print(f"banked span [{src_eid}]: {span[:140]!r}")

    eid = "ev_smoke"
    pool = {eid: {"evidence_id": eid, "direct_quote": span}}
    member = BasketMember(
        evidence_id=eid, source_url="https://example.org/x", source_tier="T2",
        origin_cluster_id="o::1", credibility_weight=0.8, authority_score=0.8,
        span=(0, len(span)), direct_quote=span, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )
    basket = ClaimBasket(
        claim_cluster_id="c1", claim_text=span, subject="AI", predicate="productivity",
        supporting_members=[member], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )

    # (A) activation + model assertion (P2: reject a silent PG_ABSTRACTIVE_WRITER_MODEL override).
    aw.assert_activation_preconditions()
    model = aw._resolve_model()
    if model != "z-ai/glm-5.2":
        _fail(f"(A) resolved writer model is {model!r}, not the expected campaign model z-ai/glm-5.2")
    print(f"(A) ok: activation passes (entailment=enforce); model={model}.")

    gs = vc._member_global_span(member, pool)
    if gs is None:
        _fail("_member_global_span did not resolve — member span/pool malformed")
    token = f"[#ev:{eid}:{gs[0]}-{gs[1]}]"
    writer_verify = aw.make_writer_verify_fn(_base_verify)

    # (B) PRODUCTION path + ENFORCED deadline (P1-2 + P1-3): run the real abstractive_pre_pass wrapped in
    # wait_for, then the real make_abstractive_writer_fn + _compose_section_per_basket; assert it COMPLETES
    # FAST (the (a) fix) and the production compose emits the ABSTRACTIVE paraphrase carrying the token.
    print(f"(B) running PRODUCTION abstractive_pre_pass (reasoning=2048, model={model}) under {_DEADLINE_S:.0f}s ...")
    t0 = time.time()
    try:
        pre = await asyncio.wait_for(
            aw.abstractive_pre_pass([basket], pool, writer_verify_fn=writer_verify),
            timeout=_DEADLINE_S,
        )
    except asyncio.TimeoutError:
        _fail(f"(B) abstractive_pre_pass exceeded the {_DEADLINE_S:.0f}s deadline — the (a) reasoning tuning "
              f"did NOT fix the Route-C timeout")
    dt = time.time() - t0
    draft = (pre or {}).get("c1") or ""
    if not draft.strip():
        _fail(f"(B) the production pre-pass produced NO draft for the basket (writer did not fire) in {dt:.1f}s")
    if token not in draft:
        _fail(f"(B) the production draft is missing the provenance token {token}: {draft[:200]!r}")
    if _norm(draft.replace(token, " ")) == _norm(span):
        _fail(f"(B) the draft is byte-identical to the span (writer did NOT paraphrase): {draft[:200]!r}")
    if dt > _FAST_S:
        _fail(f"(B) production pre-pass took {dt:.1f}s (> {_FAST_S:.0f}s) — too slow; the (a) tuning is not "
              f"keeping the writer fast under the production path")
    composed = vc._compose_section_per_basket([basket], pool,
                                              writer_fn=aw.make_abstractive_writer_fn(pre),
                                              verify_fn=writer_verify)
    joined = "\n".join(composed)
    if token not in joined or _norm(joined.replace(token, " ")) == _norm(span):
        _fail(f"(B) the PRODUCTION compose did not emit the abstractive draft (got K-span/verbatim or empty): {joined[:200]!r}")
    print(f"(B) ok: PRODUCTION pre-pass FIRED + paraphrased + completed in {dt:.1f}s (< {_FAST_S:.0f}s); compose emitted the abstractive draft.")

    # (C) DEGRADE via the REAL compose loop (P1-4): force the writer to fail, run the production pre-pass
    # + compose, assert the section degrades to the verbatim K-span (token preserved).
    async def _boom(*a, **k):
        raise RuntimeError("forced writer failure (smoke)")
    orig = aw._call_writer
    aw._call_writer = _boom
    try:
        pre_fail = await asyncio.wait_for(
            aw.abstractive_pre_pass([basket], pool, writer_verify_fn=writer_verify), timeout=_DEADLINE_S)
        composed_fail = vc._compose_section_per_basket([basket], pool,
                                                       writer_fn=aw.make_abstractive_writer_fn(pre_fail),
                                                       verify_fn=writer_verify)
    finally:
        aw._call_writer = orig
    joined_fail = "\n".join(composed_fail)
    if token not in joined_fail:
        _fail(f"(C) forced writer failure did NOT degrade to the verbatim K-span through the real compose loop: {joined_fail[:200]!r}")
    # The K-span is the WINDOWED verbatim direct_quote (head/window of the span), so it is span-DERIVED
    # but not necessarily byte-identical to the matched sentence (windowing / source hyphenation like
    # "tech-nology"). Assert high content-word overlap (it is the verbatim span), not exact equality.
    _kw = set(_norm(joined_fail.replace(token, " ")).split())
    _sw = set(_norm(span).split())
    _overlap = len(_kw & _sw) / max(1, len(_sw))
    if _overlap < 0.6:
        _fail(f"(C) the K-span fallback is not span-derived (content-word overlap {_overlap:.0%} < 60%): {joined_fail[:200]!r}")
    print("(C) ok: forced writer failure -> the REAL compose loop degraded to the verbatim K-span (token preserved).")

    print(
        "PASS I-beatboth-011 §3.1 real-corpus smoke (strengthened): activation+model (A); the PRODUCTION "
        "abstractive_pre_pass FIRED on a real GLM call, paraphrased a real banked span, and COMPLETED FAST "
        f"(< {_FAST_S:.0f}s) under an ENFORCED deadline — proving the (a) reasoning=2048 tuning cures the "
        "Route-C 120s timeout (B); the real compose loop degrades to the verbatim K-span on writer failure "
        "(C). Honest scope: full strict_verify+NLI acceptance is the resume run's job, not this unit smoke."
    )


if __name__ == "__main__":
    asyncio.run(main())
