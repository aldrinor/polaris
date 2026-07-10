"""Cross-section repetition guard (I-deepfix-001 FIX 5, GH #1344).

THE DEFECT (composition-collapse audit, drb_72): the composer recycled ~8 findings across 6
sections (e.g. Goldman's 2.5% GDP estimate appeared in 4 sections, the robot-count estimate in
4, the "15% of tasks" figure in 3, the Frey-Osborne method in 4). ``fact_dedup`` consolidates
near-restatements WITHIN a single section only, so a finding restated VERBATIM in a DIFFERENT
section survives — burning section space that DISTINCT findings should occupy.

THE GUARD (this module): after per-section compose, detect a finding (a cited sentence) that
recurs VERBATIM across DIFFERENT sections and CONSOLIDATE it to its richest instance plus a short
citation-preserving back-reference, freeing section space for distinct findings.

§-1.3 CONSOLIDATE-KEEP-ALL (never a drop / cap / thin): every recycled instance KEEPS its own
numeric citation marker(s) inline on the back-reference — no citation is ever dropped, and NO
citation is moved between sections (so the per-section-local citation numbering the downstream
``_remap_section_markers_to_global`` relies on stays valid). Repetition is consolidated, not
deleted; the finding's full prose remains in its richest section.

EXACT-RECYCLE ONLY — NOT a paraphrase-collapse (Codex diff-gate iter-1 P1 #2): equivalence is an
EXACT normalized-text match (NUMERIC-citation-stripped, whitespace-collapsed, lowercased,
trailing-punctuation-stripped). Two sentences that differ in ANY content — a year, a figure, an
entity, directionality, an extra clause — have DIFFERENT normalized text and are NEVER clustered.
Crucially, ONLY renderer-guaranteed numeric citation markers (``[12]``) are stripped from the
signature; NON-citation bracketed content — a bracketed entity/label such as ``[Alpha]`` — is
PRESERVED in the signature (Codex diff-gate iter-2 P1). So ``The model [Alpha] cut error 10% [1]``
and ``The model [Beta] cut error 10% [2]`` have DIFFERENT signatures and are never clustered:
distinct verified content can NEVER be replaced by a back-reference. A loose token-overlap
threshold is deliberately NOT used — it would let near-identical-but-distinct sentences cluster,
turning a render-only consolidation into a silent DROP (a §-1.3 violation).

MARKER-REQUIRED — never rewrites an honest gap disclosure (Fable diff-gate iter-1 P1): a unit is an
eligible finding ONLY if it carries at least one NUMERIC ``[N]`` citation marker. Every
strict_verify-kept claim sentence carries markers (§9.1 invariant 2); the production gap / degraded
disclosures (``_GAP_STUB_SENTENCE`` / ``_NO_EVIDENCE_GAP_STUB_SENTENCE`` /
``_SECTION_FAILED_GAP_STUB_SENTENCE``) and back-references are marker-less BY DESIGN. So two starved
sections carrying the same gap stub can NEVER cluster, and the honest per-section gap disclosure is
never deleted or replaced by a false "See ... for this finding" pointer. Belt-and-braces: a section
flagged ``is_gap_stub=True`` is skipped entirely.

LAYOUT-PRESERVING (Codex diff-gate iter-1 P1 #3): a recycled instance is replaced by an in-place
single-occurrence substring swap on the ORIGINAL ``verified_text`` — every other byte (markdown
``### slot`` sub-headings, blank lines, adjacent sentences) is preserved unchanged. The guard NEVER
re-splits + ``" ".join``-rejoins a body (which would flatten ``### Heading`` layout into inline
prose and corrupt contract-section slot headings). A unit whose text contains a markdown heading
line (``#``-prefixed) is not eligible, and a unit that does not occur EXACTLY once in its body is
left untouched — precision-first: never risk corrupting real prose on a splitter/matching miss.

FAITHFULNESS-NEUTRAL (constraint 1, never a relax): RENDER-ONLY. It edits ONLY the rendered
``verified_text`` string, and ONLY AFTER the frozen faithfulness engine (strict_verify / NLI
entailment / 4-role D8 / provenance / span-grounding) has already run per section. It does not touch
``kept_sentences_pre_resolve`` (the SentenceVerification objects the 4-role D8 gate judges), the
per-section verified/dropped counts, or any evidence row.

KILL-SWITCH (LAW VI / constraint 3): ``PG_CROSS_SECTION_REPETITION_GUARD`` — DEFAULT OFF. When OFF
(or unset) the guard is a no-op and the assembled report is BYTE-IDENTICAL to the legacy path.
Tunable: ``PG_CROSS_SECTION_REPETITION_MIN_WORDS`` (min distinct content words per eligible finding,
default 6) — read from the environment (no magic numbers).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger("polaris_graph.cross_section_repetition_guard")

# ── Environment knobs (LAW VI — every threshold/flag is env-tunable, no magic numbers) ──────────
_ENV_ENABLED = "PG_CROSS_SECTION_REPETITION_GUARD"
_ENV_MIN_WORDS = "PG_CROSS_SECTION_REPETITION_MIN_WORDS"

_MIN_WORDS_DEFAULT = 6

_OFF_TOKENS = frozenset({"0", "false", "off", "no"})

# NUMERIC citation marker (``[1]``, ``[12]``, and the GROUPED ``[1, 2]`` form the renderer can emit).
# This is the renderer-guaranteed citation syntax at this pre-global-remap stage (§9.1 invariant 2). It
# is the ONLY thing stripped from the equivalence signature and is what a unit's eligibility ("is this a
# strict_verify-kept CLAIM sentence?") is keyed on. NON-citation bracketed content (a bracketed
# entity/label such as ``[Alpha]``) is deliberately NOT matched here, so it stays IN the signature and
# two units that differ only by such an entity are never clustered (Codex diff-gate iter-2 P1 — no
# faithfulness leak). P0-4 (2026-07-10): the GROUPED ``[1, 2]`` alternative makes the signature
# citation-token-INSENSITIVE so a rotated-citation duplicate is detected regardless of its marker shape.
_CITATION_NUM_RE = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
# A raw provenance token (``[#ev:...]``) — also stripped from the signature in case an unresolved token
# survives to this report-level stage (citation-token-insensitive P0-4).
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")

# Content-word tokenizer for the min-content-words eligibility gate ONLY (never the equivalence
# signature). Unicode-aware (Codex diff-gate iter-2 P2): ``[^\W_]+`` matches runs of Unicode letters
# and digits (excluding underscore), so a repeated cited finding written in a non-Latin script is
# still measured by real content-word count instead of silently underfiring an ASCII-only ``[a-z0-9]``.
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Function words removed ONLY for the min-content-words eligibility count (never for the equivalence
# signature, which is an EXACT match). Intentionally small + generic.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "but", "by", "for", "from", "had", "has",
    "have", "in", "into", "is", "it", "its", "of", "on", "or", "that", "the", "their", "them",
    "these", "they", "this", "to", "was", "were", "which", "will", "with", "would",
})

# The back-reference that replaces a recycled instance. The recycled instance's own numeric
# citation marker(s) are appended so no citation is dropped (§-1.3 keep-all).
_BACKREF_TEMPLATE = 'See "{title}" for this finding.'
_BACKREF_FALLBACK_TITLE = "the section above"


def guard_enabled() -> bool:
    """Kill-switch ``PG_CROSS_SECTION_REPETITION_GUARD`` — DEFAULT ON (2026-07-10 compose gear-loop,
    P0-4). The guard is a render-only, faithfulness-NEUTRAL consolidate-keep-all pass (every recycled
    citation is preserved as a back-reference), so it is safe to run by default. Only an explicit off
    token (``0`` / ``false`` / ``off`` / ``no``) disables it; unset or blank => ON."""
    raw = os.environ.get(_ENV_ENABLED)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _OFF_TOKENS


def _min_content_words() -> int:
    """Minimum distinct content words for a sentence to be an eligible finding (default 6). A
    malformed or non-positive value falls back to the default."""
    raw = os.environ.get(_ENV_MIN_WORDS, "")
    if not raw.strip():
        return _MIN_WORDS_DEFAULT
    try:
        val = int(raw.strip())
    except (TypeError, ValueError):
        return _MIN_WORDS_DEFAULT
    if val <= 0:
        return _MIN_WORDS_DEFAULT
    return val


def _has_numeric_citation(sentence: str) -> bool:
    """True iff the sentence carries at least one numeric ``[N]`` citation marker (the eligibility
    signal for a strict_verify-kept claim; marker-less disclosures/back-refs are excluded)."""
    return bool(_CITATION_NUM_RE.search(sentence))


def _contains_heading(sentence: str) -> bool:
    """True iff any line of the unit is a markdown heading (``#``-prefixed). Such a unit is not
    eligible — replacing it would delete a contract-section ``### slot`` sub-heading (layout defect)."""
    for line in sentence.splitlines():
        if line.lstrip().startswith("#"):
            return True
    return False


def _signature(sentence: str) -> str:
    """EXACT-recycle equivalence signature: ONLY numeric ``[N]`` citation markers removed, whitespace
    collapsed, lowercased, trailing sentence punctuation stripped. Two units are equivalent iff their
    signatures are EQUAL — any difference in content (year / figure / entity / a bracketed label such
    as ``[Alpha]`` / direction / extra clause) yields a different signature, so distinct verified
    content can NEVER be clustered (no faithfulness leak). Non-citation bracketed content is preserved
    verbatim in the signature (Codex diff-gate iter-2 P1). P0-4 (2026-07-10): raw ``[#ev:...]`` tokens
    and the grouped ``[N, M]`` marker form are also stripped so the signature is citation-token-
    INSENSITIVE (a rotated-citation duplicate clusters regardless of marker shape)."""
    no_cite = _CITATION_NUM_RE.sub(" ", _EV_TOKEN_RE.sub(" ", sentence))
    collapsed = " ".join(no_cite.split()).lower()
    return collapsed.rstrip(".!?;:, ")


def _content_word_count(sentence: str) -> int:
    """Number of distinct content-word tokens (stopwords + numeric citations removed) — the min-words
    gate. Bracketed entity words (e.g. ``Alpha`` in ``[Alpha]``) count as content."""
    no_cite = _CITATION_NUM_RE.sub(" ", sentence)
    return len({t for t in _WORD_RE.findall(no_cite.lower()) if t not in _STOPWORDS})


def _citation_markers(sentence: str) -> list[str]:
    """Ordered list of the unit's numeric ``[N]`` citation marker(s), kept verbatim for the
    back-reference so no citation is ever dropped (§-1.3 keep-all)."""
    return _CITATION_NUM_RE.findall(sentence)


def _backref_sentence(title: str, citations: list[str]) -> str:
    """Build the back-reference that replaces a recycled instance, preserving its citations."""
    clean_title = (title or "").strip() or _BACKREF_FALLBACK_TITLE
    base = _BACKREF_TEMPLATE.format(title=clean_title)
    if citations:
        return f"{base} {''.join(citations)}"
    return base


def consolidate_cross_section_repetition(section_results: list[Any]) -> dict[str, Any]:
    """Consolidate findings that recur VERBATIM across DIFFERENT sections down to a richest instance
    plus a citation-preserving back-reference. Mutates each affected ``SectionResult.verified_text``
    IN PLACE via a single-occurrence substring swap (layout-preserving). Returns a telemetry dict
    ``{clusters, consolidated}`` (empty dict when the guard is OFF).

    Contract:
      * OFF (flag unset / off token) -> ``{}`` and NO mutation (byte-identical legacy output).
      * Eligible finding = a sentence that (a) carries >= 1 numeric ``[N]`` marker, (b) has
        >= min_content_words distinct content words, (c) contains NO markdown heading line, in a
        section that is not dropped and not ``is_gap_stub``.
      * Equivalence = EXACT normalized-text match (NOT a loose overlap threshold); ONLY numeric
        citations are stripped, so bracketed non-citation content stays distinguishing.
      * A cluster consolidates ONLY when it spans >= 2 DISTINCT sections.
      * The richest instance (most citation markers; earliest section/sentence on a tie) is KEPT
        verbatim; every OTHER instance in a DIFFERENT section is replaced IN PLACE by a
        back-reference carrying that instance's OWN marker(s) — no citation dropped, none moved.
      * A unit that does not occur EXACTLY once in its body is left untouched (precision fail-safe).
      * Same-section duplicates are left to ``fact_dedup`` (never consolidated here).
      * A ``dropped_due_to_failure`` / ``is_gap_stub`` / empty section is EXCLUDED from the unit set,
        so it is never a cluster member, never the richest instance, and never a back-reference
        TARGET. The ``dropped_due_to_failure`` predicate is the SAME one the downstream render filter
        uses (``if not sr.dropped_due_to_failure``), so a rendered section can NEVER be collapsed into
        a back-reference to a non-rendered section (Codex diff-gate P1: no final-output content loss).
    """
    if not guard_enabled():
        return {}

    # Lazy import to avoid any generator-package import-order coupling.
    from .verified_compose import split_into_sentences  # noqa: PLC0415

    min_words = _min_content_words()

    # Per-section eligible-unit lists. ``sections[i]`` is None for a section that is dropped, empty,
    # or a gap stub (left completely untouched).
    sections: list[dict[str, Any] | None] = []
    for sr in section_results:
        # Codex diff-gate P1 (dropped-section safety): a dropped_due_to_failure section (the EXACT
        # predicate the downstream render filter uses — ``if not sr.dropped_due_to_failure``), a gap
        # stub, or an empty section is set to None and NEVER contributes a unit. So it can never be a
        # cluster member, the richest instance, or a back-reference TARGET — a rendered section is
        # never collapsed into a back-reference to a non-rendered section (no final-output content loss).
        if getattr(sr, "dropped_due_to_failure", False) or getattr(sr, "is_gap_stub", False):
            sections.append(None)
            continue
        text = getattr(sr, "verified_text", "") or ""
        if not text.strip():
            sections.append(None)
            continue
        sections.append({"sr": sr, "text": text})

    # Flat list of eligible finding-units across all in-scope sections. Each unit keeps the RAW
    # sentence text (for the in-place substring swap) and its normalized signature (for clustering).
    units: list[dict[str, Any]] = []
    for sec_pos, sec in enumerate(sections):
        if sec is None:
            continue
        for sent_pos, sent in enumerate(split_into_sentences(sec["text"])):
            if _contains_heading(sent):
                continue
            if not _has_numeric_citation(sent):
                continue
            if _content_word_count(sent) < min_words:
                continue
            units.append({
                "sec_pos": sec_pos,
                "sent_pos": sent_pos,
                "raw": sent,
                "sig": _signature(sent),
                "citations": _citation_markers(sent),
            })

    if len(units) < 2:
        return {"clusters": 0, "consolidated": 0}

    # Cluster by EXACT signature (deterministic; insertion-ordered members).
    groups: dict[str, list[int]] = {}
    for i, unit in enumerate(units):
        groups.setdefault(unit["sig"], []).append(i)

    # Plan the in-place swaps (do not mutate while clustering).
    replacements: dict[int, list[dict[str, str]]] = {}
    clusters = 0
    consolidated = 0
    for members in groups.values():
        distinct_secs = {units[m]["sec_pos"] for m in members}
        if len(distinct_secs) < 2:
            continue
        clusters += 1
        # Richest = most citation markers; earliest (section, sentence) breaks ties deterministically
        # (negated positions so ``max`` prefers the earliest instance).
        richest = max(
            members,
            key=lambda m: (
                len(units[m]["citations"]),
                -units[m]["sec_pos"],
                -units[m]["sent_pos"],
            ),
        )
        richest_sec = units[richest]["sec_pos"]
        richest_title = getattr(sections[richest_sec]["sr"], "title", "") or ""  # type: ignore[index]
        for m in members:
            if m == richest or units[m]["sec_pos"] == richest_sec:
                # The kept instance, or a same-section twin (that is fact_dedup's job) — never here.
                continue
            replacements.setdefault(units[m]["sec_pos"], []).append({
                "old": units[m]["raw"],
                "new": _backref_sentence(richest_title, units[m]["citations"]),
            })

    # Apply the swaps in place, one section at a time. Each swap targets EXACTLY one occurrence; a
    # unit that is absent or ambiguous (count != 1) in the current body is skipped (fail-safe).
    for sec_pos, swaps in replacements.items():
        sec = sections[sec_pos]
        if sec is None:
            continue
        text = sec["sr"].verified_text
        changed = False
        for swap in swaps:
            old = swap["old"]
            if text.count(old) != 1:
                continue
            text = text.replace(old, swap["new"], 1)
            changed = True
            consolidated += 1
        if changed:
            sec["sr"].verified_text = text

    if consolidated:
        logger.info(
            "[cross_section_repetition_guard] consolidated %d recycled finding instance(s) across "
            "sections into %d cross-section cluster(s); every recycled citation preserved as a "
            "back-reference (§-1.3 consolidate-keep-all; frozen faithfulness engine untouched)",
            consolidated, clusters,
        )

    return {"clusters": clusters, "consolidated": consolidated}
