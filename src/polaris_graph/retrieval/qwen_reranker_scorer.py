"""Qwen3-Reranker causal-LM yes/no-logit relevance scorer (I-bug-reranker-noise, #1312).

WHY THIS EXISTS. The recency-completion reranker WINNER is ``Qwen/Qwen3-Reranker-4B``
(I-recency-001 #1296). It was *scored* in the bake-off via the model authors' canonical
causal-LM method — append a fixed ``Judge whether ... "yes" or "no"`` template, run one
forward pass, and read ``softmax(logit["yes"], logit["no"])[1]`` as P(relevant). Production,
however, loaded the SAME model id through ``sentence_transformers.CrossEncoder``. A Qwen3
reranker is an ``AutoModelForCausalLM``, NOT a sequence-classification head; ``CrossEncoder``
attaches a FRESH, RANDOMLY-INITIALIZED classification head to it. That head was never trained,
so ``encoder.predict()`` returns ~0.5 NOISE — the reranker winner was, in effect, NOT running
in production (the reorder it produced was random). The bake-off file documents this exact
trap (``scripts/dr_benchmark/retrieval_bakeoff/reranker/run_bakeoff.py`` lines 27-29, 130):
"loading a Qwen reranker via CrossEncoder mints a random score head -> ~0.5 noise; the
canonical method scores P('yes')".

WHAT THIS MODULE IS. A tiny, lazy, GPU-first scorer that reproduces the bake-off's proven
``_build_qwen_causal_fn`` method as production code (the bake-off lives under ``scripts/`` and
must NOT be imported by ``src/``). It exposes one callable:

    score_query_document_relevance(query, documents, *, model_id, device=None) -> list[float]

returning P("yes") in [0, 1] per document, in INPUT ORDER (a higher score = more relevant).

INVARIANTS PRESERVED BY THE CALLER (``evidence_selector._maybe_rerank_selection``):
  * torch / transformers are imported LAZILY *inside* this module's functions, and this module
    is itself imported lazily by the caller only on the reranker-ON path — so the default-OFF
    selection path pays ZERO import / model cost.
  * Any load/scoring failure is the CALLER's concern: it falls back LOUDLY to the original
    (tier-balanced) order. This module simply raises on failure; it never returns a silent stub.
  * Model id stays a ``.env`` knob (``PG_RERANKER_MODEL`` -> ``CrossEncoderConfig.from_env``);
    this module is id-agnostic and works for 0.6B / 4B / 8B identically (same architecture, same
    template) — which also makes the fix CPU-fire-testable on the 0.6B while production serves
    the 4B on GPU.
"""

from __future__ import annotations

import logging
import os
from typing import Optional, Sequence
from src.polaris_graph.settings import resolve

logger = logging.getLogger("polaris_graph.qwen_reranker_scorer")


class RerankerLoadError(RuntimeError):
    """I-deepfix-001 P1-1 (#1344): raised ONLY when the W7 reranker STRUCTURALLY
    fails to load — the lazy torch/transformers import, ``from_pretrained``, the
    ``.to(device)`` placement, or the yes/no token-id resolution. The caller
    (``evidence_selector._maybe_rerank_selection``) treats this as the structural
    W7-dark signal the winner-firing gate hard-gates on. A failure of the per-document
    FORWARD PASS (a transient encode/OOM exception) is NOT wrapped in this type — it
    surfaces as a plain exception so the caller can treat it as a transient (the model
    DID load) and NOT flip the sticky structural signal. This mirrors the embedder's
    structural-vs-transient split (``evidence_selector._get_semantic_embedder``)."""

# The fixed scoring template from the Qwen3-Reranker model card (verbatim with the bake-off's
# proven ``_build_qwen_causal_fn``). The model answers "yes"/"no"; we read the next-token logits
# of those two tokens and softmax them -> P("yes") = relevance.
_SYSTEM_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
    'and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
    "<|im_start|>user\n"
)
_ASSISTANT_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
_INSTRUCT = "Given a web search query, retrieve relevant passages that answer the query"

# Per-document input truncation length (tokens). A CAP, not a target — long docs are truncated
# so the single forward pass stays bounded. Matches the bake-off's max_length.
_MAX_INPUT_TOKENS = 4096


def _resolve_device(device: Optional[str]) -> str:
    """GPU-first: ``cuda`` when available, else ``cpu``. Honors an explicit override.

    Precedence: an explicit ``device`` arg wins (the production W7 path pre-resolves
    in ``evidence_selector._maybe_rerank_selection`` so env > cfg.device is decided
    THERE, before the call). This ``PG_RERANKER_DEVICE`` fallback is defense for
    DIRECT callers that pass ``device=None`` (and the offline test surface) — it is a
    LAUNCH-ENV read, not a slate force-ON value, so it does not affect SLATE-PURITY /
    NO-LOSER gating (those gate winner force-ON *values*, not device reads)."""
    if device:
        return device
    env_device = resolve("PG_RERANKER_DEVICE").strip()
    if env_device:
        return env_device
    import torch  # lazy

    return "cuda" if torch.cuda.is_available() else "cpu"


def score_query_document_relevance(
    query: str,
    documents: Sequence[str],
    *,
    model_id: str,
    device: Optional[str] = None,
) -> list[float]:
    """Score each document's relevance to ``query`` as P("yes") in [0, 1], in input order.

    Loads ``model_id`` as an ``AutoModelForCausalLM`` (the CORRECT class for a Qwen3 reranker)
    and reads the next-token "yes"/"no" logits — the canonical, bake-off-proven method. A real
    relevance signal: a clearly-relevant document scores markedly HIGHER than junk (unlike the
    ~0.5 noise the random CrossEncoder head produced).

    Raises on any load/scoring failure (the caller falls back loudly to the original order).
    torch + transformers are imported here, lazily, so the reranker-OFF path never touches them.
    """
    docs = list(documents)
    if not docs:
        return []

    # I-deepfix-001 P1-1 (#1344): the STRUCTURAL LOAD region. A failure HERE (import /
    # from_pretrained / device placement / token-id resolution) is a structural W7-dark
    # signal -> re-raise as RerankerLoadError so the caller marks the gate dark. A
    # later FORWARD-PASS failure (below, in _score_one) is a transient and is NOT
    # wrapped, so it does not flip the sticky structural signal.
    try:
        import torch  # lazy — nothing here loads on the reranker-OFF path
        from transformers import AutoModelForCausalLM, AutoTokenizer

        resolved_device = _resolve_device(device)
        logger.info(
            "[qwen-reranker] loading %s on %s (causal-LM yes/no-logit scoring; NOT CrossEncoder)",
            model_id, resolved_device,
        )
        tokenizer = AutoTokenizer.from_pretrained(model_id, padding_side="left")
        model = (
            AutoModelForCausalLM.from_pretrained(model_id, dtype="auto")
            .to(resolved_device)
            .eval()
        )
        token_id_no = tokenizer.convert_tokens_to_ids("no")
        token_id_yes = tokenizer.convert_tokens_to_ids("yes")
    except Exception as load_exc:  # structural import / load / device / token failure
        raise RerankerLoadError(
            f"W7 reranker structural load failed for {model_id!r}: {load_exc}"
        ) from load_exc

    def _score_one(document: str) -> float:
        text = (
            _SYSTEM_PREFIX
            + f"<Instruct>: {_INSTRUCT}\n<Query>: {query or ''}\n<Document>: {document}"
            + _ASSISTANT_SUFFIX
        )
        inputs = tokenizer(
            text,
            return_tensors="pt",
            truncation=True,
            max_length=_MAX_INPUT_TOKENS,
        ).to(resolved_device)
        with torch.no_grad():
            last_token_logits = model(**inputs).logits[0, -1]
        yes_no_pair = torch.stack(
            [last_token_logits[token_id_no], last_token_logits[token_id_yes]]
        ).float()
        return float(torch.softmax(yes_no_pair, dim=0)[1])

    return [_score_one(d) for d in docs]
