"""Lossless evidence packs routed to the report's own facets.

The router has no count, token, or rank cutoff.  Existing assignments are
preserved, complete claim baskets are co-located, and every remaining evidence
row is assigned to its best prompt-derived facet.  A coverage ledger makes the
keep-all invariant executable.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any


_TOKEN_RE = re.compile(r"[A-Za-z\u00c0-\u024f][A-Za-z0-9\u00c0-\u024f_-]{2,}")
_STOPWORDS = frozenset({
    "about", "after", "also", "and", "are", "before", "between", "but", "by",
    "evidence", "findings", "for", "from", "into", "its", "report", "section",
    "source", "sources", "study", "that", "the", "their", "these", "this", "those",
    "through", "under", "using", "was", "were", "what", "when", "where", "which",
    "while", "with", "within",
})


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        token for token in _TOKEN_RE.findall(str(text or "").lower())
        if token not in _STOPWORDS
    )


def _plan_words(plan: Any) -> frozenset[str]:
    return _tokens(
        f"{getattr(plan, 'title', '') or ''} {getattr(plan, 'focus', '') or ''}"
    )


def _row_words(row: Mapping[str, Any] | None) -> frozenset[str]:
    row = row or {}
    return _tokens(" ".join(str(row.get(name) or "") for name in (
        "title", "source_title", "subject", "statement", "direct_quote",
    )))


def _basket_ids(basket: Any, evidence_pool: Mapping[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for member in _get(basket, "supporting_members", []) or []:
        evidence_id = str(_get(member, "evidence_id", "") or "")
        if evidence_id and evidence_id in evidence_pool and evidence_id not in seen:
            seen.add(evidence_id)
            out.append(evidence_id)
    return out


def _basket_words(basket: Any, ids: list[str], evidence_pool: Mapping[str, Any]) -> frozenset[str]:
    text = " ".join(str(_get(basket, name, "") or "") for name in (
        "claim_text", "subject", "predicate",
    ))
    row_text = " ".join(
        " ".join(str((evidence_pool.get(evidence_id) or {}).get(name) or "") for name in (
            "title", "subject", "statement", "direct_quote",
        ))
        for evidence_id in ids
    )
    return _tokens(f"{text} {row_text}")


def build_basket_memberships(
    credibility_analysis: Any,
    evidence_pool: Mapping[str, Any],
) -> dict[str, list[str]]:
    """Map every present basket member to all of its real basket IDs.

    This is metadata-only: it neither routes nor removes a row.  It is exposed
    separately so the basket-prompt isolation arm can identify same-claim
    sources without also enabling the facet-pack routing behavior.
    """

    out: dict[str, list[str]] = {}
    baskets = list(_get(credibility_analysis, "baskets", []) or [])
    for basket_index, basket in enumerate(baskets):
        basket_id = str(
            _get(basket, "claim_cluster_id", "") or f"basket_{basket_index}"
        )
        for evidence_id in _basket_ids(basket, evidence_pool):
            memberships = out.setdefault(evidence_id, [])
            if basket_id not in memberships:
                memberships.append(basket_id)
    return out


def _extend(plan: Any, evidence_ids: list[str]) -> None:
    existing = list(getattr(plan, "ev_ids", None) or [])
    seen = set(str(item) for item in existing)
    for evidence_id in evidence_ids:
        if evidence_id not in seen:
            existing.append(evidence_id)
            seen.add(evidence_id)
    plan.ev_ids = existing


def _best_plan(
    plans: list[Any],
    words: frozenset[str],
    member_ids: list[str],
) -> tuple[int, Any]:
    """Lexicographic best home: existing ownership, topical overlap, plan order."""

    member_set = set(member_ids)
    scored: list[tuple[int, int, int, Any]] = []
    for index, plan in enumerate(plans):
        assigned = set(str(item) for item in (getattr(plan, "ev_ids", None) or []))
        ownership = len(assigned & member_set)
        overlap = len(_plan_words(plan) & words)
        scored.append((ownership, overlap, -index, plan))
    ownership, overlap, neg_index, plan = max(scored, key=lambda item: item[:3])
    return -neg_index, plan


def build_lossless_facet_packs(
    plans: list[Any],
    evidence_pool: Mapping[str, dict[str, Any]],
    *,
    credibility_analysis: Any = None,
    auxiliary_plan: Callable[[Any], bool] | None = None,
    ordered_evidence_ids: list[str] | None = None,
) -> tuple[list[Any], dict[str, Any], dict[str, list[str]]]:
    """Route a complete evidence stream into body facets and return its ledger.

    ``auxiliary_plan`` identifies pre-generation residual/enrichment containers.
    Their evidence is folded into body facets before those containers are removed;
    the ledger records the move and asserts that no evidence ID is lost.
    """

    all_plans = list(plans or [])
    pool_ids = [
        evidence_id for evidence_id in (ordered_evidence_ids or list(evidence_pool))
        if evidence_id in evidence_pool
    ]
    # Include any pool key omitted from a caller-provided order exactly once.
    have_order = set(pool_ids)
    pool_ids.extend(evidence_id for evidence_id in evidence_pool if evidence_id not in have_order)
    if not all_plans:
        return all_plans, {
            "input_evidence_ids": pool_ids,
            "covered_evidence_ids": [],
            "missing_evidence_ids": pool_ids,
            "sections": [],
            "basket_routes": [],
            "auxiliary_sections_folded": [],
        }, {}

    is_auxiliary = auxiliary_plan or (lambda _plan: False)
    destinations = [plan for plan in all_plans if not is_auxiliary(plan)]
    if not destinations:
        destinations = list(all_plans)
    auxiliary = [plan for plan in all_plans if plan not in destinations]

    basket_routes: list[dict[str, Any]] = []
    basket_ids_by_evidence = build_basket_memberships(
        credibility_analysis, evidence_pool,
    )
    baskets = list(_get(credibility_analysis, "baskets", []) or [])
    for basket_index, basket in enumerate(baskets):
        member_ids = _basket_ids(basket, evidence_pool)
        if not member_ids:
            continue
        words = _basket_words(basket, member_ids, evidence_pool)
        destination_index, destination = _best_plan(destinations, words, member_ids)
        _extend(destination, member_ids)
        basket_id = str(_get(basket, "claim_cluster_id", "") or f"basket_{basket_index}")
        basket_routes.append({
            "basket_id": basket_id,
            "member_evidence_ids": member_ids,
            "destination_index": destination_index,
            "destination_title": str(getattr(destination, "title", "") or ""),
        })

    # Fold every auxiliary assignment into a body facet before removing its container.
    auxiliary_folded: list[dict[str, Any]] = []
    for source_plan in auxiliary:
        moved: list[dict[str, str]] = []
        for evidence_id in list(getattr(source_plan, "ev_ids", None) or []):
            evidence_id = str(evidence_id)
            if evidence_id not in evidence_pool:
                continue
            _, destination = _best_plan(
                destinations, _row_words(evidence_pool.get(evidence_id)), [evidence_id],
            )
            _extend(destination, [evidence_id])
            moved.append({
                "evidence_id": evidence_id,
                "destination_title": str(getattr(destination, "title", "") or ""),
            })
        auxiliary_folded.append({
            "source_title": str(getattr(source_plan, "title", "") or ""),
            "moved": moved,
        })

    # Assign every as-yet-unrepresented pool row.  Zero lexical overlap still gets
    # a stable first-plan home; absence of a match is never a reason to discard it.
    covered = {
        str(evidence_id)
        for plan in destinations
        for evidence_id in (getattr(plan, "ev_ids", None) or [])
        if str(evidence_id) in evidence_pool
    }
    for evidence_id in pool_ids:
        if evidence_id in covered:
            continue
        _, destination = _best_plan(
            destinations, _row_words(evidence_pool.get(evidence_id)), [evidence_id],
        )
        _extend(destination, [evidence_id])
        covered.add(evidence_id)

    order = {evidence_id: index for index, evidence_id in enumerate(pool_ids)}
    for plan in destinations:
        existing = list(getattr(plan, "ev_ids", None) or [])
        valid = [str(item) for item in existing if str(item) in evidence_pool]
        invalid = [item for item in existing if str(item) not in evidence_pool]
        # Stable complete stream ordered by the prompt/credibility layer; invalid
        # legacy IDs remain at the tail for downstream disclosure/debugging.
        plan.ev_ids = sorted(dict.fromkeys(valid), key=lambda item: order[item]) + invalid

    occurrences: dict[str, list[int]] = {evidence_id: [] for evidence_id in pool_ids}
    sections: list[dict[str, Any]] = []
    for index, plan in enumerate(destinations):
        ids = [
            str(item) for item in (getattr(plan, "ev_ids", None) or [])
            if str(item) in evidence_pool
        ]
        for evidence_id in ids:
            occurrences.setdefault(evidence_id, []).append(index)
        sections.append({
            "index": index,
            "title": str(getattr(plan, "title", "") or ""),
            "evidence_ids": ids,
        })
    missing = [evidence_id for evidence_id in pool_ids if not occurrences.get(evidence_id)]
    assert not missing, f"lossless facet pack omitted evidence IDs: {missing[:10]}"
    ledger = {
        "input_evidence_ids": pool_ids,
        "covered_evidence_ids": [eid for eid in pool_ids if occurrences.get(eid)],
        "missing_evidence_ids": missing,
        "duplicate_assignments": {
            eid: indices for eid, indices in occurrences.items() if len(indices) > 1
        },
        "sections": sections,
        "basket_routes": basket_routes,
        "auxiliary_sections_folded": auxiliary_folded,
    }
    return destinations, ledger, basket_ids_by_evidence
