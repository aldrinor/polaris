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
import math
import os
import re
import threading
import time
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    wait as futures_wait,
)
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
# I-deepfix-001 W04-consolidation-nli-wall (#1344): a TOTAL wall-clock deadline for the
# whole score_pairs scoring loop. The bounded-parallel pool.map blocks until EVERY chunk
# finishes — on a slow/contended/CPU-degraded cross-encoder (the post-OOM CPU re-score
# pins the rest of the run), this had NO time bound (the MAX_PAIRS cap bounds COUNT, not
# wall-clock), and the prose path runs it ONCE PER SECTION. When the deadline passes we
# STOP collecting further edges and return the edges gathered so far. §-1.3: a partial
# edge set only UNDER-merges => keeps MORE/equal baskets, never drops a corroborator.
# Consolidation is a WEIGHT, not a faithfulness gate. Default generous; <= 0 disables.
ENV_WALL_SECONDS = "PG_CONSOLIDATION_NLI_WALL_SECONDS"
# I-deepfix-001 fix-3 (#1344): optional device placement for the cross-encoder. On
# the crammed 2-GPU split (W6 embedder + W5 reranker + W10 NLI co-resident on cuda:0)
# a CUDA OOM during load/predict used to RAISE and KILL the consolidation step (a
# §-1.3 WEIGHT, not a faithfulness gate). Unset => NO device kwarg (byte-identical
# library auto-placement). A CUDA OOM degrades to CPU (keeps MORE baskets, never dies).
ENV_DEVICE = "PG_CONSOLIDATION_NLI_DEVICE"
# I-deepfix-001 (#1344): cap the index-pairs scored in ONE cross-encoder `.predict`
# forward, INDEPENDENT of the worker count. The old chunk_size = ceil(pairs/min(workers,
# pairs)) grew UNBOUNDED with corpus size (~2500 pairs -> a ~5000-tuple forward), which
# OOM'd the crammed card on the 890+-source clinical corpora (the CUBLAS_STATUS_ALLOC_FAILED
# crash). Bounding the forward keeps peak GPU memory constant regardless of corpus size.
ENV_PREDICT_CHUNK = "PG_CONSOLIDATION_NLI_PREDICT_CHUNK"
# I-deepfix-001 W04-prebucket (#1369): over-MAX_PAIRS PRE-BUCKETING. The drb_72 live run
# fed 311- and 351-text buckets into `score_pairs` (48,205 / 61,425 candidate pairs >
# the 20,000 cap), so the whole bucket's NLI consolidation was SKIPPED — near-duplicate
# findings stayed UNMERGED and rendered as REPEATED separate findings. A blind cap raise
# would re-open the O(n^2) compute/memory blowup the cap guards. Instead, when this flag
# is ON, an over-cap bucket is SUB-DIVIDED into lexical-overlap sub-buckets whose
# per-sub-bucket pair count stays <= the cap, and the NLI consolidation RUNS within each
# sub-bucket. §-1.3 CONSOLIDATE-keep-all: near-dups that share a sub-bucket MERGE
# (citations kept on the survivor basket by the callers' keep-all member union); a
# cross-sub-bucket near-dup pair is simply never scored => stays UNMERGED, which is a
# KEEP — worst case equals the current skip behavior, never worse; NOTHING is dropped.
# DEFAULT-OFF => the over-cap skip runs byte-identical (this is a build/validation
# scaffold flag per the activate+archive discipline; the run slates flip it ON).
ENV_SUBBUCKET = "PG_CONSOLIDATION_NLI_SUBBUCKET"
# Content-word Jaccard threshold for routing a text into an existing sub-bucket (the
# similarity key that keeps near-duplicates together). LAW VI env-tunable.
ENV_SUBBUCKET_JACCARD = "PG_CONSOLIDATION_NLI_SUBBUCKET_JACCARD"

_DEFAULT_MODEL = "cross-encoder/nli-deberta-v3-base"
_DEFAULT_WORKERS = "8"
_DEFAULT_MARGIN = "0.0"      # entailment must be the argmax (logit > the other two)
# S2/S3 re-pass P1-4: raised 20000 -> 60000 so the qualitative/numeric NLI NOMINATION is not
# starved on a large drb_72-scale section (the pre-bucket route + wall still bound wall-clock;
# MAX_PAIRS only bounds the per-call pair COUNT). Fully env-overridable (LAW VI).
_DEFAULT_MAX_PAIRS = "60000"
# I-deepfix-001 C2 (#1344): raised 90 -> 180. The prose path runs score_pairs ONCE PER
# SECTION; on a large corpus (890+ sources) with a CPU-degraded cross-encoder the 90s wall
# STARVED the consolidation — it truncated mid-scoring and UNDER-merged, dropping real
# corroboration weight (a §-1.3 loss of keep-all corroborators from the basket). A more
# generous default lets a large section's paraphrase clusters fully union before the wall.
# Still a WEIGHT, not a faithfulness gate; still fully env-overridable (LAW VI); <=0 disables.
_DEFAULT_WALL_SECONDS = "180"   # I-deepfix-001 C2: per-call score_pairs total wall (s)
_DEFAULT_PREDICT_CHUNK = "256"  # I-deepfix-001 #1344: max index-pairs per `.predict` forward
_DEFAULT_SUBBUCKET_JACCARD = "0.30"  # I-deepfix-001 W04-prebucket (#1369): routing threshold
_CPU_DEVICE = "cpu"         # the OOM-degrade target

# nli-deberta-v3-base label order (verified from model.config.id2label in the smoke
# test): index 0 = contradiction, 1 = entailment, 2 = neutral. These are the
# FALLBACK indices when a model exposes no id2label; the real indices are RESOLVED
# from the loaded model's config by ``_resolve_label_indices`` (I-deepfix-001 L4).
_DEFAULT_ENTAILMENT_IDX = 1
_DEFAULT_CONTRADICTION_IDX = 0
_ENTAILMENT_IDX = _DEFAULT_ENTAILMENT_IDX
_CONTRADICTION_IDX = _DEFAULT_CONTRADICTION_IDX

# I-deepfix-001 L4 (#1344): MULTILINGUAL NLI.
#
# The consolidation entailment leg is a WEIGHT (it only merges paraphrase baskets;
# it never drops a source or touches the faithfulness gate), so the model is fully
# env-overridable via ``PG_CONSOLIDATION_NLI_MODEL`` (LAW VI). The English default
# above under-entails a cross-lingual paraphrase — a native-language claim and its
# supporting span in another language would NOT be recognised as corroborating, so
# their baskets stay split and the corroboration weight is lost.
#
# To retrieve/consolidate in the task language, point ``PG_CONSOLIDATION_NLI_MODEL``
# at a MULTILINGUAL cross-encoder — recommended:
#     MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7
# whose 3-way label order differs from the English default. The old code hardcoded
# index 0=contradiction / 1=entailment, so swapping the model would have SILENTLY
# mis-read the logits (a correctness bug). ``_resolve_label_indices`` now reads the
# entailment / contradiction indices from the LOADED model's ``config.id2label`` so
# ANY 3-way NLI model plugs in correctly. Engine-neutral for basket weighting; it
# only makes the multilingual model usable, never relaxes a gate.


def _resolve_label_indices(model: Any) -> None:
    """Set ``_ENTAILMENT_IDX`` / ``_CONTRADICTION_IDX`` from ``model``'s label map.

    Reads a 3-way ``id2label`` (via ``model.config`` or ``model.model.config``) and
    finds the index whose label contains "entail" and the one containing
    "contradict". Only overrides the module defaults when BOTH are found, distinct,
    and the map is exactly 3-way; otherwise the defaults stand (fail-safe: an
    unreadable config keeps the verified nli-deberta order). Idempotent — safe to
    call on every load."""
    global _ENTAILMENT_IDX, _CONTRADICTION_IDX
    try:
        config = getattr(model, "config", None) or getattr(
            getattr(model, "model", None), "config", None
        )
        id2label = getattr(config, "id2label", None)
        if not id2label:
            return
        norm = {int(k): str(v).strip().lower() for k, v in id2label.items()}
        if len(norm) != 3:
            return
        ent = next((i for i, lab in norm.items() if "entail" in lab), None)
        con = next((i for i, lab in norm.items() if "contradict" in lab), None)
        if ent is None or con is None or ent == con:
            return
        _ENTAILMENT_IDX = ent
        _CONTRADICTION_IDX = con
    except Exception:  # noqa: BLE001 — a bad config never breaks scoring; keep defaults
        return


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


def _predict_chunk() -> int:
    """I-deepfix-001 (#1344): the max index-pairs scored in ONE cross-encoder `.predict`
    forward. Caps peak GPU memory INDEPENDENT of corpus size (the old chunk grew unbounded
    and OOM'd the clinical corpora). The grouping is an order-independent union-find over
    the gathered edges, so smaller forwards are byte-identical to the verdict (only
    WHERE-in-a-batch a pair sits, never WHICH pairs are compared or the entailment margin).
    ``<= 0`` disables the cap (unbounded, the byte-identical legacy behaviour). Default 256."""
    return _read_int(ENV_PREDICT_CHUNK, _DEFAULT_PREDICT_CHUNK, lo=0, hi=1_000_000)


def _wall_seconds() -> float:
    """I-deepfix-001 W04 (#1344): the total score_pairs wall in seconds. ``<= 0`` (or a
    non-finite value) disables the wall => the loop blocks unbounded exactly as before
    (the escape hatch). Default 180s (C2 raised it from 90 to stop starving large
    sections mid-scoring)."""
    raw = os.environ.get(ENV_WALL_SECONDS, "").strip() or _DEFAULT_WALL_SECONDS
    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[consolidation_nli] %s=%r not a float; using %s",
            ENV_WALL_SECONDS, raw, _DEFAULT_WALL_SECONDS,
        )
        return float(_DEFAULT_WALL_SECONDS)
    import math as _math
    if not _math.isfinite(value) or value <= 0:
        return 0.0
    return value


def _device() -> Optional[str]:
    """Configured cross-encoder device (``PG_CONSOLIDATION_NLI_DEVICE``), or None when
    unset/blank => NO device kwarg passed (byte-identical library auto-placement)."""
    raw = os.environ.get(ENV_DEVICE, "").strip()
    return raw or None


# ─────────────────────────────────────────────────────────────────────────
# Over-cap PRE-BUCKETING — I-deepfix-001 W04-prebucket (#1369)
# ─────────────────────────────────────────────────────────────────────────
_SUBBUCKET_WORD_RE = re.compile(r"[a-z0-9]+")
# Minimal English glue words excluded from the routing signature. Words shorter than
# 3 chars ("a"/"is"/"of"/"to"/"in"...) are already dropped by the length floor below.
# Over-inclusion here only splits sub-buckets finer (an under-merge, §-1.3-safe);
# under-inclusion only wastes a few bounded NLI pairs — neither direction is unsafe.
_SUBBUCKET_STOPWORDS = frozenset(
    "the and for with that this from are was were has have had its their them they "
    "not but into over under between among also been being can may will would could "
    "should than then when where which while who whom whose what how why all any "
    "each more most other some such only own same very just both few nor too".split()
)


def _subbucket_enabled() -> bool:
    """``PG_CONSOLIDATION_NLI_SUBBUCKET`` gate for the over-cap pre-bucketing path.
    DEFAULT-OFF => the over-cap SKIP runs byte-identical (whole bucket passes through
    unmerged, exactly the current behavior)."""
    return os.getenv(ENV_SUBBUCKET, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _subbucket_jaccard() -> float:
    """Content-word Jaccard threshold for routing a text into an existing sub-bucket
    (default 0.30). Out-of-range / malformed => default (logged, never raised — a typo
    must not crash a paid run)."""
    value = _read_float(ENV_SUBBUCKET_JACCARD, _DEFAULT_SUBBUCKET_JACCARD)
    if not (0.0 < value <= 1.0):
        logger.warning(
            "[consolidation_nli] %s=%s out of (0,1]; using default %s",
            ENV_SUBBUCKET_JACCARD, value, _DEFAULT_SUBBUCKET_JACCARD,
        )
        return float(_DEFAULT_SUBBUCKET_JACCARD)
    return value


def _subbucket_tokens(text: str) -> frozenset[str]:
    """Deterministic content-word routing signature: lowercased alnum words of >= 3
    chars minus the glue-word set. Self-contained on purpose — consolidation_nli must
    stay dependency-light because BOTH dedup modules lazily import THIS module (a
    fact_dedup import here would risk an import cycle)."""
    words = _SUBBUCKET_WORD_RE.findall((text or "").lower())
    return frozenset(w for w in words if len(w) >= 3 and w not in _SUBBUCKET_STOPWORDS)


def _max_subbucket_size(max_pairs: int) -> int:
    """Largest ``k`` with ``k*(k-1)/2 <= max_pairs`` (floored at 2 so one pair can
    always be scored). This is the per-sub-bucket SIZE cap that keeps every
    sub-bucket's pairwise count under the O(n^2) guard."""
    k = int((1.0 + math.sqrt(1.0 + 8.0 * float(max_pairs))) / 2.0)
    while k > 2 and (k * (k - 1)) // 2 > max_pairs:
        k -= 1  # float-precision guard: never let rounding exceed the cap
    return max(2, k)


def _pre_bucket_indices(texts: list[str], max_pairs: int) -> list[list[int]]:
    """Partition ``range(len(texts))`` into similarity-keyed SUB-BUCKETS, each small
    enough that its pairwise count stays <= ``max_pairs``.

    Greedy single-pass over the input order (deterministic, order-stable): each text
    joins the best-Jaccard existing sub-bucket (vs. the sub-bucket's FIRST member's
    token signature) that is (a) below the size cap and (b) at/above the routing
    threshold; ties keep the earliest bucket; otherwise it OPENS a new sub-bucket.
    Near-duplicate findings share most content words, so they route together; two
    texts with no token overlap (or empty signatures) never share a sub-bucket.

    COMPLETE + DISJOINT: every index lands in exactly one sub-bucket — nothing is
    dropped. A near-dup pair split across sub-buckets is simply never NLI-scored
    (stays unmerged = KEEP, the same outcome the over-cap skip gave EVERY pair).
    Complexity O(n * buckets) set ops — trivial at the few-hundred-text scale that
    overflows the pair cap (311/351 in the drb_72 evidence)."""
    size_cap = _max_subbucket_size(max_pairs)
    threshold = _subbucket_jaccard()
    signatures = [_subbucket_tokens(t) for t in texts]
    buckets: list[list[int]] = []
    representatives: list[frozenset[str]] = []
    for i in range(len(texts)):
        sig = signatures[i]
        best = -1
        best_score = 0.0
        if sig:
            for b, rep in enumerate(representatives):
                if len(buckets[b]) >= size_cap or not rep:
                    continue
                overlap = len(sig & rep)
                if not overlap:
                    continue
                score = overlap / float(len(sig | rep))
                if score >= threshold and score > best_score:
                    best, best_score = b, score
        if best >= 0:
            buckets[best].append(i)
        else:
            buckets.append([i])
            representatives.append(sig)
    return buckets


def _is_cuda_oom(exc: BaseException) -> bool:
    """True iff ``exc`` is a CUDA out-of-memory / allocation failure (the only failure the
    W10 winner DEGRADES to CPU; every other error fails loud per §-1.4). Detects the typed
    ``torch.cuda.OutOfMemoryError``, the generic ``RuntimeError('CUDA out of memory ...')``,
    AND the cuBLAS allocation failures ``CUBLAS_STATUS_ALLOC_FAILED`` /
    ``CUBLAS_STATUS_NOT_INITIALIZED`` — by class name + message, so no hard torch import.

    I-deepfix-001 (#1344): the cuBLAS branch is the crash fix. When the card is full the
    SAME out-of-memory condition surfaces from a cuBLAS handle allocation as
    ``CUDA error: CUBLAS_STATUS_ALLOC_FAILED`` (or ``..._NOT_INITIALIZED`` when a prior
    alloc poisoned the handle) with NO 'out of memory' substring. The old matcher missed
    it, so the CPU degrade never fired and the run DIED at the consolidation step on the
    large clinical corpora. cuBLAS-alloc is OOM-equivalent — route it to the SAME
    already-tested identical-result CPU degrade."""
    name = type(exc).__name__
    if name in ("OutOfMemoryError", "CudaOutOfMemoryError"):
        return True
    msg = str(exc).lower()
    if "out of memory" in msg and ("cuda" in msg or "gpu" in msg):
        return True
    return "cublas_status_alloc_failed" in msg or "cublas_status_not_initialized" in msg


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
        # I-deepfix-001 L4 (#1344): resolve entailment/contradiction indices from the
        # loaded model so a MULTILINGUAL cross-encoder with a different label order is
        # read correctly (never mis-mapped to the English default).
        _resolve_label_indices(_MODEL)
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
        _resolve_label_indices(_MODEL)  # I-deepfix-001 L4 (#1344)
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


def entails_directional(
    premise: str,
    hypothesis: str,
    *,
    margin: Optional[float] = None,
    predict_fn: Optional[Callable[[list[tuple[str, str]]], Any]] = None,
) -> Optional[bool]:
    """DIRECTIONAL single-pair entailment: does ``premise`` entail ``hypothesis``?

    I-deepfix-001 P2 citation-purity (#1344): the ALCE / DeepTRACE citation direction —
    ``premise`` = the corroborator's claim-local cited span, ``hypothesis`` = the rendered
    claim (or one of its claim-local clauses). This is the ONE-directional counterpart to the
    bidirectional ``score_pairs`` used for basket consolidation: a citation is a
    span->claim SUPPORT relation (the span must entail the claim), which is asymmetric, so we
    read ONLY the forward logits — NOT both directions.

    Returns three states so the caller can distinguish a real NON-entailment from an
    infra fault:
      * ``True``  — ``premise`` entails ``hypothesis`` (entailment is the strict argmax by
        ``margin``, the SAME threshold ``_entails`` applies in consolidation);
      * ``False`` — a CONFIDENT non-entailment (the detach signal — the cited span does not
        carry this claim);
      * ``None``  — the verdict is UNAVAILABLE (empty text, or the cross-encoder could not be
        loaded / scored for a NON-OOM reason). None is the DEGRADE sentinel: the caller keeps
        the citation on its already-passed lexical/numeric grounding rather than detaching on
        a model outage (never fights §-1.3 breadth on infra failure).

    Reuses ``_load_model`` + ``_entails`` on ONE forward pair, with the SAME CUDA-OOM -> CPU
    degrade as ``score_pairs`` (an OOM re-scores on CPU, never dies). ``predict_fn`` is the
    deterministic test-injection seam (no GPU / model download); production passes None => the
    lazy cross-encoder. No new model is loaded — it is the SAME resident cross-encoder the
    consolidation leg already loads, so P2 adds ZERO OpenRouter / GPU spend.
    """
    if not premise or not premise.strip() or not hypothesis or not hypothesis.strip():
        return None
    margin = _margin() if margin is None else margin
    _injected = predict_fn is not None
    if predict_fn is None:
        try:
            model = _load_model()
        except Exception as exc:  # noqa: BLE001 — infra fault => UNKNOWN (caller keeps)
            logger.warning(
                "[consolidation_nli] entails_directional: cross-encoder unavailable (%s); "
                "returning None (caller keeps the citation on lexical/numeric grounding).",
                exc,
            )
            return None
        predict_fn = model.predict  # type: ignore[assignment]
    batch: list[tuple[str, str]] = [(premise, hypothesis)]
    try:
        logits = predict_fn(batch)
    except Exception as exc:  # noqa: BLE001 — only a CUDA OOM degrades; else UNKNOWN
        if not _is_cuda_oom(exc) or _injected:
            logger.warning(
                "[consolidation_nli] entails_directional: predict failed (%s); returning "
                "None (caller keeps the citation).", exc,
            )
            return None
        try:
            cpu_model = _reload_model_on_cpu()
            logits = cpu_model.predict(batch)
        except Exception as exc2:  # noqa: BLE001 — CPU degrade also failed => UNKNOWN
            logger.warning(
                "[consolidation_nli] entails_directional: CPU re-score failed (%s); "
                "returning None.", exc2,
            )
            return None
    return _entails(logits[0], margin)


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

    # Total upper-triangle pair count, computed WITHOUT materializing the O(n^2) list —
    # an over-cap bucket must never allocate the full list just to be told it is over
    # the cap (I-deepfix-001 W04-prebucket #1369; under-cap construction is unchanged).
    total_pairs = n * (n - 1) // 2
    pairs: list[tuple[int, int]]
    if total_pairs > max_pairs:
        if _subbucket_enabled():
            # I-deepfix-001 W04-prebucket (#1369): the RIGHT over-cap behavior — SUB-DIVIDE
            # the bucket into lexical-overlap sub-buckets whose per-sub-bucket pair count
            # stays <= the cap, then score ONLY the within-sub-bucket pairs through the
            # UNCHANGED bounded-parallel/predict-chunk/wall machinery below. Near-dups
            # (which share most content words) route into the SAME sub-bucket and still
            # MERGE; a cross-sub-bucket pair is never scored => stays UNMERGED (a KEEP —
            # worst case equals the old whole-bucket skip, never worse; §-1.3). Total
            # scored pairs grow ~linearly with n (<= n/2 * size_cap), never O(n^2), so
            # the compute/memory blowup the cap guards stays closed.
            sub_buckets = _pre_bucket_indices(texts, max_pairs)
            pairs = [
                (bucket[a], bucket[b])
                for bucket in sub_buckets
                for a in range(len(bucket))
                for b in range(a + 1, len(bucket))
            ]
            largest = max((len(b) for b in sub_buckets), default=0)
            logger.warning(
                "[consolidation_nli] W04: %d candidate pairs exceeds %s=%d — PRE-BUCKETING "
                "%d texts into %d lexical sub-buckets (largest=%d, per-sub-bucket pairs <= "
                "cap); NLI consolidation RUNS on %d within-sub-bucket pairs. Cross-sub-bucket "
                "near-dups stay UNMERGED (KEEP — never worse than the skip; no basket "
                "dropped, §-1.3).",
                total_pairs, ENV_MAX_PAIRS, max_pairs, n, len(sub_buckets), largest,
                len(pairs),
            )
            if not pairs:
                return []
        else:
            # I-deepfix-001 W04-consolidation-nli-wall (#1344): an over-MAX_PAIRS scale guard
            # must DEGRADE, not ABORT the whole run. The prior `raise ValueError` propagated
            # uncaught through `_apply_consolidation_nli` (finding_dedup.py) and aborted the
            # run on a large cluster count. Consolidation is a WEIGHT, not a faithfulness
            # gate: when the pair count exceeds the cap, SKIP scoring and return NO edges =>
            # the literal clusters pass through UNMERGED (keeps MORE/equal baskets, §-1.3),
            # exactly mirroring the prose path's correct over-cap skip in fact_dedup.py. The
            # skip is a LOUD telemetry note, never silent. The whole-run abort is converted to
            # a per-step under-merge.
            logger.warning(
                "[consolidation_nli] W04: %d candidate pairs exceeds %s=%d — SKIPPING NLI "
                "consolidation for this bucket (literal clusters pass through UNMERGED; no "
                "basket dropped). Raise %s or set %s=1 to pre-bucket and merge them.",
                total_pairs, ENV_MAX_PAIRS, max_pairs, ENV_MAX_PAIRS, ENV_SUBBUCKET,
            )
            return []
    else:
        # All upper-triangle index pairs. O(n^2) is bounded by `max_pairs`.
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]

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
    # I-deepfix-001 (#1344): cap the per-forward batch so it cannot grow unbounded with
    # corpus size (the clinical CUBLAS_STATUS_ALLOC_FAILED). At most `workers` chunks run
    # concurrently, so peak GPU memory is bounded by workers * predict_chunk regardless of
    # corpus size. Union-find over the edges is order-independent => byte-identical output.
    _pchunk = _predict_chunk()
    if _pchunk > 0:
        chunk_size = min(chunk_size, _pchunk)
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

    # I-deepfix-001 W04-consolidation-nli-wall (#1344): a TOTAL wall-clock deadline over the
    # whole scoring loop. The bounded-parallel gather previously BLOCKED until EVERY chunk
    # finished (pool.map drains all); on a slow/CPU-degraded cross-encoder that had no time
    # bound. When the deadline passes we STOP collecting further chunk edges and return the
    # edges gathered so far. A partial edge set only UNDER-merges => keeps MORE/equal baskets
    # (§-1.3), never drops a corroborator. `wall <= 0` disables the deadline (unbounded, the
    # escape hatch / byte-identical default-OFF caller). Deterministic: the returned edges are
    # still sorted, so for a non-truncated run the output is identical regardless of timing.
    _wall = _wall_seconds()
    _deadline = (time.monotonic() + _wall) if _wall > 0 else None

    def _deadline_passed() -> bool:
        return _deadline is not None and time.monotonic() > _deadline

    all_edges: list[tuple[int, int]] = []
    _truncated = False
    if workers <= 1 or len(chunks) <= 1:
        for chunk in chunks:
            if _deadline_passed():
                _truncated = True
                break
            all_edges.extend(_score_chunk(chunk))
    else:
        # I-deepfix-001 W04 (#1344): manage the pool MANUALLY (NOT `with`) so the
        # non-blocking shutdown cannot be defeated by `with`'s __exit__ shutdown(wait=True),
        # which would BLOCK until a wedged cross-encoder chunk finishes — making the wall
        # cosmetic (the function would not RETURN until the slow chunks drained).
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            futures = [pool.submit(_score_chunk, chunk) for chunk in chunks]
            pending = set(futures)
            while pending:
                _remaining = None if _deadline is None else max(0.0, _deadline - time.monotonic())
                if _remaining is not None and _remaining <= 0:
                    _truncated = True
                    break
                done, pending = futures_wait(
                    pending, timeout=_remaining, return_when=FIRST_COMPLETED,
                )
                if not done:
                    # `wait` returned on the timeout with nothing newly completed => the wall
                    # elapsed mid-flight. Collect whatever already finished and stop.
                    _truncated = True
                    break
                for fut in done:
                    all_edges.extend(fut.result())
            if _truncated:
                # Collect any futures that DID finish before the wall (do not block on the
                # rest — they keep running to completion in their threads but we stop waiting,
                # SS-1.3: skipping their edges only UNDER-merges).
                for fut in list(pending):
                    if fut.done():
                        try:
                            all_edges.extend(fut.result())
                        except Exception:  # noqa: BLE001 — a late failure must not abort the run
                            pass
        finally:
            # NON-BLOCKING teardown so a wedged chunk cannot delay the partial return.
            pool.shutdown(wait=False, cancel_futures=True)
    if _truncated:
        logger.warning(
            "[consolidation_nli] W04: scoring wall (%ss) elapsed with %d/%d chunks scored "
            "— returning the partial edge set (UNDER-merges only; no basket dropped, §-1.3). "
            "Raise %s to score more pairs.",
            _wall, len(all_edges), len(chunks), ENV_WALL_SECONDS,
        )

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
