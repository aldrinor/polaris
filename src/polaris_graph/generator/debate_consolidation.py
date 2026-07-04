"""B1 (I-deepfix-001 #1344) — debate-class con-basket consolidation BEFORE strict_verify.

DeepTRACE one-sided #1 (field best 48.7, ideal 0) + overconfident #2 (ideal 0). A report that
renders only the majority ("pro") side of a genuine disagreement scores one-sided; if it also
asserts that side at max confidence it scores overconfident. The weight-and-consolidate path can
FUNNEL-DROP the minority ("con") side at section composition: a con-basket is selected for a
section ONLY if one of its members backs an evidence_id the outline assigned to that section
(``_section_baskets_for_compose``). A refuting basket whose evidence was NOT assigned to the
section therefore never composes, and the disagreement is silently lost.

THE FIX (this module, pure): whenever a section's SELECTED pro-basket carries
``refuter_cluster_ids`` (a genuine, already-detected disagreement), the referenced con-basket(s)
are CONSOLIDATED into the section's compose set alongside the pro-basket — so both sides flow into
``_compose_section_per_basket`` and re-pass the UNCHANGED strict_verify per clause together. The
con side is span-grounded exactly like the pro side; it is never fabricated (a con-basket only
exists because the contradiction detector / dissent recall already built it), and it is never
funnel-dropped at selection.

§-1.3 DNA — CONSOLIDATE, never DROP: this only ADDS the disagreeing basket that already exists in
the corpus; it removes nothing and caps nothing. FAITHFULNESS is untouched — the con-basket's
members carry their OWN isolated span verdicts and re-pass the frozen faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance / span-grounding) per clause downstream. A con-basket
with no span-verified member composes nothing, exactly like any other basket.

``should_hedge_confidence`` reports when BOTH sides are present so the composed answer is never
rendered as a max-confidence one-sided claim (#2). PURE / offline. LAW VI kill-switch. snake_case.
"""
from __future__ import annotations

import os
from typing import Any, Iterable

_ENV_FLAG = "PG_DEBATE_CON_BASKET_CONSOLIDATION"
_OFF_VALUES = frozenset({"", "0", "false", "off", "no"})


def debate_consolidation_enabled() -> bool:
    """B1 kill-switch. Default ON; OFF => con-baskets are not force-consolidated (legacy funnel)."""
    return os.environ.get(_ENV_FLAG, "1").strip().lower() not in _OFF_VALUES


def _cluster_id(basket: Any) -> str:
    if isinstance(basket, dict):
        return str(basket.get("claim_cluster_id") or "")
    return str(getattr(basket, "claim_cluster_id", "") or "")


def _refuter_ids(basket: Any) -> tuple:
    if isinstance(basket, dict):
        raw = basket.get("refuter_cluster_ids") or ()
    else:
        raw = getattr(basket, "refuter_cluster_ids", ()) or ()
    return tuple(str(c) for c in raw if str(c))


def referenced_con_cluster_ids(selected_baskets: Iterable[Any]) -> set[str]:
    """The claim_cluster_ids the SELECTED (pro) baskets refute — the con side to consolidate. PURE."""
    out: set[str] = set()
    for b in selected_baskets or ():
        out.update(_refuter_ids(b))
    return out


def augment_with_con_baskets(
    selected_baskets: list,
    all_baskets: Iterable[Any],
) -> list:
    """Consolidate every referenced con-basket into the section's compose set — never dropping.

    ``selected_baskets`` is the section's primary (pro) basket list (``_section_baskets_for_compose``
    output). ``all_baskets`` is the full ``credibility_analysis.baskets`` universe. For each con
    cluster id referenced by a selected basket's ``refuter_cluster_ids``, the matching basket in
    ``all_baskets`` (by ``claim_cluster_id``) is APPENDED if not already selected — so the minority
    side composes alongside the majority BEFORE strict_verify.

    Returns a NEW list (never mutates the input). Deterministic: pro baskets keep their order, con
    baskets are appended in ``all_baskets`` order. When nothing is referenced (or the con-baskets are
    already selected) the returned list equals the input contents => byte-identical downstream.
    """
    selected = list(selected_baskets or [])
    con_ids = referenced_con_cluster_ids(selected)
    if not con_ids:
        return selected
    present = {_cluster_id(b) for b in selected}
    con_ids -= present
    if not con_ids:
        return selected
    augmented = list(selected)
    for b in all_baskets or ():
        ccid = _cluster_id(b)
        if ccid in con_ids:
            augmented.append(b)
            con_ids.discard(ccid)  # first match wins; ids are unique per basket
    return augmented


def should_hedge_confidence(compose_baskets: Iterable[Any]) -> bool:
    """True iff BOTH a pro-basket (carrying ``refuter_cluster_ids``) AND its referenced con-basket are
    in the compose set — i.e. a genuine two-sided disagreement is being rendered, so the answer must
    NOT be asserted at max confidence (DeepTRACE overconfident #2). PURE."""
    baskets = list(compose_baskets or [])
    if not baskets:
        return False
    present = {_cluster_id(b) for b in baskets}
    for b in baskets:
        refs = set(_refuter_ids(b))
        if refs and (refs & present):
            return True
    return False
