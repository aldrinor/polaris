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

DOCUMENTED RESIDUAL 2 (extraction coverage — clinical-tuned): the reused
``extract_numeric_claims`` is clinical-pattern-tuned. Empirically it (a) emits AT
MOST ONE claim per row, and (b) returns NOTHING for non-clinical numerics (GDP,
emissions, model-accuracy, etc.). Consequently a non-clinical numeric row yields
ZERO findings and is kept as a SAFE SINGLETON — never falsely merged, never
dropped — but its finding is NOT clustered and earns NO corroboration_count. So
dedup + corroboration are EFFECTIVE for clinical corpora and INERT-but-SAFE for
non-clinical ones. This is a coverage limitation, not a correctness bug: it can
never cause unique-claim loss or a wrong merge. Gap D's domain-general
corroboration ambition requires a field-agnostic numeric-finding extractor, which
is deliberately deferred to a follow-up rather than risking an over-merging
heuristic here. (The multi-claim-per-row retention logic below is therefore
defensive/future-proof against an extractor that later emits >1 claim per row.)

Pure: constructs no client, no network, no LLM. snake_case; explicit imports.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any
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
    """
    subject = getattr(claim, "subject", "") or ""
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

    n = len(clusters)
    if n < 2:
        return clusters

    # Representative CLAIM TEXT of each candidate cluster (lowest-row-index member — the same
    # representative the emission step re-derives, so the key is stable). Polarity signature is
    # carried on the cluster from the candidate stage (index 1).
    rep_texts = [_row_text(rows[cluster[2][0]]) for cluster in clusters]
    rep_polarity = [cluster[1] for cluster in clusters]

    edges = score_pairs(rep_texts, predict_fn=predict_fn)
    # (ii) polarity HARD-BLOCK: drop any bidirectional-entailment edge whose two
    # representatives carry mismatched polarity signatures (antonym / negation flip).
    edges = [(i, j) for (i, j) in edges if rep_polarity[i] == rep_polarity[j]]
    if not edges:
        return clusters

    # DIRECT-EDGE adjacency (NOT transitive union-find). I-deepfix-001 P4 Codex fix (#1344):
    # build the direct bidirectional-entailment neighbour set of each cluster, then group
    # KEEP-FIRST — a redundant cluster joins a primary ONLY when it carries a DIRECT edge to
    # THAT primary. This is the exact direct-to-primary safe pattern ``fact_dedup.py`` FIX-D
    # (#1335) uses; it structurally blocks the A::B + B::C => {A,B,C} transitive over-merge
    # (C never joins A's basket unless C DIRECTLY entails A), so a basket head's
    # corroboration_count can never be inflated by a claim that only entails a sibling.
    entails: dict[int, set[int]] = {}
    for i, j in edges:
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


def _build_qualitative_groups(
    rows: list[dict[str, Any]],
    row_has_finding: list[bool],
    dropped: set[int],
    *,
    threshold: float,
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
    if _qualitative_nli_enabled():
        clusters = _apply_qualitative_nli_union(rows, clusters)

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
        if claims:
            row_has_finding[ri] = True
        ev_id = str(row.get("evidence_id", ri))
        for cj, claim in enumerate(claims):
            key = _finding_key(claim, ev_id, cj, exact_value=redesign_on)
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
