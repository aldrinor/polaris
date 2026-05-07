"""Tests for bundle_builder — end-to-end audit bundle assembly."""

from __future__ import annotations

import hashlib
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polaris_graph.audit_bundle.bundle_builder import (
    build_audit_bundle,
    extract_manifest_from_bundle,
)
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

def _src(source_id: str = "src-A", full_text: str = "trial of aspirin") -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
        provenance={"legal_cleared": True},
    )


def _pool() -> EvidencePool:
    return EvidencePool(
        pool_id="pool-fixed-1",
        decision_id="dec-fixed-1",
        sources=[_src()],
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 1, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _decision() -> ScopeDecision:
    return ScopeDecision(
        decision_id="dec-fixed-1",
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


def _report(pool_id: str = "pool-fixed-1", decision_id: str = "dec-fixed-1") -> VerifiedReport:
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
    return VerifiedReport(
        pool_id=pool_id,
        decision_id=decision_id,
        sections=[section],
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="test/model",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _stub_sign(payload: bytes) -> bytes:
    """Test stub: synthesize a fake .asc that includes a hash anchor."""
    digest = hashlib.sha256(payload).hexdigest()
    return (
        f"-----BEGIN PGP SIGNATURE-----\n"
        f"# stub signature for tests; hash={digest}\n"
        f"-----END PGP SIGNATURE-----\n"
    ).encode("utf-8")


# ---------- Validation ----------

def test_build_rejects_default_sentinel_sign_fn(tmp_path: Path):
    """Default sign_fn must raise — no silent unsigned bundles."""
    with pytest.raises(RuntimeError, match="sign_fn"):
        build_audit_bundle(_decision(), _pool(), _report(), output_dir=tmp_path)


def test_build_rejects_pool_id_mismatch(tmp_path: Path):
    pool = _pool()
    bad_report = _report(pool_id="other-pool-id")
    with pytest.raises(ValueError, match="pool_id"):
        build_audit_bundle(
            _decision(), pool, bad_report, output_dir=tmp_path, sign_fn=_stub_sign
        )


def test_build_rejects_decision_id_mismatch(tmp_path: Path):
    bad_report = _report(decision_id="other-decision-id")
    with pytest.raises(ValueError, match="decision_id"):
        build_audit_bundle(
            _decision(), _pool(), bad_report, output_dir=tmp_path, sign_fn=_stub_sign
        )


def test_build_rejects_non_success_verdict(tmp_path: Path):
    """The manifest_builder rejects non-success verdicts; bundle_builder
    surfaces that."""
    failed_report = VerifiedReport(
        pool_id="pool-fixed-1",
        decision_id="dec-fixed-1",
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
        build_audit_bundle(
            _decision(), _pool(), failed_report, output_dir=tmp_path, sign_fn=_stub_sign
        )


# ---------- Happy path ----------

def test_build_produces_targz(tmp_path: Path):
    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=_stub_sign
    )
    assert bundle_path.exists()
    assert bundle_path.suffixes == [".tar", ".gz"]
    assert bundle_path.stat().st_size > 0
    assert tarfile.is_tarfile(bundle_path)


def test_bundle_contains_required_files(tmp_path: Path):
    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=_stub_sign
    )
    with tarfile.open(bundle_path, "r:gz") as tar:
        names = [m.name for m in tar.getmembers()]
    # Must contain manifest + signature + 3 BPEI artifacts + metadata + 1 source
    assert any(n.endswith("manifest.yaml") and not n.endswith(".asc") for n in names)
    assert any(n.endswith("manifest.yaml.asc") for n in names)
    assert any(n.endswith("scope_decision.json") for n in names)
    assert any(n.endswith("evidence_pool.json") for n in names)
    assert any(n.endswith("verified_report.json") for n in names)
    assert any(n.endswith("metadata.json") for n in names)
    assert any("/sources/" in n and n.endswith(".txt") for n in names)


def test_bundle_files_have_top_level_dir(tmp_path: Path):
    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=_stub_sign
    )
    with tarfile.open(bundle_path, "r:gz") as tar:
        names = tar.getnames()
    # All files share a single top-level audit_<id>/ prefix
    top_dirs = {n.split("/")[0] for n in names if "/" in n}
    assert len(top_dirs) == 1
    assert next(iter(top_dirs)).startswith("audit_")


def test_bundle_filename_includes_bundle_id(tmp_path: Path):
    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=_stub_sign
    )
    assert bundle_path.name.startswith("audit_")
    assert bundle_path.name.endswith(".tar.gz")


def test_bundle_signature_is_what_sign_fn_returned(tmp_path: Path):
    captured = {}

    def capture_sign(payload: bytes) -> bytes:
        captured["payload"] = payload
        return b"-----BEGIN PGP SIGNATURE-----\nstub\n-----END PGP SIGNATURE-----\n"

    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=capture_sign
    )
    with tarfile.open(bundle_path, "r:gz") as tar:
        sig_member = next(m for m in tar.getmembers() if m.name.endswith(".asc"))
        sig_data = tar.extractfile(sig_member).read()
    assert sig_data == b"-----BEGIN PGP SIGNATURE-----\nstub\n-----END PGP SIGNATURE-----\n"
    # And the payload signed was the manifest yaml — it should be parseable
    assert b"bundle_id" in captured["payload"]
    assert b"decision_id" in captured["payload"]


def test_sign_fn_exception_propagates_as_runtime_error(tmp_path: Path):
    def boom(_: bytes) -> bytes:
        raise OSError("simulated")

    with pytest.raises(RuntimeError, match="OSError"):
        build_audit_bundle(
            _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=boom
        )


def test_extract_manifest_from_bundle_round_trip(tmp_path: Path):
    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=_stub_sign
    )
    manifest, manifest_bytes, sig_bytes = extract_manifest_from_bundle(bundle_path)
    assert manifest.decision_id == "dec-fixed-1"
    assert manifest.pool_id == "pool-fixed-1"
    assert manifest_bytes.startswith(b"bundle_") or b"bundle_id" in manifest_bytes
    assert sig_bytes.startswith(b"-----BEGIN PGP SIGNATURE-----")


def test_extract_manifest_files_match_sha256(tmp_path: Path):
    """SHA256 anchor in manifest matches actual file bytes in tarball.

    This is the fundamental audit-bundle integrity guarantee."""
    bundle_path = build_audit_bundle(
        _decision(), _pool(), _report(), output_dir=tmp_path, sign_fn=_stub_sign
    )
    manifest, _yaml, _sig = extract_manifest_from_bundle(bundle_path)

    with tarfile.open(bundle_path, "r:gz") as tar:
        for entry in manifest.files:
            # tarball stores files under audit_<id>/ prefix
            top_dir = next(
                m.name for m in tar.getmembers()
                if m.name.endswith("manifest.yaml") and not m.endswith(".asc") if False
            ) if False else None
            # Find the file in tar by suffix match
            target = None
            for m in tar.getmembers():
                if m.name.endswith("/" + entry.path):
                    target = m
                    break
            assert target is not None, f"file {entry.path} not in tarball"
            data = tar.extractfile(target).read()
            actual_hash = hashlib.sha256(data).hexdigest()
            assert actual_hash == entry.sha256, (
                f"hash mismatch for {entry.path}: "
                f"manifest={entry.sha256}, actual={actual_hash}"
            )
            assert len(data) == entry.size_bytes
