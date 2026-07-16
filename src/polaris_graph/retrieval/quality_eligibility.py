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
from typing import Any, Callable, Optional
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


def score_source_quality(row: Any) -> tuple[str, float, str]:
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

    for row in list(evidence_rows or []):
        url = _row_url(row)
        if not url:
            continue
        verdict, weight, basis = score_source_quality(row)
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
) -> EligibilityPlan:
    """Post-fetch topical eligibility against the CLEAN objective + owning thread.

    Reuses the SAME embedding-cosine scorer live retrieval uses pre-fetch
    (``evidence_selector._semantic_relevance_scores``), but as a CONTRACT-AWARE
    ELIGIBILITY stage on the FETCHED body (statement + direct_quote), not a prefetch
    reorder. Confirmed off-topic (score < ``floor``) is quarantined from the citable
    menu (HARD) / down-ranked (SOFT); uncertain (>= floor) stays. A ``None`` score
    (embedder unavailable) is UNKNOWN — fail-OPEN for topicality (we never quarantine
    a source we could not score; topicality is not a stated user prohibition).

    ``objective`` is the clean research objective (contract objective / clean
    question), NOT the instruction-laden prompt. ``thread_queries`` are the owning
    thread's sub-queries (the per-subquery max clears a focused facet).
    """
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
            basis = f"topicality cosine {score:.3f} < floor {floor:.3f} (confirmed off-topic)"
            if is_hard:
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
