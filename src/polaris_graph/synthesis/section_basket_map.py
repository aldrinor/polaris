"""Deterministic basket->section map (MASTER_EXECUTION_PLAN v2 S5 / Design 4 D1).

The problem this closes (measured on drb_72): consolidation is corpus-GLOBAL and
section membership is ROW-level; the two only meet through a late intersection lookup
in ``verified_compose._section_baskets_for_compose``. That bridge leaks in both
directions -- baskets whose members were never outline-assigned are STRANDED
(~600 of 657 baskets never rendered) and baskets whose members straddle sections are
pulled into EVERY such section, so the same claim composes repeatedly.

This module GROUPS every global basket UNDER the outline sections: one designated
PRIMARY home per basket plus any number of CORROBORATING memberships. The basket
KEEPS its GLOBAL identity (``claim_cluster_id`` never forks; corroboration counted
once) -- the map is pure PLACEMENT + ROLE tagging. It drops nothing, caps nothing,
targets no number (CLAUDE.md §-1.3 WEIGHT-and-CONSOLIDATE). The faithfulness engine
(strict_verify / NLI / 4-role D8 / provenance / span-grounding) is never touched: the
map only decides WHICH baskets a section's writer is submitted and in what role -- the
same class of decision the intersection bridge already makes today, made complete and
deterministic.

Provenance-token neutrality (operator 2026-07-10, per-sentence SOURCE-TIE): this module
never reads or mutates sentence text or the ``[#ev:<id>:<start>-<end>]`` provenance
token. It groups basket ids and member evidence_ids only; the tokens live on the
composed sentences downstream and are preserved by the UNCHANGED compose path.

Pure: no LLM, no network, stdlib only. Deterministic: sorted outputs, keep-first ties,
no wall-clock or dict-iteration-order dependence (Design 4 acceptance 4).

Every knob reads through the environment at call time (LAW VI). Master kill-switch
``PG_SECTION_BASKET_MAP`` (default OFF => the map is never built or consumed => the
legacy intersection path is byte-identical).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# ── Env knobs (LAW VI; read at call time; defaults reproduce today's absence-of-map) ─────────────
_MASTER_ENV = "PG_SECTION_BASKET_MAP"                 # D1 build + D2 consume master switch
_W_PROVENANCE_ENV = "PG_SECTION_BASKET_MAP_W_PROVENANCE"   # w_p (Design: 3)
_W_SUBQUERY_ENV = "PG_SECTION_BASKET_MAP_W_SUBQUERY"       # w_q (Design: 2)
_W_TOPICAL_ENV = "PG_SECTION_BASKET_MAP_W_TOPICAL"         # w_t (Design: 1)
_TOPICAL_MIN_ENV = "PG_SECTION_BASKET_MAP_TOPICAL_MIN"     # candidate threshold (Design: >=1 shared word)
_RESIDUAL_TITLE_ENV = "PG_SECTION_BASKET_MAP_RESIDUAL_TITLE"

_DEFAULT_W_PROVENANCE = 3
_DEFAULT_W_SUBQUERY = 2
_DEFAULT_W_TOPICAL = 1
_DEFAULT_TOPICAL_MIN = 1
# Reuses ``verified_compose._RESIDUAL_COVERAGE_TITLE`` so the map's residual home and the
# legacy orphan-router residual home carry the SAME section title.
_DEFAULT_RESIDUAL_TITLE = "Additional Corroborated Findings"

_MIN_CONTENT_WORD_LEN = 3
_HEAD_CLAIM_CHARS = 80

# Self-contained content-word tokenizer (kept independent of the generator layer; the
# synthesis layer must not depend backward on generator/). Mirrors the intent of
# verified_compose._repair_content_words: lowercased words >= 3 chars, minus stopwords,
# provenance tokens stripped first.
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
# Fix 6 (2026-07-10, question-agnostic i18n; grounded in — but never tuned to — drb_72): a UNICODE
# word regex so a non-Latin corpus (CJK / Arabic / Cyrillic / Devanagari / Greek …) yields content
# words instead of the empty set the ASCII-only ``[A-Za-z0-9]+`` produced — which killed the topical
# signal and dumped every basket to residual for any non-English research question. ``[^\W_]+`` with
# re.UNICODE matches any run of unicode word characters (letters + digits) minus underscore; paired
# with ``str.casefold`` (not ``.lower``) below it folds case across the widest set of scripts. The
# length / stopword rules still apply (they gate Latin-script connective noise); a non-Latin run
# passes through as a single content token, which is strictly better than zero.
_CONTENT_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "was", "were", "has", "have", "had", "with", "that",
        "this", "from", "into", "onto", "over", "under", "than", "then", "they", "them",
        "their", "there", "which", "while", "what", "when", "where", "who", "whom", "how",
        "its", "our", "your", "his", "her", "not", "but", "can", "will", "would", "could",
        "should", "may", "might", "such", "also", "been", "being", "does", "did", "each",
        "per", "via", "any", "all", "one", "two", "more", "most", "some", "these", "those",
        "about", "between", "across", "within", "toward", "towards", "among",
    }
)


def _flag_on(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() not in ("", "0", "false", "off", "no")


def section_basket_map_enabled() -> bool:
    """Master kill-switch (``PG_SECTION_BASKET_MAP``, default OFF).

    OFF => callers must NOT build or consume the map: the legacy intersection path in
    ``verified_compose._section_baskets_for_compose`` stays byte-identical.
    """
    return _flag_on(_MASTER_ENV)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def resolve_weights() -> dict[str, int]:
    """Assignment-scoring weights (LAW VI env, Design defaults w_p=3 / w_q=2 / w_t=1)."""
    return {
        "provenance": _int_env(_W_PROVENANCE_ENV, _DEFAULT_W_PROVENANCE),
        "subquery": _int_env(_W_SUBQUERY_ENV, _DEFAULT_W_SUBQUERY),
        "topical": _int_env(_W_TOPICAL_ENV, _DEFAULT_W_TOPICAL),
    }


def _topical_min() -> int:
    return _int_env(_TOPICAL_MIN_ENV, _DEFAULT_TOPICAL_MIN)


def _residual_title() -> str:
    raw = os.getenv(_RESIDUAL_TITLE_ENV, "")
    return raw if raw.strip() else _DEFAULT_RESIDUAL_TITLE


# ── Duck-typed accessors (production ClaimBasket/SectionPlan OR fixture dicts both work) ──────────

def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _content_words(text: str) -> set[str]:
    stripped = _EV_TOKEN_RE.sub(" ", text or "")
    # Fix 6: casefold (not lower) so non-Latin scripts fold correctly; length + stopword rules kept.
    return {
        w.casefold()
        for w in _CONTENT_WORD_RE.findall(stripped)
        if len(w) >= _MIN_CONTENT_WORD_LEN and w.casefold() not in _STOPWORDS
    }


def _cluster_id(basket: Any) -> str:
    return str(_get(basket, "claim_cluster_id", "") or "")


def _basket_member_ev_ids(basket: Any) -> list[str]:
    """Evidence_ids of the basket's ``supporting_members`` (order-preserving, deduped).

    Falls back to a plain ``member_ev_ids`` list so a fixture can carry members directly.
    """
    out: list[str] = []
    seen: set[str] = set()
    members = _get(basket, "supporting_members", None)
    if members:
        for m in members:
            eid = str(_get(m, "evidence_id", "") or "")
            if eid and eid not in seen:
                seen.add(eid)
                out.append(eid)
        return out
    for eid in (_get(basket, "member_ev_ids", None) or []):
        s = str(eid or "")
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _basket_words(basket: Any) -> set[str]:
    parts = [
        str(_get(basket, "claim_text", "") or ""),
        str(_get(basket, "subject", "") or ""),
        str(_get(basket, "predicate", "") or ""),
    ]
    return _content_words(" ".join(parts))


def _head_claim(basket: Any) -> str:
    txt = str(_get(basket, "claim_text", "") or _get(basket, "subject", "") or "")
    return txt[:_HEAD_CLAIM_CHARS]


def _section_ev_ids(plan: Any) -> set[str]:
    return {str(x) for x in (_get(plan, "ev_ids", None) or []) if x}


def _section_subquery_indices(plan: Any) -> set[int]:
    out: set[int] = set()
    for q in (_get(plan, "sub_query_indices", None) or []):
        try:
            out.add(int(q))
        except (TypeError, ValueError):
            continue
    return out


def _member_subquery_index(
    ev_id: str,
    evidence_pool: dict[str, Any] | None,
    subquery_to_index: dict[str, int] | None,
) -> set[int]:
    """The sub-query index/indices a member row originated from.

    Uses ``retrieval_subquery`` (preferred, Design 1's formalized field) then
    ``query_origin`` (legacy), mapped against the ``sub_queries`` list. Empty when
    unresolvable (sentinel/label/junk anchors degrade to no sub-query signal).
    """
    if not evidence_pool or not subquery_to_index:
        return set()
    row = evidence_pool.get(ev_id)
    if row is None:
        return set()
    out: set[int] = set()
    for key in ("retrieval_subquery", "query_origin"):
        raw = _get(row, key, None)
        if not raw:
            continue
        idx = subquery_to_index.get(str(raw))
        if idx is not None:
            out.add(idx)
    return out


def _index_evidence_pool(evidence_pool: Any) -> dict[str, Any] | None:
    """evidence_id -> row, for either a list of rows or an already-keyed dict."""
    if evidence_pool is None:
        return None
    if isinstance(evidence_pool, dict):
        return evidence_pool
    keyed: dict[str, Any] = {}
    for row in evidence_pool:
        eid = str(_get(row, "evidence_id", "") or "")
        if eid:
            keyed[eid] = row
    return keyed


# ── Output dataclasses (Design 4 D1) ─────────────────────────────────────────────────────────────

@dataclass
class SectionBasketView:
    """One basket's membership in ONE section, with its role and section-matched facet."""

    claim_cluster_id: str
    role: str                          # "primary" | "corroborating"
    section_member_ev_ids: list[str]   # the members that matched THIS section (the facet)
    match_signals: dict                # {"provenance": n, "subquery": n, "topical": n}

    def to_json_dict(self) -> dict:
        return {
            "claim_cluster_id": self.claim_cluster_id,
            "role": self.role,
            "section_member_ev_ids": list(self.section_member_ev_ids),
            "match_signals": dict(self.match_signals),
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "SectionBasketView":
        """Rebuild a view from its ``to_json_dict`` form (Fix 3 — the missing loader)."""
        return cls(
            claim_cluster_id=str(data.get("claim_cluster_id", "") or ""),
            role=str(data.get("role", "") or ""),
            section_member_ev_ids=[str(x) for x in (data.get("section_member_ev_ids") or [])],
            match_signals=dict(data.get("match_signals") or {}),
        )


@dataclass
class SectionBasketMap:
    """The whole placement. ``stranded_count`` is an INVARIANT: it MUST be 0."""

    views_by_section: dict[int, list[SectionBasketView]]
    primary_section_by_cluster: dict[str, int]
    residual_section_index: int | None
    residual_title: str | None
    stranded_count: int
    assignment_table: list[dict] = field(default_factory=list)
    # Fix 7a — per-signal availability + realized totals, surfaced so a DEAD signal (e.g. the
    # sub-query lineage when the upstream S4 outline carries no sub_query_indices — the known
    # cp4 defect this run exposed) is VISIBLE in every checkpoint instead of a silent hidden zero.
    # ``signals_available`` is a bool per signal; ``signal_totals`` is the summed nonzero count.
    signals_available: dict = field(default_factory=dict)
    signal_totals: dict = field(default_factory=dict)

    def to_json_dict(self) -> dict:
        return {
            "views_by_section": {
                str(idx): [v.to_json_dict() for v in views]
                for idx, views in sorted(self.views_by_section.items())
            },
            "primary_section_by_cluster": dict(sorted(self.primary_section_by_cluster.items())),
            "residual_section_index": self.residual_section_index,
            "residual_title": self.residual_title,
            "stranded_count": self.stranded_count,
            "assignment_table": list(self.assignment_table),
            "signals_available": dict(self.signals_available),
            "signal_totals": dict(self.signal_totals),
        }

    @classmethod
    def from_json_dict(cls, data: dict) -> "SectionBasketMap":
        """Rehydrate a map from its ``to_json_dict`` form (Fix 3 — the loader the checkpoint
        architecture needs). Int-normalizes ``views_by_section`` keys (JSON object keys are always
        strings) and rebuilds the ``SectionBasketView`` objects, so a JSON-round-tripped map is
        byte-for-byte equivalent to the in-memory one the build produced — the seam that consumed
        a rehydrated map used to silently see ZERO views per section (string keys never matched the
        int ``section_index`` lookup)."""
        views_by_section: dict[int, list[SectionBasketView]] = {}
        for raw_idx, raw_views in (data.get("views_by_section") or {}).items():
            idx = int(raw_idx)
            views_by_section[idx] = [
                SectionBasketView.from_json_dict(v) for v in (raw_views or [])
            ]
        primary_section_by_cluster: dict[str, int] = {
            str(k): int(v) for k, v in (data.get("primary_section_by_cluster") or {}).items()
        }
        residual_raw = data.get("residual_section_index", None)
        residual_index = int(residual_raw) if residual_raw is not None else None
        return cls(
            views_by_section=views_by_section,
            primary_section_by_cluster=primary_section_by_cluster,
            residual_section_index=residual_index,
            residual_title=data.get("residual_title", None),
            stranded_count=int(data.get("stranded_count", 0) or 0),
            assignment_table=list(data.get("assignment_table") or []),
            signals_available=dict(data.get("signals_available") or {}),
            signal_totals=dict(data.get("signal_totals") or {}),
        )


def dumps_map(m: SectionBasketMap) -> str:
    """Deterministic JSON bytes (sorted keys) — the checkpoint/harness serialization."""
    return json.dumps(m.to_json_dict(), sort_keys=True, ensure_ascii=False, indent=2)


def load_map(raw: str) -> SectionBasketMap:
    """Fix 3 — inverse of :func:`dumps_map`: parse the deterministic JSON bytes back into a
    :class:`SectionBasketMap`. The build side and this loader are now a matched pair, so a map
    persisted to a checkpoint rehydrates to an equivalent object (round-trip stable)."""
    return SectionBasketMap.from_json_dict(json.loads(raw))


# ── The build (deterministic, three signals, §-1.3 weight-not-filter) ───────────────────────────

def build_section_basket_map(
    baskets: list,
    section_plans: list,
    *,
    evidence_pool: Any = None,
    sub_queries: list | None = None,
    weights: dict[str, int] | None = None,
) -> SectionBasketMap:
    """Group every basket under the outline sections with primary/corroborating roles.

    Deterministic and pure. Nothing is dropped: a basket with no candidate section goes
    primary into ONE appended residual section, so ``stranded_count`` is structurally 0.
    """
    # Fix 5(c): primary selection is now TIERED-LEXICOGRAPHIC, so the flat weighted sum is gone.
    # ``weights`` stays in the signature for API/back-compat (and ``resolve_weights`` for the env
    # contract), but it no longer drives placement — a real provenance/sub-query assignment can
    # never be outweighed by weak lexical matches. Resolved here only to keep the env knobs live.
    _ = weights or resolve_weights()
    topical_min = _topical_min()
    pool = _index_evidence_pool(evidence_pool)
    subquery_to_index: dict[str, int] | None = None
    if sub_queries:
        subquery_to_index = {}
        for i, sq in enumerate(sub_queries):
            key = str(sq or "")
            if key and key not in subquery_to_index:
                subquery_to_index[key] = i

    n_sections = len(section_plans)
    sec_ev_ids = [_section_ev_ids(p) for p in section_plans]
    sec_subq = [_section_subquery_indices(p) for p in section_plans]
    sec_words = [_content_words(f"{_get(p, 'title', '') or ''} {_get(p, 'focus', '') or ''}")
                 for p in section_plans]

    # Fix 5(a) — structural cross-section IDF. A content word that appears in >=2 sections cannot
    # tell those sections apart, so it is NON-discriminative and is removed from every section's
    # topical match set. This is pure document-frequency over the outline word-sets: no hardcoded
    # word list, no question-specific constant, no threshold tuned to this corpus. A clinical drug
    # outline or an economics outline is filtered by exactly the same rule at runtime.
    _section_df: dict[str, int] = {}
    for _ws in sec_words:
        for _word in _ws:
            _section_df[_word] = _section_df.get(_word, 0) + 1
    sec_disc_words = [{word for word in ws if _section_df.get(word, 0) < 2} for ws in sec_words]

    views_by_section: dict[int, list[SectionBasketView]] = {}
    primary_section_by_cluster: dict[str, int] = {}
    assignment_table: list[dict] = []
    residual_index: int | None = None
    # Fix 7a — realized per-signal totals so a DEAD signal is visible, never a hidden zero.
    signal_totals: dict[str, int] = {"provenance": 0, "subquery": 0, "topical": 0}

    for pos, basket in enumerate(baskets):
        raw_cid = _cluster_id(basket)
        if raw_cid:
            cid = raw_cid
        else:
            # Fix 4: an empty-cid basket must NOT silently vanish (the old ``continue`` dropped it
            # while ``stranded_count`` still read 0). Give it a deterministic synthetic id and let it
            # flow to a home, so it is COUNTED and disclosed, never discarded.
            cid = f"__nocid__#{pos}"
        # Fix 4: a DUPLICATE cid must NOT overwrite an earlier distinct basket (the old
        # ``primary_section_by_cluster[cid] = ...`` collapsed two baskets into one map row while
        # ``stranded_count`` still read 0). Uniquify the MAP KEY deterministically; the VIEW keeps
        # the original ``cid`` for the downstream basket lookup, and the loud mismatch check in the
        # compose seam surfaces any genuine cid collision.
        map_key = cid
        if map_key in primary_section_by_cluster:
            map_key = f"{cid}#{pos}"
        member_ids = set(_basket_member_ev_ids(basket))
        b_words = _basket_words(basket)
        member_subq = {ev: _member_subquery_index(ev, pool, subquery_to_index) for ev in member_ids}

        candidates: dict[int, dict[str, int]] = {}
        for idx in range(n_sections):
            prov = len(member_ids & sec_ev_ids[idx])
            plan_subq = sec_subq[idx]
            subq = sum(1 for ev in member_ids if member_subq[ev] & plan_subq) if plan_subq else 0
            # Fix 5(b): topical = count of DISCRIMINATIVE shared words (non-discriminative words
            # removed above), so 84%-single-generic-word placements can no longer accrue.
            top = len(b_words & sec_disc_words[idx])
            if prov > 0 or subq > 0 or top >= topical_min:
                candidates[idx] = {"provenance": prov, "subquery": subq, "topical": top}

        if candidates:
            # Fix 5(c) — TIERED-LEXICOGRAPHIC primary selection (provenance, then sub-query, then
            # discriminative topical, then lowest section index) REPLACES the flat weighted sum. A
            # single real provenance (or sub-query) assignment can never be outvoted by an
            # accumulation of weak lexical matches — the flat-sum bug that produced the measured
            # 84%-single-word placements and the ev_1041 'future' leak. Structural + question-
            # agnostic; the env weights are retained only for the diagnostic assignment_table.
            def _rank(i: int, _c: dict[int, dict[str, int]] = candidates) -> tuple[int, int, int, int]:
                s = _c[i]
                return (-s["provenance"], -s["subquery"], -s["topical"], i)

            primary_idx = min(candidates, key=_rank)
            corroborating = sorted(i for i in candidates if i != primary_idx)
        else:
            # No candidate section: keep-all residual home (Design 4 D1 step 4).
            if residual_index is None:
                residual_index = n_sections
            primary_idx = residual_index
            corroborating = []

        primary_section_by_cluster[map_key] = primary_idx

        # Primary view.
        if primary_idx < n_sections:
            primary_facet = sorted(member_ids & sec_ev_ids[primary_idx])
            if not primary_facet:
                # Fix 9: a topical/sub-query-only primary (no member ev_id in the section) carries
                # the basket's FULL member list as its facet — uniform with the residual branch
                # below and with the rule the corroborating branch uses to decide emission — so a
                # primary home is never an empty-facet placeholder.
                primary_facet = sorted(member_ids)
            primary_signals = candidates[primary_idx]
        else:
            # Residual: the basket's full member set is its facet; signals are all zero.
            primary_facet = sorted(member_ids)
            primary_signals = {"provenance": 0, "subquery": 0, "topical": 0}
        views_by_section.setdefault(primary_idx, []).append(
            SectionBasketView(cid, "primary", primary_facet, primary_signals)
        )
        for _k in signal_totals:
            signal_totals[_k] += int(primary_signals.get(_k, 0))

        # Corroborating views: only where the section-matched facet is non-empty (there is
        # something to cite there). A candidate matched purely by topical/sub-query overlap
        # with no member ev_id in the section carries no groundable facet, so it emits no
        # corroborating view (nothing for strict_verify to ground).
        corroborating_emitted: list[int] = []
        for idx in corroborating:
            facet = sorted(member_ids & sec_ev_ids[idx])
            if not facet:
                continue
            views_by_section.setdefault(idx, []).append(
                SectionBasketView(cid, "corroborating", facet, candidates[idx])
            )
            corroborating_emitted.append(idx)
            for _k in signal_totals:
                signal_totals[_k] += int(candidates[idx].get(_k, 0))

        assignment_table.append(
            {
                "claim_cluster_id": cid,
                "head_claim": _head_claim(basket),
                "primary_section": primary_idx,
                "corroborating_sections": corroborating_emitted,
                "signals": primary_signals,
                "member_count": len(member_ids),
                "corroboration_count": int(_get(basket, "corroboration_count", 0) or 0),
            }
        )

    # Determinism: sort views within each section by cluster id, then role
    # (primary before corroborating) so byte output is input-order-independent.
    for idx in views_by_section:
        views_by_section[idx].sort(key=lambda v: (v.claim_cluster_id, v.role))
    # (cid, primary_section, member_count) keeps the table deterministic even if two baskets share
    # a cid (Fix 4 edge case); for the healthy unique-cid case this sorts identically to cid alone.
    assignment_table.sort(key=lambda r: (r["claim_cluster_id"], r["primary_section"], r["member_count"]))

    # Fix 4 — honest stranded count: INPUT baskets minus baskets that produced a (unique) map entry.
    # Every basket now yields exactly one entry, so this is structurally 0; if a future path ever
    # skips a basket it is caught here instead of masked by a duplicate/empty-cid collapse.
    stranded = len(baskets) - len(primary_section_by_cluster)

    # Fix 7a — per-signal availability. ``subquery`` is structurally unavailable when the caller
    # passes no ``sub_queries`` (the wiring gap) even before any count; the upstream cp4 outline
    # carrying ``sub_query_indices=None`` is a SEPARATE S4 defect that MUST be filed as an S4
    # follow-on, never absorbed silently into S5 — surfacing it here (LOUD log + serialized stat)
    # is how S5 refuses to hide it.
    subquery_wired = subquery_to_index is not None
    signals_available = {
        "provenance": signal_totals["provenance"] > 0,
        "subquery": bool(subquery_wired and signal_totals["subquery"] > 0),
        "topical": signal_totals["topical"] > 0,
    }
    for _sig, _ok in signals_available.items():
        if not _ok:
            logger.warning(
                "[section_basket_map] signal '%s' is DEAD (available=False, total=%d, wired=%s) — "
                "placement fell back to the remaining signals; a dead sub-query signal is the "
                "upstream S4 outline defect (file as an S4 follow-on, do not absorb into S5).",
                _sig, signal_totals.get(_sig, 0),
                subquery_wired if _sig == "subquery" else True,
            )

    return SectionBasketMap(
        views_by_section=views_by_section,
        primary_section_by_cluster=primary_section_by_cluster,
        residual_section_index=residual_index,
        residual_title=_residual_title() if residual_index is not None else None,
        stranded_count=stranded,
        assignment_table=assignment_table,
        signals_available=signals_available,
        signal_totals=dict(signal_totals),
    )
