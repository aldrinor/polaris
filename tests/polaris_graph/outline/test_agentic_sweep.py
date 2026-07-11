"""Unit tests for the FULL-CORPUS cp4_used=agentic sweep invariant (scripts/outline_agentic_sweep.py).

The sweep is credential-gated end-to-end (needs GLM-5.2), but its ASSERTION machinery — the mission
invariant 'cp4_used must be agentic; seed fallback ONLY on GLM-5.2 truncation' — is pure and must be
locked so it cannot silently drift into accepting a fallback-plain downgrade.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "outline_agentic_sweep",
    Path(__file__).resolve().parents[3] / "scripts" / "outline_agentic_sweep.py",
)
sweep = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sweep)


def test_clean_agentic_passes():
    passed, _ = sweep._classify("agentic", "")
    assert passed is True


def test_sanctioned_truncation_degrade_passes():
    passed, reason = sweep._classify(
        "agentic-degraded-seed",
        "ReasoningFirstTruncationError: reasoning prelude exceeded completion budget",
    )
    assert passed is True and "truncation" in reason


def test_non_truncation_degrade_fails():
    passed, reason = sweep._classify("agentic-degraded-seed", "TimeoutError: wall exceeded")
    assert passed is False and "NON-truncation" in reason


def test_fallback_plain_fails():
    passed, reason = sweep._classify("plain", "")
    assert passed is False and "fallback-plain is forbidden" in reason


def test_missing_cp4_block_fails():
    passed, _ = sweep._classify("MISSING", "")
    assert passed is False


def test_count_baskets_only_multi_member_clusters():
    clusters = [{"member_indices": [1, 2]}, {"member_indices": [3]}, {"member_indices": [4, 5, 6]}]
    assert sweep._count_baskets(clusters) == 2


def test_dry_run_selfcheck_passes():
    # the offline self-check the operator runs to confirm the machinery before keys land.
    assert sweep._dry_run_selfcheck() == 0
