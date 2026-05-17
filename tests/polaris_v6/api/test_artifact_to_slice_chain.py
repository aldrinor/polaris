"""I-arch-001d — artifact_to_slice_chain bridge coverage.

Tests use a synthetic AuditIR-shape artifact dir built in tmp_path so the
bridge is exercised end-to-end without depending on a canonical V30 run.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polaris_v6.api.artifact_to_slice_chain import (
    SovereigntyFilterEmptiedReportError,
    _evidence_ids_in_tokens,
    _normalize_drop_reason,
    _normalize_tier,
    build_slice_chain,
)
from polaris_graph.retrieval2.evidence_pool import SourceTier


# ---------------------------------------------------------------------------
# Synthetic AuditIR-shape fixture builder
# ---------------------------------------------------------------------------


def _write_synthetic_artifact_dir(
    tmp_path: Path,
    *,
    bibliography_entries: list[dict] | None = None,
    sentences_per_section: int = 2,
    section_titles: list[str] | None = None,
    cited_evidence_ids_per_sentence: list[list[str]] | None = None,
    pipeline_status: str = "success",
    cost_usd: float = 0.42,
) -> Path:
    """Build a minimal AuditIR-loadable artifact dir.

    Shape matches src/polaris_graph/audit_ir/loader.py:961 load_audit_ir
    required files: manifest.json + report.md + bibliography.json +
    contradictions.json + verification_details.json.
    """
    artifact_dir = tmp_path / "synthetic_run"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    bib = bibliography_entries or [
        {"num": 1, "evidence_id": "ev_001", "statement": "FDA: tirzepatide indicated for T2D.", "tier": "T1", "url": "https://www.fda.gov/drugs/tirzepatide"},
        {"num": 2, "evidence_id": "ev_002", "statement": "NEJM 2024 trial reports A1c reduction.", "tier": "T2", "url": "https://www.nejm.org/doi/full/10.1056/NEJMtirz"},
    ]
    titles = section_titles or ["Summary", "Efficacy"]

    # Manifest with the keys loader._parse_manifest requires.
    manifest = {
        "run_id": "SWEEP_synthetic_001",
        "slug": "synthetic_q",
        "status": pipeline_status,
        "question": "Is tirzepatide effective for type 2 diabetes?",
        "protocol_sha256": "a" * 64,
        "evaluator_gate": {
            "gate_class": "release",
            "release_allowed": True,
            "reasons": [],
            "rule_blockers": [],
            "judge_critical_axes": [],
            "judge_parse_ok": True,
        },
        "completeness": {"percent": 100.0, "covered": 1, "total": 1},
        "cost_usd": cost_usd,
        "budget_cap_usd": 5.0,
        "generator": {"words": 100, "sentences_verified": 4, "sentences_dropped": 0},
        "contradictions_found": 0,
        "release_allowed": True,
        "v30_enabled": True,
        "v30_warnings": [],
        # I-arch-001d v6 fields (read directly by bridge, not via loader):
        "domain": "clinical",
        "scope": {"decision_id": "dec-synthetic-001", "classification": "clinical_efficacy"},
        "retrieval": {
            "started_at": "2026-05-13T01:00:00+00:00",
            "finished_at": "2026-05-13T01:05:00+00:00",
            "latency_ms": 300_000,
            "queries_executed": ["query 1", "query 2"],
            "pool_id": "pool-synthetic-001",
        },
        "models": {"generator": "gen-synth-v1", "evaluator": "strict_verify_v1"},
        # Loader-required blocks not specific to v6:
        "frame_coverage_report": {
            "entries": [],
            "by_status": {"pass": 1, "partial": 0},
            "frame_gap_count": 0,
            "pipeline_fault_count": 0,
            "total_entities": 1,
            "total_slots": 1,
            "research_question": "Is tirzepatide effective for type 2 diabetes?",
            "schema_version": "1.0",
        },
        "corpus": {
            "tier_fractions": {"T1": 1.0, "T2": 0.0, "T3": 0.0},
            "count": 2,
            "approved": True,
            "material_deviation": False,
        },
    }
    (artifact_dir / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))

    # Verification details — sections list with kept[] / dropped[] keys per loader._parse_verified_report.
    sections = []
    for sec_idx, title in enumerate(titles):
        kept_sentences = []
        for i in range(sentences_per_section):
            cited_ids = (
                cited_evidence_ids_per_sentence[sec_idx * sentences_per_section + i]
                if cited_evidence_ids_per_sentence
                else [bib[i % len(bib)]["evidence_id"]]
            )
            tokens = [{"evidence_id": eid, "start": 0, "end": 100} for eid in cited_ids]
            kept_sentences.append({
                "sentence": f"Synthetic sentence {i} in {title}.",
                "tokens": tokens,
                "failure_reasons": [],
            })
        sections.append({
            "title": title,
            "kept": kept_sentences,
            "dropped": [],
            "total_kept": sentences_per_section,
            "total_dropped": 0,
            "total_in": sentences_per_section,
            "dropped_due_to_failure": 0,
        })
    verification = {
        "sections": sections,
        "totals": {
            "sentences_verified": sum(s["total_kept"] for s in sections),
            "sentences_dropped": 0,
        },
        "drop_reason_counts": {},
    }
    (artifact_dir / "verification_details.json").write_text(json.dumps(verification, sort_keys=True))

    # bibliography.json is a list directly per loader._parse_bibliography (line 510-512).
    (artifact_dir / "bibliography.json").write_text(json.dumps(bib, sort_keys=True))
    # contradictions.json is a list per loader._parse_contradictions (line 549).
    (artifact_dir / "contradictions.json").write_text(json.dumps([]))
    (artifact_dir / "report.md").write_text("# Synthetic Report\n\nBody.\n")
    # Optional: frame_coverage.json + tier_mix.json (loader will tolerate absence).
    return artifact_dir


# ---------------------------------------------------------------------------
# Tier + drop_reason unit tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw,canonical,raw_kept", [
    ("T1", SourceTier.T1, "T1"),
    ("T2", SourceTier.T2, "T2"),
    ("T3", SourceTier.T3, "T3"),
    ("T4", SourceTier.T3, "T4"),
    ("T7", SourceTier.T3, "T7"),
    ("UNKNOWN", SourceTier.T3, "UNKNOWN"),
    ("", SourceTier.T3, "UNKNOWN"),
])
def test_tier_normalization(raw, canonical, raw_kept):
    actual_tier, actual_raw = _normalize_tier(raw)
    assert actual_tier == canonical
    assert actual_raw == raw_kept


@pytest.mark.parametrize("raw,expected", [
    ("numeric_mismatch", "numeric_mismatch"),
    ("number_not_in_any_cited_span", "numeric_mismatch"),
    ("no_integer_overlap_any_cited_span", "numeric_mismatch"),
    ("overlap_too_low", "overlap_too_low"),
    ("no_content_word_overlap_any_cited_span", "overlap_too_low"),
    ("entailment_failed", "entailment_failed"),
    ("entailment_failed:semantic_judge_says_no", "entailment_failed"),
    ("trial_name_mismatch", "invalid_token"),
    ("garbage_unknown_reason", "invalid_token"),  # default
    (None, None),
])
def test_drop_reason_normalization(raw, expected):
    assert _normalize_drop_reason(raw) == expected


def test_evidence_ids_in_tokens():
    tokens = [
        "[#ev:ev_001:0-100]",
        "[#ev:ev_002:50-200]",
        "garbage no match",
    ]
    assert _evidence_ids_in_tokens(tokens) == {"ev_001", "ev_002"}


# ---------------------------------------------------------------------------
# Integration: build_slice_chain
# ---------------------------------------------------------------------------


def test_happy_path_returns_valid_pydantic_models(tmp_path):
    artifact_dir = _write_synthetic_artifact_dir(tmp_path)
    decision, pool, report = build_slice_chain(artifact_dir)
    # ScopeDecision
    assert decision.status == "in_scope"
    assert decision.scope_class == "clinical_efficacy"
    assert decision.decision_id == "dec-synthetic-001"
    # EvidencePool: only T1 sources kept (T2 excluded per sovereignty default)
    assert len(pool.sources) == 1
    assert pool.sources[0].source_id == "ev_001"
    assert pool.sources[0].tier == SourceTier.T1
    assert pool.sources[0].provenance["legal_cleared"] is True
    # VerifiedReport
    assert report.pipeline_verdict == "success"
    assert report.pool_id == pool.pool_id
    assert report.decision_id == decision.decision_id
    assert report.verifier_pass_threshold == 0.4
    assert report.cost_usd == 0.42
    assert report.generator_model == "gen-synth-v1"


def test_sovereignty_cascade_redacts_sentences_citing_non_cleared(tmp_path):
    """Sentences citing the T2-only source (ev_002) get redacted; T1-only sentences kept."""
    bib = [
        {"num": 1, "evidence_id": "ev_001", "statement": "T1 source.", "tier": "T1", "url": "https://www.fda.gov/a"},
        {"num": 2, "evidence_id": "ev_002", "statement": "T2 source.", "tier": "T2", "url": "https://www.example.com/b"},
    ]
    cited_per_sent = [
        ["ev_001"],            # sec1 sent0: cleared
        ["ev_002"],            # sec1 sent1: NOT cleared → redact
        ["ev_001", "ev_002"],  # sec2 sent0: mixed → redact (sovereignty cascade)
        ["ev_001"],            # sec2 sent1: cleared
    ]
    artifact_dir = _write_synthetic_artifact_dir(
        tmp_path,
        bibliography_entries=bib,
        section_titles=["A", "B"],
        cited_evidence_ids_per_sentence=cited_per_sent,
    )
    _, _, report = build_slice_chain(artifact_dir)
    # Section A: sent0 passes, sent1 redacted → pass_rate = 0.5, status="verified"
    sec_a = next(s for s in report.sections if s.section_title == "A")
    assert sec_a.section_verify_pass_rate == 0.5
    assert sec_a.section_status == "verified"
    # The redacted sentence should have verifier_pass=False + drop_reason=invalid_token + evaluator_agrees=False
    redacted = [s for s in sec_a.verified_sentences if not s.verifier_pass]
    assert len(redacted) == 1
    assert redacted[0].drop_reason == "invalid_token"
    assert redacted[0].evaluator_agrees is False


def test_sovereignty_emptied_report_raises(tmp_path):
    """When EVERY sentence cites a non-cleared source, all sections drop and error raises."""
    bib = [
        {"num": 1, "evidence_id": "ev_001", "statement": "T2.", "tier": "T2", "url": "https://www.example.com/x"},
    ]
    cited = [["ev_001"], ["ev_001"], ["ev_001"], ["ev_001"]]
    artifact_dir = _write_synthetic_artifact_dir(
        tmp_path,
        bibliography_entries=bib,
        section_titles=["A", "B"],
        cited_evidence_ids_per_sentence=cited,
    )
    with pytest.raises(SovereigntyFilterEmptiedReportError):
        build_slice_chain(artifact_dir)


def test_section_drops_when_no_passing_sentences(tmp_path):
    """A section with all sentences citing non-cleared sources → section_status='dropped'."""
    bib = [
        {"num": 1, "evidence_id": "ev_001", "statement": "T1.", "tier": "T1", "url": "https://www.fda.gov/a"},
        {"num": 2, "evidence_id": "ev_002", "statement": "T2.", "tier": "T2", "url": "https://www.example.com/b"},
    ]
    cited = [
        ["ev_001"],  # sec A sent0: passes
        ["ev_001"],  # sec A sent1: passes
        ["ev_002"],  # sec B sent0: redact
        ["ev_002"],  # sec B sent1: redact
    ]
    artifact_dir = _write_synthetic_artifact_dir(
        tmp_path,
        bibliography_entries=bib,
        section_titles=["A", "B"],
        cited_evidence_ids_per_sentence=cited,
    )
    _, _, report = build_slice_chain(artifact_dir)
    sec_b = next(s for s in report.sections if s.section_title == "B")
    assert sec_b.section_status == "dropped"
    sec_a = next(s for s in report.sections if s.section_title == "A")
    assert sec_a.section_status == "verified"
