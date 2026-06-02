"""I-meta-008 (#1015) — 4-role verifier spend is bounded by the SAME PG_MAX_COST_PER_RUN cap
the generator uses. Offline, fake transport, NO network, NO real LLM, NO spend.

ROOT CAUSE under test: before this fix, the three 4-role verifier calls (Mirror / Sentinel /
Judge) ran through `OpenRouterRoleTransport` (raw httpx) whose `RoleResponse.usage` was never
threaded into the run-budget accumulator (`check_run_budget` / `_add_run_cost`). So verifier
spend was UNCOUNTED and `PG_MAX_COST_PER_RUN` could not bite on it. The fix accounts each
verifier completion's cost at the single per-call chokepoint
(`role_pipeline.RecordingTransport.complete`) into the shared `_RUN_COST_CTX`, raising
`BudgetExceededError` before the next paid verifier call once generator + verifier cross the cap.

These tests prove:
  * Test A — verifier usage drives the SHARED accumulator (pre-seeded with a near-cap GENERATOR
    cost) past the cap -> `BudgetExceededError` raised at the seam (generator + verifier bounded
    TOGETHER). Exercises the nested `completion_tokens_details.reasoning_tokens` path (the
    dominant Mirror/Judge cost) so the reasoning-token accounting is verified.
  * Test B — `usage=None` (the existing mock-suite shape) floors SMALL and does NOT raise; the
    regression guard for `tests/roles` + `tests/dr_benchmark` + the I-bug-100 P2 floor (each call
    costs a small NON-zero amount, never $0.0).
  * Test C — the Sentinel fail-closed `except` does NOT swallow `BudgetExceededError` (the §2.3
    BLOCKING guard). ROLE-AWARE fake: Mirror/Judge cost ~nothing, the cap is crossed EXACTLY at
    the Sentinel call, and the budget error must PROPAGATE (not degrade to a fail-closed
    UNGROUNDED `SentinelResult`).
  * Test D — `compute_role_call_cost` unit behavior: the NON-EMPTY all-zero usage block is
    floored (Codex design-review P1 #1 — the prior `cost==0.0 and not usage` only caught
    None/{}), nested reasoning bills at the output rate, `usage["cost"]` present takes
    `max(cost, imputed)`.

Cap monkeypatching: per the design, patch the MODULE ATTRIBUTE
`openrouter_client.PG_MAX_COST_PER_RUN` (the constant is import-time, NOT re-read from env) with
`monkeypatch.setattr` — NEVER `importlib.reload`, which would create a fresh `_RUN_COST_CTX` +
module object the seam's `_orc` reference would not share. `reset_run_cost()` is called at the
TOP of every test because `_RUN_COST_CTX` persists across synchronous tests in one process.
"""

from __future__ import annotations

import pytest

import src.polaris_graph.llm.openrouter_client as openrouter_client
from src.polaris_graph.llm.openrouter_client import BudgetExceededError
from src.polaris_graph.roles import role_pipeline
from src.polaris_graph.roles.release_policy import CoverageLedger
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sentinel_contract import SentinelVerdict
from src.polaris_graph.roles.sweep_integration import (
    FourRoleClaim,
    FourRoleEvaluationInputs,
    run_four_role_seam,
)

_TIMESTAMP = "2026-05-29T00:00:00Z"
_MODEL_SLUGS = {
    "mirror": "cohere/command-a-plus",
    "sentinel": "ibm-granite/granite-guardian-4.1-8b",
    "judge": "qwen/qwen3.6-35b-a3b",
}


def _static_inputs() -> FourRoleEvaluationInputs:
    """One releasable claim driven through the static (no-builder) seam path — same shape as
    `test_gate_b_seam.test_seam_static_inputs_used_as_is_no_audit`."""
    return FourRoleEvaluationInputs(
        claims=[
            FourRoleClaim(
                claim_id="s-1",
                claim_text="The dose is 5.0 mg.",
                evidence_documents=[
                    EvidenceDocument(doc_id="doc1", text="The trial reported a 5.0 mg dose.")
                ],
                severity="S0",
                s0_categories=["contraindications"],
                covered_element_ids=["elem-1"],
            )
        ],
        coverage_ledger=CoverageLedger(required_element_ids=["elem-1"]),
        required_s0_categories=["contraindications"],
        model_slugs=_MODEL_SLUGS,
        rewrite_already_attempted=True,
    )


class _FakeRoleTransport:
    """Canned in-process `RoleTransport` — NO network, NO spend.

    Mirror pass-1 returns a grounded `<co>`-equivalent citation on the claim's first doc_id;
    pass-2 echoes the embedded content_hash; Sentinel returns GROUNDED; Judge returns VERIFIED.
    `usage_for_role` (role -> usage dict) drives the per-call cost; a role absent from the map
    yields `usage=None` (the floored-small path). `completions` counts in-process completions
    (NEVER a socket).
    """

    def __init__(self, usage_for_role: dict[str, dict | None] | None = None) -> None:
        self._usage_for_role = usage_for_role or {}
        self.completions = 0

    def complete(self, request: RoleRequest) -> RoleResponse:
        self.completions += 1
        usage = self._usage_for_role.get(request.role)
        if request.role == "mirror":
            if "pass2_input" in (request.params or {}):
                import json

                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(
                    raw_text=json.dumps(payload),
                    served_model=request.model_slug,
                    usage=usage,
                )
            from src.polaris_graph.roles.mirror_contract import CitationSpan

            documents = (request.params or {}).get("documents") or []
            doc_id = documents[0]["doc_id"] if documents else "doc1"
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=(doc_id,))],
                usage=usage,
            )
        if request.role == "sentinel":
            return RoleResponse(
                raw_text="<score>no</score>", served_model=request.model_slug, usage=usage
            )
        if request.role == "judge":
            return RoleResponse(
                raw_text="VERIFIED", served_model=request.model_slug, usage=usage
            )
        raise AssertionError(f"unexpected role {request.role!r}")


def _run_seam(transport, run_dir):
    return run_four_role_seam(
        transport,
        run_dir=run_dir,
        timestamp=_TIMESTAMP,
        four_role_inputs=_static_inputs(),
    )


# --- Test A: verifier usage tips the SHARED (generator + verifier) accumulator past the cap ----
def test_verifier_usage_drives_shared_accumulator_past_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.05)
    openrouter_client.reset_run_cost()
    # Pre-seed a near-cap GENERATOR cost: this is what proves "generator + verifier are bounded
    # together" — the verifier delta is what tips the SHARED counter over.
    openrouter_client._add_run_cost(0.04)

    # A large reasoning block (NESTED under completion_tokens_details, the dominant Mirror/Judge
    # cost) on the FIRST verifier call (Mirror pass-1) so the very first completion crosses the
    # remaining $0.01 headroom. qwen judge slug not used here; the mirror slug
    # cohere/command-a-plus has no price-table row -> Opus-tier default ($15/M output), so
    # ~200k reasoning tokens ~= $3.0 >> headroom.
    tipping_usage = {
        "prompt_tokens": 1000,
        "completion_tokens": 1000,
        "completion_tokens_details": {"reasoning_tokens": 200_000},
    }
    transport = _FakeRoleTransport(usage_for_role={"mirror": tipping_usage})

    with pytest.raises(BudgetExceededError):
        _run_seam(transport, tmp_path)
    # The breach fired (the accumulator went past the cap); the served-identity record for the
    # breaching call was appended BEFORE the cost check raised.
    assert openrouter_client.current_run_cost() > 0.05


# --- Test B: usage=None floors SMALL and does NOT raise (regression guard for the mock suite) ---
def test_usage_none_floors_small_does_not_raise(monkeypatch, tmp_path):
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 5.00)
    openrouter_client.reset_run_cost()
    # No pre-seed; every role returns usage=None -> each call floors at ~$0.003. Across
    # Mirror(x2) + Sentinel + Judge (~$0.012) this stays far under the 5.00 cap -> no raise.
    transport = _FakeRoleTransport(usage_for_role=None)
    result = _run_seam(transport, tmp_path)
    # Completed without raising; the existing roles/seam suite (usage=None) is unaffected.
    assert result.release_allowed is True
    assert transport.completions > 0
    # The I-bug-100 P2 floor is in effect: the usage-less calls cost a small NON-zero amount,
    # NOT $0.0 (a $0 bill would silently slip the cap on a degraded LIVE response).
    assert openrouter_client.current_run_cost() > 0.0


# --- Test C: the Sentinel fail-closed except does NOT swallow BudgetExceededError --------------
def test_sentinel_does_not_swallow_budget_error(monkeypatch, tmp_path):
    monkeypatch.setattr(openrouter_client, "PG_MAX_COST_PER_RUN", 0.05)
    openrouter_client.reset_run_cost()
    # ROLE-AWARE trap avoidance: Mirror runs FIRST (pass-1, pass-2). If Mirror's calls crossed
    # the cap, the raise would fire at MIRROR and the test would pass WITHOUT exercising the
    # Sentinel guard (false confidence — the exact trap the design §2.3 Test C warned about).
    # So Mirror+Judge return ZERO usage (floored ~$0.003/call => Mirror x2 == ~$0.006) and ONLY
    # the Sentinel call carries the tipping usage. Pre-seed $0.04 so that after Mirror x2 the
    # total is ~$0.046 (UNDER the $0.05 cap -> Mirror does NOT raise) and the cap is crossed
    # EXACTLY at the Sentinel call (~$0.046 + ~$1.51 >> $0.05). Asserted via `completions == 3`.
    openrouter_client._add_run_cost(0.04)
    # Sentinel slug ibm-granite/... has no price-table row -> Opus-tier default ($15/M output).
    # ~100k reasoning tokens ~= $1.5 >> the remaining ~$0.005 headroom.
    sentinel_tipping = {
        "prompt_tokens": 500,
        "completion_tokens": 500,
        "completion_tokens_details": {"reasoning_tokens": 100_000},
    }
    # Mirror + Judge get explicit zero usage (floored small, well under the headroom so they do
    # NOT cross the cap); only Sentinel tips it.
    transport = _FakeRoleTransport(
        usage_for_role={
            "mirror": {"prompt_tokens": 0, "completion_tokens": 0},
            "judge": {"prompt_tokens": 0, "completion_tokens": 0},
            "sentinel": sentinel_tipping,
        }
    )
    # WITHOUT the typed re-raise in sentinel_adapter.py, the broad fail-closed except converts the
    # BudgetExceededError into an UNGROUNDED SentinelResult and this raises NOTHING — the cap
    # would be defeated on the Sentinel path. With the guard, the budget error propagates.
    with pytest.raises(BudgetExceededError):
        _run_seam(transport, tmp_path)
    # Lock that the breach fired AT the Sentinel call (3rd completion: Mirror pass-1, pass-2,
    # THEN Sentinel) — not earlier at a Mirror call (which would NOT exercise the swallow guard).
    assert transport.completions == 3


# --- Test D: compute_role_call_cost unit behavior (the floor + extraction precision) -----------
def test_compute_role_call_cost_floors_nonempty_all_zero_usage():
    # Codex design-review P1 #1: the PRIOR `cost==0.0 and not usage` only caught None/{}; a
    # NON-EMPTY all-zero usage block (e.g. {"prompt_tokens": 0, ...}) would record $0 and slip the
    # cap. The token-level floor closes that hole.
    cost = role_pipeline.compute_role_call_cost(
        "ibm-granite/granite-guardian-4.1-8b",
        {"prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0},
    )
    assert cost > 0.0  # floored, NOT $0.0


def test_compute_role_call_cost_floors_none_and_empty():
    assert role_pipeline.compute_role_call_cost("qwen/qwen3-32b", None) > 0.0
    assert role_pipeline.compute_role_call_cost("qwen/qwen3-32b", {}) > 0.0


def test_compute_role_call_cost_bills_nested_reasoning_at_output_rate():
    # qwen/qwen3-32b output rate is $0.60/M; 1_000_000 reasoning tokens (nested) ~= $0.60.
    cost = role_pipeline.compute_role_call_cost(
        "qwen/qwen3-32b",
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "completion_tokens_details": {"reasoning_tokens": 1_000_000},
        },
    )
    assert cost == pytest.approx(0.60, rel=1e-6)


def test_compute_role_call_cost_takes_max_of_api_cost_and_imputed():
    # api cost present and LARGER than the imputed token cost -> max() picks api cost.
    usage = {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.5}
    cost = role_pipeline.compute_role_call_cost("qwen/qwen3-32b", usage)
    assert cost == pytest.approx(0.5)
    # api cost present but SMALLER than imputed -> max() picks imputed (conservative direction).
    usage_small_api = {
        "prompt_tokens": 0,
        "completion_tokens": 1_000_000,
        "cost": 0.01,
    }  # imputed = $0.60 at qwen output rate
    cost2 = role_pipeline.compute_role_call_cost("qwen/qwen3-32b", usage_small_api)
    assert cost2 == pytest.approx(0.60, rel=1e-6)


# --- Cross-check: SentinelVerdict import is wired (lint-proof: assert the swallow target type) --
def test_sentinel_verdict_enum_present():
    # Documents WHAT the swallow guard prevents: a BudgetExceededError must NOT become an
    # UNGROUNDED SentinelResult. (Type-presence sanity; the behavioral lock is Test C.)
    assert SentinelVerdict.UNGROUNDED is not None
