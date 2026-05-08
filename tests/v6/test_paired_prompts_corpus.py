"""I-anti-001 — corpus invariants for paired-prompts fixture (≥20 entries,
all schema-valid, all 8 Carney priority domains present, defense anchor current)."""

from __future__ import annotations

import json
from pathlib import Path

from polaris_v6.sycophancy.paired_prompts import PairedPrompt

FIXTURE = (
    Path(__file__).parent / "fixtures" / "sycophancy_v1" / "paired_prompts.json"
)
CARNEY_DOMAIN_TOKENS = (
    "clinical", "trade", "housing", "defense", "climate",
    "ai_sov", "canada_us", "workforce",
)


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_corpus_has_at_least_twenty_entries() -> None:
    payload = _load()
    assert len(payload["paired_prompts"]) >= 20


def test_all_entries_validate_against_pydantic() -> None:
    payload = _load()
    for p in payload["paired_prompts"]:
        PairedPrompt.model_validate(p)


def test_anti_001_carney_priority_domains_present_and_defense_anchor_current() -> None:
    payload = _load()
    ids = [p["paired_id"] for p in payload["paired_prompts"]]
    for token in CARNEY_DOMAIN_TOKENS:
        assert any(token in pid for pid in ids), f"missing domain token: {token}"
    defense = next(p for p in payload["paired_prompts"] if p["paired_id"] == "syc_defense_001")
    assert defense["expected_factual_anchor"] == "achieved 2% NATO target in 2026"
