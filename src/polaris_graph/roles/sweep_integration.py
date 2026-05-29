"""Sweep-side 4-role evaluation orchestration (I-meta-002 sub-PR-6).

This module is the THIN seam between `scripts/run_honest_sweep_r3.py` and the per-claim
4-role pipeline (`role_pipeline.run_claim_pipeline`, sub-PR-5). It exists so the big sweep
file's edit stays minimal: the sweep supplies an INJECTED `RoleTransport` plus the already-
extracted per-claim inputs, and this module drives the Mirror -> Sentinel -> Judge pipeline
for each claim, feeds the resulting `D8ClaimRow`s through the SINGLE binding gate
(`apply_d8_release_policy`, sub-PR-3), persists the snowball KG (sub-PR-5), and returns a
flat result the sweep maps onto the manifest + `VerifiedSentence.evaluator_agrees`.

NO network and NO spend here. The transport is dependency-injected; tests inject a mock.
There is NO `datetime.now()`: the caller supplies the audit `timestamp` (LAW VI). The KG
opens a SQLite file under the caller-supplied `run_dir` only — no other I/O except the D8
config YAML read (a pure file read).

Fail-closed contract (Codex P2 directives, binding):

  * D8 IS THE SINGLE BINDING GATE. `apply_d8_release_policy` produces the headline
    `release_allowed`. The legacy `evaluator_gate` may be emitted by the sweep as ADVISORY
    metadata only; this module never reads or writes it.
  * NO synthesized claim_ids. Each claim carries its existing `claim_id` (from the verified
    sentence / section). A blank id fails LOUD (`ValueError`) — duplicate/edited claims must
    not collide and break rewrite/gap traceability.
  * NO empty / vacuous D8 pass. An empty claim set OR an empty canonical required-element set
    (the coverage denominator) fails LOUD before any pipeline call — a `fraction()==1.0` over
    an empty denominator must never be allowed to release nothing as "all good".
  * Coverage denominator comes from the CANONICAL required elements (`required_element_ids`,
    caller-supplied), NOT from which claims happened to survive. `covered_element_ids` is
    populated ONLY from VERIFIED final verdicts via the caller-supplied claim->element map,
    so dropping/refusing a claim lowers coverage rather than dodging the gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    Gap,
    ReleaseDecision,
    apply_d8_release_policy,
    load_d8_policy_config,
)
from src.polaris_graph.roles.role_pipeline import run_claim_pipeline
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleCallRecord,
    RoleTransport,
)
from src.polaris_graph.memory.verified_claim_graph import VerifiedClaimGraphStore

# Canonical verdict token used to decide reuse / coverage credit (never an Enum here).
_VERDICT_VERIFIED = "VERIFIED"

# The three role slots the per-claim pipeline expects in its `model_slugs` map.
_REQUIRED_ROLE_SLUG_KEYS = ("mirror", "sentinel", "judge")


@dataclass
class FourRoleClaim:
    """One claim handed to the 4-role evaluation, carrying its EXISTING identity.

    `claim_id` is the verified-sentence / section id already minted upstream — it is used
    verbatim for `D8ClaimRow.claim_id` and is NEVER synthesized here. `covered_element_ids`
    lists the CANONICAL required-element ids this claim would satisfy IF it clears the
    pipeline as VERIFIED; the ledger credits them only on a VERIFIED final verdict, so a
    dropped/UNSUPPORTED claim contributes nothing to coverage.
    """

    claim_id: str
    claim_text: str
    evidence_documents: list[EvidenceDocument]
    severity: str
    s0_categories: list[str] = field(default_factory=list)
    covered_element_ids: list[str] = field(default_factory=list)


@dataclass
class FourRoleEvaluationInputs:
    """Caller-supplied inputs for the GUARDED sweep 4-role branch (sub-PR-6).

    Bundles everything the sweep hands to `run_four_role_evaluation` so the big sweep file's
    edit stays minimal and the contract is explicit: the per-claim `claims` (each with its
    EXISTING id), the canonical-denominator `coverage_ledger`, the per-question
    `required_s0_categories`, and the pinned `model_slugs` (mirror/sentinel/judge). The sweep
    NEVER builds these from the report — the caller (Gate-B) supplies them, so the sweep cannot
    synthesize a claim_id or a coverage denominator.
    """

    claims: list[FourRoleClaim]
    coverage_ledger: CoverageLedger
    required_s0_categories: list[str]
    model_slugs: dict[str, str]
    rewrite_already_attempted: bool = False


@dataclass
class FourRoleEvaluationResult:
    """Flat result the sweep maps onto the manifest + per-sentence evaluator_agrees.

    `release_allowed` / `held_reasons` / `gaps` come from the SINGLE binding D8 decision.
    `final_verdicts` maps claim_id -> final composed verdict (the sweep maps VERIFIED -> True
    and everything else -> False to populate `VerifiedSentence.evaluator_agrees`). `records`
    is the complete served-identity audit trail across all claims (for the Path-B identity
    gate). `coverage_fraction` is the canonical-denominator coverage actually achieved.
    """

    release_allowed: bool
    held_reasons: list[str]
    gaps: list[Gap]
    final_verdicts: dict[str, str]
    records: list[RoleCallRecord]
    coverage_fraction: float
    fabricated_occurrence_latched: bool
    needs_rewrite: list[str]
    kg_path: Path


def evaluator_agrees_from_verdict(final_verdict: str) -> bool:
    """Map a composed final verdict to the two-family `evaluator_agrees` boolean.

    VERIFIED -> True (the evaluator stack confirms the claim); every other verdict
    (PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE) -> False. The sweep applies this ONLY
    to kept sentences (`verifier_pass=True`), so the `VerifiedSentence` validator that forbids
    `evaluator_agrees=True` on a dropped sentence is never tripped.
    """
    return final_verdict == _VERDICT_VERIFIED


def run_four_role_evaluation(
    transport: RoleTransport,
    *,
    claims: list[FourRoleClaim],
    run_dir: Path,
    timestamp: str,
    coverage_ledger: CoverageLedger,
    required_s0_categories: list[str],
    model_slugs: dict[str, str],
    rewrite_already_attempted: bool = False,
    d8_config_path: str | Path | None = None,
) -> FourRoleEvaluationResult:
    """Drive the per-claim 4-role pipeline, apply the SINGLE binding D8 gate, persist the KG.

    Pure orchestration over the INJECTED `transport` (no network, no spend). For EACH claim:
    run `run_claim_pipeline`, collect its `D8ClaimRow` + served-identity records + final
    verdict, and — only on a VERIFIED final verdict — credit that claim's canonical
    `covered_element_ids` into the ledger. Then run `apply_d8_release_policy` ONCE over the
    collected rows (D8 is the headline gate) and write every per-claim outcome to the snowball
    `VerifiedClaimGraphStore` under `run_dir`.

    Fail-closed guards (Codex P2): raises `ValueError` on an empty claim set, an empty
    canonical required-element denominator, a blank/duplicate `claim_id`, or a missing role
    slug — never a vacuous pass and never a synthesized id.
    """
    # (P2) NO vacuous pass: an empty claim set or an empty canonical coverage denominator must
    # fail LOUD here, before any D8 call — fraction()==1.0 over an empty required set would
    # otherwise release "nothing" as all-clear.
    if not claims:
        raise ValueError(
            "run_four_role_evaluation: no claims supplied; a 4-role evaluation over zero "
            "claims cannot produce a release decision (fail-closed, no vacuous pass)."
        )
    if not coverage_ledger.required_element_ids:
        raise ValueError(
            "run_four_role_evaluation: coverage_ledger.required_element_ids is empty; the "
            "coverage denominator MUST be the canonical per-question required-element set "
            "(fail-closed, no vacuous pass over an empty denominator)."
        )
    # (Codex sub-PR-6 diff P1, LETHAL safety invariant) The coverage NUMERATOR must be rebuilt
    # here SOLELY from VERIFIED final verdicts — never trusted from the caller. A prefilled
    # `covered_element_ids` would let a Sentinel-UNGROUNDED claim that we correctly downgrade to
    # UNSUPPORTED still ride pre-credited coverage and release. Reject a non-empty incoming set
    # (fail LOUD), then credit a FRESH internal ledger only on VERIFIED finals below.
    if coverage_ledger.covered_element_ids:
        raise ValueError(
            "run_four_role_evaluation: coverage_ledger.covered_element_ids must be EMPTY on "
            "input; the coverage numerator is rebuilt here from VERIFIED final verdicts only, so "
            "a prefilled numerator cannot let an ungrounded/downgraded claim ride pre-credited "
            "coverage (fail-closed)."
        )
    internal_ledger = CoverageLedger(
        required_element_ids=list(coverage_ledger.required_element_ids),
        covered_element_ids=set(),
    )
    missing_slugs = [key for key in _REQUIRED_ROLE_SLUG_KEYS if not model_slugs.get(key)]
    if missing_slugs:
        raise ValueError(
            f"run_four_role_evaluation: model_slugs missing required role slug(s) "
            f"{missing_slugs}; the pipeline needs mirror/sentinel/judge pins."
        )

    # (P2) NO synthesized ids: every claim must carry a non-blank, unique existing claim_id.
    seen_ids: set[str] = set()
    for claim in claims:
        claim_id = (claim.claim_id or "").strip()
        if not claim_id:
            raise ValueError(
                "run_four_role_evaluation: a claim has a blank claim_id; claim_ids are "
                "caller-supplied (verified-sentence / section ids) and never synthesized."
            )
        if claim_id in seen_ids:
            raise ValueError(
                f"run_four_role_evaluation: duplicate claim_id {claim_id!r}; ids must be "
                f"unique so rewrite/gap traceability does not collide."
            )
        seen_ids.add(claim_id)

    d8_rows: list[D8ClaimRow] = []
    all_records: list[RoleCallRecord] = []
    final_verdicts: dict[str, str] = {}

    kg_store = VerifiedClaimGraphStore(run_dir=run_dir)
    try:
        for claim in claims:
            result = run_claim_pipeline(
                transport,
                claim_id=claim.claim_id,
                claim=claim.claim_text,
                evidence_documents=claim.evidence_documents,
                severity=claim.severity,
                s0_categories=claim.s0_categories,
                model_slugs=model_slugs,
                timestamp=timestamp,
            )
            d8_rows.append(result.d8_row)
            all_records.extend(result.records)
            final_verdicts[claim.claim_id] = result.final_verdict

            # Coverage credit ONLY on a VERIFIED final verdict, against the CANONICAL required
            # ids this claim covers — a dropped/UNSUPPORTED claim adds nothing (denominator is
            # the fixed required set, so this can only ever lower the achieved fraction).
            if result.final_verdict == _VERDICT_VERIFIED:
                internal_ledger.covered_element_ids.update(claim.covered_element_ids)

            # Snowball KG: persist EVERY outcome (audit); only VERIFIED rows are reusable
            # (anti-poisoning is enforced inside the store). role_verdicts records the raw
            # Mirror/Sentinel/Judge signals for provenance.
            kg_store.write_claim(
                claim_text=claim.claim_text,
                claim_id=claim.claim_id,
                verdict=result.final_verdict,
                role_verdicts={
                    "mirror_classification": (
                        result.mirror_result.classification
                        if result.mirror_result is not None
                        else None
                    ),
                    "sentinel_verdict": (
                        result.sentinel_result.verdict.value
                        if result.sentinel_result is not None
                        else None
                    ),
                    "raw_judge_verdict": result.raw_judge_verdict,
                    "final_verdict": result.final_verdict,
                },
                timestamp=timestamp,
            )
        kg_path = Path(kg_store.db_path)
    finally:
        kg_store.close()

    # The D8 threshold is loaded from config (LAW VI, pure file read — no network).
    config = load_d8_policy_config(d8_config_path)

    decision: ReleaseDecision = apply_d8_release_policy(
        d8_rows,
        required_s0_categories=required_s0_categories,
        coverage_ledger=internal_ledger,
        coverage_threshold=config.coverage_threshold,
        rewrite_already_attempted=rewrite_already_attempted,
    )

    return FourRoleEvaluationResult(
        release_allowed=decision.release_allowed,
        held_reasons=decision.held_reasons,
        gaps=decision.gaps,
        final_verdicts=final_verdicts,
        records=all_records,
        coverage_fraction=internal_ledger.fraction(),
        fabricated_occurrence_latched=decision.fabricated_occurrence_latched,
        needs_rewrite=decision.needs_rewrite,
        kg_path=kg_path,
    )
