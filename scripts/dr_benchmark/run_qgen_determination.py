"""Query-gen WINNER-DETERMINATION orchestrator (I-qgen-001, GH #1291).

The single-task `run_qgen_coverage` proves coverage on ONE task; it does NOT determine the winner.
A real determination (operator directive 2026-06-23) needs three things the single run lacks:

1. EQUAL BUDGET = the floor's OWN natural query count, per task. The floor for drb_72 fires 35
   queries (20 hand-authored amplified + 14 decomposed + anchor); an arbitrary cap (e.g. 24) would
   silently cripple it (the Codex iter-1 P1-6 failure). Both methods get the SAME cap = the floor's
   count, so the comparison isolates query QUALITY (whose N queries cover more), not query COUNT.
2. ALL rubric-backed DRB-II tasks (idx 56/62/66/72), not one — one task is one data point.
3. RERUNS (the GLM judge + closed-loop LLM are stochastic) + a paired bootstrap with a minimum-effect
   threshold, so the winner clears noise. Reruns reuse CACHED retrieval (retrieval keyed by query),
   so only the stochastic parts re-run — the heavy fetch is one-time per task.

Faithfulness is untouched; this scores COVERAGE only. Retrieval + judge are the APPROVED harness
(run_qgen_coverage helpers + qgen_coverage_harness). Spend-gated behind PG_QGEN_AUTHORIZED_SPEND=1.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.dr_benchmark.gate0_lineage import SLUG_TO_IDX
from scripts.dr_benchmark.qgen_coverage_harness import (
    CoverageBudget,
    load_blocked_references,
    load_canonical_question,
    run_coverage_test,
)
from scripts.dr_benchmark.qgen_methods import ClosedLoopMethod, FloorMethod
from scripts.dr_benchmark.run_qgen_coverage import (
    floor_queries,
    make_glm_coverage_judge,
    make_glm_llm,
    make_real_retrieve,
)

# The 4 DRB-II tasks that carry an info_recall rubric (drb_90 has no gold task -> excluded).
DEFAULT_SLUGS = [
    "drb_72_ai_labor",
    "drb_75_metal_ions_cvd",
    "drb_76_gut_microbiota_crc",
    "drb_78_parkinsons_dbs",
]
FLOOR = "floor_template_facets"
CLOSED = "closed_loop_gap_requery"


def floor_budget(slug: str, question: str) -> int:
    """Equal budget for a task = the floor's natural query count (its facets + the anchor)."""
    return len(floor_queries(slug, question)) + 1


def run_one_task(slug: str, reruns: int, domain: str | None) -> dict:
    """Run BOTH methods on one task `reruns` times under the floor's equal budget.

    Each task constructs its OWN retrieve/judge/llm (per-thread isolation — no shared client).
    Retrieval is cached by query, so reruns re-run only the stochastic judge + closed-loop LLM.
    """
    idx = SLUG_TO_IDX[slug]
    question = load_canonical_question(idx)
    blocked = load_blocked_references(idx)
    budget_n = floor_budget(slug, question)
    facets = floor_queries(slug, question)

    retrieve = make_real_retrieve(domain=domain)
    judge = make_glm_coverage_judge()
    llm = make_glm_llm()
    # Equal cap = floor count; give the closed loop enough rounds to spend that budget adaptively.
    budget = CoverageBudget(max_queries=budget_n, max_query_rounds=int(os.getenv("PG_QGEN_MAX_QUERY_ROUNDS", "5")))

    per_rerun: list[dict] = []
    for r in range(reruns):
        methods = [FloorMethod(facets=facets), ClosedLoopMethod(llm=llm)]
        results = run_coverage_test(idx, methods, retrieve, judge, budget=budget, blocked_refs=blocked)
        by = {x.method: x for x in results}
        per_rerun.append(
            {
                "rerun": r,
                "floor_coverage": by[FLOOR].coverage,
                "closed_coverage": by[CLOSED].coverage,
                "floor_covered": by[FLOOR].covered,
                "closed_covered": by[CLOSED].covered,
                "total": by[FLOOR].total,
                "floor_queries": by[FLOOR].n_queries_issued,
                "closed_queries": by[CLOSED].n_queries_issued,
                "floor_blocked_dropped": by[FLOOR].blocked_dropped,
                "closed_blocked_dropped": by[CLOSED].blocked_dropped,
            }
        )
        print(
            f"[determine] {slug} rerun {r+1}/{reruns}: floor={by[FLOOR].coverage:.3f} "
            f"closed={by[CLOSED].coverage:.3f} (budget={budget_n}q)",
            flush=True,
        )

    floor_mean = sum(x["floor_coverage"] for x in per_rerun) / len(per_rerun)
    closed_mean = sum(x["closed_coverage"] for x in per_rerun) / len(per_rerun)
    return {
        "slug": slug,
        "idx": idx,
        "required_points": per_rerun[0]["total"],
        "equal_budget_queries": budget_n,
        "floor_mean_coverage": floor_mean,
        "closed_mean_coverage": closed_mean,
        "delta_mean": closed_mean - floor_mean,
        "per_rerun": per_rerun,
    }


def paired_bootstrap(deltas: list[float], iters: int, seed: int) -> dict:
    """Bootstrap CI of the mean paired delta (closed - floor). The independent unit is the TASK;
    we resample the per-task mean deltas with replacement. Honest about small N (4 tasks)."""
    rng = random.Random(seed)
    n = len(deltas)
    if n == 0:
        return {"mean": 0.0, "ci_low": 0.0, "ci_high": 0.0, "n": 0}
    means = []
    for _ in range(iters):
        sample = [deltas[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo = means[int(0.025 * len(means))]
    hi = means[int(0.975 * len(means)) - 1] if len(means) > 1 else means[-1]
    return {"mean": sum(deltas) / n, "ci_low": lo, "ci_high": hi, "n": n}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Query-gen winner determination (4 tasks, equal budget, reruns, bootstrap)")
    p.add_argument("--slugs", nargs="*", default=DEFAULT_SLUGS)
    p.add_argument("--reruns", type=int, default=3)
    p.add_argument("--workers", type=int, default=2, help="tasks run in parallel (I/O bound)")
    p.add_argument("--bootstrap-iters", type=int, default=10000)
    p.add_argument("--min-effect", type=float, default=0.05, help="min coverage delta to call a winner")
    p.add_argument("--seed", type=int, default=20260623)
    p.add_argument("--out", default="outputs/qgen_coverage/determination.json")
    args = p.parse_args(argv)

    if os.getenv("PG_QGEN_AUTHORIZED_SPEND") != "1":
        print("[determine] needs PG_QGEN_AUTHORIZED_SPEND=1 (operator spend gate). Aborting.", file=sys.stderr)
        return 3

    print(f"[determine] {len(args.slugs)} tasks x {args.reruns} reruns, {args.workers} parallel, equal budget = floor count/task")
    tasks: list[dict] = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(run_one_task, s, args.reruns, None): s for s in args.slugs}
        for fut in as_completed(futs):
            slug = futs[fut]
            try:
                tasks.append(fut.result())
            except Exception as exc:  # fail LOUD per task, keep the others
                print(f"[determine] TASK FAILED {slug}: {exc!r}", file=sys.stderr)

    tasks.sort(key=lambda t: t["slug"])
    deltas = [t["delta_mean"] for t in tasks]
    boot = paired_bootstrap(deltas, args.bootstrap_iters, args.seed)
    floor_overall = sum(t["floor_mean_coverage"] for t in tasks) / len(tasks) if tasks else 0.0
    closed_overall = sum(t["closed_mean_coverage"] for t in tasks) / len(tasks) if tasks else 0.0

    # Winner: the higher-coverage method, IFF the paired bootstrap CI clears the min-effect threshold
    # in its favor. Otherwise INCONCLUSIVE (do not crown a winner on noise).
    if boot["ci_low"] > args.min_effect:
        winner = CLOSED
    elif boot["ci_high"] < -args.min_effect:
        winner = FLOOR
    else:
        winner = "INCONCLUSIVE"

    report = {
        "slugs": args.slugs,
        "reruns": args.reruns,
        "min_effect": args.min_effect,
        "seed": args.seed,
        "floor_overall_coverage": floor_overall,
        "closed_overall_coverage": closed_overall,
        "paired_delta_bootstrap": boot,
        "winner": winner,
        "tasks": tasks,
        "note": "Independent unit = task (N tasks). Small-N caveat: DRB-II has 4 rubric-backed tasks.",
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as h:
        json.dump(report, h, ensure_ascii=False, indent=2)

    print("\n=== DETERMINATION ===")
    for t in tasks:
        print(f"  {t['slug']:<26} floor={t['floor_mean_coverage']:.3f} closed={t['closed_mean_coverage']:.3f} "
              f"delta={t['delta_mean']:+.3f} (budget={t['equal_budget_queries']}q, {t['required_points']}pts)")
    print(f"  OVERALL floor={floor_overall:.3f} closed={closed_overall:.3f}")
    print(f"  paired delta mean={boot['mean']:+.3f} 95% CI [{boot['ci_low']:+.3f}, {boot['ci_high']:+.3f}] (n={boot['n']} tasks)")
    print(f"  WINNER: {winner}  (min-effect={args.min_effect})")
    print(f"[determine] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
