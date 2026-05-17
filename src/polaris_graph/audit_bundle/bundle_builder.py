"""Bundle builder — end-to-end audit bundle assembler.

Per `.codex/slices/slice_004/architecture_proposal.md` §"bundle_builder".

Pipeline:
    ScopeDecision + EvidencePool + VerifiedReport (verdict=success)
        ↓
    build_manifest_and_files()  -> manifest + content files
        ↓
    serialize_manifest_yaml()    -> manifest.yaml bytes
        ↓
    sign_fn(manifest.yaml)       -> manifest.yaml.asc bytes
        ↓
    pack_tarball()               -> audit_<bundle_id>.tar.gz

The output tarball:
    audit_<bundle_id>/
      manifest.yaml
      manifest.yaml.asc
      scope_decision.json
      evidence_pool.json
      verified_report.json
      sources/<source_id>.txt   (for each cited source)
      metadata.json

External verifiers run:
    tar -xzf audit_<id>.tar.gz
    cd audit_<id>
    gpg --verify manifest.yaml.asc manifest.yaml
    # then re-hash each content file and compare against manifest.files[*].sha256
"""

from __future__ import annotations

import io
import logging
import tarfile
import time
from pathlib import Path
from typing import Callable

from polaris_graph.audit_bundle.bundle_schema import BundleManifest
from polaris_graph.audit_bundle.manifest_builder import (
    build_manifest_and_files,
    serialize_manifest_yaml,
)
from polaris_graph.clinical_generator.verified_report import VerifiedReport
from polaris_graph.retrieval2.evidence_pool import EvidencePool
from polaris_graph.scope.scope_decision import ScopeDecision

_LOG = logging.getLogger(__name__)


# Type alias for the sign function we accept (Protocol-style duck typing).
# Concrete impl is GPGSigner from gpg_signer.py; tests can pass a stub.
SignFn = Callable[[bytes], bytes]


def _default_sign_fn(_payload: bytes) -> bytes:
    """Sentinel that refuses to run.

    Forces callers to provide a real signer (or test stub). Per LAW II,
    silently writing an unsigned bundle is FORBIDDEN — the audit bundle's
    legal value comes from the signature.
    """
    raise NotImplementedError(
        "no sign_fn injected. The audit bundle MUST be GPG-signed. "
        "Inject a real signer (e.g. GPGSigner from gpg_signer.py) or "
        "a test stub."
    )


def build_audit_bundle(
    decision: ScopeDecision,
    pool: EvidencePool,
    report: VerifiedReport,
    output_dir: Path,
    sign_fn: SignFn = _default_sign_fn,
    *,
    extra_files: dict[str, tuple[bytes, str]] | None = None,
) -> Path:
    """End-to-end: build manifest + sign + pack tarball.

    Args:
        decision: slice 001 ScopeDecision
        pool: slice 002 EvidencePool (must match report.pool_id)
        report: slice 003 VerifiedReport (must have verdict=success)
        output_dir: directory where audit_<id>.tar.gz is written
        sign_fn: function that takes manifest.yaml bytes and returns
                 .asc bytes. Default raises NotImplementedError; callers
                 MUST inject a real signer.
        extra_files: optional {path: (bytes, content_type)} of extra
                 artifacts to include + hash in the signed manifest —
                 I-gen-004 (#496) threads reasoning_trace.jsonl here.

    Returns:
        Path to the generated audit_<bundle_id>.tar.gz file.

    Raises:
        ValueError: if report.pipeline_verdict != 'success' or pool/report
                    FK chain inconsistent.
        RuntimeError: if sign_fn raises (propagated, original error chained).
    """
    if report.pool_id != pool.pool_id:
        raise ValueError(
            f"FK chain mismatch: report.pool_id={report.pool_id!r} != "
            f"pool.pool_id={pool.pool_id!r}"
        )
    if report.decision_id != decision.decision_id:
        raise ValueError(
            f"FK chain mismatch: report.decision_id={report.decision_id!r}"
            f" != decision.decision_id={decision.decision_id!r}"
        )

    t_start = time.perf_counter()
    manifest, content_files = build_manifest_and_files(
        decision, pool, report, extra_files=extra_files,
    )

    manifest_yaml = serialize_manifest_yaml(manifest)

    try:
        manifest_sig = sign_fn(manifest_yaml)
    except NotImplementedError:
        raise RuntimeError(
            "audit bundle requires a sign_fn; default sentinel forbids "
            "shipping unsigned bundles per CLAUDE.md LAW II"
        )
    except Exception as exc:
        raise RuntimeError(
            f"sign_fn raised {type(exc).__name__}: {exc}"
        ) from exc

    # Pack everything into a single .tar.gz under top-level dir audit_<id>
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_filename = f"audit_{manifest.bundle_id}.tar.gz"
    bundle_path = output_dir / bundle_filename

    with tarfile.open(bundle_path, "w:gz") as tar:
        top_dir = f"audit_{manifest.bundle_id}"

        # 1. manifest.yaml + manifest.yaml.asc (NOT in manifest.files;
        #    they are the manifest itself + signature)
        _add_file(tar, f"{top_dir}/manifest.yaml", manifest_yaml)
        _add_file(tar, f"{top_dir}/manifest.yaml.asc", manifest_sig)

        # 2. Content files (paths from manifest.files)
        for path, content_bytes in content_files.items():
            _add_file(tar, f"{top_dir}/{path}", content_bytes)

    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
    _LOG.info(
        "audit bundle built bundle_id=%s files=%d size=%dB elapsed=%dms",
        manifest.bundle_id,
        len(manifest.files),
        bundle_path.stat().st_size,
        elapsed_ms,
    )
    return bundle_path


def _add_file(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    """Add bytes to a tarfile under `name`."""
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mtime = int(time.time())
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def extract_manifest_from_bundle(
    bundle_path: Path,
) -> tuple[BundleManifest, bytes, bytes]:
    """Helper for verifiers/tests: extract manifest + signature + their bytes.

    Returns:
        (manifest, manifest_yaml_bytes, manifest_sig_bytes)

    Raises FileNotFoundError if either is missing in the tarball.
    """
    bundle_path = Path(bundle_path)
    manifest_yaml: bytes | None = None
    manifest_sig: bytes | None = None

    with tarfile.open(bundle_path, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith("manifest.yaml") and not member.name.endswith(
                "manifest.yaml.asc"
            ):
                f = tar.extractfile(member)
                if f is not None:
                    manifest_yaml = f.read()
            elif member.name.endswith("manifest.yaml.asc"):
                f = tar.extractfile(member)
                if f is not None:
                    manifest_sig = f.read()

    if manifest_yaml is None:
        raise FileNotFoundError(
            f"manifest.yaml not found in bundle {bundle_path}"
        )
    if manifest_sig is None:
        raise FileNotFoundError(
            f"manifest.yaml.asc not found in bundle {bundle_path}"
        )

    import yaml

    parsed = yaml.safe_load(manifest_yaml.decode("utf-8"))
    manifest = BundleManifest.model_validate(parsed)
    return manifest, manifest_yaml, manifest_sig
