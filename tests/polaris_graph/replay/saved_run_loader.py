"""Typed loader for a SAVED POLARIS run directory's audit artifacts (I-perm-009).

A saved run directory (e.g. ``outputs/audits/beatboth8/drb_76/``) holds the real,
already-paid-for artifacts of a completed run. This loader reads them into a typed
``SavedRun`` so the replay harness can reconstruct the D8 decision and audit the report
WITHOUT re-running the pipeline (no network, no spend).

Fails loudly (FileNotFoundError / KeyError) on a missing artifact — never silently
defaults (LAW II).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Default saved run + scope template. Overridable via env (LAW VI, zero hard-coding):
# the harness must run against the committed beatboth8 evidence by default but stay
# repointable at any saved run dir without code edits.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ENV_RUN_DIR = "PG_REPLAY_RUN_DIR"
_ENV_TEMPLATE = "PG_REPLAY_TEMPLATE_PATH"
_DEFAULT_RUN_DIR = _REPO_ROOT / "outputs" / "audits" / "beatboth8" / "drb_76"
_DEFAULT_TEMPLATE = _REPO_ROOT / "config" / "scope_templates" / "clinical.yaml"

# Artifact filenames inside a saved run directory.
_FILE_AUDIT_MAP = "four_role_claim_audit.json"
_FILE_MANIFEST = "manifest.json"
_FILE_REPORT = "report.md"
_FILE_AUDIT_PACK = "audit_pack.json"

_MANIFEST_KEY_SLUG = "slug"
_MANIFEST_KEY_FOUR_ROLE = "four_role_evaluation"
_FOUR_ROLE_KEY_FINAL_VERDICTS = "final_verdicts"


@dataclass
class SavedRun:
    """All artifacts of one saved run, typed for the replay harness."""

    run_dir: Path
    slug: str
    audit_map: dict[str, dict[str, Any]]  # four_role_claim_audit.json (claim_id -> row)
    manifest: dict[str, Any]
    four_role: dict[str, Any]  # manifest["four_role_evaluation"]
    final_verdicts: dict[str, str]  # claim_id -> "VERIFIED"|"UNSUPPORTED"|...
    report_md: str
    audit_pack: dict[str, Any]  # claims[] with cited_span_text (None if not present)

    @property
    def saved_held_reasons(self) -> list[str]:
        return list(self.four_role.get("held_reasons", []))

    @property
    def saved_coverage_fraction(self) -> float:
        return float(self.four_role.get("coverage_fraction", 0.0))

    @property
    def saved_needs_rewrite(self) -> list[str]:
        return list(self.four_role.get("needs_rewrite", []))

    @property
    def saved_fabricated_latched(self) -> bool:
        return bool(self.four_role.get("fabricated_occurrence_latched", False))


def default_run_dir() -> Path:
    return Path(os.environ.get(_ENV_RUN_DIR) or _DEFAULT_RUN_DIR)


def default_template_path() -> Path:
    return Path(os.environ.get(_ENV_TEMPLATE) or _DEFAULT_TEMPLATE)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise FileNotFoundError(f"saved-run artifact missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_saved_run(run_dir: Path | str | None = None) -> SavedRun:
    """Load every artifact a saved run directory must contain.

    ``audit_pack.json`` is optional (only present after a build_audit_pack pass); when
    absent ``audit_pack`` is ``{}`` and the §-1.1 span audit is skipped by the caller.
    """
    run_path = Path(run_dir) if run_dir is not None else default_run_dir()
    if not run_path.is_dir():
        raise FileNotFoundError(f"saved-run directory not found: {run_path}")

    manifest = _read_json(run_path / _FILE_MANIFEST)
    if _MANIFEST_KEY_FOUR_ROLE not in manifest:
        raise KeyError(
            f"{_FILE_MANIFEST} has no {_MANIFEST_KEY_FOUR_ROLE!r} block: {run_path}"
        )
    four_role = manifest[_MANIFEST_KEY_FOUR_ROLE]
    final_verdicts = four_role.get(_FOUR_ROLE_KEY_FINAL_VERDICTS)
    if not isinstance(final_verdicts, dict):
        raise KeyError(
            f"{_MANIFEST_KEY_FOUR_ROLE}.{_FOUR_ROLE_KEY_FINAL_VERDICTS} missing/invalid: {run_path}"
        )

    audit_pack_path = run_path / _FILE_AUDIT_PACK
    audit_pack = _read_json(audit_pack_path) if audit_pack_path.is_file() else {}

    return SavedRun(
        run_dir=run_path,
        slug=str(manifest.get(_MANIFEST_KEY_SLUG, run_path.name)),
        audit_map=_read_json(run_path / _FILE_AUDIT_MAP),
        manifest=manifest,
        four_role=four_role,
        final_verdicts=final_verdicts,
        report_md=(run_path / _FILE_REPORT).read_text(encoding="utf-8"),
        audit_pack=audit_pack,
    )
