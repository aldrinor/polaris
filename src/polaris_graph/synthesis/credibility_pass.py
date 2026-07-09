"""I-cred-012 (#1162) — credibility-analysis pass ORCHESTRATOR (the activation chain).

Pure orchestrator that runs the committed P4→P3→P2→P5→P6 redesign chain over the generator's EFFECTIVE
evidence pool and returns the disclosure inputs (``credibility_by_evidence``, ``origin_by_evidence``,
``claims``, ``edges``, ``weight_mass``). The sweep runner calls it under the master slate
``PG_SWEEP_CREDIBILITY_REDESIGN``; OFF ⇒ not invoked ⇒ byte-identical. ADVISORY only: ``strict_verify`` +
the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps/drops a sentence or flips
release.

FAIL-LOUD vs LABEL (I-arch-005 B12, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"):
a row missing ``evidence_id``, a P4 independence-annotation gap, or a wired-module crash still ABORT the
pass (``CredibilityPassError``) — those are real, unrecoverable integrity holes. But the two INFRA
conditions that used to abort the WHOLE report no longer hold it (I-arch-005 B12-P1, operator-locked
2026-06-14 "nothing shall hold the report"):
  * a PER-SOURCE P2 ``judge_error`` — ``score_source_credibility`` isolates it to ONE row and falls back
    to that source's DETERMINISTIC priors (a real weight, never fabricated);
  * a MISSING production credibility judge (``judge=None``) — an infra/config condition, NOT a
    faithfulness finding: the chain runs priors-only and every source carries its real deterministic
    authority weight.
In both cases the affected sources are LABELED ``credibility_unscored`` (a disclosed gap, surfaced LOUD
per LAW II — never a silent downgrade) and the rest keep scoring; the report SHIPS with the gap rather
than HELD. The genuine cited-evidence coverage gap (a CITED evidence_id with NO credibility row at all)
stays fail-loud — that is a real provenance hole, caught downstream by ``apply_disclosure_to_svs``'s
coverage assertion. The credibility WEIGHT math is untouched; only the abort-the-basket reaction on
those two infra conditions became a per-source label (the pass is ADVISORY — the binding gates are
``strict_verify`` + the 4-role D8 release policy).

Order (locked): P4 copied-annotated rows (fail-loud on missing eid) → P3 supersession → P2 score
(LABEL credibility_unscored on judge_error / judge=None, never abort) → POST-P3 credibility =
P2 × P3 multiplier (certainty carried) → P5 claim graph
→ P6 weight-mass over the POST-P3 judgments. P10 dissent + the M-52 effective-pool hoist + the P8
render-site wrapper are the per-hook sub-issues; this module is the chain core they consume.
"""
from __future__ import annotations

import dataclasses
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from src.polaris_graph.authority.credibility_skill import score_source_credibility
from src.polaris_graph.authority.supersession import supersession_adjustment
from src.polaris_graph.synthesis.claim_graph import build_claim_graph
from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass

_MASTER_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

# I-arch-008 HOP-A KEYSTONE (#1265): the basket consolidator re-clusters claims from scratch via
# ``claim_graph.build_claim_graph`` whose FAIL-CLOSED ``build_merge_key`` singletons every clinical
# numeric whose dose/comparator/effect_measure/endpoint is blank (the documented A13 residual). That
# fragments 787 sources -> ~1781 mostly-singleton clusters (only 1 multi-member), so
# ``verified_support_origin_count`` stays <=1 everywhere and the rendered header reads "Multi-source
# corroborated (>=2 verified origins): 0". MEANWHILE ``finding_dedup.dedup_by_finding`` ALREADY groups
# the SAME rows by numeric finding (787 -> ~99 clusters WITH member_indices + member_hosts), and that
# grouping is on the LIVE run path (run_honest_sweep_r3.py:8079) — but it is thrown away for the basket
# path. When this flag is ON the basket consolidator CONSUMES finding_dedup's already-computed cluster
# grouping: it MERGES claim_graph's existing claim partition (never rebuilds members from rows, never
# splits, never drops) so same-finding members land in ONE basket, then runs the EXISTING isolated
# per-member verify UNCHANGED. Multi-source baskets EMERGE because the members are already grouped — NOT
# because any member newly passes the gate (the set that passes ``_verify_member_in_isolation`` is
# byte-identical: same claim.text, same span, same verify_fn). DEFAULT OFF => the legacy claim_graph
# grouping runs byte-identical (§-1.3 WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP).
_ENV_BASKET_CONSUME_FINDING_DEDUP = "PG_BASKET_CONSUME_FINDING_DEDUP"


def basket_consume_finding_dedup_enabled() -> bool:
    """True iff the HOP-A keystone (consume finding_dedup grouping for baskets) is explicitly enabled.

    DEFAULT OFF (unset / 0 / off / false / no) => the legacy claim_graph cluster grouping is used
    verbatim => the assembled baskets, the rendered header, and the disclosure JSON are byte-identical
    to the pre-change tree. ON => ``_regroup_graph_by_finding_dedup`` merges the claim partition using
    finding_dedup membership before ``_assemble_baskets`` (grouping + origin-counting ONLY — the
    per-member verify and strict_verify are NEVER touched)."""
    return os.environ.get(_ENV_BASKET_CONSUME_FINDING_DEDUP, "").strip().lower() not in _OFF_VALUES

# I-arch-007 ITEM 1b (#1264): bounded parallelism for the per-member isolated-verify loop in
# ``_assemble_baskets``. The advisory pass verifies EVERY basket member against its OWN single span via
# the production entailment judge — a SERIAL O(N) loop over hundreds of members at up to 150 s/call is the
# wedge that hung Q72/Q76/Q90 (the credibility-pass death). Parallelizing the INDEPENDENT per-member
# verifies with a BOUNDED pool + deterministic post-step reassembly changes WALL-CLOCK only — never which
# verdict any member gets (``_verify_member_in_isolation`` is pure per-member: each member's claim vs its
# OWN single span) and never a binding gate (the pass is ADVISORY; ``basket_verdict`` is a pure LABEL).
# LAW VI: env-overridable, no magic number. DEFAULT 1 = the byte-identical SERIAL path — the parallelism
# stays INERT until explicitly enabled, which honors the HARD ordering constraint that 1b's parallel
# verifies (they share the singleton entailment-judge client) must NOT run concurrently before ITEM 2a
# makes that client thread-safe/thread-local (CONSOLIDATED_FIX_PLAN ITEM 1b "HARD ORDERING CONSTRAINT").
_ENV_PASS_MAX_INFLIGHT = "PG_CREDIBILITY_PASS_MAX_INFLIGHT"
_DEFAULT_PASS_MAX_INFLIGHT = 1

# I-deepfix-001 BANK-BEFORE-WALL (#1264 follow-up): when the caller threads a soft deadline, the
# fraction of the REMAINING budget granted to phase A (P2 source scoring) — the rest is reserved for
# the per-member basket verifies (phase B, the leg that feeds the SUPPORTS baskets / the breadth
# enrichment). Without this split, phase A could consume the entire budget and phase B would bank
# ZERO verified members => the corroboration layer still empties (the exact drb_72 box1 defect
# reappearing one phase later). LAW VI: env-overridable; a bad value falls back to the default.
_ENV_PHASE_A_BUDGET_FRAC = "PG_CREDIBILITY_PASS_PHASE_A_FRAC"
_DEFAULT_PHASE_A_BUDGET_FRAC = 0.5
# Floor on any phase budget (seconds) so a near-expired deadline still lets a few members bank
# rather than sentinel-filling everything on arrival.
_MIN_PHASE_BUDGET_S = 60.0


def _phase_a_budget_frac() -> float:
    """The phase-A share of the remaining soft-deadline budget, in (0, 1). Bad/out-of-range env
    values fall back to the default (fail-safe: the split must always leave phase B a share)."""
    raw = os.environ.get(_ENV_PHASE_A_BUDGET_FRAC, "").strip()
    if not raw:
        return _DEFAULT_PHASE_A_BUDGET_FRAC
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return _DEFAULT_PHASE_A_BUDGET_FRAC
    if not (0.0 < val < 1.0):
        return _DEFAULT_PHASE_A_BUDGET_FRAC
    return val


def _pass_max_inflight() -> int:
    """The bounded per-member verify concurrency (LAW VI). 1 (default) ⇒ the serial path is taken
    verbatim — byte-identical to the pre-1b loop. A bad/empty value falls back to the serial default
    (fail-safe, never an unbounded pool)."""
    try:
        value = int(
            os.environ.get(_ENV_PASS_MAX_INFLIGHT, _DEFAULT_PASS_MAX_INFLIGHT)
            or _DEFAULT_PASS_MAX_INFLIGHT
        )
    except (TypeError, ValueError):
        return _DEFAULT_PASS_MAX_INFLIGHT
    return value if value >= 1 else _DEFAULT_PASS_MAX_INFLIGHT


# ── I-deepfix-001 B9(a) (#1353): deterministic tier-authority prior join ─────────────────────────
# FORENSIC ROOT (verified against the banked drb_72 corpus_snapshot): the generator-visible evidence
# rows arrive with NO ``authority_score`` (and no ``source_class`` / ``signal_scores`` to recompute the
# full authority model from), so ``weight_mass.aggregate_weight_mass`` reads ``authority_score`` = None
# -> ``cluster_mass`` = 0.0 across EVERY claim and ``weight_mass`` renders 0.0 — the opposite of the
# CONSOLIDATE-and-WEIGHT goal. The rows DO carry a ``tier`` (T1..T7 / UNKNOWN) on every row. The fix:
# when a row lacks ``authority_score``, JOIN a deterministic tier-derived prior onto the row copy so a
# real, honest weight flows to BOTH the canonical-selection in independence_collapse (lowest-authority
# canonical for an undated cluster) AND to weight_mass.cluster_mass. This is a WEIGHT, never a DROP /
# CAP / FILTER (§-1.3); it never touches strict_verify / NLI / 4-role / provenance. It is joined at the
# TOP of _run_chain (before collapse) so collapse and weight_mass agree on the canonical.
#
# The per-tier prior MIRRORS ``nodes.weighted_corpus_gate._DEFAULT_TIER_CREDIBILITY_PRIOR`` (one
# semantic source of truth; kept local to avoid coupling a synthesis module to a nodes module). LAW VI:
# the whole map is env-overridable via PG_CREDIBILITY_TIER_AUTHORITY_PRIOR (JSON), and the join itself
# is gated default-ON by PG_CREDIBILITY_TIER_AUTHORITY_JOIN.
_ENV_TIER_AUTHORITY_JOIN = "PG_CREDIBILITY_TIER_AUTHORITY_JOIN"
_ENV_TIER_AUTHORITY_PRIOR = "PG_CREDIBILITY_TIER_AUTHORITY_PRIOR"
# I-deepfix-001 (#1344) W1: the UNKNOWN/no-match prior is RAISED off 0.20 to a neutral 0.45
# ("unclassified", disclosed) — a credible NON-journal institution that the tier classifier does
# not recognize (WEF/OECD/most IGOs are absent from every tier set) was being pinned to the SAME
# 0.20 band as an anonymous blog, a de-facto SOFT FILTER (weight_mass = authority_score, so it
# sank and lost slots). 0.45 is a CALIBRATED credibility weight on the continuous scale, not a
# floor forcing a coverage number — it is the honest "unclassified" position; predatory/junk still
# lands low via the authority model's junk_detection. LAW VI: fully overridable via the env JSON.
_DEFAULT_TIER_AUTHORITY_PRIOR: dict[str, float] = {
    "T1": 0.95, "T2": 0.85, "T3": 0.75, "T4": 0.60,
    "T5": 0.40, "T6": 0.30, "T7": 0.15, "UNKNOWN": 0.45,
}
# B9(a) fail-loud canary: with the master redesign ON, an all-zero authority_score across rows is a
# WIRING BREAK (the join no-oped), not a legitimate zero. Default ON => the LOUD warning always fires;
# the hard raise is opt-in (PG_REQUIRE_NONZERO_AUTHORITY) to honor the FAIL-OPEN rule (a scorer-side
# wiring detection must never itself drop a source).
_ENV_REQUIRE_NONZERO_AUTHORITY = "PG_REQUIRE_NONZERO_AUTHORITY"

# ── I-deepfix-003 (#1374): recognized-institution TIER FLOOR (RAISE-ONLY, anchor-eligibility) ─────
# The tier classifier buries credible NON-journal institutions at T6/UNKNOWN, and the downstream
# anchor-to-strong-source signal reads the TIER label — so a WEF/OECD/BLS/think-tank/university
# source is not seen as a valid anchor even though its authority WEIGHT is high. When a row's URL
# resolves to an ``institutional_authority`` band (registry OR the ``*.gov`` / ``*.edu`` rule) this
# stamps a RAISE-ONLY tier floor so the source becomes anchor-eligible in the synthesis layer
# (AtomicClaim.source_tier / BasketMember.source_tier both derive from the row ``tier`` this join
# writes). It NEVER lowers a stronger existing tier (a genuine T1 journal keeps T1) and NEVER touches
# the faithfulness engine (strict_verify / NLI / 4-role D8 / provenance) — a claim's grounding is
# unchanged; only where the source SORTS as an anchor changes. Behind its OWN kill-switch
# (default ON); OFF => tier unchanged while the WEIGHT leg still runs (that rides
# PG_INSTITUTIONAL_AUTHORITY_WEIGHT). §-1.3 WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP.
_ENV_INSTITUTIONAL_TIER = "PG_INSTITUTIONAL_AUTHORITY_TIER"
# band_key -> anchor-eligible tier FLOOR. igo / statistical_agency / government (primary
# institutional producers) AND think_tank / news_masthead / university (rigorous secondary
# analysis) ALL floor to T3 — operator decision 2026-07-09 (Fable gate item A) so credible
# institutions clear the T1-T3 anchor bar. (``government`` is the band the ``*.gov`` /
# ``ed.gov`` suffix rule assigns.)
_INSTITUTIONAL_TIER_FLOOR: dict[str, str] = {
    "igo": "T3",
    "statistical_agency": "T3",
    "government": "T3",
    # Operator decision 2026-07-09 (Fable gate item A): raise think_tank / news_masthead /
    # university from T4 to T3 so credible institutions (HBR, MIT Sloan, Tony Blair Institute,
    # AFL-CIO, universities) CLEAR the T1-T3 "strong anchor" bar (Signal-2). The explicit
    # authority_note ("institutional authority: <band>") preserves transparency — T3 here means
    # "government OR recognized institutional authority", it never implies a think-tank IS a
    # government agency. Still RAISE-ONLY (a genuine T1/T2 journal is never lowered to T3).
    "think_tank": "T3",
    "news_masthead": "T3",
    "university": "T3",
}
# Tier STRENGTH rank: lower = stronger (T1 strongest, UNKNOWN weakest). Used ONLY for the RAISE-ONLY
# guard — a floor is applied to a field iff it is STRICTLY STRONGER than that field's current value,
# so no field is ever lowered.
_TIER_STRENGTH_RANK: dict[str, int] = {
    "T1": 1, "T2": 2, "T3": 3, "T4": 4, "T5": 5, "T6": 6, "T7": 7, "UNKNOWN": 8,
}


def institutional_tier_floor_enabled() -> bool:
    """True iff the I-deepfix-003 recognized-institution TIER-floor leg is active (LAW VI kill-switch
    ``PG_INSTITUTIONAL_AUTHORITY_TIER``, default ON). OFF => tiers are left untouched by this join
    (and no ``authority_note`` is stamped); the WEIGHT leg is independent and keeps running."""
    return os.environ.get(_ENV_INSTITUTIONAL_TIER, "on").strip().lower() not in _OFF_VALUES


def _tier_rank_of(value: object) -> int:
    """The STRENGTH rank of a raw tier value (blank/unrecognized => UNKNOWN = weakest). RAISE-ONLY
    guard helper: read per-field so a stronger existing tier in either ``tier`` / ``source_tier`` is
    never lowered."""
    key = str(value or "").strip().upper()
    return _TIER_STRENGTH_RANK.get(key if key in _TIER_STRENGTH_RANK else "UNKNOWN", 8)


def tier_authority_join_enabled() -> bool:
    """True iff the default-ON B9(a) tier-authority prior join is active (LAW VI kill-switch
    ``PG_CREDIBILITY_TIER_AUTHORITY_JOIN=0`` => rows keep whatever authority_score they arrived with)."""
    return os.environ.get(_ENV_TIER_AUTHORITY_JOIN, "on").strip().lower() not in _OFF_VALUES


def _tier_authority_prior_map() -> dict[str, float]:
    """The per-tier authority prior (LAW VI). Env JSON override merges over the default; a malformed
    override falls back to the default (fail-safe: never an empty/zeroed map). PURE-ish (reads env)."""
    raw = os.environ.get(_ENV_TIER_AUTHORITY_PRIOR, "").strip()
    if not raw:
        return dict(_DEFAULT_TIER_AUTHORITY_PRIOR)
    try:
        import json as _json  # noqa: PLC0415
        override = _json.loads(raw)
        if not isinstance(override, dict):
            return dict(_DEFAULT_TIER_AUTHORITY_PRIOR)
        merged = dict(_DEFAULT_TIER_AUTHORITY_PRIOR)
        for k, v in override.items():
            merged[str(k).strip().upper()] = _clamp01(v) or 0.0
        return merged
    except Exception:
        return dict(_DEFAULT_TIER_AUTHORITY_PRIOR)


def _tier_of_row(row: dict) -> str:
    """The row's tier label, normalized to the prior-map key shape (``T4`` / ``UNKNOWN``). A blank /
    unrecognized tier maps to ``UNKNOWN`` (the conservative low prior, never a wrong-high default)."""
    tier = str(row.get("source_tier") or row.get("tier") or "").strip().upper()
    return tier if tier in _DEFAULT_TIER_AUTHORITY_PRIOR else "UNKNOWN"


def _row_url(row: dict) -> str:
    """The row's source URL for the W1 institutional lookup (first non-empty of the usual keys)."""
    for key in ("source_url", "url", "canonical_url", "final_url"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _join_tier_authority_prior(rows: list[dict]) -> list[dict]:
    """B9(a): return COPIES of ``rows`` with a deterministic tier-derived ``authority_score`` joined
    onto any row that lacks one (None / missing / non-numeric). A row that ALREADY carries a numeric
    authority_score is preserved verbatim (the real computed weight wins; the tier prior is only a
    fallback). Never mutates the caller's rows; never drops a row. Returns the rows unchanged when the
    join is disabled. PURE-ish (reads env via the prior map).

    I-deepfix-001 (#1344) W1 — POSITIVE institutional-authority WEIGHT: after the base
    authority_score is resolved (real computed weight OR tier prior), a recognized credible
    institution (WEF/OECD/IGO, national statistical agency, major think-tank, reputable news
    masthead — the LAW-VI ``institutional_authority`` registry) has its authority_score RAISED to
    its calibrated institutional band. This is a RAISE-ONLY floor: a real computed weight ABOVE the
    band is never lowered, and a freak-low weight can never demote a real institution. Disclosed via
    ``authority_score_source``.

    I-deepfix-003 (#1374) — recognized-institution TIER FLOOR + explicit label: when the row's URL
    resolves to an institutional band (registry OR the ``*.gov`` / ``*.edu`` rule) this ALSO stamps a
    RAISE-ONLY anchor-eligible tier floor (igo/statistical_agency/government -> T3;
    think_tank/news_masthead/university -> T3) so a credible institution the tier classifier buried at
    T6/UNKNOWN is seen as a valid anchor downstream (AtomicClaim.source_tier / BasketMember.source_tier
    both derive from the row ``tier`` written here). Each tier field is guarded against ITS OWN current
    rank, so a stronger existing tier (a genuine T1 journal) is NEVER lowered. It also stamps an
    explicit ``authority_note = "institutional authority: <band>"`` so a reader sees WHY the source is
    credible. The tier leg is behind its OWN kill-switch ``PG_INSTITUTIONAL_AUTHORITY_TIER`` (default
    ON); OFF => tier + note untouched while the WEIGHT leg (``PG_INSTITUTIONAL_AUTHORITY_WEIGHT``) still
    runs. Nothing is dropped and the faithfulness engine is untouched — a pure WEIGHT/tier correction
    of the de-facto soft-filter (``weight_mass = authority_score``, so a mis-low institution sank and
    lost slots). §-1.3 WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP."""
    if not tier_authority_join_enabled():
        return rows
    from src.polaris_graph.synthesis.institutional_authority import (  # noqa: PLC0415
        institutional_authority_for_url,
        institutional_band_for_url,
    )

    prior = _tier_authority_prior_map()
    tier_floor_on = institutional_tier_floor_enabled()
    out: list[dict] = []
    for row in rows:
        existing = row.get("authority_score")
        has_existing = (
            isinstance(existing, (int, float)) and not isinstance(existing, bool)
        )
        base = (
            float(existing)
            if has_existing
            else float(prior.get(_tier_of_row(row), prior["UNKNOWN"]))
        )
        url = _row_url(row)
        # ``new_row`` stays None until something actually changes -> the caller's row is appended
        # verbatim (byte-identical no-op) when neither leg fires.
        new_row: dict | None = None

        # ── W1 WEIGHT leg (PG_INSTITUTIONAL_AUTHORITY_WEIGHT, RAISE-ONLY) ──
        inst_weight = institutional_authority_for_url(url)
        if inst_weight is not None and inst_weight > base:
            new_row = dict(row)  # COPY — never mutate the caller's row
            new_row["authority_score"] = float(inst_weight)
            new_row["authority_score_source"] = "institutional_registry"  # disclosed
            new_row["institutional_authority_band"] = float(inst_weight)
        elif not has_existing:
            new_row = dict(row)  # COPY — never mutate the caller's row
            new_row["authority_score"] = base
            new_row["authority_score_source"] = "tier_prior"  # disclosed deterministic fallback
        # else: has_existing and no institutional raise -> weight kept verbatim (new_row stays None).

        # ── I-deepfix-003 TIER-floor leg + authority_note (PG_INSTITUTIONAL_AUTHORITY_TIER, RAISE-ONLY) ──
        if tier_floor_on:
            band_key = institutional_band_for_url(url)
            if band_key is not None:
                if new_row is None:
                    new_row = dict(row)  # promote to a COPY so we never mutate the caller's row
                # Explicit institutional-authority label — reader sees WHY the source is credible
                # (operator decision: reuse the T3/T4 tier BUT surface an explicit label, not a bare
                # badge). Rides on the row's authority record (no external consumer reads it yet —
                # surface it wherever that record is disclosed).
                new_row["authority_note"] = f"institutional authority: {band_key}"
                floor_tier = _INSTITUTIONAL_TIER_FLOOR.get(band_key)
                if floor_tier is not None:
                    floor_rank = _TIER_STRENGTH_RANK[floor_tier]
                    raised = False
                    # Guard EACH tier field independently against ITS OWN current rank so a stronger
                    # existing value is NEVER lowered. ``tier`` is the field every downstream
                    # claim/basket consumer reads (claim_graph, BasketMember); ``source_tier`` is
                    # raised too ONLY when the row already carries it.
                    for field in ("tier", "source_tier"):
                        if field == "source_tier" and field not in row:
                            continue
                        if floor_rank < _tier_rank_of(row.get(field)):
                            new_row[field] = floor_tier
                            raised = True
                    if raised:
                        new_row["tier_before_institutional_floor"] = _tier_of_row(row)  # disclosed
                        new_row["institutional_authority_tier_floor"] = floor_tier  # disclosed

        out.append(new_row if new_row is not None else row)
    return out


def _emit_zero_authority_canary(rows: list[dict]) -> None:
    """B9(a) fail-loud canary: with the redesign ON, an all-zero / all-missing authority_score across
    rows means the prior join no-oped — a WIRING BREAK, not a legitimate zero. Always emits the LOUD
    warning (LAW II); the HARD raise is opt-in via ``PG_REQUIRE_NONZERO_AUTHORITY`` so this detection
    can never itself drop a source (the FAIL-OPEN rule)."""
    if not rows:
        return
    any_nonzero = any(
        isinstance(r.get("authority_score"), (int, float))
        and not isinstance(r.get("authority_score"), bool)
        and float(r.get("authority_score") or 0.0) > 0.0
        for r in rows
    )
    if any_nonzero:
        return
    import logging as _logging  # noqa: PLC0415
    msg = (
        "[credibility-pass] B9(a) WIRING-BREAK CANARY: authority_score is zero/missing across ALL "
        f"{len(rows)} rows with the credibility redesign ON — weight_mass will render 0.0 everywhere. "
        "The tier-authority prior join did not fire (check PG_CREDIBILITY_TIER_AUTHORITY_JOIN and that "
        "rows carry a 'tier'). This is a wiring break, not a legitimate zero."
    )
    _logging.getLogger(__name__).warning(msg)
    if os.environ.get(_ENV_REQUIRE_NONZERO_AUTHORITY, "").strip().lower() in ("1", "true", "yes", "on"):
        raise CredibilityPassError(
            "abort_zero_authority_wiring_break: " + msg + " (PG_REQUIRE_NONZERO_AUTHORITY opt-in raise)"
        )


def credibility_redesign_enabled() -> bool:
    """The master activation slate. OFF ⇒ the runner never calls the pass ⇒ byte-identical.

    P0-A20 (I-arch-007, 602->22 funnel): the WEIGHT-AND-CONSOLIDATE redesign (CLAUDE.md §-1.3)
    is now the COHERENT DEFAULT — UNSET evaluates ON, matching the run-path mirror
    ``run_honest_sweep_r3._cred_redesign_on`` (which already defaults ``"on"``). Pre-fix this
    helper (and the other four library mirrors) defaulted to the EMPTY string, which IS a member
    of ``_OFF_VALUES`` -> unset evaluated OFF -> the library stayed on the legacy filter-and-cap /
    source-DROP path while the orchestrator believed the redesign was on. That split IS the funnel.
    An EXPLICIT ``PG_SWEEP_CREDIBILITY_REDESIGN=0`` (or off/false/no) still returns False -> the
    legacy path is preserved byte-for-byte for the regression/escape-hatch case."""
    return os.environ.get(_MASTER_FLAG, "on").strip().lower() not in _OFF_VALUES


class CredibilityPassError(RuntimeError):
    """Activated pass cannot complete faithfully — fail-loud, never a silent false-green advisory."""


@dataclass
class EvidenceCredibility:
    evidence_id: str
    credibility_weight: float       # POST-P3: P2 weight × supersession multiplier, clamped [0,1]
    reliability_score: float
    relevance_score: float
    origin_cluster_id: str
    is_canonical_origin: bool
    certainty_downgrade: bool       # carried explicitly from P3 (supersession), not folded into the number
    soft_warning: str | None
    # I-arch-005 B12 (#1257): True iff THIS source's credibility judge errored (the priors-only
    # fallback weight was used). A DISCLOSED LABEL — the source is still scored (priors), the rest
    # of the corpus keeps its LLM judgments, and the WHOLE report no longer aborts on one judge
    # error. Defaulted False so every legacy construction + the flag-OFF path is byte-identical.
    credibility_unscored: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# I-arch-002 [8] / Wave-3 design §5/§6 — the per-claim ClaimBasket.
#
# A basket is one claim_cluster_id's whole group of supporting sources. Principle
# 2 (CONSOLIDATE, don't DROP): ``supporting_members`` keeps ALL sources, never a
# representative. Principle 3 (BASKET FAITHFULNESS): the verdict is decided against
# the WHOLE basket, but ``verified_support_origin_count`` is computed by ISOLATED
# per-member verification — each member verified against its OWN single span, never
# a multi-citation union (design §0/§5 FIX-3: a union that passes while a member
# fails alone must count that member UNVERIFIED). ``basket_verdict`` is a LABEL only
# (design §6): it may downgrade / drop / label, but NEVER resurrect a
# strict_verify-dropped sentence.
#
# These are ADVISORY side-outputs assembled under the master flag. strict_verify +
# the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps or
# drops a sentence or flips release.
# ─────────────────────────────────────────────────────────────────────────────

# basket_verdict labels (design §5 — NAMED constants, no inline magic strings).
BASKET_VERDICT_FULL = "full"            # every supporting member independently verified on its own span
BASKET_VERDICT_PARTIAL = "partial"      # some but not all members verified
BASKET_VERDICT_CONTESTED = "contested"  # >=1 refuter edge references this cluster (user judges)
BASKET_VERDICT_UNVERIFIED = "unverified"  # no member verified alone

# I-deepfix-001 F1-STRUCTURAL (#1344) — kill-switch for the basket-build chrome screen.
# The consolidation engine matched two pieces of page-furniture (a truncated DOI/running-header
# fragment and a CC-license footer) across two papers and certified them as one claim with two
# origins (the chrome x chrome basket behind F1 + A1-A10). When ON (default), each SUPPORTS
# member's claim-local span AND the cluster claim_text are screened through the SAME shared
# render-seam predicate ``weighted_enrichment.is_render_chrome_or_unrenderable``; a member whose
# span is chrome/unrenderable is EXCLUDED from ``verified_origin_ids`` (the strengthening count)
# but is KEPT as a basket member (never deleted) and stays in the pool + disclosure. This is
# faithfulness-ADJACENT (consolidation layer): it ONLY REMOVES a chrome/unrenderable span from a
# corroboration COUNT -- it strengthens faithfulness, can never relax a gate or inflate breadth,
# and never hard-drops a source. LAW VI: OFF => byte-identical legacy count.
_ENV_BASKET_CHROME_SCREEN = "PG_BASKET_CHROME_SCREEN"


def _basket_chrome_screen_enabled() -> bool:
    """I-deepfix-001 F1-STRUCTURAL: is the basket-build chrome screen ON? (default ON). LAW VI."""
    return os.environ.get(_ENV_BASKET_CHROME_SCREEN, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


# ─────────────────────────────────────────────────────────────────────────────
# F3-3b (I-deepfix-001 #1369) — corroboration entailment-judge AVAILABILITY guard.
#
# ROOT CAUSE (Fable F3-3b, PRIMARY, forensic on the drb_72 real run): the ISOLATED
# per-member entailment judge that must confirm a grouped member SUPPORTS its claim
# before it counts as a corroboration origin went UNAVAILABLE 176 times this run. A
# member whose entailment call errored/timed-out is durably marked
# ``entailment_judge_unavailable`` (see BasketMember + Wave-3 P1b) and NEVER counted, so
# the multi-source corroboration collapses (4/78 cited). The run used a same-family GLM
# entailment judge with POOR OpenRouter provider availability — the SAME class as the D8
# judge provider-count render-blocker (the kimi-k2.6 availability lesson).
#
# THIS BLOCK adds the three availability protections Fable specifies, WITHOUT changing
# what COUNTS as support (a real SUPPORTS entailment) and WITHOUT touching the frozen
# faithfulness engine (strict_verify / the entailment verifier / 4-role D8 / provenance):
#   (i)   active_entailment_judge_model() names the ACTUAL binding judge the per-member verify ran
#         on (``PG_ENTAILMENT_MODEL``, default the entailment_judge default ``z-ai/glm-5.2``) — the
#         model that ACTUALLY counted the corroboration, so the Methods disclosure never makes a
#         wrong methods claim (LAW II / §-1.1). corroboration_judge_model() names the HIGH-PROVIDER-
#         COUNT open model the corroboration judge SHOULD resolve to (kimi-k2.6), surfaced in the
#         Methods disclosure SEPARATELY as the RECOMMENDED mitigation target. The advisory
#         corroboration verify shares the process-singleton entailment judge with the binding
#         strict_verify (verify_sentence_provenance has NO per-call model seam), so the model is
#         ACTUALLY selected by the run-slate ``PG_ENTAILMENT_MODEL`` — a faithfulness-adjacent
#         wiring above a builder's authority for the frozen binding judge. These resolvers +
#         disclosure make BOTH the real judge and the intended target explicit and env-overridable;
#         neither mutates the singleton.
#   (ii)  bounded retries with backoff on transient/blank/429 ALREADY exist on the shared
#         entailment judge path (entailment_judge.py: _DEFAULT_ENTAILMENT_RETRIES, the U16
#         rate-limit floor/backoff, provider rotation). The corroboration verify inherits
#         them; no change is made to that frozen path.
#   (iii) count_judge_unavailable_members() + build_judge_availability_methods_disclosure()
#         SURFACE the report-level ``entailment_judge_unavailable`` member count into the
#         Methods disclosure (LAW II: never silently soften the corroboration count).
#   (iv)  _enforce_judge_availability_canary() — a FAIL-LOUD canary that always LOUD-warns
#         the count/fraction and HARD-RAISES ``CredibilityPassError`` when the unavailable
#         fraction exceeds an ENV-DRIVEN threshold (no default magic number drives the
#         raise; unset => warn-only, matching the proven _emit_zero_authority_canary
#         fail-open posture so a legacy/default run never aborts on a blip).
# ─────────────────────────────────────────────────────────────────────────────
_ENV_CORROBORATION_JUDGE_MODEL = "PG_CORROBORATION_ENTAILMENT_MODEL"
# The high-provider-count open model the corroboration entailment judge SHOULD resolve to
# (the D8 availability lesson: pick a model OpenRouter serves via many providers so the
# per-member burst does not 429/blank-storm and LOSE verdicts to outages). kimi-k2.6 is a
# reasoning open model served by ~21 providers and is NOT in the glm generator family, so
# the two-family invariant holds for an advisory corroboration judge. LAW VI: env-overridable.
_DEFAULT_CORROBORATION_JUDGE_MODEL = "moonshotai/kimi-k2.6"
# (iv) the fail-loud canary threshold — env-driven, no default magic-number hard-fail.
_ENV_JUDGE_UNAVAILABLE_MAX_FRAC = "PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC"
# The env the LIVE per-member entailment judge ACTUALLY resolves its model from (the same
# ``verify_sentence_provenance`` -> ``_get_judge()`` singleton the binding strict_verify uses).
# The Methods disclosure names THIS model — the one that actually counted the corroboration —
# so the report never makes a WRONG methods claim (LAW II / §-1.1). Kept as a local literal
# fallback (verified against ``entailment_judge._DEFAULT_ENTAILMENT_MODEL``); the real default is
# lazy-imported at resolve time so the two never drift.
_ENV_ACTIVE_ENTAILMENT_MODEL = "PG_ENTAILMENT_MODEL"
_ENTAILMENT_JUDGE_DEFAULT_MODEL = "z-ai/glm-5.2"


def corroboration_judge_model() -> str:
    """F3-3b(i): the HIGH-PROVIDER-COUNT open model the corroboration entailment judge SHOULD
    resolve to (``PG_CORROBORATION_ENTAILMENT_MODEL``, default a many-provider open reasoning
    model). Surfaced in the Methods disclosure as the RECOMMENDED higher-provider mitigation
    target — NOT as the judge that actually ran (that is ``active_entailment_judge_model()``).

    HONEST ACTIVATION NOTE: the advisory corroboration verify calls the SAME
    ``verify_sentence_provenance`` -> ``_get_judge()`` PROCESS SINGLETON as the binding
    strict_verify (there is no per-call model-injection seam), so the model actually used is
    ``PG_ENTAILMENT_MODEL`` — set by the run slate. This resolver NAMES the intended target and
    is env-overridable; it deliberately does NOT mutate the frozen singleton (that would change
    the binding judge's verdicts — a faithfulness change above a builder's authority). Pointing
    the LIVE judge at this model is a run-slate / operator decision (§9.1.8 + the D8 lesson)."""
    return os.environ.get(_ENV_CORROBORATION_JUDGE_MODEL, "").strip() or _DEFAULT_CORROBORATION_JUDGE_MODEL


def active_entailment_judge_model() -> str:
    """F3-3b(i): the model the LIVE per-member corroboration entailment judge ACTUALLY runs on.

    The advisory per-member verify shares ``verify_sentence_provenance`` -> ``_get_judge()`` (the
    frozen process singleton) with the binding strict_verify, and that judge resolves its model from
    ``PG_ENTAILMENT_MODEL`` (default the entailment_judge default ``z-ai/glm-5.2``). The Methods
    disclosure MUST name THIS model — the one that actually counted the corroboration — never the
    recommended target, otherwise a clinical-grade report would state a WRONG methods claim (LAW II /
    §-1.1). The real default is lazy-imported from ``entailment_judge`` (single source of truth); a
    local literal is the fail-safe fallback if that import is unavailable. Read-only (reads env)."""
    override = os.environ.get(_ENV_ACTIVE_ENTAILMENT_MODEL, "").strip()
    if override:
        return override
    try:
        from src.polaris_graph.llm.entailment_judge import (  # noqa: PLC0415
            _DEFAULT_ENTAILMENT_MODEL as _ej_default,
        )
        return str(_ej_default).strip() or _ENTAILMENT_JUDGE_DEFAULT_MODEL
    except Exception:
        return _ENTAILMENT_JUDGE_DEFAULT_MODEL


def _judge_unavailable_max_frac() -> float | None:
    """F3-3b(iv): the ENV-DRIVEN fail-loud threshold (a fraction in (0, 1]). UNSET / ``off`` /
    ``none`` / non-numeric / out-of-range => ``None`` = the canary is WARN-ONLY (never raises).

    No default magic number drives a hard abort (per the F3 spec): the raise fires ONLY when the
    operator/run-slate EXPLICITLY configures a ceiling and the run exceeds it — the same
    fail-open-by-default posture ``_emit_zero_authority_canary`` uses so a legacy/default run is
    never aborted by a transient judge blip. LAW VI."""
    raw = os.environ.get(_ENV_JUDGE_UNAVAILABLE_MAX_FRAC, "").strip().lower()
    if raw in ("", "off", "none", "disabled", "no"):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] %s=%r is not a float; the judge-availability canary stays "
            "WARN-ONLY (no hard raise).", _ENV_JUDGE_UNAVAILABLE_MAX_FRAC, raw,
        )
        return None
    if not (0.0 < value <= 1.0):
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] %s=%s out of (0,1]; the judge-availability canary stays "
            "WARN-ONLY (no hard raise).", _ENV_JUDGE_UNAVAILABLE_MAX_FRAC, value,
        )
        return None
    return value


def count_judge_unavailable_members(baskets: list) -> tuple[int, int]:
    """F3-3b(iii): return ``(judge_unavailable_member_count, total_member_count)`` across every
    basket's ``supporting_members``. ``judge_unavailable`` counts a member whose entailment judge
    was DURABLY UNAVAILABLE this run (``entailment_judge_unavailable`` — a judge_error / timeout /
    transport-hard-drop / deadline-skip), the ONLY signal that means a verdict was LOST to an
    outage (a clean NEUTRAL/CONTRADICTED is a genuine gap, not counted here). Pure/read-only."""
    total = 0
    unavailable = 0
    for basket in (baskets or []):
        for member in (getattr(basket, "supporting_members", None) or []):
            total += 1
            if bool(getattr(member, "entailment_judge_unavailable", False)):
                unavailable += 1
    return unavailable, total


def build_judge_availability_methods_disclosure(
    unavailable: int, total: int, *, judge_model: str | None = None, recommended_model: str | None = None
) -> str:
    """F3-3b(iii): the report Methods-section disclosure sentence about entailment-judge
    availability during corroboration counting.

    ``judge_model`` names the ACTUAL binding judge the per-member corroboration verify ran on this
    run (``active_entailment_judge_model()`` = ``PG_ENTAILMENT_MODEL``, default the entailment_judge
    default ``z-ai/glm-5.2``) — the model that ACTUALLY counted the corroboration. Naming any other
    model here would be a WRONG methods statement in a clinical-grade report (LAW II / §-1.1): the
    advisory verify shares the frozen process-singleton judge (no per-call model seam), so it cannot
    have run on a different model than the run-slate ``PG_ENTAILMENT_MODEL``.

    ``recommended_model`` (``corroboration_judge_model()`` = the high-provider-count open model,
    default kimi-k2.6) is surfaced SEPARATELY, as the recommended higher-provider mitigation target
    when a judge-outage storm actually lost verdicts — never asserted as the judge that ran.

    NEVER empty — even at zero unavailable it states the actual judge and that no verdicts were lost,
    so the Methods section is honest either way. The caller surfaces this on the
    ``CredibilityAnalysis`` (``methods_disclosure``) for the report Methods builder to render."""
    judge = (judge_model or active_entailment_judge_model())
    recommended = (recommended_model or corroboration_judge_model())
    if total <= 0:
        return (
            "Corroboration counting: no basket members were verified this run "
            f"(entailment judge: {judge})."
        )
    frac = unavailable / total if total else 0.0
    if unavailable <= 0:
        return (
            f"Corroboration counting: entailment verification (judge: {judge}) was available for "
            f"all {total} basket member(s); no corroboration verdicts were lost to judge "
            "unavailability."
        )
    # The recommended mitigation is surfaced SEPARATELY and only when it differs from the judge that
    # actually ran (never claiming the recommended model was the one that counted the corroboration).
    recommend_clause = ""
    if recommended and recommended != judge:
        recommend_clause = (
            f" Recommended mitigation: point the entailment judge at a higher-provider-count open "
            f"model ({recommended})."
        )
    return (
        f"Corroboration counting: entailment verification (judge: {judge}) was UNAVAILABLE for "
        f"{unavailable} of {total} basket member(s) ({frac:.1%}) this run — those members are "
        "disclosed as verification-unavailable and were NOT counted as corroboration origins "
        f"(the multi-source counts are a floor, never inflated).{recommend_clause}"
    )


def _enforce_judge_availability_canary(unavailable: int, total: int) -> None:
    """F3-3b(iv): the FAIL-LOUD judge-availability canary.

    ALWAYS emits a LOUD warning with the unavailable count/fraction (LAW II — the corroboration
    count is never silently softened). HARD-RAISES ``CredibilityPassError`` ONLY when an
    ENV-DRIVEN ceiling (``PG_CORROBORATION_JUDGE_UNAVAILABLE_MAX_FRAC``) is set AND the unavailable
    fraction exceeds it — a genuine judge-outage STORM (the drb_72 176-outage collapse) that
    guts corroboration must FAIL the run rather than ship a deficient report. Unset ceiling =>
    warn-only (fail-open, never aborts a legacy/default run). No default magic number drives the
    raise."""
    if total <= 0:
        return
    frac = unavailable / total
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger(__name__).warning(
        "[credibility-pass] F3-3b judge-availability: entailment verification UNAVAILABLE for "
        "%d/%d basket member(s) (%.1f%%) this run — those members are disclosed "
        "verification-unavailable and NOT counted as corroboration origins (never silently "
        "softened). Set %s to a fraction to HARD-FAIL on a judge-outage storm.",
        unavailable, total, frac * 100.0, _ENV_JUDGE_UNAVAILABLE_MAX_FRAC,
    )
    threshold = _judge_unavailable_max_frac()
    if threshold is not None and frac > threshold:
        raise CredibilityPassError(
            "abort_corroboration_judge_unavailable_storm: entailment verification was unavailable "
            f"for {unavailable}/{total} basket member(s) ({frac:.1%}), exceeding the configured "
            f"ceiling {_ENV_JUDGE_UNAVAILABLE_MAX_FRAC}={threshold:.3f}. The corroboration count is "
            "gutted by a judge-outage storm (same class as the drb_72 176-outage collapse) — "
            "failing loud rather than shipping a deficient report (never victory-on-deficient). "
            "Point the entailment judge at a higher-provider-count open model "
            f"(corroboration_judge_model()={corroboration_judge_model()!r}) or raise the ceiling."
        )


# I-arch-010 FIX-2 Step 0 — the 3-value per-member entailment tier (the no-leak
# classifier). ``span_verdict`` stays STRICTLY BINARY (SUPPORTS/UNSUPPORTED) so every
# existing ``== "SUPPORTS"`` consumer (render/count/enrichment/biblio) is byte-unchanged;
# ``member_tier`` is the ADDITIVE seam a downstream keep-with-labels layer (I-arch-011)
# reads to surface grounded-but-weak candidates WITHOUT ever surfacing deterministic
# garbage. Binding invariant: ``span_verdict == "SUPPORTS"`` iff
# ``member_tier == MEMBER_TIER_ENTAILMENT_VERIFIED``.
MEMBER_TIER_ENTAILMENT_VERIFIED = "ENTAILMENT_VERIFIED"      # (a)-(e) PASS AND genuine ENTAILED (judge ran, no error) — the ONLY counted/rendered tier
MEMBER_TIER_DETERMINISTIC_ONLY = "DETERMINISTIC_ONLY"        # (a)-(e) PASS but entailment NEUTRAL/CONTRADICTED OR judge-errored — grounded-but-weak (I-arch-011-surfaceable)
MEMBER_TIER_UNVERIFIED = "UNVERIFIED"                        # own span FAILS (a)-(e), or timed out / no evidence — never surfaced


@dataclass
class BasketMember:
    """One source backing a claim basket, carrying its OWN isolated span verdict.

    ``span_verdict`` is the result of verifying this member ALONE against its own
    span (SUPPORTS / UNSUPPORTED). It is never a union verdict — that is the whole
    anti-laundering property (design §5 FIX-3). A member with no verified span is
    kept (Principle 2: never dropped) and shown as UNSUPPORTED.
    """

    evidence_id: str
    source_url: str
    source_tier: str
    origin_cluster_id: str
    credibility_weight: float | None
    authority_score: float
    span: tuple                     # (start, end) of the member's own verified span
    direct_quote: str               # the span text the member was verified against
    # "SUPPORTS" | "UNSUPPORTED" — the BINARY result of isolated per-member
    # verification. Design §5's enum also lists CONTEXT, but that is a RENDER-layer
    # (P5.x) distinction (a span shown as background, not support); isolated
    # strict_verify is pass/fail, so this assembly emits only the two binary values.
    span_verdict: str
    # I-arch-010 FIX-2 Step 0 — the ADDITIVE 3-value entailment tier (see the
    # MEMBER_TIER_* constants). Default UNVERIFIED so any legacy constructor that omits
    # it is the safest (never-surfaced) tier. ``span_verdict`` stays binary; this field
    # is the seam I-arch-011 reads to distinguish grounded-but-weak (DETERMINISTIC_ONLY)
    # from deterministic garbage (UNVERIFIED). No TAIL consumer renders/counts it.
    member_tier: str = MEMBER_TIER_UNVERIFIED
    # I-deepfix-001 Wave-3 PART 2 ARM B P1b (#1344): the DURABLE judge-outage signal. True iff this
    # member is DETERMINISTIC_ONLY BECAUSE the entailment judge errored / timed out this run (NOT a
    # clean NEUTRAL/CONTRADICTED). Default False so any legacy constructor that omits it is the safe
    # (genuine-gap) value. Read ONLY by the ARM-B degraded-verify disclosure to separate a transient
    # judge OUTAGE from a genuine evidence gap; never rendered, never counted as support.
    entailment_judge_unavailable: bool = False
    # I-deepfix-001 COV-DECHROME-BASKETS (#1344): True iff this member's claim-local span
    # (``direct_quote``) is page furniture / a dead-fetch shell / a truncated fragment, per the SAME
    # shared render-seam predicate the basket-build chrome screen already runs. Default False so any
    # legacy constructor that omits it is the safe (not-chrome) value. The downstream cross-source
    # (``depth_synthesis``) member selection reads this DURABLE flag to hold a chrome member OUT of the
    # corroboration set BEFORE the eligibility gate (the coverage forensic root: chrome member spans
    # collapsed the depth pre-pass 3->0 and killed the one cross-source pair). Never rendered, never
    # counted as support, never a faithfulness verdict; the member itself is KEPT (§-1.3 no-drop).
    span_is_chrome: bool = False


@dataclass
class ClaimBasket:
    """A per-claim basket — the group of sources carrying the SAME claim (design §5).

    ``supporting_members`` keeps ALL sources (never dropped). ``refuter_cluster_ids``
    REFERENCE the contradicting clusters (not duplicated). ``total_clustered_origin_count``
    is ADVISORY (the clustered, not-verified origin count from weight_mass) and is
    NEVER rendered as support strength. ``verified_support_origin_count`` —
    the ONLY strengthening count — is the number of DISTINCT origin clusters whose
    member passed ISOLATED per-member verification on its own span. ``basket_verdict``
    is a LABEL derived from those counts + refuter references; it can never upgrade a
    dropped sentence.
    """

    claim_cluster_id: str
    claim_text: str
    subject: str
    predicate: str
    supporting_members: list                 # list[BasketMember] — ALL sources, never dropped
    refuter_cluster_ids: tuple               # REFERENCE only (design §5)
    weight_mass: float                       # authority-only, copy-uninflatable (from weight_mass.py)
    total_clustered_origin_count: int        # ADVISORY ONLY — never rendered as support strength
    verified_support_origin_count: int       # isolated-verified distinct origins (the only strengthening count)
    basket_verdict: str                      # full | partial | contested | unverified (LABEL only)


@dataclass
class CredibilityAnalysis:
    credibility_by_evidence: dict   # evidence_id -> EvidenceCredibility
    origin_by_evidence: dict        # evidence_id -> origin_cluster_id
    claims: list                    # AtomicClaim[] (Phase-5)
    edges: list                     # ContradictionEdge[] (Phase-5)
    weight_mass: list               # ClaimWeightMass[] (Phase-6)
    # I-arch-002 [8] — per-claim baskets + the sentence->claim_cluster_id binding.
    # Defaulted so the empty-rows early-return (and any legacy caller) still builds.
    baskets: list = field(default_factory=list)             # ClaimBasket[]
    cluster_id_by_evidence: dict = field(default_factory=dict)  # evidence_id -> claim_cluster_id[] (binding)
    # F3-3b (I-deepfix-001 #1369) — corroboration entailment-judge availability disclosure.
    # Defaulted so the empty-rows early-return + every legacy caller still builds byte-identically.
    entailment_judge_unavailable_member_count: int = 0   # members whose entailment judge was durably UNAVAILABLE
    basket_member_count: int = 0                          # total basket members verified this run
    methods_disclosure: str = ""                          # report Methods-section judge-availability sentence


def _require_evidence_id(row: dict, index: int) -> str:
    eid = str((row or {}).get("evidence_id") or "").strip()
    if not eid:
        raise CredibilityPassError(
            f"abort_credibility_pass_error: evidence row {index} has no evidence_id (cannot disclose a "
            f"claim whose source can't be identified)"
        )
    return eid


def _clamp01(value: float) -> float:
    return 0.0 if value < 0.0 else 1.0 if value > 1.0 else value


# ── I-arch-002 [8] — ClaimBasket assembly + isolated per-member verification ───


def _row_span_text(row: dict) -> str:
    """The member's own span text (the same field strict_verify reads). Mirrors
    ``provenance_generator``'s ``direct_quote or statement`` resolution so the
    isolated verification runs against the SAME bytes strict_verify would."""
    return str((row or {}).get("direct_quote") or (row or {}).get("statement") or "")


def _claim_local_span(claim_text: str, row_text: str) -> str:
    """ISSUE #1279 P1#2 — the CLAIM-LOCAL span text for the basket member's ``direct_quote``.

    The downstream verified-compose acceptance region (``verified_compose._member_global_span``) is
    recovered by LOCATING the member's ``direct_quote`` inside the global row text. If ``direct_quote``
    is the WHOLE row (``_row_span_text(row)``), the region becomes ``(0, len(row))`` — the entire row —
    and a composed sentence citing a DIFFERENT in-row claim's offsets passes the cross-claim region gate
    (the P1#2 hole). The claim's OWN ``text`` (the extractor's ``context_snippet`` — a verbatim substring
    of the row for numeric/qualitative claims) is the claim-LOCAL span, so the region is claim-specific.

    Returns the claim-local span IFF it is a NON-EMPTY substring of ``row_text`` (so it resolves
    downstream); otherwise returns ``""`` (FAIL-CLOSED: the member defines NO acceptance region and NO
    verbatim-fallback span — never the whole row). This is strictly MORE restrictive than the full row.
    """
    local = str(claim_text or "").strip()
    haystack = str(row_text or "")
    if local and haystack and local in haystack:
        return local
    return ""


_ENTAILMENT_FAILURE_PREFIXES = (
    # I-arch-010 FIX-2 Step 0 — the COMPLETE set of failure-reason prefixes the
    # ENTAILMENT block of ``verify_sentence_provenance`` can append (verified against
    # provenance_generator.py: the NEUTRAL/CONTRADICTED drops at :2076/:2182/:2216 use
    # ``entailment_failed:``; the legacy transport hard-drop at :2243 uses
    # ``entailment_judge_error_fail_closed:``). A member whose failure_reasons are ALL
    # in this set passed the deterministic (a)-(e) engine and only entailment is
    # unsatisfied/inconclusive — grounded-but-weak (DETERMINISTIC_ONLY), DISTINCT from a
    # member whose OWN span fails (a)-(e) (deterministic garbage, UNVERIFIED).
    "entailment_failed:",
    "entailment_judge_error_fail_closed:",
)

# I-deepfix-001 Wave-3 PART 2 ARM B P1b (#1344): the SUBSET of entailment failure prefixes that mean the
# judge was DURABLY UNAVAILABLE (errored / timed out / transport-hard-dropped) this run — as opposed to a
# CLEAN NEUTRAL/CONTRADICTED verdict (``entailment_failed:``, where the judge RAN and answered). Only a
# judge-UNAVAILABLE member may drive the ARM-B "entailment verification was unavailable" disclosure; a
# clean non-entailment is a GENUINE evidence gap, not a transient outage (Codex Wave-3 P1b). Paired with
# the durable ``result.judge_error`` boolean (the machine-readable marker per provenance_generator.py).
_ENTAILMENT_JUDGE_ERROR_PREFIX = "entailment_judge_error_fail_closed:"


def _classify_member_tier(result: Any) -> tuple[str, str, bool]:
    """Map a full ``SentenceVerification`` result onto ``(span_verdict, member_tier, judge_unavailable)``.

    ``span_verdict`` stays STRICTLY BINARY (the binding invariant
    ``span_verdict == "SUPPORTS"`` iff ``member_tier == ENTAILMENT_VERIFIED``).
    Reads ONLY ``is_verified`` / ``judge_error`` / ``failure_reasons`` — all already on
    the object; the deterministic (a)-(e) engine and the entailment judge verdict logic
    are NEVER touched (FROZEN, §-1.4).

    I-deepfix-001 Wave-3 PART 2 ARM B P1b (#1344): ``judge_unavailable`` is the DURABLE
    third signal — ``True`` iff the member's entailment tier is DETERMINISTIC_ONLY BECAUSE the
    judge errored / timed out / transport-hard-dropped this run (``result.judge_error`` OR an
    ``entailment_judge_error_fail_closed:`` reason), ``False`` for a CLEAN NEUTRAL/CONTRADICTED
    (``entailment_failed:``, judge ran) and for every non-DETERMINISTIC_ONLY tier. It NEVER
    changes the span_verdict / member_tier (byte-identical to the pre-P1b 2-tuple for those two);
    it only lets the ARM-B disclosure distinguish a transient judge OUTAGE from a genuine gap.
    """
    is_verified = bool(getattr(result, "is_verified", False))
    judge_error = bool(getattr(result, "judge_error", False))
    if is_verified and not judge_error:
        # genuine ENTAILED (judge ran, no error) — the ONLY counted/rendered tier.
        return "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED, False
    if is_verified and judge_error:
        # FIX-1 transport-keep: passed (a)-(e), entailment INCONCLUSIVE (judge errored).
        # NOT genuinely entailed → must NOT count/render as verified support (closes the
        # judge_error leak). Grounded-but-weak: an I-arch-011 keep-with-label candidate.
        # P1b: judge_error=True → the judge was UNAVAILABLE (durable outage signal).
        return "UNSUPPORTED", MEMBER_TIER_DETERMINISTIC_ONLY, True
    # is_verified == False below.
    failure_reasons = list(getattr(result, "failure_reasons", None) or [])
    if failure_reasons and all(
        any(str(r).startswith(p) for p in _ENTAILMENT_FAILURE_PREFIXES)
        for r in failure_reasons
    ):
        # deterministic (a)-(e) PASS but entailment NEUTRAL/CONTRADICTED (or any
        # entailment failure when FIX-1 is off) — grounded-but-weak, same tier as the
        # row above for I-arch-011's purpose (it cleared the deterministic engine).
        # P1b: judge-UNAVAILABLE only when the DURABLE outage signal is present — the durable
        # ``judge_error`` boolean OR an ``entailment_judge_error_fail_closed:`` reason. A CLEAN
        # NEUTRAL/CONTRADICTED (only ``entailment_failed:`` reasons, judge ran) is judge_unavailable
        # == False → a genuine gap, never disclosed as "verification unavailable".
        judge_unavailable = judge_error or any(
            str(r).startswith(_ENTAILMENT_JUDGE_ERROR_PREFIX) for r in failure_reasons
        )
        return "UNSUPPORTED", MEMBER_TIER_DETERMINISTIC_ONLY, judge_unavailable
    # the member's OWN span genuinely lacks the claim's number / content-overlap (or no
    # failure reasons at all) — deterministic garbage; NEVER surfaced.
    return "UNSUPPORTED", MEMBER_TIER_UNVERIFIED, False


def _verify_member_in_isolation(
    claim_text: str,
    member_row: dict,
    *,
    verify_fn: Callable,
) -> tuple[str, str, bool]:
    """Verify ONE member against ITS OWN single span — never a union (design §5 FIX-3).

    Builds a single-provenance-token sentence (``<claim_text> [#ev:<eid>:0-<len>]``)
    so ``verify_sentence_provenance`` has EXACTLY ONE token. The per-token union loop
    inside the verifier (which aggregates decimals/text across MULTIPLE tokens) is the
    laundering path; one token means no union, so a member whose own span lacks the
    claim's number/content fails ALONE — even if a multi-citation union would pass.

    Returns the 3-tuple ``(span_verdict, member_tier, judge_unavailable)`` (I-arch-010 FIX-2
    Step 0 + I-deepfix-001 Wave-3 P1b). ``span_verdict`` is ``"SUPPORTS"`` iff the isolated
    sentence is genuinely entailment-verified, else ``"UNSUPPORTED"``; ``member_tier`` is the
    additive 3-value classification; ``judge_unavailable`` is the DURABLE judge-outage signal
    (see ``_classify_member_tier``). The verifier is INJECTED (production
    ``verify_sentence_provenance`` by default; a deterministic fake in tests) and is NEVER
    re-run as a gate — this is advisory.
    """
    eid = str((member_row or {}).get("evidence_id") or "")
    span = _row_span_text(member_row)
    if not eid or not span:
        # No evidence to verify against — the safest non-counted, never-surfaced tier.
        return "UNSUPPORTED", MEMBER_TIER_UNVERIFIED, False
    # Defensive single-token guarantee (the anti-laundering invariant, design §5
    # FIX-3): strip ANY stray provenance / calc token already in the claim text so
    # the appended one is the ONLY token. With exactly one token the verifier's
    # per-token union loop cannot aggregate this member's span with any other — a
    # member whose own span lacks the claim fails ALONE.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        _CALC_TOKEN_RE,
        _PROVENANCE_TOKEN_RE,
    )
    safe_text = _PROVENANCE_TOKEN_RE.sub(" ", str(claim_text or ""))
    safe_text = _CALC_TOKEN_RE.sub(" ", safe_text).strip()
    # ONE token spanning the member's whole own span.
    sentence = f"{safe_text} [#ev:{eid}:0-{len(span)}]"
    pool = {eid: dict(member_row)}
    try:
        result = verify_fn(sentence, pool)
    except Exception:
        # Advisory path: a verifier failure on one member is conservatively the safest
        # tier (never resurrects the member, never aborts the basket) — fail-closed for
        # the strengthening count, which can only ever UNDERCOUNT, never inflate. A verifier
        # crash is NOT a judge outage (judge_unavailable=False → a genuine gap, never disclosed
        # as "verification unavailable").
        return "UNSUPPORTED", MEMBER_TIER_UNVERIFIED, False
    return _classify_member_tier(result)


# I-deepfix-001 BANK-BEFORE-WALL (#1264 follow-up, drb_72 box1 canary rc=1): the sentinel verdict a
# member receives when the pass's soft deadline expires BEFORE its isolated verify ran. Conservative
# by direction — "UNSUPPORTED" can only UNDERCOUNT corroboration (the member never joins a SUPPORTS
# basket, never surfaces, never inflates breadth); ``judge_unavailable=True`` is the existing durable
# verification-unavailable label (Wave-3 P1b) so the skip is DISCLOSED, never silent. The members
# verified BEFORE the deadline keep their genuine ENFORCE-entailment verdicts and are BANKED — the
# frozen faithfulness engine (verify_fn) is called-not-edited and never re-run as a gate.
_DEADLINE_SKIP_VERDICT = ("UNSUPPORTED", MEMBER_TIER_UNVERIFIED, True)


def _run_member_verifies(
    tasks: list[tuple[str, dict]],
    *,
    verify_fn: Callable,
    max_inflight: int,
    deadline_monotonic: float | None = None,
) -> list[tuple[str, str, bool]]:
    """Run the per-member isolated verifies for ``tasks`` and return their verdicts IN ORDER.

    Each verdict is the 3-tuple ``(span_verdict, member_tier, judge_unavailable)`` from
    ``_verify_member_in_isolation`` (I-deepfix-001 Wave-3 P1b). The tuple is opaque here —
    it is passed through unchanged, so the serial and bounded-parallel paths stay
    verdict-identical.

    ``tasks`` is the FLAT, deterministically-ordered list of ``(claim_text, member_row)`` pairs
    (built in the ORIGINAL ``sorted(clusters)`` → member order). The returned verdict list is
    index-aligned with ``tasks`` (``results[i]`` is the verdict for ``tasks[i]``), so the caller
    reassembles baskets in EXACTLY the serial order — the parallel path is verdict-identical to the
    serial path, only faster.

    ``max_inflight == 1`` (the default) takes the SERIAL path verbatim — byte-identical to the
    pre-1b inline loop. For ``max_inflight >= 2`` a BOUNDED ``ThreadPoolExecutor`` caps concurrency at
    exactly ``max_inflight``; each worker runs inside a COPIED ``contextvars.copy_context()`` so:
      * the run-scoped JUDGE TELEMETRY ContextVar (FX-09, a MUTABLE dict) is the SAME object in the
        copy, so the judge's in-place ``calls/judge_error`` ticks land in the parent's counter (mirrors
        ``provenance_generator._verify_in_context``);
      * the run-scoped COST ContextVar (a float — rebinds don't propagate across a copy) is isolated to
        zero in the worker and its per-task delta is re-added to the parent counter + the budget
        re-checked (mirrors ``credibility_skill.score_source_credibility``), so the parallel advisory
        verifies never silently lose the run's cost accounting (Codex P2).
    A worker exception PROPAGATES out (fail-loud) exactly as the serial loop's ``verify_fn`` would —
    the existing ``_verify_member_in_isolation`` already maps a verifier failure to ``UNSUPPORTED``
    internally, so only a programming/budget defect ever escapes here.

    This is ADVISORY — ``_verify_member_in_isolation`` is never re-run as a gate, and parallelism
    changes WALL-CLOCK only, never any verdict.

    ``deadline_monotonic`` (I-deepfix-001 BANK-BEFORE-WALL): an OPTIONAL ``time.monotonic()``
    deadline. When it expires mid-pass, the verdicts computed SO FAR are BANKED verbatim and every
    not-yet-verified member gets ``_DEADLINE_SKIP_VERDICT`` (disclosed verification-unavailable —
    an UNDERCOUNT-only degrade, mirroring ``credibility_skill``'s proven priors-fill wall pattern).
    The drb_72 box1 defect this fixes: this loop had NO deadline, so the CALLER's all-or-nothing
    ``asyncio.wait_for`` wall discarded the ENTIRE analysis (baskets included) on a rich corpus and
    the "Corroborated Weighted Findings" breadth layer silently vanished from report.md (§-1.3
    funnel reassertion; breadth-enrichment canary rc=1). ``None`` (every legacy caller/test) =>
    byte-identical unbounded behavior.
    """
    n = len(tasks)
    if max_inflight <= 1 or n <= 1:
        # SERIAL fast path (default / single task): byte-identical to the pre-1b inline loop when no
        # deadline is threaded; with a deadline, bank the verified prefix + sentinel-fill the rest.
        serial_results: list[tuple[str, str, bool]] = []
        for _i, (claim_text, member_row) in enumerate(tasks):
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                import logging as _logging  # noqa: PLC0415
                _logging.getLogger(__name__).warning(
                    "[credibility-pass] BANK-BEFORE-WALL: member-verify soft deadline expired at "
                    "%d/%d (serial); BANKING the %d verified verdict(s) and filling the remaining %d "
                    "with the disclosed verification-unavailable sentinel (UNDERCOUNT-only; the "
                    "banked SUPPORTS members still surface the breadth layer — never discarded).",
                    _i, n, _i, n - _i,
                )
                serial_results.extend([_DEADLINE_SKIP_VERDICT] * (n - _i))
                break
            serial_results.append(
                _verify_member_in_isolation(claim_text, member_row, verify_fn=verify_fn)
            )
        return serial_results

    import concurrent.futures  # noqa: PLC0415 (lazy: zero cost on the serial default path)
    import contextvars  # noqa: PLC0415
    from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
        _add_run_cost,
        check_run_budget,
        current_run_cost,
        reset_run_cost,
    )

    def _verify_one(
        idx: int, claim_text: str, member_row: dict, ctx: contextvars.Context
    ) -> tuple[int, tuple[str, str, bool], float]:
        def _run() -> tuple[tuple[str, str, bool], float]:
            reset_run_cost()  # isolate THIS member's spend in the copied context (parent re-adds a clean delta)
            verdict = _verify_member_in_isolation(claim_text, member_row, verify_fn=verify_fn)
            return verdict, current_run_cost()
        verdict, delta = ctx.run(_run)
        return idx, verdict, delta

    results: list[tuple[str, str, bool] | None] = [None] * n
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=max_inflight)
    deadline_expired = False
    try:
        futures = [
            pool.submit(_verify_one, i, claim_text, member_row, contextvars.copy_context())
            for i, (claim_text, member_row) in enumerate(tasks)
        ]
        # I-deepfix-001 BANK-BEFORE-WALL: bound the join by the remaining soft-deadline budget (None =>
        # unbounded, byte-identical). Mirrors credibility_skill._judge_rows_pooled's PROVEN
        # as_completed(timeout=...)-then-drain wall pattern — bank what finished, never discard.
        _join_timeout: float | None = None
        if deadline_monotonic is not None:
            _join_timeout = max(0.001, deadline_monotonic - time.monotonic())
        try:
            for future in concurrent.futures.as_completed(futures, timeout=_join_timeout):
                idx, verdict, delta = future.result()  # re-raises BudgetExceededError / worker exc (fail closed)
                results[idx] = verdict
                _add_run_cost(delta)   # thread the per-member spend into the single run counter (no lost ticks)
                check_run_budget(0)    # raises BudgetExceededError -> bounded overspend (~max_inflight in flight)
        except concurrent.futures.TimeoutError:
            # The soft deadline fired before every member verified. Drain any future that DID finish
            # (a real verdict / a real BudgetExceededError is never lost), then sentinel-fill the rest
            # below. The banked SUPPORTS verdicts keep the corroboration/breadth layer ALIVE — the
            # all-or-nothing discard (the drb_72 box1 rc=1 root cause) is structurally gone.
            deadline_expired = True
            for _i, future in enumerate(futures):
                if results[_i] is not None or not future.done():
                    continue
                try:
                    idx, verdict, delta = future.result()
                except BudgetExceededError:
                    raise  # a real cap breach MUST still abort the sweep, even on the deadline path
                except Exception:  # noqa: BLE001 — a genuinely-failed worker takes the sentinel below
                    continue
                results[idx] = verdict
                _add_run_cost(delta)
                check_run_budget(0)  # enforce the aggregate cap on the drain path too (fail-closed)
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        # Deadline path: don't block on still-running verifies (wait=False) and cancel the queued
        # ones; the healthy path joins normally (wait=True). Orphaned worker cost ticks are recovered
        # by the caller's process-global ledger reconcile (multi_section_generator's finally block).
        pool.shutdown(wait=not deadline_expired, cancel_futures=deadline_expired)
    if deadline_expired:
        _banked = sum(1 for v in results if v is not None)
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] BANK-BEFORE-WALL: member-verify soft deadline expired with %d/%d "
            "verified; BANKING the verified verdicts and filling the remaining %d with the disclosed "
            "verification-unavailable sentinel (UNDERCOUNT-only; banked SUPPORTS members still "
            "surface the breadth layer — the analysis is never discarded).",
            _banked, n, n - _banked,
        )
        return [v if v is not None else _DEADLINE_SKIP_VERDICT for v in results]
    for i, verdict in enumerate(results):
        if verdict is None:
            raise CredibilityPassError(
                f"abort_credibility_pass_error: basket member index {i} produced no verdict from the "
                f"compute pool (fail-closed — a dropped future must never silently undercount)."
            )
    return [v for v in results if v is not None]


def _emit_basket_consume_marker(regrouped: int, *, noop: bool) -> None:
    """I-deepfix-001 Wave-3a (#1344): the HOP-A basket-consume ACTIVATION fire marker. Emitted ONLY when
    PG_BASKET_CONSUME_FINDING_DEDUP is ON so the OFF path (this whole regroup is skipped at the caller)
    stays byte-identical — the run_log carries no ``[activation]`` line. ``noop=True`` is the silent-no-op
    the routing proof flagged (the function returned the input graph UNCHANGED). Structural presence +
    count, never a threshold (§-1.3). Side-effect only; the returned graph is byte-untouched."""
    if not basket_consume_finding_dedup_enabled():
        return
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger(__name__).info(
        "[activation] basket_consume_finding_dedup: regrouped old_to_new=%d noop=%s",
        int(regrouped), bool(noop),
    )


def _regroup_graph_by_finding_dedup(
    graph: Any,
    annotated: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None,
) -> Any:
    """HOP-A KEYSTONE (#1265): MERGE claim_graph's existing claim partition using
    ``finding_dedup``'s already-computed cluster grouping, so same-finding members land in
    ONE basket. Returns a NEW graph-shaped view (same ``claims`` objects, MERGED ``clusters``,
    REMAPPED ``edges``); the input ``graph`` is never mutated.

    FAITHFULNESS — grouping + relabel ONLY (the HARD constraint):
      * The ``claims`` list (and every ``AtomicClaim.text`` / span the isolated verify reads) is
        UNCHANGED — passed through by reference. So the set of members that pass
        ``_verify_member_in_isolation`` downstream is byte-identical to the legacy grouping: same
        claim text, same span, same verify_fn. No member newly passes any gate.
      * Clusters are MERGED, never split and never dropped: the rebuilt partition covers EXACTLY the
        same claim indices as the input (a partition refinement in reverse — union only). A
        qualitative / raw / non-clinical claim that finding_dedup does not cluster keeps its OWN
        legacy singleton id (finding_dedup only groups finding-bearing rows; everything else is left
        exactly as claim_graph clustered it).
      * ``verified_support_origin_count`` rises ONLY because distinct ALREADY-verified origins now
        share a basket — never because acceptance was relaxed.
      * EDGES are remapped to the merged ids so a CONTESTED basket (a refuter edge references it)
        still renders CONTESTED — relabeling cluster ids without remapping edges would SILENTLY hide
        a contradiction (clinical-lethal). Each edge's ``claim_cluster_ids`` is rewritten through the
        same old->new map.

    ``finding_dedup`` is on the LIVE run path already (run_honest_sweep_r3.py:8079); this consumes its
    PURE grouping (no network, no LLM) with the SAME ``gov_suffixes`` + ``domain`` the rest of the
    pass uses. Deferred import (mirrors the lazy ``verify_sentence_provenance`` import) — finding_dedup
    imports credibility_pass inside its own function, so a function-local import here avoids the cycle.
    """
    from src.polaris_graph.synthesis.finding_dedup import dedup_by_finding  # noqa: PLC0415

    claims = list(getattr(graph, "claims", None) or [])
    if not claims:
        _emit_basket_consume_marker(0, noop=True)
        return graph

    # claim_graph emits AT MOST ONE numeric AtomicClaim per evidence_id (extract_numeric_claims emits
    # <=1/row); finding_dedup groups by the SAME numeric finding. Map evidence_id -> the NUMERIC claim
    # index so a finding cluster's member rows resolve to the right atom to union.
    #
    # I-deepfix-001 (#1344) KEYSTONE gap: finding_dedup ALSO forms QUALITATIVE baskets
    # (finding_key[0]=="__qual__"); numeric-only map resolved them to 0 members -> never merged
    # -> 0 corroboration + composer span-dumped. ALSO map non-numeric (qualitative/raw) atoms.
    # A row may carry MULTIPLE qualitative atoms per eid, so keep the FULL per-eid list and union
    # only ONE representative per origin row (never all-to-all -> would falsely merge two distinct
    # within-row claims). Merge-only; no member newly passes verify; edges remapped below.
    numeric_claim_idx_by_eid: dict[str, int] = {}
    qual_claim_idx_by_eid: dict[str, list[int]] = {}
    for ci, claim in enumerate(claims):
        kind = str(getattr(claim, "kind", "") or "")
        eid = str(getattr(claim, "evidence_id", "") or "")
        if kind == "numeric":
            # First numeric atom per eid wins (deterministic; <=1 expected in practice).
            numeric_claim_idx_by_eid.setdefault(eid, ci)
        else:
            qual_claim_idx_by_eid.setdefault(eid, []).append(ci)

    # finding_dedup member_indices are ROW indices into ``annotated`` -> resolve to evidence_id.
    eid_by_row_index = {
        i: str((row or {}).get("evidence_id") or "")
        for i, row in enumerate(annotated or [])
    }

    dedup = dedup_by_finding(annotated, gov_suffixes=gov_suffixes, domain=domain)

    # ── Union-Find over claim indices: union the numeric atoms that finding_dedup grouped together.
    parent = list(range(len(claims)))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra != rb:
            # Deterministic representative: the lower claim index, so the rebuilt id is stable
            # across runs (claims are in a deterministic extraction order).
            parent[max(ra, rb)] = min(ra, rb)

    # ── I-deepfix-001 P1#1 (MERGE-ONLY seed, FAITHFULNESS-CRITICAL): SEED the union-find from the
    #    EXISTING claim_graph cluster partition BEFORE applying any finding-dedup union. Pre-fix the
    #    parent[] started as pure singletons; if a finding-dedup group pulled only SOME members of an
    #    existing cluster [i, j] into a lower-index merge, only i was relabeled while j kept the old id,
    #    and the edge remap below then rewrote all old-id edges (incl. a contested/refuter edge) onto the
    #    new id — the residual old basket holding j SILENTLY lost its contested state (a contradiction
    #    misrouted; violates hard constraint 3 + MERGE-ONLY). Unioning each existing cluster's members
    #    first makes a whole cluster move ATOMICALLY: no existing cluster is ever split.
    for _existing_members in (getattr(graph, "clusters", None) or {}).values():
        _seed_idxs = [int(m) for m in (_existing_members or []) if 0 <= int(m) < len(claims)]
        for _m in _seed_idxs[1:]:
            _union(_seed_idxs[0], _m)

    for fcluster in (getattr(dedup, "clusters", None) or []):
        fkey = getattr(fcluster, "finding_key", None)
        is_qualitative_cluster = (
            isinstance(fkey, tuple) and bool(fkey) and str(fkey[0]) == "__qual__"
        )
        member_claim_indices: list[int] = []
        for row_index in (getattr(fcluster, "member_indices", None) or []):
            eid = eid_by_row_index.get(int(row_index), "")
            if is_qualitative_cluster:
                qual_indices = qual_claim_idx_by_eid.get(eid)
                # I-deepfix-001 P1#2 (qual representative disambiguation, FAITHFULNESS-CRITICAL):
                # a single annotated row can carry MORE THAN ONE qualitative atom
                # (qualitative_conflict_detector.py:493 emits multiple atoms per row). The FIRST atom
                # is NOT guaranteed to be the atom that made this row match the qualitative finding
                # group, so unioning qual_indices[0] could FALSE-MERGE two distinct within-row
                # assertions and inflate verified_support_origin_count from separately-verified but
                # DIFFERENT claims. Conservative (undercount-safe) choice: union ONLY rows that map to
                # EXACTLY ONE qualitative atom (unambiguous); SKIP a multi-atom row entirely rather
                # than guess. This can only UNDER-count corroboration, never false-merge different
                # claims.
                if qual_indices and len(qual_indices) == 1:
                    member_claim_indices.append(qual_indices[0])  # unambiguous one-atom row
            else:
                ci = numeric_claim_idx_by_eid.get(eid)
                if ci is not None:
                    member_claim_indices.append(ci)
        # Union all members of this finding cluster into one component (merge-only).
        for ci in member_claim_indices[1:]:
            _union(member_claim_indices[0], ci)

    # ── Relabel: every claim in a merged component takes the EXISTING claim_cluster_id of its
    #    component representative (a real ``clm_*`` id already on a member — never a new scheme, so
    #    the downstream join key format is unchanged). Components that were never unioned keep their
    #    own id verbatim (byte-identical for unmerged claims). old_id -> new_id for the edge remap.
    rep_id_by_root: dict[int, str] = {}
    for idx in range(len(claims)):
        root = _find(idx)
        if root not in rep_id_by_root:
            rep_id_by_root[root] = str(getattr(claims[root], "claim_cluster_id", "") or "")

    old_to_new: dict[str, str] = {}
    new_clusters: dict[str, list[int]] = {}
    for idx, claim in enumerate(claims):
        old_id = str(getattr(claim, "claim_cluster_id", "") or "")
        new_id = rep_id_by_root[_find(idx)]
        if old_id and old_id != new_id:
            old_to_new[old_id] = new_id
        # Relabel the claim in place is UNSAFE (shared object); we only rebuild the clusters dict and
        # the cluster_id_by_evidence binding from new_id, and _assemble_baskets reads members from the
        # clusters dict + the binding — never re-reads claim.claim_cluster_id for the basket id. But to
        # keep the basket's claim_cluster_id and the binding consistent we DO set it (these AtomicClaim
        # objects are this pass's own, freshly built by build_claim_graph this call — not the caller's).
        claim.claim_cluster_id = new_id
        new_clusters.setdefault(new_id, []).append(idx)

    if not old_to_new:
        # No merge happened (e.g. finding_dedup found nothing to group) -> the legacy grouping stands.
        _emit_basket_consume_marker(0, noop=True)
        return graph

    # ── Remap edges so a refuter reference still lands on the MERGED cluster id (never hide a
    #    contradiction). claim_cluster_ids that were not relabeled pass through unchanged.
    new_edges: list = []
    for edge in (getattr(graph, "edges", None) or []):
        ids = tuple(sorted({
            old_to_new.get(str(c), str(c))
            for c in (getattr(edge, "claim_cluster_ids", ()) or ())
            if str(c)
        }))
        new_edges.append(dataclasses.replace(edge, claim_cluster_ids=ids))

    _emit_basket_consume_marker(len(old_to_new), noop=False)
    return dataclasses.replace(
        graph,
        claims=claims,
        clusters=new_clusters,
        edges=new_edges,
        distinct_cluster_count=len(new_clusters),  # keep the count consistent with the merged partition
    )


def _assemble_baskets(
    graph: Any,
    weight_mass: list,
    annotated: list[dict],
    credibility_by_evidence: dict,
    *,
    verify_fn: Callable,
    max_inflight: int = _DEFAULT_PASS_MAX_INFLIGHT,
    deadline_monotonic: float | None = None,
) -> list:
    """Assemble one ClaimBasket per claim cluster (design §5/§6).

    Principle 2: ALL members of a cluster are kept (``supporting_members`` is the full
    group, never a representative). Principle 3: ``verified_support_origin_count`` is the
    count of DISTINCT origin clusters whose member passed ISOLATED per-member verification
    (NOT the raw passing-member count, and NOT ``weight_mass.independent_origin_count`` —
    that is the clustered, not-verified count, surfaced ONLY as the ADVISORY
    ``total_clustered_origin_count``). ``basket_verdict`` is a pure LABEL.

    I-arch-007 ITEM 1b (#1264): the per-member isolated verifies (the expensive entailment-judge
    calls) are gathered into a FLAT, deterministically-ordered task list, dispatched through a BOUNDED
    pool (``max_inflight``), and reassembled in the ORIGINAL ``sorted(clusters)`` → member order. The
    verdict each member receives is unchanged from the serial path — only wall-clock differs.
    """
    row_by_eid = {str(r.get("evidence_id", "")): r for r in (annotated or [])}
    wm_by_cluster = {
        str(getattr(w, "claim_cluster_id", "") or ""): w for w in (weight_mass or [])
    }

    # Refuter references (design §5): for each cluster, the OTHER cluster ids it is
    # joined to by a ContradictionEdge. REFERENCE only — never duplicated into the basket.
    refuters_by_cluster: dict[str, set] = {}
    for edge in (getattr(graph, "edges", None) or []):
        ids = [str(c) for c in (getattr(edge, "claim_cluster_ids", ()) or ()) if str(c)]
        uniq = set(ids)
        if len(uniq) == 1:
            # I-deepfix-001 P1#1 (keystone contested-edge, FAITHFULNESS-CRITICAL): a CONTRADICTION
            # edge (every ``graph.edges`` entry is a ContradictionEdge) whose two endpoints resolve to
            # the SAME cluster id collapses to a SELF-LOOP (e.g. ``('clm_a',)``). This happens either
            # natively (``_edge_cluster_pair`` returns a 1-element tuple when both contradicting rows
            # sit in ONE cluster) OR after ``_regroup_graph_by_finding_dedup`` merges the two contested
            # clusters into one. The ``other != cid`` loop below recorded NO refuter for such an edge,
            # so the basket fell through to full/partial/unverified and STOPPED rendering ``contested``
            # — a contradiction silently hidden by the merge (violates hard constraint 3). An
            # intra-basket contradiction is the STRONGEST contested signal and is NEVER dropped: record
            # the cluster as its OWN refuter so ``basket_verdict`` stays ``contested`` and every
            # downstream consumer that keys on ``refuter_cluster_ids`` (the disclosure contested-count,
            # the consensus-quantifier guard) stays consistent. Holds for numeric AND qualitative merges.
            (self_cid,) = tuple(uniq)
            refuters_by_cluster.setdefault(self_cid, set()).add(self_cid)
            continue
        for cid in ids:
            for other in ids:
                if other != cid:
                    refuters_by_cluster.setdefault(cid, set()).add(other)

    clusters = getattr(graph, "clusters", None) or {}
    claims = getattr(graph, "claims", None) or []

    # ── ITEM 1b step 1: build the per-member verify task list in the ORIGINAL deterministic order ──
    # (sorted(clusters) → member order). Each entry is (claim_text, member_row); empty clusters are
    # skipped exactly as the serial loop does, so the index alignment is identical to a serial pass.
    sorted_cluster_ids = [cid for cid in sorted(clusters) if [claims[i] for i in clusters[cid]]]
    verify_tasks: list[tuple[str, dict]] = []
    for cluster_id in sorted_cluster_ids:
        for claim in [claims[i] for i in clusters[cluster_id]]:
            eid = str(getattr(claim, "evidence_id", "") or "")
            row = row_by_eid.get(eid, {})
            verify_tasks.append((str(getattr(claim, "text", "") or ""), row))

    # ── ITEM 1b step 2: run the verifies (serial when max_inflight<=1; bounded-parallel otherwise) ──
    # Verdicts come back index-aligned with verify_tasks, so the reassembly below consumes them in the
    # SAME order the serial loop computed them — verdict-identical, only faster.
    verdicts = _run_member_verifies(
        verify_tasks, verify_fn=verify_fn, max_inflight=max_inflight,
        deadline_monotonic=deadline_monotonic,
    )
    _verdict_cursor = 0

    baskets: list[ClaimBasket] = []
    for cluster_id in sorted_cluster_ids:
        member_indices = clusters[cluster_id]
        member_claims = [claims[i] for i in member_indices]
        head = member_claims[0]
        cwm = wm_by_cluster.get(cluster_id)

        members: list[BasketMember] = []
        verified_origin_ids: set[str] = set()
        verified_any = False
        all_verified = True
        for claim in member_claims:
            eid = str(getattr(claim, "evidence_id", "") or "")
            row = row_by_eid.get(eid, {})
            ec = credibility_by_evidence.get(eid)
            origin_id = str(getattr(ec, "origin_cluster_id", "") or "") if ec else ""
            if not origin_id:
                # an unmapped member is its own independent origin (mirrors weight_mass)
                origin_id = f"origin::{eid}"
            span = _row_span_text(row)
            # ISSUE #1279 P1#2 (tightening): the member's ``direct_quote`` is the CLAIM-LOCAL span (the
            # claim's own ``text`` / extractor ``context_snippet``), NOT the full row. The full row would
            # make the downstream verified-compose acceptance region the WHOLE row, defeating the
            # cross-claim region gate (a sentence citing a DIFFERENT in-row claim's offsets would pass).
            # FAIL-CLOSED: when the claim-local span is unrecoverable (not a substring of the row), the
            # member gets an EMPTY direct_quote -> ``_member_global_span`` returns None -> the member
            # defines NO acceptance region and NO verbatim-fallback span (never the whole row).
            claim_local_span = _claim_local_span(str(getattr(claim, "text", "") or ""), span)
            # ISOLATED per-member verification (design §5 FIX-3): the claim's TEXT against
            # THIS member's own single span — never a union of basket spans. The verdict was
            # precomputed (serial or bounded-parallel) and is consumed here in the ORIGINAL order.
            # I-arch-010 FIX-2 Step 0: the precomputed value is now a (span_verdict, member_tier)
            # 2-tuple. span_verdict stays the BINARY gate for the strengthening count (only
            # SUPPORTS — i.e. genuine ENTAILMENT_VERIFIED — increments it); member_tier is the
            # additive seam stored on the member for the I-arch-011 keep-with-labels layer.
            verdict, member_tier, judge_unavailable = verdicts[_verdict_cursor]
            _verdict_cursor += 1
            # I-deepfix-001 COV-DECHROME-BASKETS (#1344): the per-member chrome flag, computed in the
            # SUPPORTS branch below and carried DURABLY onto the member so the downstream cross-source
            # (``depth_synthesis``) member selection can hold it out of the corroboration set BEFORE the
            # eligibility gate. Reset per member; stays False for a non-SUPPORTS member (only isolated-
            # SUPPORTS members flow to the cross-source synthesis, so no others need the flag).
            _span_is_chrome = False
            if verdict == "SUPPORTS":
                # I-deepfix-001 F1-STRUCTURAL (#1344): screen the member's claim-local span AND the
                # cluster claim_text through the shared render-seam predicate before crediting the
                # strengthening count. A chrome/unrenderable span is page furniture
                # (cookie/byline/foreign-masthead/paywall/DOI-error) or a dead-fetch shell, never a
                # genuine corroborator -- exclude it from verified_origin_ids (the member is STILL
                # appended below, never deleted; the source stays in the pool + disclosure).
                # FAITHFULNESS-ADJACENT (consolidation layer): this only REMOVES a chrome span from a
                # corroboration COUNT -- it strengthens, never relaxes a gate, never inflates breadth,
                # never hard-drops a source. FLAG for Codex extra-care: is_render_chrome_or_unrenderable
                # folds the ``unrenderable``/truncation arm, so a TRUNCATED-but-real span (e.g. a span
                # cut mid-word) is also demoted from the count -- such a span would not render as
                # verified support anyway, but this is the §-1.3-sensitive edge.
                if _basket_chrome_screen_enabled():
                    try:
                        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
                            is_render_chrome_or_unrenderable as _is_render_chrome,
                        )
                        # I-deepfix-002 (#1363, Codex P2 precision): screen ONLY THIS MEMBER's
                        # span, not the cluster ``head.text``. A chrome/truncated basket HEAD must
                        # not demote an otherwise-clean member (each member is judged on its own
                        # span); this removes the over-demotion risk Codex flagged while leaving
                        # the real-corpus outcome unchanged.
                        _span_is_chrome = bool(_is_render_chrome(claim_local_span))
                    except Exception as _screen_exc:  # fail-OPEN: never crash the pass on a screen fault
                        import logging as _logging  # noqa: PLC0415
                        _logging.getLogger(__name__).warning(
                            "[credibility-pass] F1-STRUCTURAL basket chrome screen unavailable "
                            "(%s) -- failing OPEN, crediting the member as before", _screen_exc,
                        )
                        _span_is_chrome = False
                if _span_is_chrome:
                    # chrome/unrenderable span: excluded from the verified-origin COUNT; the member is
                    # still appended below (kept). Not "all verified" since this span is not genuine
                    # renderable verified support (basket_verdict is a display LABEL, never a gate).
                    all_verified = False
                    # I-deepfix-001 COV-DECHROME-BASKETS (#1344): LOUD per-basket disclosure — the
                    # coverage forensic flagged these chrome exclusions were SILENT, forcing manual
                    # reconstruction. The member is KEPT in the basket (§-1.3 no-drop); only its chrome
                    # span is held out of the corroboration count + the downstream cross-source set.
                    import logging as _logging  # noqa: PLC0415
                    _logging.getLogger(__name__).info(
                        "[credibility-pass] basket %s: SUPPORTS member held out of corroboration: "
                        "chrome span (eid=%s)", cluster_id, eid,
                    )
                else:
                    verified_any = True
                    verified_origin_ids.add(origin_id)
            else:
                all_verified = False
            members.append(BasketMember(
                evidence_id=eid,
                source_url=str(getattr(claim, "source_url", "") or row.get("source_url", "")),
                source_tier=str(getattr(claim, "source_tier", "") or row.get("tier", "")),
                origin_cluster_id=origin_id,
                credibility_weight=(getattr(ec, "credibility_weight", None) if ec else None),
                authority_score=_clamp01(float(row.get("authority_score", 0.0) or 0.0)),
                # ISSUE #1279 P1#2: the member's span + direct_quote are the CLAIM-LOCAL span (not the
                # full row), so the verified-compose acceptance region is claim-specific. Empty when the
                # claim-local span is unrecoverable (fail-closed: no region, no fallback span).
                span=(0, len(claim_local_span)),
                direct_quote=claim_local_span,
                span_verdict=verdict,
                member_tier=member_tier,
                # I-deepfix-001 Wave-3 P1b (#1344): the durable judge-outage signal for this member
                # (True only when DETERMINISTIC_ONLY BECAUSE the judge errored/timed out this run).
                entailment_judge_unavailable=judge_unavailable,
                # I-deepfix-001 COV-DECHROME-BASKETS (#1344): the durable chrome-span flag (True iff
                # this member's claim-local span is page furniture / a dead-fetch shell). The downstream
                # cross-source member selection reads it to hold the member out of the corroboration set
                # BEFORE eligibility. Never rendered, never a faithfulness verdict; the member is KEPT.
                span_is_chrome=_span_is_chrome,
            ))

        refuter_ids = tuple(sorted(refuters_by_cluster.get(cluster_id, set())))
        # verified count = DISTINCT verified origin clusters (the only strengthening count).
        verified_support_origin_count = len(verified_origin_ids)
        # advisory clustered count (NOT verified) — sourced from weight_mass, never reused
        # as the strengthening count.
        total_clustered_origin_count = int(
            getattr(cwm, "independent_origin_count", 0) or 0
        ) if cwm is not None else 0

        # basket_verdict is a pure LABEL (design §6): derived from verified counts +
        # refuter references. It NEVER feeds is_verified / strict_verify — a downstream
        # consumer reads it for display, it can never resurrect a dropped sentence.
        if refuter_ids:
            basket_verdict = BASKET_VERDICT_CONTESTED
        elif not verified_any:
            basket_verdict = BASKET_VERDICT_UNVERIFIED
        elif all_verified:
            basket_verdict = BASKET_VERDICT_FULL
        else:
            basket_verdict = BASKET_VERDICT_PARTIAL

        baskets.append(ClaimBasket(
            claim_cluster_id=cluster_id,
            claim_text=str(getattr(head, "text", "") or ""),
            subject=str(getattr(head, "subject", "") or ""),
            predicate=str(getattr(head, "predicate", "") or ""),
            supporting_members=members,
            refuter_cluster_ids=refuter_ids,
            weight_mass=float(getattr(cwm, "weight_mass", 0.0) or 0.0) if cwm is not None else 0.0,
            total_clustered_origin_count=total_clustered_origin_count,
            verified_support_origin_count=verified_support_origin_count,
            basket_verdict=basket_verdict,
        ))
    return baskets


def run_credibility_analysis(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None = None,
    judge: Callable | None = None,
    now_year: int | None = None,
    max_inflight: int | None = None,
    deadline_monotonic: float | None = None,
) -> CredibilityAnalysis:
    """Run the P4→P3→P2→P5→P6 chain over the EFFECTIVE evidence pool.

    Fail-loud on a MISSING evidence_id, a P4 independence-annotation gap, or a wired-module crash (real
    integrity holes). The two INFRA conditions that used to abort the WHOLE report no longer hold it
    (I-arch-005 B12-P1, operator-locked 2026-06-14 "nothing shall hold the report"): a PER-SOURCE P2
    ``judge_error`` and a MISSING production judge (``judge=None``) each LABEL the affected sources
    ``credibility_unscored`` (priors-only weight — a real, honest deterministic weight, never fabricated)
    and the rest keep scoring, so the report ships with the disclosed gap. ``rows`` MUST already be the
    generator's effective pool (post-M-52, post-dissent); ``gov_suffixes`` is the PSL gov-suffix tuple the
    rest of the pipeline uses (dependency-injected, no global). ``judge`` is the production credibility
    judge (injected); None ⇒ the whole pool ships priors-only + LABELED ``credibility_unscored`` (a
    disclosed gap surfaced LOUD per LAW II), NOT a silent false-green and NOT a hold.

    ``max_inflight`` (I-arch-007 ITEM 1b, #1264) bounds the per-member isolated-verify concurrency in
    ``_assemble_baskets`` (LAW VI). ``None`` (the default) reads the ``PG_CREDIBILITY_PASS_MAX_INFLIGHT``
    env knob, which itself defaults to 1 = the byte-identical SERIAL path. The bound changes WALL-CLOCK
    only — the per-member verdicts and the resulting baskets are identical to the serial pass.

    ``deadline_monotonic`` (I-deepfix-001 BANK-BEFORE-WALL): an OPTIONAL ``time.monotonic()`` soft
    deadline the caller sets INSIDE its own hard wall. The chain budgets it across the two LLM-bound
    phases (P2 source scoring / per-member basket verifies) so the pass RETURNS a real
    ``CredibilityAnalysis`` — with every verdict computed so far BANKED and the rest disclosed
    verification-unavailable — BEFORE the caller's all-or-nothing wall can discard the whole analysis.
    ``None`` (every legacy caller) => byte-identical unbounded behavior.
    """
    if max_inflight is None:
        max_inflight = _pass_max_inflight()
    if not rows:
        return CredibilityAnalysis({}, {}, [], [], [])
    if judge is None:
        # I-arch-005 B12-P1 (#1257, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"): a missing
        # production credibility judge is an INFRA/config condition (the pass is ADVISORY — strict_verify
        # + the 4-role D8 release policy stay the ONLY binding gates), NOT a faithfulness finding. It must
        # NOT abort the whole report. The chain runs priors-only (every source carries its real
        # deterministic authority weight, never fabricated) and LABELS every source credibility_unscored —
        # a disclosed gap. LOUD log (LAW II: no silent downgrade) so the operator sees it.
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] no production credibility judge wired (judge=None); running priors-only "
            "and LABELING all %d source(s) credibility_unscored (disclosed gap) — the report ships with "
            "the gap, never aborts (operator-locked 'nothing shall hold the report').",
            len(rows),
        )
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    try:
        return _run_chain(
            research_question, rows,
            gov_suffixes=gov_suffixes, domain=domain, judge=judge, now_year=now_year,
            max_inflight=max_inflight, deadline_monotonic=deadline_monotonic,
        )
    except (CredibilityPassError, BudgetExceededError):
        # CredibilityPassError = fail-loud abort; BudgetExceededError (Codex #012a P1-2) must reach the
        # sweep's budget-abort path cleanly, NOT be masked as a generic credibility-pass error.
        raise
    except Exception as exc:  # ANY OTHER wired-module failure → fail-loud abort, never a silent false-green
        raise CredibilityPassError(
            f"abort_credibility_pass_error: a wired credibility module failed "
            f"({type(exc).__name__}): {exc}"
        ) from exc


def _run_chain(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None,
    judge: Callable | None,
    now_year: int | None,
    max_inflight: int = _DEFAULT_PASS_MAX_INFLIGHT,
    deadline_monotonic: float | None = None,
) -> CredibilityAnalysis:
    """The P4→P3→P2→P5→P6 chain body; wrapped by run_credibility_analysis for the fail-loud posture."""
    # ── I-deepfix-001 B9(a): join a deterministic tier-authority prior onto any row missing an
    # authority_score, on COPIED rows, BEFORE collapse so independence_collapse's undated-canonical
    # selection AND weight_mass.cluster_mass read the SAME non-zero authority. A row that already
    # carries a real computed authority_score is preserved verbatim. WEIGHT, never a DROP (§-1.3); the
    # faithfulness engine is untouched. Then the fail-loud canary: an all-zero authority_score across
    # rows (with the redesign ON) is a wiring break, surfaced LOUD (raise only on opt-in). ──
    rows = _join_tier_authority_prior(rows)
    _emit_zero_authority_canary(rows)
    # ── P4: independent-origin collapse → per-row assignment, on COPIED rows (never mutate the caller) ──
    collapse = collapse_independent_origins(rows, gov_suffixes=gov_suffixes)
    if len(collapse.assignments) != len(rows):
        raise CredibilityPassError(
            "abort_independence_annotation_gap: P4 returned "
            f"{len(collapse.assignments)} assignments for {len(rows)} rows"
        )
    annotated: list[dict] = []
    origin_by_evidence: dict = {}
    for i, row in enumerate(rows):
        eid = _require_evidence_id(row, i)
        assignment = collapse.assignments[i]
        new_row = dict(row)  # COPY
        new_row["origin_cluster_id"] = assignment.origin_cluster_id
        new_row["is_canonical_origin"] = assignment.is_canonical_origin
        annotated.append(new_row)
        origin_by_evidence[eid] = assignment.origin_cluster_id

    # ── P3: supersession multiplier per source ──
    supers_by_evidence = {
        _require_evidence_id(row, i): supersession_adjustment(row, now_year=now_year)
        for i, row in enumerate(annotated)
    }

    # ── P2: credibility judgments — judge_error / judge=None LABEL the source, never abort ──
    # I-arch-005 B12 (#1257, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"): the pass
    # is ADVISORY (its own docstring). The two INFRA conditions must NOT abort the WHOLE report —
    # each LABELS the affected source(s) ``credibility_unscored`` (a disclosed gap) and KEEPS the
    # rest scoring with real weights:
    #   * a PER-SOURCE judge_error — ``score_source_credibility`` already isolates the error to ONE
    #     row and falls back to that source's DETERMINISTIC priors (a real, honest weight, never
    #     fabricated), flagging it ``judge_error=True``;
    #   * judge=None (no production judge wired) — ``score_source_credibility(judge=None)`` returns
    #     priors-only for EVERY row but with ``judge_error=False`` (it is not a per-source error, it
    #     is a global infra condition). So the ``errored_ids`` set is EMPTY in that case; we OR in
    #     ``judge_missing`` below so EVERY source is correctly labeled ``credibility_unscored`` (NOT a
    #     silent priors-only false-green — that EXACT trap is why the explicit OR exists).
    # The credibility WEIGHT math is unchanged — a labeled row simply carries its priors-only weight +
    # the disclosed label. (The genuine provenance hole — a CITED evidence_id with NO credibility row
    # at all — is still fail-loud, caught downstream by ``apply_disclosure_to_svs``'s coverage
    # assertion; that is a real coverage gap, NOT a recoverable infra condition.)
    judge_missing = judge is None
    # I-deepfix-001 BANK-BEFORE-WALL: budget phase A (P2 source scoring) to a FRACTION of the
    # remaining soft-deadline budget so phase B (the per-member basket verifies that feed the
    # SUPPORTS baskets / breadth enrichment) is GUARANTEED a share. score_source_credibility takes
    # min(env pool wall, this budget) and already partial-banks at its wall (drain + priors-fill,
    # never a discard). None deadline (legacy) => None budget => env-only, byte-identical.
    _phase_a_wall_s: float | None = None
    if deadline_monotonic is not None:
        _remaining_s = deadline_monotonic - time.monotonic()
        _phase_a_wall_s = max(_MIN_PHASE_BUDGET_S, _remaining_s * _phase_a_budget_frac())
    judgments = score_source_credibility(
        research_question, annotated, domain=domain, judge=judge,
        pool_wall_s=_phase_a_wall_s,
    )
    errored_ids = {j.evidence_id for j in judgments if getattr(j, "judge_error", False)}
    if errored_ids:
        example = sorted(errored_ids)[:5]
        # LOUD log (LAW II: no silent downgrade) — the run still ships, but the operator sees it.
        import logging as _logging  # noqa: PLC0415
        _logging.getLogger(__name__).warning(
            "[credibility-pass] credibility judge errored for %d/%d source(s) (e.g. %s); "
            "LABELING them credibility_unscored (priors-only weight) and continuing to score the "
            "rest — the report ships with the disclosed gap (never aborts the basket).",
            len(errored_ids), len(judgments), example,
        )

    # ── POST-P3 credibility = P2 weight × supersession multiplier (certainty carried, not folded away) ──
    credibility_by_evidence: dict = {}
    for row, judgment in zip(annotated, judgments):
        eid = judgment.evidence_id
        supersession = supers_by_evidence.get(eid)
        multiplier = supersession.multiplier if supersession else 1.0
        credibility_by_evidence[eid] = EvidenceCredibility(
            evidence_id=eid,
            credibility_weight=_clamp01(judgment.credibility_weight * multiplier),
            reliability_score=judgment.reliability_score,
            relevance_score=judgment.relevance_score,
            origin_cluster_id=origin_by_evidence.get(eid, ""),
            is_canonical_origin=bool(row.get("is_canonical_origin")),
            certainty_downgrade=bool(supersession.certainty_downgrade) if supersession else False,
            soft_warning=(supersession.soft_warning if supersession else None),
            # OR in ``judge_missing``: with judge=None EVERY source is priors-only with
            # judge_error=False, so ``errored_ids`` is empty — without the OR every source would ship
            # credibility_unscored=False (a silent priors-only false-green, the EXACT trap B12-P1 fixes).
            credibility_unscored=(eid in errored_ids) or judge_missing,
        )

    # POST-P3 judgments for downstream — P6 disclosure must use the post-P3 credibility, not raw P2.
    adjusted_judgments = [
        dataclasses.replace(j, credibility_weight=credibility_by_evidence[j.evidence_id].credibility_weight)
        for j in judgments
    ]

    # ── P5: claim graph (atomic claims + contradiction edges) ──
    graph = build_claim_graph(annotated, domain=domain)

    # ── I-arch-008 HOP-A KEYSTONE (#1265): consume finding_dedup's already-computed grouping ──
    # DEFAULT OFF => byte-identical (the legacy claim_graph fragmentation stands). ON => MERGE the
    # claim partition using finding_dedup membership so same-finding members share ONE basket, BEFORE
    # weight-mass aggregation so the mass keys agree with the merged ids. Grouping + relabel + edge
    # remap ONLY — the claims/spans the isolated verify reads are untouched, so no member newly passes.
    if basket_consume_finding_dedup_enabled():
        graph = _regroup_graph_by_finding_dedup(
            graph, annotated, gov_suffixes=gov_suffixes, domain=domain,
        )

    # ── P6: origin-cluster weight-mass (mass = authority(canonical) ONLY; credibility disclosed) ──
    weight_mass = aggregate_weight_mass(graph.claims, annotated, adjusted_judgments)

    # ── I-arch-002 [8] — assemble per-claim baskets with ISOLATED per-member verification.
    # The verifier is the PRODUCTION single-sentence callable, lazy-imported here so this
    # module's import graph stays decoupled from the big provenance module (mirrors the
    # local imports at run_credibility_analysis / apply_disclosure_to_svs). It is used
    # ADVISORY only — strict_verify itself is never re-run as a gate.
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        verify_sentence_provenance,
    )
    # I-arch-011 (#1268): the per-member basket verify runs under entailment-ENFORCE (the
    # PG_STRICT_VERIFY_ENTAILMENT default). It MUST stay enforce: ``span_verdict==SUPPORTS`` is
    # consumed at render WITHOUT re-verification — both as inline corroborator citations
    # (provenance_generator.py B6/B8 ``_verified_corroborators_for_tokens``) and as the breadth
    # enrichment section — so an entailment-OFF advisory verdict would ship un-entailed corroborator
    # citations (the rejected F2b; Codex P0-1). The serial-entailment HANG is avoided NOT by
    # disabling the judge but by the architecture's bounded parallelism + wall: ``max_inflight``
    # (PG_CREDIBILITY_PASS_MAX_INFLIGHT, slate=16) runs the verify 16-way over a PER-THREAD judge
    # client (I-arch-007 ITEM 2a, entailment_judge.py threading.local — deadlock-safe), and the
    # caller's PG_CREDIBILITY_PASS_WALL_S=3000 wall bounds the whole pass. Faithfulness STRENGTHENED.
    baskets = _assemble_baskets(
        graph, weight_mass, annotated, credibility_by_evidence,
        verify_fn=verify_sentence_provenance,
        max_inflight=max_inflight,
        # I-deepfix-001 BANK-BEFORE-WALL: phase B gets the WHOLE remaining budget (phase A was
        # capped to its fraction above). At expiry the verified prefix is BANKED and the rest is
        # sentinel-filled (disclosed, UNDERCOUNT-only) — the analysis is returned, never discarded.
        deadline_monotonic=deadline_monotonic,
    )

    # ── F3-3b (I-deepfix-001 #1369): corroboration entailment-judge AVAILABILITY guard ──
    # Count the members whose entailment judge was DURABLY UNAVAILABLE this run (the outage
    # signal, not a clean NEUTRAL/CONTRADICTED), SURFACE it into the Methods disclosure (iii),
    # and run the FAIL-LOUD canary (iv) — which always LOUD-warns and HARD-RAISES only when the
    # ENV-DRIVEN ceiling is set and exceeded. This runs BEFORE the return so a judge-outage storm
    # that guts corroboration FAILS the run rather than shipping a deficient CredibilityAnalysis.
    _judge_unavailable, _basket_members = count_judge_unavailable_members(baskets)
    _methods_disclosure = build_judge_availability_methods_disclosure(
        _judge_unavailable, _basket_members,
        # Name the ACTUAL binding judge (PG_ENTAILMENT_MODEL) that counted the corroboration —
        # never the recommended target (that would be a wrong methods claim, LAW II). kimi-k2.6 is
        # surfaced SEPARATELY inside the builder as the recommended higher-provider mitigation.
        judge_model=active_entailment_judge_model(),
        recommended_model=corroboration_judge_model(),
    )
    _enforce_judge_availability_canary(_judge_unavailable, _basket_members)

    # ── sentence -> claim_cluster_id binding (design §6): evidence_id -> the cluster
    #    id(s) its atomic claim(s) belong to. The resolve sites today carry only cited
    #    tokens (each an evidence_id), so this lets the render layer (P5.x) map a cited
    #    token to the basket whose verified count it should surface. Reference data only.
    cluster_id_by_evidence: dict[str, list[str]] = {}
    for claim in (graph.claims or []):
        eid = str(getattr(claim, "evidence_id", "") or "")
        ccid = str(getattr(claim, "claim_cluster_id", "") or "")
        if not eid or not ccid:
            continue
        bucket = cluster_id_by_evidence.setdefault(eid, [])
        if ccid not in bucket:
            bucket.append(ccid)

    return CredibilityAnalysis(
        credibility_by_evidence=credibility_by_evidence,
        origin_by_evidence=origin_by_evidence,
        claims=graph.claims,
        edges=graph.edges,
        weight_mass=weight_mass,
        baskets=baskets,
        cluster_id_by_evidence=cluster_id_by_evidence,
        entailment_judge_unavailable_member_count=_judge_unavailable,
        basket_member_count=_basket_members,
        methods_disclosure=_methods_disclosure,
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-cred-008b (#1162) — the SHARED per-claim disclosure populate+carrier+coverage
# helper, called at ALL FOUR cited-prose resolve sites (legacy _run_section,
# fact-dedup re-resolve, V30 contract runner, quantified-analysis). ONE copy of
# this faithfulness-critical logic so it cannot drift across the four sites.
# ─────────────────────────────────────────────────────────────────────────────

def _cited_evidence_ids_for_coverage(sv: Any) -> list[str]:
    """The cited evidence_ids on a RESOLVER-EMITTED SentenceVerification (its tokens)."""
    out: list[str] = []
    for token in (getattr(sv, "tokens", None) or []):
        eid = str(getattr(token, "evidence_id", "") or "")
        if eid:
            out.append(eid)
    return out


def apply_disclosure_to_svs(svs: list, analysis: "CredibilityAnalysis") -> list:
    """Populate the four advisory disclosure fields on each resolver-emitted SV, then carry the
    P3 certainty downgrade — ONE shared implementation for all four cited-prose resolve sites.

    Steps (ADVISORY only — never re-runs strict_verify, never flips ``is_verified``):
      1. COVERAGE ASSERTION (fail-LOUD): every cited token's evidence_id on these SVs MUST have
         credibility + origin coverage in ``analysis`` (both maps are co-built per-row in
         ``_run_chain``). A cited token with none ⇒ ``CredibilityPassError(abort_credibility_coverage_gap)``.
         Scoped to RESOLVER-EMITTED cited SVs (the SVs handed to ``resolve_provenance_to_citations``),
         NOT every ``[N]`` marker in deterministic tables/timelines — those never become SVs at the
         resolve sites, so they are excluded for free (Codex I-cred-012 iter-5 P2-3).
      2. POPULATE: the EvidenceCredibility→float adaptation
         (``{eid: ec.credibility_weight}``) feeds ``populate_disclosure`` (which expects FLOAT weights,
         not the EvidenceCredibility object), populating span_verdict / credibility_weight /
         independent_origin_count / certainty_label.
      3. P3 CERTAINTY CARRIER (Codex I-cred-012 iter-5 P2): ``populate_disclosure`` derives certainty
         from credibility/origins ONLY; it does NOT see the P3 supersession downgrade. So for each
         populated SV whose cited evidence carries ``certainty_downgrade=True``, cap its certainty_label
         (never above "moderate") and surface the source's ``soft_warning`` on the SV's ``soft_warnings``.

    Inputs are NOT mutated; ``populate_disclosure`` returns NEW SVs via ``dataclasses.replace``.
    """
    from src.polaris_graph.synthesis.disclosure_population import populate_disclosure

    cred_by_ev = analysis.credibility_by_evidence or {}
    origin_by_ev = analysis.origin_by_evidence or {}

    # ── Step 1: coverage assertion (fail-loud BEFORE populate) ──
    for sv in (svs or []):
        for eid in _cited_evidence_ids_for_coverage(sv):
            if eid not in cred_by_ev or eid not in origin_by_ev:
                raise CredibilityPassError(
                    "abort_credibility_coverage_gap: a cited evidence_id "
                    f"({eid!r}) emitted by the resolver has no credibility/origin coverage "
                    "in the credibility analysis; refusing to disclose a claim whose source "
                    "the activated pass never scored (fail-loud, never a false-green advisory)"
                )

    # ── Step 2: EvidenceCredibility → FLOAT adaptation, then populate ──
    cred_floats = {
        eid: ec.credibility_weight for eid, ec in cred_by_ev.items()
    }
    # I-arch-002 [10] / design §5 FIX-4 (Reading A) — Codex Slice-B P1: thread the
    # per-claim baskets + the evidence_id->claim_cluster_id binding (both built by
    # _run_chain on this CredibilityAnalysis) into populate_disclosure so the
    # OVERWRITE of independent_origin_count -> verified_support_origin_count actually
    # reaches the operator-visible claim_disclosure.json emit
    # (run_honest_sweep_r3.py:353 / quantified_analysis.py:539 both read this field
    # off kept_sentences_pre_resolve). Pre-fix apply_disclosure_to_svs omitted these,
    # so the clustered (not-verified) count still leaked to the JSON. OFF byte-identity
    # is structural: this whole function only runs when credibility_analysis is not
    # None (itself gated on PG_SWEEP_CREDIBILITY_REDESIGN at every call site); when the
    # flag is OFF baskets is empty / the binding is empty, so populate_disclosure's
    # _surfaced_verified_count returns None and the legacy clustered count is preserved.
    populated = populate_disclosure(
        svs, cred_floats, origin_by_ev,
        baskets=getattr(analysis, "baskets", None),
        cluster_id_by_evidence=getattr(analysis, "cluster_id_by_evidence", None),
    )

    # ── Step 3: P3 certainty carrier (downgrade + soft_warning surface) ──
    out: list = []
    for sv in populated:
        downgrade = False
        warnings: list[str] = []
        for eid in _cited_evidence_ids_for_coverage(sv):
            ec = cred_by_ev.get(eid)
            if ec is None:
                continue
            if bool(getattr(ec, "certainty_downgrade", False)):
                downgrade = True
                warn = getattr(ec, "soft_warning", None)
                if warn:
                    warnings.append(str(warn))
        if not downgrade:
            out.append(sv)
            continue
        # Cap certainty at "moderate" (never "high") when any cited source was P3-downgraded.
        new_label = sv.certainty_label
        if new_label == "high":
            new_label = "moderate"
        existing_warnings = list(getattr(sv, "soft_warnings", None) or [])
        for w in warnings:
            if w not in existing_warnings:
                existing_warnings.append(w)
        out.append(dataclasses.replace(
            sv,
            certainty_label=new_label,
            soft_warnings=existing_warnings,
        ))
    return out
