"""S4 OUTLINE — ORCH-3 revise loop with section RE-OPEN (Design 5 ORCH-3).

FS-Researcher completion piece C1 (structural half): the paper's report-level review marks
flawed sections ``[IN-PROGRESS]`` again and re-writes them. POLARIS composes sections once
and concatenates; nothing revisits the plan when a section comes back thin, dropped, or with
baskets never cited. This module is the DETERMINISTIC core of that loop:

  1. ``build_section_outcomes`` — the per-section CHECKLIST (pure code over compose telemetry):
     verified count, kept fraction, dropped, unused ev_ids, uncovered baskets, undersupplied.
     Plus ``find_orphan_baskets`` — multi-source baskets assigned to NO section.
  2. ``parse_revision_ops`` — validate the reviser's JSON op list against the ev_id allow-list
     and the live plan titles; unknown refs are REJECTED with reason codes; a wholly-invalid /
     unparseable response is fail-open (zero ops => the caller keeps wave-1).
  3. ``apply_revision_ops`` — apply keep/merge/split/retitle/reassign/add under deterministic
     rules and EMIT the set of sections to recompose (that set IS the paper's ``[IN-PROGRESS]``
     re-open signal). ``keep`` sections are byte-identical reuse (``plan_signature`` proves it).

Pure code, no LLM, no network (LAW V). The LIVE reviser call and the recompose WAVE that
consumes ``recompose_titles`` are wired in the compose stage (WP-3a, VM hamster) — this module
is the apply-logic engine those wires drive, and where apply bugs are hunted offline
(``outline_lab.py`` ``apply-dry`` mode). §-1.3: reassignment moves an ev_id between SECTIONS
only; the row stays in the pool, other sections, and the bibliography — never deleted.
Faithfulness engine untouched: every recomposed section re-runs the full existing per-sentence
pipeline downstream; kept text carries its already-verified provenance tokens unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# knob defaults (LAW VI; Design 5 §6 + master §6) — resolver-swap seam per master §1.5.
PG_OUTLINE_REVISE_ROUNDS_DEFAULT = 1        # hard max 2
PG_OUTLINE_REVISE_ROUNDS_HARD_MAX = 2
PG_OUTLINE_REVISE_MAX_RECOMPOSE_DEFAULT = 8  # compute-safety ceiling, NOT a quality target
_ORPHAN_CORROBORATION_MIN = 2

_VALID_OPS = frozenset({"keep", "merge", "split", "retitle", "reassign", "add"})


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return int(default)


def revise_rounds() -> int:
    """Bounded revise-round count (default 1, hard max 2) — Design 5 §6."""
    return max(0, min(_env_int("PG_OUTLINE_REVISE_ROUNDS", PG_OUTLINE_REVISE_ROUNDS_DEFAULT),
                      PG_OUTLINE_REVISE_ROUNDS_HARD_MAX))


def max_recompose() -> int:
    return max(1, _env_int("PG_OUTLINE_REVISE_MAX_RECOMPOSE", PG_OUTLINE_REVISE_MAX_RECOMPOSE_DEFAULT))


# ─────────────────────────────────────────────────────────────────────────
# 1. Section outcome digests — the section CHECKLIST (pure telemetry read)
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class SectionOutcome:
    title: str
    verified_sentence_count: int
    kept_fraction: float
    dropped: bool
    unused_ev_ids: list[str]        # assigned but never cited in verified prose
    uncovered_baskets: list[str]    # corroboration>=min baskets here with zero cited members
    undersupplied: bool             # ORCH-2 flag carried through


def _plan_get(plan: Any, key: str, default: Any) -> Any:
    if isinstance(plan, Mapping):
        return plan.get(key, default)
    return getattr(plan, key, default)


def build_section_outcomes(
    plans: Sequence[Any],
    section_results: Mapping[str, Mapping[str, Any]],
    *,
    basket_members: Mapping[str, Sequence[str]] | None = None,
    basket_corroboration: Mapping[str, int] | None = None,
    corroboration_min: int = _ORPHAN_CORROBORATION_MIN,
) -> list[SectionOutcome]:
    """Compute one ``SectionOutcome`` per plan from compose telemetry.

    ``plans``: list of {title, ev_ids, basket_ids?, undersupplied?}.
    ``section_results``: title -> {verified_sentence_count, cited_ev_ids, kept_fraction,
    dropped}. Build-to-interface (plain dicts) so this is testable without the live compose
    result objects. A basket is ``uncovered`` when it is assigned to the section, carries
    corroboration >= min, and none of its members were cited in that section's verified prose.
    """
    basket_members = basket_members or {}
    basket_corroboration = basket_corroboration or {}
    outcomes: list[SectionOutcome] = []
    for plan in plans:
        title = str(_plan_get(plan, "title", "") or "")
        result = section_results.get(title, {})
        assigned = [str(e) for e in (_plan_get(plan, "ev_ids", []) or [])]
        cited = {str(e) for e in (result.get("cited_ev_ids", []) or [])}
        verified = int(result.get("verified_sentence_count", 0) or 0)
        unused = [e for e in assigned if e not in cited]

        uncovered: list[str] = []
        for bid in (_plan_get(plan, "basket_ids", []) or []):
            bid = str(bid)
            if int(basket_corroboration.get(bid, 0)) < corroboration_min:
                continue
            members = {str(m) for m in basket_members.get(bid, [])}
            if not (members & cited):
                uncovered.append(bid)

        outcomes.append(
            SectionOutcome(
                title=title,
                verified_sentence_count=verified,
                kept_fraction=float(result.get("kept_fraction", 0.0) or 0.0),
                dropped=bool(result.get("dropped", False)),
                unused_ev_ids=unused,
                uncovered_baskets=sorted(uncovered),
                undersupplied=bool(_plan_get(plan, "undersupplied", False)),
            )
        )
    return outcomes


def find_orphan_baskets(
    plans: Sequence[Any],
    basket_corroboration: Mapping[str, int],
    *,
    corroboration_min: int = _ORPHAN_CORROBORATION_MIN,
) -> list[str]:
    """Multi-source baskets (corroboration >= min) assigned to NO section anywhere."""
    assigned: set[str] = set()
    for plan in plans:
        for bid in (_plan_get(plan, "basket_ids", []) or []):
            assigned.add(str(bid))
    return sorted(
        bid
        for bid, corr in basket_corroboration.items()
        if int(corr) >= corroboration_min and str(bid) not in assigned
    )


# ─────────────────────────────────────────────────────────────────────────
# 2. Reviser op parsing / validation (deterministic; fail-open)
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class RevisionParseResult:
    ops: list[dict[str, Any]]           # accepted, validated ops in submission order
    rejected: list[dict[str, Any]]      # {op, reason_code}
    gap_queries: list[str]
    revision_needed: bool
    parse_failed: bool = False


def _validate_ev_ids(values: Any, allowed: set[str]) -> tuple[list[str], list[str]]:
    ok, bad = [], []
    for v in (values or []):
        s = str(v)
        (ok if s in allowed else bad).append(s)
    return ok, bad


def parse_revision_ops(
    raw: Any,
    *,
    allowed_ev_ids: set[str],
    plan_titles: Sequence[str],
) -> RevisionParseResult:
    """Validate the reviser output. ``raw`` may be a JSON string or an already-parsed dict.

    Every referenced ev_id must be in ``allowed_ev_ids``; every referenced existing-section
    title must be in ``plan_titles``. A reference to an unknown id/title REJECTS that op with a
    reason code (the op is dropped, the round is not aborted). Unparseable / shape-invalid input
    => ``parse_failed`` with zero ops (caller keeps wave-1 — fail-open to the existing good
    result; the reviser can only improve or no-op, never lose a report).
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return RevisionParseResult([], [], [], False, parse_failed=True)
    if not isinstance(raw, Mapping):
        return RevisionParseResult([], [], [], False, parse_failed=True)

    titles = {str(t) for t in plan_titles}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for op in (raw.get("ops", []) or []):
        if not isinstance(op, Mapping):
            rejected.append({"op": op, "reason_code": "not_an_object"})
            continue
        kind = str(op.get("op", ""))
        if kind not in _VALID_OPS:
            rejected.append({"op": dict(op), "reason_code": "unknown_op"})
            continue

        def _need_title(name: str = "title") -> str | None:
            t = str(op.get(name, ""))
            if t not in titles:
                rejected.append({"op": dict(op), "reason_code": f"unknown_{name}:{t}"})
                return None
            return t

        if kind in ("keep", "retitle", "reassign") and _need_title() is None:
            continue
        if kind == "retitle" and not str(op.get("new_title", "")).strip():
            rejected.append({"op": dict(op), "reason_code": "missing_new_title"})
            continue
        if kind == "merge":
            merge_titles = [str(t) for t in (op.get("titles", []) or [])]
            unknown = [t for t in merge_titles if t not in titles]
            if len(merge_titles) < 2 or unknown:
                rejected.append({"op": dict(op), "reason_code": f"bad_merge_titles:{unknown}"})
                continue
            if not str(op.get("new_title", "")).strip():
                rejected.append({"op": dict(op), "reason_code": "missing_new_title"})
                continue

        # ev_id references, wherever they appear
        bad_all: list[str] = []
        for key in ("ev_ids", "add_ev_ids", "drop_ev_ids"):
            if key in op:
                good, bad = _validate_ev_ids(op.get(key), allowed_ev_ids)
                op = {**op, key: good}
                bad_all += bad
        if kind == "split":
            into = op.get("into", []) or []
            if not isinstance(into, Sequence) or len(list(into)) < 2:
                rejected.append({"op": dict(op), "reason_code": "bad_split_into"})
                continue
            cleaned_into = []
            for child in into:
                if not isinstance(child, Mapping) or not str(child.get("title", "")).strip():
                    rejected.append({"op": dict(op), "reason_code": "bad_split_child"})
                    cleaned_into = None
                    break
                good, bad = _validate_ev_ids(child.get("ev_ids"), allowed_ev_ids)
                bad_all += bad
                cleaned_into.append({**child, "ev_ids": good})
            if cleaned_into is None:
                continue
            op = {**op, "into": cleaned_into}
        if kind == "add" and not str(op.get("title", "")).strip():
            rejected.append({"op": dict(op), "reason_code": "missing_add_title"})
            continue
        if bad_all:
            rejected.append({"op": dict(op), "reason_code": f"unknown_ev_ids:{bad_all[:5]}"})
            continue
        accepted.append(dict(op))

    return RevisionParseResult(
        ops=accepted,
        rejected=rejected,
        gap_queries=[str(q) for q in (raw.get("gap_queries", []) or [])],
        revision_needed=bool(raw.get("revision_needed", bool(accepted))),
    )


# ─────────────────────────────────────────────────────────────────────────
# 3. Deterministic apply — emits the recompose (RE-OPEN) set
# ─────────────────────────────────────────────────────────────────────────
@dataclass
class RevisionApplyResult:
    new_plans: list[dict[str, Any]]     # final plan set, in stable order
    recompose_titles: list[str]         # sections to RE-OPEN and recompose (the [IN-PROGRESS] set)
    kept_titles: list[str]              # sections reused byte-identical (no recompose)
    applied_ops: list[dict[str, Any]]
    deferred_ops: list[dict[str, Any]]  # dropped by the max_recompose ceiling (disclosed no-ops)
    rejected_ops: list[dict[str, Any]]
    changed: bool = False


# op precedence for the stable apply order (Design 5 §5 determinism contract)
_OP_ORDER = {"merge": 0, "split": 1, "retitle": 2, "reassign": 3, "add": 4, "keep": 5}


def plan_signature(plan: Mapping[str, Any]) -> str:
    """Stable content hash of a plan — a ``keep`` section's signature is byte-identical to its
    wave-1 signature (the acceptance-bar #5 hash-compare)."""
    payload = {
        "title": str(_plan_get(plan, "title", "")),
        "focus": str(_plan_get(plan, "focus", "")),
        "ev_ids": sorted(str(e) for e in (_plan_get(plan, "ev_ids", []) or [])),
        "basket_ids": sorted(str(b) for b in (_plan_get(plan, "basket_ids", []) or [])),
        "archetype": str(_plan_get(plan, "archetype", "")),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _as_dict(plan: Any) -> dict[str, Any]:
    if isinstance(plan, Mapping):
        return dict(plan)
    return {
        "title": _plan_get(plan, "title", ""),
        "focus": _plan_get(plan, "focus", ""),
        "ev_ids": list(_plan_get(plan, "ev_ids", []) or []),
        "basket_ids": list(_plan_get(plan, "basket_ids", []) or []),
        "archetype": _plan_get(plan, "archetype", ""),
    }


def apply_revision_ops(
    plans: Sequence[Any],
    parse_result: RevisionParseResult,
    *,
    max_recompose_cap: int | None = None,
    outcomes: Sequence[SectionOutcome] | None = None,
) -> RevisionApplyResult:
    """Apply validated ops deterministically and return the new plan set + the recompose set.

    ``keep`` reuses the wave-1 section byte-identical (never in the recompose set).
    ``merge`` builds ONE new section from the UNION of the merged ev_ids (never text-glue).
    ``split`` / ``retitle`` / ``reassign`` / ``add`` recompose the affected section(s) only.
    Wholesale-invalid input (parse failed, or zero accepted ops) => original plans unchanged,
    empty recompose set (fail-open to wave-1). Over the ``max_recompose`` ceiling, highest-impact
    ops win (dropped/undersupplied sections first) and the rest are DEFERRED as disclosed no-ops.
    """
    cap = max_recompose_cap if max_recompose_cap is not None else max_recompose()
    base = [_as_dict(p) for p in plans]
    by_title = {p["title"]: p for p in base}

    if parse_result.parse_failed or not parse_result.ops:
        return RevisionApplyResult(
            new_plans=base, recompose_titles=[], kept_titles=[p["title"] for p in base],
            applied_ops=[], deferred_ops=[], rejected_ops=list(parse_result.rejected),
            changed=False,
        )

    # impact ranking for the ceiling: dropped/undersupplied sections first
    impact = {}
    for oc in (outcomes or []):
        impact[oc.title] = (0 if (oc.dropped or oc.undersupplied) else 1, oc.title)

    def _op_touches(op: Mapping[str, Any]) -> list[str]:
        kind = op["op"]
        if kind == "merge":
            return list(op.get("titles", []))
        if kind in ("split", "retitle", "reassign"):
            return [str(op.get("title", ""))]
        return []

    def _op_impact(op: Mapping[str, Any]) -> tuple[int, str]:
        touched = _op_touches(op)
        ranks = [impact.get(t, (2, t)) for t in touched] or [(2, op.get("op", ""))]
        return min(ranks)

    ordered = sorted(
        parse_result.ops,
        key=lambda op: (_op_impact(op), _OP_ORDER.get(op["op"], 9)),
    )

    recompose: list[str] = []
    kept: list[str] = []
    applied: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    removed_titles: set[str] = set()
    added_plans: list[dict[str, Any]] = []

    def _recompose_budget_left() -> int:
        return cap - len(recompose)

    for op in ordered:
        kind = op["op"]
        if kind == "keep":
            applied.append(op)
            continue

        need = 1
        if kind == "split":
            need = len(list(op.get("into", [])))
        elif kind == "merge":
            need = 1
        if _recompose_budget_left() < need:
            deferred.append({**op, "reason_code": "max_recompose_ceiling"})
            continue

        if kind == "merge":
            titles = [str(t) for t in op["titles"]]
            union_ev: list[str] = []
            union_bask: list[str] = []
            for t in titles:
                src = by_title.get(t, {})
                union_ev += [str(e) for e in (src.get("ev_ids", []) or [])]
                union_bask += [str(b) for b in (src.get("basket_ids", []) or [])]
                removed_titles.add(t)
            new_title = str(op["new_title"])
            added_plans.append({
                "title": new_title, "focus": str(op.get("reason", "")),
                "ev_ids": sorted(set(union_ev)), "basket_ids": sorted(set(union_bask)),
                "archetype": "merged",
            })
            recompose.append(new_title)
            applied.append(op)
        elif kind == "split":
            src_title = str(op["title"])
            removed_titles.add(src_title)
            for child in op["into"]:
                ct = str(child["title"])
                added_plans.append({
                    "title": ct, "focus": str(child.get("focus", "")),
                    "ev_ids": sorted({str(e) for e in (child.get("ev_ids", []) or [])}),
                    "basket_ids": [], "archetype": "split",
                })
                recompose.append(ct)
            applied.append(op)
        elif kind == "retitle":
            src_title = str(op["title"])
            plan = dict(by_title.get(src_title, {}))
            plan["title"] = str(op["new_title"])
            by_title[src_title] = plan
            recompose.append(plan["title"])
            applied.append(op)
        elif kind == "reassign":
            src_title = str(op["title"])
            plan = dict(by_title.get(src_title, {}))
            evset = {str(e) for e in (plan.get("ev_ids", []) or [])}
            evset |= {str(e) for e in (op.get("add_ev_ids", []) or [])}
            evset -= {str(e) for e in (op.get("drop_ev_ids", []) or [])}
            plan["ev_ids"] = sorted(evset)
            by_title[src_title] = plan
            recompose.append(plan["title"])
            applied.append(op)
        elif kind == "add":
            at = str(op["title"])
            added_plans.append({
                "title": at, "focus": str(op.get("focus", "")),
                "ev_ids": sorted({str(e) for e in (op.get("ev_ids", []) or [])}),
                "basket_ids": [], "archetype": "added",
            })
            recompose.append(at)
            applied.append(op)

    # assemble: original order minus removed/retitled-away, then appended new sections
    recompose_set = set(recompose)
    new_plans: list[dict[str, Any]] = []
    for p in base:
        current = by_title.get(p["title"], p)
        if p["title"] in removed_titles:
            continue
        if current["title"] in removed_titles:
            continue
        new_plans.append(current)
        if current["title"] not in recompose_set:
            kept.append(current["title"])
    new_plans += added_plans

    changed = bool(recompose or removed_titles)
    return RevisionApplyResult(
        new_plans=new_plans,
        recompose_titles=recompose,
        kept_titles=kept,
        applied_ops=applied,
        deferred_ops=deferred,
        rejected_ops=list(parse_result.rejected),
        changed=changed,
    )
