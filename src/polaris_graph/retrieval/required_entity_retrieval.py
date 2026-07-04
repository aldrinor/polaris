"""I-complete-004 (#1190): targeted required-entity retrieval lane.

PURPOSE
=======
Some clinical must-cover S0 safety entities (contraindications, dosing limits,
boxed warnings, regulatory status) live on drug-label / guideline pages
(DailyMed, accessdata.fda.gov, EMA, NICE, Health Canada, NIH ODS) that the
generic Serper/S2 research corpus rarely surfaces. When that content is absent
from the cited corpus, the report cannot make verified contraindication/dosing
claims and the must-cover slots gap-disclose — the recurring cause of
`four_role_held` on clinical questions (#1188 + canary diagnosis).

This lane is an ENV-GATED, additive retry. For each must-cover entity that is
STILL unsatisfied after the normal V30 frame fetch, it:

1. Builds TARGETED safety queries (intervention anchor x entity safety term)
   biased to an authoritative clinical-authority domain set UNION the entity's
   OWN ``url_pattern`` host, and fires them through ``search_fn`` (Serper) to
   DISCOVER candidate authoritative URLs.
2. FETCHES the discovered candidate URLs through the EXISTING live-retrieval
   pipeline (``retrieval_fn`` = ``run_live_retrieval`` with ``seed_urls`` +
   ``seed_only=True`` — the same AccessBypass/Zyte chokepoint, no Serper/S2
   fan-out), producing canonical evidence rows that carry their REAL fetched
   URLs.
3. RETURNS those evidence rows so the caller MERGES them into the corpus
   (``evidence_for_gen``) — exactly like the saturation gap-round merge.

FAITHFULNESS (§-1.1 — LETHAL otherwise)
=======================================
The discovered rows are injected as ORDINARY corpus evidence carrying their REAL
fetched URLs — they are NEVER keyed to an entity_id and NEVER relabeled with an
entity's canonical ``url_pattern`` (the citation-faithfulness lie). All
downstream gating is UNCHANGED: the generator can fill a must-cover slot ONLY if
the new evidence passes the SAME strict_verify, and the 4-role coverage gate
(`_entity_canonical_match`, operator-locked, NOT touched here) still requires
EXACT canonical-identifier equality. An entity with no verifiable authoritative
content stays the gap-disclosure it already was — no fabrication, no forced
coverage.

HONEST SCOPE
============
Because the 4-role coverage gate for url-pattern regulatory entities requires
``record.url == entity.url_pattern`` EXACTLY, injecting an ALTERNATE authoritative
URL CANNOT flip that specific entity's coverage. What this lane does is get the
authoritative SAFETY CONTENT into the corpus so the generator can write VERIFIED
contraindication / dosing claims (directly addressing #1190's "absent from the
cited research corpus"). It flips 4-role coverage only for DOI/PMID-keyed
entities, or when the entity's exact ``url_pattern`` is itself among the fetched
URLs — not for the url-pattern regulatory entity class as a rule.

PURITY / TESTABILITY
====================
``run_required_entity_lane`` takes the search and retrieval callables by
DEPENDENCY INJECTION (``search_fn`` / ``retrieval_fn``). Production wires the
real Serper search and ``run_live_retrieval``; tests pass deterministic stubs.
NO network in this module. The caller owns the env gate and the corpus merge.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass

logger = logging.getLogger(__name__)

# --- env gate (HARD constraint 1: flag-OFF = byte-identical) ------------------
_LANE_ENABLED_ENV = "PG_REQUIRED_ENTITY_RETRIEVAL"

# --- authoritative-domain set (LAW VI: named const, env-overridable) ----------
# The operator-approved clinical-authority set. Each entity's OWN url_pattern
# host is UNIONed onto this per-entity so url-only-canonical entities
# (ods.od.nih.gov, accessdata.fda.gov, health-products.canada.ca) are reachable
# in the targeted search (the default list alone does not cover them).
_REQUIRED_ENTITY_DOMAINS_ENV = "PG_REQUIRED_ENTITY_DOMAINS"
_DEFAULT_REQUIRED_ENTITY_DOMAINS: tuple[str, ...] = (
    "fda.gov",
    "dailymed.nlm.nih.gov",
    "ema.europa.eu",
    "nice.org.uk",
    "who.int",
    "drugs.com",
)

# --- bounds (HARD constraint 3: named consts, env-overridable, no runaway) ----
# Max distinct targeted queries fired per unsatisfied entity.
_MAX_QUERIES_PER_ENTITY_ENV = "PG_REQUIRED_ENTITY_MAX_QUERIES_PER_ENTITY"
_DEFAULT_MAX_QUERIES_PER_ENTITY = 3
# Max unsatisfied entities the lane will process in one run.
_MAX_ENTITIES_ENV = "PG_REQUIRED_ENTITY_MAX_ENTITIES"
_DEFAULT_MAX_ENTITIES = 12
# Max search results requested per targeted query (discovery width).
_MAX_RESULTS_PER_QUERY_ENV = "PG_REQUIRED_ENTITY_MAX_RESULTS_PER_QUERY"
_DEFAULT_MAX_RESULTS_PER_QUERY = 5
# Max candidate URLs FETCHED per entity (the billed fetch cap for this lane).
_MAX_SEED_URLS_PER_ENTITY_ENV = "PG_REQUIRED_ENTITY_MAX_SEED_URLS_PER_ENTITY"
_DEFAULT_MAX_SEED_URLS_PER_ENTITY = 3

# --- query-length safety bounds (I-deepfix-001 #1344, L5 fix) -----------------
# The research-question-anchored gap / coverage queries prepend the WHOLE
# question to each entity. On drb_72 the raw question was 2116 chars, so the
# built ``<question> <entity>`` query blew past Serper's 2048-char ``q`` hard
# limit -> HTTP 400 "query too long" -> the lane merged 0 rows and every derived
# entity stayed a gap. Two env-overridable (LAW VI) bounds fix it:
#   * the ANCHOR is clipped to its first N chars (mirrors the _intervention_anchor
#     ``[:120]`` fallback) so the question can never dominate the query, and
#   * the FINAL built query string is hard-clipped to the Serper ceiling as a
#     last-line defence for a pathologically long entity term.
# This bounds a QUERY STRING length only — it NEVER drops a source
# (§-1.3 WEIGHT-AND-CONSOLIDATE, not FILTER): a length-bounded query makes the
# coverage lane actually reach Serper instead of 400-ing to zero rows.
_QUERY_ANCHOR_MAX_CHARS_ENV = "PG_REQUIRED_ENTITY_QUERY_ANCHOR_MAX_CHARS"
_DEFAULT_QUERY_ANCHOR_MAX_CHARS = 120
_SERPER_QUERY_MAX_CHARS_ENV = "PG_SERPER_QUERY_MAX_CHARS"
_DEFAULT_SERPER_QUERY_MAX_CHARS = 2048

# --- minimum verifiable span (mirrors contract_section_runner default) --------
# A METADATA_ONLY row whose direct_quote is shorter than this has no verifiable
# span to cite — it is treated as UNSATISFIED (the same floor the gap-routing in
# contract_section_runner.py:370-386 uses). Env-overridable (LAW VI).
_MIN_VERIFIABLE_SPAN_ENV = "PG_MIN_VERIFIABLE_SPAN_CHARS"
_DEFAULT_MIN_VERIFIABLE_SPAN_CHARS = 50

# --- safety-term phrasings per S0 category (deterministic, no magic strings) --
# Maps an entity's s0_category -> the safety phrasing appended to the
# intervention anchor to build a targeted query. A category absent here falls
# back to the generic safety terms below (still bounded).
_S0_CATEGORY_QUERY_TERMS: dict[str, tuple[str, ...]] = {
    "contraindications": ("contraindications", "who should not take", "warnings"),
    "dosing_limits": ("dosing", "maximum dose", "tolerable upper intake limit"),
    "black_box_warnings": ("boxed warning", "black box warning", "safety"),
    "regulatory_status": ("label", "approval status", "prescribing information"),
}
_GENERIC_SAFETY_TERMS: tuple[str, ...] = (
    "safety adverse effects",
    "contraindications",
    "dosing",
)

# Caller-supplied source/origin labels so the merged rows are honestly tagged
# as required-entity-lane discoveries (not mislabeled as primary-trial seeds).
SEED_SOURCE_LABEL = "required_entity_lane"
SEED_QUERY_ORIGIN = "required_entity_targeted_search"


@dataclass
class RequiredEntityLaneResult:
    """Outcome of one lane invocation (for the manifest / audit trail).

    ``evidence_rows`` are the NEWLY fetched corpus rows (real fetched URLs) the
    caller merges into ``evidence_for_gen``. The lane NEVER mutates the frame
    rows. All counts are deterministic.
    """

    evidence_rows: list[dict[str, Any]] = field(default_factory=list)
    attempted_entity_ids: tuple[str, ...] = ()
    queries_by_entity: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    seed_urls: tuple[str, ...] = ()


def lane_enabled() -> bool:
    """True iff the env gate is set. Flag-OFF = byte-identical (no lane)."""
    return os.getenv(_LANE_ENABLED_ENV, "0").strip() in ("1", "true", "True")


def _min_verifiable_span_chars() -> int:
    try:
        return int(os.getenv(_MIN_VERIFIABLE_SPAN_ENV, str(_DEFAULT_MIN_VERIFIABLE_SPAN_CHARS)))
    except ValueError:
        return _DEFAULT_MIN_VERIFIABLE_SPAN_CHARS


def _bounded_int_env(name: str, default: int) -> int:
    """Read a non-negative int env knob; fall back to default on bad value."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(0, value)


def _query_anchor_max_chars() -> int:
    return _bounded_int_env(
        _QUERY_ANCHOR_MAX_CHARS_ENV, _DEFAULT_QUERY_ANCHOR_MAX_CHARS
    )


def _serper_query_max_chars() -> int:
    return _bounded_int_env(
        _SERPER_QUERY_MAX_CHARS_ENV, _DEFAULT_SERPER_QUERY_MAX_CHARS
    )


def _bounded_anchor(research_question: str) -> str:
    """Whitespace-collapsed research question clipped to the query-anchor char
    ceiling (mirrors :func:`_intervention_anchor`'s ``[:120]`` fallback).

    Bounding the anchor length keeps the built ``<anchor> <entity>`` query inside
    Serper's 2048-char ``q`` limit so a long question no longer 400s the coverage
    lane. It bounds a QUERY STRING length only — no source is dropped (§-1.3).
    A ``0`` ceiling (explicit operator override) disables the anchor clip.
    """
    collapsed = " ".join((research_question or "").split()).strip()
    limit = _query_anchor_max_chars()
    return collapsed[:limit] if limit > 0 else collapsed


def _bounded_gap_query(anchor: str, entity: str) -> str:
    """Build ``<anchor> <entity>`` and hard-clip to the Serper query ceiling.

    The anchor is already length-bounded by :func:`_bounded_anchor`; this final
    clip is the belt-and-suspenders guarantee that NO built query can exceed the
    Serper ``q`` limit even for a pathologically long entity term. A ``0``
    ceiling (explicit operator override) disables the final clip.
    """
    query = f"{anchor} {entity}".strip() if anchor else (entity or "").strip()
    limit = _serper_query_max_chars()
    if limit > 0 and len(query) > limit:
        query = query[:limit].rstrip()
    return query


def required_entity_domains() -> tuple[str, ...]:
    """The authoritative clinical-authority domain set (LAW VI: env-overridable).

    ``PG_REQUIRED_ENTITY_DOMAINS`` is a comma-separated override; blank entries
    are dropped. Empty/absent -> the operator-approved default set.
    """
    raw = os.getenv(_REQUIRED_ENTITY_DOMAINS_ENV)
    if raw is None or not raw.strip():
        return _DEFAULT_REQUIRED_ENTITY_DOMAINS
    domains = tuple(part.strip() for part in raw.split(",") if part.strip())
    return domains or _DEFAULT_REQUIRED_ENTITY_DOMAINS


def entity_url_host(url_pattern: Optional[str]) -> Optional[str]:
    """Return the bare host of an entity's ``url_pattern`` (no scheme/port/path).

    Used to UNION the entity's own canonical host onto the per-entity domain
    bias so url-only-canonical entities are reachable. Returns None when the
    pattern is empty or carries no host.
    """
    if not url_pattern or not isinstance(url_pattern, str):
        return None
    try:
        host = urlsplit(url_pattern.strip()).netloc
    except ValueError:
        return None
    if not host:
        return None
    # Strip any userinfo / port; keep the bare registrable host.
    host = host.split("@")[-1].split(":")[0].strip().lower()
    return host or None


def frame_row_is_unsatisfied(row: FrameRow, *, min_span_chars: Optional[int] = None) -> bool:
    """An entity is UNSATISFIED iff its FrameRow has no verifiable span.

    Mirrors the gap-routing test in contract_section_runner.py:370-386:
    FRAME_GAP_UNRECOVERABLE, OR METADATA_ONLY with a direct_quote shorter than
    the minimum verifiable span. Any other class (OPEN_ACCESS / ABSTRACT_ONLY /
    HUMAN_CURATED / METADATA_ONLY-with-real-quote) is already satisfied.
    """
    floor = _min_verifiable_span_chars() if min_span_chars is None else min_span_chars
    if row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        return True
    if row.provenance_class == ProvenanceClass.METADATA_ONLY:
        return len((row.direct_quote or "").strip()) < floor
    return False


def _intervention_anchor(
    *,
    entity_meta: Optional[Any],
    scope_overrides: Optional[Mapping[str, Any]],
    research_question: str,
) -> str:
    """Pick the cleanest anchor for the targeted query (deterministic order).

    Priority: the contract entity's ``label_name`` (cleanest, e.g. "Mounjaro");
    then ``scope_overrides['intervention']``; then a trimmed prefix of the
    research question. Never empty (the question is always present).
    """
    label_name = getattr(entity_meta, "label_name", None) if entity_meta is not None else None
    if isinstance(label_name, str) and label_name.strip():
        return label_name.strip()
    if scope_overrides:
        intervention = scope_overrides.get("intervention")
        if isinstance(intervention, str) and intervention.strip():
            return intervention.strip()
    # Fallback: first chunk of the research question (bounded for query sanity).
    return (research_question or "").strip()[:120]


def build_targeted_queries(
    *,
    entity: Mapping[str, Any],
    intervention_anchor: str,
    max_queries: Optional[int] = None,
) -> tuple[str, ...]:
    """Build the targeted safety queries for one unsatisfied entity.

    ``<intervention_anchor> <safety term>`` per the entity's ``s0_category``
    (falling back to generic safety terms). Deterministic order, de-duplicated,
    capped at ``max_queries`` (env-bounded). The authoritative-domain ``site:``
    bias is applied by the search backend via the ``domains=`` argument, NOT
    baked into the query string here.
    """
    cap = (
        _bounded_int_env(_MAX_QUERIES_PER_ENTITY_ENV, _DEFAULT_MAX_QUERIES_PER_ENTITY)
        if max_queries is None
        else max(0, max_queries)
    )
    s0_category = entity.get("s0_category")
    terms = _S0_CATEGORY_QUERY_TERMS.get(s0_category or "", _GENERIC_SAFETY_TERMS)
    anchor = (intervention_anchor or "").strip()
    queries: list[str] = []
    seen: set[str] = set()
    for term in terms:
        query = f"{anchor} {term}".strip() if anchor else term.strip()
        key = query.lower()
        if query and key not in seen:
            seen.add(key)
            queries.append(query)
        if len(queries) >= cap:
            break
    return tuple(queries)


# --- R3 (#1344): field-agnostic still-missing-entity gap-detect ---------------
# Max targeted gap queries the general still-missing-entity detector emits per run
# (compute-safety bound; each query still flows the unchanged weight-and-consolidate
# path + frozen verify — §-1.3, never a breadth target).
_MISSING_ENTITY_MAX_QUERIES_ENV = "PG_MISSING_ENTITY_GAP_MAX_QUERIES"
_DEFAULT_MISSING_ENTITY_MAX_QUERIES = 12


def entity_covered_in_corpus(entity_term: str, corpus_texts: Sequence[str]) -> bool:
    """True iff ``entity_term`` appears (case-insensitive substring) in ANY of the
    corpus texts (titles / quotes / statements the caller supplies).

    This is a DETECT-only signal for the R3 gap-detect: a required entity whose
    name never appears in the gathered corpus is a candidate for a targeted
    corrective retrieval. It is deliberately lenient (substring, case-folded) so a
    present-but-differently-cased mention still counts as covered — the detector
    must never over-fire a corrective round for an entity the corpus already has.
    """
    needle = " ".join((entity_term or "").split()).strip().lower()
    if not needle:
        return True  # empty term is vacuously "covered" — never fire a query for it
    for text in corpus_texts or ():
        if needle in (text or "").lower():
            return True
    return False


def missing_entity_gap_queries(
    *,
    required_entities: Sequence[str],
    corpus_texts: Sequence[str],
    research_question: str,
    max_queries: Optional[int] = None,
) -> list[str]:
    """R3 (#1344): derive targeted corrective queries for STILL-MISSING required
    entities — field-agnostic (no clinical-safety literal).

    DRB-II 2nd-order recall rubrics need a chained fact: A -> find entity -> fact
    B. The up-front decomposition fans out once and the single-pass CRAG loop can
    stop before the chain closes, so entities the task requires but the corpus
    never surfaced stay uncovered. This detector compares the REQUIRED entities
    against what the corpus actually mentions (:func:`entity_covered_in_corpus`)
    and emits ONE research-question-anchored targeted query per STILL-MISSING
    entity. Each query flows the SAME weight-and-consolidate retrieval + the
    UNCHANGED frozen verify — this only decides WHAT to search next, never drops
    a source or relaxes a gate (§-1.3).

    Anchoring to the research question keeps the corrective query on-subject (the
    same drift fix FS-Researcher's scope-anchor applies) so a bare entity name
    does not generalise into its broad field.

    Args:
        required_entities: entity names/labels the task requires covered.
        corpus_texts: the text the corpus currently carries (titles, direct
            quotes, statements) used to decide coverage.
        research_question: the retrieval anchor prepended to each gap query.
        max_queries: override for `PG_MISSING_ENTITY_GAP_MAX_QUERIES` (tests).

    Returns:
        An ordered, de-duplicated, capped list of targeted gap queries — one per
        still-missing entity. Empty iff every required entity is already covered
        (the caller then fires no corrective round).
    """
    cap = (
        _bounded_int_env(
            _MISSING_ENTITY_MAX_QUERIES_ENV, _DEFAULT_MISSING_ENTITY_MAX_QUERIES
        )
        if max_queries is None
        else max(0, max_queries)
    )
    anchor = _bounded_anchor(research_question)
    queries: list[str] = []
    seen: set[str] = set()
    for raw_entity in required_entities or ():
        entity = " ".join((raw_entity or "").split()).strip()
        if not entity:
            continue
        if entity_covered_in_corpus(entity, corpus_texts):
            continue
        query = _bounded_gap_query(anchor, entity)
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(query)
        if len(queries) >= cap:
            break
    return queries


def _domains_for_entity(entity: Mapping[str, Any]) -> list[str]:
    """Authoritative domains UNION the entity's own ``url_pattern`` host."""
    domains = list(required_entity_domains())
    host = entity_url_host(entity.get("url_pattern"))
    if host and host not in domains:
        domains.append(host)
    return domains


def _result_url(hit: Any) -> str:
    """Extract a candidate URL from a single Serper result row (or raw string)."""
    if isinstance(hit, str):
        return hit.strip()
    if isinstance(hit, Mapping):
        for key in ("url", "link"):
            value = hit.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def run_required_entity_lane(
    *,
    frame_rows: Sequence[FrameRow],
    entity_meta_by_id: Mapping[str, Any],
    entity_cfg_by_id: Mapping[str, Mapping[str, Any]],
    research_question: str,
    scope_overrides: Optional[Mapping[str, Any]],
    search_fn: Callable[..., Any],
    retrieval_fn: Callable[..., Any],
) -> RequiredEntityLaneResult:
    """Run the targeted required-entity lane (ENV-GATED by the CALLER).

    For each UNSATISFIED FrameRow:
      1. Build + fire targeted authoritative-domain-biased search queries via
         ``search_fn(query, domains=, max_results=)`` and COLLECT the candidate
         URLs (capped per-entity and total-entities).
      2. FETCH the collected candidate URLs through ``retrieval_fn`` (the live
         retriever) with ``seed_urls`` + ``seed_only=True`` — same Zyte
         chokepoint, no Serper/S2 fan-out — producing canonical evidence rows
         carrying their REAL fetched URLs.

    Returns the NEWLY fetched evidence rows for the CALLER to merge into the
    corpus (dedup + evidence_id renumber, like the saturation gap-round). The
    lane NEVER mutates ``frame_rows`` and NEVER keys a row to an entity_id, so a
    fetched row can never be relabeled as the entity (provenance honesty).

    DEPENDENCY INJECTION: ``search_fn`` and ``retrieval_fn`` are injected so this
    is pure / offline-testable. The caller owns the env gate (``lane_enabled()``).
    """
    max_entities = _bounded_int_env(_MAX_ENTITIES_ENV, _DEFAULT_MAX_ENTITIES)
    max_results = _bounded_int_env(
        _MAX_RESULTS_PER_QUERY_ENV, _DEFAULT_MAX_RESULTS_PER_QUERY
    )
    max_seed_urls = _bounded_int_env(
        _MAX_SEED_URLS_PER_ENTITY_ENV, _DEFAULT_MAX_SEED_URLS_PER_ENTITY
    )
    floor = _min_verifiable_span_chars()

    attempted: list[str] = []
    queries_by_entity: dict[str, tuple[str, ...]] = {}
    seed_urls: list[str] = []
    seen_seed: set[str] = set()

    for row in frame_rows:
        if len(attempted) >= max_entities:
            break
        if not frame_row_is_unsatisfied(row, min_span_chars=floor):
            continue
        entity_id = row.entity_id
        entity_cfg = entity_cfg_by_id.get(entity_id)
        if entity_cfg is None:
            # No config to anchor the targeted query on — cannot act; skip.
            continue
        attempted.append(entity_id)

        anchor = _intervention_anchor(
            entity_meta=entity_meta_by_id.get(entity_id),
            scope_overrides=scope_overrides,
            research_question=research_question,
        )
        queries = build_targeted_queries(
            entity=entity_cfg, intervention_anchor=anchor
        )
        queries_by_entity[entity_id] = queries

        # (1) Targeted authoritative-domain-biased search -> DISCOVER candidate
        # URLs (consume the search output). Errors are non-fatal: a failed query
        # simply yields no candidates for that entity.
        domains = _domains_for_entity(entity_cfg)
        entity_urls: list[str] = []
        for query in queries:
            try:
                hits = search_fn(query, domains=domains, max_results=max_results)
            except Exception:  # noqa: BLE001 — discovery is best-effort
                logger.warning(
                    "required_entity_lane: search failed for entity=%s query=%r",
                    entity_id,
                    query,
                )
                continue
            for hit in hits or []:
                url = _result_url(hit)
                if not url or url in seen_seed:
                    continue
                seen_seed.add(url)
                entity_urls.append(url)
                if len(entity_urls) >= max_seed_urls:
                    break
            if len(entity_urls) >= max_seed_urls:
                break
        seed_urls.extend(entity_urls)

    if not seed_urls:
        return RequiredEntityLaneResult(
            evidence_rows=[],
            attempted_entity_ids=tuple(attempted),
            queries_by_entity=queries_by_entity,
            seed_urls=(),
        )

    # (2) FETCH the discovered URLs through the existing live retriever, seed-only
    # (no Serper/S2 fan-out), so each candidate is fetched + classified through
    # the SAME chokepoint and emerges as a canonical evidence row with its REAL
    # url. A retrieval failure leaves the corpus unchanged (best-effort).
    try:
        result = retrieval_fn(
            research_question=research_question,
            amplified_queries=[],
            seed_urls=list(seed_urls),
            seed_only=True,
            seed_source=SEED_SOURCE_LABEL,
            seed_query_origin=SEED_QUERY_ORIGIN,
            anchor_seed=False,
        )
    except Exception:  # noqa: BLE001 — a failed fetch leaves the corpus as-is
        logger.warning(
            "required_entity_lane: live-retrieval fetch raised for %d seed urls; "
            "leaving corpus unchanged",
            len(seed_urls),
        )
        return RequiredEntityLaneResult(
            evidence_rows=[],
            attempted_entity_ids=tuple(attempted),
            queries_by_entity=queries_by_entity,
            seed_urls=tuple(seed_urls),
        )

    evidence_rows = list(getattr(result, "evidence_rows", []) or [])
    return RequiredEntityLaneResult(
        evidence_rows=evidence_rows,
        attempted_entity_ids=tuple(attempted),
        queries_by_entity=queries_by_entity,
        seed_urls=tuple(seed_urls),
    )


# ============================================================================
# COVERAGE LEVER L5 — question/facet-derived required-entity retrieval lane
# ============================================================================
# I-deepfix-001 (#1344) DRB-II COVERAGE lever L5.
#
# The R3 gap-detect (:func:`missing_entity_gap_queries`) already turns a KNOWN
# list of required entities into targeted corrective queries. L5 closes the
# remaining gap: it DERIVES that required-entity set from the QUESTION and the
# FACET tree (the R1 :mod:`expert_facet_planner` output) — deterministically and
# OFFLINE — so the lane runs even when no external rubric hands us the list. It
# then targets ONLY the derived entities the corpus does not yet mention and
# fetches candidate sources for them through the SAME injected live-retrieval
# chokepoint the clinical lane uses (seed-only, no Serper/S2 fan-out).
#
# FAITHFULNESS (§-1.1 / operator BINDING — LETHAL otherwise)
# ----------------------------------------------------------
# Identical contract to the clinical lane: fetched rows are ORDINARY corpus
# evidence carrying their REAL fetched URLs; they are NEVER keyed to an entity
# and NEVER relabeled. strict_verify / NLI entailment / 4-role D8 / provenance /
# span-grounding are UNCHANGED. A derived required entity for which the lane
# surfaces NO evidence STAYS exactly the gap disclosure it already was — it is
# recorded in ``gap_entities`` and NOTHING is injected for it (no fabrication, no
# forced coverage). Deriving an entity only decides WHAT to search next; it can
# never credit coverage on its own (§-1.3 WEIGHT-AND-CONSOLIDATE, never
# FILTER / FORCE). The per-entity + per-run bounds are compute-safety CEILINGS
# billed by actual use — never a breadth target / cap / thinner / floor.
#
# DEFAULT-ON kill-switch (LAW VI): ``PG_COVERAGE_L5_REQUIRED_ENTITY`` defaults
# ON; set it to 0/false/off for a byte-identical no-op.
# ============================================================================

# --- default-ON kill-switch (LAW VI) ------------------------------------------
_COVERAGE_L5_ENABLED_ENV = "PG_COVERAGE_L5_REQUIRED_ENTITY"

# --- compute-safety CEILING on derived entities (NOT a breadth target; §-1.3) -
_COVERAGE_L5_MAX_ENTITIES_ENV = "PG_COVERAGE_L5_MAX_ENTITIES"
_DEFAULT_COVERAGE_L5_MAX_ENTITIES = 24

# Honest source/origin tags so merged L5 rows are attributed to THIS lane (never
# mislabeled as clinical-lane seeds or primary-trial seeds).
COVERAGE_L5_SEED_SOURCE_LABEL = "required_entity_coverage_l5"
COVERAGE_L5_SEED_QUERY_ORIGIN = "required_entity_coverage_l5_targeted_search"

# Question words / articles / conjunctions / pronouns / common lead verbs that
# must NOT seed (or continue) a proper-noun run — a sentence-initial capital or a
# Title-Cased function word is not a named entity. Compared case-folded, so a
# capitalized "The"/"In" inside a Title-Case facet name still breaks the run.
_ENTITY_STOPWORDS: frozenset = frozenset({
    "the", "a", "an", "and", "or", "but", "of", "for", "to", "in", "on", "at",
    "by", "with", "from", "as", "how", "what", "why", "when", "where", "which",
    "who", "whom", "whose", "does", "do", "did", "is", "are", "was", "were",
    "will", "would", "can", "could", "should", "shall", "may", "might", "must",
    "has", "have", "had", "this", "that", "these", "those", "it", "its", "their",
    "our", "your", "his", "her", "into", "about", "over", "under", "between",
})
# Lowercase name-internal connectives allowed to BRIDGE a proper-noun run, but
# ONLY when the next token is itself a capitalized non-stopword ("Bank of
# England", "University of Toronto"). "and"/"or" are deliberately EXCLUDED so a
# list ("Ozempic and Mounjaro") splits into distinct entities instead of merging.
_ENTITY_CONNECTIVES: frozenset = frozenset({
    "of", "de", "von", "van", "der", "di", "da", "del", "du", "la", "le",
    "dos", "das", "ter",
})

# One word-ish token: starts alnum, keeps internal &./'- (so "GLP-1", "U.S.",
# "S&P" survive as single tokens). Surrounding punctuation/quotes are dropped.
_ENTITY_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9&./'\-]*")
# Explicitly quoted spans (straight + curly) are trusted entity phrases verbatim.
_STRAIGHT_QUOTE_RE = re.compile(r'"([^"\n]{2,80})"')
_CURLY_QUOTE_RE = re.compile("[“]([^”\n]{2,80})[”]")

# Fetch-width bounds are SHARED with the clinical lane (same lane family, same
# chokepoint): PG_REQUIRED_ENTITY_MAX_RESULTS_PER_QUERY / _MAX_SEED_URLS_PER_ENTITY.


def coverage_l5_enabled() -> bool:
    """True unless the L5 kill-switch is explicitly disabled (DEFAULT-ON, LAW VI).

    ``PG_COVERAGE_L5_REQUIRED_ENTITY`` defaults ON; only an explicit
    ``0``/``false``/``no``/``off`` (case-insensitive) disables the lane, after
    which it is a byte-identical no-op. Blank/unset => ON.
    """
    return (os.getenv(_COVERAGE_L5_ENABLED_ENV, "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _coverage_l5_max_entities() -> int:
    return _bounded_int_env(
        _COVERAGE_L5_MAX_ENTITIES_ENV, _DEFAULT_COVERAGE_L5_MAX_ENTITIES
    )


def _entity_tokens(text: str) -> list[str]:
    return _ENTITY_TOKEN_RE.findall(text or "")


def _quoted_spans(text: str) -> list[str]:
    """Return explicitly quoted spans (straight + curly). Trusted verbatim."""
    out: list[str] = []
    out.extend(_STRAIGHT_QUOTE_RE.findall(text or ""))
    out.extend(_CURLY_QUOTE_RE.findall(text or ""))
    return out


def _proper_noun_phrases(text: str, *, max_run_tokens: int = 6) -> list[str]:
    """Deterministic proper-noun phrase extraction (offline, no LLM).

    A "run" is a maximal sequence of capitalized non-stopword tokens, bridged
    only by a lowercase name-internal connective that is immediately followed by
    another capitalized non-stopword token. Sentence-initial function words and
    Title-Cased articles break the run (they are stopwords, compared case-folded)
    so a question like "How does AI ..." yields "AI", not "How". Over-inclusion is
    harmless here — an extra derived entity only fires ONE bounded targeted query
    and can never credit coverage (verify is unchanged); under-merging (splitting
    "Ozempic and Mounjaro") is preferred over wrongly welding two distinct names.
    """
    toks = _entity_tokens(text)
    n = len(toks)
    phrases: list[str] = []
    i = 0
    while i < n:
        tok = toks[i]
        low = tok.lower()
        is_head = (
            tok[:1].isupper()
            and low not in _ENTITY_STOPWORDS
            and any(c.isalpha() for c in tok)
        )
        if not is_head:
            i += 1
            continue
        run = [tok]
        j = i + 1
        while j < n and len(run) < max_run_tokens:
            t = toks[j]
            tl = t.lower()
            if (
                t[:1].isupper()
                and tl not in _ENTITY_STOPWORDS
                and any(c.isalpha() for c in t)
            ):
                run.append(t)
                j += 1
                continue
            # connective bridge: lowercase name-internal word flanked by a
            # following capitalized non-stopword token (peek ahead).
            if (
                tl in _ENTITY_CONNECTIVES
                and (j + 1) < n
                and toks[j + 1][:1].isupper()
                and toks[j + 1].lower() not in _ENTITY_STOPWORDS
            ):
                run.append(t)
                j += 1
                continue
            break
        # Trim any trailing connective (defensive — the lookahead prevents it).
        while run and run[-1].lower() in _ENTITY_CONNECTIVES:
            run.pop()
        if run and any(len(r) >= 2 and any(c.isalpha() for c in r) for r in run):
            phrases.append(" ".join(run))
        i = j if j > i else i + 1
    return phrases


def _facet_text(facet: Any) -> str:
    """Extract the display text of one facet (Mapping / Facet-like / str)."""
    if isinstance(facet, Mapping):
        for key in ("name", "facet", "title", "label", "text"):
            value = facet.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
    name = getattr(facet, "name", None)
    if isinstance(name, str) and name.strip():
        return name
    if isinstance(facet, str):
        return facet
    return ""


def _explicit_facet_entities(facet: Any) -> list[str]:
    """Curated entity names carried on a facet Mapping (trusted verbatim)."""
    if not isinstance(facet, Mapping):
        return []
    out: list[str] = []
    for key in ("entities", "required_entities"):
        value = facet.get(key)
        if not isinstance(value, (list, tuple)):
            continue
        for item in value:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, Mapping):
                name = item.get("name") or item.get("label") or item.get("id")
                if isinstance(name, str):
                    out.append(name)
    return out


def extract_required_entities(
    research_question: str,
    facets: Optional[Sequence[Any]] = None,
    *,
    max_entities: Optional[int] = None,
) -> tuple[str, ...]:
    """Derive the required-entity set from the QUESTION and the FACET tree.

    DETERMINISTIC / OFFLINE — no network, no LLM. The set is the union of:

    1. Curated entity names carried explicitly on a facet Mapping
       (``entities`` / ``required_entities``) — trusted verbatim, added first.
    2. Proper-noun phrases + quoted spans in the research question.
    3. Proper-noun phrases + quoted spans in each facet's display text.

    De-duplicated case-insensitively (first-appearance order preserved) and
    capped at ``max_entities`` (``PG_COVERAGE_L5_MAX_ENTITIES``, a compute-safety
    CEILING — §-1.3, never a breadth target). ``facets`` accepts a heterogeneous
    sequence of strings, :class:`~...expert_facet_planner.Facet` objects, or
    Mappings; unknown shapes are skipped (fail-safe).
    """
    cap = _coverage_l5_max_entities() if max_entities is None else max(0, max_entities)
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(term: Any) -> None:
        if not isinstance(term, str):
            return
        cleaned = " ".join(term.split()).strip().strip('"“”').strip()
        if len(cleaned) < 2:
            return
        key = cleaned.lower()
        if key in seen:
            return
        seen.add(key)
        ordered.append(cleaned)

    # 1. explicit curated entity lists (highest confidence, added first)
    for facet in facets or ():
        for name in _explicit_facet_entities(facet):
            _add(name)

    # 2. proper nouns + quoted spans from the research question
    for phrase in _proper_noun_phrases(research_question or ""):
        _add(phrase)
    for span in _quoted_spans(research_question or ""):
        _add(span)

    # 3. proper nouns + quoted spans from each facet's display text
    for facet in facets or ():
        text = _facet_text(facet)
        if not text:
            continue
        for phrase in _proper_noun_phrases(text):
            _add(phrase)
        for span in _quoted_spans(text):
            _add(span)

    return tuple(ordered[:cap])


@dataclass
class CoverageL5Result:
    """Outcome of one L5 lane invocation (for the manifest / audit trail).

    ``evidence_rows`` are the NEWLY fetched corpus rows (real fetched URLs) the
    caller merges into ``evidence_for_gen`` (same dedup + evidence_id renumber
    the saturation gap-round + clinical lane use). ``gap_entities`` are the
    derived required entities for which the lane surfaced NO candidate source —
    they STAY gap disclosures (nothing injected, no fabrication). All counts are
    deterministic and the lane NEVER mutates its inputs.
    """

    evidence_rows: list = field(default_factory=list)
    derived_entities: tuple = ()
    missing_entities: tuple = ()
    queries_by_entity: Mapping = field(default_factory=dict)
    gap_entities: tuple = ()
    seed_urls: tuple = ()


def run_l5_required_entity_coverage(
    *,
    research_question: str,
    facets: Optional[Sequence[Any]],
    corpus_texts: Sequence[str],
    search_fn: Callable[..., Any],
    retrieval_fn: Callable[..., Any],
    domains: Optional[Sequence[str]] = None,
) -> CoverageL5Result:
    """Run the COVERAGE lever L5 lane (DEFAULT-ON, self-gated).

    Pipeline:
      1. DERIVE the required-entity set from ``research_question`` + ``facets``
         (:func:`extract_required_entities`).
      2. Keep ONLY the derived entities the corpus does not already mention
         (:func:`entity_covered_in_corpus`) — the lenient substring coverage
         signal that never over-fires for a present entity.
      3. For each still-missing entity, fire ONE research-question-anchored
         targeted ``search_fn`` query and COLLECT candidate URLs (bounded). An
         entity that surfaces ZERO candidates is recorded in ``gap_entities`` and
         STAYS a gap disclosure — nothing is injected for it.
      4. FETCH the collected URLs through ``retrieval_fn`` seed-only (same Zyte
         chokepoint, no Serper/S2 fan-out) and RETURN the fetched rows for the
         caller to merge. Rows carry their REAL fetched URLs and are NEVER keyed
         to an entity nor relabeled (provenance honesty — the operator-locked
         exact-equality coverage gate cannot be tricked).

    ``domains`` defaults to an EMPTY bias (field-agnostic — L5 spans economics,
    technology, policy, ... so it must NOT bias to a clinical-authority set). The
    caller may pass a bias set. DEPENDENCY-INJECTED ``search_fn`` / ``retrieval_fn``
    keep this pure / offline-testable. Kill-switch OFF => empty no-op result.
    """
    if not coverage_l5_enabled():
        return CoverageL5Result()

    derived = extract_required_entities(research_question, facets)
    if not derived:
        return CoverageL5Result(derived_entities=derived)

    missing = tuple(
        entity
        for entity in derived
        if not entity_covered_in_corpus(entity, corpus_texts)
    )
    if not missing:
        return CoverageL5Result(derived_entities=derived, missing_entities=())

    max_results = _bounded_int_env(
        _MAX_RESULTS_PER_QUERY_ENV, _DEFAULT_MAX_RESULTS_PER_QUERY
    )
    max_seed_urls = _bounded_int_env(
        _MAX_SEED_URLS_PER_ENTITY_ENV, _DEFAULT_MAX_SEED_URLS_PER_ENTITY
    )
    bias = list(domains or [])
    anchor = _bounded_anchor(research_question)

    queries_by_entity: dict[str, str] = {}
    seed_urls: list[str] = []
    seen_seed: set[str] = set()
    gap_entities: list[str] = []

    for entity in missing:
        query = _bounded_gap_query(anchor, entity)
        queries_by_entity[entity] = query
        try:
            hits = search_fn(query, domains=bias, max_results=max_results)
        except Exception:  # noqa: BLE001 — discovery is best-effort
            logger.warning("coverage_l5: search failed for entity=%r", entity)
            hits = None
        entity_urls: list[str] = []
        for hit in hits or []:
            url = _result_url(hit)
            if not url or url in seen_seed:
                continue
            seen_seed.add(url)
            entity_urls.append(url)
            if len(entity_urls) >= max_seed_urls:
                break
        if not entity_urls:
            # No candidate authoritative source surfaced -> the entity STAYS a
            # gap disclosure (never fabricated, never forced-covered).
            gap_entities.append(entity)
        seed_urls.extend(entity_urls)

    if not seed_urls:
        return CoverageL5Result(
            evidence_rows=[],
            derived_entities=derived,
            missing_entities=missing,
            queries_by_entity=queries_by_entity,
            gap_entities=tuple(gap_entities),
            seed_urls=(),
        )

    try:
        result = retrieval_fn(
            research_question=research_question,
            amplified_queries=[],
            seed_urls=list(seed_urls),
            seed_only=True,
            seed_source=COVERAGE_L5_SEED_SOURCE_LABEL,
            seed_query_origin=COVERAGE_L5_SEED_QUERY_ORIGIN,
            anchor_seed=False,
        )
    except Exception:  # noqa: BLE001 — a failed fetch leaves the corpus as-is
        logger.warning(
            "coverage_l5: live-retrieval fetch raised for %d seed urls; "
            "leaving corpus unchanged",
            len(seed_urls),
        )
        return CoverageL5Result(
            evidence_rows=[],
            derived_entities=derived,
            missing_entities=missing,
            queries_by_entity=queries_by_entity,
            gap_entities=tuple(gap_entities),
            seed_urls=tuple(seed_urls),
        )

    evidence_rows = list(getattr(result, "evidence_rows", []) or [])
    return CoverageL5Result(
        evidence_rows=evidence_rows,
        derived_entities=derived,
        missing_entities=missing,
        queries_by_entity=queries_by_entity,
        gap_entities=tuple(gap_entities),
        seed_urls=tuple(seed_urls),
    )
