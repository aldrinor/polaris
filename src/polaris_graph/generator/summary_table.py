"""Deterministic, verified-only SUMMARY TABLE renderer (I-deepfix-001 P7, #1344).

Some research prompts explicitly ask the report to end with a summary TABLE and name
the exact column headers, e.g. drb_72:

    "... please create a summary table ... The table column headers should be
    "Research Literature", "Country/Region", "Application Area/Occupation",
    "Specific Applications and Impacts", and "Key Risks and Limitations"."

The multi-section generator produces span-verified narrative prose but does not emit
this requested GFM table, so ``report.md`` renders zero table rows and the DRB-II
"presentation" rubric fails on "article does not contain a summary table".

This module renders that table WITHOUT any LLM call, purely from ALREADY-verified
content, so it introduces NO new claim (CLAUDE.md §-1.3: a summary table is a
presentation of already-verified findings). Faithfulness contract:

* Every row is one CITED source that carries at least one strict-verify-passed claim.
* The "Research Literature" cell is bibliographic metadata (author / title / ``[N]``)
  drawn from the numbered bibliography — an identity, not a claim. Its source_title and
  authors are CHROME-SCREENED with the same predicate as the claim cell (a chrome /
  interstitial title or license/boilerplate author is dropped, the label falling back to a
  clean citation form) so no page furniture renders in the cell; the claim/row is kept.
* The "Specific Applications and Impacts" (claim-role) cell is the source's own
  verified sentence, verbatim (whitespace-normalised, excerpted with an ellipsis),
  carrying its ``[N]`` citation.
* The Country/Region, Application Area/Occupation and Key Risks cells surface ONLY
  short terms that appear VERBATIM in that source's verified spans (high-precision
  curated vocabularies). A cell with no verbatim match renders an em dash ``—`` — an
  honest DISCLOSED GAP; nothing is inferred or invented.

The faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding)
is UNTOUCHED — this reads the finished, verified bibliography + kept-sentence objects
and emits markdown. Behaviour is gated behind the default-ON kill-switch
``PG_RENDER_SUMMARY_TABLE`` (LAW VI); OFF => no table => byte-identical report.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

logger = logging.getLogger(__name__)

# --- canary / marker --------------------------------------------------------
CANARY_TAG = "[summary_table]"
# Distinctive idempotency marker embedded once in a rendered table (HTML comment,
# invisible in a markdown viewer). A resume / re-finalize that re-reads a report
# already carrying this marker is a no-op.
TABLE_MARKER = "<!-- polaris:summary_table -->"

# --- env kill-switch (default ON; LAW VI) -----------------------------------
_ENABLE_FLAG = "PG_RENDER_SUMMARY_TABLE"
_OFF_VALUES = frozenset({"0", "false", "off", "no", ""})

# --- disclosed-gap marker ---------------------------------------------------
GAP_CELL = "—"

# --- excerpt caps -----------------------------------------------------------
_CLAIM_CELL_MAX_CHARS = 220
_LITERATURE_TITLE_MAX_CHARS = 60
_MAX_TERMS_PER_CELL = 3

# --- provenance / citation tokens to strip from a claim sentence ------------
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
_NUM_MARKER_RE = re.compile(r"\[\d+\]")
_WS_RE = re.compile(r"\s+")

# --- header -> column ROLE ---------------------------------------------------
ROLE_LITERATURE = "literature"
ROLE_GEOGRAPHY = "geography"
ROLE_RISK = "risk"
ROLE_DOMAIN = "domain"
ROLE_CLAIM = "claim"
ROLE_GAP = "gap"

# Ordered so a header with several signals resolves to the most specific role.
# "Application Area/Occupation" hits DOMAIN (occupation/area) before CLAIM; "Specific
# Applications and Impacts" carries no DOMAIN token so it falls through to CLAIM.
_ROLE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (ROLE_LITERATURE, ("literature", "studies", "study", "reference", "paper",
                        "source", "author", "citation", "title", "research")),
    (ROLE_GEOGRAPHY, ("country", "countries", "region", "geograph", "nation",
                      "location", "jurisdiction")),
    (ROLE_RISK, ("risk", "limitation", "concern", "challenge", "caveat",
                 "weakness", "danger", "threat", "harm")),
    (ROLE_DOMAIN, ("occupation", "industry", "sector", "profession", "job",
                   "application area", "area", "domain", "field", "use case", "task")),
    (ROLE_CLAIM, ("application", "impact", "effect", "finding", "result", "use",
                  "contribution", "specific", "outcome", "evidence")),
)

# --- header-list detection cues (prompt asked for a table with named columns) -
# I-wire-001 F1 (missing-summary-table wiring): the cue also matches the run-bound
# paraphrase form "... with columns: <a>, <b>, ..." / a bare "columns: <a>, <b>, ..."
# so a prompt that names the headers AFTER a colon (no quotes) is still detected. The
# authoritative header source is the per-task output CONTRACT (threaded as
# ``contract_headers``); this parser is the belt-and-suspenders fallback.
_HEADER_CUE_RE = re.compile(
    r"(column\s+headers?|table\s+columns?|columns?\s+(?:should\s+be|are)|"
    r"headers?\s+(?:should\s+be|are)|with\s+columns?\s*:?|columns?\s*:)",
    re.IGNORECASE,
)
_SMART_QUOTED_RE = re.compile(r"“(.+?)”")
_STRAIGHT_QUOTED_RE = re.compile(r"\"(.+?)\"")
# Connector words that stay lowercase inside a header phrase when the belt-and-suspenders
# UNQUOTED fallback title-cases an all-lowercase header (so "specific applications and
# impacts" -> "Specific Applications and Impacts", never "... And ..."). A header that
# already carries its own casing is preserved verbatim (see :func:`_smart_titlecase`).
_UNQUOTED_HEADER_SMALL_WORDS = frozenset(
    {"and", "or", "of", "the", "in", "to", "a", "an", "for", "on", "with", "by"}
)
# The unquoted header list runs from the cue to the END of its sentence (first ``. `` /
# trailing period); a header list is comma-separated (with an optional ", and" before the
# last item), so we split on ',' ONLY — never on a bare " and " (which lives INSIDE a real
# header like "Specific Applications and Impacts").
_UNQUOTED_SENTENCE_END_RE = re.compile(r"\.(?:\s|$)")
_UNQUOTED_LEADING_AND_RE = re.compile(r"^and\s+", re.IGNORECASE)

# ---------------------------------------------------------------------------
# High-precision, curated verbatim vocabularies. A term is surfaced into a cell
# ONLY when it appears (word-ish, hyphen/whitespace-normalised) in that source's
# verified span text — so every surfaced token is grounded in verified evidence.
# ---------------------------------------------------------------------------
# Geography phrases matched CASE-INSENSITIVELY (full names + adjectives only; bare
# two-letter abbreviations are handled case-sensitively below to avoid matching the
# English pronoun "us"). This is a GENERAL, comprehensive world-economies set (NOT a
# benchmark-specific list): each entry is a (verbatim-phrase, canonical-display) pair,
# surfaced ONLY when the phrase appears as a WHOLE WORD in the source's own verified
# span (so "poland" is never read from "lapland"/"upland", "india" never from
# "indiana"/"indonesia"). Multi-word phrases use literal spaces; NO hyphenated geo
# phrases (the geography matcher does not hyphen-normalise). Display de-dup keeps the
# first-seen canonical form.
_GEO_PHRASES: tuple[tuple[str, str], ...] = (
    ("united states", "United States"),
    ("u.s.", "United States"),
    ("american workers", "United States"),
    ("canada", "Canada"),
    ("canadian", "Canada"),
    ("united kingdom", "United Kingdom"),
    ("britain", "United Kingdom"),
    ("british", "United Kingdom"),
    ("european union", "European Union"),
    ("europe", "Europe"),
    ("european", "Europe"),
    ("china", "China"),
    ("chinese", "China"),
    ("germany", "Germany"),
    ("german", "Germany"),
    ("france", "France"),
    ("india", "India"),
    ("japan", "Japan"),
    ("japanese", "Japan"),
    ("oecd", "OECD"),
    ("worldwide", "Global"),
    ("global economy", "Global"),
    ("developing countries", "Developing countries"),
    ("developed countries", "Developed countries"),
    # --- expanded general world-economies set (I-deepfix-001 vocab expansion) ---
    ("belgium", "Belgium"),
    ("belgian", "Belgium"),
    ("netherlands", "Netherlands"),
    ("poland", "Poland"),
    ("saudi arabia", "Saudi Arabia"),
    ("saudi arabian", "Saudi Arabia"),
    ("bahrain", "Bahrain"),
    ("bahraini", "Bahrain"),
    ("italy", "Italy"),
    ("italian", "Italy"),
    ("spain", "Spain"),
    ("spanish", "Spain"),
    ("portugal", "Portugal"),
    ("portuguese", "Portugal"),
    ("greece", "Greece"),
    ("ireland", "Ireland"),
    ("switzerland", "Switzerland"),
    ("austria", "Austria"),
    ("austrian", "Austria"),
    ("sweden", "Sweden"),
    ("swedish", "Sweden"),
    ("norway", "Norway"),
    ("norwegian", "Norway"),
    ("denmark", "Denmark"),
    ("finland", "Finland"),
    ("finnish", "Finland"),
    ("iceland", "Iceland"),
    ("icelandic", "Iceland"),
    ("hungary", "Hungary"),
    ("hungarian", "Hungary"),
    ("romania", "Romania"),
    ("romanian", "Romania"),
    ("ukraine", "Ukraine"),
    ("ukrainian", "Ukraine"),
    ("russia", "Russia"),
    ("russian", "Russia"),
    ("turkish", "Turkey"),
    ("israel", "Israel"),
    ("israeli", "Israel"),
    ("qatar", "Qatar"),
    ("qatari", "Qatar"),
    ("kuwait", "Kuwait"),
    ("kuwaiti", "Kuwait"),
    ("united arab emirates", "United Arab Emirates"),
    ("emirati", "United Arab Emirates"),
    ("australia", "Australia"),
    ("australian", "Australia"),
    ("new zealand", "New Zealand"),
    ("south korea", "South Korea"),
    ("singapore", "Singapore"),
    ("singaporean", "Singapore"),
    ("taiwan", "Taiwan"),
    ("taiwanese", "Taiwan"),
    ("hong kong", "Hong Kong"),
    ("malaysia", "Malaysia"),
    ("malaysian", "Malaysia"),
    ("thailand", "Thailand"),
    ("vietnam", "Vietnam"),
    ("vietnamese", "Vietnam"),
    ("philippines", "Philippines"),
    ("filipino", "Philippines"),
    ("pakistan", "Pakistan"),
    ("pakistani", "Pakistan"),
    ("bangladesh", "Bangladesh"),
    ("bangladeshi", "Bangladesh"),
    ("brazil", "Brazil"),
    ("brazilian", "Brazil"),
    ("mexico", "Mexico"),
    ("mexican", "Mexico"),
    ("argentina", "Argentina"),
    ("argentine", "Argentina"),
    ("argentinian", "Argentina"),
    ("chilean", "Chile"),
    ("colombia", "Colombia"),
    ("colombian", "Colombia"),
    ("south africa", "South Africa"),
    ("south african", "South Africa"),
    ("nigeria", "Nigeria"),
    ("nigerian", "Nigeria"),
    ("egypt", "Egypt"),
    ("egyptian", "Egypt"),
    ("kenya", "Kenya"),
    ("kenyan", "Kenya"),
    ("scandinavia", "Scandinavia"),
    ("scandinavian", "Scandinavia"),
    ("nordic countries", "Nordic countries"),
    ("latin america", "Latin America"),
    ("latin american", "Latin America"),
    ("middle east", "Middle East"),
    ("middle eastern", "Middle East"),
    ("southeast asia", "Southeast Asia"),
    ("asia", "Asia"),
    ("africa", "Africa"),
)
# Case-SENSITIVE standalone uppercase abbreviations. Each entry is a regex BODY that is
# whole-token bounded by :func:`_word_boundary_search` (lookaround), so "US" never matches
# inside "GAUSS"/"USA" and "U.S." never matches inside "U.S.A".
_GEO_ABBREV: tuple[tuple[str, str], ...] = (
    ("US", "United States"),
    (r"U\.S\.", "United States"),
    ("UK", "United Kingdom"),
    ("EU", "European Union"),
)
# Occupation / application-area phrases (case-insensitive, high precision). GENERAL,
# comprehensive occupation/sector set; each surfaced ONLY when it appears as a WHOLE
# WORD in the source's own verified span. No overlap-hazard bare tokens (e.g. no bare
# "hr"/"it"); the full phrase "human resources"/"information technology" is used instead.
_DOMAIN_PHRASES: tuple[str, ...] = (
    "customer-support", "customer support", "customer service", "call center",
    "call centre", "software developer", "software engineer", "programmer",
    "programming", "manufacturing", "knowledge work", "knowledge worker",
    "freelancer", "freelance", "content creation", "translation", "translator",
    "recruiting", "recruitment", "radiology", "radiologist", "paralegal",
    "legal profession", "clerical", "administrative support", "construction",
    "mining", "consulting", "graphic design", "journalism", "journalist",
    "customer-support agents",
    # --- expanded general occupation / application-area set ---
    "scientific writing", "academic writing", "technical writing", "medical writing",
    "oral radiology", "maxillofacial radiology", "dental education", "dentistry",
    "medical research", "medical education", "clinical practice",
    "healthcare", "health care", "nursing", "nurse", "physician", "pharmacy",
    "pharmacist", "public health", "mental health",
    "organizational change", "organisational change", "change management",
    "project management", "human resources", "human resource management",
    "hiring", "talent acquisition", "performance management",
    "employer flexibility", "remote work", "hybrid work", "work from home",
    "telework", "office work", "office workspace", "office worker",
    "administrative work", "data entry", "data analysis", "data science",
    "data analytics", "skills training", "job training", "vocational training",
    "on-the-job training", "workforce training", "professional development",
    "education", "teaching", "teacher", "higher education", "e-learning",
    "finance", "financial services", "banking", "accounting", "accountant",
    "auditing", "insurance", "marketing", "advertising", "sales",
    "customer relations", "agriculture", "farming", "logistics", "supply chain",
    "transportation", "transport", "warehousing", "warehouse", "retail",
    "retailer", "e-commerce", "hospitality", "tourism", "engineering",
    "research and development", "content writing", "copywriting", "editing",
    "proofreading", "customer experience", "information technology",
    "cybersecurity", "data management",
)
# Risk / limitation themes (case-insensitive, high precision). GENERAL, comprehensive
# risk/limitation set; each surfaced ONLY when it appears as a WHOLE WORD in the
# source's own verified span. Whole-word matching keeps precision (e.g. "bias" is never
# read from "biased", "cost" never from "costume").
_RISK_PHRASES: tuple[str, ...] = (
    "displacement", "displace", "job loss", "unemployment", "substitution",
    "inequality", "polarization", "polarisation", "discrimination",
    "algorithmic bias", "privacy", "surveillance", "misinformation",
    "hallucination", "deskilling", "reskilling", "retraining", "job insecurity",
    "wage decline", "ethical concerns", "labor displacement",
    # --- expanded general risk / limitation set ---
    # NOTE: only RISK-FRAMED phrases live here. Neutral/positive-polarity tokens
    # ("reliability", "accuracy", "transparency", "governance", "compliance", "cost",
    # "safety", "well-being", ...) were pruned (Codex P2): they name goals/mechanisms,
    # not risks, and read wrong in a "Key Risks and Limitations" cell. Their risk-FRAMED
    # forms ("lack of transparency", "high cost", "worker safety", "well-being harm",
    # "data security") are retained.
    "bias", "gender bias", "racial bias", "implicit bias",
    "algorithmic discrimination", "data privacy", "data protection",
    "data security", "lack of transparency",
    "inaccuracy", "error rate", "plagiarism", "copyright",
    "copyright infringement", "intellectual property",
    "ethical issues", "ethical concern", "high cost",
    "implementation cost", "skill gap", "skills gap", "skill mismatch",
    "job security", "job displacement", "over-reliance", "overreliance",
    "automation bias", "autonomy loss", "loss of autonomy",
    "well-being harm", "burnout", "worker safety",
    "manipulation", "fraud", "toxicity", "harmful content",
    "misuse", "dependence",
)


# Built-in fallback chrome/interstitial screen (CAPTCHA walls, JS/cookie interstitials,
# masthead/copyright furniture) used ONLY when the caller injects no ``chrome_screen``.
# In production the sweep injects the pipeline's canonical
# ``weighted_enrichment.is_render_chrome_or_unrenderable`` so the table drops exactly the
# same page furniture the render-seam already stripped from the body — a chrome
# interstitial is not a research finding, so excluding it is faithfulness-neutral and the
# source still lives in the numbered bibliography (NOT a §-1.3 corpus drop).
_DEFAULT_CHROME_RE = re.compile(
    r"just a moment"
    r"|complete the security check"
    r"|security check to access"
    r"|verify you are (?:a )?human"
    r"|are you a robot"
    r"|enable javascript|javascript is (?:disabled|required)"
    r"|cloudflare|\bray id\b|\bcaptcha\b"
    r"|access denied|please enable cookies"
    r"|all rights reserved"
    r"|\]\(https?://"            # a markdown link to a URL (scraped nav / blog-post chrome)
    r"|#author"                  # author-box anchor fragment
    r"|category:\s*articles",    # masthead category line
    re.IGNORECASE,
)


def _default_chrome_screen(text: str) -> bool:
    """True when ``text`` is a chrome/interstitial fragment rather than a research claim.
    PURE. Conservative — real prose that merely mentions e.g. "security" is not caught."""
    return bool(_DEFAULT_CHROME_RE.search(text or ""))


@dataclass
class _RowData:
    num: int
    literature: str
    claim: str
    claim_truncated: bool
    geography: list[str]
    domain: list[str]
    risk: list[str]
    # Source-consolidation bookkeeping (I-deepfix-001 UNIT-2). ``doc_key`` is the row's
    # normalized source-document identity (see :func:`_doc_identity`); an EMPTY key is never
    # consolidated. ``cite_nums`` is the multi-citation set carried on the row — a singleton
    # holds ``[num]``; a consolidated cluster holds the sorted union of ALL member ``[N]``s
    # (consolidate-keep-all: every eid stays cited). ``num`` remains the sort key.
    doc_key: str = ""
    cite_nums: list[int] = field(default_factory=list)


@dataclass
class SummaryTableResult:
    text: str
    changed: bool
    canary: str = ""
    rows: int = 0
    headers: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Enablement / parsing helpers
# ---------------------------------------------------------------------------
def summary_table_enabled() -> bool:
    """LAW VI kill-switch (default ON). OFF => no table => byte-identical report."""
    return os.environ.get(_ENABLE_FLAG, "1").strip().lower() not in _OFF_VALUES


def _smart_titlecase(phrase: str) -> str:
    """Title-case an ALL-lowercase header phrase (keeping connector words lowercase after
    the first word); a phrase that ALREADY carries any uppercase letter is returned
    VERBATIM (so "Country/Region" / "Specific Applications and Impacts" are preserved
    byte-for-byte and never mangled by a naive ``str.title``). PURE."""
    phrase = phrase.strip()
    if not phrase or any(c.isupper() for c in phrase):
        return phrase
    words = phrase.split()
    out: list[str] = []
    for i, w in enumerate(words):
        if i > 0 and w in _UNQUOTED_HEADER_SMALL_WORDS:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def parse_requested_headers(research_question: str) -> list[str]:
    """The exact column headers the prompt requests, or ``[]`` when the prompt does
    not ask for a titled summary table. Detection is CUE-anchored (a "column
    headers"/"columns should be"/"with columns:" phrase) so ordinary quoted text
    elsewhere in the prompt is never mistaken for a header list. Handles smart and
    straight quotes, then an UNQUOTED comma-list fallback (I-wire-001 F1). PURE."""
    if not research_question:
        return []
    cue = _HEADER_CUE_RE.search(research_question)
    if not cue:
        return []
    # Window from the cue to the end of its sentence/paragraph (bounded).
    start = cue.end()
    tail = research_question[start:start + 800]
    # Stop at a hard paragraph break if one occurs inside the window.
    para = tail.find("\n\n")
    if para != -1:
        tail = tail[:para]
    smart = [h.strip() for h in _SMART_QUOTED_RE.findall(tail) if h.strip()]
    if len(smart) >= 2:
        return smart
    straight = [h.strip() for h in _STRAIGHT_QUOTED_RE.findall(tail) if h.strip()]
    if len(straight) >= 2:
        return straight
    # I-wire-001 F1 — UNQUOTED fallback (belt-and-suspenders; the CONTRACT path is
    # primary). The cue matched but quote-extraction found < 2 header names, so the
    # prompt named the headers as a plain comma list ("... with columns: A, B, C, and
    # D."). Bound to the cue's SENTENCE, split on ',' ONLY (a bare " and " lives inside a
    # real header), drop a leading ", and", strip a trailing period, smart-title-case.
    sentence_end = _UNQUOTED_SENTENCE_END_RE.search(tail)
    sentence_tail = tail[: sentence_end.start()] if sentence_end else tail
    unquoted: list[str] = []
    for raw in sentence_tail.split(","):
        piece = _UNQUOTED_LEADING_AND_RE.sub("", raw.strip()).strip().rstrip(".").strip()
        if piece:
            unquoted.append(_smart_titlecase(piece))
    if len(unquoted) >= 2:
        return unquoted
    return []


def _classify_header(header: str) -> str:
    low = header.strip().lower()
    for role, keywords in _ROLE_KEYWORDS:
        if any(kw in low for kw in keywords):
            return role
    return ROLE_GAP


def assign_header_roles(headers: list[str]) -> list[str]:
    """Map each requested header to a column ROLE, then guarantee EXACTLY ONE
    claim-role column carries the verified sentence: if several headers classify as
    CLAIM only the first keeps it (the rest become disclosed-gap columns); if none
    classify as CLAIM the last non-literature column is promoted so the verified
    finding always has a home. PURE."""
    roles = [_classify_header(h) for h in headers]
    claim_idxs = [i for i, r in enumerate(roles) if r == ROLE_CLAIM]
    if claim_idxs:
        for i in claim_idxs[1:]:
            roles[i] = ROLE_GAP
    else:
        # Promote the last non-literature column (or the last column) to CLAIM.
        promote = None
        for i in range(len(roles) - 1, -1, -1):
            if roles[i] != ROLE_LITERATURE:
                promote = i
                break
        if promote is None and roles:
            promote = len(roles) - 1
        if promote is not None:
            roles[promote] = ROLE_CLAIM
    return roles


# ---------------------------------------------------------------------------
# Verified-content extraction
# ---------------------------------------------------------------------------
def extract_section_claims(sections: Iterable[Any]) -> list[dict]:
    """Flatten the multi-section generator's kept, span-verified sentences into a
    simple, testable list of ``{"evidence_id", "sentence", "span_verdict",
    "is_verified"}`` rows. Duck-typed (``getattr``) so a fake object or a plain dict
    works in tests. Only sentences whose FIRST provenance token names a source are
    kept (that first token is the sentence's primary citation). PURE."""
    out: list[dict] = []
    for sr in sections or []:
        if getattr(sr, "dropped_due_to_failure", False):
            continue
        kept = getattr(sr, "kept_sentences_pre_resolve", None)
        if kept is None and isinstance(sr, dict):
            kept = sr.get("kept_sentences_pre_resolve")
        for sv in kept or []:
            sentence = _get(sv, "sentence", "")
            if not sentence:
                continue
            eid = _primary_evidence_id(sv)
            if not eid:
                continue
            out.append({
                "evidence_id": eid,
                "sentence": sentence,
                "span_verdict": _get(sv, "span_verdict", ""),
                "is_verified": bool(_get(sv, "is_verified", False)),
            })
    return out


def _get(obj: Any, name: str, default: Any) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _primary_evidence_id(sv: Any) -> str:
    tokens = _get(sv, "tokens", None) or []
    for tok in tokens:
        eid = str(_get(tok, "evidence_id", "") or "")
        if eid:
            return eid
    # Fallback: parse a [#ev:<id>:..] token from the sentence text itself.
    m = re.search(r"\[#ev:([^:\]]+):", str(_get(sv, "sentence", "") or ""))
    return m.group(1) if m else ""


def _clean_claim_text(sentence: str) -> str:
    text = _EV_TOKEN_RE.sub("", sentence or "")
    text = _NUM_MARKER_RE.sub("", text)
    text = _WS_RE.sub(" ", text).strip()
    return text


def _excerpt(text: str, max_chars: int) -> tuple[str, bool]:
    """Word-boundary excerpt of ``text`` to ``max_chars``. Returns (excerpt,
    truncated). Never splits mid-word on the trailing edge. PURE."""
    if len(text) <= max_chars:
        return text, False
    cut = text[:max_chars]
    sp = cut.rfind(" ")
    if sp > int(max_chars * 0.6):
        cut = cut[:sp]
    return cut.rstrip(" ,;:"), True


# Page-furniture / chrome signals that make an otherwise-verified span read badly in a
# table cell. Used ONLY to RANK already-verified candidate sentences (never to drop a
# source) — choosing the cleanest verified sentence to display is faithfulness-neutral.
_CHROME_SIGNALS: tuple[str, ...] = (
    "http", "](", "#author", "blog post", "category:", "cookie", "login",
    "©", "volume ", "all rights reserved", "click here", "see this",
)


def _claim_quality(clean: str) -> tuple[int, int, int]:
    """Ranking key for a cleaned verified sentence (higher is better): prefer a clean
    prose start with no chrome signal, then a quantitative sentence, then a longer one.
    PURE."""
    low = clean.lower()
    chrome = any(sig in low for sig in _CHROME_SIGNALS)
    first = clean[:1]
    clean_start = (first.isalpha() and first.isupper()) or first in "“\"'"
    if clean_start and not chrome:
        tier = 2
    elif not chrome:
        tier = 1
    else:
        tier = 0
    has_num = 1 if re.search(r"\d", clean) else 0
    return (tier, has_num, min(len(clean), 400))


def _pick_best_claim(sentences: list[str]) -> str:
    """Deterministically pick the cleanest, most impact-bearing verified sentence for a
    source (see :func:`_claim_quality`); stable tie-break by original order. Every
    candidate is already span-verified, so this only chooses which verified sentence to
    DISPLAY — it never admits an unverified claim. PURE."""
    best = ""
    best_key: tuple[int, int, int, int] = (-1, -1, -1, 1)
    for idx, s in enumerate(sentences):
        clean = _clean_claim_text(s)
        if not clean:
            continue
        tier, has_num, length = _claim_quality(clean)
        key = (tier, has_num, length, -idx)
        if key > best_key:
            best_key = key
            best = clean
    return best


# ---------------------------------------------------------------------------
# Source consolidation (I-deepfix-001 UNIT-2). Multiple rows that are the SAME source
# document restating the SAME verified finding collapse into ONE multi-citation row —
# CONSOLIDATE-KEEP-ALL (CLAUDE.md §-1.3): every source stays cited, none is dropped. This
# touches ONLY row grouping/presentation; the faithfulness engine is untouched (each row
# already carries a strict-verify-passed claim). Distinct number-sets from the SAME document
# stay SEPARATE rows (a real second finding is never merged away).
# ---------------------------------------------------------------------------
_SOURCE_CONSOLIDATE_FLAG = "PG_SUMMARY_TABLE_SOURCE_CONSOLIDATE"
_CONSOLIDATE_JACCARD_ENV = "PG_SUMMARY_TABLE_CONSOLIDATE_JACCARD"
_CONSOLIDATE_JACCARD_DEFAULT = 0.6
# I-deepfix-001 (#1369) FIX 5 — a STRICTER Jaccard bar applied ONLY when BOTH
# claims are NUMBERLESS (empty salient-number set). A numberless qualitative
# claim has no numeric discriminator, so two DISTINCT findings that merely share
# vocabulary could pass the 0.6 bar and lose a real second row. Requiring a much
# higher overlap (default 0.85) keeps distinct numberless findings SEPARATE.
_NUMBERLESS_JACCARD_ENV = "PG_SUMMARY_TABLE_NUMBERLESS_JACCARD"
_NUMBERLESS_JACCARD_DEFAULT = 0.85

# Salient numeric tokens (percentages / decimals / integers). Two rows can consolidate ONLY
# when they carry the IDENTICAL salient-number set, so "43%" and "2.5% of GDP" never merge.
_NUM_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)?%?")

# A small, local stopword set for the claim-token Jaccard overlap (LAW VI: no external dep).
_CONSOLIDATE_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by", "for", "from",
    "had", "has", "have", "in", "into", "is", "it", "its", "of", "on", "or", "over", "per",
    "that", "the", "their", "them", "then", "these", "they", "this", "those", "to", "was",
    "were", "which", "who", "whose", "with", "we", "our", "not", "no", "than", "such", "also",
    "between", "across", "under", "about", "after", "before", "during", "while",
})


def _doc_identity(b: dict) -> str:
    """Normalized SOURCE-DOCUMENT identity for a bibliography row. Prefers the URL host+path
    (``url`` or ``source_url``, lowercased, scheme/query/fragment/trailing-slash stripped);
    falls back to the lowercased whitespace-normalized ``source_title``/``statement``. Returns
    ``""`` when neither is present — an empty key is NEVER consolidated (fail-closed: a row with
    no identifiable document stays its own row). PURE."""
    if not isinstance(b, dict):
        return ""
    url = str(b.get("url") or b.get("source_url") or "").strip().lower()
    if url:
        url = re.sub(r"^[a-z][a-z0-9+.\-]*://", "", url)  # strip scheme
        url = url.split("?", 1)[0].split("#", 1)[0]        # strip query + fragment
        url = url.rstrip("/")
        if url:
            return url
    title = str(b.get("source_title") or b.get("statement") or "").strip().lower()
    return _WS_RE.sub(" ", title).strip()


def _salient_numbers(clean: str) -> frozenset[str]:
    """The set of salient numeric tokens (percentages / decimals / integers) in a cleaned claim.
    The consolidation gate requires an EXACT match of this set, so two different quantitative
    findings from one document (e.g. "43%" vs "2.5% of GDP") are NEVER merged. PURE."""
    return frozenset(_NUM_TOKEN_RE.findall(clean or ""))


def _claim_tokens(clean: str) -> frozenset[str]:
    """Lowercased content-word token set of a cleaned claim, minus the local stopword set. Used
    for the Jaccard overlap half of :func:`_same_finding`. PURE."""
    out: set[str] = set()
    for raw in re.split(r"\s+", (clean or "").lower()):
        tok = raw.strip(".,;:!?()[]{}\"'`—–…%")
        if not tok or tok in _CONSOLIDATE_STOPWORDS:
            continue
        out.add(tok)
    return frozenset(out)


def _consolidate_jaccard() -> float:
    """The claim-token Jaccard threshold for consolidation (env ``PG_SUMMARY_TABLE_CONSOLIDATE_
    JACCARD``, default 0.6; LAW VI). FAIL-LOUD parse: a malformed value is logged at WARNING (not
    swallowed silently) and the documented safe default 0.6 is used; a parsed value is clamped to
    ``[0.0, 1.0]``."""
    raw = os.environ.get(_CONSOLIDATE_JACCARD_ENV)
    if raw is None or raw.strip() == "":
        return _CONSOLIDATE_JACCARD_DEFAULT
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "[activation] summary_table_source_consolidate: invalid %s=%r; using default %.2f",
            _CONSOLIDATE_JACCARD_ENV, raw, _CONSOLIDATE_JACCARD_DEFAULT,
        )
        return _CONSOLIDATE_JACCARD_DEFAULT
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def _numberless_consolidate_jaccard() -> float:
    """The STRICTER claim-token Jaccard threshold applied when BOTH claims are
    NUMBERLESS (env ``PG_SUMMARY_TABLE_NUMBERLESS_JACCARD``, default 0.85; LAW
    VI). Same fail-loud parse + ``[0.0, 1.0]`` clamp as :func:`_consolidate_jaccard`.
    A numberless claim has no numeric discriminator, so consolidating two such
    claims demands a much higher vocabulary overlap before they are treated as
    the SAME finding — otherwise a distinct qualitative row is silently lost."""
    raw = os.environ.get(_NUMBERLESS_JACCARD_ENV)
    if raw is None or raw.strip() == "":
        return _NUMBERLESS_JACCARD_DEFAULT
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "[activation] summary_table_source_consolidate: invalid %s=%r; using default %.2f",
            _NUMBERLESS_JACCARD_ENV, raw, _NUMBERLESS_JACCARD_DEFAULT,
        )
        return _NUMBERLESS_JACCARD_DEFAULT
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return val


def _source_consolidate_enabled() -> bool:
    """LAW VI kill-switch for source consolidation (default ON). OFF => rows pass through
    unchanged (byte-identical to the one-row-per-eid behaviour)."""
    return os.environ.get(_SOURCE_CONSOLIDATE_FLAG, "1").strip().lower() not in _OFF_VALUES


def _same_finding(a: str, b: str) -> bool:
    """True iff two cleaned claim strings state the SAME finding: IDENTICAL salient-number set
    AND claim-token Jaccard overlap >= the configured threshold. Both halves must hold, so a
    different quantitative result is never merged even when the surrounding prose is similar.
    PURE."""
    sa, sb = _salient_numbers(a), _salient_numbers(b)
    if sa != sb:
        return False
    ta, tb = _claim_tokens(a), _claim_tokens(b)
    if not ta and not tb:
        return True
    if not ta or not tb:
        return False
    jaccard = len(ta & tb) / len(ta | tb)
    # I-deepfix-001 (#1369) FIX 5 — a NUMBERLESS-vs-NUMBERLESS pair (both empty
    # salient-number sets) has no numeric discriminator, so it must clear the
    # STRICTER threshold; a numbered pair keeps the standard bar.
    threshold = (
        _numberless_consolidate_jaccard() if not sa else _consolidate_jaccard()
    )
    return jaccard >= threshold


def _union_terms(term_lists: Iterable[list[str]]) -> list[str]:
    """Order-stable, case-insensitive-deduped union of curated cell terms across cluster members,
    capped at ``_MAX_TERMS_PER_CELL``. Each input term is ALREADY verbatim-verified for its own
    source, so the union only surfaces already-verified terms (never fabricates). PURE."""
    seen: set[str] = set()
    out: list[str] = []
    for terms in term_lists:
        for t in terms or []:
            key = t.lower()
            if key not in seen:
                seen.add(key)
                out.append(t)
    return out[:_MAX_TERMS_PER_CELL]


# I-deepfix-001 (#1369) FIX 1 — summary-table duplicate rows (10/36 rows in box-2 were dups of 3 docs:
# SERBE×6, Deloitte [10][11], laweconcenter [25][26]). Root cause (Fable): (a) doc_key splits the SAME
# document across a URL-keyed row and title-keyed rows (blank-URL bibliography entries), so they never
# unite; (b) _same_finding's Jaccard>=0.6 bar rejects the composer's synonym-swap paraphrases (0.53-0.56).
# A SECOND additive pass groups the FINAL rows by their VISIBLE source label (Literature minus trailing
# [N] citations) and merges, within a label, rows with an identical non-empty salient-number set OR high
# claim-token CONTAINMENT — catching URL-vs-title splits and paraphrases without lowering the primary bar.
# CONSOLIDATE-KEEP-ALL: every citation survives on the merged row. Default-ON PG_SUMMARY_TABLE_LABEL_REGROUP.
_LABEL_CITE_SUFFIX_RE = re.compile(r"(?:\s*\[\d+\])+\s*$")
_ENV_LABEL_REGROUP = "PG_SUMMARY_TABLE_LABEL_REGROUP"
_REGROUP_CONTAINMENT_WITH_NUMBERS = 0.60  # even with an identical number set, require real token overlap
# I-deepfix-001 (#1369) iter2 (Codex + Fable P2): a NUMBERLESS pair has no numeric discriminator, so the
# label-regroup second pass must clear the SAME strict bar as the first-pass numberless Jaccard (0.85),
# not 0.60 — else two DISTINCT same-label qualitative findings at 60% containment over-merge and a real
# second finding is lost from the table (§-1.3 no-drop). Number-matched pairs keep the 0.60 bar (the
# identical salient-number set is the real discriminator there).
_REGROUP_CONTAINMENT_NUMBERLESS = 0.85


def _merge_cluster(cluster: list[_RowData]) -> _RowData:
    """Collapse a >=2-member same-document same-finding cluster into ONE multi-citation row.
    ``num`` = min member num (stable sort anchor); ``cite_nums`` = sorted union of ALL members'
    citations (CONSOLIDATE-KEEP-ALL — every eid stays cited); claim = cleanest member claim; the
    curated cells = order-stable capped union; literature = the min-num member's author+title base
    followed by ALL ``[N]`` citations. PURE."""
    ordered = sorted(cluster, key=lambda r: r.num)
    min_row = ordered[0]
    cite_nums = sorted({n for m in ordered for n in (m.cite_nums or [m.num])})
    best_claim = _pick_best_claim([m.claim for m in ordered])
    rep = min_row
    for m in ordered:
        if _clean_claim_text(m.claim) == best_claim:
            rep = m
            break
    # I-deepfix-001 (#1369) FIX 1: strip ALL trailing [N] citations (robust to an already-consolidated
    # multi-cite row entering the label-regroup second pass), then re-append the full keep-all set. For a
    # single-cite row "X [8]" this is byte-identical to the prior single-suffix strip.
    base = _LABEL_CITE_SUFFIX_RE.sub("", min_row.literature).rstrip()
    literature = base + "".join(f"[{n}]" for n in cite_nums)
    return _RowData(
        num=min_row.num,
        literature=literature,
        claim=best_claim,
        claim_truncated=rep.claim_truncated,
        geography=_union_terms([m.geography for m in ordered]),
        domain=_union_terms([m.domain for m in ordered]),
        risk=_union_terms([m.risk for m in ordered]),
        doc_key=min_row.doc_key,
        cite_nums=cite_nums,
    )


def _consolidate_rows_by_source(rows: list[_RowData]) -> list[_RowData]:
    """Group rows by non-empty ``doc_key`` and greedily cluster same-finding restatements from the
    SAME document into one multi-citation row (CONSOLIDATE-KEEP-ALL). Empty-``doc_key`` rows and
    singletons pass through unchanged. Deterministic: members are clustered in ascending ``num``
    order and each new row's greedy match is against the cluster SEED. Emits the realized-effect
    ``[activation]`` marker (anti-dark: a live consolidation path always logs). PURE apart from the
    marker log."""
    rows_in = len(rows)
    passthrough: list[_RowData] = []
    by_doc: dict[str, list[_RowData]] = {}
    for r in rows:
        if r.doc_key:
            by_doc.setdefault(r.doc_key, []).append(r)
        else:
            passthrough.append(r)  # no document identity => never consolidated

    out: list[_RowData] = list(passthrough)
    clusters = 0
    for group in by_doc.values():
        ordered = sorted(group, key=lambda r: r.num)
        used = [False] * len(ordered)
        for i, seed in enumerate(ordered):
            if used[i]:
                continue
            cluster = [seed]
            used[i] = True
            for j in range(i + 1, len(ordered)):
                if used[j]:
                    continue
                if _same_finding(seed.claim, ordered[j].claim):
                    cluster.append(ordered[j])
                    used[j] = True
            if len(cluster) >= 2:
                out.append(_merge_cluster(cluster))
                clusters += 1
            else:
                out.append(cluster[0])  # singleton unchanged

    logger.info(
        "[activation] summary_table_source_consolidate: clusters=%d rows_in=%d rows_out=%d",
        clusters, rows_in, len(out),
    )
    return out


def _label_regroup_enabled() -> bool:
    """LAW VI kill-switch ``PG_SUMMARY_TABLE_LABEL_REGROUP`` (default ON). OFF => the second pass is a
    no-op and rows pass through byte-identically."""
    return os.environ.get(_ENV_LABEL_REGROUP, "1").strip().lower() not in _OFF_VALUES


def _row_label_key(r: "_RowData") -> str:
    """The row's VISIBLE-source grouping key: the Literature cell with its trailing ``[N]`` citations
    stripped, whitespace-normalized and lowercased. Groups a document that split across a URL-keyed row
    and title-keyed rows (which ``doc_key`` kept apart). PURE."""
    lit = _LABEL_CITE_SUFFIX_RE.sub("", r.literature or "")
    return _WS_RE.sub(" ", lit).strip().lower()


def _same_finding_regroup(a: str, b: str) -> bool:
    """Relaxed same-finding test for the SAME-LABEL second pass: a DIFFERENT salient-number set is never
    merged (different quantitative result); an identical number set (or both numberless) merges when the
    claim-token CONTAINMENT (|A∩B|/min(|A|,|B|)) clears the bar — a lower bar when an identical NON-EMPTY
    number set already anchors the pair, the stricter bar when there is no numeric discriminator. Uses
    containment (not Jaccard) so synonym swaps + length asymmetry do not defeat it. PURE."""
    sa, sb = _salient_numbers(a), _salient_numbers(b)
    if sa != sb:
        return False
    ta, tb = _claim_tokens(a), _claim_tokens(b)
    if not ta and not tb:
        return True
    if not ta or not tb:
        return False
    containment = len(ta & tb) / min(len(ta), len(tb))
    bar = _REGROUP_CONTAINMENT_WITH_NUMBERS if sa else _REGROUP_CONTAINMENT_NUMBERLESS
    return containment >= bar


def _regroup_rows_by_label(rows: list["_RowData"]) -> list["_RowData"]:
    """SECOND additive consolidation pass (FIX 1): group by VISIBLE source label and merge same-label
    rows that state the same finding under the relaxed :func:`_same_finding_regroup` test. Empty/`source`
    labels and singletons pass through unchanged; merge is CONSOLIDATE-KEEP-ALL via ``_merge_cluster``.
    Emits the realized-effect ``[activation]`` marker (anti-dark). Order-stable. PURE apart from the log."""
    if not _label_regroup_enabled():
        return rows
    rows_in = len(rows)
    by_label: dict[str, list[_RowData]] = {}
    order: list[str] = []
    passthrough: list[_RowData] = []
    for r in rows:
        key = _row_label_key(r)
        if not key or key == "source":
            passthrough.append(r)  # no identifiable label => never regrouped (fail-closed)
            continue
        if key not in by_label:
            by_label[key] = []
            order.append(key)
        by_label[key].append(r)
    out: list[_RowData] = []
    groups = 0
    for key in order:
        group = by_label[key]
        if len(group) < 2:
            out.append(group[0])
            continue
        ordered = sorted(group, key=lambda r: r.num)
        used = [False] * len(ordered)
        for i, seed in enumerate(ordered):
            if used[i]:
                continue
            cluster = [seed]
            used[i] = True
            for j in range(i + 1, len(ordered)):
                if used[j]:
                    continue
                if _same_finding_regroup(seed.claim, ordered[j].claim):
                    cluster.append(ordered[j])
                    used[j] = True
            if len(cluster) >= 2:
                out.append(_merge_cluster(cluster))
                groups += 1
            else:
                out.append(cluster[0])
    out.extend(passthrough)
    logger.info(
        "[activation] summary_table_label_regroup: groups=%d rows_in=%d rows_out=%d",
        groups, rows_in, len(out),
    )
    return out


def _word_boundary_search(needle_regex_body: str, text: str, *, ignore_case: bool) -> bool:
    """True iff ``needle_regex_body`` matches ``text`` bounded on BOTH sides by a NON-word
    character (or a string edge) — i.e. as a WHOLE token, never as a substring inside a
    larger word. This is the anti-fabrication core: "mining" must NOT match "examining"
    and "india" must NOT match "indiana". ``needle_regex_body`` is an already regex-ready
    body (``re.escape`` it for a literal phrase). PURE."""
    flags = re.IGNORECASE if ignore_case else 0
    return re.search(r"(?<!\w)(?:" + needle_regex_body + r")(?!\w)", text, flags) is not None


def _dedupe_morphological(terms: list[str]) -> list[str]:
    """Collapse morphological near-duplicates within one cell — a term whose letters are a
    prefix of an already-kept term's letters (e.g. "Displace" vs "Displacement",
    "Freelance" vs "Freelancer"). Order-stable, keeps the FIRST-seen surface form. This is
    a PRESENTATION de-dup over terms that are EACH already verbatim-verified — it only
    removes a redundant sibling, never adds or fabricates a term. PURE."""
    kept: list[str] = []
    for t in terms:
        tl = re.sub(r"[^a-z]", "", t.lower())
        is_dup = False
        for k in kept:
            kl = re.sub(r"[^a-z]", "", k.lower())
            if not tl or not kl:
                continue
            short, long = (tl, kl) if len(tl) <= len(kl) else (kl, tl)
            if len(short) >= 4 and long.startswith(short):
                is_dup = True
                break
        if not is_dup:
            kept.append(t)
    return kept


def _match_terms_ci(text_lower: str, phrases: Iterable[str]) -> list[str]:
    """Distinct display terms whose curated phrase appears as a WHOLE WORD/token in the
    lowercased text. Hyphens are normalised to spaces on BOTH sides so "customer-support"
    matches "customer support"; matching is word-boundary anchored (never a substring), so
    "mining" is NOT surfaced from "examining"/"determining"/"undermining". Order-stable,
    deduped, morphological near-duplicates collapsed. PURE."""
    norm = text_lower.replace("-", " ")
    seen: set[str] = set()
    out: list[str] = []
    for phrase in phrases:
        p = phrase.replace("-", " ").lower().strip()
        if not p or not _word_boundary_search(re.escape(p), norm, ignore_case=False):
            continue
        display = phrase.replace("-", " ").strip()
        key = display.lower()
        if key not in seen:
            seen.add(key)
            out.append(display[:1].upper() + display[1:])
    return _dedupe_morphological(out)


def _match_geography(text: str) -> list[str]:
    """Distinct canonical geographies whose curated phrase/abbreviation appears as a WHOLE
    WORD in ``text``. Whole-token bounded (never substring), so "india" is NOT surfaced
    from "indiana"/"Indiana" and "US" is NOT surfaced from "USA"/"GAUSS". Full-name phrases
    match case-insensitively; bare uppercase abbreviations match case-sensitively (so the
    English pronoun "us" is never read as the United States). Order-stable, deduped. PURE."""
    out: list[str] = []
    seen: set[str] = set()
    for phrase, display in _GEO_PHRASES:
        if display.lower() in seen:
            continue
        if _word_boundary_search(re.escape(phrase), text, ignore_case=True):
            seen.add(display.lower())
            out.append(display)
    for body, display in _GEO_ABBREV:
        if display.lower() in seen:
            continue
        if _word_boundary_search(body, text, ignore_case=False):
            seen.add(display.lower())
            out.append(display)
    return out


def _format_authors(authors: Any) -> str:
    names = [str(a).strip() for a in (authors or []) if str(a).strip()]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]}, {names[1]}"
    return f"{names[0]} et al."


def _build_rows(
    bibliography: list[dict],
    section_claims: list[dict] | None,
    chrome_screen: Callable[[str], bool] | None = None,
) -> list[_RowData]:
    """One row per numbered bibliography source that carries at least one verified,
    NON-chrome claim. Claim text prefers the CLEAN kept-sentence (``section_claims``); it
    falls back to THIS source's OWN verified basket member's VERBATIM ``direct_quote``
    (span_verdict==SUPPORTS) only when no clean sentence was captured — NEVER the basket's
    synthesized/consolidated ``claim_text`` (which can carry a DIFFERENT source's
    subject/predicate). A source whose only verified spans are chrome / interstitial
    furniture (per ``chrome_screen``) yields NO row — it has no research finding to
    present (it remains in the bibliography). PURE."""
    def screen(text: str) -> bool:
        # ALWAYS run the built-in interstitial screen; OR-in the injected canonical
        # predicate (which adds masthead / mid-word-truncation coverage). Fail-open on
        # an injected-predicate error => treat as NOT chrome (never drop a real claim).
        if _default_chrome_screen(text):
            return True
        if chrome_screen is not None:
            try:
                return bool(chrome_screen(text))
            except Exception:  # noqa: BLE001 — additive screen; keep the claim on error
                return False
        return False
    # eid -> bibliography row (numbered, cited sources only).
    eid_to_bib: dict[str, dict] = {}
    for b in bibliography or []:
        if not isinstance(b, dict):
            continue
        eid = str(b.get("evidence_id") or "")
        num = b.get("num")
        if eid and isinstance(num, int) and eid not in eid_to_bib:
            eid_to_bib[eid] = b

    # eid -> its STRICT-VERIFY-PASSED clean sentences (``is_verified`` only).
    eid_to_sentences: dict[str, list[str]] = {}
    for c in section_claims or []:
        eid = str(c.get("evidence_id") or "")
        if eid not in eid_to_bib:
            continue
        # Require strict-verify-PASSED (``is_verified``). A raw ``span_verdict == SUPPORTS``
        # is NOT sufficient (Codex iter-2 P2): a span can isolate-SUPPORT while the kept
        # sentence still FAILS strict_verify (numeric-match / >=2 content-word overlap /
        # provenance). Only a strict-verify-passed kept sentence may seed a claim cell — this
        # matches the module's stated contract ("one strict-verify-passed claim per row").
        if not c.get("is_verified"):
            continue
        eid_to_sentences.setdefault(eid, []).append(str(c.get("sentence") or ""))

    rows: list[_RowData] = []
    for eid, b in eid_to_bib.items():
        num = int(b["num"])
        sentences = eid_to_sentences.get(eid, [])
        # THIS source's OWN verified basket-member verbatim direct_quotes (the member's own
        # evidence_id AND its own isolated span_verdict==SUPPORTS). Never another source's
        # member, never the basket's synthesized claim_text.
        own_quotes = _own_verified_member_quotes(b)
        claim_source_texts = list(sentences)
        used_fallback = False
        if not claim_source_texts:
            if own_quotes:
                claim_source_texts = list(own_quotes)
                used_fallback = True
        if not claim_source_texts:
            continue  # no verified claim for this source => no row (don't invent)

        # Drop chrome/interstitial spans (CAPTCHA walls, mastheads) — not research
        # findings — before selecting the claim to display, consistent with the body's
        # render-seam. A source left with no real claim yields no row.
        usable = [t for t in claim_source_texts if not screen(_clean_claim_text(t))]
        if not usable:
            continue
        claim_source_texts = usable

        best = _pick_best_claim(claim_source_texts)
        if not best:
            continue
        excerpt, truncated = _excerpt(best, _CLAIM_CELL_MAX_CHARS)
        if used_fallback and excerpt[:1].islower():
            excerpt = "…" + excerpt  # signal a mid-span basket excerpt honestly

        # Attribute-extraction scans ONLY THIS source's OWN verified text — its clean
        # kept-sentences AND its OWN verified basket-member direct_quotes (span_verdict==
        # SUPPORTS). It NEVER scans the basket's synthesized/other-source claim_text, so a
        # surfaced geography/domain/risk term can only come from THIS row's own verified
        # evidence (no cross-source leak). The curated vocabularies are high-precision and
        # WHOLE-WORD matched, so scanning this source's own verified text lifts recall
        # without admitting anything unverified (CLAUDE.md §-1.3 surface-more-verified).
        blob_parts = list(claim_source_texts)
        for _q in own_quotes:
            if _q not in blob_parts:
                blob_parts.append(_q)
        span_blob = " ".join(blob_parts)
        geography = _match_geography(span_blob)[:_MAX_TERMS_PER_CELL]
        domain = _match_terms_ci(span_blob.lower(), _DOMAIN_PHRASES)[:_MAX_TERMS_PER_CELL]
        risk = _match_terms_ci(span_blob.lower(), _RISK_PHRASES)[:_MAX_TERMS_PER_CELL]

        # Chrome-screen the Research-Literature cell metadata (source_title / authors) with
        # the SAME predicate the claim cell uses (CLAUDE.md §-1.3: EVERY rendered cell must be
        # verified-clean, not only the claim cell). A source can carry a CLEAN verified claim
        # yet a chrome/interstitial source_title (e.g. "Just a moment…", "Access denied") or
        # license/boilerplate author furniture ("© … all rights reserved"). Screen each field
        # independently; a chrome field is DROPPED (metadata only) and the label safely falls
        # back to a clean citation form — author — title, else "Source [N]". This NEVER drops
        # the verified claim/row: it only prevents chrome from rendering in the cell (a
        # screened-out title/author still lives in the numbered bibliography, NOT a §-1.3 drop).
        raw_title = str(b.get("source_title") or b.get("statement") or "").strip()
        if raw_title and screen(raw_title):
            raw_title = ""  # chrome title => drop metadata; fall back to a clean citation form
        title, title_trunc = _excerpt(raw_title, _LITERATURE_TITLE_MAX_CHARS)
        if title_trunc:
            title += "…"
        # Normalize the authors value to a LIST before the per-author screening loop.
        # Provenance may supply ``authors`` as a single STRING (not a list); iterating a bare
        # string would screen it CHARACTER-by-character — corrupting a clean "Bloom N" into
        # "B et al." and defeating the whole-phrase chrome screen (a chrome author would slip
        # past char-by-char). A str => a ONE-element list (screened as ONE author entry); a
        # list/tuple is kept as-is; None/other keeps the existing empty fallback.
        raw_authors = b.get("authors")
        if isinstance(raw_authors, str):
            raw_authors = [raw_authors]
        elif isinstance(raw_authors, (list, tuple)):
            pass
        else:
            raw_authors = []
        clean_authors = [
            a for a in raw_authors
            if str(a).strip() and not screen(str(a))  # drop per-author chrome/boilerplate
        ]
        author_str = _format_authors(clean_authors)
        # Fall back to a CLEAN single-cited label: the ``[{num}]`` wrapper below appends the
        # citation, so use bare "Source" here (never "Source [N]" which would double-cite).
        literature = " — ".join(p for p in (author_str, title) if p) or "Source"

        rows.append(_RowData(
            num=num,
            literature=f"{literature} [{num}]",
            claim=excerpt,
            claim_truncated=truncated,
            geography=geography,
            domain=domain,
            risk=risk,
            doc_key=_doc_identity(b),
            cite_nums=[num],
        ))
    # Source-consolidation post-pass (CONSOLIDATE-KEEP-ALL, CLAUDE.md §-1.3). Gated ON by default
    # (LAW VI kill-switch); OFF => the one-row-per-eid list is byte-identical. Runs BEFORE the sort
    # so the collapsed multi-citation rows and the untouched singletons order together by ``num``.
    if _source_consolidate_enabled():
        rows = _consolidate_rows_by_source(rows)
        # I-deepfix-001 (#1369) FIX 1: SECOND label-regroup pass catches the URL-vs-title splits and
        # synonym-swap paraphrases the first (doc_key + Jaccard) pass leaves as duplicate rows. Kept
        # UNDER the same master consolidation gate so PG_SUMMARY_TABLE_SOURCE_CONSOLIDATE=0 stays
        # byte-identical to the one-row-per-eid legacy output.
        rows = _regroup_rows_by_label(rows)
    rows.sort(key=lambda r: r.num)
    return rows


def _own_verified_member_quotes(bib_row: dict) -> list[str]:
    """Verbatim ``direct_quote`` texts from THIS bibliography row's OWN verified basket
    members — the ONLY faithful fallback claim source when no clean kept-sentence was
    captured for the source.

    A member contributes iff BOTH hold: (a) it is THIS row's own source
    (``member.evidence_id == bib_row.evidence_id``), and (b) its OWN isolated
    ``span_verdict`` is ``SUPPORTS`` (the binding per-member verified gate — the very
    members counted in ``verified_support_origin_count``). The rendered text is the
    member's VERBATIM ``direct_quote``; the basket's synthesized/consolidated
    ``claim_text`` is NEVER used (it can carry a DIFFERENT source's subject/predicate — a
    cross-source fabrication). A member of another origin, or this source's own member
    whose span is NOT SUPPORTS, contributes nothing. Order-stable, deduped. PURE."""
    row_eid = str(bib_row.get("evidence_id") or "")
    if not row_eid:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for basket in (bib_row.get("baskets") or []):
        if not isinstance(basket, dict):
            continue
        for member in (basket.get("supporting_members") or []):
            if not isinstance(member, dict):
                continue
            if str(member.get("evidence_id") or "") != row_eid:
                continue  # a co-basket OTHER source — never borrow its span
            if str(member.get("span_verdict") or "").upper() != "SUPPORTS":
                continue  # this source's own span is not verified-SUPPORTS => no fallback
            quote = str(member.get("direct_quote") or "").strip()
            if quote and quote not in seen:
                seen.add(quote)
                out.append(quote)
    return out


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------
def _escape_cell(text: str) -> str:
    return text.replace("\n", " ").replace("|", "\\|").strip()


def _cell_for_role(role: str, row: _RowData) -> str:
    if role == ROLE_LITERATURE:
        return _escape_cell(row.literature) or GAP_CELL
    if role == ROLE_CLAIM:
        claim = row.claim + ("…" if row.claim_truncated else "")
        return f"{_escape_cell(claim)} [{row.num}]"
    if role == ROLE_GEOGRAPHY:
        return _escape_cell("; ".join(row.geography)) or GAP_CELL
    if role == ROLE_DOMAIN:
        return _escape_cell("; ".join(row.domain)) or GAP_CELL
    if role == ROLE_RISK:
        return _escape_cell("; ".join(row.risk)) or GAP_CELL
    return GAP_CELL


def build_summary_table_markdown(
    headers: list[str], rows: list[_RowData], include_heading: bool = True
) -> str:
    """Render the GFM table (header, separator, one row per verified source) plus a
    faithfulness disclosure note and the idempotency marker. PURE.

    ``include_heading`` (default True) preserves the legacy standalone block that carries
    its own generic ``## Summary table`` heading (every existing caller is byte-identical).
    When False (N3 anchor path, PG_SUMMARY_TABLE_ANCHOR_SECTION), ONLY that heading line and
    its trailing blank separator are omitted so the block can be inserted DIRECTLY under the
    report's own body heading that names the summary table; TABLE_MARKER, the disclosure note
    and the table itself are byte-identical to the include_heading=True form."""
    roles = assign_header_roles(headers)
    esc_headers = [_escape_cell(h) for h in headers]
    lines: list[str] = []
    if include_heading:
        lines.append("## Summary table")
        lines.append("")
    lines.append(TABLE_MARKER)
    lines.append(
        "_Built only from verified findings (CLAUDE.md §-1.3: a presentation of "
        "already-verified content, no new claim). The Research-Literature and "
        "Specific-Applications-and-Impacts cells trace to a strict-verify-passed "
        "claim cited [N]. The Country/Region, Application-Area/Occupation and Key-Risks "
        "cells list only terms that appear VERBATIM as whole words in that source's own "
        "verified spans; a "
        "— marks that no such term was found in the verified evidence (disclosed gap — "
        "nothing was inferred)._"
    )
    lines.append("")
    lines.append("| " + " | ".join(esc_headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        cells = [_cell_for_role(role, row) for role in roles]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _insert_before_appendix(report_md: str, table_md: str, appendix_boundary_marker: str) -> str:
    """Insert the table at the END of the scored body — immediately before the audit
    machinery appendix boundary when present, else appended at the end of the report.
    PURE."""
    block = "\n\n" + table_md.rstrip() + "\n"
    if appendix_boundary_marker and appendix_boundary_marker in report_md:
        idx = report_md.index(appendix_boundary_marker)
        head = report_md[:idx].rstrip()
        tail = report_md[idx:]
        return head + block + "\n\n" + tail
    return report_md.rstrip() + block


# I-deepfix-001 (#1369) FIX 3 (iter3) — off-topic summary-table rows. Root cause (Fable): the promotion
# topical gate is wired ONLY to the CWF single-source promotion partition, never to summary-table row
# building, so an off-topic-but-span-verified source (materials-science MWCNT row [28] in a Gen-AI-and-jobs
# report) rows-ifies unchecked. WEIGHT-NOT-FILTER / no-drop (Codex+Fable P1): a row whose claim shares EXACTLY
# ZERO content-word overlap with the research question is DEMOTED to the bottom of the table — NEVER dropped
# (lexical overlap is not a reliable off-topic signal; an on-topic synonym row has zero literal overlap too).
# Every verified row survives; skips (no demotion) when the question yields no tokens. Default-ON
# PG_SUMMARY_TABLE_TOPICAL_GATE.
_ENV_TOPICAL_GATE = "PG_SUMMARY_TABLE_TOPICAL_GATE"


def _topical_gate_enabled() -> bool:
    """LAW VI kill-switch (default ON). OFF => rows pass through byte-identically."""
    return os.environ.get(_ENV_TOPICAL_GATE, "1").strip().lower() not in _OFF_VALUES


def _topical_tokens(text: str) -> frozenset[str]:
    """Content-word tokens for the topical-overlap test, splitting on whitespace AND hyphens/slashes so a
    compound like "employment-to-population" contributes "employment" (else an on-topic row that never
    uses the question's exact surface form would be wrongly dropped). Stopword-stripped. PURE."""
    out: set[str] = set()
    for raw in re.split(r"[\s\-/]+", (text or "").lower()):
        tok = raw.strip(".,;:!?()[]{}\"'`—–…%")
        if not tok or tok in _CONSOLIDATE_STOPWORDS:
            continue
        out.add(tok)
    return frozenset(out)


def _topical_gate_rows(rows: list["_RowData"], research_question: str) -> list["_RowData"]:
    """WEIGHT-NOT-FILTER / no-drop (Codex + Fable P1, §-1.3): NEVER drop a verified summary-table row on
    topical grounds — a vocabulary-mismatch on-topic row ('Automation exposure is highest in clerical
    occupations' vs a 'generative AI employment effects' question) has zero LITERAL question-token overlap
    yet is genuinely on-topic, and lexical overlap is not a reliable off-topic signal. Instead DEMOTE: keep
    EVERY row, but order the zero-overlap rows AFTER the overlapping ones (stable within each group) so
    on-topic findings surface first without deleting any content. Emits the realized-effect marker. PURE
    apart from the log."""
    if not _topical_gate_enabled():
        return rows
    qtokens = _topical_tokens(research_question or "")
    if not qtokens:
        logger.info(
            "[activation] summary_table_topical_gate: demoted=0 kept=%d (no question tokens -> skip)",
            len(rows),
        )
        return rows
    on_topic: list[_RowData] = []
    off_topic: list[_RowData] = []
    for r in rows:
        ctoks = _topical_tokens(r.claim or "")
        if ctoks and not (ctoks & qtokens):
            off_topic.append(r)  # zero literal overlap -> DEMOTE to the bottom, never drop
        else:
            on_topic.append(r)
    logger.info(
        "[activation] summary_table_topical_gate: demoted=%d kept=%d (no-drop, on-topic-first)",
        len(off_topic), len(on_topic) + len(off_topic),
    )
    return on_topic + off_topic


# I-deepfix-001 wave-2 (#1370) N3 — ANCHOR the verified summary table INTO the body section
# whose heading NAMES it (e.g. "### Industry Application Cases and Risk Summary Table"), instead
# of the detached generic "## Summary table" heading dropped before the Bibliography. Placement /
# anchoring only: the row building, verification gating, chrome screen and disclosed-gap ("—")
# cells are UNTOUCHED (they are correct honest behaviour). Default-OFF flag (LAW VI): unset/"0"
# => byte-identical current output (the legacy _insert_before_appendix path).
_ENV_ANCHOR_SECTION = "PG_SUMMARY_TABLE_ANCHOR_SECTION"

# A body heading (2..5 ``#``) whose text names a "summary table". Anchored to line starts
# (MULTILINE) so only headings match; IGNORECASE so "SUMMARY TABLE" / "Summary Table" all anchor.
_SUMMARY_TABLE_HEADING_RE = re.compile(
    r"^#{2,5}\s+.*summary\s+table", re.IGNORECASE | re.MULTILINE
)


def _anchor_section_enabled() -> bool:
    """LAW VI flag (default OFF). OFF => the legacy detached-heading path => byte-identical."""
    return os.environ.get(_ENV_ANCHOR_SECTION, "0").strip().lower() not in _OFF_VALUES


def _find_summary_table_heading(report_md: str, appendix_boundary_marker: str) -> int | None:
    """Scan ONLY the body BEFORE the appendix boundary for the FIRST markdown heading line whose
    text names a summary table; return the offset just PAST that heading line (and its single
    trailing blank line, if any) — the insertion point directly under the heading, before the
    section's existing prose. Return None when no such heading exists in the body. PURE."""
    if not report_md:
        return None
    if appendix_boundary_marker and appendix_boundary_marker in report_md:
        body_limit = report_md.index(appendix_boundary_marker)
    else:
        body_limit = len(report_md)
    for match in _SUMMARY_TABLE_HEADING_RE.finditer(report_md):
        if match.start() >= body_limit:
            break  # the heading is inside the appendix machinery, not the scored body
        line_end = report_md.find("\n", match.end())
        if line_end == -1:
            return len(report_md)  # heading is the last line; append point is EOF
        pos = line_end + 1
        next_nl = report_md.find("\n", pos)
        if next_nl == -1:
            # only a trailing (possibly blank) remnant after the heading line
            return len(report_md) if report_md[pos:].strip() == "" else pos
        # skip a SINGLE blank line immediately after the heading (the heading's separator)
        if report_md[pos:next_nl].strip() == "":
            return next_nl + 1
        return pos
    return None


def render_requested_summary_table(
    *,
    research_question: str,
    bibliography: list[dict],
    section_claims: list[dict] | None = None,
    existing_report_md: str = "",
    appendix_boundary_marker: str = "",
    chrome_screen: Callable[[str], bool] | None = None,
    contract_headers: list[str] | None = None,
) -> SummaryTableResult:
    """Build and insert the prompt-requested summary table into ``existing_report_md``.

    No-op (``changed=False``, text unchanged) when the kill-switch is OFF, the prompt
    does not request a titled table, the report already carries the table marker
    (idempotent / resume-safe), or no source carries a verified claim. Otherwise
    returns the report text with the table inserted at the end of the scored body.
    PURE (reads only the env kill-switch).

    I-wire-001 F1 — the header source is resolved as ``contract_headers or
    parse_requested_headers(research_question)``: when the caller supplies the per-task
    output CONTRACT's ``required_table.columns`` (>= 2 clean names) those are
    AUTHORITATIVE (they are transcribed verbatim from the gold prompt and are exactly
    what the run-validity gate matches against), otherwise the parser recovers the
    headers from the bound question. None/empty ``contract_headers`` => byte-identical to
    the prior parse-from-question behaviour."""
    if not summary_table_enabled():
        return SummaryTableResult(text=existing_report_md, changed=False, canary="disabled")
    if existing_report_md and TABLE_MARKER in existing_report_md:
        return SummaryTableResult(text=existing_report_md, changed=False, canary="already_present")
    # CONTRACT path is primary (authoritative when it yields >= 2 clean columns); the
    # bound-question parser is the fallback.
    headers = [str(h).strip() for h in (contract_headers or []) if str(h).strip()]
    if len(headers) < 2:
        headers = parse_requested_headers(research_question)
    if len(headers) < 2:
        return SummaryTableResult(text=existing_report_md, changed=False, canary="no_table_requested")
    rows = _build_rows(bibliography or [], section_claims, chrome_screen)
    # I-deepfix-001 (#1369) FIX 3 (iter3): DEMOTE off-topic table rows (literal zero question-overlap) to the
    # bottom — never drop (weight-not-filter / §-1.3 no-drop). Every verified row survives.
    rows = _topical_gate_rows(rows, research_question)
    if not rows:
        return SummaryTableResult(
            text=existing_report_md, changed=False, canary="no_verified_rows", headers=headers
        )
    # N3 (#1370): when enabled AND the report body carries a heading that NAMES the summary
    # table, anchor the (heading-less) table DIRECTLY under that heading, keeping the section's
    # existing narrative prose below it (§-1.3: never drop content). Otherwise keep the exact
    # legacy path — the detached "## Summary table" block inserted before the appendix boundary.
    anchor_pos: int | None = None
    if _anchor_section_enabled() and existing_report_md:
        anchor_pos = _find_summary_table_heading(existing_report_md, appendix_boundary_marker)
    if anchor_pos is not None:
        table_md = build_summary_table_markdown(headers, rows, include_heading=False)
        new_text = (
            existing_report_md[:anchor_pos]
            + table_md.rstrip()
            + "\n\n"
            + existing_report_md[anchor_pos:]
        )
        anchored = True
    else:
        table_md = build_summary_table_markdown(headers, rows)
        if not existing_report_md:
            new_text = table_md
        else:
            new_text = _insert_before_appendix(
                existing_report_md, table_md, appendix_boundary_marker
            )
        anchored = False
    n_geo = sum(1 for r in rows if r.geography)
    n_dom = sum(1 for r in rows if r.domain)
    n_risk = sum(1 for r in rows if r.risk)
    canary = (
        f"{CANARY_TAG} rows={len(rows)} cols={len(headers)} "
        f"geo_filled={n_geo} domain_filled={n_dom} risk_filled={n_risk} "
        f"anchored={anchored}"
    )
    return SummaryTableResult(
        text=new_text, changed=True, canary=canary, rows=len(rows), headers=headers
    )
