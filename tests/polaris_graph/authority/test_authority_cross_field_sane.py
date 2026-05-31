"""Smoke S3 — cross-field sanity (Phase 0a, GH #983).

>=50 non-clinical URLs (law / physics / policy / JP-gov / African-energy) with
frozen mocked OpenAlex+ROR. Each must get a non-UNKNOWN defensible source_class
and an honest authority_confidence matching field thickness. Proves the
field-agnostic claim: NO non-clinical URL returns the legacy no_rule_matched
UNKNOWN. Offline; no network.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "authority" / "cross_field_50_urls.jsonl"


def _load() -> list[dict]:
    assert FIXTURE.exists(), f"missing S3 fixture: {FIXTURE}"
    return [json.loads(ln) for ln in FIXTURE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_s3_cross_field_sane(monkeypatch):
    monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    from src.polaris_graph.authority import AuthoritySignals
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    rows = _load()
    assert len(rows) >= 50, f"S3 fixture has only {len(rows)} URLs (need >=50)"

    unknown_classes: list[str] = []
    class_mismatches: list[str] = []
    for e in rows:
        sig = ClassificationSignals(url=e["url"], title="")
        sig.authority = AuthoritySignals(**e["authority_signals"])
        result = classify_source_tier(sig)
        # No source should land the legacy no_rule_matched UNKNOWN source_class.
        if result.source_class == "UNKNOWN":
            unknown_classes.append(f"{e['field']}: {e['url']}")
        want = e.get("expect_source_class")
        if want and result.source_class != want:
            class_mismatches.append(
                f"{e['field']} {e['url']}: got {result.source_class} want {want}"
            )

    assert not unknown_classes, (
        f"S3: {len(unknown_classes)} cross-field URLs returned UNKNOWN source_class "
        f"(field-agnostic claim broken): {unknown_classes[:10]}"
    )
    assert not class_mismatches, f"S3 source_class mismatches: {class_mismatches[:10]}"


def test_s3_confidence_matches_field_thickness(monkeypatch):
    monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    from src.polaris_graph.authority import AuthoritySignals
    from src.polaris_graph.retrieval.tier_classifier import (
        ClassificationSignals,
        classify_source_tier,
    )

    bad: list[str] = []
    for e in _load():
        want_conf = e.get("expect_confidence")
        if not want_conf:
            continue
        sig = ClassificationSignals(url=e["url"], title="")
        sig.authority = AuthoritySignals(**e["authority_signals"])
        result = classify_source_tier(sig)
        if result.authority_confidence != want_conf:
            bad.append(
                f"{e['field']} {e['url']}: conf {result.authority_confidence} want {want_conf}"
            )
    assert not bad, f"S3 confidence mismatches: {bad[:10]}"
