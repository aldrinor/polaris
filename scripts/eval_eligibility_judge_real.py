#!/usr/bin/env python3
"""REAL-model precision/recall eval for the opaque-clause ELIGIBILITY JUDGE.

Companion to ``scripts/eval_eligibility_judge.py`` (which injects a DETERMINISTIC
FAKE judge keyed on ``gold_kind`` — its P/R=1.0 proves only plumbing). This script
reuses the SAME labeled corpus, the SAME per-contract SPEC contracts, and the SAME
admit/exclude scoring logic, but injects a REAL LLM judge that calls the repo's
OpenRouter policy model (``z-ai/glm-5.2``). This measures whether the model
ACTUALLY discriminates predatory/off-topic/wrong-kind sources — not just whether
the aggregation plumbing works.

CRUCIAL: the real judge sees ONLY the production metadata view built by
``eligibility_judge._source_metadata_view`` (url/host/title/venue/type/
is_peer_reviewed/tier/year/doi/body_snippet). It NEVER sees ``gold_kind`` /
``category`` — no label leakage. The prompt is built by
``eligibility_judge._build_judge_prompt``.

Requires OPENROUTER_API_KEY (source ./.env). Makes ~1 LLM call per (source,
contract-with-clauses). NOT committed — a measurement.

Usage:
    python scripts/eval_eligibility_judge_real.py
    python scripts/eval_eligibility_judge_real.py --contract task72_journal_highquality_ontopic
    python scripts/eval_eligibility_judge_real.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from src.polaris_graph.planning import eligibility_judge  # noqa: E402
from src.polaris_graph.planning.eligibility_judge import (  # noqa: E402
    build_opaque_eligibility,
)

# Reuse the scoring logic verbatim from the fake-judge eval.
from scripts.eval_eligibility_judge import (  # noqa: E402
    _FakePolicy,
    _prf,
)

_CORPUS = _REPO / "tests" / "planning" / "fixtures" / "eligibility_corpus.json"
_MODEL = "z-ai/glm-5.2"
_MAX_TOKENS = 16000
_REASONING_POOL = 8000  # bound so the closing JSON always survives (glm-5.2 is reasoning-first)


# ---------------------------------------------------------------------------
# The REAL LLM judge — one bounded OpenRouter call per source, over all clauses.
# Sees ONLY the production metadata view (built inside judge_source before this
# callable is reached). Returns the raw JSON string the production parser consumes.
# ---------------------------------------------------------------------------


def _make_real_judge(client: Any) -> Any:
    """Build a synchronous (meta, clauses)->str judge that drives the async client.

    Reasoning-first safe: big max_tokens, and if content is empty we fall back to
    the reasoning field (glm-5.2 routes JSON into reasoning_content under load).
    """

    def _judge(meta: dict[str, Any], clauses: list[str]) -> str:
        prompt = eligibility_judge._build_judge_prompt(meta, clauses)

        async def _run() -> Any:
            return await client.generate(
                prompt=prompt,
                system=(
                    "You are a strict source-eligibility judge. Return ONLY the "
                    "requested JSON object, no prose."
                ),
                max_tokens=_MAX_TOKENS,
                temperature=0.0,
                reasoning_max_tokens=_REASONING_POOL,
            )

        resp = asyncio.run(_run())
        content = getattr(resp, "content", None) or ""
        if not content.strip():
            # Reasoning-first misroute: capture reasoning as the raw text; the
            # production parser tolerantly extracts the {...} object from it.
            content = getattr(resp, "reasoning", None) or ""
        return content

    return _judge


# ---------------------------------------------------------------------------
# Scoring — mirrors evaluate_contract in the fake eval, but with the REAL judge
# and NO gold_kind threading (production metadata view only).
# ---------------------------------------------------------------------------


def evaluate_contract_real(
    corpus: dict[str, Any], name: str, spec: dict[str, Any], judge: Any
) -> dict[str, Any]:
    sources = corpus["sources"]
    rows = [dict(s) for s in sources]  # NO gold_kind stashing — production view strips unknowns anyway.

    policy = _FakePolicy(
        opaque=list(spec.get("opaque_eligibility") or []),
        force=dict(spec.get("predicate_force") or {}),
        chash=f"eval-real:{name}",
    )
    plan = build_opaque_eligibility(
        policy, rows, llm=judge,
        fail_open_on_unknown=bool(spec.get("fail_open_on_unknown", True)),
    )

    excluded = set(plan.eligibility_excluded_ids)
    all_urls = [str(s.get("source_url") or s.get("url") or "") for s in sources]
    id_by_url = {str(s.get("source_url") or s.get("url") or ""): s["id"] for s in sources}
    admitted_ids = {id_by_url[u] for u in all_urls if u not in excluded}
    excluded_ids = {id_by_url[u] for u in all_urls if u in excluded}

    gold_admit = set(spec.get("gold_admit_ids") or [])
    gold_exclude = set(spec.get("gold_exclude_ids") or [])

    tp_admit = len(admitted_ids & gold_admit)
    fp_admit = len(admitted_ids & gold_exclude)
    fn_admit = len(excluded_ids & gold_admit)
    ap, ar, af1 = _prf(tp_admit, fp_admit, fn_admit)

    tp_excl = len(excluded_ids & gold_exclude)
    fp_excl = len(excluded_ids & gold_admit)
    fn_excl = len(admitted_ids & gold_exclude)
    ep, er, ef1 = _prf(tp_excl, fp_excl, fn_excl)

    # Human-legible misclassifications.
    cat_by_id = {s["id"]: s.get("category", "") for s in sources}
    title_by_id = {s["id"]: s.get("source_title", "") for s in sources}

    def _describe(ids: list[str]) -> list[dict[str, str]]:
        return [
            {"id": i, "category": cat_by_id.get(i, ""), "title": title_by_id.get(i, "")}
            for i in ids
        ]

    misadmitted = sorted(admitted_ids & gold_exclude)   # should have been excluded but admitted (WORST)
    misexcluded = sorted(excluded_ids & gold_admit)     # good source wrongly dropped

    return {
        "contract": name,
        "n_sources": len(sources),
        "admitted": len(admitted_ids),
        "excluded": len(excluded_ids),
        "admit": {"precision": round(ap, 4), "recall": round(ar, 4), "f1": round(af1, 4)},
        "exclude": {"precision": round(ep, 4), "recall": round(er, 4), "f1": round(ef1, 4)},
        "misadmitted": _describe(misadmitted),
        "misexcluded": _describe(misexcluded),
        "n_receipts": len(plan.receipts),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(_CORPUS))
    ap.add_argument("--contract", default=None, help="run only this contract")
    ap.add_argument("--model", default=_MODEL)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    corpus = json.loads(Path(args.corpus).read_text(encoding="utf-8"))
    contracts = corpus["contracts"]
    names = [args.contract] if args.contract else list(contracts.keys())

    from src.polaris_graph.llm.openrouter_client import OpenRouterClient  # noqa: PLC0415

    client = OpenRouterClient(model=args.model, budget_usd=50.0)
    judge = _make_real_judge(client)

    cost0 = client.usage.total_cost_usd
    calls0 = client.usage.total_calls
    t0 = time.time()

    results = []
    for n in names:
        print(f"[running] {n} ...", file=sys.stderr)
        results.append(evaluate_contract_real(corpus, n, contracts[n], judge))

    elapsed = time.time() - t0
    cost = client.usage.total_cost_usd - cost0
    calls = client.usage.total_calls - calls0
    in_tok = client.usage.total_input_tokens
    out_tok = client.usage.total_output_tokens
    rea_tok = client.usage.total_reasoning_tokens

    summary = {
        "model": args.model,
        "elapsed_s": round(elapsed, 1),
        "llm_calls": calls,
        "cost_usd": round(cost, 4),
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "reasoning_tokens": rea_tok,
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0

    print(f"\nREAL eligibility-judge eval — model={args.model}")
    print(f"  LLM calls={calls}  cost=${cost:.4f}  elapsed={elapsed:.1f}s")
    print(f"  tokens: in={in_tok} out={out_tok} reasoning={rea_tok}\n")
    for r in results:
        print(f"[{r['contract']}]  ({r['n_sources']} sources, {r['n_receipts']} receipts)")
        print(f"  admitted={r['admitted']}  excluded={r['excluded']}")
        print(f"  ADMIT   P={r['admit']['precision']:.3f} R={r['admit']['recall']:.3f} F1={r['admit']['f1']:.3f}")
        print(f"  EXCLUDE P={r['exclude']['precision']:.3f} R={r['exclude']['recall']:.3f} F1={r['exclude']['f1']:.3f}")
        if r["misadmitted"]:
            print("  !! LEAKED (admitted but gold=exclude):")
            for m in r["misadmitted"]:
                print(f"       {m['id']} [{m['category']}] {m['title']}")
        if r["misexcluded"]:
            print("  ~~ WRONGLY DROPPED (excluded but gold=admit):")
            for m in r["misexcluded"]:
                print(f"       {m['id']} [{m['category']}] {m['title']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
