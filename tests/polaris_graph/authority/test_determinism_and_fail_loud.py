"""Smoke S6 — determinism + fail-loud data loader (Phase 0a, GH #983).

- ON, two consecutive runs over the same fixtures -> identical AuthorityResult
  (no RNG, no live calls, no dict-order leakage).
- data_loader raises (not silent-default) on a missing / empty / unparseable
  config/authority/* file (LAW II — no silent fallback).
Offline; no network.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
S2_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "authority" / "clinical_200_urls.jsonl"
CROSS_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "authority" / "cross_field_50_urls.jsonl"


def test_s6_authority_model_deterministic(monkeypatch):
    monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    from src.polaris_graph.authority import AuthoritySignals, score_source_authority
    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

    rows = [
        json.loads(ln)
        for ln in CROSS_FIXTURE.read_text(encoding="utf-8").splitlines()
        if ln.strip()
    ]
    for e in rows:
        sig1 = ClassificationSignals(url=e["url"], title="")
        sig1.authority = AuthoritySignals(**e["authority_signals"])
        sig2 = ClassificationSignals(url=e["url"], title="")
        sig2.authority = AuthoritySignals(**e["authority_signals"])
        r1 = score_source_authority(sig1)
        r2 = score_source_authority(sig2)
        assert asdict(r1) == asdict(r2), f"non-deterministic result for {e['url']}"


def test_s6_loader_fail_loud_on_missing_dir(monkeypatch, tmp_path):
    from src.polaris_graph.authority import data_loader

    empty = tmp_path / "empty_authority"
    empty.mkdir()
    monkeypatch.setenv("PG_AUTHORITY_DATA_DIR", str(empty))
    data_loader.clear_cache()
    with pytest.raises(data_loader.AuthorityDataError):
        data_loader.load_authority_data()
    data_loader.clear_cache()


def test_s6_loader_fail_loud_on_empty_file(monkeypatch, tmp_path):
    from src.polaris_graph.authority import data_loader

    d = tmp_path / "authority_data"
    d.mkdir()
    (d / "VERSION").write_text("0a.test\n", encoding="utf-8")
    # All required files present but scholarly_weights is empty -> must raise.
    for name in (
        "ror_type_class_map.yaml", "junk_patterns.yaml", "recency_profile.yaml",
        "blend_weights.yaml", "clinical_view.yaml",
    ):
        (d / name).write_text("k: v\n", encoding="utf-8")
    (d / "psl_gov_suffixes.txt").write_text("gov\n", encoding="utf-8")
    (d / "scholarly_weights.yaml").write_text("", encoding="utf-8")  # empty
    monkeypatch.setenv("PG_AUTHORITY_DATA_DIR", str(d))
    data_loader.clear_cache()
    with pytest.raises(data_loader.AuthorityDataError):
        data_loader.load_authority_data()
    data_loader.clear_cache()


def test_s6_loader_fail_loud_on_unparseable(monkeypatch, tmp_path):
    from src.polaris_graph.authority import data_loader

    d = tmp_path / "authority_bad"
    d.mkdir()
    (d / "VERSION").write_text("0a.test\n", encoding="utf-8")
    for name in (
        "ror_type_class_map.yaml", "junk_patterns.yaml", "recency_profile.yaml",
        "blend_weights.yaml", "clinical_view.yaml",
    ):
        (d / name).write_text("k: v\n", encoding="utf-8")
    (d / "psl_gov_suffixes.txt").write_text("gov\n", encoding="utf-8")
    (d / "scholarly_weights.yaml").write_text("{ this: is: broken yaml ][", encoding="utf-8")
    monkeypatch.setenv("PG_AUTHORITY_DATA_DIR", str(d))
    data_loader.clear_cache()
    with pytest.raises(data_loader.AuthorityDataError):
        data_loader.load_authority_data()
    data_loader.clear_cache()
