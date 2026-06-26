"""I-wire-007 (#1321) change #4: SEAM-PRESERVE partial verdicts, routed FAIL-CLOSED.

On the outer seam WALL timeout the compute drain had already settled SOME claims and persisted them to
the four_role_settled_verdicts.jsonl sidecar. The recovery (`recover_seam_partial_verdicts`) reads them
back so they are NOT discarded — but the recovered partial is STILL routed through the seam release
policy (`build_seam_release_outcome`), whose non-empty SEAM_GAP_UNADJUDICATED disclosed gap forces a
NON-success disposition. So a partial set holds/flags the run as under-verified — NEVER a false
full-certify.

ACCEPTANCE (the task gate): a partial set -> release policy holds/flags, never a false full-certify;
the unverified remainder drags coverage DOWN; unsettled claims are absent (fail-closed).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.polaris_graph.roles.sweep_integration import (
    FOUR_ROLE_SETTLED_VERDICTS_FILENAME,
    _append_settled_verdict,
)

# The recovery + seam release builder live in the run script (loaded as a module).
import importlib.util as _ilu

_SWEEP_PATH = Path(__file__).resolve().parents[3] / "scripts" / "run_honest_sweep_r3.py"


def _load_sweep_module():
    spec = _ilu.spec_from_file_location("run_honest_sweep_r3", _SWEEP_PATH)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_sidecar(run_dir: Path, rows: list[dict]) -> None:
    path = run_dir / FOUR_ROLE_SETTLED_VERDICTS_FILENAME
    for row in rows:
        _append_settled_verdict(
            path,
            claim_id=row["claim_id"],
            verdict=row["verdict"],
            covered_element_ids=row.get("covered_element_ids", []),
        )


# --- recover_seam_partial_verdicts ---------------------------------------------------------------
def test_recovers_settled_partials_from_the_sidecar(tmp_path):
    sweep = _load_sweep_module()
    _write_sidecar(
        tmp_path,
        [
            {"claim_id": "c1", "verdict": "VERIFIED", "covered_element_ids": ["e1"]},
            {"claim_id": "c2", "verdict": "UNSUPPORTED", "covered_element_ids": ["e2"]},
            {"claim_id": "c3", "verdict": "VERIFIED", "covered_element_ids": ["e3"]},
        ],
    )
    # 10 claims total; only 3 settled before the wall (the recovery must NOT invent the other 7).
    verdicts, coverage, settled = sweep.recover_seam_partial_verdicts(tmp_path, total_claims=10)
    assert settled == 3
    assert verdicts == {"c1": "VERIFIED", "c2": "UNSUPPORTED", "c3": "VERIFIED"}
    # 2 VERIFIED covered ids over 10 total claims = 0.2 — the remainder DRAGS coverage down.
    assert coverage == pytest.approx(0.2)


def test_unsettled_claims_are_absent_fail_closed(tmp_path):
    """A claim that never settled before the wall is ABSENT from the recovered map (stays held)."""
    sweep = _load_sweep_module()
    _write_sidecar(tmp_path, [{"claim_id": "c1", "verdict": "VERIFIED", "covered_element_ids": ["e1"]}])
    verdicts, _coverage, _settled = sweep.recover_seam_partial_verdicts(tmp_path, total_claims=5)
    assert "c1" in verdicts
    for missing in ("c2", "c3", "c4", "c5"):
        assert missing not in verdicts, "an unsettled claim must NEVER appear as a recovered verdict"


def test_missing_sidecar_returns_empty_no_worse_than_discard(tmp_path):
    """No sidecar -> ({}, 0.0, 0): byte-equivalent to the prior discard-everything behaviour."""
    sweep = _load_sweep_module()
    verdicts, coverage, settled = sweep.recover_seam_partial_verdicts(tmp_path, total_claims=10)
    assert verdicts == {} and coverage == 0.0 and settled == 0


def test_torn_final_line_is_skipped_not_fatal(tmp_path):
    """A crash mid-append can leave a torn last line; recovery skips it and keeps the clean rows."""
    sweep = _load_sweep_module()
    path = tmp_path / FOUR_ROLE_SETTLED_VERDICTS_FILENAME
    path.write_text(
        json.dumps({"claim_id": "c1", "verdict": "VERIFIED", "covered_element_ids": ["e1"]}) + "\n"
        + '{"claim_id": "c2", "verdict": "VERIF',  # torn (no newline, invalid json).
        encoding="utf-8",
    )
    verdicts, _coverage, settled = sweep.recover_seam_partial_verdicts(tmp_path, total_claims=10)
    assert settled == 1 and verdicts == {"c1": "VERIFIED"}


# --- the FAIL-CLOSED routing (the acceptance gate) -----------------------------------------------
def test_partial_routes_to_disclosed_gaps_never_full_certify(tmp_path):
    """A partial recovery routed through build_seam_release_outcome HOLDS/flags — never full-certify.

    The SEAM_GAP_UNADJUDICATED disclosed gap is present (non-empty), the normal polished report is
    blocked, and the status is a disclosed-gaps / insufficient-safety variant — NOT a clean success.
    """
    sweep = _load_sweep_module()
    from src.polaris_graph.roles.release_policy import (
        STATUS_RELEASED_INSUFFICIENT_SAFETY,
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
    )

    outcome, body_withheld, _reason = sweep.build_seam_release_outcome(
        sections=[],                       # no shipped sentences -> no cited identities to screen.
        evidence_for_gen=[],
        is_clinical=False,
        seam_held_reason="seam_timeout",
        coverage_fraction=0.2,             # the recovered partial coverage.
    )
    # NON-success: the disclosed gap forces released_with_disclosed_gaps (or insufficient-safety for a
    # clinical Q) — it can NEVER be a clean full-certify success.
    assert outcome.status in (
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
        STATUS_RELEASED_INSUFFICIENT_SAFETY,
    )
    assert any(
        g.startswith(sweep.SEAM_GAP_UNADJUDICATED) for g in outcome.disclosed_gaps
    ), "the unadjudicated disclosed gap MUST be present so the run cannot certify clean"
    assert outcome.adjudicated is False, "the judge never adjudicated on a seam timeout"


def test_high_partial_coverage_still_holds_never_certifies(tmp_path):
    """LOCK the one relaxation vector: even a HIGH recovered partial coverage (0.99) must STILL route
    to a disclosed-gaps / insufficient-safety disposition — never a clean full-certify success.

    `coverage_fraction` flows ONLY into the DISPLAYED `release_quality_score` (release_policy.py:426
    'NOT a trap-door threshold'; zero `>`/`<` comparisons on it in src/ or scripts/). The status is
    forced non-success by the UNCONDITIONAL SEAM_GAP_UNADJUDICATED gap regardless of coverage. This
    test would FAIL if a future change ever thresholded disposition on the recovered coverage."""
    sweep = _load_sweep_module()
    from src.polaris_graph.roles.release_policy import (
        STATUS_RELEASED_INSUFFICIENT_SAFETY,
        STATUS_RELEASED_WITH_DISCLOSED_GAPS,
    )

    for cov in (0.0, 0.5, 0.99, 1.0):
        outcome, _withheld, _reason = sweep.build_seam_release_outcome(
            sections=[],
            evidence_for_gen=[],
            is_clinical=False,
            seam_held_reason="seam_timeout",
            coverage_fraction=cov,
        )
        assert outcome.status in (
            STATUS_RELEASED_WITH_DISCLOSED_GAPS,
            STATUS_RELEASED_INSUFFICIENT_SAFETY,
        ), f"coverage={cov} must NEVER certify clean on a seam timeout"
        assert any(g.startswith(sweep.SEAM_GAP_UNADJUDICATED) for g in outcome.disclosed_gaps)
        assert outcome.adjudicated is False, "the judge never adjudicated regardless of coverage"


def test_clinical_partial_ships_insufficient_safety_variant(tmp_path):
    """A clinical/safety-floor Q on a seam timeout ships the honest insufficient-safety variant."""
    sweep = _load_sweep_module()
    from src.polaris_graph.roles.release_policy import STATUS_RELEASED_INSUFFICIENT_SAFETY

    outcome, _withheld, _reason = sweep.build_seam_release_outcome(
        sections=[],
        evidence_for_gen=[],
        is_clinical=True,
        seam_held_reason="seam_timeout",
        coverage_fraction=0.2,
    )
    assert outcome.status == STATUS_RELEASED_INSUFFICIENT_SAFETY
    assert outcome.normal_release_blocked is True, "the polished normal report is NOT shipped as clean"
