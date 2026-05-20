"""Audit-bundle conformance check (I-cd-012 / GH#608).

Validates an extracted audit-bundle directory against the frozen v1.0
BundleManifest schema (`bundle_schema.py`). Public API consumed by:

- I-B-08 (#630) — real-run bundle / EvidenceContract bridge: confirms
  every emitted bundle conforms before the GPG signing step.
- Future reviewer/operator tooling that wants a fast pre-verification
  check before the more expensive `gpg --verify` step.

This module is PURE-FUNCTION (no I/O at import time, no global state).

What it checks (all 11 layers must pass for `valid=True`):
 1. `manifest.yaml` parses to a valid `BundleManifest` (Pydantic).
 2. `bundle_version` literal equals `BUNDLE_VERSION` ("1.0").
 3. `manifest.yaml.asc` exists and is non-empty (PRESENCE only —
    cryptographic verification belongs to a separate operator tool).
 4. All 6 required content types are present in `manifest.files`
    (>= 1 FileEntry each: scope_decision, evidence_pool, verified_report,
    metadata, source_snapshot, reasoning_trace).
 5. Every `files[*].path` resolves under `extracted_dir` (path-traversal
    belt-and-suspenders even though `bundle_schema._path_no_traversal`
    rejects unsafe paths at Pydantic parse).
 6. Every `files[*].path` exists on disk.
 7. Every actual SHA256 matches `files[*].sha256`.
 8. Every actual size matches `files[*].size_bytes`.
 9. `scope_decision.json` parses to `ScopeDecision`.
10. `evidence_pool.json` parses to `EvidencePool`.
11. `verified_report.json` parses to `VerifiedReport`.
12. `reasoning_trace.jsonl` parses as JSONL (every non-empty line is a
    valid JSON object).

What it does NOT check (out of scope):
- `gpg --verify manifest.yaml.asc manifest.yaml` — cryptographic
  verification belongs to operator/reviewer side tooling, not the
  pre-sign emitter check.
- Sovereignty filtering on source full-texts (separate concern,
  `sovereignty_guard.py`).
- Pipeline-level invariants of the wrapped content (two-family
  segregation, strict-verify pass rate floor) — those are upstream
  pipeline contracts; conformance only checks the BUNDLE shape.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from polaris_graph.audit_bundle.bundle_schema import (
    BUNDLE_VERSION,
    BundleManifest,
    ContentType,
)
from polaris_graph.clinical_generator.verified_report import VerifiedReport
from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool
from polaris_graph.scope.scope_decision import ScopeDecision


MANIFEST_FILENAME = "manifest.yaml"
SIGNATURE_FILENAME = "manifest.yaml.asc"
# Mirrors `src/polaris_graph/generator/reasoning_trace.py:34
# REASONING_TRACE_FILENAME` — the active producer constant. A
# bundle that renames this file must bump BUNDLE_VERSION.
REASONING_TRACE_FILENAME = "reasoning_trace.jsonl"

# All ContentType members required for a v1.0 bundle.
_REQUIRED_CONTENT_TYPES: tuple[ContentType, ...] = (
    "scope_decision",
    "evidence_pool",
    "verified_report",
    "metadata",
    "source_snapshot",
    "reasoning_trace",
)


@dataclass(frozen=True)
class ConformanceError:
    """Structured conformance failure record (public API for I-B-08)."""

    code: str
    message: str
    path: str | None = None


@dataclass
class ConformanceResult:
    """Public API return shape — consumed by I-B-08 emitter."""

    valid: bool
    errors: list[ConformanceError] = field(default_factory=list)

    def add(self, code: str, message: str, path: str | None = None) -> None:
        self.errors.append(ConformanceError(code=code, message=message, path=path))


def check_bundle_conformance(extracted_dir: Path) -> ConformanceResult:
    """Validate an extracted audit-bundle directory.

    Args:
        extracted_dir: Directory containing the extracted .tar.gz contents
            (manifest.yaml + manifest.yaml.asc + content files).

    Returns:
        ConformanceResult with `valid=True` iff all 12 checks pass.
    """
    result = ConformanceResult(valid=True)
    extracted_dir = extracted_dir.resolve()

    # --- 1. manifest.yaml parses to BundleManifest --------------------
    manifest_path = extracted_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        result.add("MISSING_MANIFEST", f"manifest.yaml not found in {extracted_dir}")
        result.valid = False
        return result

    try:
        manifest_raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        result.add("MANIFEST_YAML_PARSE_ERROR", f"manifest.yaml is not valid YAML: {exc}")
        result.valid = False
        return result

    try:
        manifest = BundleManifest(**(manifest_raw or {}))
    except Exception as exc:  # noqa: BLE001 — Pydantic raises various
        result.add("MANIFEST_SCHEMA_INVALID", f"manifest.yaml does not parse to BundleManifest: {exc}")
        result.valid = False
        return result

    # --- 2. bundle_version literal == BUNDLE_VERSION ------------------
    if manifest.bundle_version != BUNDLE_VERSION:
        result.add(
            "WRONG_BUNDLE_VERSION",
            f"bundle_version={manifest.bundle_version!r} != frozen {BUNDLE_VERSION!r}",
        )
        result.valid = False

    # --- 3. manifest.yaml.asc presence + non-empty --------------------
    signature_path = extracted_dir / SIGNATURE_FILENAME
    if not signature_path.exists():
        result.add(
            "MISSING_SIGNATURE",
            f"{SIGNATURE_FILENAME} not found in {extracted_dir} (bundle is unsigned)",
            path=SIGNATURE_FILENAME,
        )
        result.valid = False
    elif signature_path.stat().st_size == 0:
        result.add(
            "EMPTY_SIGNATURE",
            f"{SIGNATURE_FILENAME} is empty (bundle signature is missing)",
            path=SIGNATURE_FILENAME,
        )
        result.valid = False

    # --- 4. All 6 required content types present ----------------------
    present_types: set[ContentType] = {entry.content_type for entry in manifest.files}
    for required in _REQUIRED_CONTENT_TYPES:
        if required not in present_types:
            result.add(
                "MISSING_REQUIRED_CONTENT_TYPE",
                f"v1.0 bundle requires at least one file of content_type={required!r}",
            )
            result.valid = False

    # --- 4b. Reasoning-trace path MUST equal the canonical filename --
    # Codex diff iter-1 P1: without this, a bundle can rename
    # reasoning_trace.jsonl to trace.jsonl, update the manifest path,
    # and still pass valid=True, diverging from the active producer
    # constant in generator/reasoning_trace.py:34.
    for entry in manifest.files:
        if entry.content_type == "reasoning_trace" and entry.path != REASONING_TRACE_FILENAME:
            result.add(
                "REASONING_TRACE_FILENAME_MISMATCH",
                f"reasoning_trace path {entry.path!r} != canonical "
                f"{REASONING_TRACE_FILENAME!r} (see "
                f"src/polaris_graph/generator/reasoning_trace.py:34)",
                path=entry.path,
            )
            result.valid = False

    # --- 5-8. Per-file path resolution + existence + hash + size -----
    by_content_type: dict[ContentType, list[Path]] = {}
    for entry in manifest.files:
        # Layer 5: belt-and-suspenders path resolution check.
        try:
            resolved = (extracted_dir / entry.path).resolve()
        except (OSError, ValueError) as exc:
            result.add(
                "PATH_RESOLVE_ERROR",
                f"path {entry.path!r} cannot be resolved: {exc}",
                path=entry.path,
            )
            result.valid = False
            continue
        if not _is_under(resolved, extracted_dir):
            result.add(
                "PATH_OUTSIDE_BUNDLE",
                f"path {entry.path!r} resolves outside the extracted bundle "
                f"({resolved} not under {extracted_dir})",
                path=entry.path,
            )
            result.valid = False
            continue

        # Layer 6: file exists.
        if not resolved.exists():
            result.add(
                "MISSING_FILE",
                f"path {entry.path!r} listed in manifest but not present on disk",
                path=entry.path,
            )
            result.valid = False
            continue

        # Layer 7: SHA256 matches. Wrap read_bytes/stat so a directory
        # path or read error surfaces as a structured ConformanceError
        # rather than raising out of the check (Codex diff iter-1 P2).
        try:
            file_bytes = resolved.read_bytes()
            actual_size = resolved.stat().st_size
        except OSError as exc:
            result.add(
                "FILE_READ_ERROR",
                f"path {entry.path!r} could not be read: {exc}",
                path=entry.path,
            )
            result.valid = False
            continue
        actual_sha = hashlib.sha256(file_bytes).hexdigest()
        if actual_sha != entry.sha256:
            result.add(
                "SHA256_MISMATCH",
                f"path {entry.path!r}: manifest claims {entry.sha256}, actual {actual_sha}",
                path=entry.path,
            )
            result.valid = False
            continue

        # Layer 8: size matches.
        if actual_size != entry.size_bytes:
            result.add(
                "SIZE_MISMATCH",
                f"path {entry.path!r}: manifest claims {entry.size_bytes} bytes, actual {actual_size}",
                path=entry.path,
            )
            result.valid = False
            continue

        by_content_type.setdefault(entry.content_type, []).append(resolved)

    # --- 9-11. Typed-JSON content validation --------------------------
    for typed_check in (
        ("scope_decision", ScopeDecision),
        ("evidence_pool", EvidencePool),
        ("verified_report", VerifiedReport),
    ):
        content_type, schema_cls = typed_check
        for path in by_content_type.get(content_type, []):  # type: ignore[arg-type]
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                result.add(
                    "CONTENT_JSON_INVALID",
                    f"{path.name} is not valid JSON: {exc}",
                    path=str(path.relative_to(extracted_dir)),
                )
                result.valid = False
                continue
            try:
                schema_cls(**payload)
            except Exception as exc:  # noqa: BLE001 — Pydantic raises various
                result.add(
                    "CONTENT_SCHEMA_INVALID",
                    f"{path.name} does not parse to {schema_cls.__name__}: {exc}",
                    path=str(path.relative_to(extracted_dir)),
                )
                result.valid = False

    # --- 12. reasoning_trace.jsonl parses as JSONL --------------------
    for path in by_content_type.get("reasoning_trace", []):
        try:
            for line_no, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if not line.strip():
                    continue
                try:
                    parsed: Any = json.loads(line)
                except json.JSONDecodeError as exc:
                    result.add(
                        "REASONING_TRACE_JSONL_INVALID",
                        f"{path.name} line {line_no} is not valid JSON: {exc}",
                        path=str(path.relative_to(extracted_dir)),
                    )
                    result.valid = False
                    break
                if not isinstance(parsed, dict):
                    result.add(
                        "REASONING_TRACE_JSONL_INVALID",
                        f"{path.name} line {line_no} is not a JSON object",
                        path=str(path.relative_to(extracted_dir)),
                    )
                    result.valid = False
                    break
        except OSError as exc:
            result.add(
                "REASONING_TRACE_READ_ERROR",
                f"{path.name} cannot be read: {exc}",
                path=str(path.relative_to(extracted_dir)),
            )
            result.valid = False

    return result


def _is_under(candidate: Path, parent: Path) -> bool:
    """Cross-version `Path.is_relative_to` (3.9+) — Windows-safe."""
    try:
        candidate.relative_to(parent)
        return True
    except ValueError:
        return False
