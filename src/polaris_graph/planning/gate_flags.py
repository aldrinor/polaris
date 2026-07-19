"""Research Planning Gate feature flags (default-OFF).

One tiny module so every stage reads the gate's activation the SAME way and the
OFF path is unambiguously byte-identical. Mirrors the champion flag idiom
(``fs_researcher_enabled`` etc.): a single ``os.getenv`` read, truthy on
``{"1","true","yes","on"}``, default ``"0"`` = OFF.

``PG_GATE`` is the S2 master switch: when unset/0, the retrieval-projection
threading in ``fs_researcher_query_gen`` / ``live_retriever`` / ``run_one_query``
is inert — every ``retrieval_plan`` argument stays ``None`` and the champion path
runs unchanged. It gates ONLY whether the gate's projection is CONSULTED; it
never itself drops a source or alters faithfulness.
"""

from __future__ import annotations

import os
from src.polaris_graph.settings import resolve

_TRUTHY = ("1", "true", "yes", "on")


def gate_enabled() -> bool:
    """True iff the planning-gate retrieval projection is wired ON (default OFF)."""
    return resolve("PG_GATE").strip().lower() in _TRUTHY
