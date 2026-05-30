"""Contract tests for the Judge (Qwen3.6) verdict parser + source_missing split.

Properties under test:
- each of the 5 canonical verdicts parses to itself;
- any non-enum token hard-FAILS (JudgeEnumError) with NO silent default;
- classify_unreachable enforces the LOCKED precedence (fabricated identity first).
Pure logic, no model, no network.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.benchmark.claim_audit_scorer import Verdict
from src.polaris_graph.roles.judge_contract import (
    JUDGE_CHOICES,
    JudgeEnumError,
    classify_unreachable,
    parse_judge_verdict,
)


# --- the 5-enum reuse + parsing ----------------------------------------------------
def test_judge_choices_is_the_canonical_five_enum() -> None:
    from typing import get_args

    assert JUDGE_CHOICES == list(get_args(Verdict))
    assert JUDGE_CHOICES == [
        "VERIFIED",
        "PARTIAL",
        "UNSUPPORTED",
        "FABRICATED",
        "UNREACHABLE",
    ]


@pytest.mark.parametrize(
    "token",
    ["VERIFIED", "PARTIAL", "UNSUPPORTED", "FABRICATED", "UNREACHABLE"],
)
def test_each_canonical_verdict_parses(token: str) -> None:
    assert parse_judge_verdict(token) == token


def test_surrounding_whitespace_tolerated() -> None:
    assert parse_judge_verdict("  VERIFIED  ") == "VERIFIED"
    assert parse_judge_verdict("\nFABRICATED\n") == "FABRICATED"


# --- hard-fail on any non-enum token (NO silent default) ---------------------------
@pytest.mark.parametrize(
    "raw",
    [
        "",                 # empty
        "   ",              # whitespace only
        "verified",         # lowercase (deliberately NOT case-folded)
        "Verified",         # mixed case
        "GROUNDED",         # wrong vocabulary
        "ENTAILED",         # entailment vocab, not judge vocab
        "VERIFIED.",        # trailing punctuation
        "yes",              # garbage
        "VERIFIED PARTIAL", # two tokens
        "the claim is verified",  # prose
    ],
)
def test_non_enum_token_raises_judge_enum_error(raw: str) -> None:
    with pytest.raises(JudgeEnumError):
        parse_judge_verdict(raw)


def test_non_string_raises_judge_enum_error() -> None:
    with pytest.raises(JudgeEnumError):
        parse_judge_verdict(None)  # type: ignore[arg-type]


# --- classify_unreachable: LOCKED precedence (fabricated identity FIRST) ------------
_POOL = ("doc_a", "doc_b", "doc_failed_fetch")


def test_absent_id_with_fetch_failure_is_fabricated_precedence() -> None:
    # P1-b precedence test: a fabricated id must NOT launder as a fetch failure.
    assert classify_unreachable("fetch_failure", "doc_never_selected", _POOL) == "FABRICATED"


def test_present_id_with_fetch_failure_is_unreachable() -> None:
    # genuine fetch failure for an in-pool (pre-fetch-selected) source.
    assert classify_unreachable("fetch_failure", "doc_failed_fetch", _POOL) == "UNREACHABLE"


@pytest.mark.parametrize("subtype", ["paywall", "robots", "fetch_failure"])
def test_present_id_each_fetch_miss_subtype_is_unreachable(subtype: str) -> None:
    assert classify_unreachable(subtype, "doc_a", _POOL) == "UNREACHABLE"


def test_none_citation_id_is_fabricated() -> None:
    assert classify_unreachable("fetch_failure", None, _POOL) == "FABRICATED"


def test_empty_citation_id_is_fabricated() -> None:
    assert classify_unreachable("paywall", "", _POOL) == "FABRICATED"


def test_in_pool_id_with_unknown_subtype_raises() -> None:
    # CONSCIOUS CONTRACT PIN (D8 + LAW II): `source_missing` is the bucket this classifier
    # SPLITS, not a verdict bucket — so feeding `source_missing` (or None/unknown) back in
    # with an in-pool id is a programming error and must fail LOUD, not silently default.
    # sub-PR-3's gate wiring must conform: it routes the fetch-miss subtypes here, never the
    # already-split `source_missing` label.
    with pytest.raises(ValueError):
        classify_unreachable("source_missing", "doc_a", _POOL)
    with pytest.raises(ValueError):
        classify_unreachable(None, "doc_a", _POOL)
