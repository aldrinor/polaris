#!/usr/bin/env python3
"""I-beatboth-011 keystone-F1 (#1284) — behavioral replay harness for WITHIN-BASKET multi-cited
verified synthesis + the relational-quantifier guard.

§-1.4 fail-loud (non-zero exit) acceptance. The keystone-F1 effect must ACTUALLY FIRE in the composed
output, not merely pass a unit test. The shape proven here is the WITHIN-BASKET, per-member synthesis
(one CLAIM, N corroborating SUPPORTS members of the SAME basket co-located into ONE multi-cited
sentence) — distinct from the I-beatboth-002 cross-basket producer. This is the §-1.3 DNA reading of
"corroboration": repetition across the basket's members is STRENGTH, surfaced as multiple citations on
one sentence, never collapsed to the single strongest member.

Three assertions (the whole point — prove it WIRED, not just present):

  (i)   MULTI-CITATION FIRES — a basket with >=2 corroborating verified SUPPORTS members yields ONE
        multi-cited sentence carrying ALL of their [#ev:...] tokens, and that sentence strict_verify-
        PASSES per-clause against the UNCHANGED production verifier (every clause keeps its own span).
  (ii)  THE GUARD DROPS A FABRICATED RELATIONAL QUANTIFIER — a candidate multi-cited sentence whose
        writer prepended an aggregate predicate ("most studies show ...") that the basket consensus
        state does NOT license is REJECTED/repaired by relational_quantifier_guard, so the fabricated
        quantifier never reaches the rendered sentence. (under-relax is safe; an unverifiable
        quantifier is the lethal direction.)
  (iii) SINGLE-SOURCE PATH IS BYTE-IDENTICAL — a basket with exactly ONE verified member produces the
        unchanged single-cite sentence (the multi-cited producer adds breadth, it never rewrites the
        one-source path).

RED BASELINE: run against the UNMODIFIED tree (no ``_join_verified_clauses`` / no
``relational_quantifier_guard``) — the import guard FAILS LOUD with a non-zero exit. After keystone-F1
lands it PASSES. "Committed + green + Codex-approve" is NOT acceptance; this firing-in-output gate is.

REAL CORPUS: loads a real banked ``corpus_snapshot.json`` (the real evidence pool + real evidence_ids)
and binds each real id to a controlled verified span, so strict_verify is deterministic — no network,
no model spend, no relaxation. The LLM writer is FAKE/injected; ``strict_verify`` is the REAL
production single-sentence verifier (``verify_sentence_provenance``).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# Deterministic verification only — keep the entailment judge OFF so this harness needs no model.
# Set BEFORE importing the verifier (mirror the ancestor single-basket / I-beatboth-002 harnesses).
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    parse_provenance_tokens,
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
)

# The REAL banked corpus the harness loads (proves it runs on real data, not a synthetic-only fixture).
_CORPUS_SNAPSHOT = _REPO / "outputs" / "corpus_backups" / "extracted" / "drb_72_ai_labor" / "corpus_snapshot.json"

# Controlled verified spans bound to real evidence_ids — clean ASCII so strict_verify is deterministic
# and portable. These are THREE corroborating phrasings of the SAME claim (productivity gains from
# generative-AI adoption), each its OWN source's verbatim span — the within-basket corroboration set.
_SPAN_1 = "Generative AI adoption raised measured worker productivity in customer-support roles."
_SPAN_2 = "Studies report worker productivity gains following generative AI adoption in support roles."
_SPAN_3 = "Measured output per worker rose after generative AI tools were deployed in support teams."
# A fourth, single-source span for the single-cite byte-identity fixture.
_SPAN_SOLO = "Reported aggregate employment impact remained small in the near term."
# Two DECIMAL-bearing corroborating spans (different numbers) — strict_verify requires every decimal in a
# sentence to appear in its span, so a joined multi-token sentence must verify PER CLAUSE, not whole-vs-one.
_SPAN_DEC_1 = "Worker output rose 12 percent after generative AI tools were deployed in support teams."
_SPAN_DEC_2 = "Measured productivity increased 8 percent following AI adoption in customer service."
# A span whose SOURCE itself wrote the word "most" — a verbatim quotation the guard must NEVER mutate.
_SPAN_VERBATIM_Q = "Most of the surveyed firms reported productivity gains after AI adoption."


def _fail(case: str, detail: str) -> None:
    print(f"FAIL [{case}]: {detail}")
    sys.exit(1)


def _load_real_evidence_ids(n: int) -> list[str]:
    """Load the REAL corpus_snapshot and return the first ``n`` distinct real evidence_ids. FAIL LOUD
    if the snapshot is missing / malformed / too small — the harness must run on real banked data."""
    if not _CORPUS_SNAPSHOT.exists():
        _fail("corpus_missing", f"real corpus_snapshot.json not found: {_CORPUS_SNAPSHOT}")
    try:
        snap = json.loads(_CORPUS_SNAPSHOT.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - fail-loud
        _fail("corpus_parse", f"could not parse {_CORPUS_SNAPSHOT}: {exc}")
    rows = snap.get("evidence_for_gen") or []
    ids: list[str] = []
    seen: set[str] = set()
    for row in rows:
        eid = str((row or {}).get("evidence_id") or "").strip()
        if eid and eid not in seen:
            seen.add(eid)
            ids.append(eid)
        if len(ids) >= n:
            break
    if len(ids) < n:
        _fail("corpus_too_small", f"need {n} real evidence_ids, the snapshot yielded {len(ids)}")
    return ids


def _member(eid: str, quote: str, origin: str) -> BasketMember:
    """A SUPPORTS member with a DISTINCT origin cluster (so it is an independent corroborating origin)."""
    return BasketMember(
        evidence_id=eid, source_url=f"https://example.org/{eid}", source_tier="T1",
        origin_cluster_id=origin, credibility_weight=0.9, authority_score=0.9,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )


def _basket(ccid: str, subject: str, members: list, *, refuters: tuple = ()) -> ClaimBasket:
    verified_origins = len({m.origin_cluster_id for m in members
                            if str(m.span_verdict).upper() == "SUPPORTS"})
    return ClaimBasket(
        claim_cluster_id=ccid, claim_text=(members[0].direct_quote if members else ""),
        subject=subject, predicate="finding", supporting_members=list(members),
        refuter_cluster_ids=refuters, weight_mass=1.0,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=verified_origins,
        basket_verdict=("contested" if refuters else "full"),
    )


def _faithful_member_writer(basket, scoped_pool) -> str:
    """A FAKE per-MEMBER writer: drafts ONE faithful sentence per SUPPORTS member of the basket, each
    citing that member's OWN id+span. The only injected part; strict_verify is real. Returns the
    newline-joined per-member single-cite sentences (what the within-basket producer consumes)."""
    out = []
    for m in (getattr(basket, "supporting_members", None) or []):
        if str(getattr(m, "span_verdict", "")).upper() != "SUPPORTS":
            continue
        eid = str(getattr(m, "evidence_id", "") or "")
        span = str(getattr(m, "direct_quote", "") or "")
        if eid and span:
            out.append(f"{span} [#ev:{eid}:0-{len(span)}].")
    return "\n".join(out)


def main() -> int:
    # ── Import the keystone-F1 effects; FAIL LOUD on the RED baseline (symbols absent on the
    #    unmodified tree). This is the §-1.4 "effect must be PRESENT" gate. ──
    try:
        from src.polaris_graph.generator.verified_compose import (
            _join_verified_clauses,
            compose_basket_multicited_sentence,
        )
    except ImportError as exc:
        _fail("effect_not_present",
              "_join_verified_clauses / compose_basket_multicited_sentence are not present in "
              f"verified_compose.py — the keystone-F1 within-basket synthesis effect does not yet "
              f"exist (RED baseline). Expected to PASS once F1 lands. ({exc})")
        return 1  # unreachable (sys.exit in _fail)
    try:
        from src.polaris_graph.generator.relational_quantifier_guard import (
            guard_relational_quantifier,
        )
    except ImportError as exc:
        _fail("guard_not_present",
              "relational_quantifier_guard.guard_relational_quantifier is not present (RED baseline). "
              f"Expected to PASS once F1-2 lands. ({exc})")
        return 1  # unreachable

    # The default-OFF flag must exist and default to OFF (LAW VI / byte-identical-when-off).
    from src.polaris_graph.generator.verified_compose import _multicited_compose_enabled  # noqa: PLC0415
    os.environ.pop("PG_VERIFIED_COMPOSE_MULTICITED", None)
    if _multicited_compose_enabled():
        _fail("flag_default", "PG_VERIFIED_COMPOSE_MULTICITED must default OFF (byte-identical when off)")

    # ── Real corpus: real evidence_ids bound to controlled verified spans (deterministic pool). ──
    eid_1, eid_2, eid_3, eid_solo, eid_d1, eid_d2 = _load_real_evidence_ids(6)
    # eid_vq reuses eid_3's row swapped to the verbatim-quantifier span in a dedicated sub-pool below.
    span_by_eid = {
        eid_1: _SPAN_1, eid_2: _SPAN_2, eid_3: _SPAN_3, eid_solo: _SPAN_SOLO,
        eid_d1: _SPAN_DEC_1, eid_d2: _SPAN_DEC_2,
    }
    evidence_pool = {eid: {"evidence_id": eid, "direct_quote": span} for eid, span in span_by_eid.items()}

    # ── (i) MULTI-CITATION FIRES: a basket with THREE corroborating SUPPORTS members (distinct origins)
    #    -> ONE multi-cited sentence carrying ALL THREE [#ev] tokens, each clause strict_verify-PASS. ──
    multi_basket = _basket(
        "b_corroborated", "productivity",
        [_member(eid_1, _SPAN_1, "o1"), _member(eid_2, _SPAN_2, "o2"), _member(eid_3, _SPAN_3, "o3")],
    )
    multi = compose_basket_multicited_sentence(
        multi_basket, evidence_pool,
        writer_fn=_faithful_member_writer, verify_fn=verify_sentence_provenance,
    )
    if not multi or not multi.strip():
        _fail("i_multicited_absent",
              "keystone-F1 produced NO multi-cited synthesized sentence for a 3-member corroborated "
              "basket (silent no-op) — the effect did not fire.")
    toks = parse_provenance_tokens(multi)
    cited_ids = {str(getattr(t, "evidence_id", "") or "") for t in toks}
    if not ({eid_1, eid_2, eid_3} <= cited_ids):
        _fail("i_not_all_three_cited",
              f"the synthesized sentence must carry ALL THREE corroborating members' tokens; "
              f"cited={sorted(cited_ids)} sentence={multi!r}")
    # It must be ONE sentence (the splitter must NOT split the co-located clauses apart).
    from src.polaris_graph.generator.verified_compose import split_into_sentences  # noqa: PLC0415
    units = split_into_sentences(multi)
    if len(units) != 1:
        _fail("i_not_one_sentence",
              f"the multi-cited clauses must co-locate into ONE sentence (join-char regression); "
              f"split into {len(units)}: {units!r}")
    # EVERY citation strict_verify-PASSES against the global pool (each clause grounds its own span).
    gv = verify_sentence_provenance(multi, evidence_pool)
    if not bool(getattr(gv, "is_verified", False)):
        _fail("i_not_all_verified",
              f"every clause on the multi-cited sentence must strict_verify-PASS; rejected: {multi!r}")
    # No fabricated relational quantifier slipped through (the producer must never license one).
    lowered = multi.lower()
    banned_quantifiers = ("most studies", "consistently", "studies show", "broad consensus",
                          "the majority of", "overwhelmingly", "universally", "n of m")
    hit = [q for q in banned_quantifiers if q in lowered]
    if hit:
        _fail("i_aggregate_predicate",
              f"the multi-cited sentence must NOT carry an aggregate/relational quantifier; "
              f"found {hit} in {multi!r}")

    # ── (ii) THE GUARD DROPS A FABRICATED RELATIONAL QUANTIFIER. A writer that prepends an aggregate
    #    predicate the basket consensus does NOT license must have it stripped by the guard, and the
    #    repaired sentence must STILL strict_verify (faithful-by-construction — the per-clause spans
    #    are untouched). We test the guard directly on a fabricated candidate over THIS basket. ──
    fabricated = (
        f"Most studies show that {_SPAN_1[:1].lower()}{_SPAN_1[1:].rstrip('.')} [#ev:{eid_1}:0-{len(_SPAN_1)}]."
    )
    # Pre-condition: the fabricated candidate carries the banned quantifier (so the guard has something
    # to drop) — otherwise this fixture proves nothing.
    if "most studies show" not in fabricated.lower():
        _fail("ii_fixture_invalid", f"the fabricated candidate must carry the quantifier; got {fabricated!r}")
    repaired = guard_relational_quantifier(fabricated, multi_basket)
    if repaired is None or not str(repaired).strip():
        # A None / empty repair is an acceptable DROP only if the caller would then fall back; but for a
        # single fabricated sentence the guard must REPAIR to the faithful residue, not annihilate it.
        _fail("ii_guard_annihilated",
              f"the guard must REPAIR the fabricated candidate to its faithful residue, not drop it "
              f"entirely; got {repaired!r}")
    if any(q in str(repaired).lower() for q in ("most studies", "the majority of", "consistently",
                                                "studies show", "broad consensus")):
        _fail("ii_quantifier_survived",
              f"the guard FAILED to remove the unlicensed relational quantifier; residue={repaired!r}")
    # The repaired sentence must STILL strict_verify (the span + its token are intact).
    rgv = verify_sentence_provenance(str(repaired), evidence_pool)
    if not bool(getattr(rgv, "is_verified", False)):
        _fail("ii_repair_not_verified",
              f"the guard's repaired sentence must still strict_verify (faithful residue); "
              f"rejected: {repaired!r}")

    # ── (ii-b) END-TO-END through the producer: a writer that fabricates a quantifier per member must
    #    NOT yield a quantified rendered sentence — the producer's guard catches it. ──
    def _quantifier_writer(basket, scoped_pool) -> str:
        out = []
        for m in (getattr(basket, "supporting_members", None) or []):
            if str(getattr(m, "span_verdict", "")).upper() != "SUPPORTS":
                continue
            eid = str(getattr(m, "evidence_id", "") or "")
            span = str(getattr(m, "direct_quote", "") or "")
            if eid and span:
                out.append(f"Most studies show that {span[:1].lower()}{span[1:].rstrip('.')} [#ev:{eid}:0-{len(span)}].")
        return "\n".join(out)

    multi_q = compose_basket_multicited_sentence(
        multi_basket, evidence_pool,
        writer_fn=_quantifier_writer, verify_fn=verify_sentence_provenance,
    )
    if not multi_q or not multi_q.strip():
        _fail("iib_producer_empty",
              "the producer must still emit a faithful sentence after the guard strips the fabricated "
              "quantifier (always-release), got empty.")
    if any(q in multi_q.lower() for q in ("most studies", "the majority of", "consistently",
                                          "studies show", "broad consensus")):
        _fail("iib_quantifier_survived_producer",
              f"the producer's guard FAILED to strip the fabricated quantifier end-to-end; got {multi_q!r}")
    qgv = verify_sentence_provenance(multi_q, evidence_pool)
    if not bool(getattr(qgv, "is_verified", False)):
        _fail("iib_producer_not_verified",
              f"the de-quantified producer output must still strict_verify; rejected: {multi_q!r}")

    # ── (iii) SINGLE-SOURCE PATH IS BYTE-IDENTICAL: a basket with exactly ONE verified member yields the
    #    UNCHANGED single-cite sentence (the multi-cited producer adds breadth, never rewrites 1-source). ──
    solo_basket = _basket("b_solo", "employment impact", [_member(eid_solo, _SPAN_SOLO, "osolo")])
    # The single-source compose contract: the existing per-basket K-span draft (UNCHANGED).
    from src.polaris_graph.generator.verified_compose import build_verified_span_draft  # noqa: PLC0415
    expected_single = build_verified_span_draft(solo_basket, evidence_pool)
    if not expected_single or not expected_single.strip():
        _fail("iii_fixture_invalid", "the single-source K-span draft fixture must be non-empty.")
    solo = compose_basket_multicited_sentence(
        solo_basket, evidence_pool,
        writer_fn=_faithful_member_writer, verify_fn=verify_sentence_provenance,
    )
    if solo != expected_single:
        _fail("iii_single_not_byte_identical",
              f"a single-member basket must produce the UNCHANGED single-cite draft; "
              f"expected={expected_single!r} got={solo!r}")
    solo_ids = {str(getattr(t, "evidence_id", "") or "") for t in parse_provenance_tokens(solo)}
    if solo_ids != {eid_solo}:
        _fail("iii_single_wrong_cite",
              f"the single-source sentence must cite exactly its one member ({eid_solo}); "
              f"cited={sorted(solo_ids)}")

    # ── (iv) DECIMAL-BEARING joined sentence verifies PER CLAUSE (advisor gap #3). strict_verify requires
    #    every decimal in a sentence to appear in its span; a multi-token joined sentence with DIFFERENT
    #    decimals per clause must verify per-clause-scoped, NOT whole-sentence-vs-one-span (else the
    #    majority of number-bearing baskets silently degrade to a single K-span and multi-cite never fires). ──
    dec_basket = _basket(
        "b_decimals", "productivity gains",
        [_member(eid_d1, _SPAN_DEC_1, "od1"), _member(eid_d2, _SPAN_DEC_2, "od2")],
    )
    dec = compose_basket_multicited_sentence(
        dec_basket, evidence_pool,
        writer_fn=_faithful_member_writer, verify_fn=verify_sentence_provenance,
    )
    if not dec or not dec.strip():
        _fail("iv_decimal_absent", "the decimal-bearing 2-member basket produced no multi-cited sentence.")
    dec_ids = {str(getattr(t, "evidence_id", "") or "") for t in parse_provenance_tokens(dec)}
    if not ({eid_d1, eid_d2} <= dec_ids):
        _fail("iv_decimal_not_multicite",
              f"multi-citation must FIRE with DIFFERENT decimals per clause (no whole-sentence decimal "
              f"check degrading it to one K-span); cited={sorted(dec_ids)} sentence={dec!r}")
    if "12" not in dec or "8" not in dec:
        _fail("iv_decimal_lost", f"both clauses' decimals must survive in the joined sentence; got {dec!r}")
    dgv = verify_sentence_provenance(dec, evidence_pool)
    if not bool(getattr(dgv, "is_verified", False)):
        _fail("iv_decimal_not_verified",
              f"the decimal-bearing joined sentence must strict_verify PER CLAUSE; rejected: {dec!r}")

    # ── (v) A VERBATIM SOURCE QUANTIFIER IS PRESERVED (advisor gap #1 — faithfulness). When a member's
    #    writer clause FAILS verify, the producer falls back to that member's VERBATIM K-span. The source's
    #    OWN word "Most ..." is a quotation, NOT a fabricated aggregate — the guard must NEVER delete it.
    #    A writer that returns nothing forces the verbatim K-span path for both members. ──
    vq_pool = dict(evidence_pool)
    vq_pool[eid_3] = {"evidence_id": eid_3, "direct_quote": _SPAN_VERBATIM_Q}
    vq_basket = _basket(
        "b_verbatim_q", "firm productivity",
        [_member(eid_3, _SPAN_VERBATIM_Q, "ovq"), _member(eid_solo, _SPAN_SOLO, "ovq2")],
    )
    def _empty_writer(_b, _p) -> str:  # forces the verbatim K-span fallback for every member
        return ""
    vq = compose_basket_multicited_sentence(
        vq_basket, vq_pool, writer_fn=_empty_writer, verify_fn=verify_sentence_provenance,
    )
    if not vq or not vq.strip():
        _fail("v_verbatim_absent", "the verbatim-quantifier basket produced no multi-cited sentence.")
    # The source's own "Most of the surveyed firms ..." MUST appear verbatim (the guard left it alone).
    if "most of the surveyed firms" not in vq.lower():
        _fail("v_verbatim_quantifier_mutated",
              f"the guard MUST NOT delete a quantifier the SOURCE itself wrote (verbatim K-span "
              f"misquoted); got {vq!r}")
    vqgv = verify_sentence_provenance(vq, vq_pool)
    if not bool(getattr(vqgv, "is_verified", False)):
        _fail("v_verbatim_not_verified",
              f"the verbatim-K-span multi-cited sentence must strict_verify; rejected: {vq!r}")

    # ── (v-b) THE REAL DEFAULT WRITER preserves a verbatim source quantifier (advisor gap #1, deeper).
    #    The DEFAULT production writer is build_short_member_sentence — it returns the source's VERBATIM
    #    first sentence, which PASSES verify, so it flows through the WRITER path (not the K-span fallback).
    #    The guard must NOT strip "Most of the surveyed firms ..." from that VERBATIM writer output either —
    #    a quantifier PRESENT IN THE MEMBER'S SPAN is the source's word, never a fabrication. (Case (v) used
    #    an empty writer; this case exercises the real writer where the misquote actually bites.) ──
    from src.polaris_graph.generator.verified_compose import build_short_member_sentence  # noqa: PLC0415
    _short_writer = lambda _b, _p: build_short_member_sentence(_b, vq_pool)  # the actual default writer_fn
    vq2 = compose_basket_multicited_sentence(
        vq_basket, vq_pool, writer_fn=_short_writer, verify_fn=verify_sentence_provenance,
    )
    if not vq2 or not vq2.strip():
        _fail("vb_real_writer_absent", "the verbatim-quantifier basket produced nothing under the real writer.")
    if "most of the surveyed firms" not in vq2.lower():
        _fail("vb_real_writer_quantifier_mutated",
              f"the guard MUST NOT delete a quantifier the SOURCE wrote even when it arrives via the REAL "
              f"writer (build_short_member_sentence returns the verbatim span); misquoted: {vq2!r}")
    vq2gv = verify_sentence_provenance(vq2, vq_pool)
    if not bool(getattr(vq2gv, "is_verified", False)):
        _fail("vb_real_writer_not_verified",
              f"the real-writer verbatim-quantifier sentence must strict_verify; rejected: {vq2!r}")

    # ── (vi) ABSTRACTIVE-WRITER KEYING (advisor gap #2). The real abstractive writer is a precomputed
    #    dict keyed by the basket's claim_cluster_id and precomputes ONE WHOLE-basket draft per basket.
    #    The within-basket producer must STILL fire multi-cite under that writer — the per-member sub-basket
    #    lookup returns the parent's whole-basket draft (or misses), which fails the single-member scoped
    #    pool, so each member cleanly falls back to its OWN verbatim K-span. Mimic the real keying here. ──
    from src.polaris_graph.generator.abstractive_writer import (  # noqa: PLC0415
        make_abstractive_writer_fn,
    )
    # A precomputed dict keyed by claim_cluster_id, holding a whole-basket synthesized draft (as the real
    # pre-pass produces) — cites a DIFFERENT member's id than the sub-basket scopes to, so verify fails on
    # the single-member pool and the member falls back to its verbatim K-span (proving multi-cite still
    # fires from the deterministic spans regardless of the writer path).
    whole_basket_draft = f"AI adoption raised productivity across the firms [#ev:{eid_1}:0-{len(_SPAN_1)}]."
    precomputed = {"b_corroborated": whole_basket_draft}
    aw_writer = make_abstractive_writer_fn(precomputed)
    aw = compose_basket_multicited_sentence(
        multi_basket, evidence_pool, writer_fn=aw_writer, verify_fn=verify_sentence_provenance,
    )
    if not aw or not aw.strip():
        _fail("vi_abstractive_absent",
              "multi-citation did NOT fire under the real abstractive-writer keying (silent no-op).")
    aw_ids = {str(getattr(t, "evidence_id", "") or "") for t in parse_provenance_tokens(aw)}
    if not ({eid_1, eid_2, eid_3} <= aw_ids):
        _fail("vi_abstractive_degraded",
              f"under the claim_cluster_id-keyed writer the producer must STILL surface all THREE members "
              f"(via per-member verbatim K-span fallback), not degrade to one K-span; cited={sorted(aw_ids)} "
              f"sentence={aw!r}")
    awgv = verify_sentence_provenance(aw, evidence_pool)
    if not bool(getattr(awgv, "is_verified", False)):
        _fail("vi_abstractive_not_verified",
              f"the abstractive-writer-path multi-cited sentence must strict_verify; rejected: {aw!r}")

    print("PASS iarch-beatboth-011 keystone-F1 within-basket multi-cited synthesis harness "
          f"(real corpus: {_CORPUS_SNAPSHOT.name}, real ids: {eid_1}/{eid_2}/{eid_3}/{eid_solo}/"
          f"{eid_d1}/{eid_d2}): "
          "(i) multi-citation FIRES — a 3-member corroborated basket renders ONE sentence carrying ALL "
          "THREE [#ev] tokens, every clause strict_verify-PASSES; "
          "(ii) the relational-quantifier guard DROPS a fabricated 'most studies show ...' that the "
          "basket consensus does not license (direct + end-to-end through the producer), residue still "
          "strict_verifies; "
          "(iii) a single-source basket produces the UNCHANGED single-cite sentence (byte-identical); "
          "(iv) a DECIMAL-bearing 2-member basket fires multi-cite + verifies PER CLAUSE (12% and 8% both "
          "survive); "
          "(v) a quantifier the SOURCE itself wrote ('Most of the surveyed firms ...') is PRESERVED "
          "verbatim (the guard never mutates a verbatim K-span); "
          "(vi) under the REAL abstractive-writer keying (claim_cluster_id, whole-basket draft) multi-cite "
          "STILL fires from per-member verbatim K-spans (no silent degrade). "
          "strict_verify untouched; no network, no model spend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
