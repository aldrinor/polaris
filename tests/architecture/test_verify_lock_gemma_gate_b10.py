"""B10 (2026-06-14) — verify_lock gemma conformance gate.

Asserts the AST-based gate:
  - PASSES on the real post-fix tree (no live src/ gemma default), and
  - DETECTS a forbidden google/gemma* getenv default + a mis-pointed
    PG_EVALUATOR_MODEL default, while
  - does NOT false-positive on cost-table dict literals, family-registry dict
    literals, or comments/docstrings containing "google/gemma".
"""

from __future__ import annotations

import ast

import pytest

import importlib.util
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_VL_PATH = _REPO_ROOT / "scripts" / "architecture" / "verify_lock.py"

_spec = importlib.util.spec_from_file_location("polaris_verify_lock_b10", _VL_PATH)
verify_lock = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(verify_lock)  # type: ignore[union-attr]


def test_real_tree_has_no_gemma_default():
    """The live worktree (with transparency.py + llm_provider.py fixed) is clean."""
    violations = verify_lock.scan_gemma_defaults()
    assert violations == [], f"unexpected gemma defaults: {violations}"


def test_gemma_gate_returns_zero_on_clean_tree():
    import io

    buf = io.StringIO()
    rc = verify_lock.gemma_gate(stream=buf)
    assert rc == 0
    assert "OK" in buf.getvalue()


# --- Unit tests of the AST detector on hand-built snippets (no filesystem) -----

def _detect(src: str) -> list[tuple[str | None, str | None]]:
    """Run _getenv_default_literal over every Call in ``src``."""
    tree = ast.parse(src)
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            env, default = verify_lock._getenv_default_literal(node)
            if default is not None:
                found.append((env, default))
    return found


def test_detects_getenv_gemma_default():
    found = _detect('import os\nx = os.getenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")\n')
    assert ("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it") in found


def test_detects_environ_get_gemma_default():
    found = _detect('import os\nx = os.environ.get("PG_X", "google/gemma-2-9b")\n')
    assert ("PG_X", "google/gemma-2-9b") in found


def test_ignores_cost_table_dict_literal():
    """A dict literal mapping a gemma slug to a price tuple is NOT a getenv call."""
    found = _detect('PRICES = {"google/gemma-4-31b-it": (0.13, 0.38), "google/gemma": (0.05, 0.30)}\n')
    assert found == []


def test_ignores_family_registry_dict_literal():
    found = _detect('FAM = {"gemma": ("google/gemma", "google/gemma-", "gemma/")}\n')
    assert found == []


def test_ignores_comment_and_docstring():
    src = (
        '# default: google/gemma-4-31b-it\n'
        '"""Uses PG_EVALUATOR_MODEL (default google/gemma-4-31b-it)."""\n'
        'import os\n'
        'x = os.getenv("PG_OK", "z-ai/glm-5.1")\n'
    )
    found = _detect(src)
    # only the real getenv (glm) is seen; the gemma comment/docstring are not Calls
    assert ("PG_OK", "z-ai/glm-5.1") in found
    assert all("gemma" not in (d or "") for _, d in found)


def test_getenv_without_default_is_not_flagged():
    """os.getenv('X') (no default) and the 'or'-chained pattern have no literal default."""
    found = _detect('import os\nx = os.getenv("PG_EVALUATOR_MODEL") or "z-ai/glm-5.1"\n')
    assert found == []


def test_detects_keyword_default_gemma(monkeypatch, tmp_path):
    """Codex B10 iter-1 P2: a `default=` KEYWORD gemma slug must not bypass the gate."""
    found = _detect('import os\nx = os.getenv("PG_EVALUATOR_MODEL", default="google/gemma-4-31b-it")\n')
    assert ("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it") in found
