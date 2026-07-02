"""I-arch-007 ITEM 2 (#1264) — BREADTH: weighted unbound-SUPPORTS enrichment selection.

THE PROBLEM (the 485-in / ~13-cited collapse): the V30 contract render universe is the
5 required contract entities + a handful of LLM-planner enrichment picks. On a FULLY
SUCCESSFUL credibility pass that weighted + basketed hundreds of sources, the ~437 sources
that are NOT bound to a contract ``v30_entity_id`` are never *offered* to any section — a
purely STRUCTURAL funnel (it fires even when nothing times out). This module surfaces those
unbound-but-span-verified SUPPORTS sources into ONE extra legacy (field-agnostic) section so
they flow through the UNCHANGED ``_run_section`` -> ``strict_verify`` path.

§-1.3 DNA — WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP:
  * WEIGHT, DON'T FILTER (I-arch-011 B18, the keystone): candidates are ORDERED by
    relevance-to-question THEN basket ``weight_mass`` (priority of consideration). There is NO cap /
    target / top-N / FLOOR DROP — the FULL surviving list is offered. KEEP-ALL-AND-SORT-BELOW-FLOOR-
    LAST: a member whose source row scores BELOW ``PG_RELEVANCE_FLOOR`` is NOT excluded — it is KEPT
    and sorted LAST (a below-floor ORDERING demotion, never a drop), exactly the way the retrieval
    pool itself down-weights a below-floor row under the redesign (evidence_selector.py:2066-2070,
    ``kept = list(scored)``). The pre-I-arch-011 code RE-IMPOSED a hard ``selection_relevance < 0.30``
    DROP here — the SECTION-1.3-FORBIDDEN filter-and-cap anti-pattern the selector docstring
    (evidence_selector.py:1944-1953) explicitly forbids, which killed 729/746 unbound SUPPORTS so the
    enrichment appended NOTHING. That drop is REMOVED. ``below_floor_count`` is now pure TELEMETRY
    (how many kept rows sit below the floor), never an exclusion.
  * CONSOLIDATE, DON'T DROP: the members come straight from the already-computed claim baskets
    (``ClaimBasket.supporting_members``) — the consolidated multi-source groups.
  * BASKET FAITHFULNESS: a member is offered ONLY if its OWN isolated ``span_verdict`` is
    ``"SUPPORTS"`` (computed by the credibility pass at credibility_pass.py:442-457). It is then
    re-verified against its own span by the section's UNCHANGED ``strict_verify``. Breadth
    EMERGES from how many survive that gate — it is never forced.

RECONCILIATION WITH RETRIEVAL P0-A6 (evidence_selector.py:2036-2070): the retrieval POOL
WEIGHTS-not-FILTERS — under the default redesign a below-floor row is KEPT and down-weighted in the
pool, never hard-dropped (P0-A6 is UNTOUCHED). The breadth ENRICHMENT section now behaves
IDENTICALLY: a below-floor unbound SUPPORTS member is KEPT and sorted LAST, never dropped — the
relevance floor is an ORDERING weight at the surfacing boundary, not a re-introduction of the
retrieval filter P0-A6 removed. The ONLY hard gate remains the faithfulness engine (strict_verify /
NLI / 4-role / span-grounding), which is untouched.

FAITHFULNESS-NEUTRALITY: this module only READS already-computed state and builds a candidate
``SectionPlan``. It moves NO strict_verify / NLI / 4-role D8 / span-grounding / section-floor /
sentinel threshold. The master flag defaults OFF (=> empty selection => byte-identical) and a
degraded pass (``credibility_analysis is None``) also yields an empty selection (byte-identical).
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

# LAW VI: env-overridable, default OFF (unset => byte-identical legacy render).
_ENV_BREADTH_ENRICHMENT = "PG_BREADTH_ENRICHMENT_ENABLED"

# A NON-contract title => ``is_contract_section()`` (an isinstance(ContractSectionPlanExt) check)
# is False => the section dispatches through ``_run_legacy_bounded`` -> field-agnostic
# ``_run_section`` -> the same three-stream strict_verify the contract sentences use.
_ENRICHMENT_TITLE = "Corroborated Weighted Findings"
_ENRICHMENT_FOCUS = (
    "Additional independently span-verified findings drawn from the weighted source corpus that "
    "were not bound to a contract entity. Each sentence must survive the same strict_verify gate as "
    "every other section; unsupported material is dropped, never padded."
)

_SUPPORTS = "SUPPORTS"

# The per-row topicality sidecar the retrieval relevance gate stamps (evidence_selector.py:2128)
# and finding_dedup reads (finding_dedup.py:212). It is THE existing relevance standard.
_RELEVANCE_FIELD = "selection_relevance"

# Constant sentinel for the relevance ORDERING key when a row carries no usable relevance score.
# Using a constant (not the parsed value, not 0.0) ensures a pool of all-missing-relevance rows
# ties on the relevance key, so the weight_mass tiebreak reproduces today's pure weight-desc order.
_MISSING_RELEVANCE_SORT_KEY = 0.0


def _row_relevance(row: Any) -> float | None:
    """The row's ``selection_relevance`` topicality score, or ``None`` when not usable.

    Returns ``None`` (=> relevance-gate FALLBACK = keep, ordering = sentinel) when the row is
    missing, has no ``selection_relevance``, or carries an unparseable value. Deliberately NOT
    ``float(row.get(field, 0.0) or 0.0)`` (finding_dedup's coercion): that maps a missing/None
    score to 0.0, which would push it below any floor and wrongly EXCLUDE a member whose pool
    membership already implies the retrieval relevance floor passed once.
    """
    if not isinstance(row, dict):
        return None
    raw = row.get(_RELEVANCE_FIELD)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _relevance_sort_key(relevance: float | None) -> float:
    """Relevance value for the ORDERING key; the constant sentinel when relevance is unknown."""
    return _MISSING_RELEVANCE_SORT_KEY if relevance is None else relevance


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) DEFER-1 — off-topic CITE-SURFACE suppression.
#
# drb_72 cited OFF-TOPIC sources (B1 supply-chain blogs, B2 Russian cosmetics, B3
# recycling journal, B4 post-merger M&A) as numbered findings in the breadth
# "Corroborated Weighted Findings" section. The keystone (I-arch-011 B18) correctly
# forbids the lexical ``selection_relevance < floor`` DROP (it killed 729/746 real
# unbound SUPPORTS and also suppressed REAL on-topic low-cred sources). So the
# discriminator is NOT the noisy score — it is the SEMANTIC confirmed-OFF verdict
# the topic gate / W2 content-relevance judge already produced and stamped on the
# row (``topic_offtopic_demoted`` / ``content_relevance_label``). A confirmed
# "this is about cosmetics, not AI labor" verdict is, by definition, not a
# corroborator of an AI-labor claim, so withholding it from CITATION is not a
# §-1.3 hard-drop: the source STAYS in evidence_pool + the credibility disclosure
# (kept-and-disclosed). Gated default-ON; ``PG_OFFTOPIC_CITE_SUPPRESS=0`` restores
# the byte-identical legacy cite-surface.
_CONFIRMED_OFFTOPIC_LABELS = frozenset({"demoted", "escalated_demoted"})


def offtopic_cite_suppress_enabled() -> bool:
    """Kill-switch ``PG_OFFTOPIC_CITE_SUPPRESS`` (default ON). OFF => the cite
    surface is byte-identical to the legacy keep-all-and-cite behaviour."""
    return os.environ.get("PG_OFFTOPIC_CITE_SUPPRESS", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def _is_confirmed_offtopic(row: Any) -> bool:
    """True iff a SEMANTIC judge confirmed this source is OFF-topic.

    Keys ONLY on the topic-gate sidecar (``topic_offtopic_demoted is True``) OR the
    W2 content-relevance LABEL (``content_relevance_label`` in
    {``demoted``, ``escalated_demoted``}) — NEVER on the noisy lexical/embedding
    ``selection_relevance`` score (that is the §-1.3-banned keystone DROP). A
    missing/absent label is keep-neutral (NOT off-topic): an unjudged or
    judged-RELEVANT row is never suppressed."""
    if not isinstance(row, dict):
        return False
    if row.get("topic_offtopic_demoted") is True:
        return True
    label = str(row.get("content_relevance_label", "") or "").strip().lower()
    return label in _CONFIRMED_OFFTOPIC_LABELS


def breadth_enrichment_enabled() -> bool:
    """True iff the default-OFF master flag is explicitly enabled (LAW VI)."""
    return os.environ.get(_ENV_BREADTH_ENRICHMENT, "").strip().lower() in (
        "1", "true", "on", "yes",
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344 follow-on, M5) — PROMOTION-ELIGIBILITY PARTITION.
#
# drb_72 let near-zero-weight, single-origin, non-journal sources anchor standalone
# numbered findings exactly like a corroborated NEJM/AEA source: cognifit blog
# (weight 0.03), inboundlogistics (0.00), procom (0.01), protolabs (0.00), a wsu
# blog (0.06), an IZA working paper (0.05), a predatory 10.5555 DOI (0.00), and an
# off-topic 10.26163 DOI (0.00). Each is on-topic enough to span-verify (the body
# sentence is verbatim from the source span, so it self-entails and PASSES the
# UNCHANGED strict_verify), yet carries ~0 credibility weight and is corroborated by
# nobody. Whether a source EARNED a top-level cited claim is a SURFACE-placement
# (credibility / corroboration) decision, NOT a grounding decision — it is handled
# here at the cite surface, NEVER in the frozen faithfulness engine.
#
# §-1.3 — WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP: this is a ROUTING decision,
# not a removal. A member is PROMOTED (earns a standalone cited claim) if ANY of:
#   * corroboration >= K distinct verified origins (the CONSOLIDATE leg), OR
#   * credibility weight >= W (the WEIGHT leg), OR
#   * its host is a recognized peer-reviewed journal venue (over-demotion guard).
# A single-origin AND below-W AND non-journal member is ROUTED to ``disclosed_only``:
# KEPT in evidence_pool + the credibility disclosure + a dedicated report block, but
# NOT promoted to a standalone numbered finding. Nothing is dropped; conservation holds
# (promoted UNION disclosed_only == the original ordered list). The faithfulness engine
# (strict_verify / NLI / 4-role D8 / span-grounding / provenance) is untouched — weight
# and corroboration are credibility judgments, never a faithfulness gate. The OR-with-
# corroboration leg IS the §-1.3 CONSOLIDATE principle (any source another agrees with is
# rescued). Gated default-ON; ``PG_CWF_PROMOTION_ELIGIBILITY=0`` fails OPEN to promote-all
# => the partition is byte-identical to the legacy keep-all-and-cite selection.
_ENV_PROMOTION = "PG_CWF_PROMOTION_ELIGIBILITY"                 # default ON
_ENV_PROMOTION_MIN_WEIGHT = "PG_CWF_PROMOTION_MIN_WEIGHT"       # LAW VI override (default below)
_ENV_PROMOTION_MIN_CORROBORATION = "PG_CWF_PROMOTION_MIN_CORROBORATION"
_DEFAULT_PROMOTION_MIN_WEIGHT = 0.10   # WEIGHT leg threshold (LAW VI overridable)
_DEFAULT_PROMOTION_MIN_CORROBORATION = 2  # CONSOLIDATE leg: distinct verified origins (LAW VI overridable)
_DISCLOSED_ONLY_REASON = "single_origin_low_weight_non_journal"


def promotion_eligibility_enabled() -> bool:
    """Kill-switch ``PG_CWF_PROMOTION_ELIGIBILITY`` (default ON). OFF => promote-all =>
    the enrichment selection is byte-identical to the legacy keep-all-and-cite list."""
    return os.environ.get(_ENV_PROMOTION, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _parse_promotion_min_weight(raw: Any) -> float:
    """The WEIGHT-leg threshold W in [0.0, 1.0] (LAW VI). Garbage => ValueError (fail-loud)."""
    if raw is None or not str(raw).strip():
        value = _DEFAULT_PROMOTION_MIN_WEIGHT
    else:
        try:
            value = float(str(raw).strip())
        except ValueError as e:
            raise ValueError(
                f"{_ENV_PROMOTION_MIN_WEIGHT} must be a float in [0.0, 1.0]; got {raw!r}"
            ) from e
    if not (0.0 <= value <= 1.0):
        raise ValueError(f"{_ENV_PROMOTION_MIN_WEIGHT} out of range [0.0, 1.0]: {value}")
    return value


def _parse_promotion_min_corroboration(raw: Any) -> int:
    """The CONSOLIDATE-leg threshold K (distinct verified origins), int >= 1 (LAW VI).
    Garbage => ValueError (fail-loud)."""
    if raw is None or not str(raw).strip():
        return _DEFAULT_PROMOTION_MIN_CORROBORATION
    try:
        value = int(str(raw).strip())
    except ValueError as e:
        raise ValueError(
            f"{_ENV_PROMOTION_MIN_CORROBORATION} must be an int >= 1; got {raw!r}"
        ) from e
    if value < 1:
        raise ValueError(f"{_ENV_PROMOTION_MIN_CORROBORATION} must be >= 1: {value}")
    return value


def _host_is_known_journal(url: str) -> bool:
    """Over-demotion guard: a recognized peer-reviewed journal article is ALWAYS
    promotion-eligible regardless of weight, so a freak-low weight can never demote a
    real journal. Pure read of the EXISTING ``PEER_REVIEWED_JOURNAL_DOMAINS`` weighting
    table (a credibility classifier, not a faithfulness gate). Lazy import keeps this
    module free of any retrieval-side dependency; any error fails-CLOSED (not a journal)
    so the guard can only RESCUE, never accidentally demote."""
    if not url:
        return False
    try:
        from urllib.parse import urlparse

        from src.polaris_graph.retrieval.tier_classifier import (
            PEER_REVIEWED_JOURNAL_DOMAINS,
            _domain_matches,
        )

        host = (urlparse(url).hostname or "").lower()
        return bool(host) and _domain_matches(host, PEER_REVIEWED_JOURNAL_DOMAINS)
    except Exception:  # noqa: BLE001 — guard fails CLOSED (treat as non-journal); never raises
        return False


def contract_bound_evidence_ids(contract_plans: Any) -> set[str]:
    """The evidence_ids already inside the contract render universe (excluded from enrichment).

    Robust against duck-typed plan shapes: unions a plan's ``ev_ids`` (the SectionPlan field
    every contract plan mirrors) with every ``slot.entity_ids`` it carries. Missing attrs are
    treated as empty so a shape change can NEVER over-exclude into an empty enrichment.
    """
    bound: set[str] = set()
    for plan in contract_plans or ():
        for eid in (getattr(plan, "ev_ids", None) or ()):
            if eid:
                bound.add(str(eid))
        for slot in (getattr(plan, "slots", None) or ()):
            for eid in (getattr(slot, "entity_ids", None) or ()):
                if eid:
                    bound.add(str(eid))
    return bound


# I-arch-007 #1264 CHOKE-FIX (observability): the enrichment had several independent silent-empty
# exits (credibility None / no baskets / no SUPPORTS members at all / every SUPPORTS member already
# bound or pool-absent) and the call site logged ONLY the success branch. That is why the operator
# saw "zero appended weighted-enrichment section log lines in ALL reports" and could not tell WHICH
# gate killed it. Each reason below is a stable machine-readable token the call site logs LOUDLY so a
# no-op is never silent again.
#
# I-arch-007 #1264 had a FIFTH exit — "every remaining member below the relevance floor" — because
# the selection HARD-DROPPED below-floor rows. I-arch-011 (B18) REMOVED that drop (keep-all-sort-
# below-floor-last), so a below-floor row can NEVER cause an empty exit any more. The empty case is
# now honestly one of: degraded credibility / no baskets / no SUPPORTS member / all bound-or-pool-
# absent. The `_REASON_ALL_BELOW_FLOOR` token is therefore RETIRED (it can no longer be reached).
_REASON_OK = "ok"
_REASON_CREDIBILITY_NONE = "credibility_analysis_none"  # degrade / flag-off path
_REASON_NO_BASKETS = "no_baskets"
_REASON_NO_SUPPORTS_MEMBERS = "no_supports_members"  # baskets exist but no SUPPORTS member at all
_REASON_ALL_BOUND_OR_ABSENT = "all_supports_bound_or_pool_absent"


class UnboundSupportsSelection(NamedTuple):
    """The selection result + a diagnostic breakdown of WHY it is what it is.

    ``ev_ids`` is the FULL ordered surviving list (no cap, no floor drop). The counters make every
    empty-exit auditable: the call site logs ``reason`` LOUDLY so a degraded credibility pass can
    never silently no-op the breadth fix again. ALL counters are pure READS — nothing here touches a
    faithfulness gate.

    I-arch-011 (B18): ``excluded_below_floor`` is RETAINED as the field NAME (the call site at
    multi_section_generator.py:6794/6822 reads it) but its MEANING is now pure TELEMETRY — the count
    of KEPT rows that sit below ``PG_RELEVANCE_FLOOR`` (sorted LAST), NOT an exclusion. A below-floor
    row is never dropped any more, so this counter can never reduce ``ev_ids``.
    """
    ev_ids: list[str]
    reason: str
    baskets_seen: int
    supports_members_seen: int
    excluded_bound: int
    excluded_pool_absent: int
    # I-arch-011 (B18): kept-but-below-floor count (telemetry); NOT an exclusion. Field name held
    # stable for the out-of-lane consumer (multi_section_generator.py:6794/6822).
    excluded_below_floor: int
    # I-deepfix-001 (#1344) DEFER-1: evidence_ids of SUPPORTS members SUPPRESSED FROM
    # CITATION because a SEMANTIC judge confirmed them OFF-topic (kept in
    # evidence_pool + the credibility disclosure — never deleted, never a faithfulness
    # change). Default () keeps the legacy 7-positional constructors valid + the OFF
    # path (PG_OFFTOPIC_CITE_SUPPRESS=0 => empty) byte-identical. Pure TELEMETRY +
    # the disclosed off-topic-excluded-from-citation set the call site surfaces.
    offtopic_suppressed: tuple[str, ...] = ()
    # I-deepfix-001 (#1344 M5): PROMOTION-ELIGIBILITY partition — the members ROUTED to
    # DISCLOSED-ONLY (kept in evidence_pool + the credibility disclosure, re-surfaced in a
    # dedicated report block, but NOT promoted to a standalone numbered finding) because each is
    # single-origin (uncorroborated) AND below the credibility-weight bar AND not a recognized
    # journal venue. Each record: ``{evidence_id, source_url, source_tier, credibility_weight,
    # reason}``. Append-only LAST field (default () keeps every legacy positional constructor valid
    # AND the OFF path byte-identical). NOT a drop — a ROUTE; conservation holds (``ev_ids`` UNION
    # ``disclosed_only`` == the full ordered list); the faithfulness engine is untouched.
    disclosed_only: tuple[dict[str, Any], ...] = ()


# I-deepfix-001 WS-8 (D4) part 2: COMPOSITION-ordering recency leg. The bibliography re-rank alone did not
# stop the headline breach (Codex: the 1986 source headlined from the selection/composition path). This
# demotes an OLD source in the unbound-supports selection ORDERING so it no longer anchors a top finding —
# a WEIGHT on the sort key only, NEVER a filter (the full list is kept; nothing is dropped/capped — §-1.3).
# Journal-class only: gated on PG_DOCUMENT_TYPE_WEIGHT (the journal-class signal, same as the bib re-rank)
# AND PG_COMPOSITION_RECENCY (default-ON); OFF, non-journal-class, or unknown/absent year => factor 1.0 =>
# byte-identical ordering. Reuses the SAME env-tunable curve as the bibliography leg (PG_M2_RECENCY_*).
_COMPOSITION_RECENCY_ENV = "PG_COMPOSITION_RECENCY"
_WE_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")


def _composition_recency_enabled() -> bool:
    """Journal-class gate: the composition recency leg fires only when PG_DOCUMENT_TYPE_WEIGHT is ON (the
    journal-class run signal) AND PG_COMPOSITION_RECENCY is not disabled (default-ON)."""
    dtw = os.environ.get("PG_DOCUMENT_TYPE_WEIGHT", "").strip().lower() in ("1", "true", "on", "yes")
    comp = os.environ.get(_COMPOSITION_RECENCY_ENV, "1").strip().lower() not in ("0", "false", "no", "off")
    return dtw and comp


def _we_publication_year(entry: "dict | None") -> "int | None":
    """Publication year of an evidence-pool entry: an explicit year field, else the first plausible
    4-digit year in title/statement/direct_quote/url/doi. None when none found (=> no penalty)."""
    if not isinstance(entry, dict):
        return None
    for k in ("year", "publication_year", "pub_year"):
        v = entry.get(k)
        if v is None:
            continue
        try:
            y = int(str(v).strip()[:4])
        except (TypeError, ValueError):
            continue
        if 1500 <= y <= 2100:
            return y
    for k in ("title", "statement", "direct_quote", "url", "doi"):
        m = _WE_YEAR_RE.search(str(entry.get(k) or ""))
        if m:
            y = int(m.group(0))
            if 1500 <= y <= 2100:
                return y
    return None


def _we_recency_factor(year: "int | None", reference_year: "int | None") -> float:
    """A [floor, 1.0] ordering multiplier: 1.0 within ``grace`` years of the corpus-newest source, decaying
    linearly by ``decay`` per year older, FLOORED (an old source is DEMOTED for headline order, never
    dropped). Same env curve as the bibliography leg. Missing year / disabled => 1.0."""
    if year is None or reference_year is None or not _composition_recency_enabled():
        return 1.0
    try:
        grace = int(os.getenv("PG_M2_RECENCY_GRACE_YEARS", "5"))
        decay = float(os.getenv("PG_M2_RECENCY_DECAY_PER_YEAR", "0.02"))
        floor = float(os.getenv("PG_M2_RECENCY_FLOOR", "0.25"))
    except (TypeError, ValueError):
        grace, decay, floor = 5, 0.02, 0.25
    age = max(0, int(reference_year) - int(year) - grace)
    return max(floor, 1.0 - decay * age)


def diagnose_unbound_supports_selection(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
) -> UnboundSupportsSelection:
    """``select_unbound_supports_by_weight`` + a diagnostic breakdown (the same selection logic).

    Identical surviving list + ordering as ``select_unbound_supports_by_weight`` (which delegates
    here), PLUS the per-exit counters that make a silent no-op impossible. Faithfulness-neutral:
    this only READS already-computed state; it surfaces nothing into the report by itself.
    """
    if credibility_analysis is None:
        return UnboundSupportsSelection([], _REASON_CREDIBILITY_NONE, 0, 0, 0, 0, 0)
    baskets = getattr(credibility_analysis, "baskets", None) or []
    if not baskets:
        return UnboundSupportsSelection([], _REASON_NO_BASKETS, 0, 0, 0, 0, 0)
    bound = contract_bound_evidence_ids(contract_plans)
    pool = evidence_pool or {}

    # EXISTING relevance gate (no new constant): reuse the retrieval gate's parser so the breadth
    # surfacing applies the SAME PG_RELEVANCE_FLOOR (default 0.30) + the SAME fail-loud (0.0, 1.0]
    # validation. Lazy import (reading, not a cross-module edit) mirrors live_retriever.py:3186.
    from src.polaris_graph.retrieval.evidence_selector import parse_relevance_floor

    relevance_floor = parse_relevance_floor(os.environ.get("PG_RELEVANCE_FLOOR"))

    # Per-eid: the HIGHEST basket weight_mass it appears under (ordering only, never a filter) and
    # its topicality score for the relevance-first ordering.
    best_weight: dict[str, float] = {}
    relevance_by_eid: dict[str, float | None] = {}
    supports_members_seen = 0
    excluded_bound = 0
    excluded_pool_absent = 0
    below_floor_count = 0  # I-arch-011 (B18): KEPT-but-below-floor (telemetry); NEVER an exclusion.
    # I-deepfix-001 (#1344) DEFER-1: SEMANTIC confirmed-OFF members withheld from the
    # CITED breadth surface (kept in pool + disclosure; NOT a faithfulness change).
    suppress_offtopic = offtopic_cite_suppress_enabled()
    offtopic_suppressed: list[str] = []
    # I-deepfix-001 (#1344 M5) PROMOTION-ELIGIBILITY accumulators (most-favorable-to-promotion so
    # any demotion is conservative): per-eid the MAX member ``credibility_weight`` seen (absent =>
    # unknown => keep-neutral promote), the MAX basket ``verified_support_origin_count`` (the
    # CONSOLIDATE leg), whether ANY member's host is a recognized peer-reviewed journal venue (the
    # over-demotion guard), and a tier label for the disclosure surface. Pure READS of already-
    # computed credibility state — no faithfulness gate is touched.
    best_cred_weight: dict[str, float] = {}
    max_origin: dict[str, int] = {}
    is_journal: dict[str, bool] = {}
    best_tier: dict[str, str] = {}
    for basket in baskets:
        try:
            weight = float(getattr(basket, "weight_mass", 0.0) or 0.0)
        except (TypeError, ValueError):
            weight = 0.0
        # I-deepfix-001 (#1344 M5): the basket's distinct isolated-verified origin count (the
        # CONSOLIDATE-leg signal). Non-int / missing => 0 (conservative: no corroboration credit).
        try:
            verified_origin = int(getattr(basket, "verified_support_origin_count", 0) or 0)
        except (TypeError, ValueError):
            verified_origin = 0
        for member in (getattr(basket, "supporting_members", None) or ()):
            if str(getattr(member, "span_verdict", "")).strip().upper() != _SUPPORTS:
                continue  # CONSOLIDATE: only isolated-verified SUPPORTS members are offered
            supports_members_seen += 1
            eid = str(getattr(member, "evidence_id", "") or "")
            if not eid:
                continue
            if eid in bound:
                excluded_bound += 1
                continue
            if eid not in pool:
                excluded_pool_absent += 1
                continue
            # I-deepfix-001 (#1344) DEFER-1: a member a SEMANTIC judge confirmed OFF-topic
            # (topic-gate / W2 label) is WITHHELD FROM CITATION — not surfaced into the
            # breadth section's ev_ids, so the bibliography numberer never assigns it [N].
            # §-1.3-SAFE: it is NOT a lexical ``relevance < floor`` drop (that is the banned
            # keystone DROP); it keys ONLY on the confirmed-OFF verdict, and the source STAYS
            # in evidence_pool + the credibility disclosure (kept-and-disclosed, never deleted).
            # The faithfulness engine (strict_verify / NLI / 4-role / span-grounding) is
            # untouched. OFF (PG_OFFTOPIC_CITE_SUPPRESS=0) => no member is skipped => the
            # ev_ids list is byte-identical to the legacy keep-all-and-cite behaviour.
            if suppress_offtopic and _is_confirmed_offtopic(pool.get(eid)):
                offtopic_suppressed.append(eid)
                continue
            # I-arch-011 (B18) — WEIGHT, DON'T FILTER (§-1.3, the keystone): the pre-fix code
            # RE-IMPOSED a hard ``relevance < floor`` DROP here — the FILTER-AND-CAP anti-pattern the
            # selector docstring (evidence_selector.py:1944-1953) forbids, which killed 729/746
            # unbound SUPPORTS. KEEP-ALL-AND-SORT-BELOW-FLOOR-LAST: a below-floor row is NEVER
            # excluded; it is KEPT and demoted in the ORDER (sorted last) exactly the way the
            # retrieval pool down-weights a below-floor row (evidence_selector.py:2066-2070). A
            # missing/unparseable score is keep-neutral (sentinel 0.0), NOT below-floor — pool
            # membership already implies the retrieval floor passed once. ``below_floor_count`` is
            # pure telemetry: how many KEPT rows sit below the floor, never an exclusion. The ONLY
            # hard gate is the UNCHANGED strict_verify each surfaced sentence still must pass.
            relevance = _row_relevance(pool.get(eid))
            if relevance is not None and relevance < relevance_floor:
                below_floor_count += 1  # KEPT (sorts last), never dropped
            if eid not in best_weight or weight > best_weight[eid]:
                best_weight[eid] = weight
            # First-seen relevance is deterministic across baskets (same row); keep it stable.
            relevance_by_eid.setdefault(eid, relevance)
            # I-deepfix-001 (#1344 M5): accumulate the promotion-eligibility signals for this eid
            # (most-favorable-to-promotion). ``credibility_weight`` is the MEMBER's own credibility
            # (BasketMember.credibility_weight); None/unparseable is left unknown (=> promote-neutral).
            _mw = getattr(member, "credibility_weight", None)
            if _mw is not None:
                try:
                    _mw = float(_mw)
                except (TypeError, ValueError):
                    _mw = None
            if _mw is not None:
                _prev_w = best_cred_weight.get(eid)
                best_cred_weight[eid] = _mw if _prev_w is None else max(_prev_w, _mw)
            if verified_origin > max_origin.get(eid, 0):
                max_origin[eid] = verified_origin
            if not is_journal.get(eid, False):
                _murl = str(getattr(member, "source_url", "") or "") or str(
                    (pool.get(eid) or {}).get("source_url")
                    or (pool.get(eid) or {}).get("url")
                    or ""
                )
                if _host_is_known_journal(_murl):
                    is_journal[eid] = True
            if not best_tier.get(eid):
                _mt = str(getattr(member, "source_tier", "") or "")
                if _mt:
                    best_tier[eid] = _mt

    # I-arch-011 (B18) ORDER, KEEP-ALL-SORT-BELOW-FLOOR-LAST:
    #   1. ``is_below_floor`` (False before True) — a PRESENT-and-below-floor row sorts AFTER every
    #      at/above-floor row AND after every missing-relevance row (a missing score is keep-neutral,
    #      NOT below-floor, so it ranks ahead of a genuine below-floor row).
    #   2. relevance-to-question DESC (within the same below-floor bucket).
    #   3. weight_mass DESC (priority of consideration).
    #   4. evidence_id (deterministic tiebreak).
    # A missing relevance uses the CONSTANT sentinel (0.0) and ``is_below_floor=False`` so a pool of
    # all-missing-relevance rows reproduces today's pure weight-desc order. FULL list — no cap/top-N,
    # no floor DROP.
    def _is_below_floor(eid: str) -> bool:
        rel = relevance_by_eid.get(eid)
        return rel is not None and rel < relevance_floor

    # WS-8 (D4) part 2: corpus-relative recency factor applied to the weight_mass ORDERING term (never to
    # relevance, never a filter). Journal-class only + byte-identical when off/unknown-year. Computed once.
    _year_by_eid = {eid: _we_publication_year(pool.get(eid)) for eid in best_weight}
    _years = [y for y in _year_by_eid.values() if y is not None]
    _ref_year = max(_years) if _years else None

    ev_ids = [
        eid
        for eid, _ in sorted(
            best_weight.items(),
            key=lambda kv: (
                _is_below_floor(kv[0]),                       # False (0) before True (1)
                -_relevance_sort_key(relevance_by_eid.get(kv[0])),
                # WS-8 (D4): demote an OLD source in the weight_mass ordering (still kept — §-1.3); factor
                # 1.0 when the recency leg is off / non-journal-class / year unknown => byte-identical.
                -(kv[1] * _we_recency_factor(_year_by_eid.get(kv[0]), _ref_year)),
                kv[0],
            ),
        )
    ]

    # I-arch-011 (B18): the empty case can no longer be "all below floor" (the floor never
    # excludes). Report the TRUE reason: no SUPPORTS member at all, else everything bound/pool-absent.
    # I-deepfix-001 (#1344 M5): ``reason`` is computed from the FULL surviving list BEFORE the
    # promotion partition, so it honestly reports whether any unbound SUPPORTS member was FOUND —
    # the partition only ROUTES the found members into promoted vs disclosed-only, it never changes
    # whether members existed.
    if ev_ids:
        reason = _REASON_OK
    elif supports_members_seen == 0:
        reason = _REASON_NO_SUPPORTS_MEMBERS
    else:
        reason = _REASON_ALL_BOUND_OR_ABSENT

    # I-deepfix-001 (#1344 M5) PROMOTION-ELIGIBILITY PARTITION — route (NOT drop) near-zero,
    # single-origin, non-journal members to ``disclosed_only`` (kept + re-surfaced, never deleted).
    # §-1.3: WEIGHT-and-CONSOLIDATE — a member is PROMOTED if its weight clears W OR another source
    # corroborates it (>= K verified origins) OR it is a recognized journal venue; only a member
    # failing ALL three is routed to disclosed-only. Conservation holds: ``promoted`` UNION
    # ``disclosed_only`` == the full ``ev_ids`` above (nothing vanishes). The faithfulness engine is
    # untouched — weight/corroboration are credibility judgments, never a grounding gate.
    disclosed_only: list[dict[str, Any]] = []
    if promotion_eligibility_enabled():
        # FAIL-LOUD env parse (LAW VI): a garbage threshold is an operator config error and raises
        # ValueError, NOT swallowed by the fail-open guard below.
        min_w = _parse_promotion_min_weight(os.environ.get(_ENV_PROMOTION_MIN_WEIGHT))
        min_c = _parse_promotion_min_corroboration(os.environ.get(_ENV_PROMOTION_MIN_CORROBORATION))
        try:
            def _promotion_eligible(eid: str) -> bool:
                w = best_cred_weight.get(eid)
                if w is None:
                    return True                                   # unknown weight => keep-neutral (promote)
                if w >= min_w:
                    return True                                   # WEIGHT leg
                if max_origin.get(eid, 0) >= min_c:
                    return True                                   # CONSOLIDATE leg (corroboration rescues)
                if is_journal.get(eid, False):
                    return True                                   # journal carve-out (over-demotion guard)
                return False

            _promoted = [e for e in ev_ids if _promotion_eligible(e)]
            disclosed_only = [
                {
                    "evidence_id": e,
                    "source_url": str(
                        (pool.get(e) or {}).get("source_url")
                        or (pool.get(e) or {}).get("url")
                        or ""
                    ),
                    "source_tier": best_tier.get(e, ""),
                    "credibility_weight": best_cred_weight.get(e),
                    "reason": _DISCLOSED_ONLY_REASON,
                }
                for e in ev_ids
                if not _promotion_eligible(e)
            ]
            ev_ids = _promoted
        except Exception:  # noqa: BLE001 — fail-OPEN to promote-all = byte-identical legacy keep-all
            logger.warning(
                "[weighted_enrichment] M5 promotion-eligibility partition failed; FAIL-OPEN to "
                "promote-all (byte-identical legacy keep-all-and-cite). ev_ids left unchanged.",
                exc_info=True,
            )
            disclosed_only = []

    return UnboundSupportsSelection(
        ev_ids=ev_ids,
        reason=reason,
        baskets_seen=len(baskets),
        supports_members_seen=supports_members_seen,
        excluded_bound=excluded_bound,
        excluded_pool_absent=excluded_pool_absent,
        excluded_below_floor=below_floor_count,  # field name held stable; meaning = kept-below-floor
        offtopic_suppressed=tuple(offtopic_suppressed),  # I-deepfix-001 DEFER-1 (kept+disclosed)
        disclosed_only=tuple(disclosed_only),  # I-deepfix-001 M5 (routed-to-disclosed, never dropped)
    )


def select_unbound_supports_by_weight(
    *,
    evidence_pool: Any,
    credibility_analysis: Any,
    contract_plans: Any,
) -> list[str]:
    """Ordered evidence_ids of unbound, isolated-verified SUPPORTS basket members.

    Returns the FULL surviving list — NO cap, NO target, NO top-N, NO floor DROP. A member is
    included iff:
      * its own ``span_verdict == "SUPPORTS"`` (isolated per-member verification), AND
      * its ``evidence_id`` is NOT already bound to a contract section, AND
      * its ``evidence_id`` resolves in ``evidence_pool`` (so the section can cite a real span).

    I-arch-011 (B18) — WEIGHT, DON'T FILTER (§-1.3, the keystone): the relevance floor is now an
    ORDERING weight, NEVER an exclusion. Ordering is:
      1. at/above-floor (and missing-relevance) rows FIRST, below-floor rows LAST (a demotion, not a
         drop), THEN
      2. relevance-to-question DESC, THEN
      3. basket ``weight_mass`` (priority of consideration), THEN
      4. ``evidence_id`` (deterministic tiebreak).
    The pre-fix code RE-IMPOSED a hard ``selection_relevance < PG_RELEVANCE_FLOOR`` DROP here — the
    FILTER-AND-CAP anti-pattern the selector docstring (evidence_selector.py:1944-1953) forbids,
    which killed 729/746 unbound SUPPORTS so the enrichment appended NOTHING. That drop is REMOVED;
    a below-floor row is KEPT and sorted LAST, mirroring the retrieval pool's keep-all-down-weight
    (evidence_selector.py:2066-2070). A row with NO usable relevance score is keep-neutral (sentinel
    0.0, treated as NOT-below-floor) — pool membership already implies the retrieval floor passed.

    The floor + its fail-loud (0.0, 1.0] validation come from the SAME ``parse_relevance_floor`` the
    retrieval gate uses (no new constant). A garbage ``PG_RELEVANCE_FLOOR`` raises ``ValueError``.

    Faithfulness is UNCHANGED: every surfaced member is re-verified against its own span by the
    section's UNCHANGED ``strict_verify``; breadth comes from consolidating already-verifiable
    corroborators, never from relaxing a verify gate.

    ``credibility_analysis is None`` (master flag OFF or always-release degrade) => ``[]`` =>
    byte-identical legacy render. Thin wrapper over ``diagnose_unbound_supports_selection``; the call
    site uses the diagnostic form to log WHY an empty selection happened.
    """
    return diagnose_unbound_supports_selection(
        evidence_pool=evidence_pool,
        credibility_analysis=credibility_analysis,
        contract_plans=contract_plans,
    ).ev_ids


def build_weighted_enrichment_plan(ev_ids: Any, *, section_plan_cls: Any):
    """Build ONE legacy (field-agnostic) enrichment SectionPlan, or ``None`` when empty.

    ``None`` on empty ``ev_ids`` => caller appends nothing => byte-identical OFF/degrade path.
    """
    ev_ids = list(ev_ids or [])
    if not ev_ids:
        return None
    return section_plan_cls(
        title=_ENRICHMENT_TITLE,
        focus=_ENRICHMENT_FOCUS,
        ev_ids=ev_ids,
    )


# ---------------------------------------------------------------------------
# I-arch-008 (#1265) FIX K — DETERMINISTIC VERIFIED-SPAN RENDER for the
# enrichment section (the 590-in / 0-cited collapse).
#
# THE BUG (traced + behaviorally proven on the cQ75 corpus, state/iarch007_
# breadth_collapse_finding.md): the "Corroborated Weighted Findings" section
# selects ~590 unbound-but-span-verified SUPPORTS sources, then runs them
# through ``_run_section`` -> ``_call_section`` (the LLM), which GENERATES fresh
# prose. That prose then has to RE-EARN strict_verify/entailment from scratch and
# ~0 survives — so the breadth basket renders EMPTY ("no claim survived strict
# verification"). The sources were ALREADY isolated-span-verified (``span_verdict
# == SUPPORTS``); re-generating prose about them throws that verification away.
#
# THE FIX (faithfulness-NEUTRAL, no gate relaxation): when
# ``PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS`` is ON, the enrichment section
# SKIPS the LLM and instead emits a DETERMINISTIC draft = each source's OWN
# verbatim sentence-units, each tagged with a legacy ``[ev_id]`` marker. That
# draft flows through the UNCHANGED ``_rewrite_draft_with_spans`` ->
# ``strict_verify`` path: the rewriter binds each unit to its best in-quote span
# via the SAME ``_find_best_span_for_sentence`` every section uses, and
# strict_verify validates each as that source's exact span-grounded words.
# Breadth EMERGES from how many survive the unchanged gate (measured ceiling on
# cQ75: 571 of 671 usable sources become citable, vs 7 today). NOTHING about the
# faithfulness engine moves — each rendered citation is literally the source's
# own quote against its own span.
#
# TWO build-correctness rules the behavioral harness surfaced
# (scripts/breadth_replay_harness.py — the §-1.4 acceptance gate):
#   1. PER-SENTENCE-UNIT tagging is MANDATORY. ``strict_verify`` re-splits the
#      draft into sentence units; a "whole quote + ONE trailing marker" tags only
#      the LAST unit, so every earlier unit drops with ``no_provenance_token``.
#      That naive draft verifies only 51 of 671 vs 571 for per-unit tagging — an
#      11x silent collapse (the same 590->0 symptom in microcosm). Each unit
#      therefore carries its OWN ``[ev_id]`` marker.
#   2. A JUNK SCREEN is REQUIRED. For a verbatim self-quote, strict_verify's
#      content-word/decimal checks are a tautology (idle) — they filter nothing —
#      so faithfulness rests on SPAN QUALITY. A fetch-shell / cookie-banner /
#      error-page span would otherwise self-quote straight through. We reuse the
#      SAME ``is_boilerplate_or_nonassertional`` allowlist screen strict_verify's
#      BUG-19 pregate uses, applied BOTH per source-quote and per unit, so K's
#      input hygiene is identical to the gate's.
#
# DEFAULT OFF (LAW VI) => ``render_verified_spans_enabled()`` False =>
# byte-identical legacy LLM render. ``is_enrichment_section`` matches ONLY this
# module's own ``_ENRICHMENT_TITLE`` section, so no other section is ever touched.

_ENV_RENDER_VERIFIED_SPANS = "PG_BREADTH_ENRICHMENT_RENDER_VERIFIED_SPANS"

# Per-SOURCE verbatim-unit budget (a verbosity bound + survival redundancy, NOT a
# breadth cap — the NUMBER OF SOURCES surfaced is uncapped; this only bounds how
# many of one source's own sentences are quoted, and offering a few raises the
# chance at least one clears entailment in enforce mode). Env-overridable (LAW
# VI); fail-loud on a non-int; floored at 1 so the flag can never silently zero
# the render.
_ENV_SPANS_PER_SOURCE = "PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE"
_DEFAULT_SPANS_PER_SOURCE = 3

# A sentence-unit must clear this length AND carry a real word to be a citable
# claim (drops bare fragments / lone numbers / headers). Allowlist-side only: the
# unchanged strict_verify gate still independently judges every surviving unit.
_MIN_UNIT_CHARS = 40

# I-beatboth-011 #4 (#1289) — RENDER-SAFETY char bound on a single emitted unit.
# A clean claim sentence is at most a few hundred chars; a unit longer than this is
# NOT a sentence — it is a fetch-shell / raw-extraction blob (the drb_72 defect was a
# ~75K-char raw academic-equation dump that carried a literal NUL byte and self-quoted
# straight into report.md, making it binary-corrupt). This is an allowlist-side
# RENDER bound on a single SURFACED unit, NOT a breadth cap (the number of SOURCES
# surfaced is uncapped) and NOT a faithfulness gate (strict_verify is untouched). A
# real long-but-legitimate quote is split into sentence units upstream by
# ``split_into_sentences``; a single unit exceeding this bound is structurally a blob,
# never a clinical sentence. Env-overridable (LAW VI); fail-loud on a non-int; floored
# at ``_MIN_UNIT_CHARS`` so the bound can never silently zero the render.
_ENV_MAX_UNIT_CHARS = "PG_BREADTH_ENRICHMENT_MAX_UNIT_CHARS"
_DEFAULT_MAX_UNIT_CHARS = 600

# C0 control bytes (and DEL) that MUST NEVER reach the rendered report — a literal NUL
# (\x00) at byte offset 220201 made drb_72 report.md binary-corrupt and unshowable.
# We strip every C0 control char EXCEPT \n and \t (which are legitimate whitespace in
# a multi-line quote). 0x7F (DEL) is included. This is byte-hygiene on the emitted
# render text, never a verdict and never a content drop.
_C0_CONTROL_KEEP = {"\n", "\t"}

# CAPTCHA / Cloudflare / security-interstitial stubs that fetch as a grammatical-looking
# SENTENCE (so ``is_boilerplate_or_nonassertional`` does NOT catch them) and would
# otherwise self-quote into the report. Allowlist input-hygiene, NEVER a verdict, NEVER a
# quality/length drop of real content.
#
# I-beatboth-011 #7 P1 (#1289): the bare trigger phrase "just a moment" is NOT enough to
# drop a member — real substantive prose can carry it ("Just a moment — the data show
# wages rose 5% in 2023"). Dropping such prose would violate §-1.3 keep-all. A drop now
# requires the trigger AND a STRONG WAF / security co-token (BYTE-IDENTICAL predicate
# shared with ``finding_dedup._is_captcha_stub`` so consolidation and render agree). The
# co-tokens are high-precision multi-word / branded anchors a real clinical sentence (any
# language) never contains.
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

# Web-chrome / cookie-consent / nav markers that read as a grammatical SENTENCE.
# These slip past ``is_boilerplate_or_nonassertional`` + ``strip_web_boilerplate``
# (which catch error-pages + line-level chrome, not sentence-form consent text) —
# and on a verbatim self-quote strict_verify's content/decimal checks are IDLE, so
# without this screen a "Enable basic functions like page navigation." span would
# self-quote straight into a clinical report. Same allowlist-only, whole-unit
# input-hygiene pattern as the strict_verify BUG-19 pregate: multi-word, anchored
# to chrome-specific phrasing so a real clinical sentence (any language) is never
# touched, and NEVER a verdict — only what the breadth section actively SURFACES.
_WEB_CHROME_MARKERS = (
    "enable basic functions",
    "page navigation",
    "access to secure areas",
    "secure areas of the website",
    "website cannot function",
    "without these cookies",
    "accept all cookies",
    "cookie settings",
    "cookie policy",
    "privacy policy",
    "terms of service",
    "all rights reserved",
    "page not found",
    "404 error",
    "are you a robot",
    "enable javascript",
    "request access to",
    "sign in to continue",
    "subscribe to read",
    "log in to view",
    # I-beatboth-011 §3.4 idx68 (#1289): social-media / repository / masthead chrome that leaked into
    # cited spans in banked v3 (Scribd, Facebook, YouTube, journal masthead). HIGH-PRECISION multi-word
    # anchors ONLY (never bare "share"/"download"/"subscribers", which appear in real prose) — P1-4:
    # allowlist input-hygiene, NOT a length/quality drop of real content.
    "download free for 30 days",          # Scribd
    "report this document",               # Scribd
    "is this content inappropriate",      # Scribd
    "like comment share",                 # Facebook
    "subscribers subscribed",             # YouTube channel chrome
    "share save download",                # YouTube action bar
    "tap to unmute",                      # YouTube player chrome
    "skip navigation",                    # YouTube / generic nav
    "cite this paper as",                 # journal masthead citation widget
    # I-beatboth-011 b1 (#1289): publisher login-nav + image-URL masthead chrome that self-quoted into the
    # answer BODY/Key-Findings in banked v3 (drb_72 report.md carried the literal Wiley masthead+login-nav
    # run ".../logo-header-1690978619437.png) ## Change Password Old Password New Password Too Short.[13]").
    # HIGH-PRECISION multi-word anchors ONLY (never bare "password"/"image"/"logo"/"favicon", which appear
    # in real prose) — allowlist input-hygiene, NOT a length/quality drop of real content.
    "change password old password new password",  # Wiley/publisher login-nav run
    "/pb-assets/",                                 # publisher asset path segment (slash-anchored)
    "![image",                                     # markdown image leader "![Image N: ...]" (structure-anchored)
)

# Structure-anchored web-chrome asset URLs that a bare substring marker cannot express
# precisely — I-beatboth-011 b1 (#1289). Each REQUIRES a file extension / digit-stamp so a
# real-prose mention ("the favicon was redesigned", "a logo-header CSS class") is NEVER matched
# (the §-1.3 no-real-claim-dropped invariant). favicon coverage was missing entirely; logo-header
# was a bare substring (over-screen risk) — both are now extension/path-anchored here.
_WEB_CHROME_RE = re.compile(
    r"favicon[\w.\-]*\.(?:ico|png|svg|gif|jpe?g)\b"   # favicon.<ext> asset file
    r"|\blogo-header[-\w]*\.png\b",                   # masthead image URL logo-header-<stamp>.png
    re.IGNORECASE,
)

# Trailing sentence-terminal punctuation stripped before the ``[ev_id]`` marker is
# appended, so the marker sits INSIDE the sentence unit (``...trial [ev_id].``) and
# survives strict_verify's re-split. A marker appended AFTER the period
# (``...trial. [ev_id]``) is peeled onto its own fragment -> the content sentence
# goes tokenless -> dropped ``no_provenance_token`` (the silent-collapse the harness
# caught: it suppressed otherwise-citable sources).
_TERMINAL_PUNCT = ".!?"

# Legacy ``[ev_id]`` marker form — exactly what ``_call_section``'s LLM emits and
# what ``_rewrite_draft_with_spans`` (_EV_MARKER_RE) consumes. We emit this (not a
# pre-baked ``[#ev:id:s-e]`` token) so K's spans are computed by the SAME
# production span-finder as every other section — no parallel offset math.


def render_verified_spans_enabled() -> bool:
    """True iff the default-OFF verified-span render flag is explicitly enabled (LAW VI)."""
    return os.environ.get(_ENV_RENDER_VERIFIED_SPANS, "").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def spans_per_source() -> int:
    """Per-source verbatim-unit budget from ``PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE``.

    Default ``_DEFAULT_SPANS_PER_SOURCE``. Fail-loud on a non-integer (LAW II — no
    silent fallback to a guessed value); floored at 1 so the render can never be
    silently zeroed by a ``0`` / negative value.
    """
    raw = os.environ.get(_ENV_SPANS_PER_SOURCE)
    if raw is None or not raw.strip():
        return _DEFAULT_SPANS_PER_SOURCE
    try:
        val = int(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_ENV_SPANS_PER_SOURCE}={raw!r} is not an integer "
            f"(per-source verbatim-unit budget)"
        ) from exc
    return max(1, val)


def max_unit_chars() -> int:
    """Render-safety char bound on a single emitted unit (I-beatboth-011 #4).

    Default ``_DEFAULT_MAX_UNIT_CHARS``. Fail-loud on a non-integer (LAW II — no
    silent fallback to a guessed value); floored at ``_MIN_UNIT_CHARS`` so the bound
    can never silently zero the render. A unit longer than this is structurally a
    fetch-shell / raw-extraction blob, never a clinical sentence.
    """
    raw = os.environ.get(_ENV_MAX_UNIT_CHARS)
    if raw is None or not raw.strip():
        return _DEFAULT_MAX_UNIT_CHARS
    try:
        val = int(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_ENV_MAX_UNIT_CHARS}={raw!r} is not an integer "
            f"(per-unit render char bound)"
        ) from exc
    return max(_MIN_UNIT_CHARS, val)


def _strip_control_bytes(text: str) -> str:
    """Strip C0 control bytes (and DEL 0x7F) EXCEPT \\n and \\t from render text.

    The drb_72 defect leaked a literal NUL byte (``\\x00``) into report.md, making it
    binary-corrupt and unshowable. This removes every ``ord(ch) < 32`` control char
    plus ``0x7F`` while KEEPING newline/tab (legitimate whitespace in a multi-line
    quote). Byte-hygiene on the emitted render text, never a verdict, never a content
    drop of a real claim — only non-printable control bytes are removed.
    """
    if not text:
        return text
    return "".join(
        ch
        for ch in text
        if ch in _C0_CONTROL_KEEP or (ord(ch) >= 32 and ord(ch) != 0x7F)
    )


def _is_captcha_stub(text: str) -> bool:
    """True iff ``text`` is a CAPTCHA / security-interstitial stub (allowlist-only).

    I-beatboth-011 #7 P1 (#1289): the bare trigger phrase ("just a moment") is NOT
    sufficient — a genuinely substantive sentence can contain it. A drop requires the
    trigger AND a strong WAF / security co-token (BYTE-IDENTICAL predicate shared with
    ``finding_dedup._is_captcha_stub``). §-1.3 keep-all: real prose carrying a bare
    "just a moment" with no security co-token is never dropped.
    """
    low = text.lower()
    return (_CAPTCHA_STUB_TRIGGER in low) and any(tok in low for tok in _WAF_CO_TOKENS)


def is_enrichment_section(section: Any) -> bool:
    """True iff ``section`` is THIS module's weighted-enrichment section.

    Matches on the exact ``_ENRICHMENT_TITLE`` so the deterministic render is
    scoped to the one section this module builds — every contract / body section
    is byte-identical. Robust to a duck-typed plan (missing ``title`` => False).
    """
    return str(getattr(section, "title", "") or "") == _ENRICHMENT_TITLE


def _is_web_chrome(text: str) -> bool:
    """True iff ``text`` carries a sentence-form web-chrome / cookie-consent marker."""
    low = text.lower()
    if any(marker in low for marker in _WEB_CHROME_MARKERS):
        return True
    return bool(_WEB_CHROME_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-012 (#1326) — THE ONE shared render-side chrome+truncation predicate.
#
# The render/compose surfaces (Corroborated Weighted Findings, the verified-compose
# section body, the per-claim corroboration header, Key-Findings / Abstract /
# Conclusion / depth) each grew their OWN parallel chrome screen
# (``_make_junk_screen`` here, ``verified_compose._compose_junk_screen``,
# ``run_honest_sweep_r3._span_is_render_chrome`` / ``_claim_header_is_unrenderable``,
# the ``key_findings`` filter). Parallel screens DRIFT — a chrome shape patched in
# one leaks through the others. This module is the chrome hub (verified_compose
# already delegates to ``_make_junk_screen``), so the ONE predicate lives here and
# every screen DELEGATES to it: no composer can emit an unscreened claim.
#
# FAITHFULNESS (FROZEN engine): this is render/compose INPUT hygiene only — it
# SUPPRESSES a page-furniture/truncated unit, it NEVER promotes one and NEVER
# touches a strict_verify / NLI / 4-role / span-grounding VERDICT. Page furniture is
# not a corroborating source, so suppressing it STRENGTHENS faithfulness (§-1.3).
#
# PRECISION OVER RECALL (the codebase law: "over-strip deletes a real finding, worse
# than a leak"). Every NEW category is high-precision allowlist/structure-anchored so
# a real clinical/economics/policy finding (any language) is never dropped; the
# canary below is the leak backstop. The "non-English-out-of-scope" category was
# DELIBERATELY NOT built: a language-only drop deletes real non-English sources (a
# §-1.3 multilingual-preservation regression), and any genuine non-English chrome
# already fires one of the structural categories below — so a separate language gate
# would only add over-strip risk for no recall.
_RENDER_CHROME_SCREEN_ENV = "PG_RENDER_CHROME_SCREEN"

# Page-furniture / masthead / journal / fetch-framing / nav SPANS that render as a
# grammatical-looking fragment (so the whole-line boilerplate screen misses them).
# Consolidated from run_honest_sweep_r3._RENDER_CHROME_SPAN_RE — the SINGLE source of
# truth now (the runner delegates to this predicate).
_SHARED_RENDER_CHROME_RE = re.compile(
    r"\bVolume\s+\d+\s*,?\s*(?:Number|No\.?|Issue)\s+\d+\b"
    r"|\bPages?\s+\d+\s*[-‐-―]\s*\d+\b"
    r"|\bISSN\b\s*:?\s*\d"
    r"|\bCITATIONS\b\s+\d+\s+\bREADS\b\s+\d+"
    r"|\bMarkdown Content\s*:|\bURL Source\s*:|\bPublished Time\s*:"
    r"|\bNumber of Pages\s*:|\bCite this paper as\b"
    r"|#main-content|Twitter-intent|twitter\.com/intent"
    r"|same series\s*[-‐-―]\s*working paper"
    r"|\blisted\s+topics?\s+include\b",
    re.IGNORECASE,
)
# Claim-header chrome: CC-license / keywords-list / login-wall / share-button furniture
# (consolidated from run_honest_sweep_r3._CLAIM_HEADER_CHROME_RE). "Close-Share" and CC-license
# are explicitly in the I-wire-012 category list. PRECISION: this predicate can DROP composer text,
# so the bare ``\bkeywords\b`` of the header-only version is TIGHTENED to the ``Keywords:`` list
# LABEL — a real sentence ("the keywords were extracted from ...") is never matched.
_SHARED_CLAIM_HEADER_CHROME_RE = re.compile(
    r"creative commons|licensed under a |\bkeywords\s*:|premium access|must have premium|"
    r"share icon|close\s*-\s*share|all rights reserved",
    re.IGNORECASE,
)
# Numbered table-of-contents entry, SECTION-NAME-anchored only ("1 Introduction", "3 Methods").
# PRECISION: the loose decimal "N.N Capitalized" form (kept header-only in run_honest_sweep, where
# an over-match merely swaps to subject+predicate) is DELIBERATELY EXCLUDED here — it would drop a
# real magnitude claim ("$3.2 Billion") from a composer. Only the unambiguous section-name ToC shape
# (which a real finding sentence never IS) screens droppable text.
_SHARED_TOC_RE = re.compile(
    r"^\s*\d+\s+(?:Introduction|Background|Materials?|Methods?|Results?|Discussion|"
    r"References|Conclusion|Abstract)\s*$",
    re.IGNORECASE,
)
# A WHOLE-UNIT scraped document label standing alone as a "claim" ("Abstract",
# "AI Summary", "Author summary", "Graphical abstract"). Whole-unit anchored
# (``fullmatch``-style ``^...$``) so it NEVER catches POLARIS's own ``## Abstract``
# section header (that carries the ``## `` prefix + body) or a real sentence that
# merely contains the word "abstract".
_DOC_LABEL_RE = re.compile(
    r"^(?:abstract|ai\s+summary|ai\s+overview|graphical\s+abstract|author\s+summary|"
    r"plain\s+language\s+summary|highlights|table\s+of\s+contents)\s*[:.]?\s*$",
    re.IGNORECASE,
)
# An ORCID identifier in a "claim" => an author/affiliation masthead list, never a
# finding (a real clinical/economics sentence never carries a 0000-0000-0000-0000
# ORCID id). High precision by construction.
_ORCID_RE = re.compile(r"\b\d{4}-\d{4}-\d{4}-\d{3}[\dxX]\b")
# A bare DOI / identifier row standing alone as a "claim" (no assertional prose).
_DOI_ONLY_RE = re.compile(
    r"^\s*(?:doi\s*:?\s*|https?://(?:dx\.)?doi\.org/)?10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\s*$",
    re.IGNORECASE,
)
# Trailing ``[N]`` / ``[#ev:...]`` citation markers (stripped before the sentence-form
# completeness test so "…claim.[12]" is judged on the "." not the marker).
_SHARED_TRAILING_CITE_RE = re.compile(r"(?:\s*\[(?:\d+|#ev:[^\]]*)\])+\s*$")

# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327) iter-3a — CONTAINMENT forensic chrome rules (the UNBLINDING).
#
# The legacy chrome categories above are WHOLE-UNIT junk classifiers (anchored ^…$ / standalone-
# label / bare-DOI shapes): they return False the moment a unit ALSO carries real prose, so glued
# page-furniture survived ("…over the recent past.[1] 1 Introduction 1.1 Research background 1.2
# Resea.[14]", a masthead glued mid-Abstract, a "## Dennis Zami …" author header glued onto a
# section title). These rules — ported from the independent detector
# scripts/iwire013_sec11_forensic_audit.py (which catches 55 chrome / 20 truncation on the banked
# render where the production predicate reported ~0) — flag a unit that CONTAINS chrome, not only a
# unit that IS chrome.
#
# PRECISION OVER RECALL (drop-path law — "over-strip deletes a real finding, worse than a leak"):
# the detector's loose bare ``\d+ TitleCase`` ToC token and any-run non-Latin rule were tightened
# for this DROP path (they over-flagged real economics prose with year/figure number pairs and an
# English finding quoting a short CJK term). The kept rules are structure-anchored and validated to
# flag ZERO of a clean-finding probe set while catching the real glued chrome (≈47/55 of the banked
# render; the residual are detector false-positives we deliberately KEEP, or niche chrome the canary
# backstops). Every numeric threshold is a named constant (LAW VI / §9.4).

# A glued/inline markdown header INSIDE a unit body (a SECOND "## …" header welded onto the title /
# into prose) — NOT a clean leading header (the caller passes a header's TITLE, post-``#`` strip).
_INLINE_HEADER_RE = re.compile(r"(?:^|[^\n#])#{1,6}\s+[A-Za-z]")
# Author-with-superscript-affiliation list: "Kanbach1,2 · Louisa Heiduk1 · …" (middot separators).
_AFFIL_MIDDOT_RE = re.compile(r"[A-Za-z]{2,}\d{1,2}(?:,\d)?\s*[·•]")
# A run of non-Latin script (Arabic / CJK) — the report is English-only, so a PREDOMINANTLY
# non-Latin unit is a foreign-page scrape. A SHORT inline foreign term inside English prose is NOT
# flagged (§-1.3 multilingual preservation): the run must be long AND outweigh the Latin letters.
_NONLATIN_CHAR_RE = re.compile(r"[؀-ۿݐ-ݿ一-鿿぀-ヿ가-힯]")
_NONLATIN_RUN_RE = re.compile(r"[؀-ۿݐ-ݿ一-鿿぀-ヿ가-힯]{4,}")
_MIN_NONLATIN_RUN_CHARS = 4  # a shorter run is an inline foreign term, kept
# A DOTTED section-number token glued into a unit ("1.1 Research", "5.2 AI"); the TitleCase word is
# excluded when it is a magnitude/measure unit so a real "3.2 Million / 4.5 Billion" pair never
# reads as a two-token ToC. A unit needs ``_MIN_DOTTED_TOC_HITS`` dotted tokens to flag as glued ToC.
_DOTTED_SECTION_TOKEN_RE = re.compile(r"(?:^|\s)\d+\.\d+(?:\.\d+){0,2}\s+([A-Z][a-z]+)")
_MIN_DOTTED_TOC_HITS = 2
_MAGNITUDE_UNIT_WORDS = frozenset({
    "million", "billion", "trillion", "thousand", "hundred", "percent", "percentage",
    "times", "average", "points", "point",
})
# A STANDALONE numbered-heading LINE/unit: a unit that OPENS with a dotted section number + a
# TitleCase word ("3.3 Recommender Systems", "1.1 Research background to the study"). Anchored at the
# unit start so a mid-sentence "see section 3.3 for details" never matches; the opener word is
# magnitude-excluded so "3.2 Billion outcomes …" never matches.
_STANDALONE_DOTTED_HEADING_RE = re.compile(r"^\s*\d+\.\d+(?:\.\d+){0,2}\s+([A-Z][a-z][\w]*)")
# A STANDALONE numbered SECTION-NAME heading ("1 Introduction", "3 Methods") — anchored at the unit
# start with a closed section-name vocabulary so a prose "Figure 1 Results" / "Table 2 Methods"
# (which does NOT open with a bare number) is never matched.
_STANDALONE_SECTION_NAME_RE = re.compile(
    r"^\s*\d+(?:\.\d+){0,3}\s+(?:Introduction|Background|Materials?|Methods?|Methodology|"
    r"Results?|Discussion|References?|Conclusion|Abstract|Literature|Overview)\b",
    re.IGNORECASE,
)
# Journal / submission MASTHEAD furniture welded into a unit ("44 Pages Posted: 9 Jan 2018",
# "Vol: 30 Issue: 1", "Date Issued April 2020", "Policy Research Working Paper 11057").
_MASTHEAD_CHROME_RE = re.compile(
    r"\bpages?\s+posted\s*:|\bposted\s*:\s*\d|\blast revised\s*:|\bdate issued\b|"
    r"\bworking paper\s+\d{2,}|\bvol\.?\s*:?\s*\d+\s*(?:,|issue|no\.?)|"
    r"there are \d+ versions of this paper|\bpolicy research working paper\b|"
    r"cite this paper as|number of pages",
    re.IGNORECASE,
)
# Author / submission-metadata block ("Received: 31 May 2023 / Accepted: …", "Published online").
_SUBMISSION_META_RE = re.compile(
    r"received:\s*\d|accepted:\s*\d|published online|\brevised:\s*\d", re.IGNORECASE,
)
# Browser / UI / nav / social-share junk welded into a unit.
_NAV_CHROME_RE = re.compile(
    r"share\s+facebook|facebook\s+twitter|twitter\s+linkedin|download associated records|"
    r"clear your browser cache|refresh the page or clear|accessing this content requir|"
    r"this content is only available as a pdf|i need some assistance|most recent answer|"
    r"requires a membership|please log into",
    re.IGNORECASE,
)
# Open-access / license / copyright furniture.
_LICENSE_CHROME_RE = re.compile(
    r"creative commons|creativecommons\.org/licenses|open access article distributed under|"
    r"this is an open access article|©\s*\d{4}\s+the\b|©\s*the author|copyright\s+©",
    re.IGNORECASE,
)
# HARD bibliographic / portal markers (a LONE URL is NOT chrome; these are unambiguous).
_BIBLIO_CHROME_RE = re.compile(
    r"\bdoi:\s*10\.\d|\bissn\b\s*:?\s*\d|crossref reports the following articles citing|"
    r"volume title publisher|name:\s*\S+\.txt\b|file type:\s*text/",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"https?://", re.IGNORECASE)
_DOI_URL_RE = re.compile(r"https?://(?:dx\.)?doi\.org/", re.IGNORECASE)
_MIN_URLS_FOR_CHROME = 3       # >=3 bare URLs in one unit => a link list / portal blob
_MIN_DOI_URLS_FOR_CHROME = 2   # >=2 doi.org URLs => a reference blob
# A statistics / regression TABLE welded into a unit: a dense run of parenthesised std-errors
# "(0.018) (0.016) (0.011)" or starred coefficients "0.034* 0.030* 0.027**". A real finding cites
# one coefficient, never a 3+/2+ run.
_STATS_TABLE_RE = re.compile(
    r"(?:\(\s*[-−]?\d+\.\d+\s*\)\s*){3,}|(?:\d+\.\d+\s*\*{1,3}\s*){3,}"
)

# I-deepfix-002 (#1363) FIX-1 — cookie/consent banner, DOI-registry error page, mixed-script
# masthead. drb_72 smoke leaked these into cited claims (cookie-wall [10][23][24], DOI-Not-Found
# error page [25], Russian journal masthead [5][11]); they self-entail strict_verify (text == its
# own span) so the faithfulness engine cannot catch them — they are page furniture / dead-fetch
# shells, never a corroborating source. SUPPRESS-only (FLAG-not-drop); engine UNCHANGED.
_COOKIE_CONSENT_RE = re.compile(
    r"utiliz\w*\s+technologies\s+such\s+as\s+cookies"
    r"|we\s+use\s+cookies\s+to\s+enhance\s+your\s+browsing"
    r"|we\s+value\s+your\s+privacy"
    r"|analytics,?\s+personali[sz]ation,?\s+and\s+targeted\s+advertising"
    r"|necessary\s+cookies\s+are\s+required"
    r"|the\s+technical\s+storage\s+or\s+access\s+(?:is|that\s+is)\s+(?:strictly\s+necessary|used\s+exclusively)"
    r"|opens\s+(?:in\s+a\s+new\s+window|an\s+external\s+website)"
    r"|store\s+and/or\s+access\s+information\s+on\s+your\s+device"
    r"|error\s*[-–—]\s*cookies\s+turned\s+off"
    r"|cookieabsent"
    r"|press\s+alt\+1\s+for\s+screen-reader\s+mode"
    r"|strictly\s+necessary\s+for\s+the\s+legitimate\s+purpose"
    r"|accept\s+all\s+cookies", re.IGNORECASE)
_DOI_ERROR_RE = re.compile(
    r"DOI\s+Not\s+Found"
    r"|this\s+DOI\s+cannot\s+be\s+found\s+in\s+the\s+DOI\s+System"
    r"|report\s+this\s+error\s+to\s+the\s+responsible\s+DOI\s+Registration\s+Agency"
    r"|the\s+DOI\s+has\s+not\s+been\s+activated\s+yet"
    r"|search\s+again\s+from\s+DOI\.ORG", re.IGNORECASE)
# A 4+ char non-Latin run (Cyrillic U+0400–052F added — the legacy _NONLATIN_CHAR_RE omitted it)
# AND a Vol/Issue/№/Том token = a foreign-language journal masthead, not English prose quoting a
# short foreign term.
_NONLATIN_MASTHEAD_RUN_RE = re.compile(r"[Ѐ-ԯ؀-ۿ一-鿿぀-ヿ가-힣]{4,}")
_MASTHEAD_VOL_TOKEN_RE = re.compile(r"\b(?:Vol\.?|Volume|Issue|No\.)\b|№|Том\b", re.IGNORECASE)


def _is_foreign_journal_masthead(text: str) -> bool:
    return bool(_NONLATIN_MASTHEAD_RUN_RE.search(text) and _MASTHEAD_VOL_TOKEN_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) DEFER-4 — residual WHOLE-UNIT page-furniture the FIX-1 (cookie/DOI/foreign-
# masthead/byline) and legacy categories miss. drb_72 smoke leaked these as cited claims:
#   A14 publisher PAYWALL call-to-action ("Get full access to this article / View all access and
#       purchase options for this article." [20]) — the legacy chrome_furniture_screen._PAYWALL_RE
#       covers Member-only/Feature-Story but not this Sage/Atypon access-wall string.
#   A15 working-paper COVER masthead + author-opinion DISCLAIMER ("DISCUSSION PAPER SERIES IZA DP
#       No. 14409 ... Any opinions expressed in this paper are those of the author(s) ..." [19]).
#   A16 PDF FOOTNOTE / citation-apparatus run ("See OECD (2020), Table 3.3. 14Tate and Yang (2016)
#       analyze ... 7 Post-merger restructuring." [19]).
#
# PRECISION + OVER-STRIP SAFETY (operator-locked drop-path law "over-strip deletes a real finding,
# worse than a leak"): each rule fires ONLY on a unit that is DOMINANTLY page furniture — a paywall
# CTA, a series-cover masthead, a footnote/reference run with NO finding clause. A real economics /
# labor finding never carries these anchors. Units that are a REAL finding welded to a SMALL artifact
# (A17 "…eliminated.1 1 This number assumes…", A18 "Box 3.1 … In collaboration with Indeed …",
# A19 "(See Exhibit 1.)", E1 truncated "…not only access to.") are DELIBERATELY NOT matched here —
# dropping their whole unit would delete the real finding inside, so they are left to the render-seam
# REPAIR / truncation legs. A20 ("eloundou_gpts_are_gpts") is a SUPPORT sub-bullet source-locator
# (keep-only surface), not a claim unit, so it is out of this predicate's lane too. FLAG-not-drop:
# the source row stays in evidence_pool + the credibility disclosure; the faithfulness engine
# (strict_verify / NLI / 4-role / span-grounding) is UNCHANGED.

# A14 — publisher paywall / "get full access" CTA furniture. Multi-word, access-wall-specific.
_PAYWALL_ACCESS_RE = re.compile(
    r"\bget\s+full\s+access\s+to\s+this\s+article\b"
    r"|\bview\s+all\s+access\s+and\s+purchase\s+options\b"
    r"|\bpurchase\s+options\s+for\s+this\s+article\b",
    re.IGNORECASE,
)
# A15 — working-paper / discussion-paper COVER masthead + author-opinion DISCLAIMER. Both phrases are
# series-cover boilerplate a real finding never contains (the working-paper-NUMBER masthead form
# "Policy Research Working Paper 11057" is already covered by _MASTHEAD_CHROME_RE; this adds the
# "DISCUSSION PAPER SERIES" series header and the "Any opinions expressed in this paper are those of
# the author(s)" disclaimer that the IZA cover carries).
_WORKING_PAPER_COVER_RE = re.compile(
    r"\bdiscussion\s+paper\s+series\b"
    r"|\bany\s+opinions?\s+expressed\s+in\s+this\s+paper\s+are\s+those\s+of\s+the\b",
    re.IGNORECASE,
)
# A16 — PDF footnote / citation-apparatus run: a 1-2 digit footnote number GLUED directly to a
# Capitalized surname ("14Tate and Yang (2016)") or a "See <REF> (year), Table N" cross-reference
# opener. A real sentence writes "Tate and Yang (2016)" (space, no glue) and never opens "See OECD
# (2020), Table 3.3.". The glue rule's ``[A-Z][a-z]{2,}`` excludes all-caps tokens (so "4IR", "23
# OECD") and lowercase (so "165million") — only a footnote-digit welded to a Mixed-case surname.
_FOOTNOTE_GLUE_RE = re.compile(
    r"\b\d{1,2}[A-Z][a-z]{2,}\s+(?:and|et\s+al\.?|\(\d{4}\))"
    r"|\bSee\s+[A-Z][A-Za-z]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z]+)?\s*\(\d{4}\)\s*,?\s+Table\s+\d",
)


def _is_residual_chrome_furniture(text: str) -> bool:
    """I-deepfix-001 (#1344) DEFER-4: True iff ``text`` is a residual furniture-DOMINATED unit
    (publisher paywall CTA, working-paper cover masthead/disclaimer, PDF footnote/citation run).
    High-precision whole-unit screen; a real finding welded to a small artifact is NOT matched."""
    return bool(
        _PAYWALL_ACCESS_RE.search(text)
        or _WORKING_PAPER_COVER_RE.search(text)
        or _FOOTNOTE_GLUE_RE.search(text)
    )


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1344) chrome_canary_unblind — three chrome CLASSES the containment predicate was
# BLIND to (the canary passed 0/226 while the report was saturated with chrome). Each rule is a
# high-precision CONTAINMENT signal (fires even when the class is welded INTO otherwise-real prose),
# structure/dual-signal-anchored so it can NEVER flag clean clinical prose:
#   (a) AUTHOR-AFFILIATION / EMAIL block — an email address CO-OCCURRING with an institution keyword
#       (a corresponding-author byline: "…, Department of Cardiology, Harvard University. Email:
#       jsmith@harvard.edu"). A real clinical/research finding never carries a raw email address, and
#       the email+institution DUAL signal never co-occurs in substantive prose (precision-first per
#       §-1.3: recall is secondary, over-strip is worse). The email alone is NOT enough (a finding
#       could conceivably quote one); both signals are required.
#   (b) TABLE-OF-CONTENTS DOT-LEADERS — a run of 4+ leader dots (a normal ellipsis is exactly 3)
#       followed by a page number ("Introduction ......... 12"). Consecutive-dot runs with a trailing
#       page number are ToC furniture; a decimal table ("0.034 0.030") has digits BETWEEN the dots so
#       it never matches.
#   (c) COOKIE / CONSENT banner — the "By clicking/continuing … you accept/agree/consent" consent-CTA
#       phrasing the legacy ``_COOKIE_CONSENT_RE`` alternation missed. Bounded gap (no ``.``/newline)
#       between the two anchors keeps it from spanning unrelated sentences.
# FLAG-not-drop / detector-only: a flagged unit is withheld from the rendered rollup and KEPT in
# evidence; the faithfulness engine (strict_verify / NLI / 4-role / provenance / span-grounding) is
# UNCHANGED. Gated by the caller under ``render_chrome_screen_enabled()`` (default ON).
_AFFIL_EMAIL_ADDRESS_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
_AFFIL_INSTITUTION_KEYWORD_RE = re.compile(
    r"\b(?:Universit(?:y|ies|[àáäé]|e)|Universidad|Universit[àé]|Department|Departamento|"
    r"Institut(?:e|o|ion)?|College|Hospital|Clinic|Laborator(?:y|ies)|Faculty|Facultad|"
    r"Escuela|Polytechnic|Academy|Ministry)\b",
    re.IGNORECASE,
)
_TOC_DOTLEADER_RE = re.compile(r"(?:\.[ \t]*){4,}\d{1,4}\b")
_COOKIE_BY_CLICKING_RE = re.compile(
    r"\bby\s+(?:clicking|continuing|using|browsing)\b[^.\n]{0,80}?"
    r"\byou\s+(?:accept|agree|consent)\b",
    re.IGNORECASE,
)


def _contains_missed_chrome_class(text: str) -> bool:
    """I-deepfix-001 (#1344) chrome_canary_unblind: True iff ``text`` CONTAINS one of the three
    high-precision chrome classes the legacy containment predicate was blind to — an author-
    affiliation/email byline, a ToC dot-leader run, or a "By clicking … you accept" consent banner.
    Detector-only (FLAG-not-drop); the faithfulness engine is UNCHANGED."""
    if _AFFIL_EMAIL_ADDRESS_RE.search(text) and _AFFIL_INSTITUTION_KEYWORD_RE.search(text):
        return True
    if _TOC_DOTLEADER_RE.search(text):
        return True
    return bool(_COOKIE_BY_CLICKING_RE.search(text))


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-016 (#1338) gap-fill — precision-safe furniture rules the legacy categories miss (the OSS
# survey confirmed no fetch-time HTML extractor fits the render seam; extend the deterministic
# predicate). Codex iter-1/2/3 removed every rule whose surface form overlaps a real finding (biblio
# date+page, bibliometric stats, "Name<digit>, <digit>" superscript), leaving the unambiguous
# affiliation-glued / title+affiliation / author-attribution-phrase rules. VALIDATED precision-first:
# ZERO of the 398 curated-clean real-content units are flagged; every Codex adversarial real-finding
# case is KEPT. Under-removal is the safe direction (recall secondary per §-1.3); the chrome-as-claim
# canary backstops the rarer residual classes. FLAG-not-drop: a flagged unit is withheld from the
# rendered rollup, KEPT in evidence; the faithfulness engine (strict_verify / NLI / 4-role / span) is UNCHANGED.
#
# gap 1 — a digit GLUED to an institution keyword ANCHORED to its affiliation preposition (Department
# OF, Laboratory OF/FOR/AT, Institute OF/FOR, …) so an adjective ("2Laboratory-confirmed cases",
# "1Institutional review boards") never matches (Codex iter-1 P1). Real prose spells "a/one/the department";
# only an author-block superscript glues a digit directly to "Department of"/"Institute of"/etc.
_AFFIL_GLUED_RE = re.compile(
    r"\b\d{1,2}(?:Department\s+(?:of|for)\b|Departamento\s+de\b|Faculty\s+of\b|School\s+of\b|"
    r"Institute\s+(?:of|for)\b|University\s+of\b|Universidad\s+de\b|Facultad\s+de\b|Escuela\s+de\b|"
    r"Laborator(?:y|ies)\s+(?:of|for|at)\b|Centre\s+for\b|Center\s+for\b)",
)
# gap 4 — title+affiliation composite: a dash + digit + institution ("A Survey of … - 1 Department of …").
_TITLE_AFFIL_RE = re.compile(
    r"[-–—]\s*\d{1,2}\s+(?:Department\s+of|Institute\s+(?:of|for)|Faculty\s+of|School\s+of|"
    r"University\s+of|Laborator(?:y|ies)\s+(?:of|for|at)|Centre\s+for|Center\s+for)\b",
)
# gap 1 — author-attribution MASTHEAD block: the authorship phrase ("X is listed as an author",
# "… are among the listed authors") AND a co-occurring article-portal MASTHEAD signal (the
# "article has received N accesses/citations/altmetric" engagement-stats furniture). Codex iter-4 P1:
# the phrase ALONE flags a real research-integrity finding ("X is listed as an author on the retracted
# paper"); requiring BOTH the phrase AND the portal-stats co-signal anchors it to the masthead block
# ("Gazdag is listed as an author. The article has received 3258 accesses, 16 citations…") — a real
# integrity/COI finding never co-reports portal engagement stats. Both signals required (precision-first).
_AUTHOR_ATTRIB_PHRASE_RE = re.compile(
    r"\bis listed as an?\s+(?:author|co-author)\b|\bare among the listed authors\b|"
    r"\blisted as (?:the\s+)?(?:author|co-author)s?\b",
    re.IGNORECASE,
)
_MASTHEAD_PORTAL_STATS_RE = re.compile(
    # Codex iter-5 P1: the co-signal must be a TRUE portal-only metric (a number directly followed by
    # "accesses" or "altmetric") — masthead engagement counts a research finding never reports. Bare
    # "N citations" and unconstrained "article has received" are REMOVED: a real integrity/bibliometrics
    # finding legitimately says "received 18 citations before correction", so they are not portal-unique.
    r"\b\d[\d,]*\s+(?:accesses|altmetric)\b",
    re.IGNORECASE,
)
# DROPPED (Codex iter-1/2/3, not precision-safe — surface form overlaps real findings):
#  - gap 2 biblio date+page ("…, July 12, p. 36" vs "The July 12, p. 36 article reported…").
#  - gap 3 bibliometric stats ("3,258 accesses, 16 citations, 7 altmetric" vs real bibliometrics findings;
#    "vascular accesses"). The author-attribution phrase above catches the masthead blocks these appeared in.
#  - gap 1 "Name<digit>, <digit>" author-superscript (titlecase mouse-gene notation "Smad1, 5 and Smad2, 3").
# These rare residual classes are left to the chrome-as-claim canary (enforce, floor 0.05) per §-1.3
# (precision over recall — never risk dropping a real finding).


def _contains_iwire016_gap_furniture(s: str) -> bool:
    """I-wire-016 #1338: precision-safe gap-class furniture rules (validated 0 content false-positives;
    Codex iter-1/2/3 removed every rule whose surface form overlaps a real finding). Catches the
    affiliation/author-attribution masthead blocks; rarer stats/biblio/superscript classes are left to
    the chrome-as-claim canary. FLAG-not-drop: withheld from rollup, kept in evidence; faithfulness UNCHANGED."""
    if _AFFIL_GLUED_RE.search(s) or _TITLE_AFFIL_RE.search(s):
        return True
    # author-attribution masthead: the authorship phrase AND a portal-stats co-signal (both required —
    # Codex iter-4 P1: the phrase alone flags a real integrity/COI finding).
    return bool(_AUTHOR_ATTRIB_PHRASE_RE.search(s) and _MASTHEAD_PORTAL_STATS_RE.search(s))


def _dotted_toc_hits(text: str) -> int:
    """Count dotted section-number tokens whose TitleCase word is NOT a magnitude unit (so a
    "3.2 Million / 4.5 Billion" magnitude pair contributes ZERO ToC hits)."""
    return sum(
        1 for word in _DOTTED_SECTION_TOKEN_RE.findall(text)
        if word.lower() not in _MAGNITUDE_UNIT_WORDS
    )


def _is_predominantly_nonlatin(text: str) -> bool:
    """True iff ``text`` carries a long non-Latin run AND its non-Latin characters outnumber its
    Latin letters — a foreign-page scrape, not an English finding quoting a short foreign term."""
    if not _NONLATIN_RUN_RE.search(text):
        return False
    nonlatin = len(_NONLATIN_CHAR_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    return nonlatin >= _MIN_NONLATIN_RUN_CHARS and nonlatin >= latin


def _contains_forensic_chrome(text: str) -> bool:
    """True iff ``text`` CONTAINS page-furniture chrome (not only IS chrome). The CONTAINMENT
    unblinding ported from scripts/iwire013_sec11_forensic_audit.py, tightened for this drop path
    (see the module comment above). High-precision / structure-anchored; never flags a clean
    finding. Gated by the caller under ``render_chrome_screen_enabled()``."""
    s = text
    low = s.lower()
    # browser/UI · license · author/submission metadata · bibliographic/portal · masthead
    if _NAV_CHROME_RE.search(s) or _LICENSE_CHROME_RE.search(s) or _BIBLIO_CHROME_RE.search(s):
        return True
    # I-deepfix-002 (#1363) FIX-1: cookie/consent banner · DOI-registry error page · foreign masthead
    if _COOKIE_CONSENT_RE.search(s) or _DOI_ERROR_RE.search(s) or _is_foreign_journal_masthead(s):
        return True
    # I-deepfix-001 (#1344) DEFER-4: residual furniture-dominated units — publisher paywall CTA ·
    # working-paper cover masthead/disclaimer · PDF footnote/citation-apparatus run.
    if _is_residual_chrome_furniture(s):
        return True
    # I-deepfix-001 (#1344) chrome_canary_unblind: author-affiliation/email byline · ToC dot-leaders ·
    # "By clicking … you accept" consent banner (the three classes the canary was blind to).
    if _contains_missed_chrome_class(s):
        return True
    if _SUBMISSION_META_RE.search(s) or _MASTHEAD_CHROME_RE.search(s) or _STATS_TABLE_RE.search(s):
        return True
    if _ORCID_RE.search(s) or "orcid" in low or _AFFIL_MIDDOT_RE.search(s):
        return True
    if len(_URL_RE.findall(s)) >= _MIN_URLS_FOR_CHROME:
        return True
    if len(_DOI_URL_RE.findall(s)) >= _MIN_DOI_URLS_FOR_CHROME:
        return True
    # glued markdown header / ToC fragment
    if _INLINE_HEADER_RE.search(s) or _dotted_toc_hits(s) >= _MIN_DOTTED_TOC_HITS:
        return True
    if _STANDALONE_SECTION_NAME_RE.search(s):
        return True
    standalone_dotted = _STANDALONE_DOTTED_HEADING_RE.match(s)
    if standalone_dotted and standalone_dotted.group(1).lower() not in _MAGNITUDE_UNIT_WORDS:
        return True
    # I-wire-016 #1338 gap-fill (affiliation-glued / title+affiliation / author-attribution-phrase) —
    # the precision-safe masthead classes that leaked past the legacy categories.
    if _contains_iwire016_gap_furniture(s):
        return True
    # foreign-page scrape (predominantly non-Latin)
    return _is_predominantly_nonlatin(s)


def render_chrome_screen_enabled() -> bool:
    """Default ON (LAW VI kill-switch ``PG_RENDER_CHROME_SCREEN=0``). When OFF, the NEW
    I-wire-012 chrome categories are skipped and the predicate is byte-identical to the
    legacy base junk screen (boilerplate + sentence-form web-chrome + CAPTCHA)."""
    return os.environ.get(_RENDER_CHROME_SCREEN_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _base_junk(text: str) -> bool:
    """The PRE-I-wire-012 junk screen, byte-equivalent to the old ``_make_junk_screen``
    closure: production boilerplate OR sentence-form web-chrome OR CAPTCHA stub OR a
    unit that reduces to "" under ``strip_web_boilerplate``. Import-safe (access_bypass
    import failure falls back to the chrome + CAPTCHA screens, never fail-open to nothing)."""
    try:
        from src.tools.access_bypass import (  # noqa: PLC0415
            is_boilerplate_or_nonassertional as _boiler,
            strip_web_boilerplate as _strip_boiler,
        )
    except Exception:  # pragma: no cover - access_bypass import is stable in-tree
        return _is_web_chrome(text) or _is_captcha_stub(text)
    try:
        if bool(_boiler(text)) or _is_web_chrome(text) or _is_captcha_stub(text):
            return True
        return not (_strip_boiler(text) or "").strip()
    except Exception:  # pragma: no cover - boiler helpers are pure in-tree
        return _is_web_chrome(text) or _is_captcha_stub(text)


def _is_new_chrome_category(text: str) -> bool:
    """The NEW I-wire-012 chrome categories (default-ON, high-precision) PLUS the I-wire-013 (#1327)
    CONTAINMENT forensic rules (a unit that CONTAINS glued page-furniture, not only IS junk)."""
    if _SHARED_RENDER_CHROME_RE.search(text):
        return True
    if _SHARED_CLAIM_HEADER_CHROME_RE.search(text):
        return True
    if _SHARED_TOC_RE.search(text):
        return True
    if _ORCID_RE.search(text):
        return True
    stripped = text.strip()
    if _DOC_LABEL_RE.match(stripped):
        return True
    if _DOI_ONLY_RE.match(stripped):
        return True
    # I-wire-014 (#1334): the benchmarked whole-unit-collapse furniture screen — a unit DOMINATED
    # by page furniture (journal metrics/cite/permissions/JEL/Associated-Records/member-only/
    # feature-story/cookie-geo/back-matter label runs) with no real clause surviving. Whole-unit
    # decision only (never an inline partial strip), so a real claim with a welded fragment is
    # preserved (validated content_preserved_rate = 1.0 on chrome_gold_augmented).
    try:
        from src.polaris_graph.generator.chrome_furniture_screen import (  # noqa: PLC0415
            is_furniture_dominant,
        )
        if is_furniture_dominant(text):
            return True
    except Exception:  # pragma: no cover - chrome_furniture_screen is stable in-tree
        pass
    # I-wire-013 (#1327): CONTAINMENT unblinding — glued ToC / masthead / author / license /
    # bibliographic / nav / stats-table / foreign-scrape welded into otherwise-real prose.
    return _contains_forensic_chrome(text)


def _is_unrenderable_sentence_form(text: str) -> bool:
    """``require_sentence_form`` extras for a unit that MUST be a standalone complete
    claim (a bullet / a lifted body sentence): a mid-word START cut (a lowercase opener
    is a span sliced mid-token — a real body sentence opens capital/quote/digit) or an
    INCOMPLETE sentence (no sentence-terminal punctuation after stripping a trailing
    ``[N]`` marker). NOT applied to verified-compose / enrichment clauses (which a
    composer may legitimately lowercase / leave mid-clause) — only to bullet/header
    surfaces, so a lowercased verbatim clause is never over-dropped."""
    core = text.strip()
    if not core:
        return True
    first = core[:1]
    if first.islower():
        return True
    no_cite = _SHARED_TRAILING_CITE_RE.sub("", core).rstrip()
    if no_cite and no_cite[-1] not in ".!?\"')]":
        return True
    return False


def is_render_chrome_or_unrenderable(
    text: str,
    *,
    require_sentence_form: bool = False,
    known_words: "set[str] | frozenset[str] | None" = None,
) -> bool:
    """THE ONE shared render-side chrome+truncation predicate (I-wire-012 #1326; I-wire-013 #1327).

    True iff ``text`` is page-furniture chrome, a CAPTCHA/boilerplate stub, a numbered
    ToC / CC-license / masthead / login-wall fragment, a standalone scraped doc label
    ("Abstract"/"AI Summary"), an author-ORCID/affiliation list, a bare DOI row, glued
    page-furniture welded INTO real prose (I-wire-013 CONTAINMENT), or a mid-word/cut-span
    TRUNCATION. With ``require_sentence_form=True`` it ALSO rejects a mid-word-START fragment
    and an incomplete sentence (bullet/header surfaces only).

    ``known_words`` (I-wire-013 #1327): when a caller supplies the run's corpus-vocabulary
    allowlist, the truncation leg ALSO catches a CORPUS-GROUNDED span cut at a ``[N]`` boundary
    (a non-inflectional prefix/suffix of a longer corpus word — "… 1.2 Resea.[14]"). It defaults
    to ``None`` so every existing caller (including the canary) is unchanged: no corpus → the
    boundary-cut leg is skipped → no new false positive.

    SUPPRESS-ONLY: never promotes a unit, never alters a faithfulness VERDICT. The base
    screen (boilerplate/web-chrome/CAPTCHA) ALWAYS runs (preserving the pre-I-wire-012
    behaviour of every existing consumer); the NEW categories + truncation are gated on
    ``render_chrome_screen_enabled()`` (default ON) so a ``PG_RENDER_CHROME_SCREEN=0``
    run is byte-identical to the legacy base screen."""
    if not text or not str(text).strip():
        return True  # an empty unit is non-assertional by definition
    s = str(text)
    if _base_junk(s):
        return True
    if not render_chrome_screen_enabled():
        return False  # NEW categories OFF -> byte-identical to the legacy base screen
    if _is_new_chrome_category(s):
        return True
    try:
        from src.polaris_graph.generator.key_findings import (  # noqa: PLC0415
            is_truncated_fragment,
        )
        # When a corpus allowlist is supplied, treat the unit as eligible at BOTH boundaries so the
        # corpus-grounded span-cut leg fires on a cut at the unit's leading/trailing ``[N]`` edge
        # (the chokepoint splits the report into per-citation units before calling this). With no
        # corpus (known_words=None) the boundary flags are inert and only the marker leg runs.
        _eligible = known_words is not None
        if is_truncated_fragment(
            s,
            known_words,
            ends_before_marker=_eligible,
            starts_after_marker=_eligible,
        ):
            return True
    except Exception:  # pragma: no cover - key_findings is stable in-tree
        pass
    if require_sentence_form and _is_unrenderable_sentence_form(s):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-012 (#1326) — FAIL-LOUD chrome-as-claim CANARY on the SHIPPED report.
#
# A render-integrity tripwire: it measures what FRACTION of the report's CLAIM bullets
# are chrome (page furniture that rendered as a finding) and, in ``enforce`` mode above
# a floor, REFUSES to ship — so a chrome regression can NOT ship as
# ``released_with_disclosed_gaps``. It NEVER promotes a unit and NEVER touches a
# faithfulness verdict. Modes (LAW VI, default-safe):
#   off     — explicit opt-out: no telemetry, no enforce.
#   warn    — emit telemetry to the manifest; never fails the run.
#   enforce — DEFAULT (I-wire-013 #1327): emit telemetry AND fail the run (status flip) when rate > floor.
_RENDER_CANARY_MODE_ENV = "PG_RENDER_CHROME_CANARY"
_RENDER_CANARY_FLOOR_ENV = "PG_RENDER_CHROME_CANARY_FLOOR"
_DEFAULT_RENDER_CANARY_FLOOR = 0.05
_RENDER_CANARY_MODES = ("off", "warn", "enforce")
_DEFAULT_RENDER_CANARY_MODE = "enforce"

# A TOP-LEVEL report bullet (no leading indent) = a claim surface (Key-Findings, the
# per-claim corroboration header, a finding bullet). Indented ``  - SUPPORT:`` /
# ``  - GROUNDED-BUT-WEAK`` sub-bullets (source URLs, not claims) and numbered
# bibliography lines ("1. Title") are deliberately EXCLUDED so the rate measures
# chrome-as-CLAIM, not chrome-as-source-locator.
_TOP_LEVEL_BULLET_RE = re.compile(r"^-\s+(.*\S)\s*$")
_BOLD_MARKER_RE = re.compile(r"\*\*")


def render_chrome_canary_mode() -> str:
    """Canary mode from ``PG_RENDER_CHROME_CANARY`` (off|warn|enforce); default ``enforce``
    (I-wire-013 #1327 — the tripwire enforces by default, not telemetry-only). Fail-loud on an
    UNRECOGNIZED value (LAW II — no silent guessed fallback), mirroring ``render_chrome_canary_floor``.
    ``off`` is the explicit opt-out (telemetry suppressed by the caller; verdict never trips)."""
    raw = os.environ.get(_RENDER_CANARY_MODE_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_RENDER_CANARY_MODE
    mode = raw.strip().lower()
    if mode not in _RENDER_CANARY_MODES:
        raise ValueError(
            f"{_RENDER_CANARY_MODE_ENV}={raw!r} is not a valid chrome-canary mode "
            f"(expected one of {_RENDER_CANARY_MODES})"
        )
    return mode


def render_chrome_canary_floor() -> float:
    """Chrome-as-claim rate floor from ``PG_RENDER_CHROME_CANARY_FLOOR`` (default 0.05).
    Fail-loud on a non-float (LAW II — no silent guessed fallback); clamped to [0, 1]."""
    raw = os.environ.get(_RENDER_CANARY_FLOOR_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_RENDER_CANARY_FLOOR
    try:
        val = float(raw.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{_RENDER_CANARY_FLOOR_ENV}={raw!r} is not a float (chrome-as-claim rate floor)"
        ) from exc
    return min(1.0, max(0.0, val))


def _report_claim_bullets(report_text: str) -> list[str]:
    """The report's TOP-LEVEL claim bullets, bold markers stripped (PURE)."""
    out: list[str] = []
    for line in (report_text or "").split("\n"):
        m = _TOP_LEVEL_BULLET_RE.match(line)
        if not m:
            continue
        out.append(_BOLD_MARKER_RE.sub("", m.group(1)).strip())
    return out


# I-deepfix-001 WS-7 (D3): the chrome canary was BLIND to prose — it scored only top-level claim BULLETS
# (_report_claim_bullets), so an in-prose chrome leak (a leading bare section-header word, an in-text
# "(1, 2)" ref marker, a truncated "(2017)" subject) shipped without tripping the canary (drb_72: 0/33
# bullets flagged while prose leaked). This adds the report's claim-bearing PROSE units to the canary
# DENOMINATOR, screened with the SAME shared predicate, so a prose leak now trips the canary fail-closed.
# MEASUREMENT ONLY — the canary computes a rate/verdict; it NEVER drops or edits a rendered unit (that is
# the render seam's job). Default-ON PG_RENDER_CHROME_CANARY_PROSE; OFF => bullets-only => byte-identical.
_RENDER_CANARY_PROSE_ENV = "PG_RENDER_CHROME_CANARY_PROSE"
_PROSE_UNIT_MIN_CHARS = 40


def _render_canary_prose_enabled() -> bool:
    return os.environ.get(_RENDER_CANARY_PROSE_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


def _report_prose_units(report_text: str) -> list[str]:
    """The report's claim-bearing PROSE units (substantial non-bullet, non-header paragraph lines),
    EXCLUDING scaffolding sections (Bibliography / Methods / disclosures / Source corroboration / the H1
    question echo) whose legitimate DOIs/URLs are not chrome. PURE. These are the units the chrome canary
    was blind to (it scored only top-level bullets)."""
    out: list[str] = []
    in_scaffold = False
    for line in (report_text or "").split("\n"):
        s = line.strip()
        if not s:
            continue
        hdr = _SECTION_HEADER_RE.match(line)
        if hdr:
            title = hdr.group(2).strip().lower()
            in_scaffold = any(title.startswith(t) for t in _SCAFFOLDING_SECTION_TITLES)
            continue
        if in_scaffold:
            continue
        if _TOP_LEVEL_BULLET_RE.match(line) or _LEADING_BULLET_RE.match(line):
            continue  # bullets are already scored by _report_claim_bullets
        if len(s) >= _PROSE_UNIT_MIN_CHARS:
            out.append(_BOLD_MARKER_RE.sub("", s).strip())
    return out


def evaluate_render_chrome_canary(report_text: str) -> dict[str, Any]:
    """Compute the chrome-as-claim rate over the SHIPPED report's claim bullets AND prose units, and the
    canary verdict. PURE (no I/O). ``verdict='fail'`` ONLY in ``enforce`` mode when the rate exceeds the
    floor and there is at least one claim unit — so the caller can flip the run status. In ``warn``/``off``
    the verdict is always ``pass`` (telemetry only). Each chrome unit is screened with the SAME shared
    predicate every composer uses (chrome + truncation), so the canary and the screens can never disagree.
    WS-7 (D3): prose units are added to the denominator (default-ON PG_RENDER_CHROME_CANARY_PROSE) so an
    in-prose chrome leak trips the canary — MEASUREMENT ONLY, no rendered unit is dropped or edited."""
    bullets = _report_claim_bullets(report_text)
    units = list(bullets)
    prose_units = 0
    if _render_canary_prose_enabled():
        prose = _report_prose_units(report_text)
        prose_units = len(prose)
        units = units + prose
    chrome = [b for b in units if is_render_chrome_or_unrenderable(b)]
    total = len(units)
    n_chrome = len(chrome)
    rate = (n_chrome / total) if total else 0.0
    floor = render_chrome_canary_floor()
    mode = render_chrome_canary_mode()
    tripped = bool(total and mode == "enforce" and rate > floor)
    return {
        "mode": mode,
        "floor": floor,
        # WS-7 (D3): denominator now = bullets + prose units. total_claim_bullets kept for back-compat
        # consumers (= total scored units); total_claim_units + prose_units_scored are the explicit names.
        "total_claim_bullets": total,
        "total_claim_units": total,
        "prose_units_scored": prose_units,
        "chrome_claim_bullets": n_chrome,
        "chrome_as_claim_rate": round(rate, 4),
        "verdict": "fail" if tripped else "pass",
        "examples": [b[:120] for b in chrome[:5]],
    }


# ─────────────────────────────────────────────────────────────────────────────
# I-wire-013 (#1327) iter-3a — RENDER-SEAM CHOKEPOINT.
#
# ONE sanitization pass over EVERY claim-bearing unit of the FINAL assembled report (Abstract,
# Key-Findings bullets, every ``###`` section body INCLUDING multi_section_generator output, the
# Corroborated Weighted Findings citation-split blob, the Conclusion), dropping/repairing chrome +
# truncated units with the now-unblinded predicate. This is the single seam that screens the
# currently-unscreened multi_section_generator output (0 screen calls today). It runs AFTER every
# composer + the header-sanity screen and BEFORE the chrome canary, so the canary reads the cleaned
# artifact and a residual leak still trips it fail-closed.
#
# FAITHFULNESS (FROZEN engine): RENDER hygiene only — it SUPPRESSES a page-furniture / truncated
# unit, NEVER promotes one and NEVER touches a strict_verify / NLI / 4-role / span-grounding verdict.
# Page furniture is not a corroborating source, so suppressing it STRENGTHENS faithfulness.
#
# OVER-STRIP SAFE (the drop-path law "over-strip deletes a real finding, worse than a leak"):
#   * Per-``[N]``-unit granularity — a flagged citation unit is dropped WITH its own trailing marker
#     (marker-paired, so a kept finding never loses its citation and a dropped chrome unit never
#     orphans a marker). The 4005-char Corroborated-Weighted-Findings blob keeps every real finding;
#     only its chrome sub-units drop.
#   * Scaffolding sections (Bibliography / Methods / disclosures / Reliability / Source corroboration
#     / the H1 question echo) are EXCLUDED — their legitimate DOIs/URLs are not chrome.
#   * A unit carrying SUBSTANTIAL real prose plus a glued inline ``#`` header is REPAIRED (cut at the
#     header, prefix kept) — the remainder is dropped only when it independently re-tests as chrome,
#     so a real "Limitations: … most extreme.## Analytical synthesis …" paragraph is never lost.

# LAW VI: env-overridable, default ON (kill-switch ``PG_RENDER_SEAM_SANITIZE=0`` => no-op pass-through).
_RENDER_SEAM_SANITIZE_ENV = "PG_RENDER_SEAM_SANITIZE"
# LAW VI: the corpus known-word floor (a word must occur >= this many times across the run's fetched
# source text to count as "known" for the truncation allowlist). Mirrors the detector default.
_RENDER_SEAM_KNOWN_WORD_FLOOR_ENV = "PG_RENDER_SEAM_KNOWN_WORD_FLOOR"
_DEFAULT_KNOWN_WORD_FLOOR = 5
# A unit needs at least this many real-prose characters before a glued inline header in it is
# REPAIRED (prefix kept) rather than the whole unit dropped — below it the unit is treated as junk.
_MIN_REPAIR_PREFIX_CHARS = 40
# Section headers that are pipeline SCAFFOLDING, not carried-up source prose (no body units are
# screened under them; their legitimate DOIs/URLs must not be chrome-flagged). Matched against the
# header TITLE's leading text. Mirrors the detector's _SCAFFOLDING_TITLES.
_SCAFFOLDING_SECTION_TITLES = (
    "reliability header", "methods", "capability disclosures", "contradiction disclosures",
    "bibliography", "source corroboration", "evidence-support disclosure", "research report:",
)
_KNOWN_WORD_FIELDS = ("direct_quote", "statement", "title")
_SECTION_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
# I-wire-017 (#1339) FIX C1: the shallowest header LEVEL (``###`` = 3) that may be dropped when its
# sanitized body collapses to no claim-bearing prose. Top-level (``#``/``##``) report-structure
# headers are never dropped (a top-level empty section is left for the operator to see), only the
# per-claim ``###``-and-deeper content sections that the render seam emptied out.
_MIN_DROPPABLE_EMPTY_HEADER_LEVEL = 3
_LEADING_BULLET_RE = re.compile(r"^\s*-\s+")
# I-wire-013 (#1327) iter-3b D-P1-1: split on BOTH the numeric ``[N]`` marker AND the provenance
# ``[#ev:<id>:<start>-<end>]`` token (single capture group, inner alternation — keeps the
# text/marker pairing in ``_sanitize_report_line`` intact) so the render seam covers per-citation
# units on provenance-cited reports too, not just numeric-cited ones. ``[^\]]*`` captures the whole
# ``[#ev:...]`` body up to its closing bracket. Reports with only ``[N]`` are byte-identical (the
# numeric alternative is unchanged).
_CITATION_SPLIT_RE = re.compile(r"(\[\d+\]|\[#ev:[^\]]*\])")
_INLINE_HEADER_SPLIT_RE = re.compile(r"#{1,6}\s+[A-Za-z]")

# I-deepfix-001 B6(a) (#1350): the per-claim "Source corroboration" section is a SCAFFOLDING title
# (byte-preserved above), so its worst chrome — a page-furniture scrape promoted to a basket HEADER
# bullet ("- **<masthead/ToC/affiliation>** — N verified independent source(s)") — never reaches the
# full containment predicate. This default-ON branch screens the corroboration section's HEADER
# bullets (only) through ``is_render_chrome_or_unrenderable``; a chrome header has its CLAIM TEXT
# replaced by a neutral placeholder while the verified-source COUNT is preserved verbatim. LAW VI
# kill-switch ``PG_CORROBORATION_SANITIZE=0`` => the section stays byte-preserved (pre-B6 behaviour).
#
# §-1.3 CONSOLIDATE-don't-DROP (the dominant HARD RULE, outranks the spec's literal "screen each
# sub-bullet"): the ``- SUPPORT:`` / ``- GROUNDED-BUT-WEAK:`` / ``- CONTRADICTED:`` sub-bullets carry
# a SOURCE locator (url / evidence_id / tier / weight) — NOT a claim — so they are KEEP-ONLY here;
# screening them risks the chrome predicate's "bare DOI/URL row" leg dropping a corroborating source,
# which is a faithfulness violation. A divergence from the seam spec's literal wording, documented in
# the deepfix honest-gaps. Faithfulness-NEUTRAL: this only suppresses a chrome CLAIM string; it never
# drops a source, count, or verdict.
_CORROBORATION_SANITIZE_ENV = "PG_CORROBORATION_SANITIZE"
# The corroboration section's title prefix (lower-cased), matched to scope the branch to ONLY that
# section (Bibliography / Methods / Reliability stay truly byte-preserved).
_CORROBORATION_SECTION_PREFIX = "source corroboration"
# A corroboration HEADER bullet: a TOP-LEVEL ``- **<claim>** — <count> verified ...`` line. The claim
# text is the ``**bold**`` span; the ``— N verified independent source(s)`` suffix is the count. We
# screen only the claim span and preserve the suffix verbatim. A sub-bullet (``  - SUPPORT: ...``) is
# INDENTED, so the no-leading-whitespace anchor here never matches it (sub-bullets are KEEP-ONLY).
_CORROBORATION_HEADER_RE = re.compile(r"^-\s+\*\*(?P<claim>.+?)\*\*(?P<suffix>\s*[—-].*)?$")
# The neutral placeholder a chrome basket header collapses to — the COUNT suffix still carries the
# corroboration; only the unrenderable page-furniture claim string is withheld.
_CORROBORATION_CHROME_PLACEHOLDER = "(claim text withheld — source page-furniture, not a finding)"


def render_seam_sanitize_enabled() -> bool:
    """True iff the default-ON render-seam chokepoint is active (LAW VI kill-switch
    ``PG_RENDER_SEAM_SANITIZE=0`` => byte-identical pass-through)."""
    return os.environ.get(_RENDER_SEAM_SANITIZE_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def corroboration_sanitize_enabled() -> bool:
    """True iff the default-ON B6(a) corroboration-header chrome screen is active (LAW VI kill-switch
    ``PG_CORROBORATION_SANITIZE=0`` => the corroboration section stays byte-preserved)."""
    return os.environ.get(_CORROBORATION_SANITIZE_ENV, "1").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _is_corroboration_section_title(title: str) -> bool:
    """True iff a header title names the per-claim Source-corroboration rollup (B6(a) scope)."""
    return title.strip().lower().lstrip("# ").strip().startswith(_CORROBORATION_SECTION_PREFIX)


def _sanitize_corroboration_header(
    line: str, known_words: "set[str] | frozenset[str] | None"
) -> "tuple[str, int]":
    """B6(a): screen ONE corroboration HEADER bullet. A top-level ``- **<claim>** — N verified ...``
    whose CLAIM span is chrome (page furniture promoted to a basket header) has the claim string
    replaced by a neutral placeholder, preserving the verified-source COUNT suffix verbatim. Returns
    ``(clean_line, suppressed)`` where ``suppressed`` is 1 iff a chrome claim was withheld. A
    sub-bullet (indented) or a non-matching line is returned unchanged with 0. PURE; faithfulness-
    neutral (no source / count / verdict ever dropped)."""
    m = _CORROBORATION_HEADER_RE.match(line)
    if not m:
        return line, 0  # sub-bullet / blank / prose — KEEP-ONLY, untouched
    claim = m.group("claim").strip()
    suffix = m.group("suffix") or ""
    if claim and is_render_chrome_or_unrenderable(claim, known_words=known_words):
        return f"- **{_CORROBORATION_CHROME_PLACEHOLDER}**{suffix}", 1
    return line, 0


def _known_word_floor() -> int:
    """The corpus known-word frequency floor (LAW VI). Fail-soft on a non-int / non-positive value
    to the detector default (the allowlist must never be silently emptied)."""
    raw = os.environ.get(_RENDER_SEAM_KNOWN_WORD_FLOOR_ENV, "").strip()
    if not raw:
        return _DEFAULT_KNOWN_WORD_FLOOR
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_KNOWN_WORD_FLOOR


def build_known_words_from_evidence(evidence_rows: Any, floor: int | None = None) -> set[str]:
    """The corpus-vocabulary allowlist (the truncation false-positive guard) built from the run's OWN
    fetched source text — every lowercase token occurring >= ``floor`` times across the evidence
    rows' ``direct_quote`` / ``statement`` / ``title`` fields. So a word the corpus genuinely uses
    ("labor", "Acemoglu", "computerisation") never false-flags as a span cut, while an absent
    fragment ("Resea", "hodology") does. Accepts a list of row dicts OR a ``{evidence_id: row}`` map
    (the in-memory ``ev_pool`` shape). PURE; returns an empty set when no source text is available
    (=> the caller's truncation leg is simply skipped, never a wrong drop)."""
    if floor is None:
        floor = _known_word_floor()
    if isinstance(evidence_rows, dict):
        rows: Any = evidence_rows.values()
    else:
        rows = evidence_rows or ()
    freq: Counter[str] = Counter()
    for row in rows:
        if not isinstance(row, dict):
            continue
        for field in _KNOWN_WORD_FIELDS:
            value = row.get(field)
            if isinstance(value, str) and value:
                for word in _BOUNDARY_VOCAB_RE.findall(value):
                    freq[word.lower()] += 1
    return {word for word, count in freq.items() if count >= floor}


# An alphabetic vocabulary token (mirrors the detector's _WORD_RE / key_findings._BOUNDARY_WORD_RE).
_BOUNDARY_VOCAB_RE = re.compile(r"[A-Za-z][A-Za-z'\-]*[A-Za-z]|[A-Za-z]")


def _unit_core_for_screen(text: str) -> str:
    """The screen-test text of a unit: leading ``- `` bullet marker and ``**bold**`` markers
    removed so the predicate judges the prose, not the markdown wrapper. PURE."""
    core = _LEADING_BULLET_RE.sub("", text.strip())
    return _BOLD_MARKER_RE.sub("", core).strip()


def _repair_glued_inline_header(text: str, known_words: "set[str] | frozenset[str] | None") -> "str | None":
    """If ``text`` is substantial real prose with a glued inline ``#`` header welded mid-unit, return
    the kept prefix (the header + remainder dropped) — but ONLY when the remainder independently
    re-tests as chrome, so a real paragraph is never over-stripped. Returns ``None`` when no
    repair applies (the caller then drops the whole unit)."""
    m = _INLINE_HEADER_SPLIT_RE.search(text)
    if not m or m.start() < _MIN_REPAIR_PREFIX_CHARS:
        return None
    prefix = text[:m.start()].rstrip()
    remainder = text[m.start():]
    prefix_core = _unit_core_for_screen(prefix)
    # Keep the prefix only if it is itself clean prose AND the excised remainder is independently
    # chrome (over-strip guard: never drop a remainder that re-tests clean).
    if not prefix_core or is_render_chrome_or_unrenderable(prefix_core, known_words=known_words):
        return None
    if not is_render_chrome_or_unrenderable(_unit_core_for_screen(remainder), known_words=known_words):
        return None
    return prefix


def _sanitize_report_line(line: str, known_words: "set[str] | frozenset[str] | None") -> "tuple[str, int]":
    """Sanitize ONE claim-section body line: split it into per-``[N]`` citation units, drop each unit
    (with its own trailing marker) that is chrome or a corpus-grounded truncation cut, and repair a
    unit that is real prose with a glued inline header. Returns ``(clean_line, dropped_count)``. A
    marker-less unit that is the whole short line is dropped iff it is chrome (a standalone ToC /
    masthead line). PURE."""
    parts = _CITATION_SPLIT_RE.split(line)
    segments: list[tuple[str, str]] = []
    i = 0
    while i < len(parts):
        seg_text = parts[i]
        seg_marker = parts[i + 1] if i + 1 < len(parts) else ""
        segments.append((seg_text, seg_marker))
        i += 2
    kept: list[str] = []
    dropped = 0
    # I-wire-017 (#1339) FIX B: when a prose segment is dropped as chrome, the SAME claim's trailing
    # continuation citation markers ("prose[6][7][5]" splits into a prose seg + two marker-only segs)
    # would otherwise survive orphaned. Track the drop and suppress the contiguous marker-only run
    # that immediately follows it. A marker-only run after a KEPT segment stays (it belongs to that
    # kept claim). Withhold-only — the dropped markers' evidence is untouched.
    suppress_trailing_markers = False
    for seg_text, seg_marker in segments:
        if not seg_text.strip() and not seg_marker:
            continue
        # A marker-only continuation segment (no prose, just "[N]") inherits the fate of the prose
        # segment it continues: dropped if that prose segment was dropped, kept otherwise.
        if not seg_text.strip():
            if suppress_trailing_markers:
                dropped += 1
                continue
            kept.append(seg_text + seg_marker)
            continue
        core = _unit_core_for_screen(seg_text)
        if core and is_render_chrome_or_unrenderable(core, known_words=known_words):
            repaired = _repair_glued_inline_header(seg_text, known_words)
            if repaired is not None:
                # Real-prose prefix kept WITH its citation marker (the kept finding stays cited);
                # only the glued-header remainder is excised. The prose survives, so its trailing
                # continuation markers are NOT orphaned — keep them.
                kept.append(repaired + seg_marker)
                dropped += 1
                suppress_trailing_markers = False
                continue
            dropped += 1
            suppress_trailing_markers = True  # orphan this dropped claim's continuation markers
            continue  # whole chrome unit + its marker dropped
        kept.append(seg_text + seg_marker)
        suppress_trailing_markers = False
    return "".join(kept), dropped


def _is_scaffolding_section_title(title: str) -> bool:
    """True iff a header title names a pipeline SCAFFOLDING section (excluded from sanitization)."""
    low = title.strip().lower().lstrip("# ").strip()
    return any(low.startswith(s) for s in _SCAFFOLDING_SECTION_TITLES)


def _line_has_claim_prose(line: str) -> bool:
    """True iff ``line`` carries claim-bearing prose (not just blanks or bare ``[N]`` /
    ``[#ev:...]`` citation markers). Strips leading bullet / ``**bold**`` markers and ALL citation
    markers, then checks any real alphabetic content remains. I-wire-017 (#1339) FIX C1 helper: used
    to decide whether a sanitized section body has collapsed to orphaned markers only. PURE."""
    text_only = "".join(_CITATION_SPLIT_RE.split(line)[::2])  # even indices = non-marker text
    return bool(_unit_core_for_screen(text_only).strip())


def _immediate_parent_is_scaffolding(level: int, header_stack: "list[tuple[int, bool]]") -> bool:
    """True iff the NEAREST strictly-shallower open header (the immediate markdown parent) is a
    scaffolding header — e.g. ``### references`` whose parent is ``## Bibliography``. A non-scaffolding
    header at an intermediate depth BREAKS the chain (it becomes the new parent), so a content section
    under a non-scaffolding parent is NOT protected even if a far ancestor is the report's scaffolding
    ``# Research Report:`` title. ``header_stack`` holds ``(level, is_scaffolding)`` for the open
    ancestor headers, shallowest-first. PURE."""
    for anc_level, anc_scaffolding in reversed(header_stack):
        if anc_level < level:
            return anc_scaffolding
    return False


def _drop_empty_claim_sections(lines: "list[str]") -> "tuple[list[str], int]":
    """I-wire-017 (#1339) FIX C1 post-pass: drop a non-scaffolding ``###``-or-deeper section header
    whose body — after the line-level sanitization already ran — has NO claim-bearing prose left
    (only blank lines / bare orphaned citation markers). Such a section renders as a dangling header
    over "[6][7][5]"; withholding the empty header is suppress-only (the evidence is untouched).

    A SCAFFOLDING header — by its own title OR by having a scaffolding IMMEDIATE parent
    (``### references`` under ``## Bibliography``) — is always preserved. Any top-level (``#``/``##``)
    header is also preserved (a top-level empty section is left for the operator). Returns
    ``(kept_lines, headers_dropped)``. PURE."""
    kept: list[str] = []
    headers_dropped = 0
    # Open ancestor headers as (level, is_scaffolding), shallowest-first; a header at depth d closes
    # every open ancestor at depth >= d before it is pushed.
    header_stack: list[tuple[int, bool]] = []
    i = 0
    n = len(lines)
    while i < n:
        header = _SECTION_HEADER_RE.match(lines[i])
        if not header:
            kept.append(lines[i])
            i += 1
            continue
        level = len(header.group(1))
        title = header.group(2)
        parent_scaffolding = _immediate_parent_is_scaffolding(level, header_stack)
        header_stack = [hs for hs in header_stack if hs[0] < level]
        own_scaffolding = _is_scaffolding_section_title(title)
        header_stack.append((level, own_scaffolding))
        if (
            level < _MIN_DROPPABLE_EMPTY_HEADER_LEVEL
            or own_scaffolding
            or parent_scaffolding
        ):
            kept.append(lines[i])
            i += 1
            continue
        # Collect this section's body up to (not including) the next header of ANY level.
        body_start = i + 1
        j = body_start
        while j < n and not _SECTION_HEADER_RE.match(lines[j]):
            j += 1
        body = lines[body_start:j]
        if any(_line_has_claim_prose(b) for b in body):
            kept.extend(lines[i:j])  # real content survives -> keep header + body verbatim
        else:
            headers_dropped += 1  # empty content section -> drop header + its marker-only body
        i = j
    return kept, headers_dropped


def sanitize_rendered_report(
    report_md: str, known_words: "set[str] | frozenset[str] | None" = None
) -> "tuple[str, int]":
    """THE render-seam chokepoint (I-wire-013 #1327). Run ONE sanitization pass over every
    claim-bearing unit of the assembled ``report_md``, dropping/repairing chrome + truncated units
    with the unblinded ``is_render_chrome_or_unrenderable`` predicate. Returns
    ``(clean_report_md, units_removed)``.

    Scaffolding sections (Bibliography / Methods / disclosures / Reliability / Source corroboration /
    the H1 question echo) are byte-preserved. A glued-chrome HEADER line ("## Dennis Zami …" welded
    onto a title) is dropped; a clean section header is preserved. Default-ON kill-switch
    ``PG_RENDER_SEAM_SANITIZE``; faithfulness-neutral (suppress-only). PURE."""
    if not report_md or not render_seam_sanitize_enabled():
        return report_md, 0
    out_lines: list[str] = []
    removed = 0
    in_scaffolding = False
    # I-deepfix-001 B6(a): tracked SEPARATELY from in_scaffolding. The corroboration section is
    # scaffolding (byte-preserved DOIs/URLs) EXCEPT its per-claim HEADER bullets, which carry a
    # claim string that can be page-furniture chrome. When in_corroboration is set and the B6(a)
    # screen is enabled, header bullets are screened; sub-bullets stay byte-preserved (KEEP-ONLY).
    in_corroboration = False
    corroboration_screen = corroboration_sanitize_enabled()
    for line in report_md.split("\n"):
        header = _SECTION_HEADER_RE.match(line)
        if header:
            title = header.group(2)
            in_scaffolding = _is_scaffolding_section_title(title)
            in_corroboration = _is_corroboration_section_title(title)
            # Screen a glued-chrome header by its TITLE (post-``#`` strip), but never a clean /
            # scaffolding header — dropping a real header would orphan its body.
            if not in_scaffolding and _contains_forensic_chrome(title):
                removed += 1
                continue
            out_lines.append(line)
            continue
        if in_corroboration and corroboration_screen and line.strip():
            # B6(a): inside the corroboration rollup, screen ONLY the per-claim HEADER bullet's
            # claim string (sub-bullets / blanks pass through untouched via the (line, 0) branch).
            clean_line, suppressed = _sanitize_corroboration_header(line, known_words)
            removed += suppressed
            out_lines.append(clean_line)
            continue
        if in_scaffolding or not line.strip():
            out_lines.append(line)
            continue
        clean_line, dropped = _sanitize_report_line(line, known_words)
        removed += dropped
        if clean_line.strip() or not dropped:
            out_lines.append(clean_line)
        # else: the line reduced entirely to chrome -> drop the now-empty line.
    # I-wire-017 (#1339) FIX C1: after the line-level pass, drop any non-scaffolding ###-or-deeper
    # section whose body collapsed to no claim-bearing prose (blank / bare-marker only).
    out_lines, empty_headers_dropped = _drop_empty_claim_sections(out_lines)
    removed += empty_headers_dropped
    return "\n".join(out_lines), removed


def _make_junk_screen() -> Any:
    """Return THE shared render-side chrome+truncation predicate (I-wire-012 #1326).

    Historically this returned a bespoke closure (boilerplate + web-chrome + CAPTCHA).
    It now returns ``is_render_chrome_or_unrenderable`` so every consumer of this hub
    (``verified_compose._compose_junk_screen``, this module's own
    ``_substantive_units`` / ``build_verified_span_draft``) screens through the ONE
    predicate. The base screen still ALWAYS runs (so flag-OFF is byte-identical for
    these consumers); the new chrome categories are added when
    ``PG_RENDER_CHROME_SCREEN`` is ON (default)."""
    return is_render_chrome_or_unrenderable


def _emit_unit(unit: str, eids: Any) -> str:
    """Render one verbatim unit with its ``[ev_id]`` marker(s) INSIDE the sentence.

    Strips trailing terminal punctuation then appends ``[eid]`` for each evidence_id
    (I-beatboth-011 #7 multi-citation: a same-work group emits ALL its grounding
    co-citation markers on the one unit) followed by ``.`` so every marker sits INSIDE
    the sentence unit and survives strict_verify's re-split (see ``_TERMINAL_PUNCT``).
    Accepts a single id (str) or an ordered list of ids; the order is preserved
    (representative first) and is deterministic.
    """
    if isinstance(eids, str):
        ids = [eids]
    else:
        ids = [str(e) for e in (eids or []) if str(e)]
    core = unit.rstrip()
    while core and core[-1] in _TERMINAL_PUNCT:
        core = core[:-1].rstrip()
    marker_str = "".join(f" [{eid}]" for eid in ids)
    return f"{core}{marker_str}."


def _substantive_units(direct_quote: str, *, is_junk: Any) -> list[str]:
    """The source's verbatim sentence-units that are citable claims, longest-first.

    Splits with the SAME ``split_into_sentences`` strict_verify re-splits with, so
    each emitted unit is one gate unit. Keeps a unit only if it clears
    ``_MIN_UNIT_CHARS``, carries a real letter, is NOT boilerplate/chrome per the
    shared ``is_junk`` screen, and carries no ``[...]`` (which would be mis-read as a
    marker). Ordered longest-first so the per-source budget keeps the most
    content-bearing sentences (most likely the real finding).
    """
    from src.polaris_graph.generator.provenance_generator import (  # noqa: PLC0415
        split_into_sentences,
    )

    max_chars = max_unit_chars()
    units: list[str] = []
    for raw_unit in split_into_sentences(direct_quote) or []:
        # I-beatboth-011 #4 (#1289): strip C0 control bytes (incl. a literal NUL) from
        # the unit BEFORE any length/screen check so a control byte can never reach the
        # render and the bound measures clean printable chars.
        unit = _strip_control_bytes(raw_unit or "").strip()
        if len(unit) < _MIN_UNIT_CHARS:
            continue
        # I-beatboth-011 #4 (#1289): a unit longer than the render bound is structurally
        # a fetch-shell / raw-extraction blob (the 75K equation dump), never a clinical
        # sentence — DROP it. NOT a breadth cap (source count uncapped); NOT a verify
        # gate (strict_verify untouched). A real long quote is sentence-split upstream.
        if len(unit) > max_chars:
            continue
        if not any(ch.isalpha() for ch in unit):
            continue
        # `[...]`-shaped substrings inside a quote would be mis-read as markers
        # by _rewrite_draft_with_spans; a unit carrying one is skipped (rare; keeps
        # the marker contract unambiguous rather than risk a false token bind).
        if "[" in unit and "]" in unit:
            continue
        if is_junk(unit):
            continue
        units.append(unit)
    units.sort(key=len, reverse=True)
    return units


# I-beatboth-011 #7 (#1289) — SAME-WORK CONSOLIDATION identity (§-1.3 CONSOLIDATE-
# DON'T-DROP). Two unbound SUPPORTS members are the SAME WORK when they share a
# normalized DOI, else a folded title PLUS a corroborating discriminator. KEEP ALL
# their URLs as corroborating locators of the ONE work, but COUNT/PRESENT them as ONE
# source (multi-URL corroboration), never N independent sources. Identity ladder
# mirrors the existing ``_m51_canonical_identity`` convention (evidence_selector.py:
# 2781): DOI first, else title(+discriminator), else (fallback) the evidence_id itself
# so a member with neither stays its own distinct unit (never wrongly merged).
#
# I-beatboth-011 #4 (#1289) — P1 OVER-MERGE FIX (§-1.3: NEVER merge distinct works;
# under-merge is safe, over-merge corrupts breadth/attribution). The no-DOI branch
# MUST NOT merge on folded TITLE ALONE — two genuinely DIFFERENT works can share a
# normalized title and would be wrongly collapsed, losing distinct corroborators. So
# the no-DOI key requires the folded title PLUS the FIRST PRESENT corroborating
# discriminator the records share, in this fixed priority order: publication YEAR →
# first-author SURNAME → VENUE/journal → URL HOST. A priority-ordered composite (NOT
# pairwise OR / union-find, which is non-transitive and over-merges through chains) is
# a plain equality key, biased to UNDER-merge. Title-with-no-discriminator stays its
# own ev-id singleton (distinct). This key computation is the SHARED canonical contract
# with ``synthesis/finding_dedup.py`` and is duplicated BYTE-FOR-BYTE there (the
# no-new-source-file rule forbids a shared module).
_DOI_PREFIX_RE = re.compile(r"^\s*(?:doi\s*:?\s*|https?://(?:dx\.)?doi\.org/)", re.IGNORECASE)
_TITLE_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")
_WHITESPACE_RUN_RE = re.compile(r"\s+")
# Publication-year validity bounds (SHARED with the selector's _row_year convention
# at evidence_selector.py:769-770 and finding_dedup._row_year). Outside => absent.
_MIN_YEAR = 1900
_MAX_YEAR = 2100


def _normalize_doi(raw: Any) -> str:
    """Normalized DOI for same-work grouping ('' when absent/unusable).

    SHARED contract with ``finding_dedup._normalize_doi``: strip a leading
    ``doi:`` / ``https://doi.org/`` / ``http://dx.doi.org/`` prefix, lowercase,
    ``rstrip("/")``; a USABLE DOI starts with the ``10.`` registrant prefix.
    """
    doi = str(raw or "").strip()
    if not doi:
        return ""
    doi = _DOI_PREFIX_RE.sub("", doi).strip().lower().rstrip("/")
    # A usable DOI starts with the ``10.`` registrant prefix; anything else is noise.
    return doi if doi.startswith("10.") else ""


def _normalize_title(raw: Any) -> str:
    """Normalized title key for same-work grouping ('' when too short to be safe).

    SHARED with ``finding_dedup._fold_title``: lowercase, collapse non-alphanumeric
    runs to a single space, strip; require >= 12 chars (a tiny/generic title is an
    over-merge risk).
    """
    title = str(raw or "").strip().lower()
    title = _TITLE_NORMALIZE_RE.sub(" ", title).strip()
    # Guard against an over-merge on a tiny/generic title: require real substance.
    return title if len(title) >= 12 else ""


def _record_title(ev: dict[str, Any]) -> str:
    """The record's title across the schema aliases (``source_title`` is canonical;
    ``title`` / ``page_title`` / ``name`` are the validator-mapped variants).

    SHARED precedence with ``finding_dedup._row_title`` so the two consolidators
    fold the SAME title field.
    """
    for key in ("source_title", "title", "page_title", "name"):
        value = ev.get(key)
        if value:
            return str(value)
    return ""


def _record_year(ev: dict[str, Any]) -> str:
    """Publication year as a discriminator token ('' when absent/invalid).

    Reads ``ev['year']`` else ``ev['metadata']['year']`` and validates [1900, 2100]
    — the SHARED convention with the selector's ``_row_year`` (evidence_selector.py:
    793-809) and ``finding_dedup._row_year``.
    """
    val = ev.get("year")
    if val is None:
        meta = ev.get("metadata")
        if isinstance(meta, dict):
            val = meta.get("year")
    if val is None:
        return ""
    try:
        year = int(val)
    except (TypeError, ValueError):
        return ""
    return str(year) if _MIN_YEAR <= year <= _MAX_YEAR else ""


def _first_author_surname(ev: dict[str, Any]) -> str:
    """First-author surname (folded) as a discriminator token ('' when absent).

    Records carry ``authors`` (a list, family-name-first, e.g. ``["Autor D", ...]``)
    or a singular ``author`` string. The surname is the FIRST whitespace token of the
    first author, lowercased + non-alphanumerics stripped. SHARED with
    ``finding_dedup._first_author_surname``.
    """
    raw = ev.get("authors")
    first = ""
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if entry and str(entry).strip():
                first = str(entry).strip()
                break
    elif raw:
        first = str(raw).strip()
    if not first:
        single = ev.get("author")
        if single and str(single).strip():
            first = str(single).strip()
    if not first:
        return ""
    surname = first.split()[0] if first.split() else ""
    surname = _TITLE_NORMALIZE_RE.sub("", surname.lower())
    return surname


def _record_venue(ev: dict[str, Any]) -> str:
    """Venue/journal (folded) as a discriminator token ('' when absent).

    Reads ``venue`` else ``journal``, lowercased with non-alphanumeric runs
    collapsed to a single space and trimmed. SHARED with ``finding_dedup._row_venue``.
    """
    raw = ev.get("venue") or ev.get("journal") or ""
    text = str(raw).strip().lower()
    if not text:
        return ""
    text = _TITLE_NORMALIZE_RE.sub(" ", text)
    return _WHITESPACE_RUN_RE.sub(" ", text).strip()


def _record_host(ev: dict[str, Any]) -> str:
    """URL host (no leading ``www.``) as the WEAKEST discriminator token.

    Same-work fetches usually span DIFFERENT hosts, so host merges almost nothing —
    it is last in the priority order purely as a safety net. SHARED with
    ``finding_dedup._row_host`` (which delegates to ``_host_of``); the host reduction
    here is inlined (no urllib import already present) but produces the SAME token.
    """
    from urllib.parse import urlparse  # noqa: PLC0415

    url = str(ev.get("source_url", "") or ev.get("url", "") or "")
    if not url:
        return ""
    host = (urlparse(url).hostname or "").lower().strip()
    if host.startswith("www."):
        host = host[4:]
    return host


def _title_discriminator(ev: dict[str, Any]) -> str:
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
    at DIFFERENT URLs, so they (almost) always differ on host (the ``_record_host``
    safety-net premise + §-1.3). Host therefore appears ONLY as the SECOND weak signal
    alongside year, and NEVER in the strong-path token — otherwise every legitimate
    same-work merge (which spans different hosts) would be blocked.

    Returns '' when neither a strong signal nor (year AND host) is present, so the record
    stays a title-only singleton and is never merged on title alone. SHARED contract with
    ``finding_dedup._title_discriminator`` (byte-identical key string).
    """
    year = _record_year(ev)
    surname = _first_author_surname(ev)
    venue = _record_venue(ev)
    host = _record_host(ev)
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


def _work_identity(eid: str, ev: dict[str, Any]) -> str:
    """Same-work group key for one member: DOI, else title(+discriminator), else its
    own ev_id.

    I-beatboth-011 #4 (#1289): the no-DOI branch NEVER merges on folded title ALONE
    (two different works can share a title). It requires the folded title AND the
    FIRST present discriminator (year → first-author surname → venue → host).
    Title-with-no-discriminator falls through to the evidence_id (never a constant),
    so a member with neither a DOI nor (usable title + discriminator) stays its OWN
    distinct unit — consolidation can only MERGE genuine same-work duplicates, never
    collapse unrelated works. Matches ``finding_dedup._same_work_key``.
    """
    doi = _normalize_doi(ev.get("doi"))
    if doi:
        return f"doi:{doi}"
    title = _normalize_title(_record_title(ev))
    if title:
        discriminator = _title_discriminator(ev)
        if discriminator:
            return f"title:{title}|{discriminator}"
    return f"ev:{eid}"


def _member_quote(ev: dict[str, Any]) -> str:
    """The member's render-safe direct quote (control bytes stripped)."""
    raw = (ev.get("direct_quote") or ev.get("statement") or "")
    return _strip_control_bytes(str(raw)).strip()


def build_verified_span_draft(ev_ids: Any, evidence_pool: Any) -> str:
    """Deterministic verbatim-span draft for the enrichment section (FIX K).

    Emits, in the caller's relevance/weight order, up to ``spans_per_source()`` of each
    WORK's own verbatim sentence-units, each with its legacy ``[ev_id]`` marker placed
    INSIDE the sentence, so ``_rewrite_draft_with_spans`` binds each unit to its best
    in-quote span and ``strict_verify`` validates it.

    I-beatboth-011 #4 (#1289) — RENDER SAFETY: every emitted span is control-byte
    sanitized (NO NUL / C0 bytes ever reach the report) and a unit exceeding the render
    char bound (a 75K raw-extraction blob) is dropped. A CAPTCHA / Cloudflare security
    stub member is dropped by the junk screen.

    I-beatboth-011 #7 (#1289) — SAME-WORK CONSOLIDATION (§-1.3 CONSOLIDATE-DON'T-DROP):
    members that are the SAME WORK (same normalized DOI, else title) are grouped into
    ONE multi-citation unit-set — counted/presented as ONE source — instead of N. ALL
    the work's URLs are KEPT as corroborating locators: a corroborator's ``[ev_id]``
    marker is attached to a unit ONLY when that corroborator's OWN quote actually
    contains the emitted unit, so every emitted marker is span-grounded by construction
    (this NEVER changes which members verify — the representative would verify alone;
    corroborators only ADD already-grounding co-citations). A truncated-intro duplicate
    of the representative contributes its URL as a corroborator, not a separate source.

    A source whose quote is boilerplate/chrome/CAPTCHA, pool-absent, or has no
    substantive unit contributes nothing. Returns the joined draft ("" => caller renders
    the existing gap stub, never a silent success). NO LLM, NO faithfulness-gate touch.
    """
    pool = evidence_pool or {}
    is_junk = _make_junk_screen()
    budget = spans_per_source()

    # Group ev_ids into same-work buckets, PRESERVING the caller's relevance/weight
    # order: a work's bucket is keyed by its FIRST-seen member, so the highest-ordered
    # member of each work is the representative and the bucket order is the work order.
    work_order: list[str] = []
    work_members: dict[str, list[str]] = {}
    for ev_id in (ev_ids or []):
        eid = str(ev_id or "")
        if not eid:
            continue
        ev = pool.get(eid)
        if not isinstance(ev, dict):
            continue
        direct_quote = _member_quote(ev)
        # Drop CAPTCHA stubs / boilerplate at the WHOLE-member level up front.
        if not direct_quote or is_junk(direct_quote):
            continue
        key = _work_identity(eid, ev)
        if key not in work_members:
            work_members[key] = []
            work_order.append(key)
        work_members[key].append(eid)

    parts: list[str] = []
    for key in work_order:
        member_eids = work_members[key]
        representative = member_eids[0]
        rep_ev = pool.get(representative)
        if not isinstance(rep_ev, dict):
            continue
        rep_quote = _member_quote(rep_ev)
        units = _substantive_units(rep_quote, is_junk=is_junk)
        if not units:
            continue
        # Pre-compute each corroborator's sanitized quote ONCE for the contains-check.
        corroborator_quotes = [
            (m, _member_quote(pool[m]))
            for m in member_eids[1:]
            if isinstance(pool.get(m), dict)
        ]
        for unit in units[:budget]:
            # The representative ALWAYS grounds (its own quote contains the unit). Attach
            # a corroborator marker ONLY when that corroborator's own quote also contains
            # the unit — so every emitted marker is span-grounded and no member's verify
            # status changes. ALL same-work members retain their URL as a co-locator;
            # those whose fetch differs simply do not add a (would-fail) marker.
            markers = [representative]
            for m_eid, m_quote in corroborator_quotes:
                if unit in m_quote and m_eid not in markers:
                    markers.append(m_eid)
            parts.append(_emit_unit(unit, markers))
    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# I-deepfix-001 WS-3 (#1344) — NUMBERED "Evidence base" breadth surface.
#
# THE LEAK (drb_72 "12 of 88 cited"): the FULL ordered unbound-SUPPORTS surface from
# ``select_unbound_supports_by_weight`` is already UNCAPPED (weighted_enrichment.py:295,469,573),
# but nothing RENDERS it as a numbered reference block, so most span-verified sources never
# receive a ``[N]`` citation. This surfaces EVERY source that carries a surviving isolated-
# ``SUPPORTS`` span into ONE numbered "Evidence base" section: one numbered entry per distinct
# WORK (same-work CONSOLIDATION, §-1.3 — never N entries for one work), each entry = that work's
# OWN verbatim span unit(s) tagged with its ``[ev_id]`` marker(s) so the downstream bibliography
# numberer assigns each a real ``[N]``.
#
# §-1.3 — WEIGHT-and-CONSOLIDATE, never FILTER-and-CAP: this is SURFACING breadth (keep-all), NOT a
# cap / floor / thinner. The input ``ev_ids`` is already the uncapped ordered surface; this ONLY
# renders it. Faithfulness is UNTOUCHED — each emitted unit is a verbatim span carrying a legacy
# ``[ev_id]`` marker that flows through the UNCHANGED ``_rewrite_draft_with_spans`` -> ``strict_verify``
# exactly like every other section; a unit that cannot ground is dropped by that gate, never padded.
# The SAME render-safety screens as ``build_verified_span_draft`` apply (control-byte strip, junk
# screen, per-unit char bound, same-work consolidation). Default-ON;
# ``PG_BREADTH_EVIDENCE_BASE_SECTION=0`` => returns "" => no section => byte-identical legacy output.
_ENV_EVIDENCE_BASE_SECTION = "PG_BREADTH_EVIDENCE_BASE_SECTION"
_EVIDENCE_BASE_TITLE = "Evidence base"


def evidence_base_section_enabled() -> bool:
    """Kill-switch ``PG_BREADTH_EVIDENCE_BASE_SECTION`` (default ON). OFF => the numbered
    Evidence base section is not rendered (``build_evidence_base_section`` returns "") =>
    byte-identical legacy output."""
    return os.environ.get(_ENV_EVIDENCE_BASE_SECTION, "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def build_evidence_base_section(
    ev_ids: Any,
    evidence_pool: Any,
    *,
    start_index: int = 1,
) -> str:
    """Render the FULL ordered unbound-SUPPORTS surface as ONE numbered "Evidence base" markdown
    section so EVERY source with a surviving span gets a ``[N]`` citation.

    ``ev_ids`` is the ordered surface from ``select_unbound_supports_by_weight`` (already uncapped —
    NO cap / floor / thinner is applied here). Members are CONSOLIDATED into same-work buckets
    (§-1.3 keep-all-count-once): one numbered entry per distinct work, in the caller's
    relevance/weight order, each carrying its verbatim span unit(s) + the ``[ev_id]`` marker(s) the
    downstream span-binder + ``strict_verify`` re-check.

    Returns "" when the flag is OFF, ``ev_ids`` is empty, or no surfaced source yields a substantive
    verbatim unit (caller renders nothing — byte-identical). NO LLM; NO faithfulness-gate touch.
    """
    if not evidence_base_section_enabled():
        return ""
    ev_ids = list(ev_ids or [])
    if not ev_ids:
        return ""
    pool = evidence_pool or {}
    is_junk = _make_junk_screen()
    budget = spans_per_source()

    # Same-work grouping, PRESERVING the caller's relevance/weight order (mirrors
    # ``build_verified_span_draft``: a work's bucket is keyed by its FIRST-seen member so the
    # highest-ordered member of each work is the representative and bucket order is work order).
    work_order: list[str] = []
    work_members: dict[str, list[str]] = {}
    for ev_id in ev_ids:
        eid = str(ev_id or "")
        if not eid:
            continue
        ev = pool.get(eid)
        if not isinstance(ev, dict):
            continue
        direct_quote = _member_quote(ev)
        if not direct_quote or is_junk(direct_quote):
            continue
        key = _work_identity(eid, ev)
        if key not in work_members:
            work_members[key] = []
            work_order.append(key)
        work_members[key].append(eid)

    lines: list[str] = []
    number = start_index
    for key in work_order:
        member_eids = work_members[key]
        representative = member_eids[0]
        rep_ev = pool.get(representative)
        if not isinstance(rep_ev, dict):
            continue
        rep_quote = _member_quote(rep_ev)
        units = _substantive_units(rep_quote, is_junk=is_junk)
        if not units:
            continue
        # Pre-compute each corroborator's sanitized quote ONCE for the contains-check (same-work URLs
        # co-cite ONLY when their own fetch actually contains the emitted unit — span-grounded markers).
        corroborator_quotes = [
            (m, _member_quote(pool[m]))
            for m in member_eids[1:]
            if isinstance(pool.get(m), dict)
        ]
        emitted: list[str] = []
        for unit in units[:budget]:
            markers = [representative]
            for m_eid, m_quote in corroborator_quotes:
                if unit in m_quote and m_eid not in markers:
                    markers.append(m_eid)
            emitted.append(_emit_unit(unit, markers))
        if not emitted:
            continue
        lines.append(f"{number}. {' '.join(emitted)}")
        number += 1

    if not lines:
        return ""
    return f"## {_EVIDENCE_BASE_TITLE}\n\n" + "\n".join(lines)
