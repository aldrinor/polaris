"""I-deepfix-001 Wave 2b (#1344) — the MINIMAL independently-entailing inline citation set.

Design: ``.codex/I-deepfix-001/wave2b_brief.md`` + ``.codex/I-deepfix-001/REAL_PLAN_2026.md``
(``traceability`` items 1 + 2). MODULE ONLY — wiring into the render path is a separate Batch-2
step (``2b-wiring``); nothing here is called from the live pipeline yet.

WHAT IT DECIDES (and, just as importantly, what it does NOT):

Given ONE already-verified sentence and the basket members currently cited inline on it, decide
which members render as inline ``[N]`` citations and which move to the corroboration WEIGHT channel
(the ``_basket_corroboration_block`` / CWF surface). Two legs:

  1. PRUNE (DeepTRACE Citation-Accuracy leg). For each member run
     ``entails_directional(premise=member_span, hypothesis=sentence)`` — the ALCE / DeepTRACE
     citation direction (the cited SPAN must entail the CLAIM). A confident ``False`` (the span
     does not carry that sentence) demotes the member out of the inline set into the weight channel.
     A ``True`` OR a ``None`` (infra-unavailable verdict) KEEPS the member — fail-open: a citation
     is never dropped on model uncertainty. An empty span => KEEP (cannot judge).

  2. MVC-DEMOTE (DeepTRACE Source-Necessity leg). Among the survivors, a deterministic greedy
     set-cover / min-vertex-cover over the statement x source support matrix. The minimal COVER set
     (load-bearing sources — each uniquely covers a support atom) always stays inline. The remaining
     same-statement corroborators are MVC-redundant (their support is already covered); a TUNABLE
     threshold (``PG_MIN_CITE_SET_MAX_INLINE``) decides how many redundant corroborators stay inline;
     the rest move to the weight channel.

NOT decided / NOT touched: no verdict is changed, no source is deleted, no basket is shrunk;
strict_verify / NLI / 4-role D8 / provenance / span-grounding are neither imported nor invoked. This
is a RENDER-CHANNEL placement decision only — inline-cite vs weight-channel.

DNA (CLAUDE.md §-1.3): CONSOLIDATE-keep-all is preserved. The basket keeps ALL members; this only
relabels WHERE each renders. The two returned lists PARTITION the input (``inline`` disjoint-union
``weight`` == the input members; nothing lost). A member demoted to the weight channel is still a
real corroborator the CWF surface renders as count + tier weight (§-1.3 WEIGHT-not-citation).

HONEST TRADEOFF: removing a TRUE independent supporter from the inline set LOWERS DeepTRACE
Citation-Thoroughness (#8) while raising Source-Necessity (#6). So the MVC demotion is
threshold-TUNED (``PG_MIN_CITE_SET_MAX_INLINE``), never forced to a strict singleton. The default
(``0``) DISABLES demotion (prune-only) — zero thoroughness loss.

LAW VI (zero hard-coding): every knob comes from the environment (see the ``ENV_*`` table below).
PURE: no network, no faithfulness-file import at module load, no input mutation; the only model
touch is the injectable ``entail_fn`` seam (default lazily wraps ``entails_directional``), so
importing this module is cheap and the OFF identity path loads nothing.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

logger = logging.getLogger("polaris_graph.citation_set_minimizer")

# ─────────────────────────────────────────────────────────────────────────────
# LAW VI env knobs — all tunables are env-overridable; no hard-coded thresholds.
# ─────────────────────────────────────────────────────────────────────────────
ENV_FLAG = "PG_MIN_CITE_SET"                 # master gate, default OFF
ENV_PRUNE = "PG_MIN_CITE_SET_PRUNE"          # prune-non-entailing leg, default ON (when master ON)
ENV_MAX_INLINE = "PG_MIN_CITE_SET_MAX_INLINE"  # MVC demotion cap; <=0 => demotion disabled
ENV_MARGIN = "PG_MIN_CITE_SET_MARGIN"        # entailment-logit margin forwarded to entails_directional

_DEFAULT_MAX_INLINE = 0   # 0 => demotion DISABLED (prune-only); the zero-thoroughness-loss default
# The synthetic single support atom used when the caller supplies no per-source support map: every
# entailing survivor covers this ONE atom (= the whole statement), so the greedy cover is size 1 and
# every OTHER survivor is an MVC-redundant same-statement corroborator. A caller with a real
# report-level statement x source matrix passes ``support_of`` to get a genuine multi-atom cover.
_STATEMENT_ATOM = "__statement__"

_FALSEY = ("", "0", "false", "off", "no")


# ─────────────────────────────────────────────────────────────────────────────
# LAW VI flag readers
# ─────────────────────────────────────────────────────────────────────────────
def min_cite_set_enabled() -> bool:
    """True iff the minimal-citation-set render is active (master gate ``PG_MIN_CITE_SET``).

    DEFAULT-OFF: OFF => ``minimize_citation_set`` returns the identity no-op (every input member
    inline, empty weight channel), so wiring this module in later is byte-identical while OFF."""
    return os.getenv(ENV_FLAG, "0").strip().lower() not in _FALSEY


def _prune_enabled() -> bool:
    """True iff the prune-non-entailing leg runs (``PG_MIN_CITE_SET_PRUNE``, default ON when master ON)."""
    return os.getenv(ENV_PRUNE, "1").strip().lower() not in _FALSEY


def _max_inline() -> int:
    """MVC demotion cap (``PG_MIN_CITE_SET_MAX_INLINE``, default 0 => demotion disabled).

    ``<=0`` disables demotion (prune-only). A malformed value falls back to the default rather than
    failing the render."""
    raw = os.getenv(ENV_MAX_INLINE, str(_DEFAULT_MAX_INLINE)).strip()
    try:
        return int(raw)
    except (TypeError, ValueError):
        return _DEFAULT_MAX_INLINE


def _margin() -> Optional[float]:
    """Entailment margin forwarded to ``entails_directional`` (``PG_MIN_CITE_SET_MARGIN``).

    Blank / malformed => None (use the consolidation-NLI default margin)."""
    raw = os.getenv(ENV_MARGIN, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Member-shape accessors — dict- AND object-aware, mirroring generator/citation_layer_policy.py
# so this module and the render policy agree on 'one distinct source' / 'span' / 'weight'.
# ─────────────────────────────────────────────────────────────────────────────
def _member_attr(member: Any, key: str) -> Any:
    if isinstance(member, Mapping):
        return member.get(key)
    return getattr(member, key, None)


def _member_ev_id(member: Any) -> str:
    """The member's evidence_id as a string (empty when absent)."""
    return str(_member_attr(member, "evidence_id") or "")


def _member_weight(member: Any) -> float:
    """Credibility WEIGHT for representative selection (prefers ``credibility_weight``, then
    ``authority_score``; 0.0 when neither is a number). Booleans are NOT weights."""
    for key in ("credibility_weight", "authority_score"):
        v = _member_attr(member, key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return 0.0


def _member_span(member: Any, spans: Optional[Mapping[str, str]]) -> str:
    """The member's cited SPAN text. Prefers an explicit ``spans[evidence_id]`` (the per-member
    spans the caller passes), else the member's own ``direct_quote`` (the verbatim span it was
    verified on). Empty string when neither is present (=> the prune leg cannot judge => KEEP)."""
    if spans is not None:
        eid = _member_ev_id(member)
        if eid and eid in spans:
            return str(spans.get(eid) or "")
    return str(_member_attr(member, "direct_quote") or "")


# ─────────────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class MinCiteResult:
    """The inline-vs-weight-channel placement decision for ONE verified sentence.

    ``inline_members`` — the minimal independently-entailing inline ``[N]`` citation set.
    ``weight_members`` — every demoted member (rendered in the CWF corroboration weight channel);
                         == ``pruned_members`` ++ ``demoted_members``.
    ``pruned_members`` — transparency: members whose span did NOT entail the sentence.
    ``demoted_members`` — transparency: entailing survivors demoted as MVC-redundant.
    ``enabled`` — whether the minimizer ran (False on the OFF identity no-op).

    HARD INVARIANT (keep-all): ``inline_members`` ⊎ ``weight_members`` == the input members
    (multiset, by identity), and the two lists are disjoint. Nothing is deleted.

    NOTE: ``frozen=True`` freezes the field BINDINGS, not the list contents (the lists stay
    mutable). Treat every returned list as read-only — this module never mutates them post-return
    and callers should not either."""

    inline_members: list = field(default_factory=list)
    weight_members: list = field(default_factory=list)
    pruned_members: list = field(default_factory=list)
    demoted_members: list = field(default_factory=list)
    enabled: bool = True

    @property
    def all_members(self) -> list:
        """``inline ++ weight`` — the full input member set (keep-all)."""
        return list(self.inline_members) + list(self.weight_members)


# ─────────────────────────────────────────────────────────────────────────────
# Default entailment seam (lazy — importing this module stays cheap; the OFF path never loads it)
# ─────────────────────────────────────────────────────────────────────────────
def _default_entail_fn(margin: Optional[float]) -> Callable[[str, str], Optional[bool]]:
    """A ``(premise_span, hypothesis_sentence) -> Optional[bool]`` callable that lazily wraps the
    resident consolidation cross-encoder's ``entails_directional`` (ALCE/DeepTRACE span->claim
    direction). Lazy local import so module import is cheap and the OFF identity path loads no model.
    Returns None on any infra fault (caller keeps the citation)."""

    def _fn(premise: str, hypothesis: str) -> Optional[bool]:
        # BOTH the lazy import AND the call live inside the try (I-deepfix-001 2b review P1): a
        # RUNTIME fault escaping ``entails_directional`` (e.g. a malformed-logits IndexError, or
        # future signature drift) must return None (KEEP the citation), NOT crash the prune loop.
        try:
            from src.polaris_graph.synthesis.consolidation_nli import (  # noqa: PLC0415
                entails_directional,
            )
            return entails_directional(premise, hypothesis, margin=margin)
        except Exception as exc:  # noqa: BLE001 — import OR runtime fault => UNKNOWN => KEEP (fail-open)
            logger.warning(
                "[citation_set_minimizer] entails_directional unavailable/failed (%s); "
                "returning None (caller keeps the citation).", exc,
            )
            return None

    return _fn


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic greedy set-cover / min-vertex-cover (index-based, order-independent)
# ─────────────────────────────────────────────────────────────────────────────
def _greedy_set_cover(
    survivors: list, support_of: Callable[[Any], frozenset]
) -> tuple[set[int], list[int]]:
    """Return ``(cover_indices, redundant_indices)`` for a greedy minimal set-cover of the union of
    every survivor's support atoms.

    Deterministic + order-independent: at each step pick the survivor covering the MOST still-
    uncovered atoms, tie-broken by credibility-weight desc then lowest index. Members whose support
    is empty can never be load-bearing (they cover nothing) => they fall to ``redundant``. A member
    is COVER (load-bearing) iff the greedy pass selected it to cover a still-uncovered atom;
    everything else is MVC-redundant (its support is already covered)."""
    n = len(survivors)
    supports = [frozenset(support_of(survivors[i]) or ()) for i in range(n)]
    all_atoms: set = set()
    for s in supports:
        all_atoms |= s

    covered: set = set()
    cover: list[int] = []
    remaining = set(range(n))
    while covered != all_atoms:
        best: Optional[int] = None
        best_key: Optional[tuple] = None
        for i in sorted(remaining):
            gain = len(supports[i] - covered)
            if gain <= 0:
                continue
            key = (gain, _member_weight(survivors[i]))
            if best is None or key > best_key:  # type: ignore[operator]
                best, best_key = i, key
        if best is None:
            break  # no remaining member can cover the rest (cannot happen: all_atoms == union)
        cover.append(best)
        covered |= supports[best]
        remaining.discard(best)

    cover_set = set(cover)
    redundant = [i for i in range(n) if i not in cover_set]
    return cover_set, redundant


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
def minimize_citation_set(
    sentence: str,
    members: Iterable[Any],
    *,
    spans: Optional[Mapping[str, str]] = None,
    support_of: Optional[Callable[[Any], frozenset]] = None,
    entail_fn: Optional[Callable[[str, str], Optional[bool]]] = None,
    max_inline: Optional[int] = None,
) -> MinCiteResult:
    """Decide inline-vs-weight-channel placement for ``members`` cited on ``sentence``.

    ``spans`` — optional ``{evidence_id: span_text}``; falls back to each member's ``direct_quote``.
    ``support_of`` — optional ``member -> frozenset[atom]`` statement x source support; default is a
        single synthetic atom (whole-statement) so the cover is size 1 and every other survivor is an
        MVC-redundant same-statement corroborator.
    ``entail_fn`` — optional ``(premise_span, hypothesis_sentence) -> Optional[bool]`` seam
        (test-injection); default lazily wraps ``entails_directional``. ``None``/``True`` => KEEP,
        ``False`` => prune (fail-open on uncertainty).
    ``max_inline`` — per-call override of ``PG_MIN_CITE_SET_MAX_INLINE``.

    OFF (master gate) => identity no-op: every input member inline, empty weight channel. Returns a
    ``MinCiteResult`` whose ``inline`` ⊎ ``weight`` == the input members (keep-all; nothing lost)."""
    members_list = list(members)

    # OFF => byte-identical identity no-op (no import, no model, no reorder). Wiring later is a no-op
    # while OFF because callers get back exactly the members they passed, inline, in order.
    if not min_cite_set_enabled():
        return MinCiteResult(
            inline_members=members_list,
            weight_members=[],
            pruned_members=[],
            demoted_members=[],
            enabled=False,
        )

    # ── Leg 1: PRUNE non-entailing spans (fail-open on None / empty / uncertainty). ──────────────
    survivors: list = []
    pruned: list = []
    if _prune_enabled() and sentence and sentence.strip():
        efn = entail_fn if entail_fn is not None else _default_entail_fn(_margin())
        for m in members_list:
            span = _member_span(m, spans)
            if not span.strip():
                survivors.append(m)  # no span => cannot judge => KEEP
                continue
            # Defense-in-depth (I-deepfix-001 2b review P1): the entailment seam is guarded HERE too,
            # so a raising INJECTED entail_fn (or any fault the default seam did not already swallow)
            # degrades to None => KEEP, never crashes the prune loop. Log loud, never ``except: pass``.
            try:
                verdict = efn(span, sentence)  # premise=span, hypothesis=sentence (ALCE/DeepTRACE)
            except Exception as exc:  # noqa: BLE001 — any seam fault => UNKNOWN => KEEP (fail-open)
                logger.warning(
                    "[citation_set_minimizer] entail_fn raised on ev_id=%s (%s); "
                    "keeping the citation inline (fail-open).", _member_ev_id(m), exc,
                )
                verdict = None
            if verdict is False:
                pruned.append(m)  # confident non-entailment => demote to weight channel
            else:
                survivors.append(m)  # True or None => KEEP inline candidate (fail-open)
    else:
        survivors = list(members_list)

    # ── Leg 2: MVC-demote redundant same-statement corroborators (threshold-tuned). ──────────────
    cap = _max_inline() if max_inline is None else max_inline
    demoted: list = []
    if cap and cap > 0 and survivors:
        support = support_of if support_of is not None else (lambda _m: frozenset({_STATEMENT_ATOM}))
        cover_idx, redundant_idx = _greedy_set_cover(survivors, support)
        # The load-bearing COVER always stays inline (dropping it would leave an atom uncited). Fill
        # the remaining inline slots with the highest-weight redundant corroborators up to the cap;
        # demote the rest to the weight channel. Effective inline count is max(|cover|, cap).
        keep_extra = max(0, cap - len(cover_idx))
        redundant_sorted = sorted(
            redundant_idx, key=lambda i: _member_weight(survivors[i]), reverse=True
        )
        kept_idx = set(cover_idx) | set(redundant_sorted[:keep_extra])
        inline = [survivors[i] for i in range(len(survivors)) if i in kept_idx]
        demoted = [survivors[i] for i in range(len(survivors)) if i not in kept_idx]
    else:
        inline = survivors  # demotion disabled (default) => prune-only; all survivors stay inline

    weight = pruned + demoted
    return MinCiteResult(
        inline_members=inline,
        weight_members=weight,
        pruned_members=pruned,
        demoted_members=demoted,
        enabled=True,
    )
