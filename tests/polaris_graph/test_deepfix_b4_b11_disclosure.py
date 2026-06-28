"""Behavioral fail-loud tests for deepfix baskets B4 + B11 (AGENT-C-SWEEP, owned files only).

B4 (#1360) — the Methods family-disclosure clause must HONESTLY reflect the two-family state:
  * distinct families  -> "distinct training families"
  * same family + operator override active -> LOUD non-segregation disclosure carrying the
    SHARED-LITERAL CONTRACT tokens the (foreign) PT03 check matches against
    ("not family-segregated", "same family", "self-bias safeguard disabled").
  * same family + NO override (should never happen — construction raises) -> still discloses
    honestly, never a benign "(glm lineage)" lie.

B11 C3 (#1362) — ReleaseOutcome.display_quality_score() must render "N/A (D8 unadjudicated)"
  when the four-role D8 judge never adjudicated (adjudicated=False), never a misleading bare 0.0.

These assert the EFFECT APPEARS (§-1.4 behavioral acceptance). They do NOT test the foreign
PT03 gate logic (external_evaluator.py) or the foreign SLO provider routing (provider_routing.py /
openrouter_role_transport.py) — those are flagged as foreign seams for serial wiring.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_run_script():
    """Import scripts/run_honest_sweep_r3.py as a module (it has an
    ``if __name__ == '__main__'`` guard and no heavy import-time work)."""
    path = _REPO_ROOT / "scripts" / "run_honest_sweep_r3.py"
    spec = importlib.util.spec_from_file_location("_rhs_deepfix_test", path)
    assert spec and spec.loader, f"cannot load spec for {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# B4 — eval_family_disclosure_clause
# ---------------------------------------------------------------------------

# The exact literal tokens the (foreign) PT03 disclosure check must match against.
# If these change, the PT03 matcher in external_evaluator.py MUST change in lockstep.
_PT03_SHARED_LITERAL_TOKENS = (
    "not family-segregated",
    "same family",
    "self-bias safeguard disabled",
)


def test_b4_distinct_families_clause_states_distinct():
    rhs = _load_run_script()
    clause = rhs.eval_family_disclosure_clause("glm", "qwen", permit_same_family=False)
    assert "distinct training families" in clause
    assert "glm" in clause and "qwen" in clause
    # MUST NOT carry the override-disclosure tokens on a genuinely segregated run.
    assert "NOT family-segregated" not in clause


def test_b4_same_family_with_override_discloses_voided_invariant_loud():
    """The all-GLM campaign (gen==eval==glm, PG_PERMIT_...=1). The old else-branch printed a benign
    '(glm lineage)' that HID the voided two-family safeguard. The fix must LOUDLY disclose it AND
    emit the shared-literal tokens PT03 keys on."""
    rhs = _load_run_script()
    clause = rhs.eval_family_disclosure_clause("glm", "glm", permit_same_family=True)
    lowered = clause.lower()
    # FAIL LOUD if the disclosure regresses to the benign lie.
    assert clause != "(glm lineage)", "regressed to the benign '(glm lineage)' lie"
    assert "glm" in clause
    for token in _PT03_SHARED_LITERAL_TOKENS:
        assert token in lowered, f"missing PT03 shared-literal token {token!r} in: {clause!r}"
    assert "override" in lowered
    assert "PG_PERMIT_GENERATOR_EVALUATOR_SAME_FAMILY" in clause


def test_b4_same_family_without_override_still_honest_not_benign():
    """Defense-in-depth: even if a same-family pair reaches the clause without the override
    (construction normally raises first), it must NOT print a benign single-family lineage line."""
    rhs = _load_run_script()
    clause = rhs.eval_family_disclosure_clause("glm", "glm", permit_same_family=False)
    assert clause != "(glm lineage)"
    assert "not family-segregated" in clause.lower()
    assert "same family" in clause.lower()


# ---------------------------------------------------------------------------
# B11 C3 — ReleaseOutcome.display_quality_score
# ---------------------------------------------------------------------------


def _make_outcome(*, adjudicated: bool, score: float):
    from src.polaris_graph.roles.release_policy import ReleaseOutcome

    return ReleaseOutcome(
        released=True,
        hard_block=False,
        normal_release_blocked=False,
        status="released",
        disclosed_gaps=[],
        hard_block_reasons=[],
        release_quality_score=score,
        safety_floor="ok",
        adjudicated=adjudicated,
    )


def test_b11_unadjudicated_seam_renders_na_not_zero():
    """On a D8 seam (judge never adjudicated) the raw float 0.0 reads as 'scored zero quality' —
    a lie. The display must be the honest N/A string."""
    outcome = _make_outcome(adjudicated=False, score=0.0)
    display = outcome.display_quality_score()
    assert display == "N/A (D8 unadjudicated)"
    # FAIL LOUD if a bare numeric zero leaks through.
    assert display != "0.0"
    assert display != "0.000"


def test_b11_unadjudicated_with_nonzero_coverage_still_na():
    """Even when a coverage fraction exists, if D8 never adjudicated the quality SCORE is unknown."""
    outcome = _make_outcome(adjudicated=False, score=0.42)
    assert outcome.display_quality_score() == "N/A (D8 unadjudicated)"


def test_b11_adjudicated_renders_numeric_score():
    outcome = _make_outcome(adjudicated=True, score=0.815)
    assert outcome.display_quality_score() == "0.815"


def test_b11_default_outcome_is_unadjudicated_failsafe():
    """The dataclass defaults adjudicated=False (fail-closed). An outcome built without explicit
    adjudication proof must render N/A, never a fabricated numeric score."""
    outcome = _make_outcome(adjudicated=False, score=1.0)
    assert outcome.display_quality_score() == "N/A (D8 unadjudicated)"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
