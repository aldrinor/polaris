"""I-wire-014 (#1334) FIX-B/C — shared deterministic page-furniture screen.

The benchmarked-SAFE winner (``extended_deterministic`` whole-unit-collapse) on the
real replay3 augmented gold: new-class chrome_removed 0.324 (~4x the incumbent) at
content_preserved_rate = 1.0. The decision is **whole-unit-collapse-ONLY**: furniture
tokens are stripped ONLY to TEST whether a unit is furniture-DOMINANT; if the residue is
near-empty the unit IS chrome (suppress), otherwise the unit is returned UNCHANGED. A real
claim with a welded chrome fragment is therefore never gutted (a partial inline strip — the
first design — dropped content_preserved to 0.9964 and was DISQUALIFIED). FLAG-not-drop /
§-1.3: the render seam WITHHOLDS the unit from the rollup; it never deletes evidence.

Generalizable, label-anchored furniture only. Clearly OVERFIT single-source literals from the
bake-off candidate (IZA@LISER, "Federal Reserve Bank of <City>, <Month>, <year>", "From the
Archives", J-PAL "Paper Title:/Location:/Sample Size:" metadata block) are DELIBERATELY EXCLUDED
from production — they are not generalizable signatures. DEDUP note: ISSN / "cite this paper" /
"number of pages" already live in weighted_enrichment's _SHARED_RENDER_CHROME_RE / _MASTHEAD_CHROME_RE.
"""
import re

_JOURNAL_HTML_RULES = [
    r"View All Journal Metrics",
    r"Publication usage\*?(?:\s+Total views and downloads:\s*[\d,]+)?",
    r"Total views and downloads:\s*[\d,]+",
    r"\*?Publication usage tracking started[^.]*\.?",
    r"Publications citing this one",
    r"Receive email alerts(?:\s+when this publication is cited)?",
    r"Web of Science:\s*\d+(?:\s+view articles)?(?:\s+Opens in new tab)?",
    r"Crossref:\s*\d+",
    r"References Biographies",
    r"\bCite\b(?:\s+Cite)+",
    r"Download to reference manager",
    r"If you have citation software installed[^.]*\.",
    r"Information,?\s+rights and permissions",
    r"Metrics and citations",
    r"\bJEL Classification\b",
    r"\bAssociated Records\b",
    r"Access through your organization",
    r"Check access to the full text(?:\s+by signing in through your organization)?",
    r"Section snippets",
    r"Fingerprint Dive into the research topics[^.]*\.?",
    r"Buy print copy",
    r"Tax calculation will be finalised(?:\s+at checkout)?",
    r"About this book",
    r"Part of the book series:[^.]*",
    r"Included in the following conference series:[^.]*",
    r"Conference proceedings info:[^.]*",
    # back-matter / housekeeping section-label runs (>=2 adjacent labels)
    r"(?:(?:CRediT authorship contribution statement|Author Contributions|Funding|"
    r"Declaration of competing interest|Conflicts? of Interest|Ethics declaration|"
    r"Institutional Review Board Statement|Informed Consent Statement|"
    r"Data Availability Statement|Acknowledgements|Acknowledgments|Appendix [A-Z]|"
    # I-deepfix-001 (#1344): widen the back-matter label set — these slipped the run and
    # left a >=4-word residue, so is_furniture_dominant returned False on a heading pile.
    r"Conclusions?|References|Supplementary (?:Materials?|Information)|Highlights|"
    r"Graphical Abstract|Keywords?|Abbreviations|Author Information|"
    r"How to cite(?: this article)?|Competing interests|Supporting Information|"
    r"Notes on contributors?|Disclosure statement)"
    r"\s*){2,}",
    # I-deepfix-001 (#1344): comparison/back-matter TABLE-HEADER row — >=3 pipe-delimited
    # short Title-Case cells (e.g. "| Authors | Article Title | Year | Lead Article vs.").
    r"(?:\|\s*[A-Z][^|]{0,40}){3,}\|?",
    # I-deepfix-001 (#1344): library-catalog / JS-gate scrape chrome (multilingual).
    r"Permalink(?:\s+als\s+QR-Code)?",
    r"\bQR-Code\b",
    r"Literaturnachweis",
    r"Inhaltsverzeichnis",
    r"nur vorhanden,?\s+wenn\s+Javascript\s+eingeschaltet(?:\s+ist)?",
    r"Javascript\s+eingeschaltet",
]
_JOURNAL_HTML_RE = re.compile("|".join(_JOURNAL_HTML_RULES), re.IGNORECASE)

_AFFIL_RULES = [
    r"Conflict of Interest Disclosure:[^.]*\.",
    r"\(Liquidator\)",
]
_AFFIL_RE = re.compile("|".join(_AFFIL_RULES), re.IGNORECASE)

_WHAT_YOULL_LEARN = "What you" + "’" + "ll learn:"
_PAYWALL_RULES = [
    r"Member-only story",
    re.escape(_WHAT_YOULL_LEARN) + r"\s*(?:-\s*[^-]*)*",
    r"\bFeature Story\b(?:\s+By\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)?"
    r"(?:\s+Last update\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})?",
]
_PAYWALL_RE = re.compile("|".join(_PAYWALL_RULES), re.IGNORECASE)

_COOKIE_RULES = [
    r"The content references language or the region that you are in[^.]*\.?",
    r"region that you are in",
    r"In order to better serve you and keep this site secure, please complete this challenge\.?",
    r"please complete this challenge",
    r"accept all cookies",
]
_COOKIE_RE = re.compile("|".join(_COOKIE_RULES), re.IGNORECASE)

# I-deepfix-002 (#1363) FIX-1 — author/date byline furniture welded to the front of a fetched body
# (drb_72 "August 30, 2023 **[By Jim Jones]** ..." [8]; "_Written by Jim McGwin, College of Business_"
# [14]). Obeys the whole-unit-collapse over-strip guard (is_furniture_dominant: suppress ONLY when the
# post-strip residue has < 4 real words) — a pure byline LINE collapses; a byline prefix welded to a real
# multi-clause claim keeps its >=4-word residue and is returned UNCHANGED. "By <Name>" is bounded to <=3
# capitalized tokens so "...found that, by March 2024, employment..." is never matched.
_BYLINE_RULES = [
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4}\s*\**\s*\[?\s*[Bb]y\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\s*\]?(?:\([^)\s]*\))?\s*\**",
    r"_?\b(?:Written|Posted|Reviewed|Edited|Authored|Reported|Compiled)\s+[Bb]y\s+"
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}(?:,\s+[A-Z][^_\n]{0,40})?_?",
]
_BYLINE_RE = re.compile("|".join(_BYLINE_RULES))

_FURNITURE_RES = [_JOURNAL_HTML_RE, _AFFIL_RE, _PAYWALL_RE, _COOKIE_RE, _BYLINE_RE]

# A residue is "near-empty" if it has < this many alphabetic words of length>=2 (no real clause).
_NEAR_EMPTY_WORD_FLOOR = 4

# Self-contained whole-line furniture: a LINE that, after furniture strip, is near-empty. Used by
# clean_fetch_body (whole-LINE removal only — never an inline partial strip of a welded fragment).


def _alpha_word_count(s: str) -> int:
    return len(re.findall(r"[^\W\d_]{2,}", s, re.UNICODE))


def _strip_furniture(text: str) -> str:
    s = text or ""
    for rx in _FURNITURE_RES:
        s = rx.sub(" ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\s*[-*|]\s*(?=[-*|])", " ", s)
    return s.strip(" -*|\t")


def is_furniture_dominant(text: str) -> bool:
    """True iff ``text`` is page-furniture-DOMINANT (the benchmarked whole-unit-collapse decision):
    a furniture token was removed AND the residue is near-empty (< _NEAR_EMPTY_WORD_FLOOR real
    words). A real claim with a welded fragment keeps its residue and returns False (preserved by
    construction). PURE."""
    base = (text or "").strip()
    if not base:
        return False
    residue = _strip_furniture(base)
    return residue != base and _alpha_word_count(residue) < _NEAR_EMPTY_WORD_FLOOR


def is_self_contained_furniture_line(line: str) -> bool:
    """True iff a WHOLE LINE is furniture (for clean_fetch_body whole-line removal). Same
    whole-unit-collapse test applied per line; never an inline partial strip. PURE."""
    return is_furniture_dominant(line)
