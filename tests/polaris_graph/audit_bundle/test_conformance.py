"""Unit tests for `check_bundle_conformance` (I-cd-012 / GH#608).

Covers the 12 conformance layers + 4 path-safety negative cases per the
Codex iter-3 APPROVE'd brief.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from polaris_graph.audit_bundle.bundle_schema import (
    BUNDLE_VERSION,
    BundleManifest,
    FileEntry,
)
from polaris_graph.audit_bundle.conformance import (
    MANIFEST_FILENAME,
    SIGNATURE_FILENAME,
    check_bundle_conformance,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
CANONICAL_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "signed_bundle" / "v1_canonical"


# --------------------------------------------------------------------------
# Layer 0 — canonical fixture conforms
# --------------------------------------------------------------------------

def test_canonical_fixture_conforms() -> None:
    """The v1_canonical fixture round-trips clean (`valid=True`)."""
    result = check_bundle_conformance(CANONICAL_FIXTURE)
    assert result.valid, [
        f"{e.code}: {e.message}" for e in result.errors
    ]
    assert result.errors == []


# --------------------------------------------------------------------------
# Layer 1 — missing manifest
# --------------------------------------------------------------------------

def test_missing_manifest_yaml(tmp_path: Path) -> None:
    """Bundle dir without manifest.yaml → MISSING_MANIFEST."""
    (tmp_path / SIGNATURE_FILENAME).write_text("placeholder", encoding="utf-8")
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "MISSING_MANIFEST" for e in result.errors)


# --------------------------------------------------------------------------
# Layer 3 — missing / empty signature
# --------------------------------------------------------------------------

def test_missing_signature(tmp_path: Path) -> None:
    """Bundle without manifest.yaml.asc → MISSING_SIGNATURE."""
    _copy_canonical_to(tmp_path)
    (tmp_path / SIGNATURE_FILENAME).unlink()
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "MISSING_SIGNATURE" for e in result.errors)


def test_empty_signature(tmp_path: Path) -> None:
    """manifest.yaml.asc present but empty → EMPTY_SIGNATURE."""
    _copy_canonical_to(tmp_path)
    (tmp_path / SIGNATURE_FILENAME).write_text("", encoding="utf-8")
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "EMPTY_SIGNATURE" for e in result.errors)


# --------------------------------------------------------------------------
# Layer 4 — missing required content type
# --------------------------------------------------------------------------

def test_missing_required_content_type_scope_decision(tmp_path: Path) -> None:
    """Manifest without a scope_decision entry → MISSING_REQUIRED_CONTENT_TYPE."""
    _copy_canonical_to(tmp_path)
    manifest_path = tmp_path / MANIFEST_FILENAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["files"] = [
        f for f in data["files"] if f["content_type"] != "scope_decision"
    ]
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(
        e.code == "MISSING_REQUIRED_CONTENT_TYPE" and "scope_decision" in e.message
        for e in result.errors
    )


def test_empty_files_list(tmp_path: Path) -> None:
    """Manifest with `files: []` → all 6 MISSING_REQUIRED_CONTENT_TYPE failures."""
    _copy_canonical_to(tmp_path)
    manifest_path = tmp_path / MANIFEST_FILENAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["files"] = []
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    missing_codes = [e for e in result.errors if e.code == "MISSING_REQUIRED_CONTENT_TYPE"]
    assert len(missing_codes) == 6


# --------------------------------------------------------------------------
# Layers 7-8 — SHA256 mismatch / size mismatch
# --------------------------------------------------------------------------

def test_sha256_mismatch(tmp_path: Path) -> None:
    """Tampered content (hash doesn't match manifest) → SHA256_MISMATCH."""
    _copy_canonical_to(tmp_path)
    metadata_path = tmp_path / "metadata.json"
    metadata_path.write_text("{\"tampered\": true}\n", encoding="utf-8")
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "SHA256_MISMATCH" for e in result.errors)


# --------------------------------------------------------------------------
# Layer 2 — wrong bundle_version
# --------------------------------------------------------------------------

def test_wrong_bundle_version_rejected_by_pydantic(tmp_path: Path) -> None:
    """A manifest with bundle_version != "1.0" fails at Pydantic parse
    (because BundleManifest.bundle_version is a Literal["1.0"]).
    The conformance check surfaces this as MANIFEST_SCHEMA_INVALID."""
    _copy_canonical_to(tmp_path)
    manifest_path = tmp_path / MANIFEST_FILENAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    data["bundle_version"] = "2.0"
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")
    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "MANIFEST_SCHEMA_INVALID" for e in result.errors)


# --------------------------------------------------------------------------
# Layer 12 — malformed reasoning_trace.jsonl
# --------------------------------------------------------------------------

def test_malformed_reasoning_trace_jsonl(tmp_path: Path) -> None:
    """Reasoning trace with non-JSON line → REASONING_TRACE_JSONL_INVALID.

    Requires regenerating the SHA256 in the manifest so we hit the JSONL
    check, not the hash check.
    """
    import hashlib

    _copy_canonical_to(tmp_path)
    trace_path = tmp_path / "reasoning_trace.jsonl"
    body = "this is not valid JSON\n"
    trace_path.write_text(body, encoding="utf-8", newline="")

    manifest_path = tmp_path / MANIFEST_FILENAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    body_bytes = body.encode("utf-8")
    new_sha = hashlib.sha256(body_bytes).hexdigest()
    for entry in data["files"]:
        if entry["content_type"] == "reasoning_trace":
            entry["sha256"] = new_sha
            entry["size_bytes"] = len(body_bytes)
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")

    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "REASONING_TRACE_JSONL_INVALID" for e in result.errors)


# --------------------------------------------------------------------------
# Layer 9 — malformed scope_decision.json (typed JSON)
# --------------------------------------------------------------------------

def test_malformed_scope_decision_json(tmp_path: Path) -> None:
    """scope_decision.json with wrong shape → CONTENT_SCHEMA_INVALID."""
    import hashlib

    _copy_canonical_to(tmp_path)
    sd_path = tmp_path / "scope_decision.json"
    body = "{\"status\": \"NOT_A_REAL_STATUS\"}\n"
    sd_path.write_text(body, encoding="utf-8", newline="")

    # Update manifest SHA256 so we hit Pydantic-schema check, not hash check.
    manifest_path = tmp_path / MANIFEST_FILENAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    body_bytes = body.encode("utf-8")
    new_sha = hashlib.sha256(body_bytes).hexdigest()
    for entry in data["files"]:
        if entry["content_type"] == "scope_decision":
            entry["sha256"] = new_sha
            entry["size_bytes"] = len(body_bytes)
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")

    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "CONTENT_SCHEMA_INVALID" for e in result.errors)


# --------------------------------------------------------------------------
# Iter-2 P1 — path-safety negative cases (Pydantic validator)
# --------------------------------------------------------------------------

@pytest.mark.parametrize("bad_path", [
    "..\\evil.txt",
    "sources\\..\\evil.txt",
    "C:\\POLARIS\\evil.txt",
    "\\\\server\\share\\evil.txt",
    "/etc/passwd",
    "../../etc/passwd",
])
def test_path_validator_rejects_unsafe(bad_path: str) -> None:
    """FileEntry path validator rejects backslash + drive + UNC + rooted."""
    with pytest.raises(ValidationError):
        FileEntry(
            path=bad_path,
            sha256="0" * 64,
            size_bytes=1,
            content_type="metadata",
        )


def test_path_validator_accepts_valid_relative() -> None:
    """FileEntry path validator accepts POSIX-relative paths."""
    entry = FileEntry(
        path="sources/abc123.txt",
        sha256="0" * 64,
        size_bytes=1,
        content_type="source_snapshot",
    )
    assert entry.path == "sources/abc123.txt"


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _copy_canonical_to(dest: Path) -> None:
    """Copy the canonical fixture into a tmp directory for mutation."""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(CANONICAL_FIXTURE, dest)


# --------------------------------------------------------------------------
# Codex diff iter-1 P1 — extra="forbid" + reasoning_trace filename enforcement
# --------------------------------------------------------------------------

def test_bundle_manifest_rejects_unknown_field() -> None:
    """BundleManifest with `extra="forbid"` rejects unknown top-level field."""
    minimal = {
        "decision_id": "d1",
        "pool_id": "p1",
        "report_id": "r1",
        "generator_model": "deepseek/deepseek-v4-pro",
        "polaris_version": "1.0.0",
        "files": [],
    }
    BundleManifest(**minimal)  # baseline passes
    with pytest.raises(ValidationError):
        BundleManifest(**minimal, future_field="boom")


def test_file_entry_rejects_unknown_field() -> None:
    """FileEntry with `extra="forbid"` rejects unknown field."""
    FileEntry(path="a.txt", sha256="0" * 64, size_bytes=1, content_type="metadata")
    with pytest.raises(ValidationError):
        FileEntry(
            path="a.txt",
            sha256="0" * 64,
            size_bytes=1,
            content_type="metadata",
            extra_field="boom",
        )


def test_reasoning_trace_filename_mismatch(tmp_path: Path) -> None:
    """Renaming reasoning_trace.jsonl in the manifest → REASONING_TRACE_FILENAME_MISMATCH.

    Belt-and-suspenders: even if the file content + SHA are correct, the
    canonical filename must match `manifest_builder.py:55`.
    """
    import hashlib

    _copy_canonical_to(tmp_path)
    # Move the file + rename the manifest entry's path.
    (tmp_path / "reasoning_trace.jsonl").rename(tmp_path / "trace.jsonl")
    manifest_path = tmp_path / MANIFEST_FILENAME
    data = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    for entry in data["files"]:
        if entry["content_type"] == "reasoning_trace":
            entry["path"] = "trace.jsonl"
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=True), encoding="utf-8")

    result = check_bundle_conformance(tmp_path)
    assert not result.valid
    assert any(e.code == "REASONING_TRACE_FILENAME_MISMATCH" for e in result.errors)
