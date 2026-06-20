#!/usr/bin/env python3
"""I-beatboth-002 Fix 1 (F1-0) — behavioral replay harness for MULTI-CITED VERIFIED-COMPOSE.

§-1.4 fail-loud (non-zero exit) acceptance for F1-1 (Codex BRIEF APPROVE 2026-06-20). The effect must
ACTUALLY FIRE in the composed output on a REAL banked corpus, not merely pass a unit test:

  (a) at least ONE multi-cited synthesized sentence is produced that carries citations from >1 basket;
  (b) EVERY citation on that sentence strict_verify-PASSES (the UNCHANGED production verifier);
  (c) NO evidence_id outside the cited baskets leaks in (the P1-2 fail-closed contract is preserved).

Plus the discriminating PAIR that makes the per-basket-vs-union decision EVIDENCE-BACKED (brief §45-55):

  #1  PER-BASKET IS WIRED (would FAIL under a union pool): a multi-cited sentence whose one clause cites
      a FOREIGN basket's evidence_id MUST have that foreign clause REJECTED under the basket-scoped pool
      (it falls back to its OWN K-span) — so the foreign id never reaches the co-located sentence. Under
      a UNION pool the foreign cite would wrongly PASS — the regression this fixture discriminates.
  #2  PER-BASKET DOES NOT WRONGLY REJECT genuine multi-cited synthesis: every clause cites its OWN
      in-basket region -> the multi-cited sentence renders with both baskets' citations. (This is the
      evidence that VINDICATES per-basket as the increment-1 default; if THIS failed, that is the trigger
      to take the union question to Codex + operator — NOT a silent widening.)

Plus the CONTESTED-basket fixture (read NARROWLY per Codex P2 #2): a basket carrying a contradiction is
composed with PER-MEMBER attribution and NO consensus wording ("consistently" / "studies show"); this
increment does NOT wire claim_graph/both_sides (that is F1-3) — the assertion is only that the F1-1
producer never fabricates a consensus quantifier over a contested basket.

REAL CORPUS: the harness LOADS a real banked ``corpus_snapshot.json`` (the real evidence pool +
real evidence_ids) and constructs the discriminating baskets DETERMINISTICALLY from real evidence_ids,
binding each to a controlled verified span (so strict_verify is deterministic, no network, no model
spend). The LLM writer is FAKE/injected; ``strict_verify`` is the REAL production single-sentence
verifier (``verify_sentence_provenance``). "Rendered output" = the compose path's returned prose
(the ancestor-harness pattern), NOT a full report.md pipeline render.

RED BASELINE: run this against the UNMODIFIED ``verified_compose.py`` (no ``compose_multicited_sentence``
symbol) — the import guard FAILS LOUD ("effect not present") with a non-zero exit. After F1-1 lands it
PASSES. Committed + green + Codex-approve is NOT acceptance; this firing-in-output gate is.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# Deterministic verification only — keep the entailment judge OFF so this harness needs no model
# (mirror the ancestor single-basket harness). Set BEFORE importing the verifier.
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)
# F1-1 is default-OFF; the multi-cited producer is a pure function the harness calls directly, so no
# flag flip is needed to exercise it. The flag governs the (later) production caller wiring.

# strict_verify is the REAL gate; the production multi-cited producer is under test.
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

# Controlled verified spans (the span text each real evidence_id is bound to in the derived pool —
# clean ASCII so strict_verify is deterministic and portable; the IDS are real, drawn from the corpus).
_SPAN_A = "Generative AI adoption raised measured worker productivity in customer-support roles."
_SPAN_B = "Task automation potential is concentrated in routine cognitive occupations."
_SPAN_C = "Wage effects of automation varied widely across regional labor markets."
_SPAN_D = "Reported aggregate employment impact remained small in the near term."


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


def _member(eid: str, quote: str) -> BasketMember:
    return BasketMember(
        evidence_id=eid, source_url=f"https://example.org/{eid}", source_tier="T1",
        origin_cluster_id=f"o::{eid}", credibility_weight=0.9, authority_score=0.9,
        span=(0, len(quote)), direct_quote=quote, span_verdict="SUPPORTS",
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    )


def _basket(ccid: str, subject: str, quote: str, eid: str) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=ccid, claim_text=quote, subject=subject, predicate="finding",
        supporting_members=[_member(eid, quote)], refuter_cluster_ids=(), weight_mass=1.0,
        total_clustered_origin_count=1, verified_support_origin_count=1, basket_verdict="full",
    )


def _faithful_writer(span_by_eid: dict) -> "object":
    """A FAKE writer that drafts each basket's OWN faithful sentence (its span + its own id). The only
    injected part; strict_verify is real. The id<->span map is closed over so each basket's clause
    cites its own member region."""
    def _writer(basket, scoped_pool) -> str:
        members = list(getattr(basket, "supporting_members", None) or [])
        if not members:
            return ""
        eid = str(getattr(members[0], "evidence_id", "") or "")
        span = span_by_eid.get(eid, "")
        if not span:
            return ""
        return f"{span} [#ev:{eid}:0-{len(span)}]"
    return _writer


def main() -> int:
    # ── Import the F1-1 effect; FAIL LOUD on the RED baseline (symbol absent on unmodified code). ──
    try:
        from src.polaris_graph.generator.verified_compose import (
            compose_multicited_sentence,
            _multicited_compose_enabled,
        )
    except ImportError:
        _fail("effect_not_present",
              "compose_multicited_sentence is not present in verified_compose.py — the F1-1 "
              "multi-cited synthesis effect does not yet exist (RED baseline). This is the expected "
              "failure against the UNMODIFIED code; it must PASS once F1-1 lands.")
        return 1  # unreachable (sys.exit in _fail) — keeps type-checkers happy

    # The default-OFF flag must exist and default to OFF (LAW VI / byte-identical-when-off).
    os.environ.pop("PG_VERIFIED_COMPOSE_MULTICITED", None)
    if _multicited_compose_enabled():
        _fail("flag_default", "PG_VERIFIED_COMPOSE_MULTICITED must default OFF (byte-identical when off)")

    # ── Real corpus: real evidence_ids bound to controlled verified spans (deterministic pool). ──
    eid_a, eid_b, eid_c, eid_d = _load_real_evidence_ids(4)
    span_by_eid = {eid_a: _SPAN_A, eid_b: _SPAN_B, eid_c: _SPAN_C, eid_d: _SPAN_D}
    evidence_pool = {
        eid_a: {"evidence_id": eid_a, "direct_quote": _SPAN_A},
        eid_b: {"evidence_id": eid_b, "direct_quote": _SPAN_B},
        eid_c: {"evidence_id": eid_c, "direct_quote": _SPAN_C},
        eid_d: {"evidence_id": eid_d, "direct_quote": _SPAN_D},
    }
    faithful_writer = _faithful_writer(span_by_eid)

    # ── FIXTURE #2 (and core (a)/(b)): genuine multi-cited synthesis — each clause cites its OWN
    #    in-basket region -> ONE sentence carrying >1 basket's citation, every citation verifying. ──
    b_a = _basket("ba", "productivity", _SPAN_A, eid_a)
    b_b = _basket("bb", "automation potential", _SPAN_B, eid_b)
    multi = compose_multicited_sentence(
        [b_a, b_b], evidence_pool, writer_fn=faithful_writer, verify_fn=verify_sentence_provenance,
    )
    if not multi or not multi.strip():
        _fail("a_multicited_absent",
              "F1-1 produced NO multi-cited synthesized sentence for two genuine corroborating "
              "baskets (silent no-op) — the effect did not fire.")
    toks = parse_provenance_tokens(multi)
    cited_ids = {str(getattr(t, "evidence_id", "") or "") for t in toks}
    # (a) the sentence carries citations from MORE THAN ONE basket.
    if len(cited_ids) < 2 or not ({eid_a, eid_b} <= cited_ids):
        _fail("a_not_multibasket",
              f"the synthesized sentence must carry citations from >1 basket; cited={sorted(cited_ids)} "
              f"sentence={multi!r}")
    # (a) it must be ONE sentence (the splitter must NOT split the co-located clauses apart).
    from src.polaris_graph.generator.verified_compose import split_into_sentences  # noqa: PLC0415
    units = split_into_sentences(multi)
    if len(units) != 1:
        _fail("a_not_one_sentence",
              f"the multi-cited clauses must co-locate into ONE sentence (join-char regression); "
              f"split into {len(units)}: {units!r}")
    # (b) EVERY citation on the sentence strict_verify-PASSES against the global pool (each clause
    #     grounds its own member region).
    gv = verify_sentence_provenance(multi, evidence_pool)
    if not bool(getattr(gv, "is_verified", False)):
        _fail("b_not_all_verified",
              f"every citation on the multi-cited sentence must strict_verify-PASS; "
              f"verify rejected: {multi!r}")
    # (c) NO evidence_id outside the cited baskets leaks in.
    if not (cited_ids <= {eid_a, eid_b}):
        _fail("c_foreign_leak",
              f"a citation outside the two cited baskets leaked into the sentence; "
              f"cited={sorted(cited_ids)} allowed={{{eid_a}, {eid_b}}}")
    # (c) no consensus/aggregate quantifier was fabricated over the co-located clauses.
    lowered = multi.lower()
    banned_quantifiers = ("consistently", "studies show", "broad consensus", "most studies",
                          "overwhelmingly", "universally")
    hit = [q for q in banned_quantifiers if q in lowered]
    if hit:
        _fail("c_aggregate_predicate",
              f"F1-1 must NOT emit an aggregate/relational quantifier (F1-2 deferred); found {hit} "
              f"in {multi!r}")

    # ── FIXTURE #1 (per-basket IS wired; would FAIL under a union pool): one basket's writer DRIFTS to
    #    cite a FOREIGN basket's id. Under the basket-scoped pool the foreign clause is REJECTED and
    #    falls back to its OWN K-span -> the foreign id never reaches the co-located sentence. ──
    b_c = _basket("bc", "wage effects", _SPAN_C, eid_c)
    b_d = _basket("bd", "employment impact", _SPAN_D, eid_d)

    def _foreign_drift_writer(basket, scoped_pool) -> str:
        ccid = str(getattr(basket, "claim_cluster_id", "") or "")
        if ccid == "bc":
            return f"{_SPAN_C} [#ev:{eid_c}:0-{len(_SPAN_C)}]"  # faithful, own region
        if ccid == "bd":
            # DRIFT: cite basket bc's id+span (FOREIGN to bd; absent from bd's basket-scoped pool).
            return f"{_SPAN_C} [#ev:{eid_c}:0-{len(_SPAN_C)}]"
        return ""

    multi_drift = compose_multicited_sentence(
        [b_c, b_d], evidence_pool, writer_fn=_foreign_drift_writer, verify_fn=verify_sentence_provenance,
    )
    if not multi_drift or not multi_drift.strip():
        _fail("p1_2_no_output",
              "the foreign-drift case must still produce a sentence (bd falls back to its OWN K-span); "
              "got empty.")
    drift_ids = {str(getattr(t, "evidence_id", "") or "") for t in parse_provenance_tokens(multi_drift)}
    # bd must NOT have rendered bc's foreign id as bd's clause — bd falls back to its OWN id (eid_d).
    if eid_d not in drift_ids:
        _fail("p1_2_no_own_fallback",
              f"P1-2 VIOLATION: bd did not fall back to its OWN K-span ({eid_d}) after the foreign "
              f"cite was rejected; cited={sorted(drift_ids)} sentence={multi_drift!r}")
    # The sentence must still strict_verify (the rejected foreign clause became bd's own verified span).
    gv2 = verify_sentence_provenance(multi_drift, evidence_pool)
    if not bool(getattr(gv2, "is_verified", False)):
        _fail("p1_2_not_verified",
              f"after the foreign clause fell back to bd's own K-span, the sentence must strict_verify; "
              f"rejected: {multi_drift!r}")
    # Sanity that union-vs-per-basket is actually being DISCRIMINATED: under a union pool the foreign
    # bc-cite from bd would have been accepted AS bd's clause, so eid_c would appear TWICE (once for bc,
    # once for the wrongly-accepted bd clause). Per-basket: bc cites eid_c once, bd cites eid_d. So the
    # discriminating signal is that eid_d (bd's OWN) is present — proving the foreign cite was rejected
    # and replaced, not silently widened to union (already asserted above). Belt-and-braces: both ids.
    if not ({eid_c, eid_d} <= drift_ids):
        _fail("p1_2_discriminator",
              f"per-basket must yield bc->{eid_c} AND bd->{eid_d} (own K-span after foreign reject); "
              f"cited={sorted(drift_ids)} sentence={multi_drift!r}")

    # ── CONTESTED-basket fixture (NARROW per Codex P2 #2): a basket that carries a refuter reference
    #    is composed with PER-MEMBER attribution and NO consensus wording. F1-1 must not fabricate a
    #    consensus quantifier over it. (claim_graph/both_sides wiring is F1-3 — NOT pulled forward.) ──
    contested = ClaimBasket(
        claim_cluster_id="bcontested", claim_text=_SPAN_C, subject="wage effects", predicate="finding",
        supporting_members=[_member(eid_c, _SPAN_C)],
        refuter_cluster_ids=("some_refuting_cluster",),  # marks the basket contested
        weight_mass=1.0, total_clustered_origin_count=1, verified_support_origin_count=1,
        basket_verdict="contested",
    )
    contested_multi = compose_multicited_sentence(
        [contested, b_d], evidence_pool, writer_fn=faithful_writer, verify_fn=verify_sentence_provenance,
    )
    if not contested_multi or not contested_multi.strip():
        _fail("contested_no_output", "contested basket must still compose (per-member attribution), not held.")
    if any(q in contested_multi.lower() for q in banned_quantifiers):
        _fail("contested_consensus",
              f"F1-1 must NOT assert consensus over a CONTESTED basket; found a quantifier in "
              f"{contested_multi!r}")
    # The contested basket's own clause must be present and verify (LABEL-not-hold / always-release).
    cgv = verify_sentence_provenance(contested_multi, evidence_pool)
    if not bool(getattr(cgv, "is_verified", False)):
        _fail("contested_not_verified",
              f"the contested basket's per-member clause must strict_verify (always-release); "
              f"rejected: {contested_multi!r}")

    print("PASS iarch-beatboth-002 F1 multi-cited verified-compose harness "
          f"(real corpus: {_CORPUS_SNAPSHOT.name}, real ids: {eid_a}/{eid_b}/{eid_c}/{eid_d}): "
          "(a) ONE multi-cited synthesized sentence carries citations from >1 basket; "
          "(b) every citation strict_verify-PASSES against the global pool; "
          "(c) NO foreign ev_id leaks AND no aggregate quantifier fabricated; "
          "#1 per-basket IS wired (foreign-drift clause REJECTED under the basket-scoped pool -> bd's "
          "OWN K-span, would PASS under a union pool); "
          "#2 per-basket does NOT wrongly reject genuine multi-cited synthesis (vindicates per-basket "
          "as the increment-1 default); "
          "contested basket composed per-member with NO consensus wording (always-release, F1-3 not "
          "pulled forward). strict_verify untouched; no network, no model spend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
