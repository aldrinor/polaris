"""Sweep-side 4-role evaluation orchestration (I-meta-002 sub-PR-6).

This module is the THIN seam between `scripts/run_honest_sweep_r3.py` and the per-claim
4-role pipeline (`role_pipeline.run_claim_pipeline`, sub-PR-5). It exists so the big sweep
file's edit stays minimal: the sweep supplies an INJECTED `RoleTransport` plus the already-
extracted per-claim inputs, and this module drives the Mirror -> Sentinel -> Judge pipeline
for each claim, feeds the resulting `D8ClaimRow`s through the SINGLE binding gate
(`apply_d8_release_policy`, sub-PR-3), persists the snowball KG (sub-PR-5), and returns a
flat result the sweep maps onto the manifest + `VerifiedSentence.evaluator_agrees`.

The seam itself adds no paid LLM call; the dependency-injected transport performs the
(already-paid) verifier calls, and the per-call run-budget guard lives in
`role_pipeline.RecordingTransport` (I-meta-008 — verifier spend is threaded into the shared
PG_MAX_COST_PER_RUN accumulator there, so a cap breach raises `BudgetExceededError` out of
this seam). Tests inject a mock transport. There is NO `datetime.now()`: the caller supplies
the audit `timestamp` (LAW VI). The KG opens a SQLite file under the caller-supplied `run_dir`
only — no other I/O except the D8 config YAML read (a pure file read).

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

import concurrent.futures
import contextvars
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from src.polaris_graph.llm.openrouter_client import (
    BudgetExceededError,
    _add_run_cost,
    check_run_budget,
    current_run_cost,
    reset_run_cost,
)
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    Gap,
    ReleaseDecision,
    apply_d8_release_policy,
    load_d8_policy_config,
)
from src.polaris_graph.roles.role_pipeline import (
    ClaimPipelineResult,
    run_claim_pipeline,
)
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

# I-run11-001 (#1042): bounded per-claim COMPUTE parallelism for the 4-role seam. The per-claim
# Mirror->Sentinel->Judge pipeline is independent across claims (each `run_claim_pipeline` builds
# its OWN `RecordingTransport`), so the COMPUTE half can run in a small thread pool while ALL
# reduction + persistence (D8 policy, coverage credit, KG write, run-budget cap) stays on the
# PARENT thread in ORIGINAL claim order (Codex Path-B SAFE design, .codex/I-run11-seam). At the
# benchmark stage (xhigh reasoning, minutes/claim) this is what makes the seam finish in time;
# run 10 died on the sequential operational failure mode. LAW VI: worker count from env only.
# `1` (or a single claim) preserves the EXACT sequential behaviour, including the live per-call
# budget enforcement inside `RecordingTransport.complete()`.
_CLAIM_WORKERS = max(1, int(os.getenv("PG_FOUR_ROLE_CLAIM_WORKERS", "6")))


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


def build_evaluator_agrees_map(
    final_verdicts: dict[str, str],
    kept_claim_ids: set[str] | None = None,
) -> dict[str, bool]:
    """Build the per-claim `evaluator_agrees` MAP for the sweep manifest (I-meta-002 PR-9/M5).

    Maps each `claim_id` in `final_verdicts` to the §-1.1 fail-safe boolean:

        evaluator_agrees = (claim is kept) AND evaluator_agrees_from_verdict(final_verdict)

    where `evaluator_agrees_from_verdict` is the SINGLE source of the verdict rule
    (`final_verdict == "VERIFIED"`). Every other verdict — PARTIAL / UNSUPPORTED / FABRICATED /
    UNREACHABLE / any unknown string — maps to False. The value is NEVER True before a VERIFIED
    final verdict exists AND the claim is kept (a non-VERIFIED verdict must never read as
    "evaluator agreed" in clinical context).

    `kept_claim_ids` is the set of claim_ids that survived as kept/verified sentences
    (`verifier_pass=True`). When it is None, ALL claim_ids in `final_verdicts` are treated as
    kept — INVARIANT: on the sweep path the `FourRoleClaim` set is built (by the M3a builder)
    from KEPT (is_verified) sentences only, so every claim_id in `final_verdicts` is already a
    kept claim and passing None is correct there. When a set IS supplied, a claim_id absent from
    it maps to False even if its verdict is VERIFIED (defensive: a not-kept claim can never agree).

    Keys are EXACTLY `final_verdicts.keys()` (so the map is joinable to
    `four_role_claim_audit.json` from M3b); `kept_claim_ids` affects only the boolean value and
    never adds or removes keys. An empty `final_verdicts` yields `{}` (no error here; the sweep
    branch's own fail-closed guards already handle empty claim sets upstream).
    """
    agrees_map: dict[str, bool] = {}
    for claim_id, final_verdict in final_verdicts.items():
        is_kept = kept_claim_ids is None or claim_id in kept_claim_ids
        agrees_map[claim_id] = is_kept and evaluator_agrees_from_verdict(final_verdict)
    return agrees_map


def _write_role_call_log(path: Path, role_call_log: list[dict]) -> None:
    """Write the per-role-call reasoning log as one sorted-key JSON object per line.

    I-run11-001 (#1042): factored out of `run_four_role_evaluation` so the SAME serialization is
    used by both the INCREMENTAL per-claim write (mid-run monitorability) and the final idempotent
    write. Byte-identical to the prior inline `write_text` (`ensure_ascii=False, sort_keys=True`),
    so a partial file rewritten on the next claim is just a longer prefix of the same content.
    """
    path.write_text(
        "".join(
            json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
            for entry in role_call_log
        ),
        encoding="utf-8",
    )


def _compute_claim_results(
    transport: RoleTransport,
    *,
    claims: list[FourRoleClaim],
    model_slugs: dict[str, str],
    timestamp: str,
) -> list[tuple[ClaimPipelineResult, float | None]]:
    """COMPUTE the per-claim 4-role pipeline for every claim, returning results BY INPUT INDEX.

    I-run11-001 (#1042), Codex Path-B SAFE design (.codex/I-run11-seam). This is the ONLY half
    that runs the (already-paid) verifier calls; it makes NO reduction decision — the parent
    reduces in input order. Each element is `(ClaimPipelineResult, cost_delta)` for `claims[idx]`,
    where:

      * SEQUENTIAL (`_CLAIM_WORKERS == 1` or a single claim): `run_claim_pipeline` is called
        DIRECTLY on the parent thread (no copied context, no `reset_run_cost`), so
        `RecordingTransport.complete()` enforces the LIVE per-call run budget on the parent
        `_RUN_COST_CTX` EXACTLY as today. `cost_delta is None` signals the parent "already
        accounted — do not re-add" (byte-equivalence with the pre-#1042 behaviour).

      * PARALLEL: each claim runs inside its OWN `contextvars.copy_context()` so the per-claim
        verifier spend + the pathB `_ROLE` tag are ISOLATED per worker (a plain shared context
        would cross-contaminate role tags AND a copied `ContextVar[float]` does NOT converge into
        the parent counter — Codex naive-B trap). The worker `reset_run_cost()`s its copy, runs
        the pipeline, and returns `current_run_cost()` as `cost_delta`; the PARENT re-adds it to
        the single run counter and enforces the cap. The pathB capture `_SINK` is shared BY
        REFERENCE through the copied context (atomic `list.append`), so verifier captures still
        land at the parent for the M4 gate — it is NOT isolated. A worker exception PROPAGATES
        (fail closed; no `except: pass`).
    """
    n = len(claims)

    def _compute_one(idx: int, claim: FourRoleClaim) -> tuple[int, ClaimPipelineResult, float]:
        ctx = contextvars.copy_context()

        def _run() -> tuple[ClaimPipelineResult, float]:
            # Isolate THIS claim's verifier spend in the copied context so the parent can re-add a
            # clean per-claim delta and enforce the cap deterministically at the claim boundary.
            reset_run_cost()
            res = run_claim_pipeline(
                transport,
                claim_id=claim.claim_id,
                claim=claim.claim_text,
                evidence_documents=claim.evidence_documents,
                severity=claim.severity,
                s0_categories=claim.s0_categories,
                model_slugs=model_slugs,
                timestamp=timestamp,
            )
            return res, current_run_cost()

        result, delta = ctx.run(_run)
        return idx, result, delta

    # SEQUENTIAL fast path: byte-equivalent to the pre-#1042 loop (live per-call budget preserved,
    # cost_delta None so the parent does not re-account). A single claim also takes this path (a
    # thread pool for one item is pure overhead).
    if _CLAIM_WORKERS == 1 or n <= 1:
        out: list[tuple[ClaimPipelineResult, float | None]] = []
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
            out.append((result, None))
        return out

    # PARALLEL path: bounded thread pool; collect BY INDEX (never as_completed order). A worker
    # exception surfaces from `future.result()` and propagates (fail closed) — the seam HOLDS,
    # never partial-releases.
    computed: list[tuple[ClaimPipelineResult, float | None] | None] = [None] * n
    with concurrent.futures.ThreadPoolExecutor(max_workers=_CLAIM_WORKERS) as pool:
        futures = [pool.submit(_compute_one, idx, claim) for idx, claim in enumerate(claims)]
        for future in concurrent.futures.as_completed(futures):
            idx, result, delta = future.result()  # re-raises any worker exception (fail closed).
            computed[idx] = (result, delta)

    # Defensive: every index must be filled (a None here would mean a future silently dropped — a
    # real bug, never a vacuous pass). Fail loud rather than reduce a partial result set.
    for idx, item in enumerate(computed):
        if item is None:
            raise RuntimeError(
                f"run_four_role_evaluation: claim index {idx} produced no result from the "
                f"compute pool (fail-closed — a dropped future must never reduce silently)."
            )
    return [item for item in computed if item is not None]


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
    campaign_kg_db: str | Path | None = None,
) -> FourRoleEvaluationResult:
    """Drive the per-claim 4-role pipeline, apply the SINGLE binding D8 gate, persist the KG.

    I-meta-002-q1d (#948): when `campaign_kg_db` is given, the snowball KG is persisted to that
    CAMPAIGN-scoped sqlite path (shared across the sweep's questions) instead of the per-question
    `run_dir`, so question N can reuse questions 1..N-1's VERIFIED claims. Default None preserves the
    per-`run_dir` behavior (existing callers/tests unchanged). The sweep runs questions sequentially, so
    there are no concurrent writers; anti-poisoning (only VERIFIED rows reusable) is unchanged.

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
    # I-meta-002-q1b (#939): per-role-call reasoning log, persisted to four_role_role_calls.jsonl
    # for line-by-line review. `reasoning` is its OWN field — NEVER concatenated into the verdict.
    role_call_log: list[dict] = []

    # I-run11-001 (#1042): COMPUTE the per-claim pipeline (possibly in parallel), then REDUCE on
    # the parent thread in ORIGINAL claim order. `computed[idx]` holds `(ClaimPipelineResult,
    # cost_delta)` for `claims[idx]`; `cost_delta` is the per-claim verifier spend captured INSIDE
    # the worker's isolated `_RUN_COST_CTX` (parallel path) or None (sequential path, where
    # RecordingTransport already enforced the LIVE per-call budget on the parent counter).
    computed: list[tuple[ClaimPipelineResult, float | None]] = _compute_claim_results(
        transport,
        claims=claims,
        model_slugs=model_slugs,
        timestamp=timestamp,
    )

    role_calls_path = run_dir / FOUR_ROLE_ROLE_CALLS_FILENAME

    # I-meta-002-q1d (#948): campaign-scoped KG when given, else per-question run_dir (default).
    kg_store = (
        VerifiedClaimGraphStore(db_path=campaign_kg_db)
        if campaign_kg_db is not None
        else VerifiedClaimGraphStore(run_dir=run_dir)
    )
    try:
        # Reduce in INPUT order (zip over claims + the index-ordered `computed` list). Completion
        # order NEVER drives any reduction — the parallel path collected results BY INDEX, so this
        # is byte-identical to the sequential reduction regardless of which claim finished first.
        for claim, (result, cost_delta) in zip(claims, computed):
            # I-run11-001 (#1042): on the PARALLEL path the worker's verifier spend was isolated in
            # a copied context; thread it into the SINGLE parent run-budget accumulator HERE and
            # enforce the cap. `BudgetExceededError` propagates to the existing budget-abort path
            # (it is NEVER caught here — the finally below only closes the KG store). On the
            # SEQUENTIAL path `cost_delta is None`: RecordingTransport already accounted + capped
            # live on the parent counter, so re-adding would double-count (byte-equivalence).
            if cost_delta is not None:
                _add_run_cost(cost_delta)
                check_run_budget(0)  # raises BudgetExceededError if the cap is now exceeded.

            d8_rows.append(result.d8_row)
            all_records.extend(result.records)
            final_verdicts[claim.claim_id] = result.final_verdict
            # I-meta-002-q1b (#939): record each verifier call for this claim with its reasoning
            # held SEPARATE from raw_text (the bare verdict/body). This is the verifiers' analogue
            # of the generator's reasoning_trace.jsonl.
            for record in result.records:
                role_call_log.append(
                    {
                        "claim_id": claim.claim_id,
                        "role": record.role,
                        "model_slug": record.model_slug,
                        "served_model": record.served_model,
                        "raw_text": record.raw_text,
                        "reasoning": record.reasoning,
                    }
                )

            # I-run11-001 (#1042): INCREMENTALLY persist the role-call log after EACH claim is
            # reduced (rewrite the whole file in claim order — small, fine) so a mid-run hang is
            # monitorable on disk instead of the log only landing after the full loop. The final
            # write below is kept (idempotent: it rewrites the same complete content).
            _write_role_call_log(role_calls_path, role_call_log)

            # Coverage credit ONLY on a VERIFIED final verdict, against the CANONICAL required
            # ids this claim covers — a dropped/UNSUPPORTED claim adds nothing (denominator is
            # the fixed required set, so this can only ever lower the achieved fraction).
            if result.final_verdict == _VERDICT_VERIFIED:
                internal_ledger.covered_element_ids.update(claim.covered_element_ids)

            # Snowball KG: persist EVERY outcome (audit); only VERIFIED rows are reusable
            # (anti-poisoning is enforced inside the store). role_verdicts records the raw
            # Mirror/Sentinel/Judge signals for provenance. KG writes stay PARENT-only (single
            # SQLite connection) — never inside a worker (Codex Path-B risk #2).
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

    # I-meta-002-q1b (#939): persist the per-role-call reasoning log next to the run — one JSON
    # object per line, `reasoning` in its own field, NEVER mixed into the verdict. Reviewable
    # line-by-line alongside the generator's reasoning_trace.jsonl. (Kept as the final write even
    # though I-run11-001 also writes incrementally above — idempotent same-content rewrite.)
    _write_role_call_log(role_calls_path, role_call_log)

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


# --- M3b seam: the single thin core both the sweep branch and the offline test call --------
# The builder is a KEYWORD-ARGUMENT closure that the SEAM calls AFTER generation with the
# run-local objects (`multi`, `template`, `slug`, `domain`, `ev_pool`); it PRODUCES a bundle
# with `.inputs` (FourRoleEvaluationInputs) and `.audit_map` (dict[str, dict]). It is wired in
# scripts/dr_benchmark/run_gate_b.py over native_gate_b_inputs.build_native_gate_b_inputs +
# the evidence normalization. The builder takes run-local objects (NOT captured at construction)
# because `multi`/`ev_pool` only exist INSIDE run_one_query, after generation — the seam supplies
# them. Kept as a structural `Callable` so this module never imports the builder (LAW VII CLI
# isolation; the builder lives in roles/, the closure in scripts/).
FourRoleBundleBuilder = Callable[..., object]

# Filename of the per-claim audit map persisted next to the run (Codex M3 P2 #2). The SEAM
# writes it; the builder does NO file I/O.
FOUR_ROLE_CLAIM_AUDIT_FILENAME = "four_role_claim_audit.json"

# I-meta-002-q1b (#939): filename of the per-role-call reasoning log (one JSON object per line)
# `run_four_role_evaluation` writes next to the run — the verifiers' analogue of the generator's
# reasoning_trace.jsonl, with `reasoning` held SEPARATE from the verdict for line-by-line review.
FOUR_ROLE_ROLE_CALLS_FILENAME = "four_role_role_calls.jsonl"


def run_four_role_seam(
    transport: RoleTransport,
    *,
    run_dir: Path,
    timestamp: str,
    four_role_input_builder: FourRoleBundleBuilder | None = None,
    four_role_inputs: FourRoleEvaluationInputs | None = None,
    multi: object = None,
    template: object = None,
    slug: str | None = None,
    domain: str | None = None,
    ev_pool: object = None,
    campaign_kg_db: str | Path | None = None,
) -> FourRoleEvaluationResult:
    """Resolve the 4-role inputs (builder WINS), run the SINGLE binding D8 gate, persist audit.

    This is the seam core extracted so BOTH the guarded `run_one_query` branch and the offline
    seam test exercise the SAME code (no copy-paste of the override logic). Precedence (Codex
    M3 P2 #1): if `four_role_input_builder` is provided it WINS — the SEAM calls it AFTER
    generation with the run-local objects (`multi`, `template`, `slug`, `domain`, `ev_pool`) so
    it PRODUCES the inputs+audit bundle from the finished report, and the SEAM writes
    `bundle.audit_map` to `run_dir / FOUR_ROLE_CLAIM_AUDIT_FILENAME` (json, sorted keys) so every
    claim_id is traceable alongside the run. Otherwise a directly-supplied static
    `four_role_inputs` is used as-is (unit/static path; it carries no audit_map, so nothing is
    written). If BOTH are None the branch fails closed (the sweep never synthesizes inputs).

    The run-local objects are passed through (NOT captured by the closure at construction)
    because `multi`/`ev_pool` only exist inside `run_one_query` after generation; the builder
    cannot have closed over them when the caller constructed it. Duck-typed `object` here so this
    seam never imports the generator's `MultiSectionResult` (LAW VII CLI isolation).

    Pure orchestration over the INJECTED `transport` (no network, no spend) plus one JSON write.
    """
    if four_role_input_builder is not None:
        # BUILDER WINS: produce the inputs+audit bundle from the finished report + native
        # contract (supplied the run-local objects HERE), then run the gate over bundle.inputs.
        bundle = four_role_input_builder(
            multi=multi,
            template=template,
            slug=slug,
            domain=domain,
            ev_pool=ev_pool,
        )
        inputs = bundle.inputs
        result = run_four_role_evaluation(
            transport,
            claims=inputs.claims,
            run_dir=run_dir,
            timestamp=timestamp,
            coverage_ledger=inputs.coverage_ledger,
            required_s0_categories=inputs.required_s0_categories,
            model_slugs=inputs.model_slugs,
            rewrite_already_attempted=inputs.rewrite_already_attempted,
            campaign_kg_db=campaign_kg_db,
        )
        # The SEAM (not the builder) persists the per-claim audit map alongside the run.
        (run_dir / FOUR_ROLE_CLAIM_AUDIT_FILENAME).write_text(
            json.dumps(bundle.audit_map, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result

    if four_role_inputs is None:
        raise ValueError(
            "run_four_role_seam: PG_FOUR_ROLE_MODE is on and a transport was injected, but "
            "neither a four_role_input_builder nor static four_role_inputs was supplied; the "
            "sweep does not synthesize them (fail-closed)."
        )

    # Static path (no builder): use the caller-supplied inputs as-is (no audit_map to persist).
    return run_four_role_evaluation(
        transport,
        claims=four_role_inputs.claims,
        run_dir=run_dir,
        timestamp=timestamp,
        coverage_ledger=four_role_inputs.coverage_ledger,
        required_s0_categories=four_role_inputs.required_s0_categories,
        model_slugs=four_role_inputs.model_slugs,
        rewrite_already_attempted=four_role_inputs.rewrite_already_attempted,
        campaign_kg_db=campaign_kg_db,
    )
