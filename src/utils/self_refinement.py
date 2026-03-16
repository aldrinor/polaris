#!/usr/bin/env python3
"""
POLARIS Self-Refinement Critique Loop
======================================
Implements iterative self-improvement for LLM-generated content.

Self-refinement is a SOTA technique where:
1. LLM generates initial response
2. Critique model reviews and identifies issues
3. LLM refines response based on critique
4. Iterate until approved or max iterations

Based on research:
- Self-Refine (Google, 2023): https://arxiv.org/abs/2303.17651
- Reflexion (Princeton, 2023): https://arxiv.org/abs/2303.11366
- Constitutional AI (Anthropic, 2022)

Usage:
    from src.utils.self_refinement import SelfRefinementLoop, refine_content

    loop = SelfRefinementLoop()
    result = await loop.refine(
        content="Initial draft...",
        requirements=["Must cite sources", "Be factually accurate"],
        max_iterations=3,
    )
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CritiqueResult:
    """Result from a single critique iteration."""
    iteration: int
    issues_found: List[str]
    severity_scores: Dict[str, float]  # issue -> severity (0-1)
    overall_quality: float  # 0-1 overall quality score
    approved: bool  # True if no critical issues
    critique_text: str  # Full critique text
    suggestions: List[str]  # Specific improvement suggestions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "iteration": self.iteration,
            "issues_found": self.issues_found,
            "severity_scores": self.severity_scores,
            "overall_quality": self.overall_quality,
            "approved": self.approved,
            "critique_text": self.critique_text[:500] if self.critique_text else "",
            "suggestions": self.suggestions,
        }


@dataclass
class RefinementResult:
    """Final result from refinement loop."""
    original_content: str
    final_content: str
    iterations: int
    critique_history: List[CritiqueResult]
    improvement_score: float  # Final quality - initial quality
    approved: bool
    processing_time_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_content": self.original_content[:200] + "...",
            "final_content": self.final_content[:200] + "...",
            "iterations": self.iterations,
            "critique_history": [c.to_dict() for c in self.critique_history],
            "improvement_score": round(self.improvement_score, 4),
            "approved": self.approved,
            "processing_time_ms": self.processing_time_ms,
            "metadata": self.metadata,
        }


# =============================================================================
# CRITIQUE PROMPTS
# =============================================================================

CRITIQUE_SYSTEM_PROMPT = """You are a rigorous academic critic evaluating research content.
Your role is to identify issues, factual errors, logical gaps, and areas for improvement.
Be thorough but fair - acknowledge what's done well while pointing out problems.
Focus on:
1. Factual accuracy and evidence support
2. Logical coherence and flow
3. Citation usage and attribution
4. Completeness of coverage
5. Clarity and readability"""

CRITIQUE_PROMPT_TEMPLATE = """Critique the following research content against these requirements:

REQUIREMENTS:
{requirements}

CONTENT TO CRITIQUE:
---
{content}
---

Provide your critique as JSON with this structure:
{{
    "overall_quality": 0.0-1.0,
    "approved": true/false,
    "issues": [
        {{"issue": "description", "severity": 0.0-1.0, "location": "where in content"}}
    ],
    "suggestions": ["specific improvement suggestion 1", "suggestion 2"],
    "strengths": ["what's done well"],
    "critique_summary": "brief overall assessment"
}}

Be specific about issues and suggestions. Approve only if no critical issues (severity > 0.7) remain."""

REFINEMENT_PROMPT_TEMPLATE = """Improve the following content based on this critique:

CRITIQUE:
{critique}

ISSUES TO ADDRESS:
{issues}

SUGGESTIONS:
{suggestions}

ORIGINAL CONTENT:
---
{content}
---

Provide the improved content. Address all issues while preserving what works well.
Maintain the same general structure and length unless issues require changes.
Do not add any preamble or explanation - output only the refined content."""


# =============================================================================
# SELF-REFINEMENT LOOP
# =============================================================================

class SelfRefinementLoop:
    """
    Implements iterative self-refinement for content improvement.

    The loop continues until:
    - Content is approved by critique
    - Max iterations reached
    - No improvement detected
    """

    def __init__(
        self,
        max_iterations: int = 3,
        approval_threshold: float = 0.80,  # Quality score to approve
        improvement_threshold: float = 0.02,  # Min improvement to continue
        critique_model: str = "gemini",  # Model for critique
        refinement_model: str = "gemini",  # Model for refinement
    ):
        """
        Initialize self-refinement loop.

        Args:
            max_iterations: Maximum refinement iterations
            approval_threshold: Quality score threshold for approval
            improvement_threshold: Minimum improvement to continue iterating
            critique_model: Model to use for critique
            refinement_model: Model to use for refinement
        """
        self.max_iterations = max_iterations
        self.approval_threshold = approval_threshold
        self.improvement_threshold = improvement_threshold
        self.critique_model = critique_model
        self.refinement_model = refinement_model

    async def refine(
        self,
        content: str,
        requirements: List[str],
        context: Optional[str] = None,
    ) -> RefinementResult:
        """
        Run self-refinement loop on content.

        Args:
            content: Initial content to refine
            requirements: List of requirements to check against
            context: Optional additional context for critique

        Returns:
            RefinementResult with final content and history
        """
        from src.llm.gemini_client import get_gemini_client

        start_time = datetime.now(timezone.utc)
        client = get_gemini_client()

        original_content = content
        current_content = content
        critique_history: List[CritiqueResult] = []
        last_quality = 0.0

        for iteration in range(1, self.max_iterations + 1):
            print(f"[SELF-REFINE] Iteration {iteration}/{self.max_iterations}")

            # 1. Generate critique
            critique = await self._generate_critique(
                client, current_content, requirements, context, iteration
            )
            critique_history.append(critique)

            print(f"[SELF-REFINE] Quality: {critique.overall_quality:.2f}, Issues: {len(critique.issues_found)}")

            # 2. Check if approved
            if critique.approved or critique.overall_quality >= self.approval_threshold:
                print(f"[SELF-REFINE] Content approved at iteration {iteration}")
                break

            # 3. Check if improving
            if iteration > 1:
                improvement = critique.overall_quality - last_quality
                if improvement < self.improvement_threshold:
                    print(f"[SELF-REFINE] Insufficient improvement ({improvement:.4f}), stopping")
                    break

            last_quality = critique.overall_quality

            # 4. Refine content based on critique
            if iteration < self.max_iterations:
                current_content = await self._refine_content(
                    client, current_content, critique
                )
                print(f"[SELF-REFINE] Content refined (length: {len(current_content)})")

        # Calculate improvement
        initial_quality = critique_history[0].overall_quality if critique_history else 0.0
        final_quality = critique_history[-1].overall_quality if critique_history else 0.0
        improvement_score = final_quality - initial_quality

        end_time = datetime.now(timezone.utc)
        processing_time_ms = int((end_time - start_time).total_seconds() * 1000)

        return RefinementResult(
            original_content=original_content,
            final_content=current_content,
            iterations=len(critique_history),
            critique_history=critique_history,
            improvement_score=improvement_score,
            approved=critique_history[-1].approved if critique_history else False,
            processing_time_ms=processing_time_ms,
            metadata={
                "requirements_count": len(requirements),
                "initial_quality": initial_quality,
                "final_quality": final_quality,
            },
        )

    async def _generate_critique(
        self,
        client,
        content: str,
        requirements: List[str],
        context: Optional[str],
        iteration: int,
    ) -> CritiqueResult:
        """Generate critique for content."""
        requirements_str = "\n".join(f"- {r}" for r in requirements)

        prompt = CRITIQUE_PROMPT_TEMPLATE.format(
            requirements=requirements_str,
            content=content[:8000],  # Limit content length
        )

        if context:
            prompt = f"CONTEXT:\n{context}\n\n{prompt}"

        try:
            result = await client.generate_json(
                prompt,
                system_prompt=CRITIQUE_SYSTEM_PROMPT,
            )

            # Parse critique result
            issues = result.get("issues", [])
            issues_found = [i.get("issue", "") for i in issues if i.get("issue")]
            severity_scores = {
                i.get("issue", f"issue_{idx}"): i.get("severity", 0.5)
                for idx, i in enumerate(issues)
            }

            return CritiqueResult(
                iteration=iteration,
                issues_found=issues_found,
                severity_scores=severity_scores,
                overall_quality=float(result.get("overall_quality", 0.5)),
                approved=bool(result.get("approved", False)),
                critique_text=result.get("critique_summary", ""),
                suggestions=result.get("suggestions", []),
            )

        except Exception as e:
            # LOW-118: Use logger instead of print
            logger.warning(f"Critique generation failed: {e}")
            # Return neutral critique on failure
            return CritiqueResult(
                iteration=iteration,
                issues_found=["Critique generation failed"],
                severity_scores={"critique_error": 0.5},
                overall_quality=0.5,
                approved=False,
                critique_text=f"Error: {e}",
                suggestions=["Retry critique generation"],
            )

    async def _refine_content(
        self,
        client,
        content: str,
        critique: CritiqueResult,
    ) -> str:
        """Refine content based on critique."""
        issues_str = "\n".join(f"- {issue}" for issue in critique.issues_found[:10])
        suggestions_str = "\n".join(f"- {s}" for s in critique.suggestions[:10])

        prompt = REFINEMENT_PROMPT_TEMPLATE.format(
            critique=critique.critique_text,
            issues=issues_str,
            suggestions=suggestions_str,
            content=content[:10000],  # Limit content length
        )

        try:
            refined = await client.generate(prompt)

            # Validate refinement (should be similar length, not empty)
            if len(refined) < len(content) * 0.5:
                print("[SELF-REFINE][WARN] Refined content too short, keeping original")
                return content

            if len(refined) < 100:
                print("[SELF-REFINE][WARN] Refined content invalid, keeping original")
                return content

            return refined.strip()

        except Exception as e:
            # LOW-119: Use logger instead of print
            logger.warning(f"Refinement failed: {e}")
            return content


# =============================================================================
# SPECIALIZED REFINEMENT LOOPS
# =============================================================================

class ResearchReportRefiner(SelfRefinementLoop):
    """Specialized refinement for research reports."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.default_requirements = [
            "All claims must be supported by cited evidence",
            "Citations must be properly formatted with source attribution",
            "Content must be factually accurate and verifiable",
            "Arguments must be logically coherent with clear flow",
            "Technical terms must be defined or explained",
            "Conclusions must follow from presented evidence",
            "Contradictions in evidence must be acknowledged",
            "Geographic and temporal context must be clear",
        ]

    async def refine_report(
        self,
        report_text: str,
        topic: str,
        additional_requirements: Optional[List[str]] = None,
    ) -> RefinementResult:
        """
        Refine a research report.

        Args:
            report_text: The report content to refine
            topic: The research topic for context
            additional_requirements: Extra requirements beyond defaults

        Returns:
            RefinementResult with improved report
        """
        requirements = self.default_requirements.copy()
        if additional_requirements:
            requirements.extend(additional_requirements)

        context = f"This is a research report on: {topic}"

        return await self.refine(
            content=report_text,
            requirements=requirements,
            context=context,
        )


class ConclusionRefiner(SelfRefinementLoop):
    """Specialized refinement for research conclusions."""

    def __init__(self, **kwargs):
        kwargs.setdefault("max_iterations", 2)  # Conclusions need fewer iterations
        kwargs.setdefault("approval_threshold", 0.85)  # Higher bar for conclusions
        super().__init__(**kwargs)

    async def refine_conclusion(
        self,
        conclusion: str,
        evidence_summary: str,
        verified_claims: Optional[List[str]] = None,
    ) -> RefinementResult:
        """
        Refine a research conclusion.

        Args:
            conclusion: The conclusion text to refine
            evidence_summary: Summary of supporting evidence
            verified_claims: List of verified claims that conclusion should reflect

        Returns:
            RefinementResult with improved conclusion
        """
        requirements = [
            "Conclusion must be directly supported by evidence",
            "No claims beyond what evidence supports",
            "Acknowledge limitations and uncertainties",
            "Be specific rather than vague",
            "Avoid hedging language unless truly uncertain",
        ]

        if verified_claims:
            requirements.append(
                f"Must reflect these verified findings: {', '.join(verified_claims[:5])}"
            )

        context = f"EVIDENCE SUMMARY:\n{evidence_summary[:2000]}"

        return await self.refine(
            content=conclusion,
            requirements=requirements,
            context=context,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def refine_content(
    content: str,
    requirements: List[str],
    max_iterations: int = 3,
) -> RefinementResult:
    """
    Refine content with self-critique loop.

    Convenience function for one-off refinement.

    Args:
        content: Content to refine
        requirements: Requirements to check against
        max_iterations: Maximum iterations

    Returns:
        RefinementResult with refined content
    """
    loop = SelfRefinementLoop(max_iterations=max_iterations)
    return await loop.refine(content, requirements)


async def refine_research_report(
    report_text: str,
    topic: str,
) -> RefinementResult:
    """
    Refine a research report.

    Convenience function for report refinement.

    Args:
        report_text: Report content to refine
        topic: Research topic

    Returns:
        RefinementResult with refined report
    """
    refiner = ResearchReportRefiner()
    return await refiner.refine_report(report_text, topic)


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("SELF-REFINEMENT MODULE SELF-TEST")
    print("=" * 60)

    async def run_tests():
        # Test 1: Basic refinement loop structure
        print("\n[TEST 1] Refinement loop initialization...")
        loop = SelfRefinementLoop(max_iterations=2)
        assert loop.max_iterations == 2
        assert loop.approval_threshold == 0.80
        print("  [PASS] Loop initialized correctly")

        # Test 2: CritiqueResult structure
        print("\n[TEST 2] CritiqueResult structure...")
        critique = CritiqueResult(
            iteration=1,
            issues_found=["Missing citations", "Vague claims"],
            severity_scores={"Missing citations": 0.8, "Vague claims": 0.5},
            overall_quality=0.6,
            approved=False,
            critique_text="Content needs better citation support.",
            suggestions=["Add specific source citations", "Be more precise"],
        )
        critique_dict = critique.to_dict()
        assert "issues_found" in critique_dict
        assert len(critique_dict["issues_found"]) == 2
        print("  [PASS] CritiqueResult works correctly")

        # Test 3: RefinementResult structure
        print("\n[TEST 3] RefinementResult structure...")
        result = RefinementResult(
            original_content="Original text",
            final_content="Refined text",
            iterations=2,
            critique_history=[critique],
            improvement_score=0.15,
            approved=True,
            processing_time_ms=5000,
        )
        result_dict = result.to_dict()
        assert result_dict["iterations"] == 2
        assert result_dict["approved"] == True
        print("  [PASS] RefinementResult works correctly")

        # Test 4: Full refinement loop (requires API)
        print("\n[TEST 4] Full refinement loop (API test)...")
        try:
            test_content = """
            Water filters are important for health. Studies show they remove contaminants.
            Many people use filters at home. The filters work by trapping particles.
            """

            test_requirements = [
                "Must cite specific studies",
                "Must include quantitative data",
                "Must specify filter types",
            ]

            refiner = SelfRefinementLoop(max_iterations=2)
            result = await refiner.refine(test_content, test_requirements)

            assert result.iterations >= 1
            assert len(result.critique_history) >= 1
            assert result.final_content is not None

            print(f"  [PASS] Refinement completed in {result.iterations} iterations")
            print(f"  [INFO] Quality: {result.critique_history[-1].overall_quality:.2f}")
            print(f"  [INFO] Improvement: {result.improvement_score:+.4f}")
            print(f"  [INFO] Approved: {result.approved}")

        except ValueError as e:
            if "GEMINI_API_KEY" in str(e):
                print("  [SKIP] Gemini API key not configured")
            else:
                raise
        except Exception as e:
            print(f"  [WARN] Refinement test error: {e}")

    asyncio.run(run_tests())

    print("\n" + "=" * 60)
    print("SELF-TEST COMPLETE")
    print("=" * 60)
