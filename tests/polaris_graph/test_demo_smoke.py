"""Tests for scripts/demo_smoke.py — the 5-slice end-to-end smoke."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make scripts/ importable
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import demo_smoke  # noqa: E402


def test_parse_args_default_not_verbose():
    args = demo_smoke.parse_args([])
    assert args.verbose is False


def test_parse_args_verbose_flag():
    args = demo_smoke.parse_args(["-v"])
    assert args.verbose is True


def test_parse_args_long_verbose_flag():
    args = demo_smoke.parse_args(["--verbose"])
    assert args.verbose is True


def test_main_returns_0_when_app_healthy(capsys):
    """End-to-end: main() should pass against a real create_app()."""
    rc = demo_smoke.main([])
    captured = capsys.readouterr()
    assert rc == 0, f"smoke failed: {captured.out}\nstderr: {captured.err}"
    assert "DEMO SMOKE PASSED" in captured.out
    assert "5 slices healthy" in captured.out


def test_main_verbose_prints_each_check(capsys):
    rc = demo_smoke.main(["-v"])
    out = capsys.readouterr().out
    assert rc == 0
    # All 5 slice routes appear in verbose output
    assert "/api/intake/health" in out
    assert "/api/retrieval/health" in out
    assert "/api/generation/health" in out
    assert "/api/audit-bundle/health" in out
    assert "/api/benchmark/health" in out
    assert "process_intake" in out


def test_expected_health_dict_covers_5_slices():
    """The smoke must check exactly 5 slice health endpoints."""
    assert len(demo_smoke._EXPECTED_HEALTH) == 5
    paths = set(demo_smoke._EXPECTED_HEALTH.keys())
    assert "/api/intake/health" in paths
    assert "/api/retrieval/health" in paths
    assert "/api/generation/health" in paths
    assert "/api/audit-bundle/health" in paths
    assert "/api/benchmark/health" in paths


def test_canonical_question_is_clinical():
    """The canonical demo question should be a clinical efficacy question."""
    q = demo_smoke._CANONICAL_QUESTION
    assert "aspirin" in q.lower() or "migraine" in q.lower() or \
        "clinical" in q.lower() or "effective" in q.lower()


def test_check_health_returns_false_on_wrong_slice(monkeypatch):
    """Verify the wrong-slice path returns False, not silently passes."""
    from fastapi.testclient import TestClient
    from polaris_v6.api.app import create_app

    client = TestClient(create_app())
    # Real path with wrong expected slice → should fail
    ok = demo_smoke._check_health(
        client, "/api/intake/health", "wrong_slice_id", verbose=False
    )
    assert ok is False
