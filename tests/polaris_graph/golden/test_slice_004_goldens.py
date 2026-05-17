"""Slice 004 golden-test integration runner.

Each test_*.json fixture pairs:
  - decision/pool/report shape parameters (text, ids, verdict)
  - expected: BundleSuccess (with path constraints) OR BundleBuildError

The runner builds a real bundle (with a stub sign_fn — no GPG keypair
needed in CI) and asserts:
  - tarball is valid
  - manifest.yaml + manifest.yaml.asc both present
  - SHA256 anchors in manifest match actual file bytes
  - path constraints (must_contain / must_NOT_contain) hold

Discovery resolution mirrors slices 002+003:
  POLARIS_CONTROLS_PATH > sibling polaris-controls > .codex draft
"""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from polaris_graph.audit_bundle.bundle_builder import (
    build_audit_bundle,
    extract_manifest_from_bundle,
)
from polaris_graph.clinical_generator.verified_report import (
    Section,
    VerifiedReport,
    VerifiedSentence,
)
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)
from polaris_graph.scope.scope_decision import (
    AmbiguityAxis,
    ScopeDecision,
)


_POLARIS_ROOT = Path(__file__).resolve().parents[3]


def _find_slice_004_golden_dir() -> Path | None:
    env_path = os.environ.get("POLARIS_CONTROLS_PATH")
    if env_path:
        candidate = Path(env_path).expanduser().resolve()
        if (candidate / "golden" / "slice_004").is_dir():
            return candidate / "golden" / "slice_004"

    sibling = _POLARIS_ROOT.parent / "polaris-controls" / "golden" / "slice_004"
    if sibling.is_dir():
        return sibling

    draft = _POLARIS_ROOT / ".codex" / "slices" / "slice_004" / "golden_drafts"
    if draft.is_dir():
        return draft

    return None


def _slice_004_test_files() -> list[Path]:
    pc_dir = _find_slice_004_golden_dir()
    if pc_dir is None:
        return []
    return sorted(pc_dir.glob("test_*.json"))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def test_slice_004_golden_dir_resolvable():
    if _find_slice_004_golden_dir() is None:
        pytest.skip("slice 004 goldens not available")


def test_at_least_3_slice_004_golden_files_exist():
    files = _slice_004_test_files()
    if not files:
        pytest.skip("slice 004 goldens not available")
    assert len(files) >= 3


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _stub_sign(payload: bytes) -> bytes:
    digest = hashlib.sha256(payload).hexdigest()
    return (
        f"-----BEGIN PGP SIGNATURE-----\n# stub for tests; hash={digest}\n-----END PGP SIGNATURE-----\n"
    ).encode("utf-8")


def _build_inputs_from_spec(spec: dict) -> tuple[ScopeDecision, EvidencePool, VerifiedReport]:
    """Build the research chain inputs from a golden test spec."""
    iso = datetime.now(timezone.utc)
    decision = ScopeDecision(
        decision_id=spec["decision_id"],
        status="in_scope",
        scope_class=spec.get("scope_class", "clinical_efficacy"),
        ambiguity_axes=[
            AmbiguityAxis(
                axis="population",
                plausible_interpretations=["adults"],
                needs_clarification=False,
            )
        ],
    )

    # Build sources list. For test_001 single source; for test_002 two sources;
    # for test_003 verdict=abort, we still need a non-empty pool but the
    # report.verdict=abort means snapshot_sources skips everything.
    sources: list[Source] = []
    if spec.get("source_id"):
        sources.append(
            Source(
                url=spec["source_url"],
                domain=spec.get("source_domain", "example.com"),
                tier=SourceTier(spec.get("source_tier", "T1")),
                title=spec.get("source_title", "Source"),
                snippet=spec["source_full_text"][:200],
                full_text=spec["source_full_text"],
                full_text_available=True,
                source_id=spec["source_id"],
                provenance={"legal_cleared": True},
            )
        )
    if spec.get("kept_source_id"):
        sources.append(
            Source(
                url=spec["kept_source_url"],
                domain="nejm.org",
                tier=SourceTier.T2,
                title="Keeper",
                snippet=spec["kept_source_full_text"][:200],
                full_text=spec["kept_source_full_text"],
                full_text_available=True,
                source_id=spec["kept_source_id"],
                provenance={"legal_cleared": True},
            )
        )
    if spec.get("dropped_source_id"):
        sources.append(
            Source(
                url=spec["dropped_source_url"],
                domain="random-blog.example",
                tier=SourceTier.T3,
                title="Dropped",
                snippet=spec["dropped_source_full_text"][:200],
                full_text=spec["dropped_source_full_text"],
                full_text_available=True,
                source_id=spec["dropped_source_id"],
                provenance={"legal_cleared": True},
            )
        )

    if not sources:
        # test_003 abort path
        sources.append(
            Source(
                url="https://example.com/x",
                domain="example.com",
                tier=SourceTier.T1,
                title="placeholder",
                snippet="x",
                full_text="x" * 200,
                full_text_available=True,
                source_id="src-placeholder",
                provenance={"legal_cleared": True},
            )
        )

    pool = EvidencePool(
        pool_id=spec["pool_id"],
        decision_id=spec["decision_id"],
        sources=sources,
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={
                SourceTier.T1: sum(1 for s in sources if s.tier == SourceTier.T1),
                SourceTier.T2: sum(1 for s in sources if s.tier == SourceTier.T2),
                SourceTier.T3: sum(1 for s in sources if s.tier == SourceTier.T3),
            },
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=iso,
        retrieval_finished_at_utc=iso,
        latency_ms=0,
        cost_usd=0.0,
    )

    verdict = spec.get("verdict", "success")
    if verdict == "abort_no_verified_sections":
        sections = [
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
        ]
    elif spec.get("kept_source_id") and spec.get("dropped_source_id"):
        # Mixed-keep test: one kept, one dropped sentence, citing different sources
        sections = [
            Section(
                section_id="sec_x",
                section_title="X",
                verified_sentences=[
                    VerifiedSentence(
                        section_id="sec_x",
                        sentence_text=f"kept claim [#ev:{spec['kept_source_id']}:0-50].",
                        provenance_tokens=[f"[#ev:{spec['kept_source_id']}:0-50]"],
                        verifier_pass=True,
                    ),
                    VerifiedSentence(
                        section_id="sec_x",
                        sentence_text=f"dropped claim [#ev:{spec['dropped_source_id']}:0-30].",
                        provenance_tokens=[f"[#ev:{spec['dropped_source_id']}:0-30]"],
                        verifier_pass=False,
                        drop_reason="numeric_mismatch",
                    ),
                ],
                section_verify_pass_rate=0.5,
                section_status="verified",
            )
        ]
    else:
        sections = [
            Section(
                section_id="sec_x",
                section_title="X",
                verified_sentences=[
                    VerifiedSentence(
                        section_id="sec_x",
                        sentence_text=spec["verified_sentence_text"],
                        provenance_tokens=[
                            t for t in spec["verified_sentence_text"].split()
                            if t.startswith("[#ev:")
                        ] or [f"[#ev:{spec['source_id']}:0-100]"],
                        verifier_pass=True,
                    )
                ],
                section_verify_pass_rate=1.0,
                section_status="verified",
            )
        ]

    report = VerifiedReport(
        pool_id=spec["pool_id"],
        decision_id=spec["decision_id"],
        sections=sections,
        overall_verify_pass_rate=1.0 if verdict == "success" else 0.0,
        pipeline_verdict=verdict,
        generator_model="test/golden",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=iso,
        finished_at_utc=iso,
        latency_ms=0,
        cost_usd=0.0,
    )
    return decision, pool, report


# ---------------------------------------------------------------------------
# Per-golden execution
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "golden_path",
    _slice_004_test_files()
    or [pytest.param(None, marks=pytest.mark.skip(reason="no goldens"))],
    ids=lambda p: p.stem if p else "skipped",
)
def test_slice_004_golden(golden_path: Path | None, tmp_path: Path):
    if golden_path is None:
        pytest.skip("no goldens")

    spec = json.loads(golden_path.read_text(encoding="utf-8"))
    decision, pool, report = _build_inputs_from_spec(spec)
    expected = spec["expected"]
    kind = expected["kind"]

    if kind == "BundleBuildError":
        with pytest.raises(eval(expected["raises"])):
            build_audit_bundle(
                decision, pool, report,
                output_dir=tmp_path, sign_fn=_stub_sign,
            )
        return

    # BundleSuccess path
    bundle_path = build_audit_bundle(
        decision, pool, report,
        output_dir=tmp_path, sign_fn=_stub_sign,
    )
    assert bundle_path.exists()
    assert tarfile.is_tarfile(bundle_path)

    manifest, manifest_yaml, sig = extract_manifest_from_bundle(bundle_path)
    assert sig.startswith(b"-----BEGIN PGP SIGNATURE-----")

    if "min_files" in expected:
        assert len(manifest.files) >= expected["min_files"]

    with tarfile.open(bundle_path, "r:gz") as tar:
        names = [m.name for m in tar.getmembers()]

    if "must_contain_paths" in expected:
        for required_suffix in expected["must_contain_paths"]:
            assert any(
                n.endswith("/" + required_suffix) for n in names
            ), f"missing {required_suffix!r} in tarball"

    if "must_contain_path_substring" in expected:
        substr = expected["must_contain_path_substring"]
        assert any(substr in n for n in names), f"missing substring {substr!r}"

    if "must_NOT_contain_path_substring" in expected:
        substr = expected["must_NOT_contain_path_substring"]
        assert not any(substr in n for n in names), f"should NOT contain {substr!r}"

    # Always verify SHA256 anchors match
    with tarfile.open(bundle_path, "r:gz") as tar:
        for entry in manifest.files:
            target = next(
                (m for m in tar.getmembers() if m.name.endswith("/" + entry.path)),
                None,
            )
            assert target is not None, f"file {entry.path} missing"
            data = tar.extractfile(target).read()
            assert hashlib.sha256(data).hexdigest() == entry.sha256
