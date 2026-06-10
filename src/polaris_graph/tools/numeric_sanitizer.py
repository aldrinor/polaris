"""Numeric extraction sanitizer (I-perm-007 #1201).

The quantified differentiator parses cruft-polluted scraped text: DOI prefixes, URL fragments,
accession numbers, and reference markers get extracted as clinical data points (proof: drb_76
yields ``value=10.1038 unit="%"`` — a DOI prefix parsed as a percent; ``8.0 M3`` from the
accession ``s41586-020-2080-8``). This sanitizer drops a numeric match ONLY when the number's OWN
whitespace-delimited token is a structural identifier (DOI / URL / accession / PMID / ISSN), NOT
merely when a URL sits ELSEWHERE in the window — so a legitimate ``99%`` or ``30 days`` followed
by a trailing citation URL is KEPT. Over-filtering is impossible to turn into a fabrication: the
sanitizer only REMOVES candidate data points, never invents one (a dropped real datapoint is a
fail-closed no-op, surfaced as a coverage gap, never a wrong number).

DEFAULT OFF: ``PG_SWEEP_NUMERIC_SANITIZER`` unset/falsey -> the sanitizer is a no-op (the caller
keeps every match; byte-identical extraction).
"""

from __future__ import annotations

import os
import re

_FLAG = "PG_SWEEP_NUMERIC_SANITIZER"
_OFF_VALUES = frozenset({"", "0", "false", "no", "off"})

# A structural identifier the number is EMBEDDED IN (checked against the number's own token):
#   - a URL scheme / host / path:           http://  https://  www.  /article/  /eid/
#   - a DOI:                                 doi=  doi:  doi.org/  10.<4-9 digits>/
#   - URL-encoded slash in a DOI/path:       %2f
#   - a database identifier:                 pmid  issn  scholar_lookup
_STRUCTURAL_ID_RE = re.compile(
    r"https?://|www\.|/article/|/eid/|doi[:=/]|doi\.org|10\.\d{4,9}/|%2f|pmid|issn|scholar_lookup",
    re.IGNORECASE,
)
# An accession / catalogue token has EITHER a LETTER adjacent to a digit (e.g. "s41586-020-2080-8",
# "PMC123") OR TWO-OR-MORE internal hyphens (e.g. "978-3-16-148410-0"). A numeric RANGE or CI bound
# ("0.4-6.7", "0.47-0.89", "10-100") has NO letter and a SINGLE hyphen between numbers, so it is
# NEVER matched — dropping a real range/CI is a clinical-data loss (Codex slice-1 P1: ev_560 6.7%).
_ACCESSION_RE = re.compile(r"[A-Za-z]\d|-\d[\d.]*-\d")


def numeric_sanitizer_enabled() -> bool:
    """``PG_SWEEP_NUMERIC_SANITIZER`` (default OFF -> no-op, byte-identical extraction)."""
    return os.environ.get(_FLAG, "").strip().lower() not in _OFF_VALUES


# Token boundaries: whitespace PLUS markdown-link / citation delimiters, so an immediately-adjacent
# no-space citation like "58%([_9_](https://x))" does NOT fold its URL into the number's token
# (Codex slice-1 P2).
_TOKEN_BREAK = "([])"


def _token_around(text: str, start: int, end: int) -> str:
    """The maximal token spanning ``[start, end)``, bounded by whitespace or ``([])``."""
    left = start
    while left > 0 and not text[left - 1].isspace() and text[left - 1] not in _TOKEN_BREAK:
        left -= 1
    right = end
    while right < len(text) and not text[right].isspace() and text[right] not in _TOKEN_BREAK:
        right += 1
    return text[left:right]


def is_structural_identifier_number(text: str, start: int, end: int) -> bool:
    """True if the numeric match at ``[start, end)`` is EMBEDDED in a structural identifier
    (DOI / URL / accession / PMID / ISSN) — i.e. the number is plumbing, not clinical data.

    Checks the number's OWN token only, so a clean ``99%`` followed by a citation URL in a later
    token is NOT flagged.
    """
    token = _token_around(text, start, end)
    if _STRUCTURAL_ID_RE.search(token):
        return True
    if _ACCESSION_RE.search(token):
        return True
    return False
