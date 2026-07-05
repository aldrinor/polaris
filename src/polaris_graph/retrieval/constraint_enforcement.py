"""I-scope-001 — the generic SCOPE + TIMELINE enforcement plan builder.

Generalizes the PROVEN date-window WEIGHT seam (``evidence_selector`` ~2881: build a per-URL
demote map + an out-of-window tail-partition set + disclosed exclusion records) to arbitrary
SCOPE facets driven by the ontology. It emits, for one corpus + one protocol:

  * ``url_to_scope_weight``   — multiplicative (0,1] demote for WEIGHT-demoted sources
                               (mirrors ``url_to_date_weight``); folded into the SAME
                               selection sort key. WEIGHT path — never a drop.
  * ``out_of_scope_urls``     — the tail-partition set (mirrors ``_oow_urls``).
  * ``grounding_excluded_ids``— HARD-mode urls masked OUT of the billed grounding set
                               ``evidence_for_gen`` (restrict-to / exclude-hard / hard
                               timeline). KEPT in the pool + disclosure, never deleted.
  * ``must_include_urls``     — op='include' boost/pin flag (additive, non-demoting).
  * ``scope_excluded_records``— PRISMA-style telemetry, one row per decision.

DNA §-1.3: WEIGHT-DON'T-FILTER + DISCLOSE. A HARD mask removes a source from the ANSWER
GROUNDING surface only, never from the evidence pool / strict_verify / NLI / D8 / provenance
(the ONE hard gate stays byte-untouched). Fail-open: an unresolved facet => neutral (weight
1.0, never punished). Default-OFF ``PG_SCOPE_CONSTRAINT_ENFORCE`` => empty plan => byte-
identical selection + no grounding mask. All knobs config-driven (LAW VI).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from src.polaris_graph.retrieval.scope_facet_classifier import (
    classify_source_facets,
    facet_default_weight,
    load_scope_ontology,
)

logger = logging.getLogger("polaris_graph.constraint_enforcement")

_ENFORCE_FLAG = "PG_SCOPE_CONSTRAINT_ENFORCE"
_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})

_YEAR_RE = re.compile(r"\b(19|20|21)\d{2}\b")
_ISO_YM_RE = re.compile(r"\b((?:19|20|21)\d{2})-(0[1-9]|1[0-2])\b")


def scope_enforcement_enabled() -> bool:
    """I-scope-001 enforcement kill-switch. DEFAULT OFF (operator activates on the slate).
    OFF => ``build_scope_enforcement`` returns an EMPTY plan => byte-identical selection."""
    return os.getenv(_ENFORCE_FLAG, "0").strip().lower() not in _OFF_VALUES


@dataclass
class ScopeEnforcementPlan:
    """The demote / mask / boost decisions for one corpus under one protocol's scope+timeline
    intent. Empty plan => byte-identical widest+deepest run."""

    url_to_scope_weight: dict[str, float] = field(default_factory=dict)
    out_of_scope_urls: set[str] = field(default_factory=set)
    grounding_excluded_ids: set[str] = field(default_factory=set)
    must_include_urls: set[str] = field(default_factory=set)
    scope_excluded_records: list[dict[str, Any]] = field(default_factory=list)
    scope_disclosed_rows: list[dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.url_to_scope_weight
            or self.out_of_scope_urls
            or self.grounding_excluded_ids
            or self.must_include_urls
        )


def _field(source: "Any", *names: str) -> "Any":
    if isinstance(source, Mapping):
        for n in names:
            if n in source and source.get(n) is not None:
                return source.get(n)
        return None
    for n in names:
        v = getattr(source, n, None)
        if v is not None:
            return v
    return None


def _row_url(row: "Any") -> str:
    return str(_field(row, "source_url", "url") or "")


def _row_pub_ym(row: "Any") -> "tuple[int, int | None] | None":
    """Best-effort (year, month|None) from a row's date fields. None when undated
    (fail-open — an undated row is NEVER excluded by a timeline window).

    Month-precision keys (``pub_date`` is the production month field emitted by
    live_retriever) are read BEFORE the year-only fallbacks (``publication_year`` /
    ``year``) so month precision wins: a live row carrying ``pub_date``="2023-05"
    plus a year-only ``publication_year``=2023 resolves to (2023, 5), not (2023, None).
    Reading only the year would degrade every real row to YEAR precision and wrongly
    hard-mask an in-window month source under a HARD month-precision cutoff (§-1.3)."""
    for key in ("pub_date", "publication_date", "published", "date", "publication_year", "year"):
        v = _field(row, key)
        if v is None:
            continue
        s = str(v)
        m = _ISO_YM_RE.search(s)
        if m:
            return (int(m.group(1)), int(m.group(2)))
        y = _YEAR_RE.search(s)
        if y:
            return (int(y.group(0)), None)
    return None


def _parse_window_bound(iso: "str | None") -> "tuple[int, int | None] | None":
    if not iso:
        return None
    s = str(iso)
    m = _ISO_YM_RE.search(s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    y = _YEAR_RE.search(s)
    if y:
        return (int(y.group(0)), None)
    return None


def _ym_index(ym: "tuple[int, int | None]", *, ceil: bool) -> int:
    """Month index (year*12+month). A year-only bound uses month 1 for a floor and 12 for a
    ceiling so a whole-year window is inclusive."""
    year, month = ym
    if month is None:
        month = 12 if ceil else 1
    return year * 12 + month


def _row_out_of_window(
    row: "Any", start_idx: "int | None", end_idx: "int | None"
) -> bool:
    """True iff the row has an EXPLICIT publication date outside [start, end]. Undated =>
    False (fail-open, kept)."""
    pub = _row_pub_ym(row)
    if pub is None:
        return False
    idx = _ym_index((pub[0], pub[1]), ceil=False)
    if start_idx is not None and idx < start_idx:
        return True
    if end_idx is not None:
        # compare at the row's own precision against the ceiling
        row_ceil = _ym_index((pub[0], pub[1]), ceil=(pub[1] is None))
        if row_ceil > end_idx:
            return True
    return False


def _facet_ids(facets: list[dict[str, Any]], op: str, strictness: "str | None") -> list[str]:
    out = []
    for f in facets:
        if not isinstance(f, dict):
            continue
        if str(f.get("op")) != op:
            continue
        if strictness is not None and str(f.get("strictness")) != strictness:
            continue
        fid = str(f.get("facet_id") or "")
        if fid:
            out.append(fid)
    return out


def _named_match(label: str, identity: dict[str, Any], row: "Any") -> bool:
    """Match a named-include source to a row by its org acronym / label tokens against the
    row url / host / title. Deterministic, conservative (acronym is case-sensitive)."""
    hay = " ".join(
        str(_field(row, k) or "") for k in ("source_url", "url", "title")
    )
    acronym = str(identity.get("acronym") or "").strip()
    if acronym and re.search(r"\b" + re.escape(acronym) + r"\b", hay):
        return True
    # fall back to a distinctive lowercase token from the label (>= 4 chars)
    for tok in re.findall(r"[A-Za-z]{4,}", label):
        if tok.lower() in ("guidelines", "guideline", "reports", "report", "data",
                           "publications", "publication", "standards", "framework"):
            continue
        if tok.lower() in hay.lower():
            return True
    return False


def build_scope_enforcement(
    protocol: "dict[str, Any] | None",
    evidence_rows: "list[Any] | None",
    ontology: "dict[str, Any] | None" = None,
) -> ScopeEnforcementPlan:
    """Build the scope+timeline enforcement plan for one corpus (§2.2).

    Reads ``protocol['scope_constraints']`` (from ``ScopeConstraints.to_dict``) + the timeline
    strictness inside ``protocol['user_constraints']`` + the date window from
    ``protocol['date_range']``. Classifies each row via ``classify_source_facets`` and applies
    the per-(op,strictness) rule. Returns an EMPTY plan when the enforce flag is OFF or when no
    scope/timeline constraint was stated (byte-identical). Pure; never raises."""
    plan = ScopeEnforcementPlan()
    if not scope_enforcement_enabled():
        return plan
    if not protocol:
        return plan
    rows = list(evidence_rows or [])
    if not rows:
        return plan

    ont = ontology if ontology is not None else load_scope_ontology()
    sc = protocol.get("scope_constraints") or {}
    uc = protocol.get("user_constraints") or {}
    facets = list(sc.get("facets") or []) if isinstance(sc, dict) else []
    named_include = list(sc.get("named_include") or []) if isinstance(sc, dict) else []

    prefer_weight = _facet_ids(facets, "prefer", "weight")
    prefer_hard = _facet_ids(facets, "prefer", "hard")
    include_ids = _facet_ids(facets, "include", None)
    exclude_weight = _facet_ids(facets, "exclude", "weight")
    exclude_hard = _facet_ids(facets, "exclude", "hard")

    # trigger spans for disclosure
    span_by_facet = {
        str(f.get("facet_id")): str(f.get("trigger_span") or "")
        for f in facets if isinstance(f, dict)
    }

    # timeline (hard) window
    timeline_strictness = str(uc.get("timeline_strictness") or "weight")
    dr = protocol.get("date_range") or {}
    if isinstance(dr, (list, tuple)):
        _s_iso, _e_iso = (dr[0] if len(dr) > 0 else None), (dr[1] if len(dr) > 1 else None)
    elif isinstance(dr, dict):
        _s_iso, _e_iso = dr.get("start"), dr.get("end")
    else:
        _s_iso, _e_iso = None, None
    _start = _parse_window_bound(_s_iso)
    _end = _parse_window_bound(_e_iso)
    _start_idx = _ym_index(_start, ceil=False) if _start else None
    _end_idx = _ym_index(_end, ceil=(_end[1] is None)) if _end else None
    timeline_hard_active = (
        timeline_strictness == "hard" and (_start_idx is not None or _end_idx is not None)
    )

    have_scope = bool(
        prefer_weight or prefer_hard or include_ids or exclude_weight or exclude_hard
        or named_include
    )
    if not have_scope and not timeline_hard_active:
        return plan

    def _min_weight(ids: list[str]) -> float:
        ws = [facet_default_weight(i, ont) for i in ids]
        return min(ws) if ws else facet_default_weight("", ont)

    for row in rows:
        url = _row_url(row)
        if not url:
            continue
        try:
            row_facets, _basis = classify_source_facets(row, ont)
        except Exception:  # noqa: BLE001 - fail-open: an unresolved row is neutral
            row_facets = set()

        # op='include' — additive boost; non-matching NOT demoted.
        matched_include = [i for i in include_ids if i in row_facets]
        for named in named_include:
            if isinstance(named, dict) and _named_match(
                str(named.get("label") or ""), dict(named.get("identity") or {}), row
            ):
                plan.must_include_urls.add(url)
                plan.scope_excluded_records.append({
                    "source_url": url, "matched_facet": str(named.get("label") or ""),
                    "op": "include", "action": "named_include_boost", "weight": 1.0,
                    "reason": "named-include pinned", "trigger_span": str(named.get("label") or ""),
                })
        if matched_include:
            plan.must_include_urls.add(url)
            plan.scope_excluded_records.append({
                "source_url": url, "matched_facet": ",".join(matched_include),
                "op": "include", "action": "include_boost", "weight": 1.0,
                "reason": "in requested include facet",
                "trigger_span": span_by_facet.get(matched_include[0], ""),
            })

        # HARD exclusion — masked from grounding, KEPT in pool + disclosure.
        hard_excluded = False
        matched_exclude_hard = [i for i in exclude_hard if i in row_facets]
        if matched_exclude_hard:
            hard_excluded = True
            plan.grounding_excluded_ids.add(url)
            plan.scope_excluded_records.append({
                "source_url": url, "matched_facet": ",".join(matched_exclude_hard),
                "op": "exclude", "action": "hard_excluded_from_grounding_disclosed",
                "weight": 0.0, "reason": "in do-not-use facet (hard)",
                "trigger_span": span_by_facet.get(matched_exclude_hard[0], ""),
            })
        elif prefer_hard and not any(i in row_facets for i in prefer_hard):
            hard_excluded = True
            plan.grounding_excluded_ids.add(url)
            plan.scope_excluded_records.append({
                "source_url": url, "matched_facet": ",".join(prefer_hard),
                "op": "prefer", "action": "hard_excluded_from_grounding_disclosed",
                "weight": 0.0, "reason": "outside restrict-to facet (hard)",
                "trigger_span": span_by_facet.get(prefer_hard[0], ""),
            })

        # HARD timeline — out-of-window masked from grounding, KEPT + disclosed.
        if timeline_hard_active and _row_out_of_window(row, _start_idx, _end_idx):
            hard_excluded = True
            plan.grounding_excluded_ids.add(url)
            _pub = _row_pub_ym(row)
            plan.scope_excluded_records.append({
                "source_url": url,
                "matched_facet": "timeline",
                "op": "timeline", "action": "timeline_hard_excluded_disclosed",
                "weight": 0.0,
                "reason": "outside hard timeline window",
                "pub_ym": (f"{_pub[0]:04d}-{_pub[1]:02d}" if _pub and _pub[1]
                           else (str(_pub[0]) if _pub else None)),
                "trigger_span": str(uc.get("timeline_trigger_span") or ""),
            })

        if hard_excluded:
            plan.scope_disclosed_rows.append({
                "source_url": url,
                "disclosed": "hard_excluded_from_grounding_kept_in_corpus",
            })
            continue

        # WEIGHT demote (prefer-weight miss OR exclude-weight hit). Multiplicative, kept.
        w = 1.0
        demote_reason = ""
        demote_facet = ""
        if prefer_weight and not any(i in row_facets for i in prefer_weight):
            w = min(w, _min_weight(prefer_weight))
            demote_reason = "outside preferred facet"
            demote_facet = ",".join(prefer_weight)
        matched_exclude_weight = [i for i in exclude_weight if i in row_facets]
        if matched_exclude_weight:
            w = min(w, _min_weight(matched_exclude_weight))
            demote_reason = "in de-emphasized facet"
            demote_facet = ",".join(matched_exclude_weight)
        # P1 fix (§2.2/§2.4 include != prefer): a source the user explicitly INCLUDED
        # (op='include' / named-include) is NEVER also demoted — include is an ADDITIVE
        # boost, so it must not sink its own pinned source. The include block above ran
        # first this iteration, so ``must_include_urls`` already carries this url when it
        # was included. Skipping the demote keeps the disclosure honest (a source is never
        # recorded as both boosted and demoted) and matches the selector's include-pin.
        if 0.0 < w < 1.0 and url not in plan.must_include_urls:
            plan.url_to_scope_weight[url] = w
            plan.out_of_scope_urls.add(url)
            plan.scope_excluded_records.append({
                "source_url": url, "matched_facet": demote_facet,
                "op": ("exclude" if matched_exclude_weight else "prefer"),
                "action": "demoted_out_of_scope_kept", "weight": w,
                "reason": demote_reason,
                "trigger_span": span_by_facet.get(
                    (demote_facet.split(",")[0] if demote_facet else ""), ""
                ),
            })

    if not plan.is_empty():
        logger.info(
            "[scope_enforce] I-scope-001: demoted=%d hard_masked=%d boosted=%d "
            "(timeline_hard=%s)",
            len(plan.url_to_scope_weight), len(plan.grounding_excluded_ids),
            len(plan.must_include_urls), timeline_hard_active,
        )
    return plan
