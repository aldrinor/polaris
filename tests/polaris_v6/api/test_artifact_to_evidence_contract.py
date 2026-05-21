"""I-cd-680 — build_evidence_contract_from_artifact coverage (Codex Option B).

Reuses the synthetic AuditIR-shape artifact builder from the slice-chain
tests. Verifies a REAL artifact_dir maps to a valid EvidenceContract with
NO fabricated source-document offsets (span_start=0, span_end=len of the
recorded span text — the truthful self-offset; rich offsets are deferred
to #710).
"""

from __future__ import annotations

import pytest

from polaris_v6.api.artifact_to_evidence_contract import (
    build_evidence_contract_from_artifact,
)
from polaris_v6.schemas.evidence_contract import EvidenceContract
from tests.polaris_v6.api.test_artifact_to_slice_chain import (
    _write_synthetic_artifact_dir,
)


def _build(tmp_path, **kw) -> EvidenceContract:
    artifact_dir = _write_synthetic_artifact_dir(tmp_path, **kw)
    return build_evidence_contract_from_artifact(
        artifact_dir,
        run_id="real_run_001",
        template="ai_sovereignty",
        question="What sovereign compute does Canada have?",
        queued_at="2026-05-20T00:00:00+00:00",
        finished_at="2026-05-20T00:10:00+00:00",
        pipeline_status="success",
    )


def test_real_artifact_builds_valid_evidence_contract(tmp_path):
    ec = _build(tmp_path)
    assert isinstance(ec, EvidenceContract)
    assert ec.run_id == "real_run_001"
    assert ec.template == "ai_sovereignty"
    assert ec.contract_version == "1.0"
    # Run metadata threaded from the caller (run_store), not the artifact.
    assert ec.question.startswith("What sovereign")
    assert ec.pipeline_status == "success"


def test_evidence_pool_offsets_are_truthful_self_offsets(tmp_path):
    """No fabricated source-document offsets (Codex Option B). Each SourceSpan
    has span_start=0 and span_end=len(span_text) — the recorded span IS the
    text; rich offsets into the original source body are deferred (#710)."""
    ec = _build(tmp_path)
    assert ec.evidence_pool, "expected at least one cleared (T1) source"
    for span in ec.evidence_pool:
        assert span.span_start == 0
        assert span.span_end == len(span.span_text)
        assert span.span_text  # non-empty
        assert span.source_tier in ("T1", "T2", "T3")


def test_verified_sentences_carry_provenance(tmp_path):
    ec = _build(tmp_path)
    assert ec.verified_sentences, "expected verified sentences from the report"
    for s in ec.verified_sentences:
        assert s.section_id
        assert s.sentence_text
        # provenance_tokens is a list[str] mapped straight from the slice-chain.
        assert isinstance(s.provenance_tokens, list)


def test_models_and_cost_threaded_from_slice_chain(tmp_path):
    ec = _build(tmp_path, cost_usd=1.23)
    assert ec.cost_usd == pytest.approx(1.23)
    assert ec.generator_model  # non-empty (from manifest models block / default)
    assert ec.verifier_model
    assert isinstance(ec.family_segregation_passed, bool)
