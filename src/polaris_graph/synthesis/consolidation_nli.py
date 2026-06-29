"""Consolidation-NLI winner (I-wire-001 W1, #1306) — Bidirectional-NLI grouping.

Bake-off section winner for consolidation/baskets (`state/section_winner_board.md`):
**Bidirectional-NLI (nli-deberta-v3-base)** — R=1.0/P=1.0/f1=1.0, where the literal
SHA-1/signature floor merges nothing (R=0.0). The literal `finding_dedup._finding_key`
floor only clusters rows whose extracted subject/predicate/value/unit match EXACTLY, so
two sources that PARAPHRASE the SAME claim with different surface forms (or that carry no
extractable numeric finding) get DISTINCT keys and never corroborate. This module detects
those same-claim paraphrases with a bidirectional NLI cross-encoder and UNIONS their
literal clusters into one basket, so the corroboration (count + distinct hosts) RISES.

DNA (CLAUDE.md §-1.3): this is a CONSOLIDATION / WEIGHT, never a faithfulness relaxation.
It only ever MERGES literal clusters into larger baskets (corroboration goes UP, member
hosts go UP); it never drops a row, never changes strict_verify / the NLI entailment
verifier / 4-role D8 / provenance / span-grounding (those modules are FROZEN and not
imported here). A merge can only KEEP more corroborators together — it can never relax a
verify verdict.

FAITHFULNESS-SAFE MERGE PREDICATE (bidirectional): two cluster representatives merge ONLY
when entailment is the argmax of the cross-encoder logits in BOTH directions (A entails B
AND B entails A) above a score margin. Requiring BOTH directions makes the predicate
symmetric and gives free polarity safety — an antonym pair ("raised" vs "lowered") scores
CONTRADICTION (verified in the model smoke test), so it can never falsely corroborate.

RUNTIME PARALLELISM (operator-locked, wired bounded-parallel from the start): the pairwise
NLI scores are computed bounded-parallel via a `ThreadPoolExecutor(max_workers=N)` where N
= `PG_CONSOLIDATION_NLI_WORKERS` (default 8). Grouping is a DETERMINISTIC order-independent
union-find post-step over the GATHERED score matrix — concurrency can never change the
resulting baskets (gather-then-sort by cluster index).

Pure grouping: constructs no faithfulness gate, no network LLM. The only heavy dependency
(the cross-encoder) is imported and loaded LAZILY inside `score_pairs`, so importing this
module is cheap and the legacy path that never calls it pays nothing.
"""
from __future__ import annotations

import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger("polaris_graph.consolidation_nli")

# ─────────────────────────────────────────────────────────────────────────
# Env knobs (LAW VI — zero hard-coding; all tunables are env-overridable)
# ─────────────────────────────────────────────────────────────────────────
ENV_FLAG = "PG_CONSOLIDATION_NLI"                       # default-OFF master gate
ENV_MODEL = "PG_CONSOLIDATION_NLI_MODEL"                # cross-encoder id
ENV_WORKERS = "PG_CONSOLIDATION_NLI_WORKERS"            # bounded-parallel cap
ENV_MARGIN = "PG_CONSOLIDATION_NLI_MARGIN"              # entailment-logit margin
ENV_MAX_PAIRS = "PG_CONSOLIDATION_NLI_MAX_PAIRS"        # O(n^2) safety cap
# I-deepfix-001 fix-3 (#1344): optional device placement for the cross-encoder. On
# the crammed 2-GPU split (W6 embedder + W5 reranker + W10 NLI co-resident on cuda:0)
# a CUDA OOM during load/predict used to RAISE and KILL the consolidation step (a
# §-1.3 WEIGHT, not a faithfulness gate). Unset => NO device kwarg (byte-identical
# library auto-placement). A CUDA OOM degrades to CPU (keeps MORE baskets, never dies).
ENV_DEVICE = "PG_CONSOLIDATION_NLI_DEVICE"

_DEFAULT_MODEL = "cross-encoder/nli-deberta-v3-base"
_DEFAULT_WORKERS = "8"
_DEFAULT_MARGIN = "0.0"      # entailment must be the argmax (logit > the other two)
_DEFAULT_MAX_PAIRS = "20000"
_CPU_DEVICE = "cpu"         # the OOM-degrade target

# nli-deberta-v3-base label order (verified from model.config.id2label in the smoke
# test): index 0 = contradiction, 1 = entailment, 2 = neutral.
_ENTAILMENT_IDX = 1
_CONTRADICTION_IDX = 0


def consolidation_nli_enabled() -> bool:
    """`PG_CONSOLIDATION_NLI` master gate. DEFAULT-OFF => the caller's legacy literal
    floor runs byte-identical (this module is never imported on that path). ON => the
    bidirectional-NLI consolidation runs as a post-step over the literal clusters."""
    return os.getenv(ENV_FLAG, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _read_int(env: str, default: str, *, lo: int, hi: int) -> int:
    raw = os.environ.get(env, "").strip() or default
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning("[consolidation_nli] %s=%r not an int; using %s", env, raw, default)
        return int(default)
    return max(lo, min(hi, value))


def _read_float(env: str, default: str) -> float:
    raw = os.environ.get(env, "").strip() or default
    try:
        return float(raw)
    except (ValueError, TypeError):
        logger.warning("[consolidation_nli] %s=%r not a float; using %s", env, raw, default)
        return float(default)


def _workers() -> int:
    return _read_int(ENV_WORKERS, _DEFAULT_WORKERS, lo=1, hi=64)


def _margin() -> float:
    return _read_float(ENV_MARGIN, _DEFAULT_MARGIN)


def _max_pairs() -> int:
    return _read_int(ENV_MAX_PAIRS, _DEFAULT_MAX_PAIRS, lo=1, hi=10_000_000)


def _device() -> Optional[str]:
    """Configured cross-encoder device (``PG_CONSOLIDATION_NLI_DEVICE``), or None when
    unset/blank => NO device kwarg passed (byte-identical library auto-placement)."""
    raw = os.environ.get(ENV_DEVICE, "").strip()
    return raw or None


def _is_cuda_oom(exc: BaseException) -> bool:
    """True iff ``exc`` is a CUDA out-of-memory error (the only failure the W10 winner
    DEGRADES to CPU; every other error fails loud per §-1.4). Detects both the typed
    ``torch.cuda.OutOfMemoryError`` and the generic ``RuntimeError('CUDA out of
    memory ...')`` by class name + message, so this needs no hard torch import."""
    name = type(exc).__name__
    if name in ("OutOfMemoryError", "CudaOutOfMemoryError"):
        return True
    msg = str(exc).lower()
    return "out of memory" in msg and ("cuda" in msg or "gpu" in msg)


# ─────────────────────────────────────────────────────────────────────────
# Lazy cross-encoder load (one model per process, thread-safe)
# ─────────────────────────────────────────────────────────────────────────
_MODEL_LOCK = threading.Lock()
_MODEL: Any = None
# I-deepfix-001 fix-3 (#1344): the device the resident `_MODEL` was loaded on (or None
# for library auto-placement). When a predict-time CUDA OOM forces a CPU degrade, the
# model is rebuilt on CPU and this is set to "cpu" so the rebuild happens once.
_MODEL_DEVICE: Optional[str] = None


def _construct_cross_encoder(model_id: str, device: Optional[str]) -> Any:
    """Build a `CrossEncoder` with an OPTIONAL device kwarg (lazy import). A None
    device passes NO kwarg (byte-identical library auto-placement)."""
    from sentence_transformers import CrossEncoder  # noqa: PLC0415 — lazy by design

    if device is None:
        return CrossEncoder(model_id)
    return CrossEncoder(model_id, device=device)


def _load_model(device: Optional[str] = None) -> Any:
    """Lazily load the cross-encoder ONCE per process (double-checked lock). Loading
    happens only inside the flag-ON branch (the caller already gated on the flag), so an
    environment without `sentence_transformers` only fails when the winner is actually
    activated — never on import.

    I-deepfix-001 fix-3 (#1344): honors ``PG_CONSOLIDATION_NLI_DEVICE`` (or the explicit
    ``device`` arg, used by the predict-OOM CPU degrade). On a CUDA OOM during the GPU
    load the model is RETRIED on CPU (degrade) so the consolidation winner still FIRES —
    it never raises an OOM and never loses a basket. A non-OOM load error still fails
    loud (§-1.4). The model is cached with its loaded device in ``_MODEL_DEVICE``."""
    global _MODEL, _MODEL_DEVICE
    if _MODEL is not None:
        return _MODEL
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        model_id = os.environ.get(ENV_MODEL, "").strip() or _DEFAULT_MODEL
        want_device = _device() if device is None else device
        logger.info(
            "[consolidation_nli] loading cross-encoder %s (device=%s)",
            model_id, want_device or "auto",
        )
        try:
            _MODEL = _construct_cross_encoder(model_id, want_device)
            _MODEL_DEVICE = want_device
        except Exception as exc:  # noqa: BLE001 — classify: only a CUDA OOM degrades
            if not _is_cuda_oom(exc) or want_device == _CPU_DEVICE:
                raise  # non-OOM (or already-CPU) load failure => fail loud (§-1.4)
            logger.warning(
                "[consolidation_nli] CUDA OOM loading the cross-encoder on device=%s; "
                "DEGRADING to CPU so consolidation still fires (no basket lost): %s",
                want_device, exc,
            )
            _MODEL = _construct_cross_encoder(model_id, _CPU_DEVICE)
            _MODEL_DEVICE = _CPU_DEVICE
        return _MODEL


def _reload_model_on_cpu() -> Any:
    """Drop the resident (GPU) cross-encoder and rebuild it on CPU — the predict-time
    CUDA OOM degrade. Returns the CPU model. Thread-safe (under ``_MODEL_LOCK``)."""
    global _MODEL, _MODEL_DEVICE
    with _MODEL_LOCK:
        if _MODEL is not None and _MODEL_DEVICE == _CPU_DEVICE:
            return _MODEL  # another thread already degraded
        model_id = os.environ.get(ENV_MODEL, "").strip() or _DEFAULT_MODEL
        logger.warning(
            "[consolidation_nli] CUDA OOM during predict; DEGRADING the cross-encoder "
            "to CPU and re-scoring (no basket lost)."
        )
        _MODEL = _construct_cross_encoder(model_id, _CPU_DEVICE)
        _MODEL_DEVICE = _CPU_DEVICE
        return _MODEL


def _entails(logits: Any, margin: float) -> bool:
    """True iff entailment is the strict argmax of the 3-way logits by at least `margin`.

    Pure index comparison on the model's [contradiction, entailment, neutral] logits — no
    softmax needed (argmax is monotone under softmax). Requiring entailment > BOTH others
    (by `margin`) means an antonym pair (argmax=contradiction) can never pass."""
    ent = float(logits[_ENTAILMENT_IDX])
    con = float(logits[_CONTRADICTION_IDX])
    neu = float(logits[3 - _ENTAILMENT_IDX - _CONTRADICTION_IDX])  # the remaining (neutral) idx
    return ent > con + margin and ent > neu + margin


# ─────────────────────────────────────────────────────────────────────────
# Union-find (deterministic, order-independent post-step)
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class _UnionFind:
    """Tiny union-find over [0, n). Merges to the LOWEST index so the assignment is
    fully deterministic regardless of the order edges arrive (order-independence)."""

    parent: list[int]

    @classmethod
    def of(cls, n: int) -> "_UnionFind":
        return cls(parent=list(range(n)))

    def find(self, x: int) -> int:
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path-compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra < rb else (rb, ra)
        self.parent[hi] = lo  # always attach to the lower root => deterministic


# ─────────────────────────────────────────────────────────────────────────
# Pairwise scoring (BOUNDED-parallel) + grouping (deterministic post-step)
# ─────────────────────────────────────────────────────────────────────────
def score_pairs(
    texts: list[str],
    *,
    margin: Optional[float] = None,
    workers: Optional[int] = None,
    max_pairs: Optional[int] = None,
    predict_fn: Optional[Callable[[list[tuple[str, str]]], Any]] = None,
) -> list[tuple[int, int]]:
    """Return the list of `(i, j)` cluster index pairs (i < j) that BIDIRECTIONALLY entail.

    The cross-encoder predict is invoked bounded-parallel across pair-chunks via a
    `ThreadPoolExecutor(max_workers=workers)`. Each chunk produces `(i, j, both_entail)`
    triples; results are GATHERED and then sorted by `(i, j)` so the returned edge list is
    identical for any worker count (order-independence).

    `predict_fn` is an injection seam for the fire-test (a deterministic stub that needs no
    GPU/model download); production passes None => the real lazy cross-encoder is used.
    """
    margin = _margin() if margin is None else margin
    workers = _workers() if workers is None else workers
    max_pairs = _max_pairs() if max_pairs is None else max_pairs

    n = len(texts)
    if n < 2:
        return []

    # All upper-triangle index pairs. O(n^2) is bounded by `max_pairs` (fail-loud guard):
    # a runaway cluster count must not silently scan millions of pairs on a paid run.
    pairs: list[tuple[int, int]] = [(i, j) for i in range(n) for j in range(i + 1, n)]
    if len(pairs) > max_pairs:
        raise ValueError(
            f"[consolidation_nli] {len(pairs)} candidate pairs exceeds "
            f"{ENV_MAX_PAIRS}={max_pairs}; raise the cap or pre-bucket the clusters."
        )

    # I-deepfix-001 fix-3 (#1344): track whether the predict came from the real lazy
    # cross-encoder (production) vs an injected stub (the fire-test seam). On a CUDA OOM
    # during predict, the production path RELOADS the model on CPU and re-scores (degrade,
    # no basket lost); an injected stub is simply retried (its own recovery semantics).
    _injected_predict = predict_fn is not None
    if predict_fn is None:
        model = _load_model()
        predict_fn = model.predict  # type: ignore[assignment]
    # A 1-element holder so a CPU degrade in one chunk swaps the active predict for ALL
    # subsequent chunks (the GPU model is gone; reloading per chunk would thrash).
    _predict_holder: list[Any] = [predict_fn]
    _degraded = threading.Event()

    # Chunk the pairs across the bounded worker pool. A chunk is scored with ONE batched
    # predict (both directions in the same batch), so a chunk == one model call.
    n_chunks = max(1, min(workers, len(pairs)))
    chunk_size = (len(pairs) + n_chunks - 1) // n_chunks
    chunks = [pairs[k:k + chunk_size] for k in range(0, len(pairs), chunk_size)]

    def _predict_with_oom_degrade(batch: list[tuple[str, str]]) -> Any:
        """Run the active predict; on a CUDA OOM, DEGRADE to CPU (production) or retry
        the injected stub, then re-run ONCE. A non-OOM error fails loud (§-1.4)."""
        try:
            return _predict_holder[0](batch)
        except Exception as exc:  # noqa: BLE001 — classify: only a CUDA OOM degrades
            if not _is_cuda_oom(exc):
                raise
            if _injected_predict:
                # Test/degrade seam: retry the same injected predict once.
                _degraded.set()
                return _predict_holder[0](batch)
            # Production: rebuild the cross-encoder on CPU and swap it in for this and
            # every later chunk, then re-score this batch.
            cpu_model = _reload_model_on_cpu()
            _predict_holder[0] = cpu_model.predict
            _degraded.set()
            return _predict_holder[0](batch)

    def _score_chunk(chunk: list[tuple[int, int]]) -> list[tuple[int, int]]:
        # Build BOTH directions for every pair in one batch: [A->B, B->A, ...].
        batch: list[tuple[str, str]] = []
        for i, j in chunk:
            batch.append((texts[i], texts[j]))
            batch.append((texts[j], texts[i]))
        logits = _predict_with_oom_degrade(batch)  # shape (2*len(chunk), 3)
        edges: list[tuple[int, int]] = []
        for idx, (i, j) in enumerate(chunk):
            fwd = logits[2 * idx]
            rev = logits[2 * idx + 1]
            if _entails(fwd, margin) and _entails(rev, margin):
                edges.append((i, j))
        return edges

    all_edges: list[tuple[int, int]] = []
    if workers <= 1 or len(chunks) <= 1:
        for chunk in chunks:
            all_edges.extend(_score_chunk(chunk))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for chunk_edges in pool.map(_score_chunk, chunks):
                all_edges.extend(chunk_edges)

    # DETERMINISTIC post-step: sort the gathered edges so the union-find input is
    # concurrency-invariant (the union is order-stable anyway because it attaches to the
    # lowest root, but sorting makes the contract explicit and the output reproducible).
    all_edges.sort()
    return all_edges


def group_clusters(
    cluster_texts: list[str],
    *,
    margin: Optional[float] = None,
    workers: Optional[int] = None,
    max_pairs: Optional[int] = None,
    predict_fn: Optional[Callable[[list[tuple[str, str]]], Any]] = None,
) -> dict[int, int]:
    """Bidirectional-NLI consolidation over literal clusters.

    Input: `cluster_texts[k]` = the representative text of literal cluster `k`.
    Output: a mapping `cluster_index -> merged_group_root` where same-claim paraphrase
    clusters share a root (the LOWEST member index). Clusters with no entailing partner map
    to themselves. The mapping is identical for any `workers` value (order-independent).
    """
    n = len(cluster_texts)
    uf = _UnionFind.of(n)
    edges = score_pairs(
        cluster_texts, margin=margin, workers=workers,
        max_pairs=max_pairs, predict_fn=predict_fn,
    )
    for i, j in edges:
        uf.union(i, j)
    return {k: uf.find(k) for k in range(n)}
