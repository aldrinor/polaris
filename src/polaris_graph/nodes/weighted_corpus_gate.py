"""I-cred-006b (#1170) — weighted-corpus gate: REPLACE the tier-COUNT/material-deviation
corpus REFUSAL with PROCEED + a credibility-weighted disclosure (operator directive 2026-06-08,
repeat-flagged + FURIOUS: "we shall NOT have gate here, we shall WEIGHT the source").

THE PROBLEM (drb_72, #1100): the dry-run gathered 151 sources (throttle fixed) but the
corpus_approval gate aborted ``abort_corpus_approval_denied`` because ~50% were tier-4 on an
ECONOMICS question where T4 working papers (NBER / Acemoglu) are legitimate primary sources. That
is a DOMAIN-BLIND tier-COUNT refusal — the §-1.1-banned metadata proxy (counting source-types
verifies no individual claim). The corpus_adequacy gate's ``max_t5_plus_t6_fraction`` is the same
class of proxy.

THE FIX (this module): when ``PG_SWEEP_WEIGHTED_CORPUS_GATE`` is ON, the two corpus-level REFUSAL
branches in ``run_one_query`` are replaced by PROCEED — and this module builds the deterministic,
DOMAIN-AWARE credibility-weighting disclosure that is attached to the run (``corpus_credibility_
disclosure.json`` + a manifest field). Lower-tier sources are not refused; they are DISCLOSED as
lower-credibility and weighted by the deterministic ``authority_score`` already computed per source.

FAITHFULNESS POSTURE (binding — see the issue's faithfulness argument):
  * The per-claim binding gates are UNTOUCHED and remain the ONLY faithfulness floor:
    ``strict_verify`` (generator/provenance_generator.py — every sentence must match its cited
    [start:end] span: evidence-id in pool, span bounds valid, every decimal present, >=2 content-word
    overlap) drops any unsupported sentence REGARDLESS of that source's tier; the 4-role D8 release
    decision is per-claim. Removing the corpus-level tier-count proxy changes WHICH corpora reach
    generation, NOT whether any individual claim is verified.
  * The legitimate corpus-ZERO floor stays: a corpus with no usable sources cannot synthesize and
    still aborts (``abort_no_sources`` upstream, and ``has_usable_corpus`` here as a defense-in-depth
    check the caller asserts before proceeding). This is a real floor, not a tier proxy.
  * PURE + OFFLINE: no network, no LLM/judge, no spend, no row mutation. The per-source weight is the
    deterministic ``authority_score`` POLARIS already computed (the credibility-judge LLM weighting is
    the SEPARATE downstream ``PG_SWEEP_CREDIBILITY_REDESIGN`` machinery; this gate never invokes it).
  * DEFAULT-OFF byte-identical: with the flag unset/falsey the caller never calls this module and the
    two REFUSAL branches fire exactly as today (LAW VI env-overridable, no magic numbers).

This module owns NO control flow — it only (a) reads the flag and (b) builds the disclosure object.
The caller (``run_one_query``) decides to proceed-vs-refuse based on ``weighted_corpus_gate_enabled()``.
"""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── flag (default OFF — matches the other PG_SWEEP_* capability flags) ────────
_FLAG = "PG_SWEEP_WEIGHTED_CORPUS_GATE"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})

# Per-tier nominal credibility prior, used ONLY for the human-readable disclosure label when a source
# has no deterministic ``authority_score`` (so the disclosure is never blank). It is NOT a gate and NOT
# a faithfulness signal — strict_verify decides per-claim support, not this number. T1 (peer-reviewed
# primary) highest; T7 (stub/unknown) lowest. LAW VI: the whole map is env-overridable as a fallback.
_DEFAULT_TIER_CREDIBILITY_PRIOR: dict[str, float] = {
    "T1": 0.95, "T2": 0.85, "T3": 0.75, "T4": 0.60,
    "T5": 0.40, "T6": 0.30, "T7": 0.15, "UNKNOWN": 0.20,
}


def weighted_corpus_gate_enabled() -> bool:
    """True unless ``PG_SWEEP_WEIGHTED_CORPUS_GATE`` is unset/falsey (default OFF => byte-identical).

    When OFF the caller never calls this module's disclosure builder and the tier-count /
    material-deviation REFUSAL branches in ``run_one_query`` fire exactly as today.
    """
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


def _tier_prior(tier: str) -> float:
    """The nominal per-tier credibility prior (disclosure label only; not a gate)."""
    return _DEFAULT_TIER_CREDIBILITY_PRIOR.get(str(tier or "").strip().upper(), 0.20)


def _coerce_authority(value: Any) -> float | None:
    """Coerce a source's ``authority_score`` to a finite [0,1] float; None when absent/non-numeric."""
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    if x != x or x in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def _compute_authority_score_for_source(source: Any) -> "tuple[float | None, bool]":
    """I-arch-011 B11: deterministically COMPUTE a source's domain-aware ``authority_score`` from its
    surface signals (url + title) when no pre-computed score is available on the object or the join map.

    I-beatboth-010 (#1288) FIX-B: returns ``(authority_score, is_low_confidence)``. ``is_low_confidence``
    is True when ``score_source_authority`` reports ``AuthorityConfidence.LOW`` — the url+title-only path
    with thin OpenAlex coverage, where Signal A (scholarly) is 0.0 and Signal B (institutional) is the
    neutral 0.40, so the blended score is a flat, non-discriminating ~0.39 for ~93% of sources. The
    caller then prefers the DISCRIMINATING per-tier prior for the disclosed weight (WEIGHT-strengthening,
    no drop). A genuinely high/medium-confidence computed score is still used as authority_score.

    This is the documented-primary weighting path: it reuses the SAME deterministic, domain-aware
    ``score_source_authority`` the rest of the pipeline already uses (e.g. plan_sufficiency_gate's
    ``_enrich_authority_if_missing``), so the disclosure weight is the real authority signal, not the
    flat per-tier prior. PURE + OFFLINE: no network, no LLM/judge, no spend, and — unlike
    ``_enrich_authority_if_missing`` — NO row/object mutation (this module promises "no row mutation"),
    so the score is computed and returned locally only.

    Lazy import keeps the module's "no authority-package coupling at import time" posture. Returns None
    on any failure (missing url, import error) so the caller falls back to the per-tier prior — the
    disclosure is never blank, and a compute failure is a graceful WEIGHT fallback, never a drop.
    """
    url = str(getattr(source, "url", "") or "")
    if not url:
        return None, True
    try:
        from src.polaris_graph.authority.authority_model import (
            AuthorityConfidence,
            score_source_authority,
        )
        from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

        title = str(getattr(source, "title", "") or "")
        result = score_source_authority(ClassificationSignals(url=url, title=title))
        is_low = result.authority_confidence == AuthorityConfidence.LOW
        return float(result.authority_score), is_low
    except Exception:
        # Graceful WEIGHT fallback to the per-tier prior; never a drop, never a
        # raise. FAIL-LOUD via the log (not silent) so a regression that would
        # silently collapse EVERY source back to tier_prior — re-introducing B11
        # with no signal — is visible in the run log per LAW II / §9.4.
        logger.warning(
            "weighted_corpus_gate: deterministic authority_score recompute failed "
            "for url=%r; falling back to the per-tier credibility prior for this "
            "source's disclosure weight.",
            url,
            exc_info=True,
        )
        return None, True


@dataclass
class SourceCredibilityRow:
    """One source's DISCLOSED credibility weight (deterministic — authority_score, tier-prior fallback).

    ``credibility_weight`` is the deterministic ``authority_score`` when present, else the per-tier
    nominal prior (so the disclosure is never blank). ``weight_basis`` records which was used, so the
    disclosure is honest about provenance. This is a DISCLOSURE field, never a keep/drop verdict.
    """

    url: str
    tier: str
    domain: str
    credibility_weight: float
    weight_basis: str   # "authority_score" | "tier_prior"


@dataclass
class CorpusCredibilityDisclosure:
    """The corpus-level credibility-weighting disclosure attached when the weighted-corpus gate is ON.

    Replaces the tier-COUNT/material-deviation REFUSAL: the corpus is ACCEPTED and its credibility is
    DISCLOSED (weighted, domain-aware), not refused on source-type mix. ADVISORY — the binding
    per-claim gates (strict_verify + 4-role D8) are untouched.
    """

    gate: str                       # the flag name, for audit provenance
    domain: str
    research_question: str
    total_sources: int
    tier_counts: dict[str, int]
    tier_fractions: dict[str, float]
    had_material_deviation: bool    # what the OLD gate WOULD have refused on (disclosed, not acted on)
    weighted_credibility_mean: float  # source-count-weighted mean of per-source credibility (disclosure)
    per_source: list[SourceCredibilityRow] = field(default_factory=list)
    disclosure_note: str = ""
    # I-deepfix-001 D5 (#1344): the honest machine-readable credibility-TIERING batch status
    # carried from live_retriever (classify_sources_llm_tiering's TieringBatchResult.tiering_status:
    # {tiering_mode, llm_success_count, rules_floor_count, fallback_count, error_count, total}).
    # Plumbed onto this durable disclosure so the diced preflight's D5 gate can assert
    # `tiering_mode != 'rules_floor_degraded'` on a FRESH run — i.e. GLM tiering actually fired and
    # the batch did not silently collapse to the deterministic rules-floor. None when the caller did
    # not thread a status (LLM-tiering OFF / non-LiveRetrievalResult retrieval) => byte-identical
    # absence. ADVISORY / DISCLOSURE only — credibility stays a WEIGHT (no drop, no abort — §-1.3);
    # the binding per-claim gates (strict_verify + 4-role D8) are untouched. asdict() serializes it.
    tiering_status: dict | None = None


def has_usable_corpus(classified_sources: list[Any], evidence_rows: list[Any]) -> bool:
    """Defense-in-depth corpus-ZERO floor the caller asserts before proceeding on the weighted gate.

    The weighted gate REPLACES the tier-MIX refusal, NOT the legitimate "cannot synthesize from
    nothing" floor.

    I-cred-006b iter-2 (Codex P0): generation consumes ``retrieval.evidence_rows`` (the cited rows
    with spans), NOT ``classified_sources``. Live retrieval can append a ``CorpusSource`` (so
    ``classified_sources`` is non-empty) while every content-starved / no-content evidence row is
    skipped (so ``evidence_rows`` is empty). Checking only ``classified_sources`` therefore let the ON
    path reach generation with zero usable evidence — a "synthesize from nothing" violation when the
    planner (and its downstream plan-sufficiency gate) is OFF. So the floor requires BOTH: at least one
    classified source to weight AND at least one usable evidence row to generate from. ``evidence_rows``
    is REQUIRED (no default) so a caller cannot silently bypass the evidence-row floor.
    """
    return bool(classified_sources) and bool(evidence_rows)


def weighted_corpus_proceeds(
    *,
    flag_on: bool,
    has_material_deviation: bool,
    classified_sources: list[Any],
    evidence_rows: list[Any],
) -> bool:
    """THE load-bearing decision: does the weighted-corpus gate turn a material-deviation REFUSAL into
    a PROCEED for this corpus? Extracted as a pure, behaviorally-testable function (mirrors
    ``check_auto_approve_allowed`` being a separate function) so a logic typo cannot hide behind
    string-presence tests — the §-1.1 false-green trap, in test form.

    Returns True iff ALL hold:
      * the gate flag is ON (``PG_SWEEP_WEIGHTED_CORPUS_GATE``);
      * the corpus has a material tier deviation (the ONLY case the old gate would have REFUSED — a
        within-distribution corpus already auto-approves and needs no weighted-proceed);
      * the corpus has at least one classified source AND one usable evidence row
        (``has_usable_corpus`` — the corpus-ZERO / "cannot synthesize from nothing" floor still
        aborts; iter-2 P0: evidence_rows, not just classified_sources, because generation consumes the
        cited rows).

    When this returns False the caller falls through to the UNCHANGED approval logic
    (``check_auto_approve_allowed`` / default-approve), so OFF + within-distribution behavior is
    byte-identical. The journal-only adequacy FLOOR (``_jo_force_inadequate``) is enforced by the
    caller BEFORE this decision (it aborts at the adequacy gate, upstream of approval), so it is not a
    parameter here.
    """
    return (
        bool(flag_on)
        and bool(has_material_deviation)
        and has_usable_corpus(classified_sources, evidence_rows)
    )


def build_corpus_credibility_disclosure(
    *,
    classified_sources: list[Any],
    tier_counts: dict[str, int],
    tier_fractions: dict[str, float],
    total_sources: int,
    had_material_deviation: bool,
    domain: str,
    research_question: str,
    authority_by_url: dict[str, Any] | None = None,
    tiering_status: dict | None = None,
) -> CorpusCredibilityDisclosure:
    """Build the deterministic, domain-aware corpus credibility disclosure — PURE, offline, no LLM.

    Each source is weighted by its deterministic, domain-aware ``authority_score`` — preferring, in
    order: (1) the source object's own ``.authority_score`` attribute; (2) the optional
    ``authority_by_url`` join map (``{url: authority_score}``, supplied by the caller from the evidence
    rows where the numeric authority lives in planner mode); (3) I-arch-011 B11: a deterministic compute
    from the source's url/title via the same ``score_source_authority`` the rest of the pipeline uses
    (pure, offline, no row mutation), so the domain-aware authority weighting actually runs instead of
    silently collapsing to the flat prior. It falls back to the per-tier nominal ``tier_prior`` ONLY
    when none of those three yields a score (so the disclosure is never blank). The disclosure
    records the tier mix, what the OLD gate would have refused on (``had_material_deviation``), and a
    source-weighted mean credibility — so the run honestly DISCLOSES that lower-tier sources are
    lower-credibility, rather than refusing the whole corpus on the source-type count.

    ``classified_sources`` are the ``CorpusSource``-shaped objects (``.url`` / ``.tier`` / ``.domain``
    + optional ``.authority_score``); read-only. ``authority_by_url`` is read-only. No row mutation, no
    network, no spend.
    """
    auth_by_url = authority_by_url or {}
    per_source: list[SourceCredibilityRow] = []
    weight_sum = 0.0
    for s in (classified_sources or []):
        tier = str(getattr(s, "tier", "") or "UNKNOWN")
        url = str(getattr(s, "url", "") or "")
        # I-arch-011 B11: restore ``authority_score`` as the PRIMARY weight_basis so the documented
        # deterministic, domain-aware authority weighting actually runs. The disclosure previously fell
        # back to the flat per-tier ``tier_prior`` for EVERY source (all 528 on drb_90) because the
        # ``CorpusSource`` objects carry no ``.authority_score`` attribute AND, in legacy / non-planner
        # mode, no evidence row carries one either, so the ``authority_by_url`` join was empty. The
        # original module comment (lines 16, 186-189) says ``tier_prior`` is the fallback used ONLY
        # "when neither is available" — but "neither available" was the common case, so tier_prior was
        # NOT a fallback, it was the rule. The fix RESTORES the intended order:
        #   1. the source object's own ``.authority_score`` attribute;
        #   2. the caller's per-url ``authority_by_url`` join (planner mode);
        #   3. COMPUTE it deterministically from the source's url/title via the same domain-aware
        #      ``score_source_authority`` the rest of the pipeline uses (offline, pure, no LLM/network);
        #   4. ONLY when that genuinely cannot run does it fall to the per-tier ``tier_prior`` (so the
        #      disclosure is never blank).
        # This is a WEIGHT restoration, not a cap/floor/filter: every source still flows through (no
        # drop), and strict_verify + the 4-role D8 release decision remain the only faithfulness gate.
        auth = _coerce_authority(getattr(s, "authority_score", None))
        if auth is None and url:
            auth = _coerce_authority(auth_by_url.get(url))
        if auth is not None:
            # (1)/(2): a genuine pre-computed authority_score (the source object's own
            # attribute or the planner-mode per-url join) carries a real OpenAlex-backed
            # signal -> use it as the primary disclosure weight.
            weight = auth
            basis = "authority_score"
        else:
            # (3) I-beatboth-010 (#1288) FIX-B: compute the score from url+title. On the
            # thin-OpenAlex url+title-only path that score is a flat, NON-discriminating
            # ~0.39 blend at LOW confidence (Signal A scholarly=0.0, Signal B institutional
            # =neutral 0.40), so on drb_72 553/592 sources collapsed to the identical
            # 0.3315 — AER == YouTube == Scribd == OECD, and the discriminating
            # _DEFAULT_TIER_CREDIBILITY_PRIOR was dead code. When the computed score is LOW
            # confidence, use the DISCRIMINATING per-tier prior (T1=0.95 .. T6=0.30 ..
            # UNKNOWN=0.20) as the disclosed WEIGHT so a journal out-weighs YouTube/Scribd.
            # Keep the computed score only when it is genuinely NOT low-confidence. This is
            # WEIGHT-strengthening only: every source still flows through (no drop/cap/
            # floor), and strict_verify + the 4-role D8 release decision remain the only
            # faithfulness gate. (REJECTED the journal-floor/min_t1_count variant — that is
            # the §-1.1/§-1.3-banned metadata-as-quality cap the operator reversed 2026-06-07.)
            computed_score, computed_is_low = (
                _compute_authority_score_for_source(s) if url else (None, True)
            )
            computed_score = _coerce_authority(computed_score)
            if computed_score is not None and not computed_is_low:
                weight = computed_score
                basis = "authority_score"
            else:
                weight = _tier_prior(tier)
                basis = "tier_prior"
        weight_sum += weight
        per_source.append(SourceCredibilityRow(
            url=str(getattr(s, "url", "") or ""),
            tier=tier,
            domain=str(getattr(s, "domain", "") or ""),
            credibility_weight=round(weight, 4),
            weight_basis=basis,
        ))

    n = len(per_source)
    weighted_mean = round(weight_sum / n, 4) if n else 0.0

    note = (
        f"Weighted-corpus gate ({_FLAG}) ON: the corpus is ACCEPTED and its credibility is DISCLOSED "
        f"(weighted, domain-aware) rather than refused on tier-mix. {n} source(s); source-weighted "
        f"mean credibility {weighted_mean:.2f}. "
        + (
            "The corpus deviates from the pre-registered tier distribution; under the old gate this "
            "would have been refused (abort_corpus_approval_denied / abort_corpus_inadequate). That "
            "tier-COUNT refusal verified no individual claim — the per-claim faithfulness floor "
            "(strict_verify + the 4-role D8 release decision) remains the binding check and is "
            "unchanged. Lower-tier sources are disclosed as lower-credibility, not dropped."
            if had_material_deviation
            else "The corpus is within the pre-registered tier distribution."
        )
    )

    return CorpusCredibilityDisclosure(
        gate=_FLAG,
        domain=str(domain or ""),
        research_question=str(research_question or ""),
        total_sources=int(total_sources),
        tier_counts=dict(tier_counts or {}),
        tier_fractions=dict(tier_fractions or {}),
        had_material_deviation=bool(had_material_deviation),
        weighted_credibility_mean=weighted_mean,
        per_source=per_source,
        disclosure_note=note,
        # I-deepfix-001 D5 (#1344): carry the honest credibility-tiering batch status straight
        # through onto the durable disclosure (asdict serializes it into the manifest). PURE
        # plumbing — a defensive shallow copy of exactly what the caller threaded (no normalization
        # of mode/counts), so the diced preflight's D5 gate reads the REAL tiering_mode. None passes
        # through as None (caller did not thread a status). DISCLOSURE only — no drop, no abort; the
        # faithfulness engine is untouched.
        tiering_status=(dict(tiering_status) if isinstance(tiering_status, dict) else tiering_status),
    )


def disclosure_to_dict(disclosure: CorpusCredibilityDisclosure) -> dict[str, Any]:
    """Serialize the disclosure to a plain dict (for ``corpus_credibility_disclosure.json`` + manifest)."""
    return asdict(disclosure)
