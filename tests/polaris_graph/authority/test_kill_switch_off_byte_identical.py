"""Smoke S1 — kill-switch OFF byte-identity + determinism (Phase 0a, GH #983).

With PG_USE_AUTHORITY_MODEL unset, run the full ~1,529-URL corpus through
classify_source_tier and assert each ClassificationResult (tier, confidence,
matched_rules, reasons) is byte-identical to the frozen baseline produced by
scripts/freeze_clinical_tier_baseline.py. Proves NOTHING breaks when OFF.
Hard-fail on any single diff. Offline; no network.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE = REPO_ROOT / "tests" / "fixtures" / "authority" / "clinical_tier_baseline_off.json"


def _load_baseline() -> list[dict]:
    assert BASELINE.exists(), f"missing S1 baseline: {BASELINE}"
    return json.loads(BASELINE.read_text(encoding="utf-8"))


def test_s1_off_byte_identical_over_full_corpus(monkeypatch):
    monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    baseline = _load_baseline()
    assert len(baseline) >= 1500, f"baseline too small: {len(baseline)} (expected ~1529)"

    diffs: list[str] = []
    for row in baseline:
        signals = ClassificationSignals(url=row["url"], title=row["title"])
        result = classify_source_tier(signals)
        if result.tier.value != row["tier"]:
            diffs.append(f"{row['url']}: tier {result.tier.value} != {row['tier']}")
            continue
        if result.confidence != row["confidence"]:
            diffs.append(f"{row['url']}: confidence {result.confidence} != {row['confidence']}")
            continue
        if list(result.matched_rules) != row["matched_rules"]:
            diffs.append(f"{row['url']}: matched_rules differ")
            continue
        if list(result.reasons) != row["reasons"]:
            diffs.append(f"{row['url']}: reasons differ")
    assert not diffs, f"S1 OFF byte-identity FAILED ({len(diffs)} diffs): {diffs[:10]}"


def test_s1_off_additive_fields_are_none(monkeypatch):
    """On the OFF path the four additive authority fields stay None (byte-id)."""
    monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    baseline = _load_baseline()
    for row in baseline[:200]:
        result = classify_source_tier(
            ClassificationSignals(url=row["url"], title=row["title"])
        )
        assert result.authority_score is None
        assert result.source_class is None
        assert result.corroboration_count is None
        assert result.authority_confidence is None


def test_s1_off_path_deterministic(monkeypatch):
    monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    baseline = _load_baseline()
    for row in baseline[:100]:
        sig = ClassificationSignals(url=row["url"], title=row["title"])
        r1 = classify_source_tier(sig)
        r2 = classify_source_tier(ClassificationSignals(url=row["url"], title=row["title"]))
        assert r1.tier == r2.tier
        assert r1.reasons == r2.reasons
        assert r1.matched_rules == r2.matched_rules
