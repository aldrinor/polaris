"""Prompt-derived, pre-generation evidence scope contract.

The contract partitions a copied evidence pool immediately before composition:
semantic OFF-topic sources are excluded, and definitively wrong-type/language
sources are excluded only when the prompt states an exclusive constraint. All
excluded rows remain in the caller's corpus and are returned as disclosure
records. Topic-judge failures fail open; unresolved document types fail closed
only for an explicit exclusive document-type constraint.

This module has no retrieval client and no generator/verification dependency.
``deepen_scope_contract`` is the tested acquisition hook for retrieval runners;
prebuilt-corpus composers must not pretend they can deepen when they cannot
supply a real retrieval callable.
"""
from __future__ import annotations

import copy
import re
import time
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
from src.polaris_graph.retrieval.topic_relevance_gate import (
    classify_topic_relevance,
)

_OFF_VALUES = frozenset({"0", "false", "no", "off", "disabled", ""})
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_EXCLUSIVE_RE = re.compile(
    r"\b(?:only|exclusively|solely|restricted\s+to|limited\s+to|must\s+all\s+be)\b",
    re.IGNORECASE,
)


def scope_contract_enabled() -> bool:
    """Central default-ON composition contract flag."""
    return (resolve("PG_COMPOSITION_SCOPE_CONTRACT") or "").strip().lower() not in _OFF_VALUES


def scope_deepening_enabled() -> bool:
    """Central default-off live-deepening flag."""

    return (resolve("PG_SCOPE_DEEPENING") or "").strip().lower() in _TRUE_VALUES


@dataclass
class ScopeContractResult:
    """One immutable-input partition plus complete exclusion telemetry."""

    evidence: list[dict[str, Any]] = field(default_factory=list)
    kept_original_indices: list[int] = field(default_factory=list)
    off_topic_excluded: list[dict[str, Any]] = field(default_factory=list)
    wrong_type_excluded: list[dict[str, Any]] = field(default_factory=list)
    judge_failed_open: bool = False
    constraints: dict[str, Any] = field(default_factory=dict)
    deepening: dict[str, Any] = field(default_factory=dict)

    @property
    def excluded_count(self) -> int:
        return len(self.off_topic_excluded) + len(self.wrong_type_excluded)

    def disclosure(self) -> dict[str, Any]:
        payload = {
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
        if self.deepening:
            payload["deepening"] = dict(self.deepening)
        return payload


def _hard_exclusive(prompt: str, constraints: Mapping[str, Any], key: str) -> bool:
    """Conservative hard-constraint detector; soft preferences never filter."""
    explicit = constraints.get(f"{key}_exclusive")
    if explicit is not None:
        return bool(explicit)
    values = [str(v).strip().lower() for v in (constraints.get(key) or []) if str(v).strip()]
    if not values:
        return False
    # Require exclusivity and the extracted value or its dimension in the same
    # sentence. The values are the vocabulary; no anticipated language/org list.
    for clause in re.split(r"(?<=[.!?;])\s+", prompt or ""):
        low = clause.lower()
        if not _EXCLUSIVE_RE.search(low):
            continue
        surfaces = {
            form
            for value in values
            for form in (
                value,
                value.replace("_", " "),
                value.replace("_", "-"),
            )
            if form
        }
        mentions_value = any(surface in low for surface in surfaces)
        if key == "source_types" and (
            mentions_value
            or re.search(r"\b(?:source|citation|cite|document|publication)\w*\b", low)
        ):
            return True
        if key == "languages" and (
            mentions_value or re.search(r"\blanguage\b", low)
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
        elif genre == DocumentType.UNKNOWN:
            if known_non_journal_surface(row):
                reasons.append("source_type: known non-journal publication surface")
            else:
                reasons.append(
                    "source_type: unresolved under exclusive document-type constraint"
                )
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
    mismatch. An UNKNOWN document type is archived rather than cited only under
    an explicit exclusive document-type constraint.
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

    source_types = [
        str(v).strip().lower()
        for v in constraint_map.get("source_types", [])
        if str(v).strip()
    ]
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
    query_fn: Callable[..., list[str]] | None,
    topic_judge: Callable[[str], str],
    *,
    wall_seconds: float | None = None,
    novelty_judge: Callable[[str], str] | None = None,
) -> ScopeContractResult:
    """Add eligible works until semantic novelty or the disclosed wall is exhausted.

    Every candidate re-passes topic and exclusive-type/language admission before
    canonical-work dedup. A round that adds no new proposition, relationship,
    population, or timeframe ends the loop; there is no evidence-count target.
    """

    from src.polaris_graph.synthesis.finding_dedup import _same_work_key  # noqa: PLC0415

    current = result
    started = time.monotonic()
    deadline = (
        started + max(0.0, float(wall_seconds))
        if wall_seconds is not None else None
    )
    seen_signatures = {
        signature
        for row in current.evidence
        for signature in _semantic_signatures(row)
    }
    seen_semantic_rows = list(current.evidence)
    known_works = {
        _same_work_key(dict(row)) or f"row:{_row_key(row) or id(row)}"
        for row in current.evidence
    }
    rounds = 0
    added_works = 0
    stop_reason = "novelty_exhausted"
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            stop_reason = "wall_budget"
            break
        builder = query_fn or build_scope_deepening_queries
        try:
            queries = builder(research_question, current.constraints, current.evidence)
        except TypeError:
            queries = builder(research_question, current.constraints)
        if not queries:
            stop_reason = "no_gap_queries"
            break
        native_filters = {
            "source_types": list(current.constraints.get("source_types") or []),
            "languages": list(current.constraints.get("languages") or []),
            "is_retracted": False,
        }
        candidates = list(retrieve_fn(queries, native_filters) or [])
        rounds += 1
        if not candidates:
            stop_reason = "retrieval_exhausted"
            break
        partition = apply_scope_contract(
            candidates, research_question, topic_judge, constraints=current.constraints,
        )
        additions: list[dict[str, Any]] = []
        round_signatures: set[str] = set()
        for row in partition.evidence:
            work_key = _same_work_key(dict(row)) or f"row:{_row_key(row) or id(row)}"
            if work_key in known_works:
                continue
            known_works.add(work_key)
            additions.append(row)
            round_signatures.update(_semantic_signatures(row))
        novel_signatures = round_signatures - seen_signatures
        has_novelty = bool(novel_signatures)
        if has_novelty and novelty_judge is not None:
            has_novelty = _judge_semantic_novelty(
                seen_semantic_rows,
                additions,
                novelty_judge,
            )
        current.evidence.extend(additions)
        added_works += len(additions)
        current.off_topic_excluded.extend(partition.off_topic_excluded)
        current.wrong_type_excluded.extend(partition.wrong_type_excluded)
        seen_signatures.update(round_signatures)
        seen_semantic_rows.extend(additions)
        if not has_novelty:
            stop_reason = "novelty_exhausted"
            break
    current.deepening = {
        "rounds": rounds,
        "added_canonical_works": added_works,
        "stop_reason": stop_reason,
        "wall_seconds": wall_seconds,
        "elapsed_seconds": time.monotonic() - started,
    }
    return current


def build_scope_deepening_queries(
    research_question: str,
    constraints: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]] | None = None,
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

    facets = list(dict.fromkeys(
        query for query in decompose_question(research_question) if str(query).strip()
    ))
    base = [research_question]
    if facets:
        if evidence:
            row_tokens = [
                set(_semantic_tokens(" ".join(str(value) for value in row.values())))
                for row in evidence
            ]
            coverage = {
                facet: sum(
                    bool(set(_semantic_tokens(facet)) & tokens)
                    for tokens in row_tokens
                )
                for facet in facets
            }
            thinnest = min(coverage.values())
            base.extend(facet for facet in facets if coverage[facet] == thinnest)
        else:
            base.extend(facets)
    obligations = (
        constraints.get("required_coverage")
        or constraints.get("coverage_obligations")
        or []
    )
    for obligation in obligations:
        if isinstance(obligation, Mapping):
            text = str(
                obligation.get("concept")
                or obligation.get("text")
                or obligation.get("requirement")
                or ""
            ).strip()
        else:
            text = str(obligation or "").strip()
        if text:
            base.append(f"{research_question} {text}")
    base = list(dict.fromkeys(base))
    schema = constraints.get("research_schema") or constraints.get("retrieval_frame") or {}
    evidence_needs = (
        schema.get("evidence_needs", [])
        if isinstance(schema, Mapping)
        else []
    )
    terms = [
        str(item).replace("_", " ")
        for item in [
            *(constraints.get("source_types", []) or []),
            *(evidence_needs or []),
        ]
        if str(item).strip()
    ]
    if not terms:
        return base
    return expand_evidence_type_queries(
        base,
        apply_to_frame=True,
        enabled=True,
        terms=terms,
    )


_SEMANTIC_TOKEN_RE = re.compile(r"[^\W_][\w'-]+", re.UNICODE)
_SEMANTIC_STOPWORDS = frozenset({
    "about", "also", "and", "are", "for", "from", "has", "have", "into",
    "study", "that", "the", "their", "these", "this", "those", "using",
    "was", "were", "which", "with",
})


def _semantic_tokens(text: str) -> tuple[str, ...]:
    return tuple(sorted({
        token.casefold()
        for token in _SEMANTIC_TOKEN_RE.findall(str(text or ""))
        if len(token) > 2 and token.casefold() not in _SEMANTIC_STOPWORDS
    }))


def _semantic_signatures(row: Mapping[str, Any]) -> set[str]:
    """Evidence-derived novelty units for gap-loop saturation."""

    signatures: set[str] = set()
    field_groups = {
        "proposition": ("proposition", "claim_text", "statement", "direct_quote", "snippet"),
        "relation": ("predicate", "relationship", "association", "effect"),
        "population": ("population", "sample", "cohort"),
        "timeframe": ("timeframe", "period", "date_range", "publication_date", "year"),
    }
    for label, names in field_groups.items():
        value = next(
            (
                str(row.get(name) or "").strip()
                for name in names
                if str(row.get(name) or "").strip()
            ),
            "",
        )
        tokens = _semantic_tokens(value)
        if tokens:
            signatures.add(f"{label}:{' '.join(tokens)}")
    return signatures


def _judge_semantic_novelty(
    seen_rows: Sequence[Mapping[str, Any]],
    additions: Sequence[Mapping[str, Any]],
    judge_fn: Callable[[str], str],
) -> bool:
    """Return False only when the model confidently reports no new semantic unit."""

    if not additions:
        return False

    def _render(rows: Sequence[Mapping[str, Any]]) -> str:
        lines: list[str] = []
        for row in rows:
            values = [
                str(row.get(name) or "").strip()
                for name in (
                    "proposition", "claim_text", "statement", "predicate", "relationship",
                    "population", "sample", "cohort", "timeframe", "period", "date_range",
                )
                if str(row.get(name) or "").strip()
            ]
            if values:
                lines.append(" | ".join(values))
        return "\n".join(lines)

    prompt = f"""Compare the admitted evidence from earlier acquisition rounds with the newly
admitted canonical works. Decide whether the new works add at least one genuinely NEW proposition,
relationship, population, or timeframe. A paraphrase, repeated estimate, or additional source for
an existing proposition is corroboration, not semantic novelty.

Earlier admitted evidence:
{_render(seen_rows)}

Newly admitted canonical works:
{_render(additions)}

Return exactly NOVEL if at least one new semantic unit exists.
Return exactly EXHAUSTED if every new row only repeats or paraphrases existing semantic units."""
    try:
        verdict = str(judge_fn(prompt) or "").strip().upper()
    except Exception:
        return True
    if verdict == "EXHAUSTED":
        return False
    return True
