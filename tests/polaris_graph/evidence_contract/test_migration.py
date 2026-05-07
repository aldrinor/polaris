"""Tests for the contract version migration registry (I-ecg-004)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polaris_graph.evidence_contract import (
    ContractMigrationError,
    EvidenceContract,
    MIGRATIONS,
    migrate_contract,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_v1_minimal_loads_via_pydantic():
    raw = _load("v1_contract_minimal.json")
    c = EvidenceContract.model_validate(raw)
    assert c.contract_version == "1.0"
    assert c.expected_entities[0].name == "aspirin"


def test_v1_full_loads_via_pydantic():
    raw = _load("v1_contract_full.json")
    c = EvidenceContract.model_validate(raw)
    assert len(c.expected_entities) == 3
    assert len(c.expected_claims) == 3
    assert {j.value for j in c.jurisdictions} == {"CA", "US", "EU"}


def test_migrate_v1_to_v1_is_identity():
    raw = _load("v1_contract_minimal.json")
    out = migrate_contract(raw, target_version="1.0")
    assert out == raw


def test_migrate_unknown_source_version_raises():
    with pytest.raises(ContractMigrationError, match="no migration path"):
        migrate_contract({"contract_version": "0.5"}, target_version="1.0")


def test_migrate_missing_version_raises():
    with pytest.raises(ContractMigrationError, match="contract_version missing"):
        migrate_contract({"foo": "bar"}, target_version="1.0")


def test_migrate_unknown_target_version_raises():
    raw = _load("v1_contract_minimal.json")
    with pytest.raises(ContractMigrationError, match="no migration path"):
        migrate_contract(raw, target_version="99.0")


def test_v1_round_trip_through_migration():
    raw = _load("v1_contract_minimal.json")
    migrated = migrate_contract(raw, target_version="1.0")
    parsed = EvidenceContract.model_validate(migrated)
    dumped = json.loads(parsed.model_dump_json())
    assert dumped["research_question"] == raw["research_question"]
    assert dumped["expected_entities"][0]["name"] == "aspirin"
    assert dumped["contract_version"] == "1.0"


def test_migrations_registry_supports_future_v2():
    """Smoke test: when v2 lands, registering ('1.0', '2.0'): fn enables migration."""
    def _v1_to_v2(d: dict) -> dict:
        out = dict(d)
        out["new_v2_field"] = "added"
        return out

    MIGRATIONS[("1.0", "2.0")] = _v1_to_v2
    try:
        raw = _load("v1_contract_minimal.json")
        migrated = migrate_contract(raw, target_version="2.0")
        assert migrated["contract_version"] == "2.0"
        assert migrated["new_v2_field"] == "added"
    finally:
        del MIGRATIONS[("1.0", "2.0")]
