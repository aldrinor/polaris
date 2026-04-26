"""Tests for src/polaris_graph/audit_ir/serializer.py — JSON safe coercion."""

from __future__ import annotations

import json
from pathlib import Path

from src.polaris_graph.audit_ir import load_audit_ir
from src.polaris_graph.audit_ir.registry import CANONICAL_DEMO_DIR
from src.polaris_graph.audit_ir.serializer import to_json_dict


def test_to_json_dict_round_trips_canonical_run() -> None:
    """Whole IR serializes to JSON without errors."""
    ir = load_audit_ir(CANONICAL_DEMO_DIR)
    payload = to_json_dict(ir)
    serialized = json.dumps(payload)
    restored = json.loads(serialized)
    assert restored["run_id"] == ir.run_id
    assert restored["ir_schema_version"] == ir.ir_schema_version


def test_to_json_dict_handles_path() -> None:
    ir = load_audit_ir(CANONICAL_DEMO_DIR)
    payload = to_json_dict(ir)
    assert isinstance(payload["artifact_dir"], str)
    assert payload["artifact_dir"].endswith("clinical_tirzepatide_t2dm")


def test_to_json_dict_handles_mapping_proxy_in_tier_mix() -> None:
    """tier_mix.fractions is a MappingProxyType — must serialize as a dict."""
    ir = load_audit_ir(CANONICAL_DEMO_DIR)
    payload = to_json_dict(ir)
    fractions = payload["tier_mix"]["fractions"]
    assert isinstance(fractions, dict)
    assert "T1" in fractions
    assert isinstance(fractions["T1"], float)


def test_to_json_dict_preserves_contradiction_count() -> None:
    ir = load_audit_ir(CANONICAL_DEMO_DIR)
    payload = to_json_dict(ir)
    assert len(payload["contradictions"]) == 14
    assert payload["contradictions"][0]["claims"]


def test_to_json_dict_preserves_verified_report_sentences() -> None:
    """View 1 (M-3) reads sentences + tokens through this serialization."""
    ir = load_audit_ir(CANONICAL_DEMO_DIR)
    payload = to_json_dict(ir)
    sections = payload["verified_report"]["sections"]
    assert len(sections) > 0
    found = False
    for section in sections:
        for sentence in section["sentences"]:
            assert "claim_id" in sentence
            assert "tokens" in sentence
            for tok in sentence["tokens"]:
                assert "evidence_id" in tok
                assert "start" in tok
                assert "end" in tok
            if sentence["tokens"]:
                found = True
    assert found


def test_to_json_dict_preserves_model_provenance(ir: object = None) -> None:
    ir = load_audit_ir(CANONICAL_DEMO_DIR)
    payload = to_json_dict(ir)
    mp = payload["model_provenance"]
    assert mp is not None
    assert mp["generator_family"] == "deepseek"
    assert mp["evaluator_family"] == "qwen"
    assert len(mp["rule_checks"]) > 0
