#!/usr/bin/env python3
"""
POLARIS Phase 0: Initialization & Novelty Check
================================================
Standalone CLI script for vector initialization.

Purpose:
- Parse vector_id to extract stage, application, region
- Create or recover VWM collection for this vector
- Compute SHA256 fingerprint of vector question
- Check for duplicate/near-duplicate vectors

Usage:
    python src/phases/p00_init.py --vector-id S1V1_Household_Water_Filter_NORTH_AMERICA --output outputs/P0/

CLI Contract:
    --vector-id: Required. Vector ID string.
    --output: Optional. Output directory (default: outputs/P0/)
    --config: Optional. Config directory (default: config/settings)
    --self-test: Run self-test mode
"""

import argparse
import hashlib
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional, Tuple

# Configure logging
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase0Output
from src.state.ledger import Ledger, append_ledger
from src.config import get_config, OUTPUTS_DIR, STATE_DIR
from src.memory.chroma_client import ChromaManager, get_chroma_manager
from config.vector_library import validate_vector_id as library_validate_vector_id, get_vector_by_id
from src.audit import get_audit
from src.utils.question_classifier import classify_question


# =============================================================================
# CONSTANTS
# =============================================================================

# Stage configuration
REGIONAL_STAGES = {1, 2, 3, 6, 8}
GLOBAL_STAGES = {4, 5, 7, 9, 10, 11, 12, 13}

STAGE_NAMES = {
    1: "Contamination Problem Identification",
    2: "Cost of Pain Quantification",
    3: "Solution Landscape Analysis",
    4: "Technology Gap Identification",
    5: "C-POLAR Value Proposition",
    6: "Market Size Quantification",
    7: "Competitive Intelligence",
    8: "Regulatory Pathway Analysis",
    9: "Technical Feasibility Assessment",
    10: "Business Model Design",
    11: "Financial Modeling",
    12: "Risk Assessment",
    13: "Go-to-Market Strategy",
}

# Question templates by stage (simplified - full templates in vector_library)
QUESTION_TEMPLATES = {
    1: "What {topic} contamination rates and patterns exist in {application} for {region}?",
    2: "What is the economic impact of contamination in {application} for {region}?",
    3: "What antimicrobial solutions exist for {application} in {region}?",
    4: "What technology gaps exist in antimicrobial solutions for {application}?",
    5: "What unique value does C-POLAR provide for {application}?",
    6: "What is the market size for antimicrobial solutions in {application} for {region}?",
    7: "Who are the competitors in antimicrobial solutions for {application}?",
    8: "What are the regulatory requirements for antimicrobial coatings in {application} for {region}?",
    9: "What is the technical feasibility of C-POLAR for {application}?",
    10: "What business models suit C-POLAR deployment in {application}?",
    11: "What are the financial projections for C-POLAR in {application}?",
    12: "What risks exist for C-POLAR deployment in {application}?",
    13: "What is the go-to-market strategy for C-POLAR in {application}?",
}


# =============================================================================
# VECTOR PARSING
# =============================================================================

def parse_vector_id(vector_id: str) -> Tuple[int, int, str, str]:
    """
    Parse vector ID into components.

    Args:
        vector_id: e.g., "S1V1_Household_Water_Filter_NORTH_AMERICA"

    Returns:
        Tuple of (stage, vector_number, application, region)

    Raises:
        ValueError: If vector_id format is invalid
    """
    # Pattern: S{stage}V{num}_{application}_{region}
    pattern = r'^S(\d+)V(\d+)_(.+)_(NORTH_AMERICA|EUROPE|ASIA_PACIFIC|GLOBAL)$'
    match = re.match(pattern, vector_id)

    if not match:
        raise ValueError(
            f"Invalid vector_id format: {vector_id}. "
            f"Expected: S{{stage}}V{{num}}_{{application}}_{{region}}"
        )

    stage = int(match.group(1))
    vector_number = int(match.group(2))
    application = match.group(3)
    region = match.group(4)

    # Validate stage
    if stage < 1 or stage > 13:
        raise ValueError(f"Invalid stage {stage}. Must be 1-13.")

    # Validate region matches stage type
    is_regional = stage in REGIONAL_STAGES
    if is_regional and region == "GLOBAL":
        raise ValueError(f"Stage {stage} is regional but region is GLOBAL")
    if not is_regional and region != "GLOBAL":
        raise ValueError(f"Stage {stage} is global but region is {region}")

    return stage, vector_number, application, region


def generate_question(stage: int, application: str, region: str) -> str:
    """Generate the research question for a vector."""
    template = QUESTION_TEMPLATES.get(stage, "Research {application} for {region}")

    # Replace placeholders
    question = template.replace("{application}", application.replace("_", " "))
    question = question.replace("{region}", region.replace("_", " "))
    question = question.replace("{topic}", "pathogen")  # Default topic

    return question


def compute_fingerprint(question: str) -> str:
    """Compute SHA256 fingerprint of question."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()


# =============================================================================
# SOTA: PICO FRAMEWORK EXTRACTION
# Based on: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4431673/
# =============================================================================

# Region to ISO code mapping
REGION_ISO_CODES = {
    "NORTH_AMERICA": ["US", "CA", "MX"],
    "EUROPE": ["GB", "DE", "FR", "IT", "ES", "NL", "BE", "SE", "NO", "DK", "FI", "AT", "CH", "IE", "PT", "PL"],
    "ASIA_PACIFIC": ["CN", "JP", "KR", "IN", "AU", "NZ", "SG", "MY", "TH", "ID", "PH", "VN", "TW", "HK"],
    "GLOBAL": [],  # No geographic filter for global
}

# Region to keyword mapping
REGION_KEYWORDS = {
    "NORTH_AMERICA": ["United States", "USA", "Canada", "Mexico", "North America", "American", "Canadian"],
    "EUROPE": ["Europe", "European Union", "UK", "Germany", "France", "European", "Britain", "British"],
    "ASIA_PACIFIC": ["Asia", "Pacific", "China", "Japan", "Australia", "Asian", "APAC", "Asia-Pacific"],
    "GLOBAL": ["worldwide", "global", "international"],
}

# Stage-specific PICO templates
STAGE_PICO_TEMPLATES = {
    1: {  # Contamination Problem Identification
        "population": "water supply systems and users",
        "intervention": "contamination assessment",
        "comparison": "safe water standards",
        "outcome": "contamination rates and patterns",
    },
    2: {  # Cost of Pain Quantification
        "population": "affected communities and healthcare systems",
        "intervention": "waterborne illness impacts",
        "comparison": "baseline health metrics",
        "outcome": "economic and health costs",
    },
    3: {  # Solution Landscape Analysis
        "population": "water treatment market",
        "intervention": "antimicrobial solutions",
        "comparison": "existing treatment methods",
        "outcome": "efficacy and market adoption",
    },
    4: {  # Technology Gap Identification
        "population": "water treatment technologies",
        "intervention": "technology assessment",
        "comparison": "ideal performance standards",
        "outcome": "identified technology gaps",
    },
    5: {  # C-POLAR Value Proposition
        "population": "water treatment stakeholders",
        "intervention": "C-POLAR technology",
        "comparison": "existing antimicrobial solutions",
        "outcome": "unique value and differentiation",
    },
    6: {  # Market Size Quantification
        "population": "water treatment market segments",
        "intervention": "market analysis",
        "comparison": "historical market data",
        "outcome": "market size and growth projections",
    },
    7: {  # Competitive Intelligence
        "population": "antimicrobial coating market",
        "intervention": "competitor analysis",
        "comparison": "C-POLAR capabilities",
        "outcome": "competitive positioning",
    },
    8: {  # Regulatory Pathway Analysis
        "population": "water treatment regulations",
        "intervention": "regulatory assessment",
        "comparison": "compliance requirements",
        "outcome": "regulatory pathway and timeline",
    },
}


def extract_pico_fields(
    stage: int,
    application: str,
    question: str,
) -> dict:
    """
    SOTA: Extract PICO framework fields from the vector context.

    PICO = Population, Intervention, Comparison, Outcome
    This helps structure queries for systematic review-style research.

    Args:
        stage: The vector stage (1-13)
        application: The application area (e.g., "Household_Water_Filter")
        question: The research question

    Returns:
        Dict with pico_population, pico_intervention, pico_comparison, pico_outcome
    """
    # Get stage template or default
    template = STAGE_PICO_TEMPLATES.get(stage, {
        "population": "target market",
        "intervention": "proposed solution",
        "comparison": "existing alternatives",
        "outcome": "expected results",
    })

    # Customize with application context
    app_clean = application.replace("_", " ").lower()

    pico = {
        "pico_population": f"{app_clean} - {template['population']}",
        "pico_intervention": template["intervention"],
        "pico_comparison": template["comparison"],
        "pico_outcome": template["outcome"],
    }

    # Extract specific terms from question if present
    question_lower = question.lower()

    # Look for population indicators
    if "household" in question_lower or "residential" in question_lower:
        pico["pico_population"] = f"household/residential {app_clean}"
    elif "commercial" in question_lower or "industrial" in question_lower:
        pico["pico_population"] = f"commercial/industrial {app_clean}"
    elif "municipal" in question_lower or "public" in question_lower:
        pico["pico_population"] = f"municipal/public {app_clean}"

    # Look for outcome indicators
    if "contamination" in question_lower:
        pico["pico_outcome"] = "contamination rates and pathogen presence"
    elif "cost" in question_lower or "economic" in question_lower:
        pico["pico_outcome"] = "economic costs and financial impact"
    elif "efficacy" in question_lower or "effectiveness" in question_lower:
        pico["pico_outcome"] = "treatment efficacy and effectiveness"

    return pico


def extract_geographic_scope(region: str) -> Tuple[list, list]:
    """
    SOTA: Extract geographic scope as ISO codes and keywords.

    Args:
        region: Region string (e.g., "NORTH_AMERICA")

    Returns:
        Tuple of (iso_codes, keywords)
    """
    iso_codes = REGION_ISO_CODES.get(region, [])
    keywords = REGION_KEYWORDS.get(region, [])

    return iso_codes, keywords


# =============================================================================
# VWM MANAGEMENT
# =============================================================================

# Module-level ChromaManager instance (lazy initialized)
_chroma: Optional[ChromaManager] = None


def _get_chroma() -> ChromaManager:
    """Get or initialize ChromaManager."""
    global _chroma
    if _chroma is None:
        _chroma = get_chroma_manager()
    return _chroma


def get_vwm_collection_name(vector_id: str) -> str:
    """Generate VWM collection name for a vector."""
    chroma = _get_chroma()
    return chroma.get_vwm_name(vector_id)


def create_vwm_collection(vector_id: str) -> str:
    """
    Create or recover VWM collection.

    Uses real ChromaDB via ChromaManager.

    Args:
        vector_id: The vector ID to create VWM for

    Returns:
        Collection name if successful

    Raises:
        RuntimeError: If collection creation fails
    """
    chroma = _get_chroma()
    collection = chroma.register_vwm(vector_id)

    if collection is None:
        raise RuntimeError(f"Failed to create VWM collection for {vector_id}")

    return collection.name


# =============================================================================
# NOVELTY CHECK
# =============================================================================

def check_novelty(fingerprint: str, stage: int, region: str) -> Tuple[str, Optional[str], Optional[float]]:
    """
    Check if this vector is a duplicate or near-duplicate.

    Queries LTM-Global for fingerprint matches using ChromaDB.

    Args:
        fingerprint: SHA256 hash of the question
        stage: Stage number
        region: Region string

    Returns:
        Tuple of (status, peer_vector_id, similarity_score)
        status: "proceed" | "duplicate" | "near_duplicate"
    """
    chroma = _get_chroma()
    return chroma.check_fingerprint_novelty(fingerprint, stage, region)


def register_fingerprint(
    fingerprint: str,
    vector_id: str,
    question: str,
    stage: int,
    region: str,
) -> None:
    """
    Register a fingerprint in LTM-Global after successful processing.

    Args:
        fingerprint: SHA256 hash of the question
        vector_id: Vector ID
        question: The full question text
        stage: Stage number
        region: Region string
    """
    chroma = _get_chroma()
    chroma.register_fingerprint(fingerprint, vector_id, question, stage, region)


# =============================================================================
# MAIN PHASE LOGIC
# =============================================================================

def run_phase0(
    vector_id: str,
    output_dir: Path,
    skip_library_validation: bool = False,
) -> Phase0Output:
    """
    Execute Phase 0: Initialization & Novelty Check.

    Args:
        vector_id: Vector ID to process
        output_dir: Directory to write output
        skip_library_validation: Skip vector library validation (for self-test)

    Returns:
        Phase0Output model
    """
    timestamps = {"start": datetime.now(UTC).isoformat() + "Z"}
    audit = get_audit()

    # 0. Validate vector exists in library (unless skipped for testing)
    if not skip_library_validation:
        if not library_validate_vector_id(vector_id):
            raise ValueError(f"Vector ID not found in library: {vector_id}")

    # 1. Parse vector ID
    stage, vector_number, application, region = parse_vector_id(vector_id)

    # Audit: Log vector parsing
    if audit:
        audit.log_vector_parse(
            raw_input_size=len(vector_id),
            hard_constraints=[
                f"stage:{stage}",
                f"region:{region}",
            ],
            soft_constraints=[
                f"application:{application}",
            ],
            parsing_method="regex",
        )

    # 2. Generate question
    question = generate_question(stage, application, region)

    # 3. Compute fingerprint
    fingerprint = compute_fingerprint(question)

    # 4. Check novelty BEFORE creating VWM (to detect duplicates)
    status, peer_vector_id, similarity_score = check_novelty(fingerprint, stage, region)

    # 5. Create VWM collection (real ChromaDB)
    vwm_collection = create_vwm_collection(vector_id)

    # 6. SOTA: Classify question type (Sprint 2)
    classification = classify_question(question=question, vector_id=vector_id, use_llm=False)
    question_type = classification.question_type if isinstance(classification.question_type, str) else classification.question_type.value
    question_type_confidence = classification.confidence
    classification_method = classification.classification_method

    # 7. Register fingerprint in LTM-Global (if proceeding)
    if status == "proceed":
        register_fingerprint(
            fingerprint=fingerprint,
            vector_id=vector_id,
            question=question,
            stage=stage,
            region=region,
        )

    # 8. SOTA: Extract PICO framework fields
    pico_fields = extract_pico_fields(stage, application, question)

    # 9. SOTA: Extract geographic scope
    geographic_scope, geographic_keywords = extract_geographic_scope(region)

    timestamps["end"] = datetime.now(UTC).isoformat() + "Z"

    # 10. Build output
    output = Phase0Output(
        vector_id=vector_id,
        status=status,
        fingerprint=fingerprint,
        vwm_collection=vwm_collection,
        peer_vector_id=peer_vector_id,
        similarity_score=similarity_score,
        timestamps=timestamps,
        stage=stage,
        application=application,
        region=region,
        question=question,
        is_regional=stage in REGIONAL_STAGES,
        # SOTA: Classification results (Sprint 2)
        question_type=question_type,
        question_type_confidence=question_type_confidence,
        classification_method=classification_method,
        # SOTA: PICO framework extraction
        pico_population=pico_fields["pico_population"],
        pico_intervention=pico_fields["pico_intervention"],
        pico_comparison=pico_fields["pico_comparison"],
        pico_outcome=pico_fields["pico_outcome"],
        # SOTA: Geographic scope
        geographic_scope=geographic_scope if geographic_scope else None,
        geographic_keywords=geographic_keywords if geographic_keywords else None,
    )

    return output


# =============================================================================
# SELF-TEST
# =============================================================================

def run_self_test() -> bool:
    """
    Run Phase 0 self-tests.

    Tests:
    1. Valid vector ID parsing
    2. Invalid vector ID rejection
    3. VWM collection creation
    4. Duplicate detection (when LTM populated)
    """
    print("Running Phase 0 self-tests...")

    # Test 1: Valid regional vector
    try:
        stage, num, app, region = parse_vector_id("S1V1_Household_Water_Filter_NORTH_AMERICA")
        assert stage == 1
        assert num == 1
        assert app == "Household_Water_Filter"
        assert region == "NORTH_AMERICA"
        print("  [PASS] Valid regional vector parsing")
    except Exception as e:
        print(f"  [FAIL] Valid regional vector parsing: {e}")
        return False

    # Test 2: Valid global vector
    try:
        stage, num, app, region = parse_vector_id("S4V1_HVAC_Systems_GLOBAL")
        assert stage == 4
        assert region == "GLOBAL"
        print("  [PASS] Valid global vector parsing")
    except Exception as e:
        print(f"  [FAIL] Valid global vector parsing: {e}")
        return False

    # Test 3: Invalid format rejection
    try:
        parse_vector_id("invalid_vector_id")
        print("  [FAIL] Invalid format should be rejected")
        return False
    except ValueError:
        print("  [PASS] Invalid format rejected")

    # Test 4: Stage/region mismatch rejection
    try:
        parse_vector_id("S1V1_Test_GLOBAL")  # Stage 1 is regional, can't be GLOBAL
        print("  [FAIL] Stage/region mismatch should be rejected")
        return False
    except ValueError:
        print("  [PASS] Stage/region mismatch rejected")

    # Test 5: Question generation
    question = generate_question(1, "Household_Water_Filter", "NORTH_AMERICA")
    assert "Household Water Filter" in question
    assert "NORTH AMERICA" in question
    print("  [PASS] Question generation")

    # Test 6: Fingerprint consistency
    fp1 = compute_fingerprint("test question")
    fp2 = compute_fingerprint("test question")
    fp3 = compute_fingerprint("different question")
    assert fp1 == fp2
    assert fp1 != fp3
    print("  [PASS] Fingerprint consistency")

    # Test 7: VWM collection naming
    name = get_vwm_collection_name("S1V1_Test_NORTH_AMERICA")
    assert name.startswith("vwm_")
    assert len(name) <= 63
    print("  [PASS] VWM collection naming")

    # Test 8: Full phase execution
    try:
        output = run_phase0(
            "S1V1_Household_Water_Filter_NORTH_AMERICA",
            OUTPUTS_DIR / "P0"
        )
        # Accept both "proceed" and "duplicate" (duplicate means previous run registered fingerprint)
        assert output.status in ["proceed", "duplicate", "near_duplicate"]
        assert output.stage == 1
        assert output.is_regional is True
        print(f"  [PASS] Full phase execution (status={output.status})")
    except Exception as e:
        print(f"  [FAIL] Full phase execution: {e}")
        return False

    # Test 9: Question type classification
    try:
        assert output.question_type is not None
        assert output.question_type_confidence is not None
        assert output.question_type_confidence >= 0.0
        print(f"  [PASS] Question type classification: {output.question_type} (conf={output.question_type_confidence:.2f})")
    except Exception as e:
        print(f"  [FAIL] Question type classification: {e}")
        return False

    # Test 10: SOTA PICO extraction
    try:
        assert output.pico_population is not None
        assert output.pico_intervention is not None
        assert output.pico_comparison is not None
        assert output.pico_outcome is not None
        print(f"  [PASS] PICO extraction: P={output.pico_population[:30]}...")
    except Exception as e:
        print(f"  [FAIL] PICO extraction: {e}")
        return False

    # Test 11: SOTA Geographic scope extraction
    try:
        assert output.geographic_scope is not None
        assert output.geographic_keywords is not None
        assert "US" in output.geographic_scope  # NORTH_AMERICA should include US
        assert "Canada" in output.geographic_keywords or "United States" in output.geographic_keywords
        print(f"  [PASS] Geographic scope: ISO={output.geographic_scope}, keywords={len(output.geographic_keywords)}")
    except Exception as e:
        print(f"  [FAIL] Geographic scope extraction: {e}")
        return False

    print("\nAll Phase 0 self-tests PASSED!")
    return True


# =============================================================================
# CLI ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="POLARIS Phase 0: Initialization & Novelty Check"
    )
    parser.add_argument(
        "--vector-id",
        type=str,
        help="Vector ID to process (e.g., S1V1_Household_Water_Filter_NORTH_AMERICA)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=str(OUTPUTS_DIR / "P0"),
        help="Output directory"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/settings",
        help="Config directory"
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run self-test mode"
    )

    args = parser.parse_args()

    # Self-test mode
    if args.self_test:
        success = run_self_test()
        sys.exit(0 if success else 1)

    # Normal execution requires vector-id
    if not args.vector_id:
        parser.error("--vector-id is required (unless using --self-test)")

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Log to ledger: running
    ledger = Ledger()
    ledger.append(
        vector_id=args.vector_id,
        phase=0,
        status="running",
        attempt=1
    )

    try:
        # Execute phase
        print(f"[PHASE-0][{args.vector_id}][INFO] Starting initialization...")
        output = run_phase0(args.vector_id, output_dir)

        # Write output
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"{args.vector_id}__P0__{timestamp}.json"

        with open(output_file, "w", encoding="utf-8") as f:
            f.write(output.model_dump_json(indent=2))

        print(f"[PHASE-0][{args.vector_id}][INFO] Output: {output_file}")
        print(f"[PHASE-0][{args.vector_id}][INFO] Status: {output.status}")
        print(f"[PHASE-0][{args.vector_id}][INFO] Stage: {output.stage} ({STAGE_NAMES.get(output.stage, 'Unknown')})")
        print(f"[PHASE-0][{args.vector_id}][INFO] Regional: {output.is_regional}")
        print(f"[PHASE-0][{args.vector_id}][INFO] Question Type: {output.question_type} (conf={output.question_type_confidence:.2f})")

        # Log to ledger: completed
        ledger.append(
            vector_id=args.vector_id,
            phase=0,
            status="completed",
            attempt=1,
            output_path=str(output_file)
        )

        sys.exit(0)

    except Exception as e:
        print(f"[PHASE-0][{args.vector_id}][ERROR] {e}")

        # Log to ledger: failed
        ledger.append(
            vector_id=args.vector_id,
            phase=0,
            status="failed",
            attempt=1,
            error=str(e)
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
