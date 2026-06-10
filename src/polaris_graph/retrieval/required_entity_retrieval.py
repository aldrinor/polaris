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
