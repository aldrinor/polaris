"""Manifest builder — collects all bundle content + computes SHA256s.

Per `.codex/slices/slice_004/architecture_proposal.md` §"manifest_builder".

Given a ScopeDecision + EvidencePool + VerifiedReport (the research chain
output), serializes each to canonical JSON, snapshots cited source
texts, and assembles a BundleManifest with SHA256 anchors over every
content file.

The manifest itself is YAML-serialized (canonical sort keys); GPG signs
that YAML. External verifiers re-serialize the manifest and re-verify
the signature.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import yaml

from polaris_graph.audit_bundle.bundle_schema import (
    BUNDLE_VERSION,
    BundleManifest,
    FileEntry,
)
from pathlib import Path

from polaris_graph.audit_bundle.snapshot_sources import (
    snapshot_sources,
    snapshot_sources_with_reachable,
)
from polaris_graph.audit_bundle.sovereignty_guard import (
    assert_all_pool_sources_legal_cleared,
)
from polaris_graph.clinical_generator.provenance import extract_tokens
from polaris_graph.clinical_generator.verified_report import VerifiedReport
from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool
from polaris_graph.scope.scope_decision import ScopeDecision


POLARIS_VERSION = "6.2.0"

# Canonical filenames inside the bundle. External verifiers depend on
# these; do not rename without bumping bundle_version.
FILE_SCOPE_DECISION = "scope_decision.json"
FILE_EVIDENCE_POOL = "evidence_pool.json"
FILE_VERIFIED_REPORT = "verified_report.json"
FILE_METADATA = "metadata.json"
FILE_REVIEWER_README = "REVIEWER_README.md"
# I-gen-004 (#496): raw model reasoning channel; mirrors
# generator.reasoning_trace.REASONING_TRACE_FILENAME.
FILE_REASONING_TRACE = "reasoning_trace.jsonl"
SOURCES_DIR = "sources"

# I-gen-561 (#561) P2-5: tar members that bundle_builder writes ALONGSIDE the
# packed content files (manifest.yaml + its detached signature). They never
# appear in `files_bytes`, so an `extra_files` path equal to one of these
# would pass the core-file collision check yet still clash at pack time.
_RESERVED_TAR_MEMBERS = frozenset({"manifest.yaml", "manifest.yaml.asc"})


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _serialize_json_canonical(model: Any) -> bytes:
    """Pydantic model -> deterministic UTF-8 JSON bytes.

    sort_keys + no extra whitespace beyond standard separators ensures
    re-serialization on the verifier side produces identical bytes →
    SHA256 stable across implementations.
    """
    if hasattr(model, "model_dump"):
        payload = model.model_dump(mode="json")
    else:
        payload = model
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def _assert_cited_spans_reachable(report: VerifiedReport, snapshots: dict) -> None:
    """Raise ValueError if any cited span exceeds its snapshot's reachable_chars.

    Validates the UNION of tokens parsed from `sentence.sentence_text` and
    `sentence.provenance_tokens`, deduped by `token.raw`. Missing source_id =>
    unreachable. Span end > reachable_chars => unreachable.
    """
    seen: set[str] = set()
    for section in report.sections:
        if section.section_status == "dropped":
            continue
        for sentence in section.verified_sentences:
            if not sentence.verifier_pass:
                continue
            tokens = list(extract_tokens(sentence.sentence_text))
            for raw in sentence.provenance_tokens:
                tokens.extend(extract_tokens(raw))
            for tok in tokens:
                if tok.raw in seen:
                    continue
                seen.add(tok.raw)
                entry = snapshots.get(tok.source_id)
                if entry is None:
                    raise ValueError(
                        f"cited span unreachable after snapshot: source "
                        f"{tok.source_id!r} not in snapshots (token={tok.raw!r})"
                    )
                if not (0 <= tok.span_start < tok.span_end <= entry.reachable_chars):
                    raise ValueError(
                        f"cited span unreachable after snapshot: source "
                        f"{tok.source_id!r} token={tok.raw!r} span="
                        f"{tok.span_start}-{tok.span_end} reachable={entry.reachable_chars}"
                    )


def _safe_source_filename(source_id: str) -> str:
    """Build a tar-safe filename from a source_id.

    source_id is opaque (uuid by default, but could be 'src-1' etc). We
    sanitize aggressively: only [a-zA-Z0-9_-]. Anything else becomes _.
    Length-capped at 100 chars to avoid pathological inputs.
    """
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in source_id
    )[:100]
    return f"{SOURCES_DIR}/{safe}.txt"


def build_manifest_and_files(
    decision: ScopeDecision,
    pool: EvidencePool,
    report: VerifiedReport,
    *,
    extra_files: dict[str, tuple[bytes, str]] | None = None,
) -> tuple[BundleManifest, dict[str, bytes]]:
    """Build the bundle manifest + content-file dict.

    Args:
        extra_files: optional {path: (content_bytes, content_type)} of
            caller-supplied artifacts to include + hash in the signed
            manifest — I-gen-004 (#496) threads the run's
            reasoning_trace.jsonl through here. Each path must NOT
            collide with a core bundle file.

    Returns:
        (manifest, files) where files is {path: content_bytes}. The
        caller (bundle_builder) packs files into a tarball and writes
        the manifest.yaml + manifest.yaml.asc alongside.

    Raises:
        ValueError if report.pipeline_verdict != 'success', or if an
        extra_files path collides with a core bundle file.
    """
    if report.pipeline_verdict != "success":
        raise ValueError(
            f"cannot build audit bundle for verdict "
            f"{report.pipeline_verdict!r}; report must be successful"
        )

    files_bytes: dict[str, bytes] = {}

    # 1. Slice 001 ScopeDecision
    sd_bytes = _serialize_json_canonical(decision)
    files_bytes[FILE_SCOPE_DECISION] = sd_bytes

    # 2. Slice 002 EvidencePool
    ep_bytes = _serialize_json_canonical(pool)
    files_bytes[FILE_EVIDENCE_POOL] = ep_bytes

    # 3. Slice 003 VerifiedReport
    vr_bytes = _serialize_json_canonical(report)
    files_bytes[FILE_VERIFIED_REPORT] = vr_bytes

    # 4. Sovereignty: refuse to ship verbatim spans for non-cleared sources
    assert_all_pool_sources_legal_cleared(pool)

    # 4b. Per-source snapshots + cited-span reachability guard
    snapshot_entries = snapshot_sources_with_reachable(report, pool)
    _assert_cited_spans_reachable(report, snapshot_entries)
    for source_id, entry in snapshot_entries.items():
        files_bytes[_safe_source_filename(source_id)] = entry.text.encode("utf-8")
    snapshots = {sid: e.text for sid, e in snapshot_entries.items()}

    # 4b. REVIEWER_README ships verbatim in every bundle as metadata content_type.
    readme_path = Path(__file__).parent / "REVIEWER_README.md"
    files_bytes[FILE_REVIEWER_README] = readme_path.read_bytes()

    # 5. Bundle metadata (versions + creation timestamp)
    metadata = {
        "bundle_version": BUNDLE_VERSION,
        "polaris_version": POLARIS_VERSION,
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "generator_model": report.generator_model,
        "decision_id": decision.decision_id,
        "pool_id": report.pool_id,
        "report_id": report.report_id,
        "source_snapshot_count": len(snapshots),
    }
    files_bytes[FILE_METADATA] = json.dumps(
        metadata,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")

    # I-gen-004 (#496): merge caller-supplied extra files (e.g. the run's
    # reasoning_trace.jsonl). Each carries its own content_type; a path
    # collision with a core bundle file is a hard error.
    extra_content_types: dict[str, str] = {}
    for path, (content, ct_extra) in (extra_files or {}).items():
        if path in files_bytes:
            raise ValueError(
                f"extra_files path {path!r} collides with a core bundle file"
            )
        if path in _RESERVED_TAR_MEMBERS:
            raise ValueError(
                f"extra_files path {path!r} collides with a reserved tar "
                f"member ({sorted(_RESERVED_TAR_MEMBERS)} are written "
                f"alongside the packed files)"
            )
        files_bytes[path] = content
        extra_content_types[path] = ct_extra

    # Build FileEntry list with content_type tags
    file_entries: list[FileEntry] = []
    content_type_by_path = {
        FILE_SCOPE_DECISION: "scope_decision",
        FILE_EVIDENCE_POOL: "evidence_pool",
        FILE_VERIFIED_REPORT: "verified_report",
        FILE_METADATA: "metadata",
    }
    for path, content in files_bytes.items():
        ct = (
            content_type_by_path.get(path)
            or extra_content_types.get(path)
            or (
                "source_snapshot"
                if path.startswith(SOURCES_DIR + "/")
                else "metadata"
            )
        )
        file_entries.append(
            FileEntry(
                path=path,
                sha256=_sha256_bytes(content),
                size_bytes=len(content),
                content_type=ct,  # type: ignore[arg-type]
            )
        )

    # Sort entries deterministically for stable manifest output
    file_entries.sort(key=lambda f: f.path)

    manifest = BundleManifest(
        decision_id=decision.decision_id,
        pool_id=report.pool_id,
        report_id=report.report_id,
        generator_model=report.generator_model,
        polaris_version=POLARIS_VERSION,
        files=file_entries,
    )
    return manifest, files_bytes


def serialize_manifest_yaml(manifest: BundleManifest) -> bytes:
    """Produce canonical YAML bytes for GPG signing.

    PyYAML default_flow_style=False + sort_keys=True keeps it stable
    across re-serializations.
    """
    payload = manifest.model_dump(mode="json")
    return yaml.safe_dump(
        payload,
        default_flow_style=False,
        sort_keys=True,
        allow_unicode=True,
    ).encode("utf-8")
