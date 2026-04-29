"""M-INT-2 — Cache + cache-warming around sweep entry."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def test_sweep_imports_cache_warming_substrates() -> None:
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    assert hasattr(sweep, "warm_cache")
    assert hasattr(sweep, "RetrievalCacheStore")
    assert hasattr(sweep, "CacheFetcher")
    assert hasattr(sweep, "_warm_canonical_corpus")


def test_warm_canonical_corpus_writes_cache_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CACHE_WARMING", "1")
    monkeypatch.setenv(
        "PG_RETRIEVAL_CACHE_DB_PATH",
        str(tmp_path / "cache.sqlite"),
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._warm_canonical_corpus(
        workspace_id="ws_test",
        canonical_urls=["https://example.com/a", "https://example.com/b"],
        out_root=tmp_path,
    )
    assert summary is not None
    assert summary["fetched_count"] == 2
    assert summary["errored_count"] == 0


def test_warm_canonical_corpus_skips_existing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Second call on same URLs should skip them (idempotency)."""
    monkeypatch.setenv("PG_USE_CACHE_WARMING", "1")
    monkeypatch.setenv(
        "PG_RETRIEVAL_CACHE_DB_PATH",
        str(tmp_path / "cache.sqlite"),
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    urls = ["https://example.com/a", "https://example.com/b"]
    s1 = sweep._warm_canonical_corpus(
        workspace_id="ws_idem",
        canonical_urls=urls,
        out_root=tmp_path,
    )
    s2 = sweep._warm_canonical_corpus(
        workspace_id="ws_idem",
        canonical_urls=urls,
        out_root=tmp_path,
    )
    assert s1["fetched_count"] == 2
    assert s2["fetched_count"] == 0
    assert s2["skipped_count"] == 2


def test_disabled_flag_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CACHE_WARMING", "0")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._warm_canonical_corpus(
        workspace_id="ws_off",
        canonical_urls=["https://example.com/a"],
        out_root=tmp_path,
    )
    assert summary is None


def test_empty_url_list_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CACHE_WARMING", "1")
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    summary = sweep._warm_canonical_corpus(
        workspace_id="ws_empty",
        canonical_urls=[],
        out_root=tmp_path,
    )
    assert summary is None


def test_warming_failure_does_not_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PG_USE_CACHE_WARMING", "1")
    monkeypatch.setenv(
        "PG_RETRIEVAL_CACHE_DB_PATH",
        str(tmp_path / "cache.sqlite"),
    )
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")

    def _broken_warm(*args, **kwargs):
        raise RuntimeError("simulated cache failure")

    monkeypatch.setattr(sweep, "warm_cache", _broken_warm)
    summary = sweep._warm_canonical_corpus(
        workspace_id="ws_fail",
        canonical_urls=["https://example.com/a"],
        out_root=tmp_path,
    )
    # Returns None on failure (not raise).
    assert summary is None
