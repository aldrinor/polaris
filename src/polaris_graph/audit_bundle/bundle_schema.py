"""Bundle manifest schema for slice 004 audit-bundle export.

Per `.codex/slices/slice_004/architecture_proposal.md`.

Pure-types module. The BundleManifest is the audit anchor: an external
verifier extracts the .tar.gz, computes SHA256 of every content file,
checks against `files[*].sha256`, then verifies the GPG signature on the
manifest itself. If the manifest verifies and content hashes match, the
bundle is intact.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Type literals
# ---------------------------------------------------------------------------

ContentType = Literal[
    "scope_decision",      # slice 001 ScopeDecision JSON
    "evidence_pool",       # slice 002 EvidencePool JSON
    "verified_report",     # slice 003 VerifiedReport JSON
    "source_snapshot",     # full_text of one cited source
    "metadata",            # bundle-level metadata (versions, etc.)
    "reasoning_trace",     # I-gen-004 (#496): raw model reasoning channel
]


BUNDLE_VERSION = "1.0"


# ---------------------------------------------------------------------------
# FileEntry
# ---------------------------------------------------------------------------

class FileEntry(BaseModel):
    """One file in the bundle, with hash anchor."""

    path: str = Field(
        min_length=1,
        max_length=500,
        description=(
            "Relative path inside the .tar.gz. e.g. 'manifest.yaml',"
            " 'sources/abc-123.txt', 'verified_report.json'."
        ),
    )
    sha256: str = Field(
        min_length=64,
        max_length=64,
        description="Lowercase hex SHA256 digest of file contents.",
    )
    size_bytes: int = Field(ge=0)
    content_type: ContentType

    @field_validator("sha256")
    @classmethod
    def _sha256_lowercase_hex(cls, v: str) -> str:
        v = v.strip().lower()
        if len(v) != 64:
            raise ValueError("sha256 must be exactly 64 hex chars")
        if any(c not in "0123456789abcdef" for c in v):
            raise ValueError("sha256 must be lowercase hex")
        return v

    @field_validator("path")
    @classmethod
    def _path_no_traversal(cls, v: str) -> str:
        v = v.strip()
        if v.startswith("/") or ".." in v.split("/"):
            raise ValueError(
                "path must be relative and must not contain '..' segments"
            )
        return v


# ---------------------------------------------------------------------------
# BundleManifest
# ---------------------------------------------------------------------------

class BundleManifest(BaseModel):
    """Top-level bundle manifest — what GPG signs.

    The signature in `manifest.yaml.asc` is over the YAML-serialized form
    of this manifest. External verifiers re-serialize and re-verify.
    """

    bundle_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    bundle_version: Literal["1.0"] = BUNDLE_VERSION

    # Foreign keys back through the research pipeline
    decision_id: str = Field(min_length=1, description="slice 001 ScopeDecision id")
    pool_id: str = Field(min_length=1, description="slice 002 EvidencePool id")
    report_id: str = Field(min_length=1, description="slice 003 VerifiedReport id")

    # Provenance metadata
    generator_model: str = Field(min_length=1, max_length=200)
    polaris_version: str = Field(min_length=1, max_length=50)

    # Content files (excluding manifest.yaml + manifest.yaml.asc themselves)
    files: list[FileEntry] = Field(default_factory=list, max_length=10000)

    bundle_created_at_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("files")
    @classmethod
    def _files_unique_paths(cls, v: list[FileEntry]) -> list[FileEntry]:
        paths = [f.path for f in v]
        if len(set(paths)) != len(paths):
            duplicates = sorted({p for p in paths if paths.count(p) > 1})
            raise ValueError(
                f"files must have unique paths; duplicates: {duplicates}"
            )
        return v

    def file_by_content_type(
        self, content_type: ContentType
    ) -> list[FileEntry]:
        """Filter files to a specific content_type. Used by verifiers."""
        return [f for f in self.files if f.content_type == content_type]

    def total_bytes(self) -> int:
        return sum(f.size_bytes for f in self.files)


# ---------------------------------------------------------------------------
# BundleBuildError (parallel to other slices' Error types)
# ---------------------------------------------------------------------------

class BundleBuildError(BaseModel):
    """Returned when a bundle cannot be assembled."""

    error: bool = True
    code: str  # 'report_not_success' | 'gpg_unavailable' |
               # 'gpg_key_missing' | 'serialization_failed'
    message: str
    report_id: str | None = None
