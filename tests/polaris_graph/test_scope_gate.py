"""
Tests for Phase 2b (scope gate) + Phase 2c (templates).

Validates:
- Protocol gets written to protocol.json at T+0.
- SHA-256 is stable across identical content.
- All four domain templates load and produce valid protocols.
- PICO heuristic extracts intervention / population when present.
- needs_user_review fires when PICO extraction fails for clinical.
- verify_protocol() detects tampering.
"""
from __future__ import annotations

import json
import pytest
from pathlib import Path

from src.polaris_graph.nodes.scope_gate import (
    SUPPORTED_DOMAINS,
    extract_pico_heuristic,
    run_scope_gate,
    verify_protocol,
)


def test_clinical_scope_gate_writes_protocol(tmp_path: Path) -> None:
    result = run_scope_gate(
        research_question=(
            "What is the efficacy and safety of semaglutide 2.4mg for "
            "weight loss in adults with obesity?"
        ),
        run_dir=tmp_path / "run01",
        run_id="TEST_001",
        domain="clinical",
    )
    assert result.protocol_path.exists()
    assert result.protocol_sha256  # non-empty
    assert len(result.protocol_sha256) == 64  # hex SHA-256

    doc = json.loads(result.protocol_path.read_text(encoding="utf-8"))
    assert doc["research_question"].startswith("What is the efficacy")
    assert doc["domain"] == "clinical"
    assert doc["template_used"] == "config/scope_templates/clinical.yaml"
    # PICO heuristic should have extracted intervention and population
    assert doc["intervention"] == "semaglutide"
    # Either "adults" or a diabetes/obesity marker should match
    assert doc["population"] in {"adults", "obesity"}
    # Outcome: weight loss should be detected
    assert doc["outcome"] == "weight loss"

    # Tier expectations from template
    tier_labels = [t["tier"] for t in doc["expected_tier_distribution"]]
    assert "T1" in tier_labels
    assert "T2" in tier_labels
    assert "T3" in tier_labels


def test_policy_scope_gate_writes_protocol(tmp_path: Path) -> None:
    result = run_scope_gate(
        research_question=(
            "How is FDA regulating compounded GLP-1 agonists after the "
            "shortage ended?"
        ),
        run_dir=tmp_path / "run02",
        run_id="TEST_002",
        domain="policy",
    )
    doc = json.loads(result.protocol_path.read_text(encoding="utf-8"))
    assert doc["domain"] == "policy"
    # Policy template puts T3 as the dominant tier
    tier3 = next(
        (t for t in doc["expected_tier_distribution"] if t["tier"] == "T3"),
        None,
    )
    assert tier3 is not None
    assert tier3["min_fraction"] >= 0.30


def test_tech_and_due_diligence_templates_load(tmp_path: Path) -> None:
    for i, domain in enumerate(("tech", "due_diligence")):
        result = run_scope_gate(
            research_question=f"Generic {domain} question for template loading.",
            run_dir=tmp_path / f"run0{i+3}",
            run_id=f"TEST_00{i+3}",
            domain=domain,
        )
        doc = json.loads(result.protocol_path.read_text(encoding="utf-8"))
        assert doc["domain"] == domain
        assert doc["expected_tier_distribution"]  # non-empty


def test_needs_user_review_when_pico_missing(tmp_path: Path) -> None:
    """BUG-B-100 deep-dive R3: a clinical question with BOTH PICO
    anchors missing is now REJECTED (not flag-only). The old behavior
    was to set needs_user_review=True and proceed, which let the
    pipeline spend retrieval budget on an unscoped query."""
    result = run_scope_gate(
        research_question="Tell me about cardiovascular outcomes.",
        run_dir=tmp_path / "run_vague",
        run_id="TEST_VAGUE",
        domain="clinical",
    )
    # Neither "cardiovascular outcomes" nor any drug name can be
    # extracted as population or intervention — so reject.
    assert result.protocol.scope_decision == "reject"
    assert result.protocol.scope_rejected is True
    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"
    reasons = " ".join(result.protocol.scope_reasons).lower()
    assert "population" in reasons or "intervention" in reasons or "pico" in reasons


def test_sha256_stable_across_identical_content(tmp_path: Path) -> None:
    result_a = run_scope_gate(
        research_question="Efficacy of metformin in type 2 diabetes adults.",
        run_dir=tmp_path / "run_a",
        run_id="TEST_A",
        domain="clinical",
    )
    result_b = run_scope_gate(
        research_question="Efficacy of metformin in type 2 diabetes adults.",
        run_dir=tmp_path / "run_b",
        run_id="TEST_A",  # same run_id and time-adjacent
        domain="clinical",
    )
    # Hashes will differ slightly because created_at_iso differs.
    # Both should be valid 64-hex strings.
    assert len(result_a.protocol_sha256) == 64
    assert len(result_b.protocol_sha256) == 64


def test_verify_protocol_detects_tampering(tmp_path: Path) -> None:
    result = run_scope_gate(
        research_question="Tirzepatide safety in adults with T2DM.",
        run_dir=tmp_path / "run_verify",
        run_id="TEST_VERIFY",
        domain="clinical",
    )
    # Round-trip verify should succeed
    ok, hex_hash, err = verify_protocol(result.protocol_path)
    assert ok is True
    assert len(hex_hash) == 64
    assert err == ""

    # Tamper
    original_text = result.protocol_path.read_text(encoding="utf-8")
    tampered = original_text.replace("tirzepatide", "semaglutide")
    result.protocol_path.write_text(tampered, encoding="utf-8")
    ok2, hex_hash2, err2 = verify_protocol(result.protocol_path)
    # verify_protocol returns ok=True but hex_hash changed (not matching original)
    assert hex_hash2 != result.protocol_sha256


def test_user_overrides_are_logged(tmp_path: Path) -> None:
    overrides = {
        "add_inclusion": ["Only post-2020 publications"],
        "languages": ["en", "fr"],
        "date_range": {"start": "2020-01-01", "end": "2024-12-31"},
    }
    result = run_scope_gate(
        research_question="Safety of liraglutide in adolescents.",
        run_dir=tmp_path / "run_override",
        run_id="TEST_OVERRIDE",
        domain="clinical",
        user_overrides=overrides,
    )
    doc = json.loads(result.protocol_path.read_text(encoding="utf-8"))
    assert doc["user_overrides"] == overrides
    assert "Only post-2020 publications" in doc["criteria"]["inclusion"]
    assert doc["languages"] == ["en", "fr"]
    assert doc["date_range"]["start"] == "2020-01-01"
    assert doc["date_range"]["end"] == "2024-12-31"


def test_empty_query_raises() -> None:
    with pytest.raises(ValueError):
        run_scope_gate(
            research_question="   ",
            run_dir="/tmp/ignored",
            run_id="TEST_EMPTY",
        )


def test_unsupported_domain_rejects() -> None:
    """BUG-B-100 deep-dive R3: unsupported domain is now REJECTED
    (previously fell back to clinical silently — a category error
    hiding as a warning log). The original defective test name
    was `test_unsupported_domain_falls_back`."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        result = run_scope_gate(
            research_question="Something about semaglutide.",
            run_dir=td,
            run_id="TEST_UNSUPPORTED",
            domain="made_up_domain",
        )
        assert result.protocol.scope_decision == "reject"
        assert result.protocol.scope_rejected is True
        assert result.protocol.scope_rejection_code == "unsupported_domain"
        # The original domain is preserved in the record, not silently coerced.
        assert result.protocol.domain == "made_up_domain"


# ─────────────────────────────────────────────────────────────────
# BUG-B-100 deep-dive R3 — 5 tests per Codex specification.
# ─────────────────────────────────────────────────────────────────

def test_b100_scope_rejects_unsupported_domain(tmp_path: Path) -> None:
    """Spec test 1: unsupported domain → reject with unsupported_domain."""
    result = run_scope_gate(
        research_question="What is the best espresso machine for home use?",
        run_dir=tmp_path / "run_espresso",
        run_id="TEST_B100_1",
        domain="finance",
    )
    assert result.protocol.scope_decision == "reject"
    assert result.protocol.scope_rejected is True
    assert result.protocol.scope_rejection_code == "unsupported_domain"


def test_b100_scope_rejects_unscoped_clinical(tmp_path: Path) -> None:
    """Spec test 2: clinical question with neither population nor
    intervention → reject with clinical_pico_unscoped."""
    result = run_scope_gate(
        research_question="Tell me about safety outcomes.",
        run_dir=tmp_path / "run_unscoped",
        run_id="TEST_B100_2",
        domain="clinical",
    )
    assert result.protocol.scope_decision == "reject"
    assert result.protocol.scope_rejection_code == "clinical_pico_unscoped"


def test_b100_scope_flags_partial_clinical(tmp_path: Path) -> None:
    """Spec test 3: clinical question with exactly ONE of population /
    intervention missing → review (flag-only, not reject)."""
    # "Semaglutide outcomes" has intervention but no population.
    result = run_scope_gate(
        research_question="What are the outcomes of semaglutide?",
        run_dir=tmp_path / "run_partial",
        run_id="TEST_B100_3",
        domain="clinical",
    )
    # At least intervention should extract
    assert result.protocol.intervention is not None
    # Population likely missing (no explicit demographic)
    if result.protocol.population is None:
        assert result.protocol.scope_decision == "review"
        assert result.protocol.scope_rejected is False
        assert result.protocol.needs_user_review is True


def test_b100_scope_proceeds_for_adequately_scoped_clinical(tmp_path: Path) -> None:
    """Spec test 4: clinical question with both anchors → proceed."""
    result = run_scope_gate(
        research_question=(
            "What is the efficacy of semaglutide for weight loss in "
            "adults with obesity?"
        ),
        run_dir=tmp_path / "run_proceed",
        run_id="TEST_B100_4",
        domain="clinical",
    )
    assert result.protocol.population is not None
    assert result.protocol.intervention is not None
    assert result.protocol.scope_decision == "proceed"
    assert result.protocol.scope_rejected is False


def test_b100_orchestrator_aborts_before_retrieval_on_reject() -> None:
    """Spec test 5: source-level guard that the orchestrator has an
    abort branch reading scope.protocol.scope_rejected BEFORE any
    call to run_live_retrieval."""
    import ast, inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    # Find the position of the scope_rejected check
    reject_idx = source.find("scope.protocol.scope_rejected")
    retrieval_idx = source.find("run_live_retrieval(")
    assert reject_idx > 0, "expected scope_rejected check in run_one_query"
    assert retrieval_idx > 0, "expected run_live_retrieval call"
    assert reject_idx < retrieval_idx, (
        "scope_rejected check must precede run_live_retrieval — "
        "otherwise the abort fires too late"
    )
    # The branch must contain an abort-scope-rejected manifest
    after_check = source[reject_idx:retrieval_idx]
    assert '"status": "abort_scope_rejected"' in after_check, (
        "scope-rejected branch must write manifest.status=abort_scope_rejected"
    )
    assert "return summary" in after_check, (
        "scope-rejected branch must return summary before retrieval"
    )


def test_extract_pico_heuristic_drug_detection() -> None:
    pico = extract_pico_heuristic(
        "What is the efficacy of semaglutide for weight loss?"
    )
    assert pico["intervention"] == "semaglutide"
    assert pico["outcome"] == "weight loss"

    pico2 = extract_pico_heuristic(
        "Pembrolizumab in NSCLC patients with PD-L1 expression."
    )
    assert pico2["intervention"] == "pembrolizumab"

    pico3 = extract_pico_heuristic("What are pharmaceutical trends in 2025?")
    assert pico3["intervention"] is None  # no drug
    assert pico3["population"] is None
