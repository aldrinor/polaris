#!/usr/bin/env python3
"""I-ret-002 (#1294) reranker layer — ISOLATION bake-off runner.

Loads each reranker candidate by its EXACT, web-verified HF/pip id, runs the GATE-0 per-candidate
LIVENESS canary, then scores it on the FROZEN per-idx pool with credibility-graded NDCG@K +
required-source recall@K guard. Writes ranked results JSON.

WINNER METRIC (brief §6): credibility-graded NDCG@K is PRIMARY (on POLARIS data); the
required-source recall@K guard is a hard NON-REGRESSION gate (a candidate that evicts a required
source below the baseline recall@K is disqualified regardless of NDCG — the dedup-0.97-floor
pattern). External benchmarks (MTEB-reranking / BEIR) are a SUPPLEMENTAL cross-check only, not run
here.

RE-ORDER ONLY (§-1.3 / PROD INVARIANT). Every candidate sees the byte-identical frozen pool and the
SAME top-K window; they differ ONLY in ORDER. No candidate may drop a row. Off-topic items get gain
0 (demoted, they sink in NDCG) — never removed. The off-topic-drop facet is SUPERSEDED/SCRUBBED.

HONEST FLAGS:
  * needs_gpu candidates are gated behind a live ``torch.cuda.is_available()`` check; with no GPU
    they are registered-but-skipped (status="skipped_needs_gpu"), NEVER faked.
  * no_key / non-deployable-license candidates are registered honestly (yardstick only; never
    crowned). zerank-1-small is Apache-2.0 (deployable); llama-nemotron-rerank-1b-v2 is the NVIDIA
    Open Model License YARDSTICK.
  * any candidate that fails the liveness canary is recorded status="failed_liveness" and excluded
    from the ranking — never scored as a believable low number.

The Qwen3-Reranker scoring REUSES the proven causal-LM yes/no-logit method from
``scripts/relevance_scorer_bakeoff.py`` (loading a Qwen reranker via CrossEncoder mints a random
score head -> ~0.5 noise; the canonical method scores P("yes")).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "..", "..", "..", ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.dr_benchmark.retrieval_bakeoff.reranker import gate0  # noqa: E402
from scripts.dr_benchmark.retrieval_bakeoff.reranker import build_fixture  # noqa: E402

RerankFn = gate0.RerankFn

# Default top-K window (held identical across all candidates). CLI-overridable; never hardcoded as
# a "magic" cut — it is the same window every candidate re-orders within.
DEFAULT_K = 20


# ---------------------------------------------------------------------------------------------
# Candidate registry — EXACT ids + role + honest runnable flags (brief §6, web-verified).
# ---------------------------------------------------------------------------------------------
@dataclass
class Candidate:
    name: str
    model_id: str  # exact HF/pip/in-repo id
    role: str  # baseline | candidate | yardstick
    license: str
    runnable: str  # "yes" (CPU) | "needs_gpu"
    deployable: bool  # False => yardstick only, never crowned (license/sovereignty)
    loader: str  # which adapter builds the RerankFn
    notes: str = ""


CANDIDATES: list[Candidate] = [
    Candidate(
        name="polaris_lexical_rerank",
        model_id="src/polaris_graph/retrieval/live_retriever.py:_rerank_and_reserve",
        role="baseline",
        license="in-repo",
        runnable="yes",
        deployable=True,
        loader="lexical",
        notes="current-default FLOOR; token-overlap, CPU, no model. Every model must beat this.",
    ),
    Candidate(
        name="bge_reranker_v2_m3",
        model_id="BAAI/bge-reranker-v2-m3",
        role="baseline",
        license="apache-2.0",
        runnable="needs_gpu",
        deployable=True,
        loader="cross_encoder",
        notes="dated 2024 baseline (the old-SOTA line the 2025/26 cohort must clear).",
    ),
    Candidate(
        name="gte_reranker_modernbert_base",
        model_id="Alibaba-NLP/gte-reranker-modernbert-base",
        role="candidate",
        license="apache-2.0",
        runnable="needs_gpu",
        deployable=True,
        loader="cross_encoder",
        notes="landscape lead pick (149M, 8192-ctx). CrossEncoder, softmaxed [0,1] scores.",
    ),
    Candidate(
        name="mxbai_rerank_base_v2",
        model_id="mixedbread-ai/mxbai-rerank-base-v2",
        role="candidate",
        license="apache-2.0",
        runnable="needs_gpu",
        deployable=True,
        loader="mxbai",
        notes="0.5B RL-tuned instruction-aware; pip install mxbai-rerank; MxbaiRerankV2.rank().",
    ),
    Candidate(
        name="zerank_1_small",
        model_id="zeroentropy/zerank-1-small",
        role="candidate",
        license="apache-2.0",
        runnable="needs_gpu",
        deployable=True,
        loader="cross_encoder_trust",
        notes="Apache-2.0 (verified; only zerank-2 is CC-BY-NC). CrossEncoder trust_remote_code.",
    ),
    Candidate(
        name="qwen3_reranker_4b",
        model_id="Qwen/Qwen3-Reranker-4B",
        role="candidate",
        license="apache-2.0",
        runnable="needs_gpu",
        deployable=True,
        loader="qwen_causal",
        notes="causal-LM yes/no-logit method (NOT CrossEncoder — that mints a random head).",
    ),
    Candidate(
        name="qwen3_reranker_8b",
        model_id="Qwen/Qwen3-Reranker-8B",
        role="candidate",
        license="apache-2.0",
        runnable="needs_gpu",
        deployable=True,
        loader="qwen_causal",
        notes="causal-LM yes/no-logit method.",
    ),
    Candidate(
        name="llama_nemotron_rerank_1b_v2",
        model_id="nvidia/llama-nemotron-rerank-1b-v2",
        role="yardstick",
        license="nvidia-open-model-license",
        runnable="needs_gpu",
        deployable=False,  # NVIDIA OML — yardstick only, never crowned vs the Apache cohort
        loader="nemotron",
        notes="1B Llama-3.2 cross-encoder yardstick (NVIDIA Open Model License).",
    ),
]


# ---------------------------------------------------------------------------------------------
# Adapters: each returns a RerankFn (query, docs) -> list[float]. Models load lazily, ONCE.
# All torch / transformers / vendor imports are INSIDE the adapters so the module imports + the
# offline smoke run with NO ML deps installed and NO network.
# ---------------------------------------------------------------------------------------------
def _build_lexical_rerank_fn() -> RerankFn:
    """Baseline: the in-repo lexical token-overlap score (no model, CPU). Wraps the SAME helpers
    the production ``_rerank_and_reserve`` uses so the bake-off scores the real incumbent signal."""
    from src.polaris_graph.retrieval.live_retriever import (  # local import (heavy module)
        _lexical_relevance_score,
        _rerank_content_tokens,
    )

    class _Stub:
        """Minimal SearchCandidate-shaped object _lexical_relevance_score can score."""

        def __init__(self, text: str) -> None:
            self.title = text
            self.snippet = ""
            self.body = text

    def fn(query: str, docs: Sequence[str]) -> list[float]:
        q_tokens = _rerank_content_tokens(query)
        return [float(_lexical_relevance_score(_Stub(d), q_tokens)) for d in docs]

    return fn


def _build_cross_encoder_fn(model_id: str, *, trust_remote_code: bool, device: str) -> RerankFn:
    from sentence_transformers import CrossEncoder

    model = CrossEncoder(model_id, trust_remote_code=trust_remote_code, device=device)

    def fn(query: str, docs: Sequence[str]) -> list[float]:
        pairs = [[query, d] for d in docs]
        scores = model.predict(pairs)
        return [float(s) for s in scores]

    return fn


def _build_mxbai_fn(model_id: str, *, device: str) -> RerankFn:
    from mxbai_rerank import MxbaiRerankV2

    model = MxbaiRerankV2(model_id, device=device)

    def fn(query: str, docs: Sequence[str]) -> list[float]:
        # .rank returns results ranked; we need a score PER input position, in input order.
        results = model.rank(query, list(docs), return_documents=False, top_k=len(docs))
        by_index = {int(r.index): float(r.score) for r in results}
        return [by_index[i] for i in range(len(docs))]

    return fn


def _build_qwen_causal_fn(model_id: str, *, device: str) -> RerankFn:
    """REUSE the proven causal-LM yes/no-logit method from scripts/relevance_scorer_bakeoff.py."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_id, padding_side="left")
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype="auto").to(device).eval()
    tid_no = tok.convert_tokens_to_ids("no")
    tid_yes = tok.convert_tokens_to_ids("yes")
    prefix = (
        "<|im_start|>system\nJudge whether the Document meets the requirements based on the Query "
        'and the Instruct provided. Note that the answer can only be "yes" or "no".<|im_end|>\n'
        "<|im_start|>user\n"
    )
    suffix = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"
    instr = "Given a web search query, retrieve relevant passages that answer the query"

    def score_one(q: str, doc: str) -> float:
        text = prefix + f"<Instruct>: {instr}\n<Query>: {q}\n<Document>: {doc}" + suffix
        inp = tok(text, return_tensors="pt", truncation=True, max_length=4096).to(device)
        with torch.no_grad():
            logits = model(**inp).logits[0, -1]
        pair = torch.stack([logits[tid_no], logits[tid_yes]]).float()
        return float(torch.softmax(pair, dim=0)[1])

    def fn(query: str, docs: Sequence[str]) -> list[float]:
        return [score_one(query, d) for d in docs]

    return fn


def _build_nemotron_fn(model_id: str, *, device: str) -> RerankFn:
    """NVIDIA Llama-Nemotron rerank-1b-v2 — a transformer cross-encoder. Loaded via Sentence
    Transformers CrossEncoder with trust_remote_code (per the model card's ST integration)."""
    return _build_cross_encoder_fn(model_id, trust_remote_code=True, device=device)


def build_rerank_fn(cand: Candidate, *, device: str) -> RerankFn:
    if cand.loader == "lexical":
        return _build_lexical_rerank_fn()
    if cand.loader == "cross_encoder":
        return _build_cross_encoder_fn(cand.model_id, trust_remote_code=False, device=device)
    if cand.loader == "cross_encoder_trust":
        return _build_cross_encoder_fn(cand.model_id, trust_remote_code=True, device=device)
    if cand.loader == "mxbai":
        return _build_mxbai_fn(cand.model_id, device=device)
    if cand.loader == "qwen_causal":
        return _build_qwen_causal_fn(cand.model_id, device=device)
    if cand.loader == "nemotron":
        return _build_nemotron_fn(cand.model_id, device=device)
    raise ValueError(f"unknown loader {cand.loader!r} for candidate {cand.name!r}")


# ---------------------------------------------------------------------------------------------
# Scoring one candidate over one frozen idx pool (RE-ORDER only).
# ---------------------------------------------------------------------------------------------
def _ranked_order(scores: Sequence[float]) -> list[int]:
    """Stable descending sort of indices by score (ties keep arrival order — a re-order, not a drop)."""
    return sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))


def score_candidate_on_idx(
    rerank_fn: RerankFn,
    fx: "build_fixture.GoldIdxFixture",
    *,
    k: int,
) -> dict[str, Any]:
    """Return {ndcg_at_k, required_recall_at_k, gold_n, required_n, pool_n}. Re-orders the SAME
    pool; never removes a row."""
    docs = [c.body or c.title for c in fx.pool]
    gains = fx.gains()
    required_flags = [c.required for c in fx.pool]
    total_required = sum(1 for f in required_flags if f)

    scores = rerank_fn(fx.question, docs)
    if len(scores) != len(docs):
        raise gate0.RerankerLivenessError(
            f"reranker returned {len(scores)} scores for {len(docs)} docs (re-order must be 1:1)."
        )
    order = _ranked_order(scores)
    ranked_gains = [gains[i] for i in order]
    ranked_required = [required_flags[i] for i in order]
    return {
        "ndcg_at_k": gate0.graded_ndcg_at_k(ranked_gains, k),
        "required_recall_at_k": gate0.required_recall_at_k(ranked_required, total_required, k),
        "gold_n": len(fx.gold_claim_ids),
        "required_n": total_required,
        "pool_n": len(fx.pool),
    }


def run_bakeoff(
    *,
    fixtures: dict[str, "build_fixture.GoldIdxFixture"],
    candidates: list[Candidate],
    k: int,
    device: str,
    have_gpu: bool,
) -> dict[str, Any]:
    """Run GATE-0 (scorer+lineage) once, then per-candidate liveness + scoring. Returns the full
    results dict (also a ranked list). Honest skip/fail statuses; never fabricates a score."""
    gate0.run_scorer_and_lineage_gate(tuple(fixtures.keys()))  # fail loud before any model load

    results: list[dict[str, Any]] = []
    baseline_recall: dict[str, float] = {}  # slug -> baseline required-recall@K (non-regression ref)

    for cand in candidates:
        row: dict[str, Any] = {
            "name": cand.name,
            "model_id": cand.model_id,
            "role": cand.role,
            "license": cand.license,
            "deployable": cand.deployable,
            "status": "pending",
        }
        # Honest GPU gate.
        if cand.runnable == "needs_gpu" and not have_gpu:
            row["status"] = "skipped_needs_gpu"
            results.append(row)
            print(f"[skip] {cand.name}: needs_gpu, no CUDA available (registered, not faked)", flush=True)
            continue
        # Load + per-candidate liveness canary (fail loud, never score a stub).
        try:
            fn = build_rerank_fn(cand, device=device)
        except Exception as exc:  # missing dep / missing weights / load error
            row["status"] = "failed_load"
            row["error"] = repr(exc)[:300]
            results.append(row)
            print(f"[fail-load] {cand.name}: {exc!r}", flush=True)
            continue
        try:
            gate0.run_liveness_canary(fn, candidate_name=cand.name)
        except gate0.RerankerLivenessError as exc:
            row["status"] = "failed_liveness"
            row["error"] = str(exc)[:300]
            results.append(row)
            print(f"[fail-liveness] {cand.name}: {exc}", flush=True)
            continue

        # Score every gold idx.
        per_idx: dict[str, Any] = {}
        ndcgs: list[float] = []
        for slug, fx in fixtures.items():
            m = score_candidate_on_idx(fn, fx, k=k)
            per_idx[slug] = m
            ndcgs.append(m["ndcg_at_k"])
            if cand.role == "baseline" and cand.name == "polaris_lexical_rerank":
                baseline_recall[slug] = m["required_recall_at_k"]
        row["status"] = "scored"
        row["per_idx"] = per_idx
        row["mean_ndcg_at_k"] = sum(ndcgs) / len(ndcgs) if ndcgs else 0.0
        results.append(row)
        print(f"[scored] {cand.name}: mean_ndcg@{k}={row['mean_ndcg_at_k']:.4f}", flush=True)

    # Non-regression guard: disqualify any scored candidate whose required-recall@K regressed below
    # the baseline on ANY idx (a re-order that evicts a required sole-supporter). NOT a drop — the
    # candidate kept all rows; it just ordered a required source out of the window.
    #
    # CRITICAL anti-silent-no-op (drb_72 class): the guard is RELATIVE to the lexical baseline. If
    # the baseline did not actually run+score (subset run, or it failed_load/failed_liveness), there
    # is NO reference recall to compare against — the guard CANNOT be evaluated. We must NOT default
    # such candidates to passes_recall_guard=True (a believable-false pass that could crown an
    # unvetted reranker). They are marked "not_evaluated" and EXCLUDED from crowning, fail-loud-visible.
    scored_rows = [r for r in results if r.get("status") == "scored"]
    baseline_ran = bool(baseline_recall) and any(
        r["name"] == "polaris_lexical_rerank" and r["status"] == "scored" for r in results
    )
    if scored_rows and not baseline_ran:
        print(
            "[recall-guard] WARNING: the polaris_lexical_rerank baseline did NOT score (subset run "
            "or load/liveness failure) — the required-recall@K non-regression guard CANNOT be "
            "evaluated. Scored candidates are marked passes_recall_guard='not_evaluated' and are "
            "EXCLUDED from crowning (never a silent True). Re-run WITH the baseline to crown a winner.",
            flush=True,
        )
    for row in scored_rows:
        if not baseline_ran:
            row["required_recall_regressions"] = []
            row["passes_recall_guard"] = "not_evaluated"
            continue
        violations = []
        for slug, m in row.get("per_idx", {}).items():
            base = baseline_recall.get(slug)
            if base is None:
                # Baseline ran but lacks THIS idx (slug mismatch) — also cannot compare; fail loud.
                raise gate0.RerankerLivenessError(
                    f"recall-guard: baseline has no recall for idx {slug!r} but candidate "
                    f"{row['name']!r} scored it — cannot evaluate the non-regression guard. "
                    f"Run baseline+candidates over the SAME slug set."
                )
            if m["required_recall_at_k"] < base - 1e-12:
                violations.append(
                    {"slug": slug, "recall": m["required_recall_at_k"], "baseline": base}
                )
        row["required_recall_regressions"] = violations
        row["passes_recall_guard"] = len(violations) == 0
        if violations:
            print(
                f"[recall-guard] {row['name']} DISQUALIFIED: required-recall@{k} regressed vs "
                f"baseline on {[v['slug'] for v in violations]}",
                flush=True,
            )

    # Rank: deployable, scored, AND the recall guard returned a real True (not 'not_evaluated').
    # Yardsticks/non-deployable are ranked separately (never crowned). Skipped/failed never enter.
    eligible = [
        r for r in results
        if r.get("status") == "scored" and r.get("deployable") and r.get("passes_recall_guard") is True
    ]
    eligible.sort(key=lambda r: -r["mean_ndcg_at_k"])
    for i, r in enumerate(eligible):
        r["rank"] = i + 1

    return {
        "layer": "reranker",
        "k": k,
        "metric": "credibility_graded_ndcg_at_k (PRIMARY) + required_source_recall_at_k guard",
        "off_topic_drop_facet": "SUPERSEDED_SCRUBBED (demote-only, re-order-only, no hard drop)",
        "have_gpu": have_gpu,
        "device": device,
        "candidates": results,
        "ranking_deployable_recall_guard_passed": [r["name"] for r in eligible],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run the reranker ISOLATION bake-off.")
    ap.add_argument("--pool-dir", required=True)
    ap.add_argument("--annot-dir", required=True)
    ap.add_argument("--info-recall-dir", required=True)
    ap.add_argument("--out", required=True, help="results JSON path")
    ap.add_argument("--k", type=int, default=DEFAULT_K)
    ap.add_argument("--slugs", default=",".join(build_fixture.GOLD_SLUGS))
    ap.add_argument(
        "--candidates", default=",".join(c.name for c in CANDIDATES),
        help="comma-separated candidate names to run (default: all)",
    )
    args = ap.parse_args()

    device = "cpu"
    have_gpu = False
    try:
        import torch
        have_gpu = bool(torch.cuda.is_available())
        device = "cuda" if have_gpu else "cpu"
    except Exception:
        pass

    slugs = tuple(s for s in args.slugs.split(",") if s)
    fixtures = build_fixture.build_all(
        slugs=slugs,
        pool_dir=args.pool_dir,
        annot_dir=args.annot_dir,
        info_recall_dir=args.info_recall_dir,
    )
    wanted = {c.strip() for c in args.candidates.split(",") if c.strip()}
    cands = [c for c in CANDIDATES if c.name in wanted]
    if not cands:
        print(f"no candidates selected from {sorted(wanted)}", file=sys.stderr)
        return 2

    out = run_bakeoff(fixtures=fixtures, candidates=cands, k=args.k, device=device, have_gpu=have_gpu)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\nwrote {args.out}; ranking={out['ranking_deployable_recall_guard_passed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
