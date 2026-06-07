"""Standalone POLARIS import-root alias installer (I-ready-018 #1138, Codex C3).

Why standalone (NOT under ``polaris_graph`` / ``polaris_v6``): installing the alias must NOT itself
import the very packages it unifies (that would create the un-aliased tree before the finder is in
place — the exact divergence we prevent). This module lives directly under ``src/`` and imports
nothing from the aliased packages, so it is safe to import from both ``sitecustomize`` (interpreter
startup) and an explicit entrypoint (``run_gate_b``) before any ``polaris_graph``/``polaris_v6``
import.

PROBLEM. ``src/`` is a real package (``src/__init__.py``), so when BOTH repo-root and ``src/`` are on
``sys.path`` (V6 server ``PYTHONPATH=src`` + ``python -m`` CWD; pytest) Python builds TWO module trees
``polaris_graph.*`` / ``src.polaris_graph.*`` (and ``polaris_v6.*`` / ``src.polaris_v6.*``) with
DISTINCT class objects → pydantic ``model_type`` aborts in the generator chain + duplicate
``strict_verify`` singletons (a faithfulness hazard).

FIX. A ``MetaPathFinder`` that aliases each bare root onto its canonical ``src.`` counterpart so both
spellings are the SAME module object. CANONICAL = the ``src.``-prefixed name: the beat-both RUN
launches from repo-root WITHOUT ``src`` on ``sys.path`` (only ``src.polaris_graph`` resolves), and the
``--upload-file`` path imports ``polaris_v6`` internals via the bare root — so installing this alias
from the run entrypoint keeps those bare imports working root-only too (Codex iter-1 P1-1).

SAFETY: idempotent; fail-fast on pre-loaded divergence; re-entrancy guarded; restores the canonical
``__spec__``/``__name__``/``__path__`` so ``importlib.reload`` re-execs the real module and package
resource discovery works on first import; defers to the default machinery when the canonical root is
not importable (so a legitimate bare-only launch from outside the repo still works).
"""
from __future__ import annotations

import sys

# (alias_root, canonical_root) pairs. Both are real src/ packages imported BOTH ways across the tree.
_ALIAS_ROOTS = (
    ("polaris_graph", "src.polaris_graph"),
    ("polaris_v6", "src.polaris_v6"),
)
_FINDER_TAG = "_polaris_import_root_alias"


def install_import_root_alias() -> None:
    """Install the import-root alias MetaPathFinder (idempotent)."""
    for finder in sys.meta_path:
        if getattr(finder, "_tag", None) == _FINDER_TAG:
            return  # already installed

    import importlib
    import importlib.abc
    import importlib.machinery
    import importlib.util

    class _PolarisAliasFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
        """Alias bare ``<root>[.sub]`` → canonical ``src.<root>[.sub]`` (same module object)."""

        _tag = _FINDER_TAG

        def __init__(self) -> None:
            # Re-entrancy guard ONLY — NO threading.Lock (CPython serializes imports per-module via
            # _bootstrap._ModuleLock; holding our own lock across import_module(), which re-enters this
            # finder for the canonical module's own bare submodule imports, DEADLOCKS).
            self._in_progress: set[str] = set()
            # canonical_root -> bool importable (None = unchecked). If the canonical tree does not exist
            # (bare-only launch from outside the repo), defer to the default machinery.
            self._canon_ok: dict[str, bool] = {}

        @staticmethod
        def _split(fullname: str):
            for alias_root, canonical_root in _ALIAS_ROOTS:
                if fullname == alias_root or fullname.startswith(alias_root + "."):
                    return alias_root, canonical_root
            return None

        def _canonical_importable(self, canonical_root: str) -> bool:
            if canonical_root not in self._canon_ok:
                if canonical_root in sys.modules:
                    self._canon_ok[canonical_root] = True
                else:
                    try:
                        self._canon_ok[canonical_root] = (
                            importlib.util.find_spec(canonical_root) is not None
                        )
                    except (ImportError, ValueError, AttributeError):
                        self._canon_ok[canonical_root] = False
            return self._canon_ok[canonical_root]

        def find_spec(self, fullname, path=None, target=None):  # noqa: ARG002
            match = self._split(fullname)
            if match is None:
                return None
            alias_root, canonical_root = match
            if fullname in self._in_progress:
                return None
            if not self._canonical_importable(canonical_root):
                return None  # no canonical tree → let the default machinery resolve the bare name
            return importlib.machinery.ModuleSpec(fullname, self, origin="polaris-import-root-alias")

        def create_module(self, spec):
            alias_root, canonical_root = self._split(spec.name)
            canonical = canonical_root + spec.name[len(alias_root):]
            existing_alias = sys.modules.get(spec.name)
            existing_canon = sys.modules.get(canonical)
            if (
                existing_alias is not None
                and existing_canon is not None
                and existing_alias is not existing_canon
            ):
                raise ImportError(
                    f"polaris import-root alias divergence: {spec.name!r} and {canonical!r} are "
                    f"already loaded as DIFFERENT module objects; the alias must be installed BEFORE "
                    f"any {alias_root} import."
                )
            self._in_progress.add(spec.name)
            try:
                module = importlib.import_module(canonical)
            finally:
                self._in_progress.discard(spec.name)
            # Codex P2-3 (iter-1/2): stash the canonical spec ON the module object (NOT a name-keyed
            # dict). exec_module runs AFTER _init_module_attrs has overwritten module.__name__ to the
            # ALIAS name, so a dict keyed by either spelling is fragile; a private attr on the module is
            # unambiguous. This makes the __path__/__spec__ restore actually fire on FIRST import.
            module.__polaris_canonical_spec__ = module.__spec__
            sys.modules[spec.name] = module
            return module

        def exec_module(self, module):
            # _init_module_attrs just clobbered module.__name__/__spec__ to the alias values (no-op
            # loader). Restore the canonical ones so the module identity is real and reload() re-execs
            # the real code; restore __path__ so package resource discovery (importlib.resources/pkgutil)
            # works on FIRST import, not only after a reload.
            real_spec = module.__dict__.pop("__polaris_canonical_spec__", None)
            if real_spec is not None:
                module.__spec__ = real_spec
                module.__name__ = real_spec.name
                locations = getattr(real_spec, "submodule_search_locations", None)
                if locations is not None:
                    module.__path__ = list(locations)
            return None

    sys.meta_path.insert(0, _PolarisAliasFinder())
