"""PG Faithfulness Validation (1C.2): Run 5 diverse queries, verify >90% faithfulness on ALL.

Validates faithfulness consistency across different research domains:
  FV-01: Silver nanoparticle antimicrobial water filtration (Benchmark Q1 — science/contradiction)
  FV-02: Copper-alloy antimicrobial surfaces for HAI reduction (Benchmark Q8 — clinical/RCT)
  FV-03: AMR policy recommendations for Canada (Benchmark Q10 — policy/multi-country)
  FV-04: Microplastics in drinking water (non-benchmark — environmental science)
  FV-05: Sleep deprivation and cognitive performance (non-benchmark — health/neuroscience)

Features:
  - Checkpointed: resume by re-running (skips completed queries)
  - Per-query result tracking in outputs/polaris_graph/faithfulness_validation.json
  - Final summary with PASS/FAIL verdict per query and overall

Usage:
  python scripts/pg_faithfulness_validation.py                # Run all pending
  python scripts/pg_faithfulness_validation.py --query FV-03   # Run single query
  python scripts/pg_faithfulness_validation.py --summary       # Print summary only
"""

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("logs/polaris_graph.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs/polaris_graph")
RESULTS_FILE = OUTPUT_DIR / "faithfulness_validation.json"
FAITHFULNESS_THRESHOLD = 90.0

# ---------------------------------------------------------------------------
# 5 Diverse Queries
# ---------------------------------------------------------------------------
QUERIES = {
    "FV-01": {
        "query": (
            "What is the current scientific consensus on the effectiveness of silver "
            "nanoparticle coatings for antimicrobial water filtration, and where do "
            "peer-reviewed studies disagree on long-term efficacy, environmental impact, "
            "and regulatory safety thresholds?"
        ),
        "application": "Scientific Contradiction Analysis",
        "region": "GLOBAL",
        "source": "Benchmark Q1",
        "domain": "Materials Science / Water Treatment",
    },
    "FV-02": {
        "query": (
            "Synthesize the clinical evidence for copper-alloy antimicrobial surfaces "
            "in reducing healthcare-associated infections (HAIs), including all "
            "randomized controlled trials published since 2015, their sample sizes, "
            "primary endpoints, effect sizes, hospital settings, pathogen coverage, "
            "cost-effectiveness analyses, and the current Cochrane or systematic "
            "review conclusions."
        ),
        "application": "Clinical Evidence Synthesis",
        "region": "GLOBAL",
        "source": "Benchmark Q8",
        "domain": "Clinical Medicine / Infection Control",
    },
    "FV-03": {
        "query": (
            "Based on evidence from successful national antimicrobial resistance (AMR) "
            "action plans in the UK, Sweden, Australia, and Netherlands, what policy "
            "recommendations should Canada adopt for antimicrobial surface regulations "
            "in healthcare facilities? For each recommendation, provide the evidence "
            "base from comparator countries, expected effectiveness metrics, "
            "implementation cost estimates, and realistic timeline."
        ),
        "application": "Evidence-Based Policy Analysis",
        "region": "GLOBAL",
        "source": "Benchmark Q10",
        "domain": "Public Health Policy / AMR",
    },
    "FV-04": {
        "query": (
            "What are the environmental and health impacts of microplastics in "
            "drinking water systems, including current detection methods, concentration "
            "levels measured in municipal water supplies worldwide, proven filtration "
            "technologies with removal efficiency data from peer-reviewed studies, "
            "and regulatory standards established or proposed by WHO, EPA, and EU?"
        ),
        "application": "Environmental Health Research",
        "region": "GLOBAL",
        "source": "Non-benchmark (environmental science)",
        "domain": "Environmental Science / Public Health",
    },
    "FV-05": {
        "query": (
            "What is the current evidence on the dose-response relationship between "
            "sleep deprivation and cognitive performance in adults, including effects "
            "on working memory, attention, decision-making, and emotional regulation, "
            "with specific findings from randomized controlled trials, meta-analyses, "
            "and neuroimaging studies published since 2018?"
        ),
        "application": "Neuroscience Evidence Synthesis",
        "region": "GLOBAL",
        "source": "Non-benchmark (neuroscience)",
        "domain": "Neuroscience / Cognitive Psychology",
    },
}


def load_results() -> dict:
    """Load existing results or create empty structure."""
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "validation_id": "1C.2_faithfulness_validation",
        "threshold": FAITHFULNESS_THRESHOLD,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries": {},
    }


def save_results(results: dict) -> None:
    """Save results atomically."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = RESULTS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)
    tmp.replace(RESULTS_FILE)


def print_summary(results: dict) -> None:
    """Print summary table of all completed queries."""
    print("\n" + "=" * 80, flush=True)
    print("  FAITHFULNESS VALIDATION SUMMARY (1C.2)", flush=True)
    print(f"  Threshold: >= {FAITHFULNESS_THRESHOLD}%", flush=True)
    print("=" * 80, flush=True)

    all_pass = True
    completed = 0
    total_cost = 0.0

    print(f"\n  {'ID':<8} {'Domain':<40} {'Faith%':>8} {'Words':>7} "
          f"{'Cites':>6} {'Srcs':>5} {'Time':>7} {'Cost':>7} {'Result':>8}", flush=True)
    print(f"  {'-' * 8} {'-' * 40} {'-' * 8} {'-' * 7} "
          f"{'-' * 6} {'-' * 5} {'-' * 7} {'-' * 7} {'-' * 8}", flush=True)

    for qid in sorted(QUERIES.keys()):
        qr = results.get("queries", {}).get(qid)
        domain = QUERIES[qid]["domain"][:40]
        if qr and qr.get("status") == "completed":
            completed += 1
            faith = qr.get("faithfulness_pct", 0)
            words = qr.get("total_words", 0)
            cites = qr.get("total_citations", 0)
            srcs = qr.get("unique_sources", 0)
            elapsed_min = qr.get("elapsed_seconds", 0) / 60
            cost = qr.get("cost_usd", 0)
            total_cost += cost
            passed = faith >= FAITHFULNESS_THRESHOLD
            if not passed:
                all_pass = False
            verdict = "PASS" if passed else "FAIL"
            print(f"  {qid:<8} {domain:<40} {faith:>7.1f}% {words:>7} "
                  f"{cites:>6} {srcs:>5} {elapsed_min:>6.1f}m ${cost:>6.2f} "
                  f"{'  ' + verdict:>8}", flush=True)
        elif qr and qr.get("status") == "failed":
            all_pass = False
            err = qr.get("error", "unknown")[:30]
            print(f"  {qid:<8} {domain:<40} {'ERROR':>8} {'-':>7} "
                  f"{'-':>6} {'-':>5} {'-':>7} {'-':>7} {'  FAIL':>8}", flush=True)
            print(f"           Error: {err}", flush=True)
        else:
            print(f"  {qid:<8} {domain:<40} {'PENDING':>8} {'-':>7} "
                  f"{'-':>6} {'-':>5} {'-':>7} {'-':>7} {'     -':>8}", flush=True)

    print(f"\n  Completed: {completed}/{len(QUERIES)}", flush=True)
    print(f"  Total cost: ${total_cost:.2f}", flush=True)

    if completed == len(QUERIES):
        overall = "PASS" if all_pass else "FAIL"
        print(f"\n  {'=' * 50}", flush=True)
        print(f"  OVERALL VERDICT: {overall}", flush=True)
        print(f"  {'=' * 50}", flush=True)
    else:
        print(f"\n  {len(QUERIES) - completed} queries remaining.", flush=True)


async def run_query(qid: str, qdef: dict, results: dict) -> dict:
    """Run a single query through the pipeline and record results."""
    from src.polaris_graph.graph import build_and_run

    print("\n" + "=" * 70, flush=True)
    print(f"  {qid}: {qdef['domain']}", flush=True)
    print(f"  Source: {qdef['source']}", flush=True)
    print(f"  Query: {qdef['query'][:100]}...", flush=True)
    print("=" * 70, flush=True)

    start = time.time()
    max_iters = int(os.getenv("PG_MAX_ITERATIONS", "5"))
    max_mins = int(os.getenv("PG_MAX_EXECUTION_MINUTES", "180"))

    try:
        result = await build_and_run(
            vector_id=qid,
            query=qdef["query"],
            application=qdef["application"],
            region=qdef["region"],
            stage=1,
            max_iterations=max_iters,
            max_execution_minutes=max_mins,
        )

        elapsed = time.time() - start
        qm = result.get("quality_metrics") or {}
        usage = result.get("llm_usage") or {}
        report = result.get("final_report", "")
        evidence = result.get("evidence_chain", result.get("evidence", []))
        sections = result.get("sections", result.get("report_sections", []))
        bibliography = result.get("bibliography", [])

        total_words = qm.get("total_words", 0)
        total_citations = qm.get("total_citations", 0)
        unique_sources = qm.get("unique_sources", 0)
        faithfulness_pct = qm.get(
            "faithfulness_pct", qm.get("faithfulness_score", 0) * 100
        )
        cost = usage.get("total_cost_usd", 0)

        # Tier distribution
        tier_counts = {"GOLD": 0, "SILVER": 0, "BRONZE": 0, "UNVERIFIED": 0}
        for ev in evidence:
            tier = ev.get("quality_tier", "UNVERIFIED")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1

        entry = {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "query": qdef["query"],
            "domain": qdef["domain"],
            "source": qdef["source"],
            "faithfulness_pct": faithfulness_pct,
            "total_words": total_words,
            "total_citations": total_citations,
            "unique_sources": unique_sources,
            "evidence_count": len(evidence),
            "section_count": len(sections),
            "bibliography_count": len(bibliography),
            "tier_distribution": tier_counts,
            "elapsed_seconds": elapsed,
            "cost_usd": cost,
            "passed": faithfulness_pct >= FAITHFULNESS_THRESHOLD,
            "output_file": str(OUTPUT_DIR / f"{qid}.json"),
            "report_file": str(OUTPUT_DIR / f"{qid}_report.md"),
        }

        # Save full result
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_DIR / f"{qid}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        if report:
            with open(OUTPUT_DIR / f"{qid}_report.md", "w", encoding="utf-8") as f:
                f.write(report)

        print(f"\n  {qid} COMPLETED ({elapsed:.0f}s / {elapsed / 60:.1f}min)", flush=True)
        print(f"  Faithfulness: {faithfulness_pct:.1f}%", flush=True)
        print(f"  Words: {total_words} | Citations: {total_citations} | Sources: {unique_sources}", flush=True)
        print(f"  Evidence: {len(evidence)} | Tiers: {tier_counts}", flush=True)
        print(f"  Cost: ${cost:.2f}", flush=True)
        verdict = "PASS" if faithfulness_pct >= FAITHFULNESS_THRESHOLD else "FAIL"
        print(f"  Verdict: {verdict} (threshold: {FAITHFULNESS_THRESHOLD}%)", flush=True)

        return entry

    except Exception as e:
        elapsed = time.time() - start
        logger.exception(f"{qid} FAILED")
        entry = {
            "status": "failed",
            "failed_at": datetime.now(timezone.utc).isoformat(),
            "query": qdef["query"],
            "domain": qdef["domain"],
            "source": qdef["source"],
            "error": str(e),
            "elapsed_seconds": elapsed,
            "passed": False,
        }
        print(f"\n  *** {qid} FAILED ({elapsed:.0f}s): {e}", flush=True)
        return entry


async def main():
    parser = argparse.ArgumentParser(description="POLARIS Faithfulness Validation (1C.2)")
    parser.add_argument("--query", type=str, help="Run single query by ID (e.g., FV-03)")
    parser.add_argument("--summary", action="store_true", help="Print summary only")
    args = parser.parse_args()

    results = load_results()

    if args.summary:
        print_summary(results)
        return

    # Determine which queries to run
    if args.query:
        qid = args.query.upper()
        if qid not in QUERIES:
            print(f"Unknown query ID: {qid}. Valid: {sorted(QUERIES.keys())}")
            sys.exit(1)
        pending = [qid]
    else:
        pending = [
            qid for qid in sorted(QUERIES.keys())
            if qid not in results.get("queries", {})
            or results["queries"][qid].get("status") not in ("completed",)
        ]

    if not pending:
        print("All queries completed. Use --summary to view results.")
        print_summary(results)
        return

    print("=" * 70, flush=True)
    print("  POLARIS FAITHFULNESS VALIDATION (1C.2)", flush=True)
    print(f"  Queries to run: {pending}", flush=True)
    print(f"  Threshold: >= {FAITHFULNESS_THRESHOLD}%", flush=True)
    print(f"  Max iterations: {os.getenv('PG_MAX_ITERATIONS', '5')}", flush=True)
    print(f"  Max minutes: {os.getenv('PG_MAX_EXECUTION_MINUTES', '180')}", flush=True)
    print("=" * 70, flush=True)

    for qid in pending:
        qdef = QUERIES[qid]
        entry = await run_query(qid, qdef, results)
        results["queries"][qid] = entry
        save_results(results)
        print(f"\n  Checkpoint saved to {RESULTS_FILE}", flush=True)

    results["completed_at"] = datetime.now(timezone.utc).isoformat()
    save_results(results)
    print_summary(results)


if __name__ == "__main__":
    asyncio.run(main())
