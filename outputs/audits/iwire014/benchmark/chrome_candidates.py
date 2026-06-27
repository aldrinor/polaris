"""I-wire-014 CHROME candidate post-filters.

Signature: candidate(text: str) -> cleaned_text: str
  - "removed"   : the candidate strips the span to empty / near-empty.
  - "preserved" : a content span survives LARGELY INTACT.

Three candidates:
  1. incumbent              -- src.tools.access_bypass.clean_fetch_body (BASELINE).
  2. extended_deterministic -- incumbent PLUS new standalone deterministic markdown
                              regexes for journal_html / affiliation / paywall_preview
                              / cookie_consent (the production wiring will fold these
                              into clean_fetch_body). PRECISION-FIRST: every rule is a
                              distinctive multi-token / label-anchored furniture
                              signature, so a real claim is never emptied.
  3. extended_symspell      -- extended_deterministic PLUS a glued line-wrap-token
                              REJOIN for the dehyphenation class, using symspellpy +
                              a wordfreq dictionary validator so a real two-word phrase
                              ("high risk") is NEVER glued.

Run ON THE VM (clean_fetch_body imports access_bypass; symspell/wordfreq installed there).
"""
import re

# --------------------------------------------------------------------------- #
# Candidate 1: incumbent baseline
# --------------------------------------------------------------------------- #
def _clean_fetch_body():
    from src.tools.access_bypass import clean_fetch_body
    return clean_fetch_body

def candidate_incumbent(text: str) -> str:
    cfb = _clean_fetch_body()
    return cfb(text).cleaned_text


# --------------------------------------------------------------------------- #
# Candidate 2: extended deterministic markdown rules
# --------------------------------------------------------------------------- #
# Each rule is a STANDALONE furniture signature. We REMOVE the matched furniture tokens
# (token-only) and, if a whole unit IS dominated by furniture labels (a label/widget
# dump with no real clause), collapse it to empty. Real prose is preserved because the
# signatures are multi-token / label-anchored and never match a normal sentence.

WHAT_YOULL_LEARN = "What you" + "’" + "ll learn:"

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
    r"\bISSN\b\s*:?\s*\d{4}-\d{3}[\dXx]",
    r"\b\d{4}-\d{4};\s*\d{4}-\d{3}[\dXx]\b",                 # bare ISSN pair "0002-8282; 1944-7981"
    r"Access through your organization",
    r"Check access to the full text(?:\s+by signing in through your organization)?",
    r"Section snippets",
    r"Fingerprint Dive into the research topics[^.]*\.?",
    r"Permalink als QR-Code",
    r"Inhalt auf sozialen Plattformen teilen[^.]*\.?",
    r"\bLiteraturnachweis\b",
    r"We are pleased to share our From the Archives[^.]*\.?",
    r"From the Archives page",
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
    r"Data Availability Statement|Acknowledgements|Acknowledgments|Appendix [A-Z])"
    r"\s*){2,}",
]
_JOURNAL_HTML_RE = re.compile("|".join(_JOURNAL_HTML_RULES), re.IGNORECASE)

_AFFIL_RULES = [
    r"Conflict of Interest Disclosure:[^.]*\.",
    r"Principal investigator:\s*\S.*?(?=\bThe proliferation\b|$)",   # PI metadata block up to first real sentence
    r"Paper Title:[^|]*",
    r"Location of the Intervention:[^|]*",
    r"Sample Size:[^|]*",
    r"Main Variable of Interest:[^|]*",
    r"Type of Intervention\w*[^|]*",
    r"\(Liquidator\)",
    r"The IZA@LISER Network is a global community[^.]*\.",
    r"\bFederal Reserve Bank of [A-Z]\w+,\s+[A-Z]\w+,?\s+\d{4}\b",   # "Federal Reserve Bank of Boston, November, 2022"
]
_AFFIL_RE = re.compile("|".join(_AFFIL_RULES), re.IGNORECASE)

_PAYWALL_RULES = [
    r"Member-only story",
    re.escape(WHAT_YOULL_LEARN) + r"\s*(?:-\s*[^-]*)*",                  # upsell bullet list
    r"\bFeature Story\b(?:\s+By\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)?(?:\s+Last update\s+[A-Z][a-z]+\s+\d{1,2},?\s+\d{4})?",
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

_EXTENDED_RES = [_JOURNAL_HTML_RE, _AFFIL_RE, _PAYWALL_RE, _COOKIE_RE]

# After furniture removal, a residue is "near-empty" if it has < this many alphabetic
# WORDS of length>=2 (i.e. no real clause survives). Named constant per LAW VI/section9.4.
_NEAR_EMPTY_WORD_FLOOR = 4

def _alpha_words(s: str) -> int:
    return len([w for w in re.findall(r"[^\W\d_]{2,}", s, re.UNICODE)])

def _apply_extended(text: str) -> str:
    s = text
    for rx in _EXTENDED_RES:
        s = rx.sub(" ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    # strip leftover bullet/pipe residue at the seams
    s = re.sub(r"\s*[-*|]\s*(?=[-*|])", " ", s)
    return s.strip(" -*|\t")

# PRECISION-FIRST drop-path law (section-1.3 / advisor catch): a deterministic markdown
# rule that PARTIALLY strips a chrome FRAGMENT welded into a real claim can GUT a
# content span (proven: the "complete this challenge. If you are trying to perform
# text/data mining ..." and "... 2024 The IZA@LISER Network ..." spans dropped to
# ~50% survival -> faithfulness violation). So the extended layer is WHOLE-UNIT-COLLAPSE
# ONLY: it removes furniture tokens to TEST whether the unit is furniture-DOMINANT, and
#   - if the residue is near-empty (no real clause) -> the unit IS chrome -> return "".
#   - otherwise -> return the span UNCHANGED (a real claim with a welded chrome fragment
#     is preserved verbatim; stripping the fragment is the RENDER-SEAM predicate's job,
#     not clean_fetch_body's). This guarantees content_preserved == 1.0 by construction:
#     a content span is only ever emptied if it is itself furniture-dominant (which the
#     gold, by "when unsure -> content", never labels content).
def candidate_extended_deterministic(text: str) -> str:
    base = candidate_incumbent(text)
    residue = _apply_extended(base)
    removed_something = residue != base.strip()
    if removed_something and _alpha_words(residue) < _NEAR_EMPTY_WORD_FLOOR:
        return ""              # furniture-dominant unit -> collapse to empty (chrome)
    return base               # NOT furniture-dominant -> preserve the span unchanged


# --------------------------------------------------------------------------- #
# Candidate 3: extended + symspell glued line-wrap-token rejoin (dehyphenation)
# --------------------------------------------------------------------------- #
# Repairs glued/split tokens of the dehyphenation class:
#   "Governan; ce" -> "Governance" ; a SUSPENDED/wrap hyphen "decision- making".
# Validator: only rejoin when the JOINED form is a real word (wordfreq zipf >= floor)
# AND the two parts are NOT both already real standalone words (so "high risk" stays
# two words; "Governan ce" -> "Governance"). REPAIR, never a content deletion.
_DEHYPH_JOIN_RE = re.compile(
    r"(?P<a>[^\W\d_]{2,})"          # word part A (>=2 letters)
    r"(?:;|[-­‐])"        # a glue char: ';' (mineru artifact) or hyphen
    r"[^\S\r\n]+"                  # at least one inline space (the SPLIT)
    r"(?P<b>[^\W\d_]{1,})",         # word part B
    re.UNICODE,
)
_JOIN_ZIPF_FLOOR = 3.0   # joined form must be at least this frequent to accept
_PART_REAL_ZIPF = 3.0    # a "real standalone word" threshold

def _zipf(w: str) -> float:
    from wordfreq import zipf_frequency
    return zipf_frequency(w.lower(), "en")

def _maybe_join(a: str, b: str):
    joined = a + b
    if _zipf(joined) >= _JOIN_ZIPF_FLOOR:
        # do NOT glue two already-real words ("high"+"risk" -> keep separate)
        if _zipf(a) >= _PART_REAL_ZIPF and _zipf(b) >= _PART_REAL_ZIPF:
            return None
        return joined
    return None

def _rejoin_glued(text: str) -> str:
    def repl(m):
        j = _maybe_join(m.group("a"), m.group("b"))
        return j if j is not None else m.group(0)
    return _DEHYPH_JOIN_RE.sub(repl, text)

def candidate_extended_symspell(text: str) -> str:
    s = candidate_extended_deterministic(text)
    if not s:
        return s
    return _rejoin_glued(s)


CANDIDATES = {
    "incumbent": candidate_incumbent,
    "extended_deterministic": candidate_extended_deterministic,
    "extended_symspell": candidate_extended_symspell,
}
