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

    # 2. Per cluster: representative + corroboration over INDEPENDENT hosts.
    clusters: list[FindingCluster] = []
    rep_indices: set[int] = set()
    rep_meta: dict[int, dict[str, Any]] = {}
    for key, member_ris in groups.items():
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
    )
