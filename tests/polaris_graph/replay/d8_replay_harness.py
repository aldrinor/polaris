"""Offline replay of the D8 release policy over a SAVED run (I-perm-009).

Reconstructs the D8 inputs from a ``SavedRun`` and replays ``apply_d8_release_policy``.
It REUSES the production helpers (``load_required_entities``, ``validate_entity_severity``,
``load_d8_policy_config``, ``apply_d8_release_policy``, AND the S0 content-requirement matcher
``_content_requirements_satisfied``) so there is ZERO logic drift — the harness exercises the
real release policy and the real S0 coverage rule, not a copy.

Two modes:

* ``corpus_satisfaction=False`` (BASELINE-LOCK): reconstruct coverage + S0 categories from the
  saved per-claim ``covered_element_ids`` / ``s0_categories`` exactly as the production run
  recorded them. Reproduces the saved ``held_reasons`` bit-for-bit.

* ``corpus_satisfaction=True`` (I-perm-002 candidate): credit a required element from ANY
  VERIFIED claim that cites that element's evidence_id — BUT, faithful to production
  ``_claim_covers_entity``, an S0 SAFETY category is credited ONLY when the VERIFIED claim's
  text ALSO satisfies the entity's deterministic ``coverage_content_requirements``
  (``_content_requirements_satisfied``). This is NOT evidence_id-alone crediting (Codex A4):
  on drb_76 the VERIFIED Safety claims cite the contraindication evidence but their text lacks
  the literal required token ``contraindicated`` (they say "not recommended"/"should be
  avoided"), so the S0 ``contraindications`` category is NOT credited and the false hold does
  NOT clear. That HONEST result proves the real B2 fix needs semantic/qualitative
  contraindication recognition (I-perm-002) or the always-release relabel (I-perm-001), not a
  naive corpus-wide evidence_id credit. The R6 same-substance/risk-population guard is the
  production responsibility of I-perm-002.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.polaris_graph.roles.native_gate_b_inputs import (
    _KEY_ENTITY_ID,
    _content_requirements_satisfied,
    load_required_entities,
    validate_entity_severity,
)
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    ReleaseDecision,
    ReleaseOutcome,
    apply_d8_release_policy,
    compute_release_outcome,
    load_d8_policy_config,
)

from tests.polaris_graph.replay.saved_run_loader import SavedRun, default_template_path

_VERDICT_VERIFIED = "VERIFIED"


@dataclass
class D8ReplayResult:
    """Outcome of one offline D8 replay over a saved run."""

    decision: ReleaseDecision
    coverage_fraction: float
    required_element_ids: list[str]
    required_s0_categories: list[str]
    covered_element_ids: set[str] = field(default_factory=set)
    credited_categories: set[str] = field(default_factory=set)


@dataclass
class _RequiredEntities:
    element_ids: list[str]
    s0_categories: list[str]
    s0_by_element: dict[str, str | None]
    entity_by_id: dict[str, dict]


def _load_required_entities(template_path: Path, slug: str) -> _RequiredEntities:
    """Reuse the production helpers so the required-set + S0 derivation match the real builder."""
    template = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    d8_config = load_d8_policy_config()
    entities = load_required_entities(template, slug)
    element_ids = [e[_KEY_ENTITY_ID] for e in entities]
    entity_by_id = {e[_KEY_ENTITY_ID]: e for e in entities}
    s0_by_element: dict[str, str | None] = {}
    required_s0: set[str] = set()
    for entity in entities:
        _severity, s0_category = validate_entity_severity(entity, d8_config)
        s0_by_element[entity[_KEY_ENTITY_ID]] = s0_category
        if s0_category is not None:
            required_s0.add(s0_category)
    return _RequiredEntities(element_ids, sorted(required_s0), s0_by_element, entity_by_id)


def verified_claims_citing(run: SavedRun, evidence_id: str) -> list[str]:
    """Claim ids that are VERIFIED AND cite ``evidence_id`` (the per-safety-section floor input)."""
    out: list[str] = []
    for claim_id, verdict in run.final_verdicts.items():
        if verdict != _VERDICT_VERIFIED:
            continue
        if evidence_id in run.audit_map[claim_id].get("evidence_ids", []):
            out.append(claim_id)
    return out


_MISSING_S0_PREFIX = "d8_s0_must_cover_missing:"


def replay_release_outcome(
    run: SavedRun,
    *,
    always_release: bool,
    template_path: Path | None = None,
    corpus_satisfaction: bool = False,
) -> ReleaseOutcome:
    """Replay the I-perm-001 always-release outcome (BLOCK -> LABEL) over a saved run.

    Computes the no-fabrication hard line + the clinical safety floor from the saved verdicts:
    ``zero_verified`` (no VERIFIED claim), ``zero_usable_evidence`` (no cited evidence at all),
    ``safety_floor_insufficient`` (every required S0 SAFETY category is in the missing set).

    ``corpus_satisfaction`` (I-perm-002 #1196): when True, the safety floor is computed from
    coverage RE-DERIVED through the production S0 content-requirement matcher
    (``_content_requirements_satisfied``) rather than the saved literal-era ``covered_element_ids``.
    With ``PG_SWEEP_SEMANTIC_CONTRAINDICATION`` ON this credits a faithful contraindication warning
    ("not recommended"/"should be avoided") that the literal-token era left un-credited — so the
    safety floor clears and a run that was ``released_insufficient_safety_evidence`` becomes a
    caveated ``released_with_disclosed_gaps``. Default False preserves the I-perm-009/I-perm-001
    baseline (literal-era coverage, bit-for-bit).
    """
    result = replay_d8(
        run, template_path=template_path, corpus_satisfaction=corpus_satisfaction
    )
    decision = result.decision
    zero_verified = not any(v == _VERDICT_VERIFIED for v in run.final_verdicts.values())
    zero_usable_evidence = not any(
        run.audit_map.get(cid, {}).get("evidence_ids") for cid in run.final_verdicts
    )
    missing_s0 = {
        reason[len(_MISSING_S0_PREFIX):]
        for reason in decision.held_reasons
        if reason.startswith(_MISSING_S0_PREFIX)
    }
    required_s0 = set(result.required_s0_categories)
    safety_floor_insufficient = bool(required_s0) and required_s0 <= missing_s0
    return compute_release_outcome(
        decision,
        zero_verified=zero_verified,
        zero_usable_evidence=zero_usable_evidence,
        safety_floor_insufficient=safety_floor_insufficient,
        coverage_fraction=result.coverage_fraction,
        always_release=always_release,
    )


def replay_d8(
    run: SavedRun,
    *,
    template_path: Path | None = None,
    corpus_satisfaction: bool = False,
    rewrite_already_attempted: bool = False,
) -> D8ReplayResult:
    """Replay the production D8 release policy over a saved run's recorded verdicts."""
    tpath = template_path or default_template_path()
    req = _load_required_entities(tpath, run.slug)
    required_set = set(req.element_ids)

    credited_categories: set[str] = set()
    d8_rows: list[D8ClaimRow] = []
    covered: set[str] = set()

    for claim_id, verdict in run.final_verdicts.items():
        audit_row = run.audit_map[claim_id]
        claim_text = str(audit_row.get("sentence", ""))
        s0_categories = list(audit_row.get("s0_categories", []))

        if corpus_satisfaction and verdict == _VERDICT_VERIFIED:
            for evidence_id in audit_row.get("evidence_ids", []):
                if evidence_id not in required_set:
                    continue
                category = req.s0_by_element.get(evidence_id)
                if category is None:
                    # Non-S0 required element: canonical (evidence_id) match credits coverage,
                    # mirroring production _claim_covers_entity for a non-S0 entity.
                    covered.add(evidence_id)
                    continue
                # S0 SAFETY: credit ONLY when the claim text satisfies the deterministic
                # content requirements (faithful to production; no evidence_id-alone credit).
                entity = req.entity_by_id[evidence_id]
                if _content_requirements_satisfied(claim_text, entity):
                    covered.add(evidence_id)
                    if category not in s0_categories:
                        s0_categories.append(category)
                    credited_categories.add(category)

        if verdict == _VERDICT_VERIFIED:
            covered.update(audit_row.get("covered_element_ids", []))

        d8_rows.append(
            D8ClaimRow(
                claim_id=claim_id,
                severity=audit_row["severity"],
                verdict=verdict,
                s0_categories=s0_categories,
            )
        )

    covered &= required_set
    ledger = CoverageLedger(required_element_ids=req.element_ids, covered_element_ids=covered)
    d8_config = load_d8_policy_config()
    decision = apply_d8_release_policy(
        d8_rows,
        required_s0_categories=req.s0_categories,
        coverage_ledger=ledger,
        coverage_threshold=d8_config.coverage_threshold,
        rewrite_already_attempted=rewrite_already_attempted,
        prior_fabricated_latched=run.saved_fabricated_latched,
    )
    return D8ReplayResult(
        decision=decision,
        coverage_fraction=ledger.fraction(),
        required_element_ids=req.element_ids,
        required_s0_categories=req.s0_categories,
        covered_element_ids=covered,
        credited_categories=credited_categories,
    )
