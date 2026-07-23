"""Pre-generation, generator-judged contradiction discovery.

Candidate pairs come only from scoped evidence rows that share prompt-derived
content vocabulary or a reported measure.  The judge classifies the relationship
between the two supplied claims; only confident, comparable conflicts survive.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from src.polaris_graph.settings import resolve


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_TOKEN_RE = re.compile(r"[^\W\d_][\w'-]+", re.UNICODE)
_UNIT_RE = re.compile(r"(?:%|[A-Za-z]+(?:/[A-Za-z]+)?)")
_NUMBER_WITH_UNIT_RE = re.compile(
    r"[-+]?\d+(?:[.,]\d+)?\s*(%|[A-Za-z]+(?:/[A-Za-z]+)?)",
)
_STOPWORDS = frozenset({
    "about", "after", "also", "among", "and", "are", "because", "before",
    "between", "but", "can", "could", "during", "for", "from", "had", "has",
    "have", "into", "its", "may", "more", "not", "over", "reported", "study",
    "than", "that", "the", "their", "these", "this", "those", "through", "under",
    "using", "was", "were", "which", "while", "with", "within", "would",
})


def contradiction_mining_enabled() -> bool:
    """Return the central default-off switch at call time."""

    return (resolve("PG_CONTRADICTION_MINING") or "").strip().lower() in _TRUE_VALUES


def _row_text(row: Mapping[str, Any]) -> str:
    return " ".join(
        str(row.get(name) or "")
        for name in (
            "title", "source_title", "subject", "predicate", "measure", "metric",
            "endpoint", "population", "period", "statement", "direct_quote", "snippet",
        )
    ).strip()


def _row_tokens(row: Mapping[str, Any]) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _TOKEN_RE.findall(_row_text(row))
        if len(token) > 2 and token.casefold() not in _STOPWORDS
    )


def _row_measures(row: Mapping[str, Any]) -> frozenset[str]:
    declared = {
        str(row.get(name) or "").strip().casefold()
        for name in ("measure", "metric", "endpoint", "outcome")
        if str(row.get(name) or "").strip()
    }
    units = {
        match.group(1).casefold()
        for match in _NUMBER_WITH_UNIT_RE.finditer(_row_text(row))
        if _UNIT_RE.fullmatch(match.group(1))
    }
    return frozenset(declared | units)


def cluster_candidate_pairs(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return unique pairs sharing a discriminating term or reported measure.

    Term frequency is computed from this evidence pool, so no domain vocabulary
    is embedded. Each row uses its least-frequent repeated terms as cluster anchors.
    """

    copied = [dict(row) for row in rows]
    tokens = [_row_tokens(row) for row in copied]
    measures = [_row_measures(row) for row in copied]
    frequencies = Counter(token for row_tokens in tokens for token in row_tokens)
    anchors: list[frozenset[str]] = []
    for row_tokens in tokens:
        repeated = [token for token in row_tokens if frequencies[token] > 1]
        if not repeated:
            anchors.append(frozenset())
            continue
        minimum_frequency = min(frequencies[token] for token in repeated)
        anchors.append(frozenset(
            token for token in repeated if frequencies[token] == minimum_frequency
        ))
    row_count = len(copied)
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for left_index, left in enumerate(copied):
        for right_index in range(left_index + 1, row_count):
            shared_terms = anchors[left_index] & anchors[right_index]
            shared_measures = measures[left_index] & measures[right_index]
            if shared_terms or shared_measures:
                pairs.append((left, copied[right_index]))
    return pairs


def _judge_prompt(
    research_question: str,
    left: Mapping[str, Any],
    right: Mapping[str, Any],
) -> str:
    left_id = str(left.get("evidence_id") or left.get("source_url") or "row_a")
    right_id = str(right.get("evidence_id") or right.get("source_url") or "row_b")
    return f"""You are comparing two scoped evidence rows before a research report is written.

Research question:
{research_question}

Row A ({left_id}):
{_row_text(left)}

Row B ({right_id}):
{_row_text(right)}

Decide whether the rows make incompatible empirical claims about the SAME quantity or relationship.
Different populations, methods, periods, measures, endpoints, or observed-versus-modelled results
are not automatically conflicts. If the claims cannot be compared on the same basis, classify them
as non_comparable. If they can both be true, classify them as compatible.

Return one JSON object only:
{{
  "classification": "conflict" | "compatible" | "non_comparable",
  "confident": true | false,
  "reason": "one sentence stating the exact disagreement or comparability boundary",
  "subject": "shared subject",
  "predicate": "shared quantity or relationship",
  "measure": "shared measure, or empty string"
}}"""


def _parse_object(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def find_contradictions(
    rows: Sequence[Mapping[str, Any]],
    research_question: str,
    judge_fn: Callable[[str], str],
) -> list[dict[str, Any]]:
    """Judge candidate pairs and retain only confident comparable conflicts."""

    conflicts: list[dict[str, Any]] = []
    for left, right in cluster_candidate_pairs(rows):
        verdict = _parse_object(judge_fn(_judge_prompt(research_question, left, right)))
        if verdict.get("classification") != "conflict" or verdict.get("confident") is not True:
            continue
        left_id = str(left.get("evidence_id") or left.get("source_url") or "")
        right_id = str(right.get("evidence_id") or right.get("source_url") or "")
        reason = " ".join(str(verdict.get("reason") or "").split())
        if not left_id or not right_id or not reason:
            continue
        conflicts.append({
            "evidence_ids": [left_id, right_id],
            "subject": str(verdict.get("subject") or "").strip(),
            "predicate": str(verdict.get("predicate") or "").strip(),
            "measure": str(verdict.get("measure") or "").strip(),
            "reason": reason,
            "comparison_status": "conflict",
            "confidence": "confirmed",
        })
    return conflicts
