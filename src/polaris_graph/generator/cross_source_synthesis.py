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
  * "extension" (D2, I-deepfix-001) is now licensed — but ONLY by a CERTIFIED DIRECTIONAL-entailment
    verdict from ``consolidation_nli.entails_directional`` (clause B entails-and-extends clause A). It
    FAILS CLOSED to ``neutral`` on any absent/negative/error signal, is gated by ``PG_CROSS_SOURCE_EXTENSION``
    (default-ON), and NEVER outranks a real ``conflict``. No free-form judge, no LLM guess for the word.
  * "agreement" (L3, I-deepfix-001 COVERAGE) is licensed on the LIVE edges-only path by an EXPLICIT
    BIDIRECTIONAL-equivalence verdict — clause A entails clause B AND clause B entails clause A (BOTH
    directions entail), the symmetric consolidation-merge predicate, asked of the SAME certified engine
    ``consolidation_nli.entails_directional`` in both directions. Before L3 the live composer passed only
    ``edges`` (never an ``agree_map``/``equiv_clusters``), so agreement could NEVER fire live; L3 wires the
    explicit signal so two clauses that are the SAME claim corroborated render "; consistent with this, ".
    It FAILS CLOSED to ``neutral`` on any one-way / absent / negative / error signal, is gated by
    ``PG_CROSS_SOURCE_AGREEMENT`` (default-ON), and NEVER outranks a real ``conflict``. No free-form judge,
    no LLM guess for the word.

LAW VI: gated by ``PG_CROSS_SOURCE_SYNTHESIS`` (read by the caller in ``verified_compose``); when the
flag is off this module is never invoked and the section producer is byte-identical. PURE: no network,
no model, no faithfulness-file import, no input mutation. snake_case.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# The CLOSED set of cross-source connectives. The VALUE is inserted between the two verified clauses;
# it carries NO factual content and NO provenance token, so ``strict_verify`` still gates iff both atoms
# pass. ``neutral`` is pure juxtaposition (the fail-closed default). The ``agreement`` / ``conflict`` /
# ``extension`` phrases are kept in sync with ``relational_quantifier_guard._ANALYTICAL_CONNECTIVE_RELATION``
# (the guard neutralizes an UNLICENSED one back to ``neutral``). Wave-2a NOTE (deliberate, brief decision 4):
# ``comparison`` (``"; for comparison, "``) is DELIBERATELY NOT added to the guard's regex — this composer
# is the SOLE emitter of it and licenses "comparison" FIRST (the fail-closed numeric comparator), so there
# is no unlicensed "for comparison" for the guard to neutralize; adding it to the guard would risk mutating
# a verbatim-atom source-prose "for comparison" on the DEFAULT-ON ``PG_CROSS_SOURCE_SYNTHESIS`` path.
LICENSED_CONNECTIVES: dict[str, str] = {
    "agreement": "; consistent with this, ",
    "conflict": "; in contrast, ",
    "extension": "; extending this, ",  # D2: licensed by a certified directional-entailment verdict
    "comparison": "; for comparison, ",  # Wave-2a: licensed by the deterministic FAIL-CLOSED numeric comparator (non-directional)
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
    directional_entails: Optional[bool] = None,
    bidirectional_entails: Optional[bool] = None,
) -> str:
    """Decide the LICENSED relation between two claim clusters from the EXISTING certified engines.

    Returns one of ``conflict`` / ``agreement`` / ``extension`` / ``neutral``:
      * ``conflict``   iff a ContradictionEdge joins the pair (the certified semantic/qualitative/rule
        contradiction detectors) — surfaces the disagreement ("in contrast"), the DeepTRACE
        one-sidedness win, ONLY ever from a real verified edge;
      * ``agreement``  iff EITHER (i) an EXPLICIT BIDIRECTIONAL-equivalence verdict positively confirms
        that clause A entails clause B AND clause B entails clause A (``bidirectional_entails is True`` —
        the L3 COVERAGE signal the caller computes from the certified engine
        ``consolidation_nli.entails_directional`` asked in BOTH directions, the symmetric consolidation
        merge predicate) OR (ii) the consolidation/equivalence lookup (``agree_map`` / ``equiv_clusters``)
        says A entails/equiv B — either way the two clauses are the SAME claim corroborated ("consistent
        with this"). ``bidirectional_entails`` licenses agreement ONLY when EXACTLY ``True``; ``None`` /
        ``False`` (no signal, a one-way entailment, a confident non-equivalence, or an infra fault) adds
        NOTHING here and FAILS CLOSED (the ``agree_map`` lookup or neutral decides). The live edges-only
        path carries no ``agree_map``, so before L3 agreement could never fire; the explicit signal is
        what wires it. A WRONG "consistent with this" is a relation fabrication, so it is gated by the
        engine and NEVER by a free-form / LLM guess for the word;
      * ``extension``  iff a CERTIFIED DIRECTIONAL-entailment signal positively confirms that clause B
        (the SECOND, continuation clause the "; extending this, " connective points at) entails-and-adds
        to clause A — i.e. B is a proper superset/elaboration of A, so "A; extending this, B" is faithful.
        The signal is ``directional_entails`` (computed by the caller from the certified engine
        ``consolidation_nli.entails_directional``, the ONE-directional NLI counterpart to the bidirectional
        consolidation merge). The caller sets it ``True`` ONLY on a PROPER one-way entailment — B entails A
        AND A does NOT entail B (a confident reverse non-entailment), so a bidirectional PARAPHRASE
        (equivalence) is excluded at the signal and can never reach the extension branch here even when the
        agreement-precedence inputs (``agree_map`` / ``equiv_clusters``) are absent on the live edges-only
        path. It licenses ``extension`` ONLY when EXACTLY ``True``; ``None`` / ``False``
        (no signal, a confident non-entailment, an equivalence, or an infra fault) FAIL-CLOSED to neutral.
        This is a NEW RELATION WORD between two already strict_verify-PASSED atoms; a WRONG "extension" is
        a relation fabrication, so it is gated by the engine and NEVER by a free-form / LLM guess;
      * ``neutral``    otherwise — pure juxtaposition. NEVER fabricate a relation the engines did not
        license (over-relax is the lethal direction).

    Precedence (most-specific-faithful first): ``conflict`` ALWAYS wins (a contested pair is reported as a
    conflict, never smoothed into agreement/extension). Then ``agreement`` (a bidirectional equivalence is
    "consistent with", not an "extension" — a truly equivalent B adds no information); the explicit
    ``bidirectional_entails`` signal and the ``agree_map``/``equiv_clusters`` lookup are the two agreement
    sources and are checked BEFORE extension so an equivalence is never mislabeled an extension. Then
    ``extension`` (a PROPER one-way directional entailment, which a bidirectional equivalence never
    contains — the two are mutually exclusive: extension needs ``a_entails_b`` False, agreement needs it
    True). Then ``neutral``. ``bidirectional_entails`` / ``directional_entails`` are WEIGHTED signals
    surfaced as a connective word; neither is ever a DROP / CAP / FILTER (§-1.3)."""
    if _edge_between(edges, cluster_a_id, cluster_b_id):
        return "conflict"
    if bidirectional_entails is True or _agree(
        agree_map, equiv_clusters, cluster_a_id, cluster_b_id
    ):
        return "agreement"
    if directional_entails is True:
        return "extension"
    return "neutral"


def _distinct_ev_ids(text: str) -> set[str]:
    """The distinct evidence_ids cited by the provenance tokens in ``text``."""
    return {m.group("ev_id") for m in _EV_SPAN_RE.finditer(text or "")}


# LAW VI — the fine flag for the D2 "extension" relation. DEFAULT-ON (the whole cross-source path is
# gated by ``PG_CROSS_SOURCE_SYNTHESIS`` upstream in ``verified_compose``; this only lets an operator
# switch OFF the directional-extension word without disabling conflict/agreement). Even when ON,
# ``extension`` is FAIL-CLOSED: it renders ONLY on a positive certified directional-entailment verdict.
_ENV_EXTENSION_FLAG = "PG_CROSS_SOURCE_EXTENSION"


def cross_source_extension_enabled() -> bool:
    """``PG_CROSS_SOURCE_EXTENSION`` — the D2 extension-relation switch. DEFAULT-ON. OFF => the composer
    never asks the directional engine and ``license_relation`` never sees ``directional_entails=True``,
    so the connective can only ever be conflict / agreement / neutral (the pre-D2 behavior). This is a
    WEIGHT switch, never a hard cap on breadth (§-1.3)."""
    return os.getenv(_ENV_EXTENSION_FLAG, "1").strip().lower() not in ("", "0", "false", "off", "no")


# LAW VI — the fine flag for the L3 COVERAGE "agreement" relation. DEFAULT-ON (the whole cross-source path
# is gated by ``PG_CROSS_SOURCE_SYNTHESIS`` upstream in ``verified_compose``; this only lets an operator
# switch OFF the explicit bidirectional-equivalence agreement word without disabling conflict/extension).
# Even when ON, ``agreement`` is FAIL-CLOSED: it renders ONLY on a positive certified BIDIRECTIONAL
# (both-directions-entail) verdict (or a real ``agree_map``/``equiv_clusters`` lookup).
_ENV_AGREEMENT_FLAG = "PG_CROSS_SOURCE_AGREEMENT"


def cross_source_agreement_enabled() -> bool:
    """``PG_CROSS_SOURCE_AGREEMENT`` — the L3 explicit bidirectional-equivalence agreement switch.
    DEFAULT-ON. OFF => the composer never asks the engine for the bidirectional signal and
    ``license_relation`` never sees ``bidirectional_entails=True``, so agreement can then only be licensed
    by an ``agree_map``/``equiv_clusters`` lookup (which the LIVE edges-only path does not carry — i.e. the
    pre-L3 behavior where agreement never fired live). This is a WEIGHT switch, never a hard cap on breadth
    (§-1.3)."""
    return os.getenv(_ENV_AGREEMENT_FLAG, "1").strip().lower() not in ("", "0", "false", "off", "no")


def _strip_ev_tokens(clause: str) -> str:
    """The clause prose with its ``[#ev:...]`` provenance tokens removed and whitespace collapsed — the
    CLEAN natural-language text handed to the NLI cross-encoder. The rendered clause KEEPS its token
    (this only affects the signal input, never the emitted sentence)."""
    return re.sub(r"\s+", " ", _EV_TOKEN_RE.sub(" ", clause or "")).strip()


def _default_entail_fn() -> Optional[Callable[[str, str], Optional[bool]]]:
    """The CERTIFIED directional-entailment engine — ``consolidation_nli.entails_directional`` (the
    one-directional NLI counterpart to the bidirectional consolidation merge, reading ONLY the forward
    logits at the SAME entailment-argmax threshold ``_entails`` the consolidation leg uses). It reuses
    the RESIDENT cross-encoder the consolidation leg already loads (zero extra OpenRouter/GPU spend) and
    FAIL-CLOSES to ``None`` on any infra fault. Returns None only if the module cannot be imported at
    all (then the extension signal is unavailable -> fail-closed to no-extension)."""
    try:
        from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
            entails_directional,
        )
    except Exception as exc:  # noqa: BLE001 — signal unavailable => fail-closed (no extension)
        logger.warning(
            "[cross_source_synthesis] certified directional-entailment engine unavailable (%s); "
            "extension relation fail-closed to neutral", exc,
        )
        return None
    return entails_directional


def _safe_entail(
    fn: Callable[[str, str], Optional[bool]], premise: str, hypothesis: str,
) -> Optional[bool]:
    """ONE certified directional-entailment verdict, FAIL-CLOSED to ``None`` on any engine fault. Never
    raises into the composer and never fabricates a relation — an infra fault reads as "no signal", so the
    connective falls to ``neutral`` (over-relax is the lethal direction)."""
    try:
        return fn(premise, hypothesis)
    except Exception as exc:  # noqa: BLE001 — an engine fault FAIL-CLOSES to neutral (never a relation)
        logger.warning(
            "[cross_source_synthesis] directional-entailment engine raised (%s); "
            "relation signal fail-closed to neutral", exc,
        )
        return None


def _pair_entailment_verdicts(
    clause_a: str,
    clause_b: str,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]],
) -> tuple[Optional[bool], Optional[bool]]:
    """The TWO certified directional NLI verdicts for the ordered clause pair, SHARED by both the
    ``extension`` (directional) and ``agreement`` (bidirectional-equivalence) relation signals so the
    resident cross-encoder is asked at most ONCE per direction per pair (no duplicate forward passes on
    the hot path). Reads ONLY the CLEAN token-stripped clause prose (the rendered clause keeps its token).

    Returns ``(a_entails_b, b_entails_a)`` where each element is the ``consolidation_nli.entails_directional``
    verdict — ``True`` (entails), ``False`` (a CONFIDENT non-entailment), or ``None`` (empty text /
    unavailable engine / infra fault — the FAIL-CLOSED sentinel). Each direction fails closed INDEPENDENTLY;
    a fault on one never fabricates a verdict for the other. Never an LLM/judge call — the SAME resident
    cross-encoder the consolidation leg already loads (zero extra OpenRouter/GPU spend)."""
    fn = entail_fn if entail_fn is not None else _default_entail_fn()
    if fn is None:
        return (None, None)
    clause_a_text = _strip_ev_tokens(clause_a)
    clause_b_text = _strip_ev_tokens(clause_b)
    if not clause_a_text or not clause_b_text:
        return (None, None)
    a_entails_b = _safe_entail(fn, clause_a_text, clause_b_text)  # does clause_a entail clause_b?
    b_entails_a = _safe_entail(fn, clause_b_text, clause_a_text)  # does clause_b entail clause_a?
    return (a_entails_b, b_entails_a)


def _extension_from_verdicts(
    a_entails_b: Optional[bool], b_entails_a: Optional[bool],
) -> Optional[bool]:
    """The ``extension`` licence derived from the two shared verdicts: clause_b entails clause_a (the
    SUPPORT direction) AND clause_a does NOT entail clause_b (a CONFIDENT reverse non-entailment => clause_b
    is a PROPER superset, not an equivalence). ``True`` ONLY on that proper one-way entailment; any other
    combination — including a reverse ``True`` (equivalence), a reverse ``None`` (unavailable), or a forward
    that is not ``True`` — returns ``None`` (FAIL-CLOSED to neutral, never a wrong "extending this")."""
    if b_entails_a is True and a_entails_b is False:
        return True
    return None


def _bidirectional_agreement_from_verdicts(
    a_entails_b: Optional[bool], b_entails_a: Optional[bool],
) -> Optional[bool]:
    """The ``agreement`` licence derived from the two shared verdicts: a BIDIRECTIONAL equivalence — clause_a
    entails clause_b AND clause_b entails clause_a (BOTH directions entail, the symmetric consolidation-merge
    predicate the L3 COVERAGE lever wires to the LIVE edges-only path). ``True`` ONLY when BOTH are ``True``;
    any ``False`` / ``None`` (a one-way entailment, a confident non-equivalence, an unavailable engine, or an
    infra fault) returns ``None`` (FAIL-CLOSED to neutral, never a wrong "consistent with this"). Mutually
    exclusive with ``_extension_from_verdicts`` by construction (extension needs ``a_entails_b`` False)."""
    if a_entails_b is True and b_entails_a is True:
        return True
    return None


def _directional_extension_signal(
    clause_a: str,
    clause_b: str,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]],
) -> Optional[bool]:
    """Compute the CERTIFIED directional-entailment verdict that licenses ``extension`` for the ordered
    pair ``(clause_a, clause_b)``.

    The rendered sentence is ``[clause_a]; extending this, [clause_b]`` — the "; extending this, "
    connective points BACK at clause_a, so clause_b is the clause that EXTENDS/elaborates it. For that to
    be faithful, clause_b must be a PROPER superset of clause_a: clause_b must ADD information, not merely
    restate it. A mere bidirectional PARAPHRASE (clause_b entails clause_a AND clause_a entails clause_b)
    adds NOTHING — the faithful word there is "consistent with" (agreement), not "extending this". So we
    ask the certified engine BOTH directions and license ``extension`` ONLY on a PROPER one-way entailment:

      * FORWARD  ``fn(clause_b, clause_a)`` must be ``True``  — clause_b entails clause_a (the SUPPORT
        direction the engine was built for);
      * REVERSE  ``fn(clause_a, clause_b)`` must be ``False`` — a CONFIDENT non-entailment, i.e. clause_a
        does NOT entail clause_b, proving clause_b carries strictly MORE than clause_a (a proper superset,
        not an equivalence).

    Returns:
      * ``True``  only when FORWARD is ``True`` AND REVERSE is ``False`` (a proper directional extension);
      * ``None`` (the FAIL-CLOSED sentinel — ``license_relation`` treats anything but ``True`` as "no
        extension") when the feature is OFF, no engine is available, the FORWARD direction is not a
        positive entailment, OR the REVERSE direction is anything other than a confident ``False``
        (``True`` = equivalence, ``None`` = unavailable, or an engine fault). We never guess the relation
        and never call an LLM here; the equivalence guard fails CLOSED to neutral, never open to a wrong
        relation word between two verified facts.

    L3 refactor: the two directional NLI passes are now computed by the SHARED ``_pair_entailment_verdicts``
    (so the extension and agreement signals ask the resident cross-encoder at most once per direction), and
    the extension decision is the pure ``_extension_from_verdicts``. The RESULT is byte-identical to the
    pre-L3 forward/reverse logic (FORWARD = ``b_entails_a`` must be ``True``; REVERSE = ``a_entails_b`` must
    be ``False``); only the internal wiring is shared."""
    if not cross_source_extension_enabled():
        return None
    a_entails_b, b_entails_a = _pair_entailment_verdicts(clause_a, clause_b, entail_fn)
    return _extension_from_verdicts(a_entails_b, b_entails_a)


def _bidirectional_agreement_signal(
    clause_a: str,
    clause_b: str,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]],
) -> Optional[bool]:
    """Compute the CERTIFIED BIDIRECTIONAL-equivalence verdict that licenses ``agreement`` for the pair
    ``(clause_a, clause_b)`` — the L3 COVERAGE lever.

    The rendered sentence is ``[clause_a]; consistent with this, [clause_b]``. For that to be faithful the
    two clauses must be the SAME claim corroborated — a BIDIRECTIONAL equivalence: clause_a entails clause_b
    AND clause_b entails clause_a (BOTH directions entail), the symmetric predicate the consolidation merge
    already uses. We ask the SAME certified engine (``consolidation_nli.entails_directional``) in BOTH
    directions and license ``agreement`` ONLY on both-True.

    Returns:
      * ``True``  only when clause_a entails clause_b AND clause_b entails clause_a (a proven equivalence);
      * ``None`` (the FAIL-CLOSED sentinel — ``license_relation`` treats anything but ``True`` as "no
        bidirectional agreement") when the feature is OFF, no engine is available, EITHER direction is not a
        positive entailment (a one-way entailment, a confident non-equivalence, an unavailable verdict, or
        an engine fault). We never guess the relation and never call an LLM here; the connective falls to
        neutral (or an ``agree_map`` lookup) rather than open to a wrong "consistent with this"."""
    if not cross_source_agreement_enabled():
        return None
    a_entails_b, b_entails_a = _pair_entailment_verdicts(clause_a, clause_b, entail_fn)
    return _bidirectional_agreement_from_verdicts(a_entails_b, b_entails_a)


def _cross_source_relation_signals(
    clause_a: str,
    clause_b: str,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]],
) -> tuple[Optional[bool], Optional[bool]]:
    """Compute BOTH engine signals — ``(directional_entails, bidirectional_entails)`` — for the ordered
    pair from ONE shared pair of NLI forward passes (the hot-path entry the composer uses).

    Each signal is INDEPENDENTLY flag-gated (``PG_CROSS_SOURCE_EXTENSION`` / ``PG_CROSS_SOURCE_AGREEMENT``,
    both DEFAULT-ON) and FAIL-CLOSED to ``None``. When BOTH flags are off, NO engine call is made
    (``(None, None)``). Extension and agreement are MUTUALLY EXCLUSIVE by construction (extension needs
    ``a_entails_b`` False; agreement needs it True), and ``license_relation`` checks agreement ahead of
    extension as the backstop. Sharing the two verdicts keeps this FAST (§ operator FAST DNA): the resident
    cross-encoder is asked at most twice per eligible pair regardless of how many relation words we derive."""
    ext_on = cross_source_extension_enabled()
    agr_on = cross_source_agreement_enabled()
    if not (ext_on or agr_on):
        return (None, None)
    a_entails_b, b_entails_a = _pair_entailment_verdicts(clause_a, clause_b, entail_fn)
    directional = _extension_from_verdicts(a_entails_b, b_entails_a) if ext_on else None
    bidirectional = _bidirectional_agreement_from_verdicts(a_entails_b, b_entails_a) if agr_on else None
    return (directional, bidirectional)


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


# ── I-deepfix-001 Wave-2a (#1344): PLAN-DRIVEN pairing (replaces near-self-annulling anchor equality) ──
# LAW VI: DEFAULT-OFF (``PG_CROSS_SOURCE_BODY``). OFF => the legacy ``_basket_anchor`` (subject|predicate)
# grouping runs UNCHANGED (byte-identical). ON => a pair of section baskets is a CANDIDATE when they are
# PLAN-related — same section facet (proxied by the same normalized subject, since baskets carry no facet
# field and consolidation already merged same-subject-same-predicate claims into ONE cluster, so the old
# subject|predicate anchor near-self-annuls), OR joined by a certified ContradictionEdge / refuter
# reference, OR bidirectionally/directionally agreeing per the threaded agree-map. The RELATION word is
# still decided ONLY by ``license_relation`` from the certified engines; candidacy just admits the pair to
# be analyzed. FAIL-CLOSED: an unlicensed pair renders the neutral connective, never a fabricated relation.
_ENV_CROSS_SOURCE_BODY = "PG_CROSS_SOURCE_BODY"


def cross_source_body_enabled() -> bool:
    """``PG_CROSS_SOURCE_BODY`` gate (default OFF, LAW VI). OFF => anchor-equality pairing (byte-identical);
    ON => plan-driven candidate pairing (same-facet / contradiction / agreement). A WEIGHT/CONSOLIDATE
    lever, never a cap / target / thinner (§-1.3)."""
    return os.getenv(_ENV_CROSS_SOURCE_BODY, "0").strip().lower() not in ("", "0", "false", "off", "no")


# ── I-deepfix-001 FIX 3 (#1344): thread the consolidation AGREEMENT MAP into the composer ─────────────
# LAW VI: DEFAULT-OFF (``PG_CROSS_SOURCE_THREAD_CONSOLIDATION``). Before FIX 3 the caller
# (``verified_compose._compose_section_per_basket``) threaded ONLY ``edges`` (the ContradictionEdge list)
# and never an ``agree_map`` / ``equiv_clusters``, so ``compose_cross_source_analytical_units`` logged
# ``input_threaded=False degraded=True`` and cross-basket CORROBORATION could never admit a plan-driven
# candidate (only same-facet / edge / refuter did). ON => the caller builds a per-section agree_map from
# the SAME certified bidirectional-NLI merge predicate the consolidation leg uses (both directions entail),
# so ``input_threaded=True`` and two DISTINCT baskets carrying the SAME claim are admitted + surface the
# ``agreement`` connective. It is a CONSOLIDATE lever (adds candidacy + a relation WORD), never a
# drop / cap / thinner (§-1.3), and it is FAITHFULNESS-NEUTRAL: strict_verify is byte-untouched; each
# emitted connective is STILL independently re-gated per BUILT clause inside ``_process_pair`` and each
# atom re-passes strict_verify (the map only admits candidacy + telemetry, it never relaxes the engine).
_ENV_THREAD_CONSOLIDATION = "PG_CROSS_SOURCE_THREAD_CONSOLIDATION"


def cross_source_thread_consolidation_enabled() -> bool:
    """``PG_CROSS_SOURCE_THREAD_CONSOLIDATION`` gate (default OFF, LAW VI). OFF => the caller threads no
    agree_map (byte-identical: ``input_threaded=False`` as before). ON => the caller builds a per-section
    bidirectional-equivalence agree_map (``build_basket_agreement_map``) and threads it. A CONSOLIDATE
    lever, never a cap / target / thinner (§-1.3)."""
    return os.getenv(_ENV_THREAD_CONSOLIDATION, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _basket_claim_text(basket: Any) -> str:
    """The basket's representative claim text — the SAME cluster-representative text the consolidation leg
    compares. '' (never an agreement candidate) when absent, mirroring ``_basket_anchor``'s blank guard."""
    return _strip_ev_tokens(str(getattr(basket, "claim_text", "") or "").strip())


def build_basket_agreement_map(
    baskets: list,
    *,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
) -> dict[str, set]:
    """Build the per-section consolidation AGREEMENT MAP threaded into the cross-source composer (FIX 3).

    Two DISTINCT-cluster section baskets AGREE iff the certified engine confirms a BIDIRECTIONAL
    equivalence over their representative claim texts — clause A entails clause B AND clause B entails
    clause A (BOTH directions entail), the SAME symmetric merge predicate ``consolidation_nli`` uses. The
    result is a dict ``cluster_id -> set(cluster_id)`` in the shape ``_agree`` reads; an empty dict when no
    pair agrees (then ``input_threaded`` stays False — honest, never forced).

    FAIL-CLOSED (Codex #1344 iter-1 P1): each pair's bidirectional NLI check is wrapped in try/except so a
    RAISED exception from ``entail_fn(ta, tb)`` OR ``entail_fn(tb, ta)`` NEVER propagates and aborts the
    composer — the pair simply contributes NO map entry (an infra fault licenses NOTHING, the §-1.3 +
    module "under-relax is safe; over-relax is lethal" contract). A one-way / absent / non-``True`` verdict
    likewise adds no entry. Never mutates the baskets. Reuses the RESIDENT cross-encoder the consolidation
    leg already loads (``_default_entail_fn``) — zero extra OpenRouter / GPU spend.

    Faithfulness-neutral: the map only ADMITS candidacy + drives the ``input_threaded`` telemetry; the
    emitted ``agreement`` connective is STILL independently re-gated per BUILT clause inside
    ``_process_pair`` (``_bidirectional_agreement_signal``) and each atom re-passes the UNCHANGED
    strict_verify. It NEVER relaxes the frozen engine."""
    if not cross_source_thread_consolidation_enabled():
        return {}
    items: list[tuple[str, str]] = []
    for b in (baskets or []):
        cid = _cluster_id(b)
        text = _basket_claim_text(b)
        if cid and text:
            items.append((cid, text))
    if len(items) < 2:
        return {}
    fn = entail_fn if entail_fn is not None else _default_entail_fn()
    if fn is None:
        return {}
    agree_map: dict[str, set] = {}
    n = len(items)
    for i in range(n):
        cluster_a_id, text_a = items[i]
        for j in range(i + 1, n):
            cluster_b_id, text_b = items[j]
            if not cluster_a_id or not cluster_b_id or cluster_a_id == cluster_b_id:
                continue
            # FAIL-CLOSED: an ``entail_fn`` fault on EITHER direction contributes no map entry and never
            # aborts the composer (Codex #1344 iter-1 P1). The bidirectional-equivalence decision reuses
            # the shared pure ``_bidirectional_agreement_from_verdicts`` (both-True), so the "agreement"
            # licence here is byte-identical to the composer's own ``_bidirectional_agreement_signal``.
            try:
                a_entails_b = fn(text_a, text_b)
                b_entails_a = fn(text_b, text_a)
            except Exception as exc:  # noqa: BLE001 — an NLI fault licenses NOTHING (fail-closed)
                logger.warning(
                    "[cross_source_synthesis] agreement-map bidirectional NLI raised (%s); pair "
                    "fails closed (no map entry)", exc,
                )
                continue
            if _bidirectional_agreement_from_verdicts(a_entails_b, b_entails_a) is True:
                agree_map.setdefault(cluster_a_id, set()).add(cluster_b_id)
                agree_map.setdefault(cluster_b_id, set()).add(cluster_a_id)
    return agree_map


def _basket_subject(basket: Any) -> str:
    """A basket's normalized SUBJECT (the facet proxy). '' for a blank subject (never a facet match)."""
    return _norm_anchor(getattr(basket, "subject", "") or "")


def _same_facet(a: Any, b: Any) -> bool:
    """Two baskets are on the SAME section facet iff they share a non-empty normalized subject. This is
    strictly BROADER than the legacy subject|predicate anchor (which self-annuls after consolidation) yet
    bounded to the same entity — never an arbitrary cross-subject juxtaposition (brief risk #3)."""
    sa = _basket_subject(a)
    return bool(sa) and sa == _basket_subject(b)


def _refuter_cross_ref(a: Any, b: Any, cluster_a_id: str, cluster_b_id: str) -> bool:
    """True iff either basket's durable ``refuter_cluster_ids`` references the other's cluster — the
    consolidation-layer conflict signal that complements ``_edge_between`` (both read only certified
    contradiction references, never a free-form guess). Conservative on missing data -> False."""
    def _refs(basket: Any) -> set:
        try:
            return {str(x) for x in (getattr(basket, "refuter_cluster_ids", None) or ())}
        except TypeError:
            return set()
    return cluster_b_id in _refs(a) or cluster_a_id in _refs(b)


def _pair_is_plan_candidate(
    a: Any, b: Any, cluster_a_id: str, cluster_b_id: str,
    *, edges: Any, agree_map: Any, equiv_clusters: Any,
    numeric_key_by_cluster: Optional[dict] = None,
) -> bool:
    """The plan-driven candidacy predicate: same facet OR a certified contradiction (edge / refuter) OR a
    threaded agreement lookup OR (I-deepfix-001 #1369 STEP 3) a licensed construct-level numeric comparison.
    NLI (extension / bidirectional agreement) refines the CONNECTIVE for admitted candidates but is NOT
    re-run here as a candidacy gate over every O(N^2) pair (a pure cross-subject NLI-only candidacy is
    DEFERRED for cost; the resident encoder still fires per candidate). Pure; deterministic; conservative
    on missing data."""
    if _same_facet(a, b):
        return True
    if _edge_between(edges, cluster_a_id, cluster_b_id):
        return True
    if _refuter_cross_ref(a, b, cluster_a_id, cluster_b_id):
        return True
    if _agree(agree_map, equiv_clusters, cluster_a_id, cluster_b_id):
        return True
    # I-deepfix-001 (#1369) STEP 3: construct-level numeric candidacy — admit a pair whose two clusters
    # carry numeric merge keys the DETERMINISTIC, FAIL-CLOSED comparator licenses (same construct + unit,
    # differing values), even across DIFFERENT subjects/facets. This is what lets Frey-Osborne vs Eloundou
    # vs ILO exposure numbers become cross-source comparison candidates (892 numbers that rendered zero
    # comparison). Only when the key lookup is threaded AND the comparator is enabled AND the license fires;
    # the RELATION is still decided by _process_pair (which re-consults the comparator), so this only WIDENS
    # candidacy — it never asserts a comparison the licensing engine did not grant.
    if numeric_key_by_cluster:
        from src.polaris_graph.generator.numeric_comparator import (  # noqa: PLC0415
            license_numeric_comparison,
            numeric_comparator_enabled,
        )
        if numeric_comparator_enabled() and license_numeric_comparison(
            numeric_key_by_cluster.get(cluster_a_id),
            numeric_key_by_cluster.get(cluster_b_id),
        ):
            return True
    return False


def _anchor_candidate_pairs(baskets: list):
    """The LEGACY (default-OFF path) pairing: baskets grouped by the subject|predicate anchor, yielding
    every unordered pair within an anchor group in the SAME order as the pre-Wave-2a nested loop, so the
    OFF path is byte-identical."""
    by_anchor: dict[str, list] = {}
    for b in baskets:
        anchor = _basket_anchor(b)
        if anchor:
            by_anchor.setdefault(anchor, []).append(b)
    _emitted = 0
    for _anchor, group in by_anchor.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                _emitted += 1
                yield group[i], group[j]
    # I-deepfix-001 Wave-3a (#1344): anchor-equality ACTIVATION DEGRADE tripwire. Emitted ONLY when
    # PG_CROSS_SOURCE_BODY is ON — which in normal operation is exactly the case where the plan-driven
    # pairing (NOT this legacy path) is used, so this marker stays ABSENT (the canary asserts absence). It
    # fires only if the body ever degrades to anchor pairing under the ON flag. On the OFF path the flag is
    # OFF => no line => byte-identical (the ``_emitted`` counter produces no output). This runs on generator
    # exhaustion, which the single full-drain consumer loop guarantees.
    if cross_source_body_enabled():
        logger.info("[activation] cross_source_body: anchor_equality pairs=%d", _emitted)


def _plan_driven_candidate_pairs(
    baskets: list, *, edges: Any, agree_map: Any, equiv_clusters: Any,
    numeric_key_by_cluster: Optional[dict] = None,
):
    """The Wave-2a pairing: every unordered distinct-cluster pair of section baskets admitted by
    ``_pair_is_plan_candidate``, in stable i<j order over the section basket list. ``numeric_key_by_cluster``
    (I-deepfix-001 #1369 STEP 3) is threaded so a construct-level numeric comparison can WIDEN candidacy."""
    n = len(baskets)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = baskets[i], baskets[j]
            ca, cb = _cluster_id(a), _cluster_id(b)
            if not ca or not cb or ca == cb:
                continue
            if _pair_is_plan_candidate(
                a, b, ca, cb, edges=edges, agree_map=agree_map, equiv_clusters=equiv_clusters,
                numeric_key_by_cluster=numeric_key_by_cluster,
            ):
                yield a, b


def _process_pair(
    a: Any,
    b: Any,
    cluster_a_id: str,
    cluster_b_id: str,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    edges: Any,
    equiv_clusters: Any,
    agree_map: Any,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]],
    clause_cache: dict,
    numeric_key_by_cluster: Optional[dict],
    numeric_upgrade_counter: Optional[list] = None,
) -> Optional[str]:
    """Build ONE cross-source analytical unit for a candidate pair, or ``None`` when it fails to build.

    UNCHANGED per-clause faithfulness contract: each clause is built by ``_first_verified_clause`` (the
    existing ``verified_compose`` per-basket path — strict_verify against THAT basket's OWN scoped pool +
    own-region gate), cached per cluster id. The connective carries NO token and is licensed ONLY by the
    certified engines (``license_relation`` from ContradictionEdge / consolidation-NLI) plus the
    Wave-2a deterministic numeric comparator (a NEUTRAL pair whose two baskets carry FULLY-comparable
    numeric merge keys upgrades to ``comparison``; any missing/ambiguous/differing field fails CLOSED to
    neutral). The result keeps >=2 distinct cited evidence_ids (a real cross-SOURCE relation)."""
    from src.polaris_graph.generator.verified_compose import (  # noqa: PLC0415
        _join_verified_clauses,
        _strip_terminal_punct,
    )
    from src.polaris_graph.generator.relational_quantifier_guard import (  # noqa: PLC0415
        guard_relational_quantifier,
    )

    def _clause(basket: Any, cid: str) -> Optional[str]:
        if cid not in clause_cache:
            clause_cache[cid] = _first_verified_clause(
                basket, evidence_pool, writer_fn=writer_fn, verify_fn=verify_fn,
            )
        return clause_cache[cid]

    clause_a = _clause(a, cluster_a_id)
    clause_b = _clause(b, cluster_b_id)
    if not clause_a or not clause_b:
        return None  # an atom failed to build/verify -> keep both as independent sentences
    # The two clauses MUST cite DISTINCT origins (a real cross-SOURCE relation).
    if not (_distinct_ev_ids(clause_a) - _distinct_ev_ids(clause_b)):
        return None
    # D2 extension + L3 agreement (both fail-closed): ask the CERTIFIED engine — from ONE shared pair of
    # NLI forward passes — for the directional (extension) + bidirectional (agreement) signals.
    directional_entails, bidirectional_entails = _cross_source_relation_signals(
        clause_a, clause_b, entail_fn,
    )
    rel = license_relation(
        cluster_a_id, cluster_b_id, edges=edges, equiv_clusters=equiv_clusters, agree_map=agree_map,
        directional_entails=directional_entails,
        bidirectional_entails=bidirectional_entails,
    )
    # Wave-2a numeric comparator: upgrade a NEUTRAL pair to ``comparison`` ONLY when both baskets carry
    # FULLY-comparable numeric merge keys (every discriminator equal + positively known, differing values).
    # conflict / agreement / extension always take precedence; any ambiguity fails CLOSED to neutral. The
    # lookup is threaded only when ``PG_NUMERIC_COMPARATOR`` is on, so OFF => this block never runs.
    if rel == "neutral" and numeric_key_by_cluster:
        from src.polaris_graph.generator.numeric_comparator import (  # noqa: PLC0415
            license_numeric_comparison,
            numeric_comparator_enabled,
        )
        if numeric_comparator_enabled():
            comp = license_numeric_comparison(
                numeric_key_by_cluster.get(cluster_a_id),
                numeric_key_by_cluster.get(cluster_b_id),
            )
            if comp:
                rel = comp
                # Wave-3a (#1344): ADDITIVE activation count (never changes ``rel`` or the licensing).
                if numeric_upgrade_counter is not None:
                    numeric_upgrade_counter[0] += 1
    connective = LICENSED_CONNECTIVES.get(rel, LICENSED_CONNECTIVES["neutral"])
    # Strip clause_A's terminal so the join reads as one flowing sentence "[clause A]<connective>[clause B]".
    joined = _join_verified_clauses(
        [_strip_terminal_punct(clause_a), clause_b], connective=connective,
    )
    if not joined:
        return None
    # The guard neutralizes an UNLICENSED connective (defense-in-depth: our composer only ever emits a
    # licensed one). ``licensed_relations`` is the SINGLE relation we licensed for this sentence.
    guarded = guard_relational_quantifier(joined, None, licensed_relations={rel})
    final = (guarded or joined).strip()
    # KEEP only a real cross-source unit: >=2 distinct cited evidence_ids survive.
    if len(_distinct_ev_ids(final)) < 2:
        return None
    return final


def compose_cross_source_analytical_units(
    section_baskets: list,
    evidence_pool: dict,
    *,
    writer_fn: Callable[[Any, dict], str],
    verify_fn: Callable[..., Any],
    edges: Any = None,
    equiv_clusters: Any = None,
    agree_map: Any = None,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
    numeric_key_by_cluster: Optional[dict] = None,
) -> list[str]:
    """Produce verified cross-source ANALYTICAL sentences for a section.

    Wave-2a: candidate pairs come from ``_plan_driven_candidate_pairs`` when ``PG_CROSS_SOURCE_BODY`` is ON
    (same facet / contradiction / agreement) else the legacy ``_anchor_candidate_pairs`` (subject|predicate
    anchor equality — byte-identical OFF). ``numeric_key_by_cluster`` (threaded only when
    ``PG_NUMERIC_COMPARATOR`` is on) lets a NEUTRAL pair of fully-comparable numeric baskets render the
    ``comparison`` connective; None => the comparator is never consulted (byte-identical).

    For every candidate pair with DISTINCT claim clusters (see ``_process_pair``):
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
    baskets = [b for b in (section_baskets or []) if b is not None]
    # Wave-2a: plan-driven candidate pairing (``PG_CROSS_SOURCE_BODY``) vs the legacy subject|predicate
    # anchor grouping. BOTH feed the SAME per-pair processing + eligible/units/loud-canary accounting, so
    # the OFF path is OUTPUT byte-identical (same pairs, same order, same per-clause result). It is NOT
    # call-identical: the ``clause_cache`` below runs ``writer_fn``/``verify_fn`` once per CLUSTER rather
    # than once per pair-membership, so a basket appearing in K anchor pairs is composed once, not K times.
    # For the deterministic writer_fn/verify_fn the composer is given (precomputed-dict lookup / strict
    # verify) the RESULT is identical; only the number of internal calls changes (no observable effect).
    if cross_source_body_enabled():
        # Materialize so the plan-driven pair COUNT can be reported by the activation marker; the single
        # full-drain loop below is behaviorally identical to iterating the generator (same pairs, order).
        candidate_pairs = list(_plan_driven_candidate_pairs(
            baskets, edges=edges, agree_map=agree_map, equiv_clusters=equiv_clusters,
            numeric_key_by_cluster=numeric_key_by_cluster,
        ))
        # I-deepfix-001 Wave-3a (#1344): plan-driven ACTIVATION fire marker. Emitted ONLY under
        # PG_CROSS_SOURCE_BODY (this branch) so OFF is byte-identical. ``input_threaded`` is true when the
        # certified consolidation inputs (equiv_clusters / agree_map) were threaded — false means the
        # pairing degraded to same-facet/edge/refuter candidacy only. Structural presence + count (§-1.3).
        _input_threaded = bool(equiv_clusters) or bool(agree_map)
        logger.info(
            "[activation] cross_source_body: plan_driven pairs=%d input_threaded=%s degraded=%s",
            len(candidate_pairs), _input_threaded, not _input_threaded,
        )
    else:
        candidate_pairs = _anchor_candidate_pairs(baskets)

    units: list[str] = []
    seen_pair_keys: set[frozenset] = set()
    eligible_pairs = 0
    # Wave-3a (#1344): ADDITIVE numeric-comparator upgrade counter (a one-element mutable, threaded into
    # ``_process_pair`` and incremented where a NEUTRAL pair is upgraded to ``comparison``). Behavior-inert
    # — it only feeds the numeric_comparator activation marker emitted after the loop.
    _numeric_upgrades = [0]
    # cluster_id -> Optional[str]; each basket's verified clause is built at most ONCE (deterministic given
    # the same basket/pool/fns), so caching changes call-count only, never the emitted units (see above).
    clause_cache: dict = {}
    for a, b in candidate_pairs:
        ca, cb = _cluster_id(a), _cluster_id(b)
        if not ca or not cb or ca == cb:
            continue  # same / unidentifiable cluster is not a cross-source pair
        pair_key = frozenset((ca, cb))
        if pair_key in seen_pair_keys:
            continue
        seen_pair_keys.add(pair_key)
        eligible_pairs += 1
        unit = _process_pair(
            a, b, ca, cb, evidence_pool,
            writer_fn=writer_fn, verify_fn=verify_fn,
            edges=edges, equiv_clusters=equiv_clusters, agree_map=agree_map,
            entail_fn=entail_fn, clause_cache=clause_cache,
            numeric_key_by_cluster=numeric_key_by_cluster,
            numeric_upgrade_counter=_numeric_upgrades,
        )
        if unit:
            units.append(unit)

    # I-deepfix-001 Wave-3a (#1344): numeric-comparator ACTIVATION fire marker. Emitted ONLY when
    # PG_NUMERIC_COMPARATOR is ON (OFF => no line => byte-identical). ``upgraded`` counts NEUTRAL pairs the
    # deterministic comparator lifted to ``comparison``; ``build_ok`` is false when the upstream numeric
    # merge-key lookup was not threaded (None) — the silent-swallow signal now made loud at the build site.
    from src.polaris_graph.generator.numeric_comparator import (  # noqa: PLC0415
        numeric_comparator_enabled as _numeric_comparator_enabled,
    )
    if _numeric_comparator_enabled():
        logger.info(
            "[activation] numeric_comparator: upgraded=%d build_ok=%s",
            _numeric_upgrades[0], numeric_key_by_cluster is not None,
        )

    if eligible_pairs and not units:
        # Fail-LOUD canary (the "verify the feature fired in output, not in config" rule): candidate
        # cross-source pairs EXISTED, yet zero analytical units survived per-clause re-verify/licensing.
        # This is the silent-no-op trap — a FAILED validation surfaced LOUD, never quietly accepted.
        logger.warning(
            "[cross_source_synthesis] %d candidate cross-source pair(s) but 0 analytical units survived "
            "per-clause re-verify/licensing — analytical layer produced nothing for this section",
            eligible_pairs,
        )
    elif units:
        logger.info(
            "[cross_source_synthesis] composed %d cross-source analytical unit(s) from %d candidate pair(s)",
            len(units), eligible_pairs,
        )
    return units
