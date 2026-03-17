"""Forensic audit script for POLARIS v3 Hybrid reports.

Measures analytical depth, structural quality, and surface metrics
across all 4 quality layers. Designed for head-to-head comparison
against v1 (PG_TEST_039) and v2 (V2_E2E_007) baselines.

Usage:
    python scripts/audit_v3_report.py <report_md_path> [--json]
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path


def audit_report(report_md: str) -> dict:
    """Full forensic audit of a v3 report.

    Checks 4 quality layers:
    1. Core Analytical Depth (comparison, aggregation, challenge)
    2. Structure (duplicates, cross-references, coherence)
    3. Integrity (citations, filler, banned patterns)
    4. Surface (tables, key findings, word count)

    Args:
        report_md: Full markdown text of the report.

    Returns:
        Dict of audit metrics.
    """
    # --- Layer 1: Core Analytical Depth ---
    comparison_markers = len(re.findall(
        r'\b(compared to|in contrast|whereas|however|unlike|alternatively|'
        r'on the other hand|differs from|outperformed|underperformed)\b',
        report_md, re.I,
    ))
    aggregation_patterns = len(re.findall(
        r'\b(across \d+ studies|multiple sources|ranged from|median of|'
        r'average of|converging|majority of evidence|consistently)\b',
        report_md, re.I,
    ))
    challenge_markers = len(re.findall(
        r'\b(limitation|conflicting|gap in|remains unclear|caveat|'
        r'insufficient evidence|notable absence|further research needed)\b',
        report_md, re.I,
    ))
    explanation_markers = len(re.findall(
        r'\b(because|due to|mechanism|attributed to|driven by|'
        r'resulting from|implication|significance)\b',
        report_md, re.I,
    ))

    # --- Layer 2: Structure ---
    sentences = re.split(r'(?<=[.!?])\s+', report_md)
    non_trivial = [s.strip().lower() for s in sentences if len(s.strip()) > 30]
    unique_sentences = set(non_trivial)
    dup_ratio = 1 - len(unique_sentences) / max(len(non_trivial), 1)

    cross_refs = len(re.findall(
        r'as discussed in \[', report_md, re.I,
    ))
    # Section count
    sections = re.findall(r'^## .+', report_md, re.M)
    section_count = len(sections)

    # --- Layer 3: Integrity ---
    citations = re.findall(r'\[\d+\]', report_md)
    total_citations = len(citations)
    unique_citation_numbers = len(set(citations))
    words = report_md.split()
    word_count = len(words)
    cite_density = total_citations / max(word_count, 1) * 100

    # Filler detection
    filler_phrases = re.findall(
        r'\b(furthermore|it is important to note|interestingly|'
        r'in conclusion|it should be noted that|notably|'
        r'it is worth mentioning)\b',
        report_md, re.I,
    )
    filler_count = len(filler_phrases)

    # Sequential source pattern (bad: "Study A... Study B... Study C...")
    sequential_summaries = len(re.findall(
        r'(?:study|research|investigation|analysis)\s+\w+\s+(?:found|showed|reported|demonstrated)',
        report_md, re.I,
    ))

    # Banned patterns
    garbled_text = len(re.findall(r'â€|Ã[¡-¼]|\ufffd', report_md))

    # --- Layer 4: Surface ---
    table_rows = re.findall(r'\|[^|]+\|[^|]+\|', report_md)
    # Exclude header separator rows (|---|---|)
    data_table_rows = [
        r for r in table_rows
        if not re.match(r'\|\s*[-:]+\s*\|', r)
    ]
    table_count = 0
    in_table = False
    for line in report_md.split('\n'):
        if re.match(r'\|.+\|.+\|', line.strip()):
            if not in_table:
                table_count += 1
                in_table = True
        else:
            in_table = False
    # Approximate: each table has header + separator + data rows
    table_count = max(table_count // 3, table_count > 0)

    # Simpler: count distinct table blocks (header rows followed by separator)
    table_blocks = len(re.findall(
        r'\|[^|\n]+\|[^|\n]+\|\n\|[\s:|-]+\|',
        report_md,
    ))

    key_findings = len(re.findall(
        r'\*\*Key Findings?\*\*', report_md, re.I,
    ))

    # Bibliography size
    bib_entries = len(re.findall(r'^\[\d+\]', report_md, re.M))

    return {
        # Layer 1: Analytical Depth
        "comparison_markers": comparison_markers,
        "aggregation_patterns": aggregation_patterns,
        "challenge_markers": challenge_markers,
        "explanation_markers": explanation_markers,
        # Layer 2: Structure
        "word_count": word_count,
        "section_count": section_count,
        "dup_ratio_pct": round(dup_ratio * 100, 1),
        "cross_section_refs": cross_refs,
        # Layer 3: Integrity
        "total_citations": total_citations,
        "unique_citation_numbers": unique_citation_numbers,
        "citation_density_per_100w": round(cite_density, 2),
        "filler_count": filler_count,
        "sequential_summaries": sequential_summaries,
        "garbled_text_instances": garbled_text,
        # Layer 4: Surface
        "table_blocks": table_blocks,
        "key_findings_sections": key_findings,
        "bibliography_entries": bib_entries,
    }


def _grade(metrics: dict) -> str:
    """Assign a letter grade based on audit metrics."""
    score = 0

    # Analytical depth (40 points)
    score += min(metrics["comparison_markers"], 20)
    score += min(metrics["aggregation_patterns"], 10)
    score += min(metrics["challenge_markers"], 5)
    score += min(metrics["explanation_markers"], 5)

    # Structure (20 points)
    if metrics["dup_ratio_pct"] < 1:
        score += 10
    elif metrics["dup_ratio_pct"] < 5:
        score += 5
    score += min(metrics["cross_section_refs"], 5)
    score += min(metrics["key_findings_sections"], 5)

    # Integrity (25 points)
    if metrics["citation_density_per_100w"] >= 2.0:
        score += 10
    elif metrics["citation_density_per_100w"] >= 1.0:
        score += 5
    score += max(0, 5 - metrics["filler_count"])
    score += max(0, 5 - metrics["garbled_text_instances"])
    if metrics["bibliography_entries"] >= 15:
        score += 5
    elif metrics["bibliography_entries"] >= 8:
        score += 3

    # Surface (15 points)
    score += min(metrics["table_blocks"] * 3, 9)
    if metrics["word_count"] >= 8000:
        score += 3
    elif metrics["word_count"] >= 5000:
        score += 2
    if metrics["section_count"] >= 6:
        score += 3

    if score >= 85:
        return "A+"
    elif score >= 75:
        return "A"
    elif score >= 65:
        return "B+"
    elif score >= 55:
        return "B"
    elif score >= 45:
        return "B-"
    elif score >= 35:
        return "C+"
    elif score >= 25:
        return "C"
    return "D"


def main():
    parser = argparse.ArgumentParser(description="POLARIS v3 Report Forensic Audit")
    parser.add_argument("report_path", help="Path to the report markdown file")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    path = Path(args.report_path)
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)

    report_text = path.read_text(encoding="utf-8")
    metrics = audit_report(report_text)
    grade = _grade(metrics)
    metrics["grade"] = grade

    if args.json:
        print(json.dumps(metrics, indent=2))
    else:
        print(f"{'='*60}")
        print(f"POLARIS v3 Forensic Audit: {path.name}")
        print(f"{'='*60}")
        print()
        print(f"  Grade: {grade}")
        print(f"  Words: {metrics['word_count']:,}")
        print(f"  Sections: {metrics['section_count']}")
        print()
        print("  Layer 1: Analytical Depth")
        print(f"    Comparison markers:  {metrics['comparison_markers']:>4}")
        print(f"    Aggregation patterns:{metrics['aggregation_patterns']:>4}")
        print(f"    Challenge markers:   {metrics['challenge_markers']:>4}")
        print(f"    Explanation markers: {metrics['explanation_markers']:>4}")
        print()
        print("  Layer 2: Structure")
        print(f"    Duplicate ratio:     {metrics['dup_ratio_pct']:>5.1f}%")
        print(f"    Cross-section refs:  {metrics['cross_section_refs']:>4}")
        print()
        print("  Layer 3: Integrity")
        print(f"    Citations:           {metrics['total_citations']:>4} ({metrics['unique_citation_numbers']} unique)")
        print(f"    Citation density:    {metrics['citation_density_per_100w']:>5.2f} per 100 words")
        print(f"    Filler phrases:      {metrics['filler_count']:>4}")
        print(f"    Sequential summaries:{metrics['sequential_summaries']:>4}")
        print(f"    Garbled text:        {metrics['garbled_text_instances']:>4}")
        print()
        print("  Layer 4: Surface")
        print(f"    Tables:              {metrics['table_blocks']:>4}")
        print(f"    Key Findings:        {metrics['key_findings_sections']:>4}")
        print(f"    Bibliography:        {metrics['bibliography_entries']:>4}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
