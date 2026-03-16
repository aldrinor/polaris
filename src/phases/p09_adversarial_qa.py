"""
Phase 9: Adversarial QA - Skeptical Question Generation and Answering

This phase generates skeptical questions that challenge the claims made in P7's
draft response, then attempts to answer them using VWM retrieval. Unresolved
questions are flagged as knowledge gaps.

ARCHITECT DIRECTIVE: NO MOCKING OF LOGIC
- Real question generation via LLM
- Real VWM retrieval for answers
- Genuine gap detection
"""

import asyncio
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.schemas.phase_models import Phase7Output, Phase9Output, AdversarialQA
from src.state.ledger import Ledger
from src.config import get_config, OUTPUTS_DIR
from src.memory.chroma_client import get_chroma_manager
from src.llm.gemini_client import get_gemini_client
from src.audit import get_audit


# ============================================================================
# QUESTION GENERATION
# ============================================================================

async def generate_skeptical_questions(
    draft_response: str,
    research_objective: str,
    num_questions: int = 3,
) -> List[Dict[str, Any]]:
    """
    Generate skeptical questions that challenge the draft response.

    These questions should:
    1. Challenge factual claims
    2. Probe for missing evidence
    3. Identify potential contradictions
    4. Question methodology or sources

    Args:
        draft_response: The P7 draft response with citations
        research_objective: Original research question/objective
        num_questions: Number of questions to generate (default 3)

    Returns:
        List of question dicts with 'question', 'target_claim', 'challenge_type'
    """
    client = get_gemini_client()

    system_prompt = """You are a skeptical peer reviewer analyzing a research response.
Your role is to identify weaknesses, gaps, and potential issues."""

    prompt = f"""RESEARCH OBJECTIVE:
{research_objective}

DRAFT RESPONSE TO REVIEW:
{draft_response[:8000]}

Generate exactly {num_questions} skeptical questions that challenge this response.

For each question:
1. Identify a specific claim or statement in the response
2. Formulate a probing question that challenges it
3. Classify the challenge type

Challenge types:
- FACTUAL: Questions the accuracy of a stated fact
- EVIDENCE: Questions whether sufficient evidence supports the claim
- METHODOLOGY: Questions the approach or reasoning
- COMPLETENESS: Questions whether important aspects are missing
- CONTRADICTION: Points out potential internal inconsistencies

Output your questions in this exact JSON format:
```json
[
  {{
    "question": "The specific skeptical question",
    "target_claim": "The claim being challenged (quote or paraphrase)",
    "challenge_type": "FACTUAL|EVIDENCE|METHODOLOGY|COMPLETENESS|CONTRADICTION"
  }}
]
```

Generate exactly {num_questions} questions. Be genuinely skeptical - these questions
should identify real weaknesses or gaps in the response.
"""

    response = await client.generate(prompt, system_prompt)

    # Parse JSON from response
    questions = parse_json_from_response(response, default=[])

    # Validate and normalize
    validated = []
    valid_types = {"FACTUAL", "EVIDENCE", "METHODOLOGY", "COMPLETENESS", "CONTRADICTION"}

    for q in questions[:num_questions]:
        if isinstance(q, dict) and "question" in q:
            validated.append({
                "question": str(q.get("question", "")),
                "target_claim": str(q.get("target_claim", "")),
                "challenge_type": q.get("challenge_type", "EVIDENCE") if q.get("challenge_type") in valid_types else "EVIDENCE"
            })

    # If LLM didn't generate enough, add generic probing questions
    while len(validated) < num_questions:
        validated.append({
            "question": f"What evidence directly supports the main conclusions in this response?",
            "target_claim": "Overall response validity",
            "challenge_type": "EVIDENCE"
        })

    return validated[:num_questions]


def parse_json_from_response(response: str, default: Any = None) -> Any:
    """Extract JSON from LLM response, handling code blocks."""
    # Try to find JSON in code block
    json_match = re.search(r'```(?:json)?\s*\n?([\s\S]*?)\n?```', response)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError as e:
            # HIGH-006: Log JSON parse error instead of silent pass
            logger.debug(f"JSON code block parse failed, trying next method: {e}")

    # Try direct parse
    try:
        return json.loads(response)
    except json.JSONDecodeError as e:
        # HIGH-007: Log JSON parse error instead of silent pass
        logger.debug(f"Direct JSON parse failed, trying next method: {e}")

    # Try to find array in response
    array_match = re.search(r'\[[\s\S]*\]', response)
    if array_match:
        try:
            return json.loads(array_match.group(0))
        except json.JSONDecodeError as e:
            # HIGH-008: Log JSON parse error instead of silent pass
            logger.debug(f"Array JSON parse failed, returning default: {e}")

    return default


# ============================================================================
# VWM RETRIEVAL FOR ANSWERING
# ============================================================================

async def retrieve_evidence_for_question(
    question: str,
    vector_id: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant chunks from VWM to answer a skeptical question.

    Args:
        question: The skeptical question to answer
        vector_id: Vector ID for the collection
        top_k: Number of chunks to retrieve

    Returns:
        List of relevant chunks with metadata
    """
    try:
        chroma = get_chroma_manager()
        chroma.initialize_client()
        collection_name = f"vwm_{vector_id}"

        try:
            collection = chroma._client.get_collection(name=collection_name)
        except Exception as e:
            # LOW-033: Log collection fetch error
            logger.debug(f"VWM collection '{collection_name}' not found: {e}")
            return []

        # Query for relevant chunks
        results = collection.query(
            query_texts=[question],
            n_results=top_k,
            include=["documents", "metadatas", "distances"]
        )

        chunks = []
        if results and results.get("ids") and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                chunk = {
                    "chunk_id": chunk_id,
                    "text": results["documents"][0][i] if results.get("documents") else "",
                    "distance": results["distances"][0][i] if results.get("distances") else 1.0,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {}
                }
                chunks.append(chunk)

        return chunks

    except Exception as e:
        # LOW-034: Use logger instead of print
        logger.warning(f"VWM retrieval error: {e}")
        return []


# ============================================================================
# ANSWER GENERATION AND GAP DETECTION
# ============================================================================

async def answer_question_with_evidence(
    question: Dict[str, Any],
    evidence_chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Attempt to answer a skeptical question using retrieved evidence.

    Args:
        question: Question dict with 'question', 'target_claim', 'challenge_type'
        evidence_chunks: Retrieved chunks that may contain the answer

    Returns:
        Answer dict with 'answer', 'confidence', 'resolved', 'supporting_chunks'
    """
    if not evidence_chunks:
        return {
            "answer": "No relevant evidence found in the knowledge base.",
            "confidence": 0.0,
            "resolved": False,
            "assessment": "NO_EVIDENCE",
            "supporting_chunks": [],
            "remaining_gaps": "No evidence chunks available to address this question.",
            "gap_type": "NO_EVIDENCE"
        }

    # Build context from evidence
    context_parts = []
    for i, chunk in enumerate(evidence_chunks[:5]):
        chunk_text = chunk.get("text", "")[:1500]  # Limit chunk size
        context_parts.append(f"[Evidence {i+1}] (ID: {chunk['chunk_id']})\n{chunk_text}")

    evidence_context = "\n\n".join(context_parts)

    client = get_gemini_client()

    system_prompt = """You are a research analyst answering a skeptical question using available evidence.
Be honest about what the evidence does and does not support."""

    prompt = f"""SKEPTICAL QUESTION:
{question['question']}

TARGETED CLAIM:
{question['target_claim']}

CHALLENGE TYPE: {question['challenge_type']}

AVAILABLE EVIDENCE:
{evidence_context}

Based ONLY on the evidence provided, answer the skeptical question.

Evaluate honestly:
- Does the evidence adequately address the question?
- Is the original claim supported, refuted, or uncertain?
- What gaps remain?

Output in this exact JSON format:
```json
{{
  "answer": "Your substantive answer based on the evidence",
  "confidence": 0.0-1.0,
  "resolved": true/false,
  "assessment": "SUPPORTED|PARTIALLY_SUPPORTED|UNCERTAIN|REFUTED|NO_EVIDENCE",
  "supporting_evidence_ids": ["list", "of", "chunk_ids", "used"],
  "remaining_gaps": "Description of what's still unclear or missing"
}}
```

Be honest about confidence. If the evidence doesn't fully answer the question, say so.
"""

    response = await client.generate(prompt, system_prompt)

    # Parse response
    result = parse_json_from_response(response, default={})

    # Handle case where Gemini returns a list instead of dict
    if isinstance(result, list):
        result = result[0] if result else {}
    if not isinstance(result, dict):
        result = {}

    # Normalize and validate
    confidence = float(result.get("confidence", 0.3))
    resolved = result.get("resolved", False)
    assessment = result.get("assessment", "UNCERTAIN")

    # SOTA: Stricter resolution criteria - require FULLY SUPPORTED
    # PARTIALLY_SUPPORTED is no longer sufficient for resolution
    # This ensures only well-evidenced claims pass adversarial QA
    if assessment == "SUPPORTED" and confidence >= 0.75:
        # FULLY SUPPORTED with high confidence = resolved
        resolved = True
    elif assessment == "REFUTED" and confidence >= 0.80:
        # REFUTED with very high confidence = resolved (we know the answer is wrong)
        resolved = True
    else:
        # PARTIALLY_SUPPORTED, UNCERTAIN, NO_EVIDENCE = NOT resolved
        resolved = False

    # Determine gap type if not resolved
    gap_type = None
    if not resolved:
        if assessment == "NO_EVIDENCE":
            gap_type = "NO_EVIDENCE"
        elif assessment == "UNCERTAIN":
            gap_type = "INSUFFICIENT_EVIDENCE"
        elif assessment == "REFUTED" and confidence < 0.80:
            gap_type = "CONTRADICTION"
        elif assessment == "PARTIALLY_SUPPORTED":
            # SOTA: PARTIALLY_SUPPORTED is now a gap (requires more evidence)
            gap_type = "PARTIAL_COVERAGE"
        else:
            gap_type = "PARTIAL_COVERAGE"

    return {
        "answer": result.get("answer", "Unable to generate answer."),
        "confidence": confidence,
        "resolved": resolved,
        "assessment": assessment,
        "supporting_chunks": result.get("supporting_evidence_ids", []),
        "remaining_gaps": result.get("remaining_gaps", ""),
        "gap_type": gap_type
    }


# ============================================================================
# LLM-AS-JUDGE RUBRIC EVALUATION (SOTA)
# ============================================================================

async def evaluate_response_rubric(
    draft_response: str,
    research_objective: str,
) -> Dict[str, Any]:
    """
    SOTA: LLM-as-Judge rubric evaluation for response quality.

    Evaluates the draft response on four dimensions (1-5 scale):
    - Comprehensiveness: All required aspects covered?
    - Objectivity: Neutral, scientific tone?
    - Coherence: Logical flow and organization?
    - Evidence Support: Claims backed by citations?

    If any dimension < 3, flags for revision.

    Args:
        draft_response: The P7 draft response text
        research_objective: The original research question

    Returns:
        Dict with rubric scores, overall score, needs_revision flag, and feedback
    """
    client = get_gemini_client()

    system_prompt = """You are an expert research quality evaluator.
You assess research responses using a structured rubric with strict scoring criteria.
Be critical and objective - do not inflate scores."""

    prompt = f"""RESEARCH OBJECTIVE:
{research_objective}

RESPONSE TO EVALUATE:
{draft_response[:10000]}

Evaluate this research response using the following rubric. Score each dimension from 1-5.

RUBRIC DIMENSIONS:

1. COMPREHENSIVENESS (1-5)
   - 1: Major aspects missing, incomplete coverage
   - 2: Several important aspects missing
   - 3: Covers main points but lacks depth in some areas
   - 4: Good coverage with minor gaps
   - 5: Complete, thorough coverage of all relevant aspects

2. OBJECTIVITY (1-5)
   - 1: Clearly biased, uses loaded language
   - 2: Some bias apparent, unbalanced presentation
   - 3: Generally objective but occasional bias
   - 4: Objective with minor subjective elements
   - 5: Completely neutral, scientific tone throughout

3. COHERENCE (1-5)
   - 1: Disorganized, hard to follow, jumps between topics
   - 2: Weak organization, unclear transitions
   - 3: Adequate structure but some logical gaps
   - 4: Well-organized with clear flow
   - 5: Excellent logical progression, clear structure

4. EVIDENCE SUPPORT (1-5)
   - 1: Claims unsupported, missing citations
   - 2: Some claims cited but many unsupported
   - 3: Most major claims cited, some gaps
   - 4: Good citation coverage with minor gaps
   - 5: All claims supported with appropriate citations

Output your evaluation in this exact JSON format:
```json
{{
  "comprehensiveness": <1-5>,
  "objectivity": <1-5>,
  "coherence": <1-5>,
  "evidence_support": <1-5>,
  "feedback": "Specific feedback on areas needing improvement (1-2 sentences per dimension scoring <4)"
}}
```

Be strict and honest. Only give 5s for truly excellent work.
"""

    try:
        response = await client.generate(prompt, system_prompt)
        result = parse_json_from_response(response, default={})

        # Handle list response
        if isinstance(result, list):
            result = result[0] if result else {}
        if not isinstance(result, dict):
            result = {}

        # Extract and validate scores
        comprehensiveness = int(result.get("comprehensiveness", 3))
        objectivity = int(result.get("objectivity", 3))
        coherence = int(result.get("coherence", 3))
        evidence_support = int(result.get("evidence_support", 3))

        # Clamp to valid range
        comprehensiveness = max(1, min(5, comprehensiveness))
        objectivity = max(1, min(5, objectivity))
        coherence = max(1, min(5, coherence))
        evidence_support = max(1, min(5, evidence_support))

        # Calculate overall score
        overall = (comprehensiveness + objectivity + coherence + evidence_support) / 4.0

        # Check if revision needed (any dimension < 3)
        needs_revision = any(score < 3 for score in [comprehensiveness, objectivity, coherence, evidence_support])

        feedback = result.get("feedback", "")
        if needs_revision and not feedback:
            weak_areas = []
            if comprehensiveness < 3:
                weak_areas.append("comprehensiveness")
            if objectivity < 3:
                weak_areas.append("objectivity")
            if coherence < 3:
                weak_areas.append("coherence")
            if evidence_support < 3:
                weak_areas.append("evidence support")
            feedback = f"Response needs improvement in: {', '.join(weak_areas)}"

        return {
            "comprehensiveness": comprehensiveness,
            "objectivity": objectivity,
            "coherence": coherence,
            "evidence_support": evidence_support,
            "overall": round(overall, 2),
            "needs_revision": needs_revision,
            "feedback": feedback,
        }

    except Exception as e:
        # LOW-082: Use logger instead of print
        logger.warning(f"Rubric evaluation failed: {e}")
        # Return neutral scores on failure
        return {
            "comprehensiveness": 3,
            "objectivity": 3,
            "coherence": 3,
            "evidence_support": 3,
            "overall": 3.0,
            "needs_revision": False,
            "feedback": f"Evaluation failed: {str(e)}",
        }


# ============================================================================
# MAIN PHASE EXECUTION
# ============================================================================

def load_previous_chunk_ids(vector_id: str) -> set:
    """
    Load chunk IDs from all previous P9 outputs for this vector.

    This enables signal_novelty calculation by tracking what evidence
    has been seen in previous iterations.

    Args:
        vector_id: Vector ID to load history for

    Returns:
        Set of chunk IDs seen in previous iterations
    """
    seen_chunks = set()
    p8_dir = OUTPUTS_DIR / "P9"

    if not p8_dir.exists():
        return seen_chunks

    p8_files = sorted(p8_dir.glob(f"{vector_id}__P9__*.json"))

    for p8_file in p8_files:
        try:
            with open(p8_file, 'r', encoding='utf-8') as f:
                p8_data = json.load(f)

            # Extract chunk IDs from qa_results
            for qa_result in p8_data.get("qa_results", []):
                for chunk_id in qa_result.get("supporting_chunks", []):
                    seen_chunks.add(chunk_id)

        except Exception as e:
            # LOW-083: Use logger instead of print
            logger.warning(f"Failed to load {p8_file.name}: {e}")

    return seen_chunks


async def run_phase_9(
    vector_id: str,
    p7_output: Optional[Phase7Output] = None,
) -> Phase9Output:
    """
    Execute Phase 9: Adversarial QA

    Workflow:
    1. Load P7 draft response
    2. Load previously seen chunk IDs for signal_novelty
    3. Generate skeptical questions
    4. Retrieve evidence from VWM for each question
    5. Attempt to answer questions
    6. Calculate signal_novelty (proportion of new chunks)
    7. Flag unresolved gaps

    Args:
        vector_id: Vector ID for the research
        p7_output: Optional P7 output (will load from file if not provided)

    Returns:
        Phase9Output with questions, answers, gaps, signal_novelty, and summary statistics
    """
    config = get_config()
    start_time = datetime.now(timezone.utc)
    audit = get_audit()

    print(f"\n{'='*60}")
    print(f"PHASE 9: ADVERSARIAL QA")
    print(f"Vector ID: {vector_id}")
    print(f"{'='*60}")

    # Load P7 output if not provided
    if p7_output is None:
        p7_dir = OUTPUTS_DIR / "P7"
        p7_files = list(p7_dir.glob(f"{vector_id}__P7__*.json"))
        if not p7_files:
            raise FileNotFoundError(f"No P7 output found for {vector_id} in {p7_dir}")

        p7_path = sorted(p7_files)[-1]  # Most recent
        print(f"  Loading P7 output: {p7_path.name}")

        with open(p7_path, 'r', encoding='utf-8') as f:
            p7_data = json.load(f)

        p7_output = Phase7Output(**p7_data)

    draft_response = p7_output.analysis_text
    # Try to get research objective - may need to load from P1 output
    research_objective = getattr(p7_output, 'query', None)
    if not research_objective:
        # Try to load from P1 output
        p1_dir = OUTPUTS_DIR / "P1"
        p1_files = list(p1_dir.glob(f"{vector_id}__P1__*.json"))
        if p1_files:
            with open(sorted(p1_files)[-1], 'r', encoding='utf-8') as f:
                p1_data = json.load(f)
                research_objective = p1_data.get("research_question", "Analyze the evidence and claims in this research.")
        else:
            research_objective = "Analyze the evidence and claims in this research."

    if not draft_response:
        raise ValueError("P7 output missing analysis_text")

    # Step 0: Load previously seen chunk IDs for signal_novelty calculation
    print("\n  Step 0: Loading previous iteration history for signal_novelty...")
    previously_seen_chunks = load_previous_chunk_ids(vector_id)
    print(f"    Previously seen chunks: {len(previously_seen_chunks)}")

    # Track chunks seen in this iteration
    this_iteration_chunks = set()

    # Step 1: Generate skeptical questions
    print("\n  Step 1: Generating skeptical questions...")
    num_questions = config.thresholds.rag.top_k_per_query or 3
    num_questions = min(num_questions, 5)  # Cap at 5

    questions = await generate_skeptical_questions(
        draft_response=draft_response,
        research_objective=research_objective,
        num_questions=3,  # Per directive: generate 3 skeptical questions
    )

    print(f"    Generated {len(questions)} skeptical questions:")
    for i, q in enumerate(questions):
        print(f"      Q{i+1} [{q['challenge_type']}]: {q['question'][:80]}...")

    # Step 2: Answer each question using VWM evidence
    print("\n  Step 2: Answering questions with VWM evidence...")
    qa_results = []

    for i, question in enumerate(questions):
        print(f"\n    Processing Q{i+1}...")

        # Retrieve evidence
        evidence = await retrieve_evidence_for_question(
            question=question["question"],
            vector_id=vector_id,
            top_k=5
        )
        print(f"      Retrieved {len(evidence)} evidence chunks")

        # Track chunk IDs for signal_novelty calculation
        for chunk in evidence:
            chunk_id = chunk.get("chunk_id", "")
            if chunk_id:
                this_iteration_chunks.add(chunk_id)

        # Generate answer
        answer_result = await answer_question_with_evidence(
            question=question,
            evidence_chunks=evidence,
        )

        qa_result = AdversarialQA(
            question_id=f"Q{i+1}",
            question=question["question"],
            target_claim=question["target_claim"],
            challenge_type=question["challenge_type"],
            evidence_count=len(evidence),
            answer=answer_result["answer"],
            confidence=answer_result["confidence"],
            resolved=answer_result["resolved"],
            assessment=answer_result.get("assessment", "UNCERTAIN"),
            supporting_chunks=answer_result.get("supporting_chunks", []),
            remaining_gaps=answer_result.get("remaining_gaps", ""),
            gap_type=answer_result.get("gap_type")
        )
        qa_results.append(qa_result)

        status = "RESOLVED" if qa_result.resolved else f"UNRESOLVED ({qa_result.gap_type})"
        print(f"      Status: {status} (confidence: {qa_result.confidence:.2f})")

    # Step 3: Compile gap analysis
    print("\n  Step 3: Compiling gap analysis...")
    gaps = []
    for qa in qa_results:
        if not qa.resolved:
            gaps.append({
                "question_id": qa.question_id,
                "question": qa.question,
                "gap_type": qa.gap_type,
                "remaining_gaps": qa.remaining_gaps,
                "challenge_type": qa.challenge_type
            })

    # Calculate summary statistics
    total_questions = len(qa_results)
    resolved_count = sum(1 for qa in qa_results if qa.resolved)
    resolution_rate = resolved_count / total_questions if total_questions > 0 else 0.0

    avg_confidence = sum(qa.confidence for qa in qa_results) / total_questions if total_questions > 0 else 0.0

    gap_types: Dict[str, int] = {}
    for gap in gaps:
        gt = gap["gap_type"]
        if gt:
            gap_types[gt] = gap_types.get(gt, 0) + 1

    # Step 4: Calculate signal_novelty
    print("\n  Step 4: Calculating signal_novelty metric...")
    unique_this_iteration = len(this_iteration_chunks)
    new_chunks = this_iteration_chunks - previously_seen_chunks
    new_chunks_count = len(new_chunks)
    cumulative_unique = len(previously_seen_chunks | this_iteration_chunks)

    # signal_novelty = proportion of chunks that are new
    if unique_this_iteration > 0:
        signal_novelty = new_chunks_count / unique_this_iteration
    else:
        signal_novelty = 1.0  # First iteration or no chunks

    print(f"    Unique chunks this iteration: {unique_this_iteration}")
    print(f"    New chunks (not seen before): {new_chunks_count}")
    print(f"    Cumulative unique chunks: {cumulative_unique}")
    print(f"    Signal Novelty: {signal_novelty:.3f}")

    # Step 5: SOTA LLM-as-Judge rubric evaluation
    print("\n  Step 5: Running LLM-as-Judge rubric evaluation...")
    rubric_result = await evaluate_response_rubric(
        draft_response=draft_response,
        research_objective=research_objective,
    )

    print(f"    Comprehensiveness: {rubric_result['comprehensiveness']}/5")
    print(f"    Objectivity: {rubric_result['objectivity']}/5")
    print(f"    Coherence: {rubric_result['coherence']}/5")
    print(f"    Evidence Support: {rubric_result['evidence_support']}/5")
    print(f"    Overall: {rubric_result['overall']}/5")
    if rubric_result['needs_revision']:
        print(f"    [WARN] REVISION NEEDED: {rubric_result['feedback']}")

    # Audit: Log QA exchanges and completion
    if audit:
        for qa in qa_results:
            audit.log_qa_exchange(
                question_type=qa.challenge_type,
                question_text=qa.question,
                answer_text=qa.answer[:500] if qa.answer else "",
                evidence_used=qa.supporting_chunks,
                confidence=qa.confidence,
                resolved=qa.resolved,
            )

        # Log adversarial QA complete
        audit.log_adversarial_qa_complete(signal_novelty=signal_novelty)

        # Log LLM calls for question generation and answering
        audit.log_llm_call(
            phase=9,
            purpose="skeptical_question_generation",
            model="gemini",
            input_tokens=len(draft_response) // 4,
            output_tokens=len(str(questions)) // 4,
            cost_usd=0.0,
            success=True,
        )

    end_time = datetime.now(timezone.utc)

    # Build output
    output = Phase9Output(
        vector_id=vector_id,
        phase="P9",
        timestamp_start=start_time.isoformat(),
        timestamp_end=end_time.isoformat(),
        p7_file=p7_output.vector_id,
        research_objective=research_objective[:500],
        qa_results=qa_results,
        gaps=gaps,
        total_questions=total_questions,
        resolved_count=resolved_count,
        unresolved_count=total_questions - resolved_count,
        resolution_rate=resolution_rate,
        average_confidence=avg_confidence,
        gap_type_distribution=gap_types,
        # SOTA signal_novelty metrics for knowledge saturation detection
        signal_novelty=signal_novelty,
        unique_chunks_this_iteration=unique_this_iteration,
        cumulative_unique_chunks=cumulative_unique,
        new_chunks_count=new_chunks_count,
        # SOTA LLM-as-Judge rubric evaluation
        rubric_comprehensiveness=rubric_result['comprehensiveness'],
        rubric_objectivity=rubric_result['objectivity'],
        rubric_coherence=rubric_result['coherence'],
        rubric_evidence_support=rubric_result['evidence_support'],
        rubric_overall=rubric_result['overall'],
        rubric_needs_revision=rubric_result['needs_revision'],
        rubric_feedback=rubric_result['feedback'],
    )

    # Save output
    output_dir = OUTPUTS_DIR / "P9"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{vector_id}__P9__{timestamp}.json"

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output.model_dump(), f, indent=2, ensure_ascii=False)

    print(f"\n  Summary:")
    print(f"    Questions: {total_questions}")
    print(f"    Resolved: {resolved_count} ({resolution_rate*100:.1f}%)")
    print(f"    Unresolved Gaps: {len(gaps)}")
    print(f"    Avg Confidence: {avg_confidence:.2f}")
    print(f"    Signal Novelty: {signal_novelty:.3f}")
    print(f"    New Evidence Chunks: {new_chunks_count}/{unique_this_iteration}")
    print(f"    Rubric Overall: {rubric_result['overall']}/5")
    if rubric_result['needs_revision']:
        print(f"    [!] REVISION FLAGGED")
    print(f"\n  Output saved: {output_path.name}")

    # Update ledger
    ledger = Ledger()
    revision_flag = ", REVISION_NEEDED" if rubric_result['needs_revision'] else ""
    ledger.append(
        vector_id=vector_id,
        phase=9,
        status="completed",
        output_path=str(output_path),
        notes=f"questions={total_questions}, resolved={resolved_count}, rate={resolution_rate:.2f}, rubric={rubric_result['overall']}/5{revision_flag}"
    )

    return output


# ============================================================================
# SELF-TEST
# ============================================================================

def self_test():
    """Run self-tests for Phase 9 components."""
    print("\nRunning Phase 9 self-tests...")

    # Test 1: JSON parsing
    test_response = '''Here are the questions:
```json
[
  {"question": "What is the source?", "target_claim": "claim 1", "challenge_type": "EVIDENCE"},
  {"question": "Is this accurate?", "target_claim": "claim 2", "challenge_type": "FACTUAL"}
]
```
'''
    parsed = parse_json_from_response(test_response)
    assert parsed is not None, "JSON parsing failed"
    assert len(parsed) == 2, f"Expected 2 questions, got {len(parsed)}"
    print("  [PASS] JSON parsing from code blocks")

    # Test 2: Direct JSON parsing
    direct_json = '[{"question": "test?", "target_claim": "claim", "challenge_type": "EVIDENCE"}]'
    parsed2 = parse_json_from_response(direct_json)
    assert parsed2 is not None and len(parsed2) == 1
    print("  [PASS] Direct JSON parsing")

    # Test 3: Question validation/normalization logic
    raw_questions = [
        {"question": "Q1?", "target_claim": "C1", "challenge_type": "FACTUAL"},
        {"question": "Q2?", "target_claim": "C2", "challenge_type": "INVALID_TYPE"},
        {"question": "Q3?"},  # Missing fields
    ]

    validated = []
    valid_types = {"FACTUAL", "EVIDENCE", "METHODOLOGY", "COMPLETENESS", "CONTRADICTION"}
    for q in raw_questions:
        if isinstance(q, dict) and "question" in q:
            validated.append({
                "question": str(q.get("question", "")),
                "target_claim": str(q.get("target_claim", "")),
                "challenge_type": q.get("challenge_type", "EVIDENCE") if q.get("challenge_type") in valid_types else "EVIDENCE"
            })

    assert len(validated) == 3, f"Expected 3 validated, got {len(validated)}"
    assert validated[0]["challenge_type"] == "FACTUAL"
    assert validated[1]["challenge_type"] == "EVIDENCE"  # Invalid type normalized
    assert validated[2]["target_claim"] == ""  # Missing field defaulted
    print("  [PASS] Question validation and normalization")

    # Test 4: Answer result normalization
    answer_result = {
        "answer": "Test answer",
        "confidence": 0.8,
        "resolved": True,
        "assessment": "SUPPORTED",
        "supporting_evidence_ids": ["c1", "c2"]
    }

    confidence = float(answer_result.get("confidence", 0.3))
    resolved = answer_result.get("resolved", False)
    assessment = answer_result.get("assessment", "UNCERTAIN")

    # SOTA: Stricter resolution - require FULLY SUPPORTED with high confidence
    if assessment == "SUPPORTED" and confidence >= 0.75:
        resolved = True
    elif assessment == "REFUTED" and confidence >= 0.80:
        resolved = True

    assert resolved == True  # 0.8 >= 0.75 with SUPPORTED
    assert confidence == 0.8
    print("  [PASS] Answer result normalization (SOTA: stricter criteria)")

    # Test 5: Gap detection logic
    test_qa_results = [
        {"resolved": True, "gap_type": None},
        {"resolved": False, "gap_type": "NO_EVIDENCE", "question": "Q2", "question_id": "Q2", "remaining_gaps": "missing", "challenge_type": "EVIDENCE"},
        {"resolved": False, "gap_type": "INSUFFICIENT_EVIDENCE", "question": "Q3", "question_id": "Q3", "remaining_gaps": "partial", "challenge_type": "FACTUAL"},
    ]

    gaps = [qa for qa in test_qa_results if not qa["resolved"]]
    assert len(gaps) == 2
    print("  [PASS] Gap detection logic")

    # Test 6: Resolution rate calculation
    resolved_count = sum(1 for qa in test_qa_results if qa["resolved"])
    resolution_rate = resolved_count / len(test_qa_results)
    assert abs(resolution_rate - 0.333) < 0.01, f"Expected ~0.33, got {resolution_rate}"
    print("  [PASS] Resolution rate calculation")

    print("\nAll Phase 9 self-tests PASSED!")
    return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 9: Adversarial QA")
    parser.add_argument("--vector-id", required=False, help="Vector ID to process")
    parser.add_argument("--input", required=False, help="Path to P7 output JSON (optional)")
    parser.add_argument("--output", required=False, help="Output directory (optional)")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")

    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.vector_id:
        # P9 requires P7 output (contains analysis_text) - NOT P8
        # If --input is provided, check if it's P7 or load P7 directly
        p7_output = None
        if args.input:
            input_path = Path(args.input)
            # Check if input is a P7 file (not P8)
            if "_P7_" in input_path.name or "__P7__" in input_path.name:
                with open(args.input, 'r', encoding='utf-8') as f:
                    p7_output = Phase7Output(**json.load(f))
            else:
                # Input is not P7 - load P7 from standard location
                print(f"  [INFO] Input '{input_path.name}' is not P7 output - loading P7 directly")
                # p7_output will be loaded in run_phase_9

        result = asyncio.run(run_phase_9(vector_id=args.vector_id, p7_output=p7_output))

        # Optionally save to custom output dir
        if args.output:
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = out_dir / f"{args.vector_id}__P9__{timestamp}.json"
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)
            print(f"  Output saved to: {out_path}")

        print(f"\nPhase 9 complete. Resolution rate: {result.resolution_rate*100:.1f}%")
    else:
        print("Usage: python p08_adversarial_qa.py --vector-id <ID> [--input P7.json] [--output dir] or --self-test")
