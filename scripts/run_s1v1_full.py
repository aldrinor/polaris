#!/usr/bin/env python3
"""
POLARIS v3 Full Pipeline Run: S1V1 Vector

Executes the complete v3 LangGraph research workflow for the S1V1 test vector.
Outputs results to state/v3/ for RAGAS evaluation.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path (needed for 'from src.' imports)
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)  # Change to project root for relative paths

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"logs/s1v1_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    ]
)
logger = logging.getLogger(__name__)


def run_s1v1():
    """Run the S1V1 vector through the v3 pipeline."""

    # S1V1 Vector Configuration
    vector_config = {
        "vector_id": "S1V1_Household_Water_Filter_NORTH_AMERICA_PROD_RUN_V1",
        "query": "What pathogen contamination rates and patterns exist in Household Water Filter applications for NORTH AMERICA?",
        "application": "household_water_filter",
        "region": "NORTH_AMERICA",
        "stage": 1,
    }

    # Pipeline configuration
    pipeline_config = {
        "max_iterations": 5,           # Maximum ReAct iterations
        "max_execution_minutes": 180,  # Maximum execution time (analyst takes ~90 min)
        "min_faithfulness": 0.85,      # Minimum faithfulness threshold (SOTA target)
    }

    logger.info("=" * 80)
    logger.info("POLARIS v3 FULL PIPELINE RUN")
    logger.info("=" * 80)
    logger.info(f"Vector ID: {vector_config['vector_id']}")
    logger.info(f"Query: {vector_config['query']}")
    logger.info(f"Application: {vector_config['application']}")
    logger.info(f"Region: {vector_config['region']}")
    logger.info(f"Stage: {vector_config['stage']}")
    logger.info(f"Max Iterations: {pipeline_config['max_iterations']}")
    logger.info(f"Max Time: {pipeline_config['max_execution_minutes']} minutes")
    logger.info(f"Min Faithfulness: {pipeline_config['min_faithfulness']}")
    logger.info("=" * 80)

    try:
        # Import the v3 orchestration
        from src.orchestration.graph import run_research

        # Run the full pipeline
        logger.info("Starting v3 pipeline execution...")
        start_time = datetime.now()

        result = run_research(
            vector_id=vector_config["vector_id"],
            query=vector_config["query"],
            application=vector_config["application"],
            region=vector_config["region"],
            stage=vector_config["stage"],
            max_iterations=pipeline_config["max_iterations"],
            max_execution_minutes=pipeline_config["max_execution_minutes"],
            min_faithfulness=pipeline_config["min_faithfulness"]
        )

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Log results
        logger.info("=" * 80)
        logger.info("PIPELINE EXECUTION COMPLETE")
        logger.info("=" * 80)
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Status: {result.get('status', 'unknown')}")
        logger.info(f"Gating Case: {result.get('gating_case', 'N/A')}")
        logger.info(f"Iterations: {result.get('iteration_count', 0)}")
        logger.info(f"Converged: {result.get('converged', False)}")

        # Save result to state/v3/
        output_dir = Path("state/v3")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_file = output_dir / f"{vector_config['vector_id']}_result.json"

        # Prepare output (convert non-serializable objects)
        # FIX: Properly serialize Evidence and SearchResult objects to dicts
        def serialize_evidence(ev):
            """Serialize Evidence object to dict."""
            if hasattr(ev, "model_dump"):
                return ev.model_dump()
            elif isinstance(ev, dict):
                return ev
            else:
                # Fallback: parse string repr to dict (for recovery)
                import re
                match = re.search(r"evidence_id='([^']*)'.*chunk_id='([^']*)'.*source_url='([^']*)'.*text='([^']*)'", str(ev))
                if match:
                    return {
                        "evidence_id": match.group(1),
                        "chunk_id": match.group(2),
                        "source_url": match.group(3),
                        "text": match.group(4)[:500]
                    }
                return {"raw": str(ev)[:500]}

        def serialize_search_result(sr):
            """Serialize SearchResult object to dict."""
            if hasattr(sr, "model_dump"):
                d = sr.model_dump()
                return {
                    "url": d.get("url", ""),
                    "title": d.get("title", ""),
                    "snippet": d.get("snippet", "")[:500] if d.get("snippet") else ""
                }
            elif isinstance(sr, dict):
                return {
                    "url": sr.get("url", ""),
                    "title": sr.get("title", ""),
                    "snippet": sr.get("snippet", "")[:500] if sr.get("snippet") else ""
                }
            else:
                return {"url": str(sr)[:200], "title": "", "snippet": ""}

        output_data = {
            "vector_id": result.get("vector_id"),
            "original_query": result.get("original_query"),
            "application": result.get("application"),
            "region": result.get("region"),
            "stage": result.get("stage"),
            "status": result.get("status"),
            "gating_case": result.get("gating_case"),
            "iteration_count": result.get("iteration_count", 0),
            "converged": result.get("converged", False),
            "final_report": result.get("final_report"),
            "evidence_chain": [serialize_evidence(ev) for ev in result.get("evidence_chain", [])],
            "search_results": [
                serialize_search_result(r) for r in result.get("search_results", [])[:20]
            ],
            # FIX: Properly serialize Pydantic models
            "quality_metrics": (
                result.get("quality_metrics").model_dump()
                if hasattr(result.get("quality_metrics"), "model_dump")
                else result.get("quality_metrics")
            ),
            "iteration_summary": (
                result.get("iteration_summary").model_dump()
                if hasattr(result.get("iteration_summary"), "model_dump")
                else result.get("iteration_summary")
            ),
            "post_hoc_faithfulness": result.get("post_hoc_faithfulness"),
            "audit_result": (
                result.get("audit_result").to_dict()
                if hasattr(result.get("audit_result"), "to_dict")
                else result.get("audit_result")
            ),
            "timestamps": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_seconds": duration
            },
            "pipeline_config": pipeline_config,
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, default=str)

        logger.info(f"Results saved to: {output_file}")

        # Summary
        logger.info("=" * 80)
        logger.info("SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Evidence collected: {len(result.get('evidence_chain', []))} items")
        logger.info(f"Search results: {len(result.get('search_results', []))} items")
        logger.info(f"Final report: {'Yes' if result.get('final_report') else 'No'}")

        if result.get("quality_metrics"):
            qm = result["quality_metrics"]
            logger.info(f"Quality Metrics:")
            if isinstance(qm, dict):
                for key, value in qm.items():
                    logger.info(f"  - {key}: {value}")

        return result

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)

        # Save error state
        error_file = Path("state/v3") / f"{vector_config['vector_id']}_error.json"
        error_file.parent.mkdir(parents=True, exist_ok=True)

        with open(error_file, "w", encoding="utf-8") as f:
            json.dump({
                "vector_id": vector_config["vector_id"],
                "status": "failed",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }, f, indent=2)

        raise


if __name__ == "__main__":
    result = run_s1v1()

    # Exit with appropriate code
    if result and result.get("status") != "failed":
        sys.exit(0)
    else:
        sys.exit(1)
