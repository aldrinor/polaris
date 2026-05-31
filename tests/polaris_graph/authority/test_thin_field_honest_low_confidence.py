"""Smoke S4 (contract parts 3+4) — honest LOW confidence on thin fields.

Over adversarial_thin_field.jsonl (grey-lit / non-English / niche-regional,
deliberately THIN OpenAlex), assert for EVERY source:
  - authority_confidence == "LOW" (never mislabeled HIGH)
  - source_class is NOT falsely PRIMARY_SCHOLARLY / PRIMARY_OFFICIAL
  - 0.1 <= authority_score <= 0.8 (honest uncertain mid-band)
  - reasons cite "thin OpenAlex coverage"
Offline; no network.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "authority" / "adversarial_thin_field.jsonl"

_BAND_LOW = 0.10
_BAND_HIGH = 0.80
_FALSE_AUTHORITY = {"PRIMARY_SCHOLARLY", "PRIMARY_OFFICIAL"}


def _load() -> list[dict]:
    assert FIXTURE.exists(), f"missing S4 thin fixture: {FIXTURE}"
    return [json.loads(ln) for ln in FIXTURE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_s4_thin_field_honest_low_confidence(monkeypatch):
    monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    from src.polaris_graph.authority import AuthoritySignals, score_source_authority
    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

    rows = _load()
    assert rows, "S4 thin fixture is empty"

    failures: list[str] = []
    for e in rows:
        sig = ClassificationSignals(url=e["url"], title="")
        sig.authority = AuthoritySignals(**e["authority_signals"])
        result = score_source_authority(sig)

        if result.authority_confidence.value != "LOW":
            failures.append(f"{e['url']}: confidence {result.authority_confidence.value} != LOW")
        if result.source_class.value in _FALSE_AUTHORITY:
            failures.append(f"{e['url']}: false-authority class {result.source_class.value}")
        if not (_BAND_LOW <= result.authority_score <= _BAND_HIGH):
            failures.append(
                f"{e['url']}: score {result.authority_score:.3f} outside honest band"
                f" [{_BAND_LOW}, {_BAND_HIGH}]"
            )
        if not any("thin openalex" in r.lower() for r in result.reasons):
            failures.append(f"{e['url']}: reasons do not cite thin OpenAlex coverage")

    assert not failures, f"S4 thin-field contract FAILED: {failures}"
