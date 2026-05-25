"""
compute_ui_surface_sha.py — print sha256 of the UI surface (web/app/** + web/components/**).

Used by both visual_review_gate.py (when emitting the audit) and the
codex-visual-required CI workflow (when verifying it). Single source
of truth for the algorithm; if it drifts, the audit breaks.

The algorithm matches `git ls-files <paths> | sort | xargs sha256sum |
sha256sum` semantics but is pure-Python and works on the working tree
(not git-tracked content), so the writer sees the same SHA they'd see
on CI before committing.

Excludes node_modules and .next (heavy / regenerated). Prints exactly
one 64-hex line on stdout; exits 0 always (a missing surface dir
yields an empty hash, which the gate treats as a separate error).
"""

from __future__ import annotations

import hashlib
import pathlib
import sys


UI_SURFACE_PATHS = ("web/app", "web/components")


def compute(repo_root: pathlib.Path) -> str:
    parts: list[bytes] = []
    for surface in UI_SURFACE_PATHS:
        root = repo_root / surface
        if not root.exists():
            continue
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            if "node_modules" in p.parts:
                continue
            if ".next" in p.parts:
                continue
            rel = p.relative_to(repo_root).as_posix()
            h = hashlib.sha256()
            with p.open("rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            parts.append(f"{h.hexdigest()}  {rel}\n".encode("utf-8"))
    return hashlib.sha256(b"".join(parts)).hexdigest()


if __name__ == "__main__":
    repo_root = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path.cwd()
    print(compute(repo_root))
