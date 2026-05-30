"""Verified-only extractive executive summary (I-meta-002-q1d #949 part b).

Frontier DR reports lead with a key-findings-up-front summary; POLARIS opened cold into Efficacy. This
builds a "Key Findings" block by EXTRACTING the first verified sentence (verbatim, with its `[N]` citation)
from each verified section. It is PURELY EXTRACTIVE — it copies sentences that already survived strict_verify
and introduces ZERO new claims, no LLM call, no spend. Empty input → "" (no empty heading).
"""

from __future__ import annotations

import os
import re
from typing import Any

# One sentence = minimal run up to end punctuation, PLUS any trailing `[N]` citation marker(s), where the
# end punctuation must be a real sentence boundary: followed by whitespace+capital/bracket/digit OR end of
# text. The boundary lookahead prevents stopping inside a decimal ("2.1" — the period is followed by a digit,
# no whitespace, so it is not a boundary). Matching (not splitting) keeps trailing-citation forms (`claim.
# [1]` AND `claim [1].`) attached to the sentence — re.split would consume the trailing `[N]` (Codex
# diff-gate iter-1 P2).
_SENTENCE_RE = re.compile(r".+?[.!?](?:\s*\[\d+\])*(?=\s+[A-Z(\[\d]|\s*$)", re.DOTALL)

_OFF_VALUES = frozenset({"0", "false", "no", "off", ""})

# How many leading verified sentences to lift from each section (default 1 — the headline finding).
_SENTENCES_PER_SECTION = 1
# Hard cap on total bullets so the summary stays a summary.
_MAX_BULLETS = 6


def key_findings_enabled() -> bool:
    """Default ON. `PG_SWEEP_KEY_FINDINGS=0` ships the report without the exec-summary block (cold-open)."""
    return os.getenv("PG_SWEEP_KEY_FINDINGS", "1").strip().lower() not in _OFF_VALUES


def _first_verified_sentences(verified_text: str, n: int) -> list[str]:
    matches = [m.group(0).strip() for m in _SENTENCE_RE.finditer(verified_text or "")]
    return [s for s in matches if s][:n]


def build_key_findings(sections: list[Any]) -> str:
    """Return a markdown "## Key Findings" block: the first verified sentence (verbatim, citation intact)
    from each non-dropped section with verified_text. Verified-only + extractive — never a new claim.
    Returns "" when disabled or when no section has verified prose (no empty heading)."""
    if not key_findings_enabled():
        return ""
    bullets: list[str] = []
    for sr in sections or []:
        if getattr(sr, "dropped_due_to_failure", False):
            continue
        verified_text = getattr(sr, "verified_text", "") or ""
        if not verified_text.strip():
            continue
        title = getattr(sr, "title", "") or ""
        for sentence in _first_verified_sentences(verified_text, _SENTENCES_PER_SECTION):
            label = f"**{title}.** " if title else ""
            bullets.append(f"- {label}{sentence}")
            if len(bullets) >= _MAX_BULLETS:
                break
        if len(bullets) >= _MAX_BULLETS:
            break
    if not bullets:
        return ""
    header = (
        "## Key Findings\n\n"
        "_Each finding below is a verbatim, span-verified statement carried up from the body section "
        "named in bold; citations are the body's._\n\n"
    )
    return header + "\n".join(bullets) + "\n\n"
