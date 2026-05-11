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


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 (Codex post-merge diagnosis): overlap-based signature matching
# ─────────────────────────────────────────────────────────────────────────


def test_signatures_overlap_shares_two_decimals() -> None:
    """Same 9.2%/13.9% fact with different extra years should overlap."""
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature(
        "9.2% of Quebecers aged 55-64 vs 13.9% in ROC in 2014 [ev_X]."
    )
    sig_b = extract_signature(
        "9.2% in 2014, building on the 1997 baseline, compared 13.9% in ROC [ev_Y]."
    )
    # sig_a has years={2014}; sig_b has years={2014, 1997}; but decimals match
    assert _signatures_overlap(sig_a, sig_b)


def test_signatures_overlap_shares_two_dollar_amounts() -> None:
    """Same $11.2B/$13.4B fact in different sections should overlap."""
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature(
        "PBO estimates $11.2 billion in 2024-25 rising to $13.4 billion in 2027-28 [ev_X]."
    )
    sig_b = extract_signature(
        "Incremental cost $11.2 billion 2024-25 to $13.4 billion 2027-28 (Quebec context) [ev_Y]."
    )
    assert _signatures_overlap(sig_a, sig_b)


def test_signatures_overlap_distinct_facts_dont_match() -> None:
    """Different decimals should NOT overlap."""
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("8.7% of Quebec households in 2007 [ev_X].")
    sig_b = extract_signature("9.2% of Quebecers aged 55-64 in 2014 [ev_Y].")
    # Only 1 decimal overlap (none shared); not enough for overlap match
    assert not _signatures_overlap(sig_a, sig_b)


def test_signatures_overlap_empty_sig_never_matches() -> None:
    """Empty signatures should never overlap."""
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("The system is regressive [ev_X].")  # empty
    sig_b = extract_signature("Premium is 3% of income [ev_Y].")
    assert not _signatures_overlap(sig_a, sig_b)
    assert not _signatures_overlap(sig_a, sig_a)


def test_build_groups_real_q5_post_fix_pattern_with_extra_years() -> None:
    """Reproduces Codex Phase 3 diagnosis case: the same 9.2%/13.9%
    fact appears in two sections but with different incidental years —
    Phase 2's exact-FactSignature would have missed this; Phase 3's
    overlap matcher should catch it.
    """
    sections = {
        "Efficacy": [
            "9.2% of Quebecers aged 55 to 64 vs 13.9% in ROC in 2014 [ev_X].",
        ],
        "Long-term Outcomes": [
            "Building on 1997 baseline, 9.2% reported access barriers vs "
            "13.9% in ROC as of 2014 [ev_Y].",
        ],
    }
    groups = build_groups(sections)
    assert len(groups) == 1, (
        f"overlap matcher should catch 9.2%/13.9% repeat despite year drift; "
        f"got {len(groups)} groups"
    )
    assert groups[0].primary.section == "Efficacy"
    assert groups[0].redundants[0].section == "Long-term Outcomes"


def test_build_groups_three_section_chain_clusters_correctly() -> None:
    """A → B → C where A and B share core fact, B and C share core fact,
    but A and C don't directly share. With greedy clustering (B joins A's
    cluster first; C joins B's cluster which is A's cluster), all three
    end up in one group.
    """
    sections = {
        "Efficacy": ["8.7% of Quebec, 4.8% ROC in 2007 [ev_1]."],
        "Comparative": ["8.7% Quebec vs 4.8% ROC, ranging from 1.2% to 2.4% [ev_2]."],
        "Long-term Outcomes": ["8.7% Quebec OOP rate 4.8% ROC, baseline 1997 [ev_3]."],
    }
    groups = build_groups(sections)
    assert len(groups) == 1
    # All three sections should be in the cluster
    sections_in_cluster = {groups[0].primary.section} | {r.section for r in groups[0].redundants}
    assert sections_in_cluster == {"Efficacy", "Comparative", "Long-term Outcomes"}


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 iter-2 (Codex P1 corrections): false-positive guard +
# non-vacuous transitive cluster
# ─────────────────────────────────────────────────────────────────────────


def test_signatures_overlap_same_decimal_diff_year_does_not_match() -> None:
    """3.7% in 2016 vs 3.7% in 2014 should NOT match — different years
    means different facts. Codex iter-1 P1-1 case.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("3.7% in 2016 [ev_X].")
    sig_b = extract_signature("3.7% in 2014 [ev_Y].")
    assert not _signatures_overlap(sig_a, sig_b), (
        "single decimal with disagreeing years must not overlap"
    )


def test_signatures_overlap_same_decimal_disjoint_dollars_does_not_match() -> None:
    """Same single decimal but completely different dollar amounts is
    NOT a fact match. Codex iter-1 P1-1 case.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("3.0% of $40,000 income [ev_X].")
    sig_b = extract_signature("3.0% of $200,000 income [ev_Y].")
    # Both have {3.0} decimal but different dollar contexts
    # Without strict guard, _signatures_overlap would return True via Path 2
    # With guard, should return False
    assert not _signatures_overlap(sig_a, sig_b), (
        "single decimal with disjoint dollars should not overlap"
    )


def test_build_groups_transitive_chain_non_vacuous() -> None:
    """A and C do NOT directly overlap; B bridges them.
    A = {1.1, 2.2}; B = {1.1, 2.2, 3.3, 4.4}; C = {3.3, 4.4}.
    A↔B match (shared 1.1, 2.2). B↔C match (shared 3.3, 4.4). A↛C direct.
    True transitive clustering should fold all three into ONE group.
    Codex iter-1 P1-2 case.
    """
    sections = {
        "Efficacy": ["The figures are 1.1% and 2.2% [ev_A]."],
        "Comparative": ["Numbers were 1.1%, 2.2%, 3.3%, 4.4% [ev_B]."],
        "Regulatory": ["3.3% and 4.4% are the boundaries [ev_C]."],
    }
    groups = build_groups(
        sections,
        section_order=["Efficacy", "Comparative", "Regulatory"],
    )
    assert len(groups) == 1, (
        f"transitive chain A→B→C should fold to 1 group; got {len(groups)}"
    )
    sections_in_cluster = (
        {groups[0].primary.section}
        | {r.section for r in groups[0].redundants}
    )
    assert sections_in_cluster == {"Efficacy", "Comparative", "Regulatory"}


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 iter-3 (Codex regression fix): preserve exact single-dollar
# duplicate grouping without reopening pure-decimal false-positive
# ─────────────────────────────────────────────────────────────────────────


def test_signatures_overlap_identical_single_dollar_still_matches() -> None:
    """Codex iter-2 P1 regression: '$200 more per person' appearing in
    two sections has FactSignature(decimals={}, dollar_buckets={204}, years={})
    on both sides. Identical signature MUST match (legacy exact-equality
    behavior preserved).
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("Quebec spends $200 more per person [ev_X].")
    sig_b = extract_signature("Quebec spends $200 more per person on prescriptions [ev_Y].")
    assert _signatures_overlap(sig_a, sig_b), (
        "identical single-dollar signatures must still match"
    )


def test_build_groups_quebec_200_dollar_cross_section_caught() -> None:
    """Q5 observable bug Codex flagged: '$200 more per person' across
    4 sections should cluster into ONE redundancy group.
    """
    sections = {
        "Efficacy": ["Quebec spends $200 more per person on prescriptions [ev_X]."],
        "Regulatory": ["The province spends $200 more per person than the rest of Canada [ev_Y]."],
        "Population Subgroups": ["Per capita spending exceeds Canada by $200 [ev_Z]."],
        "Long-term Outcomes": ["This adds up: $200 more per resident [ev_W]."],
    }
    groups = build_groups(sections, section_order=list(sections.keys()))
    assert len(groups) == 1, (
        f"single-dollar duplicate fact across 4 sections should be ONE group; "
        f"got {len(groups)}"
    )
    assert groups[0].primary.section == "Efficacy"
    assert len(groups[0].redundants) == 3


def test_signatures_overlap_year_only_identical_still_matches() -> None:
    """Identical year-only signatures match: '1997 baseline' in two sections."""
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("Implemented in 1997 [ev_X].")
    sig_b = extract_signature("Established in 1997 [ev_Y].")
    assert _signatures_overlap(sig_a, sig_b), (
        "identical year-only signatures must match"
    )


# ─────────────────────────────────────────────────────────────────────────
# Phase 3 iter-3 (Codex Path 2 conflict-masking fix): same decimal +
# shared year + disjoint dollars must NOT match; same decimal + shared
# dollar + disjoint years must NOT match.
# ─────────────────────────────────────────────────────────────────────────


def test_signatures_overlap_same_decimal_shared_year_disjoint_dollars_blocks() -> None:
    """3.0% of $40K in 2014 vs 3.0% of $200K in 2014: shared year masks
    the dollar conflict. Codex iter-3 P1 case.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("3.0% of $40,000 income in 2014 [ev_X].")
    sig_b = extract_signature("3.0% of $200,000 income in 2014 [ev_Y].")
    assert not _signatures_overlap(sig_a, sig_b), (
        "year-overlap should NOT mask disjoint-dollar conflict"
    )


def test_signatures_overlap_same_decimal_shared_dollar_disjoint_years_blocks() -> None:
    """3.0% of $40K in 2014 vs 3.0% of $40K in 2016: shared dollar
    masks the year conflict. Codex iter-3 P1 case.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("3.0% of $40,000 income in 2014 [ev_X].")
    sig_b = extract_signature("3.0% of $40,000 income in 2016 [ev_Y].")
    assert not _signatures_overlap(sig_a, sig_b), (
        "dollar-overlap should NOT mask disjoint-year conflict"
    )


def test_signatures_overlap_same_decimal_one_side_empty_context_matches() -> None:
    """3.0% with $40K + 2014 vs 3.0% with only $40K: one side has empty
    years. No conflict, supporting overlap on dollars → match.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature("3.0% of $40,000 income in 2014 [ev_X].")
    sig_b = extract_signature("3.0% of $40,000 income [ev_Y].")  # no year
    assert _signatures_overlap(sig_a, sig_b), (
        "one side with empty year axis should not block — no conflict"
    )


def test_signatures_overlap_path1_two_decimals_disjoint_dollars_blocks() -> None:
    """Path 1 case — ≥2 decimals shared but dollar buckets disjoint (years
    overlap, dollars conflict). Was matching via Path 1 short-circuit in
    iter 3; now blocked by the lifted top-level conflict guard.

    3.0%/1.6% on income $40K/$80K in 2014 vs 3.0%/1.6% on income
    $200K/$300K in 2014 — same decimals, same year, but the dollar
    contexts are different income tiers. Distinct facts.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature(
        "3.0% on $40,000 and 1.6% on $80,000 income in 2014 [ev_X]."
    )
    sig_b = extract_signature(
        "3.0% on $200,000 and 1.6% on $300,000 income in 2014 [ev_Y]."
    )
    assert not _signatures_overlap(sig_a, sig_b), (
        "Path 1 must respect populated-dollar conflict guard"
    )


def test_signatures_overlap_path3_two_dollars_disjoint_years_blocks() -> None:
    """Path 3 case — ≥2 dollar buckets shared but years disjoint. Was
    matching via Path 3 short-circuit in iter 3; now blocked.

    Two distinct fiscal-year reports each citing $40K and $200K
    thresholds, but for different years (2014 vs 2018) — not the same
    fact.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature(
        "Thresholds of $40,000 and $200,000 in 2014 [ev_X]."
    )
    sig_b = extract_signature(
        "Thresholds of $40,000 and $200,000 in 2018 [ev_Y]."
    )
    assert not _signatures_overlap(sig_a, sig_b), (
        "Path 3 must respect populated-year conflict guard"
    )


def test_signatures_overlap_path1_two_decimals_compatible_context_matches() -> None:
    """Positive Path 1 case under new top-level guard — ≥2 shared decimals
    AND one side has empty supporting axes (no conflict possible) →
    should still match.

    9.2% and 13.9% appear in both sentences; sig_b has no dollar context
    so no conflict is possible. Match is preserved.
    """
    from src.polaris_graph.generator.fact_dedup import _signatures_overlap
    sig_a = extract_signature(
        "9.2% and 13.9% of seniors received OAS in 2014 [ev_X]."
    )
    sig_b = extract_signature(
        "9.2% and 13.9% of seniors received OAS [ev_Y]."
    )
    assert _signatures_overlap(sig_a, sig_b), (
        "Path 1 with compatible context (one side empty) must still match"
    )
