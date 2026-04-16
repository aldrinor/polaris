"""Full-scale production-config loopback run. Every LLM call routes through
loopback/pending/ → operator responds → loopback/responses/. Real STORM (5
perspectives × 3 rounds), real analyzer, real verify, real wiki compose.
Zero OpenRouter cost; operator time is the constraint.

Usage:
    python scripts/pg_loopback_full_scale.py <vector_id> <query>

Example:
    python scripts/pg_loopback_full_scale.py PG_LB_FS_01 "What are the health benefits and risks of intermittent fasting?"

Estimated per run: 150-300 LLM calls, 2-8 operator-hours, 0-35 min wall-clock
after all responses arrive (the wall-clock is dominated by operator response
latency, not pipeline compute).
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# ---- Full production caps (NOT minimal) ----
os.environ["PG_LOOPBACK_MODE"] = "1"
os.environ["PG_MAX_ITERATIONS"] = "4"
os.environ["PG_QUERIES_PER_VECTOR"] = "30"
os.environ["PG_AGENTIC_MAX_ROUNDS"] = "5"
os.environ["PG_AGENTIC_MIN_ROUNDS"] = "2"
os.environ["PG_AGENTIC_PAGES_PER_ROUND"] = "6"
os.environ["PG_MAX_SOURCES_TO_ANALYZE"] = "60"
os.environ["PG_MAX_EVIDENCE_TO_EXTRACT"] = "400"
os.environ["PG_MAX_EVIDENCE_FOR_VERIFY"] = "2000"
os.environ["PG_MAX_EVIDENCE_FOR_SYNTHESIS"] = "1000"
os.environ["PG_VERIFY_BATCH_SIZE"] = "10"
os.environ["PG_STORM_ROUNDS_PER_PERSPECTIVE"] = "3"
os.environ["PG_STORM_CONCURRENCY"] = "2"  # keep pending queue manageable
os.environ["PG_MAX_OUTLINE_SECTIONS"] = "8"
os.environ["PG_MAX_SECTIONS"] = "8"
os.environ["PG_SECTION_WRITE_CONCURRENCY"] = "2"
os.environ["PG_SYNTHESIS_MAX_EXPANSION_PASSES"] = "2"
os.environ["PG_MAX_EXECUTION_MINUTES"] = "1440"  # 24h — operator-paced
os.environ["PG_BUDGET_GUARD_USD"] = "40"

# Sub-agent response latency is 30s-3min per call. Every internal timeout
# must be larger than the worst-case operator response plus pipeline retry
# overhead, otherwise cascading retries double the operator workload.
os.environ["PG_ANALYSIS_BATCH_TIMEOUT"] = "7200"
os.environ["PG_STORM_INTERVIEW_TIMEOUT"] = "7200"
os.environ["PG_AGENTIC_ANALYSIS_TIMEOUT_SECONDS"] = "7200"
os.environ["PG_VERIFY_BATCH_TIMEOUT"] = "7200"
os.environ["PG_VERIFY_PER_CALL_TIMEOUT"] = "7200"
os.environ["PG_VERIFY_GATHER_TIMEOUT"] = "28800"
os.environ["PG_CLUSTER_BATCH_TIMEOUT"] = "7200"
os.environ["PG_SECTION_WRITE_TIMEOUT"] = "7200"
os.environ["PG_AGENTIC_MAX_TIME_SECONDS"] = "72000"
os.environ["PG_STORM_MAX_TIME_SECONDS"] = "72000"
os.environ["PG_MOST_TOTAL_TIMEOUT"] = "7200"
os.environ["PG_AGENTIC_FETCH_TIMEOUT"] = "180"
os.environ["PG_LOOPBACK_TIMEOUT_SEC"] = "14400"
os.environ["PG_PLANNER_TIMEOUT"] = "7200"
os.environ["PG_REACT_TIMEOUT_SECONDS"] = "7200"
os.environ["PG_WRITE_TIMEOUT"] = "7200"
os.environ["PG_STRUCTURED_DATA_TOTAL_TIMEOUT"] = "7200"
os.environ["PG_LLM_TIMEOUT_SECONDS"] = "7200"
os.environ["PG_LLM_LONG_TIMEOUT_SECONDS"] = "7200"
os.environ["PG_WIKI_OUTLINE_TIMEOUT"] = "7200"
os.environ["PG_WIKI_ABSTRACT_TIMEOUT"] = "7200"
os.environ["PG_WIKI_COMPOSE_TIMEOUT"] = "7200"
os.environ["PG_QUESTION_DECOMP_TIMEOUT"] = "7200"
os.environ["PG_OUTLINE_TIMEOUT"] = "7200"

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

from dotenv import load_dotenv
load_dotenv(override=False)


def _usage():
    print("Usage: python scripts/pg_loopback_full_scale.py <vector_id> <query> [application] [region]")
    print("Example: python scripts/pg_loopback_full_scale.py PG_LB_FS_01 \"What are the proven health benefits and risks of intermittent fasting?\" \"Evidence-Based Health\" GLOBAL")
    sys.exit(2)


if len(sys.argv) < 3:
    _usage()

VECTOR_ID = sys.argv[1]
QUERY = sys.argv[2]
APPLICATION = sys.argv[3] if len(sys.argv) >= 4 else "Systematic Review"
REGION = sys.argv[4] if len(sys.argv) >= 5 else "GLOBAL"

LOG_FILE = PROJECT_ROOT / "logs" / f"pg_loopback_{VECTOR_ID}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
    ],
)


async def main():
    from src.polaris_graph.graph import build_and_run

    banner = "=" * 78
    print(banner, flush=True)
    print(f"  {VECTOR_ID}: LOOPBACK FULL-SCALE — production config, zero LLM cost", flush=True)
    print(f"  Query: {QUERY[:70]}", flush=True)
    print(f"  App:   {APPLICATION} | Region: {REGION}", flush=True)
    print(banner, flush=True)

    start = time.time()
    try:
        result = await build_and_run(
            vector_id=VECTOR_ID,
            query=QUERY,
            application=APPLICATION,
            region=REGION,
            stage=1,
            max_iterations=4,
            max_execution_minutes=1440,
        )
        elapsed = time.time() - start
        qm = result.get("quality_metrics") or {}
        usage = result.get("llm_usage") or {}

        print(flush=True)
        print(banner, flush=True)
        print(f"  {VECTOR_ID} COMPLETED in {elapsed:.0f}s ({elapsed/60:.1f} min)", flush=True)
        print(f"  status:              {result.get('status')}", flush=True)
        print(f"  iteration_count:     {result.get('iteration_count')}", flush=True)
        print(f"  converged:           {result.get('converged')}", flush=True)
        print(f"  quality_gate_result: {result.get('quality_gate_result')}", flush=True)
        print(f"  evidence:            {len(result.get('evidence', []))}", flush=True)
        print(f"  claims:              {len(result.get('claims', []))}", flush=True)
        print(f"  bibliography:        {len(result.get('bibliography', []))}", flush=True)
        print(f"  sections:            {len(result.get('sections', []))}", flush=True)
        print(f"  total_words:         {qm.get('total_words', 0)}", flush=True)
        print(f"  total_citations:     {qm.get('total_citations', 0)}", flush=True)
        print(f"  zero_cite_sections:  {qm.get('zero_cite_sections', '?')}", flush=True)
        print(f"  unique_sources:      {qm.get('unique_sources', 0)}", flush=True)
        print(f"  faithfulness_score:  {qm.get('faithfulness_score', 0)}", flush=True)
        print(f"  perspective_entropy: {result.get('perspective_entropy', 0)}", flush=True)
        print(f"  llm calls:           {usage.get('total_calls', 0)}", flush=True)
        print(f"  llm cost (phantom):  ${usage.get('total_cost_usd', 0)}", flush=True)
        print(banner, flush=True)

        # Gate check
        gate_failures = []
        if qm.get("total_citations", 0) < 20:
            gate_failures.append(f"total_citations={qm.get('total_citations', 0)}<20")
        if qm.get("zero_cite_sections", 99) != 0:
            gate_failures.append(f"zero_cite_sections={qm.get('zero_cite_sections', '?')}!=0")
        if qm.get("faithfulness_score", 0) < 0.80:
            gate_failures.append(f"faithfulness={qm.get('faithfulness_score', 0)}<0.80")
        if qm.get("unique_sources", 0) < 5:
            gate_failures.append(f"unique_sources={qm.get('unique_sources', 0)}<5")
        if result.get("perspective_entropy", 0) < 0.55:
            gate_failures.append(f"perspective_entropy={result.get('perspective_entropy', 0)}<0.55")
        if result.get("status") != "complete":
            gate_failures.append(f"status={result.get('status')}!=complete")

        if gate_failures:
            print(f"  GATE: FAILED — {', '.join(gate_failures)}", flush=True)
            sys.exit(1)
        else:
            print(f"  GATE: PASSED", flush=True)
    except Exception as exc:
        elapsed = time.time() - start
        print(f"\n  {VECTOR_ID} CRASHED after {elapsed:.0f}s: {exc}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    asyncio.run(main())
