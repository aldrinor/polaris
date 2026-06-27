"""Repo/src sitecustomize — installs the POLARIS import-root alias (I-ready-018 #1138, Codex C3).

Auto-loaded by CPython's ``site`` at interpreter startup when ``src/`` is on ``sys.path`` — which is
exactly the both-roots condition that creates the dual-module-tree bug (V6 server ``PYTHONPATH=src``
+ ``python -m`` CWD; pytest). The beat-both RUN is ``src.``-only single-root and does NOT load this
(and does not need it for its core path; the ``--upload-file`` path installs the alias explicitly via
``run_gate_b``).

The actual finder lives in the standalone ``_polaris_import_alias`` module so installing it does NOT
import the very packages it unifies (chicken-and-egg). See that module for the full rationale.
"""
from __future__ import annotations

try:
    # I-wire-014 (#1336): apply the native-thread-safety clamp at interpreter startup too (the
    # earliest possible point, before any user import). Importing the standalone stdlib-only module
    # IS the clamp. Fixes the intermittent A15 re-fetch ``malloc(): ... corrupted`` native crash.
    import _polaris_native_thread_safety  # noqa: F401 — import-time side effect: applies the clamp
except Exception:  # noqa: BLE001 — sitecustomize must NEVER break interpreter startup
    pass

try:
    # ``src`` is on sys.path (this file is src/sitecustomize.py), so the standalone installer module
    # resolves as a bare top-level import WITHOUT touching polaris_graph / polaris_v6.
    import _polaris_import_alias

    _polaris_import_alias.install_import_root_alias()
except Exception:  # noqa: BLE001 — sitecustomize must NEVER break interpreter startup
    # If the installer is unavailable for any reason, fall through silently: the dual-identity bug only
    # affects the both-roots test/server contexts (caught loudly by test_import_root_alias_iready018),
    # never the single-root beat-both run.
    pass
