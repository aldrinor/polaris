"""Abstract / executive-summary (front) + Conclusion (end) synthesis layer, drafted LAST
from the ALREADY-strict_verify-PASSED body (I-arch-011 PR-d #1268).

This is the LAST composition step (composition_design_plan §THE FLOW step 4): it runs AFTER
the verified body (``SectionResult.verified_text``) is assembled, and draws ONLY from already-
verified body sentences — NEVER from ``evidence_pool`` / the raw corpus.

FAITHFULNESS CONTRACT (clinical-lethal). Every abstract/conclusion sentence is a VERBATIM
RE-PRESENTATION of an already-verified body sentence (carrying the body's own ``[N]`` citation).
It is faithful BY IDENTITY: it is byte-equal to a sentence that already passed ``strict_verify``
in the body (the proven Key-Findings extractive contract). Because it carries the body sentence's
exact prose, the post-gate ``reconcile_report_against_verdicts`` redactor removes the abstract/
conclusion copy in the SAME multi-occurrence loop it redacts the body copy if the 4-role seam flips
the claim to non-VERIFIED (no orphan, no fail-closed abort). Empty verified body -> a disclosed
"insufficient verified evidence" line, NEVER fabricated filler (§-1.3).

WHY VERBATIM-ONLY (cross-claim author-summary synthesis was DESIGNED then CUT, 2026-06-18):
The brief's P1 required that a LABELED author-summary which "reuses the body's entities+numbers but
asserts a NEW relation/comparative/causal/safety conclusion" be REJECTED by a DETERMINISTIC gate
(no new hot-path judge). A first build added a ``check_claim_atom_grounding`` bag-of-atoms gate, but
the PR-d replay harness proved it UNSOUND for exactly that class: a recombination of the body's own
atoms ("X causes Y" when the body separately contains X, Y, and the word "causes") has every atom
present BY CONSTRUCTION, so presence-checking can never reject it. Catching atom-RECOMBINATION
requires entailment of the synthesis sentence against the SPECIFIC cited claim — a judge call the
brief told us to keep off the hot path, and a larger build than PR-d. Rather than ship a green
harness over a gate that cannot do its job (a future landmine: a later engineer enables the labeled-
synthesis path trusting the gate, and recombination fabrications ship), PR-d ships the safe subset
that already renders — verbatim re-presentation, faithful by identity — and the unsound synthesis
machinery is REMOVED. Any future labeled-synthesis feature must build the entailment gate first.

Adds NO new model/slug/resolver and NO new hot-path LLM judge; the render is purely DETERMINISTIC
(no spend). Does NOT modify ``strict_verify`` nor any I-arch-010 tail code.
"""

from __future__ import annotations

import os
import re
from typing import Any

# key_findings is the SIBLING extractive-summary module (same generator family). PR-d reuses its
# PROVEN faithfulness filters so a gap-disclosure / leaked-header line is never lifted as a finding,
# and its sentence-match regex (which keeps a trailing ``[N]`` attached to its sentence). These are
# the same primitives the existing Key-Findings front block ships on — deliberate shared coupling,
# not incidental: PR-d is the draft-last sibling of Key Findings.
from src.polaris_graph.generator.key_findings import (
    _CITATION_RE,
    _GAP_MARKER_RE,
    _SENTENCE_RE,
    _first_verified_sentences,
    _strip_leading_markdown_headers,
)

_OFF_VALUES = frozenset({"0", "false", "no", "off", ""})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

# Default-OFF master flag. Flag-OFF -> build_abstract()/build_conclusion() return "" so the
# report.md ARTIFACT is BYTE-IDENTICAL to the pre-PR-d stack. Gate-B / the run slate activates it.
_ENABLED_ENV = "PG_SYNTHESIS_ABSTRACT_CONCLUSION"

# How many leading verified sentences to lift per section into the abstract (headline finding).
_ABSTRACT_SENTENCES_PER_SECTION = 1
# Hard cap so the abstract stays a summary (mirrors key_findings _MAX_BULLETS posture).
_ABSTRACT_MAX_SENTENCES = 6
# How many trailing/most-significant verified sentences the conclusion re-presents.
_CONCLUSION_MAX_SENTENCES = 5

# Disclosed "no verified evidence" line (NEVER fabricated filler — §-1.3).
_INSUFFICIENT_EVIDENCE = (
    "No claim in this report survived span/numeric/entailment verification against its "
    "cited source; there is insufficient verified evidence to summarize."
)


def synthesis_abstract_conclusion_enabled() -> bool:
    """Default OFF. Set ``PG_SYNTHESIS_ABSTRACT_CONCLUSION=1`` to render the abstract + conclusion."""
    return os.getenv(_ENABLED_ENV, "0").strip().lower() in _TRUE_VALUES


# ─────────────────────────────────────────────────────────────────────────────
# Verified-body sentence harvesting (VERBATIM re-presentation — the only render path)
# ─────────────────────────────────────────────────────────────────────────────
def _section_is_verified(sr: Any) -> bool:
    """A section contributes verified prose iff it is not dropped, not a gap stub, and has
    at least one verified sentence (the SAME skip contract Key Findings uses)."""
    if getattr(sr, "dropped_due_to_failure", False):
        return False
    if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
        return False
    return bool((getattr(sr, "verified_text", "") or "").strip())


def _verified_sentences_in_order(verified_text: str) -> list[str]:
    """Every span-verified (cited, non-gap, non-header) sentence in a section's verified_text,
    in document order. Reuses the proven key_findings filters so a gap-disclosure / leaked-header
    line is never lifted as a finding."""
    text = _strip_leading_markdown_headers(verified_text or "")
    # _first_verified_sentences applies the citation/gap/header filters; ask for a high cap so we
    # get ALL verified sentences in order (the abstract/conclusion select among them deterministically).
    return _first_verified_sentences(text, 10_000)


def _harvest_abstract_sentences(sections: list[Any]) -> list[str]:
    """The abstract leads with each section's HEADLINE verified finding (its first verified
    sentence), verbatim with its citation, capped. Pure re-presentation — zero new claims."""
    out: list[str] = []
    for sr in sections or []:
        if not _section_is_verified(sr):
            continue
        verified_text = getattr(sr, "verified_text", "") or ""
        for sentence in _first_verified_sentences(
            _strip_leading_markdown_headers(verified_text),
            _ABSTRACT_SENTENCES_PER_SECTION,
        ):
            out.append(sentence)
            if len(out) >= _ABSTRACT_MAX_SENTENCES:
                return out
    return out


def _harvest_conclusion_sentences(sections: list[Any]) -> list[str]:
    """The conclusion re-presents the CLOSING verified finding of each section (its last verified
    sentence), verbatim with its citation, capped. Pure re-presentation — zero new claims. Falls
    back to the first verified sentence if a section has only one (so a single-finding section is
    still represented), de-duplicating against what was already chosen."""
    out: list[str] = []
    seen: set[str] = set()
    for sr in sections or []:
        if not _section_is_verified(sr):
            continue
        ordered = _verified_sentences_in_order(getattr(sr, "verified_text", "") or "")
        if not ordered:
            continue
        sentence = ordered[-1]
        if sentence in seen:
            continue
        seen.add(sentence)
        out.append(sentence)
        if len(out) >= _CONCLUSION_MAX_SENTENCES:
            break
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Block builders (front abstract + end conclusion)
# ─────────────────────────────────────────────────────────────────────────────
_ABSTRACT_HEADER = (
    "## Abstract\n\n"
    "_Each sentence below is a verbatim, span-verified statement carried up from the body; "
    "citations are the body's. This summary introduces no new claim._\n\n"
)
_CONCLUSION_HEADER = (
    "## Conclusion\n\n"
    "_Each sentence below is a verbatim, span-verified statement from the body; citations are "
    "the body's. This conclusion introduces no new claim._\n\n"
)


def build_abstract(sections: list[Any]) -> str:
    """Return a markdown ``## Abstract`` block: verbatim, span-verified headline findings carried
    up from the body, drafted LAST. Returns "" when disabled (flag-OFF byte-identity). When the
    body has NO verified prose, renders the disclosed insufficient-evidence line (NEVER empty
    fabricated filler)."""
    if not synthesis_abstract_conclusion_enabled():
        return ""
    sentences = _harvest_abstract_sentences(sections)
    if not sentences:
        return _ABSTRACT_HEADER + _INSUFFICIENT_EVIDENCE + "\n\n"
    return _ABSTRACT_HEADER + " ".join(sentences) + "\n\n"


def build_conclusion(sections: list[Any]) -> str:
    """Return a markdown ``## Conclusion`` block: verbatim, span-verified closing findings carried
    up from the body, drafted LAST. Returns "" when disabled (flag-OFF byte-identity). When the
    body has NO verified prose, renders the disclosed insufficient-evidence line (NEVER empty
    fabricated filler)."""
    if not synthesis_abstract_conclusion_enabled():
        return ""
    sentences = _harvest_conclusion_sentences(sections)
    if not sentences:
        return _CONCLUSION_HEADER + _INSUFFICIENT_EVIDENCE + "\n\n"
    return _CONCLUSION_HEADER + " ".join(sentences) + "\n\n"


# ─────────────────────────────────────────────────────────────────────────────
# Post-redaction refilter (the duplicate-claim landmine, brief P2-2)
# ─────────────────────────────────────────────────────────────────────────────
_ABSTRACT_CONCLUSION_HEADER_RE = re.compile(r"(?m)^##\s*(?:Abstract|Conclusion)\s*$")


def refilter_abstract_conclusion_block(report_text: str) -> str:
    """Drop Abstract / Conclusion sentences that became a redaction GAP STUB after the four-role
    seam, and remove a block left with no real finding (no empty heading) — the exact analog of
    ``key_findings.refilter_key_findings_block``.

    The abstract/conclusion sentences are VERBATIM re-presentations of body claims, so the
    multi-occurrence ``reconcile_report_against_verdicts`` loop already redacts the abstract/
    conclusion copy of a non-VERIFIED claim into the gap-replacement text in the SAME pass it
    redacts the body copy (no orphan). This pass then tidies the block: it removes the
    gap-replacement sentence(s) the redactor wrote into the abstract/conclusion summary line and,
    if a block has no verified sentence left, drops the whole block (heading + preamble). Idempotent
    + byte-identical when nothing in a block was redacted.
    """
    if not synthesis_abstract_conclusion_enabled():
        return report_text
    out = report_text
    for header_re in (
        re.compile(r"(?m)^##\s*Abstract\s*$"),
        re.compile(r"(?m)^##\s*Conclusion\s*$"),
    ):
        out = _refilter_one_block(out, header_re)
    return out


def _refilter_one_block(report_text: str, header_re: re.Pattern[str]) -> str:
    """Within the bounded block starting at ``header_re``, drop any gap-disclosure sentence the
    redactor wrote (``_GAP_MARKER_RE``), and drop the whole block if no real finding remains."""
    header_match = header_re.search(report_text)
    if not header_match:
        return report_text
    block_start = header_match.start()
    rest = report_text[header_match.end():]
    next_header = re.search(r"(?m)^#{1,6}\s", rest)
    block_end = header_match.end() + (next_header.start() if next_header else len(rest))
    block = report_text[block_start:block_end]

    # The block body is the heading + an italic preamble + ONE summary line of space-joined
    # sentences. Split that summary line into sentences and drop any that became a gap stub.
    kept_any_finding = False
    new_lines: list[str] = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("_"):
            new_lines.append(line)
            continue
        # The summary line: drop gap-disclosure sentences, keep verified (still-cited) ones. Use
        # key_findings' _SENTENCE_RE (a MATCH, not a split) so a trailing ``[N]`` citation stays
        # attached to its sentence ("...20 percent.[1] Next..." segments correctly).
        sentences = [m.group(0).strip() for m in _SENTENCE_RE.finditer(line.strip())]
        if not sentences:  # a line with no sentence-terminator (defensive) — treat whole line as one
            sentences = [line.strip()]
        kept_sentences = [s for s in sentences if s and not _GAP_MARKER_RE.search(s)]
        if any(_CITATION_RE.search(s) for s in kept_sentences):
            kept_any_finding = True
        if kept_sentences:
            new_lines.append(" ".join(kept_sentences))
        # else: every sentence on this line was a gap stub -> drop the whole summary line.

    if kept_any_finding:
        new_block = "\n".join(new_lines)
        if not new_block.endswith("\n"):
            new_block += "\n"
        return report_text[:block_start] + new_block + report_text[block_end:]

    # No verified finding remains in the block -> drop the whole block (no empty heading).
    trimmed = report_text[:block_start] + report_text[block_end:]
    return re.sub(r"^\n+", "", trimmed) if block_start == 0 else trimmed
