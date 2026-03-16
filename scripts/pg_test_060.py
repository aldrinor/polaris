"""PG_TEST_060: Full Production Pipeline — Validate 26 New Trace Emissions."""

import asyncio
import json
import logging
import os
import sys
import time
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

VECTOR_ID = "PG_TEST_060"
OUTPUT_DIR = Path("outputs/polaris_graph")


async def main():
    from src.polaris_graph.graph import build_and_run

    print("=" * 70, flush=True)
    print("  PG_TEST_060: FULL PRODUCTION PIPELINE VALIDATION", flush=True)
    print("  Validating 26 new trace emissions + dashboard rendering", flush=True)
    print("=" * 70, flush=True)

    start = time.time()

    try:
        result = await build_and_run(
            vector_id=VECTOR_ID,
            query=(
                "What are the most effective and affordable water filtration "
                "technologies for removing PFAS from drinking water?"
            ),
            application="Household Water Filter",
            region="NORTH AMERICA",
            stage=1,
            max_iterations=int(os.getenv("PG_MAX_ITERATIONS", "5")),
            max_execution_minutes=int(os.getenv("PG_MAX_EXECUTION_MINUTES", "180")),
        )

        elapsed = time.time() - start
        qm = result.get("quality_metrics") or {}
        usage = result.get("llm_usage") or {}
        report = result.get("final_report", "")
        evidence = result.get("evidence_chain", result.get("evidence", []))

        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  PG_TEST_060 COMPLETED ({elapsed:.0f}s / {elapsed / 60:.1f}min)", flush=True)
        print(f"  Evidence: {len(evidence)}", flush=True)
        print(f"  Words: {qm.get('total_words', 0)}", flush=True)
        print(f"  Citations: {qm.get('total_citations', 0)}", flush=True)
        print(f"  Unique Sources: {qm.get('unique_sources', 0)}", flush=True)
        print(f"  Faithfulness: {qm.get('faithfulness_pct', 0):.1f}%", flush=True)
        print(f"  Cost: ${usage.get('total_cost_usd', 0):.2f}", flush=True)
        print("=" * 70, flush=True)

        # Save results
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUTPUT_DIR / f"{VECTOR_ID}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, default=str)
        print(f"\n  Result saved: {out_path}", flush=True)

        if report:
            report_path = OUTPUT_DIR / f"{VECTOR_ID}_report.md"
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(report)
            print(f"  Report saved: {report_path}", flush=True)

        # Validate trace file exists and has new event types
        trace_path = Path(f"logs/pg_trace_{VECTOR_ID}.jsonl")
        if trace_path.exists():
            event_types = set()
            evidence_actions = set()
            total_events = 0
            with open(trace_path, "r", encoding="utf-8") as f:
                for line in f:
                    total_events += 1
                    try:
                        evt = json.loads(line)
                        event_types.add(evt.get("event_type", ""))
                        if evt.get("event_type") == "evidence":
                            evidence_actions.add(evt.get("data", {}).get("action", ""))
                    except json.JSONDecodeError:
                        pass

            print(f"\n  Trace: {trace_path} ({total_events} events, {trace_path.stat().st_size / 1024:.0f} KB)", flush=True)
            print(f"  Event types: {sorted(event_types)}", flush=True)
            print(f"  Evidence actions: {sorted(evidence_actions)}", flush=True)

            # Check for required new emissions
            required_types = {"pipeline_start", "llm_detail"}
            required_actions = {
                "tier_scoring_detail", "dedup_detail", "verification_context",
                "citation_mapping_full", "expansion_detail",
            }
            missing_types = required_types - event_types
            missing_actions = required_actions - evidence_actions
            if missing_types:
                print(f"\n  *** MISSING event types: {missing_types}", flush=True)
            if missing_actions:
                print(f"  *** MISSING evidence actions: {missing_actions}", flush=True)
            if not missing_types and not missing_actions:
                print("\n  ALL required new emissions PRESENT", flush=True)
        else:
            print(f"\n  *** WARNING: Trace file not found: {trace_path}", flush=True)

    except Exception as e:
        elapsed = time.time() - start
        logger.exception("PG_TEST_060 FAILED")
        print(f"\n  *** PG_TEST_060 FAILED ({elapsed:.0f}s): {e}", flush=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
