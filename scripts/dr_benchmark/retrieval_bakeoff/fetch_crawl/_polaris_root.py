"""I-ret-002 (#1294) layer 2 (fetch_crawl) — POLARIS repo-root resolver.

WHY THIS EXISTS
---------------
These four bake-off files are authored in an isolated git worktree whose checkout does NOT
contain the production seams (``src/polaris_graph/retrieval/shell_detector.py``,
``scripts/dr_benchmark/gate0_lineage.py``) nor the banked corpus snapshots. They live only in
the shared POLARIS checkout. This helper resolves the real POLARIS repo root at runtime and
inserts it on ``sys.path`` so the authored files import the SAME seams the pipeline uses (no
fork, no copy) and read the SAME banked corpora — whether run from the worktree or, later,
from the main tree (where the root resolves to the local repo and nothing changes).

RESOLUTION ORDER (first hit wins; FAILS LOUD if none found — never a silent wrong root):
  1. ``$POLARIS_ROOT`` env var, if it points at a dir containing the seams.
  2. The conventional absolute install path ``C:/POLARIS`` (and ``/POLARIS`` on POSIX).
  3. Walk up from this file's directory until a dir containing the seams is found.

No magic numbers; no silent fallback — a missing root raises so the harness fails loud (LAW II).
"""

from __future__ import annotations

import os
import sys

# Marker files that uniquely identify a real POLARIS checkout (the seams this layer reuses).
_ROOT_MARKERS = (
    os.path.join("src", "polaris_graph", "retrieval", "shell_detector.py"),
    os.path.join("scripts", "dr_benchmark", "gate0_lineage.py"),
)


def _has_markers(candidate: str) -> bool:
    return bool(candidate) and all(
        os.path.isfile(os.path.join(candidate, m)) for m in _ROOT_MARKERS
    )


def _candidate_paths() -> list[str]:
    candidates: list[str] = []
    env = os.environ.get("POLARIS_ROOT", "").strip()
    if env:
        candidates.append(os.path.abspath(env))
    # Conventional install paths.
    candidates.append(os.path.abspath("C:/POLARIS"))
    candidates.append(os.path.abspath("/POLARIS"))
    # Walk up from this file (covers the main-tree case: the seams are local).
    here = os.path.dirname(os.path.abspath(__file__))
    cur = here
    for _ in range(12):
        candidates.append(cur)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # De-dup, preserve order.
    seen: set[str] = set()
    ordered: list[str] = []
    for c in candidates:
        if c and c not in seen:
            seen.add(c)
            ordered.append(c)
    return ordered


def resolve_polaris_root() -> str:
    """Return the absolute POLARIS repo root, or raise RuntimeError (FAIL LOUD)."""
    for candidate in _candidate_paths():
        if _has_markers(candidate):
            return candidate
    raise RuntimeError(
        "fetch_crawl bake-off: could not resolve the POLARIS repo root (no candidate dir "
        f"contained the seams {_ROOT_MARKERS!r}). Set POLARIS_ROOT to the real checkout, or run "
        "from inside the POLARIS tree. FAIL LOUD — never import a forked/missing seam silently."
    )


def ensure_on_syspath() -> str:
    """Resolve the POLARIS root and ensure it is importable; return the root. Idempotent."""
    root = resolve_polaris_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    return root
