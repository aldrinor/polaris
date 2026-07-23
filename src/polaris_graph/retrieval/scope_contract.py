"""Prompt-derived, pre-generation evidence scope contract.

The contract partitions a copied evidence pool immediately before composition:
semantic OFF-topic sources are excluded, and definitively wrong-type/language
sources are excluded only when the prompt states an exclusive constraint.  All
excluded rows remain in the caller's corpus and are returned as disclosure
records.  Unknown classifications and judge failures fail open.

This module has no retrieval client and no generator/verification dependency.
``deepen_scope_contract`` is the tested acquisition hook for retrieval runners;
prebuilt-corpus composers must not pretend they can deepen when they cannot
supply a real retrieval callable.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from src.polaris_graph.settings import resolve
from src.polaris_graph.retrieval.exclusive_citation_eligibility import (
    known_non_journal_surface,
)
from src.polaris_graph.retrieval.rq_eligibility import (
    DocumentType,
    _admitted_genres,
    _row_genre,
    _row_language,
    detect_language_offline,
)
from src.polaris_graph.retrieval.saturation import marginal_novelty
from src.polaris_graph.retrieval.topic_relevance_gate import (
    classify_topic_relevance,
)

_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})
_EXCLUSIVE_RE = re.compile(
    r"\b(?:only|exclusively|solely|restricted\s+to|limited\s+to|must\s+all\s+be)\b",
    re.IGNORECASE,
)


def scope_contract_enabled() -> bool:
    """Central default-ON composition contract flag."""
    return (resolve("PG_COMPOSITION_SCOPE_CONTRACT") or "").strip().lower() not in _OFF_VALUES


@dataclass
class ScopeContractResult:
    """One immutable-input partition plus complete exclusion telemetry."""

    evidence: list[dict[str, Any]] = field(default_factory=list)
    kept_original_indices: list[int] = field(default_factory=list)
    off_topic_excluded: list[dict[str, Any]] = field(default_factory=list)
    wrong_type_excluded: list[dict[str, Any]] = field(default_factory=list)
    judge_failed_open: bool = False
    constraints: dict[str, Any] = field(default_factory=dict)

    @property
    def excluded_count(self) -> int:
        return len(self.off_topic_excluded) + len(self.wrong_type_excluded)

    def disclosure(self) -> dict[str, Any]:
        return {
            "input_count": len(self.evidence) + self.excluded_count,
            "composition_evidence_count": len(self.evidence),
            "off_topic_excluded_count": len(self.off_topic_excluded),
            "wrong_type_excluded_count": len(self.wrong_type_excluded),
            "judge_failed_open": self.judge_failed_open,
            "constraints": dict(self.constraints),
            "off_topic_excluded": self.off_topic_excluded,
            "wrong_type_excluded": self.wrong_type_excluded,
            "excluded_from_composition_only": True,
            "source_corpus_retained": True,
        }


def _hard_exclusive(prompt: str, constraints: Mapping[str, Any], key: str) -> bool:
    """Conservative hard-constraint detector; soft preferences never filter."""
    explicit = constraints.get(f"{key}_exclusive")
    if explicit is not None:
        return bool(explicit)
    values = [str(v).strip().lower() for v in (constraints.get(key) or []) if str(v).strip()]
    if not values:
        return False
    # Require exclusivity and a source-citation context in the same sentence.
    for clause in re.split(r"(?<=[.!?;])\s+", prompt or ""):
        low = clause.lower()
        if not _EXCLUSIVE_RE.search(low):
            continue
        if key == "source_types" and re.search(
            r"\b(?:source|citation|cite|article|paper|journal|report|book|preprint|website|news)\w*\b",
            low,
        ):
            return True
        if key == "languages" and re.search(
            r"\b(?:language|english|spanish|french|german|chinese|japanese|arabic|korean)\w*\b",
            low,
        ):
            return True
    return False


def _row_key(row: Mapping[str, Any]) -> str:
    return str(row.get("evidence_id") or row.get("source_url") or row.get("url") or "")


def _record(row: Mapping[str, Any], reason: str, category: str) -> dict[str, Any]:
    return {
        "evidence_id": row.get("evidence_id", ""),
        "title": row.get("title") or row.get("statement") or row.get("source_title") or "",
        "url": row.get("source_url") or row.get("url") or "",
        "reason": reason,
        "category": category,
        "excluded_from_composition": True,
        "retained_in_source_corpus": True,
    }


def _confident_language(row: Mapping[str, Any]) -> str | None:
    language = _row_language(row)
    if language:
        return language
    text = " ".join(str(row.get(k) or "") for k in ("title", "statement", "snippet", "abstract"))
    return detect_language_offline(text)


def _wrong_type_reason(
    row: Mapping[str, Any],
    source_types: list[str],
    languages: list[str],
) -> str:
    reasons: list[str] = []
    admitted = _admitted_genres(source_types)
    if admitted is not None:
        genre = _row_genre(row)
        if genre != DocumentType.UNKNOWN and genre not in admitted:
            reasons.append(
                f"source_type: genre={genre.value} not in "
                f"{sorted(item.value for item in admitted)}"
            )
        elif genre == DocumentType.UNKNOWN and set(source_types) <= {"journal_article", "peer_reviewed"}:
            # The salvaged publication-surface classifier is a conservative
            # negative proof.  No venue-name allowlist and no UNKNOWN exclusion.
            if known_non_journal_surface(row):
                reasons.append("source_type: known non-journal publication surface")
    if languages:
        language = _confident_language(row)
        if language is not None and language not in languages:
            reasons.append(f"language: row={language} not in {languages}")
    return "; ".join(reasons)


def apply_scope_contract(
    rows: Sequence[Mapping[str, Any]],
    research_question: str,
    topic_judge: Callable[[str], str],
    *,
    constraints: Mapping[str, Any] | None = None,
) -> ScopeContractResult:
    """Return the citable composition pool without mutating ``rows``.

    Topic judging is semantic and explicit-exclusion mode.  Any judge exception
    or malformed batch fails open inside ``classify_topic_relevance``.  Type and
    language exclusions require both a hard prompt marker and a definitive row
    mismatch; UNKNOWN stays in the pool.
    """
    copied = [copy.deepcopy(dict(row)) for row in rows]
    if not scope_contract_enabled():
        return ScopeContractResult(evidence=copied, kept_original_indices=list(range(len(copied))))

    constraint_map = dict(constraints or {})
    try:
        topic = classify_topic_relevance(
            copied,
            research_question,
            topic_judge,
            # Ask the shared judge to retain/stamp its split verdicts, then
            # exclude only OFF_SUBJECT below.  The legacy hard-drop collapses
            # OFF_ASPECT into OFF and demonstrably thins topical breadth.
            exclude_offtopic=False,
        )
        topic_dropped = list(topic.off_subject_rows)
        dropped_ids = {id(row) for row in topic_dropped}
        topic_kept = [row for row in copied if id(row) not in dropped_ids]
        failed_open = bool(topic.n_failed_open_batches) or any(
            "fail-open" in note for note in topic.notes
        )
    except Exception:
        topic_kept, topic_dropped, failed_open = copied, [], True

    dropped_ids = {id(row) for row in topic_dropped}
    original_index_by_id = {id(row): index for index, row in enumerate(copied)}
    off_topic = [
        _record(row, "semantic_topic_judge: off-topic to research question", "off_topic")
        for row in topic_dropped
    ]

    source_types = [str(v).strip().lower() for v in constraint_map.get("source_types", []) if str(v).strip()]
    languages = [str(v).strip().lower()[:2] for v in constraint_map.get("languages", []) if str(v).strip()]
    if not _hard_exclusive(research_question, constraint_map, "source_types"):
        source_types = []
    if not _hard_exclusive(research_question, constraint_map, "languages"):
        languages = []

    kept: list[dict[str, Any]] = []
    kept_indices: list[int] = []
    wrong_type: list[dict[str, Any]] = []
    for row in topic_kept:
        reason = _wrong_type_reason(row, source_types, languages)
        if reason:
            wrong_type.append(_record(row, reason, "wrong_type"))
            continue
        kept.append(row)
        kept_indices.append(original_index_by_id[id(row)])

    # ``dropped_ids`` is deliberately computed to make the partition invariant
    # explicit and guard future refactors from accidentally re-admitting a row.
    assert not any(id(row) in dropped_ids for row in kept)
    return ScopeContractResult(
        evidence=kept,
        kept_original_indices=kept_indices,
        off_topic_excluded=off_topic,
        wrong_type_excluded=wrong_type,
        judge_failed_open=failed_open,
        constraints={
            **constraint_map,
            "source_types_exclusive": bool(source_types),
            "languages_exclusive": bool(languages),
        },
    )


def remap_finding_clusters(
    clusters: Sequence[Mapping[str, Any]], kept_original_indices: Sequence[int]
) -> list[dict[str, Any]]:
    """Copy and remap index-based finding baskets to the scoped evidence list."""
    remap = {old: new for new, old in enumerate(kept_original_indices)}
    output: list[dict[str, Any]] = []
    for cluster in clusters:
        all_members = [int(i) for i in (cluster.get("member_indices") or [])]
        old_members = [index for index in all_members if index in remap]
        if not old_members:
            continue
        copied = copy.deepcopy(dict(cluster))
        copied["member_indices"] = [remap[i] for i in old_members]
        old_rep = int(cluster.get("representative_index", old_members[0]))
        copied["representative_index"] = remap[old_rep] if old_rep in remap else remap[old_members[0]]
        copied["corroboration_count"] = len(old_members)
        hosts = list(cluster.get("member_hosts") or [])
        if len(hosts) == len(all_members):
            copied["member_hosts"] = [
                host for index, host in zip(all_members, hosts) if index in remap
            ]
        output.append(copied)
    return output


def remap_same_work_groups(
    groups: Sequence[Mapping[str, Any]],
    kept_original_indices: Sequence[int],
    kept_evidence_ids: set[str],
) -> list[dict[str, Any]]:
    """Copy and prune same-work metadata so excluded members cannot re-enter."""
    remap = {old: new for new, old in enumerate(kept_original_indices)}
    output: list[dict[str, Any]] = []
    for group in groups:
        copied = copy.deepcopy(dict(group))
        member_ids = [
            str(item) for item in (group.get("member_evidence_ids") or [])
            if str(item) in kept_evidence_ids
        ]
        if not member_ids:
            continue
        copied["member_evidence_ids"] = member_ids
        canonical = group.get("canonical_index")
        if isinstance(canonical, int) and canonical in remap:
            copied["canonical_index"] = remap[canonical]
        elif isinstance(canonical, int):
            copied.pop("canonical_index", None)
        output.append(copied)
    return output


def deepen_scope_contract(
    result: ScopeContractResult,
    research_question: str,
    retrieve_fn: Callable[[list[str], Mapping[str, Any]], Sequence[Mapping[str, Any]]],
    query_fn: Callable[[str, Mapping[str, Any]], list[str]] | None,
    topic_judge: Callable[[str], str],
    *,
    target_count: int,
    novelty_floor: float,
    max_rounds: int,
) -> ScopeContractResult:
    """Acquisition-run hook: add eligible rows until target or saturation.

    Every candidate is re-partitioned by both gates before it counts.  The hook
    never removes an already eligible row and never invents retrieval in a
    prebuilt-only caller.
    """
    current = result
    seen_rows: list[Mapping[str, Any]] = list(current.evidence)
    for _round in range(max(0, max_rounds)):
        if len(current.evidence) >= max(0, target_count):
            break
        queries = (query_fn or build_scope_deepening_queries)(
            research_question, current.constraints,
        )
        native_filters = {
            "source_types": list(current.constraints.get("source_types") or []),
            "languages": list(current.constraints.get("languages") or []),
            "is_retracted": False,
        }
        candidates = list(retrieve_fn(queries, native_filters) or [])
        if not candidates:
            break
        novelty = marginal_novelty(seen_rows, candidates)
        partition = apply_scope_contract(
            candidates, research_question, topic_judge, constraints=current.constraints,
        )
        known = {_row_key(row) for row in current.evidence}
        additions = [row for row in partition.evidence if _row_key(row) not in known]
        current.evidence.extend(additions)
        current.off_topic_excluded.extend(partition.off_topic_excluded)
        current.wrong_type_excluded.extend(partition.wrong_type_excluded)
        seen_rows.extend(candidates)
        if novelty < novelty_floor:
            break
    return current


def build_scope_deepening_queries(
    research_question: str,
    constraints: Mapping[str, Any],
) -> list[str]:
    """Prompt-derived additive queries for a retrieval-run deepening round.

    Reuses the general decomposer and the evidence-type expansion transform.
    Desired source types come only from the extracted prompt constraints; no
    task, venue, or topic list is embedded here.
    """
    from src.polaris_graph.retrieval.evidence_type_query_expansion import (  # noqa: PLC0415
        expand_evidence_type_queries,
    )
    from src.polaris_graph.retrieval.query_decomposer import (  # noqa: PLC0415
        decompose_question,
    )

    base = [research_question]
    base.extend(decompose_question(research_question))
    terms = [str(item).replace("_", " ") for item in constraints.get("source_types", [])]
    if not terms:
        return base
    return expand_evidence_type_queries(
        base,
        clinical=True,
        enabled=True,
        terms=terms,
    )
