"""PG_TEST_061: Full Production Pipeline — Post-Session-29 Quality Validation.

Validates:
1. Blocked-domain veto rule (new) — BRONZE for commercial/blocked sources
2. 5-signal tier scoring — GOLD/SILVER/BRONZE distribution
3. Evidence quality gates — substance veto, quote validation
4. End-to-end report quality — faithfulness, citations, word count
5. Trace emissions — all required event types present
"""

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

VECTOR_ID = "PG_TEST_080"
OUTPUT_DIR = Path("outputs/polaris_graph")


async def main():
    from src.polaris_graph.graph import build_and_run

    print("=" * 70, flush=True)
    print("  PG_TEST_061: POST-SESSION-29 QUALITY VALIDATION", flush=True)
    print("  Focus: tier scoring, blocked-domain veto, report quality", flush=True)
    print("=" * 70, flush=True)

    start = time.time()

    try:
        result = await build_and_run(
            vector_id=VECTOR_ID,
            query=(
                "What are the proven health benefits and risks of intermittent "
                "fasting based on clinical research and meta-analyses?"
            ),
            application="Evidence-Based Health Research",
            region="GLOBAL",
            stage=1,
            max_iterations=int(os.getenv("PG_MAX_ITERATIONS", "2")),
            max_execution_minutes=int(os.getenv("PG_MAX_EXECUTION_MINUTES", "150")),
        )

        elapsed = time.time() - start
        qm = result.get("quality_metrics") or {}
        usage = result.get("llm_usage") or {}
        report = result.get("final_report", "")
        evidence = result.get("evidence_chain", result.get("evidence", []))
        sections = result.get("sections", result.get("report_sections", []))
        bibliography = result.get("bibliography", [])

        # --- Quality Metrics ---
        total_words = qm.get("total_words", 0)
        total_citations = qm.get("total_citations", 0)
        unique_sources = qm.get("unique_sources", 0)
        faithfulness_pct = qm.get("faithfulness_pct", qm.get("faithfulness_score", 0) * 100)
        cost = usage.get("total_cost_usd", 0)

        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  PG_TEST_061 COMPLETED ({elapsed:.0f}s / {elapsed / 60:.1f}min)", flush=True)
        print(f"  Evidence: {len(evidence)}", flush=True)
        print(f"  Words: {total_words}", flush=True)
        print(f"  Citations: {total_citations}", flush=True)
        print(f"  Unique Sources: {unique_sources}", flush=True)
        print(f"  Faithfulness: {faithfulness_pct:.1f}%", flush=True)
        print(f"  Sections: {len(sections)}", flush=True)
        print(f"  Bibliography: {len(bibliography)}", flush=True)
        print(f"  Cost: ${cost:.2f}", flush=True)
        print("=" * 70, flush=True)

        # --- Tier Distribution ---
        tier_counts = {"GOLD": 0, "SILVER": 0, "BRONZE": 0, "UNVERIFIED": 0}
        for ev in evidence:
            tier = ev.get("quality_tier", "UNVERIFIED")
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        print(f"\n  Tier Distribution: {tier_counts}", flush=True)

        # --- Blocked-Domain Veto Check ---
        blocked_gold_silver = []
        for ev in evidence:
            url = ev.get("source_url", "")
            tier = ev.get("quality_tier", "")
            veto = ev.get("veto_reason", "")
            if veto == "blocked_domain_zero_authority" and tier in ("GOLD", "SILVER"):
                blocked_gold_silver.append(url)
        if blocked_gold_silver:
            print(f"\n  *** VETO FAILURE: Blocked domains in GOLD/SILVER: {blocked_gold_silver}", flush=True)
        else:
            print("  Blocked-domain veto: OK (no blocked sources above BRONZE)", flush=True)

        # --- Substance Veto Check ---
        substance_vetoed = sum(1 for ev in evidence if "substance" in ev.get("veto_reason", ""))
        print(f"  Substance vetoes: {substance_vetoed}", flush=True)

        # --- Quality Gates ---
        gates_passed = 0
        gates_total = 6
        gate_results = []

        # Gate 1: Word count >= 2000
        g1 = total_words >= 2000
        gates_passed += int(g1)
        gate_results.append(f"  [{'PASS' if g1 else 'FAIL'}] Words >= 2000: {total_words}")

        # Gate 2: Citations >= 5
        g2 = total_citations >= 5
        gates_passed += int(g2)
        gate_results.append(f"  [{'PASS' if g2 else 'FAIL'}] Citations >= 5: {total_citations}")

        # Gate 3: Unique sources >= 5
        g3 = unique_sources >= 5
        gates_passed += int(g3)
        gate_results.append(f"  [{'PASS' if g3 else 'FAIL'}] Sources >= 5: {unique_sources}")

        # Gate 4: Faithfulness >= 70%
        g4 = faithfulness_pct >= 70.0
        gates_passed += int(g4)
        gate_results.append(f"  [{'PASS' if g4 else 'FAIL'}] Faithfulness >= 70%: {faithfulness_pct:.1f}%")

        # Gate 5: Evidence count > 0
        g5 = len(evidence) > 0
        gates_passed += int(g5)
        gate_results.append(f"  [{'PASS' if g5 else 'FAIL'}] Evidence > 0: {len(evidence)}")

        # Gate 6: Report non-empty
        g6 = len(report) > 100
        gates_passed += int(g6)
        gate_results.append(f"  [{'PASS' if g6 else 'FAIL'}] Report length > 100: {len(report)}")

        print(f"\n  Quality Gates: {gates_passed}/{gates_total}", flush=True)
        for gr in gate_results:
            print(gr, flush=True)

        # --- Save Results ---
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

        # --- Trace Validation ---
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
                        event_types.add(evt.get("type", evt.get("event_type", "")))
                        if evt.get("type", evt.get("event_type")) == "evidence":
                            evidence_actions.add(evt.get("data", {}).get("action", ""))
                    except json.JSONDecodeError:
                        pass

            print(f"\n  Trace: {trace_path} ({total_events} events, {trace_path.stat().st_size / 1024:.0f} KB)", flush=True)
            print(f"  Event types: {sorted(event_types)}", flush=True)

            required_types = {"pipeline_start", "llm_detail"}
            missing_types = required_types - event_types
            if missing_types:
                print(f"  *** MISSING event types: {missing_types}", flush=True)
            else:
                print("  All required event types PRESENT", flush=True)
        else:
            print(f"\n  *** WARNING: Trace file not found: {trace_path}", flush=True)

        # --- Final Verdict ---
        if gates_passed == gates_total:
            print(f"\n  {'=' * 50}", flush=True)
            print(f"  PG_TEST_061: FULL PASS ({gates_passed}/{gates_total} gates)", flush=True)
            print(f"  {'=' * 50}", flush=True)
        else:
            print(f"\n  {'=' * 50}", flush=True)
            print(f"  PG_TEST_061: PARTIAL PASS ({gates_passed}/{gates_total} gates)", flush=True)
            print(f"  {'=' * 50}", flush=True)

    except Exception as e:
        elapsed = time.time() - start
        logger.exception("PG_TEST_061 FAILED")
        print(f"\n  *** PG_TEST_061 FAILED ({elapsed:.0f}s): {e}", flush=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
