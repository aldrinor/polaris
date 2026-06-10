"""I-complete-004 (#1190): targeted required-entity retrieval lane.

PURPOSE
=======
Some clinical must-cover S0 safety entities (contraindications, dosing limits,
boxed warnings, regulatory status) live on drug-label / guideline pages
(DailyMed, accessdata.fda.gov, EMA, NICE, Health Canada, NIH ODS) that the
generic Serper/S2 research corpus rarely surfaces. When the V30 Phase-2 frame
fetch (`fetch_compiled_frame`) returns those entities as GAPS, the contract
slot honestly gap-discloses — but the gap recurs across clinical questions and
holds the 4-role release gate (`four_role_held`).

This lane is a SECOND-CHANCE, ENV-GATED retry on EXACTLY the must-cover entities
that came back unsatisfied. For each unsatisfied entity it:

1. Builds TARGETED search queries (intervention anchor x entity safety term)
   biased to an authoritative clinical-authority domain set UNION the entity's
   OWN ``url_pattern`` host — for corpus discovery + telemetry.
2. RE-FETCHES the entity's OWN canonical ``url_pattern`` through the existing
   deterministic ``fetch_frame_entity`` (AccessBypass/Zyte chokepoint). If the
   re-fetch now yields a non-gap FrameRow with a verifiable span, the gap row is
   REPLACED in place; otherwise the gap row is left untouched.

FAITHFULNESS (§-1.1 — LETHAL otherwise)
=======================================
The lane CANNOT fabricate or force a slot. It only re-binds an entity to content
fetched from THAT ENTITY'S OWN canonical ``url_pattern`` — so the satisfied
FrameRow always carries the entity's REAL resolved URL, never a relabel of
foreign content (the citation-faithfulness lie). All downstream gating is
UNCHANGED: the slot fills only if the new evidence passes the SAME strict_verify
and the SAME EXACT-equality ``_entity_canonical_match`` in the 4-role gate. An
entity with no verifiable authoritative content stays the gap it already was.

The targeted SEARCH results are NOT injected as the entity's coverage evidence
(that would risk relabeling); search is for discovery/telemetry only. Coverage
re-binding happens ONLY via the entity's own ``url_pattern`` re-fetch.

PURITY / TESTABILITY
====================
``run_required_entity_lane`` takes the search and fetch callables by DEPENDENCY
INJECTION (``search_fn`` / ``fetch_fn``). Production wires the real Serper search
and ``fetch_frame_entity``; tests pass deterministic stubs. NO network here.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence
from urllib.parse import urlsplit

from src.polaris_graph.nodes.frame_compiler import EvidenceBinding
from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass

logger = logging.getLogger(__name__)

# --- env gate (HARD constraint 1: flag-OFF = byte-identical) ------------------
_LANE_ENABLED_ENV = "PG_REQUIRED_ENTITY_RETRIEVAL"

# --- authoritative-domain set (LAW VI: named const, env-overridable) ----------
# The operator-approved clinical-authority set. Each entity's OWN url_pattern
# host is UNIONed onto this per-entity so url-only-canonical entities
# (ods.od.nih.gov, accessdata.fda.gov, health-products.canada.ca) are reachable
# under the EXACT-equality coverage rule the default list alone cannot satisfy.
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


@dataclass(frozen=True)
class RequiredEntityLaneResult:
    """Outcome of one lane invocation (for the manifest / audit trail).

    ``frame_rows`` is the (possibly updated) tuple, in the SAME order as the
    input; ``satisfied_entity_ids`` lists entities whose gap row was replaced by
    a verified re-fetch; ``attempted_entity_ids`` lists every entity the lane
    tried (gap-or-near-empty). All counts are deterministic.
    """

    frame_rows: tuple[FrameRow, ...]
    attempted_entity_ids: tuple[str, ...]
    satisfied_entity_ids: tuple[str, ...]
    queries_by_entity: Mapping[str, tuple[str, ...]]


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


def run_required_entity_lane(
    *,
    frame_rows: Sequence[FrameRow],
    bindings_by_entity_id: Mapping[str, EvidenceBinding],
    entity_meta_by_id: Mapping[str, Any],
    entity_cfg_by_id: Mapping[str, Mapping[str, Any]],
    research_question: str,
    scope_overrides: Optional[Mapping[str, Any]],
    search_fn: Callable[..., Any],
    fetch_fn: Callable[[EvidenceBinding], FrameRow],
) -> RequiredEntityLaneResult:
    """Run the targeted required-entity lane (ENV-GATED by the CALLER).

    For each UNSATISFIED FrameRow:
      1. Build + fire targeted authoritative-domain-biased search queries
         (corpus discovery / telemetry; capped per-entity and total-entities).
      2. RE-FETCH the entity's OWN ``url_pattern`` via ``fetch_fn`` (re-binds to
         the SAME entity_id with the ACTUAL resolved URL). If the re-fetch is
         now SATISFIED (a verifiable span), REPLACE the gap FrameRow; else leave
         it untouched.

    DEPENDENCY INJECTION: ``search_fn(query, *, domains, max_results)`` and
    ``fetch_fn(binding) -> FrameRow`` are injected so this is pure / offline-
    testable. The caller is responsible for the env gate (``lane_enabled()``).

    FAITHFULNESS: the satisfied FrameRow is whatever ``fetch_fn`` returns for the
    entity's OWN binding — its ``url`` is the entity's real resolved URL. Search
    results are NOT relabeled as the entity's coverage evidence.
    """
    rows = list(frame_rows)
    max_entities = _bounded_int_env(_MAX_ENTITIES_ENV, _DEFAULT_MAX_ENTITIES)
    max_results = _bounded_int_env(
        _MAX_RESULTS_PER_QUERY_ENV, _DEFAULT_MAX_RESULTS_PER_QUERY
    )
    floor = _min_verifiable_span_chars()

    attempted: list[str] = []
    satisfied: list[str] = []
    queries_by_entity: dict[str, tuple[str, ...]] = {}

    for index, row in enumerate(rows):
        if len(attempted) >= max_entities:
            break
        if not frame_row_is_unsatisfied(row, min_span_chars=floor):
            continue
        entity_id = row.entity_id
        binding = bindings_by_entity_id.get(entity_id)
        entity_cfg = entity_cfg_by_id.get(entity_id)
        if binding is None or entity_cfg is None:
            # No binding/config to re-fetch from — cannot act faithfully; skip.
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

        # (1) Targeted authoritative-domain-biased search — discovery/telemetry.
        # We do NOT bind these results as the entity's coverage evidence (that
        # would risk relabeling foreign content as the canonical entity). Errors
        # are non-fatal: discovery is best-effort, coverage comes from the
        # url_pattern re-fetch below.
        domains = _domains_for_entity(entity_cfg)
        for query in queries:
            try:
                search_fn(query, domains=domains, max_results=max_results)
            except Exception:  # noqa: BLE001 — discovery is best-effort
                logger.warning(
                    "required_entity_lane: search failed for entity=%s query=%r "
                    "(continuing to url_pattern re-fetch)",
                    entity_id,
                    query,
                )

        # (2) Re-fetch the entity's OWN url_pattern -> re-binds to the SAME
        # entity_id with the REAL resolved URL. Faithful: never relabel.
        try:
            refetched = fetch_fn(binding)
        except Exception:  # noqa: BLE001 — a failed re-fetch leaves the gap
            logger.warning(
                "required_entity_lane: re-fetch raised for entity=%s; leaving gap",
                entity_id,
            )
            continue
        if refetched is None or refetched.entity_id != entity_id:
            # Defensive: a re-fetch that does not bind back to the entity is
            # discarded (never silently mis-attributed).
            continue
        if not frame_row_is_unsatisfied(refetched, min_span_chars=floor):
            rows[index] = refetched
            satisfied.append(entity_id)

    return RequiredEntityLaneResult(
        frame_rows=tuple(rows),
        attempted_entity_ids=tuple(attempted),
        satisfied_entity_ids=tuple(satisfied),
        queries_by_entity=queries_by_entity,
    )
