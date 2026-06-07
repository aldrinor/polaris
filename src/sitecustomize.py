"""Repo-root sitecustomize — POLARIS import-root unifier (I-ready-018 #1138, Codex C3).

PROBLEM. ``src/`` is a real package (``src/__init__.py`` exists). When BOTH the repo root AND
``src/`` are on ``sys.path`` — which happens in the V6 server (``PYTHONPATH=src python -m
uvicorn`` → ``src`` from PYTHONPATH + repo-root from ``python -m`` CWD) and in pytest
(``PYTHONPATH=src`` + pytest rootdir) — Python builds TWO distinct module trees,
``polaris_graph.*`` and ``src.polaris_graph.*``, with DISTINCT class objects. Because
``src/polaris_graph/clinical_generator`` mixes import prefixes (consumers + generator.py +
verified_report.py use bare ``polaris_graph``; strict_verify.py + provenance.py use
``src.polaris_graph``), a ``Section(verified_sentences=[strict_verify output])`` is built with
the bare ``VerifiedSentence`` field type but fed the ``src.`` instance → pydantic ``model_type``
ValidationError → generation aborts ``completion_backend_unavailable``. It also means duplicate
``strict_verify`` module objects → duplicate ``_JUDGE_SINGLETON`` + telemetry counters (a
faithfulness hazard).

FIX (Codex design ruling C3, .codex/I-ready-018/clusterA_design_verdict.txt). A full-prefix import
ALIAS: redirect every ``polaris_graph[.X]`` import to the canonical ``src.polaris_graph[.X]`` so both
spellings resolve to the SAME module object (and therefore one VerifiedSentence / Section /
strict_verify / one ``_JUDGE_SINGLETON``). NOT a top-level ``sys.modules`` assignment (that misses
submodules imported later) — a ``MetaPathFinder`` covering the whole prefix.

CANONICAL = ``src.polaris_graph``. Rationale: the beat-both RUN launches from the repo root WITHOUT
``src`` on ``sys.path`` (``python -m scripts.dr_benchmark.run_gate_b``), so ONLY ``src.polaris_graph``
is importable there; bare ``polaris_graph`` is not. The run therefore never triggers this finder
(it never imports the bare spelling) → the run is byte-unaffected. In the both-roots contexts the
finder collapses the bare spelling onto the ``src.`` tree.

SAFETY:
  * Idempotent: installs once (guarded by a module-global + a sys.meta_path membership check).
  * Fail-fast: if the bare AND src. spellings are ALREADY loaded as DIFFERENT objects before the
    finder can unify them, raise ImportError rather than silently leaving a split identity.
  * Re-entrancy guarded: a per-thread in-progress set prevents infinite recursion while importing
    the canonical counterpart (whose own bare imports re-enter the finder).
  * No eager imports at interpreter startup — the finder triggers lazily on the first
    ``polaris_graph`` import.
"""
from __future__ import annotations

import sys
import threading

_ALIAS_ROOT = "polaris_graph"
_CANONICAL_ROOT = "src.polaris_graph"
_FINDER_TAG = "_polaris_import_root_alias"


def _install_polaris_import_alias() -> None:
    # Idempotent: never install twice (sitecustomize can be imported more than once in odd setups).
    for finder in sys.meta_path:
        if getattr(finder, "_tag", None) == _FINDER_TAG:
            return

    import importlib
    import importlib.abc
    import importlib.machinery

    class _PolarisAliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        """Redirect ``polaris_graph[.sub]`` → the canonical ``src.polaris_graph[.sub]`` module."""

        _tag = _FINDER_TAG

        def __init__(self) -> None:
            # Re-entrancy guard ONLY (NO threading.Lock — CPython's import system already serializes
            # imports per module via _bootstrap._ModuleLock; adding our own non-reentrant lock here and
            # holding it across import_module() — which re-enters this finder for the canonical module's
            # own polaris_graph submodule imports — DEADLOCKS. The _in_progress set is sufficient.)
            self._in_progress: set[str] = set()
            # alias_name -> the canonical module's REAL ModuleSpec, captured in create_module before
            # the import system clobbers the returned module's __spec__/__name__ with the alias spec
            # (see exec_module for why this matters for importlib.reload()).
            self._real_specs: dict[str, object] = {}

        @staticmethod
        def _canonical_name(fullname: str) -> str:
            # polaris_graph -> src.polaris_graph ; polaris_graph.a.b -> src.polaris_graph.a.b
            return _CANONICAL_ROOT + fullname[len(_ALIAS_ROOT):]

        def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
            if fullname != _ALIAS_ROOT and not fullname.startswith(_ALIAS_ROOT + "."):
                return None
            # Avoid re-entrancy: while we are importing the canonical counterpart, let the default
            # machinery resolve any nested lookups for THIS exact name.
            if fullname in self._in_progress:
                return None
            return importlib.machinery.ModuleSpec(fullname, self, origin="polaris-import-root-alias")

        def create_module(self, spec):
            canonical = self._canonical_name(spec.name)
            # Fail-fast: if both spellings are already loaded as DIFFERENT objects, we cannot safely
            # unify after the fact — surface it loudly instead of papering over a split identity.
            existing_alias = sys.modules.get(spec.name)
            existing_canon = sys.modules.get(canonical)
            if (
                existing_alias is not None
                and existing_canon is not None
                and existing_alias is not existing_canon
            ):
                raise ImportError(
                    f"polaris import-root alias divergence: {spec.name!r} and {canonical!r} are "
                    f"already loaded as DIFFERENT module objects; the alias finder must be "
                    f"installed (sitecustomize) BEFORE any polaris_graph import."
                )
            self._in_progress.add(spec.name)
            try:
                module = importlib.import_module(canonical)
            finally:
                self._in_progress.discard(spec.name)
            # Capture the canonical module's REAL spec BEFORE the import machinery's _init_module_attrs
            # overwrites module.__spec__ / module.__name__ with OUR alias spec (which carries the no-op
            # alias loader). Without restoring these in exec_module, importlib.reload(bare_module) would
            # route through this finder's no-op exec_module and silently NOT re-execute the real module
            # code — e.g. test_real_completion reloads after setenv to re-read OPENROUTER_ENDPOINT.
            self._real_specs[spec.name] = module.__spec__
            # Register the canonical module object under the alias name too, so both spellings are
            # the SAME object for every future import.
            sys.modules[spec.name] = module
            return module

        def exec_module(self, module):
            # create_module already executed the canonical module. _init_module_attrs just clobbered
            # module.__name__ / module.__spec__ to the ALIAS values (name = bare spelling, loader =
            # this no-op finder). Restore the canonical spec/name so the module object's identity is
            # the real one and importlib.reload() re-execs the real module code (not our no-op). The
            # module object is shared between the bare and src. sys.modules entries, so restoring once
            # fixes both. Keyed by the alias name (module.__name__ is currently the alias name).
            real_spec = self._real_specs.pop(module.__name__, None)
            if real_spec is not None:
                module.__spec__ = real_spec
                module.__name__ = real_spec.name
            return None

    sys.meta_path.insert(0, _PolarisAliasFinder())


_install_polaris_import_alias()
