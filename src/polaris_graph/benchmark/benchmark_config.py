"""Benchmark configuration loader for slice 005 head-to-head benchmark.

Per `.codex/slices/slice_005/architecture_proposal.md` §"benchmark_config".

Loads a fixture file like config/benchmark/clinical_n10.json containing
N benchmark questions plus per-question expected metadata used for
scoring (which PICO axes should be covered, whether the question is
refusal-bait, etc.).

The config is the contract between the architecture proposal's claims
and what `scripts/run_benchmark.py` actually exercises.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Type literals (mirror slice 001 / 003)
# ---------------------------------------------------------------------------

ScopeClassValue = Literal[
    "clinical_efficacy",
    "clinical_safety",
    "clinical_diagnosis",
    "clinical_prognosis",
    "out_of_scope",
]

PicoAxisName = Literal["population", "intervention", "outcome"]


# ---------------------------------------------------------------------------
# BenchmarkQuestion
# ---------------------------------------------------------------------------

class BenchmarkQuestion(BaseModel):
    """One benchmark question with expected metadata."""

    question_id: str = Field(min_length=1, max_length=100)
    question_text: str = Field(min_length=1, max_length=2000)
    scope_class: ScopeClassValue
    expected_pico_axes: list[PicoAxisName] = Field(
        default_factory=list,
        description=(
            "PICO axes that should be covered in the response for "
            "coverage_completeness scoring."
        ),
    )
    expected_pico_keywords: list[str] = Field(
        default_factory=list,
        description=(
            "Optional content keywords (lowercase substrings) checked "
            "against verified prose for coverage_completeness. When "
            "present, takes precedence over the literal axis names — "
            "e.g. ['adults', 'aspirin', 'migraine'] for an aspirin/migraine "
            "question. Empty list = scorer falls back to expected_pico_axes."
        ),
    )
    is_refusal_bait: bool = Field(
        default=False,
        description=(
            "True for instruction-override or out-of-domain questions. "
            "POLARIS auto-scores 1.0 if it correctly refuses; external "
            "systems scored by content heuristic."
        ),
    )
    notes: str = Field(
        default="",
        description="Free-form context for evaluators (not scored).",
    )

    @field_validator("question_id")
    @classmethod
    def _id_no_path_chars(cls, v: str) -> str:
        v = v.strip()
        if "/" in v or "\\" in v or ".." in v:
            raise ValueError(
                "question_id must not contain path separators or '..'"
            )
        return v

    @field_validator("expected_pico_axes")
    @classmethod
    def _axes_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("expected_pico_axes must be unique")
        return v


# ---------------------------------------------------------------------------
# BenchmarkConfig
# ---------------------------------------------------------------------------

class BenchmarkConfig(BaseModel):
    """Top-level config for one benchmark run."""

    benchmark_id: str = Field(min_length=1, max_length=100)
    benchmark_version: str = Field(default="1.0", max_length=20)
    description: str = Field(default="", max_length=1000)
    questions: list[BenchmarkQuestion] = Field(min_length=1, max_length=200)

    @field_validator("benchmark_id")
    @classmethod
    def _id_no_path_chars(cls, v: str) -> str:
        v = v.strip()
        if "/" in v or "\\" in v or ".." in v:
            raise ValueError("benchmark_id must not contain path separators")
        return v

    @field_validator("questions")
    @classmethod
    def _question_ids_unique(
        cls, v: list[BenchmarkQuestion]
    ) -> list[BenchmarkQuestion]:
        ids = [q.question_id for q in v]
        if len(set(ids)) != len(ids):
            duplicates = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(
                f"benchmark questions must have unique question_id; "
                f"duplicates: {duplicates}"
            )
        return v

    def question_ids(self) -> list[str]:
        return [q.question_id for q in self.questions]

    def question_by_id(self, question_id: str) -> BenchmarkQuestion | None:
        for q in self.questions:
            if q.question_id == question_id:
                return q
        return None

    def refusal_bait_count(self) -> int:
        return sum(1 for q in self.questions if q.is_refusal_bait)


def load_config(path: Path) -> BenchmarkConfig:
    """Load + validate a benchmark config from a JSON file."""
    with Path(path).open("r", encoding="utf-8") as f:
        data = json.load(f)
    return BenchmarkConfig.model_validate(data)
