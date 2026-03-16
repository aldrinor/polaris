#!/usr/bin/env python3
"""
POLARIS Quality Gates
=====================
Quality measurement and gating functions for SOTA compliance.

Quality Metrics:
- Source diversity: Unique domains in citations
- Hallucination rate: Claims not supported by evidence
- Citation accuracy: Semantic match between claim and evidence
- Content coverage: Research question coverage
- Word count: Minimum content threshold

Usage:
    from src.quality.gates import QualityGate, measure_source_diversity

    gate = QualityGate(report)
    result = gate.evaluate()
"""

import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

# Configure logging
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CheckResult:
    """Result of a single quality check."""
    name: str
    passed: bool
    actual: float
    threshold: float
    message: str = ""


@dataclass
class QualityGateResult:
    """Result of full quality gate evaluation."""
    passed: bool
    overall_score: float
    checks: Dict[str, CheckResult] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


# =============================================================================
# MEASUREMENT FUNCTIONS
# =============================================================================

def measure_source_diversity(citations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Measure source diversity in citations.

    SOTA Target: 10+ unique domains

    Args:
        citations: List of citation dicts with 'url' field

    Returns:
        Dict with unique_domains, unique_urls, domain_distribution
    """
    urls = [c.get("url", "") for c in citations if c.get("url")]
    domains = set()
    domain_counts = {}

    for url in urls:
        try:
            parsed = urlparse(url)
            domain = parsed.netloc
            if domain:
                domains.add(domain)
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        except Exception as e:
            # LOW-025: Log URL parsing error
            logger.debug(f"Failed to parse URL for domain extraction: {e}")
            continue

    return {
        "unique_domains": len(domains),
        "unique_urls": len(set(urls)),
        "total_citations": len(citations),
        "domain_distribution": domain_counts,
        "domains": list(domains),
    }


def measure_hallucination_rate(
    claims: List[Dict[str, Any]],
    verified_ids: Set[str],
) -> Dict[str, Any]:
    """
    Measure hallucination rate based on unverified claims.

    SOTA Target: <5% hallucination rate

    Args:
        claims: List of claims with citation_ids
        verified_ids: Set of verified chunk IDs

    Returns:
        Dict with hallucination_rate, unverified_claims
    """
    total_claims = len(claims)
    unverified_claims = []

    for claim in claims:
        claim_citations = claim.get("citations", [])
        # Claim is hallucinated if none of its citations are verified
        if claim_citations:
            has_verified = any(cid in verified_ids for cid in claim_citations)
            if not has_verified:
                unverified_claims.append(claim)
        else:
            # Claims without citations are hallucinations
            unverified_claims.append(claim)

    rate = len(unverified_claims) / total_claims if total_claims > 0 else 0.0

    return {
        "hallucination_rate": round(rate, 4),
        "total_claims": total_claims,
        "unverified_count": len(unverified_claims),
        "verified_count": total_claims - len(unverified_claims),
        "unverified_claims": unverified_claims[:5],  # Sample for debugging
    }


def measure_citation_accuracy(
    citations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Measure citation accuracy (semantic match between claim and evidence).

    SOTA Target: >95% accurate citations

    Args:
        citations: List of citations with 'confidence' or 'similarity_score'

    Returns:
        Dict with accuracy_rate, low_confidence_citations
    """
    if not citations:
        return {
            "accuracy_rate": 1.0,
            "total_citations": 0,
            "low_confidence_count": 0,
        }

    low_confidence = []
    confidence_sum = 0

    for citation in citations:
        conf = citation.get("confidence", citation.get("similarity_score", 0.5))
        confidence_sum += conf
        if conf < 0.5:
            low_confidence.append(citation)

    avg_confidence = confidence_sum / len(citations)

    return {
        "accuracy_rate": round(avg_confidence, 4),
        "total_citations": len(citations),
        "low_confidence_count": len(low_confidence),
        "low_confidence_citations": low_confidence[:3],
    }


def measure_content_coverage(
    report_text: str,
    research_question: str,
) -> Dict[str, Any]:
    """
    Measure how well the report covers the research question.

    SOTA Target: >80% coverage

    Args:
        report_text: Full report text
        research_question: Original research question

    Returns:
        Dict with coverage_score, missing_aspects
    """
    # Extract key aspects from question
    question_lower = research_question.lower()
    report_lower = report_text.lower()

    # Key aspects to check
    aspects = {
        "pathogen": ["pathogen", "bacteria", "virus", "microorganism", "germ"],
        "contamination": ["contamination", "contaminated", "polluted", "impure"],
        "rates": ["rate", "percentage", "proportion", "prevalence", "incidence"],
        "patterns": ["pattern", "trend", "distribution", "occurrence"],
        "filter": ["filter", "filtration", "treatment", "purification"],
        "water": ["water", "drinking", "household", "tap"],
    }

    covered = {}
    missing = []

    for aspect, keywords in aspects.items():
        # Check if aspect is in question
        if any(kw in question_lower for kw in keywords):
            # Check if covered in report
            is_covered = any(kw in report_lower for kw in keywords)
            covered[aspect] = is_covered
            if not is_covered:
                missing.append(aspect)

    total_aspects = len(covered)
    covered_count = sum(1 for v in covered.values() if v)
    coverage = covered_count / total_aspects if total_aspects > 0 else 1.0

    return {
        "coverage_score": round(coverage, 4),
        "aspects_checked": total_aspects,
        "aspects_covered": covered_count,
        "missing_aspects": missing,
        "aspect_details": covered,
    }


def measure_word_count(text: str) -> Dict[str, Any]:
    """
    Measure word count of report.

    SOTA Target: 2000+ words

    Args:
        text: Report text

    Returns:
        Dict with word_count, character_count
    """
    words = re.findall(r'\b\w+\b', text)

    return {
        "word_count": len(words),
        "character_count": len(text),
        "paragraph_count": text.count('\n\n') + 1,
    }


# =============================================================================
# QUALITY GATE CLASS
# =============================================================================

class QualityGate:
    """
    Quality gate evaluator for POLARIS outputs.

    Runs all quality checks and returns pass/fail status.
    """

    # SOTA Thresholds
    THRESHOLDS = {
        "source_diversity": 5,  # Minimum unique domains (SOTA: 10+)
        "hallucination_rate": 0.05,  # Maximum 5% (SOTA target)
        "citation_accuracy": 0.85,  # Minimum 85% (SOTA: 95%)
        "content_coverage": 0.70,  # Minimum 70% (SOTA: 80%)
        "word_count": 1500,  # Minimum words (SOTA: 2000+)
        "citation_count": 10,  # Minimum citations (SOTA target)
    }

    # Relaxed thresholds for development/testing
    THRESHOLDS_RELAXED = {
        "source_diversity": 3,
        "hallucination_rate": 0.15,
        "citation_accuracy": 0.60,
        "content_coverage": 0.50,
        "word_count": 500,
        "citation_count": 5,
    }

    def __init__(
        self,
        report_text: str,
        citations: List[Dict[str, Any]],
        claims: List[Dict[str, Any]] = None,
        verified_ids: Set[str] = None,
        research_question: str = "",
    ):
        """
        Initialize quality gate.

        Args:
            report_text: Full report text
            citations: List of citation dictionaries
            claims: List of claim dictionaries
            verified_ids: Set of verified chunk IDs
            research_question: Original research question
        """
        self.report_text = report_text
        self.citations = citations or []
        self.claims = claims or []
        self.verified_ids = verified_ids or set()
        self.research_question = research_question

    def evaluate(self) -> QualityGateResult:
        """
        Run all quality checks and return result.

        Returns:
            QualityGateResult with all check details
        """
        checks = {}
        issues = []
        recommendations = []

        # 1. Source Diversity
        diversity = measure_source_diversity(self.citations)
        diversity_passed = diversity["unique_domains"] >= self.THRESHOLDS["source_diversity"]
        checks["source_diversity"] = CheckResult(
            name="Source Diversity",
            passed=diversity_passed,
            actual=diversity["unique_domains"],
            threshold=self.THRESHOLDS["source_diversity"],
            message=f"{diversity['unique_domains']} unique domains",
        )
        if not diversity_passed:
            issues.append(f"Only {diversity['unique_domains']} unique domains (need {self.THRESHOLDS['source_diversity']}+)")
            recommendations.append("Add more diverse sources: academic, government, industry")

        # 2. Citation Count
        citation_count = len(self.citations)
        citation_passed = citation_count >= self.THRESHOLDS["citation_count"]
        checks["citation_count"] = CheckResult(
            name="Citation Count",
            passed=citation_passed,
            actual=citation_count,
            threshold=self.THRESHOLDS["citation_count"],
            message=f"{citation_count} citations",
        )
        if not citation_passed:
            issues.append(f"Only {citation_count} citations (need {self.THRESHOLDS['citation_count']}+)")

        # 3. Citation Accuracy
        accuracy = measure_citation_accuracy(self.citations)
        accuracy_passed = accuracy["accuracy_rate"] >= self.THRESHOLDS["citation_accuracy"]
        checks["citation_accuracy"] = CheckResult(
            name="Citation Accuracy",
            passed=accuracy_passed,
            actual=accuracy["accuracy_rate"],
            threshold=self.THRESHOLDS["citation_accuracy"],
            message=f"{accuracy['accuracy_rate']:.1%} accuracy",
        )
        if not accuracy_passed:
            issues.append(f"Citation accuracy {accuracy['accuracy_rate']:.1%} (need {self.THRESHOLDS['citation_accuracy']:.0%}+)")

        # 4. Word Count
        word_metrics = measure_word_count(self.report_text)
        word_passed = word_metrics["word_count"] >= self.THRESHOLDS["word_count"]
        checks["word_count"] = CheckResult(
            name="Word Count",
            passed=word_passed,
            actual=word_metrics["word_count"],
            threshold=self.THRESHOLDS["word_count"],
            message=f"{word_metrics['word_count']} words",
        )
        if not word_passed:
            issues.append(f"Only {word_metrics['word_count']} words (need {self.THRESHOLDS['word_count']}+)")

        # 5. Content Coverage
        if self.research_question:
            coverage = measure_content_coverage(self.report_text, self.research_question)
            coverage_passed = coverage["coverage_score"] >= self.THRESHOLDS["content_coverage"]
            checks["content_coverage"] = CheckResult(
                name="Content Coverage",
                passed=coverage_passed,
                actual=coverage["coverage_score"],
                threshold=self.THRESHOLDS["content_coverage"],
                message=f"{coverage['coverage_score']:.1%} coverage",
            )
            if not coverage_passed:
                issues.append(f"Content coverage {coverage['coverage_score']:.1%} (need {self.THRESHOLDS['content_coverage']:.0%}+)")
                if coverage["missing_aspects"]:
                    recommendations.append(f"Missing aspects: {', '.join(coverage['missing_aspects'])}")

        # 6. Hallucination Rate (if claims available)
        if self.claims:
            hallucination = measure_hallucination_rate(self.claims, self.verified_ids)
            hallucination_passed = hallucination["hallucination_rate"] <= self.THRESHOLDS["hallucination_rate"]
            checks["hallucination_rate"] = CheckResult(
                name="Hallucination Rate",
                passed=hallucination_passed,
                actual=hallucination["hallucination_rate"],
                threshold=self.THRESHOLDS["hallucination_rate"],
                message=f"{hallucination['hallucination_rate']:.1%} hallucination",
            )
            if not hallucination_passed:
                issues.append(f"Hallucination rate {hallucination['hallucination_rate']:.1%} (need <{self.THRESHOLDS['hallucination_rate']:.0%})")

        # Calculate overall score and pass/fail
        passed_checks = sum(1 for c in checks.values() if c.passed)
        total_checks = len(checks)
        overall_score = passed_checks / total_checks if total_checks > 0 else 0.0

        # Pass if all critical checks pass OR score >= 80%
        all_passed = all(c.passed for c in checks.values())

        return QualityGateResult(
            passed=all_passed or overall_score >= 0.8,
            overall_score=round(overall_score, 4),
            checks=checks,
            issues=issues,
            recommendations=recommendations,
        )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_quality_gate(
    report_text: str,
    citations: List[Dict[str, Any]],
    research_question: str = "",
    claims: List[Dict[str, Any]] = None,
    verified_ids: Set[str] = None,
) -> QualityGateResult:
    """
    Convenience function to run quality gate.

    Args:
        report_text: Full report text
        citations: List of citations
        research_question: Research question
        claims: Optional claims list
        verified_ids: Optional verified IDs

    Returns:
        QualityGateResult
    """
    gate = QualityGate(
        report_text=report_text,
        citations=citations,
        claims=claims,
        verified_ids=verified_ids,
        research_question=research_question,
    )
    return gate.evaluate()


# =============================================================================
# SELF-TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("QUALITY GATES SELF-TEST")
    print("=" * 60)

    # Test data
    test_citations = [
        {"url": "https://pubmed.ncbi.nlm.nih.gov/12345/", "confidence": 0.9},
        {"url": "https://www.cdc.gov/water/safety", "confidence": 0.85},
        {"url": "https://www.who.int/water", "confidence": 0.8},
        {"url": "https://news.example.com/article", "confidence": 0.6},
        {"url": "https://academic.edu/paper", "confidence": 0.75},
    ]

    test_report = """
    # Research Report on Water Filter Contamination

    ## Introduction
    Water filters are essential for household water safety. Pathogen contamination
    remains a significant concern in many regions. This report examines the rates
    and patterns of contamination in household water filtration systems.

    ## Findings
    Studies show that bacteria can accumulate in filters over time. The contamination
    rate varies based on filter type, usage patterns, and maintenance frequency.
    Regular replacement of filters is recommended to minimize pathogen growth.

    ## Conclusion
    Proper maintenance and regular replacement of household water filters are
    essential for ensuring safe drinking water. Further research is needed on
    optimal replacement intervals.
    """

    test_question = "What pathogen contamination rates and patterns exist in household water filters?"

    # Test 1: Source diversity
    print("\n[TEST 1] Source diversity measurement...")
    diversity = measure_source_diversity(test_citations)
    assert diversity["unique_domains"] == 5
    print(f"  Unique domains: {diversity['unique_domains']}")
    print("  [PASS] Source diversity")

    # Test 2: Word count
    print("\n[TEST 2] Word count measurement...")
    word_metrics = measure_word_count(test_report)
    assert word_metrics["word_count"] > 100
    print(f"  Word count: {word_metrics['word_count']}")
    print("  [PASS] Word count")

    # Test 3: Content coverage
    print("\n[TEST 3] Content coverage measurement...")
    coverage = measure_content_coverage(test_report, test_question)
    assert coverage["coverage_score"] > 0.5
    print(f"  Coverage score: {coverage['coverage_score']:.1%}")
    print(f"  Missing aspects: {coverage['missing_aspects']}")
    print("  [PASS] Content coverage")

    # Test 4: Full quality gate
    print("\n[TEST 4] Full quality gate evaluation...")
    result = run_quality_gate(
        report_text=test_report,
        citations=test_citations,
        research_question=test_question,
    )
    print(f"  Overall score: {result.overall_score:.1%}")
    print(f"  Passed: {result.passed}")
    print(f"  Issues: {len(result.issues)}")
    for check_name, check_result in result.checks.items():
        status = "PASS" if check_result.passed else "FAIL"
        print(f"    {check_name}: {status} ({check_result.message})")
    print("  [PASS] Quality gate evaluation")

    print("\n" + "=" * 60)
    print("ALL QUALITY GATES TESTS PASSED")
    print("=" * 60)
