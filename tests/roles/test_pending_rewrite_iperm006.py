"""I-perm-006 (#1200) — kill the phantom `d8_pending_rewrite` block under always-release.

`d8_pending_rewrite` fires whenever a non-VERIFIED claim populates `needs_rewrite` AND
`rewrite_already_attempted` is False — which is ALWAYS (it is hardcoded False at every call site and
no outer loop ever re-runs the seam to set it True). So it blocks release for a rewrite the
architecture structurally never executes. Under the always-release reframe (I-perm-001) an
UNSUPPORTED claim ships LABELED via the annotator, so the phantom block is removed when
PG_ALWAYS_RELEASE is on; `needs_rewrite` stays a pure REPORTING channel. Flag OFF -> byte-identical.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.roles.release_policy import (
    CoverageLedger,
    D8ClaimRow,
    _REASON_PENDING_REWRITE,
    apply_d8_release_policy,
)


def _decision(monkeypatch, *, always_release: bool):
    if always_release:
        monkeypatch.setenv("PG_ALWAYS_RELEASE", "1")
    else:
        # B5/B7 (2026-06-14): PG_ALWAYS_RELEASE default is now ON. The legacy OFF path is reached
        # only by an EXPLICIT off token — pin it here (delenv would now resolve to the default ON).
        monkeypatch.setenv("PG_ALWAYS_RELEASE", "0")
    # One material, non-VERIFIED claim -> populates needs_rewrite (rewrite_already_attempted=False,
    # as every production call site hardcodes).
    rows = [D8ClaimRow(claim_id="c1", severity="S1", verdict="UNSUPPORTED")]
    ledger = CoverageLedger(required_element_ids=[], covered_element_ids=set())
    return apply_d8_release_policy(
        rows,
        required_s0_categories=[],
        coverage_ledger=ledger,
        coverage_threshold=0.0,
        rewrite_already_attempted=False,
    )


def test_flag_off_byte_identical_block(monkeypatch):
    d = _decision(monkeypatch, always_release=False)
    assert "c1" in d.needs_rewrite, "non-VERIFIED claim must still be reported in needs_rewrite"
    assert _REASON_PENDING_REWRITE in d.held_reasons, "flag OFF keeps the existing phantom block"


def test_always_release_removes_phantom_block(monkeypatch):
    d = _decision(monkeypatch, always_release=True)
    # needs_rewrite is UNCHANGED — it stays the pure reporting channel.
    assert "c1" in d.needs_rewrite
    # ...but it no longer adds the phantom held_reason, so this claim alone does not block release.
    assert _REASON_PENDING_REWRITE not in d.held_reasons
