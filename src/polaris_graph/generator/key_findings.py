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

# An ATX markdown header: 1-6 '#' followed by whitespace ("### Section"). Used to detect a
# leaked section header WITHOUT mis-classifying hash-leading prose like "#1 ranked" (Codex P2).
_ATX_HEADER_RE = re.compile(r"#{1,6}\s")

_OFF_VALUES = frozenset({"0", "false", "no", "off", ""})

# How many leading verified sentences to lift from each section (default 1 — the headline finding).
_SENTENCES_PER_SECTION = 1
# Hard cap on total bullets so the summary stays a summary.
_MAX_BULLETS = 6


def key_findings_enabled() -> bool:
    """Default ON. `PG_SWEEP_KEY_FINDINGS=0` ships the report without the exec-summary block (cold-open)."""
    return os.getenv("PG_SWEEP_KEY_FINDINGS", "1").strip().lower() not in _OFF_VALUES


def _strip_leading_markdown_headers(text: str) -> str:
    """Drop leading markdown header lines (and blanks) from a section's verified_text
    (I-perm-008 #1202). A section header that leaked into ``verified_text`` (e.g.
    "### Pathogenic bacteria...") would otherwise be lifted AS the headline finding via the
    DOTALL sentence regex, producing a "- **Section.** ### <header> ..." bullet that breaks the
    Key-Findings block boundary. Stripping leading headers makes the lift a clean prose sentence."""
    lines = (text or "").split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or _ATX_HEADER_RE.match(lines[i].lstrip())):
        i += 1
    return "\n".join(lines[i:])


def _first_verified_sentences(verified_text: str, n: int) -> list[str]:
    matches = [m.group(0).strip() for m in _SENTENCE_RE.finditer(verified_text or "")]
    # A Key Finding is a span-verified CLAIM: it must carry a citation, must NOT be
    # gap-disclosure boilerplate (whose 2nd sentence is cited to the gap-task sidecar, not
    # an evidence span), and must NOT be a markdown header line (I-perm-008 — a leaked "###"
    # header is never a finding). The filters together exclude every gap/header shape in a
    # mixed section (I-gen-006 #1178 C07/P07, Codex iter-5).
    return [
        s for s in matches
        if s
        and not _ATX_HEADER_RE.match(s.lstrip())
        and _CITATION_RE.search(s)
        and not _GAP_MARKER_RE.search(s)
    ][:n]


def refilter_key_findings_block(report_text: str) -> str:
    """Drop Key-Findings bullets that became a redaction STUB after the four-role seam
    (I-perm-008 #1202, blueprint R7).

    ``build_key_findings`` is assembled PRE-four-role on strict_verify-passed prose, so a lifted
    headline finding the four-role seam later marks non-VERIFIED is redacted in report.md into a
    "- **Section.** <gap stub>" pseudo-finding. The redactor runs AFTER Key Findings is built, so
    it cannot prevent the stub bullet; this post-redaction pass removes any KF bullet whose body
    now matches the gap-disclosure boilerplate (``_GAP_MARKER_RE``). With the leaked-header strip
    in ``build_key_findings`` each bullet is a clean single line, so a line-scoped drop is exact.
    If no genuine finding remains, the whole block is dropped (no empty heading). Idempotent +
    byte-identical when no KF bullet was redacted.
    """
    if not key_findings_enabled():
        return report_text
    header_match = re.search(r"(?m)^##\s*Key Findings\s*$", report_text)
    if not header_match:
        return report_text
    block_start = header_match.start()
    rest = report_text[header_match.end():]
    next_header = re.search(r"(?m)^#{1,6}\s", rest)
    block_end = header_match.end() + (next_header.start() if next_header else len(rest))

    kept_lines: list[str] = []
    dropped_any = False
    for line in report_text[block_start:block_end].splitlines():
        # Within the bounded KF block, ANY gap-disclosure line is a redacted finding — the real
        # `reconcile_report_against_verdicts` replaces the WHOLE bullet (including the
        # "- **Section.**" prefix) with a BARE stub line, so a `- `-prefix check misses it
        # (Codex iter-1 P1). The block's only other lines are the heading + the italic preamble,
        # neither of which matches `_GAP_MARKER_RE`, so this never drops a legitimate line.
        if _GAP_MARKER_RE.search(line):
            dropped_any = True
            continue
        kept_lines.append(line)
    if not dropped_any:
        return report_text  # byte-identical when nothing was a stub
    new_block = "\n".join(kept_lines)
    if not re.search(r"(?m)^\s*-\s+\S", new_block):
        trimmed = report_text[:block_start] + report_text[block_end:]
        return re.sub(r"^\n+", "", trimmed) if block_start == 0 else trimmed
    if not new_block.endswith("\n"):
        new_block += "\n"
    return report_text[:block_start] + new_block + report_text[block_end:]


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
        # I-perm-008: strip any leaked leading section header so it is never lifted as the
        # headline finding (a "### ..." header would otherwise break the KF block boundary).
        verified_text = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
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
