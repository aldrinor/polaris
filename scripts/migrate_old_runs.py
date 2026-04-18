"""
Migrate pre-HONEST-REBUILD POLARIS run JSONs to the new schema.

Plan: C:/Users/msn/.claude/plans/lovely-finding-firefly.md Phase 1e.

Pre-rebuild schema:
    {
        "faithfulness_score": 1.0,          # self-graded, survivorship-biased
        "quality_metrics": {
            "faithfulness_score": 1.0,      # ditto
            ...
        },
        "hallucination_audit": [...],       # NLI post-synthesis audit
        ...
    }

Post-rebuild schema:
    {
        "mode_label": "Legacy run, pre-honest-rebuild",
        "evaluator_output": {
            "legacy_faithfulness": 1.0,
            "legacy_note": "LEGACY METRIC, NOT COMPARABLE TO CURRENT OUTPUT",
            "external_evaluator_grade": null,   # Phase 5 will fill this in
        },
        "quality_metrics": {
            # faithfulness_score renamed to _legacy_faithfulness_score
            ...
        },
        "_legacy_hallucination_audit": [...],   # preserved, not re-used
        ...
    }

Behavior:
- Idempotent: running twice yields the same output as running once.
- Original files preserved at outputs/_archive_pre_rebuild/<filename>.
- Emits a manifest at outputs/_archive_pre_rebuild/_migration_manifest.json
  listing processed files, skipped files, and any errors.
- Does NOT re-score or re-evaluate any content. Only renames fields and
  adds the legacy marker. Phase 5's external evaluator handles scoring.

Usage:
    python scripts/migrate_old_runs.py
    python scripts/migrate_old_runs.py --dry-run
    python scripts/migrate_old_runs.py --path outputs/polaris_graph
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LEGACY_NOTE = "LEGACY METRIC, NOT COMPARABLE TO CURRENT OUTPUT"
LEGACY_MODE_LABEL = "Legacy run, pre-honest-rebuild"
MIGRATION_MARKER = "_honest_rebuild_migration"


def _is_already_migrated(data: dict[str, Any]) -> bool:
    """Check if the file has already been migrated (idempotency guard)."""
    return data.get(MIGRATION_MARKER) is not None


def _needs_migration(data: dict[str, Any]) -> bool:
    """Check if the file contains pre-rebuild schema."""
    if "faithfulness_score" in data:
        return True
    qm = data.get("quality_metrics") or {}
    if "faithfulness_score" in qm:
        return True
    if "hallucination_audit" in data:
        return True
    return False


def migrate_record(data: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Return a migrated copy of the record and a list of changes applied.

    Does not mutate the input.
    """
    changes: list[str] = []
    out = dict(data)  # shallow copy; we'll deep-copy nested dicts on write

    # Rename top-level faithfulness_score
    if "faithfulness_score" in out:
        legacy = out.pop("faithfulness_score")
        eval_block = dict(out.get("evaluator_output") or {})
        eval_block["legacy_faithfulness"] = legacy
        eval_block["legacy_note"] = LEGACY_NOTE
        eval_block.setdefault("external_evaluator_grade", None)
        out["evaluator_output"] = eval_block
        changes.append("moved top-level faithfulness_score -> evaluator_output.legacy_faithfulness")

    # Rename quality_metrics.faithfulness_score
    qm = out.get("quality_metrics")
    if isinstance(qm, dict) and "faithfulness_score" in qm:
        qm = dict(qm)
        legacy = qm.pop("faithfulness_score")
        qm["_legacy_faithfulness_score"] = legacy
        qm["_legacy_note"] = LEGACY_NOTE
        out["quality_metrics"] = qm
        changes.append("renamed quality_metrics.faithfulness_score -> _legacy_faithfulness_score")

    # Preserve hallucination_audit under legacy name if present
    if "hallucination_audit" in out:
        audit = out.pop("hallucination_audit")
        out["_legacy_hallucination_audit"] = audit
        changes.append("moved hallucination_audit -> _legacy_hallucination_audit (pre-rebuild NLI audit preserved for reference only)")

    # Set mode label if missing
    if "mode_label" not in out:
        out["mode_label"] = LEGACY_MODE_LABEL
        changes.append("set mode_label = 'Legacy run, pre-honest-rebuild'")

    # Migration marker
    out[MIGRATION_MARKER] = {
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "migration_script": "scripts/migrate_old_runs.py",
        "plan": "C:/Users/msn/.claude/plans/lovely-finding-firefly.md",
        "changes": changes,
    }
    return out, changes


def process_file(
    src_path: Path,
    archive_dir: Path,
    dry_run: bool,
) -> dict[str, Any]:
    """Process a single JSON file. Returns a status record."""
    status: dict[str, Any] = {
        "path": str(src_path),
        "action": "unknown",
        "changes": [],
        "error": None,
    }
    try:
        data = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception as exc:
        status["action"] = "error_reading"
        status["error"] = f"{type(exc).__name__}: {exc}"
        return status

    if _is_already_migrated(data):
        status["action"] = "skip_already_migrated"
        return status
    if not _needs_migration(data):
        status["action"] = "skip_no_legacy_fields"
        return status

    migrated, changes = migrate_record(data)
    status["changes"] = changes

    if dry_run:
        status["action"] = "would_migrate"
        return status

    # Archive original
    archive_dir.mkdir(parents=True, exist_ok=True)
    archived_path = archive_dir / src_path.name
    shutil.copy2(str(src_path), str(archived_path))

    # Write migrated file in place
    src_path.write_text(
        json.dumps(migrated, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    status["action"] = "migrated"
    status["archived_to"] = str(archived_path)
    return status


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--path",
        default="outputs/polaris_graph",
        help="directory containing run JSONs (default: outputs/polaris_graph)",
    )
    ap.add_argument(
        "--archive-dir",
        default="outputs/_archive_pre_rebuild",
        help="directory to archive pre-migration originals (default: outputs/_archive_pre_rebuild)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="do not modify any files; print what would be done",
    )
    ap.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="print per-file status lines",
    )
    args = ap.parse_args(argv)

    src_dir = Path(args.path).resolve()
    archive_dir = Path(args.archive_dir).resolve()

    if not src_dir.exists():
        print(f"[migrate_old_runs] source path does not exist: {src_dir}", file=sys.stderr)
        return 2

    json_files = sorted(p for p in src_dir.glob("*.json") if p.is_file())
    if not json_files:
        print(f"[migrate_old_runs] no JSON files found in {src_dir}")
        return 0

    print(
        f"[migrate_old_runs] scanning {len(json_files)} JSON files in {src_dir}"
        f" (dry_run={args.dry_run})"
    )

    results = []
    for path in json_files:
        status = process_file(path, archive_dir, args.dry_run)
        results.append(status)
        if args.verbose or status["action"] in {"error_reading", "migrated", "would_migrate"}:
            line = f"  [{status['action']}] {path.name}"
            if status.get("error"):
                line += f"  error: {status['error']}"
            print(line)

    # Counts
    by_action: dict[str, int] = {}
    for r in results:
        by_action[r["action"]] = by_action.get(r["action"], 0) + 1
    print(f"[migrate_old_runs] summary: {by_action}")

    # Manifest (even in dry-run; it's just a record, doesn't modify source files)
    if not args.dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = archive_dir / "_migration_manifest.json"
        existing = []
        if manifest_path.exists():
            try:
                existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.append({
            "run_at": datetime.now(timezone.utc).isoformat(),
            "source_dir": str(src_dir),
            "results": results,
            "summary": by_action,
        })
        manifest_path.write_text(
            json.dumps(existing, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[migrate_old_runs] manifest: {manifest_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
