"""Tests for audit_bundle.bundle_schema."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from polaris_graph.audit_bundle.bundle_schema import (
    BUNDLE_VERSION,
    BundleBuildError,
    BundleManifest,
    FileEntry,
)


def _sha256(text: bytes | str) -> str:
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


# ---------- FileEntry ----------

def test_file_entry_minimal():
    fe = FileEntry(
        path="verified_report.json",
        sha256=_sha256("hello"),
        size_bytes=5,
        content_type="verified_report",
    )
    assert fe.path == "verified_report.json"
    assert len(fe.sha256) == 64


def test_file_entry_uppercase_hash_normalized():
    digest = _sha256("x").upper()
    fe = FileEntry(
        path="x.txt",
        sha256=digest,
        size_bytes=1,
        content_type="metadata",
    )
    assert fe.sha256 == digest.lower()


def test_file_entry_short_hash_rejected():
    with pytest.raises(ValidationError, match="64"):
        FileEntry(
            path="x.txt",
            sha256="abc123",
            size_bytes=0,
            content_type="metadata",
        )


def test_file_entry_non_hex_hash_rejected():
    bad = "g" * 64
    with pytest.raises(ValidationError, match="hex"):
        FileEntry(
            path="x.txt",
            sha256=bad,
            size_bytes=0,
            content_type="metadata",
        )


def test_file_entry_absolute_path_rejected():
    with pytest.raises(ValidationError, match="relative"):
        FileEntry(
            path="/etc/passwd",
            sha256=_sha256(""),
            size_bytes=0,
            content_type="metadata",
        )


def test_file_entry_path_traversal_rejected():
    with pytest.raises(ValidationError, match="\\.\\."):
        FileEntry(
            path="../escape/secret",
            sha256=_sha256(""),
            size_bytes=0,
            content_type="metadata",
        )


def test_file_entry_invalid_content_type_rejected():
    with pytest.raises(ValidationError):
        FileEntry(
            path="x.txt",
            sha256=_sha256(""),
            size_bytes=0,
            content_type="bogus",  # type: ignore[arg-type]
        )


def test_file_entry_negative_size_rejected():
    with pytest.raises(ValidationError):
        FileEntry(
            path="x.txt",
            sha256=_sha256(""),
            size_bytes=-1,
            content_type="metadata",
        )


# ---------- BundleManifest ----------

def _file(path: str, content_type: str = "metadata", body: bytes = b"x") -> FileEntry:
    return FileEntry(
        path=path,
        sha256=_sha256(body),
        size_bytes=len(body),
        content_type=content_type,  # type: ignore[arg-type]
    )


def test_bundle_manifest_minimal():
    m = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="deepseek/deepseek-v4-pro",
        polaris_version="6.2.0",
    )
    assert m.bundle_id  # uuid auto-populated
    assert m.bundle_version == BUNDLE_VERSION
    assert m.bundle_version == "1.0"
    assert m.bundle_created_at_utc.tzinfo is not None
    assert m.files == []


def test_bundle_manifest_with_files():
    m = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="deepseek/deepseek-v4-pro",
        polaris_version="6.2.0",
        files=[
            _file("scope_decision.json", "scope_decision"),
            _file("evidence_pool.json", "evidence_pool"),
            _file("verified_report.json", "verified_report"),
            _file("sources/src-1.txt", "source_snapshot"),
        ],
    )
    assert len(m.files) == 4


def test_bundle_manifest_unique_path_constraint():
    with pytest.raises(ValidationError, match="unique"):
        BundleManifest(
            decision_id="dec-1",
            pool_id="pool-1",
            report_id="report-1",
            generator_model="m",
            polaris_version="6.2.0",
            files=[
                _file("a.txt"),
                _file("a.txt"),  # duplicate
            ],
        )


def test_bundle_manifest_blank_decision_id_rejected():
    with pytest.raises(ValidationError):
        BundleManifest(
            decision_id="",
            pool_id="pool-1",
            report_id="report-1",
            generator_model="m",
            polaris_version="6.2.0",
        )


def test_bundle_manifest_file_by_content_type_filter():
    m = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="m",
        polaris_version="6.2.0",
        files=[
            _file("a.json", "verified_report"),
            _file("b.txt", "source_snapshot"),
            _file("c.txt", "source_snapshot"),
        ],
    )
    sources = m.file_by_content_type("source_snapshot")
    assert len(sources) == 2
    assert all(f.content_type == "source_snapshot" for f in sources)


def test_bundle_manifest_total_bytes():
    m = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="m",
        polaris_version="6.2.0",
        files=[
            _file("a.json", "verified_report", b"hello"),
            _file("b.txt", "source_snapshot", b"world!"),
        ],
    )
    assert m.total_bytes() == 5 + 6


def test_bundle_manifest_round_trip_json():
    m = BundleManifest(
        decision_id="dec-1",
        pool_id="pool-1",
        report_id="report-1",
        generator_model="m",
        polaris_version="6.2.0",
        files=[_file("x.txt")],
    )
    data = m.model_dump(mode="json")
    rehydrated = BundleManifest.model_validate(data)
    assert rehydrated.bundle_id == m.bundle_id
    assert len(rehydrated.files) == 1


# ---------- BundleBuildError ----------

def test_bundle_build_error_minimal():
    e = BundleBuildError(
        code="report_not_success",
        message="cannot build bundle when verdict=abort_no_verified_sections",
    )
    assert e.error is True
    assert e.code == "report_not_success"


def test_bundle_build_error_with_report_id():
    e = BundleBuildError(
        code="gpg_key_missing",
        message="no signing key in keyring",
        report_id="report-1",
    )
    assert e.report_id == "report-1"
