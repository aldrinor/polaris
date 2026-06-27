"""Deterministic post-render citation / truncation normalizer.

Scope (I-extract-001 Layer-B, the two classes NO extractor or LLM-judge can repair):

* **Class 4 - orphan citations.** Bare/leading bracket clusters that carry a
  reference but no claim of their own.  In the *real* rendered ``report.md`` they
  appear inline as a spurious sentence period wedged between two trailing
  citation clusters - ``...across the world.[8].[9][10] The deployment...`` (176
  such glues in the banked ``drb_72`` cert report; zero stand-alone bracket
  lines).  The ``.[9][10]`` is a render artifact: the references trail the SAME
  sentence, so collapsing ``].[`` -> ``][`` merges them onto that sentence and
  preserves attribution EXACTLY (no migration, no guess).  Multi-citation per
  claim is corroboration, not noise (CLAUDE.md SS-1.3).  The segmented/standalone
  forms named in the issue (bare ``[9][10]`` line, leading ``.[19][20] prose``)
  are also handled: their clusters migrate to the *immediately adjacent* prose
  line, and ONLY then - a blank gap / heading / table breaks ownership, so the
  unit is left in place and FLAGGED (never guessed, never deleted).

* **Class 3 - mid-word truncation.** A span cut glued with ``.; `` -
  ``aggregate statis.; bstitution``, ``employ.; ment``.  The two fragments are
  pieces of two DIFFERENT words ("statistics" + "substitution"), so no
  deterministic repair exists.  This detector therefore FLAGS only and leaves the
  text untouched (CLAUDE.md SS-1.3: when uncertain, leave it + flag).

Honest scope: only the ``.; `` glue is in scope here.  The other truncation
shapes in the substrate (end-of-text clause cuts, span cuts at the ``[N]``
marker boundary such as ``...le.[105]``) need a known-word basis - they live in
``scripts/iwire013_sec11_forensic_audit.py`` and the Layer-B LLM judge, NOT in
this pure-deterministic module.

The faithfulness engine is FROZEN and is not touched: this normalizer runs on the
rendered text downstream of it.  Pure deterministic (regex only); no LLM, no
network.  Every change is recorded as a :class:`NormalizationFlag`; nothing is
silently dropped.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --- canary -----------------------------------------------------------------
CANARY_TAG = "[citation_normalizer]"

# --- flag kinds (FLAG, never silently drop; CLAUDE.md SS-1.3) ----------------
FLAG_ORPHAN_INLINE_COLLAPSED = "orphan_inline_collapsed"
FLAG_ORPHAN_LINE_MIGRATED = "orphan_line_migrated"
FLAG_ORPHAN_UNATTACHED = "orphan_unattached"
FLAG_TRUNCATION_MIDWORD = "truncation_midword"

ACTION_REPAIRED = "repaired"
ACTION_FLAGGED = "flagged"

# --- pattern constants ------------------------------------------------------
# Orphan class 4, PRIMARY (real post-render) form: a citation cluster, a spurious
# sentence period, then another citation cluster with NO prose between them.
# ``[8].[9]`` -> ``[8][9]``: drops the artifact period, merging the trailing
# clusters onto the SAME sentence (attribution unchanged). The pattern is
# DIGIT-ANCHORED on both sides (lookbehind ``\d]`` / lookahead ``[\d``) so it only
# ever removes the spurious period BETWEEN two numeric citation clusters - a plain
# ``].[`` in code / array / JSON prose (``a[3].[index]``) is left untouched. The
# match is the lone period; the replacement is empty (delete it).
INLINE_ORPHAN_GLUE_PATTERN = re.compile(r"(?<=\d\])\.(?=\[\d)")
INLINE_ORPHAN_GLUE_REPLACEMENT = ""

# A single bracketed numeric citation token, e.g. ``[12]``.
CITATION_TOKEN_PATTERN = re.compile(r"\[\d{1,4}\]")

# Orphan class 4, segmented/standalone forms named in I-extract-001:
#   bare line     "[9][10]" / ".[19][20]"  (whole line = punctuation + clusters)
#   leading prose ".[19][20] The study ..." (line starts punct+clusters, then prose)
BARE_ORPHAN_LINE_PATTERN = re.compile(r"^[\s.,;:]*(?:\[\d{1,4}\][\s.,;:]*)+$")
LEADING_ORPHAN_PREFIX_PATTERN = re.compile(r"^(\s*[.,;:]\s*(?:\[\d{1,4}\]\s*)+)(\S.*)$")

# Optional markdown list marker stripped before inspecting a line body.
LIST_MARKER_PATTERN = re.compile(r"^(\s*(?:[-*+]|\d{1,3}[.)])\s+)(.*)$")

# Truncation class 3: the ``.; `` mid-word span-cut glue. The pre-glue token must
# be at least this long so short abbreviations ("et al.;", "etc.;", "cf.;") do not
# false-flag; the cut fragments in the artifact are always long ("statis", "employ").
MID_WORD_TRUNCATION_MIN_PREFIX_LEN = 4
MID_WORD_TRUNCATION_PATTERN = re.compile(
    r"[A-Za-z]{%d,}\.;\s*[a-z]+" % MID_WORD_TRUNCATION_MIN_PREFIX_LEN
)

# Width of context captured around an inline-glue repair for the audit flag.
_GLUE_CONTEXT_BEFORE = 6
_GLUE_CONTEXT_AFTER = 8

ALPHA_PATTERN = re.compile(r"[A-Za-z]")


@dataclass(frozen=True)
class NormalizationFlag:
    """One auditable normalizer action (repair or flag-for-review)."""

    line_index: int
    kind: str
    offending_span: str
    action: str


@dataclass
class NormalizationResult:
    """Outcome of :func:`normalize_citations_and_truncation`."""

    text: str
    flags: list[NormalizationFlag]
    line_count: int
    inline_collapsed: int
    orphan_migrated: int
    orphan_flagged: int
    truncation_flagged: int

    @property
    def changed(self) -> bool:
        """True iff any repair altered the text."""
        return bool(self.inline_collapsed or self.orphan_migrated)

    @property
    def canary(self) -> str:
        """Behavioral canary with real per-run counts."""
        return (
            f"{CANARY_TAG} lines={self.line_count} "
            f"inline_collapsed={self.inline_collapsed} "
            f"orphan_migrated={self.orphan_migrated} "
            f"orphan_flagged={self.orphan_flagged} "
            f"truncation_flagged={self.truncation_flagged}"
        )


def _split_list_marker(line: str) -> tuple[str, str]:
    """Split a line into its markdown list-marker prefix and the body."""
    match = LIST_MARKER_PATTERN.match(line)
    if match:
        return match.group(1), match.group(2)
    return "", line


def _is_prose_target(line: str) -> bool:
    """True iff ``line`` is real prose a migrated citation may attach to.

    Headings, table rows, blockquotes and bracket-only lines are not valid
    ownership targets, so a citation is never migrated onto them.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if stripped[0] in "#|>":
        return False
    if BARE_ORPHAN_LINE_PATTERN.match(stripped):
        return False
    return bool(ALPHA_PATTERN.search(stripped))


def _adjacent_prose_target(out_lines: list[str]) -> int | None:
    """Index of the immediately adjacent prose line, else ``None``.

    Only the nearest already-emitted non-blank line qualifies; a blank gap or a
    non-prose line (heading/table) breaks claim ownership -> no migration target
    (the orphan is then flagged-and-preserved, never guessed).
    """
    for idx in range(len(out_lines) - 1, -1, -1):
        candidate = out_lines[idx]
        if not candidate.strip():
            return None
        return idx if _is_prose_target(candidate) else None
    return None


def _collapse_inline_glue(
    line: str, line_index: int, flags: list[NormalizationFlag]
) -> tuple[str, int]:
    """Collapse every ``].[`` glue on a line to ``][``; record one flag each."""
    collapsed = 0
    while True:
        match = INLINE_ORPHAN_GLUE_PATTERN.search(line)
        if match is None:
            break
        start = max(0, match.start() - _GLUE_CONTEXT_BEFORE)
        end = min(len(line), match.end() + _GLUE_CONTEXT_AFTER)
        span = line[start:end]
        line = line[: match.start()] + INLINE_ORPHAN_GLUE_REPLACEMENT + line[match.end() :]
        collapsed += 1
        flags.append(
            NormalizationFlag(line_index, FLAG_ORPHAN_INLINE_COLLAPSED, span, ACTION_REPAIRED)
        )
    return line, collapsed


def normalize_citations_and_truncation(text: str) -> NormalizationResult:
    """Normalize orphan-citation and mid-word-truncation render artifacts.

    Args:
        text: the rendered report text (post-render, downstream of the frozen
            faithfulness engine).

    Returns:
        A :class:`NormalizationResult` carrying the normalized ``text``, the
        per-action audit ``flags``, and the behavioral counts surfaced in
        :attr:`NormalizationResult.canary`.
    """
    lines = text.split("\n")
    flags: list[NormalizationFlag] = []
    out_lines: list[str] = []
    inline_collapsed = 0
    orphan_migrated = 0
    orphan_flagged = 0
    truncation_flagged = 0

    for line_index, raw_line in enumerate(lines):
        # Stage 1: faithful same-sentence collapse of the inline ].[ glue.
        line, collapsed = _collapse_inline_glue(raw_line, line_index, flags)
        inline_collapsed += collapsed

        marker_prefix, body = _split_list_marker(line)
        body_stripped = body.strip()

        # Stage 2a: bare bracket-only line (no prose) -> migrate or flag.
        if body_stripped and BARE_ORPHAN_LINE_PATTERN.match(body_stripped) and not ALPHA_PATTERN.search(body_stripped):
            clusters = CITATION_TOKEN_PATTERN.findall(body_stripped)
            target = _adjacent_prose_target(out_lines)
            if target is not None:
                out_lines[target] = out_lines[target].rstrip() + "".join(clusters)
                flags.append(
                    NormalizationFlag(line_index, FLAG_ORPHAN_LINE_MIGRATED, body_stripped, ACTION_REPAIRED)
                )
                orphan_migrated += 1
                continue  # line collapsed away (its citations migrated)
            flags.append(
                NormalizationFlag(line_index, FLAG_ORPHAN_UNATTACHED, body_stripped, ACTION_FLAGGED)
            )
            orphan_flagged += 1
            out_lines.append(line)
            continue

        # Stage 2b: leading orphan prefix on otherwise-real prose -> migrate or flag.
        leading = LEADING_ORPHAN_PREFIX_PATTERN.match(body)
        if leading is not None and ALPHA_PATTERN.search(leading.group(2)):
            prefix, rest = leading.group(1), leading.group(2)
            clusters = CITATION_TOKEN_PATTERN.findall(prefix)
            target = _adjacent_prose_target(out_lines)
            if target is not None:
                out_lines[target] = out_lines[target].rstrip() + "".join(clusters)
                repaired_line = marker_prefix + rest
                flags.append(
                    NormalizationFlag(line_index, FLAG_ORPHAN_LINE_MIGRATED, prefix.strip(), ACTION_REPAIRED)
                )
                orphan_migrated += 1
                out_lines.append(repaired_line)
                truncation_flagged += _flag_truncation(repaired_line, line_index, flags)
                continue
            flags.append(
                NormalizationFlag(line_index, FLAG_ORPHAN_UNATTACHED, prefix.strip(), ACTION_FLAGGED)
            )
            orphan_flagged += 1
            out_lines.append(line)
            truncation_flagged += _flag_truncation(line, line_index, flags)
            continue

        # Stage 3: mid-word truncation -> flag only, text unchanged.
        out_lines.append(line)
        truncation_flagged += _flag_truncation(line, line_index, flags)

    result = NormalizationResult(
        text="\n".join(out_lines),
        flags=flags,
        line_count=len(lines),
        inline_collapsed=inline_collapsed,
        orphan_migrated=orphan_migrated,
        orphan_flagged=orphan_flagged,
        truncation_flagged=truncation_flagged,
    )
    logger.info(result.canary)
    return result


def _flag_truncation(line: str, line_index: int, flags: list[NormalizationFlag]) -> int:
    """Record a flag for every mid-word ``.; `` truncation span on a line."""
    count = 0
    for match in MID_WORD_TRUNCATION_PATTERN.finditer(line):
        flags.append(
            NormalizationFlag(line_index, FLAG_TRUNCATION_MIDWORD, match.group(0), ACTION_FLAGGED)
        )
        count += 1
    return count
