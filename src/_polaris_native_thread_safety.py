"""Standalone POLARIS native-thread-safety clamp (I-wire-014 #1336, native heap-corruption fix).

WHY THIS EXISTS. The A15 re-fetch phase runs the MinerU 2.5 GPU VLM PDF extractor
(``do_parse`` -> a PyTorch/HF-tokenizers forward pass; the ``Predict: N/M`` progress
bar) inside a ``run_in_executor`` worker thread. That predict runs CONCURRENTLY with
*leaked* AccessBypass fetch daemon threads — daemon workers the live_retriever timeout
abandons (``leaked_bypass_workers=N``) because they are stuck in an un-killable native
C call (libxml2/lxml parse via crawl4ai/trafilatura). Multiple native thread pools
(OpenMP / MKL / OpenBLAS under torch, the Rust tokenizers pool, libxml2) then mutate
the process glibc heap concurrently, and on an intermittent race glibc aborts the whole
process with ``malloc(): unsorted double linked list corrupted`` — a C-level crash with
NO Python traceback that kills the back-half run mid-flight (iwire014_reconfirm.log,
exact crash point: ``Predict: 0/15`` right after an M-23a Unpaywall OA-PDF swap).

THE FIX. Clamp the native math/tokenizer thread pools to single-threaded BEFORE any of
those libraries are imported (they read these env vars once, at library-init time — i.e.
the first ``import torch`` / ``import transformers`` / ``import numpy``; setting them
after that import is a SILENT no-op). Empirically validated on the VM: the same back-half
replay that crashed at ``Predict: 0/15`` clamp-free CLEARED the entire A15 re-fetch phase
(``A15 RE-FETCH complete: attempted=20 recovered=16``) with these three clamps set as
pre-Python shell env. This module makes that clamp PERMANENT + COMMITTED + reproducible
on every production entrypoint instead of an ad-hoc ssh env.

WHY STANDALONE + TOP-LEVEL UNDER ``src/`` (mirrors ``_polaris_import_alias.py``): the
clamp must run before ANY third-party native import, so it cannot itself live under a
package whose import pulls torch. It imports only the stdlib ``os`` and is safe to import
from both an explicit entrypoint (``run_gate_b`` / ``run_honest_sweep_r3`` / the replay
preflight) AND ``sitecustomize`` (interpreter startup).

FAITHFULNESS / OUTPUT INVARIANCE (the binding constraint). Thread-count clamps change
ONLY how many OS threads a native library uses internally; they do NOT change the
numerical result of a deterministic VLM forward pass, an embedder encode, an NLI score,
or a tokenizer's output. Same model + same weights + same input -> byte-identical
extracted markdown -> identical ``direct_quote`` -> identical strict_verify grounding ->
identical scores. NO faithfulness gate is touched, NO source/citation is dropped, NO
fabrication is introduced. This is a pure process-reliability fix.

LAW VI (zero hard-code): every value is ``setdefault`` — an explicit operator override in
the environment (e.g. ``OMP_NUM_THREADS=4`` set deliberately) is KEPT. The clamp only
fills the UNSET default. ``PG_NATIVE_THREAD_CLAMP=0`` disables the whole module for an
operator who wants the bare (racy) defaults back.
"""
from __future__ import annotations

import os

# The native thread-pool env knobs read at library-init time by the concurrent extractors
# in the A15 re-fetch + back-half (torch/MKL/OpenBLAS math pools, the HF-tokenizers Rust
# pool, NumPy's numexpr). All default to single-threaded — the proven anti-race clamp.
# Value "1" / "false" is the LIBRARY-NATIVE convention for "no internal threading".
_NATIVE_THREAD_CLAMP_DEFAULTS: dict[str, str] = {
    # HF tokenizers: disable the Rust parallelism pool. The single most important one —
    # tokenizers' fork-after-parallelism warning is the canonical native-race smell, and
    # MinerU's VLM tokenizer + every embedder/reranker/NLI tokenize through it.
    "TOKENIZERS_PARALLELISM": "false",
    # OpenMP runtime (libgomp/libiomp) under torch CPU ops + many C extensions.
    "OMP_NUM_THREADS": "1",
    # Intel MKL BLAS pool (torch/numpy linear algebra on Intel).
    "MKL_NUM_THREADS": "1",
    # OpenBLAS pool (torch/numpy linear algebra on the OpenBLAS build).
    "OPENBLAS_NUM_THREADS": "1",
    # NumExpr pool (pandas/numpy fast-eval).
    "NUMEXPR_NUM_THREADS": "1",
}


def apply_native_thread_safety_clamp() -> None:
    """Set the native-thread-pool clamp env vars (``setdefault``) BEFORE any native import.

    Idempotent. ``setdefault`` keeps an explicit operator override (LAW VI). Disabled
    entirely by ``PG_NATIVE_THREAD_CLAMP=0``. Never raises — a clamp failure must never
    block a run (it would only re-expose the race, not corrupt output)."""
    try:
        if os.environ.get("PG_NATIVE_THREAD_CLAMP", "1").strip().lower() in {"0", "false", "no"}:
            return
        for _name, _value in _NATIVE_THREAD_CLAMP_DEFAULTS.items():
            os.environ.setdefault(_name, _value)
    except Exception:  # noqa: BLE001 — a clamp setup error must never abort the run
        pass


# Apply on import: the entrypoints import this module as their FIRST statement (before any
# torch/transformers/mineru import), so importing it IS the clamp. ``sitecustomize`` also
# calls ``apply_native_thread_safety_clamp()`` for the interpreter-startup path.
apply_native_thread_safety_clamp()
