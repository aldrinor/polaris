"""I-deepfix-001 M6 (Layer 1) — the VERIFIED cross-source analytical-synthesis composer.

POLARIS had NO verified analytical-synthesis path, so DRB-II analysis (18% weight) scored near-zero
and "Comparative Assessment" rendered a gap stub. The within-basket multi-cited producer
(``verified_compose.compose_basket_multicited_sentence``) consolidates corroborators WITHIN one
basket and joins them with a SEMANTICALLY-NEUTRAL connective; it never spans TWO baskets and the
``relational_quantifier_guard`` actively STRIPS any relational predicate. There was no producer that
emits a sentence relating TWO distinct baskets.

THE M6 ARCHITECTURE (the only faithfulness-safe way to add analysis depth):

    An analytical sentence = ``[verified clause A][LICENSED relation connective][verified clause B]``

where (1) each clause is an existing ``strict_verify``-PASSED unit carrying its OWN
``[#ev:<id>:<start>-<end>]`` token (built by the UNCHANGED ``verified_compose`` per-basket contract),
and (2) the connective is from a CLOSED set and is LICENSED by an existing cross-basket relation
engine (``claim_graph.ClaimGraph.edges`` ContradictionEdge from the three certified detectors, or the
``consolidation_nli`` / equivalence agreement map). The synthesis asserts NO new free-standing fact —
it asserts a RELATION between two already-verified facts, and that relation is gated by the engine.

``strict_verify`` still passes iff BOTH atoms pass (the connective carries no provenance token), so the
FROZEN faithfulness engine remains the only hard gate. This module CALLS the production
``verify_sentence_provenance`` (through the per-basket ``verify_fn`` it is given) but NEVER modifies it.
It is the C2 atomic-entailment family from I-faith-001, applied at composition time: *synthesize the
RELATION, verify the ATOMS.*

FAIL-CLOSED (the §-1.3 + brief boundary contract, "under-relax is safe; over-relax is lethal"):
  * when the licensing engine does NOT fire for a pair, the connective DEFAULTS to ``neutral`` pure
    juxtaposition — a wrong "in contrast" / "consistent with this" can NEVER render;
  * when either clause fails to build / re-verify, the analytical unit is DROPPED and the two atoms
    survive as independent single-source sentences (the existing per-basket path emits them) — KEEP-ALL;
  * "extension" is in the closed vocabulary but the increment-1 ``license_relation`` NEVER returns it
    (a future producer with a directional-entailment engine may), so it is unreachable here by design.

LAW VI: gated by ``PG_CROSS_SOURCE_SYNTHESIS`` (read by the caller in ``verified_compose``); when the
flag is off this module is never invoked and the section producer is byte-identical. PURE: no network,
no model, no faithfulness-file import, no input mutation. snake_case.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# The CLOSED set of cross-source connectives. The VALUE is inserted between the two verified clauses;
# it carries NO factual content and NO provenance token, so ``strict_verify`` still gates iff both atoms
# pass. ``neutral`` is pure juxtaposition (the fail-closed default). Keep the relation PHRASES in sync
# with ``relational_quantifier_guard._ANALYTICAL_CONNECTIVE_RELATION`` (the guard neutralizes an
# UNLICENSED connective back to ``neutral``).
LICENSED_CONNECTIVES: dict[str, str] = {
    "agreement": "; consistent with this, ",
    "conflict": "; in contrast, ",
    "extension": "; extending this, ",  # reserved: license_relation never returns this in increment 1
    "neutral": "; separately, ",
}

# A provenance token: ``[#ev:<evidence_id>:<start>-<end>]`` (the shape strict_verify parses).
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
_EV_SPAN_RE = re.compile(r"\[#ev:(?P<ev_id>[A-Za-z0-9_]+):(?P<start>\d+)-(?P<end>\d+)\]")


def _norm_anchor(text: str) -> str:
    """The conservative normalized anchor key for a basket's subject (or predicate). Lower-cased,
    whitespace-collapsed, punctuation-trimmed. An empty / whitespace string is NOT an anchor (returns
    "") so empty-subject baskets are never paired (random juxtaposition is forbidden, brief risk #3)."""
    s = re.sub(r"\s+", " ", str(text or "").strip().lower())
    s = s.strip(" \t\r\n.,;:-—–")
    return s


def _basket_anchor(basket: Any) -> str:
    """A basket's pairing anchor = normalized ``subject`` + "|" + normalized ``predicate``. Two baskets
    are pairing CANDIDATES iff they share this anchor (same subject AND predicate); the RELATION between
    them is then decided by the licensing engine, never by the anchor. "" when subject is blank (the
    basket is not eligible for analytical pairing — it has no anchor to compare against)."""
    subj = _norm_anchor(getattr(basket, "subject", "") or "")
    if not subj:
        return ""
    pred = _norm_anchor(getattr(basket, "predicate", "") or "")
    return f"{subj}|{pred}"


def _cluster_id(basket: Any) -> str:
    return str(getattr(basket, "claim_cluster_id", "") or "")


def _edge_between(edges: Any, cluster_a_id: str, cluster_b_id: str) -> bool:
    """True iff a ContradictionEdge joins the two claim clusters (``claim_graph.ClaimGraph.edges`` /
    ``CredibilityAnalysis.edges``). An edge's ``claim_cluster_ids`` is the sorted pair of endpoints; we
    accept any edge whose endpoint set CONTAINS both cluster ids (recall-first, mirrors the recall-first
    edge sourcing). Conservative on missing/garbage data -> False (no conflict licensed)."""
    if not edges or not cluster_a_id or not cluster_b_id or cluster_a_id == cluster_b_id:
        return False
    want = {cluster_a_id, cluster_b_id}
    for e in edges:
        ids = getattr(e, "claim_cluster_ids", None)
        if ids is None and isinstance(e, dict):
            ids = e.get("claim_cluster_ids")
        try:
            id_set = {str(x) for x in (ids or ())}
        except TypeError:
            continue
        if want <= id_set:
            return True
    return False


def _agree(agree_map: Any, equiv_clusters: Any, cluster_a_id: str, cluster_b_id: str) -> bool:
    """True iff the consolidation/equivalence engine says cluster A and cluster B AGREE (A entails/equiv
    B). The signal is OPTIONAL: the run threads it only when an inter-basket agreement map was computed.

    ``agree_map`` may be a dict ``cluster_id -> iterable[cluster_id]`` (or set of frozenset/tuple pairs);
    ``equiv_clusters`` may be a list of clusters (each an iterable of cluster_ids) that were merged as
    equivalent. Conservative: empty / unreadable => False (NO agreement licensed -> neutral). Never a
    network/model call (the licensing already happened upstream; this is a pure lookup)."""
    if not cluster_a_id or not cluster_b_id or cluster_a_id == cluster_b_id:
        return False
    pair = {cluster_a_id, cluster_b_id}
    # (1) dict form: cluster -> neighbours that it entails/agrees-with (either direction).
    if isinstance(agree_map, dict):
        try:
            if cluster_b_id in (agree_map.get(cluster_a_id) or ()):
                return True
            if cluster_a_id in (agree_map.get(cluster_b_id) or ()):
                return True
        except TypeError:
            pass
    # (2) set/list of pairs form.
    elif agree_map:
        for entry in agree_map:
            try:
                if pair <= {str(x) for x in entry}:
                    return True
            except TypeError:
                continue
    # (3) equivalence groups: both ids inside the SAME merged group => they agree.
    for group in (equiv_clusters or ()):
        try:
            members = {str(x) for x in group}
        except TypeError:
            continue
        if pair <= members:
            return True
    return False


def license_relation(
    cluster_a_id: str,
    cluster_b_id: str,
    *,
    edges: Any = None,
    equiv_clusters: Any = None,
    agree_map: Any = None,
) -> str:
    """Decide the LICENSED relation between two claim clusters from the EXISTING certified engines.

    Returns one of ``conflict`` / ``agreement`` / ``neutral`` (NEVER ``extension`` in increment 1):
      * ``conflict``   iff a ContradictionEdge joins the pair (the certified semantic/qualitative/rule
        contradiction detectors) — surfaces the disagreement ("in contrast"), the DeepTRACE
        one-sidedness win, ONLY ever from a real verified edge;
      * ``agreement``  iff the consolidation/equivalence engine says A entails/equiv B;
      * ``neutral``    otherwise — pure juxtaposition. NEVER fabricate a relation the engines did not
        license (over-relax is the lethal direction). Conflict takes precedence over agreement (a
        contested pair is reported as a conflict, never smoothed into agreement)."""
    if _edge_between(edges, cluster_a_id, cluster_b_id):
        return "conflict"
    if _agree(agree_map, equiv_clusters, cluster_a_id, cluster_b_id):
        return "agreement"
    return "neutral"


def _distinct_ev_ids(text: str) -> set[str]:
    """The distinct evidence_ids cited by the provenance tokens in ``text``."""
    return {m.group("ev_id") for m in _EV_SPAN_RE.finditer(text or "")}


def _first_verified_clause(
    basket: Any,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
) -> Optional[str]:
    """ONE single-sentence verified clause for a basket, suitable for analytical co-location.

    Reuses the UNCHANGED ``verified_compose._per_basket_verified_clause`` (the existing P1-2/P1-1
    per-basket contract: writer drafts -> ``strict_verify`` each sentence against THIS basket's scoped
    pool -> own-region gate -> verbatim K-span fallback). The returned clause is therefore an EXISTING
    strict_verify-PASSED (or faithful-by-construction verbatim-span) unit carrying its OWN ``[#ev]``
    token. We then reduce it to its FIRST sentence-unit so the analytical join yields ONE clean sentence
    carrying exactly one token per clause. Returns None when the basket yields no verified clause (the
    pair is then skipped; the basket's own single-source unit is surfaced by the per-basket path)."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _per_basket_verified_clause,
        split_into_sentences,
    )
    clause = _per_basket_verified_clause(
        basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
    )
    if not clause or not clause.strip():
        return None
    units = [u for u in (split_into_sentences(clause) or [clause]) if u and u.strip()]
    if not units:
        return None
    first = units[0].strip()
    # The clause MUST carry exactly one provenance token (a clean single-source atom for the join).
    if not _EV_TOKEN_RE.search(first):
        return None
    return first


def compose_cross_source_analytical_units(
    section_baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    edges: Any = None,
    equiv_clusters: Any = None,
    agree_map: Any = None,
) -> list[str]:
    """Produce verified cross-source ANALYTICAL sentences for a section.

    For every UNORDERED pair of section baskets that share a subject-predicate anchor and have DISTINCT
    claim clusters:
      1. build ``clause_A`` / ``clause_B`` via the EXISTING per-basket verified contract (each already
         strict_verify-PASSED, each carrying its OWN ``[#ev]`` token);
      2. ``rel = license_relation(...)`` from the certified engines; ``connective = LICENSED_CONNECTIVES[rel]``;
      3. join ``clause_A + connective + clause_B`` (reusing ``_join_verified_clauses`` — one sentence,
         continuation lowercased), so the result carries TWO distinct ``[#ev]`` tokens from TWO baskets;
      4. run the joined sentence through ``guard_relational_quantifier(..., licensed_relations={rel})``
         so an UNLICENSED connective is neutralized to pure juxtaposition (a wrong "in contrast" can
         never render);
      5. KEEP the unit ONLY if it still carries >=2 distinct cited evidence_ids (a real cross-source
         relation). Otherwise the pair is dropped and the two atoms survive via the per-basket path.

    Pure read of the production verifier (through ``verify_fn``); the FROZEN engine is never touched.
    Order-stable. Returns the list of analytical sentence strings (possibly empty — analytical yield
    EMERGES from real anchored pairs + engine-licensed relations, it is never forced)."""
    from src.polaris_graph.generator.verified_compose import _join_verified_clauses  # noqa: PLC0415
    from src.polaris_graph.generator.relational_quantifier_guard import (  # noqa: PLC0415
        guard_relational_quantifier,
    )

    baskets = [b for b in (section_baskets or []) if b is not None]
    # Group baskets by anchor; only anchors with >=2 DISTINCT-cluster baskets can form an analytical pair.
    by_anchor: dict[str, list] = {}
    for b in baskets:
        anchor = _basket_anchor(b)
        if anchor:
            by_anchor.setdefault(anchor, []).append(b)

    units: list[str] = []
    seen_pair_keys: set[frozenset] = set()
    eligible_pairs = 0
    for anchor, group in by_anchor.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a, b = group[i], group[j]
                ca, cb = _cluster_id(a), _cluster_id(b)
                if not ca or not cb or ca == cb:
                    continue  # same / unidentifiable cluster is not a cross-source pair
                pair_key = frozenset((ca, cb))
                if pair_key in seen_pair_keys:
                    continue
                seen_pair_keys.add(pair_key)
                eligible_pairs += 1
                clause_a = _first_verified_clause(
                    a, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
                )
                clause_b = _first_verified_clause(
                    b, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
                )
                if not clause_a or not clause_b:
                    continue  # an atom failed to build/verify -> keep both as independent sentences
                # The two clauses MUST cite DISTINCT origins (a real cross-SOURCE relation).
                if not (_distinct_ev_ids(clause_a) - _distinct_ev_ids(clause_b)):
                    continue
                rel = license_relation(
                    ca, cb, edges=edges, equiv_clusters=equiv_clusters, agree_map=agree_map,
                )
                connective = LICENSED_CONNECTIVES.get(rel, LICENSED_CONNECTIVES["neutral"])
                # Strip clause_A's terminal so the join reads as one flowing sentence
                # "[clause A]<connective>[clause B]". _join_verified_clauses lowercases + de-terminates
                # the continuation and keeps the whole thing ONE sentence under the production splitter.
                from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
                    _strip_terminal_punct,
                )
                joined = _join_verified_clauses(
                    [_strip_terminal_punct(clause_a), clause_b], connective=connective,
                )
                if not joined:
                    continue
                # The guard neutralizes an UNLICENSED connective (defense-in-depth: our composer only
                # ever emits a licensed one, so this is a no-op on the happy path). licensed_relations is
                # the SINGLE relation we licensed for this sentence.
                guarded = guard_relational_quantifier(
                    joined, None, licensed_relations={rel},
                )
                final = (guarded or joined).strip()
                # KEEP only a real cross-source unit: >=2 distinct cited evidence_ids survive.
                if len(_distinct_ev_ids(final)) < 2:
                    continue
                units.append(final)

    if eligible_pairs and not units:
        # Fail-LOUD canary (the "verify the feature fired in output, not in config" rule): the flag was
        # ON and anchored cross-source pairs EXISTED, yet zero analytical units survived re-verify. This
        # is the silent-no-op trap — surface it LOUD rather than quietly emit nothing.
        logger.warning(
            "[cross_source_synthesis] %d anchored cross-source pair(s) but 0 analytical units survived "
            "per-clause re-verify/licensing — analytical layer produced nothing for this section",
            eligible_pairs,
        )
    elif units:
        logger.info(
            "[cross_source_synthesis] composed %d cross-source analytical unit(s) from %d anchored pair(s)",
            len(units), eligible_pairs,
        )
    return units
