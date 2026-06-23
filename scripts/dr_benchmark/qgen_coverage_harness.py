"""Query-generation COVERAGE-ISOLATION harness (I-qgen-001, GH #1291).

Operator method (2026-06-22): test ONLY query generation, fast, no e2e. A query-gen
method's only job is COVERAGE — getting the right evidence into the corpus. So we measure
exactly that and nothing downstream:

    run the method's queries -> retrieve -> for each REQUIRED point (a DRB-II info_recall
    rubric) ask "is its evidence present in the retrieved corpus?" -> coverage fraction.

NO report generation, NO rendering, NO DeepTRACE judge here — those gate the faithfulness
sections + the final combined run. ISOLATION: every method sees the SAME retrieve() and the
SAME coverage judge(); only the queries differ. The canonical question is bound via
gate0_lineage so coverage is scored against the RIGHT rubrics (the drb_72 wrong-question fix).

retrieve() and judge() are injected (the runner wires POLARIS retrieval + the GLM-5.2 judge),
so this module is deterministic and unit-testable on stubs.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from scripts.dr_benchmark.gate0_lineage import (
    DEFAULT_TASKS_PATH,
    GateZeroLineageError,
    SLUG_TO_IDX,
    load_canonical_question,
)

# query -> list of evidence rows [{"url": str, "text": str}]. In a real run this is wrapped
# in a deterministic per-query snapshot cache so every method sees identical retrieval.
RetrieveFn = Callable[[str], list[dict[str, str]]]
# (required_point, corpus_text) -> True iff the corpus carries the evidence for the point.
CoverageJudgeFn = Callable[[str, str], bool]


def load_required_points(idx: int, tasks_path: str = DEFAULT_TASKS_PATH) -> list[str]:
    """The info_recall rubric points (the required evidence) for a canonical DRB-II idx.

    These are exactly what a complete corpus must let the report cover. Fail loud if the
    idx or its rubric is missing — never a silent empty list.
    """
    if not os.path.isfile(tasks_path):
        raise GateZeroLineageError(f"required-points: tasks file not found: {tasks_path}")
    with open(tasks_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("idx") == idx:
                rubric = (record.get("content") or {}).get("rubric") or {}
                points = rubric.get("info_recall")
                if not points:
                    raise GateZeroLineageError(
                        f"required-points: idx={idx} has no info_recall rubric"
                    )
                return [str(p) for p in points]
    raise GateZeroLineageError(f"required-points: idx={idx} not found in {tasks_path}")


def load_blocked_references(idx: int, tasks_path: str = DEFAULT_TASKS_PATH) -> dict | None:
    """The DRB-II BLOCKED reference for an idx (the source the report must NOT view/cite), or
    None if the task has none.

    DRB-II's blocked mechanism is what forces INDEPENDENT multi-source synthesis: a method that
    "covers" a point only via the forbidden source has cheated, and DRB-II scores that support as
    INVALID. So the harness must exclude the blocked source before scoring coverage. Shape in the
    gold file: ``{"title": str, "authors": [str], "urls": [str]}``. Raises only if the idx itself
    is absent (a bad idx); an absent blocked FIELD is legitimate -> None.
    """
    if not os.path.isfile(tasks_path):
        raise GateZeroLineageError(f"blocked-refs: tasks file not found: {tasks_path}")
    with open(tasks_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("idx") == idx:
                # Ground truth (verified idx 1-56): the blocked reference lives at content.blocked
                # (top-level 'blocked' is absent). We read content.blocked PRIMARY and fall back to
                # a top-level 'blocked' so the loader is correct under either layout — robust to any
                # row-format drift (Codex iter-3 flagged a top-level path; this makes the question moot).
                blocked = (record.get("content") or {}).get("blocked")
                if not (isinstance(blocked, dict) and blocked):
                    blocked = record.get("blocked")
                return blocked if isinstance(blocked, dict) and blocked else None
    raise GateZeroLineageError(f"blocked-refs: idx={idx} not found in {tasks_path}")


def _normalize_url(url: str) -> str:
    """Normalize a URL for blocked-source matching: drop scheme, leading www, trailing slash,
    query/fragment. Lossy on purpose so mirror URLs of the same paper still match."""
    u = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        if u.startswith(prefix):
            u = u[len(prefix) :]
    if u.startswith("www."):
        u = u[4:]
    u = u.split("#", 1)[0].split("?", 1)[0]
    return u.rstrip("/")


def make_blocked_filter(blocked: dict | None) -> Callable[[dict], bool]:
    """Return ``is_blocked(row) -> bool``: True iff a retrieved row is the forbidden source.

    Matches on URL (normalized, against every blocked mirror URL) OR on the blocked title
    appearing in the row text. No-op (always False) when there is no blocked reference.
    """
    if not blocked:
        return lambda row: False
    blocked_urls = {_normalize_url(u) for u in (blocked.get("urls") or []) if u}
    blocked_title = " ".join((blocked.get("title") or "").split()).lower()

    def is_blocked(row: dict) -> bool:
        url = _normalize_url(row.get("url") or "")
        if url and url in blocked_urls:
            return True
        text = " ".join((row.get("text") or "").split()).lower()
        if blocked_title and len(blocked_title) >= 20 and blocked_title in text:
            return True
        return False

    return is_blocked


@dataclass
class CoverageBudget:
    """Identical budget every method runs under (isolation: only query quality varies)."""

    max_query_rounds: int = field(
        default_factory=lambda: int(os.getenv("PG_QGEN_MAX_QUERY_ROUNDS", "4"))
    )
    max_queries: int = field(
        default_factory=lambda: int(os.getenv("PG_QGEN_MAX_QUERIES", "24"))
    )


@runtime_checkable
class QueryGenMethod(Protocol):
    """A query-generation method under test. Its ONLY job: assemble the best corpus.

    `name` identifies it; `generate_corpus` runs its (possibly iterative/closed-loop) query
    logic against the SHARED retrieve(), returning the assembled corpus. Methods may NOT
    summarize/transform evidence text (common code owns that downstream); they only choose
    WHAT to search and WHICH retrieved rows to keep.
    """

    name: str

    def generate_corpus(
        self, question: str, retrieve: RetrieveFn, budget: CoverageBudget
    ) -> list[dict[str, str]]: ...


@dataclass
class CoverageResult:
    method: str
    idx: int
    covered: int
    total: int
    coverage: float
    n_sources: int
    n_queries_issued: int
    per_point: list[dict[str, Any]]
    # Blocked (forbidden) rows this method retrieved and that were DROPPED before scoring — so a
    # method cannot win coverage via the prohibited DRB-II source. >0 means the method DID surface
    # the blocked source (telemetry; the rows were excluded from the corpus regardless).
    blocked_dropped: int = 0


def score_coverage(
    method_name: str,
    idx: int,
    required_points: list[str],
    corpus: list[dict[str, str]],
    judge: CoverageJudgeFn,
    n_queries_issued: int,
) -> CoverageResult:
    """Coverage = fraction of required points whose evidence is present in the corpus."""
    corpus_text = "\n\n".join((row.get("text") or "") for row in corpus)
    per_point: list[dict[str, Any]] = []
    covered = 0
    for point in required_points:
        is_covered = bool(judge(point, corpus_text))
        # Keep the FULL rubric point (not truncated) so the §-1.1 audit can read exactly which
        # required point was/was not covered; a short preview rides alongside for skim-reading.
        per_point.append(
            {"point": point, "point_preview": point[:160], "covered": is_covered}
        )
        if is_covered:
            covered += 1
    total = len(required_points)
    return CoverageResult(
        method=method_name,
        idx=idx,
        covered=covered,
        total=total,
        coverage=(covered / total) if total else 0.0,
        n_sources=len(corpus),
        n_queries_issued=n_queries_issued,
        per_point=per_point,
    )


def run_coverage_test(
    idx: int,
    methods: list[QueryGenMethod],
    retrieve: RetrieveFn,
    judge: CoverageJudgeFn,
    budget: CoverageBudget | None = None,
    tasks_path: str = DEFAULT_TASKS_PATH,
    blocked_refs: dict | None = None,
) -> list[CoverageResult]:
    """Run every method on the canonical question, score coverage, return ranked results.

    The canonical question + required points come straight from the gold file (gate0_lineage),
    so the wrong-question failure cannot recur. Every method gets the SAME retrieve()/judge().

    blocked_refs (the DRB-II forbidden source, via load_blocked_references): when provided, any
    retrieved row matching it is DROPPED before it can reach a method's corpus — uniformly for
    every method — so coverage cannot be won by retrieving the prohibited source (Codex iter-2 P1).
    """
    budget = budget or CoverageBudget()
    question = load_canonical_question(idx, tasks_path)
    required_points = load_required_points(idx, tasks_path)
    is_blocked = make_blocked_filter(blocked_refs)

    results: list[CoverageResult] = []
    for method in methods:
        counting_retrieve, counter = _counting(retrieve)
        blocked_count = {"n": 0}

        def blocked_filtered(query: str, _cr=counting_retrieve, _bc=blocked_count):
            kept: list[dict[str, str]] = []
            for row in _cr(query):
                if is_blocked(row):
                    _bc["n"] += 1  # forbidden source: count it, never let it into the corpus
                else:
                    kept.append(row)
            return kept

        corpus = method.generate_corpus(question, blocked_filtered, budget)
        result = score_coverage(
            method.name, idx, required_points, corpus, judge, counter["n"]
        )
        result.blocked_dropped = blocked_count["n"]
        results.append(result)
    results.sort(key=lambda r: r.coverage, reverse=True)
    return results


def _counting(retrieve: RetrieveFn) -> tuple[RetrieveFn, dict[str, int]]:
    """Wrap retrieve() to count how many queries a method issued (isolation telemetry)."""
    counter = {"n": 0}

    def wrapped(query: str) -> list[dict[str, str]]:
        counter["n"] += 1
        return retrieve(query)

    return wrapped, counter
