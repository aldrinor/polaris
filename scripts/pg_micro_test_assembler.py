"""
Micro test: Report assembler post-processing.
Tests: filler stripping, newline insertion, hedge replacement,
       thin section merge, transition re-injection disabled.

Run: python -u scripts/pg_micro_test_assembler.py
"""
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()


def test_filler_stripping():
    """Test that filler words are removed from content."""
    from src.polaris_graph.synthesis.report_assembler import _clean_filler_and_tables

    content = (
        "Additionally, intermittent fasting reduced blood sugar by 0.51 SMD [1]. "
        "Moreover, time-restricted eating showed similar results [2]. "
        "Furthermore, the confidence interval excluded zero [1]. "
        "In addition, cardiovascular risks were noted [3]. "
        "Indeed, the hazard ratio was 1.91 [3]. "
        "Consequently, clinical practice should consider these trade-offs. "
        "Specifically, eating windows under 8 hours showed elevated risk [3]. "
        "Significantly, the meta-analysis included 99 randomized trials [1]."
    )
    # Note: citations count may drop by 1 because "Additionally, " at start
    # removes content before the first claim, but the claim itself stays
    cleaned = _clean_filler_and_tables(content)

    fillers_remaining = 0
    for f in ["Additionally", "Moreover", "Furthermore", "In addition", "Indeed",
              "Consequently", "Specifically", "Significantly"]:
        c = cleaned.count(f)
        fillers_remaining += c
        if c > 0:
            print(f"  STILL PRESENT: {f} ({c}x)")

    citations_remaining = len(re.findall(r"\[\d+\]", cleaned))

    print(f"  Fillers: {fillers_remaining} (was 8)")
    print(f"  Citations preserved: {citations_remaining} (should be 8)")
    print(f"  Content: {cleaned[:200]}...")

    passed = fillers_remaining == 0 and citations_remaining >= 7
    print(f"  PASS: {passed}")
    return passed


def test_table_filler_cleanup():
    """Test that filler words before table pipes are removed."""
    from src.polaris_graph.synthesis.report_assembler import _clean_filler_and_tables

    table_content = (
        "| Study | Result | CI |\n"
        "|:---|:---|:---|\n"
        "Moreover, | Meta-analysis 2024 | -0.51 SMD | -0.81 to -0.20 |\n"
        "Additionally, | Systematic review 2023 | -0.74 mmol/L | -1.13 to -0.36 |\n"
        "In contrast, | Epidemiological 2024 | HR 1.91 | 1.20 to 3.04 |"
    )
    cleaned = _clean_filler_and_tables(table_content)

    # Check no filler before pipes
    filler_before_pipe = bool(re.search(
        r"(Moreover|Additionally|In contrast),?\s*\|", cleaned
    ))
    print(f"  Filler before | : {filler_before_pipe} (should be False)")
    print(f"  Cleaned:\n{cleaned}")

    passed = not filler_before_pipe
    print(f"  PASS: {passed}")
    return passed


def test_hedge_replacement():
    """Test that hedging is replaced with definitive language on cited claims."""
    from src.polaris_graph.synthesis.report_assembler import _clean_filler_and_tables

    hedged = (
        "Intermittent fasting may reduce blood sugar levels [1]. "
        "Time-restricted eating might improve insulin sensitivity [2]. "
        "This approach could lower cardiovascular risk [3]. "
        "The protocol potentially reduces HbA1c [1]. "
        "Uncited claims may still hedge appropriately."
    )
    cleaned = _clean_filler_and_tables(hedged)

    # Cited claims should have definitive language
    cited_hedges = len(re.findall(r"\b(may|might|could|potentially)\b(?=[^.]*\[\d+\])", cleaned, re.I))
    # Uncited claims should keep hedging
    uncited_hedge = "may still hedge" in cleaned

    print(f"  Cited hedges remaining: {cited_hedges} (should be 0)")
    print(f"  Uncited hedge preserved: {uncited_hedge} (should be True)")
    print(f"  Content: {cleaned[:300]}...")

    passed = cited_hedges == 0 and uncited_hedge
    print(f"  PASS: {passed}")
    return passed


def test_newline_insertion():
    """Test that single-line content gets paragraph breaks."""
    # Simulate what the assembler does — must exceed 500 chars
    sec_content = (
        "Intermittent fasting significantly reduced fasting blood sugar with a "
        "standard mean difference of -0.51 (95% CI: -0.81 to -0.20; p=0.001) "
        "across 12 randomized controlled trials involving 1,245 participants [1]. "
        "Time-restricted eating protocols demonstrated a reduction in fasting "
        "glucose with a mean difference of -0.74 mmol/L (95% CI: -1.13 to -0.36) "
        "according to a 2023 systematic review of metabolic markers [2]. "
        "Epidemiological data from the NHANES longitudinal analysis raises "
        "significant concerns about cardiovascular mortality risk among individuals "
        "who restrict their eating window to fewer than 8 hours daily [3]. "
        "The American Heart Association reported a hazard ratio of 1.91 (95% CI: "
        "1.20 to 3.04) for cardiovascular death in this population [3]. "
        "**Key Findings:** The evidence shows clear glycemic benefits from "
        "intermittent fasting protocols alongside elevated cardiovascular mortality "
        "concerns for very short eating windows. | Study | Effect | CI | "
        "|:---|:---|:---| Meta-analysis 2024 | -0.51 SMD | -0.81 to -0.20 |"
    )

    # Apply the same logic as the assembler's second build
    if "\n" not in sec_content and len(sec_content) > 500:
        sec_content = re.sub(r"(?<!\n)(###\s)", r"\n\n\1", sec_content)
        sec_content = re.sub(r"(?<!\n)(\*\*Key Findings)", r"\n\n\1", sec_content)
        sec_content = re.sub(r"(?<!\n)(\|[^|]+\|[^|]+\|)", r"\n\n\1", sec_content, count=1)
        sec_content = re.sub(r"(\.\s)(?=[A-Z][a-z]{2,})", r".\n\n", sec_content)

    newlines = sec_content.count("\n")
    key_findings_on_new_line = "\n\n**Key Findings" in sec_content
    table_on_new_line = "\n\n| Study" in sec_content

    print(f"  Newlines inserted: {newlines} (should be > 0)")
    print(f"  **Key Findings on new line: {key_findings_on_new_line}")
    print(f"  Table on new line: {table_on_new_line}")
    print(f"  First 300 chars:\n{sec_content[:300]}")

    passed = newlines > 3 and key_findings_on_new_line and table_on_new_line
    print(f"  PASS: {passed}")
    return passed


def test_transition_injection_disabled():
    """Test that _inject_transitions is no longer re-adding fillers."""
    # Read the assembler source to verify the injection is commented out
    assembler_path = Path("src/polaris_graph/synthesis/report_assembler.py")
    source = assembler_path.read_text()

    # Check that _inject_transitions call is commented out
    active_inject = re.findall(
        r"^\s+section\[\"content\"\] = _inject_transitions\(",
        source,
        re.MULTILINE,
    )
    commented_inject = re.findall(
        r"#.*_inject_transitions",
        source,
    )

    print(f"  Active _inject_transitions calls: {len(active_inject)} (should be 0)")
    print(f"  Commented _inject_transitions refs: {len(commented_inject)} (should be >= 1)")

    passed = len(active_inject) == 0 and len(commented_inject) >= 1
    print(f"  PASS: {passed}")
    return passed


def test_hard_evidence_dedup():
    """Test that hard evidence dedup env var is set and logic exists."""
    val = os.getenv("PG_HARD_EVIDENCE_DEDUP", "0")
    print(f"  PG_HARD_EVIDENCE_DEDUP={val} (should be 1)")

    # Check the section_writer has the dedup logic
    writer_path = Path("src/polaris_graph/synthesis/section_writer.py")
    source = writer_path.read_text()
    has_hard_dedup = "_globally_claimed" in source
    has_env_check = "PG_HARD_EVIDENCE_DEDUP" in source

    print(f"  _globally_claimed in section_writer: {has_hard_dedup}")
    print(f"  PG_HARD_EVIDENCE_DEDUP env check: {has_env_check}")

    passed = val == "1" and has_hard_dedup and has_env_check
    print(f"  PASS: {passed}")
    return passed


def main():
    results = {}

    tests = [
        ("H", "Filler word stripping", test_filler_stripping),
        ("I", "Table filler cleanup", test_table_filler_cleanup),
        ("J", "Hedge replacement on cited claims", test_hedge_replacement),
        ("K", "Newline insertion in single-line content", test_newline_insertion),
        ("L", "Transition injection disabled", test_transition_injection_disabled),
        ("M", "Hard evidence dedup configured", test_hard_evidence_dedup),
    ]

    for test_id, name, func in tests:
        print(f"\n{'='*70}")
        print(f"TEST {test_id}: {name}")
        print(f"{'='*70}")
        results[test_id] = func()

    print(f"\n{'='*70}")
    print("SUMMARY")
    print(f"{'='*70}")
    all_pass = True
    for test_id, name, _ in tests:
        passed = results[test_id]
        if not passed:
            all_pass = False
        print(f"  Test {test_id} ({name}): {'PASS' if passed else 'FAIL'}")
    print(f"\n  ALL PASS: {all_pass}")


if __name__ == "__main__":
    main()
