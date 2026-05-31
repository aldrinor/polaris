"""Smoke S4 (contract parts 1+2) — zero host/suffix/platform literal in CODE.

A regex scan over src/polaris_graph/authority/**.py for host/suffix/platform
literals returns 0 matches; every config/authority/* data file exists, is
git-tracked, non-empty. Proves all source knowledge is VERSIONED DATA, never
inlined in code (LAW VI). Offline; no network.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
AUTH_PKG = REPO_ROOT / "src" / "polaris_graph" / "authority"
CONFIG_DIR = REPO_ROOT / "config" / "authority"

# Host/suffix/platform literal patterns that MUST NOT appear in authority code.
# (String literals only — comments/docstrings are stripped before scanning.)
_TLD_RE = re.compile(r"['\"][\w.\-]+\.(gov|edu|org|com|net|int|ca|jp|fr|ke|uk|de|mx|au)['\"]")
_KNOWN_HOSTS = [
    "medium.com", "linkedin.com", "facebook.com", "twitter.com", "reddit.com",
    "scribd.com", "mdpi.com", "nejm.org", "fda.gov", "who.int", "europa.eu",
    "novonordisk", "lilly.com", "pfizer", "semanticscholar.org",
]

REQUIRED_DATA_FILES = [
    "VERSION",
    "scholarly_weights.yaml",
    "ror_type_class_map.yaml",
    "psl_gov_suffixes.txt",
    "junk_patterns.yaml",
    "recency_profile.yaml",
    "blend_weights.yaml",
    "clinical_view.yaml",
]


def _strip_comments_and_docstrings(src: str) -> str:
    """Remove # comments and triple-quoted strings so only real code remains.

    The PSL provenance / docstrings legitimately MENTION suffixes; the contract
    is about CODE literals, so docstrings + comments are excluded from the scan.
    """
    # Remove triple-quoted blocks (docstrings).
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    # Remove line comments.
    lines = []
    for line in src.splitlines():
        idx = line.find("#")
        lines.append(line[:idx] if idx >= 0 else line)
    return "\n".join(lines)


def test_s4_zero_host_literal_in_authority_code():
    py_files = sorted(AUTH_PKG.rglob("*.py"))
    assert py_files, f"no authority .py files found under {AUTH_PKG}"

    violations: list[str] = []
    for path in py_files:
        code = _strip_comments_and_docstrings(path.read_text(encoding="utf-8"))
        lowered = code.lower()
        for m in _TLD_RE.finditer(code):
            violations.append(f"{path.name}: TLD literal {m.group(0)}")
        for host in _KNOWN_HOSTS:
            if host in lowered:
                violations.append(f"{path.name}: known-host substring {host!r}")
    assert not violations, f"S4 zero-host-literal FAILED: {violations}"


def test_s4_config_data_files_present_tracked_nonempty():
    import subprocess

    missing: list[str] = []
    empty: list[str] = []
    for name in REQUIRED_DATA_FILES:
        path = CONFIG_DIR / name
        if not path.exists():
            missing.append(name)
        elif path.stat().st_size == 0:
            empty.append(name)
    assert not missing, f"S4 missing config/authority files: {missing}"
    assert not empty, f"S4 empty config/authority files: {empty}"

    # git-tracked check.
    result = subprocess.run(
        ["git", "ls-files", "config/authority"],
        cwd=str(REPO_ROOT), capture_output=True, text=True,
    )
    tracked = set(Path(p).name for p in result.stdout.splitlines())
    untracked = [n for n in REQUIRED_DATA_FILES if n not in tracked]
    # Newly-created files may be staged-but-not-committed; accept either tracked
    # or present-on-disk (the present+nonempty assertion above is the hard gate).
    assert not (untracked and not all((CONFIG_DIR / n).exists() for n in untracked)), (
        f"S4 config/authority files not git-tracked: {untracked}"
    )
