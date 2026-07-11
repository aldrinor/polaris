"""I-meta-005 Phase 5 (#989) — dedup-by-finding + corroboration.

Clusters generator-visible evidence rows by the numeric FINDING they assert,
collapses rehashes of the SAME finding to one representative row, and attaches
``corroboration_count`` = the number of INDEPENDENT registrable-domains carrying
that finding. This is Knowledge-Based Trust (gap D of the re-architecture plan):
the sovereign, domain-general, self-computed trust signal — trust a finding the
rest of the corpus independently confirms, with no external authority service.

CONSERVATIVE-SINGLETON safety rule (brief §2.4 — clinical-lethal if violated):
two findings merge ONLY when subject is KNOWN (not the ``"unknown"`` fallback)
and equal, predicate equal, value (rounded) + unit equal, AND every qualifier the
extractor exposes (dose, arm, endpoint_phrase) is equal — comparing raw field
values so ABSENT==ABSENT matches but ABSENT-vs-PRESENT does not. Any unknown
subject or any qualifier difference keeps the findings SEPARATE. The default on
ambiguity is always "keep separate" — we never drop a distinct finding.

DOCUMENTED RESIDUAL 1 (over-merge bound): ``ExtractedNumericClaim`` does NOT
extract population or comparator. Two findings identical on every extracted field
but differing only in an UNEXTRACTED qualifier (e.g. a T2D vs an obesity
population that share "-2.1%") could merge. This is bounded to a corroboration
OVER-count — a TRUST signal, never a safety gate — and NEVER causes unique-claim
LOSS: the finding the representative asserts (subject/predicate/value/unit/dose/
arm/endpoint) is identical across all members by construction, and all
``member_indices`` + ``member_hosts`` are preserved on the cluster for audit
(manifest + conflict surfacing). A future phase may add a population/comparator
extractor to tighten the key.

RESIDUAL 2 — NOW CLOSED (I-deepfix-001 C1, #1344; supersedes the stale
"deferred to a follow-up" note): the field-agnostic numeric-finding extractor
that this docstring once deferred is LIVE. ``extract_numeric_claims`` routes a
NON-clinical row (deterministic ``is_clinical_domain`` signal) to the
DOMAIN-AGNOSTIC extractor (B9, commit ac039560), so a GDP / emissions /
model-accuracy numeric now yields a REAL claim key instead of nothing. But the
merged run still measured ``collapsed=0`` on non-clinical corpora — the traced
non-firing seam was the MERGE KEY, not the extractor: ``_finding_key`` keyed the
subject on the RAW surface string, so two sources paraphrasing the SAME subject
with a different surface form ("e-commerce" vs "ecommerce" vs "E-Commerce") got
DISTINCT keys and never consolidated. C1 STRENGTHENS the non-clinical key to a
folded subject SIGNATURE (``_fold_nonclinical_subject`` — case/punctuation-folded,
so surface variants of one subject collapse) while keeping predicate + value +
unit as hard discriminators, so two DISTINCT facts that merely share a number
NEVER collapse. The CLINICAL key is kept VERBATIM (the conservative-singleton
subject/predicate/value/unit/dose/arm/endpoint guard) — a clinical row is routed
by its own ``is_clinical_domain`` probe and takes the byte-identical strict key,
so a dose/population can never wrongly merge. (The multi-claim-per-row retention
logic below is still defensive/future-proof against an extractor that emits >1
claim per row.)

Pure: constructs no client, no network, no LLM. snake_case; explicit imports.
"""
from __future__ import annotations

import logging
import math
import os
import re
import time
import unicodedata
from concurrent.futures import (
    FIRST_COMPLETED,
    ThreadPoolExecutor,
    wait as futures_wait,
)
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from src.polaris_graph.authority.corroboration import (
    count_independent_hosts,
    registrable_domain,
)
from src.polaris_graph.retrieval.contradiction_detector import (
    extract_numeric_claims,
)

logger = logging.getLogger("polaris_graph.finding_dedup")

# The fallback subject `extract_numeric_claims` returns when it cannot identify
# the entity nearest the numeric value. Such claims are NEVER mergeable.
_UNKNOWN_SUBJECT = "unknown"

# ─────────────────────────────────────────────────────────────────────────
# Non-clinical subject-signature fold — I-deepfix-001 C1 (#1344)
# ─────────────────────────────────────────────────────────────────────────
# §-1.3 CONSOLIDATE, don't DROP: the B9 domain-agnostic extractor is live, but the
# numeric merge key keyed the subject on the RAW surface string, so two NON-clinical
# sources paraphrasing the SAME subject in a different surface form never clustered
# (the measured `collapsed=0`). C1 folds ONLY the NON-clinical subject slot into a
# case/punctuation-normalized SIGNATURE so surface variants of one subject collapse,
# while predicate + value + unit stay hard discriminators (two DISTINCT facts that
# merely share a number never merge). CLINICAL rows keep the VERBATIM strict key.
# FAITHFULNESS-NEUTRAL: this only groups more same-claim corroborators into one
# basket (corroboration_count is a Signal-D WEIGHT, never a verify gate); it drops
# no row and touches no faithfulness engine. LAW VI kill-switch (default ON).
_NONCLINICAL_SUBJECT_FOLD_ENV = "PG_FINDING_DEDUP_NONCLINICAL_SUBJECT_FOLD"
_NONALNUM_FOLD_RE = re.compile(r"[^a-z0-9]+")


def _nonclinical_fold_enabled() -> bool:
    """``PG_FINDING_DEDUP_NONCLINICAL_SUBJECT_FOLD`` kill switch (LAW VI). DEFAULT-ON:
    the C1 non-clinical subject signature. Set to ``0`` to restore the byte-identical
    raw-surface-subject key (no folding — the pre-C1 behavior). Clinical rows are
    unaffected either way (they never fold)."""
    return os.getenv(_NONCLINICAL_SUBJECT_FOLD_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _fold_nonclinical_subject(subject: str) -> str:
    """The folded NON-clinical subject signature: lowercased, every non-alphanumeric
    run stripped. Collapses surface variants of ONE subject ("e-commerce" / "ecommerce"
    / "E-Commerce" -> "ecommerce") WITHOUT merging genuinely different subjects ("gdp"
    stays distinct from "gnp"). Returns ``""`` for a subject that folds to nothing
    (pure punctuation) — the caller then treats it as the UNKNOWN sentinel (safe
    singleton, never a false merge)."""
    return _NONALNUM_FOLD_RE.sub("", (subject or "").strip().lower())


# ─────────────────────────────────────────────────────────────────────────
# Claim-key hygiene guard — S2/S3 re-pass Fix 3(c)
# ─────────────────────────────────────────────────────────────────────────
# The numeric-claim extractor sometimes names a GARBAGE token as the subject or reads a
# GARBAGE numeric as the value, producing garbage MERGE keys (drb_72 live: 'com', 'wp096',
# 'wp166', 'flatedecode', value 9.78e17 = an ISBN, 1.72e18 = a Ray-ID). §-1.3 keeps every
# row (never drop), but such a key must never be a same-claim MERGE key. When the folded
# NON-clinical subject is a PDF-stream artifact, a bare file/working-paper code, a lone
# TLD/scheme token, or a long digit run — or the value is an absurd magnitude no real
# statistic reaches — the key COLLAPSES to the UNKNOWN sentinel (a safe per-row singleton:
# never a false merge, never a drop). CLINICAL rows are unaffected (their strict verbatim
# key never routes through the fold). LAW VI kill-switch (default ON).
_KEY_HYGIENE_ENV = "PG_FINDING_DEDUP_KEY_HYGIENE"
_GARBAGE_SUBJECT_TOKENS = frozenset({
    "flatedecode", "endstream", "endobj", "startxref", "xref", "obj", "stream",
    "pdf", "html", "http", "https", "www", "com", "org", "net", "gov", "edu", "io",
})
_GARBAGE_CODE_RE = re.compile(r"^[a-z]{1,3}\d{2,}$")   # wp096 / w31161 / id1234 — code tokens
_LONG_DIGIT_RE = re.compile(r"^\d{7,}$")               # ISBN / Ray-ID-like numeric run
# Above this magnitude a "numeric finding" is almost certainly a mis-read identifier
# (ISBN ~9.78e17, Ray-ID ~1.7e18), never a real reported statistic (world GDP ~1e14).
_ABSURD_VALUE_MAGNITUDE = 1e15


def _key_hygiene_enabled() -> bool:
    """``PG_FINDING_DEDUP_KEY_HYGIENE`` kill switch (LAW VI). DEFAULT-ON: garbage
    subject/value keys collapse to the UNKNOWN sentinel (safe singleton). OFF => the
    byte-identical raw key (garbage tokens may key a basket, the pre-Fix-3c behavior)."""
    return os.getenv(_KEY_HYGIENE_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


# P0-1(a) (S2/S3 re-pass iter-5, Fable — "the consolidation ghost is wounded, not dead"): a
# STOPWORD / FUNCTION-WORD / generic-discourse subject is NOT a real research subject and must
# never be a same-claim MERGE key. The numeric extractor sometimes names the token nearest a
# number as the "subject" — a pronoun ('their'), a conjunction ('because'), a light/reporting
# verb ('reveals','shows'), an auxiliary, or a bare generic discourse noun/adjective
# ('significant','point','level','mid','capabilities'). Two DIFFERENT works that merely share
# such a garbage subject + a colliding value (the drb_72 basket-27 'reveals/increase/26.08'
# semanticscholar+ssrn merge, basket-109 'because/change/13' 3x, basket-28 'their/level/4.0'
# medium blog) then key into ONE false corroboration basket. The GENERAL rule (question-agnostic,
# NO entity/corpus list): a subject whose tokens are ALL closed-class function words OR bare
# generic-discourse tokens carries no content NOUN — collapse it to the UNKNOWN sentinel (a safe
# per-row singleton; the row is KEPT and can still consolidate via the strict NLI claim-sentence
# path, which decides same-claim on MEANING, not a token collision). §-1.3-safe: NEVER a DROP,
# only a merge-key demotion; the CLINICAL strict-verbatim key never routes through the fold.
_NONCONTENT_SUBJECT_TOKENS = frozenset({
    # pronouns / pro-forms
    "i", "we", "you", "he", "she", "it", "they", "them", "us", "me", "him", "her",
    "this", "that", "these", "those", "their", "theirs", "its", "our", "ours", "your",
    "yours", "his", "hers", "my", "mine", "who", "whom", "whose", "which", "what",
    "one", "ones", "itself", "themselves", "someone", "anyone", "everyone", "something",
    "anything", "everything", "such", "same", "own", "other", "another",
    # determiners / quantifiers
    "a", "an", "the", "some", "any", "each", "every", "all", "both", "few", "fewer",
    "many", "most", "several", "no", "none", "either", "neither", "enough", "much",
    "more", "less",
    # conjunctions / discourse connectives
    "and", "or", "but", "nor", "so", "yet", "thus", "hence", "therefore", "however",
    "moreover", "furthermore", "also", "then", "because", "although", "though", "while",
    "whereas", "thereby", "thereof", "herein", "hereby", "whereby", "meanwhile",
    "nonetheless", "nevertheless", "accordingly", "consequently", "additionally",
    "similarly", "likewise", "instead", "rather", "indeed", "overall", "furthermore",
    # prepositions / particles
    "of", "in", "on", "at", "by", "to", "for", "with", "from", "as", "into", "onto",
    "upon", "about", "over", "under", "between", "among", "per", "via", "within",
    "without", "through", "during", "before", "after", "above", "below", "across",
    "toward", "towards", "against", "along", "around", "behind", "beyond", "despite",
    # auxiliaries / light + reporting verbs (Fable named 'reveals')
    "is", "are", "was", "were", "be", "been", "being", "has", "have", "had", "do",
    "does", "did", "will", "would", "can", "could", "may", "might", "must", "shall",
    "should", "reveal", "reveals", "revealed", "show", "shows", "showed",
    "showing", "find", "finds", "found", "suggest", "suggests", "suggested",
    "indicate", "indicates", "indicated", "note", "notes", "noted", "state", "states",
    "stated", "report", "reports", "reported", "mean", "means", "seem", "seems",
    "appear", "appears", "remain", "remains", "become", "becomes", "include",
    "includes", "provide", "provides", "present", "presents", "demonstrate",
    "demonstrates", "estimate", "estimates", "estimated", "using", "used",
    # generic discourse nouns / hedge adjectives (Fable named significant/point/level/mid/
    # capabilities) — never a specific research subject on their own
    "significant", "significance", "significantly", "point", "points", "level",
    "levels", "mid", "case", "cases", "way", "ways", "thing", "things", "part",
    "parts", "aspect", "aspects", "factor", "factors", "issue", "issues", "area",
    "areas", "term", "terms", "example", "examples", "capability", "capabilities",
    "kind", "kinds", "type", "types", "sort", "sorts", "range", "ranges", "side",
    "sides", "context", "regard", "respect", "manner", "extent", "degree", "amount",
    "number", "total", "figure", "figures", "item", "items", "value", "values",
    "result", "results", "finding", "findings", "section", "chapter", "table",
    # hedge / degree adverbs — never a research subject on their own
    "particularly", "especially", "notably", "specifically", "generally", "typically",
    "largely", "primarily", "mainly", "approximately", "roughly", "nearly", "relatively",
    "substantially", "considerably", "increasingly", "respectively", "namely",
})
_SUBJECT_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9]+")


def _subject_is_noncontent(subject: str) -> bool:
    """P0-1(a) (Fable): True iff the RAW subject carries NO content noun — every whitespace/
    punctuation token folds to a closed-class function word OR a bare generic-discourse token
    in ``_NONCONTENT_SUBJECT_TOKENS``. Such a subject ('their', 'because', 'reveals',
    'significant point') is extractor noise, never a real research subject, so it must never be
    a same-claim MERGE key. Question-agnostic + deterministic; empty/whitespace => False (the
    existing UNKNOWN handling already covers an empty subject). A single content token anywhere
    (e.g. 'unemployment' in 'unemployment rate') keeps the subject."""
    s = (subject or "").strip().lower()
    if not s:
        return False
    toks = [t for t in _SUBJECT_TOKEN_SPLIT_RE.split(s) if t]
    if not toks:
        return False
    return all(t in _NONCONTENT_SUBJECT_TOKENS for t in toks)


def _is_garbage_subject(folded: str) -> bool:
    """True iff the folded non-clinical subject is a garbage token (PDF-stream artifact,
    bare file/working-paper code, lone TLD/scheme token, long digit run, OR — P0-1(a),
    Fable iter-5 — a bare closed-class function word / generic-discourse token that carries
    no content noun) that must never be a same-claim merge key. Pure/deterministic."""
    if not folded:
        return False
    if folded in _GARBAGE_SUBJECT_TOKENS:
        return True
    if folded in _NONCONTENT_SUBJECT_TOKENS:  # P0-1(a): single-token stopword/generic subject
        return True
    if _GARBAGE_CODE_RE.match(folded):
        return True
    if _LONG_DIGIT_RE.match(folded):
        return True
    return False


def _subject_is_title_like(subject: str) -> bool:
    """True iff the RAW (pre-fold) subject is a TITLE or a full clause, not a subject noun
    phrase (S2/S3 re-pass Fix 12/3, Fable). The extractor sometimes names a paper's TITLE as
    the subject ('The Projected Impact of Generative AI on Future Productivity'), which folds
    to one run-together token and then falsely keys distinct works into one basket. A genuine
    subject is a short noun phrase (1-5 words); >= 6 words OR very long is a title/clause —
    collapse it to the UNKNOWN sentinel (safe singleton). General, question-agnostic."""
    s = (subject or "").strip()
    if not s:
        return False
    words = s.split()
    if len(words) >= 6 or len(s) >= 64:
        return True
    # A lone run-together token >= 30 chars is a URL/filename SLUG or a space-stripped title
    # ('projectedimpactofgenerativeaionfutureproductivity'), never a real subject noun phrase
    # (a genuine single-word subject like 'telecommunications' is < 30 chars).
    return len(words) <= 1 and len(s) >= 30


# ─────────────────────────────────────────────────────────────────────────
# Unicode / LaTeX text normalization — S2/S3 re-pass P1-4
# ─────────────────────────────────────────────────────────────────────────
# A ligature ('signiﬁcant'), a full-width digit, or a compatibility glyph gave two
# byte-different-but-same-claim rows DISTINCT merge/NLI signals, so they never merged
# (B011/B074 'signiﬁcant' variant, LaTeX '$1.5\%$' surface). NFKC compatibility-fold
# collapses those variants to their ASCII base BEFORE the text becomes a merge/NLI signal.
# NFKC (not NFKD+strip-combining) PRESERVES accented multilingual letters (é stays é) — it
# only folds compatibility variants, so it is byte-safe for legitimate multilingual content.
_LATEX_MATH_WRAP_RE = re.compile(r"\$+")
_LATEX_PERCENT_RE = re.compile(r"\\%")
_LATEX_CMD_RE = re.compile(r"\\[a-zA-Z]+")


def _normalize_unicode_text(text: Any) -> str:
    """NFKC compatibility-fold + minimal LaTeX de-mark so ligatures / full-width digits /
    ``$..$`` math wrappers / ``\\%`` collapse to a plain-text signal (P1-4). Pure; fail-open
    (returns the input as a plain string on any error). Used ONLY for merge/NLI signals — the
    displayed source text is never touched."""
    if text is None:
        return ""
    s = str(text)
    try:
        s = unicodedata.normalize("NFKC", s)
    except Exception:  # noqa: BLE001 — a normalization defect must never crash a paid run
        return str(text)
    # Minimal LaTeX: '\%' -> '%', drop '$' math wrappers + bare '\cmd' control words so a
    # '$1.5\%$' surface reads as '1.5%' for the numeric/NLI signal. Conservative: only these.
    s = _LATEX_PERCENT_RE.sub("%", s)
    s = _LATEX_MATH_WRAP_RE.sub("", s)
    s = _LATEX_CMD_RE.sub(" ", s)
    return s


# ─────────────────────────────────────────────────────────────────────────
# Letter-spaced / extraction-degraded text — S2/S3 re-pass Fix 7 (Fable)
# ─────────────────────────────────────────────────────────────────────────
# A PDF/HTML extraction sometimes emits a run of single characters separated by spaces
# ("W e i n v e s t i g a t e t h e p o t e n t i a l") or per-glyph cloudinary/font
# artifacts. An NLI cross-encoder cannot read letter-spaced text, so such a row spuriously
# entailed unrelated claims into a false basket AND surfaced as an unreadable representative
# (the Eloundou huggingface abstract). GENERAL detector (no entity/corpus tuning): a body
# whose tokens are dominated by isolated single characters is extraction-degraded.
# ``_collapse_letter_spacing`` heals a short degraded run back to readable words when the
# spacing is regular; ``_is_extraction_degraded`` marks a row so it never seeds/joins a
# cluster and is never elected representative.
_SINGLE_CHAR_RUN_RE = re.compile(r"(?:\b[A-Za-z]\s+){4,}\b[A-Za-z]\b")


def _collapse_letter_spacing(text: Any) -> str:
    """Join runs of >=5 space-separated single letters back into a word ('W e i n v e s t'
    -> 'Weinvest'). Only collapses the isolated-letter runs; normal words are untouched.
    Pure/fail-open. Used to give the NLI/keying signal a readable form when possible."""
    s = str(text or "")
    if not _SINGLE_CHAR_RUN_RE.search(s):
        return s
    def _join(m: "re.Match[str]") -> str:
        return re.sub(r"\s+", "", m.group(0))
    return _SINGLE_CHAR_RUN_RE.sub(_join, s)


def _is_extraction_degraded(text: Any) -> bool:
    """True when ``text`` is dominated by isolated single-character tokens (letter-spaced
    extraction garbage) — the row carries no readable claim for NLI/keying/representative.
    General + question-agnostic: measured as the share of length-1 alpha tokens among the
    first ~120 tokens; a genuine sentence has almost none. Fail-open (short/empty => False)."""
    s = str(text or "")
    if len(s) < 20:
        return False
    toks = s.split()[:120]
    if len(toks) < 8:
        return False
    single = sum(1 for t in toks if len(t) == 1 and t.isalpha())
    # >=45% single-letter tokens is unambiguous letter-spacing (a normal sentence is <5%).
    return single >= max(6, int(0.45 * len(toks)))


def _clean_rep_enabled() -> bool:
    """``PG_FINDING_CLEAN_REP`` kill switch (LAW VI, DEFAULT-ON, Fix 4b/7). When ON, a
    basket's representative is never a chrome/nav/captcha/letter-spaced line if any clean
    content member exists. OFF => the legacy highest-rank pick (byte-identical)."""
    return os.getenv("PG_FINDING_CLEAN_REP", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _rep_is_unclean(row: dict[str, Any]) -> bool:
    """True when ``row`` is unfit to REPRESENT a basket: a captcha/anti-bot stub, a
    furniture/nav-dominant chrome body, or letter-spaced extraction garbage. Used ONLY to
    demote a representative when a clean sibling exists — the row itself is still KEPT
    (§-1.3 keep-all). Names resolve at call time (helpers are defined later in the module)."""
    body = _row_text(row)
    if _is_extraction_degraded(body):
        return True
    try:
        if _is_captcha_stub(row):
            return True
    except Exception:  # noqa: BLE001 — a predicate defect must never crash a paid run
        pass
    try:
        from src.polaris_graph.generator.chrome_furniture_screen import (  # noqa: PLC0415
            is_furniture_dominant,
        )
        if is_furniture_dominant(body):
            return True
    except Exception:  # noqa: BLE001
        pass
    try:
        if _body_is_chrome_dominant(body):
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


_MIDSENTENCE_TRUNCATION_RE = re.compile(r"\[\s*\.\.\.\s*\]|\[\s*…\s*\]|\.\.\.\s*$|…\s*$")
_SENTENCE_TERMINAL_RE = re.compile(r"[.!?][\"')\]]?\s*$")
# P0-1(c) (iter-5, Fable): page-navigation / share / reader-shell chrome fragments that a
# fetch glued onto a heading ('... Main findings from the consultation process Copy link to 3',
# 'Press enter or click to view image', '4 min read', 'Read More', 'View details', 'Skip to
# content'). Folded OUT of the claim-bearing test so such chrome cannot pad a bare HEADING up to
# a "claim-bearing" word count and let two DIFFERENT works byte-identical-merge on the heading
# (drb_72 basket-224 worldbank+oecd 'Main findings from the consultation process'). Question-
# agnostic surface chrome only; these tokens never occur inside a genuine research claim.
_NAV_CHROME_RE = re.compile(
    r"copy link(?: to)?|press enter or click|click to view|\bmin read\b|read more|"
    r"view details|skip to (?:content|main)|share this|add to (?:cart|library)|"
    r"cookie(?:s)? (?:policy|settings)?|sign ?in|log ?in|subscribe|newsletter|"
    r"add_circle|remove_circle|main navigation|table of contents",
    re.IGNORECASE,
)


def _claim_bearing_rep_enabled() -> bool:
    """``PG_FINDING_CLAIMBEARING_REP`` kill switch (LAW VI, DEFAULT-ON, Fable Fix 2(S3)+8). ON =>
    the representative is preferentially a CLAIM-BEARING, COMPLETE sentence (no mid-sentence
    ``[...]`` truncation). OFF => byte-identical legacy (clean-rep only)."""
    return os.getenv("PG_FINDING_CLAIMBEARING_REP", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _is_claim_bearing_complete(row: dict[str, Any]) -> bool:
    """True iff the row's body reads as a CLAIM-BEARING, COMPLETE sentence (Fable Fix 2(S3)/8):
    enough content words, no mid-sentence ``[...]`` / trailing-ellipsis truncation, and it ends on
    terminal punctuation (or is a long enough clause). Deterministic + question-agnostic; used
    ONLY to PREFER a better representative among members (never to drop a row). FAIL-OPEN: a body
    we cannot read confidently returns True so a real claim is never demoted as representative."""
    text = _normalize_unicode_text(_row_text(row)).strip()
    if not text:
        return False
    if _MIDSENTENCE_TRUNCATION_RE.search(text):
        return False
    words = [w for w in re.split(r"\s+", text) if any(c.isalnum() for c in w)]
    if len(words) < 5:
        return False
    # A complete statement ends on terminal punctuation; a very long clause without it is still
    # accepted (fail-open — many extracted spans drop the final period).
    return bool(_SENTENCE_TERMINAL_RE.search(text)) or len(words) >= 8


def _nonclaim_basket_fold_enabled() -> bool:
    """``PG_FINDING_NONCLAIM_BASKET_FOLD`` kill switch (LAW VI, DEFAULT-ON, S2/S3 re-pass iter-2
    P0-4(b)). ON => the NON_CLAIM claim-bearing gate is extended from representative CHOICE to
    basket FORMATION: a row whose body is CONFIDENTLY non-claim-bearing (``_is_claim_bearing_
    complete`` returns False — a methods/header/citation-listing fragment: mid-sentence ``[...]``
    truncation, too few content words, no terminal) does NOT mint its OWN numeric finding basket
    when its SAME-WORK group already has a claim-bearing member. The fragment FOLDS INTO its
    work (still KEPT + same-work-annotated in ``deduped_rows``) instead of standing as a distinct
    claim / fake corroborator. §-1.1 FAIL-OPEN: the gate returns True on any doubt, so only a
    CONFIDENT fragment WITH a real claim-bearing sibling is folded — a genuine claim is never
    suppressed, and a work with NO claim-bearing member keeps every row as-is. OFF =>
    byte-identical (every row mints as before)."""
    return os.getenv("PG_FINDING_NONCLAIM_BASKET_FOLD", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _choose_clean_representative(member_ris: list[int], rank_fn, rows: list[dict[str, Any]]) -> int:
    """The highest-ranked member that is NOT chrome/degraded; if every member is unclean,
    the highest-ranked overall (best available). Deterministic (ties broken by rank_fn).

    Fable Fix 2(S3)+8: among the clean members, PREFER one that is a claim-bearing complete
    sentence (no mid-sentence ``[...]`` truncation), so the surfaced representative statement
    reads as a real claim rather than a boilerplate / truncated fragment. Falls back to the
    highest-ranked clean member, then the best available overall — never drops a member."""
    ranked = sorted(set(member_ris), key=rank_fn, reverse=True)
    if not _clean_rep_enabled():
        return ranked[0]
    clean = [ri for ri in ranked if not _rep_is_unclean(rows[ri])]
    if clean and _claim_bearing_rep_enabled():
        # Fix 6 (iter-4/iter-5, Fable): FIRST prefer a member whose reader-VISIBLE sentence is a
        # real MERGEABLE claim (claim-bearing AND not a license / ISSN / keyword / JEL / BibTeX /
        # Scopus-dump / 'Published by' / arXiv-cite-as / acknowledgment / contact boilerplate) and
        # is NOT a bare author list — so a basket never SURFACES metadata as its representative
        # statement (drb_72 #027 '@article{Noy2023...}' bibtex rep) while a real claim member
        # exists. P1-6 reuses ``_row_has_mergeable_claim`` (the unified ``_sentence_mergeable``
        # screen) on rep candidates. Fail-open: falls back to any claim-bearing, then any clean.
        for ri in clean:
            body = _row_text(rows[ri])
            if (
                _row_has_mergeable_claim(rows[ri])
                and not _is_author_list_line(body)
            ):
                return ri
        for ri in clean:
            if _is_claim_bearing_complete(rows[ri]):
                return ri
    if clean:
        return clean[0]
    return ranked[0]


# ─────────────────────────────────────────────────────────────────────────
# Measurement-numeral gate — S2/S3 re-pass P0-3b
# ─────────────────────────────────────────────────────────────────────────
# A chrome / bibliographic LINE that survived the line screen could still mint a FAKE numeric
# basket: an SSRN download id (4637198), a phone number (7721), a citation year, a page range,
# a print-run. §-1.3 keeps the LINE (as qualitative context) but a NON-measurement numeral must
# NOT mint a numeric CLAIM. This deterministic gate demotes ONLY when it is CONFIDENT the
# numeral is a locator/date/id, and NEVER when the line carries a real measurement unit
# (%/$/mg/...) — fail-open toward keeping the numeric claim. General, question-agnostic.
_MEASUREMENT_GATE_ENV = "PG_FINDING_MEASUREMENT_GATE"
# A real reported statistic almost always carries one of these unit/scale markers in-line.
_MEASUREMENT_UNIT_HINT_RE = re.compile(
    r"[%$€£¥]|\bpercent|\bper\s*cent|\bpercentage\b|\bpts?\b|\bbps\b|\bbasis points?\b|"
    r"\bmg\b|\bkg\b|\bml\b|\bmm\b|\bcm\b|\bkm\b|\bmmhg\b|\bmol\b|\bgb\b|\btb\b|"
    r"\bmillion\b|\bbillion\b|\btrillion\b|\bfold\b|\btimes\b|\bratio\b|±|"
    r"\bp\s*[<=>]\s*0?\.\d|\bn\s*=\s*\d|confidence interval|\bCI\b",
    re.IGNORECASE,
)
_CITATION_CONTEXT_RE = re.compile(
    r"\bet al\b|\bdoi\b|\bvol\.?\b|\bno\.\s*\d|\bpp?\.\b|\bissn\b|\bisbn\b|\barxiv\b|"
    r"\bssrn\b|\bretrieved\b|\baccessed\b|\beds?\.\b|\bjournal\b|\bworking paper\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"\btel\b|\bphone\b|\bfax\b|\+?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}",
    re.IGNORECASE,
)
_PAGE_RANGE_RE = re.compile(
    r"\bpp?\.\s*\d+(?:\s*[-–—]\s*\d+)?|\bpages?\s+\d+\s*[-–—]\s*\d+", re.IGNORECASE
)
_URL_OR_DOCID_RE = re.compile(
    r"https?://|\bdoi\.org\b|/abstract=|[?&]id=|arxiv\.org|ssrn\.com|\bisbn\b|\bissn\b|"
    r"javascript:|mailto:|tel:",
    re.IGNORECASE,
)
_YEAR_TOKEN_RE = re.compile(r"\b(?:19|20)\d{2}\b")
# S2/S3 re-pass Fix 6 (Fable) — extend the general non-measurement recall. A numeral with
# NO measurement unit AND a locator/date/id context is not a reported statistic. All patterns
# are question-agnostic; fail-open (a measurement unit anywhere on the line always wins first).
# An explicit calendar date (month name or D/M/Y, ISO, or 'Published on ...').
_CALENDAR_DATE_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2}\b|"
    r"\b\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b|"
    r"\bpublished on\b|\bupdated\b|\blast modified\b|\baccessed on\b",
    re.IGNORECASE,
)
# A structural locator: 'Section 4', 'Chapter 3', 'Figure 2', 'Table 5', 'Appendix B', 'Part II',
# a leading list ordinal ('3. Main findings'), footnote/endnote markers.
_SECTION_ORDINAL_RE = re.compile(
    r"\b(?:section|chapter|figure|fig\.?|table|tbl\.?|appendix|annex|part|box|panel|"
    r"exhibit|note|footnote|endnote|step|phase|volume|vol\.?|issue|no\.?)\s+\d",
    re.IGNORECASE,
)
_LEADING_ORDINAL_RE = re.compile(r"^\s*\d{1,3}[.)]\s+\S")
# ISSN / ISBN / working-paper / report / catalog identifiers, and DOI-suffix citation anchors.
_IDENTIFIER_CONTEXT_RE = re.compile(
    r"\bissn\b|\bisbn\b|\bwp/?\s*\d|\bworking paper\b|\bpolicy research working paper\b|"
    r"\bdiscussion paper\b|\breport (?:no\.?|number)\b|\bnber\b|\bdp\s*\d{3,}\b|"
    r"\bw\d{4,}\b|\bizawol\b|\b10\.\d{4,}\b|\bcatalog(?:ue)?\b|\bsku\b",
    re.IGNORECASE,
)
# A US ZIP / postal code in an address-ish context (5 digits, optional +4).
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_ADDRESS_CONTEXT_RE = re.compile(
    r"\b(?:st|street|ave|avenue|blvd|road|rd|suite|ste|floor|fl|drive|dr|"
    r"cambridge|ma|zip|postal)\b",
    re.IGNORECASE,
)


def _claim_value_is_bare_year(claim: Any, line: str) -> bool:
    """True when the claim's VALUE is a 4-digit calendar year (1900-2099) with no
    measurement unit — a publication/release/'by 20xx' date, not a statistic. General."""
    try:
        v = float(getattr(claim, "value", 0.0) or 0.0)
    except (TypeError, ValueError):
        return False
    if v != int(v):
        return False
    iv = int(v)
    if not (1900 <= iv <= 2099):
        return False
    # The value must actually surface as a year token on the line (avoids demoting a real
    # count that happens to equal ~2000 when no such token is present).
    return bool(_YEAR_TOKEN_RE.search(line))


def _measurement_gate_enabled() -> bool:
    """``PG_FINDING_MEASUREMENT_GATE`` kill switch (LAW VI). DEFAULT-ON: a confidently
    non-measurement numeral (phone / page-range / URL-or-doc id / bibliographic year) mints
    NO numeric claim (the LINE is still kept as qualitative context). OFF => byte-identical
    legacy (every extracted numeral mints a numeric key)."""
    return os.getenv(_MEASUREMENT_GATE_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _is_nonmeasurement_numeral(claim: Any, line_text: str) -> bool:
    """True ONLY when the claim's numeral is CONFIDENTLY a locator / date / id, not a reported
    measurement. Fail-open: any doubt -> False (mint the numeric claim). A claim the extractor
    tagged with a unit, OR a line carrying a measurement marker (%/$/mg/n=/CI/...), is ALWAYS a
    measurement (returns False first) so a real statistic on a line that also has a URL is never
    demoted. Pure/deterministic, question-agnostic."""
    unit = str(getattr(claim, "unit", "") or "").strip()
    if unit and unit not in ("-", "—"):
        return False
    line = _normalize_unicode_text(line_text or "")
    if not line:
        return False
    if _MEASUREMENT_UNIT_HINT_RE.search(line):
        return False  # a real measurement marker is present -> keep numeric (fail-open)
    if _PHONE_RE.search(line):
        return True
    if _PAGE_RANGE_RE.search(line):
        return True
    if _URL_OR_DOCID_RE.search(line):
        return True
    # A bibliographic year (citation context + a 19xx/20xx token, no measurement marker) is a
    # date, not a statistic.
    if _CITATION_CONTEXT_RE.search(line) and _YEAR_TOKEN_RE.search(line):
        return True
    # Fix 6 (Fable) — extended general non-measurement recall (all fail-open; a unit anywhere
    # on the line already returned False above).
    # (a) An explicit calendar date, OR the claim's own VALUE being a bare 4-digit year
    #     (release/publication/"by 20xx" — the software-release-year & 'Published on' cases).
    if _CALENDAR_DATE_RE.search(line):
        return True
    if _claim_value_is_bare_year(claim, line):
        return True
    # (b) A structural locator numeral: 'Section 4' / 'Chapter 3' / 'Figure 2' / 'Table 5' /
    #     a leading list ordinal ('3. Main findings') — a document-structure pointer, not a stat.
    if _SECTION_ORDINAL_RE.search(line) or _LEADING_ORDINAL_RE.search(line):
        return True
    # (c) An ISSN/ISBN/working-paper/report/DOI-suffix identifier context (WP/21/164, DP17923,
    #     w30957, izawol.514, ISSN fragments) — a catalog id, not a measurement.
    if _IDENTIFIER_CONTEXT_RE.search(line):
        return True
    # (d) A US ZIP / postal code sitting in an address-ish context.
    if _ZIP_RE.search(line) and _ADDRESS_CONTEXT_RE.search(line):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# P0-1 (S2/S3 re-pass iter-4, Fable) — boilerplate/heading MERGE guard (THE GHOST)
# ─────────────────────────────────────────────────────────────────────────
# The numeric-tuple / byte-identical key only PROPOSES a candidate merge; a pair may MERGE only
# when its anchor is a real CLAIM sentence (then a semantic same-claim confirm follows). A
# byte-identical HEADING / license / ISSN / keyword / submission-date / acknowledgment / contact /
# author-list line is NOT a claim — two DIFFERENT works that happen to share such a line (B025 'AME
# reporting checklist' boilerplate, B226 a section heading, B124 a generic CBA-methodology stub)
# must NEVER byte-identical-merge into one corroboration basket. The guard is question-agnostic
# (no entity list, no corpus number): it fires only on a CONFIDENT metadata/boilerplate pattern OR
# a non-propositional (too-short / truncated) line. Genuine byte-identical CLAIM merges (Weizenbaum
# 3x identical PDF, Eloundou 46%) are UNAFFECTED — a real claim sentence is neither boilerplate nor
# a bare heading, so it stays mergeable. §-1.3-safe: the guard only ever BLOCKS a merge (baskets
# stay SPLIT); it never drops a row and never relaxes faithfulness.
_BOILERPLATE_METADATA_RE = re.compile(
    r"\ball rights reserved\b|\bcreative commons\b|\bcc[\s\-]?by(?:[\s\-]?[a-z]{2})*\b|"
    r"\blicensed under\b|"
    r"\bthis (?:article|work|paper|content|document) is (?:distributed|licensed|published|"
    r"made available|an open[\s\-]access)\b|"
    r"\bopen[\s\-]access article\b|©|\(c\)\s*(?:19|20)\d{2}|\bcopyright\b|"
    r"\bissn\b|\bisbn\b|\bkeywords?\s*:|\bjel(?:\s+classification|\s+codes?|\s*:)\b|"
    r"\breceived\b[^.]{0,60}\baccepted\b|\bsubmitted\b[^.]{0,60}\brevised\b|"
    r"\bcorresponding author\b|\be[\s\-]?mail\s*:|\backnowledge?ments?\b|"
    r"\bconflicts? of interest\b|\bcite this (?:article|paper|work)\b|\bhow to cite\b|"
    r"\bterms (?:of use|and conditions)\b|\bprivacy policy\b|\bdownloaded from\b|"
    r"\bsupplementary (?:material|information)\b|"
    # P1-6 (iter-5, Fable) — additional non-claim REPRESENTATIVE metadata that shipped as a
    # basket's "statement": a BibTeX record (@article{...}/@inproceedings{...}), an arXiv
    # 'Cite as' / bare arXiv id, a 'Published by <publisher>' imprint line, and a Scopus
    # author-/indexed-keywords / document-type / source-type catalog dump. Question-agnostic +
    # conservative (a real reported claim never contains these tokens).
    r"@(?:article|inproceedings|book|incollection|techreport|misc|phdthesis|mastersthesis|"
    r"conference|unpublished)\s*\{|"
    r"\bcite as\s*:|\barxiv:\s*\d{4}\.\d{4,5}|\bdoi:\s*10\.\d{4}|"
    r"\bpublished by\b|\binforma uk\b|\btaylor (?:&|and) francis\b|"
    r"\bauthor keywords\b|\bindexed keywords\b|\bdocument type\s*:|\bsource type\s*:|"
    # P0-1 (S2/S3 re-pass iter-6, Fable Fix 4a) — additional CONFIDENT chrome/metadata LINE
    # classes still surfacing as basket REPRESENTATIVES: a RIS / Scopus bibliographic export tag
    # ('KW  - artificial intelligence', 'TY  - JOUR', 'ER  -', 'AU  - '), an SSRN cover-page
    # stamp ('Electronic copy available at: https://ssrn.com/abstract='), a preprint
    # not-peer-reviewed banner ('This version is not peer-reviewed'), and a US-federal-site
    # security banner ('Before sharing sensitive information ...', 'official website of the ...').
    # Question-agnostic + conservative (a real reported claim never leads with these tokens); this
    # only ever BLOCKS a line from being a merge key / rep — it never drops a row.
    r"^\s*(?:kw|ty|er|au|py|t1|t2|jo|jf|sp|ep|vl|is|sn|do|ur|n1|m3|da)\s{1,3}-\s|"
    r"\belectronic copy available at\b|"
    r"\bthis version is not peer[\s\-]?reviewed\b|"
    r"\bbefore sharing sensitive information\b|\bofficial website of the\b|"
    r"\ball content following this page\b|\bpo box\b",
    re.IGNORECASE,
)
# A whole line that is a byline (author list): >=2 'Surname, F.' / 'F. Surname' name tokens joined
# by comma/semicolon/&/'and', nothing else. Used ONLY for representative CHOICE (fix 6) — never in
# the merge gate — so a rare false positive can only demote a rep, never force-split a claim.
_AUTHOR_LIST_LINE_RE = re.compile(
    r"^\s*(?:(?:[A-Z][A-Za-z''\-]+,?\s+(?:[A-Z]\.[\s\-]*){1,3})|"
    r"(?:(?:[A-Z]\.[\s\-]*){1,3}[A-Z][A-Za-z''\-]+))"
    r"(?:\s*(?:,|;|&|\band\b)\s*(?:(?:[A-Z][A-Za-z''\-]+,?\s+(?:[A-Z]\.[\s\-]*){1,3})|"
    r"(?:(?:[A-Z]\.[\s\-]*){1,3}[A-Z][A-Za-z''\-]+)))+\s*[.,;]?\s*$",
)


def _is_boilerplate_or_metadata_line(text: str) -> bool:
    """True iff ``text`` is CONFIDENTLY a license / copyright / ISSN-ISBN / keyword / JEL /
    submission-date / acknowledgment / contact / how-to-cite / open-access boilerplate line —
    metadata, not a reported claim. Question-agnostic + conservative (a real claim never matches
    these targeted patterns). Fail toward False (not boilerplate) on doubt so a genuine claim is
    never force-split by the merge gate that consumes this."""
    s = _normalize_unicode_text(text or "").strip()
    if not s:
        return False
    return bool(_BOILERPLATE_METADATA_RE.search(s))


def _is_claim_bearing_sentence(text: str) -> bool:
    """True iff ``text`` reads as a real, complete PROPOSITION (a claim), not a bare heading /
    label / fragment. Text-level sibling of ``_is_claim_bearing_complete`` (which reads a ROW):
    >= 5 content words, no mid-sentence ``[...]`` / trailing-ellipsis truncation, and either
    terminal punctuation or a long enough clause. Question-agnostic + deterministic."""
    s = _normalize_unicode_text(text or "").strip()
    if not s:
        return False
    if _MIDSENTENCE_TRUNCATION_RE.search(s):
        return False
    # Fold out provenance / bracketed-citation tokens ([#ev:...], [12], (2024)) so a TRAILING
    # citation does not defeat the terminal-punctuation test nor pad the content-word count (the
    # rung-0 'AI will displace 300 million jobs. [#ev:e1:0-30]' case).
    s = _RUNG0_CITE_TOKEN_RE.sub(" ", s)
    # P0-1(c) (iter-5): fold out page-nav / share / reader-shell chrome so a bare HEADING with
    # glued nav ('Main findings from the consultation process Copy link to 3') cannot be padded
    # up to a "claim-bearing" word count and false-merge two different works on the heading.
    s = _NAV_CHROME_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return False
    words = [w for w in re.split(r"\s+", s) if any(c.isalnum() for c in w)]
    if len(words) < 5:
        return False
    return bool(_SENTENCE_TERMINAL_RE.search(s)) or len(words) >= 8


def _sentence_mergeable(text: str) -> bool:
    """P0-1 (Fable): a claim sentence may anchor a byte-identical / NLI same-claim MERGE only when
    it is a real CLAIM (claim-bearing) AND NOT boilerplate/metadata. A heading / license / byline
    can be byte-identical across two DIFFERENT works, so it must never be a merge key without a
    semantic claim confirm. §-1.3-safe: this only ever BLOCKS a merge (keeps baskets SPLIT); it
    never drops a row and never relaxes faithfulness. General/question-agnostic."""
    return _is_claim_bearing_sentence(text) and not _is_boilerplate_or_metadata_line(text)


def _qual_mergeable_screen_enabled() -> bool:
    """``PG_FINDING_QUAL_MERGEABLE_SCREEN`` kill switch (LAW VI, DEFAULT-ON, iter-5 P0-1(c)/P1-5,
    Fable). ON => a qualitative-candidate row whose body has NO mergeable CLAIM sentence (a bare
    heading / nav-link dump / catalog / license / bibliography with no propositional prose — the
    drb_72 basket-321 wustl profile-nav dump) is EXCLUDED from qualitative CLUSTERING (still KEPT
    as its own keep-all singleton row). OFF => byte-identical (no screen)."""
    return os.getenv("PG_FINDING_QUAL_MERGEABLE_SCREEN", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _row_has_mergeable_claim(row: dict[str, Any]) -> bool:
    """True iff the row's body yields a real, non-boilerplate CLAIM sentence (P0-1(c)/P1-5/P1-6):
    its reader-visible sentence is claim-bearing AND not license/heading/nav/metadata. A row with
    NO mergeable claim (a nav/link-list / catalog / bibliography / license-only body) can never
    anchor a same-claim merge and must never seed/join a corroboration basket. FAIL-OPEN on doubt
    via the claim-bearing predicate's own fail-open. Question-agnostic + deterministic."""
    return _sentence_mergeable(_visible_claim_sentence(row, None))


def _noclaim_basket_pool_enabled() -> bool:
    """``PG_FINDING_NOCLAIM_BASKET_POOL`` kill switch (LAW VI, DEFAULT-ON, S2/S3 re-pass iter-7
    P0-1(b), Fable). ON => a row whose ONLY reader-visible content is CONFIDENTLY publisher /
    cataloguing / license / correspondence / reference boilerplate (``_row_is_pure_boilerplate``)
    never FOUNDS a numeric claim basket — it is routed to a DISCLOSED no-claim pool (the row is
    still KEPT in ``deduped_rows`` as a keep-all singleton; only the fake numeric-basket founding is
    suppressed). §-1.3.1(a) chrome/boilerplate carve-out applied at basket FORMATION. FAIL-OPEN: a
    row with ANY real claim sentence never enters the pool. OFF => byte-identical (no pool)."""
    return os.getenv("PG_FINDING_NOCLAIM_BASKET_POOL", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _row_is_pure_boilerplate(row: dict[str, Any]) -> bool:
    """True iff the row's reader-visible sentence is CONFIDENTLY publisher / cataloguing / license /
    rights / correspondence / reference-list boilerplate AND the row yields NO mergeable claim
    (P0-1(b)). This is the basket-founding gate: such a row (a journal masthead, an ISSN/ISBN
    cataloguing line, a rights/copyright block, a correspondence-address block, a bare reference
    list) must never mint a claim basket. CONSERVATIVE + FAIL-OPEN: requires BOTH the confident
    boilerplate pattern (``_is_boilerplate_or_metadata_line`` — targeted, never a real claim) AND
    the absence of a mergeable claim, so a genuine (even short) claim sentence is never pooled.
    Question-agnostic + deterministic."""
    vis = _visible_claim_sentence(row, None)
    return _is_boilerplate_or_metadata_line(vis) and not _sentence_mergeable(vis)


def _is_author_list_line(text: str) -> bool:
    """True iff the WHOLE line is a byline / author list (no claim). Used ONLY for representative
    CHOICE (fix 6) so a basket never SHOWS an author-list as its statement when a claim-bearing
    member exists. Never used to drop or split — fail-open."""
    s = _normalize_unicode_text(text or "").strip()
    if not s or len(s.split()) < 3:
        return False
    return bool(_AUTHOR_LIST_LINE_RE.match(s))


# ─────────────────────────────────────────────────────────────────────────
# Metadata-less same-work fallback — S2/S3 re-pass P1-5
# ─────────────────────────────────────────────────────────────────────────
# A byte-identical long title with NO year/author/venue/host discriminator fell through the
# same-work legs to a per-URL singleton, so two mirrors of ONE work (ev_932 vs ev_945, exact
# title) fragmented and inflated the distinct-works count. Two general, bounded fallbacks:
#   (1) TITLE-ALONE key when the folded title is LONG + multi-token (discriminative) so a short
#       generic title never merges two distinct works. Safe under §-1.3: a work-merge only links
#       CITATIONS; the CLAIM merge still requires NLI same-meaning, so even a rare title-alone
#       over-merge cannot fabricate a corroborated CLAIM.
#   (2) A strong arXiv id extracted from the BODY header (first chars) when the URL carries none.
# Both LAW VI kill-switched (default ON).
_SAMEWORK_TITLE_ALONE_ENV = "PG_SAMEWORK_TITLE_ALONE"
_SAMEWORK_BODY_ID_ENV = "PG_SAMEWORK_BODY_ID"
_TITLE_ALONE_MIN_LEN = 40      # folded-title char floor (a long exact title rarely collides)
_TITLE_ALONE_MIN_TOKENS = 6    # word-token floor (discriminative)
_FILENAME_EXT_RE = re.compile(r"\.(pdf|html?|docx?|txt|epub|xml|ps)$", re.IGNORECASE)
_FILENAME_VERSION_TAIL_RE = re.compile(r"[_\-\s]+\d+([_\-\.]\d+)*$")
_BODY_ARXIV_ID_RE = re.compile(r"arxiv[:\s]*?(\d{4}\.\d{4,5})", re.IGNORECASE)


def _samework_title_alone_enabled() -> bool:
    """``PG_SAMEWORK_TITLE_ALONE`` kill switch (LAW VI). DEFAULT-ON."""
    return os.getenv(_SAMEWORK_TITLE_ALONE_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _samework_body_id_enabled() -> bool:
    """``PG_SAMEWORK_BODY_ID`` kill switch (LAW VI). DEFAULT-ON."""
    return os.getenv(_SAMEWORK_BODY_ID_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _samework_title_union_enabled() -> bool:
    """``PG_SAMEWORK_TITLE_UNION`` kill switch (LAW VI, DEFAULT-ON, S2/S3 re-pass iter-2 P0-4(a)).
    ON => AFTER work-groups are keyed, a SECOND union pass merges any two work-groups that share
    an identical DISCRIMINATIVE normalized title (the ``_title_alone_key`` signature — long-title
    + token floored). This is the cross-mirror bridge the per-row key CANNOT make: an arXiv copy
    keys ``id:arxiv:...`` while its governance.ai / PDF mirror (no arXiv id in the URL) falls to
    ``titlealone:...`` — DIFFERENT keys for the SAME work (EL25 vs EL56 'GPTs are GPTs'). A
    title-normalized match on a different host IS the same work. §-1.3-safe: it only folds the
    CORROBORATION COUNT (a weight) — the CLAIM merge still requires NLI same-meaning, so a rare
    title-alone over-fold can never fabricate a corroborated claim; every member URL is kept.
    OFF => byte-identical (no title union)."""
    return os.getenv("PG_SAMEWORK_TITLE_UNION", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _strip_filename_artifacts(title: Any) -> str:
    """Strip a trailing file extension + a trailing version/segment tail ('Noy_Zhang_1_0.pdf'
    -> 'Noy Zhang') BEFORE folding, so a filename-derived title matches its clean-metadata
    sibling. Pure. Only used on the title-alone fallback path (never on the shared _fold_title,
    so render parity is preserved)."""
    s = str(title or "").strip()
    if not s:
        return ""
    s = _FILENAME_EXT_RE.sub("", s)
    s = _FILENAME_VERSION_TAIL_RE.sub("", s)
    return s


def _title_alone_key(row: dict[str, Any]) -> str:
    """A same-work key on a LONG, discriminative folded title ALONE (P1-5). Returns '' when the
    folded (filename-stripped) title is too short/too-few-tokens to be discriminative — such a
    row stays a singleton (never merged on a weak title). General. Host-AGNOSTIC by design so
    ``_same_work_key`` stays byte-identical to ``weighted_enrichment._work_identity`` (render
    parity); the P1-2 cross-host false-merge is caught by the content verdict on the title-UNION
    pass, NOT by changing this key."""
    folded = _fold_title(_strip_filename_artifacts(_row_title(row)))
    if not folded:
        return ""
    if len(folded) < _TITLE_ALONE_MIN_LEN:
        return ""
    if len(folded.split()) < _TITLE_ALONE_MIN_TOKENS:
        return ""
    return "titlealone:" + folded


def _samework_content_confirm_enabled() -> bool:
    """``PG_SAMEWORK_CONTENT_CONFIRM`` kill switch (LAW VI, DEFAULT-ON, S2/S3 re-pass iter-7 P1-2,
    Fable). ON => a CROSS-KEY title-union candidate whose two work-groups' representative claim
    sentences CONFIDENTLY do NOT entail is BLOCKED (a forum thread / aggregator that merely SHARES a
    paper's title is not the same work — the drb_72 wikipedia+ebsco / forum+NBER / forbes+ahrefs
    citation mis-attribution). Parity-safe: the same-work KEY is NOT changed (``_same_work_key`` /
    ``weighted_enrichment._work_identity`` render parity intact); only the finding-dedup title-UNION
    pass consults the content verdict. FAIL-SAFE for P0-4a: an UNKNOWN verdict (NLI unavailable /
    flag off / empty rep) leaves the legacy union UNCHANGED, so a genuine cross-mirror still folds
    and no offline/NLI-down run regresses. OFF => byte-identical legacy union."""
    return os.getenv("PG_SAMEWORK_CONTENT_CONFIRM", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _group_rep_claim_text(member_ris: list[int], rows: list[dict[str, Any]]) -> str:
    """The representative CLAIM SENTENCE of a work-group for the P1-2 content-consistency check —
    the reader-visible claim sentence of the group's longest-body member (deterministic). Feeding the
    focused claim sentence (not the whole body) keeps the entailment from weakly firing on shared
    boilerplate."""
    if not member_ris:
        return ""
    best_ri = max(member_ris, key=lambda ri: len(_row_text(rows[ri])))
    return _visible_claim_sentence(rows[best_ri], None)


def _group_content_verdict(
    ris_a: list[int],
    ris_b: list[int],
    rows: list[dict[str, Any]],
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
) -> Optional[bool]:
    """P1-2 (Fable): the cross-host same-work content verdict — TRUE (a rep of group A and a rep of
    group B BIDIRECTIONALLY entail — same work), FALSE (a CONFIDENT non-entailment in >= 1 direction
    — a title-only collision, NOT the same work), or None (UNKNOWN — flag off / empty rep / NLI
    unavailable / infra fault). The caller BLOCKS a union only on an explicit FALSE and leaves the
    legacy union UNCHANGED on None (so a genuine cross-mirror still folds and no NLI-down run
    regresses P0-4a). ``entail_fn`` is the deterministic test seam (production None ⇒ the lazy
    resident ``entails_directional`` — the SAME cross-encoder the consolidation leg already loads)."""
    if not _samework_content_confirm_enabled():
        return None
    a = _group_rep_claim_text(ris_a, rows)
    b = _group_rep_claim_text(ris_b, rows)
    if not a.strip() or not b.strip():
        return None
    try:
        if entail_fn is None:
            from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
                entails_directional as entail_fn,
            )
        ab = entail_fn(a, b)
        ba = entail_fn(b, a)
    except Exception:  # noqa: BLE001 — any infra fault ⇒ UNKNOWN (leave legacy union unchanged)
        return None
    if ab is None or ba is None:
        return None  # UNKNOWN direction ⇒ do not block (P0-4a preserved)
    if ab is True and ba is True:
        return True
    return False  # a confident non-entailment in >= 1 direction ⇒ block the union


def _body_work_identifier(row: dict[str, Any]) -> str:
    """A STRONG arXiv id extracted from the BODY HEADER (first ~400 chars) when the URL carries
    no id (P1-5). Bounded to the header so a body that merely CITES another arXiv id in its
    references never mis-merges. Returns '' when none. Pure."""
    for key in ("direct_quote", "statement", "evidence_summary", "abstract", "text"):
        body = row.get(key)
        if not body:
            continue
        head = str(body)[:400]
        m = _BODY_ARXIV_ID_RE.search(head)
        if m:
            return "arxiv:" + m.group(1).lower()
    return ""


# ─────────────────────────────────────────────────────────────────────────
# Corroboration = DISTINCT WORKS + derivative-press label — Fix 5 + Fix 6
# ─────────────────────────────────────────────────────────────────────────
# Fix 5: ``corroboration_count`` must be the number of DISTINCT WORKS carrying the claim,
# not the number of distinct registrable-domains (which double-counts one work hosted at N
# mirrors and, without same-work folding, inflated the count). After Fix 4 collapses mirror
# copies into one work id, a basket's true corroboration is its distinct same-work-id count.
# A row with no same-work group is its own singleton work (counts as 1). Single-source
# claims honestly stay 1 — never inflated.
#
# Fix 6: derivative press/blog coverage of a primary paper is corroboration-OF-REPORTING at
# LOWER weight, NEVER independent evidence. It is KEPT in the basket (§-1.3 principle 1 —
# credible on-topic sources are only weighted, never deleted) but EXCLUDED from the
# distinct-works independent count. Detected conservatively from an EXPLICIT source-type /
# tier stamp the row already carries (news / press / blog / magazine / media); no stamp =>
# NOT flagged (fail-open: counted as independent). LAW VI kill-switches (default ON).
_DISTINCT_WORKS_ENV = "PG_CORROBORATION_DISTINCT_WORKS"
_DERIVATIVE_PRESS_ENV = "PG_CORROBORATION_DERIVATIVE_PRESS"
_PRESS_TYPE_TOKENS = (
    "news", "press", "blog", "magazine", "media outlet", "newspaper",
    "journalism", "op-ed", "opinion", "trade press",
)


def _distinct_works_enabled() -> bool:
    """``PG_CORROBORATION_DISTINCT_WORKS`` kill switch (LAW VI, default ON). OFF =>
    byte-identical independent-registrable-domain corroboration count."""
    return os.getenv(_DISTINCT_WORKS_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _derivative_press_enabled() -> bool:
    """``PG_CORROBORATION_DERIVATIVE_PRESS`` kill switch (LAW VI, default ON). OFF =>
    derivative press is counted as independent evidence (the pre-Fix-6 behavior)."""
    return os.getenv(_DERIVATIVE_PRESS_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


# S2/S3 re-pass Fix 8 (Fable): a derivative-press / event / explainer page that merely
# REPORTS a primary paper must actually FIRE the corroboration-OF-reporting label even when the
# row carries NO explicit source_type stamp (most fetched rows don't). General, conservative
# HOST/PATH signals: a news subdomain, a known blogging/explainer platform, or an
# event/announcement/press-release path. Fail-open (no signal => counted as independent).
_DERIVATIVE_HOST_RE = re.compile(
    r"(?:^|\.)news\.|(?:^|\.)blog\.|\bmedium\.com\b|\bsubstack\.com\b|"
    r"\bpunku\.[a-z]|\bprnewswire\.|\bbusinesswire\.|\bglobenewswire\.",
    re.IGNORECASE,
)
_DERIVATIVE_PATH_RE = re.compile(
    # NB: NO bare '/media/' — institutional CDNs (imf.org/-/media/files/publications/wp/...)
    # serve PRIMARY papers under /media/, so it is not a derivative-press signal.
    r"/news/|/blog/|/press-?releases?/|/newsroom/|/announcements?/|/events?/|"
    r"/stories/|/explainers?/|/press/(?!kit)",
    re.IGNORECASE,
)


def _is_derivative_press(row: dict[str, Any]) -> bool:
    """True iff the row is derivative reporting of a primary work (Fix 6/8). Two general
    signals, either sufficient: (1) an EXPLICIT news/press/blog/magazine source-type stamp;
    (2) a news/blog/explainer HOST or an event/announcement/press-release PATH in the URL.
    Conservative + fail-open: no signal => NOT flagged (counted as independent).
    Pure/deterministic, question-agnostic."""
    for key in (
        "source_type", "content_type", "doc_type", "material_type",
        "source_category", "tier_label", "publication_type",
    ):
        v = str(row.get(key) or "").strip().lower()
        if v and any(t in v for t in _PRESS_TYPE_TOKENS):
            return True
    url = _row_any_url(row)
    if url:
        host = _host_of(url)
        if host and _DERIVATIVE_HOST_RE.search(host):
            return True
        if _DERIVATIVE_PATH_RE.search(url):
            return True
    return False


# S2/S3 re-pass P2-8: a member confirmed as derivative press/blog/slide/column coverage of a
# primary work already in the pool is KEPT (keep-all) but WEIGHT-lowered + LABELLED so
# composition can present it as coverage, not an independent corroborator (it is already
# excluded from the distinct-works count). The factor is a disclosed multiplier (LAW VI env).
_DERIVATIVE_WEIGHT_FACTOR_ENV = "PG_DERIVATIVE_WEIGHT_FACTOR"
_DERIVATIVE_WEIGHT_FACTOR_DEFAULT = 0.5


def _derivative_weight_factor() -> float:
    """``PG_DERIVATIVE_WEIGHT_FACTOR`` in (0, 1] — the disclosed weight multiplier stamped on a
    derivative-press member (P2-8). Malformed / out-of-range => the 0.5 default (never raised)."""
    raw = os.environ.get(_DERIVATIVE_WEIGHT_FACTOR_ENV, "").strip()
    if not raw:
        return _DERIVATIVE_WEIGHT_FACTOR_DEFAULT
    try:
        value = float(raw)
    except (ValueError, TypeError):
        return _DERIVATIVE_WEIGHT_FACTOR_DEFAULT
    return value if 0.0 < value <= 1.0 else _DERIVATIVE_WEIGHT_FACTOR_DEFAULT


# ─────────────────────────────────────────────────────────────────────────
# Same-work consolidation — I-beatboth-011 #7 CORE (#1289)
# ─────────────────────────────────────────────────────────────────────────
#
# §-1.1 audit of a rendered report (outputs/p6_postfix_resume/workforce/
# drb_72_ai_labor/report.md) → DO_NOT_SHIP. The faithfulness engine is correct
# (zero fabricated findings) — the defect is at THIS consolidation layer: the
# SAME WORK appearing at multiple URLs was counted as N INDEPENDENT sources,
# padding breadth ~2-3x. Real examples: Autor [1][2][3][4] = ONE work;
# Frey & Osborne [8][9][10] = ONE; Acemoglu & Restrepo [5][6] = ONE.
#
# Fix (§-1.3 "consolidate, keep-all, never drop a corroborator"): GROUP rows
# that are the SAME WORK — same normalized DOI; else same folded title — into
# ONE same-work unit that KEEPS ALL its URLs as corroborating locators (multi-
# URL corroboration, never delete a real corroborator) but COUNTS / PRESENTS as
# ONE source, and that counts as ONE independent origin in a finding cluster's
# `corroboration_count` (so 4 URLs of one Autor paper across 4 domains stop
# inflating the independent-host tally to 4). Also DROP non-functional members:
# a CAPTCHA / anti-bot security stub (text contains "Just a moment" /
# "Performing security verification") and a truncated-intro duplicate that is a
# strict prefix of a longer member of the SAME work.
#
# FAITHFULNESS LOCK: this changes only how same-work members are GROUPED /
# COUNTED. strict_verify / NLI / 4-role D8 / provenance / span-grounding are
# untouched. `corroboration_count` is a credibility WEIGHT (Signal D), never a
# gate — de-padding it is faithfulness-neutral. Two GENUINELY different works
# (different DOI AND different folded title) are NEVER merged.
#
# COORDINATION (#1289): `generator/weighted_enrichment.py` does the ENRICHMENT-
# side / render-side same-work consolidation in parallel. The two MUST agree, so
# the same-work key computation below is the SHARED canonical contract and is
# duplicated BYTE-FOR-BYTE in both files (the no-new-source-file rule forbids a
# shared module, so the logic is copied and pinned here as the contract):
#   DOI first  → lowercased, strip a leading "doi:" / "https://doi.org/" /
#                "http://dx.doi.org/" (and https) prefix, trim, rstrip "/";
#                a USABLE DOI must start with the "10." registrant prefix
#                (anything else is noise). Non-empty wins → merge (DOI is a
#                strong unique identifier).
#   else TITLE → lowercased, drop non-alphanumeric (punctuation→space), collapse
#                runs of whitespace to one, strip; a foldable title must be
#                >= 12 chars (guards against an over-merge on a tiny/generic
#                title).
#
# I-beatboth-011 #4 (#1289) — P1 OVER-MERGE FIX (§-1.3: NEVER merge distinct
# works; under-merge is safe, over-merge corrupts breadth/attribution): the
# no-DOI branch MUST NOT merge on folded TITLE ALONE — two genuinely DIFFERENT
# works can share a normalized title and would be wrongly collapsed, losing
# distinct corroborators. So the no-DOI key requires folded title PLUS the FIRST
# PRESENT corroborating discriminator the records share, in this fixed priority
# order: publication YEAR → first-author SURNAME → VENUE/journal → URL HOST.
# A priority-ordered composite (NOT pairwise OR / union-find: OR-over-signals is
# non-transitive and over-merges through chains — A~B on year, A~C on author then
# B,C collapse though they share only a title) is a plain equality key: transitive
# by construction, drops into the existing single-key grouping, biased to
# UNDER-merge. If the title folds but NO discriminator is present, the row gets a
# title-only fingerprint that is NOT a same-work key → it stays its own singleton
# work (distinct), never merged on title alone.
# A row with neither a usable DOI nor (foldable title + a present discriminator)
# gets NO same-work key (it is its own singleton work — never merged on emptiness).
# CAPTCHA / anti-bot stub detection (I-beatboth-011 #7 P1, #1289). The bare phrase
# "just a moment" is NOT enough to drop a member — real prose can carry it ("Just a
# moment — the data show wages rose 5% in 2023"). Dropping such prose would violate
# §-1.3 keep-all. A drop requires the trigger phrase AND a STRONG WAF / security
# co-token (BYTE-IDENTICAL predicate shared with weighted_enrichment._is_captcha_stub
# so consolidation and render agree). The co-tokens are high-precision multi-word /
# branded anchors a genuine clinical sentence (any language) never contains.
_CAPTCHA_STUB_TRIGGER = "just a moment"
_WAF_CO_TOKENS = (
    "performing security verification",   # Cloudflare / generic WAF
    "checking your browser",              # Cloudflare "checking your browser before accessing"
    "cloudflare",                         # Cloudflare attribution / interstitial brand
    "ray id",                             # Cloudflare error footer "Ray ID: ..."
    "cf-ray",                             # Cloudflare response-header / footer token
    "enable javascript and cookies",      # Cloudflare retry prompt
    "ddos protection",                    # Cloudflare attribution stub
    "attention required",                 # Cloudflare 1020 / block interstitial title
    "verifying you are human",            # hCaptcha / Cloudflare Turnstile
    "needs to review the security of your connection",  # Cloudflare interstitial body
)
# S2/S3 re-pass Fix 1(a)(b) + Fix 8: a GENERAL anti-bot / shell CHROME class evaluated on
# the TITLE+BODY UNION and GUARDED by "the body carries no propositional prose sentence" so
# a real article whose FIRST fetch hit a bot wall (but whose body was recovered) is NEVER
# chrome-deleted. The base ``_is_captcha_stub`` read only the BODY and fired only on the
# literal "just a moment" trigger, so a stub carrying the tell ONLY in its TITLE (ev_065:
# body "## Security check required ... ResearchGate GmbH", no body trigger) survived
# (30/33 chrome rows survived). These anchors are high-precision anti-bot / WAF /
# challenge-shell phrases a genuine research sentence (any language) does not carry.
# LAW VI kill-switch ``PG_CI_ANTIBOT_SHELL`` (default ON).
_CI_ANTIBOT_SHELL_ENV = "PG_CI_ANTIBOT_SHELL"
_ANTIBOT_SHELL_PATTERNS = (
    "just a moment",
    "security check required",
    "security check",
    "checking your browser",
    "checking if the site connection is secure",
    "enable javascript and cookies",
    "please enable javascript",
    "please enable cookies",
    "verify you are human",
    "verify you are not a robot",
    "verifying you are human",
    "verifying your browser",
    "are you a robot",
    "attention required",
    "one more step",
    "access denied",
    "performing security verification",
    "needs to review the security of your connection",
    "ray id",
    "cf-ray",
    "unusual activity",
    "unusual traffic",
    "ddos protection by",
)
_PROPOSITIONAL_MIN_WORDS_ENV = "PG_CHROME_PROPOSITIONAL_MIN_WORDS"
_DEFAULT_PROPOSITIONAL_MIN_WORDS = 8
_CONTENT_WORD_RE = re.compile(r"[A-Za-zÀ-ɏ]{2,}")
_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n。！？]+")


def _ci_antibot_shell_enabled() -> bool:
    """``PG_CI_ANTIBOT_SHELL`` kill switch (LAW VI). DEFAULT-ON: the general anti-bot /
    shell chrome class (title+body union, propositional-sentence guarded). OFF => the
    byte-identical legacy trigger+WAF-only ``_is_captcha_stub``."""
    return os.getenv(_CI_ANTIBOT_SHELL_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _has_propositional_sentence(body: str) -> bool:
    """True iff ``body`` carries at least one substantive PROSE sentence — a sentence with
    >= ``PG_CHROME_PROPOSITIONAL_MIN_WORDS`` alphabetic content words that is NOT itself an
    anti-bot / chrome phrase. FAIL-OPEN guard on the general chrome class: a real article
    (or a Zyte-recovered body) always has propositional prose so it is never chrome-deleted;
    a bare shell ("Security check required. To continue, enable JavaScript and cookies.")
    has none. Pure/deterministic; shared with the render/access_bypass mirrors."""
    if not body:
        return False
    raw = os.getenv(_PROPOSITIONAL_MIN_WORDS_ENV, "").strip()
    try:
        floor = int(raw) if raw else _DEFAULT_PROPOSITIONAL_MIN_WORDS
    except ValueError:
        floor = _DEFAULT_PROPOSITIONAL_MIN_WORDS
    if floor <= 0:
        floor = _DEFAULT_PROPOSITIONAL_MIN_WORDS
    for sent in _SENTENCE_SPLIT_RE.split(body):
        low = sent.lower()
        # Remove any anti-bot phrase SPAN, then count the remaining word tokens: a REAL sentence
        # that merely MENTIONS a security term ("access denied errors rose 12% after the upgrade")
        # keeps its other words and counts as prose; a bare chrome line collapses to near-nothing.
        # Leans toward KEEP — the §-1.3 / clinical-safe direction (never delete real prose).
        for p in _ANTIBOT_SHELL_PATTERNS:
            if p in low:
                low = low.replace(p, " ")
        if len(_CONTENT_WORD_RE.findall(low)) >= floor:
            return True
    return False


_DOI_PREFIX_RE = re.compile(
    r"^(?:doi:|https?://(?:dx\.)?doi\.org/)", re.IGNORECASE
)
_TITLE_NONALNUM_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
# Minimum folded-title length to be a usable same-work title (over-merge guard on
# a tiny/generic title). SHARED with weighted_enrichment._normalize_title.
_MIN_TITLE_LEN = 12
# Publication-year validity bounds (SHARED with the selector's _row_year convention
# at evidence_selector.py:769-770). A year outside this range is treated as absent.
_MIN_YEAR = 1900
_MAX_YEAR = 2100


def _normalize_doi(doi: Any) -> str:
    """Canonical DOI for same-work grouping (SHARED contract — see module note).

    Lowercase → strip a leading ``doi:`` / ``https://doi.org/`` /
    ``http://dx.doi.org/`` (http+https) prefix → trim → ``rstrip("/")``. A usable
    DOI starts with the ``10.`` registrant prefix; anything else is noise.
    Returns ``""`` for a missing / blank / non-``10.`` DOI (it never groups two
    works). Matches ``weighted_enrichment._normalize_doi`` byte-for-byte.
    """
    text = str(doi or "").strip().lower()
    if not text:
        return ""
    text = _DOI_PREFIX_RE.sub("", text).strip().rstrip("/")
    return text if text.startswith("10.") else ""


def _fold_title(title: Any) -> str:
    """Case/punct/whitespace-folded title for same-work grouping (SHARED
    contract — see module note).

    Lowercase → every non-alphanumeric run → single space → collapse whitespace
    → strip. Returns ``""`` when the folded title is shorter than
    ``_MIN_TITLE_LEN`` (a tiny/generic title is an over-merge risk and never
    groups two works). Matches ``weighted_enrichment._normalize_title``.
    """
    text = str(title or "").strip().lower()
    if not text:
        return ""
    text = _TITLE_NONALNUM_RE.sub(" ", text)
    text = _WHITESPACE_RUN_RE.sub(" ", text).strip()
    return text if len(text) >= _MIN_TITLE_LEN else ""


def _row_title(row: dict[str, Any]) -> str:
    """The row's title across the schema aliases (``source_title`` is canonical;
    ``title`` / ``page_title`` / ``name`` are the validator-mapped variants)."""
    for key in ("source_title", "title", "page_title", "name"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _row_year(row: dict[str, Any]) -> str:
    """Publication year as a discriminator token ('' when absent/invalid).

    Reads ``row['year']`` else ``row['metadata']['year']`` and validates the
    [1900, 2100] range — the SHARED convention with the selector's ``_row_year``
    (evidence_selector.py:793-809) and ``weighted_enrichment._record_year``.
    """
    val = row.get("year")
    if val is None:
        meta = row.get("metadata")
        if isinstance(meta, dict):
            val = meta.get("year")
    if val is None:
        return ""
    try:
        year = int(val)
    except (TypeError, ValueError):
        return ""
    return str(year) if _MIN_YEAR <= year <= _MAX_YEAR else ""


def _first_author_surname(row: dict[str, Any]) -> str:
    """First-author surname (folded) as a discriminator token ('' when absent).

    Records carry ``authors`` (a list, family-name-first, e.g. ``["Autor D", ...]``)
    or a singular ``author`` string. The surname is the FIRST whitespace token of
    the first author, lowercased + non-alphanumerics stripped. SHARED with
    ``weighted_enrichment._first_author_surname``.
    """
    raw = row.get("authors")
    first = ""
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if entry and str(entry).strip():
                first = str(entry).strip()
                break
    elif raw:
        first = str(raw).strip()
    if not first:
        single = row.get("author")
        if single and str(single).strip():
            first = str(single).strip()
    if not first:
        return ""
    surname = first.split()[0] if first.split() else ""
    surname = _TITLE_NONALNUM_RE.sub("", surname.lower())
    return surname


def _row_venue(row: dict[str, Any]) -> str:
    """Venue/journal (folded) as a discriminator token ('' when absent).

    Reads ``venue`` else ``journal`` (the two schema aliases), lowercased with
    non-alphanumeric runs collapsed to a single space and trimmed. SHARED with
    ``weighted_enrichment._record_venue``.
    """
    raw = row.get("venue") or row.get("journal") or ""
    text = str(raw).strip().lower()
    if not text:
        return ""
    text = _TITLE_NONALNUM_RE.sub(" ", text)
    return _WHITESPACE_RUN_RE.sub(" ", text).strip()


def _row_host(row: dict[str, Any]) -> str:
    """URL host (no leading ``www.``) as the WEAKEST discriminator token.

    Same-work fetches usually span DIFFERENT hosts (the Autor example spans 4
    domains), so host merges almost nothing — it is last in the priority order
    purely as a safety net. SHARED with ``weighted_enrichment._record_host``.
    """
    return _host_of(str(row.get("source_url", "") or row.get("url", "") or ""))


def _title_discriminator(row: dict[str, Any]) -> str:
    """The STRICT corroborating discriminator for the no-DOI title branch.

    I-beatboth-011 #4 P2 hardening (#1289): the no-DOI key MUST be strong enough that
    two DISTINCT works sharing a title cannot merge on a single weak signal. A single
    weak signal alone (year-only or host-only) is NOT enough. The token requires the
    folded title PLUS either:
      * a STRONG discriminator (first-author surname and/or venue) — every present
        STRONG/year signal is folded in (year → author → venue, fixed order), so a
        differing year OR differing author OR differing venue yields a DIFFERENT token
        and the two works do NOT merge; OR
      * two INDEPENDENT WEAK signals (year AND host) when no strong signal is present.

    HOST IS ENABLING-ONLY, NEVER BLOCKING. Same-work members are the same work fetched
    at DIFFERENT URLs, so they (almost) always differ on host (the ``_row_host``
    safety-net premise + §-1.3). Host therefore appears ONLY as the SECOND weak signal
    alongside year, and NEVER in the strong-path token — otherwise every legitimate
    same-work merge (which spans different hosts) would be blocked.

    Returns '' when neither a strong signal nor (year AND host) is present, so the row
    stays a title-only singleton and is never merged on title alone. SHARED contract with
    ``weighted_enrichment._title_discriminator`` (byte-identical key string).
    """
    year = _row_year(row)
    surname = _first_author_surname(row)
    venue = _row_venue(row)
    host = _row_host(row)
    if surname or venue:
        parts: list[str] = []
        if year:
            parts.append("y:" + year)
        if surname:
            parts.append("a:" + surname)
        if venue:
            parts.append("v:" + venue)
        return "|".join(parts)
    if year and host:
        return "y:" + year + "|h:" + host
    return ""


# ─────────────────────────────────────────────────────────────────────────
# Same-URL / same-file consolidation — I-deepfix-003 STEP 4 (#1374)
# ─────────────────────────────────────────────────────────────────────────
# §-1.3 CONSOLIDATE-don't-DROP: a chunked PDF (e.g. "reb-t-9-2-2026.pdf") with NO
# DOI and only weak/varying per-chunk titles produced an EMPTY ``_same_work_key`` for
# every chunk, so ~18 chunks of the SAME file each became their OWN singleton work —
# 18 phantom independent sources padding breadth/attribution. The DOI + title legs
# below cannot catch it (no DOI; the per-chunk title folds to nothing / lacks a
# discriminator), so nothing groups them.
#
# THE FIX (a FIRST, highest-precedence leg): two rows fetched from the SAME document —
# the SAME normalized source_url — are the SAME WORK, period. A shared fetch URL
# identifies one document more reliably than a missing/noisy extracted DOI or a weak
# per-chunk title. A usable normalized URL yields a ``url:<normalized>`` key that every
# chunk of one file shares => ONE same-work group. KEEP-ALL: each member's evidence_id /
# URL is kept as a corroborating locator (counted/presented as ONE source, never dropped).
# FAITHFULNESS-NEUTRAL: same-work grouping is a WEIGHT / render concern — strict_verify /
# NLI / 4-role D8 / provenance / span-grounding are untouched, and a shared-URL group
# counts as exactly ONE independent origin in a finding cluster's ``corroboration_count``.
#
# NORMALIZATION (§-1.3 "over-merge corrupts attribution; under-merge is safe"): scheme +
# lowercased host (leading ``www.`` stripped) + path (trailing ``/`` stripped), FRAGMENT
# dropped. A usable URL key requires a NON-EMPTY path — a host-only URL (e.g.
# "https://site.com/") is far too coarse (it would fold every page of a site into one
# work) and falls through to the DOI/title legs. A bare filename with no host
# ("reb-t-9-2-2026.pdf") uses the path alone (the task's "for a PDF the filename is
# sufficient").
#
# QUERY IS KEPT — a §-1.3-mandated refinement of the STEP-4 brief's "drop the query".
# Because this leg is HIGHEST precedence, DROPPING the query would over-merge two
# GENUINELY DIFFERENT works served by the SAME endpoint that differ ONLY in an
# identity-bearing query param — e.g. "site/download?doi=10.1/a" vs "?doi=10.2/b", or
# "viewer?docid=123" vs "?docid=456" — folding them into one work even though their DOIs
# differ. That is exactly the distinct-work over-merge §-1.3 (operator-locked) forbids.
# Keeping the query still fixes the reported bug (the 18 chunks carry the SAME full
# source_url, query included, so they still merge); the only cost is a SAFE UNDER-merge —
# two fetches of one doc that differ solely by fetch-time tracking noise (utm_* etc.) stay
# separate, which is the §-1.3-preferred failure side. (The finding_dedup independent-host
# tally already collapses same-URL rows to ONE origin via ``count_independent_hosts``; the
# URL leg's decisive effect is de-padding the same-work / breadth / render layer.)
#
# NOTE — SHARED CONTRACT: the DOI/title legs are duplicated byte-for-byte in
# ``weighted_enrichment._work_identity`` (the render/enrichment-side consolidator), and the
# SAME URL leg is now mirrored THERE too (Fable gate P1-C, GH I-deepfix-003 #1374) behind the
# SAME ``PG_SAMEWORK_URL_LEG`` switch — so BOTH the corroboration-side and render/enrichment-
# side consolidators collapse a no-DOI / weak-title multi-chunk PDF to one work (full lockstep
# parity, verified by tests/polaris_graph/test_work_identity_url_mirror.py).
#
# LAW VI kill-switch ``PG_SAMEWORK_URL_LEG`` (default ON). OFF => the URL leg is skipped and
# the key is BYTE-IDENTICAL to the pre-STEP-4 DOI/title-only keying.
_SAMEWORK_URL_LEG_ENV = "PG_SAMEWORK_URL_LEG"


def _samework_url_leg_enabled() -> bool:
    """``PG_SAMEWORK_URL_LEG`` kill switch (LAW VI). DEFAULT-ON: the same-URL same-work
    leg (STEP 4). Set to ``0`` to restore the byte-identical DOI/title-only
    ``_same_work_key`` (no URL leg — the pre-STEP-4 behavior)."""
    return os.getenv(_SAMEWORK_URL_LEG_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _normalize_source_url(row: dict[str, Any]) -> str:
    """The NORMALIZED same-work URL identity of a row (``""`` when there is no usable URL).

    scheme + lowercased host (leading ``www.`` stripped) + path (trailing ``/`` stripped),
    with the FRAGMENT dropped and the QUERY KEPT (see the module note above — dropping the
    query would over-merge identity-in-query works; keeping it only risks a §-1.3-safe
    under-merge). A usable key requires a NON-EMPTY path (a host-only URL is too coarse and
    returns ``""``); a bare filename with no host uses the path alone. A blank / unparseable
    URL returns ``""`` so the caller falls through to the DOI / title legs.
    """
    raw = str(row.get("source_url", "") or row.get("url", "") or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw)
    host = (parsed.hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    path = (parsed.path or "").rstrip("/")
    if not path:
        # Host-only (or empty) URL: too coarse to identify ONE document — fall through
        # to the DOI / title legs rather than fold an entire host into one work.
        return ""
    scheme = (parsed.scheme or "").lower()
    prefix = (scheme + "://" + host) if host else ""
    query = parsed.query
    return prefix + path + (("?" + query) if query else "")


# ─────────────────────────────────────────────────────────────────────────
# Cross-host FILENAME same-work identity — S2/S3 re-pass iter-5 P1-2 (Fable)
# ─────────────────────────────────────────────────────────────────────────
# The corpus rows rarely carry a DOI/authors (only a handful) but the SAME working paper is
# frequently rehosted at multiple institutional mirrors under an IDENTICAL, DISTINCTIVE FILENAME
# (drb_72: 'cesifo1_wp10601.pdf' at econstor.eu AND ifo.de — one CESifo WP10601 counted as 2-3
# works). A discriminative URL basename shared across DIFFERENT hosts IS the same document. This
# is a WORK-IDENTITY union (folds the corroboration COUNT only — a Signal-D weight; the CLAIM
# merge still needs NLI, so a rare basename collision can never fabricate a corroborated claim,
# and every member URL is kept as a locator, §-1.3 keep-all). Generic / non-discriminative
# basenames (index / download / a bare number / a short slug) are REJECTED so two different works
# never merge on a boilerplate filename. LAW VI kill switch (default ON).
_SAMEWORK_FILENAME_ENV = "PG_SAMEWORK_FILENAME_UNION"
_URL_BASENAME_EXT_RE = re.compile(r"\.(pdf|html?|docx?|txt|epub|xml|ps|ashx|aspx?)$", re.IGNORECASE)
# A trailing version / duplicate suffix on a filename basename: one OR MORE numeric groups
# (``_1``, ``_1_0``, ``-v2``, ``.3``) and/or a parenthetical copy marker (``(1)``). Fable Fix 6
# (S2/S3 re-pass): the base regex stripped only ONE group, so ``noy_zhang_1`` folded to
# ``noy_zhang`` while its ``noy_zhang_1_0`` mirror folded to ``noy_zhang_1`` — two copies of ONE
# paper (economics.mit.edu Noy_Zhang_1.pdf vs Noy_Zhang_1_0.pdf, drb_72 #78) counted as two
# works. Stripping the WHOLE repeated tail folds both to ``noy_zhang``. Bounded by the 8-char
# discriminative floor + generic-basename reject below, so a short/meaningful trailing number is
# never over-stripped (§-1.3-safe: a rare basename over-fold lowers the corroboration COUNT — a
# weight — only; the CLAIM merge still needs NLI, so it can never fabricate a corroborated claim,
# and every member URL is kept as a locator). Fable's safe default: unsure whether two mirrors
# are one work => count ONE work, keep both citations.
_URL_BASENAME_VERSION_TAIL_RE = re.compile(r"(?:[._\-]v?\d+)+$|\(\d+\)$")
# Non-discriminative basenames that many distinct works share — never a same-work signal.
_GENERIC_BASENAMES = frozenset({
    "index", "download", "downloads", "view", "viewer", "full", "fulltext", "abstract",
    "default", "home", "paper", "papers", "article", "articles", "document", "pdf",
    "file", "files", "content", "main", "show", "print", "read", "get", "doc", "docs",
    "en", "html", "entry", "publication", "publications", "report", "reports", "summary",
})


def _samework_filename_union_enabled() -> bool:
    """``PG_SAMEWORK_FILENAME_UNION`` kill switch (LAW VI, DEFAULT-ON, iter-5 P1-2)."""
    return os.getenv(_SAMEWORK_FILENAME_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _url_basename_key(row: dict[str, Any]) -> str:
    """A cross-host same-work key on a DISCRIMINATIVE URL basename (last path segment), or ``""``
    when the basename is generic / too short / a bare number to be a reliable identifier. Strips a
    trailing file extension + version tail; lowercased. 'cesifo1_wp10601.pdf' -> 'file:cesifo1_wp10601';
    'index.html' / 'download' / '61147' -> '' (never merges two works). Pure/question-agnostic."""
    raw = str(row.get("source_url", "") or row.get("url", "") or "").strip()
    if not raw:
        return ""
    path = (urlparse(raw).path or "").rstrip("/")
    if not path or "/" not in path:
        base = path.lstrip("/")
    else:
        base = path.rsplit("/", 1)[-1]
    base = _URL_BASENAME_EXT_RE.sub("", base).strip().lower()
    base = _URL_BASENAME_VERSION_TAIL_RE.sub("", base)
    base = base.strip("._-")
    if not base or base in _GENERIC_BASENAMES:
        return ""
    # Discriminative: at least 8 chars AND not a bare number (a numeric-only id like a CBO
    # publication number '61147' is host-specific — different works reuse short numeric slugs).
    if len(base) < 8 or base.isdigit():
        return ""
    return "file:" + base


# ─────────────────────────────────────────────────────────────────────────
# Cross-mirror same-work identity — S2/S3 re-pass Fix 4
# ─────────────────────────────────────────────────────────────────────────
# §-1.3 CONSOLIDATE-don't-DROP + "over-merge corrupts attribution; under-merge is safe":
# the base ``_same_work_key`` put the full-URL leg FIRST, so the SAME work fetched at
# DIFFERENT mirror URLs (Eloundou "GPTs are GPTs" across governance.ai / openai.com /
# repec / newyorkfed / worldbank.org; an arXiv paper at arxiv.org vs a repec mirror; an
# NBER working paper at nber.org vs a university mirror; Noy & Zhang across several hosts)
# got a DISTINCT ``url:`` key per mirror and NEVER merged — every mirror counted as an
# independent work, padding breadth/attribution.
#
# FIX (general, no host/entity/basket hardcoding):
#   1. Extract a STRONG cross-mirror identifier from the URL itself — an arXiv id, an
#      NBER working-paper number, an SSRN abstract id, or a DOI embedded in the path. Two
#      rows carrying the SAME such id are the SAME work regardless of host.
#   2. Let the DOI + URL-identifier + folded-title(+author/discriminator) legs run BEFORE
#      the full-URL leg, so a cross-mirror work merges on its shared id / title+author while
#      a chunked no-id/no-title PDF still falls through to the full-URL leg (its last resort).
# Both gated behind ``PG_SAMEWORK_CROSSMIRROR`` (default ON); OFF => byte-identical to the
# URL-leg-first ordering. SHARED byte-for-byte with ``weighted_enrichment._work_identity``.
_SAMEWORK_CROSSMIRROR_ENV = "PG_SAMEWORK_CROSSMIRROR"
_ARXIV_ID_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf|html|format)/"
    r"(?:([a-z-]+(?:\.[a-z]{2})?/\d{7})|(\d{4}\.\d{4,5}))",
    re.IGNORECASE,
)
_NBER_ID_RE = re.compile(
    r"nber\.org/(?:system/files/working_papers/|papers/)?w(\d{3,6})", re.IGNORECASE
)
# S2/S3 re-pass iter-4 Fix 3 (Fable): match BOTH SSRN abstract-id URL forms — the
# ``papers.cfm?abstract_id=`` (underscore) and the ``Delivery.cfm?abstractid=`` (no underscore)
# download form are the SAME work; the optional ``_`` in ``abstract_?id`` folds both, so two
# mirror locators of one SSRN paper share one work id instead of each minting a distinct ``url:``
# key (a §-1.3 fake corroboration). Question-agnostic; the numeric id keeps two works apart.
_SSRN_ID_RE = re.compile(
    r"(?:ssrn\.com/abstract=|ssrn_id=|abstract_?id=)(\d{4,9})", re.IGNORECASE
)
_DOI_IN_URL_RE = re.compile(r"(10\.\d{4,9}/[^\s?#&]+)")
# S2/S3 re-pass iter 2: a bare arXiv id embedded in a NON-arxiv.org MIRROR path. repec
# (ideas.repec.org/p/arx/papers/2303.10130.html) and HuggingFace (huggingface.co/papers/
# 2303.10130) host the SAME work under a /papers/<id> path, but the base _ARXIV_ID_RE fires
# only on the arxiv.org host, so those mirror copies kept a distinct url: key and inflated
# the distinct-works corroboration count (Eloundou "GPTs are GPTs" fragmented). The modern
# arXiv id form YYMM.NNNNN is a GLOBALLY UNIQUE work id, so matching it as a BOUNDED path
# segment after a papers/abs/pdf/html/format token (or an arxiv: scheme) is a SAFE
# cross-mirror merge that never over-merges two different works. Bounded by an optional
# version suffix + a delimiter/end lookahead so a longer digit run is never mis-captured.
_ARXIV_BARE_ID_RE = re.compile(
    r"(?:/(?:abs|pdf|html|format|papers?)/|arxiv[:/])(\d{4}\.\d{4,5})(?:v\d+)?(?=[/.?#]|$)",
    re.IGNORECASE,
)
# S2/S3 re-pass Fable Fix 3: the RePEc handle (a GLOBALLY UNIQUE economics-work id). IDEAS
# (ideas.repec.org) and EconPapers (econpapers.repec.org) — plus a bare ``RePEc:arch:series:id``
# handle carried in citation text — are DIFFERENT LOCATOR pages of the SAME work; without this
# leg each mirror kept a distinct ``url:`` key and inflated the distinct-works corroboration
# count (a §-1.3 fake-corroboration). The path form ``/<type>/<archive>/<series>/<id>`` (type =
# p paper / a article / b chapter / h /...): archive:series:id is the handle identity shared by
# every mirror, so we drop the host + type letter and key on it. Question-agnostic; never merges
# two different handles (id is included). An arXiv paper mirrored on repec is caught by the arXiv
# leg ABOVE (runs first), so it still cross-mirrors with arxiv.org.
_REPEC_URL_HANDLE_RE = re.compile(
    r"(?:ideas|econpapers)\.repec\.org/[a-z]/([a-z0-9]+)/([a-z0-9]+)/([a-z0-9][a-z0-9._-]*?)"
    r"(?:\.html?)?(?=[?#]|$)",
    re.IGNORECASE,
)
_REPEC_BARE_HANDLE_RE = re.compile(
    r"\brepec:([a-z0-9]+):([a-z0-9]+):([a-z0-9][a-z0-9._-]*)", re.IGNORECASE
)


def _samework_crossmirror_enabled() -> bool:
    """``PG_SAMEWORK_CROSSMIRROR`` kill switch (LAW VI). DEFAULT-ON: URL-embedded
    identifier extraction + id/title-before-full-URL ordering (Fix 4). OFF => the
    byte-identical URL-leg-first ``_same_work_key`` (pre-Fix-4 behavior)."""
    return os.getenv(_SAMEWORK_CROSSMIRROR_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _url_work_identifier(row: dict[str, Any]) -> str:
    """A STRONG cross-mirror work id extracted from the row's URL(s), else ``""``.

    Priority arXiv id > NBER wNNNNN > SSRN abstract id > DOI-embedded-in-path. Every
    such id is HOST-INDEPENDENT, so two mirrors of ONE work share it and merge (Fix 4).
    Pure/deterministic; matches ``weighted_enrichment._url_work_identifier`` byte-for-byte.
    Returns ``""`` when no strong id is present (the caller falls through to title/URL)."""
    raw = str(row.get("source_url", "") or row.get("url", "") or "")
    if not raw:
        return ""
    m = _ARXIV_ID_RE.search(raw)
    if m:
        return "arxiv:" + (m.group(1) or m.group(2)).lower()
    # iter 2: a bare arXiv id carried in a non-arxiv.org mirror /papers/ path (repec, HF).
    m = _ARXIV_BARE_ID_RE.search(raw)
    if m:
        return "arxiv:" + m.group(1).lower()
    # Fable Fix 3: a RePEc handle (IDEAS / EconPapers URL, or a bare RePEc: handle) — the same
    # economics work at two repec mirrors shares archive:series:id, so they merge instead of each
    # minting a distinct url: key (fake corroboration). arXiv-on-repec is already caught above.
    m = _REPEC_URL_HANDLE_RE.search(raw)
    if m:
        return "repec:" + ":".join(g.lower() for g in m.groups())
    m = _REPEC_BARE_HANDLE_RE.search(raw)
    if m:
        return "repec:" + ":".join(g.lower() for g in m.groups())
    m = _NBER_ID_RE.search(raw)
    if m:
        return "nber:w" + m.group(1)
    m = _SSRN_ID_RE.search(raw)
    if m:
        return "ssrn:" + m.group(1)
    m = _DOI_IN_URL_RE.search(raw)
    if m:
        doi = m.group(1).rstrip("/").lower()
        if doi.endswith(".pdf"):
            doi = doi[:-4]
        return "doi:" + doi
    return ""


def _same_work_key(row: dict[str, Any]) -> str:
    """The SHARED same-work key.

    Fix 4 (``PG_SAMEWORK_CROSSMIRROR`` ON, default): id-bearing legs FIRST, full-URL
    leg LAST — explicit DOI → URL-embedded id (arXiv / NBER / SSRN / DOI-in-path) →
    folded title + discriminator (year → author → venue, or year+host) → normalized
    full source_url (chunked-PDF last resort) → ``""`` (singleton). This lets the SAME
    work fetched at different mirror URLs merge on its shared id / title+author instead
    of each mirror getting a distinct ``url:`` key (the breadth-padding bug).

    OFF (``PG_SAMEWORK_CROSSMIRROR=0``): byte-identical to the pre-Fix-4 ordering —
    normalized source_url FIRST (STEP 4), else DOI, else folded title + discriminator.

    I-deepfix-003 STEP 4 (#1374): the full-URL leg (``_normalize_source_url``) groups
    chunks of one fetched document that carry no DOI / no usable title. Behind
    ``PG_SAMEWORK_URL_LEG`` (default ON). I-beatboth-011 #4 (#1289): the no-DOI title
    branch NEVER merges on folded title ALONE — it requires a corroborating discriminator.
    The DOI + title legs match ``weighted_enrichment._work_identity`` (render parity).
    """
    if not _samework_crossmirror_enabled():
        # Byte-identical legacy ordering (URL leg first).
        if _samework_url_leg_enabled():
            url_key = _normalize_source_url(row)
            if url_key:
                return "url:" + url_key
        doi = _normalize_doi(row.get("doi"))
        if doi:
            return "doi:" + doi
        folded = _fold_title(_row_title(row))
        if folded:
            discriminator = _title_discriminator(row)
            if discriminator:
                return "title:" + folded + "|" + discriminator
        return ""
    # Cross-mirror ordering (Fix 4): id-bearing legs first, full-URL leg last.
    doi = _normalize_doi(row.get("doi"))
    if doi:
        return "doi:" + doi
    uid = _url_work_identifier(row)
    if uid:
        return "id:" + uid
    # P1-5: a strong arXiv id carried in the BODY header when the URL leg had none (a
    # metadata-less mirror). Bounded to the header so a reference-list id never mis-merges.
    if _samework_body_id_enabled():
        bid = _body_work_identifier(row)
        if bid:
            return "id:" + bid
    folded = _fold_title(_row_title(row))
    if folded:
        discriminator = _title_discriminator(row)
        if discriminator:
            return "title:" + folded + "|" + discriminator
    # P1-5: a LONG, discriminative folded title ALONE (byte-identical long-title mirrors with
    # NO year/author/venue discriminator, e.g. ev_932 vs ev_945). Gated + length/token-floored
    # so a short/generic title never merges two distinct works; the CLAIM merge still requires
    # NLI same-meaning downstream, so a rare title-alone over-link cannot fabricate a
    # corroborated claim (§-1.3-safe). Runs BEFORE the per-URL leg so mirrors merge on title.
    if _samework_title_alone_enabled():
        ta = _title_alone_key(row)
        if ta:
            return ta
    if _samework_url_leg_enabled():
        url_key = _normalize_source_url(row)
        if url_key:
            return "url:" + url_key
    return ""


def _row_text(row: dict[str, Any]) -> str:
    """The row's body text for CAPTCHA-stub + prefix-duplicate detection."""
    for key in ("direct_quote", "statement", "evidence_summary", "text"):
        value = row.get(key)
        if value:
            return str(value)
    return ""


def _is_captcha_stub(row: dict[str, Any]) -> bool:
    """True iff the row's body is a CAPTCHA / anti-bot security stub.

    Self-contained literal check (no cross-package import — finding_dedup defers
    imports specifically to dodge cycles). Unconditional: a stub is dropped
    whether or not it has same-work siblings (it carries no real claim).

    I-beatboth-011 #7 P1 (#1289): the bare trigger phrase ("just a moment") is NOT
    sufficient — a genuinely substantive sentence can contain it. A drop requires the
    trigger AND a strong WAF / security co-token (BYTE-IDENTICAL predicate shared with
    ``weighted_enrichment._is_captcha_stub``). §-1.3 keep-all: real prose carrying a
    bare "just a moment" with no security co-token is never dropped.

    S2/S3 re-pass Fix 1(a)(b) + Fix 8: the tell is evaluated on the TITLE+BODY UNION (the
    base read only the body, so a stub whose challenge tell is only in the TITLE — ev_065
    "## Security check required ... ResearchGate GmbH" — survived). A GENERAL anti-bot /
    shell anchor (``_ANTIBOT_SHELL_PATTERNS``) is self-sufficient chrome, but ONLY when the
    body carries NO propositional prose sentence (``_has_propositional_sentence`` FAIL-OPEN
    guard): a real article whose first fetch hit a bot wall but whose body was recovered has
    propositional prose and is routed by BODY, never chrome-deleted on a stale title alone.
    """
    body = _row_text(row)
    title = _row_title(row)
    combined = (title + "\n" + body).lower()
    # Legacy high-precision: the trigger phrase + a strong WAF co-token (title+body union).
    if (_CAPTCHA_STUB_TRIGGER in combined) and any(tok in combined for tok in _WAF_CO_TOKENS):
        return True
    # General anti-bot / shell class — an anchor in the title OR body, GUARDED by the
    # body having no propositional prose sentence (substantive prose is never deleted).
    if _ci_antibot_shell_enabled():
        if (any(p in combined for p in _ANTIBOT_SHELL_PATTERNS)
                and not _has_propositional_sentence(body)):
            return True
    return False


def _row_any_url(row: dict[str, Any]) -> str:
    """The row's URL from any of the common URL fields (S2/S3 re-pass Fix 10). ``source_url``
    is primary; a row whose ``source_url`` is blank may still carry ``url`` / ``link`` /
    ``canonical_url`` / ``source`` — using them backfills an otherwise-empty member host."""
    for k in ("source_url", "url", "link", "canonical_url", "source", "page_url"):
        v = row.get(k)
        if v and str(v).strip():
            return str(v).strip()
    return ""


def _host_of(url: str) -> str:
    """Bare hostname for independent-host counting: urlparse → lowercase →
    strip leading ``www.``. Empty string on an unparseable/missing URL.

    `count_independent_hosts` / `registrable_domain` expect HOSTS, not full
    URLs, so this reduction MUST happen before they are called (else two paths
    on the same domain would count as separate institutions).
    """
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _finding_key(
    claim: Any,
    evidence_id: str,
    claim_index: int,
    *,
    exact_value: bool = False,
    clinical: bool = True,
) -> tuple:
    """Conservative finding key. An ``unknown`` subject yields a per-CLAIM
    sentinel (evidence_id + claim_index) so it can never collide — even two
    unknown claims on the SAME row stay distinct singletons.

    ``exact_value`` (I-arch-002 (#1246) P3.3, design §2) — under
    ``PG_SWEEP_CREDIBILITY_REDESIGN`` the value slot is the EXACT float (no
    ``round(..., 3)``), matching ``claim_graph._normalized_key_numeric`` (L238)
    so basket clustering keys agree across the two consolidators (a shared
    type-consistency requirement of the design). OFF keeps ``round(value, 3)``
    byte-for-byte (the legacy survivor-selection key).

    ``clinical`` (I-deepfix-001 C1, #1344) — DEFAULT True keeps the byte-identical
    strict subject key (the conservative-singleton clinical guard). When the row is
    NON-clinical (routed by ``is_clinical_domain`` exactly as the extractor routes)
    AND the C1 fold is enabled, the subject slot is a case/punctuation-folded
    SIGNATURE (``_fold_nonclinical_subject``) so surface variants of ONE subject
    consolidate while predicate + value + unit still keep two DISTINCT facts apart.
    A subject that folds to nothing collapses to the UNKNOWN sentinel (safe
    singleton). NO other slot changes, so the tuple shape / downstream consumers
    (``_cluster_value_bucket``, basket routing) are unaffected.
    """
    subject = getattr(claim, "subject", "") or ""
    if not clinical and _nonclinical_fold_enabled():
        # Fix 12/3 (Fable): a TITLE-like / full-clause subject (>=6 words) is not a subject —
        # the extractor named the paper title as the subject, which would falsely key distinct
        # works into one basket (the 'projected impact of generative AI...' title-fold merge).
        # Collapse to the UNKNOWN sentinel (safe singleton) BEFORE folding.
        if _key_hygiene_enabled() and _subject_is_title_like(subject):
            subject = ""
        # P0-1(a) (Fable iter-5): a stopword / function-word / generic-discourse subject
        # ('their', 'because', 'reveals', 'significant point') carries no content noun — it is
        # extractor noise, never a real merge subject. Collapse to the UNKNOWN sentinel BEFORE
        # folding (safe singleton; the row still consolidates via the strict NLI claim path).
        if _key_hygiene_enabled() and _subject_is_noncontent(subject):
            subject = ""
        # Fold ONLY the non-clinical subject to a surface-invariant signature.
        # An empty fold (pure-punctuation subject) becomes the UNKNOWN sentinel.
        folded = _fold_nonclinical_subject(subject)
        # Fix 3(c): a garbage folded subject (PDF-stream artifact / file-code / TLD /
        # long digit run) collapses to the UNKNOWN sentinel — never a false merge key.
        if _key_hygiene_enabled() and _is_garbage_subject(folded):
            folded = ""
        subject = folded or _UNKNOWN_SUBJECT
    if not subject or subject == _UNKNOWN_SUBJECT:
        return ("__unknown__", evidence_id, claim_index)
    raw_value = float(getattr(claim, "value", 0.0) or 0.0)
    # Fix 3(c): an absurd-magnitude value is a mis-read identifier (ISBN / Ray-ID), not a
    # real statistic — collapse to the UNKNOWN sentinel (safe per-row singleton).
    if not clinical and _key_hygiene_enabled() and abs(raw_value) >= _ABSURD_VALUE_MAGNITUDE:
        return ("__unknown__", evidence_id, claim_index)
    value_slot = raw_value if exact_value else round(raw_value, 3)
    return (
        subject,
        getattr(claim, "predicate", "") or "",
        value_slot,
        getattr(claim, "unit", "") or "",
        getattr(claim, "dose", "") or "",
        getattr(claim, "arm", "") or "",
        getattr(claim, "endpoint_phrase", "") or "",
    )


@dataclass
class SameWorkGroup:
    """One same-work unit: N rows that are the SAME work (same DOI / folded
    title) appearing at >=1 URL. KEEPS ALL the URLs as corroborating locators
    (§-1.3 keep-all) but COUNTS as ONE source."""

    same_work_id: str                   # the SHARED same-work key
    canonical_index: int                # the representative row index for the work
    member_indices: list[int]           # all surviving row indices for this work
    member_evidence_ids: list[str]      # all member evidence_ids (corroborators)
    member_urls: list[str]              # all member source_urls (kept locators)


@dataclass
class SameWorkResult:
    """Result of `consolidate_same_work`."""

    groups: list[SameWorkGroup]
    # original-row-index -> same_work_id (only rows that have a same-work key)
    work_id_by_index: dict[int, str]
    # original-row-index -> canonical row index of its same-work group
    canonical_index_by_index: dict[int, int]
    # original-row indices dropped as non-functional (CAPTCHA stub / prefix-dupe)
    dropped_indices: set[int]
    dropped_captcha_indices: set[int]
    dropped_prefix_indices: set[int]
    # S2/S3 re-pass Fix 1(d)(e): recover-before-delete disclosure. A dropped chrome row
    # whose SAME-WORK sibling has a clean (non-chrome) copy is RECOVERED — the work survives
    # via the sibling, no coverage lost. A dropped chrome row with NO clean sibling is a
    # coverage GAP — the whole work was only ever reachable as chrome (disclosed, never
    # fabricated). Both are empty when the same-work consolidation is off.
    dropped_captcha_recovered: set[int] = field(default_factory=set)
    dropped_captcha_gap: set[int] = field(default_factory=set)


def _row_rank_key(row: dict[str, Any], index: int) -> tuple:
    """Canonical-representative rank for a same-work group: highest authority,
    then relevance, then LONGEST body (the most complete copy), then lowest
    original index for determinism."""
    return (
        float(row.get("authority_score", 0.0) or 0.0),
        float(row.get("selection_relevance", 0.0) or 0.0),
        len(_row_text(row)),
        -index,
    )


def consolidate_same_work(rows: list[dict[str, Any]]) -> SameWorkResult:
    """Group same-work rows; drop non-functional members. PURE (no net/LLM).

    Two passes, both faithfulness-neutral (§-1.3 — group/count only, never relax
    a verify gate, never merge two genuinely different works):

    1. DROP CAPTCHA / anti-bot security stubs UNCONDITIONALLY (a stub carries no
       real claim; ``_is_captcha_stub`` — content literal, no same-work sibling
       required).
    2. GROUP the surviving rows by ``_same_work_key`` (DOI first, else folded
       title). Within each work pick a canonical row (highest authority /
       relevance / longest body), then DROP any member whose body is a strict
       PREFIX of a LONGER member of the SAME work (a truncated-intro duplicate).
       A row with NO same-work key is its own singleton work (never merged).

    Returns a SameWorkResult mapping each ORIGINAL row index to its same-work id
    + canonical index, the per-work groups (all member evidence_ids + URLs kept
    as corroborators), and the dropped (CAPTCHA + prefix-dupe) original indices.
    """
    dropped_captcha: set[int] = set()
    work_members: dict[str, list[int]] = {}
    captcha_keys: dict[int, str] = {}
    for ri, row in enumerate(rows):
        if _is_captcha_stub(row):
            dropped_captcha.add(ri)
            # Fix 1(d): remember the chrome row's same-work key so we can check for a
            # clean sibling (recover-before-delete) after the surviving rows are grouped.
            captcha_keys[ri] = _same_work_key(row)
            continue
        key = _same_work_key(row)
        if not key:
            # No same-work key: a per-row singleton key so it can never collide.
            key = "__singleton__:%d" % ri
        work_members.setdefault(key, []).append(ri)

    # Fix 1(d): recover-before-delete. A dropped chrome row whose real same-work key is
    # also carried by a SURVIVING (clean) sibling is RECOVERED — the work is not lost.
    # A dropped chrome row with a real key but NO surviving sibling (or no usable key at
    # all) is a coverage GAP — disclosed, never fabricated.
    dropped_captcha_recovered: set[int] = set()
    dropped_captcha_gap: set[int] = set()
    for ri, key in captcha_keys.items():
        if key and key in work_members:
            dropped_captcha_recovered.add(ri)
        else:
            dropped_captcha_gap.add(ri)

    # Fix 2(b) (Fable): a byte-identical NORMALIZED URL must ALWAYS fold to ONE work, even when
    # the per-row keys differ (one chunk keyed on a discriminative title -> ``titlealone:``,
    # another fell through to the ``url:`` leg). Union the work keys that share an identical
    # normalized member URL so refetches of ONE document never count as multiple works (the
    # residual shared-single-URL c>1 baskets). Only folds the corroboration COUNT (a weight);
    # the CLAIM merge still requires NLI. Two different works never share an identical URL.
    if _samework_url_leg_enabled() and len(work_members) > 1:
        url_to_keys: dict[str, set[str]] = {}
        for wkey, wris in work_members.items():
            for ri in wris:
                nu = _normalize_source_url(rows[ri])
                if nu:
                    url_to_keys.setdefault(nu, set()).add(wkey)
        key_parent: dict[str, str] = {}

        def _kf(k: str) -> str:
            key_parent.setdefault(k, k)
            root = k
            while key_parent[root] != root:
                root = key_parent[root]
            while key_parent[k] != root:
                key_parent[k], k = root, key_parent[k]
            return root

        def _id_bearing(k: str) -> int:
            return 0 if k.startswith(("url:", "doi:", "id:", "arxiv:")) else 1

        def _ku(a: str, b: str) -> None:
            ra, rb = _kf(a), _kf(b)
            if ra == rb:
                return
            lo, hi = sorted((ra, rb), key=lambda k: (_id_bearing(k), k))
            key_parent[hi] = lo  # attach the weaker/later key under the id-bearing/earlier root

        for _nu, ks in url_to_keys.items():
            ks_list = sorted(ks)
            for k in ks_list[1:]:
                _ku(ks_list[0], k)
        if any(_kf(k) != k for k in list(work_members.keys())):
            merged: dict[str, list[int]] = {}
            for wkey, wris in work_members.items():
                merged.setdefault(_kf(wkey), []).extend(wris)
            work_members = {k: sorted(set(v)) for k, v in merged.items()}

    # S2/S3 re-pass iter-2 P0-4(a): CROSS-MIRROR TITLE UNION. Merge any two work-groups that share
    # an identical DISCRIMINATIVE normalized title (``_title_alone_key`` — long-title + token
    # floored). This is the bridge the per-row key cannot make on its own: an arXiv copy keys
    # ``id:arxiv:...`` while its governance.ai / PDF mirror (no arXiv id in the URL) falls to
    # ``titlealone:...`` — DIFFERENT keys for the SAME work (EL25 'GPTs are GPTs' arXiv vs EL56 its
    # PDF mirror). A title-normalized match on a different host IS the same work. Mirrors the URL
    # union above; §-1.3-safe (folds only the corroboration COUNT — the CLAIM merge still needs
    # NLI, so a rare title over-fold can never fabricate a corroborated claim; every URL kept).
    if _samework_title_union_enabled() and len(work_members) > 1:
        title_to_keys: dict[str, set[str]] = {}
        for wkey, wris in work_members.items():
            for ri in wris:
                ta = _title_alone_key(rows[ri])  # 'titlealone:<folded>' or '' (floor-guarded)
                if ta:
                    title_to_keys.setdefault(ta, set()).add(wkey)
        title_parent: dict[str, str] = {}

        def _tf(k: str) -> str:
            title_parent.setdefault(k, k)
            root = k
            while title_parent[root] != root:
                root = title_parent[root]
            while title_parent[k] != root:
                title_parent[k], k = root, title_parent[k]
            return root

        def _t_id_bearing(k: str) -> int:
            # Prefer an id-bearing / url key as the surviving root over a bare titlealone key.
            return 0 if k.startswith(("doi:", "id:", "arxiv:", "url:")) else 1

        def _tu(a: str, b: str) -> None:
            ra, rb = _tf(a), _tf(b)
            if ra == rb:
                return
            lo, hi = sorted((ra, rb), key=lambda k: (_t_id_bearing(k), k))
            title_parent[hi] = lo  # attach the weaker/later key under the id-bearing/earlier root

        for _ta, ks in title_to_keys.items():
            if len(ks) < 2:
                continue  # a title carried by only ONE work-group unions nothing
            ks_list = sorted(ks)
            base = ks_list[0]
            for k in ks_list[1:]:
                if _tf(base) == _tf(k):
                    continue  # already unioned via an earlier signature
                # P1-2 (iter-7, Fable): two DIFFERENT-key work-groups sharing ONE title are a
                # cross-mirror candidate (id:arxiv + titlealone of 'GPTs are GPTs', legit P0-4a) OR a
                # title-only COLLISION (a forum thread / aggregator that merely reused the paper's
                # title — the drb_72 forum+NBER / wikipedia+ebsco / forbes+ahrefs mis-attribution).
                # Block the union ONLY on a CONFIDENT non-entailment of the two groups' reps; an
                # UNKNOWN verdict (NLI unavailable / flag off) leaves the legacy union UNCHANGED so a
                # genuine cross-mirror still folds and no NLI-down run regresses P0-4a. Parity-safe
                # (the same-work KEY is untouched).
                if _group_content_verdict(work_members[base], work_members[k], rows) is False:
                    continue
                _tu(base, k)
        if any(_tf(k) != k for k in list(work_members.keys())):
            merged_t: dict[str, list[int]] = {}
            for wkey, wris in work_members.items():
                merged_t.setdefault(_tf(wkey), []).extend(wris)
            work_members = {k: sorted(set(v)) for k, v in merged_t.items()}

    # P1-2 (S2/S3 re-pass iter-5, Fable): CROSS-HOST FILENAME UNION. Merge any two work-groups
    # that share an identical DISCRIMINATIVE URL basename (``_url_basename_key`` — 'cesifo1_wp10601.pdf'
    # at econstor.eu AND ifo.de is ONE CESifo working paper; three fetches of one ssir.org article
    # slug are ONE work). The corpus rarely carries a DOI/authors, so a distinctive filename is the
    # strongest available cross-mirror signal. Mirrors the URL/title unions above; §-1.3-safe (folds
    # only the corroboration COUNT — the CLAIM merge still needs NLI, so a rare basename collision
    # can never fabricate a corroborated claim; every member URL is kept). Kill switch => byte-identical.
    if _samework_filename_union_enabled() and len(work_members) > 1:
        base_to_keys: dict[str, set[str]] = {}
        for wkey, wris in work_members.items():
            for ri in wris:
                bk = _url_basename_key(rows[ri])
                if bk:
                    base_to_keys.setdefault(bk, set()).add(wkey)
        base_parent: dict[str, str] = {}

        def _bf(k: str) -> str:
            base_parent.setdefault(k, k)
            root = k
            while base_parent[root] != root:
                root = base_parent[root]
            while base_parent[k] != root:
                base_parent[k], k = root, base_parent[k]
            return root

        def _b_id_bearing(k: str) -> int:
            return 0 if k.startswith(("doi:", "id:", "arxiv:", "url:")) else 1

        def _bu(a: str, b: str) -> None:
            ra, rb = _bf(a), _bf(b)
            if ra == rb:
                return
            lo, hi = sorted((ra, rb), key=lambda k: (_b_id_bearing(k), k))
            base_parent[hi] = lo

        for _bk, ks in base_to_keys.items():
            if len(ks) < 2:
                continue  # a basename carried by only ONE work-group unions nothing
            ks_list = sorted(ks)
            for k in ks_list[1:]:
                _bu(ks_list[0], k)
        if any(_bf(k) != k for k in list(work_members.keys())):
            merged_b: dict[str, list[int]] = {}
            for wkey, wris in work_members.items():
                merged_b.setdefault(_bf(wkey), []).extend(wris)
            work_members = {k: sorted(set(v)) for k, v in merged_b.items()}

    dropped_prefix: set[int] = set()
    groups: list[SameWorkGroup] = []
    work_id_by_index: dict[int, str] = {}
    canonical_index_by_index: dict[int, int] = {}

    for key, member_ris in work_members.items():
        # Strict-prefix drop WITHIN this work: a member whose stripped body is a
        # strict prefix of a strictly-longer sibling's body is a truncated dup.
        texts = {ri: _row_text(rows[ri]).strip() for ri in member_ris}
        prefix_dup: set[int] = set()
        for a in member_ris:
            ta = texts[a]
            if not ta:
                continue
            for b in member_ris:
                if a is b:
                    continue
                tb = texts[b]
                # a is a strict prefix of the LONGER b -> a is a truncated dup.
                if len(tb) > len(ta) and tb.startswith(ta):
                    prefix_dup.add(a)
                    break
        dropped_prefix |= prefix_dup
        survivors = [ri for ri in member_ris if ri not in prefix_dup]
        if not survivors:
            # Degenerate (all equal-length mutual prefixes): keep the lowest idx.
            survivors = [min(member_ris)]
            dropped_prefix -= {survivors[0]}

        canonical = max(survivors, key=lambda ri: _row_rank_key(rows[ri], ri))
        # Only emit a real same-work id for genuine same-work keys. The per-row
        # "__singleton__" keys carry no cross-row meaning, so they get no same_work
        # annotation (a row with no URL/DOI/title is its own work and must not look
        # "consolidated"). STEP 4 (#1374): a ``url:`` key IS a genuine same-work group
        # (chunks of one fetched document) — it MUST populate ``work_id_by_index`` /
        # ``canonical_index_by_index`` so the origin-host fold and the render
        # annotations treat the shared-URL chunks as ONE source.
        #
        # S2/S3 re-pass Fix 2(a) (Fable): the leg-type-dependent allowlist above
        # EXCLUDED ``titlealone:`` and body-``arxiv:`` groups, while the Fix-4 leg
        # priority routes identical-URL refetches INTO a ``titlealone:`` group when the
        # chunks carry a discriminative title. Those groups then never populated
        # ``work_id_by_index``, so ``_work_of`` returned a per-row singleton and the
        # distinct-works corroboration counted N refetches of ONE work as N independent
        # sources (the 29 shared-single-URL c>1 baskets). GENERAL FIX: EVERY formed group
        # is a real work regardless of which leg keyed it — only the per-row
        # ``__singleton__`` (no shared key at all) is not. This only folds the
        # CORROBORATION COUNT (a Signal-D weight); the CLAIM merge still requires
        # NLI same-meaning, so a rare title-alone over-fold can never fabricate a
        # corroborated claim (§-1.3 keep-all: every member URL is still kept).
        is_real_work = not key.startswith("__singleton__:")
        member_evidence_ids = [
            str(rows[ri].get("evidence_id", ri)) for ri in survivors
        ]
        member_urls = sorted({
            str(rows[ri].get("source_url", "") or "") for ri in survivors
        } - {""})
        groups.append(SameWorkGroup(
            same_work_id=key,
            canonical_index=canonical,
            member_indices=sorted(survivors),
            member_evidence_ids=member_evidence_ids,
            member_urls=member_urls,
        ))
        if is_real_work:
            for ri in survivors:
                work_id_by_index[ri] = key
                canonical_index_by_index[ri] = canonical

    return SameWorkResult(
        groups=groups,
        work_id_by_index=work_id_by_index,
        canonical_index_by_index=canonical_index_by_index,
        dropped_indices=dropped_captcha | dropped_prefix,
        dropped_captcha_indices=dropped_captcha,
        dropped_prefix_indices=dropped_prefix,
        dropped_captcha_recovered=dropped_captcha_recovered,
        dropped_captcha_gap=dropped_captcha_gap,
    )


@dataclass
class FindingCluster:
    """One cluster of rows asserting the same finding."""

    finding_key: tuple
    representative_index: int           # row index of the chosen representative
    member_indices: list[int]           # all distinct row indices in the cluster
    member_hosts: list[str]             # sorted unique registrable-domains
    corroboration_count: int            # independent registrable-domains


@dataclass
class FindingDedupResult:
    """Result of `dedup_by_finding`."""

    deduped_rows: list[dict[str, Any]]  # representatives + qualitative rows, in order
    clusters: list[FindingCluster]
    raw_row_count: int
    distinct_finding_count: int
    collapsed_row_count: int
    # I-beatboth-011 #7 CORE (#1289): same-work consolidation (same DOI / folded
    # title => ONE source). Default empty so any legacy positional/keyword caller
    # is unaffected; the basket consumer + weighted_enrichment read this to agree.
    same_work: SameWorkResult | None = None
    # I-wire-001 W1 (#1306): count of literal `_finding_key` clusters absorbed by the
    # bidirectional-NLI consolidation winner (0 when PG_CONSOLIDATION_NLI is OFF — the
    # default — so the field is byte-inert for every legacy caller). This is the
    # behavioral-canary signal: >0 proves the NLI merged same-claim paraphrases the
    # literal floor left separate.
    nli_merge_count: int = 0
    # I-deepfix-001 D1 (#1344): number of QUALITATIVE (non-numeric) corroboration
    # baskets formed from no-numeric-finding rows (§-1.3 CONSOLIDATE qualitative too).
    # 0 when the kill switch is off OR the consolidate-keep-all regime is off (the
    # numeric-only legacy), so the field is byte-inert for every legacy caller. >0 is
    # the behavioral-canary signal that the qualitative-consolidation blind spot is
    # closed (the D1 diced-dice goes GREEN once one such basket has >1 distinct host).
    qualitative_basket_count: int = 0
    # S2/S3 re-pass iter-3 (Fable Fix 1(d), THE GHOST close): number of numeric baskets
    # UNIONED by the representative-invariant post-pass (a residual same-claim false-split
    # the numeric split-confirm's fail-open-on-None left behind — byte-identical or
    # bidirectionally-entailing VISIBLE representative claim sentence). 0 when the kill
    # switch is off; >0 proves a residual same-claim double-basket was repaired.
    rep_invariant_merge_count: int = 0
    # S2/S3 re-pass iter-5 P0-1(b) (Fable): per-cluster confirm/split telemetry from the numeric
    # split-confirm pass, surfaced to consolidation_summary (§-1.3.1 fail-loud). `numeric_*` keys
    # count clusters that lost a member, members kept, members split, and members split
    # specifically by the numbers-strict value gate (rep/member claim sentence lacked the value).
    numeric_confirm_telemetry: dict[str, int] = field(default_factory=dict)
    # S2/S3 re-pass iter-7 P0-1(b) (Fable): rows routed to the no-claim pool at basket FORMATION —
    # confident publisher/cataloguing/license/correspondence/reference boilerplate that would
    # otherwise have MINTED a fake numeric basket. The rows are KEPT (keep-all singletons); only the
    # fake-basket founding is suppressed. 0 when the kill switch is off; >0 is the §-1.3.1(a)
    # fail-loud disclosure that N boilerplate-only rows were kept out of the claim baskets.
    no_claim_basket_pooled_count: int = 0


# ─────────────────────────────────────────────────────────────────────────
# Consolidation-NLI winner hook (I-wire-001 W1, #1306) — flag-gated default-OFF
# ─────────────────────────────────────────────────────────────────────────
def _consolidation_nli_enabled() -> bool:
    """`PG_CONSOLIDATION_NLI` master gate. Single source of truth lives in
    ``consolidation_nli.consolidation_nli_enabled`` — import LAZILY so importing
    finding_dedup never pulls the cross-encoder dependency. DEFAULT-OFF => the literal
    floor runs byte-identical and ``_apply_consolidation_nli`` is never called."""
    from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
        consolidation_nli_enabled,
    )

    return consolidation_nli_enabled()


def _claim_sentence(row: dict[str, Any], bucket_value: Any) -> str:
    """The focused CLAIM SENTENCE for NLI — the full sentence containing the cluster's
    numeric value (expanded from ``ExtractedNumericClaim.context_snippet``), NOT the full
    ``direct_quote`` body. Feeding the whole document (often title + abstract + URL
    boilerplate, thousands of chars > the cross-encoder's ~512-token limit) makes two
    unrelated papers weakly "entail" on shared boilerplate — a §-1.1 false-merge. The
    focused claim sentence is what the bake-off scored (P=1.0); it makes genuinely
    different claims (e.g. dexamethasone-preterm vs protein-older-men) non-entailing.

    Picks the claim whose value matches ``bucket_value`` (the cluster's value); falls
    back to the first claim, then to the row body if no claim extracts."""
    claims = extract_numeric_claims([row])
    body = _row_text(row)
    if claims:
        chosen = None
        if bucket_value is not None:
            for c in claims:
                if round(float(getattr(c, "value", 0.0) or 0.0), 6) == bucket_value:
                    chosen = c
                    break
        if chosen is None:
            chosen = claims[0]
        snip = getattr(chosen, "context_snippet", "") or ""
        if snip:
            # Use the focused ~200-char value-window directly. (Expanding to the full
            # surrounding sentence was tried and REGRESSED precision on web-fetch corpora
            # whose bodies are "Title: ... URL Source: ..." boilerplate dumps — the
            # expansion re-introduced boilerplate the snippet had excluded; see the
            # I-wire-001 audit. The focused window is the cleaner claim representation.)
            return snip
    return body


def _cluster_text(
    rows: list[dict[str, Any]], member_ris: list[int], rank_fn, bucket_value: Any,
) -> str:
    """The representative CLAIM SENTENCE fed to the NLI cross-encoder for one literal
    cluster: the focused ``context_snippet`` of the cluster's best-ranked row (the same
    authority/relevance ranking the corroboration step uses). Deterministic."""
    rep_ri = max(member_ris, key=rank_fn)
    return _claim_sentence(rows[rep_ri], bucket_value)


def _unknown_nli_pool_enabled() -> bool:
    """``PG_UNKNOWN_NLI_POOL`` kill switch (LAW VI). DEFAULT-ON (S2/S3 re-pass Fable Fix 1(b)
    — REPLACE the prior isolate-unknowns policy).

    POOLING IS NOT MERGING. An ``__unknown__``-subject cluster is a per-row sentinel whose
    subject the extractor could not resolve — but that is NOT a reason to withhold it from the
    JUDGE. The prior default (OFF) gave every unknown its own unique bucket so it was never even
    NLI-COMPARED, which conflated "never mechanically merge unknowns" with "never even ASK the
    judge" and structurally UNDER-merged (byte-identical / same-claim unknown findings stayed as
    N separate singletons — the drb_72 under-merge). The correct policy: POOL unknowns into the
    consolidation-NLI value bucket (by numeric value when one exists, else the shared qualitative
    pool) so the bidirectional cross-encoder GETS to compare them, but MERGE still requires a
    confident bidirectional entailment (``_apply_consolidation_nli`` / ``group_clusters``). An
    infra ``None`` / no-edge => NO merge (fail-open, the unknown stays a singleton). Boilerplate
    can no longer false-merge here because the CLAIM-BEARING line gate (Fix 2) stops a
    non-claim-bearing line from ever becoming a finding in the first place — NLI cannot fix
    boilerplate (boilerplate entails boilerplate), so the fix is upstream, not isolation here.

    Set ``PG_UNKNOWN_NLI_POOL=0`` to restore the byte-identical isolate-unknowns behaviour (each
    unknown cluster gets its own unique bucket and is never NLI-compared)."""
    return os.getenv("PG_UNKNOWN_NLI_POOL", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _cluster_value_bucket(key: tuple, rows: list[dict[str, Any]], member_ris: list[int]) -> Any:
    """The numeric VALUE a literal cluster asserts — used to BUCKET clusters before NLI so
    only same-VALUE clusters are pairwise-compared. Two sources can corroborate the SAME
    claim only if they carry the SAME number, so bucketing by value is both a scale fix
    (O(n^2) -> O(sum bucket^2)) and a precision guard (never NLI-compare 30% vs 12%).

    Known-subject keys carry the value at index 2.

    S2/S3 re-pass Fix 1(B) (Fable — "delete __unknown__ as a merge decider"): an
    ``__unknown__`` cluster is a per-row sentinel whose SUBJECT the extractor could not
    resolve. Pooling such clusters by a recovered numeric value let the bidirectional
    cross-encoder merge two DIFFERENT-institution boilerplate/section-header rows on
    generic policy language (the World-Bank + OECD false merge). An unresolved-subject
    row must NOT participate in the value-bucket NLI pool — it gets its OWN unique bucket
    (its sentinel key) so it is never pairwise-compared here. It can still consolidate
    through the strict qualitative claim-sentence + polarity path if it genuinely
    paraphrases another claim. FAIL-OPEN = do-not-merge on an unknown subject. Gated so
    the legacy pooled behavior is one env flag away.
    """
    if isinstance(key, tuple) and key and key[0] == "__unknown__":
        if _unknown_nli_pool_enabled():
            # S2/S3 re-pass Fable Fix 1(b): POOL (not merge). Recover a numeric value so this
            # unknown cluster shares a value bucket with same-value clusters and the judge gets
            # to compare them; when there is NO recoverable value it joins the SHARED qualitative
            # NLI pool (so valueless unknowns are still ASKED, not isolated). The merge itself is
            # still decided by bidirectional entailment downstream — pooling only earns the
            # comparison, never the merge (infra-None / no-edge => stays a singleton, fail-open).
            for ri in member_ris:
                claims = extract_numeric_claims([rows[ri]])
                if claims:
                    return round(float(getattr(claims[0], "value", 0.0) or 0.0), 6)
            return ("__unk_qual__",)  # the shared qualitative NLI pool (valueless unknowns)
        # PG_UNKNOWN_NLI_POOL=0: a UNIQUE per-cluster bucket (the sentinel key itself) so this
        # unknown-subject cluster shares a bucket with no other and is never NLI-compared.
        return ("__unk__",) + tuple(str(x) for x in key)
    if isinstance(key, tuple) and key and len(key) >= 3:
        return round(float(key[2]), 6)
    for ri in member_ris:
        claims = extract_numeric_claims([rows[ri]])
        if claims:
            return round(float(getattr(claims[0], "value", 0.0) or 0.0), 6)
    return None


def _consolidation_soft_prior_enabled() -> bool:
    """``PG_CONSOLIDATION_SOFT_PRIOR`` kill switch (LAW VI, DEFAULT-ON, S2/S3 re-pass iter-7 P1-1,
    Fable). ON => the value bucket is a SOFT prior: two numeric clusters are NLI candidates when
    their FULL numeric value SETS INTERSECT (a multi-number claim whose extractors picked DIFFERENT
    anchors — the drb_72 #041/#130 1.5%/3%/3.7% PWBM pair, #039/#104/#169 $2.6-4.4T McKinsey — still
    co-buckets), not only when a SINGLE anchor value is EQUAL. The bidirectional cross-encoder stays
    the SOLE merge decider (fail-open: no edge => stays split), and the post-merge re-verify SPLITS
    any member that does not entail the final rep, so a spurious shared value can never fabricate a
    merge. OFF => byte-identical single-value bucketing."""
    return os.getenv("PG_CONSOLIDATION_SOFT_PRIOR", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


_SOFT_PRIOR_NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


def _numbers_in_claim_text(text: str) -> set[float]:
    """Every numeric token in ``text`` (the CLAIM SENTENCE) as a rounded float — the "numeric set
    of the text" (P1-1 soft prior). Year-like bare integers (1900-2100) are EXCLUDED: they are
    almost never the claim value and would over-connect the candidate buckets. Commas are folded so
    '2,600' == 2600. Deterministic + question-agnostic."""
    out: set[float] = set()
    for tok in _SOFT_PRIOR_NUMBER_RE.findall(text or ""):
        try:
            v = float(tok.replace(",", ""))
        except ValueError:
            continue
        if v == int(v) and 1900 <= v <= 2100:
            continue  # year-like bare integer — common noise, rarely the claim value
        out.add(round(v, 6))
    return out


def _cluster_value_set(key: tuple, rows: list[dict[str, Any]], member_ris: list[int]) -> frozenset:
    """The FULL SET of numbers a literal cluster's TEXT asserts (P1-1 soft prior): the known-subject
    key value (index 2) PLUS every numeric token in each member's reader-visible CLAIM SENTENCE. Two
    clusters whose value SETS intersect share >= 1 number, so they are same-claim CANDIDATES even
    when the numeric extractor picked DIFFERENT anchors for each (the drb_72 #041/#130 case: both
    texts carry 1.5%/3%/3.7% but one cluster keyed on 1.5, the other on 3.7). Reading the numbers
    from the TEXT (not the single extracted anchor) is what bridges them. Rounded to 6 dp to match
    the bucket key. Deterministic; the NLI judge still decides every merge (this only NOMINATES)."""
    vals: set = set()
    if isinstance(key, tuple) and key and len(key) >= 3:
        try:
            vals.add(round(float(key[2]), 6))
        except (TypeError, ValueError):
            pass
    for ri in member_ris:
        vals |= _numbers_in_claim_text(_visible_claim_sentence(rows[ri], None))
    return frozenset(vals)


def _apply_consolidation_nli(
    groups: dict[tuple, list[int]],
    rows: list[dict[str, Any]],
    rank_fn,
) -> tuple[dict[tuple, list[int]], int]:
    """Merge literal ``_finding_key`` clusters whose representatives BIDIRECTIONALLY
    entail (the bake-off winner — same-claim paraphrases the exact subject/predicate/value
    floor left separate, board R=0.0). Returns ``(merged_groups, nli_merge_count)`` where
    ``nli_merge_count`` = number of literal clusters absorbed into another.

    VALUE-BUCKETING (scale + precision): clusters are first bucketed by the numeric value
    they assert (``_cluster_value_bucket``); NLI runs only WITHIN a bucket. Same-claim
    corroborators must share the number, so this never misses a real merge, bounds the
    pairwise cost to per-bucket O(k^2), and can never NLI-pair two different numbers.

    UNKNOWN-SUBJECT clusters ARE eligible (the clinical extractor dumps many same-claim
    paraphrases into per-row ``__unknown__`` sentinels — exactly the R=0.0 floor the winner
    fixes). Merging them is SAFE: corroboration_count / member_hosts are a Signal-D WEIGHT
    consumed only as grouping by the downstream consumer (``credibility_pass`` relabel +
    edge-remap), never a verify gate — the isolated per-member entailment verify is
    UNCHANGED, so no member newly passes verification (faithfulness FROZEN, §-1.3). A merge
    can only inflate a weight count, never drop a row, never relax a gate.

    Determinism + order-independence: each bucket runs a bounded-parallel pairwise NLI
    (cap = ``PG_CONSOLIDATION_NLI_WORKERS``) then a deterministic union-find post-step
    (attach-to-lowest-index), so the merged grouping is identical for any worker count.
    The merged member-index lists are sorted, so the downstream loop is unchanged.

    Any failure (e.g. the cross-encoder cannot load) RAISES — a flag-ON winner that
    silently no-ops would defeat the §-1.4 canary (no silent fallback, LAW II).

    P0-1(c) (iter-5, Fable): a cluster whose VISIBLE representative sentence is NOT a real
    CLAIM (a byte-identical heading / license / nav / metadata line — the drb_72 basket-224
    ``__unknown__`` worldbank+oecd 'Main findings from the consultation process' pool merge) is
    EXCLUDED from the value buckets, so the byte-identical-entails-byte-identical shortcut can
    never fire on non-mergeable text on THIS path. §-1.3-safe: it only ever keeps a cluster
    SPLIT (never drops a row, never relaxes a gate)."""
    from src.polaris_graph.synthesis.consolidation_nli import group_clusters  # noqa: PLC0415

    keys = list(groups.keys())
    if len(keys) < 2:
        return groups, 0

    # Bucket every cluster index by the numeric value it asserts (its canonical bucket key). A
    # None => no recoverable value => its own singleton, never merged. A non-mergeable VISIBLE rep
    # (a heading / license / nav / metadata line) is EXCLUDED so it never anchors an NLI merge.
    prior_on = _consolidation_soft_prior_enabled()
    bucket_key_of: dict[int, Any] = {}
    value_set_of: dict[int, frozenset] = {}
    eligible: list[int] = []
    for i in range(len(keys)):
        member_ris = sorted(set(groups[keys[i]]))
        bk = _cluster_value_bucket(keys[i], rows, member_ris)
        bucket_key_of[i] = bk
        if bk is None:
            continue  # no recoverable value => its own singleton, never merged
        # P0-1(c): screen the cluster's VISIBLE representative claim sentence — a non-mergeable
        # heading / license / nav / metadata line must never anchor a byte-identical NLI merge
        # (the basket-224 heading pool). Non-mergeable rep => leave the cluster a singleton.
        rep_ri = _choose_clean_representative(member_ris, rank_fn, rows)
        if not _sentence_mergeable(_visible_claim_sentence(rows[rep_ri], bk)):
            continue
        # P1-1 soft prior: compute a numeric value SET only for clusters whose bucket key is a real
        # FLOAT (a resolved-subject or pool-enabled recovered numeric value). A sentinel tuple key
        # (``("__unk_qual__",)`` / ``("__unk__",...)``) gets NO value set, so isolated unknowns stay
        # isolated and the pool-enabled qualitative unknowns still union only via their SHARED
        # sentinel bucket below — the boilerplate false-merge guard is preserved.
        value_set_of[i] = (
            _cluster_value_set(keys[i], rows, member_ris)
            if (prior_on and isinstance(bk, float)) else frozenset()
        )
        eligible.append(i)

    # Union-find over ALL cluster indices; only within-bucket NLI edges union.
    parent = list(range(len(keys)))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra < rb else (rb, ra)
        parent[hi] = lo  # attach to lower => deterministic

    # CANDIDATE union-find over the ELIGIBLE clusters (the NLI candidate components). Two legs:
    #   (1) LEGACY: clusters sharing the SAME canonical bucket key (same single value OR the shared
    #       ``("__unk_qual__",)`` qualitative pool) — byte-identical to the old by-value bucketing.
    #   (2) SOFT PRIOR (P1-1): clusters whose FULL numeric value SETS INTERSECT — the multi-anchor
    #       bridge (#041/#130) the single-value bucket missed. NLI still decides each pair.
    cand_parent: dict[int, int] = {i: i for i in eligible}

    def _cfind(x: int) -> int:
        while cand_parent[x] != x:
            cand_parent[x] = cand_parent[cand_parent[x]]
            x = cand_parent[x]
        return x

    def _cunion(a: int, b: int) -> None:
        ra, rb = _cfind(a), _cfind(b)
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra < rb else (rb, ra)
        cand_parent[hi] = lo

    by_bucket: dict[Any, list[int]] = {}
    for i in eligible:
        by_bucket.setdefault(bucket_key_of[i], []).append(i)
    for _bk, idxs in by_bucket.items():
        for j in idxs[1:]:
            _cunion(idxs[0], j)
    if prior_on:
        value_to_clusters: dict[Any, list[int]] = {}
        for i in eligible:
            for v in value_set_of[i]:
                value_to_clusters.setdefault(v, []).append(i)
        for _v, idxs in value_to_clusters.items():
            for j in idxs[1:]:
                _cunion(idxs[0], j)

    components: dict[int, list[int]] = {}
    for i in eligible:
        components.setdefault(_cfind(i), []).append(i)

    for _root, cluster_idxs in sorted(components.items()):
        cluster_idxs = sorted(cluster_idxs)
        if len(cluster_idxs) < 2:
            continue
        texts = [
            _cluster_text(rows, groups[keys[i]], rank_fn, bucket_key_of[i])
            for i in cluster_idxs
        ]
        root_by_pos = group_clusters(texts)  # bounded-parallel NLI + union-find post-step
        for pos, eli in enumerate(cluster_idxs):
            _union(eli, cluster_idxs[root_by_pos[pos]])

    # Re-emit clusters: every union-find root keeps the LOWEST-index member's key as the
    # merged cluster key; folded clusters disappear (their members move to the root).
    merged_members: dict[int, list[int]] = {}
    for i in range(len(keys)):
        merged_members.setdefault(_find(i), []).extend(groups[keys[i]])

    new_groups: dict[tuple, list[int]] = {}
    absorbed = 0
    for i in range(len(keys)):  # original key order => order-stable result dict
        root = _find(i)
        if root != i:
            continue  # this cluster was folded into its root; emitted there
        new_groups[keys[i]] = sorted(set(merged_members[root]))
    absorbed = len(keys) - len(new_groups)  # clusters absorbed = before - after
    return new_groups, absorbed


# ─────────────────────────────────────────────────────────────────────────
# Rung-0 EXACT-duplicate collapse — S2/S3 re-pass Fable Fix 1(a)
# ─────────────────────────────────────────────────────────────────────────
_RUNG0_EXACT_ENV = "PG_FINDING_RUNG0_EXACT"
# Citation / provenance tokens and bracketed refs are folded out BEFORE comparison so two
# copies of ONE claim sentence that differ only in their attached ``[#ev:...]`` token compare
# equal (a byte-identical claim, regardless of which evidence row carries it).
_RUNG0_CITE_TOKEN_RE = re.compile(r"\[#[^\]]*\]|\[\d+\]|\(\s*\d{4}\s*\)")
_RUNG0_WS_RE = re.compile(r"\s+")


def _rung0_exact_collapse_enabled() -> bool:
    """``PG_FINDING_RUNG0_EXACT`` kill switch (LAW VI, DEFAULT-ON, Fable Fix 1(a)). ON => a
    rung-0 pass collapses clusters whose representative claim sentence is byte-identical after
    unicode + whitespace + citation-token normalization into ONE cluster, with NO judge (a
    byte-identical sentence IS the same claim). OFF => byte-identical legacy (no rung-0)."""
    return os.getenv(_RUNG0_EXACT_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _rung0_signature(text: str) -> str:
    """The rung-0 exact-duplicate signature of a claim sentence: unicode-normalized (via
    ``_normalize_unicode_text``), letter-spacing collapsed, citation / bracketed-ref tokens
    folded out, whitespace collapsed, casefolded. Empty when the text has no alphanumeric
    content (an empty signature NEVER groups — chrome / punctuation-only lines stay singletons).
    Pure/deterministic + question-agnostic (no entity list, no corpus-tuned threshold)."""
    base = _normalize_unicode_text(_collapse_letter_spacing(text or ""))
    base = _RUNG0_CITE_TOKEN_RE.sub(" ", base)
    base = _RUNG0_WS_RE.sub(" ", base).strip().casefold()
    if not any(ch.isalnum() for ch in base):
        return ""
    return base


def _apply_rung0_exact_collapse(
    groups: dict[tuple, list[int]],
    rows: list[dict[str, Any]],
    rank_fn,
) -> tuple[dict[tuple, list[int]], int]:
    """Fable Fix 1(a): collapse clusters whose representative claim sentence is byte-identical
    (after ``_rung0_signature`` normalization) into ONE cluster, BEFORE any NLI judge is asked.

    A byte-identical claim sentence is the same claim — no cross-encoder needed. This closes the
    structural UNDER-merge where two same-text findings sat in per-row ``__unknown__`` sentinels
    (or two distinct tuple keys) and, with the judge withheld, never consolidated. Runs on ALL
    cluster kinds (numeric + unknown) uniformly. §-1.3-safe: it only ever UNIONS clusters (member
    lists grow, keep-all preserved); it never drops a row, never relaxes a verify gate. Merges to
    the LOWEST-index cluster key (deterministic, order-independent). Returns
    ``(merged_groups, collapsed_count)`` where ``collapsed_count`` = clusters absorbed."""
    keys = list(groups.keys())
    if len(keys) < 2:
        return groups, 0
    # Representative rung-0 signature per cluster (the cluster's best-ranked member's claim text).
    sig_of: dict[int, str] = {}
    for i, key in enumerate(keys):
        member_ris = groups[key]
        bucket_value = _cluster_value_bucket(key, rows, member_ris)
        rep_text = _cluster_text(rows, member_ris, rank_fn, bucket_value)
        # P0-1 (iter-4, Fable): a byte-identical HEADING / license / metadata line is NOT a claim —
        # it must never be a merge key without a semantic confirm. Only a real, non-boilerplate
        # claim sentence earns a grouping signature; a non-mergeable rep yields "" (stays a
        # singleton). Genuine byte-identical CLAIM merges (Weizenbaum, Eloundou 46%) still union.
        sig_of[i] = _rung0_signature(rep_text) if _sentence_mergeable(rep_text) else ""
    # Group cluster indices by identical non-empty signature; union each such group.
    by_sig: dict[str, list[int]] = {}
    for i in range(len(keys)):
        s = sig_of[i]
        if s:
            by_sig.setdefault(s, []).append(i)
    parent = list(range(len(keys)))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra < rb else (rb, ra)
        parent[hi] = lo

    for _sig, idxs in by_sig.items():
        if len(idxs) < 2:
            continue
        anchor = idxs[0]
        for other in idxs[1:]:
            _union(anchor, other)

    merged_members: dict[int, list[int]] = {}
    for i in range(len(keys)):
        merged_members.setdefault(_find(i), []).extend(groups[keys[i]])
    new_groups: dict[tuple, list[int]] = {}
    for i in range(len(keys)):  # original key order => order-stable result dict
        if _find(i) != i:
            continue
        new_groups[keys[i]] = sorted(set(merged_members[i]))
    return new_groups, len(keys) - len(new_groups)


# ─────────────────────────────────────────────────────────────────────────
# Representative-invariant POST-PASS — Fable Fix 1(d) (S2/S3 re-pass iter-3)
# ─────────────────────────────────────────────────────────────────────────
# THE GHOST (§-1.1) closes here. The numeric tuple key is RECALL only; rung-0 exact
# collapse, the numeric split-confirm, and the bidirectional consolidation-NLI decide
# merges. But the split-confirm (`_confirm_numeric_clusters_via_nli`) SPLITS a member
# off its cluster on ANY non-(True,True) NLI answer — INCLUDING an infra ``None`` on the
# GPU cross-encoder — so two byte-identical copies of ONE finding can land in TWO baskets
# (observed drb_72: three identical Weizenbaum-PDF fetches split into 3; a governance.ai
# chrome-body copy + the clean Eloundou abstract of the SAME 46% claim split into 2). The
# INVARIANT: after all passes, no two surviving numeric baskets may show a byte-identical
# (or, cross-encoder active, bidirectionally-entailing) VISIBLE representative claim
# sentence. A byte-identical sentence IS the same claim (no judge needed). §-1.3-safe:
# UNION only, keep-all, corroboration counted over DISTINCT works so a same-work re-merge
# stays honest; the faithfulness engine is untouched. General / question-agnostic: the
# signal is the normalized claim sentence + numeric value, never an entity list or corpus
# number. ``_visible_claim_sentence`` mirrors the s3 snapshot's ``representative_statement``
# derivation so the invariant is stated against exactly the line the report/judge SEES.
_REP_INVARIANT_ENV = "PG_FINDING_REP_INVARIANT"
# Nav/chrome lines that must never be picked as the visible claim sentence (login / search
# UI / share / cookie / masthead glyphs). Question-agnostic surface chrome only.
_VISIBLE_CHROME_RE = re.compile(
    r"log ?in|sign ?in|subscribe|cookie|search text|search type|logical operator|"
    r"add_circle|remove_circle|skip to|newsletter|\bmenu\b|share this|©|›|»",
    re.IGNORECASE,
)


def _representative_invariant_enabled() -> bool:
    """``PG_FINDING_REP_INVARIANT`` kill switch (LAW VI, DEFAULT-ON, Fable Fix 1(d)). OFF =>
    byte-identical legacy (no post-pass invariant)."""
    return os.getenv(_REP_INVARIANT_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _visible_claim_sentence(row: dict[str, Any], bucket_value: Any) -> str:
    """The VISIBLE representative claim sentence for a row — the COMPLETE sentence a
    reader/judge sees, mirroring the s3 snapshot's ``representative_statement`` derivation
    (letter-spacing collapsed; split into complete sentences of >= 5 words that start on a
    capital/digit and are not nav/chrome; PREFER the sentence carrying the cluster's numeric
    value). Falls back to the focused ``_claim_sentence`` (context_snippet) then the body.
    Deterministic + question-agnostic. Used by the Fix 1(d) invariant so two baskets that
    LOOK identical to the reader are detected as the same claim even when their raw bodies
    differ (one a chrome-wrapped copy, one a clean abstract of the SAME finding)."""
    body = _normalize_unicode_text(_collapse_letter_spacing(_row_text(row)))
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", body.strip())
        if len(s.split()) >= 5
        and (s.strip()[:1].isupper() or s.strip()[:1].isdigit())
        and not _VISIBLE_CHROME_RE.search(s)
    ]
    value_tok: Optional[str] = None
    if bucket_value is not None:
        try:
            v = float(bucket_value)
            value_tok = str(int(v)) if v == int(v) else str(v)
        except (TypeError, ValueError):
            value_tok = None
    if value_tok:
        for s in sentences:
            if value_tok in s:
                return s
    if sentences:
        return sentences[0]
    focused = _claim_sentence(row, bucket_value)
    return focused or body


def _apply_representative_invariant(
    groups: dict[tuple, list[int]],
    rows: list[dict[str, Any]],
    rank_fn,
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
) -> tuple[dict[tuple, list[int]], int]:
    """Fable Fix 1(d): the POST-PASS same-claim invariant. UNION any two numeric baskets
    whose chosen representative's VISIBLE claim sentence is byte-identical (after
    ``_rung0_signature`` normalization) — a residual false-split the split-confirm / NLI
    left behind — and, when the cross-encoder is active, any two SAME-VALUE baskets whose
    representatives BIDIRECTIONALLY entail. UNION-only (keep-all, §-1.3); never drops a row,
    never relaxes a verify gate; corroboration is recomputed over DISTINCT works downstream
    so a same-work re-merge stays honest. Sentinel (``__unknown__`` / ``__qual__``) keys are
    left untouched (their subjects are unresolved — pooling them here would re-introduce the
    boilerplate false-merge the value-bucket guard removed). Fail-LOUD (logged). Merges to
    the LOWEST-index cluster key (deterministic). Returns ``(groups, merged_count)``.

    ``entail_fn`` is the deterministic test seam; production passes None => the lazy resident
    ``entails_directional``."""
    keys = list(groups.keys())
    if len(keys) < 2:
        return groups, 0
    sig_of: dict[int, str] = {}
    val_of: dict[int, Any] = {}
    text_of: dict[int, str] = {}
    for i, key in enumerate(keys):
        is_sentinel = (
            isinstance(key, tuple) and key and key[0] in ("__unknown__", "__qual__")
        )
        member_ris = sorted(set(groups[key]))
        # Fable Fix 2(a) (S2/S3 re-pass iter-6): allow a SINGLE-member sentinel
        # (__unknown__/__qual__) whose VISIBLE sentence is a real mergeable CLAIM into the
        # byte-identical same-claim union — the row the blanket sentinel-skip wrongly excluded
        # (drb_72 #4/#43 Eloundou "46% of jobs", #52/#53 Brookings "0.8% ... share of middle
        # managers": two byte-identical singletons carrying an __unknown__ key that therefore
        # never unioned, rep_invariant_merge_count stuck at 0). A MULTI-member sentinel POOL stays
        # excluded (pooling an unresolved-subject pool here would re-introduce the boilerplate
        # false-merge the value-bucket guard removed). The _sentence_mergeable(vis) guard below
        # still blocks any boilerplate visible line, so this can only UNION two byte-identical (or
        # same-value bidirectionally-entailing) REAL claims. §-1.3-safe (UNION-only, keep-all).
        if is_sentinel and len(member_ris) > 1:
            continue
        value = _cluster_value_bucket(key, rows, member_ris)
        rep_ri = _choose_clean_representative(member_ris, rank_fn, rows)
        vis = _visible_claim_sentence(rows[rep_ri], value)
        # P0-1 (iter-4, Fable): only a real, non-boilerplate CLAIM sentence may anchor the
        # post-pass same-claim union. A byte-identical heading / license / metadata visible line is
        # NOT a claim and must never merge two DIFFERENT works — leave it out (stays SPLIT, keep-all).
        if not _sentence_mergeable(vis):
            continue
        sig = _rung0_signature(vis)
        if sig:
            sig_of[i] = sig
            val_of[i] = value
            text_of[i] = _normalize_unicode_text(_collapse_letter_spacing(vis))
    parent = list(range(len(keys)))

    def _find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def _union(a: int, b: int) -> None:
        ra, rb = _find(a), _find(b)
        if ra == rb:
            return
        lo, hi = (ra, rb) if ra < rb else (rb, ra)
        parent[hi] = lo

    # (1) byte-identical visible representative => same claim (deterministic, no judge).
    by_sig: dict[str, list[int]] = {}
    for i, s in sig_of.items():
        by_sig.setdefault(s, []).append(i)
    n_identical = 0
    for _s, idxs in by_sig.items():
        for other in idxs[1:]:
            if _find(idxs[0]) != _find(other):
                _union(idxs[0], other)
                n_identical += 1

    # (2) bidirectional-entailment leg (only when the cross-encoder is active): within a
    #     shared numeric value bucket, union representatives that BOTH-way entail. Bounded
    #     (per-bucket + total-pair caps) so a degraded CPU encoder can never run-pin the box.
    n_entail = 0
    nli_on = _consolidation_nli_enabled() or _finding_dedup_nli_enabled()
    if nli_on and len(sig_of) >= 2:
        if entail_fn is None:
            from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
                entails_directional,
            )
            entail_fn = entails_directional
        buckets: dict[Any, list[int]] = {}
        for i in sig_of:
            try:
                vk = round(float(val_of[i]), 6)
            except (TypeError, ValueError):
                continue
            buckets.setdefault(vk, []).append(i)
        max_pairs = _finding_dedup_nli_max_pairs()
        pairs_done = 0
        for _vk, idxs in buckets.items():
            if len(idxs) < 2 or len(idxs) > 32:  # a huge same-value bucket => skip (bounded)
                continue
            for a in range(len(idxs)):
                if pairs_done >= max_pairs:
                    break
                for b in range(a + 1, len(idxs)):
                    if pairs_done >= max_pairs:
                        break
                    ia, ib = idxs[a], idxs[b]
                    if _find(ia) == _find(ib):
                        continue
                    ta, tb = text_of[ia], text_of[ib]
                    fwd = entail_fn(ta, tb)
                    rev = entail_fn(tb, ta) if fwd is True else None
                    pairs_done += 1
                    if fwd is True and rev is True:
                        _union(ia, ib)
                        n_entail += 1

    merged = n_identical + n_entail
    if merged == 0:
        return groups, 0
    merged_members: dict[int, list[int]] = {}
    for i in range(len(keys)):
        merged_members.setdefault(_find(i), []).extend(groups[keys[i]])
    new_groups: dict[tuple, list[int]] = {}
    for i in range(len(keys)):  # original key order => order-stable result dict
        if _find(i) != i:
            continue
        new_groups[keys[i]] = sorted(set(merged_members[i]))
    logger.info(
        "[finding_dedup] Fix 1(d) representative-invariant post-pass: unioned %d basket(s) "
        "(%d byte-identical visible rep, %d bidirectional-entail) — no two surviving baskets "
        "share the same visible claim (§-1.1 THE GHOST closed; UNION-only, keep-all)",
        merged, n_identical, n_entail,
    )
    return new_groups, merged


# ─────────────────────────────────────────────────────────────────────────
# NUMBERS-STRICT value presence — S2/S3 re-pass iter-5 P0-1(b) (Fable)
# ─────────────────────────────────────────────────────────────────────────
# A numeric basket asserts a specific NUMBER. Two members may stay merged ONLY when that number
# literally appears in BOTH members' claim sentences (numbers-strict — the operator's locked
# "numbers strict" faithfulness rule). If ``_claim_sentence`` fell back to a boilerplate /
# Narrative-Review-checklist rep that does NOT contain the cluster's value (the drb_72 basket-27
# 'their/level/4.0' merge where the rep sentence never contained '4'), the pair CANNOT corroborate
# that number — SPLIT. Tolerant of surface formatting (5.5 == '5.5%' == '5.5 per cent'; 1000 ==
# '1,000') by parsing every numeric token to a float and comparing values, so a true corroborator
# formatted differently is never falsely split. Fail-OPEN when there is no comparable bucket value
# (returns True — the gate simply does not apply and NLI decides).
_NUM_TOKEN_RE = re.compile(
    r"[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d+(?:\.\d+)?|[-+]?\.\d+"
)


def _text_numeric_values(text: str) -> list[float]:
    """Every numeric literal in ``text`` parsed to a float (thousands-commas stripped). Pure."""
    out: list[float] = []
    for m in _NUM_TOKEN_RE.finditer(_normalize_unicode_text(text or "")):
        tok = m.group(0).replace(",", "")
        try:
            out.append(float(tok))
        except ValueError:
            continue
    return out


def _text_contains_value(text: str, value: Any) -> bool:
    """True iff ``text`` contains a numeric literal equal (to float precision) to ``value``.
    Fail-OPEN: a non-numeric / None ``value`` returns True (the numbers-strict gate does not
    apply). Tolerant of formatting variants (percent / per-cent / thousands-commas) because it
    compares parsed VALUES, not surface strings. General/question-agnostic."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True
    tol = max(1e-9, abs(v) * 1e-6)
    for x in _text_numeric_values(text):
        if abs(x - v) <= tol:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# POST-MERGE member re-verify — S2/S3 re-pass Fable Fix 1 (anti-fabrication, THE P0)
# ─────────────────────────────────────────────────────────────────────────
# consolidation-NLI joins cluster REPRESENTATIVES (not individual members), and a same-value
# bucket can pool two clusters whose reps entail while their OTHER members do not — so a member
# can enter a merged basket WITHOUT its OWN claim sentence ever being checked against the FINAL
# basket rep. That fabricates corroboration on a numeric macro claim (drb_72 #128: springer /
# mdpi absorbed onto a PWBM TFP/GDP 1.5%-by-2035 projection neither quote contains; #339: a
# data-entry career-guide page onto an Eloundou-rubric claim). A fabricated corroboration count on
# a clinical dose / contraindication / macro number is exactly the §-1.1 "lethal" failure.
#
# THE FIX (general, question-agnostic): after ALL merge passes, re-verify each non-rep member of
# every surviving multi-member basket against the FINAL rep — keep only members that are
# byte-identical OR bidirectionally entail the rep AND (numbers-strict) carry the basket's value
# when the rep does; SPLIT the rest into their own singletons. §-1.3-safe: SPLIT-only (keep-all —
# every split member still flows through as its own basket); it never drops a row and never
# invents a merge. Fail-OPEN toward SPLIT (an infra ``None`` / one-way / contradiction splits — a
# false merge is worse than a missed one, per the operator's "over-merge corrupts attribution;
# under-merge is safe" rule). Fail-LOUD telemetry. Runs on numeric AND sentinel baskets (a false
# merge can land in either key). Reuses the SAME byte-identical + numbers-strict + bidirectional
# gate the pre-consolidation split-confirm uses, so it introduces no new judgment surface.
_POST_MERGE_REVERIFY_ENV = "PG_FINDING_POST_MERGE_REVERIFY"


def _post_merge_reverify_enabled() -> bool:
    """``PG_FINDING_POST_MERGE_REVERIFY`` kill switch (LAW VI, DEFAULT-ON, Fable Fix 1). OFF =>
    byte-identical legacy (no post-merge member re-verify)."""
    return os.getenv(_POST_MERGE_REVERIFY_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _apply_post_merge_reverify(
    groups: dict[tuple, list[int]],
    rows: list[dict[str, Any]],
    rank_fn,
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
    telemetry: Optional[dict[str, Any]] = None,
) -> tuple[dict[tuple, list[int]], int]:
    """Fable Fix 1: re-verify every non-rep member of every surviving multi-member basket against
    the FINAL representative (see the section note). Returns ``(groups, members_split)``. SPLIT
    members become distinct singleton keys so the downstream basket loop treats each as its own
    corroboration=1 basket. Deterministic; ``entail_fn`` is the test seam (production => the lazy
    resident ``entails_directional``)."""
    if entail_fn is None:
        from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
            entails_directional,
        )
        entail_fn = entails_directional
    value_strict = _numeric_value_strict_enabled()
    out: dict[tuple, list[int]] = {}
    members_split = 0
    clusters_split = 0
    for key, member_ris in groups.items():
        distinct = sorted(set(member_ris))
        if len(distinct) < 2:
            out[key] = member_ris
            continue
        value = _cluster_value_bucket(key, rows, distinct)
        rep_ri = _choose_clean_representative(distinct, rank_fn, rows)
        rep_text = _normalize_unicode_text(
            _collapse_letter_spacing(_visible_claim_sentence(rows[rep_ri], value))
        )
        rep_sig = _rung0_signature(rep_text)
        rep_mergeable = _sentence_mergeable(rep_text)
        rep_has_value = (not value_strict) or _text_contains_value(rep_text, value)
        confirmed = [rep_ri]
        split_members: list[int] = []
        for mri in distinct:
            if mri == rep_ri:
                continue
            m_text = _normalize_unicode_text(
                _collapse_letter_spacing(_visible_claim_sentence(rows[mri], value))
            )
            # A byte-identical VISIBLE claim sentence IS the same claim — always keep (mirrors the
            # rep-invariant byte-identical leg; never split a genuine duplicate on an NLI None).
            if rep_sig and _rung0_signature(m_text) == rep_sig:
                confirmed.append(mri)
                continue
            # A boilerplate / heading / non-propositional rep or member cannot corroborate a CLAIM.
            if not (rep_mergeable and _sentence_mergeable(m_text)):
                split_members.append(mri)
                continue
            # Numbers-strict: the basket's value must literally appear in BOTH claim sentences.
            if value_strict and not (rep_has_value and _text_contains_value(m_text, value)):
                split_members.append(mri)
                continue
            # Bidirectional entailment of the member's OWN claim sentence vs the FINAL rep.
            fwd = entail_fn(rep_text, m_text)
            rev = entail_fn(m_text, rep_text) if fwd is True else None
            if fwd is True and rev is True:
                confirmed.append(mri)
            else:
                # fail-open toward SPLIT (None / one-way / contradiction — anti-fabrication).
                split_members.append(mri)
        out[key] = sorted(set(confirmed))
        for mri in split_members:
            out[tuple(key) + ("__reverify_split__", mri)] = [mri]
        if split_members:
            clusters_split += 1
            members_split += len(split_members)
    if members_split:
        logger.info(
            "[finding_dedup] Fable Fix 1 post-merge re-verify: SPLIT %d member(s) out of %d "
            "basket(s) whose OWN claim sentence did not entail the final rep (anti-fabrication; "
            "SPLIT-only, keep-all, §-1.3)",
            members_split, clusters_split,
        )
    if telemetry is not None:
        telemetry["post_merge_members_split"] = (
            telemetry.get("post_merge_members_split", 0) + members_split
        )
        telemetry["post_merge_clusters_split"] = (
            telemetry.get("post_merge_clusters_split", 0) + clusters_split
        )
    return out, members_split


def _numeric_nli_confirm_enabled() -> bool:
    """``PG_FINDING_NUMERIC_NLI_CONFIRM`` kill switch (LAW VI, DEFAULT-ON, Fix 1(A)). When
    ON, the numeric ``_finding_key`` tuple is treated as CANDIDATE RECALL only: two rows that
    collide on the same (folded-subject, predicate, value, unit) tuple must ALSO bidirectionally
    entail on their claim sentence to STAY in one basket. An unconfirmed member splits to its
    own singleton (corroboration 1) — the §-1.1 defense against a folded-subject / locator-value
    tuple collision merging two DIFFERENT claims (mdpi+santander, imf+oecd). OFF => the tuple
    key alone decides (byte-identical legacy)."""
    return os.getenv("PG_FINDING_NUMERIC_NLI_CONFIRM", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _numeric_nli_confirm_strict_enabled() -> bool:
    """``PG_FINDING_NUMERIC_NLI_CONFIRM_STRICT`` kill switch (LAW VI, DEFAULT-ON, S2/S3 re-pass
    iter-2 P0-3(b)). The fail-open DIRECTION for the numeric split-confirm: a member stays in a
    merged basket ONLY when the NLI POSITIVELY confirms same-claim in BOTH directions. Anything
    the judge does NOT positively confirm — a confident non-entailment, a one-way relation, OR an
    infra ``None`` (empty text / model unavailable / degrade) — SPLITS to its own singleton. A
    false-merge is worse than a missed-merge (basket 0 corr=15 / basket 24 corr=27 were
    unconfirmed merges that shipped — that path must be impossible). OFF => the legacy direction
    (infra ``None`` KEEPS the numeric-tuple prior; split only on a CONFIDENT non-entailment)."""
    return os.getenv("PG_FINDING_NUMERIC_NLI_CONFIRM_STRICT", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _numeric_value_strict_enabled() -> bool:
    """``PG_FINDING_NUMERIC_VALUE_STRICT`` kill switch (LAW VI, DEFAULT-ON, iter-5 P0-1(b), Fable).
    ON => two numeric-cluster members may stay merged ONLY when the cluster's numeric VALUE
    literally appears in BOTH claim sentences (numbers-strict). A rep/member whose claim sentence
    (e.g. a Narrative-Review-checklist boilerplate fallback) does NOT carry the value CANNOT
    corroborate that number => SPLIT. OFF => the pre-P0-1(b) behavior (no value-presence gate)."""
    return os.getenv("PG_FINDING_NUMERIC_VALUE_STRICT", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _confirm_numeric_clusters_via_nli(
    groups: dict[tuple, list[int]],
    rows: list[dict[str, Any]],
    rank_fn,
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
    telemetry: Optional[dict[str, Any]] = None,
) -> dict[tuple, list[int]]:
    """Fix 1(A) (Fable): NLI is the merge DECIDER, the numeric tuple key only RECALL. For each
    multi-member NUMERIC cluster (a real subject/predicate/value/unit key — NOT an ``__unknown__``
    or ``__qual__`` sentinel), keep only members whose focused CLAIM SENTENCE bidirectionally
    entails the representative's claim sentence; an unconfirmed member (one-way / contradiction /
    infra ``None``) SPLITS into its own singleton so it can no longer inflate corroboration on a
    key collision. Letter-spacing is collapsed BEFORE NLI (Fix 7) so a degraded body is not
    silently un-readable. Runs BEFORE ``_apply_consolidation_nli`` so a split member that
    genuinely paraphrases ANOTHER cluster can still re-merge there through the SAME strict gate.

    §-1.3-safe: SPLIT-only; never drops a row (every member still flows through ``deduped_rows``)
    and never invents a merge. Deterministic (rep = highest-ranked member; each member judged
    against it). Same-value corroboration the cross-encoder confirms is preserved (P=1.0 in the
    bake-off); only the false key-collision baskets dissolve. ``entail_fn`` is the deterministic
    test seam; production passes None => the lazy resident ``entails_directional``."""
    if entail_fn is None:
        from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
            entails_directional,
        )
        entail_fn = entails_directional

    value_strict = _numeric_value_strict_enabled()
    tel_clusters_split = 0   # clusters that lost >=1 member
    tel_members_confirmed = 0
    tel_members_split = 0
    tel_members_split_value = 0  # split specifically by the numbers-strict value gate
    out: dict[tuple, list[int]] = {}
    for key, member_ris in groups.items():
        distinct = sorted(set(member_ris))
        is_sentinel = (
            isinstance(key, tuple) and key and key[0] in ("__unknown__", "__qual__")
        )
        if len(distinct) < 2 or is_sentinel:
            out[key] = member_ris
            continue
        value = _cluster_value_bucket(key, rows, distinct)
        rep_ri = max(distinct, key=rank_fn)
        rep_text = _normalize_unicode_text(
            _collapse_letter_spacing(_claim_sentence(rows[rep_ri], value))
        )
        rep_sig = _rung0_signature(rep_text)
        confirmed = [rep_ri]
        split_members: list[int] = []
        strict = _numeric_nli_confirm_strict_enabled()
        rep_mergeable = _sentence_mergeable(rep_text)
        # P0-1(b) numbers-strict: whether the REP claim sentence even carries the cluster's value.
        # When it does NOT (a boilerplate fallback rep), NO member can corroborate that number.
        rep_has_value = (not value_strict) or _text_contains_value(rep_text, value)
        for mri in distinct:
            if mri == rep_ri:
                continue
            m_text = _normalize_unicode_text(
                _collapse_letter_spacing(_claim_sentence(rows[mri], value))
            )
            # P0-1 (iter-4, Fable): a boilerplate / heading / non-propositional anchor is NOT a
            # claim — it may never be a merge key without a real semantic confirm. If EITHER the
            # rep OR the member sentence is non-mergeable (heading / license / metadata / too-short),
            # the pair cannot corroborate a CLAIM: SPLIT (keep-all — the member still flows through
            # as its own singleton basket). This is how B025 (AME-checklist boilerplate) and B226 (a
            # shared heading) stop byte-identical-merging two DIFFERENT works. Question-agnostic.
            if not (rep_mergeable and _sentence_mergeable(m_text)):
                split_members.append(mri)
                continue
            # P0-1(b) numbers-strict (iter-5, Fable): the cluster's numeric VALUE must literally
            # appear in BOTH claim sentences before the pair may stay merged. A boilerplate /
            # Narrative-Review-checklist rep (or member) that does NOT carry the value cannot
            # corroborate that number (the drb_72 basket-27 'their/level/4.0' merge whose rep
            # never contained '4'): SPLIT. Tolerant of formatting (5.5 == '5.5%'); fail-open when
            # the bucket value is non-numeric. §-1.3-safe (SPLIT-only, keep-all).
            if value_strict and not (rep_has_value and _text_contains_value(m_text, value)):
                split_members.append(mri)
                tel_members_split_value += 1
                continue
            # Fix 1(d) root-cause: a byte-identical CLAIM sentence IS the same claim — never
            # SPLIT it on an NLI None / one-way answer (the drb_72 3x-identical-PDF false split).
            # Confirm deterministically BEFORE the judge (the rung-0 principle applied per-member);
            # §-1.3-safe (a byte-identical CLAIM sentence can only be corroboration, never a false
            # merge — boilerplate/heading was already split out above).
            if rep_sig and _rung0_signature(m_text) == rep_sig:
                confirmed.append(mri)
                continue
            fwd = entail_fn(rep_text, m_text)
            rev = entail_fn(m_text, rep_text) if fwd is True else None
            if fwd is True and rev is True:
                confirmed.append(mri)  # POSITIVELY confirmed both directions => stays merged
            elif strict:
                # P0-3(b) SPLIT-not-merge: anything NOT positively confirmed — a confident
                # non-entailment, a one-way relation, OR an infra ``None`` (empty text / model
                # unavailable / degrade) — splits to its own singleton. A false-merge is worse
                # than a missed-merge; an unconfirmed numeric merge must be impossible.
                split_members.append(mri)
            else:
                # Legacy direction: the tuple key is a STRONG same-claim prior, so split only on
                # a CONFIDENT non-entailment; an infra ``None`` KEEPS the member (byte-identical).
                if fwd is False or rev is False:
                    split_members.append(mri)
                else:
                    confirmed.append(mri)
        out[key] = sorted(set(confirmed))
        for mri in split_members:
            # A distinct, numeric-shaped singleton key: preserves key[2]=value so the
            # downstream value-bucket + basket loop treat it correctly, uniquified by row idx.
            out[tuple(key) + ("__split__", mri)] = [mri]
        # P0-1(b) telemetry: per-cluster confirm/split counts surfaced to consolidation_summary.
        tel_members_confirmed += len(set(confirmed)) - 1  # members kept besides the rep
        tel_members_split += len(split_members)
        if split_members:
            tel_clusters_split += 1
    if telemetry is not None:
        telemetry["clusters_split"] = telemetry.get("clusters_split", 0) + tel_clusters_split
        telemetry["members_confirmed"] = (
            telemetry.get("members_confirmed", 0) + tel_members_confirmed
        )
        telemetry["members_split"] = telemetry.get("members_split", 0) + tel_members_split
        telemetry["members_split_numbers_strict"] = (
            telemetry.get("members_split_numbers_strict", 0) + tel_members_split_value
        )
    return out


# ─────────────────────────────────────────────────────────────────────────
# Qualitative-claim basket formation — I-deepfix-001 D1 (#1344)
# ─────────────────────────────────────────────────────────────────────────
#
# §-1.3 Principle 2 (CONSOLIDATE qualitative claims TOO, never numeric-only):
# the numeric ``_finding_key`` path above keys every corroboration basket on an
# EXTRACTED NUMERIC value slot, so a QUALITATIVE (non-numeric) claim that several
# INDEPENDENT sources assert can never form a multi-source basket — it survives
# as a SAFE singleton (never dropped) but earns NO corroboration weight. That is
# the D1 diced-dice blind spot (``dice_d1_consolidation_qualitative_basket``):
# baskets keyed numeric-only. This pass groups the NO-numeric-finding rows that
# assert the SAME qualitative claim into ONE multi-citation basket carrying ALL
# members, keyed on a NON-NUMERIC normalized subject/predicate signature, so the
# corroboration (count + distinct hosts) is surfaced as a WEIGHT.
#
# CONSERVATIVE (false-merge is worse than no-merge, §-1.3): two rows cluster ONLY
# when their content-word shingle sets clear a HIGH Jaccard threshold AND their
# polarity signatures match (an antonym / negation flip blocks the merge even at
# Jaccard ~1.0). A genuinely-unique claim stays a singleton (never emitted as a
# basket). Plain greedy single-pass clustering — deterministic + order-stable.
#
# FAITHFULNESS-NEUTRAL / KEEP-ALL: this only ADDS corroboration baskets +
# ``corroboration_count`` WEIGHT. It DROPS NO ROW (every member still flows
# through ``deduped_rows`` under keep-all), and touches NO verify gate
# (strict_verify / the NLI entailment verifier / 4-role D8 / provenance /
# span-grounding are untouched). Even an over-merge can only inflate a weight
# count — it can never relax faithfulness and never lose a source.
#
# The shingle / polarity / Jaccard predicates are REUSED from the proven
# fact_dedup prose path (the polarity guard is the Codex #1289 P1 antonym-flip
# defense), imported LAZILY at function scope — the same defer-to-dodge-cycles
# discipline this module already uses for credibility_pass / consolidation_nli.
_QUAL_BASKET_ENV = "PG_FINDING_DEDUP_QUALITATIVE"
_QUAL_JACCARD_ENV = "PG_FINDING_DEDUP_QUALITATIVE_JACCARD"
_QUAL_JACCARD_DEFAULT = "0.82"
# Cap the readable signature-token word count (deterministic, bounded key string).
_QUAL_KEY_MAX_WORDS = 16
# I-deepfix-001 P4 recall rung-1 (#1344): the qualitative-NLI union SUB-flag. The lexical
# greedy pass (_build_qualitative_groups) is the cheap near-verbatim CANDIDATE stage; when
# this sub-flag AND the master PG_CONSOLIDATION_NLI gate are BOTH ON, a SECOND semantic-recall
# pass unions candidate clusters whose representatives BIDIRECTIONALLY entail (the SAME strict
# NLI the numeric path uses). OFF (either flag) => byte-identical lexical-only behavior.
_QUAL_NLI_ENV = "PG_CONSOLIDATION_NLI_QUALITATIVE"

# ─────────────────────────────────────────────────────────────────────────
# Coverage-fix keystone — I-deepfix-001 Wave 1b (#1344), REAL_PLAN_2026 coverage_fix item 1
# ─────────────────────────────────────────────────────────────────────────
# The plan-canonical qualitative same-claim grouping flag: `PG_FINDING_DEDUP_NLI`. When ON, a
# THIRD (directional) semantic-recall pass unions the lexical qualitative candidate clusters
# whose representatives STRICTLY BIDIRECTIONALLY entail into ONE corroboration basket, using the
# 3-state directional primitive `consolidation_nli.entails_directional` (True / False / None):
#   * bidirectional entails (BOTH directions True)  => MERGE (keep-all, one basket);
#   * one-direction-only (exactly one True)         => an EXTENSION relation, do NOT merge;
#   * contradiction (neither direction entails)     => a durable relation, do NOT merge;
#   * infra `None` on EITHER direction (empty text / cross-encoder unavailable) => NO merge, a
#     FAIL-CLOSED singleton, and the run CONTINUES (never raises, never drops a row).
# This is the fail-closed-CONTINUE keystone the `score_pairs`-based `_apply_qualitative_nli_union`
# (PG_CONSOLIDATION_NLI_QUALITATIVE) does not provide (that path RAISES on a non-OOM model
# failure). Both flags are additive / merge-only / keep-all, BUT they are NOT independently safe
# together: when BOTH are ON the legacy union runs FIRST and would RAISE on a non-OOM model fault
# BEFORE the keystone's fail-closed grouping runs, aborting the run at the dedup step (the exact
# Wave-3 slate config). So the wiring in `_build_qualitative_groups` GUARDS the legacy union
# under the keystone regime ONLY: it degrades a legacy raise to a §-1.3-safe under-merge (logged
# loud, never except:pass) and lets the keystone's own None path yield singletons if the model is
# truly dead. When the keystone is OFF the legacy union is UNGUARDED => byte-identical legacy
# behavior. §-1.3 CONSOLIDATE-keep-all, WEIGHT-ONLY: no row dropped, no verify gate touched. The
# extension / contradiction relations are surfaced downstream in Wave 2 (cross_source_synthesis);
# this build's contribution is the MERGE decision plus leaving non-bidirectional pairs un-merged.
# DEFAULT-OFF => byte-identical. Slate-ON per the plan (Wave-3 activation).
_FINDING_DEDUP_NLI_ENV = "PG_FINDING_DEDUP_NLI"
# LAW VI knobs (no hardcoded values): bounded scoring concurrency, an O(n^2) pair-count cap, and a
# total wall-clock deadline (a CPU-degraded cross-encoder must not run-pin the box across up to
# 2*MAX_PAIRS single-item forwards — mirrors the consolidation W04 wall).
_FINDING_DEDUP_NLI_WORKERS_ENV = "PG_FINDING_DEDUP_NLI_WORKERS"
_FINDING_DEDUP_NLI_WORKERS_DEFAULT = "8"
_FINDING_DEDUP_NLI_MAX_PAIRS_ENV = "PG_FINDING_DEDUP_NLI_MAX_PAIRS"
_FINDING_DEDUP_NLI_MAX_PAIRS_DEFAULT = "20000"
_FINDING_DEDUP_NLI_WALL_SECONDS_ENV = "PG_FINDING_DEDUP_NLI_WALL_SECONDS"
# P0-2 (S2/S3 re-pass iter-4, Fable / §9.1.8 never-starve): raised 180 -> 900. With the OOM
# handler now HALVING the batch and STAYING on the A100 GPU (consolidation_nli, no whole-run CPU
# degrade), the pair budget scores fast; a generous wall is free insurance (billed by actual
# usage) that lets the full pair set complete on a large drb_72-scale corpus instead of the judge
# going BLIND (0/130 scored in 180s was the CPU-degrade symptom this closes). A CAP, not a target.
_FINDING_DEDUP_NLI_WALL_SECONDS_DEFAULT = "900"

# ─────────────────────────────────────────────────────────────────────────
# 3a — WIDENED qualitative CANDIDATE NOMINATION (F3, I-deepfix-001 #1369)
# ─────────────────────────────────────────────────────────────────────────
# ROOT CAUSE (Fable F3-3a, forensic on the drb_72 real run): the qualitative
# candidate NOMINATION is lexical NEAR-VERBATIM only. `_build_qualitative_groups`
# greedy-clusters rows by content-word shingle Jaccard >= 0.82, and the keystone
# `_apply_finding_dedup_nli_grouping` then NLI-confirms only cluster REPRESENTATIVES
# among the survivors. So a cross-document PARAPHRASE whose surface wording differs
# enough that its shingle-Jaccard falls below 0.82 stays its OWN singleton cluster —
# and when the corpus is large the O(n^2) rep-pair count trips the MAX_PAIRS cap and
# the whole directional grouping SKIPS (an under-merge), so the paraphrase never even
# becomes a CANDIDATE for the NLI union. The multi-source basket collapses.
#
# THE FIX (widen the NOMINATION only, NLI stays the sole MERGE decision — §-1.3 +
# the F3 anti-fabrication law): NOMINATE additional cross-cluster candidate PAIRS by
# TOKEN-CONTAINMENT (the smaller cluster's content-token set is largely CONTAINED in
# the other's — an ASYMMETRIC overlap that catches paraphrase/expansion pairs the
# symmetric Jaccard 0.82 near-verbatim gate misses), then CONFIRM each nominated pair
# through the SAME strict bidirectional-entailment NLI gate the keystone uses
# (`consolidation_nli.entails_directional`, BOTH directions True) plus the polarity
# hard-block. A pair MERGES iff the NLI confirms it — token-containment is ONLY a
# recall-oriented candidate BLOCKER, never a merge. This is strictly MORE recall than
# rep-only near-verbatim, and it is BOUNDED (only containment-passing pairs are ever
# NLI-scored), so it also RECALLS in the over-cap regime where the all-pairs keystone
# skips. NO row is dropped (keep-all); no numeric value-bucket rule is touched; the
# faithfulness engine (strict_verify / the entailment verifier / 4-role D8 /
# provenance / span-grounding) is untouched. LAW VI: env-tunable, kill-switchable.
_QUAL_NOMINATE_ENV = "PG_FINDING_DEDUP_QUALITATIVE_NOMINATE"
# Asymmetric content-token containment threshold: nominate a cluster pair when
# |Ti ∩ Tj| / min(|Ti|, |Tj|) >= this. Below the near-verbatim Jaccard (0.82) on
# purpose — the whole point is to nominate paraphrases Jaccard misses; the STRICT
# bidirectional NLI is what keeps a merely-token-overlapping-but-distinct pair apart.
_QUAL_NOMINATE_CONTAINMENT_ENV = "PG_FINDING_DEDUP_QUALITATIVE_NOMINATE_CONTAINMENT"
_QUAL_NOMINATE_CONTAINMENT_DEFAULT = "0.60"
# Minimum content tokens a cluster representative must carry to be nominatable (a
# 1-2 token stub cannot be a reliable containment signal — a false-positive guard).
_QUAL_NOMINATE_MIN_TOKENS = 4
# O(n^2) nominated-pair cap (LAW VI). Over the cap the pass SKIPS (under-merge, §-1.3
# keep-all — never drops a corroborator). Shares the finding-dedup-NLI default.
_QUAL_NOMINATE_MAX_PAIRS_ENV = "PG_FINDING_DEDUP_QUALITATIVE_NOMINATE_MAX_PAIRS"
_QUAL_NOMINATE_MAX_PAIRS_DEFAULT = "20000"


def _qualitative_enabled() -> bool:
    """``PG_FINDING_DEDUP_QUALITATIVE`` kill switch (LAW VI). DEFAULT-ON: the
    qualitative-basket pass is the §-1.3 CONSOLIDATE-qualitative-too path. Set to
    ``0`` to restore the byte-identical numeric-only behavior (no qualitative
    baskets formed). It is ADDITIONALLY gated on the consolidate-keep-all regime
    (``credibility_redesign_enabled``) by the caller, so a legacy (drop) run never
    sees a qualitative basket."""
    return os.getenv(_QUAL_BASKET_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _qualitative_nli_enabled() -> bool:
    """I-deepfix-001 P4 recall rung-1 (#1344): the qualitative-NLI union sub-gate. The
    SECOND semantic-recall pass runs ONLY when BOTH the master ``PG_CONSOLIDATION_NLI``
    gate (single source of truth in ``consolidation_nli.consolidation_nli_enabled``) AND
    this ``PG_CONSOLIDATION_NLI_QUALITATIVE`` sub-flag are ON.

    DEFAULT-ON for the sub-flag, but the union is INERT by default: the master gate is
    default-OFF, so a default run never activates the union and the qualitative pass stays
    byte-identical lexical-only. The benchmark slate sets the master ON (run_gate_b) and
    inherits this union without extra config. Set ``PG_CONSOLIDATION_NLI_QUALITATIVE=0`` to
    keep the numeric-NLI path but revert the qualitative pass to lexical-only."""
    if not _consolidation_nli_enabled():
        return False
    return os.getenv(_QUAL_NLI_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _finding_dedup_nli_enabled() -> bool:
    """``PG_FINDING_DEDUP_NLI`` kill switch (LAW VI). DEFAULT-OFF => the directional
    bidirectional-entailment qualitative grouping never runs and the qualitative pass is
    byte-identical. ON => the coverage-fix keystone (Wave 1b) unions qualitative candidate
    clusters that STRICTLY bidirectionally entail (fail-closed to a singleton on an infra
    None). Independent of the master ``PG_CONSOLIDATION_NLI`` gate — it is the plan-canonical
    keystone, so it is gated by its OWN flag only."""
    return os.getenv(_FINDING_DEDUP_NLI_ENV, "0").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _finding_dedup_nli_workers() -> int:
    """Bounded scoring concurrency for the directional qualitative grouping (LAW VI). A
    malformed / out-of-range value falls back to the default (fail-safe, never an unbounded
    pool). Clamped to [1, 64] to mirror ``consolidation_nli._workers``."""
    raw = os.environ.get(_FINDING_DEDUP_NLI_WORKERS_ENV, "").strip() or _FINDING_DEDUP_NLI_WORKERS_DEFAULT
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[finding_dedup] %s=%r not an int; using default %s",
            _FINDING_DEDUP_NLI_WORKERS_ENV, raw, _FINDING_DEDUP_NLI_WORKERS_DEFAULT,
        )
        return int(_FINDING_DEDUP_NLI_WORKERS_DEFAULT)
    return max(1, min(64, value))


def _finding_dedup_nli_max_pairs() -> int:
    """The O(n^2) candidate-pair cap for the directional qualitative grouping (LAW VI). Over
    the cap the pass SKIPS scoring and leaves the clusters UNMERGED (an under-merge, keep-all,
    §-1.3 safe — never drops a corroborator). A malformed value falls back to the default."""
    raw = os.environ.get(_FINDING_DEDUP_NLI_MAX_PAIRS_ENV, "").strip() or _FINDING_DEDUP_NLI_MAX_PAIRS_DEFAULT
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[finding_dedup] %s=%r not an int; using default %s",
            _FINDING_DEDUP_NLI_MAX_PAIRS_ENV, raw, _FINDING_DEDUP_NLI_MAX_PAIRS_DEFAULT,
        )
        return int(_FINDING_DEDUP_NLI_MAX_PAIRS_DEFAULT)
    return max(1, value)


def _finding_dedup_nli_wall_seconds() -> float:
    """The TOTAL wall-clock deadline (seconds) for the directional qualitative scoring loop
    (LAW VI; mirrors ``consolidation_nli._wall_seconds``). A CPU-degraded cross-encoder would
    otherwise run-pin the box across up to ``2*MAX_PAIRS`` single-item forwards. On the deadline
    the loop STOPS scoring further pairs and keeps the edges gathered so far — an UNDER-merge only
    (§-1.3-safe: keeps MORE/equal baskets, drops no corroborator). A malformed / non-finite / ``<=0``
    value disables the wall (unbounded — the escape hatch). Default 180s."""
    raw = os.environ.get(_FINDING_DEDUP_NLI_WALL_SECONDS_ENV, "").strip() or _FINDING_DEDUP_NLI_WALL_SECONDS_DEFAULT
    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[finding_dedup] %s=%r not a float; using default %s",
            _FINDING_DEDUP_NLI_WALL_SECONDS_ENV, raw, _FINDING_DEDUP_NLI_WALL_SECONDS_DEFAULT,
        )
        return float(_FINDING_DEDUP_NLI_WALL_SECONDS_DEFAULT)
    if not math.isfinite(value) or value <= 0:
        return 0.0
    return value


def _qual_jaccard_threshold() -> float:
    """Read ``PG_FINDING_DEDUP_QUALITATIVE_JACCARD`` as a float in (0, 1].
    Malformed / out-of-range => default 0.82 (logged once at WARNING, never
    raised — a typo must not crash a paid run). 0.82 is the proven conservative
    prose-merge threshold (only near-identical restatements cluster)."""
    raw = os.environ.get(_QUAL_JACCARD_ENV, "").strip() or _QUAL_JACCARD_DEFAULT
    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[finding_dedup] %s=%r is not a float; using default %s",
            _QUAL_JACCARD_ENV, raw, _QUAL_JACCARD_DEFAULT,
        )
        return float(_QUAL_JACCARD_DEFAULT)
    if not (0.0 < value <= 1.0):
        logger.warning(
            "[finding_dedup] %s=%s out of (0,1]; using default %s",
            _QUAL_JACCARD_ENV, value, _QUAL_JACCARD_DEFAULT,
        )
        return float(_QUAL_JACCARD_DEFAULT)
    return value


def _qual_key_token(text: str) -> str:
    """A deterministic, NON-NUMERIC, human-auditable signature token for a
    qualitative basket: lowercased -> citation-tokens stripped -> alnum
    word-tokenized -> stopwords dropped -> SORTED+deduped -> capped to
    ``_QUAL_KEY_MAX_WORDS`` -> space-joined. The whole token is a single STRING
    element of the finding_key tuple, so a content word that happens to be a bare
    number (e.g. ``2024``) never makes the key NUMERIC — it stays a string.
    Reuses fact_dedup's citation/stopword/word predicates so the normalization is
    byte-consistent with the prose path."""
    from src.polaris_graph.generator.fact_dedup import (  # noqa: PLC0415
        _CITATION_TOKEN_RE,
        _STOPWORDS,
        _WORD_RE,
    )

    low = _CITATION_TOKEN_RE.sub(" ", (text or "").lower())
    words = [w for w in _WORD_RE.findall(low) if w not in _STOPWORDS]
    return " ".join(sorted(set(words))[:_QUAL_KEY_MAX_WORDS])


# ─────────────────────────────────────────────────────────────────────────
# Qualitative greedy-cluster NLI CONFIRMATION — S2/S3 re-pass P0-2
# ─────────────────────────────────────────────────────────────────────────
# The greedy shingle-Jaccard pass groups NEAR-VERBATIM rows, but citation-scaffold lines
# ("Author, A. (2024). Title. Journal.") share so much formatting vocabulary that ~18 UNRELATED
# reference lines greedily clustered into one corrob=18 fake-corroboration basket. §-1.1 names a
# misstated 'corroborated' as clinical-lethal. Fix: the greedy pass is only a CANDIDATE
# NOMINATOR — each within-cluster member must BIDIRECTIONALLY entail the cluster rep (the SAME
# strict NLI bar the numeric path uses) to stay merged; an unconfirmed member (or NLI
# unavailable) splits to a singleton (corroboration stays 1). LAW VI kill-switched (default ON).
def _qual_merge_requires_nli_enabled() -> bool:
    """``PG_QUAL_MERGE_REQUIRES_NLI`` kill switch (LAW VI, DEFAULT-ON, P0-2). A qualitative
    greedy (shingle-Jaccard) cluster is a CANDIDATE only: every member must BIDIRECTIONALLY
    entail the cluster representative to stay merged. No NLI verdict (unconfirmed / model
    unavailable / no NLI path active this run) => the member splits to a singleton
    (corroboration_count 1). OFF => byte-identical legacy (greedy Jaccard alone mints the
    basket, the fake-corroboration behavior)."""
    return os.getenv("PG_QUAL_MERGE_REQUIRES_NLI", "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _confirm_greedy_clusters_via_nli(
    rows: list[dict[str, Any]],
    clusters: list[list[Any]],
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
) -> list[list[Any]]:
    """P0-2: turn every greedy (shingle-Jaccard) qualitative cluster into an NLI-CONFIRMED
    cluster. A member is kept ONLY when it BIDIRECTIONALLY entails the cluster representative
    (the lowest-row-index member) through the SAME strict 3-state gate the qualitative keystone
    uses (``consolidation_nli.entails_directional`` in BOTH directions returning True); an
    unconfirmed member (one-direction / contradiction / infra ``None`` / polarity mismatch)
    splits into its own singleton (corroboration_count 1). ``entails_directional`` NEVER raises
    (an infra fault returns ``None`` => no merge), so a model outage degrades to a safe
    UNDER-merge, never fake corroboration.

    §-1.3-safe: this only ever SPLITS a greedy cluster; it never drops a row (every member still
    flows through ``deduped_rows`` as its own keep-all row) and never invents a new merge. The
    strict NLI union passes that run AFTER this can RE-merge a genuine paraphrase, so real
    corroboration is preserved while the citation-scaffold false cluster dissolves. Deterministic
    + order-independent (the rep is the lowest-index member; each member is judged against it).
    ``entail_fn(premise, hypothesis) -> True/False/None`` is the deterministic test-injection
    seam; production passes None => the lazy resident ``entails_directional``."""
    from src.polaris_graph.generator.fact_dedup import (  # noqa: PLC0415
        _polarity_signature, _prose_shingles,
    )
    if entail_fn is None:
        from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
            entails_directional,
        )
        entail_fn = entails_directional

    def _singleton(ri: int) -> list[Any]:
        body = _row_text(rows[ri])
        return [_prose_shingles(body), _polarity_signature(body), [ri]]

    out: list[list[Any]] = []
    for cluster in clusters:
        members = cluster[2]
        if len(members) < 2:
            out.append(cluster)
            continue
        rep_ri = members[0]
        rep_body = _row_text(rows[rep_ri])
        rep_text = _normalize_unicode_text(rep_body)
        rep_pol = _polarity_signature(rep_body)
        confirmed = [rep_ri]
        for k in range(1, len(members)):
            mri = members[k]
            m_body = _row_text(rows[mri])
            # Polarity hard-block (defense-in-depth): an antonym/negation flip never corroborates.
            if _polarity_signature(m_body) != rep_pol:
                out.append(_singleton(mri))
                continue
            m_text = _normalize_unicode_text(m_body)
            fwd = entail_fn(rep_text, m_text)
            rev = entail_fn(m_text, rep_text) if fwd is True else None
            if fwd is True and rev is True:
                confirmed.append(mri)
            else:
                out.append(_singleton(mri))  # no verdict / one-way => keep, corrob 1
        out.append([cluster[0], cluster[1], confirmed])
    return out


def _apply_qualitative_nli_union(
    rows: list[dict[str, Any]],
    clusters: list[list[Any]],
    *,
    predict_fn=None,
) -> list[list[Any]]:
    """SECOND semantic-recall pass (I-deepfix-001 P4 recall rung-1, #1344): UNION lexical
    candidate clusters whose REPRESENTATIVE claim texts BIDIRECTIONALLY entail, reusing the
    SAME strict bidirectional-NLI machinery the NUMERIC path uses
    (``consolidation_nli.score_pairs``). The lexical greedy pass above is the cheap
    near-verbatim CANDIDATE stage (shingle-Jaccard 0.82); this is the NLI CONFIRM stage that
    RECALLS the same-claim paraphrases lexical Jaccard leaves as singletons — exactly the
    qualitative-corroboration blind spot most DRB-II rubric facts fall into (a non-numeric
    claim two independent sources assert in NON-overlapping wording, e.g. a Brynjolfsson-family
    and an OECD/WEF-family source both stating 'AI adoption is concentrated among large firms').

    ``clusters`` is the greedy list of ``[rep_shingles, rep_polarity, [member_ris]]`` triples
    (INCLUDING lexical singletons — a lexical singleton is exactly a claim in unique wording that
    the NLI can still recall onto a paraphrase). Returns the SAME triple shape with the merged
    member lists; the caller then emits only clusters with >= 2 members.

    REQUIRED HARD OVER-MERGE BLOCKERS (§-1.1 clinical-lethal if a false 'corroborated' renders;
    NONE optional — an NLI union raises verified_support_origin_count which P3 renders as a
    per-item 'corroborated' label, so a wrong union is a misstated-corroboration statement):
      (i)  bidirectional entailment stays STRICT — ``score_pairs`` emits an edge ONLY when
           A entails B AND B entails A (entailment the argmax in BOTH directions, no relaxed
           threshold). This structurally blocks three of the four over-merge canaries:
           HEDGED-vs-FLAT ('reduces' entails 'may reduce' but 'may reduce' does NOT entail
           'reduces' => one-directional => no union — merging them is itself a certainty
           distortion, From-May-to-Is 2606.07951), and SCOPE (manufacturing-vs-services) /
           CAUSAL-DIRECTION (A->B vs B->A) / TEMPORALITY (2020 vs 2026), where NEITHER
           direction entails.
      (ii) the ``_polarity_signature`` antonym/negation guard HARD-BLOCKS any opposite-polarity
           union even if the cross-encoder scored the pair entailing — an 'increased' vs
           'decreased' antonym can never corroborate (defense-in-depth: a model-independent
           deterministic block, not left to the NLI verdict alone).
      (iii) DIRECT-EDGE grouping, NOT transitive union-find (I-deepfix-001 P4 Codex fix, #1344):
           a redundant cluster joins a PRIMARY cluster ONLY when it DIRECTLY bidirectionally-
           entails THAT primary. Transitive union-find over NLI edges over-merges — A::B and
           B::C bidirectional edges would fold A/B/C into ONE basket even when A and C do NOT
           directly entail, inflating a basket head's corroboration_count with a claim that
           verifies only against a sibling span (the false-'corroborated' render chain §-1.1
           calls clinical-lethal). This mirrors the VALIDATED-SAFE direct-to-primary pattern the
           prose path already uses (``fact_dedup.py`` FIX-D, #1335), which replaced the same
           unsafe transitive merge. The numeric sibling path bounds this with value-bucketing;
           this is the qualitative path's equivalent precision guard.

    (iv) ALL-MEMBER SCORING (I-deepfix-001 C2, #1344 — "score ALL in-section member pairs,
         not just representatives"): the greedy candidate stage groups near-verbatim members
         into clusters, but two clusters that carry the SAME claim can have REPRESENTATIVES
         whose surface wording does not entail while a NON-representative member of one DOES
         entail a member of the other (a large paraphrase cluster only PARTIALLY unions on the
         rep alone). C2 links two clusters when ANY cross-cluster member pair bidirectionally
         entails (with matching per-member polarity), so a large paraphrase cluster FULLY
         unions. The representative-level edges are ALWAYS included as a floor, so this can
         NEVER union LESS than the pre-C2 rep-only behavior (monotone recall). All-member
         scoring is bounded by ``score_pairs``'s ``PG_CONSOLIDATION_NLI_MAX_PAIRS`` cap: over
         the cap it returns NO edges (safe UNDER-merge) and the rep-edge floor still applies,
         so a huge corpus degrades to rep-only, never regresses, never over-merges.

    KEEP-ALL / WEIGHT-ONLY (§-1.3): ONLY member-index lists are unioned (corroboration_count /
    independent_hosts rise); NO row is dropped, NO verify gate (strict_verify / the NLI
    entailment verifier / 4-role D8 / provenance / span-grounding) is touched. Deterministic +
    order-independent: ``score_pairs`` sorts its edges and the keep-first grouping attaches every
    redundant to the LOWEST-INDEX primary it DIRECTLY entails, so the merged grouping is identical
    for any worker count. ``predict_fn`` is the deterministic test-injection seam; production
    passes None => the real lazy cross-encoder.
    """
    from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
        score_pairs,
    )
    from src.polaris_graph.generator.fact_dedup import (  # noqa: PLC0415
        _polarity_signature,
    )

    n = len(clusters)
    if n < 2:
        return clusters

    # Cross-cluster DIRECT bidirectional-entailment links, in cluster-index space. Built from
    # TWO edge sets whose union is monotone over the pre-C2 rep-only behavior:
    #   (1) REP floor — representatives (lowest-row-index member of each cluster), always scored.
    #   (2) ALL-MEMBER (C2) — every member of every cluster, bounded by MAX_PAIRS.
    cluster_links: set[tuple[int, int]] = set()

    def _add_link(a: int, b: int) -> None:
        if a != b:
            cluster_links.add((a, b) if a < b else (b, a))

    # (1) Representative floor. Polarity carried on the cluster from the candidate stage (index 1).
    rep_texts = [_row_text(rows[cluster[2][0]]) for cluster in clusters]
    rep_polarity = [cluster[1] for cluster in clusters]
    for i, j in score_pairs(rep_texts, predict_fn=predict_fn):
        # (ii) polarity HARD-BLOCK: never link two mismatched-polarity representatives.
        if rep_polarity[i] == rep_polarity[j]:
            _add_link(i, j)

    # (2) ALL-MEMBER scoring (C2). Flatten every member of every cluster; score all member
    # pairs (bounded by MAX_PAIRS — over the cap score_pairs returns [] => rep floor only).
    member_texts: list[str] = []
    member_owner: list[int] = []
    member_polarity: list[tuple] = []
    for ci, cluster in enumerate(clusters):
        for ri in cluster[2]:
            body = _row_text(rows[ri])
            member_texts.append(body)
            member_owner.append(ci)
            member_polarity.append(_polarity_signature(body))
    for a, b in score_pairs(member_texts, predict_fn=predict_fn):
        ca, cb = member_owner[a], member_owner[b]
        if ca == cb:
            continue  # same cluster — already grouped by the candidate stage
        # (ii) polarity HARD-BLOCK at the MEMBER level (antonym / negation flip never links).
        if member_polarity[a] != member_polarity[b]:
            continue
        _add_link(ca, cb)

    if not cluster_links:
        return clusters

    # DIRECT-EDGE adjacency (NOT transitive union-find). I-deepfix-001 P4 Codex fix (#1344):
    # build the direct bidirectional-entailment neighbour set of each cluster, then group
    # KEEP-FIRST — a redundant cluster joins a primary ONLY when it carries a DIRECT link to
    # THAT primary. This is the exact direct-to-primary safe pattern ``fact_dedup.py`` FIX-D
    # (#1335) uses; it structurally blocks the A::B + B::C => {A,B,C} transitive over-merge
    # (C never joins A's basket unless C DIRECTLY links A), so a basket head's
    # corroboration_count can never be inflated by a claim that only entails a sibling.
    entails: dict[int, set[int]] = {}
    for i, j in cluster_links:
        entails.setdefault(i, set()).add(j)
        entails.setdefault(j, set()).add(i)

    # Keep-first over ascending cluster index => every basket's representative is its
    # lowest-index member (deterministic, order-independent for any worker count). A cluster
    # already consumed into an earlier primary is neither re-scanned nor re-emitted.
    out: list[list[Any]] = []
    consumed = [False] * n
    for i in range(n):
        if consumed[i]:
            continue
        merged_ris: list[int] = list(clusters[i][2])
        direct = entails.get(i, set())
        for j in range(i + 1, n):
            if consumed[j] or j not in direct:
                continue  # require a DIRECT mutual-entailment edge with THIS primary
            merged_ris.extend(clusters[j][2])
            consumed[j] = True
        consumed[i] = True
        # Primary keeps its own shingles/polarity as the representative signature; it now
        # carries every directly-entailing redundant cluster's row indices (keep-all).
        out.append([clusters[i][0], clusters[i][1], sorted(set(merged_ris))])
    return out


# ─────────────────────────────────────────────────────────────────────────
# 3a — WIDENED qualitative candidate NOMINATION helpers (F3, I-deepfix-001 #1369)
# ─────────────────────────────────────────────────────────────────────────
def _qual_nominate_enabled() -> bool:
    """``PG_FINDING_DEDUP_QUALITATIVE_NOMINATE`` kill switch (LAW VI). DEFAULT-ON: the
    token-containment candidate widening. The widened pass's NLI-CONFIRM only actually
    invokes the cross-encoder when an ``entail_fn`` is injected (tests) OR a cross-encoder
    NLI path is already active (``_consolidation_nli_enabled`` / ``_finding_dedup_nli_enabled``),
    so a default run with every NLI flag OFF is BYTE-IDENTICAL (no model load, no merge) even
    with this flag ON — the widening rides the SAME resident cross-encoder the run slate already
    loads. Set to ``0`` to force the pre-F3 behavior even under the slate."""
    return os.getenv(_QUAL_NOMINATE_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _qual_nominate_containment() -> float:
    """The asymmetric content-token containment threshold in (0, 1]. Malformed / out-of-range
    => the default 0.60 (logged once, never raised — a typo must not crash a paid run)."""
    raw = os.environ.get(_QUAL_NOMINATE_CONTAINMENT_ENV, "").strip() or _QUAL_NOMINATE_CONTAINMENT_DEFAULT
    try:
        value = float(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[finding_dedup] %s=%r not a float; using default %s",
            _QUAL_NOMINATE_CONTAINMENT_ENV, raw, _QUAL_NOMINATE_CONTAINMENT_DEFAULT,
        )
        return float(_QUAL_NOMINATE_CONTAINMENT_DEFAULT)
    if not (0.0 < value <= 1.0):
        logger.warning(
            "[finding_dedup] %s=%s out of (0,1]; using default %s",
            _QUAL_NOMINATE_CONTAINMENT_ENV, value, _QUAL_NOMINATE_CONTAINMENT_DEFAULT,
        )
        return float(_QUAL_NOMINATE_CONTAINMENT_DEFAULT)
    return value


def _qual_nominate_max_pairs() -> int:
    """The O(n^2) nominated-pair cap (LAW VI). Over the cap the widened pass SKIPS
    (under-merge, §-1.3 keep-all — never drops a corroborator). Malformed => default."""
    raw = os.environ.get(_QUAL_NOMINATE_MAX_PAIRS_ENV, "").strip() or _QUAL_NOMINATE_MAX_PAIRS_DEFAULT
    try:
        value = int(raw)
    except (ValueError, TypeError):
        logger.warning(
            "[finding_dedup] %s=%r not an int; using default %s",
            _QUAL_NOMINATE_MAX_PAIRS_ENV, raw, _QUAL_NOMINATE_MAX_PAIRS_DEFAULT,
        )
        return int(_QUAL_NOMINATE_MAX_PAIRS_DEFAULT)
    return max(1, value)


def _content_tokens(text: str) -> frozenset:
    """The content-word token SET of a claim body: lowercased, citation-tokens stripped,
    alnum word-tokenized, stopwords dropped. Reuses fact_dedup's citation/stopword/word
    predicates (lazy import — the same defer-to-dodge-cycles discipline this module uses) so
    the normalization is byte-consistent with the qualitative shingle/key path."""
    from src.polaris_graph.generator.fact_dedup import (  # noqa: PLC0415
        _CITATION_TOKEN_RE,
        _STOPWORDS,
        _WORD_RE,
    )

    low = _CITATION_TOKEN_RE.sub(" ", (text or "").lower())
    return frozenset(w for w in _WORD_RE.findall(low) if w not in _STOPWORDS)


def _token_containment(a: frozenset, b: frozenset) -> float:
    """ASYMMETRIC content-token containment: ``|a ∩ b| / min(|a|, |b|)``. Unlike the
    SYMMETRIC Jaccard (``|a ∩ b| / |a ∪ b|``) the near-verbatim greedy pass uses, containment
    stays HIGH when one claim is a paraphrase/expansion of the other (very different lengths,
    so Jaccard is low) as long as the SHORTER token set is largely contained in the longer —
    exactly the cross-document paraphrase the near-verbatim gate misses. Returns 0.0 when
    either set is empty (never nominates on emptiness)."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / float(min(len(a), len(b)))


def _apply_qualitative_containment_nli_grouping(
    rows: list[dict[str, Any]],
    clusters: list[list[Any]],
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
    telemetry: Optional[dict[str, Any]] = None,
) -> list[list[Any]]:
    """F3-3a (I-deepfix-001 #1369) — WIDEN the qualitative candidate NOMINATION beyond lexical
    near-verbatim, keeping the STRICT bidirectional-NLI as the SOLE merge DECISION.

    ``clusters`` is the greedy list of ``[rep_shingles, rep_polarity, [member_ris]]`` triples
    (INCLUDING lexical singletons). This pass:

      1. NOMINATES cross-cluster candidate pairs (i < j) by ASYMMETRIC content-token
         CONTAINMENT of the two representatives (``_token_containment`` >= the configured
         threshold), with the POLARITY hard-block excluding a mismatched-polarity pair from
         nomination entirely. Token-containment catches a paraphrase/expansion pair whose
         surface Jaccard falls below the 0.82 near-verbatim gate — the exact recall the greedy
         stage leaves as singletons. This is ONLY a recall-oriented candidate BLOCKER; a
         nomination is NEVER a merge.
      2. CONFIRMS each nominated pair through the SAME strict bidirectional-entailment gate the
         keystone uses (``consolidation_nli.entails_directional`` in BOTH directions returning
         True). One-direction-only (extension), contradiction, or an infra ``None`` on either
         direction => NO merge (fail-closed to a singleton; the run CONTINUES — ``entails_directional``
         never raises). The polarity guard is applied AGAIN at confirm (defense-in-depth).
      3. MERGES confirmed pairs via DIRECT-EDGE keep-first grouping (NOT transitive union-find),
         the exact safe direct-to-primary pattern ``_apply_finding_dedup_nli_grouping`` /
         ``fact_dedup`` FIX-D use — so a basket head's corroboration_count can never be inflated
         by a claim that only entails a SIBLING (the false-'corroborated' render chain §-1.1 calls
         clinical-lethal).

    KEEP-ALL / WEIGHT-ONLY (§-1.3): ONLY member-index lists are unioned; NO row is dropped, NO
    verify gate is touched. BOUNDED: over ``_qual_nominate_max_pairs`` NOMINATED pairs the pass
    SKIPS (an under-merge, keep-all). Because only containment-passing pairs are ever NLI-scored,
    this RECALLS even in the over-cap regime where the all-pairs keystone skips entirely — the
    drb_72 large-corpus scenario. Deterministic + order-independent (ascending cluster index,
    keep-first, sorted edges). ``entail_fn(premise, hypothesis) -> True/False/None`` is the
    deterministic test-injection seam; production passes None => the lazy resident
    ``entails_directional`` (the SAME cross-encoder the consolidation leg already loads — ZERO
    new model, ZERO paid spend)."""
    from src.polaris_graph.generator.fact_dedup import (  # noqa: PLC0415
        _polarity_signature,
    )

    n = len(clusters)
    if n < 2:
        return clusters

    rep_texts = [_row_text(rows[cluster[2][0]]) for cluster in clusters]
    rep_polarity = [cluster[1] for cluster in clusters]
    rep_tokens = [_content_tokens(t) for t in rep_texts]

    # (1) NOMINATE: containment-passing, polarity-matched cross-cluster pairs. A representative
    # with too few content tokens is not a reliable containment signal (false-positive guard).
    threshold = _qual_nominate_containment()
    nominated: list[tuple[int, int]] = []
    for i in range(n):
        ti = rep_tokens[i]
        if len(ti) < _QUAL_NOMINATE_MIN_TOKENS:
            continue
        for j in range(i + 1, n):
            tj = rep_tokens[j]
            if len(tj) < _QUAL_NOMINATE_MIN_TOKENS:
                continue
            if rep_polarity[i] != rep_polarity[j]:
                continue  # polarity hard-block: never nominate an opposite-polarity pair
            if _token_containment(ti, tj) >= threshold:
                nominated.append((i, j))
    if not nominated:
        if telemetry is not None:
            telemetry["nominated_pairs"] = 0
            telemetry["containment_merges"] = 0
        return clusters
    max_pairs = _qual_nominate_max_pairs()
    if len(nominated) > max_pairs:
        logger.warning(
            "[finding_dedup] F3-3a: %d nominated candidate pairs exceeds %s=%d — SKIPPING the "
            "containment-NLI widening for this section (clusters pass through UNMERGED; no basket "
            "dropped, §-1.3). Raise %s to score more pairs.",
            len(nominated), _QUAL_NOMINATE_MAX_PAIRS_ENV, max_pairs, _QUAL_NOMINATE_MAX_PAIRS_ENV,
        )
        if telemetry is not None:
            telemetry["nominated_pairs"] = len(nominated)
            telemetry["containment_merges"] = 0
            telemetry["over_cap"] = True
        return clusters

    # (2) CONFIRM: the strict bidirectional-entailment gate is the SOLE merge decision.
    if entail_fn is None:
        from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
            entails_directional,
        )
        entail_fn = entails_directional

    edges: list[tuple[int, int]] = []
    for i, j in nominated:
        # Defense-in-depth: re-assert the polarity hard-block on the actual member bodies
        # (mirrors _apply_finding_dedup_nli_grouping's model-independent guard).
        if _polarity_signature(rep_texts[i]) != _polarity_signature(rep_texts[j]):
            continue
        fwd = entail_fn(rep_texts[i], rep_texts[j])
        if fwd is not True:
            continue  # one-direction / contradiction / infra None => no edge (fail-closed)
        rev = entail_fn(rep_texts[j], rep_texts[i])
        if rev is not True:
            continue
        edges.append((i, j))
    edges.sort()
    if telemetry is not None:
        telemetry["nominated_pairs"] = len(nominated)
    if not edges:
        if telemetry is not None:
            telemetry["containment_merges"] = 0
        return clusters

    # (3) DIRECT-EDGE keep-first grouping (NOT transitive union-find).
    entails: dict[int, set] = {}
    for i, j in edges:
        entails.setdefault(i, set()).add(j)
        entails.setdefault(j, set()).add(i)
    out: list[list[Any]] = []
    consumed = [False] * n
    for i in range(n):
        if consumed[i]:
            continue
        merged_ris: list[int] = list(clusters[i][2])
        direct = entails.get(i, set())
        for j in range(i + 1, n):
            if consumed[j] or j not in direct:
                continue  # require a DIRECT mutual-entailment edge with THIS primary
            merged_ris.extend(clusters[j][2])
            consumed[j] = True
        consumed[i] = True
        out.append([clusters[i][0], clusters[i][1], sorted(set(merged_ris))])
    if telemetry is not None:
        telemetry["containment_merges"] = n - len(out)
    return out


def _apply_finding_dedup_nli_grouping(
    rows: list[dict[str, Any]],
    clusters: list[list[Any]],
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
    telemetry: Optional[dict[str, Any]] = None,
) -> list[list[Any]]:
    """PG_FINDING_DEDUP_NLI (I-deepfix-001 Wave 1b, #1344; REAL_PLAN_2026 coverage_fix item 1):
    union lexical qualitative candidate clusters whose REPRESENTATIVE claim texts STRICTLY
    BIDIRECTIONALLY entail into ONE corroboration basket.

    ``clusters`` is the greedy list of ``[rep_shingles, rep_polarity, [member_ris]]`` triples
    (INCLUDING lexical singletons — a lexical singleton is a claim in unique wording the NLI can
    still recall onto a paraphrase). Returns the SAME triple shape with the merged member lists;
    the caller then emits only clusters with >= 2 members.

    MERGE PREDICATE (strict bidirectional, 3-state — §-1.1 clinical: a false 'corroborated' is
    lethal, so NONE of these blockers is optional):
      * bidirectional entails (BOTH directions ``True`` via ``entails_directional`` — entailment
        the strict ``_entails`` argmax by margin) => MERGE.
      * one-direction-only (exactly one direction ``True``) => an EXTENSION relation => do NOT
        merge (merging a hedged<->flat pair is a certainty distortion, From-May-to-Is).
      * contradiction (neither direction entails) => a durable relation => do NOT merge.
      * infra ``None`` on EITHER direction (empty text / cross-encoder unavailable) => NO merge,
        a FAIL-CLOSED singleton; the run CONTINUES (``entails_directional`` never raises).
      * POLARITY hard-block (defense-in-depth): two mismatched-polarity representatives NEVER
        link even if the scorer returns bidirectional-entailing (a model-independent guard) —
        such pairs are excluded from scoring entirely.

    DIRECT-EDGE keep-first grouping (NOT transitive union-find): a redundant cluster joins a
    PRIMARY only when it DIRECTLY bidirectionally entails THAT primary — the same safe
    direct-to-primary pattern ``_apply_qualitative_nli_union`` + ``fact_dedup`` FIX-D use, so a
    basket head's corroboration_count can never be inflated by a claim that only entails a
    sibling. Deterministic + order-independent (ascending cluster index, keep-first).

    KEEP-ALL / WEIGHT-ONLY (§-1.3): ONLY member-index lists are unioned; NO row is dropped, NO
    verify gate (strict_verify / the NLI entailment verifier / 4-role D8 / provenance /
    span-grounding) is touched. The extension / contradiction relations are surfaced downstream
    in Wave 2 (cross_source_synthesis); this build's contribution is the MERGE decision plus
    leaving non-bidirectional pairs un-merged. ``entail_fn(premise, hypothesis) -> True/False/None``
    is the deterministic test-injection seam; production passes None => the lazy
    ``consolidation_nli.entails_directional``. That REUSES the resident cross-encoder if the
    consolidation leg already loaded it (master ``PG_CONSOLIDATION_NLI`` ON); with the keystone ON
    but the master OFF, the keystone itself triggers the ONE-TIME local cross-encoder load (still
    the local NLI model — no OpenRouter / paid-API spend, but honestly NOT free of that first load).
    """
    n = len(clusters)
    if n < 2:
        return clusters

    rep_texts = [_row_text(rows[cluster[2][0]]) for cluster in clusters]
    rep_polarity = [cluster[1] for cluster in clusters]
    # I-deepfix-001 Wave-3a (#1344): ADDITIVE activation telemetry (never changes a merge). A one-element
    # mutable flag is set when the cross-encoder returns None on a pair of NON-empty representatives — the
    # DEGRADE sentinel (infra fault: model unavailable / OOM CPU-degrade failed), distinct from a genuine
    # empty-text None. Only surfaced through the ``telemetry`` out-param; discarded (behavior-inert) when
    # the caller passes no dict (the deterministic-stub test path).
    rep_nonempty = [bool(t and t.strip()) for t in rep_texts]
    _degraded_flag = [False]

    # Candidate cluster-index pairs (i < j). The POLARITY hard-block excludes a
    # mismatched-polarity pair from scoring entirely (it can never link — defense in depth).
    pairs = [
        (i, j)
        for i in range(n)
        for j in range(i + 1, n)
        if rep_polarity[i] == rep_polarity[j]
    ]
    if not pairs:
        return clusters
    max_pairs = _finding_dedup_nli_max_pairs()
    if len(pairs) > max_pairs:
        logger.warning(
            "[finding_dedup] PG_FINDING_DEDUP_NLI: %d candidate pairs exceeds %s=%d — SKIPPING "
            "the directional qualitative grouping for this section (clusters pass through "
            "UNMERGED; no basket dropped, §-1.3). Raise %s to score more pairs.",
            len(pairs), _FINDING_DEDUP_NLI_MAX_PAIRS_ENV, max_pairs,
            _FINDING_DEDUP_NLI_MAX_PAIRS_ENV,
        )
        return clusters

    # Production scorer: the 3-state directional primitive. ``entails_directional`` NEVER raises —
    # an infra fault returns None (fail-closed) — so a bounded thread pool over the pairs can never
    # abort the run.
    _injected = entail_fn is not None
    if entail_fn is None:
        from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
            entails_directional,
        )
        entail_fn = entails_directional

    def _bidirectional(pair: tuple[int, int]) -> Optional[tuple[int, int]]:
        i, j = pair
        fwd = entail_fn(rep_texts[i], rep_texts[j])
        # ADDITIVE degrade observation (Wave-3a #1344): a None verdict on two NON-empty texts means the
        # cross-encoder was unavailable (infra fault) — record it WITHOUT changing the fail-closed edge
        # decision below. Thread-safe: a single-element list write is atomic under the GIL.
        if fwd is None and rep_nonempty[i] and rep_nonempty[j]:
            _degraded_flag[0] = True
        if fwd is not True:
            return None  # one-direction / contradiction / None => no edge (fail-closed)
        rev = entail_fn(rep_texts[j], rep_texts[i])
        if rev is None and rep_nonempty[i] and rep_nonempty[j]:
            _degraded_flag[0] = True
        if rev is not True:
            return None
        return (i, j)

    # Wall-clock bound (LAW VI; mirrors the consolidation W04 wall): a CPU-degraded cross-encoder
    # would otherwise run-pin the box across up to 2*MAX_PAIRS single-item forwards. On the
    # deadline we STOP scoring further pairs and keep the edges gathered so far — an UNDER-merge
    # only (§-1.3-safe: keeps MORE/equal baskets, drops no corroborator). <=0 disables the wall.
    wall = _finding_dedup_nli_wall_seconds()
    deadline = (time.monotonic() + wall) if wall > 0 else None

    def _deadline_passed() -> bool:
        return deadline is not None and time.monotonic() > deadline

    # Serial when a stub ``entail_fn`` is injected (deterministic tests) OR a single worker;
    # bounded-parallel in production. Either way the edge set is gathered then SORTED before
    # grouping, so the result is identical for any worker count (order-independent).
    edges: list[tuple[int, int]] = []
    truncated = False
    workers = 1 if _injected else min(_finding_dedup_nli_workers(), len(pairs))
    if workers <= 1:
        for pair in pairs:
            if _deadline_passed():
                truncated = True
                break
            edge = _bidirectional(pair)
            if edge is not None:
                edges.append(edge)
    else:
        # Manage the pool MANUALLY (not ``with``) so the wall can return the partial edge set
        # without ``__exit__``'s shutdown(wait=True) blocking on a wedged chunk.
        pool = ThreadPoolExecutor(max_workers=workers)
        try:
            futures = {pool.submit(_bidirectional, p) for p in pairs}
            pending = set(futures)
            while pending:
                remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
                if remaining is not None and remaining <= 0:
                    truncated = True
                    break
                done, pending = futures_wait(
                    pending, timeout=remaining, return_when=FIRST_COMPLETED,
                )
                if not done:
                    truncated = True  # wall elapsed mid-flight
                    break
                for fut in done:
                    edge = fut.result()  # _bidirectional never raises (entails_directional None-safe)
                    if edge is not None:
                        edges.append(edge)
            if truncated:
                for fut in list(pending):
                    if fut.done() and not fut.cancelled():
                        edge = fut.result()
                        if edge is not None:
                            edges.append(edge)
        finally:
            # NON-BLOCKING teardown so a wedged chunk cannot delay the partial return.
            pool.shutdown(wait=False, cancel_futures=True)
    if truncated:
        logger.warning(
            "[finding_dedup] PG_FINDING_DEDUP_NLI: scoring wall (%ss) elapsed — returning the "
            "partial edge set (UNDER-merges only; no basket dropped, §-1.3). Raise %s to score more.",
            wall, _FINDING_DEDUP_NLI_WALL_SECONDS_ENV,
        )

    edges.sort()
    # Wave-3a (#1344): surface the degrade + wall-truncation observations now that scoring is done. The
    # directional_merges count is finalized at the merged-return below (0 on the no-edge path). Behavior-
    # inert when ``telemetry`` is None (the stub-test path); populated only for the run-logger caller.
    if telemetry is not None:
        telemetry["degraded"] = bool(_degraded_flag[0])
        telemetry["wall_truncated"] = bool(truncated)
        telemetry["directional_merges"] = 0
    if not edges:
        return clusters

    # DIRECT-EDGE adjacency (NOT transitive union-find): only a DIRECT mutual-entailment edge
    # links two clusters, so A::B + B::C can never fold C into A's basket via B.
    entails: dict[int, set[int]] = {}
    for i, j in edges:
        entails.setdefault(i, set()).add(j)
        entails.setdefault(j, set()).add(i)

    # Keep-first over ascending cluster index => every basket's representative is its lowest-index
    # member (deterministic, order-independent). A cluster consumed into an earlier primary is
    # neither re-scanned nor re-emitted.
    out: list[list[Any]] = []
    consumed = [False] * n
    for i in range(n):
        if consumed[i]:
            continue
        merged_ris: list[int] = list(clusters[i][2])
        direct = entails.get(i, set())
        for j in range(i + 1, n):
            if consumed[j] or j not in direct:
                continue  # require a DIRECT mutual-entailment edge with THIS primary
            merged_ris.extend(clusters[j][2])
            consumed[j] = True
        consumed[i] = True
        out.append([clusters[i][0], clusters[i][1], sorted(set(merged_ris))])
    # Wave-3a (#1344): each consumed cluster reduces the output count by one, so ``n - len(out)`` is the
    # number of DIRECTIONAL merges this pass performed (behavior-inert when ``telemetry`` is None).
    if telemetry is not None:
        telemetry["directional_merges"] = n - len(out)
    return out


# ── Chrome-dominant body guard for qualitative candidates — S2/S3 re-pass P0-2 (real-run fix)
# A banked drb_72 S3 replay proved the NLI-confirm alone does NOT dissolve the fake corr=19/12
# qualitative mega-baskets: the members were CHROME non-sources (markdown nav menus
# "* [Summary](url)", bare-URL link lists, javascript:void, a %PDF xref) whose structurally-
# identical formatting the cross-encoder SPURIOUSLY entails. §-1.3.1 (chrome IS deletable) +
# §-1.3 keep-all: the ROW still flows through (keep-all); it is only excluded from qual
# CLUSTERING so it can never seed/join a corroboration basket. General/structural, fail-open.
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]*\)")
_URL_TOKEN_RE = re.compile(r"https?://\S+")
_QUAL_CHROME_LINE_RE = re.compile(
    r"^[\*\-•·]?\s*(?:\[[^\]]*\]\([^)]*\)|\(https?://|https?://)", re.IGNORECASE
)
_QUAL_CHROME_GUARD_ENV = "PG_QUAL_CHROME_GUARD"


def _qual_chrome_guard_enabled() -> bool:
    """``PG_QUAL_CHROME_GUARD`` kill switch (LAW VI, DEFAULT-ON, P0-2 real-run fix). OFF =>
    byte-identical legacy (a chrome/nav/URL/binary body may still seed a qualitative basket)."""
    return os.getenv(_QUAL_CHROME_GUARD_ENV, "1").strip().lower() not in (
        "", "0", "false", "off", "no",
    )


def _body_is_chrome_dominant(body: str) -> bool:
    """True iff the body is dominated by nav/link-list / URL / binary chrome and carries no real
    propositional claim, so it must NOT seed/join a qualitative corroboration basket. Signals
    (any one): (a) >= 3 markdown-links / bare-URLs with < 30 real prose words outside them
    (a nav / link dump); (b) a PDF xref / javascript:void marker; (c) >= 60% of the body's
    non-empty lines begin with a markdown-link / bare-URL (a nav menu). Pure/deterministic,
    fail-open (empty => False). §-1.3-safe: only excludes from CLUSTERING, never drops the row."""
    if not body:
        return False
    low = body.lower()
    if "%pdf" in low or "javascript:void" in low or "endobj" in low or "flatedecode" in low:
        return True
    # S2/S3 re-pass iter-3: garbled byte-stream body (a mangled PDF / flate stream rendered as
    # text) whose %pdf/endobj markers were lost, so the literals above miss it. Signal: almost
    # none of its whitespace tokens are word-like (>=2 ASCII letters) AND its alphabetic-char
    # fraction is low. Empirically separated on drb_72: real prose scores >=0.80 word-like /
    # >=0.86 alpha, this gibberish scores ~0.0 / ~0.45. Excludes from CLUSTERING ONLY (never
    # drops the row): a real off-topic paper (word-like ~0.81) is untouched and a genuine dense
    # source merely falls to a singleton basket => fail-open / §-1.3-safe, never inflates a count.
    head = body[:800]
    toks = head.split()
    if len(toks) >= 20:
        wordlike = sum(1 for t in toks if re.fullmatch(r"[A-Za-z]{2,}[.,;:]?", t))
        nonspace = [c for c in head if not c.isspace()]
        alpha_ratio = (sum(1 for c in nonspace if c.isalpha()) / len(nonspace)) if nonspace else 1.0
        if (wordlike / len(toks)) < 0.10 and alpha_ratio < 0.65:
            return True
    # A fetch-navigation shell ("Navigated to <title> page (https://...)") carries only page-
    # title chrome, no propositional body => a failed/again-chrome fetch, never a claim. Same
    # exclude-from-CLUSTERING-only contract, so refetch triplets can no longer corroborate.
    if re.match(r"navigated to .{0,300}\bpage\b\s*\(https?://", body.strip(), re.I | re.S):
        return True
    md = len(_MD_LINK_RE.findall(body))
    urls = len(_URL_TOKEN_RE.findall(body))
    if (md + urls) >= 1:
        prose = _URL_TOKEN_RE.sub(" ", _MD_LINK_RE.sub(" ", body))
        prose_words = len(re.findall(r"[A-Za-z]{3,}", prose))
        # A lone markdown-link / bare-URL fragment with almost no prose (< 8 words) is chrome
        # (e.g. "[ ](https://blog.hospitalmedicine.org/)"); a dense link dump (>=3 links) with
        # < 30 prose words is a nav / link list. Both carry no propositional claim.
        # S2/S3 re-pass iter-3: link-density clause. A NAV DUMP has >=50% of its chars
        # inside markdown-links / bare-URLs AND very few prose words per link. Empirically
        # separated on drb_72: real prose scores linkfrac <= 0.34 with >= 14 prose words per
        # link; nav pages score linkfrac 0.66-0.87 with < 4 words per link. Exclude from
        # CLUSTERING only (never drops the row) => fail-open / §-1.3-safe.
        linkfrac = (len(body) - len(prose)) / max(1, len(body))
        if (
            prose_words < 8
            or ((md + urls) >= 3 and prose_words < 30)
            or ((md + urls) >= 3 and linkfrac >= 0.5 and prose_words < (md + urls) * 8)
        ):
            return True
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if len(lines) >= 3:
        junk = sum(1 for ln in lines if _QUAL_CHROME_LINE_RE.match(ln))
        if junk >= max(2, int(0.6 * len(lines))):
            return True
    return False


def _build_qualitative_groups(
    rows: list[dict[str, Any]],
    row_has_finding: list[bool],
    dropped: set[int],
    *,
    threshold: float,
    nominate_entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
) -> dict[tuple, list[int]]:
    """Cluster the NO-numeric-finding (qualitative) rows that assert the SAME
    claim into corroboration baskets. Returns ``{qualitative_key: [row_idx, ...]}``
    for every cluster with >= 2 members, where ``qualitative_key`` is the
    all-STRING tuple ``("__qual__", <rep_evidence_id>, <signature_token>)`` — a
    NON-NUMERIC finding_key by construction (the D1 dice's qualitative-basket
    requirement). Singleton qualitative rows are NOT emitted (no basket).

    Conservative greedy single-pass clustering: each candidate joins the FIRST
    existing cluster whose representative shingle set is within ``threshold`` AND
    whose polarity signature matches; else it opens a new cluster. Deterministic +
    order-stable (candidates are visited in ascending row order). Two DIFFERENT
    qualitative claims never merge (low shingle overlap OR a polarity mismatch).

    F3-3a (I-deepfix-001 #1369): after the near-verbatim greedy pass + the existing
    NLI unions, a WIDENED candidate-NOMINATION pass
    (``_apply_qualitative_containment_nli_grouping``) nominates additional cross-cluster
    pairs by ASYMMETRIC token-containment (catching paraphrases the greedy Jaccard 0.82
    gate misses) and CONFIRMS them through the SAME strict bidirectional-NLI gate — the
    NLI stays the SOLE merge decision. ``nominate_entail_fn`` is the deterministic
    test-injection seam for that pass (production passes None => the lazy resident
    cross-encoder). The widened pass is a no-op unless its kill switch is ON AND either
    a cross-encoder NLI path is already active OR ``nominate_entail_fn`` is injected — so a
    default run with every NLI flag OFF stays byte-identical.
    """
    from src.polaris_graph.generator.fact_dedup import (  # noqa: PLC0415
        _PROSE_NO_MATCH,
        _jaccard,
        _polarity_signature,
        _prose_shingles,
    )
    from src.polaris_graph.generator.chrome_furniture_screen import (  # noqa: PLC0415
        is_furniture_dominant,
    )

    # Collect the qualitative candidates (no numeric finding, not dropped, long
    # enough to shingle) in ascending row order for deterministic greedy merge.
    candidates: list[tuple[int, frozenset, tuple]] = []
    for ri in range(len(rows)):
        if ri in dropped or row_has_finding[ri]:
            continue
        body = _row_text(rows[ri])
        # Chrome guard: a furniture-dominant body (cookie/byline/ToC back-matter) carries no real
        # claim -> never seeds/joins a basket. Row still KEPT (keep-all); only excluded from clustering.
        if is_furniture_dominant(body):
            continue
        # P0-2 real-run fix: a nav/link-list / bare-URL / javascript:void / %PDF-xref body is chrome
        # the cross-encoder spuriously entails into a fake corroboration mega-basket. Exclude it from
        # CLUSTERING (still KEPT, keep-all). is_furniture_dominant missed these markdown-nav bodies.
        if _qual_chrome_guard_enabled() and _body_is_chrome_dominant(body):
            continue
        # Fix 7 (Fable): letter-spaced extraction garbage ("W e i n v e s t i g a t e ...") is
        # unreadable to the NLI cross-encoder — it spuriously entailed unrelated claims into a
        # false qualitative basket (the Eloundou huggingface abstract + OUP article merge).
        # Exclude the degraded row from CLUSTERING (still KEPT as its own keep-all row).
        if _is_extraction_degraded(body):
            continue
        # P0-1(c)/P1-5 (iter-5, Fable): a row with NO mergeable CLAIM sentence (a nav-link dump /
        # catalog / bibliography / license-only body — basket-321 wustl profile-nav) can never
        # anchor a same-claim merge; exclude it from CLUSTERING (still KEPT as its own keep-all
        # singleton row). This is the qualitative sibling of the numeric `_sentence_mergeable`
        # screen, so a non-claim heading/nav can't byte-identical-cluster on ANY path.
        if _qual_mergeable_screen_enabled() and not _row_has_mergeable_claim(rows[ri]):
            continue
        shingles = _prose_shingles(body)
        if shingles is _PROSE_NO_MATCH or not shingles:
            continue  # too short to cluster (false-positive guard) — safe singleton
        candidates.append((ri, shingles, _polarity_signature(body)))

    # Greedy clustering. Each cluster = [rep_shingles, rep_polarity, [member_ris]].
    clusters: list[list[Any]] = []
    for ri, shingles, polarity in candidates:
        placed = False
        for cluster in clusters:
            if cluster[1] != polarity:
                continue  # polarity guard: never merge an opposite-polarity claim
            if _jaccard(shingles, cluster[0]) >= threshold:
                cluster[2].append(ri)
                placed = True
                break
        if not placed:
            clusters.append([shingles, polarity, [ri]])

    # P0-2 (S2/S3 re-pass): the greedy shingle-Jaccard pass above NOMINATES near-verbatim
    # candidates only — it must NOT mint a multi-member basket on lexical overlap ALONE. Citation
    # / reference-list lines share so much formatting vocabulary that a batch of UNRELATED lines
    # greedily clustered into a fake corrob=18 mega-basket (§-1.1 clinical-lethal misstated
    # corroboration). Every within-cluster member is now CONFIRMED against the rep by the SAME
    # strict bidirectional NLI the numeric path uses; an unconfirmed member (or NLI unavailable)
    # splits to a singleton (corroboration stays 1). Runs BEFORE the union passes so a genuine
    # paraphrase can still RE-merge downstream. Kill switch OFF => byte-identical legacy greedy.
    if _qual_merge_requires_nli_enabled() and any(len(c[2]) >= 2 for c in clusters):
        nli_active = (
            nominate_entail_fn is not None
            or _consolidation_nli_enabled()
            or _finding_dedup_nli_enabled()
            or _qualitative_nli_enabled()
        )
        if nli_active:
            clusters = _confirm_greedy_clusters_via_nli(
                rows, clusters, entail_fn=nominate_entail_fn,
            )
        else:
            # No NLI path active this run => a greedy multi-member cluster has no verdict =>
            # explode to singletons (corroboration stays 1; never fake corroboration).
            exploded: list[list[Any]] = []
            for c in clusters:
                if len(c[2]) < 2:
                    exploded.append(c)
                    continue
                for ri in c[2]:
                    body = _row_text(rows[ri])
                    exploded.append([_prose_shingles(body), _polarity_signature(body), [ri]])
            clusters = exploded

    # SECOND semantic-recall pass (I-deepfix-001 P4 recall rung-1, #1344). The greedy pass
    # above is the cheap near-verbatim CANDIDATE stage; when BOTH the master
    # ``PG_CONSOLIDATION_NLI`` gate and the ``PG_CONSOLIDATION_NLI_QUALITATIVE`` sub-flag are
    # ON, union candidate clusters (INCLUDING lexical singletons) whose representatives
    # BIDIRECTIONALLY entail — the SAME strict NLI the numeric baskets get, extended to the
    # qualitative path (the §-1.3 CONSOLIDATE-qualitative-too climb). OFF (either flag) =>
    # byte-identical lexical-only behavior. The union only GROWS member lists (keep-all,
    # weight-only); the four over-merge canaries (SCOPE / CAUSAL-DIRECTION / TEMPORALITY /
    # HEDGED-vs-FLAT) are hard-blocked by the strict bidirectional requirement + the polarity
    # guard inside ``_apply_qualitative_nli_union``.
    # When the keystone is OFF this runs UNGUARDED => byte-identical legacy behavior (incl. the
    # legacy union's raise-on-non-OOM-failure). When the keystone is ALSO ON (the Wave-3 slate
    # config) the legacy union runs FIRST and would RAISE on a non-OOM model fault BEFORE the
    # fail-closed keystone below — aborting the run at the dedup step. So under the keystone regime
    # ONLY, GUARD it: degrade a legacy raise to a §-1.3-safe under-merge (logged loud, never
    # except:pass) and let the keystone's own None path yield singletons if the model is truly
    # dead. This changes NOTHING when the keystone is OFF (byte-identical).
    if _qualitative_nli_enabled():
        if _finding_dedup_nli_enabled():
            try:
                clusters = _apply_qualitative_nli_union(rows, clusters)
            except Exception as exc:  # noqa: BLE001 — keystone regime: degrade to under-merge (§-1.3-safe)
                logger.warning(
                    "[finding_dedup] PG_CONSOLIDATION_NLI_QUALITATIVE union failed (%s); "
                    "continuing UNMERGED (under-merge, §-1.3) — the PG_FINDING_DEDUP_NLI "
                    "fail-closed grouping still runs.", exc,
                )
        else:
            clusters = _apply_qualitative_nli_union(rows, clusters)

    # THIRD (directional) semantic-recall pass — the coverage-fix keystone (I-deepfix-001
    # Wave 1b, #1344; PG_FINDING_DEDUP_NLI, default-OFF). Unions candidate clusters (INCLUDING
    # lexical singletons) whose representatives STRICTLY BIDIRECTIONALLY entail, using the
    # 3-state ``consolidation_nli.entails_directional`` primitive so an infra fault degrades to a
    # FAIL-CLOSED singleton and the run CONTINUES (the score_pairs path raises on a non-OOM
    # failure — hence the guard above under the both-flags-ON regime). one-direction => EXTENSION
    # (no merge); contradiction => no merge; polarity hard-block defense-in-depth. OFF =>
    # byte-identical (this call is skipped). Additive / keep-all with the guarded pass above.
    if _finding_dedup_nli_enabled():
        _nli_telemetry: dict[str, Any] = {}
        clusters = _apply_finding_dedup_nli_grouping(
            rows, clusters, telemetry=_nli_telemetry,
        )
        # I-deepfix-001 Wave-3a (#1344): the finding-dedup-NLI ACTIVATION fire marker. Emitted ONLY under
        # PG_FINDING_DEDUP_NLI (this branch is skipped when the flag is OFF => the run_log carries no
        # ``[activation]`` line => OFF byte-identical). Structural presence + count, never a threshold
        # (§-1.3): directional_merges=0 with the flag ON on eligible input is itself the eligible-yet-zero
        # signal the activation canary reads; degraded=true is the cross-encoder-fallback signal;
        # wall_truncated=true is the scoring-wall under-merge signal.
        logger.info(
            "[activation] finding_dedup_nli: invoked directional_merges=%d degraded=%s wall_truncated=%s",
            int(_nli_telemetry.get("directional_merges", 0)),
            bool(_nli_telemetry.get("degraded", False)),
            bool(_nli_telemetry.get("wall_truncated", False)),
        )

    # FOURTH pass — F3-3a WIDENED candidate NOMINATION (I-deepfix-001 #1369). Nominate cross-cluster
    # pairs by ASYMMETRIC token-containment (recalls paraphrases the near-verbatim greedy gate + the
    # rep-only keystone leave as singletons, INCLUDING in the over-cap regime where the all-pairs
    # passes above SKIP) and CONFIRM them through the SAME strict bidirectional-NLI gate — the NLI
    # stays the SOLE merge decision (token-containment is only a candidate blocker). Runs ONLY when
    # the kill switch is ON AND either an entail_fn is injected (tests) OR a cross-encoder NLI path is
    # already active — so a default run with every NLI flag OFF is byte-identical (no model load, no
    # merge). The widening rides the SAME resident cross-encoder the run slate already loads (ZERO new
    # spend). Additive / keep-all / faithfulness-neutral (§-1.3).
    if _qual_nominate_enabled() and (
        nominate_entail_fn is not None
        or _consolidation_nli_enabled()
        or _finding_dedup_nli_enabled()
    ):
        _nom_telemetry: dict[str, Any] = {}
        clusters = _apply_qualitative_containment_nli_grouping(
            rows, clusters, entail_fn=nominate_entail_fn, telemetry=_nom_telemetry,
        )
        logger.info(
            "[activation] qualitative_nominate: nominated_pairs=%d containment_merges=%d over_cap=%s",
            int(_nom_telemetry.get("nominated_pairs", 0)),
            int(_nom_telemetry.get("containment_merges", 0)),
            bool(_nom_telemetry.get("over_cap", False)),
        )

    out: dict[tuple, list[int]] = {}
    for cluster in clusters:
        members = cluster[2]
        if len(members) < 2:
            continue  # a genuinely-unique qualitative claim stays a singleton
        rep_ri = members[0]  # lowest row index (deterministic); re-ranked in emission
        rep_eid = str(rows[rep_ri].get("evidence_id", rep_ri))
        token = _qual_key_token(_row_text(rows[rep_ri]))
        # All-string key => NON-NUMERIC finding_key (D1 dice). The rep evidence_id
        # makes the key unique per cluster (no cross-cluster key collision / false
        # merge); the token makes it semantically auditable in the manifest.
        key = ("__qual__", rep_eid, token)
        out[key] = sorted(set(members))
    return out


# ─────────────────────────────────────────────────────────────────────────
# All-chrome basket DELETE — S2/S3 re-pass Fable Fix 4(b) (§-1.3.1(a) carve-out)
# ─────────────────────────────────────────────────────────────────────────
# Fable Fix 4(b): "a basket with NO claim line ANYWHERE is itself chrome — route to junk deletion
# with disclosure." A numeric/sentinel basket in which NOT ONE member yields a real, non-boilerplate
# CLAIM sentence (every member is a license / nav / ISSN / TOC / bibliographic / metadata line) is a
# chrome NON-source, deletable under §-1.3.1(a). This reuses the SAME ``_row_has_mergeable_claim``
# predicate already trusted for rep selection + merge gating — it is letter-spacing-collapse
# protected, so a real spaced / scanned-PDF abstract ("W e i n v e s t i g a t e ...") collapses to
# a claim and is NEVER flagged chrome (fail-open). It is NOT a garble / word-ratio knob (those were
# proven to false-positive on real PDF prose — the iter-6 ev_901 / ev_685 / ev_1146 finding). A row
# is deleted ONLY when EVERY basket it belongs to is all-chrome (a chrome-shaped row that also
# corroborates a REAL claim elsewhere is KEPT). DEFAULT-OFF: a brand-new DELETE path must be vetted
# on a validated real run before it deletes in production (matching this module's "un-vetted change
# must never silently degrade" discipline); the disclosure telemetry lets the operator enable +
# measure it. Every deletion is DISCLOSED (count + reason, fail-loud).
_CHROME_BASKET_DELETE_ENV = "PG_FINDING_CHROME_BASKET_DELETE"


def _chrome_basket_delete_enabled() -> bool:
    """``PG_FINDING_CHROME_BASKET_DELETE`` kill switch (LAW VI, DEFAULT-OFF, Fable Fix 4(b)). ON =>
    a numeric/sentinel basket whose members yield NO mergeable claim anywhere is deleted with
    disclosure (§-1.3.1(a) chrome carve-out). OFF (default) => byte-identical (no chrome-basket
    delete); genuine chrome is still removed upstream by the captcha / anti-bot shell drop."""
    return os.getenv(_CHROME_BASKET_DELETE_ENV, "0").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def dedup_by_finding(
    rows: list[dict[str, Any]],
    *,
    gov_suffixes: tuple[str, ...],
    domain: str | None = None,
) -> FindingDedupResult:
    """Cluster `rows` by numeric finding, collapse rehashes, count corroboration.

    Args:
        rows: generator-visible evidence rows (each a dict carrying at least
            `evidence_id`, `source_url`, and `direct_quote`/`statement`; plus the
            `authority_score` + `selection_relevance` sidecars for representative
            ranking).
        gov_suffixes: the PSL multi-level gov-suffix tuple from
            `authority.data_loader.load_authority_data()["psl_gov_suffixes"]` —
            passed in so this module hardcodes NO host/TLD literals.

    Returns:
        FindingDedupResult. `deduped_rows` are SHALLOW COPIES (the caller's rows
        are never mutated); representative copies carry additive
        `corroboration_count` / `independent_hosts` / `finding_keys` keys.

    I-arch-002 (#1246) P3.3 (design §7 / DNA §-1.3 Principle 2 — CONSOLIDATE,
    don't DROP): under ``PG_SWEEP_CREDIBILITY_REDESIGN`` this function STOPS
    being a source-dropper. The non-representative collapse-drop is bypassed so
    EVERY same-claim row flows through as a basket carrying corroboration as
    weight (routed into claim_graph clusters downstream); clustering uses the
    EXACT numeric value (no ``round(..., 3)``). The 3 safe guards are preserved
    in BOTH modes: qualitative pass-through (no-finding rows always kept),
    conservative-singleton (every extracted qualifier must match to cluster),
    and the unknown-subject sentinel (an ``unknown`` subject never merges). The
    faithfulness engine (strict_verify / provenance / NLI / 4-role) is
    untouched. OFF ⇒ the legacy collapse-to-representative drop, byte-identical.
    """
    # Deferred import: the call sites already defer-import this module, and
    # credibility_pass pulls in weight_mass / independence_collapse at module
    # scope — importing the predicate inside the function avoids any import
    # cycle and keeps the activation gate a single source of truth.
    from src.polaris_graph.synthesis.credibility_pass import (
        credibility_redesign_enabled,
    )

    redesign_on = credibility_redesign_enabled()

    rows = list(rows or [])

    # 0. Same-work consolidation (I-beatboth-011 #7 CORE, #1289). GROUP rows that
    #    are the SAME work (DOI first, else folded title) and DROP non-functional
    #    members (CAPTCHA / anti-bot stub, strict-prefix truncated dup). Dropped
    #    rows are excluded from BOTH the finding clustering and the emitted
    #    `deduped_rows` (a CAPTCHA stub or a truncated dup carries no real claim
    #    and must never enter a basket). Same-work members are KEPT (all URLs are
    #    corroborating locators, §-1.3 keep-all) but count as ONE origin in a
    #    finding cluster's `corroboration_count` (so N URLs of one paper across N
    #    domains stop inflating the independent-host tally to N). Faithfulness
    #    untouched — corroboration_count is a Signal-D WEIGHT, never a gate.
    #
    #    GATED behind ``PG_SWEEP_CREDIBILITY_REDESIGN`` (the same flag that turns
    #    on keep-all): the benchmark slate forces it ON, so the fix is LIVE there.
    #    OFF ⇒ an EMPTY SameWorkResult (no drops, no fold, no annotation), so the
    #    legacy collapse-to-representative path stays byte-identical as the
    #    docstring promises.
    if redesign_on:
        same_work = consolidate_same_work(rows)
    else:
        same_work = SameWorkResult(
            groups=[],
            work_id_by_index={},
            canonical_index_by_index={},
            dropped_indices=set(),
            dropped_captcha_indices=set(),
            dropped_prefix_indices=set(),
        )
    dropped = same_work.dropped_indices

    # Map a same-work member to its work's CANONICAL host: when a finding cluster
    # counts independent origins, every member of one work contributes a SINGLE
    # host (the canonical row's), so multi-URL same-work padding can never inflate
    # the count. A row with no same-work group keeps its own host.
    def _origin_host_of(ri: int) -> str:
        canon = same_work.canonical_index_by_index.get(ri, ri)
        # Fix 10 (Fable): backfill from any URL field so a row with a blank ``source_url``
        # but a populated ``url``/``link``/... still contributes its host (no empty
        # member_hosts). Fall back to the row's OWN url if the canonical has none.
        host = _host_of(_row_any_url(rows[canon]))
        if not host and canon != ri:
            host = _host_of(_row_any_url(rows[ri]))
        return host

    # Fix 5/6: the WORK a row belongs to (its same-work id, else a per-row singleton work).
    # Corroboration is counted over DISTINCT works, excluding derivative press (fail-open).
    distinct_works_on = redesign_on and _distinct_works_enabled()
    derivative_press_on = _derivative_press_enabled()

    def _work_of(ri: int) -> str:
        return same_work.work_id_by_index.get(ri) or ("__row__:%d" % ri)

    # 1. Extract claims per row, group by conservative finding key.
    #
    # B9 domain-generalization: `extract_numeric_claims` now routes a NON-clinical
    # row (deterministic is_clinical signal) to the DOMAIN-AGNOSTIC extractor, so
    # an economics/labor numeric yields a REAL finding key instead of nothing —
    # closing the documented "non-clinical -> singleton" residual (RESIDUAL 2
    # above) so corroborating non-clinical sources can consolidate into a basket.
    # `domain` defaults to None: the per-row is_clinical probe then classifies
    # each row by its own text, so a CLINICAL row still takes the clinical
    # extractor and is byte-identical. A caller MAY pass the run-level `domain`
    # to pin the whole pass. The conservative-singleton + unknown-subject guards
    # below are UNCHANGED in both modes — no merge predicate is relaxed.
    # I-deepfix-001 C1 (#1344): route the finding KEY the SAME way the extractor
    # routes — a row is CLINICAL iff ``is_clinical_domain`` says so (per-row probe,
    # identical to the extract_numeric_claims routing). A clinical row keeps the
    # verbatim strict subject key (byte-identical); a NON-clinical row folds its
    # subject to a surface-invariant signature so paraphrases consolidate.
    from src.polaris_graph.domain.domain_signal import is_clinical_domain
    # P0-4(b): which same-work groups already carry a CLAIM-BEARING member. A confidently
    # non-claim-bearing fragment is folded (mints no competing basket) ONLY when its work has a
    # real claim-bearing member to represent the work's claim. Computed once, deterministic.
    nonclaim_fold = _nonclaim_basket_fold_enabled()
    work_has_claimbearing: dict[str, bool] = {}
    if nonclaim_fold:
        for _ri, _row in enumerate(rows):
            if _ri in dropped:
                continue
            _wid = same_work.work_id_by_index.get(_ri)
            if _wid and not work_has_claimbearing.get(_wid) and _is_claim_bearing_complete(_row):
                work_has_claimbearing[_wid] = True
    groups: dict[tuple, list[int]] = {}
    row_has_finding: list[bool] = [False] * len(rows)
    # P0-1(b) (iter-7, Fable): rows whose ONLY visible content is confident boilerplate — routed
    # away from basket FOUNDING to a disclosed no-claim pool (kept as keep-all singletons).
    noclaim_pool_on = _noclaim_basket_pool_enabled()
    no_claim_pool: set[int] = set()
    for ri, row in enumerate(rows):
        if ri in dropped:
            # CAPTCHA stub / strict-prefix truncated dup — no real claim; never
            # clustered, never emitted (see step 0 + step 3).
            continue
        # P0-4(b): CONFIDENTLY non-claim-bearing fragment (methods/header/citation-listing) whose
        # SAME-WORK group already has a claim-bearing member folds into the work — it mints NO
        # numeric finding basket (row still KEPT + annotated to its work in step 3). Never the
        # canonical member (the work's chosen representative always mints). §-1.1 fail-open: the
        # gate returns True on doubt, so a real claim is never suppressed.
        if nonclaim_fold and not _is_claim_bearing_complete(row):
            _wid = same_work.work_id_by_index.get(ri)
            if (
                _wid
                and work_has_claimbearing.get(_wid)
                and same_work.canonical_index_by_index.get(ri) != ri
            ):
                continue
        # P0-1(b) (iter-7, Fable): a row whose ONLY reader-visible sentence is CONFIDENT publisher /
        # cataloguing / license / correspondence / reference boilerplate (a journal masthead, an
        # ISSN/ISBN line, a rights block, a correspondence-address block — drb_72 #007/#201/#218)
        # never FOUNDS a claim basket. It is routed to the DISCLOSED no-claim pool: it mints NO
        # numeric finding (row_has_finding stays False so it is KEPT as a keep-all singleton, never
        # a fake numeric corroborator). §-1.3.1(a) chrome/boilerplate carve-out at basket FORMATION;
        # FAIL-OPEN (any real claim sentence ⇒ never pooled); DISCLOSED (count in step-4 log +
        # result). Kill switch OFF ⇒ byte-identical.
        if noclaim_pool_on and _row_is_pure_boilerplate(row):
            no_claim_pool.add(ri)
            continue
        claims = (
            extract_numeric_claims([row], domain=domain)
            if domain is not None else extract_numeric_claims([row])
        )
        row_clinical = is_clinical_domain(domain, [row])
        ev_id = str(row.get("evidence_id", ri))
        # P0-3b (S2/S3 re-pass): a numeral that is a locator / date / id (SSRN download id,
        # phone number, citation year, page range) is NOT a reported measurement — it must not
        # mint a FAKE numeric basket. The LINE is still KEPT (as qualitative context: a row that
        # mints no measurement keeps row_has_finding False and flows to the qualitative path);
        # only the non-measurement numeric CLAIM is suppressed. Fail-open (any doubt / any
        # measurement unit present keeps the numeric claim). Kill switch OFF => byte-identical.
        measurement_gate = _measurement_gate_enabled()
        row_line_text = _row_text(row)
        minted = 0
        for cj, claim in enumerate(claims):
            if measurement_gate and _is_nonmeasurement_numeral(claim, row_line_text):
                continue  # non-measurement numeral: keep the line, mint no numeric claim
            key = _finding_key(
                claim, ev_id, cj, exact_value=redesign_on, clinical=row_clinical,
            )
            groups.setdefault(key, []).append(ri)
            minted += 1
        if minted:
            row_has_finding[ri] = True

    def _rank(ri: int) -> tuple:
        r = rows[ri]
        return (
            float(r.get("authority_score", 0.0) or 0.0),
            float(r.get("selection_relevance", 0.0) or 0.0),
            -ri,
        )

    # 1b. CONSOLIDATION-NLI winner (I-wire-001 W1, #1306). DEFAULT-OFF =>
    #     `groups` is the literal-floor result, byte-identical. ON => merge literal
    #     clusters whose REPRESENTATIVE rows BIDIRECTIONALLY entail (same-claim
    #     paraphrases the exact subject/predicate/value floor left separate). Merging
    #     can only UNION literal clusters into larger baskets => corroboration_count +
    #     member_hosts go UP; no row is dropped, no verify gate is touched (§-1.3
    #     CONSOLIDATE, faithfulness FROZEN). `nli_merge_count` records how many literal
    #     clusters were absorbed (the behavioral-canary signal — `collapsed_row_count`
    #     is 0 by design under keep-all, so it cannot be the canary). Runs BEFORE the
    #     per-cluster representative/corroboration loop so corroboration_count and
    #     member_hosts reflect the MERGED basket.
    # 1a-pre. NUMERIC tuple-cluster NLI split-confirmation (Fix 1(A), Fable). The tuple key is
    #     RECALL ONLY: a multi-member numeric cluster is split so each member must bidirectionally
    #     entail the rep's claim sentence to stay merged (a folded-subject/locator-value collision
    #     no longer fabricates corroboration). Runs BEFORE consolidation-NLI so split members can
    #     re-merge to their TRUE claim-mates there. Gated on a NLI path being active so a no-NLI
    #     run is byte-identical.
    # 1a-rung0. EXACT-duplicate collapse (Fable Fix 1(a)). BEFORE any judge, union clusters whose
    #     representative claim sentence is byte-identical after unicode/whitespace/citation-token
    #     normalization (a byte-identical sentence IS the same claim — no cross-encoder needed).
    #     This closes the structural under-merge where same-text findings sat as isolated per-row
    #     ``__unknown__`` sentinels with the judge withheld and never consolidated. Always-on
    #     (independent of the NLI flags); §-1.3-safe (UNION only, keep-all, no gate relaxed).
    rung0_collapsed = 0
    if groups and _rung0_exact_collapse_enabled():
        groups, rung0_collapsed = _apply_rung0_exact_collapse(groups, rows, _rank)

    numeric_confirm_telemetry: dict[str, int] = {}
    if (
        groups
        and _numeric_nli_confirm_enabled()
        and (_consolidation_nli_enabled() or _finding_dedup_nli_enabled())
    ):
        groups = _confirm_numeric_clusters_via_nli(
            groups, rows, _rank, telemetry=numeric_confirm_telemetry,
        )

    nli_merge_count = 0
    if groups and _consolidation_nli_enabled():
        groups, nli_merge_count = _apply_consolidation_nli(groups, rows, _rank)

    # 1d. REPRESENTATIVE-INVARIANT post-pass (Fable Fix 1(d) — THE GHOST close). After the
    #     tuple-key RECALL + rung-0 + numeric split-confirm + consolidation-NLI, UNION any two
    #     surviving numeric baskets whose VISIBLE representative claim sentence is byte-identical
    #     (or, with the cross-encoder active, bidirectionally entails). Repairs the residual
    #     false-splits the split-confirm's fail-open-on-None leaves behind (two byte-identical
    #     copies of ONE finding sitting in two baskets). UNION-only / keep-all / faithfulness-
    #     untouched; DEFAULT-ON kill switch. Runs BEFORE the per-cluster loop so corroboration +
    #     member_hosts reflect the repaired basket.
    rep_invariant_merged = 0
    if groups and _representative_invariant_enabled():
        groups, rep_invariant_merged = _apply_representative_invariant(groups, rows, _rank)

    # 1e. POST-MERGE member re-verify (Fable Fix 1 — anti-fabrication, THE P0). After ALL merge
    #     passes, re-verify each non-rep member of every surviving multi-member basket against the
    #     FINAL rep; SPLIT any member whose OWN claim sentence does not entail the rep (or lacks the
    #     numbers-strict value). This dissolves a fabricated-corroboration false merge that a
    #     cluster-rep-level consolidation-NLI join or a same-value bucket collision left behind
    #     (drb_72 #128 springer/mdpi onto a PWBM macro claim; #339 a career page onto an
    #     Eloundou-rubric claim). Gated on an NLI path being active (so a no-NLI run is
    #     byte-identical) + its own kill switch. SPLIT-only / keep-all / §-1.3.
    if (
        groups
        and _post_merge_reverify_enabled()
        and (_consolidation_nli_enabled() or _finding_dedup_nli_enabled())
    ):
        groups, _post_merge_split = _apply_post_merge_reverify(
            groups, rows, _rank, telemetry=numeric_confirm_telemetry,
        )

    # 1c. QUALITATIVE basket formation (I-deepfix-001 D1, #1344). §-1.3 CONSOLIDATE
    #     qualitative claims TOO (not numeric-only): rows with NO extracted numeric
    #     finding that assert the SAME qualitative claim form a multi-citation
    #     corroboration basket keyed on a NON-NUMERIC normalized signature. The
    #     numeric `groups` above can never key such a basket, so a qualitative claim
    #     several independent sources assert earned no corroboration weight (the D1
    #     dice's blind spot). CONSERVATIVE (high Jaccard + polarity guard) so two
    #     DIFFERENT qualitative claims never merge; KEEP-ALL (no row dropped);
    #     faithfulness-neutral (weight only — strict_verify / the entailment verifier
    #     / 4-role / provenance / span-grounding untouched). Gated on the
    #     consolidate-keep-all regime + a kill switch; OFF => no qualitative baskets
    #     (byte-identical numeric-only behavior). Disjoint from `groups` (qualitative
    #     rows have row_has_finding==False), so it adds baskets without re-clustering
    #     any numeric finding and leaves `distinct_finding_count` (numeric) unchanged.
    qual_groups: dict[tuple, list[int]] = {}
    if redesign_on and _qualitative_enabled():
        # P0-1(b): the no-claim pool (confident boilerplate) is excluded from qualitative basket
        # founding too — a masthead/ISSN/rights row must not found a qualitative basket either
        # (the qual mergeable-screen already excludes it, but pass it explicitly for clarity +
        # to keep the disclosure honest). The rows are still KEPT as keep-all singletons.
        qual_groups = _build_qualitative_groups(
            rows, row_has_finding, dropped | no_claim_pool,
            threshold=_qual_jaccard_threshold(),
        )
        if qual_groups:
            logger.info(
                "[finding_dedup] qualitative consolidation FIRED: %d qualitative "
                "basket(s) formed from no-numeric-finding rows (§-1.3 CONSOLIDATE "
                "qualitative too; keep-all, weight-only, faithfulness-neutral)",
                len(qual_groups),
            )

    # 2. Per cluster: representative + corroboration over INDEPENDENT hosts. The
    #    qualitative baskets (1c) are emitted alongside the numeric `groups` so they
    #    surface the same corroboration WEIGHT (count + distinct hosts) and rep
    #    annotation; their keys are NON-NUMERIC by construction.
    clusters: list[FindingCluster] = []
    rep_indices: set[int] = set()
    rep_meta: dict[int, dict[str, Any]] = {}
    for key, member_ris in list(groups.items()) + list(qual_groups.items()):
        distinct_ris = sorted(set(member_ris))
        # Fix 4b/7 (Fable): never elect a chrome/nav/captcha/letter-spaced line as the
        # representative when a clean content member exists (the row is still kept).
        rep_ri = _choose_clean_representative(distinct_ris, _rank, rows)
        # Same-work fold: count each member by its WORK's canonical host, so N
        # URLs of one paper across N domains contribute ONE independent origin —
        # the #7 CORE de-padding. `member_hosts` + `corroboration` are derived
        # from these origin hosts (keep-all is preserved separately on the rows:
        # every member row still survives and carries its own URL).
        hosts_raw = [_origin_host_of(ri) for ri in distinct_ris]
        member_hosts = sorted(
            {registrable_domain(h, gov_suffixes) for h in hosts_raw} - {""}
        )
        if distinct_works_on:
            # Fix 5: corroboration = number of DISTINCT WORKS among members (mirror copies
            # of one work already share one work id via Fix 4). Fix 6: derivative press is
            # excluded from the independent count but kept in the basket; if a claim is
            # carried ONLY by press, fall back to its distinct-press-work count (never 0).
            works_primary = {
                _work_of(ri) for ri in distinct_ris
                if not (derivative_press_on and _is_derivative_press(rows[ri]))
            }
            works_all = {_work_of(ri) for ri in distinct_ris}
            corroboration = len(works_primary) or len(works_all)
        else:
            corroboration = count_independent_hosts(hosts_raw, gov_suffixes)
        clusters.append(
            FindingCluster(
                finding_key=key,
                representative_index=rep_ri,
                member_indices=distinct_ris,
                member_hosts=member_hosts,
                corroboration_count=corroboration,
            )
        )
        rep_indices.add(rep_ri)
        meta = rep_meta.setdefault(
            rep_ri, {"corr": 0, "hosts": set(), "keys": []}
        )
        meta["corr"] = max(meta["corr"], corroboration)
        meta["hosts"].update(member_hosts)
        meta["keys"].append(list(key))

    # 3. Retain: every row that is the rep of >=1 cluster, plus every row with NO
    #    extractable finding (qualitative rows are never rehashes). Original order.
    #
    #    OFF (legacy): a finding-bearing row that is the rep of nothing is
    #    REDUNDANT -> dropped; every distinct finding it carried survives on that
    #    finding's rep row.
    #
    #    I-arch-002 (#1246) P3.3 (CONSOLIDATE-keep-all): under
    #    ``PG_SWEEP_CREDIBILITY_REDESIGN`` the non-representative DROP is BYPASSED
    #    so ALL same-claim rows flow through as a basket (repetition IS
    #    corroboration). The representative still carries the corroboration
    #    sidecar; non-rep members now survive in original order instead of being
    #    collapsed away. ``collapsed_row_count`` honestly becomes 0.
    #    I-beatboth-011 #7 CORE (#1289): CAPTCHA stubs + strict-prefix truncated
    #    dups (step 0) are NEVER emitted (no real claim). Every SURVIVING row —
    #    representative, qualitative no-finding, and same-work member alike — is
    #    annotated with its same-work group so the basket consumer
    #    (PG_BASKET_CONSUME_FINDING_DEDUP) and the enrichment-side consolidator in
    #    `generator/weighted_enrichment.py` PRESENT one work as ONE source while
    #    KEEPING every member URL as a corroborating locator (§-1.3 keep-all).
    # Fable Fix 4(b) (§-1.3.1(a) chrome carve-out, DEFAULT-OFF): a row is chrome-deletable only
    # when EVERY basket it belongs to is all-chrome (no member yields a mergeable claim), it is
    # never a rep of a surviving cluster, and it is finding-bearing. A chrome-shaped row that also
    # corroborates a REAL claim elsewhere is KEPT (fail-open). Letter-spacing-collapse protected
    # (real spaced/scanned-PDF prose collapses to a claim => never flagged).
    chrome_drop_ris: set[int] = set()
    if redesign_on and _chrome_basket_delete_enabled():
        claim_basket_ris: set[int] = set()
        chrome_basket_ris: set[int] = set()
        for _ck, _cm in groups.items():  # numeric/sentinel baskets only (qual rows are keep-all)
            _dm = sorted(set(_cm))
            if any(_row_has_mergeable_claim(rows[cri]) for cri in _dm):
                claim_basket_ris.update(_dm)
            else:
                chrome_basket_ris.update(_dm)
        chrome_drop_ris = {
            cri for cri in chrome_basket_ris
            if cri not in claim_basket_ris
            and cri not in rep_indices
            and row_has_finding[cri]
        }
    n_chrome_basket_dropped = 0
    group_by_canonical = {g.canonical_index: g for g in same_work.groups}
    deduped_rows: list[dict[str, Any]] = []
    for ri, row in enumerate(rows):
        if ri in dropped:
            continue
        if ri in chrome_drop_ris:
            n_chrome_basket_dropped += 1
            continue  # Fable Fix 4(b): all-chrome-basket member, deleted (disclosed below)
        if not redesign_on and not (ri in rep_indices or not row_has_finding[ri]):
            continue
        new_row = dict(row)  # shallow copy — never mutate the caller's row
        if ri in rep_meta:
            meta = rep_meta[ri]
            new_row["corroboration_count"] = meta["corr"]
            new_row["independent_hosts"] = sorted(meta["hosts"])
            new_row["finding_keys"] = meta["keys"]
        # P2-8 (S2/S3 re-pass): a press/blog/slide/column that merely REPORTS a primary work is
        # corroboration-OF-REPORTING, not independent evidence. KEEP it (keep-all) but LABEL it
        # derivative + surface a disclosed WEIGHT multiplier so composition presents it as
        # coverage, not a distinct corroborator (it is already excluded from the distinct-works
        # count). Additive sidecars only (no existing weight field is overwritten). Gated.
        if derivative_press_on and _is_derivative_press(row):
            new_row["derivative_of_primary"] = True
            new_row["derivative_weight_factor"] = _derivative_weight_factor()
        work_id = same_work.work_id_by_index.get(ri)
        if work_id is not None:
            canon = same_work.canonical_index_by_index[ri]
            group = group_by_canonical.get(canon)
            new_row["same_work_id"] = work_id
            new_row["is_same_work_canonical"] = (ri == canon)
            new_row["same_work_canonical_evidence_id"] = str(
                rows[canon].get("evidence_id", canon)
            )
            if group is not None:
                # KEEP-ALL: every member evidence_id + URL is a corroborating
                # locator of this one work (counts as ONE source, never drops a
                # corroborator).
                new_row["same_work_member_evidence_ids"] = list(
                    group.member_evidence_ids
                )
                new_row["same_work_member_urls"] = list(group.member_urls)
        deduped_rows.append(new_row)

    if n_chrome_basket_dropped:
        # §-1.3.1 fail-loud disclosure: every chrome deletion is reported (count + reason).
        logger.info(
            "[finding_dedup] Fable Fix 4(b) all-chrome-basket DELETE: removed %d finding-bearing "
            "row(s) that belonged ONLY to baskets with no mergeable claim anywhere (chrome "
            "non-sources, §-1.3.1(a) carve-out; credible on-topic rows untouched — every basket "
            "with any claim member was KEPT)",
            n_chrome_basket_dropped,
        )

    if no_claim_pool:
        # P0-1(b) §-1.3.1(a) fail-loud disclosure: boilerplate-only rows kept OUT of basket founding.
        logger.info(
            "[finding_dedup] P0-1(b) no-claim basket pool: %d boilerplate-only row(s) "
            "(publisher/cataloguing/license/correspondence/reference) were routed away from "
            "founding a claim basket and KEPT as keep-all singletons (never a fake numeric "
            "corroborator; credible on-topic claim rows untouched, fail-open)",
            len(no_claim_pool),
        )

    return FindingDedupResult(
        deduped_rows=deduped_rows,
        clusters=clusters,
        raw_row_count=len(rows),
        distinct_finding_count=len(groups),
        collapsed_row_count=len(rows) - len(deduped_rows),
        same_work=same_work,
        nli_merge_count=nli_merge_count,
        qualitative_basket_count=len(qual_groups),
        rep_invariant_merge_count=rep_invariant_merged,
        numeric_confirm_telemetry=dict(numeric_confirm_telemetry),
        no_claim_basket_pooled_count=len(no_claim_pool),
    )
