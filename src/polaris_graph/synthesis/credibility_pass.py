"""I-cred-012 (#1162) — credibility-analysis pass ORCHESTRATOR (the activation chain).

Pure orchestrator that runs the committed P4→P3→P2→P5→P6 redesign chain over the generator's EFFECTIVE
evidence pool and returns the disclosure inputs (``credibility_by_evidence``, ``origin_by_evidence``,
``claims``, ``edges``, ``weight_mass``). The sweep runner calls it under the master slate
``PG_SWEEP_CREDIBILITY_REDESIGN``; OFF ⇒ not invoked ⇒ byte-identical. ADVISORY only: ``strict_verify`` +
the 4-role D8 release policy stay the ONLY binding gates — nothing here keeps/drops a sentence or flips
release.

FAIL-LOUD (the drb_72 silent-downgrade lesson, locked in the I-cred-012 architecture iter-1/4 resolutions):
a dead production judge (P2 ``judge_error``) or a row missing ``evidence_id`` ABORTS the pass
(``CredibilityPassError``) rather than degrading to a false-green advisory. The activation orchestrator
escalates the modules' OFFLINE fail-soft into a hard abort.

Order (locked): P4 copied-annotated rows (fail-loud on missing eid) → P3 supersession → P2 score
(fail-loud on judge_error) → POST-P3 credibility = P2 × P3 multiplier (certainty carried) → P5 claim graph
→ P6 weight-mass over the POST-P3 judgments. P10 dissent + the M-52 effective-pool hoist + the P8
render-site wrapper are the per-hook sub-issues; this module is the chain core they consume.
"""
from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass
from typing import Any, Callable

from src.polaris_graph.authority.credibility_skill import score_source_credibility
from src.polaris_graph.authority.supersession import supersession_adjustment
from src.polaris_graph.synthesis.claim_graph import build_claim_graph
from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass

_MASTER_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def credibility_redesign_enabled() -> bool:
    """The master activation slate. OFF ⇒ the runner never calls the pass ⇒ byte-identical."""
    return os.environ.get(_MASTER_FLAG, "").strip().lower() not in _OFF_VALUES


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


@dataclass
class CredibilityAnalysis:
    credibility_by_evidence: dict   # evidence_id -> EvidenceCredibility
    origin_by_evidence: dict        # evidence_id -> origin_cluster_id
    claims: list                    # AtomicClaim[] (Phase-5)
    edges: list                     # ContradictionEdge[] (Phase-5)
    weight_mass: list               # ClaimWeightMass[] (Phase-6)


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


def run_credibility_analysis(
    research_question: str,
    rows: list[dict],
    *,
    gov_suffixes: tuple,
    domain: str | None = None,
    judge: Callable | None = None,
    now_year: int | None = None,
) -> CredibilityAnalysis:
    """Run the P4→P3→P2→P5→P6 chain over the EFFECTIVE evidence pool. Fail-loud on judge_error / missing eid.

    ``rows`` MUST already be the generator's effective pool (post-M-52, post-dissent); ``gov_suffixes`` is
    the PSL gov-suffix tuple the rest of the pipeline uses (dependency-injected, no global). ``judge`` is the
    production credibility judge (injected); None ⇒ priors-only, which the runner forbids under activation.
    """
    if not rows:
        return CredibilityAnalysis({}, {}, [], [], [])
    if judge is None:
        # Codex I-cred-012 iter-5 P1: activation requires the PRODUCTION judge. P2 with judge=None returns
        # priors-only with judge_error=False, so a miswired master-on run would ship a false-green advisory.
        # The orchestrator is only ever called under activation, so a missing judge is fail-closed.
        raise CredibilityPassError(
            "abort_credibility_pass_error: the activated credibility pass requires a callable production "
            "judge; refusing to run priors-only (a false-green advisory). Wire the production judge or "
            "leave PG_SWEEP_CREDIBILITY_REDESIGN off."
        )
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
    try:
        return _run_chain(
            research_question, rows,
            gov_suffixes=gov_suffixes, domain=domain, judge=judge, now_year=now_year,
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
) -> CredibilityAnalysis:
    """The P4→P3→P2→P5→P6 chain body; wrapped by run_credibility_analysis for the fail-loud posture."""
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

    # ── P2: credibility judgments — FAIL-LOUD on any judge_error under activation ──
    judgments = score_source_credibility(research_question, annotated, domain=domain, judge=judge)
    errored = [j.evidence_id for j in judgments if getattr(j, "judge_error", False)]
    if errored:
        raise CredibilityPassError(
            f"abort_credibility_pass_error: the production credibility judge failed for "
            f"{len(errored)} source(s) (e.g. {errored[:5]}); refusing to ship a priors-only false-green"
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
        )

    # POST-P3 judgments for downstream — P6 disclosure must use the post-P3 credibility, not raw P2.
    adjusted_judgments = [
        dataclasses.replace(j, credibility_weight=credibility_by_evidence[j.evidence_id].credibility_weight)
        for j in judgments
    ]

    # ── P5: claim graph (atomic claims + contradiction edges) ──
    graph = build_claim_graph(annotated, domain=domain)

    # ── P6: origin-cluster weight-mass (mass = authority(canonical) ONLY; credibility disclosed) ──
    weight_mass = aggregate_weight_mass(graph.claims, annotated, adjusted_judgments)

    return CredibilityAnalysis(
        credibility_by_evidence=credibility_by_evidence,
        origin_by_evidence=origin_by_evidence,
        claims=graph.claims,
        edges=graph.edges,
        weight_mass=weight_mass,
    )
