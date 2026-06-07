"""Deterministic regenerator for tests/fixtures/signed_bundle/v1_canonical/.

I-cd-012 (GH#608). Run after any schema-compatible change to the canonical
fixture data; the script rebuilds every file + recomputes SHA256s and
rewrites manifest.yaml so the conformance check still passes.

USAGE:
    python scripts/regen_signed_bundle_canonical_fixture.py

The script is DETERMINISTIC — every run produces byte-identical files
(no clocks, no random UUIDs).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

# Add src/ to path so polaris_graph imports resolve when run from repo root.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from polaris_graph.audit_bundle.bundle_schema import (  # noqa: E402
    BUNDLE_VERSION,
    BundleManifest,
    FileEntry,
)


FIXTURE_DIR = ROOT / "tests" / "fixtures" / "signed_bundle" / "v1_canonical"
SUCCESS_FIXTURE_DIR = ROOT / "tests" / "fixtures" / "signed_bundle" / "v1_canonical_success"
SOURCES_SUBDIR = FIXTURE_DIR / "sources"

# Deterministic seed values — frozen across regenerations.
FIXED_DECISION_ID = "decision_v1_canonical_0001"
FIXED_POOL_ID = "pool_v1_canonical_0001"
FIXED_REPORT_ID = "report_v1_canonical_0001"
FIXED_BUNDLE_ID = "bundle_v1_canonical_0001"
FIXED_SOURCE_ID = "src_v1_canonical_0001"
FIXED_TIMESTAMP = "2026-05-19T00:00:00+00:00"

POLARIS_VERSION = "1.0.0"
GENERATOR_MODEL = "deepseek/deepseek-v4-pro"
EVALUATOR_MODEL = "google/gemma-4-31b-it"


def _canonical_json_dump(payload: dict) -> str:
    """Deterministic JSON: sorted keys + 2-space indent + LF newlines."""
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_scope_decision() -> dict:
    """Minimal valid ScopeDecision payload — see scope/scope_decision.py."""
    return {
        "status": "in_scope",
        "scope_class": "clinical_efficacy",
        "ambiguity_axes": [],
        "clarifications_needed": [],
        "provenance": {
            "classifier_layer": "regex",
            "ambiguity_detector_layer": "regex",
        },
        "decision_id": FIXED_DECISION_ID,
        "decided_at_utc": FIXED_TIMESTAMP,
        "latency_ms": 12,
    }


def _build_evidence_pool() -> dict:
    """Minimal valid EvidencePool — see clinical_retrieval/evidence_pool.py."""
    return {
        "pool_id": FIXED_POOL_ID,
        "decision_id": FIXED_DECISION_ID,
        "sources": [
            {
                "source_id": FIXED_SOURCE_ID,
                "url": "https://example.org/clinical/canonical_v1.html",
                "domain": "example.org",
                "tier": "T1",
                "title": "Canonical clinical evidence — v1 fixture source",
                "authors": ["Test, A."],
                "snippet": "Snippet fixture content for the canonical fixture source.",
                "full_text_available": True,
                "full_text": "Full text body fixture content for the canonical fixture source.",
                "fetched_at_utc": FIXED_TIMESTAMP,
                "provenance": {"fetched_by": "canonical_fixture"},
                "retracted": False,
            }
        ],
        "adequacy": {
            "is_adequate": True,
            "sources_per_tier": {"T1": 1},
            "min_required_per_tier": {"T1": 1},
            "failure_reason": None,
        },
        "queries_executed": ["canonical fixture query"],
        "retrieval_started_at_utc": FIXED_TIMESTAMP,
        "retrieval_finished_at_utc": FIXED_TIMESTAMP,
        "latency_ms": 100,
        "cost_usd": 0.0,
    }


def _build_verified_report() -> dict:
    """Minimal valid VerifiedReport — see clinical_generator/verified_report.py."""
    return {
        "report_id": FIXED_REPORT_ID,
        "pool_id": FIXED_POOL_ID,
        "decision_id": FIXED_DECISION_ID,
        "sections": [],
        "overall_verify_pass_rate": 0.0,
        "verifier_pass_threshold": 0.4,
        "pipeline_verdict": "abort_no_verified_sections",
        "generator_model": GENERATOR_MODEL,
        "evaluator_model": EVALUATOR_MODEL,
        "family_segregation_passed": True,
        "started_at_utc": FIXED_TIMESTAMP,
        "finished_at_utc": FIXED_TIMESTAMP,
        "latency_ms": 1500,
        "cost_usd": 0.0,
    }


def _build_metadata() -> dict:
    """Bundle-level metadata (NOT the manifest — metadata.json content)."""
    return {
        "polaris_version": POLARIS_VERSION,
        "generator_model": GENERATOR_MODEL,
        "evaluator_model": EVALUATOR_MODEL,
        "bundle_created_at_utc": FIXED_TIMESTAMP,
        "schema_version": BUNDLE_VERSION,
    }


def _build_reasoning_trace_jsonl() -> str:
    """JSONL: 2 records, one per generator LLM call.

    Schema mirrors `src/polaris_graph/generator/reasoning_trace.py:67
    ReasoningTraceRecord` (the active producer dataclass). Codex diff
    iter-1 P1: align with real producer; previous 5-field invented shape
    diverged from the 15-field production record.
    """
    records = [
        {
            "call_id": "call_0001",
            "section": "outline",
            "call_type": "outline",
            "model": GENERATOR_MODEL,
            "status": "ok",
            "content_source": "direct",
            "parent_call_id": None,
            "regen_reason": None,
            "attempt_n": 1,
            "reasoning_text": "Outline reasoning trace fixture content for the canonical fixture.",
            "content_text": "1. Background\n2. Methods\n3. Results\n4. Limitations\n",
            "input_tokens": 100,
            "output_tokens": 80,
            "reasoning_tokens": 200,
            "timestamp": FIXED_TIMESTAMP,
        },
        {
            "call_id": "call_0002",
            "section": "Background",
            "call_type": "section",
            "model": GENERATOR_MODEL,
            "status": "ok",
            "content_source": "direct",
            "parent_call_id": "call_0001",
            "regen_reason": None,
            "attempt_n": 1,
            "reasoning_text": "Section reasoning trace fixture content for the canonical fixture.",
            "content_text": "Background prose fixture content.",
            "input_tokens": 200,
            "output_tokens": 150,
            "reasoning_tokens": 400,
            "timestamp": FIXED_TIMESTAMP,
        },
    ]
    return "".join(json.dumps(rec, sort_keys=True) + "\n" for rec in records)


def _build_source_snapshot() -> str:
    """Source full-text snapshot — plain UTF-8 text."""
    return (
        "Canonical clinical evidence source — v1 fixture.\n"
        "This is a fixture content full-text body used by the I-cd-012 "
        "canonical signed-bundle fixture for tests/polaris_graph/"
        "audit_bundle/test_conformance.py.\n"
    )


def _sign_manifest(fixture_dir: Path) -> None:
    """Sign manifest.yaml -> manifest.yaml.asc with the real POLARIS bundle key.

    Fail-loud (LAW II): if POLARIS_GPG_KEY_ID is unset, or signing/verify fails,
    RAISE. This script must NEVER write a placeholder/stub signature — a stub was
    the root cause of the born-inconsistent fixture (I-ready-018 #1139): the
    committed fixtures ship a REAL armored signature, and a stub-writing regen
    would silently downgrade it. The conformance check only asserts the .asc is
    present + non-empty, but the bundle's whole point is a genuine signature, so
    every regeneration MUST produce one that `gpg --verify` accepts.

    Key/homedir/passphrase come from POLARIS_GPG_KEY_ID / POLARIS_GPG_HOMEDIR
    (or GNUPGHOME) / POLARIS_GPG_PASSPHRASE — the same env contract as
    src/polaris_graph/audit_bundle/gpg_signer.load_config_from_env.
    """
    key_id = os.environ.get("POLARIS_GPG_KEY_ID", "").strip()
    if not key_id:
        raise RuntimeError(
            "POLARIS_GPG_KEY_ID is unset — cannot sign the canonical fixture. "
            "Set it (see .env / scripts/bootstrap_gpg_demo_key.sh) and re-run. "
            "Refusing to emit a placeholder stub (LAW II: no silent signature "
            "downgrade)."
        )
    manifest = fixture_dir / "manifest.yaml"
    signature = fixture_dir / "manifest.yaml.asc"
    if signature.exists():
        signature.unlink()
    homedir = (
        os.environ.get("POLARIS_GPG_HOMEDIR", "").strip()
        or os.environ.get("GNUPGHOME", "").strip()
    )
    passphrase = os.environ.get("POLARIS_GPG_PASSPHRASE", "").strip()
    base = ["gpg", "--batch", "--yes", "--pinentry-mode", "loopback"]
    if homedir:
        base += ["--homedir", homedir]
    sign_cmd = list(base)
    if passphrase:
        sign_cmd += ["--passphrase", passphrase]
    sign_cmd += [
        "--local-user", key_id, "--armor", "--detach-sign",
        "--output", str(signature), str(manifest),
    ]
    result = subprocess.run(sign_cmd, capture_output=True, text=True)
    if not signature.exists() or signature.stat().st_size == 0:
        raise RuntimeError(f"gpg signing failed: {result.stderr.strip()}")
    # LF-normalize so the committed signature is byte-stable cross-platform,
    # paired with the `tests/fixtures/signed_bundle/** -text` .gitattributes rule.
    signature.write_bytes(signature.read_bytes().replace(b"\r\n", b"\n"))
    verify = subprocess.run(
        base + ["--verify", str(signature), str(manifest)],
        capture_output=True, text=True,
    )
    if "Good signature" not in verify.stderr:
        raise RuntimeError(
            f"gpg --verify failed after signing {signature}: {verify.stderr.strip()}"
        )
    print(f"  signed manifest.yaml.asc with key {key_id} (gpg --verify: GOOD)")


def regenerate() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    SOURCES_SUBDIR.mkdir(parents=True, exist_ok=True)

    # --- 1. Write each content file deterministically ----------------
    files_on_disk: list[tuple[str, str, str]] = []  # (rel_path, content_type, bytes)

    def write(rel_path: str, content_type: str, body: str) -> None:
        abs_path = FIXTURE_DIR / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(body, encoding="utf-8", newline="\n")
        files_on_disk.append((rel_path, content_type, body))

    write("scope_decision.json", "scope_decision", _canonical_json_dump(_build_scope_decision()))
    write("evidence_pool.json", "evidence_pool", _canonical_json_dump(_build_evidence_pool()))
    write("verified_report.json", "verified_report", _canonical_json_dump(_build_verified_report()))
    write("metadata.json", "metadata", _canonical_json_dump(_build_metadata()))
    write("reasoning_trace.jsonl", "reasoning_trace", _build_reasoning_trace_jsonl())
    write(f"sources/{FIXED_SOURCE_ID}.txt", "source_snapshot", _build_source_snapshot())

    # --- 2. Build the manifest referencing the on-disk files ---------
    entries: list[FileEntry] = []
    for rel_path, content_type, body in files_on_disk:
        body_bytes = body.encode("utf-8")
        entries.append(
            FileEntry(
                path=rel_path,
                sha256=_sha256_hex(body_bytes),
                size_bytes=len(body_bytes),
                content_type=content_type,  # type: ignore[arg-type]
            )
        )

    manifest = BundleManifest(
        bundle_id=FIXED_BUNDLE_ID,
        bundle_version=BUNDLE_VERSION,
        decision_id=FIXED_DECISION_ID,
        pool_id=FIXED_POOL_ID,
        report_id=FIXED_REPORT_ID,
        generator_model=GENERATOR_MODEL,
        polaris_version=POLARIS_VERSION,
        files=entries,
        bundle_created_at_utc=datetime.fromisoformat(FIXED_TIMESTAMP),
    )

    # Deterministic YAML: sorted keys.
    manifest_dump = yaml.safe_dump(
        json.loads(manifest.model_dump_json()),
        sort_keys=True,
        default_flow_style=False,
    )
    (FIXTURE_DIR / "manifest.yaml").write_text(manifest_dump, encoding="utf-8", newline="\n")

    # --- 3. Sign the manifest with the real bundle key (fail-loud) -------
    _sign_manifest(FIXTURE_DIR)

    print(f"regenerated fixture at {FIXTURE_DIR}")
    print(f"  {len(entries)} content files + manifest.yaml + manifest.yaml.asc")
    print(f"  bundle_version = {BUNDLE_VERSION}")


def _build_verified_report_success() -> dict:
    """VerifiedReport with pipeline_verdict=success + 2 populated Sections.

    Per Codex iter-1 P2: a SUCCESS-shape fixture exercises the verified-
    report-sections renderer + provenance-token click + family-segregation
    badge against the same-lineage invariant — distinct from the abort
    fixture in v1_canonical/.
    """
    section_a_sentences = [
        {
            "section_id": "Population",
            "sentence_text": (
                "Tirzepatide is a dual GIP and GLP-1 receptor agonist approved "
                "for type 2 diabetes mellitus."
            ),
            "provenance_tokens": ["[#ev:" + FIXED_SOURCE_ID + ":0-99]"],
            "verifier_pass": True,
            "drop_reason": None,
            "evaluator_agrees": True,
            "assertion_surface": "prose",
            "evaluator_disagreement": None,
            "contradiction": None,
            "is_synthesis_claim": False,
        },
        {
            "section_id": "Population",
            "sentence_text": (
                "It is administered subcutaneously once weekly."
            ),
            "provenance_tokens": [
                "[#ev:" + FIXED_SOURCE_ID + ":100-200]",
            ],
            "verifier_pass": True,
            "drop_reason": None,
            "evaluator_agrees": True,
            "assertion_surface": "prose",
            "evaluator_disagreement": None,
            "contradiction": None,
            "is_synthesis_claim": False,
        },
    ]
    section_b_sentences = [
        {
            "section_id": "Outcomes",
            "sentence_text": (
                "Phase III trials reported A1C reductions of 2.0 to 2.4 percentage "
                "points over 40 weeks."
            ),
            "provenance_tokens": [
                "[#ev:" + FIXED_SOURCE_ID + ":201-350]",
            ],
            "verifier_pass": True,
            "drop_reason": None,
            "evaluator_agrees": True,
            "assertion_surface": "prose",
            "evaluator_disagreement": None,
            "contradiction": None,
            "is_synthesis_claim": False,
        },
    ]
    return {
        "report_id": FIXED_REPORT_ID + "_success",
        "pool_id": FIXED_POOL_ID,
        "decision_id": FIXED_DECISION_ID,
        "sections": [
            {
                "section_id": "Population",
                "section_title": "Population",
                "verified_sentences": section_a_sentences,
                "section_verify_pass_rate": 1.0,
                "section_status": "verified",
            },
            {
                "section_id": "Outcomes",
                "section_title": "Outcomes",
                "verified_sentences": section_b_sentences,
                "section_verify_pass_rate": 1.0,
                "section_status": "verified",
            },
        ],
        "overall_verify_pass_rate": 1.0,
        "verifier_pass_threshold": 0.4,
        "pipeline_verdict": "success",
        "generator_model": GENERATOR_MODEL,
        "evaluator_model": EVALUATOR_MODEL,
        "family_segregation_passed": True,
        "started_at_utc": FIXED_TIMESTAMP,
        "finished_at_utc": FIXED_TIMESTAMP,
        "latency_ms": 4200,
        "cost_usd": 0.0,
    }


def _build_reviewer_readme() -> str:
    """REVIEWER_README.md content for the success fixture — duplicate
    `content_type=metadata` entry so the Inspector's metadata-by-path
    selection is exercised (Codex iter-2 P2)."""
    return (
        "# POLARIS audit bundle — reviewer guide (canonical-success fixture)\n\n"
        "This bundle is the v1.0 SUCCESS-shape canonical fixture used by\n"
        "I-cd-013a Inspector route tests. The active bundle producer emits\n"
        "this file with `content_type=\"metadata\"` alongside `metadata.json`;\n"
        "downstream consumers MUST select `metadata.json` by explicit path.\n"
    )


def regenerate_success() -> None:
    """Deterministic regeneration of v1_canonical_success/ — pipeline_verdict=success."""
    fixture_dir = SUCCESS_FIXTURE_DIR
    sources_subdir = fixture_dir / "sources"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    sources_subdir.mkdir(parents=True, exist_ok=True)

    files_on_disk: list[tuple[str, str, str]] = []

    def write(rel_path: str, content_type: str, body: str) -> None:
        abs_path = fixture_dir / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_text(body, encoding="utf-8", newline="\n")
        files_on_disk.append((rel_path, content_type, body))

    write("scope_decision.json", "scope_decision", _canonical_json_dump(_build_scope_decision()))
    write("evidence_pool.json", "evidence_pool", _canonical_json_dump(_build_evidence_pool()))
    write("verified_report.json", "verified_report", _canonical_json_dump(_build_verified_report_success()))
    write("metadata.json", "metadata", _canonical_json_dump(_build_metadata()))
    # Codex iter-2 P2: second content_type=metadata entry exercises the
    # metadata-by-explicit-path selection logic in the Inspector loader.
    write("REVIEWER_README.md", "metadata", _build_reviewer_readme())
    write("reasoning_trace.jsonl", "reasoning_trace", _build_reasoning_trace_jsonl())
    write(f"sources/{FIXED_SOURCE_ID}.txt", "source_snapshot", _build_source_snapshot())

    entries: list[FileEntry] = []
    for rel_path, content_type, body in files_on_disk:
        body_bytes = body.encode("utf-8")
        entries.append(
            FileEntry(
                path=rel_path,
                sha256=_sha256_hex(body_bytes),
                size_bytes=len(body_bytes),
                content_type=content_type,  # type: ignore[arg-type]
            )
        )

    manifest = BundleManifest(
        bundle_id=FIXED_BUNDLE_ID + "_success",
        bundle_version=BUNDLE_VERSION,
        decision_id=FIXED_DECISION_ID,
        pool_id=FIXED_POOL_ID,
        report_id=FIXED_REPORT_ID + "_success",
        generator_model=GENERATOR_MODEL,
        polaris_version=POLARIS_VERSION,
        files=entries,
        bundle_created_at_utc=datetime.fromisoformat(FIXED_TIMESTAMP),
    )

    manifest_dump = yaml.safe_dump(
        json.loads(manifest.model_dump_json()),
        sort_keys=True,
        default_flow_style=False,
    )
    (fixture_dir / "manifest.yaml").write_text(manifest_dump, encoding="utf-8", newline="\n")

    _sign_manifest(fixture_dir)

    print(f"regenerated success fixture at {fixture_dir}")
    print(f"  {len(entries)} content files + manifest.yaml + manifest.yaml.asc")
    print(f"  bundle_version = {BUNDLE_VERSION}; pipeline_verdict = success")


if __name__ == "__main__":
    regenerate()
    regenerate_success()
