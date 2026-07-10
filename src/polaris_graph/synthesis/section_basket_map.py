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
map only decides WHICH baskets a section's writer is submitted and in what role.

SELECTION IS TIERED-LEXICOGRAPHIC (fix 5c, operator 2026-07-10), NOT a flat weighted
sum: primary = the candidate with the highest (provenance, then sub-query, then
DISCRIMINATIVE topical, then full-topical, then LOWEST index). A real provenance /
sub-query assignment can therefore never be outvoted by an accumulation of weak lexical
matches, and the env weights no longer flip a placement. This is the fix for the
"84% single-shared-word" leak that dumped every generic-word basket into section 0.

Provenance-token neutrality (operator 2026-07-10): this module never reads or mutates
sentence text or the ``[#ev:<id>:<start>-<end>]`` provenance token. It groups basket ids
and member evidence_ids only; the tokens live on the composed sentences downstream.

Pure: no LLM, no network, stdlib only (the fix 15 NLI refine is OPTIONAL, default-OFF).
Deterministic: sorted outputs, keep-first ties, no wall-clock or dict-iteration-order
dependence. Every knob reads through the environment at call time (LAW VI). Master
kill-switch ``PG_SECTION_BASKET_MAP`` (default OFF => the map is never built or consumed
=> the legacy intersection path is byte-identical).
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

# ── Env knobs (LAW VI; read at call time; defaults reproduce today's absence-of-map) ─────────────
_MASTER_ENV = "PG_SECTION_BASKET_MAP"                 # D1 build + D2 consume master switch
_W_PROVENANCE_ENV = "PG_SECTION_BASKET_MAP_W_PROVENANCE"   # w_p (legacy weights; NO LONGER flip placement)
_W_SUBQUERY_ENV = "PG_SECTION_BASKET_MAP_W_SUBQUERY"       # w_q
_W_TOPICAL_ENV = "PG_SECTION_BASKET_MAP_W_TOPICAL"         # w_t
_TOPICAL_MIN_ENV = "PG_SECTION_BASKET_MAP_TOPICAL_MIN"     # candidate threshold (Design: >=1 shared word)
_RESIDUAL_TITLE_ENV = "PG_SECTION_BASKET_MAP_RESIDUAL_TITLE"
# fix 15 (operator 2026-07-10): the D4 NLI refine pass. Default-OFF => the map stays PURE (stdlib,
# no LLM, byte-identical). When ON AND an ``entails_fn`` is threaded (the resident directional
# cross-encoder), a TOPICAL-ONLY candidate section (no provenance, no sub-query member) must ALSO
# have its section head ENTAIL the basket claim to remain a candidate — so a polarity-mismatched
# distinctive word ('Displacement or Augmentation?' vs an augmentation-positive basket) no longer
# mis-homes the basket. Provenance/sub-query candidates are NEVER NLI-gated (they are grounded).
_REFINE_NLI_ENV = "PG_SECTION_BASKET_MAP_REFINE_NLI"

_DEFAULT_W_PROVENANCE = 3
_DEFAULT_W_SUBQUERY = 2
_DEFAULT_W_TOPICAL = 1
_DEFAULT_TOPICAL_MIN = 1
# Reuses ``verified_compose._RESIDUAL_COVERAGE_TITLE`` so the map's residual home and the
# legacy orphan-router residual home carry the SAME section title.
_DEFAULT_RESIDUAL_TITLE = "Additional Corroborated Findings"

_MIN_CONTENT_WORD_LEN = 3
_HEAD_CLAIM_CHARS = 80

# fix 6 (operator 2026-07-10): UNICODE-aware content-word tokenizer. The prior ``[A-Za-z0-9]+``
# regex matched ZERO words on a non-Latin research question (Cyrillic / Greek / CJK-with-spaces),
# so the topical signal silently died and EVERY basket fell to residual. ``\w`` (re.UNICODE, the
# Python 3 default) matches unicode letters/digits; underscores are excluded via the char class.
_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")
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


def refine_nli_enabled() -> bool:
    """fix 15: True iff the optional D4 NLI refine of TOPICAL-ONLY candidates is armed
    (``PG_SECTION_BASKET_MAP_REFINE_NLI``, default OFF => the pure stdlib placement)."""
    return _flag_on(_REFINE_NLI_ENV)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    if not raw.strip():
        return default
    try:
        return int(raw.strip())
    except (TypeError, ValueError):
        return default


def resolve_weights() -> dict[str, int]:
    """LEGACY assignment-scoring weights (LAW VI env). Retained for API compatibility and the
    ``weights`` build param, but selection is now TIERED-LEXICOGRAPHIC (fix 5c) so these NO LONGER
    flip a placement — a topical weight can never outvote a provenance/sub-query tier."""
    return {
        "provenance": _int_env(_W_PROVENANCE_ENV, _DEFAULT_W_PROVENANCE),
        "subquery": _int_env(_W_SUBQUERY_ENV, _DEFAULT_W_SUBQUERY),
        "topical": _int_env(_W_TOPICAL_ENV, _DEFAULT_W_TOPICAL),
    }


def _topical_min() -> int:
    # fix 17 (operator 2026-07-10): CLAMP the effective topical_min to >= 1. At 0 the candidate
    # test ``top >= topical_min`` is ALWAYS true, so EVERY section is a candidate for EVERY basket
    # and the lowest-index tie-break dumps all of them into section 0 (residual never fires).
    return max(1, _int_env(_TOPICAL_MIN_ENV, _DEFAULT_TOPICAL_MIN))


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

    Uses ``retrieval_subquery`` (preferred) then ``query_origin`` (legacy), mapped against the
    ``sub_queries`` list. Empty when unresolvable (sentinel/label/junk anchors -> no signal).
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
        return cls(
            claim_cluster_id=str(d.get("claim_cluster_id", "")),
            role=str(d.get("role", "")),
            section_member_ev_ids=list(d.get("section_member_ev_ids", []) or []),
            match_signals=dict(d.get("match_signals", {}) or {}),
        )


@dataclass
class SectionBasketMap:
    """The whole placement. ``stranded_count`` is an INVARIANT: it MUST be 0.

    ``nocid_synthetic_count`` (fix 4/16, operator 2026-07-10) is the DISCLOSED count of baskets that
    arrived without a ``claim_cluster_id`` and were kept under a synthetic deterministic id instead
    of being silently dropped. ``signals_available`` (fix 7a) surfaces which of the three placement
    signals could STRUCTURALLY fire this run (never a hidden zero); ``signal_totals`` is the realized
    per-signal match total across primary homes.
    """

    views_by_section: dict[int, list[SectionBasketView]]
    primary_section_by_cluster: dict[str, int]
    residual_section_index: int | None
    residual_title: str | None
    stranded_count: int
    assignment_table: list[dict] = field(default_factory=list)
    nocid_synthetic_count: int = 0
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
            "nocid_synthetic_count": self.nocid_synthetic_count,
            "signals_available": dict(sorted(self.signals_available.items())),
            "signal_totals": dict(sorted(self.signal_totals.items())),
            "assignment_table": list(self.assignment_table),
        }


def dumps_map(m: SectionBasketMap) -> str:
    """Deterministic JSON bytes (sorted keys) — the checkpoint/harness serialization."""
    return json.dumps(m.to_json_dict(), sort_keys=True, ensure_ascii=False, indent=2)


def load_map(raw: str) -> SectionBasketMap:
    """fix 3 (operator 2026-07-10): rehydrate a ``dumps_map`` JSON string back to a SectionBasketMap
    with INT section keys and rebuilt ``SectionBasketView`` objects. The compose seam consumed a
    checkpoint-rehydrated map that (as a raw dict with str keys) resolved to ZERO views; this makes a
    round-tripped map byte-for-byte equal to the in-memory one (``dumps_map(load_map(raw)) == raw``)."""
    d = json.loads(raw)
    views_by_section: dict[int, list[SectionBasketView]] = {}
    for k, views in (d.get("views_by_section", {}) or {}).items():
        views_by_section[int(k)] = [SectionBasketView.from_json_dict(v) for v in (views or [])]
    return SectionBasketMap(
        views_by_section=views_by_section,
        primary_section_by_cluster={str(k): int(v) for k, v in (d.get("primary_section_by_cluster", {}) or {}).items()},
        residual_section_index=d.get("residual_section_index"),
        residual_title=d.get("residual_title"),
        stranded_count=int(d.get("stranded_count", 0) or 0),
        assignment_table=list(d.get("assignment_table", []) or []),
        nocid_synthetic_count=int(d.get("nocid_synthetic_count", 0) or 0),
        signals_available=dict(d.get("signals_available", {}) or {}),
        signal_totals=dict(d.get("signal_totals", {}) or {}),
    )


# ── The build (deterministic, tiered signals, §-1.3 weight-not-filter) ───────────────────────────

def build_section_basket_map(
    baskets: list,
    section_plans: list,
    *,
    evidence_pool: Any = None,
    sub_queries: list | None = None,
    weights: dict[str, int] | None = None,
    entails_fn: Any = None,
) -> SectionBasketMap:
    """Group every basket under the outline sections with primary/corroborating roles.

    Deterministic and pure. Nothing is dropped: a basket with no candidate section goes primary into
    ONE appended residual section, so ``stranded_count`` is structurally 0. A basket without a
    ``claim_cluster_id`` is kept under a synthetic deterministic id (fix 4/16), and two DISTINCT
    baskets that share a cluster id are disambiguated (never collapsed) so no basket vanishes.
    """
    w = weights or resolve_weights()  # retained for API compat; tiered selection ignores magnitudes
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
    # fix 14 (NOISE SINK, operator 2026-07-10): the topical signal keys on section-DISTINCTIVE words,
    # not the raw title+focus bag. A word shared by >=2 sections (the corpus-wide "employment" /
    # "impact" every section title carries) matches ALL sections, so a single generic word made every
    # basket a candidate everywhere and the lowest-index tie-break dumped the lot into section 0.
    # Subtract any word appearing in >=2 sections' word sets for the DISCRIMINATIVE topical signal;
    # keep the full-set overlap only as a secondary tie signal.
    _word_doc_freq: dict[str, int] = {}
    for _sw in sec_words:
        for _wd in _sw:
            _word_doc_freq[_wd] = _word_doc_freq.get(_wd, 0) + 1
    sec_words_distinctive = [{x for x in sw if _word_doc_freq.get(x, 0) < 2} for sw in sec_words]

    # fix 7a (operator 2026-07-10): which signals could STRUCTURALLY fire this run (never a hidden 0).
    signals_available = {
        "provenance": any(len(s) > 0 for s in sec_ev_ids),
        "subquery": bool(subquery_to_index) and any(len(s) > 0 for s in sec_subq),
        "topical": any(len(s) > 0 for s in sec_words),
    }
    signal_totals = {"provenance": 0, "subquery": 0, "topical": 0}

    # fix 15: the optional NLI refine, armed only when the flag is ON AND a judge is threaded.
    _nli_gate = entails_fn if (entails_fn is not None and refine_nli_enabled()) else None
    sec_texts = ([f"{_get(p, 'title', '') or ''}. {_get(p, 'focus', '') or ''}".strip()
                  for p in section_plans] if _nli_gate is not None else None)

    def _topical_only_survives_nli(sec_idx: int, claim: str) -> bool:
        if _nli_gate is None or not claim.strip():
            return True
        try:
            verdict = _nli_gate(sec_texts[sec_idx], claim)   # premise=section head, hypothesis=claim
        except Exception:
            return True
        return verdict is not False   # True or None(degrade) => keep (never lexical-regress)

    views_by_section: dict[int, list[SectionBasketView]] = {}
    primary_section_by_cluster: dict[str, int] = {}
    assignment_table: list[dict] = []
    residual_index: int | None = None
    nocid_synthetic_count = 0
    _seen_keys: set[str] = set()

    for _b_index, basket in enumerate(baskets):
        raw_cid = _cluster_id(basket)
        if not raw_cid:
            # fix 4/16: a cid-less basket was silently dropped (stranded read 0). Keep it under a
            # synthetic DETERMINISTIC id and DISCLOSE the count (fail-loud). §-1.3 CONSOLIDATE.
            key = f"__nocid__#{_b_index}"
            nocid_synthetic_count += 1
        else:
            key = raw_cid
            # fix 4: two DISTINCT baskets sharing a cluster id must NOT collapse (the old build
            # overwrote one, stranded read 0). Disambiguate the SECOND+ occurrence deterministically.
            if key in _seen_keys:
                suffix = 2
                while f"{raw_cid}#{suffix}" in _seen_keys:
                    suffix += 1
                key = f"{raw_cid}#{suffix}"
        _seen_keys.add(key)

        member_ids = set(_basket_member_ev_ids(basket))
        b_words = _basket_words(basket)
        member_subq = {ev: _member_subquery_index(ev, pool, subquery_to_index) for ev in member_ids}

        candidates: dict[int, dict[str, int]] = {}
        for idx in range(n_sections):
            prov = len(member_ids & sec_ev_ids[idx])
            plan_subq = sec_subq[idx]
            subq = sum(1 for ev in member_ids if member_subq[ev] & plan_subq) if plan_subq else 0
            disc_top = len(b_words & sec_words_distinctive[idx])   # discriminative candidate signal
            full_top = len(b_words & sec_words[idx])               # full-set secondary tie signal
            grounded = prov > 0 or subq > 0
            if grounded or disc_top >= topical_min:
                # fix 15: a TOPICAL-ONLY candidate must also survive the NLI head-entails-claim refine
                # when armed; a grounded (provenance/sub-query) candidate is never NLI-gated.
                if not grounded and not _topical_only_survives_nli(idx, _head_claim(basket)):
                    continue
                candidates[idx] = {
                    "provenance": prov, "subquery": subq, "topical": disc_top, "topical_full": full_top,
                }

        if candidates:
            # fix 5c: TIERED-LEXICOGRAPHIC — provenance, then sub-query, then discriminative topical,
            # then full-set topical, then LOWEST index. Weights NEVER flip a tier (a topical weight
            # cannot outvote a provenance/sub-query match). Deterministic keep-first.
            def _rank(i: int, _c: dict = candidates) -> tuple:
                s = _c[i]
                return (-s["provenance"], -s["subquery"], -s["topical"], -s["topical_full"], i)

            primary_idx = min(candidates, key=_rank)
            corroborating = sorted(i for i in candidates if i != primary_idx)
        else:
            # No candidate section: keep-all residual home (Design 4 D1 step 4).
            if residual_index is None:
                residual_index = n_sections
            primary_idx = residual_index
            corroborating = []

        primary_section_by_cluster[key] = primary_idx

        # Primary view.
        if primary_idx < n_sections:
            primary_facet = sorted(member_ids & sec_ev_ids[primary_idx])
            # fix 9: a TOPICAL-ONLY primary (matched by title/sub-query, no member ev_id in the
            # section) carries the basket's WHOLE member set — uniform with the residual branch, never
            # an empty facet (empty-facet primary semantics: cite from the whole member set).
            if not primary_facet:
                primary_facet = sorted(member_ids)
            _c = candidates[primary_idx]
            primary_signals = {"provenance": _c["provenance"], "subquery": _c["subquery"], "topical": _c["topical"]}
        else:
            # Residual: the basket's full member set is its facet; signals are all zero.
            primary_facet = sorted(member_ids)
            primary_signals = {"provenance": 0, "subquery": 0, "topical": 0}
        for _sig in ("provenance", "subquery", "topical"):
            signal_totals[_sig] += int(primary_signals[_sig])
        views_by_section.setdefault(primary_idx, []).append(
            SectionBasketView(key, "primary", primary_facet, primary_signals)
        )

        # Corroborating views: only where the section-matched facet is non-empty (there is something
        # to cite there). A candidate matched purely by topical/sub-query overlap with no member ev_id
        # in the section carries no groundable facet, so it emits no corroborating view.
        corroborating_emitted: list[int] = []
        for idx in corroborating:
            facet = sorted(member_ids & sec_ev_ids[idx])
            if not facet:
                continue
            _cc = candidates[idx]
            views_by_section.setdefault(idx, []).append(
                SectionBasketView(
                    key, "corroborating", facet,
                    {"provenance": _cc["provenance"], "subquery": _cc["subquery"], "topical": _cc["topical"]},
                )
            )
            corroborating_emitted.append(idx)

        assignment_table.append(
            {
                "claim_cluster_id": key,
                "head_claim": _head_claim(basket),
                "primary_section": primary_idx,
                "corroborating_sections": corroborating_emitted,
                "signals": primary_signals,
                "member_count": len(member_ids),
                "corroboration_count": int(_get(basket, "corroboration_count", 0) or 0),
            }
        )

    # Determinism: sort views within each section by cluster id, then role (primary before
    # corroborating) so byte output is input-order-independent.
    for idx in views_by_section:
        views_by_section[idx].sort(key=lambda v: (v.claim_cluster_id, v.role))
    assignment_table.sort(key=lambda r: r["claim_cluster_id"])

    stranded = len(
        [b for b in baskets if _cluster_id(b) and _cluster_id(b) not in primary_section_by_cluster]
    )

    return SectionBasketMap(
        views_by_section=views_by_section,
        primary_section_by_cluster=primary_section_by_cluster,
        residual_section_index=residual_index,
        residual_title=_residual_title() if residual_index is not None else None,
        stranded_count=stranded,
        assignment_table=assignment_table,
        nocid_synthetic_count=nocid_synthetic_count,
        signals_available=signals_available,
        signal_totals=signal_totals,
    )
