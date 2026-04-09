"""
Wiki E2E Test — runs full pipeline with PG_WIKI_ENABLED=1.

This is the Phase 1 ship test. It runs the complete graph (plan→search→
storm→analyze→verify→evaluate→synthesize) with the wiki synthesizer
replacing the old synthesis pipeline.
"""

import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Force wiki mode
os.environ["PG_WIKI_ENABLED"] = "1"

from dotenv import load_dotenv
load_dotenv()

# Ensure wiki stays enabled after load_dotenv
os.environ["PG_WIKI_ENABLED"] = "1"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)

VECTOR_ID = "PG_WIKI_001"
QUERY = "What are the proven health benefits and risks of intermittent fasting based on clinical evidence?"
APPLICATION = "Intermittent Fasting"
REGION = "global"
OUTPUT_DIR = Path("outputs/polaris_graph")


async def main():
    start = time.time()
    logger.info("=" * 60)
    logger.info("POLARIS Wiki E2E Test")
    logger.info("PG_WIKI_ENABLED=%s", os.getenv("PG_WIKI_ENABLED"))
    logger.info("=" * 60)

    from src.polaris_graph.graph import build_and_run

    result = await build_and_run(
        vector_id=VECTOR_ID,
        query=QUERY,
        application=APPLICATION,
        region=REGION,
        stage=1,
        max_iterations=2,
        max_execution_minutes=60,
    )

    elapsed = time.time() - start

    # ── Validate output ──────────────────────────────────────────
    report = result.get("final_report", "")
    sections = result.get("sections", [])
    bibliography = result.get("bibliography", [])
    quality = result.get("quality_metrics", {})

    total_words = quality.get("total_words", 0)
    total_citations = quality.get("total_citations", 0)
    unique_sources = quality.get("unique_sources", 0)
    zero_cite = quality.get("zero_cite_sections", 0)

    logger.info("\n" + "=" * 60)
    logger.info("RESULTS")
    logger.info("=" * 60)
    logger.info("Status: %s", result.get("status", "unknown"))
    logger.info("Sections: %d", len(sections))
    logger.info("Words: %d", total_words)
    logger.info("Citations: %d", total_citations)
    logger.info("Sources: %d", unique_sources)
    logger.info("Zero-cite sections: %d", zero_cite)
    logger.info("Quality gate: %s", quality.get("quality_gate_result", result.get("quality_gate_result", "?")))
    logger.info("Time: %.1f min", elapsed / 60)
    logger.info("Cost: $%.4f", result.get("llm_usage", {}).get("total_cost_usd", 0))

    # Per-section breakdown
    logger.info("\nPer-section:")
    for s in sections:
        cites = len(s.get("citation_ids", []))
        logger.info("  %s: %dw, %d cites — %s",
                     s["section_id"], s["word_count"], cites, s["title"][:50])

    # Check wiki exists
    wiki_path = Path("wiki") / VECTOR_ID
    if wiki_path.exists():
        wiki_files = list(wiki_path.rglob("*.md"))
        logger.info("\nWiki: %s (%d files)", wiki_path, len(wiki_files))
    else:
        logger.warning("\nWiki directory NOT created at %s", wiki_path)

    # ── Gate checks ──────────────────────────────────────────────
    gates = []
    if total_words < 2000:
        gates.append(f"FAIL: words={total_words}<2000")
    if total_citations < 5:
        gates.append(f"FAIL: citations={total_citations}<5")
    if unique_sources < 5:
        gates.append(f"FAIL: sources={unique_sources}<5")
    if zero_cite > 0:
        gates.append(f"FAIL: {zero_cite} zero-cite sections")
    if not report:
        gates.append("FAIL: empty report")

    # Check no [CITE:ev_xxx] markers remain
    cite_markers = len(re.findall(r"\[CITE:", report))
    if cite_markers:
        gates.append(f"FAIL: {cite_markers} [CITE:] markers in report")

    if gates:
        logger.warning("\nGATE FAILURES:")
        for g in gates:
            logger.warning("  %s", g)
    else:
        logger.info("\nALL GATES PASSED")

    # ── Save output ──────────────────────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{VECTOR_ID}.json"
    report_path = OUTPUT_DIR / f"{VECTOR_ID}_report.md"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, default=str)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)

    logger.info("\nOutput: %s", output_path)
    logger.info("Report: %s", report_path)
    logger.info("\nNext: python -u scripts/eval_geval.py %s", output_path)


if __name__ == "__main__":
    asyncio.run(main())
