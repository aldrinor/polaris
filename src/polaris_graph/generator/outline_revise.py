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
# reassign op fields (WP-3a compose-stage prompt schema): `add_ev_ids` = pool members to ADD
# into this section, `drop_ev_ids` = members to REMOVE. A bare `ev_ids` on a reassign is aliased
# to `add_ev_ids` (fail-open, §-1.3); a reassign carrying neither is rejected as no_op_reassign.


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

        # item 1: ``split`` MUST validate its source ``title`` here too. Without it a split with a
        # missing title passes parse then crashes ``KeyError`` at apply (``op["title"]``), and a split
        # with an UNKNOWN title silently keeps the original section AND adds the children (content
        # duplication). Validating here rejects both before apply.
        if kind in ("keep", "retitle", "reassign", "split") and _need_title() is None:
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

        # reassign fail-open alias (§-1.3): a reassign carrying a bare ``ev_ids`` but neither
        # ``add_ev_ids`` nor ``drop_ev_ids`` means "assign these members INTO this section".
        # Alias ev_ids -> add_ev_ids BEFORE validation so the payload is KEPT — the apply branch
        # reads ONLY add_ev_ids/drop_ev_ids, so without this the members are silently dropped
        # while the op still fakes accepted=1 and burns a recompose slot (the reproduced no-op).
        if kind == "reassign" and "add_ev_ids" not in op and "drop_ev_ids" not in op and "ev_ids" in op:
            aliased = {k: v for k, v in op.items() if k != "ev_ids"}
            aliased["add_ev_ids"] = op["ev_ids"]
            op = aliased

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
        # item 8 (STRIP-AND-KEEP, consistent with the outline's item-5a): a reassign/add/split that
        # references some UNKNOWN ev_ids KEEPS its valid remainder — the good ids were already retained
        # in ``op`` above; only the bad ones are stripped — and the strip is DISCLOSED as a
        # rejected-style note (``unknown_ev_ids_stripped``). The op is NOT dropped wholesale. When the
        # strip leaves NOTHING actionable the op is still rejected: a reassign that now moves nothing is
        # caught by the ``no_op_reassign`` guard just below; a wholly-unknown add/split child is marked
        # ``undersupplied`` downstream (item 12 — the gap is DISCLOSED, never faked). §-1.3: an ev_id
        # reference is a routing hint, not the source itself, so one bad hint never deletes the good
        # remainder (the prior blanket reject discarded valid reassignments over a single stale id).
        if bad_all:
            rejected.append({"op": dict(op), "reason_code": f"unknown_ev_ids_stripped:{bad_all[:5]}"})
        if kind == "reassign" and not op.get("add_ev_ids") and not op.get("drop_ev_ids"):
            # a reassign that moves nothing must NOT fake changed=True or consume a recompose
            # slot in the apply branch — reject it here (one source of truth in the parser).
            rejected.append({"op": dict(op), "reason_code": "no_op_reassign"})
            continue
        accepted.append(dict(op))

    # ── item 5: TITLE-COLLISION pass. A duplicate section title (case-insensitive) is silently
    # lossy downstream — ``by_title`` (last-wins) and the title-keyed ``section_results`` drop one
    # plan's ev_ids. Reject any op that introduces a NEW title (``add``/``retitle``/``merge`` new
    # title, or a ``split`` child title) equal (case-insensitive) to a SURVIVING plan title or to
    # another new title. Op-sequence aware: a title removed by an accepted op (merge source / split
    # source / retitle source) is NOT "surviving", so reusing a freed name is allowed. Runs over
    # ``accepted`` so the main per-op validation above is untouched.
    def _op_removed_titles(o: dict) -> list[str]:
        k = o.get("op")
        if k == "merge":
            return [str(t) for t in (o.get("titles", []) or [])]
        if k in ("split", "retitle"):
            return [str(o.get("title", ""))]
        return []

    def _op_new_titles(o: dict) -> list[str]:
        k = o.get("op")
        if k == "add":
            return [str(o.get("title", ""))]
        if k in ("retitle", "merge"):
            return [str(o.get("new_title", ""))]
        if k == "split":
            return [str(c.get("title", "")) for c in (o.get("into", []) or [])]
        return []

    _removed_lower = {t.lower() for o in accepted for t in _op_removed_titles(o)}
    _surviving_lower = {t.lower() for t in plan_titles if t.lower() not in _removed_lower}
    _seen_new_lower: set[str] = set()
    _collision_filtered: list[dict[str, Any]] = []
    for op in accepted:
        _collide = None
        for _nt in _op_new_titles(op):
            _ntl = _nt.strip().lower()
            if not _ntl:
                continue
            if _ntl in _surviving_lower or _ntl in _seen_new_lower:
                _collide = _nt
                break
        if _collide is not None:
            rejected.append({"op": dict(op), "reason_code": f"title_collision:{_collide}"})
            continue
        for _nt in _op_new_titles(op):
            _ntl = _nt.strip().lower()
            if _ntl:
                _seen_new_lower.add(_ntl)
        _collision_filtered.append(op)
    accepted = _collision_filtered

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
    required_titles: Sequence[str] | None = None,
) -> RevisionApplyResult:
    """Apply validated ops deterministically and return the new plan set + the recompose set.

    ``keep`` reuses the wave-1 section byte-identical (never in the recompose set).
    ``merge`` builds ONE new section from the UNION of the merged ev_ids (never text-glue).
    ``split`` / ``retitle`` / ``reassign`` / ``add`` recompose the affected section(s) only.
    Wholesale-invalid input (parse failed, or zero accepted ops) => original plans unchanged,
    empty recompose set (fail-open to wave-1). Over the ``max_recompose`` ceiling, highest-impact
    ops win (dropped/undersupplied sections first) and the rest are DEFERRED as disclosed no-ops.

    ``required_titles`` (item 13): when the run has a user-required section structure, only
    ``keep``/``reassign`` may run (they preserve the exact-N-in-order contract); ``merge``/
    ``split``/``add``/``retitle`` are DEFERRED as disclosed no-ops so the structure cannot break,
    and the assembled order stays the required order. ``None``/empty => no restriction (unchanged).

    Item 4: an op whose target title was already consumed by an earlier op (merged/split away, or
    retitled) is skipped as a disclosed no-op (never a ghost recompose title); retitled sections are
    resolved by their CURRENT title. Item 5 (apply half): a NEW title colliding with a live section
    is deferred. Item 12: an ``add`` with no evidence, or a ``reassign`` that empties a section, is
    marked ``undersupplied=True`` (the gap is disclosed, never faked)."""
    cap = max_recompose_cap if max_recompose_cap is not None else max_recompose()
    base = [_as_dict(p) for p in plans]
    by_title = {p["title"]: p for p in base}

    def _ci(s: Any) -> str:
        return str(s).strip().lower()

    # item 13: required-structure lock — restrict ops to keep/reassign when required_titles present.
    required_lock = bool([t for t in (required_titles or []) if str(t).strip()])

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
    applied: list[dict[str, Any]] = []
    deferred: list[dict[str, Any]] = []
    removed_titles: set[str] = set()      # merge/split SOURCES — dropped from assembly
    title_remap: dict[str, str] = {}       # retitle old->new — resolve later op targets + assembly
    added_plans: list[dict[str, Any]] = []
    # item 5 (apply half): live section titles (case-insensitive) for the collision guard.
    live_lower: set[str] = {_ci(p["title"]) for p in base}

    def _recompose_budget_left() -> int:
        return cap - len(recompose)

    def _resolve_current(t: str) -> str:
        """Follow the retitle chain so a later op referencing the ORIGINAL title lands on the
        section's CURRENT name (item 4)."""
        seen: set[str] = set()
        while t in title_remap and t not in seen:
            seen.add(t)
            t = title_remap[t]
        return t

    for op in ordered:
        kind = op["op"]
        if kind == "keep":
            applied.append(op)
            continue

        # item 13: required-structure lock — merge/split/add/retitle can break exact-N-in-order.
        if required_lock and kind not in ("keep", "reassign"):
            deferred.append({**op, "reason_code": "required_structure_locked"})
            continue

        # item 4: an op whose target was already consumed (merged/split away, or retitled) is a
        # disclosed no-op — never let it burn a recompose slot or emit a ghost title.
        _targets = [_resolve_current(t) for t in _op_touches(op)]
        if any(t in removed_titles for t in _targets):
            deferred.append({**op, "reason_code": "stale_target_removed"})
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
            titles = [_resolve_current(str(t)) for t in op["titles"]]
            new_title = str(op["new_title"])
            prospective = live_lower - {_ci(t) for t in titles}
            if _ci(new_title) in prospective:   # item 5: merged title collides with a survivor
                deferred.append({**op, "reason_code": f"title_collision:{new_title}"})
                continue
            union_ev: list[str] = []
            union_bask: list[str] = []
            for t in titles:
                src = by_title.get(t, {})
                union_ev += [str(e) for e in (src.get("ev_ids", []) or [])]
                union_bask += [str(b) for b in (src.get("basket_ids", []) or [])]
                removed_titles.add(t)
            merged_ev = sorted(set(union_ev))
            added_plans.append({
                "title": new_title, "focus": str(op.get("reason", "")),
                "ev_ids": merged_ev, "basket_ids": sorted(set(union_bask)),
                "archetype": "merged", "undersupplied": not merged_ev,
            })
            live_lower = prospective | {_ci(new_title)}
            recompose.append(new_title)
            applied.append(op)
        elif kind == "split":
            src_title = _resolve_current(str(op["title"]))
            child_titles = [str(child["title"]) for child in op["into"]]
            prospective = live_lower - {_ci(src_title)}
            _lowered = [_ci(ct) for ct in child_titles]
            if len(set(_lowered)) != len(_lowered) or any(cl in prospective for cl in _lowered):
                deferred.append({**op, "reason_code": "title_collision:split_children"})
                continue
            removed_titles.add(src_title)
            live_lower = prospective
            for child in op["into"]:
                ct = str(child["title"])
                child_ev = sorted({str(e) for e in (child.get("ev_ids", []) or [])})
                added_plans.append({
                    "title": ct, "focus": str(child.get("focus", "")),
                    "ev_ids": child_ev,
                    "basket_ids": [], "archetype": "split", "undersupplied": not child_ev,
                })
                live_lower.add(_ci(ct))
                recompose.append(ct)
            applied.append(op)
        elif kind == "retitle":
            src_title = _resolve_current(str(op["title"]))
            new_title = str(op["new_title"])
            prospective = live_lower - {_ci(src_title)}
            if _ci(new_title) in prospective:   # item 5: retitle onto a surviving section's name
                deferred.append({**op, "reason_code": f"title_collision:{new_title}"})
                continue
            plan = dict(by_title.get(src_title, {}))
            plan["title"] = new_title
            # item 4: keep by_title keyed by the CURRENT title + record the remap so later ops and
            # the assembly resolve the renamed section correctly.
            by_title.pop(src_title, None)
            by_title[new_title] = plan
            title_remap[src_title] = new_title
            live_lower = prospective | {_ci(new_title)}
            recompose.append(new_title)
            applied.append(op)
        elif kind == "reassign":
            src_title = _resolve_current(str(op["title"]))
            # item 10: guard the lookup — a reassign whose target section is somehow gone (never in
            # ``by_title``, or resolved to a name no plan carries) DEFERS as a disclosed no-op instead
            # of KeyError-ing on the empty-plan ``title`` at ``recompose.append(plan["title"])`` below.
            if src_title not in by_title:
                deferred.append({**op, "reason_code": "missing_target"})
                continue
            plan = dict(by_title.get(src_title, {}))
            evset = {str(e) for e in (plan.get("ev_ids", []) or [])}
            evset |= {str(e) for e in (op.get("add_ev_ids", []) or [])}
            evset -= {str(e) for e in (op.get("drop_ev_ids", []) or [])}
            plan["ev_ids"] = sorted(evset)
            if not evset:   # item 12: a reassign that empties a section discloses the gap
                plan["undersupplied"] = True
            by_title[src_title] = plan
            recompose.append(plan["title"])
            applied.append(op)
        elif kind == "add":
            at = str(op["title"])
            if _ci(at) in live_lower:   # item 5: add colliding with a live section title
                deferred.append({**op, "reason_code": f"title_collision:{at}"})
                continue
            # item 12: an add carries evidence via ev_ids and/or add_ev_ids; empty => undersupplied.
            add_ev = sorted(
                {str(e) for e in (op.get("ev_ids", []) or [])}
                | {str(e) for e in (op.get("add_ev_ids", []) or [])}
            )
            added_plans.append({
                "title": at, "focus": str(op.get("focus", "")),
                "ev_ids": add_ev,
                "basket_ids": [], "archetype": "added", "undersupplied": not add_ev,
            })
            live_lower.add(_ci(at))
            recompose.append(at)
            applied.append(op)

    # assemble: original order minus removed/retitled-away, then appended new sections. A retitled
    # section is resolved to its CURRENT object via ``title_remap`` (item 4) so the rename + any
    # later reassign survive assembly. Under the required-structure lock nothing is added/removed, so
    # the base (required) ORDER is preserved (item 13).
    new_plans: list[dict[str, Any]] = []
    for p in base:
        cur_title = _resolve_current(p["title"])
        if p["title"] in removed_titles or cur_title in removed_titles:
            continue
        new_plans.append(by_title.get(cur_title, p))
    new_plans += added_plans

    # item 4: dedupe recompose_titles AND drop any GHOST title not present in the final plan set —
    # a ghost would make the compose stage re-open a section that does not exist.
    _final_titles = {p["title"] for p in new_plans}
    _seen_rc: set[str] = set()
    recompose = [
        t for t in recompose
        if t in _final_titles and not (t in _seen_rc or _seen_rc.add(t))
    ]
    _recompose_final = set(recompose)
    kept = [p["title"] for p in new_plans if p["title"] not in _recompose_final]

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
