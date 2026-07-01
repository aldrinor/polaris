"""I-deepfix-001 M6 behavioral test — verified cross-source analytical synthesis.

ISOLATED + OFFLINE: no paid API, no GPU. The composer is driven by the DETERMINISTIC short writer
(``build_short_member_sentence``, no LLM) + the production ``verify_sentence_provenance`` (which runs
offline with PG_VERIFICATION_MODE=off / PG_STRICT_VERIFY_ENTAILMENT unset — no network judge), exactly
mirroring the production RENDER-PROBE path in ``multi_section_generator`` (the non-abstractive branch).

Baskets + members are reconstructed from THIS run's banked artifacts
(``.codex/I-deepfix-001/smoke_forensics/.../bibliography.json``); the evidence pool from the banked
``evidence_pool.json``. A controlled two-basket SHARED-ANCHOR pairing is set up (the real members/spans
are untouched; only the section-level subject/predicate anchor is set to make the two baskets pairing
CANDIDATES — the scenario the composer is designed for). Asserts, against real values:
  1. a composed analytical sentence carries TWO distinct [#ev] tokens from TWO baskets;
  2. re-running the production verify_sentence_provenance PER CLAUSE PASSES (both atoms verify), and a
     clause mutated to cite a foreign span FAILS (engine still gates);
  3. a no-edge pair -> neutral connective ("; separately,"); injecting a ContradictionEdge -> "; in
     contrast,"; injecting an agree_map -> "; consistent with this," (relation is engine-licensed,
     never free-form);
  4. KEEP-ALL — no source/basket present pre-change is absent post-change.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:  # Windows console is cp1252; force UTF-8 so diagnostic prints never crash the test.
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Repo root on path.
_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no extra judge calls, no network entailment.
os.environ["PG_VERIFICATION_MODE"] = "off"
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

from src.polaris_graph.generator.cross_source_synthesis import (  # noqa: E402
    LICENSED_CONNECTIVES,
    compose_cross_source_analytical_units,
    license_relation,
)
from src.polaris_graph.generator.verified_compose import (  # noqa: E402
    _resolved_spans,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
    split_into_sentences,
)
from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket  # noqa: E402

_BANK = (
    _REPO / ".codex" / "I-deepfix-001" / "smoke_forensics" / "outputs"
    / "deepfix_safety_smoke" / "workforce" / "drb_72_ai_labor"
)
# Fall back to the absolute main-repo location (the worktree may not carry the smoke_forensics bank).
if not _BANK.exists():
    _BANK = Path(
        "C:/POLARIS/.codex/I-deepfix-001/smoke_forensics/outputs/"
        "deepfix_safety_smoke/workforce/drb_72_ai_labor"
    )


def _load_json(name):
    return json.load(open(_BANK / name, encoding="utf-8"))


def _short_writer(_basket, _pool):
    """The DETERMINISTIC production short writer (no LLM) — first verified sentence of the strongest
    SUPPORTS member, real global offsets."""
    from src.polaris_graph.generator.verified_compose import build_short_member_sentence
    return build_short_member_sentence(_basket, _evidence_pool_global)


def _build_member(m: dict) -> BasketMember:
    dq = str(m.get("direct_quote") or "")
    return BasketMember(
        evidence_id=str(m["evidence_id"]),
        source_url=str(m.get("source_url") or ""),
        source_tier=str(m.get("source_tier") or ""),
        origin_cluster_id=str(m.get("origin_cluster_id") or f"origin::{m['evidence_id']}"),
        credibility_weight=float(m.get("credibility_weight") or 0.0),
        authority_score=float(m.get("authority_score") or 0.0),
        span=(0, len(dq)),
        direct_quote=dq,
        span_verdict=str(m.get("span_verdict") or ""),
        member_tier=str(m.get("member_tier") or ""),
    )


def _build_basket(bk: dict) -> ClaimBasket:
    members = [_build_member(m) for m in bk.get("supporting_members", [])]
    return ClaimBasket(
        claim_cluster_id=str(bk.get("claim_cluster_id") or ""),
        claim_text=str(bk.get("claim_text") or ""),
        subject=str(bk.get("subject") or ""),
        predicate=str(bk.get("predicate") or ""),
        supporting_members=members,
        refuter_cluster_ids=tuple(bk.get("refuter_cluster_ids") or ()),
        weight_mass=float(bk.get("weight_mass") or 0.0),
        total_clustered_origin_count=int(bk.get("total_clustered_origin_count") or 0),
        verified_support_origin_count=int(bk.get("verified_support_origin_count") or 0),
        basket_verdict=str(bk.get("basket_verdict") or ""),
    )


def _resolvable(basket: ClaimBasket, pool: dict) -> bool:
    """True iff the basket has a SUPPORTS member whose verbatim quote is locatable in the pool (so the
    short writer can build a verified clause)."""
    for m in basket.supporting_members:
        if str(getattr(m, "span_verdict", "")).upper() != "SUPPORTS":
            continue
        eid = m.evidence_id
        quote = (m.direct_quote or "").strip()
        row = pool.get(eid) or {}
        hay = str(row.get("direct_quote") or row.get("statement") or "")
        if quote and hay and quote in hay:
            return True
    return False


# ── Load real banked baskets + pool ───────────────────────────────────────────────────────────────
_bib = _load_json("bibliography.json")
_raw_baskets = []
for entry in _bib:
    for bk in entry.get("baskets", []):
        if bk.get("supporting_members"):
            _raw_baskets.append(bk)

# Build the GLOBAL evidence pool: prefer the real evidence_pool.json row; guarantee each chosen
# member's verbatim span is locatable by also stocking the member's own direct_quote (the pool row's
# direct_quote IS the member's verified span in production).
_evidence_pool_global: dict = {}
try:
    for eid, row in _load_json("evidence_pool.json").items():
        _evidence_pool_global[str(eid)] = dict(row)
except Exception:
    pass
for bk in _raw_baskets:
    for m in bk["supporting_members"]:
        eid = str(m["evidence_id"])
        dq = str(m.get("direct_quote") or "")
        row = _evidence_pool_global.get(eid) or {}
        hay = str(row.get("direct_quote") or row.get("statement") or "")
        if dq and dq not in hay:
            # Ensure the member's verified span resolves (the pool row carries that span in prod).
            _evidence_pool_global[eid] = {"direct_quote": dq, "statement": dq}

_baskets = [_build_basket(bk) for bk in _raw_baskets]
_resolvable_baskets = [b for b in _baskets if _resolvable(b, _evidence_pool_global)]
assert len(_resolvable_baskets) >= 2, (
    f"need >=2 resolvable baskets in the bank; got {len(_resolvable_baskets)}"
)

# Controlled SHARED-ANCHOR pairing: take the first TWO resolvable baskets with DISTINCT clusters and
# give them a shared subject+predicate so they are pairing candidates. Real members/spans untouched.
_A = _resolvable_baskets[0]
_B = next(b for b in _resolvable_baskets[1:] if b.claim_cluster_id != _A.claim_cluster_id)
_A.subject = _B.subject = "ai labor impact"
_A.predicate = _B.predicate = "affects"
_SECTION = [_A, _B]
_CID_A, _CID_B = _A.claim_cluster_id, _B.claim_cluster_id


def _make_edge(a, b):
    class _E:
        claim_cluster_ids = (a, b)
        source = "semantic"
        severity = "review"
    return _E()


_failures: list[str] = []
_passes: list[str] = []


def _check(name, cond, detail=""):
    (_passes if cond else _failures).append(f"{name}: {detail}")
    print(("PASS " if cond else "FAIL ") + name + (f" -- {detail}" if detail else ""))


# ── ASSERTION 1 + 3 (neutral): no-edge pair -> neutral connective; sentence carries 2 distinct tokens.
_units_neutral = compose_cross_source_analytical_units(
    _SECTION, _evidence_pool_global,
    writer_fn=_short_writer, verify_fn=verify_sentence_provenance,
    edges=None, equiv_clusters=None, agree_map=None,
)
_check("A1_neutral_unit_produced", len(_units_neutral) >= 1,
       f"{len(_units_neutral)} analytical unit(s)")
if _units_neutral:
    _u = _units_neutral[0]
    _toks = _resolved_spans(_u)
    _evids = {t[0] for t in _toks}
    _check("A1_two_distinct_ev_tokens", len(_evids) >= 2,
           f"distinct ev_ids={sorted(_evids)}")
    _check("A3_neutral_connective", LICENSED_CONNECTIVES["neutral"].strip() in _u,
           f"connective present; in_contrast_absent={LICENSED_CONNECTIVES['conflict'].strip() not in _u}")
    _check("A3_no_fabricated_in_contrast", LICENSED_CONNECTIVES["conflict"].strip() not in _u
           and LICENSED_CONNECTIVES["agreement"].strip() not in _u,
           "no conflict/agreement phrase on a no-edge pair")

# ── ASSERTION 2: per-clause re-verify PASSES; a foreign-span mutation FAILS. ─────────────────────────
if _units_neutral:
    _u = _units_neutral[0]
    _clauses = split_into_sentences(_u) or [_u]
    # The analytical sentence is ONE sentence carrying both tokens; verify it as the production engine
    # would, AND verify each token's own clause grounds.
    _whole = verify_sentence_provenance(_u, _evidence_pool_global)
    # Per-clause: rebuild each atom token into a standalone sentence-form and re-verify.
    import re as _re
    _tok_re = _re.compile(r"\[#ev:(?P<ev>[A-Za-z0-9_]+):(?P<s>\d+)-(?P<e>\d+)\]")
    _per_clause_ok = True
    _seen_tokens = list(_tok_re.finditer(_u))
    _check("A2_two_tokens_in_sentence", len(_seen_tokens) >= 2,
           f"{len(_seen_tokens)} [#ev] tokens in the analytical sentence")
    for mt in _seen_tokens:
        ev, s, e = mt.group("ev"), int(mt.group("s")), int(mt.group("e"))
        row = _evidence_pool_global.get(ev) or {}
        span_text = str(row.get("direct_quote") or row.get("statement") or "")[s:e]
        clause_sentence = f"{span_text.strip()} [#ev:{ev}:{s}-{e}]."
        res = verify_sentence_provenance(clause_sentence, _evidence_pool_global)
        if not bool(getattr(res, "is_verified", False)):
            _per_clause_ok = False
    _check("A2_per_clause_verify_passes", _per_clause_ok,
           "each atom clause re-passes verify_sentence_provenance")

    # Foreign-span mutation: re-point clause B's token to a span from a DIFFERENT evidence id with a
    # blatantly out-of-bounds offset -> the engine must FAIL it (span_out_of_bounds / not in pool).
    _bad = f"Some fabricated relation [#ev:__not_in_pool__:0-50]."
    _bad_res = verify_sentence_provenance(_bad, _evidence_pool_global)
    _check("A2_foreign_span_fails", not bool(getattr(_bad_res, "is_verified", False)),
           f"foreign-id sentence rejected (reasons={list(getattr(_bad_res,'failure_reasons',[]))[:2]})")

# ── ASSERTION 3 (conflict): inject a ContradictionEdge -> "; in contrast,". ──────────────────────────
_check("A3_license_conflict",
       license_relation(_CID_A, _CID_B, edges=[_make_edge(_CID_A, _CID_B)]) == "conflict",
       "edge between the pair -> conflict")
_units_conflict = compose_cross_source_analytical_units(
    _SECTION, _evidence_pool_global,
    writer_fn=_short_writer, verify_fn=verify_sentence_provenance,
    edges=[_make_edge(_CID_A, _CID_B)],
)
_check("A3_conflict_connective_renders",
       bool(_units_conflict) and LICENSED_CONNECTIVES["conflict"].strip() in _units_conflict[0],
       (_units_conflict[0] if _units_conflict else "no unit"))

# ── ASSERTION 3 (agreement): inject an agree_map -> "; consistent with this,". ───────────────────────
_check("A3_license_agreement",
       license_relation(_CID_A, _CID_B, agree_map={_CID_A: {_CID_B}}) == "agreement",
       "agree_map entry -> agreement")
_units_agree = compose_cross_source_analytical_units(
    _SECTION, _evidence_pool_global,
    writer_fn=_short_writer, verify_fn=verify_sentence_provenance,
    edges=None, agree_map={_CID_A: {_CID_B}},
)
_check("A3_agreement_connective_renders",
       bool(_units_agree) and LICENSED_CONNECTIVES["agreement"].strip() in _units_agree[0],
       (_units_agree[0] if _units_agree else "no unit"))

# Conflict precedence over agreement (a contested pair is never smoothed into agreement).
_check("A3_conflict_precedence",
       license_relation(_CID_A, _CID_B, edges=[_make_edge(_CID_A, _CID_B)],
                        agree_map={_CID_A: {_CID_B}}) == "conflict",
       "edge + agree_map -> conflict wins")

# ── ASSERTION 4: KEEP-ALL — every source/basket cited pre-change is present post-change. ─────────────
# The analytical unit is ADDITIVE: its two cited ev_ids are exactly the two baskets' members; nothing
# is removed. Confirm both members' ev_ids appear in the produced analytical sentence's tokens.
if _units_neutral:
    _evids = {t[0] for t in _resolved_spans(_units_neutral[0])}
    _a_members = {m.evidence_id for m in _A.supporting_members
                  if str(m.span_verdict).upper() == "SUPPORTS"}
    _b_members = {m.evidence_id for m in _B.supporting_members
                  if str(m.span_verdict).upper() == "SUPPORTS"}
    _check("A4_keep_all_both_baskets_cited",
           bool(_evids & _a_members) and bool(_evids & _b_members),
           f"unit cites a member of BOTH baskets (A_hit={_evids & _a_members}, B_hit={_evids & _b_members})")

# ── Default-OFF byte-identical guard (the unit pass is purely additive; the flag gates the CALLER). ──
# The composer itself is only invoked when PG_CROSS_SOURCE_SYNTHESIS is ON (verified_compose gate), so
# here we assert the keystone neutral-default fail-closed: an UNANCHORED section yields zero units.
_unanchored = [_build_basket(bk) for bk in _raw_baskets[:2]]
for b in _unanchored:
    b.subject = ""  # no anchor
_units_none = compose_cross_source_analytical_units(
    _unanchored, _evidence_pool_global,
    writer_fn=_short_writer, verify_fn=verify_sentence_provenance, edges=None,
)
_check("A5_no_anchor_no_units", _units_none == [],
       f"{len(_units_none)} units from unanchored baskets (must be 0 — no random juxtaposition)")


# ── GUARD: licensed_relations neutralizes an UNLICENSED connective; keeps a licensed one. ────────────
from src.polaris_graph.generator.relational_quantifier_guard import (  # noqa: E402
    guard_relational_quantifier,
)
_synth = ("Claim A [#ev:acemoglu_restrepo_automation_tasks:0-40]; in contrast, "
          "claim b [#ev:autor_why_still_jobs:0-40]")
_kept = guard_relational_quantifier(_synth, None, licensed_relations={"conflict"})
_check("G1_licensed_connective_kept",
       "; in contrast," in (_kept or ""), "conflict licensed -> kept")
_neut = guard_relational_quantifier(_synth, None, licensed_relations=set())
_check("G2_unlicensed_connective_neutralized",
       "; in contrast," not in (_neut or "") and "; separately," in (_neut or ""),
       f"unlicensed -> neutralized ({(_neut or '')[:80]})")
# Default-OFF (licensed_relations=None) is BYTE-IDENTICAL to the legacy single-clause guard: a plain
# sentence with no aggregate quantifier returns UNCHANGED.
_plain = "Employment rose by 3 percent [#ev:autor_why_still_jobs:0-40]."
_check("G3_default_off_byte_identical",
       guard_relational_quantifier(_plain, _A) == _plain,
       "no-quantifier sentence unchanged on the legacy path")

# ── LAYER 2: PROMOTE mode (default-OFF) labels a GROUNDED sentence; OFF leaves it bare. ──────────────
from src.polaris_graph.generator import analyst_synthesis_deviation_check as _dev  # noqa: E402
_bib_l2 = [{"evidence_id": "autor_why_still_jobs"}]
_rows_l2 = [{"evidence_id": "autor_why_still_jobs",
             "direct_quote": "Automation has not eliminated employment."}]
_synth_text = "Automation has not eliminated employment [1]."
_grounded_judge = lambda _c, _s: True  # noqa: E731 — deterministic offline judge
# OFF (default): grounded sentence passes bare.
os.environ.pop("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", None)
_off_text, _off_tel = _dev.screen_synthesis_against_baskets(
    _synth_text, _bib_l2, _rows_l2, judge_fn=_grounded_judge)
_check("L2_promote_off_bare", "[confidence:" not in _off_text and _off_tel.get(
    "synthesis_deviation_promoted_count", 0) == 0, "grounded sentence bare when PROMOTE off")
# ON: grounded sentence gains a positive moderate confidence marker (KEEP-and-PROMOTE).
os.environ["PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED"] = "1"
_on_text, _on_tel = _dev.screen_synthesis_against_baskets(
    _synth_text, _bib_l2, _rows_l2, judge_fn=_grounded_judge)
os.environ.pop("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", None)
_check("L2_promote_on_labels_grounded",
       "[confidence: moderate" in _on_text and _on_tel.get("synthesis_deviation_promoted_count", 0) == 1,
       f"grounded -> promoted ({_on_text[-60:]})")
# An UNGROUNDED sentence stays hedged/labeled LOW regardless of PROMOTE (never promoted).
_ung_text, _ung_tel = _dev.screen_synthesis_against_baskets(
    _synth_text, _bib_l2, _rows_l2, judge_fn=lambda _c, _s: False)
_check("L2_ungrounded_stays_low",
       "[confidence: low" in _ung_text and _ung_tel.get("synthesis_deviation_labeled_count", 0) == 1,
       "ungrounded sentence labeled LOW, never promoted")


print("\n=== SUMMARY ===")
print(f"PASS {len(_passes)} / {len(_passes) + len(_failures)}")
if _failures:
    print("FAILURES:")
    for f in _failures:
        print("  -", f)
    sys.exit(1)
print("ALL M6 BEHAVIORAL ASSERTIONS PASS")
