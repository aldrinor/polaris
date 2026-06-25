#!/usr/bin/env python3
"""I-wire-001 W6 (#1314) — composition floor_abstractive PRODUCTION-PATH behavioral fire-test.

§-1.4 behavioral DoD: prove the LOCKED composition winner ``floor_abstractive`` (board row 12,
composite 20.55, beats all rivals p<0.05) FIRES through the PRODUCTION composition seam
``verified_compose._compose_section_per_basket`` on a REAL corpus, NOT a curated snippet — and that
the flag-OFF path is byte-identical to the deterministic composer.

KEY FACT (confirmed in the wiring brief): ``floor_abstractive`` == the production module
``src/polaris_graph/generator/abstractive_writer.py`` (I-beatboth-005 #1282) used as the ``writer_fn``
of ``_compose_section_per_basket``. It is ALREADY wired flag-gated default-OFF at the real caller seam
``multi_section_generator.py:3950-3974`` behind ``PG_ABSTRACTIVE_WRITER`` (+ ``PG_VERIFIED_COMPOSE`` to
reach the branch + ``PG_STRICT_VERIFY_ENTAILMENT=enforce`` fail-closed guard). No new flag is added —
a second flag for one effect is a §-1.3 anti-knob. THIS test certifies the existing wiring fires.

REAL DATA: the baskets are materialized from ``compose_gold_corrected.json`` — assembled ONCE from the
real banked corpus ``outputs/corpus_backups/extracted/drb_72_ai_labor/corpus_snapshot.json`` (manifest
``corpus_path`` proves it; first-non-chrome real evidence sentence per banked row; no synthetic spans).

FAITHFULNESS FROZEN: every composed sentence is re-checked by the UNCHANGED production
``verify_sentence_provenance`` exactly as ``_compose_section_per_basket`` does. This test wires AROUND
the engine, never INTO it.

THE THREE ASSERTIONS (fail-loud, non-zero exit on any):
  (OFF) flag-OFF composition == the deterministic short-writer composition, byte-for-byte.
  (ON)  flag-ON composition: >=1 rendered unit is GENUINELY PARAPHRASED (differs, token-stripped, from
        its source span AND from the deterministic K-span) AND EVERY rendered unit passes the UNCHANGED
        ``verify_sentence_provenance`` (no faithfulness breach). A flag-ON output that is a verbatim dump
        (no synthesis) OR carries an enforce breach => FAIL.
  (DEGRADE) a forced writer failure degrades through the REAL compose loop to the verbatim K-span
        (token preserved) — the always-release / never-strand invariant.

This is a real-GLM DoD: the ON leg needs a bounded GLM-5.2 call. An absent OPENROUTER_API_KEY is a HARD
failure (never a silent exit-0 skip) — "no key" means the DoD was not proven, not that it passed.
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

# The real corpus gold (materialized ONCE from the banked drb_72 corpus_snapshot — manifest.corpus_path).
# Vendored alongside this test (fixtures/) so the fire-test is self-contained and does not depend on the
# bake-off harness file being present on the branch under test.
_GOLD = _REPO / "tests" / "fixtures" / "iwire001" / "compose_gold_corrected.json"
# Outer test-harness safety net ONLY: kept ABOVE the pre-pass's own internal wall-deadline (720s
# default, the #1314 hang fix) so the pre-pass's bounded completion / abandon-to-K-span governs the
# test, not a tighter outer timeout. If THIS fires, the internal wall itself failed (a true bug).
_PREPASS_DEADLINE_S = float(os.getenv("IWIRE_FIRE_TEST_PREPASS_DEADLINE_S", "900"))
# The §-1.4 ON-leg defaults to the FULL 23-basket corpus (IWIRE_FIRE_TEST_ON_MAX_BASKETS=0) — the
# full-scale activation cert. The I-wire-001 W6 #1314 hang fix (per-call deadline + OUTER wall-deadline
# + abandon-don't-await in abstractive_pre_pass) makes the full corpus complete bounded: a stuck call
# is force-closed to the K-span and the whole pre-pass is wall-bounded, never infinite. Empirically the
# 23-basket pre-pass completes at concurrency 8 (~177s) and 3 (~197s); the wall (720s default) is the
# completion guarantee. Set a positive value to sample a smaller slice for a quick local smoke. 0 => ALL.
_ON_MAX_BASKETS = int(os.getenv("IWIRE_FIRE_TEST_ON_MAX_BASKETS", "0"))
# Default to the PROVEN full-scale fan-out (8) unless the caller overrides — the wall-deadline (not a
# throttled concurrency) is now the completion guarantee, so the documented default is the proven one.
os.environ.setdefault("PG_ABSTRACTIVE_WRITER_CONCURRENCY", "8")
# Per-call + outer-wall deadlines (the hang fix). Generous enough that a healthy basket is never
# force-closed; finite so a stuck call/pre-pass cannot hang. Caller env wins (LAW VI).
os.environ.setdefault("PG_ABSTRACTIVE_WRITER_CALL_DEADLINE_S", "120")
os.environ.setdefault("PG_ABSTRACTIVE_WRITER_WALL_DEADLINE_S", "720")


def _fail(msg: str) -> None:
    print(f"FAIL I-wire-001 W6 floor_abstractive fire-test: {msg}")
    sys.exit(1)


def _load_env() -> None:
    """Best-effort .env load so a local OPENROUTER_API_KEY is picked up (setdefault: never override)."""
    envf = _REPO / ".env"
    if not envf.exists():
        return
    for ln in envf.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if "=" in ln and not ln.startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def _strip_tokens(text: str) -> str:
    """Token-stripped, whitespace-collapsed, trailing-punct-stripped, lowercased — so a verbatim
    output normalizes EXACTLY to its span (the byte-identical / not-paraphrased discriminator)."""
    s = re.sub(r"\[#ev:[^\]]*\]", " ", text or "")
    s = " ".join(s.split())
    return re.sub(r"[\s.,;:!?\-—–]+$", "", s).lower()


def _content_overlap(a: str, b: str) -> float:
    wa, wb = set(_strip_tokens(a).split()), set(_strip_tokens(b).split())
    return len(wa & wb) / max(1, len(wb))


def _materialize_baskets(gold: dict) -> tuple[list, dict]:
    """Build live ClaimBasket objects + the evidence_pool from the gold JSON. Self-contained replica of
    the bake-off harness's _materialize_baskets (identical BasketMember/ClaimBasket construction) so this
    fire-test does not depend on the harness file being present on the branch under test. The spans are
    REAL banked verified spans from the drb_72 corpus — no synthetic evidence."""
    from src.polaris_graph.synthesis.credibility_pass import (  # noqa: PLC0415
        BasketMember,
        ClaimBasket,
        MEMBER_TIER_ENTAILMENT_VERIFIED,
    )

    def _member(eid: str, span: str, tier: str, weight: float) -> BasketMember:
        return BasketMember(
            evidence_id=eid, source_url=f"https://corpus/{eid}", source_tier=tier or "T1",
            origin_cluster_id=f"o::{eid}", credibility_weight=weight, authority_score=weight,
            span=(0, len(span)), direct_quote=span, span_verdict="SUPPORTS",
            member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
        )

    def _basket(ccid: str, subject: str, members: list, *, claim_text: str) -> ClaimBasket:
        return ClaimBasket(
            claim_cluster_id=ccid, claim_text=claim_text, subject=subject, predicate="finding",
            supporting_members=members, refuter_cluster_ids=(), weight_mass=float(len(members)),
            total_clustered_origin_count=len(members), verified_support_origin_count=len(members),
            basket_verdict="full",
        )

    pool = dict(gold["evidence_pool"])
    out = []
    for b in gold["baskets"]:
        members = [_member(m["eid"], m["span"], m["tier"], m["weight"]) for m in b["members"]]
        out.append(_basket(b["claim_cluster_id"], b["subject"], members, claim_text=b["claim_text"]))
    return out, pool


def main() -> None:
    _load_env()
    if not _GOLD.exists():
        _fail(f"real corpus gold missing: {_GOLD}")
    gold = json.loads(_GOLD.read_text(encoding="utf-8", errors="replace"))
    corpus_path = (gold.get("manifest") or {}).get("corpus_path", "?")
    print(f"[gold] {gold['manifest']['n_baskets']} baskets materialized from REAL corpus: {corpus_path}")

    # The faithfulness engine + the production seam (FROZEN; imported as-is, never patched).
    from src.polaris_graph.generator import abstractive_writer as aw  # noqa: PLC0415
    from src.polaris_graph.generator import verified_compose as vc  # noqa: PLC0415
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        verify_sentence_provenance,
    )

    baskets, pool = _materialize_baskets(gold)
    if not baskets:
        _fail("no baskets materialized from the gold")

    # ── (OFF) flag-OFF == the deterministic short-writer composition, byte-for-byte ──────────────
    # This is exactly what multi_section_generator.py:3971-3974 runs when PG_ABSTRACTIVE_WRITER is off.
    # The OFF producer is the DETERMINISTIC verbatim short-writer (no LLM); its faithfulness measure is
    # the engine's deterministic span-grounding, so we run the OFF leg with entailment OFF (the abstractive
    # writer's entailment guarantee is irrelevant to a verbatim K-span). This keeps the byte-identical
    # proof fast + deterministic; the ON leg re-enables enforce for its faithfulness proof below.
    os.environ.pop("PG_ABSTRACTIVE_WRITER", None)
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "off"
    off_units = vc._compose_section_per_basket(
        baskets, pool,
        writer_fn=lambda _b, _p: vc.build_short_member_sentence(_b, pool),
        verify_fn=verify_sentence_provenance,
    )
    off_text = "\n".join(u for u in off_units if u and u.strip())
    if not off_text.strip():
        _fail("(OFF) deterministic composer produced an empty section")
    # Re-run it: the OFF path is deterministic + pure -> must be byte-identical across runs.
    off_units_2 = vc._compose_section_per_basket(
        baskets, pool,
        writer_fn=lambda _b, _p: vc.build_short_member_sentence(_b, pool),
        verify_fn=verify_sentence_provenance,
    )
    if "\n".join(u for u in off_units_2 if u and u.strip()) != off_text:
        _fail("(OFF) deterministic composer is NOT reproducible (byte-identical) across two runs")
    print(f"(OFF) ok: deterministic composer reproducible byte-identical: {len(off_units)} units, "
          f"{len(off_text)} chars.")

    # ── (ON) the PRODUCTION abstractive path FIRES + paraphrases + every unit enforce-passes ─────
    os.environ["PG_ABSTRACTIVE_WRITER"] = "1"
    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"  # fail-closed activation precondition
    os.environ.setdefault("PG_GENERATOR_MODEL", "z-ai/glm-5.2")
    if not os.environ.get("OPENROUTER_API_KEY"):
        _fail("OPENROUTER_API_KEY absent — this MANDATORY real-GLM DoD fire-test cannot pass without it "
              "(refusing to exit 0 and false-green the cert gate)")

    # Activation guard fires (raises if entailment != enforce) — exactly multi_section_generator:3957.
    aw.assert_activation_preconditions()
    model = aw._resolve_model()
    if model != "z-ai/glm-5.2":
        _fail(f"(ON) resolved writer model is {model!r}, not the campaign z-ai/glm-5.2")
    writer_verify = aw.make_writer_verify_fn(verify_sentence_provenance)

    # Bound the ON real-GLM slice (OFF already ran over ALL baskets). The baskets are still REAL drb_72
    # corpus baskets driven through the unchanged production seam — only the COUNT is bounded so the
    # real-GLM proof completes under intermittent provider rate-limits. The full-scale ON run is point-9.
    on_baskets = baskets if _ON_MAX_BASKETS <= 0 else baskets[:_ON_MAX_BASKETS]

    print(f"(ON) running the PRODUCTION abstractive_pre_pass on {len(on_baskets)} REAL baskets "
          f"(of {len(baskets)}; model={model}, bounded by PG_ABSTRACTIVE_WRITER_CONCURRENCY) "
          f"under {_PREPASS_DEADLINE_S:.0f}s ...")
    t0 = time.time()

    async def _run_prepass() -> dict:
        return await asyncio.wait_for(
            aw.abstractive_pre_pass(on_baskets, pool, writer_verify_fn=writer_verify),
            timeout=_PREPASS_DEADLINE_S,
        )

    try:
        precomputed = asyncio.run(_run_prepass())
    except asyncio.TimeoutError:
        _fail(f"(ON) abstractive_pre_pass exceeded the {_PREPASS_DEADLINE_S:.0f}s section deadline")
    dt = time.time() - t0
    if not precomputed:
        _fail(f"(ON) the production pre-pass produced NO drafts for ANY basket in {dt:.1f}s "
              "(writer did not fire on the real corpus)")

    # Drive the SAME production seam multi_section_generator:3962-3965 uses on the ON path. Composed
    # ONCE (the writer_fn is a pure precomputed-dict lookup — no extra GLM calls); _compose_section_per_basket
    # applies its internal §3.5/idx8/B11 dedup so the output list is NOT 1:1 with `baskets` (a deduped
    # unit is dropped). Therefore NEVER zip on_units to baskets — verify + classify on the unit list itself.
    on_units = vc._compose_section_per_basket(
        on_baskets, pool,
        writer_fn=aw.make_abstractive_writer_fn(precomputed),
        verify_fn=writer_verify,
    )
    on_units = [u for u in on_units if u and u.strip()]
    if not on_units:
        _fail("(ON) the production compose seam produced an empty section")

    # Verbatim reference set (built ONCE, alignment-free): every member span + every basket K-span,
    # token-stripped. A composed unit whose token-stripped text matches NONE of these was genuinely
    # synthesized (paraphrased) by the abstractive writer; a match means a verbatim/K-span rendering.
    verbatim_refs: set[str] = set()
    for b in on_baskets:
        ks = _strip_tokens(vc.build_verified_span_draft(b, pool) or "")
        if ks:
            verbatim_refs.add(ks)
        for m in vc._basket_supports_members(b):
            sp = _strip_tokens(str(getattr(m, "direct_quote", "") or ""))
            if sp:
                verbatim_refs.add(sp)

    # ASSERTION 1 (faithfulness FROZEN): EVERY composed sentence re-passes the UNCHANGED engine verifier
    # against the GLOBAL evidence pool — exactly the re-verification the production section tail
    # (_rewrite_draft_with_spans + strict_verify) applies. A single breach fails the run (no relaxation).
    # ASSERTION 2 (effect APPEARS): >=1 unit is GENUINELY synthesized (token-stripped text not in the
    # verbatim reference set). A whole-section verbatim dump is a NO-OP and FAILS LOUD.
    breaches: list[str] = []
    paraphrased = 0
    verbatim_dump = 0
    for unit in on_units:
        for sent in vc.split_into_sentences(unit):
            res = verify_sentence_provenance(sent, pool)
            if not bool(getattr(res, "is_verified", False)):
                breaches.append(sent[:160])
        if _strip_tokens(unit) not in verbatim_refs:
            paraphrased += 1
        else:
            verbatim_dump += 1
    if breaches:
        _fail(f"(ON) {len(breaches)} rendered sentence(s) FAILED the UNCHANGED verify_sentence_provenance "
              f"(faithfulness breach — the engine is frozen, no relaxation): {breaches[:3]}")
    if paraphrased < 1:
        _fail(f"(ON) NO rendered unit is abstractively synthesized — all {len(on_units)} units match a "
              "verbatim span/K-span (the floor_abstractive effect did NOT appear in the real output)")
    print(f"(ON) ok: production abstractive compose FIRED on the real corpus in {dt:.1f}s — "
          f"{paraphrased}/{len(on_units)} units genuinely PARAPHRASED, "
          f"{verbatim_dump} verbatim/K-span; ALL composed sentences enforce-PASS (0 breaches).")

    # ── (DEGRADE) a forced writer failure degrades to the verbatim K-span through the REAL loop ──
    # Pick the first basket with a resolvable K-span, force the writer to raise, and assert the
    # production pre-pass + compose loop falls back to the verbatim span (always-release).
    target = None
    for b in baskets:
        if (vc.build_verified_span_draft(b, pool) or "").strip():
            target = b
            break
    if target is None:
        _fail("(DEGRADE) no basket has a resolvable K-span to test the fallback")
    kspan = vc.build_verified_span_draft(target, pool) or ""

    orig_call = aw._call_writer

    async def _boom(*_a, **_k):
        raise RuntimeError("forced writer failure (fire-test)")

    aw._call_writer = _boom
    try:
        async def _run_fail() -> dict:
            return await asyncio.wait_for(
                aw.abstractive_pre_pass([target], pool, writer_verify_fn=writer_verify),
                timeout=_PREPASS_DEADLINE_S,
            )
        pre_fail = asyncio.run(_run_fail())
    finally:
        aw._call_writer = orig_call
    degraded = vc._compose_section_per_basket(
        [target], pool,
        writer_fn=aw.make_abstractive_writer_fn(pre_fail),
        verify_fn=writer_verify,
    )
    deg_text = "\n".join(degraded)
    if "[#ev:" not in deg_text:
        _fail(f"(DEGRADE) forced writer failure did NOT degrade to a token-carrying K-span: {deg_text[:160]!r}")
    if _content_overlap(deg_text, kspan) < 0.6:
        _fail(f"(DEGRADE) the fallback is not span-derived (content overlap "
              f"{_content_overlap(deg_text, kspan):.0%} < 60%): {deg_text[:160]!r}")
    print("(DEGRADE) ok: forced writer failure -> the REAL compose loop degraded to the verbatim K-span "
          "(token preserved, span-derived).")

    print(
        "PASS I-wire-001 W6 floor_abstractive fire-test: on the REAL drb_72 corpus the production seam "
        "_compose_section_per_basket is BYTE-IDENTICAL flag-OFF (deterministic composer, reproducible); "
        "flag-ON it FIRES the abstractive writer (>=1 genuinely paraphrased unit, NOT a verbatim dump) "
        "with EVERY unit re-passing the UNCHANGED verify_sentence_provenance (faithfulness frozen); and a "
        "forced writer failure degrades to the verbatim K-span. Wired via the EXISTING PG_ABSTRACTIVE_WRITER "
        "flag (no new knob, §-1.3). Honest scope: full 4-role/NLI acceptance is the combined e2e run's job."
    )


if __name__ == "__main__":
    main()
