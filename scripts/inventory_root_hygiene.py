"""Inventory POLARIS root for I-hygiene-001 cleanup.

Categorizes every top-level entry under C:/POLARIS/ as:
- KEEP: essential project structure, must remain at root
- ARCHIVE: temp/scratch/cache dir or obsolete artifact, move to archive/2026-05-11-root-hygiene/
- INSPECT: ambiguous, needs Codex review

Does NOT delete or move anything. Output: state/polaris_restart/i_hygiene_001_inventory.md.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path("C:/POLARIS")

KEEP_DIRS = {
    # Hidden essentials
    ".claude", ".codex", ".env", ".github", ".gitignore", ".dockerignore",
    ".legacy", ".private", ".git",
    # Top-level files
    "CLAUDE.md", "Dockerfile", "README.md", "architecture.md", "ground_rules.md",
    "docker-compose.yml", "pytest.ini",
    "requirements.txt", "requirements-orchestrator.txt", "requirements-v6.txt",
    # Top-level dirs (essential project structure)
    "archive", "config", "data", "docs", "helm", "logs", "memory", "models",
    "outputs", "polaris-controls", "scripts", "src", "state", "tests", "web",
    # User env files
    ".env.example",
}

# Patterns that indicate clearly-archivable scratch
ARCHIVE_PATTERNS = [
    re.compile(r"^\.codex-tmp$"),
    re.compile(r"^\.codex_pytest_tmp$"),
    re.compile(r"^\.codex_review_workforce$"),
    re.compile(r"^\.codex_tmp.*$"),
    re.compile(r"^\.coverage$"),
    re.compile(r"^\.pytest-cache.*$"),
    re.compile(r"^\.pytest_cache.*$"),
    re.compile(r"^\.pytest_scope_gate_tmp.*$"),
    re.compile(r"^\.pytest_tmp.*$"),
    re.compile(r"^\.ruff_cache$"),
    re.compile(r"^\.tmp.*$"),
    re.compile(r"^POLARIS\.tmppytest$"),
    re.compile(r"^POLARIStmp_pytest.*$"),
    re.compile(r"^__pycache__$"),
    re.compile(r"^codex_cache_.*$"),
    re.compile(r"^codex_review_tmp.*$"),
    re.compile(r"^codex_tmp.*$"),
    re.compile(r"^dashboard_probe.*$"),
    re.compile(r"^m\d+v\d+.*$"),  # m10v2_manual, m10v3_one, m9v2_pytest etc.
    re.compile(r"^m8_.*$"),
    re.compile(r"^m9_.*$"),
    re.compile(r"^m_int_.*_manual_.*$"),
    re.compile(r"^m_live_.*$"),
    re.compile(r"^manual_pytest_.*$"),
    re.compile(r"^manual_review_scratch.*$"),
    re.compile(r"^manual_tmp.*$"),
    re.compile(r"^md3_.*_tmp$"),
    re.compile(r"^md3_round.*$"),
    re.compile(r"^md3_pytest.*$"),
    re.compile(r"^py_pytest.*$"),
    re.compile(r"^pytest-cache-files-.*$"),
    re.compile(r"^pytest_basetemp.*$"),
    re.compile(r"^pytest_run_.*$"),
    re.compile(r"^python_mode_.*_probe$"),
    re.compile(r"^tmp.*$"),
]

NAMING_VIOLATIONS = []  # populated as we scan


def categorize(name: str, is_dir: bool) -> tuple[str, str]:
    """Return (category, reason)."""
    if name in KEEP_DIRS:
        return "KEEP", "essential project structure"
    for pat in ARCHIVE_PATTERNS:
        if pat.match(name):
            # Check naming violation for the report
            if re.search(r"[A-Z]", name) and not name.startswith("POLARIS") and not name == "__pycache__":
                NAMING_VIOLATIONS.append(name)
            elif "." in name and name not in (".coverage",) and not name.startswith("."):
                NAMING_VIOLATIONS.append(name)
            return "ARCHIVE", f"matches archive pattern: {pat.pattern}"
    return "INSPECT", "unrecognized — needs Codex review"


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    entries = sorted(os.listdir(ROOT))
    keep, archive, inspect = [], [], []
    for name in entries:
        full = ROOT / name
        is_dir = full.is_dir()
        cat, reason = categorize(name, is_dir)
        marker = "[D]" if is_dir else "[F]"
        line = f"{marker} {name} — {reason}"
        if cat == "KEEP":
            keep.append(line)
        elif cat == "ARCHIVE":
            archive.append(line)
        else:
            inspect.append(line)

    out_path = Path("state/polaris_restart/i_hygiene_001_inventory.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    body = [
        "# I-hygiene-001 root-cleanup inventory",
        "",
        f"Source: `{ROOT}` enumerated 2026-05-11.",
        f"Total entries: {len(entries)} | KEEP: {len(keep)} | ARCHIVE: {len(archive)} | INSPECT: {len(inspect)}",
        "",
        "## KEEP (essential, must remain at root)",
        "",
        *keep,
        "",
        "## ARCHIVE (move to archive/2026-05-11-root-hygiene/)",
        "",
        *archive,
        "",
        "## INSPECT (Codex must adjudicate — unrecognized at root)",
        "",
        *inspect,
        "",
        "## CLAUDE.md §4.1 snake_case naming violations (subset of ARCHIVE — recorded for the report)",
        "",
        *(f"- `{v}`" for v in NAMING_VIOLATIONS),
    ]
    out_path.write_text("\n".join(body), encoding="utf-8")
    print(f"saved {out_path}")
    print(f"KEEP={len(keep)} ARCHIVE={len(archive)} INSPECT={len(inspect)}")


if __name__ == "__main__":
    main()
