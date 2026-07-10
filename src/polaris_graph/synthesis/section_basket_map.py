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
targets no number (CLAUDE.md §-1.3 WEIGHT-and-CONSOLIDATE).

This module makes NO faithfulness decision itself (placement + role tagging only). The
faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is
UNFROZEN as of 2026-07-10 and is tuned elsewhere; this module neither enforces nor
relaxes it. The map only decides WHICH baskets a section's writer is submitted and in
what role -- the same class of decision the intersection bridge already makes today,
made complete and deterministic. (Pre-2026-07-10 this docstring called the engine
"never touched / untouchable"; that framing is retired with the UNFREEZE -- the engine
is simply not this module's concern.)

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

import hashlib
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
_CONTENT_WORD_RE = re.compile(r"[A-Za-z0-9]+")
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
    return {
        w.lower()
        for w in _CONTENT_WORD_RE.findall(stripped)
        if len(w) >= _MIN_CONTENT_WORD_LEN and w.lower() not in _STOPWORDS
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


def _synth_cid(basket: Any) -> str:
    """Fix 12: a DETERMINISTIC synthesized cluster id for a basket that arrives with an
    empty ``claim_cluster_id``. Hashes the basket's member ev_ids (sorted) + its head
    claim so the SAME cid-less basket always maps to the SAME id across builds -- never a
    silent DROP (§-1.3 consolidate-keep-all), never a wall-clock/order dependence."""
    member_ids = _basket_member_ev_ids(basket)
    claim = str(_get(basket, "claim_text", "") or _get(basket, "subject", "") or "")
    seed = "|".join(sorted(member_ids)) + "||" + claim
    return "synthcid_" + hashlib.blake2b(seed.encode("utf-8"), digest_size=8).hexdigest()


def _stable_tiebreak(cid: str, idx: int) -> str:
    """Fix 14: a NEUTRAL deterministic tie-break key (stable hash of cid+section idx).
    Replaces the old ``(-weighted, i)`` key whose second element was the LOWEST section
    index -- a systematic bias toward section 0 (e.g. 'Positive Views' first on a
    controversy question). blake2b is process-independent (unlike salted ``hash()``)."""
    return hashlib.blake2b(f"{cid}::{idx}".encode("utf-8"), digest_size=8).hexdigest()


def _nli_confirm_placement(
    nli_placement_judge: Any,
    basket: Any,
    candidates: dict[int, dict[str, int]],
    section_plans: list,
) -> int | None:
    """Fix 6 seam: when a LIVE NLI/topic judge is supplied, ask it to CONFIRM a
    real-section home for a basket that has ONLY topical candidates (prov=0 AND subq=0).

    FAIL-OPEN by contract: any exception, a missing judge, or an unconfirmed verdict
    returns ``None`` so the basket routes to the keep-all residual -- the judge can only
    PROMOTE a topical-only basket into a real section, NEVER force one, NEVER drop one.
    The judge is any callable ``judge(claim_text, section_title) -> truthy``.
    """
    if nli_placement_judge is None:
        return None
    try:
        claim = str(_get(basket, "claim_text", "") or _get(basket, "subject", "") or "")
        if not claim:
            return None
        for idx in sorted(candidates):
            title = str(_get(section_plans[idx], "title", "") or "")
            if nli_placement_judge(claim, title):
                return idx
    except Exception:  # noqa: BLE001 — fail-open to residual (never force a real-section home)
        return None
    return None


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
    def from_json_dict(cls, d: dict) -> "SectionBasketView":
        """Fix 8: rebuild a view from its JSON form (resume/harness load)."""
        return cls(
            claim_cluster_id=str(d.get("claim_cluster_id", "") or ""),
            role=str(d.get("role", "primary") or "primary"),
            section_member_ev_ids=list(d.get("section_member_ev_ids", []) or []),
            match_signals=dict(d.get("match_signals", {}) or {}),
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
    # Fix 7/17: which signals were actually LIVE this build + honest placement counts,
    # so a dead signal (e.g. sub-query lineage) is DISCLOSED, never silent.
    stats: dict = field(default_factory=dict)

    def to_json_dict(self) -> dict:
        return {
            "views_by_section": {
                str(idx): [v.to_json_dict() for v in views]
                for idx, views in sorted(self.views_by_section.items(), key=lambda kv: str(kv[0]))
            },
            "primary_section_by_cluster": dict(sorted(self.primary_section_by_cluster.items())),
            "residual_section_index": self.residual_section_index,
            "residual_title": self.residual_title,
            "stranded_count": self.stranded_count,
            "assignment_table": list(self.assignment_table),
            "stats": dict(self.stats),
        }

    @classmethod
    def from_json_dict(cls, d: dict) -> "SectionBasketMap":
        """Fix 8: RESUME loader. Restores INT section keys + ``SectionBasketView`` objects
        from the cp5-JSON serialization (which carries STRING keys + plain dicts). Without
        this, a JSON-loaded map yields str keys + dict views and the compose seam finds
        ZERO baskets for every section SILENTLY."""
        raw_views = d.get("views_by_section", {}) or {}
        views_by_section: dict[int, list[SectionBasketView]] = {}
        for k, vlist in raw_views.items():
            try:
                ik: Any = int(k)
            except (TypeError, ValueError):
                ik = k  # tolerate a non-int key rather than drop the whole section
            views_by_section[ik] = [
                SectionBasketView.from_json_dict(v) for v in (vlist or [])
            ]
        prim_raw = d.get("primary_section_by_cluster", {}) or {}
        primary_section_by_cluster: dict[str, int] = {}
        for cid, sidx in prim_raw.items():
            try:
                primary_section_by_cluster[str(cid)] = int(sidx)
            except (TypeError, ValueError):
                primary_section_by_cluster[str(cid)] = sidx
        return cls(
            views_by_section=views_by_section,
            primary_section_by_cluster=primary_section_by_cluster,
            residual_section_index=d.get("residual_section_index"),
            residual_title=d.get("residual_title"),
            stranded_count=int(d.get("stranded_count", 0) or 0),
            assignment_table=list(d.get("assignment_table", []) or []),
            stats=dict(d.get("stats", {}) or {}),
        )


def dumps_map(m: SectionBasketMap) -> str:
    """Deterministic JSON bytes (sorted keys) — the checkpoint/harness serialization."""
    return json.dumps(m.to_json_dict(), sort_keys=True, ensure_ascii=False, indent=2)


def load_map(payload: dict | str) -> SectionBasketMap:
    """Fix 8: parse a serialized map (dict or JSON string) back to a live object."""
    if isinstance(payload, str):
        payload = json.loads(payload)
    return SectionBasketMap.from_json_dict(payload)


# ── The build (deterministic, three signals, §-1.3 weight-not-filter) ───────────────────────────

def build_section_basket_map(
    baskets: list,
    section_plans: list,
    *,
    evidence_pool: Any = None,
    sub_queries: list | None = None,
    weights: dict[str, int] | None = None,
    nli_placement_judge: Any = None,
) -> SectionBasketMap:
    """Group every basket under the outline sections with primary/corroborating roles.

    Deterministic and pure. Nothing is dropped: a basket with no GROUNDED candidate
    section goes primary into ONE appended residual section, so ``stranded_count`` is
    structurally 0 (Fix 12/13: a cid-less basket gets a synthesized deterministic cid and
    is placed + counted like any other).

    Fix 6 (2026-07-10): a real-section PRIMARY requires a GROUNDED signal -- a shared
    provenance ev_id OR a shared sub-query origin. A topical-only match (one generic
    shared word, prov=0 AND subq=0) is NOT sufficient to home a basket into a real
    controversy section while the D4 NLI refine is inert (measured: 86% of real-section
    primaries had provenance=0 and an EMPTY facet). Such baskets route to the keep-all
    residual (zero drops, §-1.3). When ``nli_placement_judge`` is supplied it MAY confirm
    a real-section home; it FAILS OPEN to residual and never forces a real-section home.
    """
    w = weights or resolve_weights()
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

    # Fix 7/17: DISCLOSE which signals were actually live this build. The sub-query signal
    # is DEAD unless cp4 plans carry sub_query_indices AND the caller threaded both an
    # evidence_pool and sub_queries -- surface that, never let a dead signal stay silent.
    any_plan_subq = any(bool(s) for s in sec_subq)
    signals_available = {
        "provenance": True,  # always computable (member ev_ids ∩ section ev_ids)
        "subquery": bool(subquery_to_index) and bool(pool) and any_plan_subq,
        "topical": True,
    }

    views_by_section: dict[int, list[SectionBasketView]] = {}
    primary_section_by_cluster: dict[str, int] = {}
    assignment_table: list[dict] = []
    residual_index: int | None = None
    topical_only_to_residual = 0
    synthesized_cids = 0

    for basket in baskets:
        cid = _cluster_id(basket)
        if not cid:
            # Fix 12: never silently DROP a cid-less basket (§-1.3 consolidate-keep-all).
            # Synthesize a DETERMINISTIC cid so it is placed + counted like any other.
            cid = _synth_cid(basket)
            synthesized_cids += 1
        member_ids = set(_basket_member_ev_ids(basket))
        b_words = _basket_words(basket)
        member_subq = {ev: _member_subquery_index(ev, pool, subquery_to_index) for ev in member_ids}

        candidates: dict[int, dict[str, int]] = {}
        grounded: list[int] = []
        for idx in range(n_sections):
            prov = len(member_ids & sec_ev_ids[idx])
            plan_subq = sec_subq[idx]
            subq = sum(1 for ev in member_ids if member_subq[ev] & plan_subq) if plan_subq else 0
            top = len(b_words & sec_words[idx])
            if prov > 0 or subq > 0 or top >= topical_min:
                candidates[idx] = {"provenance": prov, "subquery": subq, "topical": top}
                if prov > 0 or subq > 0:
                    grounded.append(idx)

        # Fix 6: a real-section PRIMARY must be GROUNDED (prov>0 OR subq>0). A topical-only
        # candidate cannot home a real section while D4 NLI is inert -> route to residual.
        placement = grounded
        if not placement and candidates and nli_placement_judge is not None:
            confirmed = _nli_confirm_placement(nli_placement_judge, basket, candidates, section_plans)
            if confirmed is not None:
                placement = [confirmed]

        if placement:
            def _score(i: int, _cid: str = cid) -> tuple[int, str]:
                s = candidates[i]
                weighted = (
                    w["provenance"] * s["provenance"]
                    + w["subquery"] * s["subquery"]
                    + w["topical"] * s["topical"]
                )
                # Fix 14: neutral deterministic tie-break, NOT the lowest section index.
                return (-weighted, _stable_tiebreak(_cid, i))

            primary_idx = min(placement, key=_score)
            corroborating = sorted(i for i in candidates if i != primary_idx)
        else:
            # No GROUNDED candidate (topical-only or none): keep-all residual home.
            if candidates:
                topical_only_to_residual += 1
            if residual_index is None:
                residual_index = n_sections
            primary_idx = residual_index
            corroborating = []

        primary_section_by_cluster[cid] = primary_idx

        # Primary view.
        if primary_idx < n_sections:
            primary_facet = sorted(member_ids & sec_ev_ids[primary_idx])
            primary_signals = candidates[primary_idx]
        else:
            # Residual: the basket's full member set is its facet; signals are all zero.
            primary_facet = sorted(member_ids)
            primary_signals = {"provenance": 0, "subquery": 0, "topical": 0}
        views_by_section.setdefault(primary_idx, []).append(
            SectionBasketView(cid, "primary", primary_facet, primary_signals)
        )

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

    # Determinism: sort views within each section by cluster id, then role. Fix 16: sort
    # PRIMARY before CORROBORATING by an explicit role RANK (0 before 1) -- lexically
    # 'corroborating' < 'primary' would otherwise put corroborating first.
    for idx in views_by_section:
        views_by_section[idx].sort(
            key=lambda v: (v.claim_cluster_id, 0 if v.role == "primary" else 1)
        )
    assignment_table.sort(key=lambda r: r["claim_cluster_id"])

    # Fix 13: HONEST stranded count. Compare EVERY input basket (including cid-less rows,
    # via their synthesized cid) against the placed set -- NOT the self-referential
    # ``primary_section_by_cluster`` the loop just filled (which excluded cid-less rows).
    placed = set(primary_section_by_cluster)
    stranded = 0
    for b in baskets:
        bcid = _cluster_id(b) or _synth_cid(b)
        if bcid not in placed:
            stranded += 1

    stats = {
        "signals_available": signals_available,
        "n_baskets_in": len(baskets),
        "n_placed": len(primary_section_by_cluster),
        "synthesized_cids": synthesized_cids,
        "topical_only_to_residual": topical_only_to_residual,
        "residual_used": residual_index is not None,
        "stranded_count": stranded,
    }
    # Fix 17: FAIL-LOUD envelope invariant. stranded MUST be 0 by construction (every
    # basket, incl. cid-less, is placed). If it is not, a basket lost its home -- surface
    # it LOUDLY (never a silent stranded_count==0-on-paper while baskets vanish).
    if stranded != 0:
        logger.error(
            "[section_basket_map] INVARIANT VIOLATION: stranded_count=%d (expected 0) — "
            "%d input baskets, %d placed. A basket lost its home; this is a bug.",
            stranded, len(baskets), len(primary_section_by_cluster),
        )

    return SectionBasketMap(
        views_by_section=views_by_section,
        primary_section_by_cluster=primary_section_by_cluster,
        residual_section_index=residual_index,
        residual_title=_residual_title() if residual_index is not None else None,
        stranded_count=stranded,
        assignment_table=assignment_table,
        stats=stats,
    )
