"""Query-gen BAKE-OFF: all 10 methods vs the coverage scoreboard (I-qgen-001, GH #1291).

Executes the locked brief: FLOOR (current POLARIS) + the 9 runnable frontier methods (WebWeaver,
IterResearch, ConvergeWriter, WARP, DuMate, FS-Researcher, ScaffoldAgent, PokeeResearch, DOLORES)
— DeepResearch-R1/9K is trained-only, noted-not-faked. Each method generates its queries against
the SHARED retrieve() under an EQUAL query budget, and is scored on COVERAGE = DRB-II info_recall
(finding-level), the operative metric. Highest coverage wins. No end-to-end report, no rendering.

Every method uses the SAME reasoning-excluded GLM-5.2 (query-gen + judge) and the SAME retrieve()
(cache for the floor's deterministic queries, live fetch for the frontier methods' novel queries),
so only the query LOGIC differs. Blocked DRB-II source dropped before scoring (no cheating).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from scripts.dr_benchmark.gate0_lineage import SLUG_TO_IDX
from scripts.dr_benchmark.qgen_coverage_harness import (
    CoverageBudget,
    load_blocked_references,
    load_canonical_question,
    load_required_points,
    make_blocked_filter,
)
from scripts.dr_benchmark.qgen_methods import FloorMethod
from scripts.dr_benchmark.qgen_frontier_methods import build_frontier_methods
from scripts.dr_benchmark.qgen_metrics import breadth_recall, build_digest, finding_coverage, make_cache_only_retrieve
from scripts.dr_benchmark.run_qgen_coverage import floor_queries, make_glm_judge_llm
from scripts.dr_benchmark.run_qgen_determination import floor_budget


def run_task(slug: str, judge_llm, allow_fetch: bool, judge_workers: int) -> dict:
    idx = SLUG_TO_IDX[slug]
    question = load_canonical_question(idx)
    points = load_required_points(idx)
    blocked = load_blocked_references(idx)
    is_blocked = make_blocked_filter(blocked)
    budget = CoverageBudget(max_queries=floor_budget(slug, question),
                            max_query_rounds=int(os.getenv("PG_QGEN_MAX_QUERY_ROUNDS", "3")))
    raw_retrieve = make_cache_only_retrieve(domain=None, allow_fetch=allow_fetch)

    def retrieve(query):
        return [r for r in raw_retrieve(query) if not is_blocked({"url": r.get("url"), "text": r.get("text")})]

    # FLOOR + the 9 frontier methods, all on the reasoning-excluded GLM-5.2.
    methods = [FloorMethod(facets=floor_queries(slug, question), name="floor")] + build_frontier_methods(judge_llm)
    method_workers = int(os.getenv("PG_QGEN_METHOD_WORKERS", "3"))

    def score_method(m) -> dict:
        try:
            corpus = m.generate_corpus(question, retrieve, budget)
            br = breadth_recall(corpus)
            digest = build_digest(corpus)
            fc = finding_coverage(points, digest, judge_llm, workers=judge_workers)
            row = {"method": m.name, "finding_coverage": fc.coverage, "finding_covered": fc.covered,
                   "finding_total": fc.total, "distinct_sources": br.distinct_sources,
                   "distinct_findings": br.distinct_findings, "n_queries": getattr(m, "_n_queries", None)}
        except Exception as exc:  # fail loud per method, keep the rest
            row = {"method": m.name, "error": repr(exc), "finding_coverage": -1.0}
        fc_v = row.get("finding_coverage")
        print(f"[bakeoff] {slug} {m.name:<15} coverage={fc_v:.3f} "
              f"sources={row.get('distinct_sources','?')} findings={row.get('distinct_findings','?')} "
              f"q={row.get('n_queries','?')}", flush=True)
        return row

    # Methods are independent -> run them concurrently (bounded, to avoid a fetch storm).
    results = []
    with ThreadPoolExecutor(max_workers=method_workers) as ex:
        futs = {ex.submit(score_method, m): m.name for m in methods}
        for fut in as_completed(futs):
            results.append(fut.result())

    results.sort(key=lambda r: r.get("finding_coverage", -1), reverse=True)
    return {"slug": slug, "idx": idx, "required_points": len(points),
            "equal_budget_queries": budget.max_queries, "ranking": results}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Query-gen bake-off: 10 methods vs DRB-II info_recall coverage")
    p.add_argument("--slugs", nargs="*", default=["drb_72_ai_labor"])
    p.add_argument("--allow-fetch", action="store_true", default=True)
    p.add_argument("--no-fetch", dest="allow_fetch", action="store_false")
    p.add_argument("--judge-workers", type=int, default=8)
    p.add_argument("--out", default="outputs/qgen_coverage/bakeoff.json")
    args = p.parse_args(argv)

    if os.getenv("PG_QGEN_AUTHORIZED_SPEND") != "1":
        print("[bakeoff] needs PG_QGEN_AUTHORIZED_SPEND=1 (the bake-off spends). Aborting.", file=sys.stderr)
        return 3

    judge_llm = make_glm_judge_llm()  # reasoning-excluded GLM-5.2: query-gen + coverage judge
    tasks = []
    for slug in args.slugs:
        try:
            tasks.append(run_task(slug, judge_llm, args.allow_fetch, args.judge_workers))
        except Exception as exc:
            print(f"[bakeoff] TASK FAILED {slug}: {exc!r}", file=sys.stderr)

    # Overall ranking: mean coverage per method across tasks.
    by_method: dict[str, list[float]] = {}
    for t in tasks:
        for r in t["ranking"]:
            if r.get("finding_coverage", -1) >= 0:
                by_method.setdefault(r["method"], []).append(r["finding_coverage"])
    overall = sorted(((m, sum(v) / len(v)) for m, v in by_method.items()), key=lambda x: x[1], reverse=True)

    report = {"slugs": args.slugs, "tasks": tasks,
              "overall_mean_coverage": [{"method": m, "mean_coverage": c} for m, c in overall],
              "winner": overall[0][0] if overall else None}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as h:
        json.dump(report, h, ensure_ascii=False, indent=2)

    print("\n=== BAKE-OFF: query-gen methods ranked by DRB-II info_recall coverage ===")
    for rank, (m, c) in enumerate(overall, 1):
        print(f"  #{rank:<2} {m:<15} mean_coverage={c:.3f}")
    print(f"  WINNER: {report['winner']}")
    print(f"[bakeoff] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
