"""Backward-compat shim for the Q4 canonical rename (codex compat-by-default).

The module ``junk_deletion_gate`` was renamed to ``content_integrity_deletion_gate``
to match the content-integrity vocabulary the gate actually enforces. The old
basename is still referenced as an import target (and, per prior analysis, as a
string in some places), so the old module name MUST stay importable.

Rather than re-export a *copy* of the canonical names (which would give a
SEPARATE module namespace — a ``monkeypatch.setattr`` on this module would then
NOT be observed by ``partition_rows``, which reads its own module globals), this
shim ALIASES ``sys.modules['...junk_deletion_gate']`` to the canonical module
object. Old ``import ...junk_deletion_gate`` and
``from ...junk_deletion_gate import X`` resolve to the SAME module object and the
SAME globals dict as ``content_integrity_deletion_gate`` (codex same-object
requirement): patching ``is_row_confirmed_offtopic`` (or any predicate) on either
name is seen by ``partition_rows``.

Remove only after owner deprecation — not now.
"""
from __future__ import annotations

import sys

from src.polaris_graph.generator import content_integrity_deletion_gate as _canonical

# Alias the old module name to the canonical module object so both names share
# ONE namespace (same-object requirement for monkeypatching).
sys.modules[__name__] = _canonical
