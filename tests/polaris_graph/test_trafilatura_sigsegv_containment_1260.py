"""GH #1260 — contain the native libxml2/trafilatura SIGSEGV.

The hot path called `trafilatura.extract()` (and `trafilatura.extract_metadata()`)
DIRECTLY in worker threads, bypassing the subprocess guard. A libxml2
SIGSEGV/heap-corruption in any worker thread kills the whole Python process
silently (no traceback). This was a RECURRING crash class (2 of 5 live runs
died from it). This module proves the containment, OFFLINE and deterministic:

  (a) CONFORMANCE — every `trafilatura.extract(` / `trafilatura.extract_metadata(`
      CALL in `src/` goes through the ONE guarded door. An AST scan (not regex —
      the guard body, the subprocess code-string, and comments all contain the
      literal `trafilatura.extract`) asserts the only direct AST Calls live
      inside the two guard functions in access_bypass.py.

  (b) SUBPROCESS CONTAINMENT — under PG_TRAFILATURA_SUBPROCESS=1 a simulated
      child segfault (mocked subprocess returns rc=139/-11) does NOT kill the
      parent: both `safe_trafilatura_extract` and `safe_trafilatura_extract_metadata`
      return None and the caller falls back. No exception escapes.

  (c) FAULTHANDLER — the Gate-B entrypoint arms `faulthandler.enable(all_threads=True)`
      so the NEXT native crash leaves a C+Python stack instead of silence. Proven
      by spying on `faulthandler.enable` (pytest enables faulthandler by default,
      so `is_enabled()` is a fake pass — we assert the call actually happened).

All tests are offline: no network, no spend, no real libxml2 crash. The
subprocess boundary is mocked.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.tools.access_bypass as ab


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"

# The two libxml2 doors that must only be CALLED inside the guard functions.
_GUARDED_ATTRS = frozenset({"extract", "extract_metadata"})
# Functions inside access_bypass.py that are ALLOWED to call the doors directly
# (they ARE the guard / its subprocess sibling).
_GUARD_FUNCTIONS = frozenset({
    "safe_trafilatura_extract",
    "safe_trafilatura_extract_metadata",
})


# ---------------------------------------------------------------------------
# (a) AST conformance — no UNGUARDED libxml2 door anywhere in src/
# ---------------------------------------------------------------------------


def _iter_src_py_files():
    for path in sorted(SRC_ROOT.rglob("*.py")):
        yield path


def _direct_trafilatura_door_calls(tree: ast.AST):
    """Yield (call_node, enclosing_funcname) for every AST Call of the form
    `trafilatura.extract(...)` / `trafilatura.extract_metadata(...)`.

    A string literal containing `trafilatura.extract` (the subprocess code that
    runs in the child) is NOT an ast.Call → it is correctly ignored. Comments
    are stripped by the parser → ignored. Only real call expressions match."""
    # Map each node to its nearest enclosing FunctionDef name via a parent walk.
    parents: dict[int, str] = {}

    class _Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self._stack: list[str] = []

        def _visit_scope(self, node) -> None:
            self._stack.append(node.name)
            self.generic_visit(node)
            self._stack.pop()

        visit_FunctionDef = _visit_scope
        visit_AsyncFunctionDef = _visit_scope

        def visit_Call(self, node: ast.Call) -> None:
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr in _GUARDED_ATTRS
                and isinstance(func.value, ast.Name)
                and func.value.id == "trafilatura"
            ):
                parents[id(node)] = self._stack[-1] if self._stack else "<module>"
            self.generic_visit(node)

    visitor = _Visitor()
    visitor.visit(tree)
    return parents


def test_every_src_trafilatura_door_goes_through_the_guard():
    """CONFORMANCE (requirement a): the ONLY direct AST calls to
    `trafilatura.extract` / `.extract_metadata` in all of `src/` live inside the
    two guard functions in access_bypass.py. Any other call site is an
    UNGUARDED libxml2 door — a silent-SIGSEGV liability — and fails this test."""
    offenders: list[str] = []
    guard_file = (SRC_ROOT / "tools" / "access_bypass.py").resolve()

    for path in _iter_src_py_files():
        source = path.read_text(encoding="utf-8")
        if "trafilatura" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for node_id, funcname in _direct_trafilatura_door_calls(tree).items():
            is_guard_internal = (
                path.resolve() == guard_file and funcname in _GUARD_FUNCTIONS
            )
            if not is_guard_internal:
                offenders.append(f"{path.relative_to(REPO_ROOT)}::{funcname}")

    assert not offenders, (
        "UNGUARDED trafilatura libxml2 door(s) found — route through "
        "safe_trafilatura_extract / safe_trafilatura_extract_metadata:\n  "
        + "\n  ".join(offenders)
    )


def test_guard_functions_exist_and_are_the_door():
    """Both guard entrypoints exist and are callable — the test above is only
    meaningful if the guard it points callers at actually exists."""
    assert callable(ab.safe_trafilatura_extract)
    assert callable(ab.safe_trafilatura_extract_metadata)


# ---------------------------------------------------------------------------
# (b) subprocess SIGSEGV containment — both doors
# ---------------------------------------------------------------------------


@dataclass
class _CrashedProc:
    """A child that died on a SIGSEGV-class signal. -11 == POSIX SIGSEGV (exit
    139); Windows surfaces an access violation as a large positive code — both
    are `returncode != 0`, which the guard treats as contained."""
    returncode: int = -11
    stdout: str = ""
    stderr: str = ""


def test_extract_subprocess_segfault_does_not_kill_parent(monkeypatch):
    """SUBPROCESS CONTAINMENT (requirement b): a mocked child segfault (rc=-11)
    on the content door returns None — the parent survives, no exception."""
    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "1")
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CrashedProc())
    assert ab.safe_trafilatura_extract("<p>pathological</p>") is None


def test_extract_metadata_subprocess_segfault_does_not_kill_parent(monkeypatch):
    """SUBPROCESS CONTAINMENT (requirement b): a mocked child segfault (rc=-11)
    on the METADATA door returns None — the parent survives, no exception."""
    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "1")
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CrashedProc())
    assert ab.safe_trafilatura_extract_metadata("<p>pathological</p>") is None


def test_extract_metadata_subprocess_returns_fields_on_success(monkeypatch):
    """The metadata subprocess path reconstructs the four consumed fields from
    the child's JSON as a namespace exposing `.title/.author/.date/.description`
    (the live trafilatura Document cannot cross a process boundary)."""
    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "1")
    import json
    import subprocess

    child_json = json.dumps({
        "title": "A Real Title",
        "author": "Jane Doe",
        "date": "2026-01-01",
        "description": "abstract text",
    })

    @dataclass
    class _OkProc:
        returncode: int = 0
        stdout: str = child_json
        stderr: str = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _OkProc())
    meta = ab.safe_trafilatura_extract_metadata("<p>ok</p>")
    assert meta is not None
    assert meta.title == "A Real Title"
    assert meta.author == "Jane Doe"
    assert meta.date == "2026-01-01"
    assert meta.description == "abstract text"


def test_extract_metadata_subprocess_timeout_returns_none(monkeypatch):
    """A metadata subprocess timeout is contained (None), never propagated."""
    monkeypatch.setenv("PG_TRAFILATURA_SUBPROCESS", "1")
    import subprocess

    def _timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(subprocess, "run", _timeout)
    assert ab.safe_trafilatura_extract_metadata("<p>slow</p>") is None


def test_extract_metadata_skips_oversized_html(monkeypatch):
    """The metadata door shares the SAME size gate — an oversized doc bypasses
    libxml2 entirely (returns None) without ever calling trafilatura."""
    monkeypatch.setattr(ab, "_TRAFILATURA_MAX_HTML_CHARS", 1000)
    monkeypatch.delenv("PG_TRAFILATURA_SUBPROCESS", raising=False)
    import trafilatura
    called = {"n": 0}
    monkeypatch.setattr(
        trafilatura, "extract_metadata",
        lambda *a, **k: (called.__setitem__("n", called["n"] + 1) or object()),
    )
    oversized = "<p>" + ("x" * 5000) + "</p>"
    assert ab.safe_trafilatura_extract_metadata(oversized) is None
    assert called["n"] == 0, "oversized HTML must never reach libxml2"


def test_extract_metadata_in_process_never_raises(monkeypatch):
    """A Python-level metadata error returns None (BS4 fallback), never raises."""
    monkeypatch.delenv("PG_TRAFILATURA_SUBPROCESS", raising=False)
    import trafilatura

    def _boom(*a, **k):
        raise ValueError("malformed doc")

    monkeypatch.setattr(trafilatura, "extract_metadata", _boom)
    assert ab.safe_trafilatura_extract_metadata("<p>hi</p>") is None


def test_extract_metadata_in_process_returns_document(monkeypatch):
    """In-process (subprocess OFF) the metadata door returns trafilatura's own
    object unchanged when the doc is within the size gate."""
    monkeypatch.delenv("PG_TRAFILATURA_SUBPROCESS", raising=False)
    import trafilatura
    sentinel = SimpleNamespace(title="T", author="A", date="D", description="X")
    monkeypatch.setattr(trafilatura, "extract_metadata", lambda *a, **k: sentinel)
    assert ab.safe_trafilatura_extract_metadata("<p>hi</p>") is sentinel


# ---------------------------------------------------------------------------
# (c) faulthandler armed on the Gate-B entrypoint
# ---------------------------------------------------------------------------


def test_gate_b_entry_enables_faulthandler_all_threads(monkeypatch):
    """FAULTHANDLER (requirement c): the Gate-B entry helper actually calls
    `faulthandler.enable(all_threads=True)`. pytest enables faulthandler by
    default, so `is_enabled()` is a fake pass — we spy on the enable call to
    prove our code armed it (and with all_threads, so a crash in a worker
    thread also dumps its stack)."""
    import faulthandler
    import scripts.dr_benchmark.run_gate_b as gate_b

    calls: list[dict] = []
    monkeypatch.setattr(
        faulthandler, "enable",
        lambda *a, **k: calls.append({"args": a, "kwargs": k}),
    )
    gate_b.enable_faulthandler()
    assert len(calls) == 1, "Gate-B entry must arm faulthandler exactly once"
    assert calls[0]["kwargs"].get("all_threads") is True, (
        "faulthandler must be enabled with all_threads=True so a crash in a "
        "worker thread also leaves a stack"
    )


def test_gate_b_entry_faulthandler_never_blocks_run(monkeypatch):
    """If `faulthandler.enable` raises (e.g. stderr redirected to a non-fileno
    stream under a harness), the helper swallows it — diagnostics setup must
    never block the run."""
    import faulthandler
    import scripts.dr_benchmark.run_gate_b as gate_b

    def _boom(*a, **k):
        raise RuntimeError("sys.stderr has no fileno")

    monkeypatch.setattr(faulthandler, "enable", _boom)
    # Must not raise.
    gate_b.enable_faulthandler()


# ---------------------------------------------------------------------------
# (d) Gate-B pairs the subprocess flag with the trafilatura backend flag
# ---------------------------------------------------------------------------


def test_gate_b_query_env_pairs_subprocess_with_trafilatura(monkeypatch):
    """The run path turns the trafilatura BACKEND on (PG_TRAFILATURA_ENABLED=1);
    it MUST also turn the subprocess CONTAINMENT on (PG_TRAFILATURA_SUBPROCESS=1)
    — otherwise the guard is an in-process size-gate only and the libxml2
    SIGSEGV stays uncatchable on the paid run (the I-arch-005 dead-flag class).
    Asserted by SOURCE inspection (no run, no spend): PG_TRAFILATURA_ENABLED stays a
    setdefault; PG_TRAFILATURA_SUBPROCESS is now FORCE-assigned (I-arch-007 ITEM 6,
    run_gate_b.py:1632) so a stray operator =0 cannot leave containment off."""
    gate_b_src = (
        REPO_ROOT / "scripts" / "dr_benchmark" / "run_gate_b.py"
    ).read_text(encoding="utf-8")
    assert 'setdefault("PG_TRAFILATURA_ENABLED", "1")' in gate_b_src
    assert 'os.environ["PG_TRAFILATURA_SUBPROCESS"] = "1"' in gate_b_src


# ---------------------------------------------------------------------------
# (e) cosmetic — FIX-QM2 log names only the queued backends
# ---------------------------------------------------------------------------


def test_fix_qm2_log_no_longer_hardcodes_backend_triple():
    """The FIX-QM2 concurrent-fetch log must not unconditionally claim
    'Crawl4AI+Jina+Firecrawl' — it lied when PG_CRAWL4AI_ENABLED=0 or Firecrawl
    had no key. Source check: the old hardcoded string is gone and the log is
    built from the queued-backend list."""
    ab_src = (
        REPO_ROOT / "src" / "tools" / "access_bypass.py"
    ).read_text(encoding="utf-8")
    assert "Concurrent Crawl4AI+Jina+Firecrawl" not in ab_src, (
        "FIX-QM2 log still hardcodes the backend triple"
    )
    assert '"+".join(_queued_backends)' in ab_src, (
        "FIX-QM2 log must name the backends actually queued"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
