"""
FIX-138A: Automated Output Quality Gate

Checks the final report text for readability and quality issues that
pass faithfulness/entropy gating but produce unreadable output:
1. CoT leakage (thinking process leaked into prose)
2. Internal markers ([REVISION_HEDGED], [PARTIAL_SUPPORT:...], [UNGROUNDED])
3. Near-duplicate sentences (Jaccard word overlap)
4. PDF corruption noise (content about PDF extraction failures)

Returns an OutputQualityResult with pass/fail, score, and issue list.
All thresholds are configurable via environment variables (LAW VI).
"""

import logging
import os
import re
from dataclasses import dataclass, field
from typing import List

logger = logging.getLogger(__name__)


# Thresholds (configurable via env vars, LAW VI)
MAX_COT_INSTANCES = int(os.environ.get("POLARIS_OQG_MAX_COT", "5"))
MAX_MARKER_INSTANCES = int(os.environ.get("POLARIS_OQG_MAX_MARKERS", "3"))
MAX_DUPLICATE_RATIO = float(os.environ.get("POLARIS_OQG_MAX_DUPL_RATIO", "0.15"))
MAX_PDF_NOISE_INSTANCES = int(os.environ.get("POLARIS_OQG_MAX_PDF_NOISE", "3"))
DEDUP_JACCARD_THRESHOLD = float(
    os.environ.get("POLARIS_OQG_DEDUP_THRESHOLD", "0.70")
)


@dataclass
class QualityIssue:
    """A single quality issue found in the output."""
    category: str  # "cot_leakage", "internal_marker", "near_duplicate", "pdf_noise"
    severity: str  # "critical", "major", "minor"
    description: str
    example: str = ""
    count: int = 0


@dataclass
class OutputQualityResult:
    """Result of the output quality gate check."""
    passed: bool
    score: float  # 0.0 to 100.0
    issues: List[QualityIssue] = field(default_factory=list)
    cot_count: int = 0
    marker_count: int = 0
    duplicate_count: int = 0
    pdf_noise_count: int = 0
    total_sentences: int = 0


# CoT patterns that should never appear in final output
COT_PATTERNS = [
    r"Let me (try|check|reach|count|think|ensure|verify|see|look|read|now)",
    r"I will (now|try|write|check|generate|create|produce|compose|draft)",
    r"I need to\b",
    r"I should\b",
    r"Checking (word|character|sentence)\b",
    r"Now (I|let|let's|we)\b",
    r"Okay,?\s+(let|so|I)",
    r"First,?\s+I\b",
    r"The user (wants|asked|requested)",
    r"word count",
    r"character count",
    r"sentence count",
    r"token (count|limit)",
    r"Actually,?\s+(?:let|I|the)",
    r"In summary,?\s+(?:I|we|the task)",
    r"To summarize,?\s+(?:I|we|the)",
    r"My (approach|plan|strategy|thought)",
    r"Step \d+:",
    # FIX-140: Additional CoT patterns from gap analysis
    r"Wait,?\s+(?:let|I|the|so)",
    r"Looking at\s+",
    r"The evidence\s+(says|provided|suggests|indicates|shows)",
    r"I can\s+(?:see|tell|find)",
    r"Hmm,?\s+",
    r"So,?\s+(?:the|this|I|we|let)",
    # FIX-143: Evidence ID artifacts and prompt template echoes
    r"\bev_atomic_[a-f0-9]+\b",
    r"\bev_\w{3,40}\b",
    r"\bchunk_atomic_\w+\b",
    r'Source quote:\s*"',
    r"Attempt\s+\d+\s*[-—:]",
    r"\bthe claim to express\b",
    r"\bthe original sentence\b",
    r"\bmore faithful\b",
    r"\bthe rewrite\b",
    r"\bevidence descriptions?\b",
]

# Internal markers that must be stripped before output
INTERNAL_MARKER_PATTERNS = [
    r"\[REVISION_HEDGED\]",
    r"\[PARTIAL_SUPPORT:[^\]]*\]",
    r"\[UNGROUNDED\]",
    r"\[FIX-\d+\]",
    r"\[DEBUG\]",
    r"\[INTERNAL\]",
]

# PDF noise content patterns
PDF_NOISE_PATTERNS = [
    r"%PDF-\d",
    r"corrupted\s+or\s+binary\s+encoded",
    r"preventing\s+text\s+extraction",
    r"binary\s+encoded\s+content",
    r"PDF\s+document\s+(could\s+not|cannot|failed\s+to)",
    r"text\s+extraction\s+(was\s+not|is\s+not)\s+possible",
    r"garbled\s+(text|content|output)",
    r"document\s+appears\s+to\s+be\s+(corrupt|damaged|binary)",
    # FIX-142: Additional PDF noise patterns from gap analysis
    r"not\s+directly\s+extractable",
    r"minimal\s+extractable",
    r"\bcorrupted\b(?!\s+or\s+binary)",
    r"PDF-\d+\.\d+",
]


def check_output_quality(report_text: str) -> OutputQualityResult:
    """
    Run all quality checks against the final report text.

    Args:
        report_text: The final report text to check.

    Returns:
        OutputQualityResult with pass/fail, score, and detailed issues.
    """
    if not report_text or not report_text.strip():
        return OutputQualityResult(
            passed=False,
            score=0.0,
            issues=[QualityIssue(
                category="empty",
                severity="critical",
                description="Report text is empty",
            )],
        )

    issues = []
    sentences = _split_sentences(report_text)
    total_sentences = len(sentences)

    # Check 1: CoT leakage
    cot_count, cot_examples = _check_cot_leakage(report_text)
    if cot_count > 0:
        severity = "critical" if cot_count > MAX_COT_INSTANCES else "major"
        issues.append(QualityIssue(
            category="cot_leakage",
            severity=severity,
            description=f"Found {cot_count} CoT leakage instances",
            example=cot_examples[0] if cot_examples else "",
            count=cot_count,
        ))

    # Check 2: Internal markers
    marker_count, marker_examples = _check_internal_markers(report_text)
    if marker_count > 0:
        severity = "critical" if marker_count > MAX_MARKER_INSTANCES else "major"
        issues.append(QualityIssue(
            category="internal_marker",
            severity=severity,
            description=f"Found {marker_count} internal markers",
            example=marker_examples[0] if marker_examples else "",
            count=marker_count,
        ))

    # Check 3: Near-duplicate sentences
    duplicate_count = _check_near_duplicates(sentences)
    duplicate_ratio = duplicate_count / max(total_sentences, 1)
    if duplicate_count > 0:
        severity = "major" if duplicate_ratio > MAX_DUPLICATE_RATIO else "minor"
        issues.append(QualityIssue(
            category="near_duplicate",
            severity=severity,
            description=(
                f"Found {duplicate_count} near-duplicate sentences "
                f"({duplicate_ratio*100:.1f}% of total)"
            ),
            count=duplicate_count,
        ))

    # Check 4: PDF noise content
    pdf_count, pdf_examples = _check_pdf_noise(report_text)
    if pdf_count > 0:
        severity = "major" if pdf_count > MAX_PDF_NOISE_INSTANCES else "minor"
        issues.append(QualityIssue(
            category="pdf_noise",
            severity=severity,
            description=f"Found {pdf_count} PDF noise phrases",
            example=pdf_examples[0] if pdf_examples else "",
            count=pdf_count,
        ))

    # Calculate score (100 = perfect, 0 = unusable)
    # Deductions: CoT=-4/instance, markers=-3/instance, dupes=-2/instance, pdf=-2/instance
    deductions = (
        cot_count * 4.0
        + marker_count * 3.0
        + duplicate_count * 2.0
        + pdf_count * 2.0
    )
    score = max(0.0, 100.0 - deductions)

    # Determine pass/fail
    has_critical = any(i.severity == "critical" for i in issues)
    passed = not has_critical and score >= 60.0

    result = OutputQualityResult(
        passed=passed,
        score=score,
        issues=issues,
        cot_count=cot_count,
        marker_count=marker_count,
        duplicate_count=duplicate_count,
        pdf_noise_count=pdf_count,
        total_sentences=total_sentences,
    )

    logger.info(
        f"[FIX-138] Output Quality Gate: score={score:.1f}, passed={passed}, "
        f"cot={cot_count}, markers={marker_count}, dupes={duplicate_count}, "
        f"pdf_noise={pdf_count}"
    )

    return result


def _split_sentences(text: str) -> List[str]:
    """Split report text into individual sentences for analysis."""
    # Split on sentence-ending punctuation followed by space or newline
    raw = re.split(r'(?<=[.!?])\s+', text)
    # Also split on newlines for bullet points
    sentences = []
    for chunk in raw:
        for line in chunk.split("\n"):
            stripped = line.strip().lstrip("- *#>")
            if stripped and len(stripped.split()) >= 4:
                sentences.append(stripped)
    return sentences


def _check_cot_leakage(text: str) -> tuple:
    """Count CoT leakage instances and collect examples."""
    count = 0
    examples = []
    for pattern in COT_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE | re.MULTILINE)
        if matches:
            hit_count = len(matches)
            count += hit_count
            if len(examples) < 3:
                # Find the actual context around the match
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    start = max(0, m.start() - 20)
                    end = min(len(text), m.end() + 40)
                    examples.append(text[start:end].strip())
                    if len(examples) >= 3:
                        break
    return count, examples


def _check_internal_markers(text: str) -> tuple:
    """Count internal markers and collect examples."""
    count = 0
    examples = []
    for pattern in INTERNAL_MARKER_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            count += len(matches)
            examples.extend(matches[:3])
    return count, examples[:3]


def _check_near_duplicates(sentences: List[str]) -> int:
    """Count near-duplicate sentence pairs using Jaccard similarity."""
    if len(sentences) <= 1:
        return 0

    cite_pattern = re.compile(r'\[CITE:[^\]]+\]|\[\d+\]')

    def word_set(text: str) -> set:
        cleaned = cite_pattern.sub("", text).lower()
        return set(cleaned.split())

    duplicates = 0
    seen_sets = []
    for sentence in sentences:
        words = word_set(sentence)
        if not words:
            continue
        for existing in seen_sets:
            intersection = len(words & existing)
            union = len(words | existing)
            if union > 0 and (intersection / union) >= DEDUP_JACCARD_THRESHOLD:
                duplicates += 1
                break
        else:
            seen_sets.append(words)

    return duplicates


def _check_pdf_noise(text: str) -> tuple:
    """Count PDF noise content instances."""
    count = 0
    examples = []
    for pattern in PDF_NOISE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            count += len(matches)
            examples.extend(matches[:3])
    return count, examples[:3]


def repair_output_quality(text: str) -> str:
    """
    FIX-144: Active repair — strip all detected artifacts from report text.

    Called BEFORE check_output_quality() so the quality gate measures the
    repaired text. This is the last line of defense against pipeline artifacts
    that survived upstream sanitization.

    Args:
        text: The report text to repair.

    Returns:
        Cleaned text with artifacts stripped.
    """
    if not text or not text.strip():
        return text

    repaired = text
    total_repairs = 0

    # Repair 1: Strip CoT leakage lines
    # For line-level CoT patterns (anchored with ^), remove entire lines
    # FIX-231: When POLARIS_COT_SCRUBBER_LITE=1, use only unambiguous patterns
    # to avoid destroying legitimate research prose like "The evidence suggests..."
    _safe_cot_patterns = [
        r"^Let me (try|check|reach|count|think|ensure|verify|see|look|read|now).*$",
        r"^I will (now|try|write|check|generate|create|produce|compose|draft).*$",
        r"^I need to\b.*$",
        r"^I should\b.*$",
        r"^Checking (word|character|sentence)\b.*$",
        r"^Now (I|let|let's|we)\b.*$",
        r"^Okay,?\s+(let|so|I).*$",
        r"^First,?\s+I\b.*$",
        r"^Wait,?\s+.*$",
        r"^I can\s+(?:see|tell|find).*$",
        r"^Hmm,?\s+.*$",
        r"^My (approach|plan|strategy|thought).*$",
        r"^Step \d+:.*$",
    ]
    _aggressive_cot_patterns = [
        r"^Actually,?\s+.*$",
        r"^In summary,?\s+(?:I|we|the task).*$",
        r"^To summarize,?\s+(?:I|we|the).*$",
        r"^Looking at\s+.*$",
        r"^The evidence\s+(says|provided|suggests|indicates|shows).*$",
        r"^So,?\s+(?:the|this|I|we|let).*$",
    ]
    lite_mode = os.environ.get("POLARIS_COT_SCRUBBER_LITE", "0") == "1"
    _line_cot_patterns = _safe_cot_patterns if lite_mode else _safe_cot_patterns + _aggressive_cot_patterns
    lines = repaired.split("\n")
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        is_cot = False
        for pat in _line_cot_patterns:
            if re.match(pat, stripped_line, re.IGNORECASE):
                is_cot = True
                total_repairs += 1
                break
        if not is_cot:
            cleaned_lines.append(line)
    repaired = "\n".join(cleaned_lines)

    # Repair 2: Strip inline artifacts (evidence IDs, source quotes, prompt echoes)
    _inline_repairs = [
        (r"\bev_atomic_[a-f0-9]+\b", ""),
        (r"\bev_\w{3,40}\b", ""),
        (r"\bchunk_atomic_\w+\b", ""),
        (r'\.\s*Source quote:\s*"[^"]{0,500}"', "."),
        (r'Source quote:\s*"[^"]{0,500}"\.?\s*', ""),
        (r"Attempt\s+\d+\s*[-—:]\s*", ""),
        (r"\bthe claim to express\b", ""),
        (r"\bthe original sentence\b", ""),
        (r"\bmore faithful\b", ""),
        (r"\bthe rewrite\b", ""),
        (r"\bevidence descriptions?\b", ""),
    ]
    for pattern, replacement in _inline_repairs:
        matches = re.findall(pattern, repaired, re.IGNORECASE)
        if matches:
            total_repairs += len(matches)
            repaired = re.sub(pattern, replacement, repaired, flags=re.IGNORECASE)

    # Repair 3: Strip internal markers
    for pattern in INTERNAL_MARKER_PATTERNS:
        matches = re.findall(pattern, repaired, re.IGNORECASE)
        if matches:
            total_repairs += len(matches)
            repaired = re.sub(pattern, "", repaired, flags=re.IGNORECASE)

    # Repair 4: Clean up whitespace artifacts from removal
    if total_repairs > 0:
        repaired = re.sub(r"  +", " ", repaired)
        repaired = re.sub(r"\(\s*\)", "", repaired)
        repaired = re.sub(r"\s+\.", ".", repaired)
        repaired = re.sub(r"\s+,", ",", repaired)
        repaired = re.sub(r"\n{3,}", "\n\n", repaired)
        logger.info(
            f"[FIX-144] Repaired {total_repairs} artifacts in report text"
        )

    return repaired
