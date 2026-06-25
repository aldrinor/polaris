#!/usr/bin/env python3
"""FIRE-TEST for I-bug-reranker-noise (#1312): real signal, not random-head noise.

Proves the fix at ``evidence_selector._maybe_rerank_selection`` works END-TO-END: the
Qwen3-Reranker, loaded the CORRECT way (causal-LM yes/no logits via
``qwen_reranker_scorer.score_query_document_relevance``), produces a REAL relevance signal
— a clearly-relevant passage scores markedly higher than clearly-irrelevant junk, and
``_maybe_rerank_selection`` REORDERS the selected rows so the relevant row rises to the top.

The pre-fix CrossEncoder load minted a random classification head -> ~0.5 noise for every
pair (no signal, no meaningful reorder). FAIL LOUD (non-zero exit) if the signal is absent.

DEVICE / SIZE NOTE: this box has no GPU, and the production WINNER (Qwen3-Reranker-4B, ~8GB)
is too heavy to load on CPU here. The bug AND the fix are LOADER-LEVEL and architecture-
identical across 0.6B/4B/8B (same causal-LM, same yes/no template), so we fire-test on
``Qwen/Qwen3-Reranker-0.6B`` on CPU as a faithful proxy. Production keeps PG_RERANKER_MODEL
-> 4B, GPU-served. Override the proxy id with PG_FIRE_TEST_RERANKER_MODEL if desired.
"""

from __future__ import annotations

import os
import sys

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# CPU-feasible proxy for the GPU-served 4B winner (loader is size-independent).
_PROXY_MODEL_ID = os.environ.get("PG_FIRE_TEST_RERANKER_MODEL", "Qwen/Qwen3-Reranker-0.6B")

# Minimum margin between the relevant and the junk score. A random head gives ~0 margin
# (both ~0.5); a working causal-LM scorer separates them by a wide gap. A modest floor
# proves "real signal, not noise" without overfitting an exact number.
_MIN_MARGIN = 0.20


def main() -> int:
    from src.polaris_graph.retrieval.evidence_selector import _maybe_rerank_selection
    from src.polaris_graph.retrieval.qwen_reranker_scorer import (
        score_query_document_relevance,
    )

    query = "What is the cardiovascular benefit of semaglutide in adults with obesity?"
    relevant_doc = (
        "In the SELECT trial, semaglutide 2.4 mg reduced the risk of major adverse "
        "cardiovascular events by 20% compared with placebo in adults with overweight or "
        "obesity and established cardiovascular disease."
    )
    junk_doc = (
        "The municipal parking authority announced revised weekend tariffs for the "
        "downtown garage, effective the first of next month, alongside new bicycle racks."
    )

    print(f"[fire-test] loading {_PROXY_MODEL_ID} (causal-LM yes/no scoring) ...", flush=True)
    scores = score_query_document_relevance(
        query, [relevant_doc, junk_doc], model_id=_PROXY_MODEL_ID, device="cpu"
    )
    rel_score, junk_score = scores[0], scores[1]
    margin = rel_score - junk_score
    print(f"[fire-test] P(yes) relevant = {rel_score:.4f}", flush=True)
    print(f"[fire-test] P(yes) junk     = {junk_score:.4f}", flush=True)
    print(f"[fire-test] margin          = {margin:.4f} (min required {_MIN_MARGIN})", flush=True)

    failures: list[str] = []
    if not (rel_score > junk_score):
        failures.append(
            f"relevant ({rel_score:.4f}) did NOT outscore junk ({junk_score:.4f}) — "
            "no relevance signal (looks like the random-head noise the fix removes)."
        )
    if margin < _MIN_MARGIN:
        failures.append(
            f"margin {margin:.4f} < {_MIN_MARGIN}: signal too weak to distinguish from "
            "~0.5 noise (a working reranker separates relevant from junk by a wide gap)."
        )

    # End-to-end: _maybe_rerank_selection must REORDER selected rows so the relevant row
    # rises above the junk row. Junk is placed FIRST so a real reorder is observable.
    os.environ["PG_RERANKER_MODEL"] = "qwen3"
    os.environ["PG_FIRE_TEST_RERANKER_MODEL"] = _PROXY_MODEL_ID  # carried into config? no — see below
    selected_rows = [
        {"id": "junk", "statement": junk_doc, "direct_quote": ""},
        {"id": "relevant", "statement": relevant_doc, "direct_quote": ""},
    ]
    # The production path reads the model id from CrossEncoderConfig.from_env() (-> 4B). To keep
    # the e2e reorder check CPU-feasible we patch that single config call to the proxy id; the
    # SCORING CODE under test (qwen_reranker_scorer + _maybe_rerank_selection wiring) is unchanged.
    import src.config.core as _core

    _orig_from_env = _core.CrossEncoderConfig.from_env

    def _proxy_from_env(data=None):
        cfg = _orig_from_env(data)
        cfg.model = _PROXY_MODEL_ID
        return cfg

    _core.CrossEncoderConfig.from_env = staticmethod(_proxy_from_env)
    try:
        reranked = _maybe_rerank_selection(selected_rows, query)
    finally:
        _core.CrossEncoderConfig.from_env = staticmethod(_orig_from_env)

    order_ids = [r["id"] for r in reranked]
    print(f"[fire-test] reordered ids (junk-first input) = {order_ids}", flush=True)
    if order_ids[0] != "relevant":
        failures.append(
            f"_maybe_rerank_selection did NOT promote the relevant row to the top "
            f"(got order {order_ids}) — the reorder is not driven by real relevance."
        )

    if failures:
        print("\n[FIRE-TEST FAILED]", flush=True)
        for f in failures:
            print(f"  - {f}", flush=True)
        return 1
    print(
        f"\n[FIRE-TEST PASSED] real signal (margin {margin:.4f}) + correct reorder "
        f"(relevant promoted above junk). The causal-LM loader produces relevance, not noise.",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
