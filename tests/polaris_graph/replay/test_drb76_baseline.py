"""I-perm-009 proof ledger — drb_76 baseline locks + fix-target asserts.

OFFLINE on the committed saved run ``outputs/audits/beatboth8/drb_76/`` (no network, no spend,
no model calls). The proof ledger for the permanent-fix program:

* BASELINE-LOCK tests prove the offline replay reproduces the real run's D8 decision exactly.
* The §-1.1 ZERO-FABRICATION test + its adversarial unit tests prove the numeric invariant has
  no substring/sign/operator false-negative (the clinical-safety load-bearing check) and never
  passes vacuously on a missing audit pack.
* The I-perm-002 HONEST-FINDING test proves, with the FAITHFUL production S0 content-requirement
  matcher, that a naive corpus-wide evidence_id credit does NOT clear the false contraindications
  hold (the VERIFIED Safety claims lack the literal token ``contraindicated``) — so the real fix
  needs semantic recognition or the always-release relabel.
* The PRODUCTION-FLIP test is xfail(strict) — the ledger entry that flips when I-perm-002/001 land.
"""

from __future__ import annotations

import pytest

from tests.polaris_graph.replay.cited_span_audit import (
    AuditPackMissingClaimsError,
    _numeric_exprs,
    audit_cited_spans,
)
from tests.polaris_graph.replay.d8_replay_harness import replay_d8, verified_claims_citing
from tests.polaris_graph.replay.saved_run_loader import load_saved_run

# Locked drb_76 baseline (the real run's recorded four_role_evaluation).
_BASELINE_HELD_REASONS = {
    "d8_unsupported_residual_below_coverage",
    "d8_s0_must_cover_missing:contraindications",
    "d8_pending_rewrite",
}
_BASELINE_COVERAGE = 0.40
_BASELINE_NEEDS_REWRITE = 10
_CONTRAINDICATIONS_HOLD = "d8_s0_must_cover_missing:contraindications"
_CONTRAINDICATION_EVIDENCE = "probiotic_immunocompromised_contraindication"


@pytest.fixture(autouse=True)
def _legacy_off_for_baseline_lock(monkeypatch):
    """B5/B7 (2026-06-14): PG_ALWAYS_RELEASE default is now ON. These BASELINE-LOCK tests must
    reproduce the saved drb_76 run's D8 *decision* exactly — and that run was recorded under the
    legacy default-OFF (so ``d8_pending_rewrite`` is in its held_reasons). `apply_d8_release_policy`
    reads `always_release_enabled()` for the pending-rewrite block; pin the explicit OFF token so
    the replay faithfully reproduces the recorded baseline. The always-release RELABEL of this same
    run is covered separately in test_iperm001_release.py (which passes always_release explicitly)."""
    monkeypatch.setenv("PG_ALWAYS_RELEASE", "0")


@pytest.fixture(scope="module")
def saved_run():
    return load_saved_run()


# --- BASELINE-LOCK: the offline replay is faithful to the real run --------------------------


def test_baseline_lock_reproduces_held_reasons(saved_run):
    result = replay_d8(saved_run, corpus_satisfaction=False)
    assert set(result.decision.held_reasons) == _BASELINE_HELD_REASONS
    assert set(result.decision.held_reasons) == set(saved_run.saved_held_reasons)


def test_baseline_lock_coverage_fraction(saved_run):
    result = replay_d8(saved_run, corpus_satisfaction=False)
    assert result.coverage_fraction == pytest.approx(_BASELINE_COVERAGE)
    assert result.coverage_fraction == pytest.approx(saved_run.saved_coverage_fraction)


def test_baseline_lock_needs_rewrite_count(saved_run):
    result = replay_d8(saved_run, corpus_satisfaction=False)
    assert len(result.decision.needs_rewrite) == _BASELINE_NEEDS_REWRITE
    assert len(result.decision.needs_rewrite) == len(saved_run.saved_needs_rewrite)


def test_baseline_not_release_allowed(saved_run):
    result = replay_d8(saved_run, corpus_satisfaction=False)
    assert result.decision.release_allowed is False


# --- §-1.1 ZERO-FABRICATION invariant (content audit, not string-presence) ------------------


def test_zero_fabrication_invariant(saved_run):
    """Every numeric expression shipped in a claim appears (with sign/operator/percent) in its
    cited span — re-confirms DRB76_FORENSIC "zero fabrications" mechanically."""
    findings = audit_cited_spans(saved_run.audit_pack)
    assert findings == [], (
        "ungrounded numerics (fabrication / mis-bound citation): "
        + "; ".join(f"idx={f.idx} num={f.numeric!r} eid={f.evidence_id}" for f in findings)
    )


@pytest.mark.parametrize(
    "claim, span, must_flag, label",
    [
        ("5 mg dose", "given 50 mg daily", True, "substring 5-in-50 (lethal)"),
        ("change of -5%", "change of 5%", True, "measurement sign flip"),
        ("p<0.001", "p=0.001", True, "comparator < vs ="),
        ("p>0.05", "p<0.05", True, "comparator > vs <"),
        ("p < 0.001", "p=0.001", True, "SPACED comparator < vs ="),
        ("RR > 1.2", "RR=1.2", True, "SPACED comparator > vs ="),
        ("p <= 0.05", "p=0.05", True, "SPACED <= vs ="),
        ("p < 0.001", "p < 0.001", False, "SPACED comparator same value OK"),
        ("P value of 0.32", "(P=0.32 for non-linearity)", False, "bare vs '=' same value"),
        ("HR 0.65 (95% CI 0.47-0.89)", "0.65, 95% CI 0.47 to 0.89", False, "range endpoints"),
        ("26.2 ± 2.3%", "26.2±2.3%", False, "spacing/unicode"),
        ("13,000 patients", "13000 patients", False, "thousands separator"),
    ],
)
def test_numeric_matcher_no_false_negative(claim, span, must_flag, label):
    """Adversarial guard on the §-1.1 matcher: it must catch substring/sign/operator drift
    (no false-negative) without flagging legitimate reformatting (no false-positive)."""
    missing = _numeric_exprs(claim) - _numeric_exprs(span)
    assert bool(missing) is must_flag, f"{label}: missing={sorted(missing)}"


def test_zero_fabrication_fails_loud_on_missing_pack():
    """A missing/empty audit pack must FAIL LOUD, never pass the §-1.1 test vacuously (LAW II)."""
    with pytest.raises(AuditPackMissingClaimsError):
        audit_cited_spans({})
    with pytest.raises(AuditPackMissingClaimsError):
        audit_cited_spans({"claims": []})


# --- I-perm-002 HONEST FINDING: naive corpus credit is insufficient under the prod matcher --


def test_iperm002_evidence_id_credit_does_not_clear_safety_hold(saved_run):
    """With the FAITHFUL production S0 content-requirement matcher, crediting from a VERIFIED
    claim's evidence_id does NOT clear the contraindications hold: the VERIFIED Safety claims
    cite the contraindication evidence but their text lacks the literal token 'contraindicated'.
    Proves the real B2 fix needs semantic recognition or the always-release relabel, NOT a naive
    corpus-wide evidence_id credit (Codex A4)."""
    sim = replay_d8(saved_run, corpus_satisfaction=True)
    assert _CONTRAINDICATIONS_HOLD in sim.decision.held_reasons
    assert "contraindications" not in sim.credited_categories
    assert sim.coverage_fraction == pytest.approx(_BASELINE_COVERAGE)


def test_safety_floor_input_has_verified_safety_claim(saved_run):
    """R2 per-safety-section floor input: >=1 VERIFIED claim cites the contraindication evidence,
    so the Safety section is NOT zero-verified. Under always-release (I-perm-001) this releases
    with a prominent contraindication-completeness caveat (R3), not 'insufficient safety evidence'
    and not a normal-render block."""
    verified = verified_claims_citing(saved_run, _CONTRAINDICATION_EVIDENCE)
    assert len(verified) >= 1, "expected >=1 VERIFIED claim citing the contraindication evidence"


@pytest.mark.xfail(
    strict=True,
    reason=(
        "I-perm-002/I-perm-001 (#1196/#1195) ledger entry: flips green when the production binding "
        "credits the contraindication via semantic/qualitative recognition (#1196) OR the "
        "always-release relabel converts the literal-token S0 gap into a displayed caveat (#1195), "
        "and this test is re-pointed at that production replay. Today the production binding still "
        "emits the false hold (the VERIFIED Safety claims lack the literal token 'contraindicated')."
    ),
)
def test_iperm002_production_flip(saved_run):
    """PENDING I-perm-002/001: the production-equivalent binding must stop emitting the false hold."""
    result = replay_d8(saved_run, corpus_satisfaction=False)
    assert _CONTRAINDICATIONS_HOLD not in result.decision.held_reasons
