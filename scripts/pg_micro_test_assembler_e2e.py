"""
End-to-end assembler test: Run assemble_report() with mock sections
and verify all post-processing works together without conflicts.

Run: python -u scripts/pg_micro_test_assembler_e2e.py
"""
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()


def test_assemble_report_e2e():
    from src.polaris_graph.synthesis.report_assembler import assemble_report
    from src.polaris_graph.synthesis.section_writer import SectionDraft
    from src.polaris_graph.schemas import ReportOutline, SectionOutlineItem

    # Build a realistic outline with 3 sections
    outline = ReportOutline(
        title="Research Report: Intermittent Fasting Health Effects",
        abstract="This report examines the health benefits and risks of intermittent fasting.",
        sections=[
            SectionOutlineItem(
                section_id="s01", title="Glycemic Control Improvements",
                description="Blood sugar and insulin effects",
                evidence_ids=["ev_aaa", "ev_bbb"], target_words=500, order=1,
            ),
            SectionOutlineItem(
                section_id="s02", title="Cardiovascular Risk Profile",
                description="Heart disease mortality data",
                evidence_ids=["ev_ccc", "ev_ddd"], target_words=500, order=2,
            ),
            SectionOutlineItem(
                section_id="s03", title="Thin Guidelines Section",
                description="Public health recommendations",
                evidence_ids=["ev_eee"], target_words=200, order=3,
            ),
        ],
    )

    # Build mock section drafts with realistic content including:
    # - Filler words to strip
    # - Hedging on cited claims
    # - Table with filler before pipe
    # - Single-line content (no newlines)
    # - Evidence IDs for citation resolution
    sections = [
        SectionDraft(
            section_id="s01",
            title="Glycemic Control Improvements",
            content=(
                "Additionally, intermittent fasting significantly reduced fasting blood sugar "
                "with a standard mean difference of -0.51 [CITE:ev_aaa]. Moreover, this finding "
                "was confirmed across 12 randomized controlled trials involving 1,245 participants "
                "[CITE:ev_aaa]. Furthermore, time-restricted eating may reduce fasting glucose "
                "by -0.74 mmol/L [CITE:ev_bbb]. Indeed, these results suggest that intermittent "
                "fasting protocols could improve insulin sensitivity in metabolically compromised "
                "populations [CITE:ev_bbb]. Consequently, the aggregate evidence from meta-analyses "
                "supports glycemic benefits. Specifically, the confidence intervals excluded zero "
                "for both primary outcomes [CITE:ev_aaa][CITE:ev_bbb]. | Metric | Effect | Source | "
                "|:---|:---|:---| Moreover, | Blood Sugar SMD | -0.51 | [CITE:ev_aaa] | "
                "Additionally, | Fasting Glucose | -0.74 mmol/L | [CITE:ev_bbb] | "
                "**Key Findings:** Glycemic control improves significantly with IF protocols."
            ),
            word_count=120,
            evidence_count=2,
        ),
        SectionDraft(
            section_id="s02",
            title="Cardiovascular Risk Profile",
            content=(
                "In addition, epidemiological data from NHANES linked time-restricted eating "
                "to elevated cardiovascular mortality risk [CITE:ev_ccc]. Significantly, the "
                "hazard ratio was 1.91 (95% CI: 1.20 to 3.04) for all-cause death [CITE:ev_ccc]. "
                "Furthermore, a separate analysis found that eating windows under 8 hours may "
                "increase heart disease death risk by 135% [CITE:ev_ddd]. Additionally, these "
                "findings in May 2024 contradicted the short-term metabolic benefits established "
                "in Section 1. Indeed, this paradox remains unresolved [CITE:ev_ddd]. "
                "**Key Findings:** Cardiovascular mortality risk is elevated for short eating windows."
            ),
            word_count=80,
            evidence_count=2,
        ),
        SectionDraft(
            section_id="s03",
            title="Thin Guidelines Section",
            content=(
                "Moreover, public health guidelines remain cautious [CITE:ev_eee]. "
                "No formal recommendation exists."
            ),
            word_count=12,
            evidence_count=1,
        ),
    ]

    # Set evidence_ids on drafts
    sections[0].evidence_ids = ["ev_aaa", "ev_bbb"]
    sections[1].evidence_ids = ["ev_ccc", "ev_ddd"]
    sections[2].evidence_ids = ["ev_eee"]

    # Build mock evidence pool
    evidence = [
        {"evidence_id": "ev_aaa", "statement": "IF reduced blood sugar SMD -0.51", "source_url": "https://pubmed.ncbi.nlm.nih.gov/111", "source_title": "Meta-analysis 2024", "tier": "GOLD"},
        {"evidence_id": "ev_bbb", "statement": "TRE reduced glucose -0.74 mmol/L", "source_url": "https://pubmed.ncbi.nlm.nih.gov/222", "source_title": "Systematic review 2023", "tier": "GOLD"},
        {"evidence_id": "ev_ccc", "statement": "NHANES HR 1.91 for cardiovascular death", "source_url": "https://jamanetwork.com/333", "source_title": "JAMA cohort 2024", "tier": "SILVER"},
        {"evidence_id": "ev_ddd", "statement": "Eating windows <8h linked to 135% higher CV death", "source_url": "https://newsroom.heart.org/444", "source_title": "AHA 2024", "tier": "SILVER"},
        {"evidence_id": "ev_eee", "statement": "No formal public health recommendation for IF", "source_url": "https://www.who.int/555", "source_title": "WHO advisory 2024", "tier": "GOLD"},
    ]

    # Build mock citation audit
    from src.polaris_graph.synthesis.report_assembler import CitationAudit

    class MockMapping:
        def __init__(self, eid, num):
            self.evidence_id = eid
            self.citation_number = num
            self.is_grounded = True

    class MockAudit:
        def __init__(self):
            self.mappings = [
                MockMapping("ev_aaa", 1),
                MockMapping("ev_bbb", 2),
                MockMapping("ev_ccc", 3),
                MockMapping("ev_ddd", 4),
                MockMapping("ev_eee", 5),
            ]

    audit = MockAudit()

    # Run assembler
    try:
        full_report, report_sections, bibliography = assemble_report(
            outline=outline,
            sections=sections,
            evidence=evidence,
            citation_audit=audit,
        )
    except Exception as e:
        print(f"  ASSEMBLER CRASHED: {e}")
        import traceback
        traceback.print_exc()
        return False

    # === VERIFY ALL FIXES ===
    print(f"  Report length: {len(full_report)} chars")
    print(f"  Sections: {len(report_sections)}")
    print(f"  Bibliography: {len(bibliography)}")

    issues = []

    # 1. Newlines present
    newlines = full_report.count("\n")
    print(f"\n  [C5] Newlines: {newlines}")
    if newlines < 5:
        issues.append("C5: No newlines in report")

    # 2. No filler words
    fillers = ["Additionally", "Moreover", "Furthermore", "In addition",
               "Indeed", "Consequently", "Specifically", "Significantly"]
    filler_count = sum(full_report.count(f) for f in fillers)
    print(f"  [C2] Filler words: {filler_count}")
    if filler_count > 2:  # Allow 1-2 that might be in non-sentence positions
        issues.append(f"C2: {filler_count} filler words remain")

    # 3. No filler before table pipes
    table_filler = bool(re.search(
        r"(Moreover|Additionally|Indeed|Furthermore),?\s*\|", full_report
    ))
    print(f"  [C3] Filler before |: {table_filler}")
    if table_filler:
        issues.append("C3: Filler before table pipes")

    # 4. Citations resolved [CITE:] -> [N]
    cite_raw = full_report.count("[CITE:")
    cite_num = len(re.findall(r"\[\d+\]", full_report))
    print(f"  [CITE] Raw [CITE:]: {cite_raw}, Resolved [N]: {cite_num}")
    if cite_raw > 0:
        issues.append(f"CITE: {cite_raw} unresolved [CITE:] markers")
    if cite_num < 5:
        issues.append(f"CITE: Only {cite_num} resolved citations")

    # 5. Hedging replaced on cited claims
    cited_hedges = re.findall(r"\b(may|might|could)\b(?=[^.]*\[\d+\])", full_report, re.I)
    # Filter out "May" as month
    real_hedges = [h for h in cited_hedges if not (h == "May" and "2024" in full_report[full_report.index(h):full_report.index(h)+10])]
    print(f"  [C7] Cited hedges: {len(real_hedges)}")
    if real_hedges:
        issues.append(f"C7: {len(real_hedges)} hedges on cited claims")

    # 6. "May 2024" preserved
    may_preserved = "May 2024" in full_report
    does_2024 = "Does 2024" in full_report
    print(f"  [C7b] 'May 2024' preserved: {may_preserved}, 'Does 2024': {does_2024}")
    if does_2024:
        issues.append("C7b: 'May 2024' mangled to 'Does 2024'")

    # 7. Thin section merged
    sec_titles = [s["title"] for s in report_sections]
    thin_merged = "Thin Guidelines Section" not in sec_titles
    print(f"  [C4] Thin section merged: {thin_merged} (sections: {sec_titles})")
    if not thin_merged:
        issues.append("C4: Thin section not merged")

    # 8. Section headings present
    h2_count = full_report.count("## ")
    print(f"  [FMT] ## headings: {h2_count}")
    if h2_count < 2:
        issues.append(f"FMT: Only {h2_count} ## headings")

    # 9. **Key Findings** on its own line
    kf_on_line = "\n\n**Key Findings" in full_report or "\n**Key Findings" in full_report
    print(f"  [FMT] Key Findings on new line: {kf_on_line}")

    # 10. No double-capitalization artifacts
    double_cap = bool(re.search(r"\. [A-Z][A-Z][a-z]", full_report))
    # This would indicate "THE" or "THe" from double capitalize
    print(f"  [BUG] Double-capitalization: {double_cap}")

    # Print a sample of the report
    print(f"\n  === REPORT SAMPLE (first 800 chars) ===")
    print(full_report[:800])
    print(f"\n  === REPORT SAMPLE (section 1 content) ===")
    if report_sections:
        print(report_sections[0]["content"][:500])

    # Verdict
    print(f"\n  === ISSUES FOUND: {len(issues)} ===")
    for issue in issues:
        print(f"    - {issue}")

    passed = len(issues) == 0
    print(f"\n  ALL PASS: {passed}")
    return passed


if __name__ == "__main__":
    print("=" * 70)
    print("E2E ASSEMBLER TEST: All fixes running together")
    print("=" * 70)
    ok = test_assemble_report_e2e()
    print(f"\n{'='*70}")
    print(f"RESULT: {'PASS' if ok else 'FAIL'}")
    print(f"{'='*70}")
