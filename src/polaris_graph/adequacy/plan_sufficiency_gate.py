"""Plan-sufficiency gate — I-meta-005 Phase 3 (#987). The money-trap fix.

`assess_plan_sufficiency` decides whether the BILLED evidence set covers EVERY
planned sub-question to its per-section evidence target at the numeric authority
floor — BEFORE a generator token is billed. It is a PURE function (no network,
no LLM) over rows that already carry the §2.3a authority sidecar + `query_origin`
provenance, plus the pinned `ResearchPlan`.

KEY DESIGN (brief §2.2):
- Coverage UNIT = the section outline item (its `evidence_target`).
- Relevance = PROVENANCE-FIRST: a row is relevant to a section iff its
  `query_origin` matches (normalized equality) one of the sub-query texts at the
  section's `sub_query_indices`. The content-word overlap fallback is used ONLY
  for rows whose `query_origin` is EMPTY or one of the explicit NON-QUERY
  SENTINEL origins (`{primary_trial_doi_seed, agentic_seed, deepener_seed, need_type_backend, domain_backend}`)
  — these lanes surface authoritative evidence with no originating sub-query, so
  they must be creditable. A row whose `query_origin` is a REAL sub-query text
  that does not match the section is NOT relevant to it (no title-overlap rescue).
- Authority floor = the NUMERIC `authority_score` (float [0,1]); a row counts
  toward coverage iff `authority_score >= authority_floor` (a single global
  float, NOT a per-domain dict). Below-floor relevant rows are reported, not
  credited.
- Section SUFFICIENT iff BOTH (facet-level, not section-aggregate):
    (i)  total above-floor covered_count >= evidence_target, AND
    (ii) EVERY mapped sub_query_index has >= MIN_PER_FACET above-floor relevant
         rows — so a section mapped to [4,5,6] cannot pass on rows from 4 alone.
- Verdict: PROCEED (all sufficient) / EXPAND (≥1 under-covered, round < max) /
  ABORT (≥1 under-covered, rounds/budget exhausted).

The relevance MAPPING is shared with the generator's on-mode
`_assign_evidence_to_planned_outline` via `relevant_section_indices`, so a
section certified SUFFICIENT actually RECEIVES its credited rows (brief §2.2b).

NO `if domain ==` / NO `_DEFAULT_DOMAIN_THRESHOLDS` / NO clinical literal on this
path — sufficiency is computed from the PLAN x AUTHORITY, never a domain.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Literal

logger = logging.getLogger("polaris_graph.plan_sufficiency_gate")

SufficiencyVerdict = Literal["proceed", "expand", "abort"]

# NON-QUERY sentinel origins that legitimately carry no sub-query text (brief
# §2.2). Rows with one of these origins (or an empty origin) are FALLBACK-
# ELIGIBLE: their relevance is decided by content-word overlap against a
# section's sub-query texts. A REAL sub-query origin is authoritative and uses
# provenance-first matching only. Codex-LOCKED — do not widen.
SENTINEL_ORIGINS: frozenset[str] = frozenset(
    # FX-15a (#1118): `agentic_seed` (agentic-discovered URLs) and `deepener_seed` (citation-
    # snowball deepener URLs, Codex iter-1 P1) are non-query seed lanes, creditable via the overlap
    # fallback exactly as the old mislabel `primary_trial_doi_seed` was — so the relabels preserve
    # plan-sufficiency fallback-eligibility (no behavior change).
    {"primary_trial_doi_seed", "agentic_seed", "deepener_seed", "need_type_backend", "domain_backend"}
)


def _authority_floor_default() -> float:
    """Single global numeric authority floor in [0,1] (brief §2.2). Read at call
    time so tests/operators can override via env; callers pass it explicitly."""
    try:
        return float(os.getenv("PG_PLAN_SUFFICIENCY_AUTHORITY_FLOOR", "0.3"))
    except (TypeError, ValueError):
        return 0.3


def _min_per_facet_default() -> int:
    """Minimum above-floor relevant rows EACH mapped sub-query must have for a
    section to be sufficient (brief §2.2, default 1)."""
    try:
        return max(1, int(os.getenv("PG_PLAN_SUFFICIENCY_MIN_PER_FACET", "1")))
    except (TypeError, ValueError):
        return 1


@dataclass
class UnitCoverage:
    """Per-section coverage detail (brief §2.1)."""

    unit_id: str
    title: str
    evidence_target: int
    sub_query_indices: list[int]
    covered_count: int                 # above-floor relevant rows (total)
    below_floor_count: int             # relevant-but-below-authority (reported)
    sufficient: bool
    per_facet_covered: dict[int, int] = field(default_factory=dict)
    empty_facets: list[int] = field(default_factory=list)


@dataclass
class PlanSufficiencyReport:
    verdict: SufficiencyVerdict
    authority_floor: float
    min_per_facet: int
    round_index: int
    max_rounds: int
    per_unit: list[UnitCoverage] = field(default_factory=list)
    under_covered_units: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _normalize_query(text: str) -> str:
    """Normalized form for provenance equality (whitespace-collapsed, lower)."""
    return " ".join(str(text or "").split()).strip().lower()


def _content_words(text: str) -> set[str]:
    """Reuse the EXISTING grounding tokenizer (alphabetic, >=3 chars, stopword-
    stripped) — the same primitive the provenance verifier uses (brief §2.2).
    Imported lazily so this module has no import-time generator dependency."""
    from src.polaris_graph.generator.provenance_generator import (
        _content_words as _cw,
    )
    return _cw(text)


def _min_content_word_overlap() -> int:
    """The EXISTING `MIN_CONTENT_WORD_OVERLAP` constant (default 2) — no new
    magic number for the fallback floor (brief §2.2)."""
    from src.polaris_graph.generator.provenance_generator import (
        MIN_CONTENT_WORD_OVERLAP,
    )
    return MIN_CONTENT_WORD_OVERLAP


def _row_text_for_overlap(row: dict[str, Any]) -> str:
    """The row content used for the content-word fallback: statement + the
    direct_quote span (NOT just the title — brief §2.2 fallback)."""
    return " ".join(
        str(row.get(k) or "")
        for k in ("statement", "direct_quote")
    )


def relevant_section_indices(
    row: dict[str, Any],
    outline: list[Any],
    sub_queries: list[str],
) -> list[int]:
    """Map a row to the outline section index(es) it is RELEVANT to (brief §2.2).

    SHARED by the gate (counting) and the on-mode generator assignment so the
    SUFFICIENT certification carries through to what the generator receives.
    Authority is NOT applied here — relevance is provenance/overlap only; the
    gate layers the numeric floor on top.

    Provenance-first: a non-sentinel, non-empty `query_origin` credits ONLY the
    section(s) whose `sub_query_indices` point at that exact sub-query text. A
    sentinel/empty origin uses content-word overlap against the section's
    sub-query texts. Returns the list of matching section indices (possibly
    several; possibly none -> orphan, uncredited).
    """
    origin = _normalize_query(row.get("query_origin", ""))
    raw_origin = str(row.get("query_origin", "") or "")
    norm_subqueries = [_normalize_query(sq) for sq in sub_queries]

    fallback_eligible = (raw_origin == "") or (raw_origin in SENTINEL_ORIGINS)

    matches: list[int] = []
    if not fallback_eligible:
        # PROVENANCE-FIRST: credit only sections whose mapped sub-query texts
        # equal this row's real query_origin.
        for sec_idx, section in enumerate(outline):
            for q_idx in getattr(section, "sub_query_indices", []) or []:
                if 0 <= q_idx < len(norm_subqueries) and norm_subqueries[q_idx] == origin:
                    matches.append(sec_idx)
                    break
        return matches

    # FALLBACK (empty / sentinel origin): content-word overlap against the
    # section's OWN sub-query texts, floored by MIN_CONTENT_WORD_OVERLAP.
    row_words = _content_words(_row_text_for_overlap(row))
    if not row_words:
        return matches
    floor = _min_content_word_overlap()
    for sec_idx, section in enumerate(outline):
        section_words: set[str] = set()
        for q_idx in getattr(section, "sub_query_indices", []) or []:
            if 0 <= q_idx < len(sub_queries):
                section_words |= _content_words(sub_queries[q_idx])
        if not section_words:
            continue
        if len(row_words & section_words) >= floor:
            matches.append(sec_idx)
    return matches


def _facets_matched_for_row(
    row: dict[str, Any],
    section: Any,
    sub_queries: list[str],
) -> list[int]:
    """Which of THIS section's mapped sub_query_indices the row covers (brief
    §2.2 facet-level). Provenance-first for a real origin; content-word overlap
    against the SPECIFIC facet's sub-query text for a sentinel/empty origin."""
    raw_origin = str(row.get("query_origin", "") or "")
    origin = _normalize_query(raw_origin)
    fallback_eligible = (raw_origin == "") or (raw_origin in SENTINEL_ORIGINS)
    indices = [
        q for q in (getattr(section, "sub_query_indices", []) or [])
        if 0 <= q < len(sub_queries)
    ]
    if not fallback_eligible:
        return [q for q in indices if _normalize_query(sub_queries[q]) == origin]
    row_words = _content_words(_row_text_for_overlap(row))
    if not row_words:
        return []
    floor = _min_content_word_overlap()
    return [
        q for q in indices
        if len(row_words & _content_words(sub_queries[q])) >= floor
    ]


def _enrich_authority_if_missing(row: dict[str, Any]) -> float:
    """Return the row's numeric `authority_score`, computing it at gate time for
    a billed row that lacks the sidecar (post-selection V30 contract / uploaded-
    document rows — brief §2.3a). Builds a minimal signals object from the row's
    url/title; thin inputs -> honest LOW per the Phase-0a contract (never a
    silent blind credit). Does NOT mutate the row's persisted sidecar contract
    beyond filling the missing score for THIS assessment."""
    val = row.get("authority_score")
    if isinstance(val, (int, float)):
        return float(val)
    # Missing sidecar -> compute directly from the row's surface signals.
    from src.polaris_graph.authority.authority_model import score_source_authority
    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

    url = str(row.get("source_url") or row.get("url") or "")
    title = str(row.get("statement") or row.get("title") or "")
    body = str(row.get("direct_quote") or "")
    signals = ClassificationSignals(
        url=url,
        title=title,
        publisher="",
        fetched_content_length=len(body),
        fetched_body=body,
    )
    result = score_source_authority(signals)
    score = float(result.authority_score)
    # Cache onto the row so the shared mapping / telemetry stays consistent.
    row["authority_score"] = score
    if not row.get("authority_confidence"):
        row["authority_confidence"] = result.authority_confidence.value
    return score


def assess_plan_sufficiency(
    *,
    plan: Any,
    corpus_rows: list[dict[str, Any]],
    authority_floor: float | None = None,
    round_index: int,
    max_rounds: int,
    min_per_facet: int | None = None,
) -> PlanSufficiencyReport:
    """Certify the BILLED evidence set against the pinned plan (brief §2.1).

    Args:
        plan: the pinned `ResearchPlan` (carries `sub_queries` + `outline` with
            per-section `evidence_target` + `sub_query_indices`).
        corpus_rows: the FINAL billed rows (`evidence_for_gen`) — each carries
            `query_origin` + (for live rows) the authority sidecar; injected
            contract/upload rows are enriched here.
        authority_floor: numeric floor in [0,1]; default from env.
        round_index / max_rounds: saturation-round bookkeeping (EXPAND vs ABORT).
        min_per_facet: per-facet minimum above-floor rows; default from env.

    Returns a `PlanSufficiencyReport`. PURE / no-network / no-LLM.
    """
    floor = _authority_floor_default() if authority_floor is None else float(authority_floor)
    per_facet_min = _min_per_facet_default() if min_per_facet is None else max(1, int(min_per_facet))

    sub_queries = list(getattr(plan, "sub_queries", []) or [])
    outline = list(getattr(plan, "outline", []) or [])

    per_unit: list[UnitCoverage] = []
    under_covered: list[str] = []

    for sec_idx, section in enumerate(outline):
        unit_id = f"section_{sec_idx}"
        title = getattr(section, "title", "") or unit_id
        target = int(getattr(section, "evidence_target", 0) or 0)
        mapped = [
            q for q in (getattr(section, "sub_query_indices", []) or [])
            if 0 <= q < len(sub_queries)
        ]
        covered_count = 0
        below_floor_count = 0
        per_facet_covered: dict[int, int] = {q: 0 for q in mapped}

        for row in corpus_rows:
            matched_facets = _facets_matched_for_row(row, section, sub_queries)
            if not matched_facets:
                continue
            score = _enrich_authority_if_missing(row)
            if score >= floor:
                covered_count += 1
                for q in matched_facets:
                    per_facet_covered[q] = per_facet_covered.get(q, 0) + 1
            else:
                below_floor_count += 1

        empty_facets = [
            q for q in mapped if per_facet_covered.get(q, 0) < per_facet_min
        ]
        sufficient = (
            covered_count >= target
            and target >= 1
            and len(mapped) >= 1
            and not empty_facets
        )
        unit = UnitCoverage(
            unit_id=unit_id,
            title=title,
            evidence_target=target,
            sub_query_indices=list(mapped),
            covered_count=covered_count,
            below_floor_count=below_floor_count,
            sufficient=sufficient,
            per_facet_covered=dict(per_facet_covered),
            empty_facets=empty_facets,
        )
        per_unit.append(unit)
        if not sufficient:
            under_covered.append(unit_id)

    if not under_covered:
        verdict: SufficiencyVerdict = "proceed"
        notes = [f"all {len(per_unit)} planned sections sufficient at floor {floor}"]
    elif round_index < max_rounds:
        verdict = "expand"
        notes = [
            f"{len(under_covered)} under-covered unit(s); "
            f"round {round_index} < max {max_rounds} -> EXPAND"
        ]
    else:
        verdict = "abort"
        notes = [
            f"{len(under_covered)} under-covered unit(s); "
            f"rounds exhausted (round {round_index} >= max {max_rounds}) -> ABORT"
        ]

    return PlanSufficiencyReport(
        verdict=verdict,
        authority_floor=floor,
        min_per_facet=per_facet_min,
        round_index=round_index,
        max_rounds=max_rounds,
        per_unit=per_unit,
        under_covered_units=under_covered,
        notes=notes,
    )
