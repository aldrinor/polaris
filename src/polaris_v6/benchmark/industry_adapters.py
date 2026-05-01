"""Industry benchmark adapter shims (Phase 3 Task 3.7).

POLARIS v6 reports against three external research benchmarks:
- BrowseComp (Anthropic / xAI) — multi-hop browse + cite
- GAIA (Hugging Face) — general AI assistant evaluation
- DeepResearch Bench (community) — deep research synthesis

Each external benchmark publishes its own JSON record schema. This
module maps each into a common `IndustryRunRecord` so the Phase 3
benchmark runner can score POLARIS uniformly across all three.

Phase 0 ships the schema + a deterministic adapter for each format;
Phase 3 wires the actual benchmark question files (downloaded from
each benchmark's repo) and runs POLARIS against them.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

IndustryBenchmark = Literal["browsecomp", "gaia", "deepresearch_bench"]


class IndustryRunRecord(BaseModel):
    """Common schema across all three benchmarks."""

    benchmark: IndustryBenchmark
    question_id: str
    question_text: str = Field(..., min_length=4)
    expected_answer: str | None = None
    expected_citations: list[str] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


def adapt_browsecomp(raw: dict) -> IndustryRunRecord:
    """BrowseComp schema (per public spec): {id, prompt, target, sources}.

    Trust-only mapping: caller must validate the dict came from the
    BrowseComp release. We do not deep-validate the source URLs.
    """
    if "id" not in raw or "prompt" not in raw:
        raise ValueError("BrowseComp record requires 'id' and 'prompt'")
    return IndustryRunRecord(
        benchmark="browsecomp",
        question_id=str(raw["id"]),
        question_text=str(raw["prompt"]),
        expected_answer=str(raw.get("target")) if raw.get("target") else None,
        expected_citations=[str(s) for s in raw.get("sources", [])],
        metadata={"raw_keys": ",".join(sorted(raw.keys()))},
    )


def adapt_gaia(raw: dict) -> IndustryRunRecord:
    """GAIA schema: {Question, Final answer, Annotator Metadata, Level, file_name}."""
    if "Question" not in raw:
        raise ValueError("GAIA record requires 'Question'")
    return IndustryRunRecord(
        benchmark="gaia",
        question_id=str(raw.get("task_id") or raw.get("Question", "")[:32]),
        question_text=str(raw["Question"]),
        expected_answer=str(raw.get("Final answer")) if raw.get("Final answer") else None,
        expected_citations=[],
        metadata={
            "level": str(raw.get("Level", "")),
            "file_name": str(raw.get("file_name", "")),
        },
    )


def adapt_deepresearch_bench(raw: dict) -> IndustryRunRecord:
    """DeepResearch Bench schema: {question_id, query, reference_answer, ...}."""
    if "question_id" not in raw or "query" not in raw:
        raise ValueError("DeepResearch Bench record requires 'question_id' and 'query'")
    return IndustryRunRecord(
        benchmark="deepresearch_bench",
        question_id=str(raw["question_id"]),
        question_text=str(raw["query"]),
        expected_answer=str(raw.get("reference_answer")) if raw.get("reference_answer") else None,
        expected_citations=[str(s) for s in raw.get("reference_sources", [])],
        metadata={
            "domain": str(raw.get("domain", "")),
            "difficulty": str(raw.get("difficulty", "")),
        },
    )


_DISPATCH: dict[IndustryBenchmark, callable] = {
    "browsecomp": adapt_browsecomp,
    "gaia": adapt_gaia,
    "deepresearch_bench": adapt_deepresearch_bench,
}


def adapt(benchmark: IndustryBenchmark, raw: dict) -> IndustryRunRecord:
    if benchmark not in _DISPATCH:
        raise ValueError(f"unknown benchmark: {benchmark}")
    return _DISPATCH[benchmark](raw)
