"""Phase C — REAL enforcement of quality + topicality as CITABLE-ELIGIBILITY.

This module is the executable core the review (Sol §4 "Make ``high_quality`` real",
"Make topicality real"; GATE_REVIEW_VERDICT Phase C item 4) demands. It turns two
previously-decorative contract dimensions into deterministic, domain-neutral,
POST-FETCH eligibility verdicts over metadata that live retrieval ALREADY fetched:

  * ``scope.source_quality`` (e.g. hard "only high-quality / peer-reviewed") ->
    a domain-neutral quality profile scored over ``tier`` / ``is_peer_reviewed`` /
    ``openalex_venue`` / retraction / degraded-shell flags / OJS-mill host
    heuristics. "journal-shaped" != peer-reviewed; a conference proceeding is not a
    journal unless the contract allows it. Unknown metadata under a HARD
    "only high-quality" fails CLOSED for citable eligibility (disclosed), never
    silently relaxed. A SOFT preference reorders only (emits a weight, no drop).

  * topicality -> the fetched body (``statement`` + ``direct_quote``) is scored
    against the CLEAN objective + owning research thread (NOT the instruction-laden
    prompt). Confirmed off-topic (below floor) is quarantined from the citable
    menu; uncertain stays and is down-ranked/marked.

CRITICAL — this is entirely UPSTREAM of the frozen verifier. It decides which
evidence rows are ELIGIBLE to enter the citable menu (``evidence_for_gen``) BEFORE
``strict_verify`` ever enumerates the pool. It NEVER changes HOW a claim is
verified or cited. ``provenance_generator.py`` / ``strict_verify`` stay 0-diff. A
row failing a HARD predicate is REMOVED from the citable menu here but KEPT in the
corpus + disclosure (§-1.3 disclose-don't-delete), exactly mirroring the existing
scope-hard grounding mask.

Everything is pure data: no network, no LLM, no I/O. The whole module no-ops when
its inputs carry no hard quality/topicality predicate (byte-identical). It is only
reached under ``PG_GATE`` at the citable-menu seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Verdicts + receipts (spec item 4)
# ---------------------------------------------------------------------------

PASS = "pass"
FAIL = "fail"
UNKNOWN = "unknown"

# Stages a receipt can be authored by (routed to the compliance audit).
STAGE_QUALITY = "quality_eligibility"
STAGE_TOPICALITY = "topicality_eligibility"


@dataclass
class SourceReceipt:
    """One per (source, hard term, stage) eligibility decision.

    Consumed by ``contract_compliance.audit_contract``: a hard term is SATISFIED
    only if its executable stage ran AND every citable source subject to it carries
    a ``pass`` receipt; a single ``fail``/``unknown`` keeps the term unsatisfied
    (``unknown`` never fabricated as satisfied — Sol §4 receipt-backed compliance).
    """

    contract_hash: str
    term_id: str
    source_id: str            # the row's stable id (source_url)
    stage: str                # STAGE_QUALITY | STAGE_TOPICALITY
    verdict: str              # PASS | FAIL | UNKNOWN
    basis: str = ""           # human-readable rule + evidence that fired

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_hash": self.contract_hash,
            "term_id": self.term_id,
            "source_id": self.source_id,
            "stage": self.stage,
            "verdict": self.verdict,
            "basis": self.basis,
        }


@dataclass
class EligibilityPlan:
    """The post-fetch eligibility outcome over one billed candidate set.

    Mirrors ``ScopeEnforcementPlan``: an ``eligibility_excluded_ids`` set the seam
    masks out of the citable menu (rows KEPT in corpus + disclosure), a demote
    weight map for SOFT preferences (order-not-drop), per-source receipts, and a
    disclosure record list.
    """

    eligibility_excluded_ids: set[str] = field(default_factory=set)
    url_to_quality_weight: dict[str, float] = field(default_factory=dict)
    receipts: list[SourceReceipt] = field(default_factory=list)
    excluded_records: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.eligibility_excluded_ids
            or self.url_to_quality_weight
            or self.receipts
        )


# ---------------------------------------------------------------------------
# Row metadata accessors (domain-neutral; every field is already fetched)
# ---------------------------------------------------------------------------


def _row_url(row: Any) -> str:
    if isinstance(row, dict):
        return str(row.get("source_url") or row.get("url") or "")
    return str(getattr(row, "source_url", "") or getattr(row, "url", "") or "")


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _row_text(row: Any) -> str:
    """The fetched-body surface topicality scores against: statement + quote."""
    stmt = str(_row_get(row, "statement", "") or "")
    quote = str(_row_get(row, "direct_quote", "") or "")
    return (stmt + " " + quote).strip()


# ---------------------------------------------------------------------------
# QUALITY — a domain-neutral quality profile over already-fetched metadata
# ---------------------------------------------------------------------------

# Tier quality bands (tier_classifier.TierLevel): T1 peer-reviewed primary, T2
# SR/MA, T3 gov/regulatory, T4 peer-reviewed commentary are the "high-quality"
# band; T5 industry-funded, T6 news/blog non-peer-reviewed, T7 abstract/stub are
# NOT. This is the primary deterministic quality axis (RECON-2 item 3).
_HIGH_QUALITY_TIERS: frozenset[str] = frozenset({"T1", "T2", "T3", "T4"})
_LOW_QUALITY_TIERS: frozenset[str] = frozenset({"T5", "T6", "T7"})

# OJS-mill / predatory / bare-proceeding host heuristics — domain-neutral URL
# substrings that mark a "journal-shaped but not peer-reviewed" venue. Conservative
# (a match is a strong NEGATIVE signal, never the sole POSITIVE one). Extensible.
_PREDATORY_HOST_PATTERNS: tuple[str, ...] = (
    "/ojs/",           # bare Open Journal Systems mill path
    "scirp.org",       # Scientific Research Publishing (widely-flagged mill)
    "m.scirp.org",
    "sciencepublishinggroup.com",
    "omicsonline.org",
    "omicsgroup.org",
    "hindawi-",        # spoofed-hindawi mills (real hindawi.com is NOT matched)
    "abacademies.org",  # Allied Business Academies (widely-flagged predatory-adjacent mill)
)

# Values a hard source_quality term takes that mean "peer-reviewed / high-quality".
_HIGH_QUALITY_TOKENS: frozenset[str] = frozenset({
    "high", "high-quality", "high quality", "peer-reviewed", "peer reviewed",
    "peer_reviewed", "reputable", "authoritative", "scholarly",
})


def _is_high_quality_request(quality_profile: Optional[str]) -> bool:
    q = str(quality_profile or "").strip().lower()
    return bool(q) and q in _HIGH_QUALITY_TOKENS


def _predatory_host(url: str) -> bool:
    u = (url or "").lower()
    host = ""
    try:
        host = (urlparse(u).netloc or "").lower()
    except Exception:  # noqa: BLE001
        host = ""
    for pat in _PREDATORY_HOST_PATTERNS:
        if pat in u or pat in host:
            return True
    return False


def _has_doi_or_journal_credential(row: Any, url: str) -> tuple[bool, str]:
    """FIX 5(b): POSITIVE-evidence second-chance signal for an otherwise-UNKNOWN row.

    True iff the deterministic document-genre CLASSIFIER resolves the row to a
    peer-reviewed journal/review article
    (``is_peer_reviewed_journal_article(classify_document_type(...)[0]) == True``).
    A bare DOI is NOT sufficient on its own: the DOI is an INPUT to the classifier
    (it helps genre resolution) but a positive T1-scholarly verdict comes ONLY from the
    classifier's peer-reviewed-journal judgement. Preprint (arXiv 10.48550), dataset
    (Zenodo 10.5281), working-paper (NBER 10.3386, SSRN 10.2139), and bare/content-shell
    DOIs classify to a NON-journal genre and therefore return ``(False, ...)`` here.

    Reuses the SAME predicate the scope-facet classifier already trusts — single source of
    truth, no duplicate journal logic. Pure / offline / fail-open: any classifier fault yields
    ``(False, ...)`` so a scoring error never RESCUES a row (it can only leave it UNKNOWN).

    This is consulted ONLY after every FAIL path has already returned, so it can never
    re-admit a retracted / predatory / non-peer-reviewed / low-tier source."""
    # genre: the peer-reviewed-journal predicate the scope classifier trusts. The DOI feeds
    # the classifier as one input; it is NOT a standalone credential (a bare/preprint/dataset
    # DOI resolves to a non-journal genre -> not-T1 -> the row stays UNKNOWN).
    try:
        from src.polaris_graph.retrieval.document_type_classifier import (
            classify_document_type,
            is_peer_reviewed_journal_article,
        )
        dt, _basis = classify_document_type(
            openalex_publication_type=str(_row_get(row, "openalex_publication_type", "") or ""),
            openalex_source_type=str(_row_get(row, "openalex_source_type", "") or ""),
            openalex_is_peer_reviewed=_row_get(row, "openalex_is_peer_reviewed", None),
            source_class=str(_row_get(row, "source_class", "") or ""),
            url=url,
            title=str(_row_get(row, "title", "") or ""),
            doi=str(_row_get(row, "doi", "") or ""),
        )
        if is_peer_reviewed_journal_article(dt):
            return True, f"peer-reviewed journal article ({dt.value})"
    except Exception:  # noqa: BLE001 — fail-open: no rescue on error
        pass
    return False, ""


# ---------------------------------------------------------------------------
# GENERALIZED Fix 5(b): signal -> (tier, kind) REGISTRY (journal => PASS is ONE
# T1 instance, not the mechanism). Consulted where the journal "4.5 second-chance"
# used to sit — AFTER every FAIL return, BEFORE the UNKNOWN fail-closed. The table
# is DATA (kind tokens), never control-flow literals: the SHAPE (signal->tier->∈allowed)
# is the deliverable; adding a kind later must be a row here, not a branch.
#
#   T1 = authoritative-universal (validated peer-reviewed scholarly OR official
#        gov / primary / statute / authenticated filing) -> PASS UNCONDITIONALLY
#        for any contract. "journal => PASS" is the T1-scholarly row, nothing more.
#   T2 = reputable newswire / authenticated IR / established analyst (author+method)
#        -> PASS iff its kind ∈ allowed_kinds and ∉ excluded_kinds.
#   T3 = issuer-primary (press release / corporate) -> PASS iff kind ∈ allowed and ∉ excluded.
#   unrated / no positive signal -> return None; the existing UNKNOWN path is unchanged.
#
# DOI-ALONE IS NOT T1: the T1-scholarly predicate REUSES ``_has_doi_or_journal_credential``,
# which is CLASSIFIER-CONFIRMED — it returns True only when the genre classifier resolves the
# row to a peer-reviewed journal/review article (article/review + journal source-type or a
# known peer-reviewed registrant/host). A bare, preprint (arXiv), dataset (Zenodo),
# working-paper (NBER/SSRN), predatory, or content-shell DOI classifies to a non-journal
# genre and does NOT PASS — the DOI is only an INPUT to the classifier, never a credential.
_TIER_T1 = "T1"
_TIER_T2 = "T2"
_TIER_T3 = "T3"

# Official government / primary-authority hosts (universal T1, DOI-independent). A
# conservative host-suffix set — a match is a strong POSITIVE authority signal.
_GOV_PRIMARY_HOST_SUFFIXES: tuple[str, ...] = (
    ".gov", ".gov.uk", ".gouv.fr", ".gc.ca", ".gov.au", ".govt.nz", ".gov.in",
    ".europa.eu", ".un.org", ".who.int", ".imf.org", ".worldbank.org", ".oecd.org",
    ".ecb.europa.eu", ".federalreserve.gov", ".bls.gov", ".census.gov",
)


def _host_of(url: str) -> str:
    try:
        return (urlparse((url or "").lower()).netloc or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def _official_gov_host(url: str) -> bool:
    """True iff the URL host is an official government / primary-authority domain.

    Universal T1 (like peer-reviewed scholarly): authority is authority for ANY
    contract. Deterministic host-suffix match only — never an LLM, never a guess."""
    host = _host_of(url)
    if not host:
        return False
    return any(host == suf.lstrip(".") or host.endswith(suf) for suf in _GOV_PRIMARY_HOST_SUFFIXES)


def _positive_signal_tier(row: Any, url: str) -> "tuple[str, str] | None":
    """Map a row's POSITIVE credentials to ``(tier, kind)`` or ``None``.

    First match wins with a recorded basis (the caller stringifies the kind). Pure /
    offline / fail-open: any fault yields ``None`` (never a rescue on error). This is
    consulted ONLY after every FAIL return, so it can never re-admit a retracted /
    predatory / non-peer-reviewed / low-tier source (INV-3 evidence-positive only).

    Over-engineering guard (§3.2): ≤4 predicates over already-fetched fields, no
    credibility ontology. T2/T3 host predicates (reputable newsroom / issuer-primary)
    are a labelled TODO — the SHAPE ships now; a new kind is a row, not a branch.
    """
    # T1-scholarly: the SAME predicate the scope classifier already trusts, CLASSIFIER-
    # CONFIRMED. NOT "DOI alone" — a bare/preprint/dataset DOI classifies to a non-journal
    # genre and does NOT earn T1 (it stays UNKNOWN); only a positive peer-reviewed-journal
    # verdict promotes (M8).
    try:
        ok, _basis = _has_doi_or_journal_credential(row, url)
    except Exception:  # noqa: BLE001 — fail-open: a fault never rescues a row
        ok = False
    if ok:
        return (_TIER_T1, "peer_reviewed_journal")
    # T1-government / primary authority (DOI-independent, universal).
    if _official_gov_host(url):
        return (_TIER_T1, "government")
    # TODO(v2, data-not-branch): T2 reputable-newsroom (author+method) -> ("T2","news")
    # and T3 issuer-primary -> ("T3","press_release"/"corporate"), gated on kind∈allowed.
    # Deferred per §3.2 until the host predicates are cheaply available from the
    # existing facet/tier classifier — adding each is ONE row here, never a new branch.
    return None


# ---------------------------------------------------------------------------
# GENERALIZED Fix 5(d): row -> normalized source-KIND token (for kind-match
# ordering + adequacy). REUSES the existing document-genre classifier — DATA, not
# a new ontology. Maps a ``DocumentType`` genre to the free-text kind vocabulary
# the contract's ``allowed_source_kinds`` uses ("journal" / "news" / "government"
# / "press release" / ...). Pure / offline / fail-open (UNKNOWN on any fault).
# ---------------------------------------------------------------------------

# DocumentType.value -> canonical kind token. Extend as DATA; never a control literal.
_DOCTYPE_TO_KIND: dict[str, str] = {
    "JOURNAL_ARTICLE": "journal",
    "REVIEW_ARTICLE": "journal",
    "PREPRINT": "preprint",
    "CONFERENCE_PAPER": "conference",
    "WORKING_PAPER": "working_paper",
    "BOOK": "book",
    "REPORT": "report",
    "NEWS": "news",
    "PRESS_RELEASE": "press_release",
    "BLOG_COMMENTARY": "blog",
    "ENCYCLOPEDIA": "encyclopedia",
    "DATASET": "dataset",
    "UGC": "ugc",
    "PREDATORY_OA_JOURNAL": "predatory",
    "UNKNOWN": "",
}

# Normalize a free-text allowed/excluded kind token (contract vocabulary) to the
# canonical set above so "peer-reviewed journals" and "journal articles" both match
# the "journal" genre. DATA table; the anti-hardcode grep excludes this module's
# registries. Keys are substrings tested against the lowercased contract token.
_KIND_SYNONYM_SUBSTR: tuple[tuple[str, str], ...] = (
    ("journal", "journal"), ("peer", "journal"), ("scholarly", "journal"),
    ("academic", "journal"), ("news", "news"), ("wire", "news"),
    ("press release", "press_release"), ("press-release", "press_release"),
    ("gov", "government"), ("government", "government"), ("official", "government"),
    ("statute", "government"), ("regulat", "government"),
    ("blog", "blog"), ("report", "report"), ("white paper", "report"),
    ("whitepaper", "report"), ("book", "book"), ("preprint", "preprint"),
    ("dataset", "dataset"), ("conference", "conference"), ("proceeding", "conference"),
)


def normalize_kind_token(token: str) -> str:
    """Canonicalize a free-text contract source-kind token to the genre vocabulary."""
    t = str(token or "").strip().lower()
    if not t:
        return ""
    for sub, canon in _KIND_SYNONYM_SUBSTR:
        if sub in t:
            return canon
    return t  # unknown token passes through verbatim (still matchable exactly)


def normalize_kinds(tokens: "Any") -> frozenset[str]:
    """Canonicalize an iterable of contract kind tokens (empty => empty frozenset)."""
    out: set[str] = set()
    for tok in (tokens or []):
        canon = normalize_kind_token(str(tok))
        if canon:
            out.add(canon)
    return frozenset(out)


def classified_kind(row: Any) -> str:
    """Map a fetched row to its canonical source-KIND token (or "" when unknown).

    REUSES ``classify_document_type`` (the existing genre classifier) — no new
    ontology. Fail-open: any classifier fault yields "" (an UNKNOWN kind never
    counts toward adequacy and never wins a kind-match). Adequacy counts the KIND
    of a row, NEVER a DOI/journal shortcut."""
    try:
        from src.polaris_graph.retrieval.document_type_classifier import (
            classify_document_type,
        )
        url = _row_url(row)
        dt, _basis = classify_document_type(
            openalex_publication_type=str(_row_get(row, "openalex_publication_type", "") or ""),
            openalex_source_type=str(_row_get(row, "openalex_source_type", "") or ""),
            openalex_is_peer_reviewed=_row_get(row, "openalex_is_peer_reviewed", None),
            source_class=str(_row_get(row, "source_class", "") or ""),
            url=url,
            title=str(_row_get(row, "title", "") or ""),
            doi=str(_row_get(row, "doi", "") or ""),
        )
        return _DOCTYPE_TO_KIND.get(getattr(dt, "value", ""), "")
    except Exception:  # noqa: BLE001 — fail-open: an UNKNOWN kind never counts
        return ""


def score_source_quality(
    row: Any,
    *,
    allowed_kinds: frozenset[str] = frozenset(),
    excluded_kinds: frozenset[str] = frozenset(),
) -> tuple[str, float, str]:
    """Deterministic, domain-neutral quality verdict for one fetched row.

    Returns ``(verdict, weight, basis)``:
      * ``verdict`` in {PASS, FAIL, UNKNOWN} for a HARD "only high-quality" predicate.
        PASS = positively-evidenced high quality; FAIL = positively-evidenced low
        quality (retracted / predatory host / low tier / non-peer-reviewed shell);
        UNKNOWN = no usable quality metadata (fail-CLOSED at the hard seam).
      * ``weight`` in (0, 1] — the SOFT-preference demote (never 0; order-not-drop).
      * ``basis`` — the rule + evidence that fired (for the receipt).

    "journal-shaped" is NOT peer-reviewed: an ``is_peer_reviewed`` flag that is
    explicitly False (fetched, not merely absent) is a FAIL even if the venue looks
    journal-like. A retraction is always a FAIL. Absent metadata is UNKNOWN.

    ``allowed_kinds`` / ``excluded_kinds`` (both default EMPTY => byte-identical to
    every existing caller) carry the contract's normalized source-kind policy so the
    GENERALIZED signal->tier resolver can PASS a T2/T3 credential iff its kind is
    contract-allowed (a T1 credential PASSes unconditionally). NO LLM here.
    """
    # 1) retraction — always disqualifying, highest precedence.
    if bool(_row_get(row, "is_retracted", False)):
        return FAIL, 0.05, "retracted (is_retracted=True)"

    url = _row_url(row)
    # 2) predatory / OJS-mill host — journal-shaped but not peer-reviewed.
    if _predatory_host(url):
        return FAIL, 0.1, f"predatory/OJS-mill host heuristic matched ({url})"

    tier = str(_row_get(row, "tier", "") or "").strip().upper()
    pr = _row_get(row, "is_peer_reviewed", None)  # None = not fetched (absent)

    # 3) explicit peer-review evidence.
    if pr is True and tier in _HIGH_QUALITY_TIERS:
        return PASS, 1.0, f"peer_reviewed=True AND tier={tier} (high-quality band)"
    if pr is False:
        # journal-SHAPED but explicitly NOT peer-reviewed -> not high quality.
        return FAIL, 0.2, f"is_peer_reviewed=False (journal-shaped != peer-reviewed); tier={tier or 'UNKNOWN'}"

    # 4) tier-only evidence (peer-review flag absent).
    if tier in _HIGH_QUALITY_TIERS:
        return PASS, 1.0, f"tier={tier} (high-quality band; peer_reviewed flag absent)"
    if tier in _LOW_QUALITY_TIERS:
        return FAIL, 0.3, f"tier={tier} (low-quality band: industry/news/blog/stub)"

    # 4.5) GENERALIZED Fix 5(b): DETERMINISTIC signal->(tier,kind) RESOLVER before the
    # UNKNOWN fail-closed. EVERY FAIL path (retraction / predatory host / is_peer_reviewed=False /
    # low tier) has already returned above, and so has every positive PASS — so a row reaching
    # here has NO negative evidence. If a positive credential resolves to a tier, that is POSITIVE
    # evidence of quality — PASS rather than fail-close it out (the 41%-UNKNOWN over-mask).
    # EVIDENCE-POSITIVE ONLY (INV-3): this block contains ONLY ``return PASS``; it can NEVER
    # re-admit a FAIL row (they returned above), only rescue UNKNOWN rows with a positive signal.
    #   T1 (authoritative-universal: peer-reviewed scholarly OR gov/primary) -> PASS for ANY contract.
    #   T2/T3 -> PASS iff the credential's kind ∈ allowed_kinds and ∉ excluded_kinds (contract wants it).
    # "journal => PASS" is JUST the T1-scholarly row. DOI-alone is NOT T1 (the predicate rejects preprints).
    _sig = _positive_signal_tier(row, url)
    if _sig is not None:
        _sig_tier, _sig_kind = _sig
        if _sig_tier == _TIER_T1:
            return PASS, 1.0, f"signal->tier resolver: {_sig_tier} kind={_sig_kind} (authoritative-universal, evidence-positive)"
        if _sig_kind in allowed_kinds and _sig_kind not in excluded_kinds:
            return PASS, 1.0, f"signal->tier resolver: {_sig_tier} kind={_sig_kind} ∈ allowed (contract wants this kind, evidence-positive)"
        # T2/T3 whose kind is not contract-allowed falls through to the existing UNKNOWN path.

    # 5) content-shell degradation is a quality-of-content negative but NOT a hard
    #    quality FAIL on its own — it is UNKNOWN (fail-closed under hard) with a demote.
    if (bool(_row_get(row, "content_starved", False))
            or bool(_row_get(row, "landing_page", False))
            or bool(_row_get(row, "citation_metadata_shell", False))):
        return UNKNOWN, 0.4, "content shell/starved (no quality metadata; fail-closed under hard)"

    # 6) no usable quality metadata at all -> UNKNOWN (fail-CLOSED under a hard
    #    "only high-quality"; a soft preference keeps it at neutral weight).
    return UNKNOWN, 0.6, f"no quality metadata (tier={tier or 'UNKNOWN'}, peer_reviewed absent) — fail-closed under hard"


# ---------------------------------------------------------------------------
# The eligibility pass (item 2 + item 3 + item 4 in ONE place)
# ---------------------------------------------------------------------------


def build_quality_eligibility(
    policy: Any,
    evidence_rows: "list[Any] | None",
    *,
    quality_term_id: str = "scope.source_quality",
) -> EligibilityPlan:
    """Apply the contract's quality predicate to a billed candidate set.

    ``policy`` is a :class:`RetrievalPolicy` (duck-typed: reads ``quality_profile``,
    ``predicate_force['quality_profile']``, ``contract_hash``). When no quality
    profile is set, returns an EMPTY plan (no-op, byte-identical).

    HARD "only high-quality": a row scoring FAIL or UNKNOWN is added to
    ``eligibility_excluded_ids`` (fail-closed on UNKNOWN — never silently relaxed)
    and carries a FAIL/UNKNOWN receipt; a PASS row carries a pass receipt. SOFT
    preference: NO exclusion — only a demote weight in ``url_to_quality_weight`` and
    a receipt, so ranking prefers high quality without starving the menu.
    """
    plan = EligibilityPlan()
    quality_profile = getattr(policy, "quality_profile", None)
    if not _is_high_quality_request(quality_profile):
        return plan  # no hard/soft quality predicate -> byte-identical no-op

    force = (getattr(policy, "predicate_force", {}) or {}).get("quality_profile", "soft")
    is_hard = str(force).strip().lower() == "hard"
    contract_hash = str(getattr(policy, "contract_hash", "") or "")

    # GENERALIZED Fix 5(b): thread the contract's normalized source-kind policy so the
    # signal->tier resolver can PASS a contract-allowed T2/T3 credential (T1 is unconditional).
    # Empty (no source-kind clause) => byte-identical to the pre-generalization behavior.
    _allowed_kinds = normalize_kinds(getattr(policy, "allowed_source_kinds", None))
    _excluded_kinds = normalize_kinds(getattr(policy, "excluded_source_kinds", None))

    for row in list(evidence_rows or []):
        url = _row_url(row)
        if not url:
            continue
        verdict, weight, basis = score_source_quality(
            row, allowed_kinds=_allowed_kinds, excluded_kinds=_excluded_kinds,
        )
        plan.receipts.append(SourceReceipt(
            contract_hash=contract_hash,
            term_id=quality_term_id,
            source_id=url,
            stage=STAGE_QUALITY,
            verdict=verdict,
            basis=basis,
        ))
        if is_hard:
            # HARD: FAIL and UNKNOWN are both out of the citable menu (fail-closed).
            if verdict in (FAIL, UNKNOWN):
                plan.eligibility_excluded_ids.add(url)
                plan.excluded_records.append({
                    "source_id": url, "stage": STAGE_QUALITY,
                    "verdict": verdict, "basis": basis, "force": "hard",
                })
        else:
            # SOFT: order-not-drop. A FAIL/UNKNOWN demotes; never excluded.
            if weight < 1.0:
                plan.url_to_quality_weight[url] = weight
    return plan


# ---------------------------------------------------------------------------
# GENERALIZED Fix 5 — source-KIND eligibility + corpus adequacy + acquisition
# receipt (§3.5). Replaces the RETIRED ``journal_only_filter.py`` hard mask: a hard
# kind restriction NEVER masks a frozen corpus — it arms a real nonmatching-mask
# ONLY behind corpus-adequacy AND a matching acquisition receipt; otherwise it
# degrades to a visible PREFERENCE (reorder) plus a disclosure line. This is the
# C2-safe replacement for the fail-closed corpus filter.
# ---------------------------------------------------------------------------

# Default in-scope-KIND adequacy floor (distinct usable in-scope rows). A hard kind
# restriction may arm a mask only when the corpus is provably adequate at/above this.
DEFAULT_SOURCE_KIND_MIN_ADEQUATE = 25


def corpus_kind_adequacy(
    rows: "list[Any] | None",
    allowed_kinds: frozenset[str],
    *,
    min_rows: int = DEFAULT_SOURCE_KIND_MIN_ADEQUATE,
) -> tuple[bool, int]:
    """Count DISTINCT usable in-scope-KIND rows and test the adequacy floor.

    Adequacy counts the KIND of a row (``classified_kind``), NEVER a DOI/journal
    shortcut (§3 3/3). A row counts iff its kind ∈ ``allowed_kinds`` AND it does not
    score a quality FAIL (a predatory/retracted in-scope row is not usable evidence).
    Returns ``(adequate, n)`` where ``adequate = n >= min_rows``. Empty allowed => not
    adequate at 0 (the caller never arms a mask without an allowed set)."""
    if not allowed_kinds:
        return (False, 0)
    seen: set[str] = set()
    for r in list(rows or []):
        if classified_kind(r) not in allowed_kinds:
            continue
        if score_source_quality(r, allowed_kinds=allowed_kinds)[0] == FAIL:
            continue
        url = _row_url(r)
        if url:
            seen.add(url)
    n = len(seen)
    return (n >= min_rows, n)


def _acquisition_receipt_matches(policy: Any, acquisition_receipt: "Any") -> bool:
    """True iff the corpus was fetched UNDER this contract's kind lanes (Codex receipt).

    The strongest available C2 guard against the 997->131 frozen-corpus replay: a
    hard kind mask arms only when the acquisition receipt's ``contract_hash`` matches
    the policy's ``contract_hash``. A frozen/replayed unscoped corpus (no receipt, or
    a mismatched hash) therefore NEVER arms the mask — it degrades to prefer+disclose.
    Lightweight: a single hash equality on the already-stamped receipt."""
    want = str(getattr(policy, "contract_hash", "") or "").strip()
    if not want:
        return False
    got = ""
    if isinstance(acquisition_receipt, Mapping):
        got = str(acquisition_receipt.get("contract_hash") or "").strip()
    else:
        got = str(getattr(acquisition_receipt, "contract_hash", "") or "").strip()
    return bool(got) and got == want


@dataclass
class SourceKindPlan:
    """Outcome of source-KIND eligibility over one billed candidate set.

    ``armed`` True iff a HARD nonmatching-mask fired (adequate AND receipt-matched):
    ``eligibility_excluded_ids`` then masks out-of-scope-kind rows from the citable
    menu. When NOT armed, ``eligibility_excluded_ids`` is EMPTY and the caller applies
    only the kind-match REORDER (prefer) plus ``disclosure`` (the degrade line)."""

    armed: bool = False
    eligibility_excluded_ids: set[str] = field(default_factory=set)
    receipts: list[SourceReceipt] = field(default_factory=list)
    excluded_records: list[dict[str, Any]] = field(default_factory=list)
    disclosure: str = ""
    in_scope_count: int = 0


def build_source_kind_eligibility(
    policy: Any,
    rows: "list[Any] | None",
    acquisition_receipt: "Any" = None,
    *,
    min_rows: int = DEFAULT_SOURCE_KIND_MIN_ADEQUATE,
    hard_enabled: bool = False,
    source_kind_term_id: str = "scope.source_types",
) -> SourceKindPlan:
    """Source-KIND eligibility (C2-safe replacement for the retired journal-only mask).

    ORDER OF PRECEDENCE (§3.5):
      1. EXCLUSIONS ALWAYS WIN FIRST — every excluded-kind row is masked, monotonically;
         a PASS/weight can NEVER re-include an excluded kind. Exclusions are never
         adequacy-checked and never receipt-gated.
      2. HARD allowed_source_kinds arms a nonmatching-mask ONLY when ALL of:
         ``hard_enabled`` (PG_SOURCE_RESTRICTION_HARD) AND the term force is hard AND
         the corpus is adequate (``corpus_kind_adequacy`` >= ``min_rows``) AND the
         acquisition receipt matches. Otherwise it DOWNGRADES to prefer (no exclusion)
         and records an Assumption + SourceReceipt basis + a disclosure line.
      3. Empty allowed AND empty excluded => EMPTY plan (byte-identical no-op).

    Counts in-scope-KIND rows, never DOI/journal rows. All upstream of the frozen verifier."""
    plan = SourceKindPlan()
    allowed = normalize_kinds(getattr(policy, "allowed_source_kinds", None))
    excluded = normalize_kinds(getattr(policy, "excluded_source_kinds", None))
    contract_hash = str(getattr(policy, "contract_hash", "") or "")
    row_list = list(rows or [])
    if not allowed and not excluded:
        return plan  # no source-kind clause -> byte-identical no-op

    # (1) EXCLUSIONS ALWAYS WIN — monotonic union, never re-included, never gated.
    for r in row_list:
        url = _row_url(r)
        if not url:
            continue
        k = classified_kind(r)
        if k and k in excluded:
            plan.eligibility_excluded_ids.add(url)
            plan.excluded_records.append({
                "source_id": url, "stage": STAGE_QUALITY,
                "verdict": FAIL, "basis": f"source-kind exclusion: kind={k} ∈ excluded (always wins)",
                "force": "hard",
            })
            plan.receipts.append(SourceReceipt(
                contract_hash=contract_hash, term_id="scope.excluded_source_kinds",
                source_id=url, stage=STAGE_QUALITY, verdict=FAIL,
                basis=f"excluded source-kind {k} masked (exclusion always wins)",
            ))

    if not allowed:
        return plan  # exclusion-only contract: mask done, no allow-mask to arm

    # (2) HARD allowed-kind nonmatching-mask — arms ONLY behind adequacy + receipt.
    force = (getattr(policy, "predicate_force", {}) or {}).get("allowed_source_kinds", "soft")
    term_is_hard = str(force).strip().lower() == "hard"
    adequate, n = corpus_kind_adequacy(row_list, allowed, min_rows=min_rows)
    plan.in_scope_count = n
    receipt_ok = _acquisition_receipt_matches(policy, acquisition_receipt)
    arm_hard = bool(hard_enabled and term_is_hard and adequate and receipt_ok)

    if arm_hard:
        plan.armed = True
        for r in row_list:
            url = _row_url(r)
            if not url or url in plan.eligibility_excluded_ids:
                continue
            k = classified_kind(r)
            if k not in allowed:
                plan.eligibility_excluded_ids.add(url)
                plan.excluded_records.append({
                    "source_id": url, "stage": STAGE_QUALITY,
                    "verdict": FAIL, "basis": f"hard source-kind mask: kind={k or 'UNKNOWN'} ∉ allowed {sorted(allowed)}",
                    "force": "hard",
                })
                plan.receipts.append(SourceReceipt(
                    contract_hash=contract_hash, term_id=source_kind_term_id,
                    source_id=url, stage=STAGE_QUALITY, verdict=FAIL,
                    basis=f"out-of-scope kind {k or 'UNKNOWN'} masked (adequate n={n}, receipt-matched)",
                ))
    else:
        # DEGRADE to prefer + disclosure (C2: never mask a frozen/under-scoped corpus).
        _why = []
        if not hard_enabled:
            _why.append("PG_SOURCE_RESTRICTION_HARD off")
        if not term_is_hard:
            _why.append("term force is soft")
        if not adequate:
            _why.append(f"only {n} in-scope sources (< {min_rows} adequacy floor)")
        if not receipt_ok:
            _why.append("no matching acquisition receipt")
        plan.disclosure = (
            f"Scope note: the prompt restricts sources to {sorted(allowed)}; "
            f"{'; '.join(_why)} — in-scope sources were prioritized rather than "
            f"exclusively enforced."
        )
        plan.receipts.append(SourceReceipt(
            contract_hash=contract_hash, term_id=source_kind_term_id,
            source_id="", stage=STAGE_QUALITY, verdict=UNKNOWN,
            basis=f"hard source-kind restriction DEGRADED to prefer: {'; '.join(_why)} (n={n})",
        ))
    return plan


def build_topicality_eligibility(
    evidence_rows: "list[Any] | None",
    *,
    objective: str,
    thread_queries: "list[str] | None" = None,
    floor: float,
    scorer: Callable[[str, "list[str] | None", list[dict[str, Any]]], "dict[int, float] | None"],
    contract_hash: str = "",
    topicality_term_id: str = "topicality",
    is_hard: bool = True,
    hard_floor: "float | None" = None,
    soft_floor: "float | None" = None,
) -> EligibilityPlan:
    """Post-fetch topical eligibility against the CLEAN objective + owning thread.

    Reuses the SAME embedding-cosine scorer live retrieval uses pre-fetch
    (``evidence_selector._semantic_relevance_scores``), but as a CONTRACT-AWARE
    ELIGIBILITY stage on the FETCHED body (statement + direct_quote), not a prefetch
    reorder. Confirmed off-topic (score < ``floor``) is quarantined from the citable
    menu (HARD) / down-ranked (SOFT); uncertain (>= floor) stays. A ``None`` score
    (embedder unavailable) is UNKNOWN — fail-OPEN for topicality (we never quarantine
    a source we could not score; topicality is not a stated user prohibition).

    FIX 5(c) — TWO-TIER topicality (only when ``is_hard`` AND ``hard_floor`` is set and
    ``0 <= hard_floor < floor``): confirmed junk (score < ``hard_floor``) HARD-quarantines
    as before, but the on-topic-ADJACENT band (``hard_floor <= score < floor``) is NOT
    dropped — it is SOFT-demoted (a weight, receipt verdict ``FAIL`` but no exclusion), so
    the 0.15–0.30 band that was the ACTUAL over-mask stays in the citable menu, ranked down.
    ``hard_floor=None`` (default) is byte-identical to the single-floor behavior.
    ``soft_floor`` (generalized alias, default ``None``) supplies the same quarantine
    boundary when ``hard_floor`` is not given; ``hard_floor`` wins if both are set, and
    ``soft_floor=None`` with ``hard_floor=None`` is byte-identical to the single floor.

    ``objective`` is the clean research objective (contract objective / clean
    question), NOT the instruction-laden prompt. ``thread_queries`` are the owning
    thread's sub-queries (the per-subquery max clears a focused facet).
    """
    # GENERALIZED Fix 5(c): the quarantine boundary may be supplied as ``hard_floor``
    # (legacy) OR ``soft_floor`` (generalized alias — the boundary at/above which a
    # below-``floor`` row is SOFT-DEMOTED rather than quarantined, even under a hard
    # predicate). ``hard_floor`` wins if both are set; ``soft_floor=None`` AND
    # ``hard_floor=None`` (defaults) => single-floor path (byte-identical).
    _qfloor = hard_floor if hard_floor is not None else soft_floor
    # Two-tier arms ONLY under a hard predicate with a valid quarantine floor strictly
    # below the pass floor; anything else collapses to the single-floor path (byte-identical).
    _two_tier = (
        is_hard and _qfloor is not None and 0.0 <= float(_qfloor) < float(floor)
    )
    plan = EligibilityPlan()
    rows = list(evidence_rows or [])
    if not rows or not (objective or "").strip():
        return plan

    row_dicts = [{"statement": _row_text(r), "direct_quote": ""} for r in rows]
    try:
        score_map = scorer(objective, list(thread_queries or []), row_dicts)
    except Exception:  # noqa: BLE001 — a scorer fault is UNKNOWN (fail-open), never a crash
        score_map = None
    if score_map is None:
        # embedder unavailable -> cannot score -> UNKNOWN, fail-OPEN (no quarantine).
        for r in rows:
            url = _row_url(r)
            if url:
                plan.receipts.append(SourceReceipt(
                    contract_hash=contract_hash, term_id=topicality_term_id,
                    source_id=url, stage=STAGE_TOPICALITY, verdict=UNKNOWN,
                    basis="semantic scorer unavailable (fail-open, not quarantined)",
                ))
        return plan

    for idx, r in enumerate(rows):
        url = _row_url(r)
        if not url:
            continue
        score = float(score_map.get(idx, 0.0))
        if score < floor:
            verdict = FAIL
            # FIX 5(c): under two-tier, only score < _qfloor is CONFIRMED off-topic and
            # HARD-quarantined; the _qfloor <= score < floor BAND is on-topic-adjacent and
            # SOFT-demoted (kept in the menu, ranked down) even on a hard predicate.
            _quarantine = is_hard and (not _two_tier or score < float(_qfloor))
            if _two_tier and not _quarantine:
                basis = (f"topicality cosine {score:.3f} in soft band "
                         f"[{float(_qfloor):.3f}, {floor:.3f}) (on-topic-adjacent; demoted)")
            else:
                basis = f"topicality cosine {score:.3f} < floor {floor:.3f} (confirmed off-topic)"
            if _quarantine:
                plan.eligibility_excluded_ids.add(url)
                plan.excluded_records.append({
                    "source_id": url, "stage": STAGE_TOPICALITY,
                    "verdict": verdict, "basis": basis, "force": "hard",
                })
            else:
                plan.url_to_quality_weight[url] = max(0.05, score)
        else:
            verdict = PASS
            basis = f"topicality cosine {score:.3f} >= floor {floor:.3f}"
        plan.receipts.append(SourceReceipt(
            contract_hash=contract_hash, term_id=topicality_term_id,
            source_id=url, stage=STAGE_TOPICALITY, verdict=verdict, basis=basis,
        ))
    return plan
