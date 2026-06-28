"""I-deepfix-001 P0-2/P0-3 (2026-06-28) — offline proofs for the three fixes
owned by the reranker/evidence-selector/nli-verifier file-owner agent.

Offline only: no GPU, no network, no real model load. torch / transformers /
sentence-transformers / faithlens are never imported — the device knobs are pure
launch-env reads and the retryable cache is exercised by monkeypatching the
embedder LOADER, so we assert WIRING, not model behavior.

Proves:
  P0-3a  `qwen_reranker_scorer._resolve_device` honors the new `PG_RERANKER_DEVICE`
         launch-env knob with the correct precedence: explicit arg > env > torch
         auto. (The W7 production path pre-resolves env>cfg.device in
         evidence_selector, but this is the cleanest GPU-free test surface and is
         defense for direct callers.)
  P0-3b  `nli_verifier._load_faithlens` passes `PG_NLI_DEVICE` (default "cuda:0")
         to FaithLensInfer instead of the prior hardcoded "cuda:0".
  P0-2   `evidence_selector._get_semantic_embedder` is RETRYABLE: a TRANSIENT
         `_load_embedder()` None return is retried on the next call (and clears
         on a later success) rather than permanently caching `False`; a STRUCTURAL
         import failure caches `False` immediately (no retry); and after the
         `PG_SEMANTIC_EMBEDDER_MAX_LOAD_RETRIES` bound of consecutive transient
         Nones it stops retrying (caches False) to avoid thrashing the heavy load.
"""
from __future__ import annotations

import asyncio
import sys
import types


# ---------------------------------------------------------------------------
# P0-3a — PG_RERANKER_DEVICE honored in qwen_reranker_scorer._resolve_device.
# ---------------------------------------------------------------------------

def test_resolve_device_explicit_arg_wins_over_env(monkeypatch) -> None:
    """An explicit device arg must win over PG_RERANKER_DEVICE (production W7 path
    pre-resolves env>cfg.device and passes the result here — env must NOT override
    an already-chosen device)."""
    from src.polaris_graph.retrieval import qwen_reranker_scorer as qrs

    monkeypatch.setenv("PG_RERANKER_DEVICE", "cuda:1")
    assert qrs._resolve_device("cpu") == "cpu"


def test_resolve_device_reads_env_when_arg_none(monkeypatch) -> None:
    """When no explicit device is passed, PG_RERANKER_DEVICE is honored (no torch
    import needed — the env read short-circuits before the lazy torch import)."""
    from src.polaris_graph.retrieval import qwen_reranker_scorer as qrs

    monkeypatch.setenv("PG_RERANKER_DEVICE", "cuda:1")
    assert qrs._resolve_device(None) == "cuda:1"


def test_resolve_device_env_blank_is_ignored(monkeypatch) -> None:
    """A blank / whitespace PG_RERANKER_DEVICE must be ignored (falls through to
    the torch auto-resolve, not returned as a literal empty/whitespace device)."""
    from src.polaris_graph.retrieval import qwen_reranker_scorer as qrs

    monkeypatch.setenv("PG_RERANKER_DEVICE", "   ")

    # Stub torch so the test never needs a GPU / a real torch install.
    fake_torch = types.ModuleType("torch")
    fake_torch.cuda = types.SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    assert qrs._resolve_device(None) == "cpu"


# ---------------------------------------------------------------------------
# P0-3b — PG_NLI_DEVICE honored in nli_verifier._load_faithlens.
# ---------------------------------------------------------------------------

class _RecordingFaithLensInfer:
    """Stand-in FaithLensInfer that records the device kwarg it was built with."""

    last_device = None

    def __init__(self, model_name=None, device=None):
        type(self).last_device = device


def _install_fake_faithlens(monkeypatch) -> None:
    """Make `from faithlens.inference import FaithLensInfer` yield the recorder."""
    pkg = types.ModuleType("faithlens")
    inference = types.ModuleType("faithlens.inference")
    inference.FaithLensInfer = _RecordingFaithLensInfer
    pkg.inference = inference
    monkeypatch.setitem(sys.modules, "faithlens", pkg)
    monkeypatch.setitem(sys.modules, "faithlens.inference", inference)


def _reset_faithlens_singleton() -> None:
    import src.polaris_graph.agents.nli_verifier as nli
    nli._faithlens_scorer = None


def test_load_faithlens_passes_env_device(monkeypatch) -> None:
    import src.polaris_graph.agents.nli_verifier as nli

    _reset_faithlens_singleton()
    _RecordingFaithLensInfer.last_device = None
    _install_fake_faithlens(monkeypatch)
    monkeypatch.setenv("PG_NLI_DEVICE", "cuda:1")

    result = asyncio.run(nli._load_faithlens())
    assert isinstance(result, _RecordingFaithLensInfer)
    assert _RecordingFaithLensInfer.last_device == "cuda:1", (
        "PG_NLI_DEVICE was not threaded through to FaithLensInfer(device=...)"
    )
    _reset_faithlens_singleton()


def test_load_faithlens_defaults_to_cuda0_when_unset(monkeypatch) -> None:
    import src.polaris_graph.agents.nli_verifier as nli

    _reset_faithlens_singleton()
    _RecordingFaithLensInfer.last_device = None
    _install_fake_faithlens(monkeypatch)
    monkeypatch.delenv("PG_NLI_DEVICE", raising=False)

    result = asyncio.run(nli._load_faithlens())
    assert isinstance(result, _RecordingFaithLensInfer)
    assert _RecordingFaithLensInfer.last_device == "cuda:0", (
        "default device must remain cuda:0 (unchanged behavior when PG_NLI_DEVICE "
        "is unset)"
    )
    _reset_faithlens_singleton()


# ---------------------------------------------------------------------------
# P0-2 — retryable semantic-embedder cache in evidence_selector.
# ---------------------------------------------------------------------------

def _reset_embedder_cache() -> None:
    import src.polaris_graph.retrieval.evidence_selector as es
    es._SEMANTIC_EMBEDDER_CACHE = None
    es._SEMANTIC_EMBEDDER_TRANSIENT_FAILS = 0


def test_embedder_transient_none_is_retried_then_succeeds(monkeypatch) -> None:
    """A first TRANSIENT None (e.g. a GPU OOM/race) must NOT permanently dark the
    embedder: the next call retries the load and, on success, caches the real
    handle. This is the deepfix darkness the retryable cache prevents."""
    import src.polaris_graph.retrieval.evidence_selector as es

    _reset_embedder_cache()
    monkeypatch.setenv("PG_SEMANTIC_EMBEDDER_MAX_LOAD_RETRIES", "3")

    sentinel = object()
    calls = {"n": 0}

    def _fake_load_embedder():
        calls["n"] += 1
        return None if calls["n"] == 1 else sentinel

    # Patch the symbol on the module that `_get_semantic_embedder` imports from.
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf
    monkeypatch.setattr(pf, "_load_embedder", _fake_load_embedder)

    # First call: transient None -> caller-facing None, NOT cached as False.
    assert es._get_semantic_embedder() is None
    assert es._SEMANTIC_EMBEDDER_CACHE is None, (
        "a transient None must not be cached as False (would dark the run)"
    )
    # Second call: retried -> real handle cached.
    assert es._get_semantic_embedder() is sentinel
    assert es._SEMANTIC_EMBEDDER_CACHE is sentinel
    assert es._SEMANTIC_EMBEDDER_TRANSIENT_FAILS == 0, (
        "the transient-fail counter must reset on a successful load"
    )
    # Third call: served from cache, no extra load.
    assert es._get_semantic_embedder() is sentinel
    assert calls["n"] == 2, "the cached handle must not trigger a re-load"
    _reset_embedder_cache()


def test_embedder_structural_import_failure_caches_false_no_retry(monkeypatch) -> None:
    """A STRUCTURAL import failure (the import of `_load_embedder` raises) caches
    False immediately and is never retried — retrying cannot resolve a missing
    module/symbol."""
    import src.polaris_graph.retrieval.evidence_selector as es

    _reset_embedder_cache()

    # Make the import inside _get_semantic_embedder raise. We do this by removing
    # the attribute access target via a fake module that raises on attribute use:
    real_pf = sys.modules.get("src.polaris_graph.retrieval.prefetch_offtopic_filter")

    class _RaisingModule(types.ModuleType):
        def __getattr__(self, name):
            raise ImportError(f"structural: cannot import {name}")

    monkeypatch.setitem(
        sys.modules,
        "src.polaris_graph.retrieval.prefetch_offtopic_filter",
        _RaisingModule("src.polaris_graph.retrieval.prefetch_offtopic_filter"),
    )

    assert es._get_semantic_embedder() is None
    assert es._SEMANTIC_EMBEDDER_CACHE is False, (
        "a structural import failure must cache False (no retry)"
    )
    # A subsequent call returns None from the cached-False without re-importing.
    assert es._get_semantic_embedder() is None
    assert es._SEMANTIC_EMBEDDER_CACHE is False

    # Restore for hygiene (monkeypatch also restores on teardown).
    if real_pf is not None:
        sys.modules["src.polaris_graph.retrieval.prefetch_offtopic_filter"] = real_pf
    _reset_embedder_cache()


def test_embedder_transient_bound_caches_false_to_stop_thrash(monkeypatch) -> None:
    """After PG_SEMANTIC_EMBEDDER_MAX_LOAD_RETRIES consecutive transient Nones the
    cache flips to False so a genuinely-persistent failure stops re-reading the
    ~16GB model every section (§8.4 resource discipline)."""
    import src.polaris_graph.retrieval.evidence_selector as es

    _reset_embedder_cache()
    monkeypatch.setenv("PG_SEMANTIC_EMBEDDER_MAX_LOAD_RETRIES", "2")

    calls = {"n": 0}

    def _always_none():
        calls["n"] += 1
        return None

    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf
    monkeypatch.setattr(pf, "_load_embedder", _always_none)

    # Attempt 1 of 2: transient, still retryable.
    assert es._get_semantic_embedder() is None
    assert es._SEMANTIC_EMBEDDER_CACHE is None
    # Attempt 2 of 2: hits the bound -> caches False.
    assert es._get_semantic_embedder() is None
    assert es._SEMANTIC_EMBEDDER_CACHE is False
    # Further calls do NOT re-load (the bound stopped the thrash).
    assert es._get_semantic_embedder() is None
    assert calls["n"] == 2, (
        "the load must not be retried once the transient bound flips the cache to "
        "False"
    )
    _reset_embedder_cache()


# ---------------------------------------------------------------------------
# P1-1 — W7 selection-reranker STRUCTURAL load-failure telemetry (gate input).
# ---------------------------------------------------------------------------

def _reset_w7_signal() -> None:
    import src.polaris_graph.retrieval.evidence_selector as es
    es._W7_RERANKER_LOAD_FAILED = None


def _rows(n: int) -> list:
    return [{"statement": f"s{i}", "direct_quote": f"q{i}"} for i in range(n)]


def test_w7_structural_load_failure_marks_dark(monkeypatch) -> None:
    """A STRUCTURAL load failure (the scorer raises the typed RerankerLoadError for
    an import / from_pretrained / .to(device) / token-id failure) must flip the module
    W7 structural-dark signal to True so winner_firing_gate can hard-gate W7. The
    rerank still falls back LOUDLY to the input order (no drop)."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.qwen_reranker_scorer as qrs

    _reset_w7_signal()
    monkeypatch.setenv("PG_RERANKER_MODEL", "qwen3")

    def _boom_load(*_a, **_k):
        raise qrs.RerankerLoadError(
            "W7 reranker structural load failed: CUDA out of memory"
        )

    monkeypatch.setattr(qrs, "score_query_document_relevance", _boom_load)

    rows = _rows(3)
    out = es._maybe_rerank_selection(rows, "does X help Y")
    assert out == rows, "a load failure must fall back to the original order (no drop)"
    assert es._W7_RERANKER_LOAD_FAILED is True, (
        "a structural W7 load failure must mark the gate signal dark"
    )
    _reset_w7_signal()


def test_w7_transient_forward_pass_failure_does_not_mark_dark(monkeypatch) -> None:
    """A FORWARD-PASS exception (a plain, non-typed error — the model DID load) is a
    transient and must NOT flip the sticky structural signal. This is the false-hold
    guard: a one-off encode/OOM on query N must not poison the gate for query N+1 in
    the long-lived console server (winner_firing_gate: 'never a single transient
    encode exception')."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.qwen_reranker_scorer as qrs

    _reset_w7_signal()
    monkeypatch.setenv("PG_RERANKER_MODEL", "qwen3")

    def _boom_forward(*_a, **_k):
        raise RuntimeError("transient forward-pass OOM (model already loaded)")

    monkeypatch.setattr(qrs, "score_query_document_relevance", _boom_forward)

    rows = _rows(3)
    out = es._maybe_rerank_selection(rows, "does X help Y")
    assert out == rows, "a transient failure must fall back to the original order (no drop)"
    assert es._W7_RERANKER_LOAD_FAILED is None, (
        "a transient forward-pass error must NOT flip the sticky structural signal"
    )
    _reset_w7_signal()


def test_w7_successful_load_marks_not_dark(monkeypatch) -> None:
    """A successful load+score proves W7 fired => the signal is False (not dark)."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.qwen_reranker_scorer as qrs

    _reset_w7_signal()
    monkeypatch.setenv("PG_RERANKER_MODEL", "qwen3")

    # DESC by score: return descending scores so the reorder is a real permutation.
    def _ok(query, documents, **_k):
        return [float(len(documents) - i) for i in range(len(documents))]

    monkeypatch.setattr(qrs, "score_query_document_relevance", _ok)

    out = es._maybe_rerank_selection(_rows(3), "does X help Y")
    assert len(out) == 3
    assert es._W7_RERANKER_LOAD_FAILED is False, (
        "a successful rerank must mark the W7 signal not-dark"
    )
    _reset_w7_signal()


def test_w7_disabled_leaves_signal_untouched(monkeypatch) -> None:
    """OFF path (PG_RERANKER_MODEL unset): identity no-op, the signal stays None."""
    import src.polaris_graph.retrieval.evidence_selector as es

    _reset_w7_signal()
    monkeypatch.delenv("PG_RERANKER_MODEL", raising=False)
    rows = _rows(3)
    out = es._maybe_rerank_selection(rows, "q")
    assert out is rows
    assert es._W7_RERANKER_LOAD_FAILED is None, (
        "the OFF path must not touch the W7 structural signal"
    )
    _reset_w7_signal()
