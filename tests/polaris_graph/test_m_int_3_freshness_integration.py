"""M-INT-3 — Freshness detector + eviction integrated into sweep."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_sweep_imports_freshness_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "FreshnessAlertStore")
    assert hasattr(sweep, "FreshnessStatus")
    assert hasattr(sweep, "check_freshness")
    assert hasattr(sweep, "_check_corpus_freshness")


def test_check_corpus_freshness_writes_alerts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_FRESHNESS_DETECTOR", "1")
    monkeypatch.setenv(
        "PG_FRESHNESS_DB_PATH", str(tmp_path / "freshness.sqlite"),
    )
    monkeypatch.setenv(
        "PG_RETRIEVAL_CACHE_DB_PATH", str(tmp_path / "cache.sqlite"),
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._check_corpus_freshness(
        workspace_id="ws_fresh",
        canonical_urls=["https://example.com/a", "https://example.com/b"],
        out_root=tmp_path,
    )
    assert summary is not None
    assert summary["total_checked"] == 2
    # Stub returns UNCHANGED for everything — no evictions.
    assert summary["evicted_count"] == 0
    assert summary["per_status"]["unchanged"] == 2


def test_disabled_flag_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_FRESHNESS_DETECTOR", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._check_corpus_freshness(
        workspace_id="ws_off",
        canonical_urls=["https://example.com/a"],
        out_root=tmp_path,
    )
    assert summary is None


def test_empty_url_list_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_FRESHNESS_DETECTOR", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._check_corpus_freshness(
        workspace_id="ws_empty",
        canonical_urls=[],
        out_root=tmp_path,
    )
    assert summary is None


def test_freshness_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per LAW II — freshness check failure must not gate sweep."""
    monkeypatch.setenv("PG_USE_FRESHNESS_DETECTOR", "1")
    monkeypatch.setenv(
        "PG_FRESHNESS_DB_PATH", str(tmp_path / "freshness.sqlite"),
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    def _broken_check(*args, **kwargs):
        raise RuntimeError("simulated freshness failure")

    monkeypatch.setattr(sweep, "check_freshness", _broken_check)
    summary = sweep._check_corpus_freshness(
        workspace_id="ws_fail",
        canonical_urls=["https://example.com/a"],
        out_root=tmp_path,
    )
    # Per-URL exception should be caught; summary still returned.
    assert summary is not None
    assert summary["total_checked"] == 1
