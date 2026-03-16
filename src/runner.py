"""
POLARIS Runner - Pipeline Orchestration P6-P13

Orchestrates the full research pipeline from NLI integrity (P6) through
narrative synthesis (P13) for a single vector.

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC
- Real phase execution
- Proper gating logic handling
- SOTA-aligned dynamic iteration (5-30 iterations with saturation detection)
- Claim-Evidence NLI Verification (P8)
- Comprehensive audit with gap reports
- Clean handoffs between phases

Usage:
    python src/runner.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA

Gating Behavior:
    - CASE_1: Proceed to P11-P13 (finalize)
    - CASE_2: Re-iterate P7-P10 (up to max_iterations with saturation detection)
    - CASE_3: Skip to P12 (gap report)
    - CASE_4: Skip to P12 (failure report)
"""

import asyncio
import json
import sys
import time
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import GatingCase
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.utils.cost_tracker import get_cost_tracker, BudgetExceededError
from src.audit.collector import AuditCollector, set_audit, get_audit


# ============================================================================
# SOTA CONFIGURATION (Dynamic from sota_parameters.yaml)
# ============================================================================

def load_sota_parameters() -> Dict[str, Any]:
    """Load SOTA parameters from config file."""
    sota_path = PROJECT_ROOT / "config" / "settings" / "sota_parameters.yaml"
    if sota_path.exists():
        with open(sota_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    # Fallback defaults if config missing
    return {
        "iteration": {
            "min_iterations": 5,
            "max_iterations": 30,
            "default_iterations": 10,
            "saturation_threshold": 0.85,
            "novelty_decay_threshold": 0.10,
            "consecutive_low_novelty": 3,
            "max_execution_time_minutes": 30,
        }
    }


SOTA_PARAMS = load_sota_parameters()

# Dynamic iteration limits from SOTA config
MIN_ITERATIONS = SOTA_PARAMS.get("iteration", {}).get("min_iterations", 5)
MAX_ITERATIONS = SOTA_PARAMS.get("iteration", {}).get("max_iterations", 30)
DEFAULT_ITERATIONS = SOTA_PARAMS.get("iteration", {}).get("default_iterations", 10)
SATURATION_THRESHOLD = SOTA_PARAMS.get("iteration", {}).get("saturation_threshold", 0.85)
NOVELTY_DECAY_THRESHOLD = SOTA_PARAMS.get("iteration", {}).get("novelty_decay_threshold", 0.10)
CONSECUTIVE_LOW_NOVELTY = SOTA_PARAMS.get("iteration", {}).get("consecutive_low_novelty", 3)
MAX_EXECUTION_MINUTES = SOTA_PARAMS.get("iteration", {}).get("max_execution_time_minutes", 30)

# Correction loop parameters (SOTA-aligned)
HALLUCINATION_THRESHOLD = 0.10  # SOTA-aligned: max 10% hallucination (target is 5%)
MAX_CORRECTION_RETRIES = 7  # SOTA: Increased from 3 to 7 for more aggressive correction
MIN_VERIFICATION_RATE = 0.80  # Minimum acceptable verification rate (80%)

# Recursive gap-filling parameters (SOTA "Rabbit Hole" logic)
MAX_RECURSION_DEPTH = 3  # Maximum recursive search depth
MIN_WORD_COUNT_TARGET = 2500  # Target word count before considering complete
GAP_TRIGGERED_SEARCH_LIMIT = 20  # Max URLs to fetch per gap-filling recursion


# ============================================================================
# PHASE IMPORTS (Lazy)
# ============================================================================

def get_phase_2():
    """P2: Query Generation."""
    from src.phases.p02_query_generation import run_phase2
    return run_phase2


def get_phase_3():
    """P3: Federated Search."""
    from src.phases.p03_federated_search import run_phase3
    return run_phase3


def get_phase_4():
    """P4: Relevance Filtering."""
    from src.phases.p04_relevance_filtering import run_phase4
    return run_phase4


def get_phase_5():
    """P5: VWM Indexing."""
    from src.phases.p05_vwm_indexing import run_phase5
    return run_phase5


def get_phase_6():
    from src.phases.p06_nli_integrity import run_phase6
    return run_phase6


def get_phase_7():
    from src.phases.p07_dual_rag import run_phase7
    return run_phase7


def get_phase_8():
    """P8: Claim-Evidence NLI Verification (architecture.md B.4/B.5)."""
    from src.phases.p08_claim_verification import run_phase_8
    return run_phase_8


def get_phase_9():
    from src.phases.p09_adversarial_qa import run_phase_9
    return run_phase_9


def get_phase_10():
    from src.phases.p10_gating import run_phase_10
    return run_phase_10


def get_phase_11():
    from src.phases.p11_knowledge_integration import run_phase_11
    return run_phase_11


def get_phase_12():
    from src.phases.p12_research_packaging import run_phase_12
    return run_phase_12


def get_phase_13():
    from src.phases.p13_narrative_synthesis import run_phase_13
    return run_phase_13


# ============================================================================
# HELPERS
# ============================================================================

def get_latest_output(vector_id: str, phase: int) -> Optional[Path]:
    """Get the latest output file for a phase."""
    phase_dir = OUTPUTS_DIR / f"P{phase}"
    if not phase_dir.exists():
        return None
    files = list(phase_dir.glob(f"{vector_id}__P{phase}__*.json"))
    if not files:
        return None
    return sorted(files)[-1]


def get_runner_auditor():
    """Lazy import for runner audit system."""
    from src.audit.runner_audit import RunnerAuditor
    return RunnerAuditor


class SaturationTracker:
    """
    Tracks knowledge saturation to enable dynamic iteration stopping.

    SOTA systems like Gemini Deep Research stop when knowledge saturation
    is detected rather than using a fixed iteration limit.
    """

    def __init__(self):
        self.novelty_scores: List[float] = []
        self.coverage_scores: List[float] = []
        self.consecutive_low_novelty_count = 0

    def record_iteration(self, novelty: float, coverage: float) -> None:
        """Record metrics from an iteration."""
        self.novelty_scores.append(novelty)
        self.coverage_scores.append(coverage)

        # Track consecutive low novelty
        if novelty < NOVELTY_DECAY_THRESHOLD:
            self.consecutive_low_novelty_count += 1
        else:
            self.consecutive_low_novelty_count = 0

    def should_stop(self, iteration: int, elapsed_minutes: float) -> tuple[bool, str]:
        """
        Check if iteration should stop based on saturation signals.

        Returns:
            (should_stop, reason)
        """
        # Check minimum iterations
        if iteration < MIN_ITERATIONS:
            return False, "minimum_iterations_not_met"

        # Check time limit
        if elapsed_minutes >= MAX_EXECUTION_MINUTES:
            return True, "max_execution_time_reached"

        # Check coverage saturation
        if self.coverage_scores and self.coverage_scores[-1] >= SATURATION_THRESHOLD:
            return True, "knowledge_saturation_reached"

        # Check consecutive low novelty
        if self.consecutive_low_novelty_count >= CONSECUTIVE_LOW_NOVELTY:
            return True, "novelty_decay_detected"

        # Check max iterations
        if iteration >= MAX_ITERATIONS:
            return True, "max_iterations_reached"

        return False, "continue"

    def get_stats(self) -> Dict[str, Any]:
        """Get saturation tracking statistics."""
        return {
            "iterations_tracked": len(self.novelty_scores),
            "novelty_scores": self.novelty_scores,
            "coverage_scores": self.coverage_scores,
            "avg_novelty": sum(self.novelty_scores) / len(self.novelty_scores) if self.novelty_scores else 0,
            "final_coverage": self.coverage_scores[-1] if self.coverage_scores else 0,
            "consecutive_low_novelty": self.consecutive_low_novelty_count,
        }


# ============================================================================
# RECURSIVE GAP-FILLING (SOTA "Rabbit Hole" Logic)
# ============================================================================

async def run_gap_filling_recursion(
    vector_id: str,
    gap_questions: List[str],
    recursion_depth: int,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    SOTA Recursive Gap-Filling - The "Rabbit Hole" Logic.

    When P8 detects gaps or word count is below target, this function:
    1. Generates targeted queries from the gap questions
    2. Runs federated search (P3) with academic engines
    3. Filters relevant content (P4)
    4. Indexes new chunks to VWM (P5) - APPENDS, does not overwrite

    Args:
        vector_id: Vector ID being processed
        gap_questions: List of gap questions from P8
        recursion_depth: Current recursion depth (1-3)
        verbose: Print progress

    Returns:
        Dict with recursion results
    """
    if recursion_depth > MAX_RECURSION_DEPTH:
        if verbose:
            print(f"\n  [RECURSION] Max depth ({MAX_RECURSION_DEPTH}) reached, stopping")
        return {"status": "max_depth_reached", "new_chunks": 0}

    if not gap_questions:
        if verbose:
            print(f"\n  [RECURSION] No gap questions to process")
        return {"status": "no_gaps", "new_chunks": 0}

    if verbose:
        print(f"\n" + "="*60)
        print(f"RECURSIVE GAP-FILLING (Depth {recursion_depth}/{MAX_RECURSION_DEPTH})")
        print(f"  Gap Questions: {len(gap_questions)}")
        print("="*60)

    results = {
        "recursion_depth": recursion_depth,
        "gap_questions": gap_questions,
        "queries_generated": 0,
        "urls_found": 0,
        "chunks_added": 0,
        "academic_sources": 0,
    }

    try:
        # Step 1: Generate targeted queries from gap questions
        if verbose:
            print(f"\n  [Step 1] Generating targeted queries...")

        # Convert gap questions to search queries
        targeted_queries = []
        for question in gap_questions[:5]:  # Limit to 5 gaps per recursion
            # Clean the question for search
            query = question.replace("?", "").strip()
            # Add academic modifiers for depth
            targeted_queries.append(f'"{query}"')
            targeted_queries.append(f'{query} peer-reviewed study')
            targeted_queries.append(f'{query} systematic review')

        results["queries_generated"] = len(targeted_queries)
        if verbose:
            print(f"    Generated {len(targeted_queries)} queries")

        # Step 2: Run federated search (prioritize academic engines)
        if verbose:
            print(f"\n  [Step 2] Running federated search (academic priority)...")

        run_p3 = get_phase_3()

        # Get P2 output path (we need the research objective)
        p2_path = get_latest_output(vector_id, 2)
        if p2_path and p2_path.exists():
            p3_output_dir = OUTPUTS_DIR / "P3"
            p3_output_dir.mkdir(parents=True, exist_ok=True)

            # Run search with custom queries (inject into P3)
            p3_output = await run_p3(
                vector_id=vector_id,
                input_path=p2_path,
                output_dir=p3_output_dir,
                additional_queries=targeted_queries,  # Custom gap queries
            )

            results["urls_found"] = len(p3_output.urls_found) if hasattr(p3_output, 'urls_found') else 0
            if verbose:
                print(f"    Found {results['urls_found']} URLs")

        # Step 3: Relevance filtering
        if verbose:
            print(f"\n  [Step 3] Filtering relevant content...")

        p3_path = get_latest_output(vector_id, 3)
        if p3_path and p3_path.exists():
            run_p4 = get_phase_4()
            p4_output_dir = OUTPUTS_DIR / "P4"
            p4_output_dir.mkdir(parents=True, exist_ok=True)

            p4_output = await run_p4(
                vector_id=vector_id,
                input_path=p3_path,
                output_dir=p4_output_dir
            )

            if verbose:
                filtered = len(p4_output.filtered_chunks) if hasattr(p4_output, 'filtered_chunks') else 0
                print(f"    Filtered to {filtered} relevant chunks")

        # Step 4: Index to VWM (APPEND mode)
        if verbose:
            print(f"\n  [Step 4] Indexing new chunks to VWM (append mode)...")

        p4_path = get_latest_output(vector_id, 4)
        if p4_path and p4_path.exists():
            run_p5 = get_phase_5()
            p5_output_dir = OUTPUTS_DIR / "P5"
            p5_output_dir.mkdir(parents=True, exist_ok=True)

            p5_output = await run_p5(
                vector_id=vector_id,
                input_path=p4_path,
                output_dir=p5_output_dir,
                append_mode=True,  # CRITICAL: Append, don't overwrite
            )

            results["chunks_added"] = p5_output.chunks_indexed if hasattr(p5_output, 'chunks_indexed') else 0
            if verbose:
                print(f"    Added {results['chunks_added']} new chunks to VWM")

        # Count academic sources
        if p3_path and p3_path.exists():
            with open(p3_path, 'r', encoding='utf-8') as f:
                p3_data = json.load(f)
                urls = p3_data.get("urls_found", [])
                academic_domains = ['pubmed', 'ncbi.nlm.nih.gov', 'arxiv.org', 'semanticscholar', 'openalex']
                for url in urls:
                    url_str = url if isinstance(url, str) else url.get('url', '')
                    if any(d in url_str.lower() for d in academic_domains):
                        results["academic_sources"] += 1

        if verbose:
            print(f"\n  [RECURSION COMPLETE] Depth {recursion_depth}")
            print(f"    Queries: {results['queries_generated']}")
            print(f"    URLs: {results['urls_found']}")
            print(f"    New Chunks: {results['chunks_added']}")
            print(f"    Academic Sources: {results['academic_sources']}")

        results["status"] = "success"

    except Exception as e:
        if verbose:
            print(f"\n  [RECURSION ERROR] {e}")
        results["status"] = "error"
        results["error"] = str(e)

    return results


def extract_gap_questions_from_p9(p9_output) -> List[str]:
    """
    Extract gap questions from P9 (Adversarial QA) output.

    These are the questions that could not be fully answered
    from the current evidence.
    """
    gap_questions = []

    if hasattr(p9_output, 'qa_results'):
        for qa in p9_output.qa_results:
            if isinstance(qa, dict):
                # Check for unresolved or partially resolved questions
                status = qa.get('status', qa.get('resolved', True))
                if status in [False, 'unresolved', 'UNRESOLVED', 'partial', 'PARTIAL']:
                    question = qa.get('question', qa.get('skeptical_question', ''))
                    if question:
                        gap_questions.append(question)

    elif hasattr(p9_output, 'unresolved_questions'):
        gap_questions = p9_output.unresolved_questions

    return gap_questions


async def run_iron_loop_acquisition(
    vector_id: str,
    gap_questions: List[str],
    loop_number: int,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    IRON LOOP: True Recursion - Full P2-P5 acquisition cycle with gap focus.

    Unlike the lightweight gap-filling recursion, this runs the FULL acquisition
    pipeline (P2-P5) with the gap questions as focus_topics, appending new
    evidence to the VWM.

    Args:
        vector_id: Vector ID being processed
        gap_questions: List of gap questions from P8
        loop_number: Current iron loop iteration (1-3)
        verbose: Print progress

    Returns:
        Dict with acquisition results
    """
    if verbose:
        print(f"\n" + "="*60)
        print(f"IRON LOOP ACQUISITION (Loop {loop_number}/3)")
        print(f"  Gap Focus Topics: {len(gap_questions)}")
        print("="*60)

    results = {
        "loop_number": loop_number,
        "gap_questions": gap_questions[:5],  # Store for logging
        "queries_generated": 0,
        "urls_found": 0,
        "chunks_added": 0,
        "status": "pending"
    }

    try:
        # Step 1: Get P1 output (needed for P2)
        p1_path = get_latest_output(vector_id, 1)
        if not p1_path or not p1_path.exists():
            if verbose:
                print(f"  [ERROR] No P1 output found, cannot run P2")
            results["status"] = "error_no_p1"
            return results

        # Step 2: Run P2 Query Generation with gap focus topics
        if verbose:
            print(f"\n  [P2] Generating queries with gap focus...")

        run_p2 = get_phase_2()
        p2_output_dir = OUTPUTS_DIR / "P2"
        p2_output_dir.mkdir(parents=True, exist_ok=True)

        # Pass gap questions as focus_topics to P2
        p2_output = await run_p2(
            vector_id=vector_id,
            input_path=p1_path,
            output_dir=p2_output_dir,
            focus_topics=gap_questions[:5],  # Top 5 gaps as focus
        )

        results["queries_generated"] = len(p2_output.final_queries) if hasattr(p2_output, 'final_queries') else 0
        if verbose:
            print(f"    Generated {results['queries_generated']} queries")

        # Step 3: Run P3 Search
        if verbose:
            print(f"\n  [P3] Running federated search...")

        p2_path = get_latest_output(vector_id, 2)
        if p2_path and p2_path.exists():
            run_p3 = get_phase_3()
            p3_output_dir = OUTPUTS_DIR / "P3"
            p3_output_dir.mkdir(parents=True, exist_ok=True)

            p3_output = await run_p3(
                vector_id=vector_id,
                input_path=p2_path,
                output_dir=p3_output_dir,
            )

            results["urls_found"] = len(p3_output.urls_found) if hasattr(p3_output, 'urls_found') else 0
            if verbose:
                print(f"    Found {results['urls_found']} URLs")

        # Step 4: Run P4 Relevance Filter
        if verbose:
            print(f"\n  [P4] Filtering for relevance...")

        p3_path = get_latest_output(vector_id, 3)
        if p3_path and p3_path.exists():
            run_p4 = get_phase_4()
            p4_output_dir = OUTPUTS_DIR / "P4"
            p4_output_dir.mkdir(parents=True, exist_ok=True)

            p4_output = await run_p4(
                vector_id=vector_id,
                input_path=p3_path,
                output_dir=p4_output_dir,
            )

            if verbose:
                chunks_count = len(p4_output.filtered_chunks) if hasattr(p4_output, 'filtered_chunks') else 0
                print(f"    Filtered to {chunks_count} relevant chunks")

        # Step 5: Run P5 Indexing (APPEND mode - do not overwrite VWM)
        if verbose:
            print(f"\n  [P5] Indexing new evidence (APPEND mode)...")

        p4_path = get_latest_output(vector_id, 4)
        if p4_path and p4_path.exists():
            run_p5 = get_phase_5()
            p5_output_dir = OUTPUTS_DIR / "P5"
            p5_output_dir.mkdir(parents=True, exist_ok=True)

            p5_output = await run_p5(
                vector_id=vector_id,
                input_path=p4_path,
                output_dir=p5_output_dir,
                append_mode=True,  # CRITICAL: Append to existing VWM, do not overwrite
            )

            results["chunks_added"] = p5_output.chunks_indexed if hasattr(p5_output, 'chunks_indexed') else 0
            if verbose:
                print(f"    Added {results['chunks_added']} new chunks to VWM")

        # Step 6: Re-run P6 to verify expanded VWM
        if verbose:
            print(f"\n  [P6] Verifying expanded VWM...")

        p5_path = get_latest_output(vector_id, 5)
        if p5_path and p5_path.exists():
            run_p6 = get_phase_6()
            p6_output_dir = OUTPUTS_DIR / "P6"
            p6_output_dir.mkdir(parents=True, exist_ok=True)

            p6_output = await run_p6(
                vector_id=vector_id,
                input_path=p5_path,
                output_dir=p6_output_dir,
            )

            results["new_integrity_score"] = p6_output.integrity_score if hasattr(p6_output, 'integrity_score') else 0
            if verbose:
                print(f"    New integrity score: {results['new_integrity_score']:.3f}")

        results["status"] = "success"

        if verbose:
            print(f"\n  [IRON LOOP COMPLETE] Loop {loop_number}")
            print(f"    Queries: {results['queries_generated']}")
            print(f"    URLs: {results['urls_found']}")
            print(f"    New Chunks: {results['chunks_added']}")

    except Exception as e:
        if verbose:
            print(f"\n  [IRON LOOP ERROR] {e}")
        results["status"] = "error"
        results["error"] = str(e)

    return results


# ============================================================================
# RUNNER
# ============================================================================

async def run_pipeline(
    vector_id: str,
    start_phase: int = 6,
    skip_p6: bool = False,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Run the POLARIS pipeline from P6 to P12 for a single vector.

    The pipeline handles gating logic:
    - CASE_1: Full pipeline to P12
    - CASE_2: Iterate P7-P9 up to MAX_ITERATIONS
    - CASE_3: Gap report (P11 only)
    - CASE_4: Failure report (P11 only)

    Args:
        vector_id: Vector ID to process
        start_phase: Phase to start from (default 6)
        skip_p6: Skip Phase 6 if already run
        verbose: Print progress information

    Returns:
        Dict with pipeline results and final gating case
    """
    config = get_config()
    start_time = datetime.now(timezone.utc)
    pipeline_start_time = time.time()
    ledger = Ledger()

    # Initialize cost tracker and check budget before starting
    cost_tracker = get_cost_tracker()
    try:
        cost_tracker.check_budget()
    except BudgetExceededError as e:
        raise RuntimeError(f"Cannot start pipeline: {e}")

    # ================================================================
    # DEEP AUDIT: Initialize real-time audit collector
    # ================================================================
    audit = AuditCollector(vector_id)
    set_audit(audit)  # Make globally accessible to phases
    audit.start_run()

    # Initialize saturation tracker for dynamic iteration control
    saturation_tracker = SaturationTracker()

    results = {
        "vector_id": vector_id,
        "start_time": start_time.isoformat(),
        "phases_completed": [],
        "iterations": 0,
        "final_gating_case": None,
        "stop_reason": None,
        "saturation_stats": {},
        "p8_stats": {},  # Claim verification stats
        "errors": [],
        "cost_at_start": cost_tracker.get_total_cost(),
        "sota_params": {
            "min_iterations": MIN_ITERATIONS,
            "max_iterations": MAX_ITERATIONS,
            "saturation_threshold": SATURATION_THRESHOLD,
        },
    }

    if verbose:
        print("\n" + "="*70)
        print("POLARIS PIPELINE RUNNER (SOTA-Aligned)")
        print(f"Vector ID: {vector_id}")
        print(f"Start Phase: P{start_phase}")
        print(f"Iterations: {MIN_ITERATIONS}-{MAX_ITERATIONS} (dynamic)")
        print(f"Max Execution Time: {MAX_EXECUTION_MINUTES} minutes")
        print(f"Budget Remaining: ${cost_tracker.get_remaining_budget():.4f}")
        print("="*70)

    try:
        # Phase 6: NLI Integrity
        if start_phase <= 6 and not skip_p6:
            if verbose:
                print("\n" + "-"*50)
                print("EXECUTING PHASE 6: NLI INTEGRITY")
                print("-"*50)

            # Audit: Start phase tracking
            audit.start_phase(6, "nli_integrity")

            # Get P5 output path
            p5_path = get_latest_output(vector_id, 5)
            if not p5_path:
                raise FileNotFoundError(f"No P5 output found for {vector_id}")

            p6_output_dir = OUTPUTS_DIR / "P6"
            p6_output_dir.mkdir(parents=True, exist_ok=True)

            run_p6 = get_phase_6()
            p6_output = await run_p6(
                vector_id=vector_id,
                input_path=p5_path,
                output_dir=p6_output_dir
            )
            results["phases_completed"].append("P6")
            results["p6_integrity_score"] = p6_output.integrity_score

            # Audit: End phase tracking
            audit.end_phase(6, "completed")

            # Save P6 output JSON (run_phase6 only saves verified_ids)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            p6_output_path = p6_output_dir / f"{vector_id}__P6__{timestamp}.json"
            with open(p6_output_path, "w", encoding="utf-8") as f:
                f.write(p6_output.model_dump_json(indent=2))

            if verbose:
                print(f"  Integrity Score: {p6_output.integrity_score:.3f}")

        # P7-P10 Iteration Loop (SOTA-aligned dynamic iteration)
        iteration = 0
        gating_case = None
        p8_cumulative_stats = {
            "total_claims": 0,
            "supported_claims": 0,
            "partial_claims": 0,
            "rejected_claims": 0,
            "blocked_citations": 0,
        }

        while True:  # Dynamic iteration - checked via saturation
            iteration += 1
            results["iterations"] = iteration

            # Calculate elapsed time
            elapsed_minutes = (time.time() - pipeline_start_time) / 60.0

            if verbose:
                print("\n" + "="*50)
                print(f"ITERATION {iteration}/{MAX_ITERATIONS} (dynamic, {elapsed_minutes:.1f}m elapsed)")
                print("="*50)

            # ================================================================
            # CORRECTION LOOP: P7 + P8 with regeneration on high hallucination
            # ================================================================
            rejected_claims_feedback = None
            p8_output = None

            for correction_attempt in range(MAX_CORRECTION_RETRIES):
                # Phase 7: Dual RAG
                if start_phase <= 7:
                    if verbose:
                        print("\n" + "-"*50)
                        if correction_attempt > 0:
                            print(f"EXECUTING PHASE 7: DUAL RAG (Correction Attempt {correction_attempt + 1}/{MAX_CORRECTION_RETRIES})")
                        else:
                            print("EXECUTING PHASE 7: DUAL RAG")
                        print("-"*50)

                    # Audit: Start phase tracking
                    audit.start_phase(7, "dual_rag")

                    # Get P6 output path
                    p6_path = get_latest_output(vector_id, 6)
                    if not p6_path:
                        raise FileNotFoundError(f"No P6 output found for {vector_id}")

                    p7_output_dir = OUTPUTS_DIR / "P7"
                    p7_output_dir.mkdir(parents=True, exist_ok=True)

                    run_p7 = get_phase_7()
                    p7_output = await run_p7(
                        vector_id=vector_id,
                        input_path=p6_path,
                        output_dir=p7_output_dir,
                        rejected_claims_feedback=rejected_claims_feedback,
                    )
                    results["phases_completed"].append(f"P7_iter{iteration}_attempt{correction_attempt}")

                    # Audit: End phase tracking
                    audit.end_phase(7, "completed")

                    # Save P7 output to file for P8 to read
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    p7_output_path = p7_output_dir / f"{vector_id}__P7__{timestamp}.json"
                    with open(p7_output_path, "w", encoding="utf-8") as f:
                        json.dump(p7_output.model_dump(), f, indent=2, ensure_ascii=False)

                    if verbose:
                        print(f"  Analysis Length: {len(p7_output.analysis_text)} chars")
                        print(f"  Citations: {len(p7_output.citation_tokens)}")

                # Phase 8: Claim-Evidence NLI Verification
                if verbose:
                    print("\n" + "-"*50)
                    print("EXECUTING PHASE 8: CLAIM VERIFICATION (NLI)")
                    print("-"*50)

                p7_output_path = get_latest_output(vector_id, 7)
                run_p8 = get_phase_8()
                p8_output = await run_p8(
                    vector_id=vector_id,
                    p7_output_path=p7_output_path
                )
                results["phases_completed"].append(f"P8_iter{iteration}_attempt{correction_attempt}")

                if verbose:
                    print(f"  Claims Verified: {p8_output.claims_total}")
                    print(f"  Supported: {p8_output.claims_supported} ({p8_output.verification_rate:.1%})")
                    print(f"  Partial: {p8_output.claims_partial}")
                    print(f"  Rejected: {p8_output.claims_rejected}")
                    print(f"  Citations Blocked: {len(p8_output.blocked_citations)}")
                    print(f"  Hallucination Rate: {p8_output.hallucination_rate:.1%}")

                # Check if hallucination rate is acceptable
                if p8_output.hallucination_rate <= HALLUCINATION_THRESHOLD:
                    if verbose:
                        print(f"\n  [OK] Hallucination rate {p8_output.hallucination_rate:.1%} <= {HALLUCINATION_THRESHOLD:.1%} threshold")
                    break
                elif correction_attempt < MAX_CORRECTION_RETRIES - 1:
                    # Extract rejected claims for feedback
                    rejected_claims_feedback = []
                    for result in p8_output.verification_results:
                        if result.get("status") == "rejected":
                            claim_text = result.get("claim_text", "")[:100]
                            if claim_text:
                                rejected_claims_feedback.append(claim_text)

                    if verbose:
                        print(f"\n  [WARN] Hallucination rate {p8_output.hallucination_rate:.1%} > {HALLUCINATION_THRESHOLD:.1%} threshold")
                        print(f"  [WARN] Triggering correction loop with {len(rejected_claims_feedback)} rejected claims")
                else:
                    if verbose:
                        print(f"\n  [WARN] Max correction retries reached. Accepting hallucination rate {p8_output.hallucination_rate:.1%}")

            # Accumulate P8 stats (from final attempt)
            p8_cumulative_stats["total_claims"] += p8_output.claims_total
            p8_cumulative_stats["supported_claims"] += p8_output.claims_supported
            p8_cumulative_stats["partial_claims"] += p8_output.claims_partial
            p8_cumulative_stats["rejected_claims"] += p8_output.claims_rejected
            p8_cumulative_stats["blocked_citations"] += len(p8_output.blocked_citations)

            # Update saturation tracker with P8 metrics
            novelty = 1.0 - p8_output.verification_rate if p8_output.claims_total > 0 else 1.0
            coverage = p8_output.verification_rate
            saturation_tracker.record_iteration(novelty, coverage)

            # Phase 9: Adversarial QA
            if start_phase <= 9:
                if verbose:
                    print("\n" + "-"*50)
                    print("EXECUTING PHASE 9: ADVERSARIAL QA")
                    print("-"*50)

                # Audit: Start phase tracking
                audit.start_phase(9, "adversarial_qa")

                run_p9 = get_phase_9()
                p9_output = await run_p9(vector_id=vector_id)
                results["phases_completed"].append(f"P9_iter{iteration}")

                # Audit: End phase tracking
                audit.end_phase(9, "completed")

                if verbose:
                    print(f"  Resolution Rate: {p9_output.resolution_rate:.2%}")
                    print(f"  Gaps: {p9_output.unresolved_count}")

                # ================================================================
                # RECURSIVE GAP-FILLING (SOTA "Rabbit Hole" Logic)
                # ================================================================
                # Check if we need to trigger recursive search:
                # 1. P9 detected unresolved gaps
                # 2. Current word count is below target
                current_word_count = len(p7_output.analysis_text.split()) if hasattr(p7_output, 'analysis_text') else 0
                has_gaps = p9_output.unresolved_count > 0
                below_word_target = current_word_count < MIN_WORD_COUNT_TARGET

                # Initialize recursion tracking if not present
                if "recursion_stats" not in results:
                    results["recursion_stats"] = {"depth": 0, "total_new_chunks": 0, "recursions": []}

                current_recursion_depth = results["recursion_stats"]["depth"]

                if (has_gaps or below_word_target) and current_recursion_depth < MAX_RECURSION_DEPTH:
                    if verbose:
                        print(f"\n  [GAP DETECTED] Triggering recursive search...")
                        print(f"    - Unresolved gaps: {p9_output.unresolved_count}")
                        print(f"    - Word count: {current_word_count}/{MIN_WORD_COUNT_TARGET}")
                        print(f"    - Recursion depth: {current_recursion_depth + 1}/{MAX_RECURSION_DEPTH}")

                    # Extract gap questions from P9
                    gap_questions = extract_gap_questions_from_p9(p9_output)

                    if gap_questions:
                        # Run recursive gap-filling
                        recursion_result = await run_gap_filling_recursion(
                            vector_id=vector_id,
                            gap_questions=gap_questions,
                            recursion_depth=current_recursion_depth + 1,
                            verbose=verbose
                        )

                        # Update recursion stats
                        results["recursion_stats"]["depth"] = current_recursion_depth + 1
                        results["recursion_stats"]["total_new_chunks"] += recursion_result.get("chunks_added", 0)
                        results["recursion_stats"]["recursions"].append(recursion_result)
                        results["phases_completed"].append(f"RECURSION_depth{current_recursion_depth + 1}")

                        # If we added new chunks, re-run P6 to verify the expanded VWM
                        if recursion_result.get("chunks_added", 0) > 0:
                            if verbose:
                                print(f"\n  [RE-VERIFYING] Running P6 on expanded VWM...")

                            p5_path = get_latest_output(vector_id, 5)
                            if p5_path:
                                p6_output_dir = OUTPUTS_DIR / "P6"
                                p6_output_dir.mkdir(parents=True, exist_ok=True)

                                run_p6 = get_phase_6()
                                p6_output = await run_p6(
                                    vector_id=vector_id,
                                    input_path=p5_path,
                                    output_dir=p6_output_dir
                                )
                                results["phases_completed"].append(f"P6_post_recursion_{current_recursion_depth + 1}")

                                if verbose:
                                    print(f"    New integrity score: {p6_output.integrity_score:.3f}")

            # Phase 10: Gating
            if start_phase <= 10:
                if verbose:
                    print("\n" + "-"*50)
                    print("EXECUTING PHASE 10: GATING LOGIC")
                    print("-"*50)

                # Audit: Start phase tracking
                audit.start_phase(10, "gating")

                run_p10 = get_phase_10()
                p10_output = await run_p10(
                    vector_id=vector_id,
                    iteration_count=iteration
                )
                results["phases_completed"].append(f"P10_iter{iteration}")
                gating_case = p10_output.gating_case
                results["final_gating_case"] = gating_case.value

                # Audit: End phase tracking
                audit.end_phase(10, "completed")

                if verbose:
                    print(f"  Gating Case: {gating_case.value}")
                    print(f"  Sufficiency: {p10_output.sufficiency_score:.3f}")
                    print(f"  Confidence: {p10_output.confidence_score:.3f}")
                    print(f"  Integrity: {p10_output.integrity_score:.3f}")

            # Check saturation-based stopping (SOTA dynamic iteration)
            should_stop, stop_reason = saturation_tracker.should_stop(iteration, elapsed_minutes)

            # Check gating decision combined with saturation
            if gating_case == GatingCase.CASE_1:
                if verbose:
                    print("\n>>> CASE_1: Sufficient evidence - proceeding to finalization")
                results["stop_reason"] = "case_1_sufficient_evidence"
                break
            elif gating_case == GatingCase.CASE_2:
                if should_stop:
                    if verbose:
                        print(f"\n>>> CASE_2: Saturation detected ({stop_reason}) - generating report")
                    results["stop_reason"] = stop_reason
                    break
                else:
                    if verbose:
                        print(f"\n>>> CASE_2: Partial evidence - continuing ({iteration}/{MAX_ITERATIONS})")
                    continue
            elif gating_case == GatingCase.CASE_3:
                # ================================================================
                # IRON LOOP: True Recursion on CASE_3 (Gap Detected)
                # ================================================================
                # Initialize iron loop counter if not present
                if "iron_loop_count" not in results:
                    results["iron_loop_count"] = 0

                iron_loop_count = results["iron_loop_count"]
                max_iron_loops = 3

                if iron_loop_count >= max_iron_loops:
                    if verbose:
                        print(f"\n>>> CASE_3: Max Iron Loops ({max_iron_loops}) reached - generating gap report")
                    results["stop_reason"] = "case_3_max_iron_loops"
                    break

                # Extract gap questions from P9
                gap_questions = extract_gap_questions_from_p9(p9_output)

                if not gap_questions:
                    if verbose:
                        print("\n>>> CASE_3: No extractable gaps - generating gap report")
                    results["stop_reason"] = "case_3_no_extractable_gaps"
                    break

                # IRON LOOP: Loop back to P2-P5 with gap questions
                results["iron_loop_count"] = iron_loop_count + 1

                if verbose:
                    print(f"\n>>> [IRON LOOP] CASE_3 Gap Detected - Looping back (Loop {iron_loop_count + 1}/{max_iron_loops})")
                    print(f"    Gap Questions: {len(gap_questions)}")
                    for i, q in enumerate(gap_questions[:3], 1):
                        print(f"      Q{i}: {q[:80]}...")

                # Run P2-P5 with gap focus
                iron_loop_result = await run_iron_loop_acquisition(
                    vector_id=vector_id,
                    gap_questions=gap_questions,
                    loop_number=iron_loop_count + 1,
                    verbose=verbose
                )

                if "iron_loop_results" not in results:
                    results["iron_loop_results"] = []
                results["iron_loop_results"].append(iron_loop_result)
                results["phases_completed"].append(f"IRON_LOOP_{iron_loop_count + 1}")

                if verbose:
                    print(f"    [IRON LOOP] Added {iron_loop_result.get('chunks_added', 0)} new chunks")
                    print(f"    [IRON LOOP] Continuing to P6-P9...")

                # Continue the main loop - will re-run P6-P9 with expanded VWM
                continue
            elif gating_case == GatingCase.CASE_4:
                if verbose:
                    print("\n>>> CASE_4: Integrity failure - generating failure report")
                results["stop_reason"] = "case_4_integrity_failure"
                break

        # Store P8 cumulative stats and saturation stats
        results["p8_stats"] = p8_cumulative_stats
        results["saturation_stats"] = saturation_tracker.get_stats()

        # Post-Gating Phases (P11-P13)
        # P11 only runs for CASE_1
        if gating_case == GatingCase.CASE_1:
            if verbose:
                print("\n" + "-"*50)
                print("EXECUTING PHASE 11: KNOWLEDGE INTEGRATION")
                print("-"*50)

            # Audit: Start phase tracking
            audit.start_phase(11, "knowledge_integration")

            run_p11 = get_phase_11()
            p11_output = await run_p11(vector_id=vector_id)
            results["phases_completed"].append("P11")

            # Audit: End phase tracking
            audit.end_phase(11, "completed")

            if verbose:
                print(f"  LTM Updated: {p11_output.ltm_global_updated}")
                print(f"  Claims Persisted: {p11_output.claims_persisted}")

        # P12 runs for all cases (different output types)
        if verbose:
            print("\n" + "-"*50)
            print("EXECUTING PHASE 12: RESEARCH PACKAGING")
            print("-"*50)

        # Audit: Start phase tracking
        audit.start_phase(12, "research_packaging")

        run_p12 = get_phase_12()
        p12_output = await run_p12(vector_id=vector_id)
        results["phases_completed"].append("P12")
        results["output_type"] = p12_output.output_type.value
        results["word_count"] = p12_output.word_count
        results["citation_count"] = p12_output.citation_count

        # Audit: End phase tracking
        audit.end_phase(12, "completed")

        if verbose:
            print(f"  Output Type: {p12_output.output_type.value}")
            print(f"  Word Count: {p12_output.word_count}")
            print(f"  Citations: {p12_output.citation_count}")

        # P13 runs for CASE_1 and CASE_2 (narrative synthesis)
        if gating_case in [GatingCase.CASE_1, GatingCase.CASE_2]:
            if verbose:
                print("\n" + "-"*50)
                print("EXECUTING PHASE 13: NARRATIVE SYNTHESIS")
                print("-"*50)

            run_p13 = get_phase_13()
            p13_output = await run_p13(vector_id=vector_id)
            results["phases_completed"].append("P13")

            if verbose:
                print(f"  Stage: {p13_output.stage}")
                print(f"  Patterns: {len(p13_output.cross_vector_patterns)}")
                print(f"  Themes: {len(p13_output.key_themes)}")

        # Finalize
        end_time = datetime.now(timezone.utc)
        results["end_time"] = end_time.isoformat()
        results["duration_seconds"] = (end_time - start_time).total_seconds()
        results["success"] = True

        # Track final cost
        cost_at_end = cost_tracker.get_total_cost()
        results["cost_at_end"] = cost_at_end
        results["cost_for_vector"] = cost_at_end - results["cost_at_start"]

        # ================================================================
        # DEEP AUDIT: Finalize and generate comprehensive report
        # ================================================================
        if verbose:
            print("\n" + "="*70)
            print("GENERATING DEEP AUDIT REPORT")
            print("="*70)

        try:
            # End deep audit collection
            audit.end_run()

            # Generate comprehensive deep audit report
            deep_audit_report = audit.generate_report()
            results["deep_audit"] = {
                "audit_dir": str(audit.audit_dir),
                "summary": deep_audit_report.get("summary", {}),
                "gaps": deep_audit_report.get("gaps", []),
                "recommendations": deep_audit_report.get("recommendations", []),
            }

            if verbose:
                audit.print_summary()
                print(f"\n  Deep Audit Directory: {audit.audit_dir}")

        except Exception as deep_audit_error:
            if verbose:
                print(f"\n  [WARNING] Deep audit failed: {deep_audit_error}")
            results["deep_audit_error"] = str(deep_audit_error)

        # ================================================================
        # BENCHMARK AUDIT (RAGAS + NLI evaluation)
        # ================================================================
        if verbose:
            print("\n" + "-"*50)
            print("RUNNING BENCHMARK AUDIT")
            print("-"*50)

        try:
            RunnerAuditor = get_runner_auditor()
            auditor = RunnerAuditor(vector_id)
            auditor.load_all_phase_outputs()
            auditor.run_benchmark_audit()
            auditor.analyze_gaps()

            audit_report = auditor.generate_comprehensive_report()
            results["audit"] = audit_report

            # Save audit report
            audit_dir = OUTPUTS_DIR / "audits"
            audit_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            audit_path = audit_dir / f"{vector_id}__audit__{timestamp}.json"
            with open(audit_path, "w", encoding="utf-8") as f:
                json.dump(audit_report, f, indent=2)
            results["audit_path"] = str(audit_path)

            if verbose:
                auditor.print_summary()
                print(f"\n  Benchmark Audit Report: {audit_path}")

        except Exception as audit_error:
            if verbose:
                print(f"\n  [WARNING] Benchmark audit failed: {audit_error}")
            results["audit_error"] = str(audit_error)

        # ================================================================

        if verbose:
            print("\n" + "="*70)
            print("PIPELINE COMPLETE (SOTA-Aligned)")
            print("="*70)
            print(f"  Vector: {vector_id}")
            print(f"  Final Gating: {results['final_gating_case']}")
            print(f"  Stop Reason: {results.get('stop_reason', 'N/A')}")
            print(f"  Iterations: {results['iterations']}/{MAX_ITERATIONS}")
            print(f"  Duration: {results['duration_seconds']:.1f}s ({results['duration_seconds']/60:.1f}m)")
            print(f"  Output Type: {results.get('output_type', 'N/A')}")
            print(f"  Cost: ${results['cost_for_vector']:.4f}")

            # P8 summary
            p8_stats = results.get("p8_stats", {})
            if p8_stats.get("total_claims", 0) > 0:
                support_rate = p8_stats["supported_claims"] / p8_stats["total_claims"]
                print(f"\n  [P8 VERIFICATION]")
                print(f"    Total Claims: {p8_stats['total_claims']}")
                print(f"    Supported: {p8_stats['supported_claims']} ({support_rate:.1%})")
                print(f"    Blocked Citations: {p8_stats['blocked_citations']}")

            # Saturation summary
            sat_stats = results.get("saturation_stats", {})
            if sat_stats.get("iterations_tracked", 0) > 0:
                print(f"\n  [SATURATION TRACKING]")
                print(f"    Final Coverage: {sat_stats.get('final_coverage', 0):.1%}")
                print(f"    Avg Novelty: {sat_stats.get('avg_novelty', 0):.2f}")

            print("="*70)

    except Exception as e:
        results["success"] = False
        results["errors"].append(str(e))
        results["end_time"] = datetime.now(timezone.utc).isoformat()

        if verbose:
            print(f"\n[ERROR] Pipeline failed: {e}")

        # Log error to results (don't use ledger with invalid phase)
        print(f"  [ERROR] {str(e)}")

        raise

    return results


# ============================================================================
# CLI
# ============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="POLARIS Pipeline Runner (P6-P13) - SOTA-Aligned with Dynamic Iteration"
    )
    parser.add_argument(
        "--vector-id",
        required=True,
        help="Vector ID to process"
    )
    parser.add_argument(
        "--start-phase",
        type=int,
        default=6,
        help="Phase to start from (default: 6)"
    )
    parser.add_argument(
        "--skip-p6",
        action="store_true",
        help="Skip Phase 6 if already run"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help=f"Override max iterations (default: {MAX_ITERATIONS} from config)"
    )
    parser.add_argument(
        "--output",
        help="Path to save results JSON"
    )

    args = parser.parse_args()

    # Run pipeline
    results = asyncio.run(run_pipeline(
        vector_id=args.vector_id,
        start_phase=args.start_phase,
        skip_p6=args.skip_p6,
        verbose=not args.quiet
    ))

    # Save results if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {output_path}")

    # Exit with appropriate code
    if results.get("success"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
