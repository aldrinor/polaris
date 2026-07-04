"""I-deepfix-001 Wave-3 T6 — the two-layer citation RENDER policy (single source of truth).

This module fixes the body/appendix + Layer-1/Layer-2 citation boundary in ONE place so the render
fixes that consume it (T1 basket->multi-cite, T2 cited-reference-list typing, T5 audit-machinery ->
appendix, F1 residual-coverage placement) all read the SAME policy instead of re-deriving it and
drifting. It is a pure RENDER-layer typing of an already-verified basket; it NEVER verifies, gates,
promotes, drops, caps, or thins a source.

WHAT THE POLICY DECIDES (and, just as importantly, what it does NOT):

  1. THE TWO TYPED CITATION LAYERS (readability/attribution, NOT a scoring device).
     Given a verified basket, ``split_basket_citation_layers`` types its distinct-origin ``SUPPORTS``
     members into:
       * Layer 1 = the inline BODY citation(s) whose span grounds THAT clause. Normally exactly ONE
         (the load-bearing representative); up to ``PG_CITATION_LAYER1_MAX`` (default 1, licensed
         cross-source analytical sentence -> 2 per D2). The composer may pass the exact grounding
         ``evidence_id``s it wrote via ``load_bearing_ev_ids``; absent that, Layer 1 defaults to the
         top-credibility-weight distinct-origin member (the natural single ``[N]`` representative).
       * Layer 2 = a typed per-claim corroboration line citing EVERY OTHER distinct-origin ``SUPPORTS``
         member (keep-all, DNA CONSOLIDATE). Same-origin duplicates NEVER render as a second citation.
     THE HARD INVARIANT (asserted by the fail-loud test): Layer1 ev_ids and Layer2 ev_ids PARTITION
     the full distinct-origin ``SUPPORTS`` ev_id set — union == the whole set, intersection == empty.
     Nothing is dropped; to the DeepTRACE scorer, Layer-1 union Layer-2 is ONE citation set (so #8
     thoroughness is high because every supporting source is cited, and #7 accuracy stays high because
     ONLY genuinely-supporting sources are cited). The two layers are a READABILITY split, so #6
     source-necessity (min-vertex-cover over the support matrix) is UNAFFECTED by the layer render.

  2. THE BODY / APPENDIX / DEMOTE BOUNDARY (fixed ONCE, jointly with T5 + F1).
     ``classify_render_block`` maps a render-block KIND to exactly one destination:
       * ``BODY``   — a relevant, on-topic, strict_verify-passing CLAIM (section prose, key findings,
         abstract, conclusion, AND F1 residual-coverage sentences — they are relevant statements).
       * ``APPENDIX`` — audit / disclosure / weight MACHINERY (reliability header, corroborated-
         weighted-findings roll-up, weight-basis labels, count-reconciliation prose, the credibility
         ledger, the per-claim Source-corroboration section, bibliography-audit). Kept + disclosed,
         relocated OUT of the scored body so the DeepTRACE #3 relevant-statement denominator is not
         diluted by POLARIS's own machinery. NEVER deleted.
       * ``DEMOTE_DISCLOSE`` — a confirmed-off-topic residual basket, routed to the F3 demote-and-
         disclose tail (kept + disclosed, never in the scored body).
     The distinct-origin corroboration line of a body claim (Layer 2) stays WITH its claim in the
     BODY — the appendix move relocates only non-claim audit machinery, never a claim's own citations.

DNA (CLAUDE.md §-1.3): WEIGHT don't FILTER; CONSOLIDATE don't DROP. This policy is the CONSOLIDATE
leg made visible: it keeps ALL distinct-origin corroborators as real citations and only TYPES where
each one renders. It adds no cap/target/thinner and touches no faithfulness state. The >=2-origin
basket floor and strict_verify remain the only hard gates, untouched.

LAW VI (zero hard-coding): every knob comes from the environment —
  * ``PG_CITATION_TWO_LAYER_POLICY``  kill-switch (default ON). OFF => the policy collapses to a
    single Layer-1 citation and an EMPTY Layer-2 (legacy single-``[N]`` behaviour), so callers can
    fall back byte-compatibly.
  * ``PG_CITATION_LAYER1_MAX``        max inline body citations (default 1; 2 licenses a cross-source
    analytical sentence). Overflow load-bearing members do NOT vanish — they fall to Layer 2 (still
    cited, keep-all), so the partition invariant always holds.
  * ``PG_CITATION_APPENDIX_KINDS``    comma-list of EXTRA block kinds to force into the appendix
    (additive to the canonical audit-machinery set below).

PURE: no network, no model, no faithfulness-file import, no input mutation. snake_case throughout.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

# ── LAW VI env knobs ───────────────────────────────────────────────────────────────────────────────
_TWO_LAYER_ENV = "PG_CITATION_TWO_LAYER_POLICY"       # kill-switch, default ON
_LAYER1_MAX_ENV = "PG_CITATION_LAYER1_MAX"            # inline body citations, default 1
_APPENDIX_KINDS_ENV = "PG_CITATION_APPENDIX_KINDS"    # extra appendix kinds (comma-list)

_DEFAULT_LAYER1_MAX = 1
# The cross-source analytical sentence (D2) is the only licensed 2-citation body clause; the layer-1
# cap is never allowed below 1 (a body claim always carries at least its load-bearing citation).
_MIN_LAYER1_MAX = 1


def two_layer_policy_enabled() -> bool:
    """True iff the two-layer citation render is active (LAW VI kill-switch ``PG_CITATION_TWO_LAYER_POLICY``).

    DEFAULT-ON: the policy is a faithfulness-neutral render typing, so it is on by default; ``=0`` (or
    ``off``/``false``/``no``) collapses to a single inline citation with an empty corroboration layer
    (legacy single-``[N]`` behaviour) for a byte-compatible fallback."""
    raw = os.getenv(_TWO_LAYER_ENV, "1").strip().lower()
    return raw not in ("", "0", "false", "off", "no")


def layer1_max() -> int:
    """Max inline BODY (Layer-1) citations per claim (LAW VI ``PG_CITATION_LAYER1_MAX``, default 1).

    Floored at 1 (a body claim always carries at least its load-bearing citation). A malformed value
    falls back to the default rather than failing the render."""
    raw = os.getenv(_LAYER1_MAX_ENV, str(_DEFAULT_LAYER1_MAX)).strip()
    try:
        val = int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_LAYER1_MAX
    return val if val >= _MIN_LAYER1_MAX else _MIN_LAYER1_MAX


# ── the two typed citation layers ────────────────────────────────────────────────────────────────


def _member_attr(member: Any, key: str) -> Any:
    """Read ``key`` from a member that is EITHER a dataclass/object (attribute) OR a plain ``dict``
    (the shape the ``_basket_corroboration_block`` render iterates). One accessor so the object path
    (ClaimBasket/BasketMember) and the dict path (bibliography ``row['baskets']`` members) agree."""
    if isinstance(member, dict):
        return member.get(key)
    return getattr(member, key, None)


def _member_ev_id(member: Any) -> str:
    """The member's evidence_id as a string (empty when absent). Dict- and object-aware."""
    return str(_member_attr(member, "evidence_id") or "")


def _member_origin(member: Any) -> str:
    """The member's ORIGIN identity for distinct-origin dedupe: ``origin_cluster_id`` (fallback
    ``evidence_id``, then object id). Matches ``verified_compose._distinct_origin_supports`` exactly so
    the render layers and the multi-cite composer agree on what 'one distinct source' means. Dict- and
    object-aware."""
    return str(
        _member_attr(member, "origin_cluster_id") or _member_attr(member, "evidence_id") or id(member)
    )


def _member_weight(member: Any) -> float:
    """The member's credibility WEIGHT for representative selection (highest-weight = Layer-1). Prefers
    ``credibility_weight`` (the verified_compose ordering key), falls back to ``authority_score``; 0.0
    when neither is a number. Dict- and object-aware. PURE."""
    for key in ("credibility_weight", "authority_score"):
        v = _member_attr(member, key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return 0.0


def _distinct_origin_supports(basket: Any) -> list[Any]:
    """The basket's ``SUPPORTS`` members deduped to ONE per distinct origin, highest credibility weight
    first. Delegates to the proven ``verified_compose`` helper so there is exactly ONE definition of
    'distinct-origin SUPPORTS' in the codebase; the import is local to avoid a module-load cycle."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _distinct_origin_supports as _vc_distinct_origin_supports,
    )
    return list(_vc_distinct_origin_supports(basket))


@dataclass(frozen=True)
class CitationLayers:
    """The typed two-layer citation split for ONE verified basket.

    ``layer1_members`` — the inline BODY citation member(s) (load-bearing span; normally 1, <=layer1_max).
    ``layer2_members`` — the per-claim corroboration-line member(s): every OTHER distinct-origin SUPPORTS
                         member (keep-all).
    The two member lists PARTITION the basket's distinct-origin SUPPORTS set (union == whole, no overlap,
    no same-origin duplicate). ``enabled`` records whether the two-layer render was active."""

    layer1_members: list[Any] = field(default_factory=list)
    layer2_members: list[Any] = field(default_factory=list)
    enabled: bool = True

    @property
    def layer1_ev_ids(self) -> list[str]:
        return [_member_ev_id(m) for m in self.layer1_members]

    @property
    def layer2_ev_ids(self) -> list[str]:
        return [_member_ev_id(m) for m in self.layer2_members]

    @property
    def cited_ev_ids(self) -> list[str]:
        """The FULL cited set (Layer-1 ∪ Layer-2), body order — what the DeepTRACE parser sees as one
        citation set for this claim, and what T2 lists as a real numbered reference."""
        return self.layer1_ev_ids + self.layer2_ev_ids

    @property
    def cited_members(self) -> list[Any]:
        return list(self.layer1_members) + list(self.layer2_members)


def _distinct_origin_from_members(members: Iterable[Any]) -> list[Any]:
    """Dedupe an EXPLICIT SUPPORTS member list to ONE per distinct ORIGIN, highest credibility weight
    kept, order-stable by weight desc. Dict- OR object-aware (unlike ``_distinct_origin_supports``,
    which delegates to the object-only ``verified_compose`` helper). Used by the ``supports_members``
    overload so the render's dict basket-members flow through the SAME partition logic. PURE."""
    ordered = sorted(list(members or []), key=_member_weight, reverse=True)
    seen: set[str] = set()
    out: list[Any] = []
    for m in ordered:
        origin = _member_origin(m)
        if origin in seen:
            continue
        seen.add(origin)
        out.append(m)
    return out


def _partition_supports(
    supports: list[Any], load_bearing_ev_ids: Optional[Iterable[str]], enabled: bool
) -> CitationLayers:
    """Partition an ALREADY distinct-origin, weight-desc-ordered SUPPORTS list into the two layers.
    The single implementation both ``split_basket_citation_layers`` entry points share, so the object
    (ClaimBasket) path and the explicit-members render path can never drift. PURE."""
    if not supports:
        return CitationLayers(layer1_members=[], layer2_members=[], enabled=enabled)
    if not enabled:
        # Legacy single-``[N]`` behaviour: one inline citation, no corroboration line.
        return CitationLayers(layer1_members=[supports[0]], layer2_members=[], enabled=False)

    max_l1 = layer1_max()
    # Resolve the load-bearing member(s) in the supplied weight-desc order (deterministic, stable).
    load_set: set[str] = {str(e) for e in (load_bearing_ev_ids or []) if str(e)}
    if load_set:
        primary = [m for m in supports if _member_ev_id(m) in load_set]
        # Guard: a caller-supplied ev_id that is NOT a distinct-origin SUPPORTS member is ignored (the
        # policy never invents a citation) — supports already excludes non-SUPPORTS and same-origin dups.
        if not primary:
            primary = [supports[0]]
    else:
        primary = [supports[0]]

    layer1 = primary[:max_l1]
    layer1_origins = {_member_origin(m) for m in layer1}
    # Layer 2 = every OTHER distinct-origin member (the load-bearing overflow beyond the cap included).
    layer2 = [m for m in supports if _member_origin(m) not in layer1_origins]
    return CitationLayers(layer1_members=layer1, layer2_members=layer2, enabled=True)


def split_basket_citation_layers(
    basket: Any = None,
    *,
    supports_members: Optional[Iterable[Any]] = None,
    load_bearing_ev_ids: Optional[Iterable[str]] = None,
) -> CitationLayers:
    """Type a verified basket's distinct-origin ``SUPPORTS`` members into the two citation layers.

    Two ways to call — the SAME policy, one named function (the production render path and the
    object tests both land here):
      * ``split_basket_citation_layers(basket)`` — the object path: read the ``SUPPORTS`` members off
        a ``ClaimBasket`` (via the shared ``verified_compose`` distinct-origin helper).
      * ``split_basket_citation_layers(supports_members=[...])`` — the RENDER path: the caller
        (``_basket_corroboration_block``) has ALREADY selected the verified SUPPORTS members (dicts);
        dedupe-to-distinct-origin here (dict-aware) and partition. This is what makes the policy a
        genuine render-path consumer, not a test-only helper.

    Layer 1 (inline body) = the load-bearing citation(s). If ``load_bearing_ev_ids`` is given (the
    ev_ids the composer actually grounded the body clause on), those distinct-origin members lead
    Layer 1, capped at ``layer1_max()``; otherwise Layer 1 defaults to the single top-weight
    distinct-origin member (the natural single-``[N]`` representative). Layer 2 = EVERY remaining
    distinct-origin SUPPORTS member (keep-all corroboration, DNA CONSOLIDATE). Overflow load-bearing
    members beyond the Layer-1 cap fall to Layer 2 (still cited) so the partition is total.

    HARD GUARANTEE: ``layer1 ∪ layer2`` == the distinct-origin SUPPORTS ev_id set, and
    ``layer1 ∩ layer2`` == empty. Nothing dropped, no same-origin duplicate double-cited. When the
    kill-switch is OFF the render collapses to a single Layer-1 citation and an EMPTY Layer-2 (legacy)."""
    if supports_members is not None:
        supports = _distinct_origin_from_members(supports_members)
    else:
        supports = _distinct_origin_supports(basket)
    return _partition_supports(supports, load_bearing_ev_ids, two_layer_policy_enabled())


# ── the body / appendix / demote render boundary (fixed ONCE, jointly with T5 + F1) ────────────────


class RenderDestination(str, Enum):
    """Where a render block lands in the DeepTRACE-scored output."""

    BODY = "body"                        # a relevant, on-topic, verified CLAIM (scored)
    APPENDIX = "appendix"                # audit / disclosure / weight MACHINERY (kept + disclosed)
    DEMOTE_DISCLOSE = "demote_disclose"  # confirmed-off-topic residual -> F3 tail (kept + disclosed)


# Canonical BODY block kinds — relevant on-topic verified CLAIMS. F1 residual-coverage sentences are
# BODY (they are relevant statements per the Wave-3 T5/F1 joint placement decision).
_BODY_KINDS: frozenset[str] = frozenset({
    "section_prose",
    "key_findings",
    "abstract",
    "conclusion",
    "residual_coverage",          # F1: keep-all per-facet residual verified sentences ARE relevant
    "claim",
    "corroboration_line",         # Layer-2 corroboration line stays WITH its body claim
})

# Canonical APPENDIX block kinds — POLARIS's own audit / disclosure / weight MACHINERY. Non-claim
# statements the GPT-5 decomposer would otherwise count in the #3 relevant-statement denominator.
_APPENDIX_KINDS: frozenset[str] = frozenset({
    "reliability_header",
    "corroborated_weighted_findings",
    "weight_basis",
    "count_reconciliation",
    "credibility_ledger",
    "source_corroboration_rollup",
    "disclosure",
    "bibliography_audit",
    "methods",
})

# Canonical DEMOTE kinds — confirmed-off-topic residual routed to the F3 demote-and-disclose tail.
_DEMOTE_KINDS: frozenset[str] = frozenset({
    "off_topic_residual",
})


def _extra_appendix_kinds() -> frozenset[str]:
    """LAW VI ``PG_CITATION_APPENDIX_KINDS``: extra kinds forced into the appendix (comma-list)."""
    raw = os.getenv(_APPENDIX_KINDS_ENV, "").strip()
    if not raw:
        return frozenset()
    return frozenset(k.strip().lower() for k in raw.split(",") if k.strip())


def classify_render_block(kind: str) -> RenderDestination:
    """Map a render-block KIND to its single canonical destination (the body/appendix/demote boundary,
    defined here ONCE for T5 + F1 + T1/T2). Unknown kinds default to ``BODY`` (fail-open toward the
    scored body: a real claim must never be silently hidden from the reader; only NAMED audit machinery
    is relocated). The ``PG_CITATION_APPENDIX_KINDS`` override can additively force a kind to appendix."""
    k = (kind or "").strip().lower()
    if k in _extra_appendix_kinds():
        return RenderDestination.APPENDIX
    if k in _DEMOTE_KINDS:
        return RenderDestination.DEMOTE_DISCLOSE
    if k in _APPENDIX_KINDS:
        return RenderDestination.APPENDIX
    # BODY kinds and anything unrecognized render in the scored body (fail-open toward visibility).
    return RenderDestination.BODY


def is_audit_appendix_block(kind: str) -> bool:
    """Convenience predicate for T5: True iff ``kind`` is audit/disclosure/weight machinery that the
    render must relocate OUT of the scored body into the typed appendix."""
    return classify_render_block(kind) is RenderDestination.APPENDIX
