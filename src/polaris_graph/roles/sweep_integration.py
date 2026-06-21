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
import datetime
import json
import logging
import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable

import src.polaris_graph.llm.openrouter_client as _orc
from src.polaris_graph.llm.openrouter_client import (
    BudgetExceededError,
    _add_run_cost,
    _impute_cost_from_tokens,
    check_run_budget,
    current_run_cost,
    reset_run_cost,
)
from src.polaris_graph.roles.openai_compatible_transport import RoleTransportError

logger = logging.getLogger(__name__)

# I-beatboth-006 (#1283) Fix C.3: the disclosed HARD-HALT manifest status + halt-artifact reason
# used when the per-role transport degrade is OFF (operator explicitly disabled it) and a
# `RoleTransportError` propagates to the seam. This is NEVER a raw teardown with a bare coverage=0 —
# the seam writes a disclosed `state/halt_<utc>_role_transport_exhausted.md` artifact (§3.0 halt-
# marker convention) and re-raises a TYPED `RoleTransportExhaustedError` carrying this status, so the
# fault is a DISCLOSED outcome. (With the flag ON — the default — a force-close is consumed per-claim
# upstream and never reaches here; this branch fires only on the flag-OFF / genuinely-unexpected path.)
_ROLE_TRANSPORT_EXHAUSTED_STATUS = "abort_role_transport_exhausted"


class RoleTransportExhaustedError(RuntimeError):
    """A force-closed role `RoleTransportError` propagated to the D8 seam with the degrade flag OFF.

    Carries the disclosed manifest `status` (`abort_role_transport_exhausted`) and the path to the
    `state/halt_<utc>_role_transport_exhausted.md` artifact the seam wrote BEFORE re-raising, so the
    outcome is a DISCLOSED hard halt — never a bare coverage=0 teardown. The default-ON path never
    raises this (a force-close is consumed per-claim); it fires only when an operator explicitly set
    `PG_ROLE_TRANSPORT_DEGRADE=0` and a role transport-faulted."""

    def __init__(self, message: str, *, status: str, halt_artifact: Path | None) -> None:
        super().__init__(message)
        self.status = status
        self.halt_artifact = halt_artifact


def _write_role_transport_halt_artifact(exc: RoleTransportError) -> Path | None:
    """Write the disclosed `state/halt_<utc>_role_transport_exhausted.md` halt marker (Fix C.3).

    Records the faulted role's exception type + message so the operator sees WHY the D8 seam hard-
    halted with the degrade flag OFF. Best-effort: a write failure must not mask the original fault
    (we still re-raise the typed error), so it is logged loudly and returns None. The `state/` dir is
    the repository-standard halt-marker location (§3.0); created if absent."""
    try:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        halt_dir = Path("state")
        halt_dir.mkdir(parents=True, exist_ok=True)
        artifact = halt_dir / f"halt_{ts}_role_transport_exhausted.md"
        artifact.write_text(
            "# HALT: role_transport_exhausted (I-beatboth-006 #1283 Fix C.3)\n\n"
            f"- utc: {ts}\n"
            f"- status: {_ROLE_TRANSPORT_EXHAUSTED_STATUS}\n"
            f"- reason: a role `RoleTransportError` propagated to the D8 seam with "
            f"`PG_ROLE_TRANSPORT_DEGRADE` OFF.\n"
            f"- faulted_role_error: {type(exc).__name__}: {exc}\n\n"
            "The per-role transport degrade (default ON) was explicitly disabled, so a force-closed "
            "Mirror/Judge/Sentinel transport HARD-HALTS the run loudly with this disclosed status "
            "instead of degrading per-claim to UNSUPPORTED. Re-enable `PG_ROLE_TRANSPORT_DEGRADE` "
            "(default) for the per-claim fail-closed disclosed adjudication.\n",
            encoding="utf-8",
        )
        return artifact
    except Exception:  # noqa: BLE001 — a halt-artifact write failure must not mask the original fault.
        logger.warning(
            "[polaris graph] #1283: failed to write role_transport_exhausted halt artifact "
            "(the typed RoleTransportExhaustedError is still re-raised).",
            exc_info=True,
        )
        return None
from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    Gap,
    ReleaseDecision,
    ReleaseOutcome,
    apply_d8_release_policy,
    compute_release_outcome,
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

# I-run11-001 (#1042) Codex iter-2 P2.3: tiny on-disk progress marker the PARALLEL compute writes
# after EACH claim completes ({"done": k, "total": n}), so a hung mid-compute is visible on disk
# DURING compute — the role_call_log only grows during the later, parent-only reduction.
FOUR_ROLE_COMPUTE_PROGRESS_FILENAME = "four_role_compute_progress.json"


# I-arch-004 F22 (#1255, h4): HARD cap under parallel 4-role via ATOMIC budget RESERVATION.
#
# ROOT CAUSE: the prior parallel path submitted ALL claim futures up front and only re-added each
# worker's verifier spend to the parent run counter AFTER its future completed (Codex iter-2 P1.1).
# That BOUNDS the overshoot to ~(workers in flight) but is NOT a hard cap — up to `_CLAIM_WORKERS`
# claims each run (and spend) before any of their deltas reconcile into `current_run_cost()` and the
# cap fires. So a near-cap run could overshoot `PG_MAX_COST_PER_RUN` by ~workers * per-claim spend.
#
# FIX (parent-thread admission control, no new global / no lock / `RecordingTransport` untouched):
# the PARENT reserves a conservative per-claim ANTICIPATED cost BEFORE submitting a claim's worker,
# and admits a claim ONLY while
#     current_run_cost() (settled) + reserved (in-flight) + anticipated(claim) <= cap.
# A worker SETTLES on completion: the parent re-adds the worker's ACTUAL verifier delta and releases
# that claim's reservation. Because anticipated >= actual for every claim, even if EVERY in-flight
# claim bills its FULL reservation the total can never exceed the cap — a HARD cap. When a claim
# cannot fit AND nothing is in flight to free headroom, the seam raises `BudgetExceededError`
# pre-spend (fail LOUD, no silent thin — §-1.3). The SEQUENTIAL path (workers==1 / single claim) is
# UNTOUCHED and byte-identical: it keeps the live per-call `RecordingTransport` budget (soft-by-one,
# exactly as today). Flag-gated by PG_FOUR_ROLE_BUDGET_RESERVE (default ON); OFF reverts the parallel
# path to the pre-F22 submit-all + reconcile-on-completion behaviour (still bounded, not hard).
_BUDGET_RESERVE_ENABLED = os.getenv("PG_FOUR_ROLE_BUDGET_RESERVE", "1") != "0"

# I-arch-004 F22 (#1255, h4): a TRUE per-call token upper bound for the reservation, covering BOTH the
# prompt (input) and the completion+reasoning (output) sides. For any one OpenRouter call the provider
# bills `prompt + completion + reasoning` tokens, and the SUM is bounded by the model's CONTEXT WINDOW
# (the provider rejects a request whose prompt+max_completion exceeds context_length). So
# `context_tokens` is a hard ceiling on a call's TOTAL billable tokens — pricing that whole budget at
# the model's OUTPUT rate (>= its input rate for every verifier model in the price table) makes the
# per-call estimate >= the real `_impute_cost_from_tokens` for ANY in-spec call, INCLUDING a maximal
# prompt (Codex F22 iter-1 P1: the prior bound only allowed `max_tokens` worth of input, which a long
# prompt could exceed). Default 400_000 covers the largest pinned context window (deepseek-v4-pro
# 384_000 per §9.1.8 / OpenRouter `/api/v1/models`); LAW VI override for a re-pin to a larger-context
# verifier. This is a CAP on the reservation, not a token starvation — it never lowers any max_tokens.
_RESERVE_CONTEXT_TOKENS = max(1, int(os.getenv("PG_FOUR_ROLE_RESERVE_CONTEXT_TOKENS", "400000")))


def _anticipated_claim_cost(model_slugs: dict[str, str]) -> float:
    """A conservative UPPER BOUND on one claim's 4-role verifier spend, for budget RESERVATION.

    A claim runs Mirror (pass-1 + pass-2 == 2 calls), Sentinel (1) and Judge (1). For ONE call the
    provider bills `prompt + completion + reasoning` tokens, and that SUM is bounded by the model's
    CONTEXT WINDOW (`_RESERVE_CONTEXT_TOKENS`, default 400_000 — >= the largest pinned verifier context).
    Pricing the WHOLE context budget at the model's OUTPUT rate (>= its INPUT rate for every verifier
    in the price table) makes the per-call estimate >= the real `_impute_cost_from_tokens` for ANY
    in-spec call, including a maximal prompt: actual `(prompt + completion + reasoning) <= context`, and
    every one of those tokens bills at <= output_rate, so `actual_call_cost <= context * output_rate ==
    anticipated_call_cost`. Therefore anticipated >= actual per call, which is what makes the
    reservation a HARD ceiling. Uses the SAME price table / impute function the budget guard bills with
    (genuineness: the bound is not a test-known constant — LAW II). Reasoning bills at the output rate,
    so `_impute_cost_from_tokens(slug, 0, context, 0)` == context * output_rate (Opus-tier default for an
    unpriced slug — the safe, conservative direction for a budget ceiling).
    """
    # (call_count, model_slug) per role the pipeline invokes (Mirror is two calls: pass-1 + pass-2).
    legs = (
        (2, model_slugs.get("mirror", "")),
        (1, model_slugs.get("sentinel", "")),
        (1, model_slugs.get("judge", "")),
    )
    total = 0.0
    for call_count, slug in legs:
        # Price the ENTIRE context-window token budget at the slug's OUTPUT rate (the highest of its
        # input/output rates). Passing it as `output_tokens` bills it at the output rate via the impute
        # function — a single term that upper-bounds the prompt + completion + reasoning of any one call.
        per_call = _impute_cost_from_tokens(slug, 0, _RESERVE_CONTEXT_TOKENS, 0)
        total += call_count * per_call
    return total


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
    # I-perm-001 (#1195) slice 2: the always-release-aware outcome (BLOCK->LABEL). Default None
    # for legacy/timeout construction sites; the headline D8 decision (release_allowed above) is
    # unchanged, so consumers that ignore this field are byte-identical.
    release_outcome: ReleaseOutcome | None = None


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
    run_dir: Path,
    heartbeat_claims_cb=None,
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

      * PARALLEL: each claim runs inside its OWN `contextvars.copy_context()` snapshot that is taken
        ON THE PARENT THREAD BEFORE submit (Codex iter-2 P1.2 — copying inside the worker would
        snapshot the worker's EMPTY default context, so the parent Path-B capture sink
        `pathB_capture._SINK` / `_ROLE` registered by `pathB_runner` on the PARENT would be ABSENT
        and verifier capture would no-op, failing post-run completeness when workers>1). Each claim
        gets its OWN copy (never one shared copy across concurrent workers — a copy carries the
        worker's isolated `_RUN_COST_CTX` AND the parent's `_SINK` reference). The worker
        `reset_run_cost()`s its copy, runs the pipeline, and returns `current_run_cost()` as
        `cost_delta`; the PARENT re-adds it to the single run counter and enforces the cap DURING
        compute (Codex iter-2 P1.1) so overspend is bounded to the workers in-flight at breach
        (~workers-1), not all claims. The pathB capture `_SINK` is shared BY REFERENCE through the
        copied context (atomic `list.append`), so verifier captures land at the PARENT sink for the
        M4 gate — it is NOT isolated. A worker exception PROPAGATES (fail closed; no `except: pass`).
    """
    n = len(claims)

    # I-ready-017 FX-08b (#1113): CLAIM-LEVEL DEDUP (BUG-04 determinism half).
    # 4+ byte-identical claims were SPLIT VERIFIED/UNSUPPORTED in the same run
    # (a non-deterministic release gate). Two claims whose ENTIRE pipeline INPUT
    # is identical MUST get the same verdict — so run the pipeline ONCE per
    # distinct input and fan the verdict out. The key is the FULL input the
    # pipeline consumes (claim_text + evidence doc_id+text + severity +
    # s0_categories), NOT just (sentence+ids+spans): anything that could
    # legitimately change the verdict is in the key, so two genuinely-different
    # claims can NEVER collapse to one verdict (faithfulness-safe; identical
    # input => identical output is the only justification for sharing a verdict).
    # The evidence doc `text` is the FX-03 cited WINDOW, so it encodes the span.
    # Fan-out is HONEST on the audit trail + cost: a duplicate gets its OWN
    # claim_id (dataclasses.replace on d8_row), the SHARED verdict + sub-results,
    # EMPTY records (no new model calls were made for it, so all_records /
    # role_call_log are not inflated), and zero cost (cost_delta None). Coverage
    # credit still flows per-claim (each dup's covered_element_ids on its VERIFIED
    # verdict). Flag-gated (PG_FOUR_ROLE_CLAIM_DEDUP, default ON); OFF reverts to
    # the per-claim run. Recursion on representatives is one level deep (reps have
    # all-distinct keys -> this branch is skipped on the inner call).
    _dedup_enabled = os.getenv("PG_FOUR_ROLE_CLAIM_DEDUP", "1") != "0"

    def _dedup_key(c: FourRoleClaim) -> tuple:
        return (
            " ".join((c.claim_text or "").split()),
            tuple(sorted(
                (d.doc_id, d.text) for d in (c.evidence_documents or [])
            )),
            c.severity,
            tuple(sorted(c.s0_categories or [])),
        )

    if _dedup_enabled and n > 1:
        rep_idx_by_key: dict[tuple, int] = {}
        rep_indices: list[int] = []
        for idx, claim in enumerate(claims):
            k = _dedup_key(claim)
            if k not in rep_idx_by_key:
                rep_idx_by_key[k] = idx
                rep_indices.append(idx)
        if len(rep_indices) < n:
            # At least one duplicate — run the pipeline only on representatives.
            rep_results = _compute_claim_results(
                transport,
                claims=[claims[i] for i in rep_indices],
                model_slugs=model_slugs,
                timestamp=timestamp,
                run_dir=run_dir,
                heartbeat_claims_cb=heartbeat_claims_cb,  # Codex AC1-gate P2-1: dedup path too
            )
            rep_result_by_idx = {
                rep_indices[j]: rep_results[j] for j in range(len(rep_indices))
            }
            fanned: list[tuple[ClaimPipelineResult, float | None]] = []
            for idx, claim in enumerate(claims):
                rep_idx = rep_idx_by_key[_dedup_key(claim)]
                rep_res, rep_cost = rep_result_by_idx[rep_idx]
                if idx == rep_idx:
                    fanned.append((rep_res, rep_cost))
                else:
                    # Fan the verdict out to this duplicate under ITS own
                    # claim_id; no new model calls (records=[]) and no new spend
                    # (cost None) — the representative already paid + recorded.
                    dup_row = replace(rep_res.d8_row, claim_id=claim.claim_id)
                    dup_res = replace(rep_res, d8_row=dup_row, records=[])
                    fanned.append((dup_res, None))
            return fanned

    def _compute_one(
        idx: int, claim: FourRoleClaim, worker_ctx: contextvars.Context
    ) -> tuple[int, ClaimPipelineResult, float]:
        def _run() -> tuple[ClaimPipelineResult, float]:
            # Isolate THIS claim's verifier spend in the copied context so the parent can re-add a
            # clean per-claim delta and enforce the cap deterministically at the claim boundary.
            # `reset_run_cost()` zeroes ONLY this copy's `_RUN_COST_CTX`; the parent's `_SINK` /
            # `_ROLE` references carried by the same copy are untouched, so verifier capture lands
            # at the parent sink.
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

        # Run inside the PARENT-captured context snapshot (P1.2): the worker executes `_run` under
        # the parent's Path-B capture state, not the worker thread's empty default context.
        result, delta = worker_ctx.run(_run)
        return idx, result, delta

    # SEQUENTIAL fast path: byte-equivalent to the pre-#1042 loop (live per-call budget preserved,
    # cost_delta None so the parent does not re-account). A single claim also takes this path (a
    # thread pool for one item is pure overhead).
    if _CLAIM_WORKERS == 1 or n <= 1:
        out: list[tuple[ClaimPipelineResult, float | None]] = []
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
                out.append((result, None))
        except RoleTransportError as _rte:
            # I-beatboth-006 (#1283) Fix C.3 — SAME disclosed hard-halt on the SEQUENTIAL path (flag
            # OFF / unexpected propagated RTE): write the halt artifact + re-raise the TYPED error,
            # never a raw propagation. Flag-ON (default) consumes it per-claim upstream, so this fires
            # only when PG_ROLE_TRANSPORT_DEGRADE is OFF — consistent with the parallel branch below.
            _halt_artifact = _write_role_transport_halt_artifact(_rte)
            raise RoleTransportExhaustedError(
                f"D8 seam role transport exhausted ({type(_rte).__name__}: {_rte}); "
                f"PG_ROLE_TRANSPORT_DEGRADE is OFF -> disclosed hard halt "
                f"(status={_ROLE_TRANSPORT_EXHAUSTED_STATUS}).",
                status=_ROLE_TRANSPORT_EXHAUSTED_STATUS,
                halt_artifact=_halt_artifact,
            ) from _rte
        return out

    # PARALLEL path (Codex iter-2 P1.1 + P1.2; I-arch-004 F22 HARD cap): each claim is submitted with
    # its OWN parent-captured context snapshot so the worker inherits the Path-B capture sink/role
    # registered on the parent. The PARENT is the single coordinator: it submits, drains completed
    # futures via `as_completed`, re-adds each worker's per-claim verifier delta to the SINGLE parent
    # run counter, writes the progress marker, and forwards the heartbeat — ALL on the parent thread in
    # claim order. The pool is managed MANUALLY (not via `with`, whose `__exit__` waits for ALL pending
    # futures) so on a breach / worker exception we `shutdown(wait=False, cancel_futures=True)` to
    # cancel still-queued claims, then re-raise (P2.2 cancel-on-fail).
    #
    # F22 (#1255, h4) — HARD cap via ATOMIC budget RESERVATION (default ON, PG_FOUR_ROLE_BUDGET_RESERVE):
    # the PARENT reserves a conservative `_anticipated_claim_cost(...)` for a claim BEFORE submitting its
    # worker, and admits a claim ONLY while
    #     current_run_cost() (settled) + reserved (in-flight) + anticipated <= cap.
    # On settle the parent re-adds the worker's ACTUAL delta and RELEASES that claim's reservation
    # (net change to settled+reserved is actual-anticipated <= 0, so headroom only grows). Because
    # anticipated >= actual, the cap holds HARD even if every in-flight claim bills its full reservation.
    # When the next claim cannot fit AND nothing is in flight to free headroom, we raise
    # `BudgetExceededError` PRE-SPEND (fail loud, no silent thin — §-1.3). With the flag OFF the parent
    # submits ALL futures up front and reconciles cost on completion (the pre-F22 bounded-overshoot
    # behaviour); the cap then bounds overspend to ~(workers in flight), NOT a hard ceiling.
    #
    # P2.1 (aborted-run cost under-accounting — documented, not over-engineered): on a worker
    # exception the worker's partial paid spend lives in the worker's isolated copied context and is
    # NOT reconciled into the parent counter. This is the SAME accepted tradeoff the seam-timeout
    # wrapper documents (run_honest_sweep_r3.py ~L4587-4596: in-flight verifier cost on the
    # held/aborted path is not reconciled) — prompt fail-closed termination outranks exact accounting
    # on an already-aborted run, and the operator authorized the spend.
    computed: list[tuple[ClaimPipelineResult, float | None] | None] = [None] * n
    # Codex iter-2 P1 (REGRESSION FIX): the progress write below targets `run_dir`, but
    # `_compute_claim_results` runs BEFORE `VerifiedClaimGraphStore(run_dir=...)` (which is what
    # historically created `run_dir`). Existing callers (scripts/dr_benchmark/offline_e2e.py,
    # tests/dr_benchmark/test_offline_e2e.py) pass a `run_dir` that does NOT yet exist, so the
    # parallel path's progress write raised FileNotFoundError. Ensure the dir exists exactly once
    # at the TOP of the parallel branch (idempotent; the later kg_store reuses the same dir —
    # harmless). The SEQUENTIAL fast path does NOT mkdir (it writes no progress file) so it stays
    # byte-equivalent to the pre-#1042 behaviour.
    run_dir.mkdir(parents=True, exist_ok=True)
    progress_path = run_dir / FOUR_ROLE_COMPUTE_PROGRESS_FILENAME
    done = 0

    def _settle(future) -> int:
        """Drain ONE completed future on the parent thread: record the result, write the progress
        marker, re-add the worker's ACTUAL verifier delta to the single parent counter, re-check the
        cap, and forward the heartbeat. Returns the settled claim index so the reservation caller can
        release the matching reservation WITHOUT a second `future.result()`. `nonlocal done` so the
        marker counts across calls."""
        nonlocal done
        # `future.result()` re-raises any worker exception (fail closed) — handled by the caller.
        idx, result, delta = future.result()
        computed[idx] = (result, delta)
        # P2.3 + Codex iter-2 P2 (observability): write the tiny on-disk progress marker BEFORE the
        # budget enforcement below, so the just-completed claim — INCLUDING a cap-breaching one — is
        # reflected in four_role_compute_progress.json even when the very next check_run_budget(0)
        # raises. Parent-only write — never inside a worker.
        done += 1
        progress_path.write_text(
            json.dumps({"done": done, "total": n}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # Re-add this claim's verifier spend to the SINGLE parent run counter and re-check the cap.
        # With reservation ON this is the SETTLE step (the reservation for this claim is released by
        # the caller AFTER this returns); the check is a belt-and-suspenders guard — admission already
        # bounded the spend, but actual could differ and a generator pre-seed change between admit and
        # settle would still be caught.
        if delta is not None:
            _add_run_cost(delta)
            check_run_budget(0)  # raises BudgetExceededError if the cap is now exceeded.
        # I-obs-001 #1141 AC1 (Codex AC1-gate P2): forward done/total to the run-status heartbeat AFTER
        # _add_run_cost so running_cost_usd reflects the just-completed claim. Opaque callback — the
        # seam stays ignorant of the heartbeat schema; additive, never raises.
        if heartbeat_claims_cb is not None:
            try:
                heartbeat_claims_cb(done, n)
            except Exception:  # noqa: BLE001
                pass
        return idx

    pool = concurrent.futures.ThreadPoolExecutor(max_workers=_CLAIM_WORKERS)
    try:
        if not _BUDGET_RESERVE_ENABLED:
            # Legacy (flag OFF): submit ALL futures up front, reconcile cost on completion. Bounded
            # overspend (~workers in flight), NOT a hard cap. Byte-equivalent to the pre-F22 path.
            futures = [
                pool.submit(_compute_one, idx, claim, contextvars.copy_context())
                for idx, claim in enumerate(claims)
            ]
            for future in concurrent.futures.as_completed(futures):
                _settle(future)
        else:
            # HARD cap (flag ON): parent-thread admission control with budget RESERVATION + bounded
            # in-flight submission. `reserved` is the sum of anticipated costs for admitted-but-not-yet-
            # settled claims (parent-local; never touched off the parent thread). A claim is admitted
            # only while settled + reserved + anticipated <= cap AND in-flight < _CLAIM_WORKERS.
            cap = _orc.get_max_cost_per_run()
            reserved = 0.0
            # claim index -> its reserved anticipated cost (so settle releases the exact amount).
            reservation_by_idx: dict[int, float] = {}
            inflight: set = set()  # Futures submitted but not yet settled.
            next_idx = 0
            while next_idx < n or inflight:
                # Admit as many affordable claims as the cap headroom + worker slots allow.
                admitted_any = False
                while next_idx < n and len(inflight) < _CLAIM_WORKERS:
                    anticipated = _anticipated_claim_cost(model_slugs)
                    if current_run_cost() + reserved + anticipated > cap:
                        break  # cannot afford the next claim right now — fall through to wait/raise.
                    reserved += anticipated
                    reservation_by_idx[next_idx] = anticipated
                    future = pool.submit(
                        _compute_one, next_idx, claims[next_idx], contextvars.copy_context()
                    )
                    inflight.add(future)
                    next_idx += 1
                    admitted_any = True
                if inflight:
                    # Wait for the NEXT settle so its actual delta (<= its reservation) can free
                    # headroom, then re-evaluate admission.
                    done_set, _ = concurrent.futures.wait(
                        inflight, return_when=concurrent.futures.FIRST_COMPLETED
                    )
                    for future in done_set:
                        inflight.discard(future)
                        # Settle (record result, re-add the ACTUAL delta) and get the settled claim
                        # index back, then RELEASE that claim's reservation by the SAME index the
                        # admission loop keyed it on. `_settle` reads `future.result()` exactly once
                        # (Codex F22 iter-1 P2) — no second extraction here.
                        s_idx = _settle(future)
                        reserved -= reservation_by_idx.pop(s_idx, 0.0)
                elif not admitted_any and next_idx < n:
                    # Nothing in flight to free headroom AND the next claim still cannot fit -> the run
                    # budget genuinely cannot cover even a single remaining claim. Fail LOUD, pre-spend
                    # (no silent thin — §-1.3): this is the HARD cap blocking the overshoot.
                    anticipated = _anticipated_claim_cost(model_slugs)
                    raise BudgetExceededError(
                        f"PG_MAX_COST_PER_RUN cap reservation: claim index {next_idx} needs an "
                        f"anticipated ${anticipated:.4f} but only "
                        f"${cap - current_run_cost():.4f} headroom remains "
                        f"(settled=${current_run_cost():.4f}, cap=${cap:.4f}); blocked pre-spend so "
                        f"the parallel 4-role spend cannot overshoot the cap (hard ceiling)."
                    )
    except RoleTransportError as _rte:
        # I-beatboth-006 (#1283) Fix C.3 — the DISCLOSED HARD-HALT branch. With the degrade flag ON
        # (default) a force-close is consumed PER-CLAIM upstream (role_pipeline C.1 / judge_adapter
        # C.2 / sentinel_adapter) and NEVER reaches here, so the seam keeps adjudicating. A
        # `RoleTransportError` reaching `_compute_claim_results` is BY CONSTRUCTION the flag-OFF (or a
        # genuinely-unexpected) case — the three adapter `transport.complete()` calls are the only RTE
        # sources, and flag-ON each catches it. Convert it to a DISCLOSED outcome (NOT a bare
        # coverage=0 teardown): write the `state/halt_*_role_transport_exhausted.md` artifact, tear the
        # pool down NON-BLOCKING (same P2.2 cleanup as the broad arm), then re-raise a TYPED
        # `RoleTransportExhaustedError` carrying the `abort_role_transport_exhausted` status + artifact
        # path. Faithfulness untouched — this is the disclosure/halt path only.
        _halt_artifact = _write_role_transport_halt_artifact(_rte)
        pool.shutdown(wait=False, cancel_futures=True)
        raise RoleTransportExhaustedError(
            f"D8 seam role transport exhausted ({type(_rte).__name__}: {_rte}); "
            f"PG_ROLE_TRANSPORT_DEGRADE is OFF -> disclosed hard halt "
            f"(status={_ROLE_TRANSPORT_EXHAUSTED_STATUS}).",
            status=_ROLE_TRANSPORT_EXHAUSTED_STATUS,
            halt_artifact=_halt_artifact,
        ) from _rte
    except BaseException:
        # On ANY OTHER failure (BudgetExceededError from the cap OR a propagated worker exception)
        # cancel still-pending claims and tear the pool down NON-BLOCKING (P2.2), then re-raise so the
        # existing budget-abort / fail-closed path in run_four_role_evaluation handles it. No
        # `except: pass` — the error always propagates.
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    else:
        pool.shutdown(wait=True)

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
    heartbeat_claims_cb=None,
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
    # Codex iter-2 P1.1: the PARALLEL path now ENFORCES the run-budget cap DURING compute (each
    # claim's delta is re-added to the parent counter and the cap re-checked as its future
    # completes), so a cap breach raises after only ~(workers-in-flight) claims have spent — the
    # reduction below NO LONGER re-adds `cost_delta` (it would double-count). `cost_delta` is kept
    # in the returned tuples for audit only.
    computed: list[tuple[ClaimPipelineResult, float | None]] = _compute_claim_results(
        transport,
        claims=claims,
        model_slugs=model_slugs,
        timestamp=timestamp,
        run_dir=run_dir,
        heartbeat_claims_cb=heartbeat_claims_cb,
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
        # Codex iter-2 P1.1: the run-budget cap is now enforced DURING compute inside
        # `_compute_claim_results` (parallel path) — the per-claim `cost_delta` was ALREADY re-added
        # to the parent counter and the cap re-checked there. This reduction is therefore PARENT-only
        # and budget-NEUTRAL: it touches ONLY d8_rows / all_records / final_verdicts / role_call_log /
        # coverage / kg_store.write_claim / the incremental log. `cost_delta` is retained in the tuple
        # for audit but is NOT re-added here (re-adding would double-count the verifier spend).
        for claim, (result, _cost_delta) in zip(claims, computed):
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

    # I-perm-001 (#1195) slice 2: compute the always-release-aware outcome HERE, where the
    # required-S0 set + the per-claim verdicts are natively available. `compute_release_outcome`
    # reads PG_ALWAYS_RELEASE (default OFF -> released == decision.release_allowed, byte-identical).
    _final = final_verdicts or {}
    _zero_verified = not any(v == "VERIFIED" for v in _final.values())
    # zero_usable_evidence = the NATIVE evidence signal (Codex slice-2 P1): no claim cites ANY
    # evidence document. `not final_verdicts` (no claims) was too weak — a claims-present-but-
    # all-unsupported run with no cited evidence must still zero-grounding hard-block. Mirrors the
    # replay harness's audit_map evidence_ids signal.
    _zero_usable_evidence = not any((c.evidence_documents or []) for c in claims)
    _missing_s0 = {
        reason[len("d8_s0_must_cover_missing:"):]
        for reason in decision.held_reasons
        if reason.startswith("d8_s0_must_cover_missing:")
    }
    _required_s0 = set(required_s0_categories)
    _safety_floor_insufficient = bool(_required_s0) and _required_s0 <= _missing_s0
    # B5/B7 (operator-ratified 2026-06-14): the FABRICATED narrowing (ship-minus-the-claim instead
    # of whole-report block) is SAFE only because the report_redactor excises the fabricated claim's
    # prose. The redactor is gated by PG_REDACT_HELD_UNSUPPORTED (default ON; the kill-switch is
    # "0"/"false"/"False" for offline-test isolation only — same predicate as the runner at the
    # reconcile_report_against_verdicts call site). When redaction is OFF, FABRICATED stays a hard
    # block (is_hard_block) so a fabricated claim can never ship as asserted prose.
    _redaction_active = os.environ.get("PG_REDACT_HELD_UNSUPPORTED", "1").strip() not in (
        "0", "false", "False",
    )
    release_outcome = compute_release_outcome(
        decision,
        zero_verified=_zero_verified,
        zero_usable_evidence=_zero_usable_evidence,
        safety_floor_insufficient=_safety_floor_insufficient,
        coverage_fraction=internal_ledger.fraction(),
        redaction_active=_redaction_active,
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
        release_outcome=release_outcome,
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
    heartbeat_claims_cb=None,
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
            heartbeat_claims_cb=heartbeat_claims_cb,
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
        heartbeat_claims_cb=heartbeat_claims_cb,
    )
