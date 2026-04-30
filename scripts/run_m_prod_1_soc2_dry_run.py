"""M-PROD-1: SOC2 dry-run + remediation audit.

Walks the SOC2 evidence map (docs/compliance/soc2_evidence_map.md)
and validates each referenced evidence artifact actually exists
in the current codebase. Surfaces:
  - artifacts that still exist (intact)
  - artifacts that no longer exist (gap; remediation needed)
  - artifacts referenced by glob (e.g. `*.yaml`) that resolve to
    real matching files

Per FINAL_PLAN Phase H M-PROD-1 (10 days). v1 is the AUTOMATED
gap detection. v2+ will be the remediation patches per gap.

Output:
  outputs/m_prod_1_soc2/manifest.json — per-artifact verdict +
  aggregate counts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SOC2_DOC = REPO_ROOT / "docs" / "compliance" / "soc2_evidence_map.md"
OUT_DIR = REPO_ROOT / "outputs" / "m_prod_1_soc2"


# Match any backtick-quoted reference that LOOKS like a file or
# directory path inside the evidence map. We deliberately accept
# broad matches because the doc is hand-written prose with mixed
# styles (some bare paths, some Markdown links, some glob
# patterns).
_PATH_LIKE_RE = re.compile(
    r"`("
    # 1. Files with a known extension (any path)
    r"(?:[A-Za-z_.][A-Za-z0-9_./{}<>*?-]*)"
    r"\.(?:py|md|json|jsonl|sqlite|yaml|yml|toml|sh|html|env)"
    r"|"
    # 2. Paths rooted at top-level repo dirs (with optional
    # trailing slash for directory-only references)
    r"(?:scripts|src|state|outputs|logs|docs|config|tests)"
    r"(?:/[A-Za-z0-9_./{}<>*?-]+|/)"
    r"|"
    # 3. v2 R1 P0 #2 fix: dotfile refs (.env, .gitignore, etc.)
    r"\.[A-Za-z][A-Za-z0-9_-]*"
    r")`"
)


# Some evidence references include f-string-like placeholders
# (e.g. `{vector_id}`). Treat those as glob wildcards.
def _to_glob(path_str: str) -> str:
    """Normalize SOC2 doc placeholders into glob wildcards.

    `{vector_id}` and `<phase>` both become `*`. Bare `...`
    placeholders also become `*` (used in doc prose as
    "any-subdir"). Trailing `/` is preserved (a directory
    reference)."""
    s = re.sub(r"\{[^}]+\}", "*", path_str)
    s = re.sub(r"<[^>]+>", "*", s)
    s = re.sub(r"\.{3,}", "*", s)
    return s


def _classify(path_str: str) -> dict[str, Any]:
    """Resolve a referenced path against the repo and report whether
    it exists. Treats `{var}` and `<var>` placeholders as glob
    wildcards.

    v2 R1 P0 #1 fix: dropped the rglob-anywhere fallback. v1
    fell back to `REPO_ROOT.rglob(tail)` when the documented
    path didn't match — that matched the same basename ANYWHERE
    in the repo, so `config/settings/*.yaml` falsely passed when
    `config/settings/` was renamed but YAML files existed
    elsewhere. v2 binds the glob to the documented prefix
    strictly: if the path doesn't exist where the doc claims,
    it's a gap.
    """
    glob_str = _to_glob(path_str)
    is_glob = "*" in glob_str or "?" in glob_str
    abs_candidate = REPO_ROOT / glob_str
    if is_glob:
        try:
            matches = list(REPO_ROOT.glob(glob_str))
        except Exception as exc:
            return {
                "path": path_str,
                "exists": False,
                "kind": "glob_error",
                "error": str(exc),
            }
        return {
            "path": path_str,
            "kind": "glob",
            "exists": bool(matches),
            "match_count": len(matches),
            "first_match": str(matches[0]) if matches else None,
        }
    return {
        "path": path_str,
        "kind": "literal",
        "exists": abs_candidate.exists(),
        "resolved_path": str(abs_candidate),
    }


def main() -> int:
    if not SOC2_DOC.exists():
        print(
            f"[M-PROD-1] SOC2 evidence map not found: {SOC2_DOC}",
            file=sys.stderr,
        )
        return 2

    text = SOC2_DOC.read_text(encoding="utf-8")
    raw_paths = _PATH_LIKE_RE.findall(text)

    # Dedup while preserving order.
    seen: set[str] = set()
    paths: list[str] = []
    for p in raw_paths:
        if p not in seen:
            seen.add(p)
            paths.append(p)

    # Skip inline / unqualified filenames already covered by a
    # qualified path elsewhere in the doc (e.g. parenthetical
    # `pg_batch_progress.sqlite` when `state/pg_batch_progress.sqlite`
    # also appears in the same evidence column). These are the
    # same artifact mentioned twice, not two separate references.
    qualified_basenames = {
        Path(p).name for p in paths if "/" in p
    }
    paths = [
        p for p in paths
        if "/" in p or Path(p).name not in qualified_basenames
    ]

    print("=" * 72)
    print("M-PROD-1 v2 — SOC2 dry-run evidence audit")
    print("=" * 72)
    print(f"  evidence map: {SOC2_DOC}")
    print(f"  references found: {len(paths)}")
    print()

    classifications = [_classify(p) for p in paths]
    intact = [c for c in classifications if c["exists"]]
    gaps = [c for c in classifications if not c["exists"]]

    print(f"  intact:   {len(intact)} / {len(paths)}")
    print(f"  gaps:     {len(gaps)} / {len(paths)}")
    print()
    if gaps:
        print("Gaps (artifacts referenced by SOC2 doc but missing):")
        for g in gaps:
            print(f"  - {g['path']!r}")
        print()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "milestone": "M-PROD-1",
        "version": "v2",
        "soc2_evidence_map": str(SOC2_DOC),
        "total_references": len(paths),
        "intact_count": len(intact),
        "gap_count": len(gaps),
        "intact_fraction": (
            len(intact) / len(paths) if paths else 1.0
        ),
        "intact": intact,
        "gaps": gaps,
    }
    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"manifest: {manifest_path}")
    print("=" * 72)

    return 0 if not gaps else 1


if __name__ == "__main__":
    raise SystemExit(main())
