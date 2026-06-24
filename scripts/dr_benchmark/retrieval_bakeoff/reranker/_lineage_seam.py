"""Resolve the ``gate0_lineage`` seam robustly.

The reranker layer REUSES ``scripts/dr_benchmark/gate0_lineage.py`` (the I-qgen-001 lineage/idx
binding seam — brief §6 GATE-0). In the merged tree it is a sibling package module and imports
plainly. In an isolated worktree cut BEFORE that file landed on main, the working copy may not
have it materialized yet (a transient environment artifact, not a code defect). This helper makes
the import resilient WITHOUT hardcoding any absolute path:

  1. Try the normal package import ``scripts.dr_benchmark.gate0_lineage``.
  2. If absent, locate the file on disk by walking up from this module to a ``scripts/dr_benchmark``
     dir, then by asking git for the repo's OTHER linked worktree paths (the main checkout shares
     the same object store and DOES carry the seam). Load it by file path via importlib.
  3. If it is genuinely nowhere, raise ImportError (fail loud) — never a silent stub.

The returned module is the real ``gate0_lineage`` with SLUG_TO_IDX, assert_drb_slug_registered,
is_benchmark_slug, GateZeroLineageError.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import subprocess
import sys
from types import ModuleType


_RELATIVE = os.path.join("scripts", "dr_benchmark", "gate0_lineage.py")


def _load_from_file(path: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location("gate0_lineage", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not build import spec for {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _candidate_paths() -> list[str]:
    paths: list[str] = []
    here = os.path.dirname(os.path.abspath(__file__))
    # Walk up looking for a co-located scripts/dr_benchmark/gate0_lineage.py.
    cur = here
    for _ in range(8):
        cand = os.path.join(cur, _RELATIVE)
        if cand not in paths:
            paths.append(cand)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    # Ask git for every linked worktree root (the main checkout carries the seam even when this
    # isolated worktree was cut before it landed). Pure read; never writes.
    try:
        out = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=here, capture_output=True, text=True, timeout=20, check=False,
        )
        for line in out.stdout.splitlines():
            if line.startswith("worktree "):
                root = line[len("worktree "):].strip()
                cand = os.path.join(root, _RELATIVE)
                if cand not in paths:
                    paths.append(cand)
    except Exception:
        pass
    return paths


def load_gate0_lineage() -> ModuleType:
    """Return the real gate0_lineage module, however the tree is laid out. Fail loud if absent."""
    try:
        return importlib.import_module("scripts.dr_benchmark.gate0_lineage")
    except Exception:
        pass
    for path in _candidate_paths():
        if os.path.isfile(path):
            return _load_from_file(path)
    raise ImportError(
        "gate0_lineage seam not found (scripts/dr_benchmark/gate0_lineage.py). It is the "
        "I-qgen-001 lineage binding the reranker layer REUSES; it must be present in the merged "
        "tree. Searched package import + every linked git worktree root."
    )


# Resolve once at import; re-export the public names so callers do a normal ``from ... import X``.
_mod = load_gate0_lineage()
SLUG_TO_IDX = _mod.SLUG_TO_IDX
GateZeroLineageError = _mod.GateZeroLineageError
assert_drb_slug_registered = _mod.assert_drb_slug_registered
is_benchmark_slug = _mod.is_benchmark_slug
