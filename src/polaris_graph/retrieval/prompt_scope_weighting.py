"""Prompt-derived, keep-all evidence weighting.

The module turns constraints already extracted from the user's own prompt into a
continuous ordering weight.  It never decides admission: every input row and every
query remains present.  The central activation gate is intentionally consumed by
callers so these pure functions are easy to replay and test.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from src.polaris_graph.retrieval.rq_eligibility import (
    build_rq_eligibility_from_constraints,
    demote_weight,
)
from src.polaris_graph.settings import resolve


_OFF = frozenset({"", "0", "false", "no", "off", "disabled"})
_TOKEN_RE = re.compile(r"[A-Za-z\u00c0-\u024f][A-Za-z0-9\u00c0-\u024f_-]{2,}")
_STOPWORDS = frozenset({
    "about", "after", "also", "and", "are", "before", "between", "but", "by",
    "for", "from", "have", "into", "its", "only", "over", "please", "report",
    "research", "source", "sources", "that", "the", "their", "these", "this",
    "those", "through", "under", "using", "was", "were", "what", "when", "where",
    "which", "while", "with", "within", "write",
})


def prompt_scope_weighting_enabled() -> bool:
    """Central kill-switch; default OFF."""

    return resolve("PG_PROMPT_SCOPE_WEIGHTING").strip().lower() not in _OFF


def _field(row: Any, *names: str) -> Any:
    if isinstance(row, Mapping):
        for name in names:
            value = row.get(name)
            if value is not None:
                return value
        return None
    for name in names:
        value = getattr(row, name, None)
        if value is not None:
            return value
    return None


def _row_key(row: Any) -> str:
    return str(_field(row, "source_url", "url", "evidence_id") or "")


def _row_text(row: Any) -> str:
    return " ".join(
        str(_field(row, name) or "")
        for name in ("title", "source_title", "subject", "statement", "direct_quote", "snippet")
    )


def _tokens(text: str) -> frozenset[str]:
    return frozenset(
        token for token in _TOKEN_RE.findall(str(text or "").lower())
        if token not in _STOPWORDS
    )


def _phrases(constraints: Mapping[str, Any], field: str) -> list[str]:
    value = constraints.get(field)
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item) for item in value if str(item).strip()]
    return []


def has_weighting_constraints(constraints: Mapping[str, Any] | None) -> bool:
    """Whether the extracted prompt carries an evidence-scope signal."""

    if not isinstance(constraints, Mapping):
        return False
    return bool(
        _phrases(constraints, "source_types")
        or _phrases(constraints, "languages")
        or str(constraints.get("recency") or "").strip()
        or _phrases(constraints, "required_coverage")
        or _phrases(constraints, "exclusions")
    )


def _facet_weight(row: Any, constraints: Mapping[str, Any]) -> tuple[float, list[str]]:
    """Continuous prompt-facet overlap weight, never zero."""

    floor = demote_weight()
    row_tokens = _tokens(_row_text(row))
    requested = [_tokens(p) for p in _phrases(constraints, "required_coverage")]
    requested = [tokens for tokens in requested if tokens]
    excluded = [_tokens(p) for p in _phrases(constraints, "exclusions")]
    excluded = [tokens for tokens in excluded if tokens]
    weight = 1.0
    reasons: list[str] = []
    if requested:
        overlap = max(
            (len(row_tokens & phrase) / float(len(phrase)) for phrase in requested),
            default=0.0,
        )
        weight *= floor + (1.0 - floor) * overlap
        reasons.append(f"required_coverage_overlap={overlap:.6f}")
    if excluded:
        overlap = max(
            (len(row_tokens & phrase) / float(len(phrase)) for phrase in excluded),
            default=0.0,
        )
        if overlap:
            weight *= 1.0 - (1.0 - floor) * overlap
            reasons.append(f"exclusion_overlap={overlap:.6f}")
    return max(floor * floor, min(1.0, weight)), reasons


def _existing_prominence(row: Any) -> float:
    """Read the existing credibility/authority weight without inventing a tier prior."""

    for key in (
        "credibility_weight", "authority_score", "content_relevance_weight",
        "selection_relevance", "relevance_weight",
    ):
        value = _field(row, key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, min(1.0, float(value)))
    return 1.0


def weight_evidence_stream(
    evidence: list[dict[str, Any]],
    *,
    constraints: Mapping[str, Any] | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return every row in stable descending prompt/credibility order plus a ledger.

    There is deliberately no ``limit`` argument.  The count and multiset of evidence
    IDs are asserted unchanged; only order and additive weight sidecars differ.
    """

    rows = list(evidence or [])
    if not has_weighting_constraints(constraints):
        return rows, {
            "active": False,
            "reason": "no_prompt_scope_constraints",
            "input_count": len(rows),
            "output_count": len(rows),
            "rows": [],
        }
    assert isinstance(constraints, Mapping)
    eligibility = build_rq_eligibility_from_constraints(constraints, rows)
    weighted: list[tuple[float, int, dict[str, Any], dict[str, Any]]] = []
    for index, original in enumerate(rows):
        row = dict(original)
        key = _row_key(row)
        eligibility_weight = float(eligibility.url_to_eligibility_weight.get(key, 1.0))
        facet_weight, facet_reasons = _facet_weight(row, constraints)
        # Geometric combination preserves a continuous (0,1] scale without allowing
        # one axis to erase another or any row to reach zero.
        scope_weight = math.sqrt(max(0.000001, eligibility_weight * facet_weight))
        existing = _existing_prominence(row)
        composition_weight = existing * scope_weight
        reasons = list(facet_reasons)
        for record in eligibility.eligibility_records:
            if (record.get("source_url") or record.get("evidence_id")) == key:
                reasons.extend(str(reason) for reason in (record.get("reasons") or []))
        row["prompt_scope_weight"] = scope_weight
        row["composition_weight"] = composition_weight
        row["prompt_scope_reasons"] = reasons
        record = {
            "evidence_id": str(row.get("evidence_id") or ""),
            "source_url": str(row.get("source_url") or row.get("url") or ""),
            "input_index": index,
            "prompt_scope_weight": scope_weight,
            "existing_prominence_weight": existing,
            "composition_weight": composition_weight,
            "reasons": reasons,
        }
        weighted.append((composition_weight, index, row, record))

    weighted.sort(key=lambda item: (-item[0], item[1]))
    output = [item[2] for item in weighted]
    records = [item[3] for item in weighted]
    assert len(output) == len(rows)
    assert sorted(str(r.get("evidence_id") or "") for r in output) == sorted(
        str(r.get("evidence_id") or "") for r in rows
    )
    return output, {
        "active": True,
        "input_count": len(rows),
        "output_count": len(output),
        "constraints": dict(constraints),
        "rows": records,
    }


def scope_weight_for_candidate(
    candidate: Any,
    constraints: Mapping[str, Any] | None,
) -> float:
    """Prompt-derived candidate ordering weight; never an admission decision."""

    if not has_weighting_constraints(constraints):
        return 1.0
    assert isinstance(constraints, Mapping)
    plan = build_rq_eligibility_from_constraints(constraints, [candidate])
    key = _row_key(candidate)
    eligibility_weight = float(plan.url_to_eligibility_weight.get(key, 1.0))
    facet_weight, _ = _facet_weight(candidate, constraints)
    return math.sqrt(max(0.000001, eligibility_weight * facet_weight))


def bias_queries_by_prompt_scope(
    queries: list[str], constraints: Mapping[str, Any] | None,
) -> list[str]:
    """Carry the prompt's own scope phrases into every existing query, count unchanged."""

    if not has_weighting_constraints(constraints):
        return queries
    assert isinstance(constraints, Mapping)
    phrases = (
        _phrases(constraints, "source_types")
        + _phrases(constraints, "languages")
        + ([str(constraints.get("recency"))] if constraints.get("recency") else [])
    )
    phrases = [re.sub(r"[_\s]+", " ", p).strip() for p in phrases if p.strip()]
    if not phrases:
        return list(queries)
    out: list[str] = []
    for query in queries:
        low = str(query).lower()
        suffix = [phrase for phrase in phrases if phrase.lower() not in low]
        out.append(" ".join([str(query).strip(), *suffix]).strip())
    assert len(out) == len(queries)
    return out
