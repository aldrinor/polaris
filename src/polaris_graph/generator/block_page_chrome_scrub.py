"""I-deepfix-001 P8_chrome_leak (#1344) — render-seam block-page / security-check / copyright-footer
chrome STRIPPER (presentation-only, §-1.3-safe).

WHY THIS EXISTS
---------------
The drb_72 workforce report.md body rendered a ResearchGate / Cloudflare BLOCK PAGE (bibliography
source ``[27]`` = ``ev_146``, ``source_title`` "Just a moment...", tier T7) as two verified-looking
body sentences::

    ... To continue, complete the security check below.[27] Ray ID: a160331f3c7dd701 Client IP:
    2600:1900:0:2101::1100 (c) 2008-2026 ResearchGate GmbH.[27] Our analysis identifies nine ...

The block-page text was captured as a corpus source, its span verbatim-copied into the composed
prose, and it passed strict_verify through the SELF-CITATION hole (the sentence == the cited span,
so the numeric / content-overlap / entailment checks trivially hold).

WHY THE EXISTING SCREENS MISSED IT
----------------------------------
The whole-page render-chrome predicate (``weighted_enrichment.is_render_chrome_or_unrenderable``,
called at the I-wire-013 render-seam chokepoint via ``sanitize_rendered_report``) catches the FULL
block-page text, but is BLIND to each SINGLE sentence once ``split_into_sentences`` fractures the
page at compose / render time. Proven against the run data: the joined page returns ``True`` while
"To continue, complete the security check below." and "Ray ID: ... (c) 2008-2026 ResearchGate GmbH."
each return ``False``. This is the I-wire-013 blind-predicate class re-appearing at SENTENCE
granularity, for the specific bot-challenge / copyright-footer vocabulary the containment predicate
does not enumerate.

POSTURE (binding)
-----------------
* PRESENTATION-ONLY / faithfulness-NEUTRAL (§-1.3): runs at the render seam over the FULLY-ASSEMBLED
  ``report.md`` string, AFTER the frozen faithfulness engine (strict_verify / NLI / 4-role D8 /
  provenance / span-grounding) and AFTER ``sanitize_rendered_report``. It only WITHHOLDS a block-page
  chrome SENTENCE from the rendered prose. It drops NO source (the ``[27]`` bibliography row + the
  corpus-credibility disclosure stay untouched), rewrites NO real claim, and touches NO verdict.
  It never relaxes the faithfulness engine — it removes non-content chrome, never a real claim.
* HIGH-PRECISION (precision-first): every HARD marker is a bot-challenge / security-verification /
  Cloudflare phrase that never appears in a real labor / economics / clinical finding OR in POLARIS
  disclosure prose. The copyright-footer rule is triple-gated (copyright mark + rights/entity signal
  + dominance) so a real claim that merely cites a license in passing is KEPT. Over-stripping a real
  finding is the harm this guards against, not a leaked chrome line.
* FAIL-SAFE: a sentence is dropped only when it IS block-page chrome; a real finding welded into the
  SAME line is preserved (line-scoped sentence partition). Segmentation is an exact character
  partition (``"".join(segments) == line``), so a rejoin can never corrupt real prose. Structural
  lines (headers, table rows, code fences, rules) are byte-preserved. If dropping would empty a
  line, only the line's leading structure prefix (bullet / number) is kept.
* DETERMINISTIC + PURE: stdlib only (``os`` / ``re``), no LLM, no network, no shared-module import
  (fully isolated). ``snake_case`` (LAW V). LAW VI kill-switch ``PG_BLOCK_PAGE_CHROME_SCRUB``
  (default ON); set to an off token to render byte-identically.
"""

from __future__ import annotations

import os
import re

# ─────────────────────────────────────────────────────────────────────────────
# LAW VI kill-switch.
# ─────────────────────────────────────────────────────────────────────────────
_SCRUB_ENV = "PG_BLOCK_PAGE_CHROME_SCRUB"
_OFF_TOKENS = frozenset({"0", "false", "off", "no"})

# I-deepfix-001 B4-render #13 (#1344): a SECOND, independently-gated leg that reuses the shared
# render-chrome detector (``weighted_enrichment.is_render_chrome_or_unrenderable``) at SENTENCE
# granularity. The whole-report ``sanitize_rendered_report`` runs that same detector but per
# CITATION UNIT — so a single chrome SENTENCE welded into a real-prose line (a masthead / editor-
# affiliation / raw markdown-link / bibliographic-recital / DOI-only / source-internal "[N]" marker /
# OCR title fragment) is invisible to it because the unit as a whole is not chrome. Running the
# containment detector per partitioned sentence unblinds exactly that glued-mid-prose class, in the
# report BODY and in the §8 basket labels (the scrub walks the whole assembled report, and §8 labels
# render as ``-`` bullets, not structural lines). This REUSES the proven, precision-first detector
# rather than re-enumerating chrome vocabulary here. LAW VI sub-kill-switch
# ``PG_BLOCK_PAGE_CHROME_SCRUB_SHARED`` (default ON); OFF reverts to the pre-#13 hard-marker +
# copyright-footer behaviour byte-identically. Fail-safe: any import/detector error => this leg is
# inert (never drops on a fault), so the module stays isolated in practice.
_SHARED_DETECTOR_ENV = "PG_BLOCK_PAGE_CHROME_SCRUB_SHARED"


def block_page_chrome_scrub_enabled() -> bool:
    """Return True iff ``PG_BLOCK_PAGE_CHROME_SCRUB`` is not an off token (default ON = scrub)."""
    raw = os.environ.get(_SCRUB_ENV)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _OFF_TOKENS


def shared_render_chrome_leg_enabled() -> bool:
    """Return True iff the #13 shared-detector sentence leg is active (default ON). OFF token in
    ``PG_BLOCK_PAGE_CHROME_SCRUB_SHARED`` reverts to the hard-marker + copyright-footer-only screen."""
    raw = os.environ.get(_SHARED_DETECTOR_ENV)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _OFF_TOKENS


# PRECISION ESCAPE (mirrors the copyright triple-gate's "a real claim that cites a license is KEPT"
# posture): a sentence carrying a substantive QUANTITATIVE FINDING signal — a percent (digit or
# spelled), a magnitude figure (N million/billion/…), or a currency amount — is a real claim that
# may merely CITE page-furniture (a CC-license, a publisher) in passing. The shared containment
# detector (built for whole-UNIT render-seam decisions) over-fires on such a claim per sentence, so
# the escape defers to strict_verify's already-passed verdict. Page-furniture chrome (editor /
# masthead / ORCID / bibliographic recital) never carries a quantitative finding, so the escape
# never re-admits a real chrome leak. Over-strip of a real finding is the harm this guards against.
_SUBSTANTIVE_CLAIM_RE = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:%|percent(?:age)?\b|per\s*cent\b)"
    r"|\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|"
    r"fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|"
    r"eighty|ninety|hundred)\s+(?:percent|per\s*cent)\b"
    r"|\b\d+(?:[.,]\d+)?\s*(?:million|billion|trillion|thousand)\b"
    r"|[$€£¥]\s?\d",
    re.IGNORECASE,
)


def _looks_like_substantive_quant_claim(sentence: str) -> bool:
    """True iff the sentence carries a substantive quantitative finding signal (percent / magnitude /
    currency) — a real claim the precision escape keeps even if it cites chrome in passing. PURE."""
    return bool(_SUBSTANTIVE_CLAIM_RE.search(sentence))


def _is_shared_render_chrome(sentence: str) -> bool:
    """True iff the shared render-chrome detector flags this SINGLE sentence as page-furniture
    chrome AND the sentence is not a substantive quantitative claim (precision escape). Fail-safe:
    returns False (never a drop) on ANY import/detection error, so a fault in the shared module can
    only ever LEAK chrome, never over-strip a real finding. Gated by the caller under
    ``shared_render_chrome_leg_enabled()``."""
    if _looks_like_substantive_quant_claim(sentence):
        return False  # a real quantitative finding — keep it even if it cites a license/publisher
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
    except Exception:  # pragma: no cover — weighted_enrichment is stable in-tree
        return False
    try:
        return bool(is_render_chrome_or_unrenderable(sentence))
    except Exception:  # pragma: no cover — detector is pure in-tree
        return False


# ─────────────────────────────────────────────────────────────────────────────
# HARD block-page / bot-challenge / security-verification markers. Each is a challenge-PAGE-specific
# phrase (Cloudflare / DataDome / PerimeterX / hCaptcha / ResearchGate interstitial) that never
# appears in a real finding OR in POLARIS disclosure/audit prose. A sentence containing ANY hard
# marker is block-page chrome and is withheld unconditionally. Lower-cased for a case-insensitive
# substring test.
# ─────────────────────────────────────────────────────────────────────────────
_HARD_MARKERS: tuple[str, ...] = (
    "complete the security check",
    "security check required",
    "checking your browser before",
    "checking if the site connection is secure",
    "detected unusual activity from your network",
    "unusual traffic from your",
    "performing security verification",
    "verifying you are not a bot",
    "verify you are a human",
    "verify you are human",
    "are you a robot",
    "enable javascript and cookies to continue",
    "please enable cookies and reload",
    "this process is automatic. your browser will redirect",
    "ddos protection by",
    "why do i have to complete a captcha",
    "captcha challenge",
    "please complete the captcha",
    "access to this page has been denied",
    "ray id:",                      # Cloudflare error / challenge footer "Ray ID: <hex>"
    "cf-ray",                       # Cloudflare response-header / footer token
    "cf_chl_",                      # Cloudflare challenge cookie/query token
)

# ─────────────────────────────────────────────────────────────────────────────
# Copyright-footer SOFT rule — triple-gated so a real claim that cites a license is KEPT.
# ─────────────────────────────────────────────────────────────────────────────
# (a) a copyright MARK adjacent to a year (single year or a "2008-2026" range).
_COPYRIGHT_MARK_YEAR_RE = re.compile(
    r"(?:©|\(c\)|copyright\s*(?:©|\(c\))?)\s*"
    r"\d{4}(?:\s*[-‐-―/]\s*\d{2,4})?",
    re.IGNORECASE,
)
# (b) a rights / legal-entity signal that co-occurs in a footer (never in a running claim).
_RIGHTS_ENTITY_RE = re.compile(
    r"all\s+rights\s+reserved"
    r"|\b(?:gmbh|inc\.?|llc|ltd\.?|b\.?v\.?|s\.?a\.?|s\.?l\.?|plc|pty|s\.?r\.?l\.?)\b"
    r"|\bcorp(?:oration)?\b|\bincorporated\b|\bpublish(?:ing|ers)\b",
    re.IGNORECASE,
)
# (c) dominance guard: tokens that BELONG to a footer (not real content). After removing these plus
# the mark/year and the entity signal, a residue of <= _FOOTER_RESIDUE_CONTENT_FLOOR content words
# means the sentence is DOMINATED by the footer (a real claim carries far more content).
_FOOTER_RESIDUE_CONTENT_FLOOR = 4
_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_FOOTER_FILLER_WORDS = frozenset(
    {"copyright", "all", "rights", "reserved", "the", "and", "for", "inc", "ltd", "llc", "corp",
     "gmbh", "plc", "pty", "publishing", "publishers", "incorporated", "corporation"}
)


def _is_dominant_copyright_footer(sentence: str) -> bool:
    """True iff ``sentence`` is a DOMINANT copyright footer: a copyright mark next to a year AND a
    rights/entity signal AND (after removing the mark/year and footer-filler words) a residue of at
    most ``_FOOTER_RESIDUE_CONTENT_FLOOR`` real content words. Triple-gated: a real claim that merely
    mentions a copyright/publisher in passing carries real content and is KEPT (precision-first)."""
    if not _COPYRIGHT_MARK_YEAR_RE.search(sentence):
        return False
    if not _RIGHTS_ENTITY_RE.search(sentence):
        return False
    residue = _COPYRIGHT_MARK_YEAR_RE.sub(" ", sentence)
    content = [w for w in _WORD_RE.findall(residue) if w.lower() not in _FOOTER_FILLER_WORDS]
    return len(content) <= _FOOTER_RESIDUE_CONTENT_FLOOR


# ─────────────────────────────────────────────────────────────────────────────
# Fix 4b / Fix 6 (2026-07-10 compose gear-loop iter 2) — STRUCTURAL page-furniture FORM detectors.
#
# The drb_72 body leaked whole structural chrome CLASSES the copyright-footer / hard-marker / shared
# detectors above structurally cannot see: acknowledgment lines, ``© <year> by <names>`` copyright
# lines, working-paper masthead recitals, inline page-header runs (leading page-number + section-number
# + Title-case), flattened numeric-table runs, bare author-bio / institutional self-description
# sentences, and standalone-initial units. Each detector keys on a GENERAL, question-agnostic
# STRUCTURAL FORM signature a real synthesized finding never carries (never a topic keyword). This is
# the SINGLE source of truth: ``verified_compose._structural_chrome_form`` imports it so the compose
# OUTPUT screen and this AUDIT predicate agree. Precision-first + FAIL-OPEN.
# ─────────────────────────────────────────────────────────────────────────────
_STRUCT_FURNITURE_ENV = "PG_STRUCTURAL_PAGE_FURNITURE_SCREEN"

# acknowledgment: "We/I thank / are grateful to / gratefully acknowledge X for research assistance /
# funding / comments / support" — a self-inflicted furniture line, never a finding.
_FURN_ACKNOWLEDGMENT_RE = re.compile(
    r"\b(?:we|i)\s+(?:thank|gratefully acknowledge|are (?:grateful|indebted) to|acknowledge)\b"
    r"[^.]{0,180}?\b(?:research assistance|excellent (?:research )?assistance|for (?:their )?"
    r"(?:funding|support|comments?|assistance)|financial support|helpful (?:comments?|discussions?)|"
    r"for providing)\b",
    re.I,
)
# copyright line: "© 2023 by <Name>,", "(c) 2023 by <Name> and", "all rights reserved".
_FURN_COPYRIGHT_RE = re.compile(
    r"(?:©|\(c\))\s*\d{4}\b|\b\d{4}\s+by\s+[A-Z][A-Za-z.'’\-]+(?:,|\s+and\b)|\ball rights reserved\b",
    re.I,
)
# working-paper masthead recital (beyond the source-meta screen in verified_compose).
_FURN_WORKINGPAPER_RE = re.compile(
    r"working papers? (?:are|is) circulated|(?:are|is) circulated for discussion|"
    r"may not be reproduced without|distributed for (?:purposes of )?comment|"
    r"has not (?:yet )?been (?:peer[- ]reviewed|formally reviewed)|"
    r"should not be reported as representing the views",
    re.I,
)
# inline page-header run: leading page-number + section-number + Title-case run ("10 1.2 The Economic").
_FURN_PAGE_HEADER_RE = re.compile(r"^\s*\d{1,3}\s+\d{1,2}(?:\.\d{1,2})+\s+[A-Z][a-z]")
# flattened numeric-table run: >=6 bare number tokens in a row (a table dump flattened into a line);
# real prose interleaves words, so a run this long is a table, never a sentence. (>=3 rank/value pairs.)
_FURN_NUMERIC_TABLE_RE = re.compile(r"(?:(?<![.\w])\d[\d.,%]*\s+){5,}\d[\d.,%]*")
# author-bio / institutional self-description: "holds a PhD/Master/…", "is a <role> at/of <Inst>",
# "conducts interdisciplinary/basic research", "provides evidence- and value-based".
_FURN_AUTHOR_BIO_RE = re.compile(
    r"\bhold[s]? an?\s+(?:ph\.?\s?d|doctorate|master'?s?|bachelor'?s?|m\.?sc|b\.?sc|mba)\b|"
    r"\b(?:is|was)\s+(?:an?\s+|the\s+)?(?:tenured\s+|associate\s+|assistant\s+|full\s+|visiting\s+|"
    r"emeritus\s+|affiliate\s+|adjunct\s+|senior\s+)?(?:professor|data scientist|researcher|"
    r"research (?:fellow|scientist|professor|associate|director)|postdoctoral|post-?doc|lecturer|"
    r"phd (?:student|candidate)|economist)\b\s+(?:at|of|in|,|and)\b|"
    r"\bconducts?\s+(?:interdisciplinary|basic|applied|independent)\s+(?:and\s+\w+\s+)?research\b|"
    r"\bprovides evidence-\s?and value-\s?based\b",
    re.I,
)
# standalone-initial / bare-byline non-sentence unit: a lone "S." / "A." unit, or a short run of initials.
_FURN_STANDALONE_INITIAL_RE = re.compile(r"^[A-Z]\.?$|^(?:[A-Z]\.\s*){1,4}$")


def structural_page_furniture_enabled() -> bool:
    """Kill-switch ``PG_STRUCTURAL_PAGE_FURNITURE_SCREEN`` (default ON). Only an explicit off token
    disables; unset/blank stays ON (a blank env can never silently disable the screen)."""
    raw = os.environ.get(_STRUCT_FURNITURE_ENV)
    if raw is None or not str(raw).strip():
        return True
    return str(raw).strip().lower() not in _OFF_TOKENS


def is_structural_page_furniture(sentence: str) -> bool:
    """True iff ``sentence`` carries one of the STRUCTURAL page-furniture FORMS the copyright-footer /
    hard-marker / shared detectors miss (Fix 4b/6). GENERAL + question-agnostic + precision-first;
    FAIL-OPEN on any error (never withhold a real finding on a helper fault). Default-ON kill-switch."""
    if not structural_page_furniture_enabled():
        return False
    s = (sentence or "").strip()
    if not s:
        return False
    try:
        return bool(
            _FURN_ACKNOWLEDGMENT_RE.search(s)
            or _FURN_COPYRIGHT_RE.search(s)
            or _FURN_WORKINGPAPER_RE.search(s)
            or _FURN_PAGE_HEADER_RE.search(s)
            or _FURN_NUMERIC_TABLE_RE.search(s)
            or _FURN_AUTHOR_BIO_RE.search(s)
            or _FURN_STANDALONE_INITIAL_RE.match(s)
        )
    except Exception:  # pragma: no cover — pure regexes; fail-open never withholds a real finding
        return False


def is_block_page_chrome_sentence(sentence: str) -> bool:
    """True iff a SINGLE sentence unit is block-page / security-check / copyright-footer chrome:
    it contains a HARD bot-challenge marker, OR it is a DOMINANT copyright footer, OR — when the
    #13 shared leg is enabled — the shared render-chrome detector flags it as glued page-furniture
    (masthead / editor-affiliation / raw markdown-link / bibliographic-recital / DOI-only / OCR
    title fragment), OR it is one of the structural page-furniture FORMS (Fix 4b/6: acknowledgment /
    copyright / working-paper masthead / page-header run / numeric-table run / author-bio /
    standalone-initial). High-precision: a real labor / economics / clinical finding trips none of the
    paths (precision-first per §-1.3)."""
    if not sentence or not sentence.strip():
        return False
    low = sentence.lower()
    for marker in _HARD_MARKERS:
        if marker in low:
            return True
    if _is_dominant_copyright_footer(sentence):
        return True
    if shared_render_chrome_leg_enabled() and _is_shared_render_chrome(sentence):
        return True
    if is_structural_page_furniture(sentence):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Sentence partition — an EXACT character partition of a prose line (``"".join(segments) == line``)
# so a rejoin of the kept segments can never corrupt real prose. A period is a boundary only when it
# is NOT a decimal point (``(?<!\d)`` guards "12.3" / an IPv4 octet), may carry trailing ``[N]``
# citation tokens, and is followed by whitespace + a sentence-opening character (or end-of-line).
# ─────────────────────────────────────────────────────────────────────────────
_SENTENCE_BOUNDARY_RE = re.compile(
    r"(?<!\d)[.!?](?:\s*\[\d+\])*(?=\s+[A-Z(\[\"'“‘]|\s*$)"
)


def _partition_sentences(line: str) -> list[str]:
    """Partition ``line`` into sentence segments, each carrying its trailing inter-sentence
    whitespace, such that ``"".join(result) == line`` exactly."""
    segments: list[str] = []
    pos = 0
    for match in _SENTENCE_BOUNDARY_RE.finditer(line):
        end = match.end()
        j = end
        while j < len(line) and line[j].isspace():
            j += 1
        segments.append(line[pos:j])
        pos = j
    if pos < len(line):
        segments.append(line[pos:])
    return segments


_STRUCTURAL_PREFIX_RE = re.compile(r"^(\s*(?:[-*+]\s+|>\s+|\d+[.)]\s+)*)")
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_RULE_RE = re.compile(r"^\s*(?:-{3,}|\*{3,}|_{3,})\s*$")


def _is_structural_line(line: str) -> bool:
    """True iff ``line`` is a markdown STRUCTURE line that must be byte-preserved (a heading, a table
    row, a code fence, or a horizontal rule). Blank lines are handled by the caller."""
    stripped = line.lstrip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    if stripped.startswith("|"):
        return True
    if _FENCE_RE.match(line):
        return True
    if _RULE_RE.match(line):
        return True
    return False


def _leading_structure(line: str) -> str:
    """Return the line's leading whitespace + list/quote marker prefix (e.g. ``"- "``, ``"  1. "``),
    so a fully-chrome line keeps its bullet skeleton rather than a dangling stub."""
    m = _STRUCTURAL_PREFIX_RE.match(line)
    return m.group(1) if m else ""


def _scrub_line(line: str) -> tuple[str, int]:
    """Scrub block-page chrome sentences from a single prose ``line``. Returns ``(new_line,
    dropped_count)``. FAIL-SAFE: a line with no flagged sentence returns byte-identically; a rejoin
    only concatenates KEPT segment slices (each already carrying its own single trailing space), so
    real prose is preserved with normal single spacing."""
    segments = _partition_sentences(line)
    if not segments:
        return line, 0
    flagged = [i for i, seg in enumerate(segments) if is_block_page_chrome_sentence(seg)]
    if not flagged:
        return line, 0
    kept = [seg for i, seg in enumerate(segments) if i not in set(flagged)]
    if not any(seg.strip() for seg in kept):
        # Whole line was block-page chrome — keep only the structural prefix (bullet / number) so a
        # list item is not left dangling; the chrome text is removed.
        return _leading_structure(line).rstrip(), len(flagged)
    new_line = "".join(kept).rstrip()
    return new_line, len(flagged)


def scrub_block_page_chrome(report_md: str, *, enabled: bool | None = None) -> tuple[str, int]:
    """Strip block-page / security-check / copyright-footer chrome sentences from a fully-assembled
    ``report.md`` string. Line-scoped (structural lines byte-preserved) and presentation-only.

    Returns ``(scrubbed_report_md, dropped_sentence_count)``. When the scrub is disabled, or the
    input is empty, or nothing is flagged, the input is returned byte-identically (``dropped == 0``).
    """
    if enabled is None:
        enabled = block_page_chrome_scrub_enabled()
    if not report_md or not enabled:
        return report_md, 0
    out_lines: list[str] = []
    dropped = 0
    for line in report_md.split("\n"):
        if not line.strip() or _is_structural_line(line):
            out_lines.append(line)
            continue
        new_line, count = _scrub_line(line)
        dropped += count
        out_lines.append(new_line)
    if not dropped:
        return report_md, 0
    return "\n".join(out_lines), dropped
