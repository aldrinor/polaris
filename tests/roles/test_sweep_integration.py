"""Sweep-side 4-role evaluation tests (I-meta-002 sub-PR-6). Offline, mock transport, NO network.

Exercises `sweep_integration.run_four_role_evaluation`: the per-claim pipeline feeding the
SINGLE binding D8 gate, the fail-closed guards (no synthesized/blank/duplicate claim_ids, no
vacuous pass over an empty claim set or empty canonical denominator), the snowball KG written
under a temp run_dir, and the clinical-safety property that a Sentinel-UNGROUNDED claim cannot
make `release_allowed` True even when the Judge says VERIFIED. Every completion is canned by a
mock `RoleTransport`; there is NO real LLM call and NO spend.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from src.polaris_graph.roles.mirror_contract import CitationSpan
from src.polaris_graph.roles.release_policy import CoverageLedger
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sweep_integration import (
    FOUR_ROLE_ROLE_CALLS_FILENAME,
    FourRoleClaim,
    build_evaluator_agrees_map,
    evaluator_agrees_from_verdict,
    run_four_role_evaluation,
)

_MODEL_SLUGS = {
    "mirror": "cohere/command-a-plus",
    "sentinel": "ibm-granite/granite-guardian-4.1-8b",
    "judge": "qwen/qwen3.6-35b-a3b",
}
_TIMESTAMP = "2026-05-29T00:00:00Z"
_REQUIRED_S0 = ["contraindications"]


class MockTransport:
    """Configurable mock `RoleTransport` keyed on the request role + Mirror pass.

    Mirror pass-1 returns a managed-path grounded citation span on `doc1` (so Mirror does NOT
    fail closed); pass-2 echoes the embedded content_hash so `verify_pass2_binding` holds.
    Sentinel returns `<score>no</score>` (GROUNDED) or `<score>yes</score>` (UNGROUNDED). Judge
    returns the configured verdict token. No network.
    """

    def __init__(self, *, sentinel_grounded: bool = True, judge_verdict: str = "VERIFIED") -> None:
        self._sentinel_grounded = sentinel_grounded
        self._judge_verdict = judge_verdict

    def complete(self, request: RoleRequest) -> RoleResponse:
        if request.role == "mirror":
            if "pass2_input" in request.params:
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "supported"}
                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[CitationSpan(span_start=0, span_end=8, doc_ids=("doc1",))],
            )
        if request.role == "sentinel":
            score = "no" if self._sentinel_grounded else "yes"
            return RoleResponse(raw_text=f"<score>{score}</score>", served_model=request.model_slug)
        if request.role == "judge":
            return RoleResponse(raw_text=self._judge_verdict, served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


def _claim(claim_id: str = "claim-1", *, severity: str = "S0", covers=None, s0=None) -> FourRoleClaim:
    return FourRoleClaim(
        claim_id=claim_id,
        claim_text="The dose is 5.0 mg.",
        evidence_documents=[EvidenceDocument(doc_id="doc1", text="The trial reported a 5.0 mg dose.")],
        severity=severity,
        s0_categories=s0 if s0 is not None else ["contraindications"],
        covered_element_ids=covers if covers is not None else ["elem-1"],
    )


def _ledger(required=("elem-1",)) -> CoverageLedger:
    return CoverageLedger(required_element_ids=list(required))


def _run(transport, claims, *, run_dir, ledger=None, rewrite_attempted=True):
    return run_four_role_evaluation(
        transport,
        claims=claims,
        run_dir=run_dir,
        timestamp=_TIMESTAMP,
        coverage_ledger=ledger if ledger is not None else _ledger(),
        required_s0_categories=_REQUIRED_S0,
        model_slugs=_MODEL_SLUGS,
        rewrite_already_attempted=rewrite_attempted,
    )


# --- happy path: grounded + VERIFIED claim covers the only required element + S0 -> release ---
def test_grounded_verified_claim_releases(tmp_path) -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="VERIFIED")
    result = _run(transport, [_claim()], run_dir=tmp_path)
    assert result.release_allowed is True
    assert result.held_reasons == []
    assert result.final_verdicts == {"claim-1": "VERIFIED"}
    assert result.coverage_fraction == pytest.approx(1.0)


# --- CLINICAL-SAFETY: a Sentinel-UNGROUNDED claim cannot release even with Judge=VERIFIED ---
def test_sentinel_ungrounded_claim_cannot_release(tmp_path) -> None:
    transport = MockTransport(sentinel_grounded=False, judge_verdict="VERIFIED")
    result = _run(transport, [_claim()], run_dir=tmp_path)
    # The composed verdict is downgraded to UNSUPPORTED (sentinel UNGROUNDED overrides VERIFIED).
    assert result.final_verdicts["claim-1"] == "UNSUPPORTED"
    # It therefore credits NO coverage -> below threshold -> D8 holds release.
    assert result.release_allowed is False
    assert result.held_reasons, "an UNGROUNDED-downgraded claim must hold release"
    # And evaluator_agrees would be False for that sentence (never True on a non-VERIFIED claim).
    assert evaluator_agrees_from_verdict(result.final_verdicts["claim-1"]) is False


# --- Codex sub-PR-6 diff P1: a PREFILLED coverage numerator is rejected (no pre-credited ride) ---
def test_prefilled_coverage_ledger_rejected(tmp_path) -> None:
    """A caller-supplied ledger whose covered_element_ids is already populated would let an
    ungrounded/downgraded claim ride pre-credited coverage and release. The numerator MUST be
    rebuilt internally from VERIFIED finals only, so a non-empty incoming covered set fails loud
    (the lethal-safety invariant: a Sentinel-UNGROUNDED claim can never ride prefilled coverage)."""
    transport = MockTransport(sentinel_grounded=False, judge_verdict="VERIFIED")
    prefilled = CoverageLedger(required_element_ids=["elem-1"], covered_element_ids={"elem-1"})
    with pytest.raises(ValueError, match="covered_element_ids must be EMPTY"):
        _run(transport, [_claim()], run_dir=tmp_path, ledger=prefilled)


# --- D8 is the binding gate: a FABRICATED claim latches the occurrence gate -> held ---
def test_fabricated_claim_latches_release_hold(tmp_path) -> None:
    transport = MockTransport(sentinel_grounded=True, judge_verdict="FABRICATED")
    result = _run(transport, [_claim()], run_dir=tmp_path)
    assert result.release_allowed is False
    assert result.fabricated_occurrence_latched is True


# --- fail-closed: a blank claim_id is rejected (never synthesized) ---
def test_blank_claim_id_fails_loud(tmp_path) -> None:
    transport = MockTransport()
    with pytest.raises(ValueError, match="blank claim_id"):
        _run(transport, [_claim(claim_id="   ")], run_dir=tmp_path)


# --- fail-closed: duplicate claim_ids collide rewrite/gap traceability -> rejected ---
def test_duplicate_claim_id_fails_loud(tmp_path) -> None:
    transport = MockTransport()
    with pytest.raises(ValueError, match="duplicate claim_id"):
        _run(transport, [_claim(claim_id="dup"), _claim(claim_id="dup")], run_dir=tmp_path)


# --- fail-closed: an empty claim set is NOT a vacuous pass ---
def test_empty_claim_set_fails_loud(tmp_path) -> None:
    transport = MockTransport()
    with pytest.raises(ValueError, match="no claims"):
        _run(transport, [], run_dir=tmp_path)


# --- fail-closed: an empty canonical required-element denominator is NOT a vacuous pass ---
def test_empty_coverage_denominator_fails_loud(tmp_path) -> None:
    transport = MockTransport()
    with pytest.raises(ValueError, match="required_element_ids is empty"):
        _run(transport, [_claim()], run_dir=tmp_path, ledger=CoverageLedger(required_element_ids=[]))


# --- fail-closed: a missing role slug is rejected before any pipeline call ---
def test_missing_role_slug_fails_loud(tmp_path) -> None:
    transport = MockTransport()
    with pytest.raises(ValueError, match="missing required role slug"):
        run_four_role_evaluation(
            transport,
            claims=[_claim()],
            run_dir=tmp_path,
            timestamp=_TIMESTAMP,
            coverage_ledger=_ledger(),
            required_s0_categories=_REQUIRED_S0,
            model_slugs={"mirror": "cohere/command-a-plus", "sentinel": "x"},  # no judge
        )


# --- the snowball KG is written under the temp run_dir; only VERIFIED rows are reusable ---
def test_kg_written_and_only_verified_reusable(tmp_path) -> None:
    transport = MockTransport(sentinel_grounded=False, judge_verdict="VERIFIED")  # -> UNSUPPORTED
    result = _run(transport, [_claim()], run_dir=tmp_path)
    assert result.kg_path.exists()
    assert result.kg_path.parent == tmp_path
    conn = sqlite3.connect(str(result.kg_path))
    try:
        rows = conn.execute(
            "SELECT verdict, reusable FROM verified_claims"
        ).fetchall()
    finally:
        conn.close()
    # The single claim is persisted (audit) as UNSUPPORTED and is NOT reusable (anti-poisoning).
    assert rows == [("UNSUPPORTED", 0)]


# --- coverage credit is gated on VERIFIED: a non-VERIFIED claim contributes nothing ---
def test_coverage_credit_only_on_verified(tmp_path) -> None:
    # Two required elements; only the VERIFIED claim covers its element.
    ledger = CoverageLedger(required_element_ids=["elem-1", "elem-2"])
    verified = _claim(claim_id="ok", covers=["elem-1"], s0=["contraindications"])
    # A second claim whose Sentinel is UNGROUNDED -> UNSUPPORTED -> no coverage for elem-2.
    bad = FourRoleClaim(
        claim_id="bad",
        claim_text="A different unrelated dosing statement.",
        evidence_documents=[EvidenceDocument(doc_id="doc1", text="x")],
        severity="S1",
        s0_categories=[],
        covered_element_ids=["elem-2"],
    )

    class _Mixed(MockTransport):
        def complete(self, request: RoleRequest) -> RoleResponse:
            # Sentinel UNGROUNDED only for the 'bad' claim's evidence text.
            if request.role == "sentinel":
                docs = request.params.get("documents", [])
                grounded = not any(d.get("text") == "x" for d in docs)
                score = "no" if grounded else "yes"
                return RoleResponse(raw_text=f"<score>{score}</score>", served_model=request.model_slug)
            return super().complete(request)

    result = _run(_Mixed(judge_verdict="VERIFIED"), [verified, bad], run_dir=tmp_path, ledger=ledger)
    assert result.final_verdicts == {"ok": "VERIFIED", "bad": "UNSUPPORTED"}
    # Only elem-1 credited; elem-2 uncovered -> fraction 0.5 < 0.70 -> held.
    assert result.coverage_fraction == pytest.approx(0.5)
    assert result.release_allowed is False


# --- I-meta-002 PR-9/M5: build_evaluator_agrees_map §-1.1 safe-rule ---------------------------
# evaluator_agrees = (claim kept) AND (final_verdict == "VERIFIED"); every other verdict -> False;
# empty -> {}; a not-kept claim_id -> False even if VERIFIED. Audit metadata only (no release gate).


def test_evaluator_agrees_map_true_only_for_verified() -> None:
    """Across the full verdict alphabet, ONLY the VERIFIED claim maps to True; every other
    verdict — PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE and an unknown string — is False."""
    final_verdicts = {
        "c-verified": "VERIFIED",
        "c-partial": "PARTIAL",
        "c-unsupported": "UNSUPPORTED",
        "c-fabricated": "FABRICATED",
        "c-unreachable": "UNREACHABLE",
        "c-unknown": "SOMETHING_ELSE",
    }
    agrees = build_evaluator_agrees_map(final_verdicts)
    assert agrees == {
        "c-verified": True,
        "c-partial": False,
        "c-unsupported": False,
        "c-fabricated": False,
        "c-unreachable": False,
        "c-unknown": False,
    }
    # Keys are EXACTLY final_verdicts keys (joinable to four_role_claim_audit.json).
    assert set(agrees) == set(final_verdicts)


def test_evaluator_agrees_map_empty_is_empty_dict() -> None:
    """An empty final_verdicts yields {} (no error; upstream guards handle empty claim sets)."""
    assert build_evaluator_agrees_map({}) == {}


def test_evaluator_agrees_map_not_kept_is_false_even_if_verified() -> None:
    """The defensive kept-gate: a VERIFIED claim_id ABSENT from kept_claim_ids maps to False, and
    a kept VERIFIED claim maps to True. This proves the kept-set actually gates the boolean — a
    helper that ignored kept_claim_ids would still pass the verdict-mapping test above."""
    final_verdicts = {"kept-ok": "VERIFIED", "dropped-but-verified": "VERIFIED"}
    agrees = build_evaluator_agrees_map(final_verdicts, kept_claim_ids={"kept-ok"})
    assert agrees == {"kept-ok": True, "dropped-but-verified": False}


def test_evaluator_agrees_map_none_kept_set_treats_all_as_kept() -> None:
    """kept_claim_ids=None treats ALL claim_ids as kept (the sweep-path invariant: final_verdicts
    is built from KEPT/is_verified sentences only). It must NOT collapse to an empty set."""
    final_verdicts = {"a": "VERIFIED", "b": "UNSUPPORTED"}
    assert build_evaluator_agrees_map(final_verdicts, kept_claim_ids=None) == {
        "a": True,
        "b": False,
    }


def test_evaluator_agrees_map_extra_kept_id_does_not_add_key() -> None:
    """A claim_id present in kept_claim_ids but ABSENT from final_verdicts must NOT appear in the
    map; kept_claim_ids only affects the boolean value, never the key set (joinability invariant)."""
    agrees = build_evaluator_agrees_map(
        {"only-claim": "VERIFIED"}, kept_claim_ids={"only-claim", "ghost-id"}
    )
    assert agrees == {"only-claim": True}


# --- I-meta-002-q1b (#939): verifier reasoning persists to four_role_role_calls.jsonl, SEPARATE
# from the verdict (the verifiers' analogue of the generator's reasoning_trace.jsonl) ----------


class _ReasoningMock(MockTransport):
    """A MockTransport whose every role response carries a per-role `reasoning` string, so the
    seam's persistence of reasoning-apart-from-verdict can be asserted end-to-end (no network)."""

    def complete(self, request: RoleRequest) -> RoleResponse:
        response = super().complete(request)
        response.reasoning = f"{request.role} weighed the evidence"
        return response


def test_four_role_role_calls_jsonl_separates_reasoning_from_verdict(tmp_path) -> None:
    transport = _ReasoningMock(sentinel_grounded=True, judge_verdict="VERIFIED")
    _run(transport, [_claim()], run_dir=tmp_path)

    log_path = tmp_path / FOUR_ROLE_ROLE_CALLS_FILENAME
    assert log_path.exists(), "the per-role-call reasoning log must be written next to the run"
    lines = [ln for ln in log_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, "at least one verifier call must be logged for the single claim"

    roles_seen = set()
    for line in lines:
        entry = json.loads(line)
        # reasoning is its OWN field — present and NEVER concatenated into the bare verdict.
        assert entry["reasoning"] == f"{entry['role']} weighed the evidence"
        assert entry["reasoning"] not in entry["raw_text"]
        assert "<think>" not in entry["raw_text"]
        assert entry["claim_id"] == "claim-1"
        assert entry["served_model"] == _MODEL_SLUGS[entry["role"]]
        roles_seen.add(entry["role"])
    # All three verifier roles ran and were logged for the claim.
    assert roles_seen == {"mirror", "sentinel", "judge"}
