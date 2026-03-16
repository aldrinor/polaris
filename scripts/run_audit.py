#!/usr/bin/env python3
"""
POLARIS Automated Deep Audit v2 CLI (FIX-222)

Standalone runner for the 10-dimension automated deep audit.
Can be used for regression testing against previous run results.

Usage:
    python scripts/run_audit.py --result-file state/v3/result.json
    python scripts/run_audit.py --result-file state/v3/result.json --compare state/v3/prev_audit_v2.json
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="POLARIS Automated Deep Audit v2")
    parser.add_argument("--result-file", type=str, required=True, help="Path to pipeline result JSON")
    parser.add_argument("--compare", type=str, help="Path to previous audit JSON for regression comparison")
    parser.add_argument("--output", type=str, help="Output path for audit JSON (default: auto-generated)")
    args = parser.parse_args()

    result_file = Path(args.result_file)
    if not result_file.exists():
        logger.error(f"Result file not found: {result_file}")
        sys.exit(1)

    logger.info(f"Running automated deep audit on: {result_file}")

    try:
        from src.audit.automated_deep_audit import AutomatedDeepAudit

        auditor = AutomatedDeepAudit()
        audit_result = auditor.audit_from_file(str(result_file))

        if not audit_result:
            logger.error("Audit returned no results")
            sys.exit(1)

        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"DEEP AUDIT v2 TOTAL SCORE: {audit_result['total_score']:.1f}/100")
        logger.info("=" * 60)

        for dim in audit_result.get("dimensions", []):
            bar = "#" * int(dim["score"])
            logger.info(
                f"  {dim['name']:<25} {dim['score']:5.1f}/10  "
                f"(weight {dim['weight']:.0%})  {bar}"
            )

        logger.info(f"\n  Word count: {audit_result.get('metadata', {}).get('word_count', 'N/A')}")
        logger.info(f"  Sentence count: {audit_result.get('metadata', {}).get('sentence_count', 'N/A')}")

        # Save output
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = result_file.parent / f"{result_file.stem}_audit_v2.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(audit_result, f, indent=2, default=str)
        logger.info(f"\nAudit saved to: {output_path}")

        # Regression comparison
        if args.compare:
            compare_path = Path(args.compare)
            if compare_path.exists():
                with open(compare_path) as f:
                    prev = json.load(f)

                prev_score = prev.get("total_score", 0)
                curr_score = audit_result["total_score"]
                delta = curr_score - prev_score

                logger.info("")
                logger.info("REGRESSION COMPARISON:")
                logger.info(f"  Previous: {prev_score:.1f}/100")
                logger.info(f"  Current:  {curr_score:.1f}/100")
                logger.info(f"  Delta:    {delta:+.1f}")

                if delta < -5:
                    logger.warning("  REGRESSION DETECTED (>5 point drop)")
                elif delta > 5:
                    logger.info("  IMPROVEMENT (>5 point gain)")
                else:
                    logger.info("  STABLE (within 5 points)")

                # Per-dimension comparison
                prev_dims = {d["name"]: d["score"] for d in prev.get("dimensions", [])}
                for dim in audit_result.get("dimensions", []):
                    prev_dim_score = prev_dims.get(dim["name"], 0)
                    dim_delta = dim["score"] - prev_dim_score
                    if abs(dim_delta) > 1:
                        logger.info(f"    {dim['name']}: {prev_dim_score:.1f} -> {dim['score']:.1f} ({dim_delta:+.1f})")
            else:
                logger.warning(f"Comparison file not found: {compare_path}")

        return 0

    except ImportError as e:
        logger.error(f"AutomatedDeepAudit not available: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
