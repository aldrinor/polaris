"""Tests for cross-section fact-dedup pass — GH#423 I-gen-002.

Covers:
- extract_signature: percentages, dollar amounts, years, units, edge cases.
- build_groups: cross-section grouping, intra-section ignored, empty-sig ignored.
- apply_rewrites: replace/drop semantics.
- rewrite_redundant_sentences: fallback when LLM call fails or returns garbage.
- dedup_pass: end-to-end with mocked LLM.

Based on actual Q5 Pharmacare redundancy patterns surfaced by Tier-1 pilot
(PR #421 GH#420 reconciliation):
  - 4× regressivity (3%/1.6%/0.7%) across 4 sections
  - 3× OOP 2007 (8.7%/4.8%) across 3 sections
  - 2× age 55-64 (9.2%/13.9%) across 2 sections
"""
from __future__ import annotations

from typing import Any

import pytest

from src.polaris_graph.generator.fact_dedup import (
    FactSignature,
    apply_rewrites,
    build_groups,
    count_redundancy,
    dedup_pass,
    extract_signature,
    rewrite_redundant_sentences,
)


# ─────────────────────────────────────────────────────────────────────────
# extract_signature
# ─────────────────────────────────────────────────────────────────────────


def test_extract_signature_handles_percentages() -> None:
    sig = extract_signature(
        "8.7% of Quebec households incurred more than $1000 in 2007 [ev_X]."
    )
    assert 8.7 in sig.decimals
    assert 2007 in sig.years


def test_extract_signature_handles_dollar_amounts_billions() -> None:
    sig = extract_signature(
        "PBO estimated $11.2 billion in 2024-25 increasing to $13.4 billion [ev_X]."
    )
    # Both values should produce dollar buckets
    assert len(sig.dollar_buckets) >= 1


def test_extract_signature_handles_multiple_percentages() -> None:
    sig = extract_signature(
        "more than 3% for $40,000 households, 1.6% at $80,000, "
        "0.7% above $180,000 [ev_X]."
    )
    assert 3.0 in sig.decimals or 3 in sig.decimals
    assert 1.6 in sig.decimals
    assert 0.7 in sig.decimals


def test_extract_signature_empty_for_no_numbers() -> None:
    sig = extract_signature("The premiums are regressive [ev_X].")
    assert sig.is_empty()


def test_extract_signature_handles_per_cent_spelling() -> None:
    sig = extract_signature("more than three per cent of $40,000 income [ev_X].")
    # "three per cent" written out won't match numeric regex; that's
    # expected — the dedup catches numeric tokens only.
    # The dollar amount $40,000 should be picked up.
    assert len(sig.dollar_buckets) >= 1


def test_extract_signature_handles_usd_prefix() -> None:
    sig = extract_signature(
        "industry committed USD 299 million (CAD 409 million) [ev_X]."
    )
    # USD 299M + CAD 409M => 2 buckets (different amounts)
    assert len(sig.dollar_buckets) >= 1


def test_extract_signature_normalizes_billion_to_million_units() -> None:
    sig_b = extract_signature("$11.2 billion in 2024-25 [ev_X].")
    sig_m = extract_signature("$11200 million in 2024-25 [ev_X].")
    # Both should round to the same dollar bucket
    assert sig_b.dollar_buckets == sig_m.dollar_buckets


# ─────────────────────────────────────────────────────────────────────────
# build_groups
# ─────────────────────────────────────────────────────────────────────────


def test_build_groups_detects_cross_section_duplicate() -> None:
    sections = {
        "Efficacy": [
            "The premium is more than 3% for $40,000 and 1.6% at $80,000 [ev_X].",
        ],
        "Comparative": [
            "Burden is regressive: more than 3% for $40,000 vs 1.6% at $80,000 [ev_Y].",
        ],
    }
    groups = build_groups(sections)
    assert len(groups) == 1
    assert groups[0].primary.section == "Efficacy"
    assert len(groups[0].redundants) == 1
    assert groups[0].redundants[0].section == "Comparative"


def test_build_groups_respects_section_order_for_primary() -> None:
    sections = {
        "Comparative": ["8.7% in 2007 [ev_X]."],
        "Efficacy": ["8.7% in 2007 [ev_Y]."],
    }
    # Explicit order: Efficacy first
    groups = build_groups(sections, section_order=["Efficacy", "Comparative"])
    assert len(groups) == 1
    assert groups[0].primary.section == "Efficacy"


def test_build_groups_ignores_intra_section_repetition() -> None:
    sections = {
        "Efficacy": [
            "8.7% in 2007 [ev_X].",
            "8.7% in 2007 again [ev_Y].",
        ],
    }
    # Both sentences in same section — not cross-section, not a group
    groups = build_groups(sections)
    assert len(groups) == 0


def test_build_groups_ignores_empty_signature() -> None:
    sections = {
        "Efficacy": ["The premiums are regressive [ev_X]."],
        "Comparative": ["The premiums are regressive [ev_Y]."],
    }
    groups = build_groups(sections)
    assert len(groups) == 0  # no numeric content; not deduplicated


def test_build_groups_q5_realistic_pattern() -> None:
    """Q5 Pharmacare actual redundancy pattern: 4× regressivity fact."""
    common = (
        "The premium is more than 3% for $40,000, "
        "1.6% at $80,000, and 0.7% or less above $180,000"
    )
    sections = {
        "Efficacy": [f"{common} [ev_000][ev_019]."],
        "Comparative": [f"Regressive: {common} [ev_000][ev_002]."],
        "Population Subgroups": [f"{common} [ev_000]."],
        "Long-term Outcomes": [f"For example, {common} [ev_000]."],
    }
    groups = build_groups(
        sections,
        section_order=[
            "Efficacy", "Comparative",
            "Population Subgroups", "Long-term Outcomes",
        ],
    )
    assert len(groups) == 1
    assert groups[0].primary.section == "Efficacy"
    assert len(groups[0].redundants) == 3
    redundant_sections = [r.section for r in groups[0].redundants]
    assert "Comparative" in redundant_sections
    assert "Population Subgroups" in redundant_sections
    assert "Long-term Outcomes" in redundant_sections


def test_count_redundancy() -> None:
    common = "8.7% in 2007"
    sections = {
        "Efficacy": [f"{common} [ev_X]."],
        "Comparative": [f"{common} [ev_X]."],
        "Long-term Outcomes": [f"{common} [ev_X]."],
    }
    groups = build_groups(sections)
    assert count_redundancy(groups) == 2  # 3 instances, 2 redundant


# ─────────────────────────────────────────────────────────────────────────
# apply_rewrites
# ─────────────────────────────────────────────────────────────────────────


def test_apply_rewrites_replaces_sentence() -> None:
    sections = {
        "Comparative": ["8.7% in 2007 [ev_X].", "Other claim [ev_Y]."],
    }
    rewrites = {("Comparative", 0): "as noted under Efficacy [ev_X]."}
    new_sections = apply_rewrites(sections, rewrites)
    assert new_sections["Comparative"][0] == "as noted under Efficacy [ev_X]."
    assert new_sections["Comparative"][1] == "Other claim [ev_Y]."


def test_apply_rewrites_drops_on_none() -> None:
    sections = {
        "Comparative": ["8.7% in 2007 [ev_X].", "Other claim [ev_Y]."],
    }
    rewrites = {("Comparative", 0): None}
    new_sections = apply_rewrites(sections, rewrites)
    # First sentence dropped; second stays
    assert len(new_sections["Comparative"]) == 1
    assert new_sections["Comparative"][0] == "Other claim [ev_Y]."


def test_apply_rewrites_untouched_when_no_rewrites() -> None:
    sections = {"Efficacy": ["original [ev_X]."]}
    new_sections = apply_rewrites(sections, {})
    assert new_sections == sections


# ─────────────────────────────────────────────────────────────────────────
# rewrite_redundant_sentences — failure handling
# ─────────────────────────────────────────────────────────────────────────


class _FakeLLM:
    """Async LLM stub returning a fixed string."""
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, system: str, prompt: str) -> Any:
        self.calls.append((system, prompt))

        class _Response:
            def __init__(self, c: str) -> None:
                self.content = c

        return _Response(self.content)


@pytest.mark.asyncio
async def test_rewrite_falls_back_to_drop_on_invalid_json() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    groups = build_groups(sections)
    fake_llm = _FakeLLM("not valid json at all")
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    # 1 redundant; rewrite invalid → fallback drop (None)
    assert len(rewrites) == 1
    assert all(v is None for v in rewrites.values())


@pytest.mark.asyncio
async def test_rewrite_falls_back_on_wrong_shape() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    groups = build_groups(sections)
    # Returns valid JSON but wrong shape (rewrites is a string not list)
    fake_llm = _FakeLLM('{"rewrites": "not a list"}')
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    assert all(v is None for v in rewrites.values())


@pytest.mark.asyncio
async def test_rewrite_falls_back_on_count_mismatch() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
        "Regulatory": ["8.7% in 2007 [ev_Z]."],
    }
    groups = build_groups(sections)
    # 2 redundants expected, only 1 returned
    fake_llm = _FakeLLM('{"rewrites": ["only one rewrite [ev_Y]."]}')
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    assert all(v is None for v in rewrites.values())


@pytest.mark.asyncio
async def test_rewrite_applies_valid_rewrites() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    groups = build_groups(sections)
    fake_llm = _FakeLLM(
        '{"rewrites": ["see Efficacy section [ev_Y]."]}'
    )
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    assert len(rewrites) == 1
    val = next(iter(rewrites.values()))
    assert val == "see Efficacy section [ev_Y]."


@pytest.mark.asyncio
async def test_rewrite_handles_null_per_item() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
        "Regulatory": ["8.7% in 2007 [ev_Z]."],
    }
    groups = build_groups(sections)
    # 2 redundants; LLM rewrites first as valid, returns null for second
    fake_llm = _FakeLLM(
        '{"rewrites": ["see Efficacy [ev_Y].", null]}'
    )
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    values = list(rewrites.values())
    assert "see Efficacy [ev_Y]." in values
    assert None in values


@pytest.mark.asyncio
async def test_rewrite_handles_code_fence_wrapped_json() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    groups = build_groups(sections)
    fake_llm = _FakeLLM(
        '```json\n{"rewrites": ["see Efficacy [ev_Y]."]}\n```'
    )
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    val = next(iter(rewrites.values()))
    assert val == "see Efficacy [ev_Y]."


# ─────────────────────────────────────────────────────────────────────────
# dedup_pass — end-to-end
# ─────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dedup_pass_q5_pattern_end_to_end() -> None:
    """Q5-style 4× redundancy: dedup should rewrite 3 sentences."""
    common = (
        "Premiums of more than 3% for $40,000 and 1.6% at $80,000"
    )
    sections = {
        "Efficacy": [f"{common} [ev_000][ev_019]."],
        "Comparative": [f"Regressive: {common} [ev_000][ev_002]."],
        "Population Subgroups": [f"{common} [ev_000]."],
        "Long-term Outcomes": [f"For example, {common} [ev_000]."],
    }
    fake_llm = _FakeLLM(
        '{"rewrites": ['
        '"Regressivity by income is detailed under Efficacy [ev_002].",'
        '"See Efficacy section [ev_000].",'
        '"As noted under Efficacy [ev_000]."'
        ']}'
    )
    new_sections, telemetry = await dedup_pass(
        sections, fake_llm,
        section_order=[
            "Efficacy", "Comparative",
            "Population Subgroups", "Long-term Outcomes",
        ],
    )
    assert telemetry["n_groups"] == 1
    assert telemetry["n_redundants"] == 3
    assert telemetry["n_rewrites_applied"] == 3
    assert telemetry["n_drops"] == 0
    # Efficacy unchanged (PRIMARY)
    assert new_sections["Efficacy"] == [f"{common} [ev_000][ev_019]."]
    # Three redundants rewritten
    assert "detailed under Efficacy" in new_sections["Comparative"][0]
    assert "See Efficacy" in new_sections["Population Subgroups"][0]
    assert "As noted under Efficacy" in new_sections["Long-term Outcomes"][0]


@pytest.mark.asyncio
async def test_dedup_pass_safe_drop_on_llm_failure() -> None:
    """If rewrite call fails, redundants are dropped (PRIMARY kept)."""
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    fake_llm = _FakeLLM("garbage response")
    new_sections, telemetry = await dedup_pass(sections, fake_llm)
    assert telemetry["n_drops"] == 1
    assert telemetry["n_rewrites_applied"] == 0
    assert new_sections["Efficacy"] == ["8.7% in 2007 [ev_X]."]
    assert new_sections["Comparative"] == []  # redundant dropped


@pytest.mark.asyncio
async def test_dedup_pass_returns_unchanged_when_no_duplicates() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["No numbers here [ev_Y]."],
    }
    fake_llm = _FakeLLM("should not be called")
    new_sections, telemetry = await dedup_pass(sections, fake_llm)
    assert telemetry["n_groups"] == 0
    assert telemetry["n_redundants"] == 0
    assert new_sections == sections
    # LLM should not have been called
    assert len(fake_llm.calls) == 0
