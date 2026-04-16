"""Render PRODUCTION verifier and section-writer prompts against real PG_TEST_091
evidence, save to disk so a sub-agent (acting as the LLM) can be dispatched
manually. After the sub-agent returns its response, run the validator at the
bottom of this script to parse and score the output.

This catches:
  - Prompt regressions (prompt no longer elicits parseable JSON / proper citations)
  - Schema regressions (Pydantic coercion broken)
  - CoT leakage from the prompt structure (not from the model — the model is
    Claude here, not GLM, so behavioral fidelity is limited)

This does NOT catch:
  - GLM-5.1-specific behaviors
  - Async/timing/network paths
  - Wave 3 gate logic (offline stress already covers that)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.chdir(PROJECT_ROOT)

OUT_DIR = PROJECT_ROOT / "tests" / "fixtures" / "subagent_prompts"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_fixture():
    with open("outputs/polaris_graph/PG_TEST_091.json", encoding="utf-8") as f:
        return json.load(f)


def render_verifier_prompt(evidence_subset: list[dict], research_query: str) -> tuple[str, str]:
    """Build verifier prompt the same way verifier.py:_verify_batch does."""
    from src.polaris_graph.agents.verifier import VERIFICATION_SYSTEM

    claims_text = []
    for i, ev in enumerate(evidence_subset, 1):
        quote = ev.get("direct_quote", "")
        quote_line = (
            f'  Direct quote: "{quote[:300]}"'
            if quote
            else "  Direct quote: (not available)"
        )
        # No url_content_map in this test → has_content=False → uses fallback instruction
        claims_text.append(
            f"Claim {i}: {ev.get('statement', '')}\n"
            f"  Source: {ev.get('source_title', '')} ({ev.get('source_url', '')})\n"
            f"{quote_line}\n"
            f"  Fact category: {ev.get('fact_category', '')}\n"
        )

    verify_instruction = (
        "For each claim, assess whether it is plausibly supported by the cited source. "
        "If no direct quote is available, use the source title and URL as context."
    )
    query_context = f"\nResearch question: {research_query}\n" if research_query else ""

    user = f"""Verify each of the following {len(evidence_subset)} claims.
Each claim was extracted from its cited source by an AI system.
{query_context}
{chr(10).join(claims_text)}

{verify_instruction}"""

    return VERIFICATION_SYSTEM, user


def render_section_writer_prompt(
    section_evidence: list[dict],
    section_title: str,
    section_description: str,
    query: str,
    report_title: str,
) -> tuple[str, str]:
    """Build section-writer prompt the same way section_writer.py:write_section does."""
    from src.polaris_graph.synthesis.section_writer import SECTION_SYSTEM_PROMPT

    n_evidence = len(section_evidence)
    suggested_words = min(200 + n_evidence * 80, 2000)
    system = SECTION_SYSTEM_PROMPT.format(
        n_evidence=n_evidence,
        suggested_words=suggested_words,
    )

    # Evidence text block (matches section_writer.py rendering)
    evidence_lines = []
    for ev in section_evidence:
        eid = ev.get("evidence_id", "ev_unknown")
        tier = ev.get("quality_tier", "BRONZE")
        is_faithful = ev.get("is_faithful", True)
        verified_marker = "[VERIFIED]" if is_faithful else "[UNVERIFIED]"
        statement = ev.get("statement", "")
        quote = ev.get("direct_quote", "")
        source = ev.get("source_title", "")[:80]
        evidence_lines.append(
            f"[{eid}] [{tier}] {verified_marker}\n"
            f"  Statement: {statement}\n"
            f"  Direct quote: \"{quote[:200]}\"\n"
            f"  Source: {source}"
        )
    evidence_text = "\n\n".join(evidence_lines)

    user = f"""Report title: {report_title}

Section: {section_title}
Section description: {section_description}
Research question: {query}

Available evidence for this section:
{evidence_text}

CRITICAL: This section must directly contribute to answering the research question: {query[:200]}. Every paragraph should connect its findings back to this question.

Write this section. If this is not the first section, begin with a 1-sentence bridge that connects to the previous section's topic. Then proceed with unique analysis. Connect findings to the broader report structure.
Every factual claim MUST include a [CITE:evidence_id] marker referencing the specific evidence piece.
Cite the evidence pieces that directly support your analysis. Prioritize GOLD and SILVER tier evidence. You do NOT need to cite every piece -- quality of argument is more important than exhaustive citation. Omit evidence that would weaken the narrative by being tangential or repetitive.
CITATION DIVERSITY: Do NOT cite the same source more than 3 times in this section. Spread citations across different sources to strengthen the argument with independent corroboration. You MUST cite at least 2 unique sources in this section. If cross-section evidence is provided, use it when relevant but do NOT repeat information covered in adjacent sections.
CROSS-REFERENCES: When referencing other sections of this report, always use the format 'as discussed in [Section Title]' with the exact section title. Never use section numbers (e.g., 'Section 4') and never use colons (e.g., 'discussed in: Limitations').

Target: approximately {min(200 + n_evidence * 80, 2000)} words."""

    return system, user


def main():
    data = load_fixture()
    evidence = data.get("evidence", [])
    research_query = data.get("research_query") or data.get("query") or "intermittent fasting effects on type 2 diabetes"

    print(f"Loaded PG_TEST_091: {len(evidence)} evidence")
    print(f"Research query: {research_query[:80]}")

    # ---- Verifier prompt: pick 4 evidence pieces with direct quotes ----
    # Mix of perspectives if possible
    verifier_pool = [
        e for e in evidence
        if e.get("direct_quote") and e.get("statement") and e.get("source_url")
    ]
    # Pick 4: 2 strong (clear quote-supports-statement), 1 borderline (statement
    # extends beyond quote), 1 with quote that has no statement support
    ver_picks = [verifier_pool[0], verifier_pool[10], verifier_pool[50], verifier_pool[100]]

    sys_ver, user_ver = render_verifier_prompt(ver_picks, research_query)
    (OUT_DIR / "verifier_system.txt").write_text(sys_ver, encoding="utf-8")
    (OUT_DIR / "verifier_user.txt").write_text(user_ver, encoding="utf-8")

    # Save the picks for later validation
    with open(OUT_DIR / "verifier_inputs.json", "w", encoding="utf-8") as f:
        json.dump([
            {
                "evidence_id": e.get("evidence_id"),
                "statement": e.get("statement"),
                "direct_quote": e.get("direct_quote"),
                "source_title": e.get("source_title"),
                "source_url": e.get("source_url"),
                "stored_is_faithful": e.get("is_faithful"),
                "stored_verdict": "SUPPORTED" if e.get("is_faithful") else "NOT_SUPPORTED",
            }
            for e in ver_picks
        ], f, indent=2)

    print(f"\n[VERIFIER] {len(ver_picks)} claims, system={len(sys_ver)} chars, user={len(user_ver)} chars")
    print(f"  saved: {OUT_DIR / 'verifier_system.txt'}")
    print(f"  saved: {OUT_DIR / 'verifier_user.txt'}")
    print(f"  saved: {OUT_DIR / 'verifier_inputs.json'}")

    # ---- Section-writer prompt: pick a coherent ~10-piece subset ----
    # Group by perspective and pick the dominant one
    from collections import Counter
    persp_counts = Counter(e.get("perspective", "Unknown") for e in evidence)
    dominant = persp_counts.most_common(1)[0][0]
    sec_pool = [e for e in evidence if e.get("perspective") == dominant]
    # Take 10 with direct_quote and high-quality tiers
    sec_pool_quality = sorted(
        [e for e in sec_pool if e.get("direct_quote") and e.get("statement")],
        key=lambda e: 0 if e.get("quality_tier") == "GOLD" else 1,
    )
    sec_picks = sec_pool_quality[:10]

    sys_sec, user_sec = render_section_writer_prompt(
        sec_picks,
        section_title="Mechanisms and Metabolic Effects of Intermittent Fasting",
        section_description="Examines the physiological mechanisms by which intermittent fasting affects metabolic parameters including HOMA-IR, glycemic control, and lipid profiles. Discusses safety findings across studies.",
        query=research_query,
        report_title="The Effects of Intermittent Fasting on Type 2 Diabetes Mellitus",
    )
    (OUT_DIR / "section_writer_system.txt").write_text(sys_sec, encoding="utf-8")
    (OUT_DIR / "section_writer_user.txt").write_text(user_sec, encoding="utf-8")

    with open(OUT_DIR / "section_writer_inputs.json", "w", encoding="utf-8") as f:
        json.dump([
            {
                "evidence_id": e.get("evidence_id"),
                "statement": e.get("statement"),
                "source_title": e.get("source_title"),
                "perspective": e.get("perspective"),
                "quality_tier": e.get("quality_tier"),
            }
            for e in sec_picks
        ], f, indent=2)

    print(f"\n[SECTION_WRITER] {len(sec_picks)} evidence (perspective={dominant}), system={len(sys_sec)} chars, user={len(user_sec)} chars")
    print(f"  saved: {OUT_DIR / 'section_writer_system.txt'}")
    print(f"  saved: {OUT_DIR / 'section_writer_user.txt'}")
    print(f"  saved: {OUT_DIR / 'section_writer_inputs.json'}")
    print(f"  unique sources: {len(set(e.get('source_title') for e in sec_picks))}")

    print("\n=== DISPATCH INSTRUCTIONS ===")
    print("1. Spawn a sub-agent with verifier_system + verifier_user → expect VerificationBatch JSON")
    print("2. Spawn a sub-agent with section_writer_system + section_writer_user → expect prose with [CITE:...] markers")
    print("3. Save sub-agent responses to:")
    print(f"   {OUT_DIR / 'verifier_response.json'}")
    print(f"   {OUT_DIR / 'section_writer_response.txt'}")
    print("4. Run: python scripts/pg_subagent_validate.py")


if __name__ == "__main__":
    main()
