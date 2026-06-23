"""Resume-from-checkpoint query-gen determination — fast metrics (I-qgen-001, GH #1291).

Resumes from the BANKED retrieval cache (the killed run's checkpoints) and scores floor vs
closed-loop with the two fast metrics in qgen_metrics:
  - breadth_recall  (no GLM, instant)         -> "which query-gen retrieves MORE distinct evidence"
  - finding_coverage (digest + parallel judge) -> "which covers MORE required findings"

Both run per task under the SAME equal budget (the floor's natural query count). Default is a
TRUE resume (cache-only, no re-fetch); --allow-fetch fills partially-cached tasks. The blocked
DRB-II source is dropped before scoring (no cheating). Bootstrap over tasks decides the winner.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from scripts.dr_benchmark.gate0_lineage import SLUG_TO_IDX
from scripts.dr_benchmark.qgen_coverage_harness import (
    load_blocked_references,
    load_canonical_question,
    load_required_points,
    make_blocked_filter,
)
from scripts.dr_benchmark.qgen_methods import ClosedLoopMethod, FloorMethod
from scripts.dr_benchmark.qgen_coverage_harness import CoverageBudget
from scripts.dr_benchmark.qgen_metrics import (
    breadth_recall,
    build_digest,
    finding_coverage,
    make_cache_only_retrieve,
)
from scripts.dr_benchmark.run_qgen_coverage import floor_queries, make_glm_llm, make_glm_judge_llm
from scripts.dr_benchmark.run_qgen_determination import DEFAULT_SLUGS, floor_budget, paired_bootstrap

FLOOR = "floor_template_facets"
CLOSED = "closed_loop_gap_requery"


def _build_corpus(method, question, retrieve, budget, is_blocked):
    """Run a method's queries against the (cache-only) retrieve, dropping blocked rows."""
    def filtered(query):
        return [r for r in retrieve(query) if not is_blocked({"url": r.get("url"), "text": r.get("text")})]
    return method.generate_corpus(question, filtered, budget)


def run_task(slug: str, llm, judge_llm, allow_fetch: bool, judge_workers: int,
             floor_only: bool = False, breadth_only: bool = False) -> dict:
    idx = SLUG_TO_IDX[slug]
    question = load_canonical_question(idx)
    points = load_required_points(idx)
    blocked = load_blocked_references(idx)
    is_blocked = make_blocked_filter(blocked)
    budget = CoverageBudget(max_queries=floor_budget(slug, question),
                            max_query_rounds=int(os.getenv("PG_QGEN_MAX_QUERY_ROUNDS", "2")))
    retrieve = make_cache_only_retrieve(domain=None, allow_fetch=allow_fetch)

    out = {"slug": slug, "idx": idx, "required_points": len(points),
           "equal_budget_queries": budget.max_queries, "methods": {}}
    # floor_only resumes PURELY from cache (the floor's queries are deterministic + fully banked).
    # The closed-loop's gap queries are LLM-generated + NOT cached, so it needs live retrieval —
    # a separate fresh experiment, not a cache resume. The closed-loop's decompose/gap calls just
    # LIST search queries, so they get the reasoning-excluded LLM too.
    methods = [(FLOOR, FloorMethod(facets=floor_queries(slug, question)))]
    if not floor_only:
        methods.append((CLOSED, ClosedLoopMethod(llm=judge_llm)))
    for name, method in methods:
        corpus = _build_corpus(method, question, retrieve, budget, is_blocked)
        br = breadth_recall(corpus)
        entry = {"distinct_sources": br.distinct_sources, "distinct_findings": br.distinct_findings,
                 "total_rows": br.total_rows}
        if breadth_only:
            # NO judge — recall breadth only (distinct sources/findings at equal budget). Fast.
            out["methods"][name] = entry
            print(f"[resume] {slug} {name}: sources={br.distinct_sources} "
                  f"findings={br.distinct_findings} (breadth-only)", flush=True)
        else:
            digest = build_digest(corpus)
            fc = finding_coverage(points, digest, judge_llm, workers=judge_workers)
            entry.update({"digest_chars": len(digest), "finding_covered": fc.covered,
                          "finding_total": fc.total, "finding_coverage": fc.coverage})
            out["methods"][name] = entry
            print(f"[resume] {slug} {name}: sources={br.distinct_sources} findings={br.distinct_findings} "
                  f"finding_cov={fc.coverage:.3f} ({fc.covered}/{fc.total})", flush=True)
    if not floor_only:
        f, c = out["methods"][FLOOR], out["methods"][CLOSED]
        out["breadth_delta"] = c["distinct_findings"] - f["distinct_findings"]
        if not breadth_only:
            out["coverage_delta"] = c["finding_coverage"] - f["finding_coverage"]
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Resume query-gen determination from cache (fast metrics)")
    p.add_argument("--slugs", nargs="*", default=DEFAULT_SLUGS)
    p.add_argument("--allow-fetch", action="store_true", help="fill partially-cached tasks (drb_76/78)")
    p.add_argument("--floor-only", action="store_true", help="score only the floor (pure cache resume; closed-loop needs fresh retrieval)")
    p.add_argument("--breadth-only", action="store_true", help="recall breadth only (no GLM judge): distinct sources/findings at equal budget")
    p.add_argument("--judge-workers", type=int, default=8)
    p.add_argument("--bootstrap-iters", type=int, default=10000)
    p.add_argument("--min-effect", type=float, default=0.05)
    p.add_argument("--seed", type=int, default=20260623)
    p.add_argument("--out", default="outputs/qgen_coverage/resume_determination.json")
    args = p.parse_args(argv)

    if os.getenv("PG_QGEN_AUTHORIZED_SPEND") != "1":
        print("[resume] needs PG_QGEN_AUTHORIZED_SPEND=1 (the judge spends). Aborting.", file=sys.stderr)
        return 3

    llm = make_glm_llm()              # closed-loop decompose/gap (reasoning ON)
    judge_llm = make_glm_judge_llm()  # finding-level coverage judge + closed-loop query gen (reasoning-excluded, fast)
    tasks = []
    for slug in args.slugs:
        try:
            tasks.append(run_task(slug, llm, judge_llm, args.allow_fetch, args.judge_workers,
                                   floor_only=args.floor_only, breadth_only=args.breadth_only))
        except Exception as exc:  # fail loud per task, keep the rest
            print(f"[resume] TASK FAILED {slug}: {exc!r}", file=sys.stderr)

    if args.breadth_only and not args.floor_only:
        # Winner by RECALL BREADTH: which query-gen surfaces more distinct findings at equal budget.
        # Bootstrap over tasks on the per-task finding-count delta (closed - floor); no GLM judge.
        find_deltas = [float(t["breadth_delta"]) for t in tasks]
        boot = paired_bootstrap(find_deltas, args.bootstrap_iters, args.seed)
        f_find = sum(t["methods"][FLOOR]["distinct_findings"] for t in tasks)
        c_find = sum(t["methods"][CLOSED]["distinct_findings"] for t in tasks)
        f_src = sum(t["methods"][FLOOR]["distinct_sources"] for t in tasks)
        c_src = sum(t["methods"][CLOSED]["distinct_sources"] for t in tasks)
        if boot["ci_low"] > 0:
            winner = CLOSED
        elif boot["ci_high"] < 0:
            winner = FLOOR
        else:
            winner = "INCONCLUSIVE"
        report = {"slugs": args.slugs, "mode": "breadth_only", "seed": args.seed,
                  "floor_total_distinct_findings": f_find, "closed_total_distinct_findings": c_find,
                  "floor_total_distinct_sources": f_src, "closed_total_distinct_sources": c_src,
                  "finding_delta_bootstrap": boot, "winner_by_breadth": winner, "tasks": tasks}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as h:
            json.dump(report, h, ensure_ascii=False, indent=2)
        print("\n=== BREADTH-ONLY DETERMINATION (distinct-finding recall, no judge) ===")
        for t in tasks:
            f, c = t["methods"][FLOOR], t["methods"][CLOSED]
            print(f"  {t['slug']:<26} findings floor={f['distinct_findings']} closed={c['distinct_findings']} "
                  f"(d={t['breadth_delta']:+d}) | sources floor={f['distinct_sources']} closed={c['distinct_sources']}")
        print(f"  OVERALL distinct findings floor={f_find} closed={c_find} | sources floor={f_src} closed={c_src}")
        print(f"  finding-count paired delta mean={boot['mean']:+.2f} 95% CI [{boot['ci_low']:+.2f},{boot['ci_high']:+.2f}]")
        print(f"  WINNER by breadth: {winner}")
        print(f"[resume] wrote {args.out}")
        return 0

    if args.floor_only:
        f_cov = sum(t["methods"][FLOOR]["finding_coverage"] for t in tasks) / len(tasks) if tasks else 0.0
        f_find = sum(t["methods"][FLOOR]["distinct_findings"] for t in tasks)
        report = {"slugs": args.slugs, "mode": "floor_only",
                  "floor_overall_finding_coverage": f_cov, "floor_total_distinct_findings": f_find,
                  "tasks": tasks}
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as h:
            json.dump(report, h, ensure_ascii=False, indent=2)
        print("\n=== FLOOR (current POLARIS query-gen) — finding-level coverage from cache ===")
        for t in tasks:
            fm = t["methods"][FLOOR]
            print(f"  {t['slug']:<26} {t['required_points']}pts budget={t['equal_budget_queries']}q "
                  f"| sources={fm['distinct_sources']} findings={fm['distinct_findings']} "
                  f"| finding_coverage={fm['finding_coverage']:.3f} ({fm['finding_covered']}/{fm['finding_total']})")
        print(f"  OVERALL floor finding-coverage={f_cov:.3f}  total distinct findings={f_find}")
        print(f"[resume] wrote {args.out}")
        return 0

    # Two rankings: finding-coverage (rubric-grounded) and breadth (raw recall). Winner needs the
    # coverage bootstrap CI to clear the min-effect threshold; breadth is the cross-check.
    cov_deltas = [t["coverage_delta"] for t in tasks]
    boot = paired_bootstrap(cov_deltas, args.bootstrap_iters, args.seed)
    f_cov = sum(t["methods"][FLOOR]["finding_coverage"] for t in tasks) / len(tasks) if tasks else 0.0
    c_cov = sum(t["methods"][CLOSED]["finding_coverage"] for t in tasks) / len(tasks) if tasks else 0.0
    f_find = sum(t["methods"][FLOOR]["distinct_findings"] for t in tasks)
    c_find = sum(t["methods"][CLOSED]["distinct_findings"] for t in tasks)

    if boot["ci_low"] > args.min_effect:
        winner = CLOSED
    elif boot["ci_high"] < -args.min_effect:
        winner = FLOOR
    else:
        winner = "INCONCLUSIVE"

    report = {"slugs": args.slugs, "min_effect": args.min_effect, "seed": args.seed,
              "floor_overall_finding_coverage": f_cov, "closed_overall_finding_coverage": c_cov,
              "floor_total_distinct_findings": f_find, "closed_total_distinct_findings": c_find,
              "coverage_delta_bootstrap": boot, "winner_by_coverage": winner,
              "breadth_winner": (CLOSED if c_find > f_find else FLOOR if f_find > c_find else "TIE"),
              "tasks": tasks}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as h:
        json.dump(report, h, ensure_ascii=False, indent=2)

    print("\n=== RESUME DETERMINATION (fast metrics) ===")
    for t in tasks:
        f, c = t["methods"][FLOOR], t["methods"][CLOSED]
        print(f"  {t['slug']:<26} findings floor={f['distinct_findings']} closed={c['distinct_findings']} "
              f"| coverage floor={f['finding_coverage']:.3f} closed={c['finding_coverage']:.3f} "
              f"(d={t['coverage_delta']:+.3f})")
    print(f"  OVERALL finding-coverage floor={f_cov:.3f} closed={c_cov:.3f}")
    print(f"  OVERALL distinct-findings floor={f_find} closed={c_find} (breadth winner: {report['breadth_winner']})")
    print(f"  coverage paired delta mean={boot['mean']:+.3f} 95% CI [{boot['ci_low']:+.3f},{boot['ci_high']:+.3f}]")
    print(f"  WINNER by coverage: {winner}  (min-effect={args.min_effect})")
    print(f"[resume] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
