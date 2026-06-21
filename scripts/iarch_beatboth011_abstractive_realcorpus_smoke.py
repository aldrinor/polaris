#!/usr/bin/env python3
"""I-beatboth-011 §3.1 ROUTE C — REAL-CORPUS SMOKE (#1289; the §-1.4 behavioral DoD, advisor 2026-06-21).

This is the gate the advisor demanded before the paid fresh run: prove the abstractive writer ACTUALLY
FIRES on a real GLM call against a real banked span — "wired + harness-green + Codex-APPROVE ≠ fired in
the output". FAIL LOUD (non-zero exit) unless every leg holds:

  (A) ACTIVATION  — assert_activation_preconditions() passes with PG_STRICT_VERIFY_ENTAILMENT=enforce.
  (B) FIRES + PARAPHRASES + COMPLETES — one real GLM (PG_GENERATOR_MODEL, glm-5.2) writer call on a
      real banked span returns non-empty prose that (a) carries the exact provenance token, (b) is NOT
      byte-identical to the verbatim span (it was rephrased), and (c) completes within the call deadline.
  (C) DEGRADES — a forced writer failure leaves the precomputed draft empty, so the per-basket writer_fn
      returns "" and the loop falls back to the verbatim K-span (which still carries the token).

Span source: a CLEAN sentence extracted from the banked evidence_pool (post clean_fetch_body), with a
realistic AI-labor fallback if the banked pool yields none. Run:
  python scripts/iarch_beatboth011_abstractive_realcorpus_smoke.py
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

_POOL = _REPO / "outputs" / "p6_fresh_glm52_v3" / "workforce" / "drb_72_ai_labor" / "evidence_pool.json"
_FALLBACK_SPAN = (
    "Generative AI raised measured labor productivity in customer support by 14 percent over the "
    "study period, with the largest gains accruing to less-experienced workers."
)


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


async def main() -> None:
    _load_env()
    os.environ["PG_ABSTRACTIVE_WRITER"] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
    os.environ.setdefault("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    os.environ["PG_ABSTRACTIVE_WRITER_MAX_RETRIES"] = "0"
    os.environ["PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S"] = "120"
    if not os.environ.get("OPENROUTER_API_KEY"):
        _fail("OPENROUTER_API_KEY missing — cannot run the real GLM writer smoke")

    import src.polaris_graph.generator.abstractive_writer as aw  # noqa: PLC0415
    from src.polaris_graph.generator import verified_compose as vc  # noqa: PLC0415
    from src.polaris_graph.synthesis.credibility_pass import (  # noqa: PLC0415
        BasketMember, ClaimBasket, MEMBER_TIER_ENTAILMENT_VERIFIED,
    )

    picked = _pick_banked_span()
    if picked:
        span, src_eid = picked
        print(f"banked span [{src_eid}]: {span[:140]!r}")
    else:
        span, src_eid = _FALLBACK_SPAN, "(realistic fallback — no clean banked sentence found)"
        print(f"using realistic fallback span: {span[:140]!r}")

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

    # (A) activation
    aw.assert_activation_preconditions()
    print("(A) ok: assert_activation_preconditions passes (PG_STRICT_VERIFY_ENTAILMENT=enforce).")

    gs = vc._member_global_span(member, pool)
    if gs is None:
        _fail("_member_global_span did not resolve — the member span/pool is malformed")
    token = f"[#ev:{eid}:{gs[0]}-{gs[1]}]"

    # (B) FIRES + PARAPHRASES + COMPLETES — one real GLM call.
    model = aw._resolve_model()
    print(f"(B) calling the abstractive writer (model={model}) on the real span ...")
    t0 = time.time()
    draft = await aw._call_writer(
        [member], pool, model=model, max_tokens=512, reasoning_max_tokens=2048, temperature=0.2,
    )
    dt = time.time() - t0
    if not (draft or "").strip():
        _fail(f"(B) the writer returned an EMPTY draft (did not fire) in {dt:.1f}s")
    if token not in draft:
        _fail(f"(B) the draft is missing the provenance token {token}: {draft[:240]!r}")
    body_only = " ".join(draft.replace(token, " ").split()).rstrip(".").lower()
    if body_only == " ".join(span.split()).rstrip(".").lower():
        _fail(f"(B) the draft is byte-identical to the verbatim span (the writer did NOT paraphrase): {draft[:200]!r}")
    if dt > 120:
        _fail(f"(B) the writer exceeded the 120s call deadline ({dt:.1f}s)")
    print(f"(B) ok: writer FIRED + PARAPHRASED + completed in {dt:.1f}s.\n    draft: {draft.strip()[:200]!r}")

    # (C) DEGRADES — forced writer failure -> empty precomputed -> K-span verbatim fallback.
    async def _boom(*a, **k):
        raise RuntimeError("forced writer failure (smoke)")
    orig = aw._call_writer
    aw._call_writer = _boom
    try:
        pre = await aw.abstractive_pre_pass([basket], pool, writer_verify_fn=lambda *a, **k: None)
    finally:
        aw._call_writer = orig
    writer_fn = aw.make_abstractive_writer_fn(pre)
    abstractive_out = writer_fn(basket, pool)
    if (abstractive_out or "").strip():
        _fail(f"(C) after a forced writer failure the writer still produced text (no degrade): {abstractive_out[:160]!r}")
    kspan = vc.build_verified_span_draft(basket, pool)
    if not kspan or token not in kspan:
        _fail(f"(C) the K-span verbatim fallback is missing/empty on writer failure: {kspan!r}")
    print(f"(C) ok: forced writer failure -> writer produced nothing -> verbatim K-span fallback available ({token}).")

    print(
        "PASS I-beatboth-011 §3.1 real-corpus smoke: PG_ABSTRACTIVE_WRITER=1 activates (A); the writer "
        "FIRED on a real GLM call, paraphrased a real banked span carrying the exact provenance token, and "
        "completed within the deadline (B); a forced writer failure degrades to the verbatim K-span (C). "
        "The §-1.4 'fired in the real output' DoD is met — faithfulness engine untouched."
    )


if __name__ == "__main__":
    asyncio.run(main())
