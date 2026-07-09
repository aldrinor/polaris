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


def _same_work_key(row: dict[str, Any]) -> str:
    """The SHARED same-work key: normalized DOI first, else folded title PLUS a
    corroborating discriminator, else ``""`` (no same-work grouping — the row is
    its own singleton work).

    I-beatboth-011 #4 (#1289): the no-DOI branch NEVER merges on folded title
    ALONE (two different works can share a title). It requires the folded title
    AND the FIRST present discriminator (year → first-author surname → venue →
    host). Title-with-no-discriminator → ``""`` → singleton. Matches
    ``weighted_enrichment._work_identity`` so the two consolidators put the same
    members in the same work.
    """
    doi = _normalize_doi(row.get("doi"))
    if doi:
        return "doi:" + doi
    folded = _fold_title(_row_title(row))
    if folded:
        discriminator = _title_discriminator(row)
        if discriminator:
            return "title:" + folded + "|" + discriminator
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
    """
    low = _row_text(row).lower()
    return (_CAPTCHA_STUB_TRIGGER in low) and any(tok in low for tok in _WAF_CO_TOKENS)


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
        # Fold ONLY the non-clinical subject to a surface-invariant signature.
        # An empty fold (pure-punctuation subject) becomes the UNKNOWN sentinel.
        subject = _fold_nonclinical_subject(subject) or _UNKNOWN_SUBJECT
    if not subject or subject == _UNKNOWN_SUBJECT:
        return ("__unknown__", evidence_id, claim_index)
    raw_value = float(getattr(claim, "value", 0.0) or 0.0)
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
    for ri, row in enumerate(rows):
        if _is_captcha_stub(row):
            dropped_captcha.add(ri)
            continue
        key = _same_work_key(row)
        if not key:
            # No same-work key: a per-row singleton key so it can never collide.
            key = "__singleton__:%d" % ri
        work_members.setdefault(key, []).append(ri)

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
        # Only emit a real same-work id for genuine same-work keys (a DOI/title
        # group). The per-row "__singleton__" keys carry no cross-row meaning, so
        # they get no same_work annotation (a row with no DOI/title is its own
        # work and must not look "consolidated").
        is_real_work = key.startswith("doi:") or key.startswith("title:")
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


def _cluster_value_bucket(key: tuple, rows: list[dict[str, Any]], member_ris: list[int]) -> Any:
    """The numeric VALUE a literal cluster asserts — used to BUCKET clusters before NLI so
    only same-VALUE clusters are pairwise-compared. Two sources can corroborate the SAME
    claim only if they carry the SAME number, so bucketing by value is both a scale fix
    (O(n^2) -> O(sum bucket^2)) and a precision guard (never NLI-compare 30% vs 12%).

    Known-subject keys carry the value at index 2. The ``__unknown__`` sentinel key does
    not, so the value is recovered from the representative row's extracted claim; a cluster
    with no recoverable numeric value buckets under ``None`` (its own no-merge bucket)."""
    if isinstance(key, tuple) and key and key[0] != "__unknown__" and len(key) >= 3:
        return round(float(key[2]), 6)
    for ri in member_ris:
        claims = extract_numeric_claims([rows[ri]])
        if claims:
            return round(float(getattr(claims[0], "value", 0.0) or 0.0), 6)
    return None


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
    silently no-ops would defeat the §-1.4 canary (no silent fallback, LAW II)."""
    from src.polaris_graph.synthesis.consolidation_nli import group_clusters  # noqa: PLC0415

    keys = list(groups.keys())
    if len(keys) < 2:
        return groups, 0

    # Bucket every cluster index by the numeric value it asserts. Only buckets with >=2
    # clusters carry NLI-merge candidates; the rest pass through unchanged.
    bucket_of: dict[int, Any] = {
        i: _cluster_value_bucket(keys[i], rows, groups[keys[i]]) for i in range(len(keys))
    }
    by_value: dict[Any, list[int]] = {}
    for i in range(len(keys)):
        v = bucket_of[i]
        if v is None:
            continue  # no recoverable value => its own singleton, never merged
        by_value.setdefault(v, []).append(i)

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

    for value, cluster_idxs in sorted(by_value.items(), key=lambda kv: str(kv[0])):
        if len(cluster_idxs) < 2:
            continue
        texts = [_cluster_text(rows, groups[keys[i]], rank_fn, value) for i in cluster_idxs]
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
_FINDING_DEDUP_NLI_WALL_SECONDS_DEFAULT = "180"

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
        return _host_of(str(rows[canon].get("source_url", "")))

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
    groups: dict[tuple, list[int]] = {}
    row_has_finding: list[bool] = [False] * len(rows)
    for ri, row in enumerate(rows):
        if ri in dropped:
            # CAPTCHA stub / strict-prefix truncated dup — no real claim; never
            # clustered, never emitted (see step 0 + step 3).
            continue
        claims = (
            extract_numeric_claims([row], domain=domain)
            if domain is not None else extract_numeric_claims([row])
        )
        row_clinical = is_clinical_domain(domain, [row])
        if claims:
            row_has_finding[ri] = True
        ev_id = str(row.get("evidence_id", ri))
        for cj, claim in enumerate(claims):
            key = _finding_key(
                claim, ev_id, cj, exact_value=redesign_on, clinical=row_clinical,
            )
            groups.setdefault(key, []).append(ri)

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
    nli_merge_count = 0
    if groups and _consolidation_nli_enabled():
        groups, nli_merge_count = _apply_consolidation_nli(groups, rows, _rank)

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
        qual_groups = _build_qualitative_groups(
            rows, row_has_finding, dropped, threshold=_qual_jaccard_threshold(),
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
        rep_ri = max(distinct_ris, key=_rank)
        # Same-work fold: count each member by its WORK's canonical host, so N
        # URLs of one paper across N domains contribute ONE independent origin —
        # the #7 CORE de-padding. `member_hosts` + `corroboration` are derived
        # from these origin hosts (keep-all is preserved separately on the rows:
        # every member row still survives and carries its own URL).
        hosts_raw = [_origin_host_of(ri) for ri in distinct_ris]
        member_hosts = sorted(
            {registrable_domain(h, gov_suffixes) for h in hosts_raw} - {""}
        )
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
    group_by_canonical = {g.canonical_index: g for g in same_work.groups}
    deduped_rows: list[dict[str, Any]] = []
    for ri, row in enumerate(rows):
        if ri in dropped:
            continue
        if not redesign_on and not (ri in rep_indices or not row_has_finding[ri]):
            continue
        new_row = dict(row)  # shallow copy — never mutate the caller's row
        if ri in rep_meta:
            meta = rep_meta[ri]
            new_row["corroboration_count"] = meta["corr"]
            new_row["independent_hosts"] = sorted(meta["hosts"])
            new_row["finding_keys"] = meta["keys"]
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

    return FindingDedupResult(
        deduped_rows=deduped_rows,
        clusters=clusters,
        raw_row_count=len(rows),
        distinct_finding_count=len(groups),
        collapsed_row_count=len(rows) - len(deduped_rows),
        same_work=same_work,
        nli_merge_count=nli_merge_count,
        qualitative_basket_count=len(qual_groups),
    )
