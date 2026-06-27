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

# I-wire-011 (#1325) fix 2/3 — shared render hygiene used by Key Findings (here) AND the
# Abstract/Conclusion harvesters (abstract_conclusion.py imports these). PURE string ops; they
# only change which already-verified sentence RENDERS or trim a marker RUN — never a verdict, never
# a source/count. Faithfulness-STRENGTHENING (they can only suppress a fragment, never promote one).

# Trailing `[N]` / `[#ev:...]` citation markers (stripped before the truncation test so a clean
# "…claim.[12]" is judged on the "." not the marker).
_TRAILING_CITATION_RE = re.compile(r"(?:\s*\[(?:\d+|#ev:[^\]]*)\])+\s*$")
# HIGH-PRECISION mid-word / cut-span truncation MARKERS only (the §-1.1 over-strip ban — never a
# heuristic guess at a cut word): a dangling/closed ellipsis (`…`, `...`, `[...]`, `[…]`, a dangling
# `[...` whose `]` was capped) or a trailing mid-word hyphen. An INTERNAL hyphen
# ("treatment-specific effects were observed.") is NOT a truncation and still renders.
_TRUNCATION_MARKER_RE = re.compile(r"\[\s*(?:\.\.\.|…)\s*\]?\s*$|(?:…|\.\.\.)\s*$|-\s*$")
# A run of 2+ ADJACENT numeric citation markers ("[12][13][14]" / "[12] [13]") — capped to the
# first N (document order = the body's own priority). Non-adjacent markers belong to DISTINCT
# in-sentence claims and are never merged/capped.
_ADJACENT_MARKER_RUN_RE = re.compile(r"\[\d+\](?:\s*\[\d+\])+")

# Default per-run citation cap (LAW VI override PG_KEY_FINDINGS_MAX_MARKERS / the conclusion uses
# its own override). A summary line citing >3 sources in one run is render-noise; the body + the
# bibliography retain every reference, so capping the SUMMARY display can never orphan a citation.
_DEFAULT_MAX_MARKERS = 3

# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327) iter-3a — CORPUS-GROUNDED boundary span-cut (the UNBLINDING).
#
# The legacy ``is_truncated_fragment`` only matched an explicit trailing ellipsis / hyphen MARKER,
# so it returned False on the dominant truncation shape in a real render: a span CUT mid-word right
# before its ``[N]`` citation ("… 1.2 Resea.[14]", "… incorporates the ap.[5]"). This adds the
# proven detector rule (scripts/iwire013_sec11_forensic_audit.py): a boundary token is a span cut
# iff it is NOT a word the run's OWN corpus uses AND it is a strict NON-inflectional prefix (end cut)
# / suffix (start cut) of a LONGER corpus word. The corpus-vocabulary allowlist (``known_words``,
# built by the caller from evidence_pool direct_quote/statement/title) is the FALSE-POSITIVE GUARD:
# a real-but-rare sentence-ender ("classifier", "computerisation") is either known or has no longer
# known completion, so it does NOT flag, while a real cut ("Resea"→"research") always does. The
# completion gate keeps precision high (the detector holds ~2% FP on the banked render).
#
# DROP-PATH SAFE / BACKWARD-COMPATIBLE: ``known_words`` is keyword-only and defaults to ``None`` —
# every existing caller (no corpus) gets BYTE-IDENTICAL legacy behaviour (the marker check only).
# The boundary check fires ONLY when a corpus allowlist is supplied AND the caller marks which
# boundary (``ends_before_marker`` / ``starts_after_marker``) is eligible — so a complete sentence's
# trailing complete word is never end-checked unless the caller says a marker follows it.

# An alphabetic word token (the boundary word; mirrors the detector's _WORD_RE).
_BOUNDARY_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")
# Leading `[N]` / `[#ev:...]` citation markers (stripped before reading the first word after a cut).
_LEADING_CITATION_RE = re.compile(r"^(?:\s*\[(?:\d+|#ev:[^\]]*)\])+")
# Suffixes that make a longer known word a mere INFLECTION of the token (so the token is the real
# base word, not a cut): 'disadvantage' -> {'disadvantaged','disadvantages'} only => NOT a cut. A
# real END cut has a NON-inflectional completion ('resea' -> 'research' = 'resea'+'rch').
_INFLECTION_SUFFIXES = ("s", "d", "es", "ed", "ing", "ly", "ic")
# Two-letter boundary tokens that are legitimate short words / abbreviations (never a cut).
_SHORT_OK_BOUNDARY_TOKENS = frozenset({
    "ai", "it", "is", "of", "to", "in", "on", "or", "an", "as", "be", "by", "we", "us", "no",
    "so", "do", "etc", "al", "eg", "ie", "vs", "id", "ml", "ui", "ux", "hr", "ev", "uk",
    "eu", "gn", "io", "pp", "ed", "co", "re", "at", "if", "up", "my", "go", "he", "me", "ok",
})


def _boundary_last_word(text: str) -> str:
    """The trailing alphabetic word of ``text`` (a single artificial '.' a span-truncator appends,
    plus a trailing hyphen/quote, are stripped first). '' when there is no trailing word."""
    s = text.rstrip().rstrip('"”\')')
    if s.endswith("."):
        s = s[:-1].rstrip()
    m = re.search(r"([A-Za-z][A-Za-z'\-]*)$", s)
    return m.group(1).strip("-'") if m else ""


def _boundary_first_word(text: str) -> str:
    """The leading alphabetic word of ``text`` (after any leading citation marker is stripped by the
    caller). '' when there is no leading word."""
    m = re.match(r"\s*([A-Za-z][A-Za-z'\-]*)", text)
    return m.group(1).strip("-'") if m else ""


def _known_word_has_longer_prefix(word: str, known_words: "set[str] | frozenset[str]") -> bool:
    """True iff some KNOWN corpus word is ``word`` + a NON-inflectional tail (``word`` is a chopped-
    END prefix: 'resea' -> 'research'). A token whose only longer completions are inflections
    ('disadvantage' -> 'disadvantaged') is the real base word and returns False."""
    return any(
        len(k) > len(word) and k.startswith(word) and k[len(word):] not in _INFLECTION_SUFFIXES
        for k in known_words
    )


def _known_word_has_longer_suffix(word: str, known_words: "set[str] | frozenset[str]") -> bool:
    """True iff some KNOWN corpus word ENDS with ``word`` and is longer (``word`` is a chopped-START
    suffix: 'hodology' -> 'methodology', 'nization' -> 'mechanization')."""
    return any(len(k) > len(word) and k.endswith(word) for k in known_words)


def _boundary_token_is_span_cut(
    token: str, known_words: "set[str] | frozenset[str]", *, mode: str
) -> bool:
    """A boundary token is a span cut iff it is NOT a known corpus word AND it is a strict prefix
    (end cut) / suffix (start cut) of a LONGER known corpus word. The completion gate keeps
    precision high: a legit-but-rare sentence-ender is either known or has no longer known
    completion, so it does NOT flag; a real span cut ('Resea'->'research') always does. A len-1
    token before a marker is a cut by construction; a len-2 token keeps an abbreviation allowlist."""
    if not token or not known_words:
        return False
    t = token.lower()
    if t in known_words:
        return False
    completes = (
        _known_word_has_longer_prefix(t, known_words) if mode == "end"
        else _known_word_has_longer_suffix(t, known_words)
    )
    if len(t) == 1:
        return t not in {"a", "i"}
    if len(t) == 2:
        return t not in _SHORT_OK_BOUNDARY_TOKENS and completes
    return completes  # len>=3 and a chopped fragment of a known corpus word -> a span cut


def is_truncated_fragment(
    text: str,
    known_words: "set[str] | frozenset[str] | None" = None,
    *,
    ends_before_marker: bool = False,
    starts_after_marker: bool = False,
) -> bool:
    """True iff ``text`` carries a mid-word / cut-span truncation.

    Two independent, drop-path-safe signals:
      1. UNAMBIGUOUS MARKER (always, no corpus needed): a trailing/closed ellipsis or a trailing
         mid-word hyphen, after stripping trailing ``[N]`` citation markers. Never guesses at a cut
         word from letters alone — a complete sentence with an internal hyphen still passes.
      2. CORPUS-GROUNDED BOUNDARY SPAN-CUT (I-wire-013 #1327, only when ``known_words`` is supplied):
         the boundary token before a ``[N]`` (``ends_before_marker``) or the lowercase token after
         one (``starts_after_marker``) is a non-inflectional prefix/suffix of a LONGER corpus word
         and is itself absent from the corpus — e.g. "… 1.2 Resea.[14]". The corpus allowlist is the
         false-positive guard (a real, complete word is known or has no longer completion).

    BACKWARD-COMPATIBLE: ``known_words=None`` (the default for every legacy caller) → byte-identical
    legacy behaviour (signal 1 only). PURE."""
    if not text:
        return False
    core = _TRAILING_CITATION_RE.sub("", text.strip()).rstrip()
    if core and _TRUNCATION_MARKER_RE.search(core):
        return True
    if not known_words:
        return False
    if ends_before_marker and _boundary_token_is_span_cut(
        _boundary_last_word(core), known_words, mode="end"
    ):
        return True
    if starts_after_marker:
        lead = _LEADING_CITATION_RE.sub("", text).lstrip()
        first = _boundary_first_word(lead)
        if first and first[:1].islower() and _boundary_token_is_span_cut(
            first, known_words, mode="start"
        ):
            return True
    return False


def _is_render_chrome_claim(sentence: str) -> bool:
    """I-wire-012 (#1326): True iff ``sentence`` is render-side chrome / page-furniture /
    an unrenderable fragment per THE ONE shared predicate
    (``weighted_enrichment.is_render_chrome_or_unrenderable``). Lifting Key-Findings /
    Abstract / Conclusion / depth findings through this is faithfulness-STRENGTHENING — a
    chrome span that survived strict_verify (it is a verbatim span of fetched furniture)
    must NOT lead a finding. Lazy import (the predicate lazy-imports this module's
    ``is_truncated_fragment``, so a module-top import would cycle). Fail-CONSERVATIVE: on
    any import error, keep the sentence (never silently drop a real finding)."""
    try:
        from src.polaris_graph.generator.weighted_enrichment import (  # noqa: PLC0415
            is_render_chrome_or_unrenderable,
        )
    except Exception:  # pragma: no cover - weighted_enrichment is stable in-tree
        return False
    try:
        return bool(is_render_chrome_or_unrenderable(sentence, require_sentence_form=True))
    except Exception:  # pragma: no cover - the predicate is pure in-tree
        return False


def _max_key_findings_markers() -> int:
    """Per-run citation cap for the Key-Findings summary (LAW VI). Floored at 1; fail-soft on a
    non-int (the summary must never be silently emptied of citations)."""
    raw = os.getenv("PG_KEY_FINDINGS_MAX_MARKERS", "").strip()
    if not raw:
        return _DEFAULT_MAX_MARKERS
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_MARKERS


def cap_citation_marker_runs(sentence: str, max_markers: int) -> str:
    """Trim every RUN of adjacent ``[N]`` markers in ``sentence`` to its first ``max_markers``.

    The markers are carried VERBATIM from a body span that already passed strict_verify, so each is
    span-supported; this only bounds how many co-citations a SUMMARY line displays per run (document
    order = the body's own relevance priority). PURE; ``max_markers <= 0`` returns the input
    unchanged (never strips all citations)."""
    if max_markers <= 0 or not sentence:
        return sentence

    def _cap(match: re.Match[str]) -> str:
        nums = re.findall(r"\[(\d+)\]", match.group(0))
        return "".join(f"[{n}]" for n in nums[:max_markers])

    return _ADJACENT_MARKER_RUN_RE.sub(_cap, sentence)


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
    # I-wire-011 (#1325) fix 2: also exclude a sentence carrying an unambiguous mid-word truncation
    # marker (a cut fetch span like "…comprehensi [...") so a fragment never leads a finding. Shared
    # by the Abstract/Conclusion harvesters; strengthening (it can only suppress a fragment).
    # I-wire-012 (#1326): also exclude a sentence that is render-side chrome / page-furniture
    # per THE ONE shared predicate (masthead/ISSN/ResearchGate/ToC/CC-license/ORCID/doc-label/
    # mid-word-start/incomplete) — so a chrome span never LEADS a Key-Findings / Abstract /
    # Conclusion / depth finding. Default-ON (PG_RENDER_CHROME_SCREEN=0 reverts to byte-identical).
    return [
        s for s in matches
        if s
        and not _ATX_HEADER_RE.match(s.lstrip())
        and _CITATION_RE.search(s)
        and not _GAP_MARKER_RE.search(s)
        and not is_truncated_fragment(s)
        and not _is_render_chrome_claim(s)
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
        _marker_cap = _max_key_findings_markers()
        for sentence in _first_verified_sentences(verified_text, _SENTENCES_PER_SECTION):
            # I-wire-011 (#1325) fix 2: cap each adjacent citation-marker RUN to the most-relevant
            # few (document order). Render-only; the body + bibliography keep every reference.
            sentence = cap_citation_marker_runs(sentence, _marker_cap)
            label = f"**{title}.** " if title else ""
            bullets.append(f"- {label}{sentence}")
            if len(bullets) >= _MAX_BULLETS:
                break
        if len(bullets) >= _MAX_BULLETS:
            break
    if not bullets:
        return ""
    # I-beatboth-011 §3.2 (#1289): HONEST self-cert label (was the over-claiming absolute
    # "span-verified statement" — a verbatim self-quote tautologically passes strict_verify, so the
    # absolute phrasing implied a guarantee the engine does not make). State the REAL guarantee.
    # LABEL honesty only — the faithfulness engine is UNTOUCHED.
    header = (
        "## Key Findings\n\n"
        "_Each finding below is verbatim text carried up from a cited body span; it passes strict_verify "
        "(span bounds + numeric match + ≥2 content-word grounding) but is single-origin unless marked "
        "corroborated, and span-grounding is NOT a peer-reviewed or on-topic guarantee. Citations are "
        "the body's._\n\n"
    )
    return header + "\n".join(bullets) + "\n\n"


# I-wire-011 (#1325) fix 6 — per-section analytical-depth layer (default-OFF, LAW VI).
#
# GENUINE grounded synthesis (NOT pattern-injection — the §-1.1 ban). For each verified section it
# labels the section's HEADLINE verified finding under a per-section ``**Key Findings**`` subhead and,
# ONLY when the section's own verified prose actually carries a challenge/limitation, lifts that
# verbatim challenge sentence under a ``**Challenges**`` subhead. Every emitted line is verbatim,
# cited, span-verified body text — so it raises the advisory analytical_depth key_findings/challenge
# counts HONESTLY (real content), never by injecting empty marker strings. No challenge sentence => no
# Challenges line (never a fabricated limitation). Default-OFF => no block => byte-identical.
_DEPTH_LAYER_ENV = "PG_SWEEP_DEPTH_LAYER"
# The SAME challenge cues the analytical_depth metric scores (kept in sync deliberately) — used to
# pick a REAL limitation sentence from the section's verified prose, never to fabricate one.
_CHALLENGE_CUE_RE = re.compile(
    r"\b(limitation|contradict|conflicting|gap in|insufficient evidence|notable absence|"
    r"remains unclear|further research|caveat|uncertain)\b",
    re.I,
)
# I-wire-012 (#1326) synthesis pass — a SURFACED TENSION is a verbatim verified sentence that
# expresses cross-source DISAGREEMENT / opposition (however / in contrast / whereas / conversely /
# disagree / diverge). Like the challenge lift it is verbatim, cited, span-verified body prose —
# faithful BY IDENTITY (never a generated cross-claim recombination, which abstract_conclusion.py
# proved unsound). Distinct cue set from the challenge so a section can surface BOTH.
_TENSION_CUE_RE = re.compile(
    r"\b(however|in contrast|by contrast|conversely|whereas|on the other hand|disagree\w*|"
    r"diverg\w*|inconsistent\w*|at odds|opposite\w*)\b",
    re.I,
)


def depth_layer_enabled() -> bool:
    """Default OFF. ``PG_SWEEP_DEPTH_LAYER=1`` appends the per-section analytical-depth layer."""
    return os.getenv(_DEPTH_LAYER_ENV, "0").strip().lower() not in _OFF_VALUES


def build_depth_layer(
    sections: list[Any],
    *,
    synthesized_findings: list[str] | None = None,
) -> str:
    """Return a ``## Analytical synthesis`` block.

    Two grounded layers, both verbatim/cited/span-verified — zero new unverified claims:

    * ``synthesized_findings`` (I-wire-013 #1327): the OPTIONAL grounded CROSS-SOURCE digest produced
      by ``depth_synthesis.synthesize_cross_source_findings`` — each item is ONE consolidated
      cross-source finding that ALREADY passed the UNCHANGED ``strict_verify`` (a synthesized sentence
      with no grounding span was DROPPED) and carries the report's own ``[N]`` citations. Rendered FIRST
      under a ``### Cross-source synthesis`` subhead. ``None``/empty (the legacy call) => omitted.
    * Per verified section: the headline finding under ``**Key Findings**`` and (only when the
      evidence raises one) a verbatim ``**Challenges**`` / ``**Tension**`` sentence — lifted verbatim
      from the section's already-verified prose.

    "" when disabled, or when there is neither a synthesized finding nor any section with verified
    prose (no empty heading)."""
    if not depth_layer_enabled():
        return ""
    synth_block = ""
    synth_items = [s for s in (synthesized_findings or []) if str(s).strip()]
    if synth_items:
        # HONEST provenance sub-label (§-1.1 — a misstated provenance label is treated as lethal): the
        # cross-source bullets are GENERATOR-PHRASED then re-grounded, NOT verbatim body lifts, so they
        # must NOT inherit the per-section block's "verbatim … no new claim" framing. State the REAL
        # guarantee: each consolidates >=2 corroborating sources and re-passed strict_verify (or was
        # dropped). LABEL honesty only — the faithfulness engine is UNTOUCHED.
        synth_label = (
            "_Each finding below consolidates >=2 corroborating sources; it is generator-phrased "
            "(not a verbatim quote) and every sentence re-passed strict_verify (span bounds + numeric "
            "match + content grounding) or was dropped. Citations are the report's._"
        )
        synth_block = "### Cross-source synthesis\n\n" + synth_label + "\n\n" + "\n".join(
            f"- {item.strip()}" for item in synth_items
        )
    blocks: list[str] = []
    if synth_block:
        blocks.append(synth_block)
    _cap = _max_key_findings_markers()
    for sr in sections or []:
        if getattr(sr, "dropped_due_to_failure", False):
            continue
        if getattr(sr, "is_gap_stub", False) or getattr(sr, "sentences_verified", 1) == 0:
            continue
        verified_text = _strip_leading_markdown_headers(getattr(sr, "verified_text", "") or "")
        if not verified_text.strip():
            continue
        ordered = _first_verified_sentences(verified_text, 10_000)
        if not ordered:
            continue
        title = getattr(sr, "title", "") or "Section"
        headline = cap_citation_marker_runs(ordered[0], _cap)
        lines = [f"### {title}", "", f"**Key Findings** {headline}"]
        # Lift a REAL challenge sentence (a verbatim verified sentence carrying a challenge cue) —
        # never fabricate one. Prefer one distinct from the headline.
        challenge = next(
            (s for s in ordered if _CHALLENGE_CUE_RE.search(s) and s != headline),
            "",
        )
        if challenge:
            lines.append(f"**Challenges** {cap_citation_marker_runs(challenge, _cap)}")
        # I-wire-012 (#1326): surface a REAL cross-source tension — a verbatim verified sentence
        # carrying a disagreement/opposition cue, distinct from the headline AND the challenge. Never
        # fabricated: if the section's own verified prose raises no opposition, no Tension line.
        tension = next(
            (s for s in ordered
             if _TENSION_CUE_RE.search(s) and s != headline and s != challenge),
            "",
        )
        if tension:
            lines.append(f"**Tension** {cap_citation_marker_runs(tension, _cap)}")
        blocks.append("\n".join(lines))
    if not blocks:
        return ""
    header = (
        "## Analytical synthesis\n\n"
        "_Per-section headline finding and (where the evidence itself raises one) a verbatim "
        "limitation/challenge — all carried up from cited, span-verified body prose; no new claim._\n\n"
    )
    return header + "\n\n".join(blocks) + "\n\n"
