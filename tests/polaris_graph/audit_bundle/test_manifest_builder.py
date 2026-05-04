"""Tests for manifest_builder."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

import pytest
import yaml

from polaris_graph.audit_bundle.manifest_builder import (
    FILE_EVIDENCE_POOL,
    FILE_METADATA,
    FILE_SCOPE_DECISION,
    FILE_VERIFIED_REPORT,
    POLARIS_VERSION,
    SOURCES_DIR,
    _safe_source_filename,
    build_manifest_and_files,
    serialize_manifest_yaml,
)
from polaris_graph.audit_bundle.bundle_schema import BundleManifest
from polaris_graph.generator2.verified_report import (
    Section,
    VerifiedReport,
    VerifiedSentence,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)
from polaris_graph.scope.scope_decision import (
    AmbiguityAxis,
    ScopeDecision,
)


# ---------- Fixtures ----------

def _src(source_id: str, full_text: str = "src text") -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _decision() -> ScopeDecision:
    return ScopeDecision(
        decision_id="dec-1",
        status="in_scope",
        scope_class="clinical_efficacy",
        ambiguity_axes=[
            AmbiguityAxis(
                axis="population",
                plausible_interpretations=["adults"],
                needs_clarification=False,
            )
        ],
    )


def _report(
    pool_id: str = "pool-1",
    report_id: str | None = None,
    verdict: str = "success",
) -> VerifiedReport:
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id="sec_x",
                sentence_text="claim [#ev:src-A:0-3].",
                provenance_tokens=["[#ev:src-A:0-3]"],
                verifier_pass=True,
            )
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    kwargs = dict(
        pool_id=pool_id,
        decision_id="dec-1",
        sections=[section] if verdict == "success" else [],
        overall_verify_pass_rate=1.0 if verdict == "success" else 0.0,
        pipeline_verdict=verdict,
        generator_model="deepseek/deepseek-v4-pro",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )
    if report_id is not None:
        kwargs["report_id"] = report_id
    return VerifiedReport(**kwargs)  # type: ignore[arg-type]


# ---------- _safe_source_filename ----------

def test_safe_source_filename_uuid_form():
    fn = _safe_source_filename("550e8400-e29b-41d4-a716-446655440000")
    assert fn == f"{SOURCES_DIR}/550e8400-e29b-41d4-a716-446655440000.txt"


def test_safe_source_filename_strips_path_chars():
    fn = _safe_source_filename("../etc/passwd")
    assert ".." not in fn
    assert "/" not in fn.replace(SOURCES_DIR + "/", "")


def test_safe_source_filename_truncates_long_input():
    fn = _safe_source_filename("a" * 500)
    assert len(fn) < 200  # SOURCES_DIR + slash + 100 chars + .txt


def test_safe_source_filename_replaces_special_chars():
    fn = _safe_source_filename("src!@#$%^&*()")
    assert all(c.isalnum() or c in "-_/." for c in fn.replace(SOURCES_DIR + "/", "")[:-4])


# ---------- build_manifest_and_files ----------

def test_build_manifest_includes_all_required_files():
    pool = _pool(_src("src-A"))
    manifest, files = build_manifest_and_files(_decision(), pool, _report())
    paths = set(files.keys())
    assert FILE_SCOPE_DECISION in paths
    assert FILE_EVIDENCE_POOL in paths
    assert FILE_VERIFIED_REPORT in paths
    assert FILE_METADATA in paths
    # Source snapshots
    assert any(p.startswith(SOURCES_DIR + "/") for p in paths)


def test_build_manifest_sha256_matches_content():
    pool = _pool(_src("src-A"))
    manifest, files = build_manifest_and_files(_decision(), pool, _report())
    for entry in manifest.files:
        actual_hash = hashlib.sha256(files[entry.path]).hexdigest()
        assert entry.sha256 == actual_hash


def test_build_manifest_size_bytes_match():
    pool = _pool(_src("src-A"))
    manifest, files = build_manifest_and_files(_decision(), pool, _report())
    for entry in manifest.files:
        assert entry.size_bytes == len(files[entry.path])


def test_build_manifest_rejects_non_success_verdict():
    pool = _pool(_src("src-A"))
    bad_report = VerifiedReport(
        pool_id="pool-1",
        decision_id="dec-1",
        sections=[
            Section(
                section_id="sec_x",
                section_title="X",
                verified_sentences=[
                    VerifiedSentence(
                        section_id="sec_x",
                        sentence_text="bad",
                        verifier_pass=False,
                        drop_reason="numeric_mismatch",
                    )
                ],
                section_verify_pass_rate=0.0,
                section_status="dropped",
            )
        ],
        overall_verify_pass_rate=0.0,
        pipeline_verdict="abort_no_verified_sections",
        generator_model="m",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )
    with pytest.raises(ValueError, match="successful"):
        build_manifest_and_files(_decision(), pool, bad_report)


def test_build_manifest_files_sorted_by_path():
    pool = _pool(_src("src-Z"), _src("src-A"))
    # Note: report only cites src-A so src-Z is not snapshotted
    manifest, _files = build_manifest_and_files(_decision(), pool, _report())
    paths = [f.path for f in manifest.files]
    assert paths == sorted(paths)


def test_build_manifest_propagates_decision_pool_report_ids():
    pool = _pool(_src("src-A"))
    decision = _decision()
    report = _report(pool_id="pool-7")
    manifest, _files = build_manifest_and_files(decision, pool, report)
    assert manifest.decision_id == decision.decision_id
    assert manifest.pool_id == "pool-7"
    assert manifest.report_id == report.report_id


def test_build_manifest_includes_polaris_version():
    pool = _pool(_src("src-A"))
    manifest, _files = build_manifest_and_files(_decision(), pool, _report())
    assert manifest.polaris_version == POLARIS_VERSION


def test_build_manifest_metadata_file_has_canonical_json():
    pool = _pool(_src("src-A"))
    _manifest, files = build_manifest_and_files(_decision(), pool, _report())
    metadata_bytes = files[FILE_METADATA]
    metadata = json.loads(metadata_bytes.decode("utf-8"))
    assert metadata["bundle_version"] == "1.0"
    assert metadata["polaris_version"] == POLARIS_VERSION
    assert metadata["generator_model"] == "deepseek/deepseek-v4-pro"
    assert metadata["source_snapshot_count"] == 1


def test_build_manifest_dedupes_sources():
    """Same source cited twice should appear once in snapshots."""
    pool = _pool(_src("src-A"))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            VerifiedSentence(
                section_id="sec_x",
                sentence_text="claim 1 [#ev:src-A:0-3].",
                provenance_tokens=["[#ev:src-A:0-3]"],
                verifier_pass=True,
            ),
            VerifiedSentence(
                section_id="sec_x",
                sentence_text="claim 2 [#ev:src-A:5-8].",
                provenance_tokens=["[#ev:src-A:5-8]"],
                verifier_pass=True,
            ),
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    report = VerifiedReport(
        pool_id="pool-1",
        decision_id="dec-1",
        sections=[section],
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="m",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )
    manifest, files = build_manifest_and_files(_decision(), pool, report)
    src_files = [
        p for p in files.keys() if p.startswith(SOURCES_DIR + "/")
    ]
    assert len(src_files) == 1


def test_build_manifest_canonical_json_stable_across_runs():
    """Re-serializing the same input must produce identical bytes."""
    pool = _pool(_src("src-A"))
    decision = _decision()
    report = _report()
    _, files1 = build_manifest_and_files(decision, pool, report)
    _, files2 = build_manifest_and_files(decision, pool, report)
    # ScopeDecision and EvidencePool serialization should be deterministic
    # (modulo timestamps/uuids which are baked into the inputs)
    assert files1[FILE_SCOPE_DECISION] == files2[FILE_SCOPE_DECISION]
    assert files1[FILE_EVIDENCE_POOL] == files2[FILE_EVIDENCE_POOL]
    assert files1[FILE_VERIFIED_REPORT] == files2[FILE_VERIFIED_REPORT]


# ---------- serialize_manifest_yaml ----------

def test_serialize_manifest_yaml_roundtrips():
    manifest = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="m",
        polaris_version="6.2.0",
    )
    yaml_bytes = serialize_manifest_yaml(manifest)
    parsed = yaml.safe_load(yaml_bytes.decode("utf-8"))
    assert parsed["decision_id"] == "dec-1"
    assert parsed["bundle_version"] == "1.0"


def test_serialize_manifest_yaml_stable():
    manifest = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="m",
        polaris_version="6.2.0",
    )
    a = serialize_manifest_yaml(manifest)
    b = serialize_manifest_yaml(manifest)
    assert a == b
