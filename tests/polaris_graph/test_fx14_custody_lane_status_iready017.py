"""FX-14 (I-ready-017 #1129): custody-lane honesty marker (path B, telemetry-only).

When the M-44/M-52/V29 custody block is skipped in the planner lane (primary_trial_anchors empty) the
v29/m44 telemetry is written silently empty — ambiguous (no-activity vs not-applicable vs broken).
`compute_custody_lane_status` is the pure decision: returns a not_applicable_planner_lane marker ONLY
when the flag is on AND >=1 primary_trial_doi_seed row reached generation AND both custody logs are
empty; else None (caller writes nothing → byte-identical). The generator path and the two existing
custody files (whose dict/list contracts the m49/m53 tests assert) are UNCHANGED. Offline, no network.
"""
from __future__ import annotations

from scripts.run_honest_sweep_r3 import compute_custody_lane_status

_PRIMARY = {"evidence_id": "e1", "query_origin": "primary_trial_doi_seed", "statement": "x"}
_WEB = {"evidence_id": "e2", "query_origin": "agentic_seed", "statement": "y"}
_PLAIN = {"evidence_id": "e3", "statement": "z"}  # no query_origin key (common case)


def test_marker_when_primary_seeds_present_and_logs_empty():
    out = compute_custody_lane_status(
        [_PRIMARY, _PRIMARY, _WEB, _PLAIN],
        m44_injection_empty=True,
        custody_log_empty=True,
        primary_anchors_configured=False,
        marker_on=True,
    )
    assert out is not None
    assert out["status"] == "not_applicable_planner_lane"
    assert out["primary_trial_doi_seed_rows"] == 2          # only primary seeds counted, not agentic/plain
    assert out["primary_trial_anchors_configured"] is False
    assert out["m44_injection_log_empty"] is True and out["v29_custody_log_empty"] is True


def test_none_when_flag_off_even_with_primary_seeds():
    """Flag OFF → None → caller writes nothing → byte-identical."""
    out = compute_custody_lane_status(
        [_PRIMARY],
        m44_injection_empty=True, custody_log_empty=True,
        primary_anchors_configured=True, marker_on=False,
    )
    assert out is None


def test_none_when_no_primary_seeds():
    """Genuinely no primary seeds → empty telemetry is honest (nothing to disambiguate) → None."""
    out = compute_custody_lane_status(
        [_WEB, _PLAIN],
        m44_injection_empty=True, custody_log_empty=True,
        primary_anchors_configured=False, marker_on=True,
    )
    assert out is None


def test_none_when_custody_actually_ran():
    """Custody block DID run (a log is non-empty) → not the not_applicable case → None."""
    assert compute_custody_lane_status(
        [_PRIMARY], m44_injection_empty=False, custody_log_empty=True,
        primary_anchors_configured=True, marker_on=True,
    ) is None
    assert compute_custody_lane_status(
        [_PRIMARY], m44_injection_empty=True, custody_log_empty=False,
        primary_anchors_configured=True, marker_on=True,
    ) is None


def test_non_dict_rows_ignored():
    """Robust to malformed rows (non-dict entries are skipped, not counted/crashing)."""
    out = compute_custody_lane_status(
        [_PRIMARY, "not-a-dict", None, 42],
        m44_injection_empty=True, custody_log_empty=True,
        primary_anchors_configured=True, marker_on=True,
    )
    assert out is not None and out["primary_trial_doi_seed_rows"] == 1


def test_held_drb72_count_is_2():
    """§-1.1 reconciliation: the held drb_72 evidence_pool.json has exactly 2 primary_trial_doi_seed
    rows (the honest post-FX-15a count; the forensic's '16+' predates the FX-15a mislabel fix)."""
    import json
    import pathlib
    p = pathlib.Path("outputs/audits/I-ready-017/run_artifacts/evidence_pool.json")
    if not p.exists():
        import pytest
        pytest.skip("held drb_72 evidence_pool.json not present")
    rows = json.loads(p.read_text(encoding="utf-8"))
    out = compute_custody_lane_status(
        rows, m44_injection_empty=True, custody_log_empty=True,
        primary_anchors_configured=False, marker_on=True,
    )
    assert out is not None and out["primary_trial_doi_seed_rows"] == 2
