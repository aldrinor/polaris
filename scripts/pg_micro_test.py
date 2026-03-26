"""
Micro test: Section writing with 3 evidence pieces.
Tests citation format consistency and output quality.
Run: python -u scripts/pg_micro_test.py
"""
import asyncio
import os
import sys
import json
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

# ---------------------------------------------------------------------------
# 3 small evidence pieces (real data from TEST_062 trace)
# ---------------------------------------------------------------------------
EVIDENCE = [
    {
        "evidence_id": "ev_aaa111",
        "statement": "Intermittent fasting significantly reduced fasting blood sugar with a standard mean difference of -0.51 (95% CI: -0.81, -0.20; p=0.001).",
        "quote": "intermittent fasting significantly reduced fasting blood sugar with a standard mean difference of −0.51",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/example1",
        "source_title": "Meta-analysis of IF on glycemic control (2024)",
        "tier": "GOLD",
        "relevance": 0.92,
        "verified": True,
    },
    {
        "evidence_id": "ev_bbb222",
        "statement": "Time-restricted eating reduced fasting glucose with a mean difference of -0.74 mmol/L (95% CI: -1.13 to -0.36).",
        "quote": "time-restricted eating significantly reduced fasting glucose with a mean difference of negative 0.74 mmol/L",
        "source_url": "https://pubmed.ncbi.nlm.nih.gov/example2",
        "source_title": "Systematic review of TRE on metabolic markers (2023)",
        "tier": "GOLD",
        "relevance": 0.88,
        "verified": True,
    },
    {
        "evidence_id": "ev_ccc333",
        "statement": "Intermittent fasting with an eating window under 8 hours was linked to a 135% higher heart disease death risk.",
        "quote": "intermittent fasting with an eating window under 8 hours was linked to a 135% higher heart disease death risk",
        "source_url": "https://newsroom.heart.org/example3",
        "source_title": "AHA epidemiological study on TRE and mortality (2024)",
        "tier": "SILVER",
        "relevance": 0.85,
        "verified": True,
    },
]

SECTION_TITLE = "Glycemic Control and Cardiovascular Risk: Contradictory Evidence"
QUERY = "What are the proven health benefits and risks of intermittent fasting based on clinical research and meta-analyses?"


def format_evidence_block(evidence: list[dict]) -> str:
    """Format evidence for the prompt, matching pipeline format."""
    lines = []
    for e in evidence:
        tier = e.get("tier", "BRONZE")
        verified = "[VERIFIED]" if e.get("verified") else "[UNVERIFIED]"
        lines.append(
            f"Evidence ID: {e['evidence_id']}\n"
            f"  Tier: {tier} {verified}\n"
            f"  Statement: {e['statement']}\n"
            f"  Quote: \"{e['quote']}\"\n"
            f"  Source: {e['source_title']}\n"
            f"  URL: {e['source_url']}\n"
        )
    return "\n".join(lines)


async def test_section_write():
    """Test section writing with the CURRENT pipeline prompt (analytical mode)."""
    from src.polaris_graph.llm.openrouter_client import OpenRouterClient

    client = OpenRouterClient()
    evidence_text = format_evidence_block(EVIDENCE)
    n_evidence = len(EVIDENCE)
    suggested_words = min(200 + n_evidence * 80, 2000)

    # ---------------------------------------------------------------------------
    # Test 1: Current analytical prompt (with conflicting CITATION_RULES)
    # ---------------------------------------------------------------------------
    print("=" * 70)
    print("TEST 1: Current analytical prompt (PG_V3_ANALYTICAL_PROMPT=1)")
    print("=" * 70)

    from src.polaris_graph.retrieval.synthesis_prompts import build_section_writer_prompt
    system_v3 = build_section_writer_prompt(
        n_evidence=n_evidence,
        suggested_words=suggested_words,
    )

    prompt = (
        f"SECTION TITLE: {SECTION_TITLE}\n"
        f"RESEARCH QUESTION: {QUERY}\n\n"
        f"EVIDENCE:\n{evidence_text}\n\n"
        f"Write this section. Every factual claim MUST include a "
        f"[CITE:evidence_id] marker referencing the specific evidence piece."
    )

    print(f"\n--- System prompt citation instructions ---")
    # Show conflicting parts
    for line in system_v3.split("\n"):
        if "CITE" in line or "SRC" in line or "citation" in line.lower():
            print(f"  {line.strip()}")

    print(f"\n--- User prompt citation instruction ---")
    print(f"  [CITE:evidence_id] marker referencing the specific evidence piece")

    print(f"\n--- Calling LLM ---")
    result = await client.generate(
        prompt=prompt,
        system=system_v3,
        max_tokens=2000,
        temperature=0.4,
    )

    content = result.content.strip()
    reasoning = (result.reasoning or "")[:1000]

    # Count citation formats
    cite_count = content.count("[CITE:")
    src_count = content.count("[SRC-")
    bracket_count = len([x for x in content.split("[") if x and x[0].isdigit()])

    print(f"\n--- Output ({len(content.split())} words) ---")
    print(content[:1500])
    if len(content) > 1500:
        print(f"... ({len(content)} chars total)")

    print(f"\n--- Citation format analysis ---")
    print(f"  [CITE:ev_xxx]: {cite_count}")
    print(f"  [SRC-NNN]:     {src_count}")
    print(f"  [N]:           {bracket_count}")

    if reasoning:
        print(f"\n--- Reasoning excerpt ({len(result.reasoning)} chars total) ---")
        print(reasoning)

    # ---------------------------------------------------------------------------
    # Test 2: Fixed prompt (CITE-only, no SRC conflict)
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("TEST 2: Fixed prompt (CITE-only, no SRC-NNN conflict)")
    print("=" * 70)

    from src.polaris_graph.synthesis.section_writer import SECTION_SYSTEM_PROMPT
    system_fixed = SECTION_SYSTEM_PROMPT.format(
        n_evidence=n_evidence,
        suggested_words=suggested_words,
    )

    result2 = await client.generate(
        prompt=prompt,
        system=system_fixed,
        max_tokens=2000,
        temperature=0.4,
    )

    content2 = result2.content.strip()
    reasoning2 = (result2.reasoning or "")[:1000]

    cite_count2 = content2.count("[CITE:")
    src_count2 = content2.count("[SRC-")
    bracket_count2 = len([x for x in content2.split("[") if x and x[0].isdigit()])

    print(f"\n--- Output ({len(content2.split())} words) ---")
    print(content2[:1500])
    if len(content2) > 1500:
        print(f"... ({len(content2)} chars total)")

    print(f"\n--- Citation format analysis ---")
    print(f"  [CITE:ev_xxx]: {cite_count2}")
    print(f"  [SRC-NNN]:     {src_count2}")
    print(f"  [N]:           {bracket_count2}")

    if reasoning2:
        print(f"\n--- Reasoning excerpt ({len(result2.reasoning)} chars total) ---")
        print(reasoning2)

    # ---------------------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Test 1 (analytical+CITATION_RULES): CITE={cite_count}, SRC={src_count}, [N]={bracket_count}")
    print(f"Test 2 (SECTION_SYSTEM_PROMPT):     CITE={cite_count2}, SRC={src_count2}, [N]={bracket_count2}")

    t1_ok = cite_count > 0 and src_count == 0
    t2_ok = cite_count2 > 0 and src_count2 == 0
    print(f"\nTest 1 PASS: {t1_ok}")
    print(f"Test 2 PASS: {t2_ok}")

    cost = client.cost_ledger.to_dict()
    print(f"\nCost: ${cost.get('total_cost_usd', 0):.4f}")


if __name__ == "__main__":
    asyncio.run(test_section_write())
