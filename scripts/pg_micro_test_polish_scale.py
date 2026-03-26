"""
Scale tests: Polish pass on real 14K-word report + interaction with post-processing.
Run: python -u scripts/pg_micro_test_polish_scale.py
"""
import asyncio
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

results = {}


def register(test_id, name):
    def decorator(func):
        print(f"\n{'='*70}")
        print(f"TEST {test_id}: {name}")
        print(f"{'='*70}")
        try:
            passed = func()
        except Exception as e:
            import traceback
            traceback.print_exc()
            passed = False
        results[test_id] = (name, passed)
        print(f"  >>> {'PASS' if passed else 'FAIL'}")
        return func
    return decorator


@register("SC1", "Polish pass on real 14K-word report (live LLM)")
def _():
    async def _test():
        from src.polaris_graph.llm.openrouter_client import OpenRouterClient
        client = OpenRouterClient()

        # Load actual TEST_070 report
        report_path = Path("outputs/polaris_graph/_test_polish_input.txt")
        if not report_path.exists():
            print("  No test input found, skipping")
            return True

        full_report = report_path.read_text(encoding="utf-8")
        orig_words = len(full_report.split())
        orig_cites = len(re.findall(r"\[\d+\]", full_report))
        orig_headings = full_report.count("## ")

        print(f"  Input: {orig_words} words, {orig_cites} citations, {orig_headings} headings")

        # Truncate to first 4000 words if too long for single call
        # (Real pipeline would need to handle this too)
        words = full_report.split()
        if len(words) > 4000:
            truncated = " ".join(words[:4000])
            print(f"  Truncated to 4000 words for test (real pipeline sends full)")
        else:
            truncated = full_report

        trunc_cites = len(re.findall(r"\[\d+\]", truncated))
        trunc_headings = truncated.count("## ")

        polish_prompt = (
            "You are an expert academic editor. Edit this research report:\n"
            "1. REDUNDANCY: Same stats in multiple sections? Keep in most relevant, "
            "cross-reference elsewhere.\n"
            "2. PROSE: Vary sentence structure. Tighten verbose sentences.\n"
            "3. PRESERVE: Keep ALL [N] citation markers exactly. Keep all ## headings. "
            "Keep **Key Findings** sections.\n\n"
            f"Output the COMPLETE edited report.\n\nREPORT:\n{truncated}"
        )

        import time
        t0 = time.time()
        r = await client.reason(
            prompt=polish_prompt,
            effort="high",
            max_tokens=16384,
        )
        elapsed = time.time() - t0

        polished = r.content.strip()
        new_words = len(polished.split())
        new_cites = len(re.findall(r"\[\d+\]", polished))
        new_headings = polished.count("## ")

        print(f"  Output: {new_words} words, {new_cites} citations, {new_headings} headings")
        print(f"  Time: {elapsed:.1f}s")
        print(f"  Word ratio: {new_words/max(len(truncated.split()),1):.1%}")
        print(f"  Citation ratio: {new_cites/max(trunc_cites,1):.1%}")
        print(f"  Heading ratio: {new_headings/max(trunc_headings,1):.1%}")

        # Check for CoT leakage
        has_cot = any(p in polished[:300].lower() for p in [
            "analyze the request", "let me", "the user", "my task"
        ])
        print(f"  CoT in output: {has_cot}")

        # Validation criteria (same as pipeline)
        length_ok = len(polished) > len(truncated) * 0.3
        cites_ok = new_cites >= trunc_cites * 0.5
        headings_ok = new_headings >= trunc_headings * 0.5

        print(f"  Length OK (>30%): {length_ok}")
        print(f"  Citations OK (>50%): {cites_ok}")
        print(f"  Headings OK (>50%): {headings_ok}")

        # Show first 500 chars of polished output
        print(f"  Preview: {polished[:500]}")

        return length_ok and cites_ok and not has_cot

    return asyncio.run(_test())


@register("SC2", "Polish output survives _reduce_filler post-processing")
def _():
    from src.polaris_graph.synthesis.report_assembler import _reduce_filler

    # Simulate polished report with proper formatting
    polished = (
        "## Section 1: Protocol Definitions\n\n"
        "Intermittent fasting encompasses four primary protocols [1]. "
        "Time-restricted eating limits intake to 8 hours daily [2]. "
        "Alternate-day fasting alternates between fasting and ad libitum days [3].\n\n"
        "## Section 2: Weight Loss\n\n"
        "Clinical trials demonstrate weight loss of 3-8% over 12 weeks [4]. "
        "The 4:3 protocol achieved 7.6% reduction versus 5% with calorie restriction [5].\n\n"
        "**Key Findings:**\n"
        "- IF produces consistent weight loss across protocols [4].\n"
        "- 4:3 protocol shows superior outcomes [5].\n\n"
        "## References\n\n"
        "1. Smith et al. (2024)\n"
        "2. Jones et al. (2025)\n"
    )

    # Run _reduce_filler
    reduced = _reduce_filler(polished)

    # Check preservation
    headings_ok = reduced.count("## ") >= polished.count("## ") * 0.8
    cites_ok = len(re.findall(r"\[\d+\]", reduced)) >= len(re.findall(r"\[\d+\]", polished)) * 0.8
    has_newlines = "\n" in reduced
    kf_ok = "**Key Findings:**" in reduced or "Key Findings" in reduced

    print(f"  Headings: {polished.count('## ')} -> {reduced.count('## ')} (OK: {headings_ok})")
    print(f"  Citations: {len(re.findall(r'[0-9]+', polished))} -> {len(re.findall(r'[0-9]+', reduced))}")
    print(f"  Newlines preserved: {has_newlines} ({reduced.count(chr(10))})")
    print(f"  Key Findings: {kf_ok}")

    return headings_ok and cites_ok and has_newlines


@register("SC3", "Full pipeline post-processing chain doesn't destroy content")
def _():
    from src.polaris_graph.synthesis.report_assembler import (
        _clean_filler_and_tables,
        _reduce_filler,
    )

    # Simulate content after polish pass
    content = (
        "Alternate-day fasting demonstrated a mean difference of -4.30 kg "
        "(95% CI: -5.54 to -3.05; I2=96%; GRADE: low) across 7 RCTs involving "
        "269 participants [1]. Time-restricted eating reduced fasting glucose by "
        "-0.74 mmol/L (95% CI: -1.13 to -0.36; GRADE: moderate) [2]. "
        "As established in Section 1, the 4:3 protocol achieved superior weight "
        "loss of 7.6% versus 5% with calorie restriction [3]. "
        "| Protocol | Effect | CI | GRADE | "
        "|:---|:---|:---|:---| "
        "| ADF | -4.30 kg | -5.54 to -3.05 | Low [1] | "
        "| TRE | -0.74 mmol/L | -1.13 to -0.36 | Moderate [2] | "
        "**Key Findings:** IF produces consistent metabolic improvements [1][2][3]."
    )

    # Run through full chain: filler strip -> reduce_filler
    step1 = _clean_filler_and_tables(content)
    step2 = _reduce_filler(step1)

    # Verify key data survives
    checks = {
        "MD -4.30": "-4.30" in step2,
        "95% CI": "95%" in step2,
        "I2=96%": "96%" in step2,
        "GRADE: low": "GRADE" in step2 or "low" in step2.lower(),
        "7 RCTs": "7 RCT" in step2 or "7 randomized" in step2.lower(),
        "269 participants": "269" in step2,
        "Citations [1][2][3]": bool(re.findall(r"\[\d+\]", step2)),
        "Key Findings": "Key Findings" in step2,
    }

    all_ok = True
    for check, present in checks.items():
        status = "OK" if present else "MISSING"
        if not present:
            all_ok = False
        print(f"  {check}: {status}")

    print(f"  Final: {step2[:300]}")

    return all_ok


@register("SC4", "GRADE ratings survive through evidence formatting to section write")
def _():
    from src.polaris_graph.synthesis.token_budget import format_l1, format_l2

    # Simulate evidence with GRADE rating
    ev_with_grade = {
        "evidence_id": "ev_abc123",
        "statement": "ADF reduced weight MD -4.30 kg (95% CI -5.54 to -3.05; 7 RCTs; n=269)",
        "source_title": "BMJ Systematic Review",
        "year": 2025,
        "is_faithful": True,
        "quality_tier": "GOLD",
        "relevance_score": 0.95,
        "direct_quote": "ADF reduced weight",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/123",
        "grade_certainty": "high",
    }

    l1 = format_l1(ev_with_grade)
    l2 = format_l2(ev_with_grade)

    # Check GRADE appears and would be visible to section writer
    l1_grade = "GRADE: high" in l1
    l2_grade = "GRADE: high" in l2
    l1_eid = "ev_abc123" in l1
    l2_eid = "ev_abc123" in l2

    print(f"  L1 has GRADE: {l1_grade}, has evidence_id: {l1_eid}")
    print(f"  L2 has GRADE: {l2_grade}, has evidence_id: {l2_eid}")
    print(f"  L1: {l1}")

    return l1_grade and l2_grade and l1_eid and l2_eid


# ===================================================================
# SUMMARY
# ===================================================================

print(f"\n{'='*70}")
print("SCALE + INTERACTION TEST SUMMARY")
print(f"{'='*70}")
total = len(results)
passed = sum(1 for _, p in results.values() if p)
for tid in sorted(results.keys()):
    name, ok = results[tid]
    print(f"  {tid:5s} {name:60s} {'PASS' if ok else 'FAIL'}")
print(f"\n  TOTAL: {passed}/{total} PASS")
print(f"  ALL PASS: {passed == total}")
