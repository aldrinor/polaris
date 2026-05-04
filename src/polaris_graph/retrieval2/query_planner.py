"""Query planner for slice 002 clinical retrieval.

Per `.codex/slices/slice_002/architecture_proposal.md` §"Module boundaries".

Pure function: ScopeDecision -> list[str] of search queries. No I/O,
no LLM, no network. Deterministic given the same ScopeDecision.

Strategy:
1. Pull plausible_interpretations from the three PICO axes (population,
   intervention, outcome) of the ScopeDecision.
2. Boolean-expand: (P1 OR P2 ...) AND (I1 OR I2 ...) AND (O1 OR O2 ...).
3. Augment with scope-class-specific clinical vocabulary
   (e.g. for clinical_safety: "adverse events", "pharmacovigilance").
4. Cap at QUERY_CAP queries to bound retrieval cost.
5. De-duplicate on Jaccard token similarity ≥ JACCARD_THRESHOLD.
"""

from __future__ import annotations

import re

from polaris_graph.scope.scope_decision import ScopeDecision

QUERY_CAP = 12
JACCARD_THRESHOLD = 0.85
MIN_QUERY_LEN = 6  # too-short queries are noise (e.g. just "diabetes")


# Scope-class augmentation vocabulary. Each scope_class adds a set of
# canonical clinical terms that broaden the query toward the right kind
# of evidence (regulatory vs primary research vs registry).
_SCOPE_AUGMENT: dict[str, list[str]] = {
    "clinical_efficacy": [
        "randomized controlled trial",
        "systematic review",
        "meta-analysis",
        "efficacy",
    ],
    "clinical_safety": [
        "adverse events",
        "pharmacovigilance",
        "post-marketing surveillance",
        "drug safety",
    ],
    "clinical_diagnosis": [
        "diagnostic accuracy",
        "sensitivity specificity",
        "screening test",
        "diagnostic criteria",
    ],
    "clinical_prognosis": [
        "prognostic factors",
        "survival analysis",
        "long-term outcomes",
        "natural history",
    ],
}


def _interpretations_by_axis(
    decision: ScopeDecision,
) -> dict[str, list[str]]:
    """Pull plausible_interpretations from each PICO axis.

    Axes that are not present (e.g. ambiguity_axes is empty for a
    refused decision) return empty lists. Whitespace is stripped.
    """
    out: dict[str, list[str]] = {
        "population": [],
        "intervention": [],
        "outcome": [],
    }
    for axis in decision.ambiguity_axes:
        out[axis.axis] = [
            i.strip() for i in axis.plausible_interpretations if i.strip()
        ]
    return out


def _cartesian_pico(
    populations: list[str],
    interventions: list[str],
    outcomes: list[str],
) -> list[str]:
    """Cross-product PICO terms into space-joined query strings.

    Empty axes are dropped from the join (a query with population +
    outcome but no intervention is still useful — just less specific).
    """
    queries: list[str] = []
    pop_terms = populations or [""]
    int_terms = interventions or [""]
    out_terms = outcomes or [""]

    for pop in pop_terms:
        for interv in int_terms:
            for outcome in out_terms:
                parts = [t for t in (pop, interv, outcome) if t]
                if not parts:
                    continue
                query = " ".join(parts).strip()
                if len(query) >= MIN_QUERY_LEN:
                    queries.append(query)
    return queries


def _augment_with_scope_terms(
    base_queries: list[str],
    scope_class: str | None,
) -> list[str]:
    """Append scope-class-specific clinical vocabulary to broaden coverage.

    For each base query, also emit query + " <augment-term>" for each
    term in the scope-class augmentation vocabulary. Emits the base
    queries first so they have the best rank in the de-dup pass.
    """
    if not scope_class or scope_class not in _SCOPE_AUGMENT:
        return list(base_queries)

    augments = _SCOPE_AUGMENT[scope_class]
    out = list(base_queries)
    for q in base_queries:
        for term in augments:
            out.append(f"{q} {term}")
    return out


_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")


def _tokens(query: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(query)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _dedupe(queries: list[str], threshold: float = JACCARD_THRESHOLD) -> list[str]:
    """Drop queries that are >= threshold Jaccard-similar to a kept query.

    Order-preserving: earlier queries win, later near-duplicates are
    dropped. This means the cartesian-product base queries (which
    appear before augmented queries) are preferred when a near-dup
    fight breaks out.
    """
    kept: list[str] = []
    kept_tokens: list[set[str]] = []
    for q in queries:
        t = _tokens(q)
        if not t:
            continue
        is_dup = any(
            _jaccard(t, prior) >= threshold for prior in kept_tokens
        )
        if is_dup:
            continue
        kept.append(q)
        kept_tokens.append(t)
    return kept


def plan_queries(decision: ScopeDecision) -> list[str]:
    """Generate search queries for a ScopeDecision.

    Returns up to QUERY_CAP queries, ordered most-specific first.
    Returns [] if the decision has no PICO interpretations to expand
    from (e.g. a refused decision or out-of-scope decision).

    Pure function — no I/O, no LLM, no network.
    """
    by_axis = _interpretations_by_axis(decision)
    base = _cartesian_pico(
        by_axis["population"],
        by_axis["intervention"],
        by_axis["outcome"],
    )
    if not base:
        return []

    augmented = _augment_with_scope_terms(base, decision.scope_class)
    deduped = _dedupe(augmented)
    return deduped[:QUERY_CAP]
