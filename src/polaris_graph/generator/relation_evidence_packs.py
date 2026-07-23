"""Pre-generation proposition packs and a report-wide relation map.

The structures contain only fields already present in admitted evidence and
only reorder or group existing section membership.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from src.polaris_graph.settings import resolve


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_TOKEN_RE = re.compile(r"[^\W\d_][\w'-]+", re.UNICODE)
_STOPWORDS = frozenset({
    "about", "also", "and", "are", "evidence", "findings", "for", "from",
    "report", "section", "source", "study", "that", "the", "their", "these",
    "this", "those", "using", "was", "were", "which", "with",
})


def relation_evidence_packs_enabled() -> bool:
    """Return the central default-off switch at call time."""

    return (resolve("PG_RELATION_EVIDENCE_PACKS") or "").strip().lower() in _TRUE_VALUES


def _get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _row_proposition(row: Mapping[str, Any]) -> str:
    return str(
        row.get("proposition")
        or row.get("claim_text")
        or row.get("statement")
        or row.get("direct_quote")
        or row.get("title")
        or ""
    ).strip()


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _TOKEN_RE.findall(str(text or ""))
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    )


def _proposition_key(row: Mapping[str, Any]) -> str:
    declared = str(
        row.get("proposition_id")
        or row.get("claim_cluster_id")
        or row.get("basket_id")
        or ""
    ).strip()
    if declared:
        return declared
    words = sorted(_tokens(_row_proposition(row)))
    return " ".join(words)


def _attributes(row: Mapping[str, Any]) -> dict[str, str]:
    aliases = {
        "design": ("design", "study_design", "method"),
        "population": ("population", "sample", "cohort"),
        "measure": ("measure", "metric", "endpoint", "outcome"),
        "basis": ("observed_or_modeled", "observed_vs_modeled", "evidence_basis"),
        "period": ("period", "timeframe", "date_range"),
    }
    output: dict[str, str] = {}
    for label, names in aliases.items():
        value = next(
            (str(row.get(name) or "").strip() for name in names if str(row.get(name) or "").strip()),
            "",
        )
        if value:
            output[label] = value
    return output


def assign_conflict_owners(
    conflicts: Sequence[Mapping[str, Any]],
    plans: Sequence[Any],
) -> list[dict[str, Any]]:
    """Assign each conflict to one section using membership, vocabulary, then order."""

    output: list[dict[str, Any]] = []
    for conflict in conflicts:
        ids = {str(item) for item in (conflict.get("evidence_ids") or []) if str(item)}
        conflict_words = _tokens(" ".join(
            str(conflict.get(name) or "")
            for name in ("subject", "predicate", "measure", "reason")
        ))
        scored: list[tuple[int, int, int, Any]] = []
        for index, plan in enumerate(plans):
            plan_ids = {str(item) for item in (_get(plan, "ev_ids", []) or [])}
            plan_words = _tokens(
                f"{_get(plan, 'title', '')} {_get(plan, 'focus', '')}"
            )
            scored.append((
                len(ids & plan_ids),
                len(conflict_words & plan_words),
                -index,
                plan,
            ))
        copied = dict(conflict)
        if scored:
            owner = max(scored, key=lambda item: item[:3])[3]
            copied["section_title"] = str(_get(owner, "title", "") or "")
        output.append(copied)
    return output


def build_relation_evidence_packs(
    plans: Sequence[Any],
    evidence_pool: Mapping[str, Mapping[str, Any]],
    conflicts: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, str], str, list[dict[str, Any]]]:
    """Build section packs and the report-wide map without changing membership."""

    owned_conflicts = assign_conflict_owners(conflicts, plans)
    conflicts_by_id: dict[str, list[dict[str, Any]]] = {}
    for conflict in owned_conflicts:
        for evidence_id in conflict.get("evidence_ids") or []:
            conflicts_by_id.setdefault(str(evidence_id), []).append(conflict)

    section_blocks: dict[str, str] = {}
    global_entries: list[dict[str, Any]] = []
    observed_membership: list[str] = []
    for plan in plans:
        title = str(_get(plan, "title", "") or "")
        groups: dict[str, dict[str, Any]] = {}
        for evidence_id in _get(plan, "ev_ids", []) or []:
            evidence_id = str(evidence_id)
            row = evidence_pool.get(evidence_id)
            if not isinstance(row, Mapping):
                continue
            observed_membership.append(evidence_id)
            key = _proposition_key(row) or evidence_id
            group = groups.setdefault(key, {
                "proposition": _row_proposition(row),
                "supporting_evidence_ids": [],
                "contradicting_evidence_ids": [],
                "source_attributes": [],
            })
            group["supporting_evidence_ids"].append(evidence_id)
            attributes = _attributes(row)
            if attributes:
                group["source_attributes"].append({
                    "evidence_id": evidence_id,
                    **attributes,
                })
            for conflict in conflicts_by_id.get(evidence_id, []):
                if conflict.get("section_title") != title:
                    continue
                group["contradicting_evidence_ids"].extend(
                    other for other in conflict.get("evidence_ids") or []
                    if str(other) != evidence_id
                )
                group["conflict_reason"] = str(conflict.get("reason") or "")
        entries = list(groups.values())
        for entry in entries:
            entry["supporting_evidence_ids"] = list(dict.fromkeys(
                entry["supporting_evidence_ids"]
            ))
            entry["contradicting_evidence_ids"] = list(dict.fromkeys(
                entry["contradicting_evidence_ids"]
            ))
            global_entries.append({"section": title, **entry})
        section_blocks[title] = json.dumps(entries, ensure_ascii=False, sort_keys=True)

    expected_membership = [
        str(evidence_id)
        for plan in plans
        for evidence_id in (_get(plan, "ev_ids", []) or [])
        if str(evidence_id) in evidence_pool
    ]
    assert observed_membership == expected_membership
    global_map = json.dumps(global_entries, ensure_ascii=False, sort_keys=True)
    return section_blocks, global_map, owned_conflicts


def is_synthesis_plan(plan: Any) -> bool:
    """Detect the prompt-defined cross-section role from its own title/focus."""

    words = _tokens(f"{_get(plan, 'title', '')} {_get(plan, 'focus', '')}")
    return bool(words & {"synthesis", "cross-study", "integration", "convergence"})


def relation_context_for_plan(
    plan: Any,
    section_blocks: Mapping[str, str],
    global_map: str,
) -> tuple[str, str]:
    """Return local framing and, only for the synthesis role, the global map."""

    title = str(_get(plan, "title", "") or "")
    return section_blocks.get(title, ""), global_map if is_synthesis_plan(plan) else ""
