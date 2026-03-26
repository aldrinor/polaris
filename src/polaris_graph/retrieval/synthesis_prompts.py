"""Synthesis Prompt Constants (Fix R5-#5 + Citation Rules).

Collects all prompt injection blocks that the v2 section writer system
prompt must include. Separating these from the synthesizer code makes
them testable, reviewable, and versionable.

Usage:
    from src.polaris_graph.retrieval.synthesis_prompts import (
        PHANTOM_FIGURE_BAN,
        EVIDENCE_FIRST_RULES,
        ANALYTICAL_WRITING_RULES,
        SECTION_WRITER_SYSTEM_PROMPT,
    )
"""

from __future__ import annotations

import os

from src.polaris_graph.retrieval.citation_normalizer import CITATION_RULES  # v2 only

# ---------------------------------------------------------------------------
# FIX-CITE: v1/v3 citation rules using [CITE:evidence_id] format
# ---------------------------------------------------------------------------
# The v2 pipeline uses [SRC-NNN] with a SourceRegistry that maps NNN->URL.
# The v1/v3 pipeline uses [CITE:evidence_id] throughout (section_writer.py,
# quality gate, citation density check, expansion, hallucination audit).
# Injecting CITATION_RULES ([SRC-NNN]) into the v1/v3 prompt causes the LLM
# to use a format that no downstream component can resolve, yielding 0 citations.

CITE_EVIDENCE_RULES = """
CITATION FORMAT (MANDATORY — violations will fail quality gate):
- Cite sources inline as [CITE:evidence_id], using the exact evidence ID provided.
- For multiple sources: [CITE:ev_aaa][CITE:ev_bbb] (separate brackets).
- NEVER combine citations: [CITE:ev_aaa, ev_bbb] is FORBIDDEN.
- NEVER abbreviate or rename evidence IDs.
- NEVER use [SRC-NNN] format — use [CITE:evidence_id] ONLY.
- Every factual claim MUST have at least one [CITE:evidence_id] citation.
""".strip()

# ---------------------------------------------------------------------------
# Fix R5-#5: Phantom Figure Ban
# ---------------------------------------------------------------------------
# Evidence chunks from PDFs contain references to "Figure 4", "Table 2", etc.
# Since we killed Smart Art and don't render source images, these references
# produce phantom holes — the reader looks for Figure 4, finds nothing, and
# immediately recognizes the report as unverified AI output.

PHANTOM_FIGURE_BAN = """
FIGURE/TABLE REFERENCE RULES (MANDATORY):
- Do NOT reference external figures, charts, tables, or appendices that you cannot display.
- Transform references into inline facts:
  BAD:  "As shown in Figure 2, the removal efficiency was 99.2%"
  GOOD: "The removal efficiency was 99.2%"
  BAD:  "Table 3 summarizes the cost comparison across all sites"
  GOOD: "Cost comparison across sites showed..."
  BAD:  "See Appendix B for the full dataset"
  GOOD: (omit entirely — the reader cannot see Appendix B)
- You MAY create your own markdown tables from data if the evidence supports it.
- You MUST NOT invent data to fill a table. Only tabulate facts present in the evidence.
""".strip()


# ---------------------------------------------------------------------------
# Evidence-First Writing Rules
# ---------------------------------------------------------------------------

EVIDENCE_FIRST_RULES = """
EVIDENCE-FIRST WRITING RULES (MANDATORY):
- Every factual claim MUST be grounded in the provided evidence.
- Do NOT state facts from your training data — only from the evidence below.
- If the evidence is insufficient, say so honestly. Do NOT pad with filler.
- Filler phrases are BANNED: "It is important to note", "Furthermore",
  "In conclusion", "It should be noted that", "Interestingly".
- Write in active voice. Be direct. Be specific with numbers and units.
- If two sources disagree, present BOTH positions with citations.
""".strip()


# ---------------------------------------------------------------------------
# RC-2: Analytical Writing Rules (v3 hybrid prompt)
# ---------------------------------------------------------------------------

ANALYTICAL_WRITING_RULES = """
ANALYTICAL WRITING RULES (MANDATORY):
- You are ANALYZING evidence, not restating it. Your job is to synthesize, compare, and evaluate.
- Every factual claim MUST be grounded in the provided evidence.
- Do NOT state facts from your training data — only from the evidence below.

FIVE REQUIRED ANALYTICAL OPERATIONS:
1. AGGREGATE: When 3+ sources report similar findings, combine into one synthesized
   claim citing all sources. NEVER list source findings sequentially.
   BAD:  "Study A found 95%. Study B found 89%. Study C found 92%."
   GOOD: "Removal efficiencies ranged from 89-95% across three studies [1,2,3],
          with a median of 92%."

2. COMPARE: When evidence differs by methodology, region, timeframe, or conditions,
   create explicit comparison paragraphs. Use "whereas", "in contrast", "compared to".
   BAD:  "Method A achieved X. Method B achieved Y."
   GOOD: "Method A achieved X under conditions P, whereas Method B achieved Y under
          conditions Q — the difference likely attributable to Z [1,2]."

3. EXPLAIN: For each major finding, explain WHY — what mechanism, what implication,
   what practical significance. Do not just state what was found.

4. TABULATE: When 3+ comparable data points exist (same measurement, different
   conditions/entities), you MUST present them as a markdown table with citations
   in each row. This is NOT optional.

5. CHALLENGE: Each section MUST include at least one paragraph acknowledging
   limitations, contradictions, or gaps in the evidence base.

BANNED PATTERNS:
- Sequential source summaries ("Study A found... Study B found... Study C found...")
- Filler phrases: "It is important to note", "Furthermore", "In conclusion",
  "It should be noted that", "Interestingly"
- Writing about evidence without citing it
- Padding beyond what evidence supports
""".strip()


# ---------------------------------------------------------------------------
# Anti-Hallucination Rules
# ---------------------------------------------------------------------------

ANTI_HALLUCINATION_RULES = """
ANTI-HALLUCINATION RULES (MANDATORY):
- You may ONLY cite evidence IDs provided to you. Do NOT invent citation IDs.
- If you cannot find supporting evidence for a claim, DELETE the claim.
- Do NOT write "studies have shown" without a specific citation.
- Do NOT generalize beyond what the specific evidence states.
- Numerical values MUST match the evidence exactly — do not round or approximate.
""".strip()


# ---------------------------------------------------------------------------
# Composite system prompt for section writer
# ---------------------------------------------------------------------------

def build_section_writer_prompt(
    n_evidence: int,
    suggested_words: int,
    analytical_focus: str = "",  # RC-3: from question decomposition
) -> str:
    """Build the complete section writer system prompt.

    Combines all mandatory rules into a single, coherent system prompt.
    This is the ONE place where all prompt constraints live.

    When PG_V3_ANALYTICAL_PROMPT=1, uses ANALYTICAL_WRITING_RULES
    instead of EVIDENCE_FIRST_RULES for deeper synthesis quality.

    Args:
        n_evidence: Number of evidence pieces assigned to this section.
        suggested_words: Dynamic word target (from SectionSpec.effective_target_words).
        analytical_focus: Optional analytical focus question from RC-3
            question decomposition. Prepended to the prompt when provided.

    Returns:
        Complete system prompt string.
    """
    use_analytical = os.getenv("PG_V3_ANALYTICAL_PROMPT", "0") == "1"
    writing_rules = ANALYTICAL_WRITING_RULES if use_analytical else EVIDENCE_FIRST_RULES

    focus_block = ""
    if analytical_focus:
        focus_block = f"\nANALYTICAL FOCUS: {analytical_focus}\n"

    return f"""You are writing one section of a research report. You have {n_evidence} evidence pieces.
{focus_block}
{writing_rules}

{CITE_EVIDENCE_RULES}

{PHANTOM_FIGURE_BAN}

{ANTI_HALLUCINATION_RULES}

WORD TARGET:
- Target approximately {suggested_words} words based on available evidence.
- {n_evidence} evidence pieces support roughly {suggested_words} words of analysis.
- Do NOT pad beyond what the evidence supports. Quality over quantity.
- If evidence is thin, write a shorter, honest section rather than padding with filler.

KEY FINDINGS:
- End each section with a "**Key Findings**" subsection (3-5 bullet points).
- Each bullet must cite at least one source.
- Bullets must be specific (include numbers, units, conditions) not vague summaries."""
