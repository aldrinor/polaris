"""Crown Jewel I-cj-001 — Two-family evaluator invariant.

Per CLAUDE.md §9.1.1: generator and evaluator MUST be from different
training lineages. polaris_graph.llm.openrouter_client.check_family_
segregation raises RuntimeError at construction-time when violated.

These tests are the binding registry: a future PR that weakens the
segregation gate causes one of these tests to fail under a clearly
named 'test_cj_001_*' identifier.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.llm.openrouter_client import check_family_segregation


def test_cj_001_different_families_pass() -> None:
    gen, ev = check_family_segregation(
        generator_model="deepseek/deepseek-v3.2-exp",
        evaluator_model="qwen/qwen3-8b",
        generator_override="",
        evaluator_override="",
    )
    assert (gen, ev) == ("deepseek", "qwen")


def test_cj_001_same_family_raises() -> None:
    with pytest.raises(RuntimeError, match=r"same training-lineage family"):
        check_family_segregation(
            generator_model="qwen/qwen3-32b",
            evaluator_model="qwen/qwen3-8b",
            generator_override="",
            evaluator_override="",
        )


def test_cj_001_unknown_generator_without_override_raises() -> None:
    with pytest.raises(RuntimeError, match=r"generator model.*does not"):
        check_family_segregation(
            generator_model="unknown-vendor/some-model",
            evaluator_model="qwen/qwen3-8b",
            generator_override="",
            evaluator_override="",
        )


def test_cj_001_unknown_evaluator_without_override_raises() -> None:
    with pytest.raises(RuntimeError, match=r"evaluator model.*does not"):
        check_family_segregation(
            generator_model="deepseek/deepseek-v3.2-exp",
            evaluator_model="unknown-vendor/some-model",
            generator_override="",
            evaluator_override="",
        )


def test_cj_001_explicit_override_bypasses_unknown() -> None:
    gen, ev = check_family_segregation(
        generator_model="some-finetune/model",
        evaluator_model="another-finetune/model",
        generator_override="deepseek",
        evaluator_override="qwen",
    )
    assert (gen, ev) == ("deepseek", "qwen")
