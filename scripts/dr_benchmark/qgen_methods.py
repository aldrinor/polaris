"""Query-gen method adapters for the coverage-isolation harness (I-qgen-001, GH #1291).

Each method's ONLY job: assemble the best corpus via the SHARED retrieve(). Methods decide
WHAT to search and WHICH retrieved rows to keep — they never transform evidence text
(common POLARIS code owns chunking/dedup/provenance downstream). Isolation: same retrieve()
for everyone, only the queries differ.

- FloorMethod: current POLARIS query-gen (question anchor + a fixed set of facet queries).
- ClosedLoopMethod: the frontier mechanism (WebWeaver/IterResearch family) — decompose the
  question into the method's OWN sub-points (never the gold rubrics), seed-retrieve, then
  gap-driven re-query. Uses an injected LLM (GLM-5.2 in a real run; stubbable in tests).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from scripts.dr_benchmark.qgen_coverage_harness import CoverageBudget, RetrieveFn

# (prompt) -> completion text. Wires GLM-5.2 in a real run; stubbable in unit tests.
LlmFn = Callable[[str], str]


def _dedup_keep(rows: list[dict], seen_urls: set[str]) -> list[dict]:
    """Keep rows with a new URL (common-code dedup, identical for every method)."""
    out: list[dict] = []
    for row in rows or []:
        url = (row.get("url") or "").strip()
        if url and url not in seen_urls:
            seen_urls.add(url)
            out.append(row)
    return out


@dataclass
class FloorMethod:
    """Current POLARIS query generation: the question anchor + a fixed list of facet queries.

    Open-loop / plan-once — exactly the behaviour the diagnosis flagged as two steps behind
    the frontier. This is the floor every candidate must beat.
    """

    facets: list[str] = field(default_factory=list)
    name: str = "floor_template_facets"

    def generate_corpus(
        self, question: str, retrieve: RetrieveFn, budget: CoverageBudget
    ) -> list[dict[str, str]]:
        seen: set[str] = set()
        corpus: list[dict[str, str]] = []
        for query in ([question] + list(self.facets))[: budget.max_queries]:
            corpus += _dedup_keep(retrieve(query), seen)
        return corpus


@dataclass
class ClosedLoopMethod:
    """Frontier closed loop: coverage-contract -> seed-retrieve -> gap-driven re-query.

    The method builds its OWN coverage contract by decomposing the question (it never sees
    the gold rubrics — that would be answer-key leakage). After seeding, it asks the LLM
    which sub-topics are still thin and re-queries for exactly those, up to the budget.
    """

    llm: LlmFn
    name: str = "closed_loop_gap_requery"

    def generate_corpus(
        self, question: str, retrieve: RetrieveFn, budget: CoverageBudget
    ) -> list[dict[str, str]]:
        seen: set[str] = set()
        corpus: list[dict[str, str]] = []
        # Budget is enforced by QUERIES ISSUED (not unique URLs) so every method competes
        # under the same query budget cap — a query that returns many or few URLs must not
        # change how many queries a method is allowed to spend (Codex iter-2 P1).
        queries_issued = 0

        contract = self._decompose(question)
        for query in [question] + contract:
            if queries_issued >= budget.max_queries:
                break
            corpus += _dedup_keep(retrieve(query), seen)
            queries_issued += 1

        for _ in range(budget.max_query_rounds):
            if queries_issued >= budget.max_queries:
                break
            gaps = self._find_gaps(question, contract, corpus)
            if not gaps:
                break
            for query in gaps:
                if queries_issued >= budget.max_queries:
                    break
                corpus += _dedup_keep(retrieve(query), seen)
                queries_issued += 1
        return corpus

    def _decompose(self, question: str) -> list[str]:
        raw = self.llm(
            "Decompose this research question into 6-10 specific sub-topics a COMPLETE "
            "answer must cover. Return ONE short search query per line, no numbering, no prose.\n\n"
            f"QUESTION:\n{question}"
        )
        return [ln.strip() for ln in (raw or "").splitlines() if ln.strip()][:10]

    def _find_gaps(
        self, question: str, contract: list[str], corpus: list[dict[str, str]]
    ) -> list[str]:
        retrieved = "\n".join(
            ((row.get("url") or "") + " " + (row.get("text") or "")[:120])
            for row in corpus[:60]
        )
        raw = self.llm(
            "Given the question, its sub-topics, and the sources retrieved so far, list up "
            "to 4 SHORT search queries for sub-topics still THIN or MISSING. One query per "
            "line, no numbering. If coverage is already adequate, return nothing.\n\n"
            f"QUESTION:\n{question}\n\nSUB-TOPICS:\n" + "\n".join(contract)
            + f"\n\nRETRIEVED SO FAR:\n{retrieved}"
        )
        return [ln.strip() for ln in (raw or "").splitlines() if ln.strip()][:4]
