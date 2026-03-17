"""Citation Normalizer (v2 Layer 3).

Handles the compound citation rebellion: LLMs inevitably write
"[SRC-001, SRC-002]" instead of "[SRC-001][SRC-002]", or even
"[SRC-001, 002]". This module:

1. Provides the CITATION_RULES prompt block for the section writer system prompt
2. Provides normalize_citations() to split/fix compound citations post-generation
3. Provides resolve_to_numbers() to remap [SRC-NNN] -> [1], [2], [3] in assembly

Fix R3-#3: Without this, compound brackets like [SRC-001, SRC-002] are invisible
to a simple regex like \\[SRC-\\d+\\], and those sources become permanently
orphaned from the bibliography.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("polaris_graph")


# ---------------------------------------------------------------------------
# Prompt injection block (for section writer system prompt)
# ---------------------------------------------------------------------------

CITATION_RULES = """
CITATION FORMAT (MANDATORY — violations will fail quality gate):
- Cite sources inline as [SRC-001], [SRC-002], etc.
- For multiple sources: [SRC-001][SRC-002][SRC-003] (separate brackets).
- NEVER combine citations: [SRC-001, SRC-002] is FORBIDDEN.
- NEVER abbreviate: [SRC-001, 002] is FORBIDDEN.
- NEVER use parentheses: (SRC-001) is FORBIDDEN.
- Every factual claim MUST have at least one [SRC-NNN] citation.
""".strip()


# ---------------------------------------------------------------------------
# Post-generation normalization
# ---------------------------------------------------------------------------

# Pattern: [SRC-001, SRC-002, ...] or [SRC-001, 002, ...]
_COMPOUND_RE = re.compile(
    r"\["                          # opening bracket
    r"(SRC-\d{3}"                  # first full SRC-NNN
    r"(?:\s*[,;]\s*"               # comma or semicolon separator
    r"(?:SRC-)?\d{3})+)"           # subsequent SRC-NNN or bare NNN
    r"\]",                         # closing bracket
)

# Pattern: (SRC-001) with parentheses instead of brackets
_PAREN_RE = re.compile(r"\((SRC-\d{3})\)")

# Pattern: bare SRC-NNN without brackets
_BARE_RE = re.compile(r"(?<!\[)(SRC-\d{3})(?!\])")


def normalize_citations(text: str) -> str:
    """Split compound citations and fix formatting.

    Transforms:
        [SRC-001, SRC-002]      -> [SRC-001][SRC-002]
        [SRC-001, 002, 003]     -> [SRC-001][SRC-002][SRC-003]
        [SRC-001; SRC-002]      -> [SRC-001][SRC-002]
        (SRC-001)               -> [SRC-001]
        bare SRC-001 in text    -> [SRC-001]
        [SRC-001][SRC-001]      -> [SRC-001]  (adjacent dedup)
    """
    # Step 1: Split compound brackets
    def _split_compound(match: re.Match) -> str:
        inner = match.group(1)
        # Extract all NNN values
        parts = re.split(r"\s*[,;]\s*", inner)
        ids: list[str] = []
        last_prefix = ""
        for part in parts:
            part = part.strip()
            if part.startswith("SRC-"):
                ids.append(part)
                last_prefix = part[:4]  # "SRC-"
            elif re.match(r"^\d{3}$", part) and last_prefix:
                ids.append(f"SRC-{part}")
        return "".join(f"[{sid}]" for sid in ids)

    text = _COMPOUND_RE.sub(_split_compound, text)

    # Step 2: Fix parenthesized citations
    text = _PAREN_RE.sub(r"[\1]", text)

    # Step 3: Fix bare SRC-NNN (no brackets)
    text = _BARE_RE.sub(r"[\1]", text)

    # Step 4: Deduplicate adjacent identical citations [SRC-001][SRC-001] -> [SRC-001]
    text = re.sub(r"(\[SRC-\d{3}\])(?:\1)+", r"\1", text)

    return text


# ---------------------------------------------------------------------------
# Assembly: SRC-NNN -> [1], [2], [3]
# ---------------------------------------------------------------------------

def resolve_to_numbers(
    text: str,
    citation_map: dict[str, int],
) -> str:
    """Replace [SRC-NNN] with sequential citation numbers [1], [2], etc.

    Args:
        text: Report text with [SRC-NNN] markers.
        citation_map: Mapping from SRC-NNN -> citation number.
                      Obtain from SourceRegistry.to_citation_map().

    Returns:
        Text with [SRC-NNN] replaced by [N].
    """
    # First normalize any compound citations that slipped through
    text = normalize_citations(text)

    def _replace(match: re.Match) -> str:
        src_id = match.group(1)
        num = citation_map.get(src_id)
        if num is not None:
            return f"[{num}]"
        logger.warning("Orphaned citation: [%s] not in registry", src_id)
        return match.group(0)  # leave as-is for debugging

    return re.sub(r"\[(SRC-\d{3})\]", _replace, text)


# ---------------------------------------------------------------------------
# Validation: count citation coverage
# ---------------------------------------------------------------------------

def citation_stats(text: str) -> dict[str, int]:
    """Count citation markers in text for quality gate.

    Returns dict with:
        total_citations: number of [SRC-NNN] markers
        unique_sources: number of distinct SRC-NNN IDs
        uncited_paragraphs: paragraphs with 0 citations
        compound_violations: remaining compound brackets (should be 0)
    """
    all_cites = re.findall(r"\[SRC-(\d{3})\]", text)
    compound = len(_COMPOUND_RE.findall(text))

    paragraphs = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 50]
    uncited = sum(1 for p in paragraphs if "[SRC-" not in p)

    return {
        "total_citations": len(all_cites),
        "unique_sources": len(set(all_cites)),
        "uncited_paragraphs": uncited,
        "total_paragraphs": len(paragraphs),
        "compound_violations": compound,
    }
