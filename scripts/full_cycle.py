#!/usr/bin/env python3
"""
POLARIS Full Cycle: Preflight -> Purge -> Run -> Eval -> Audit

FIX-224: Single authoritative entry point for pipeline execution.
Orchestrates the complete pipeline execution:
0. PREFLIGHT: Validate environment, feature flags, dependencies
1. PURGE: Clean all temp, state, outputs (optionally memory)
2. RUN: Execute full S1V1 pipeline
3. EVAL: Run RAGAS evaluation
4. AUDIT: Run comprehensive audit (v2 automated deep audit)

Usage:
    python scripts/full_cycle.py                    # Run all phases
    python scripts/full_cycle.py --skip-purge       # Skip purge phase
    python scripts/full_cycle.py --wipe-memory      # Also wipe ChromaDB
    python scripts/full_cycle.py --dry-run           # Show what would happen
    python scripts/full_cycle.py --result-file <path> # Use existing result
"""

import os
import sys
import json
import shutil
import logging
import argparse
import subprocess
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

# Configure logging
log_file = f"logs/full_cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file)
    ]
)
logger = logging.getLogger(__name__)


def phase_banner(phase_num: int, phase_name: str, status: str = "STARTING"):
    """Print a phase banner."""
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"PHASE {phase_num}: {phase_name} [{status}]")
    logger.info("=" * 70)


def phase_0_preflight(dry_run: bool = False) -> bool:
    """Phase 0: Preflight Validation (FIX-224).

    Validates:
    - Required environment variables
    - Feature flags in .env
    - Python dependencies
    - Scripts/preflight.py checks

    Returns:
        True if preflight passes, False otherwise
    """
    phase_banner(0, "PREFLIGHT VALIDATION")

    if dry_run:
        logger.info("[DRY RUN] Would validate environment and feature flags")
        phase_banner(0, "PREFLIGHT VALIDATION", "SKIPPED (dry-run)")
        return True

    errors = []

    # Check critical environment variables
    from dotenv import load_dotenv
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path, override=True)

    required_vars = {
        "FIREWORKS_API_KEY": "KIMI K2.5 LLM provider",
        "SERPER_API_KEY": "Web search via Serper.dev",
    }

    for var, desc in required_vars.items():
        val = os.environ.get(var, "")
        if not val:
            errors.append(f"Missing {var} ({desc})")
        else:
            logger.info(f"  {var}: present ({len(val)} chars)")

    # Check feature flags (FIX-214)
    required_flags = {
        "POLARIS_CLUSTER_SYNTHESIS": ("1", "Cluster-synthesize architecture"),
        "POLARIS_CITEFIRST_ENABLED": ("1", "Cite-first synthesizer"),
    }

    for flag, (expected, desc) in required_flags.items():
        val = os.environ.get(flag, "")
        if val != expected:
            errors.append(f"Feature flag {flag} must be '{expected}' (got '{val}') - {desc}")
        else:
            logger.info(f"  {flag}={val} ({desc})")

    # Check recommended flags
    recommended_flags = {
        "POLARIS_LLM_COT_FILTER": ("1", "LLM-based CoT post-filter"),
        "POLARIS_QUERY_TOPIC_ANCHOR": ("1", "Topic-anchored query simplification"),
    }

    for flag, (expected, desc) in recommended_flags.items():
        val = os.environ.get(flag, "")
        if val != expected:
            logger.warning(f"  {flag}={val} (recommended: '{expected}') - {desc}")
        else:
            logger.info(f"  {flag}={val} ({desc})")

    # Run scripts/preflight.py if available
    preflight_script = PROJECT_ROOT / "scripts" / "preflight.py"
    if preflight_script.exists():
        logger.info("Running preflight.py...")
        try:
            result = subprocess.run(
                [sys.executable, str(preflight_script)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                errors.append(f"preflight.py failed (exit {result.returncode}): {result.stderr[:200]}")
            else:
                logger.info("  preflight.py: PASSED")
        except subprocess.TimeoutExpired:
            errors.append("preflight.py timed out (60s)")
        except Exception as e:
            logger.warning(f"  preflight.py could not run: {e}")
    else:
        logger.info("  preflight.py: not found (skipped)")

    if errors:
        logger.error("")
        logger.error("PREFLIGHT FAILED:")
        for err in errors:
            logger.error(f"  - {err}")
        phase_banner(0, "PREFLIGHT VALIDATION", "FAILED")
        return False

    phase_banner(0, "PREFLIGHT VALIDATION", "PASSED")
    return True


def phase_1_purge(wipe_memory: bool = False, dry_run: bool = False):
    """Phase 1: Full Purge - Clean all temp, state, outputs."""
    phase_banner(1, "FULL PURGE")

    if dry_run:
        logger.info("[DRY RUN] Would purge: __pycache__, state, outputs, cost_ledger")
        if wipe_memory:
            logger.info("[DRY RUN] Would also wipe ChromaDB")
        phase_banner(1, "FULL PURGE", "SKIPPED (dry-run)")
        return True

    # Clean temp files
    patterns = ["**/__pycache__", "**/*.pyc", "**/*.pyo", "**/.pytest_cache", "**/*.egg-info"]
    removed = 0
    for pattern in patterns:
        for path in PROJECT_ROOT.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed += 1
    logger.info(f"Removed {removed} temp files/directories")

    # Reset state files
    state_dir = PROJECT_ROOT / "state"

    # Reset cost ledger
    cost_file = state_dir / "cost_ledger.json"
    cost_file.write_text("{}")
    logger.info("Reset cost_ledger.json")

    # Reset progress ledger
    progress_file = state_dir / "progress_ledger.jsonl"
    if progress_file.exists():
        progress_file.unlink()
    logger.info("Reset progress_ledger.jsonl")

    # Reset restart instructions
    restart_file = state_dir / "restart_instructions.md"
    restart_file.write_text("# Restart Instructions\n\nNo pending restart instructions.\n")
    logger.info("Reset restart_instructions.md")

    # Clean outputs (but preserve directory structure)
    outputs_dir = PROJECT_ROOT / "outputs"
    if outputs_dir.exists():
        removed = 0
        for phase_dir in outputs_dir.iterdir():
            if phase_dir.is_dir():
                for f in phase_dir.glob("*"):
                    if f.is_file():
                        f.unlink()
                        removed += 1
        logger.info(f"Removed {removed} output files")

    # Optionally wipe ChromaDB
    if wipe_memory:
        memory_dir = PROJECT_ROOT / "memory" / "chroma_db"
        if memory_dir.exists():
            shutil.rmtree(memory_dir)
            memory_dir.mkdir(parents=True)
            logger.info("Wiped ChromaDB (memory/chroma_db)")

    # Clean v3 state (but preserve structure)
    v3_dir = state_dir / "v3"
    if v3_dir.exists():
        for f in v3_dir.glob("*.json"):
            f.unlink()
        logger.info("Cleared state/v3/ JSON files")

    phase_banner(1, "FULL PURGE", "COMPLETE")
    return True


def phase_2_run(dry_run: bool = False):
    """Phase 2: Full Run - Execute S1V1 pipeline."""
    phase_banner(2, "FULL RUN")

    # S1V1 Vector Configuration
    vector_config = {
        "vector_id": "S1V1_Household_Water_Filter_NORTH_AMERICA",
        "query": "What pathogen contamination rates and patterns exist in Household Water Filter applications for NORTH AMERICA?",
        "application": "household_water_filter",
        "region": "NORTH_AMERICA",
        "stage": 1,
    }

    pipeline_config = {
        "max_iterations": 5,
        "max_execution_minutes": 180,
        "min_faithfulness": 0.85,
    }

    logger.info(f"Vector ID: {vector_config['vector_id']}")
    logger.info(f"Query: {vector_config['query']}")
    logger.info(f"Max Iterations: {pipeline_config['max_iterations']}")
    logger.info(f"Max Time: {pipeline_config['max_execution_minutes']} minutes")

    if dry_run:
        logger.info("[DRY RUN] Would execute run_research() with above config")
        phase_banner(2, "FULL RUN", "SKIPPED (dry-run)")
        return None

    try:
        from src.orchestration.graph import run_research

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

        logger.info(f"Pipeline completed in {duration:.2f} seconds")
        logger.info(f"Status: {result.get('status', 'unknown')}")
        logger.info(f"Gating Case: {result.get('gating_case', 'N/A')}")
        logger.info(f"Evidence collected: {len(result.get('evidence_chain', []))} items")
        logger.info(f"Final report: {'Yes' if result.get('final_report') else 'No'}")

        # Save result
        output_dir = Path("state/v3")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{vector_config['vector_id']}_result.json"

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
            "draft_report": result.get("draft_report"),
            # FIX-253: Serialize evidence as dicts (not str repr) to preserve
            # list fields like perspective_origins for the audit system
            "evidence_chain": [
                ev.model_dump() if hasattr(ev, "model_dump")
                else (ev if isinstance(ev, dict) else str(ev))
                for ev in result.get("evidence_chain", [])
            ],
            "search_results": [
                {
                    "url": r.get("url") if isinstance(r, dict) else str(r),
                    "title": r.get("title") if isinstance(r, dict) else "",
                    "snippet": r.get("snippet", "")[:500] if isinstance(r, dict) else ""
                }
                for r in result.get("search_results", [])[:20]
            ],
            "quality_metrics": result.get("quality_metrics"),
            "audit_result": result.get("audit_result"),
            "post_hoc_faithfulness": result.get("post_hoc_faithfulness"),
            "pipeline_faithfulness": result.get("pipeline_faithfulness"),
            "bibliography": result.get("bibliography", []),
            "sentences_to_revise": result.get("sentences_to_revise", []),
            "timestamps": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat(),
                "duration_seconds": duration
            },
            "pipeline_config": pipeline_config,
            # FIX-254: Save perspective_coverage so D7 audit can read perspective balance
            "perspective_coverage": result.get("perspective_coverage", {}),
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, default=str)

        logger.info(f"Results saved to: {output_file}")

        phase_banner(2, "FULL RUN", "COMPLETE")
        return output_file

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        phase_banner(2, "FULL RUN", "FAILED")
        return None


def phase_3_eval(result_file: Path, dry_run: bool = False):
    """Phase 3: Full Eval - Run RAGAS evaluation."""
    phase_banner(3, "FULL EVAL")

    if dry_run:
        logger.info(f"[DRY RUN] Would evaluate: {result_file}")
        phase_banner(3, "FULL EVAL", "SKIPPED (dry-run)")
        return None

    if not result_file or not result_file.exists():
        logger.error(f"Result file not found: {result_file}")
        return None

    logger.info(f"Evaluating: {result_file}")

    try:
        # Set environment for GPU
        os.environ["POLARIS_USE_GPU"] = "1"
        os.environ["POLARIS_MINICHECK_MODEL"] = "roberta-large"
        os.environ["POLARIS_SUPPORT_THRESHOLD"] = "0.3"

        from scripts.run_ragas_v3 import run_ragas_evaluation

        result = run_ragas_evaluation(str(result_file))

        if result:
            logger.info("")
            logger.info("RAGAS METRICS SUMMARY:")
            logger.info(f"  Faithfulness:     {result.ragas_metrics.faithfulness:.1%}")
            logger.info(f"  Answer Relevancy: {result.ragas_metrics.answer_relevancy:.1%}")
            logger.info(f"  Composite Score:  {result.ragas_metrics.composite_score:.1%}")
            logger.info(f"  Hallucination:    {result.hallucination_rate:.1%}")

        phase_banner(3, "FULL EVAL", "COMPLETE")
        return result

    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        phase_banner(3, "FULL EVAL", "FAILED")
        return None


def phase_4_audit(result_file: Path, dry_run: bool = False):
    """Phase 4: Full Audit - Run comprehensive final audit."""
    phase_banner(4, "FULL AUDIT")

    if dry_run:
        logger.info(f"[DRY RUN] Would audit: {result_file}")
        phase_banner(4, "FULL AUDIT", "SKIPPED (dry-run)")
        return None

    if not result_file or not result_file.exists():
        logger.error(f"Result file not found: {result_file}")
        return None

    logger.info(f"Auditing: {result_file}")

    try:
        # Set environment for GPU
        os.environ["POLARIS_USE_GPU"] = "1"
        os.environ["POLARIS_MINICHECK_MODEL"] = "roberta-large"
        os.environ["POLARIS_SUPPORT_THRESHOLD"] = "0.3"

        from scripts.final_audit import run_final_audit

        state = run_final_audit(result_file)

        if state:
            audit_result = state.get('audit_result', {})
            faithfulness = audit_result.get('faithfulness_score', 0.0)
            faithful_count = audit_result.get('faithful_count', 0)
            unfaithful_count = audit_result.get('unfaithful_count', 0)

            logger.info("")
            logger.info("AUDIT SUMMARY:")
            logger.info(f"  Faithfulness Score: {faithfulness:.1%}")
            logger.info(f"  Faithful sentences: {faithful_count}")
            logger.info(f"  Unfaithful sentences: {unfaithful_count}")

            grade = 'A' if faithfulness >= 0.9 else 'B' if faithfulness >= 0.8 else 'C' if faithfulness >= 0.7 else 'D'
            logger.info(f"  Grade: {grade}")

        phase_banner(4, "FULL AUDIT", "COMPLETE")
        return state

    except Exception as e:
        logger.error(f"Audit failed: {e}", exc_info=True)
        phase_banner(4, "FULL AUDIT", "FAILED")
        return None


def phase_5_deep_audit(result_file: Path, dry_run: bool = False):
    """Phase 5: Automated Deep Audit v2 (FIX-222)."""
    phase_banner(5, "DEEP AUDIT v2")

    if dry_run:
        logger.info(f"[DRY RUN] Would run automated deep audit on: {result_file}")
        phase_banner(5, "DEEP AUDIT v2", "SKIPPED (dry-run)")
        return None

    if not result_file or not result_file.exists():
        logger.error(f"Result file not found: {result_file}")
        return None

    try:
        from src.audit.automated_deep_audit import AutomatedDeepAudit

        auditor = AutomatedDeepAudit()
        audit_result = auditor.audit_from_file(str(result_file))

        if audit_result:
            logger.info("")
            logger.info("DEEP AUDIT v2 SUMMARY:")
            logger.info(f"  Total Score: {audit_result.get('total_score', 0):.1f}/100")
            for dim in audit_result.get('dimensions', []):
                logger.info(f"  {dim['name']}: {dim['score']:.1f}/10 ({dim['weight']:.0%})")

            # Save audit result
            audit_file = result_file.parent / f"{result_file.stem}_audit_v2.json"
            with open(audit_file, "w", encoding="utf-8") as f:
                json.dump(audit_result, f, indent=2, default=str)
            logger.info(f"  Saved to: {audit_file}")

        phase_banner(5, "DEEP AUDIT v2", "COMPLETE")
        return audit_result

    except ImportError:
        logger.warning("AutomatedDeepAudit not available (FIX-222 not yet implemented)")
        phase_banner(5, "DEEP AUDIT v2", "SKIPPED (not available)")
        return None
    except Exception as e:
        logger.error(f"Deep audit failed: {e}", exc_info=True)
        phase_banner(5, "DEEP AUDIT v2", "FAILED")
        return None


def print_cost_summary():
    """Print cost tracker summary."""
    cost_file = PROJECT_ROOT / "state" / "cost_ledger.json"
    if cost_file.exists():
        try:
            with open(cost_file) as f:
                data = json.load(f)

            if data:
                logger.info("")
                logger.info("COST SUMMARY:")
                total_cost = 0.0
                for model, usage in data.items():
                    if isinstance(usage, dict):
                        cost = usage.get('total_cost', 0.0)
                        total_cost += cost
                        logger.info(f"  {model}: ${cost:.4f}")
                logger.info(f"  TOTAL: ${total_cost:.4f}")
            else:
                logger.info("Cost ledger is empty (no API calls tracked yet)")
        except Exception as e:
            logger.warning(f"Could not read cost ledger: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Full Cycle: Preflight -> Purge -> Run -> Eval -> Audit"
    )
    parser.add_argument("--skip-purge", action="store_true", help="Skip the purge phase")
    parser.add_argument("--wipe-memory", action="store_true", help="Also wipe ChromaDB memory")
    parser.add_argument("--result-file", type=str, help="Use existing result file (skip run)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without executing")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip preflight validation")
    args = parser.parse_args()

    start_time = datetime.now()

    logger.info("")
    logger.info("+====================================================================+")
    logger.info("|    POLARIS FULL CYCLE: PREFLIGHT -> PURGE -> RUN -> EVAL -> AUDIT  |")
    logger.info("+====================================================================+")
    logger.info(f"|  Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}                                  |")
    logger.info(f"|  Log File: {log_file:<53} |")
    if args.dry_run:
        logger.info("|  Mode: DRY RUN                                                   |")
    logger.info("+====================================================================+")

    # Phase 0: Preflight (FIX-224)
    if not args.skip_preflight:
        if not phase_0_preflight(dry_run=args.dry_run):
            logger.error("Preflight failed. Fix issues above before running pipeline.")
            sys.exit(1)
    else:
        logger.info("Skipping preflight validation")

    result_file = None

    # Phase 1: Purge
    if not args.skip_purge and not args.result_file:
        phase_1_purge(wipe_memory=args.wipe_memory, dry_run=args.dry_run)
    else:
        logger.info("Skipping purge phase")

    # Phase 2: Run
    if args.result_file:
        result_file = Path(args.result_file)
        logger.info(f"Using existing result file: {result_file}")
    else:
        result_file = phase_2_run(dry_run=args.dry_run)
        if not result_file and not args.dry_run:
            logger.error("Pipeline run failed, cannot continue to eval/audit")
            sys.exit(1)

    if args.dry_run:
        result_file = result_file or Path("state/v3/example_result.json")

    # Phase 3: Eval
    phase_3_eval(result_file, dry_run=args.dry_run)

    # Phase 4: Audit (SKIPPED — FIX-242)
    # Phase 4 (final_audit.py) re-measures faithfulness with LESS data than
    # graph.py finalize_node and OVERWRITES the correct value with 0.0.
    # The deep audit v2 (Phase 5) is the authoritative quality assessment.
    logger.info("Skipping Phase 4 (final_audit.py) — FIX-242: finalize_node metrics are authoritative")

    # Phase 5: Deep Audit v2 (FIX-222)
    phase_5_deep_audit(result_file, dry_run=args.dry_run)

    # Print cost summary
    print_cost_summary()

    # Final summary
    end_time = datetime.now()
    total_duration = (end_time - start_time).total_seconds()

    logger.info("")
    logger.info("+====================================================================+")
    logger.info("|                    FULL CYCLE COMPLETE                             |")
    logger.info("+====================================================================+")
    logger.info(f"|  Total Duration: {total_duration/60:.1f} minutes                                      |")
    logger.info(f"|  Result File: {str(result_file):<51} |")
    logger.info("+====================================================================+")

    return 0


if __name__ == "__main__":
    sys.exit(main())
