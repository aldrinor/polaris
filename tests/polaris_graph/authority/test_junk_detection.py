"""Smoke S5 (junk) — structural junk detection (Phase 0a, GH #983).

4 junk cases + 1 control. Each junk case fires its junk-class, lands
source_class in {PRESS_RELEASE, UGC, COMMENTARY}, caps authority_score at
JUNK_CEIL, and cites a matching reason. The control (legitimate primary
source) must NOT trip any junk pattern. Offline; no network.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
JUNK_DIR = REPO_ROOT / "tests" / "fixtures" / "authority" / "junk"
JUNK_CASES = ["press_release", "login_wall", "blog", "self_interest"]
_JUNK_CLASSES = {"PRESS_RELEASE", "UGC", "COMMENTARY"}


def _load(name: str) -> dict:
    path = JUNK_DIR / f"{name}.json"
    assert path.exists(), f"missing junk fixture: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _score(fixture: dict):
    from src.polaris_graph.authority import AuthoritySignals, score_source_authority
    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

    sig = ClassificationSignals(url=fixture["url"], title="")
    sig.authority = AuthoritySignals(**fixture["authority_signals"])
    sig.fetched_body = fixture.get("body", "")
    sig.structured_jsonld = fixture.get("jsonld", "")
    sig.claim_vendor_token = fixture.get("claim_vendor_token", "")
    return score_source_authority(sig)


def test_s5_junk_cases_fire_and_cap():
    from src.polaris_graph.authority.data_loader import load_authority_data

    junk_ceil = load_authority_data()["blend_weights"]["JUNK_CEIL"]
    failures: list[str] = []
    for name in JUNK_CASES:
        fixture = _load(name)
        result = _score(fixture)
        if result.source_class.value not in _JUNK_CLASSES:
            failures.append(f"{name}: source_class {result.source_class.value} not a junk class")
        if result.authority_score > junk_ceil:
            failures.append(
                f"{name}: score {result.authority_score:.3f} > JUNK_CEIL {junk_ceil}"
            )
        if not any("junk pattern fired" in r.lower() for r in result.reasons):
            failures.append(f"{name}: no junk reason present")
        want = fixture.get("expect_source_class")
        if want and result.source_class.value != want:
            failures.append(f"{name}: source_class {result.source_class.value} != {want}")
    assert not failures, f"S5 junk detection FAILED: {failures}"


def test_s5_control_primary_not_junk():
    fixture = _load("control_primary")
    result = _score(fixture)
    assert result.source_class.value not in _JUNK_CLASSES, (
        f"control primary falsely flagged junk: {result.source_class.value}"
    )
    assert result.source_class.value == fixture["expect_source_class"]
    # A legitimate primary with rich signals should clear the junk ceiling.
    assert result.authority_score > 0.25
