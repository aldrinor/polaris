"""M-INT-3 — Freshness detector + eviction integrated into sweep."""

from __future__ import annotations

import asyncio
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
    assert hasattr(sweep, "FreshnessDetector")
    assert hasattr(sweep, "FreshnessCheckResult")
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


def test_main_async_prints_freshness_summary_after_cache_warming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys,
) -> None:
    monkeypatch.setenv("PG_CAPTURE_PIN", "0")
    monkeypatch.setenv("PG_USE_FRESHNESS_DETECTOR", "1")
    monkeypatch.setattr(
        sys, "argv",
        [
            "run_honest_sweep_r3.py",
            "--only", "freshness_smoke",
            "--out-root", str(tmp_path / "out"),
        ],
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    monkeypatch.setattr(
        sweep,
        "SWEEP_QUERIES",
        [
            {
                "domain": "tech",
                "slug": "freshness_smoke",
                "question": "Does the sweep print freshness telemetry?",
                "canonical_urls": ["https://example.com/a"],
            }
        ],
    )
    call_order: list[str] = []

    def _fake_warm(*, workspace_id: str, canonical_urls: list[str], out_root: Path):
        assert workspace_id == "sweep"
        assert canonical_urls == ["https://example.com/a"]
        call_order.append("warm")
        return {"fetched_count": 1, "skipped_count": 0, "errored_count": 0}

    def _fake_check(*, workspace_id: str, canonical_urls: list[str], out_root: Path):
        assert workspace_id == "sweep"
        assert canonical_urls == ["https://example.com/a"]
        assert call_order == ["warm"]
        call_order.append("fresh")
        return {
            "total_checked": 1,
            "evicted_count": 0,
            "per_status": {
                "unchanged": 1,
                "superseded": 0,
                "retracted": 0,
                "expression_of_concern": 0,
                "unreachable": 0,
            },
        }

    async def _fake_run_one_query(query: dict, out_root: Path) -> dict:
        run_dir = out_root / query["slug"]
        run_dir.mkdir(parents=True, exist_ok=True)
        return {
            "domain": query["domain"],
            "slug": query["slug"],
            "question": query["question"],
            "status": "ok",
            "manifest": {},
            "cost_usd": 0.0,
            "run_dir": str(run_dir),
            "run_id": "RUN_FRESHNESS_SMOKE",
        }

    monkeypatch.setattr(sweep, "_warm_canonical_corpus", _fake_warm)
    monkeypatch.setattr(sweep, "_check_corpus_freshness", _fake_check)
    monkeypatch.setattr(sweep, "run_one_query", _fake_run_one_query)

    rc = asyncio.run(sweep.main_async())
    assert rc == 0
    assert call_order == ["warm", "fresh"]

    captured = capsys.readouterr()
    assert "[M-INT-3] sweep_freshness_summary: total_checked=1" in captured.out
    assert "per_status={unchanged=1, superseded=0, retracted=0" in captured.out
    assert "expression_of_concern=0, unreachable=0}" in captured.out
    assert "evicted_count=0" in captured.out
