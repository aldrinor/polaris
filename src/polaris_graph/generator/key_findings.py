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

# A Key Finding is a SPAN-VERIFIED statement — by definition it carries its `[N]` / `[#ev:`
# citation (module docstring). This is the robust per-SENTENCE gap filter (I-gen-006 #1178
# C07/P07): a gap-disclosure sentence ("... did not survive strict verification; curator-
# actionable gap.") carries NO citation, so in a MIXED V30 section (a leading gap slot +
# later verified prose, where the SECTION still has sentences_verified>0) the uncited gap
# sentence is skipped and the first CITED sentence is lifted instead. Keys on the citation
# invariant, never on matching gap-disclosure text.
_CITATION_RE = re.compile(r"\[\d+\]|\[#ev:")

# Gap-disclosure boilerplate (I-gen-006 #1178 C07/P07, Codex iter-5): the V30 contract-runner
# gap disclosure is a FIXED two-sentence template — "Contract-bound content ... curator-actionable
# gap. See manifest.frame_coverage_report and human_gap_tasks.json for per-entity detail.[N]" — and
# its SECOND sentence DOES carry a `[N]` (a pointer to the gap-task sidecar, NOT an evidence span),
# so the citation filter alone cannot exclude it. A Key Finding must be a span-verified CLAIM, never
# a gap pointer; exclude any sentence carrying a canonical gap-disclosure marker. Robust because the
# disclosure text is generated from fixed constants (contract_section_runner / _GAP_STUB_SENTENCE),
# never free-form prose — this is a rendering filter, not a §-1.1 quality-by-pattern judgement.
_GAP_MARKER_RE = re.compile(
    r"curator-actionable gap|did not survive strict verification|"
    r"did not survive (?:4-role )?verification|frame_coverage_report|human_gap_tasks",
    re.IGNORECASE,
)

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
    # A Key Finding is a span-verified CLAIM: it must carry a citation AND must NOT be
    # gap-disclosure boilerplate (whose 2nd sentence is cited to the gap-task sidecar, not
    # an evidence span). Both filters together exclude every gap shape in a mixed section
    # (I-gen-006 #1178 C07/P07, Codex iter-5).
    return [
        s for s in matches
        if s and _CITATION_RE.search(s) and not _GAP_MARKER_RE.search(s)
    ][:n]


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
        # I-gen-006 (#1178) BB5-C07/P07: a 0-verified gap DISCLOSURE renders disclosure
        # text in verified_text (the legacy is_gap_stub or a V30 contract gap) but is NOT
        # span-verified prose — it must never surface as a Key-Findings "span-verified
        # statement". Skip every gap disclosure (universal signal: sentences_verified == 0).
        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
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
