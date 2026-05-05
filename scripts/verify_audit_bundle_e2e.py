"""End-to-end live verification of slice 004 audit-bundle signing.

Builds a minimal valid {decision, pool, report} payload, POSTs to
/api/audit-bundle, writes the returned tarball, extracts the .asc
signature + signed manifest, and runs `gpg --verify` to confirm the
signature is valid.

This is the LAW II fitness check for slice 004. Without GPG the endpoint
must 503; with GPG configured the bundle must produce a verifying
signature. No middle ground.

Usage:
    PYTHONPATH=src python scripts/verify_audit_bundle_e2e.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from fastapi.testclient import TestClient


_ISO = "2026-05-04T16:30:00.000Z"


def _build_payload() -> dict:
    """Minimal valid {decision, pool, report} that satisfies all schemas."""
    return {
        "decision": {
            "status": "in_scope",
            "scope_class": "clinical_efficacy",
            "ambiguity_axes": [],
            "clarifications_needed": [],
            "decision_id": "decision-e2e-test",
            "decided_at_utc": _ISO,
            "latency_ms": 100,
            "provenance": {"classifier_provenance": "regex"},
        },
        "pool": {
            "pool_id": "pool-e2e",
            "decision_id": "decision-e2e-test",
            "sources": [
                {
                    "source_id": "src-cochrane-e2e",
                    "url": "https://www.cochrane.org/CD001",
                    "domain": "cochrane.org",
                    "tier": "T1",
                    "title": "Cochrane test source",
                    "publication_date": None,
                    "authors": [],
                    "snippet": "Aspirin 1000 mg is effective for migraine.",
                    "full_text_available": True,
                    "full_text": "Aspirin 1000 mg is effective for acute migraine in adults. Trials show pain relief at 2 hours.",
                    "fetched_at_utc": _ISO,
                    "provenance": {"backend": "cochrane"},
                }
            ],
            "adequacy": {
                "is_adequate": True,
                "sources_per_tier": {"T1": 1, "T2": 0, "T3": 0},
                "min_required_per_tier": {"T1": 1, "T2": 0, "T3": 0},
                "failure_reason": None,
            },
            "queries_executed": [],
            "retrieval_started_at_utc": _ISO,
            "retrieval_finished_at_utc": _ISO,
            "latency_ms": 100,
            "cost_usd": 0.0,
        },
        "report": {
            "report_id": "report-e2e",
            "pool_id": "pool-e2e",
            "decision_id": "decision-e2e-test",
            "sections": [
                {
                    "section_id": "sec_outcomes",
                    "section_title": "Outcomes",
                    "verified_sentences": [
                        {
                            "section_id": "sec_outcomes",
                            "sentence_text": (
                                "Aspirin 1000 mg is effective for acute "
                                "migraine in adults [#ev:src-cochrane-e2e:0-50]."
                            ),
                            "provenance_tokens": ["[#ev:src-cochrane-e2e:0-50]"],
                            "verifier_pass": True,
                            "drop_reason": None,
                        }
                    ],
                    "section_verify_pass_rate": 1.0,
                    "section_status": "verified",
                }
            ],
            "overall_verify_pass_rate": 1.0,
            "pipeline_verdict": "success",
            "generator_model": "deepseek/deepseek-v4-pro",
            "verifier_pass_threshold": 0.4,
            "started_at_utc": _ISO,
            "finished_at_utc": _ISO,
            "latency_ms": 1000,
            "cost_usd": 0.001,
        },
    }


def _verify_tarball(tar_bytes: bytes, verbose: bool) -> int:
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        tar_path = td_path / "bundle.tar.gz"
        tar_path.write_bytes(tar_bytes)

        if verbose:
            print(f"  bundle bytes: {len(tar_bytes)}")
            print(f"  written to: {tar_path}")

        with tarfile.open(tar_path, "r:gz") as tf:
            members = tf.getnames()
            tf.extractall(td_path / "extracted")
        if verbose:
            print(f"  members: {members}")

        ext = td_path / "extracted"
        # Find the signed manifest + signature
        sig_files = list(ext.rglob("*.asc"))
        if not sig_files:
            print("  FAIL: no .asc signature in tarball", file=sys.stderr)
            return 2
        sig_path = sig_files[0]
        manifest_path = sig_path.with_suffix("")  # strip .asc
        if not manifest_path.is_file():
            print(
                f"  FAIL: signed manifest missing: {manifest_path}",
                file=sys.stderr,
            )
            return 3
        if verbose:
            print(f"  signature: {sig_path.relative_to(ext)} "
                  f"({sig_path.stat().st_size} bytes)")
            print(f"  manifest:  {manifest_path.relative_to(ext)} "
                  f"({manifest_path.stat().st_size} bytes)")

        # gpg --verify <sig> <manifest>
        proc = subprocess.run(
            ["gpg", "--verify", str(sig_path), str(manifest_path)],
            capture_output=True, text=True,
        )
        if verbose:
            print(f"  gpg rc: {proc.returncode}")
            print(f"  gpg stderr (first 3 lines):")
            for line in proc.stderr.splitlines()[:3]:
                print(f"    {line}")
        if proc.returncode != 0:
            print(
                f"  FAIL: gpg --verify returned {proc.returncode}",
                file=sys.stderr,
            )
            return 4
        if "Good signature" not in proc.stderr:
            print(
                f"  FAIL: gpg verified but did not say 'Good signature':\n"
                f"  {proc.stderr}",
                file=sys.stderr,
            )
            return 5
    return 0


def main(argv: list[str]) -> int:
    verbose = "-v" in argv or "--verbose" in argv
    load_dotenv()
    print("Slice 004 audit-bundle live verification")
    print("==========================================")

    # Lazy imports so missing keys surface as 503 not import error
    from polaris_v6.api.app import create_app

    app = create_app()
    client = TestClient(app)

    # Health check
    h = client.get("/api/audit-bundle/health").json()
    print(f"  signing_backend: {h.get('signing_backend')!r}")
    if h.get("signing_backend") != "gpg":
        print(
            "  FAIL: expected signing_backend='gpg' (set POLARIS_GPG_KEY_ID "
            "in .env and run scripts/setup_gpg_for_demo.py first)",
            file=sys.stderr,
        )
        return 1

    payload = _build_payload()
    if verbose:
        print(f"  payload size: {len(json.dumps(payload))} bytes")

    print("[1/2] POST /api/audit-bundle")
    r = client.post("/api/audit-bundle", json=payload)
    if r.status_code != 200:
        print(
            f"  FAIL: status={r.status_code} body={r.text[:300]}",
            file=sys.stderr,
        )
        return 1
    tar_bytes = r.content
    print(f"  OK   {len(tar_bytes)} bytes returned")

    print("[2/2] gpg --verify on signed manifest")
    rc = _verify_tarball(tar_bytes, verbose)
    if rc != 0:
        return rc

    print("==========================================")
    print("AUDIT BUNDLE E2E PASSED: real GPG signature verifies")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
