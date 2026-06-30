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
async def test_rewrite_keeps_all_on_invalid_json() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    groups = build_groups(sections)
    fake_llm = _FakeLLM("not valid json at all")
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    # §-1.3 CONSOLIDATE-keep-all: a failed rewrite must NOT delete the corroborating cited
    # sentence — it emits NO drop keys, so apply_rewrites keeps every original verbatim.
    assert rewrites == {}, "invalid JSON must keep all corroborators (no drop keys), not drop them"


@pytest.mark.asyncio
async def test_rewrite_keeps_all_on_wrong_shape() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    groups = build_groups(sections)
    # Returns valid JSON but wrong shape (rewrites is a string not list)
    fake_llm = _FakeLLM('{"rewrites": "not a list"}')
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    assert rewrites == {}, "wrong-shape response must keep all corroborators (consolidate-keep-all)"


@pytest.mark.asyncio
async def test_rewrite_keeps_all_on_count_mismatch() -> None:
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
        "Regulatory": ["8.7% in 2007 [ev_Z]."],
    }
    groups = build_groups(sections)
    # 2 redundants expected, only 1 returned → shape mismatch
    fake_llm = _FakeLLM('{"rewrites": ["only one rewrite [ev_Y]."]}')
    rewrites = await rewrite_redundant_sentences(groups, fake_llm)
    assert rewrites == {}, "count-mismatch response must keep all corroborators (consolidate-keep-all)"


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
async def test_rewrite_keeps_original_on_null_per_item() -> None:
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
    # The valid rewrite is applied; the null item is OMITTED (no key) so apply_rewrites KEEPS the
    # original corroborating sentence — §-1.3, never drop a corroborator on a null rewrite.
    assert "see Efficacy [ev_Y]." in values
    assert None not in values, "a null per-item rewrite must keep the original, not emit a drop"
    assert len(rewrites) == 1, "only the valid rewrite is keyed; the null item stays as its original"


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
async def test_dedup_pass_keeps_corroborators_on_llm_failure() -> None:
    """If the rewrite call fails, the corroborating redundants are KEPT (consolidate-keep-all,
    §-1.3) — a failed merge never deletes a corroborating source."""
    sections = {
        "Efficacy": ["8.7% in 2007 [ev_X]."],
        "Comparative": ["8.7% in 2007 [ev_Y]."],
    }
    fake_llm = _FakeLLM("garbage response")
    new_sections, telemetry = await dedup_pass(sections, fake_llm)
    assert telemetry["n_drops"] == 0, "a failed rewrite must drop nothing (keep all corroborators)"
    assert telemetry["n_rewrites_applied"] == 0
    assert new_sections["Efficacy"] == ["8.7% in 2007 [ev_X]."]
    assert new_sections["Comparative"] == ["8.7% in 2007 [ev_Y]."], (
        "the corroborating sentence is KEPT on rewrite failure, not dropped"
    )


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
    but A and C don't directly share. With non-conflicting context,
    transitive clustering merges all three.

    Codex brief-iter-1 P1 hardening: this test used to use mixed years
    (2007 / none / 1997). Under the new contextless-bridge guard those
    two populated years are a conflict and the endpoints are correctly
    refused merge. Reframed here with consistent year context so the
    transitive merge test still validates the chain-clustering behavior
    independently of the conflict guard. Year-conflict bridge case is
    now covered by `test_build_groups_no_contextless_bridge_merge_years`.
    """
    sections = {
        "Efficacy": ["8.7% of Quebec, 4.8% ROC [ev_1]."],
        "Comparative": ["8.7% Quebec vs 4.8% ROC, ranging from 1.2% to 2.4% [ev_2]."],
        "Long-term Outcomes": ["8.7% Quebec OOP rate 4.8% ROC, baseline [ev_3]."],
    }
    groups = build_groups(sections)
    assert len(groups) == 1
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


def test_build_groups_no_contextless_bridge_merge_years() -> None:
    """Codex brief-iter-1 P1 fix — contextless bridge B={9.2%,13.9%} must
    NOT merge year-conflicting endpoints A={9.2%,13.9%,2014} and
    C={9.2%,13.9%,2016} into a single group.

    Even though _signatures_overlap(A,B) and _signatures_overlap(B,C) are
    both True (Path 1 ≥2 shared decimals, no conflict because B has empty
    years), A and C themselves conflict on years. Cluster membership
    must require no-conflict-with-any-member; merging clusters must
    require pairwise compatibility.
    """
    sections = {
        "intro": [
            "9.2% and 13.9% of seniors received OAS in 2014 [ev_A].",
        ],
        "history": [
            "9.2% and 13.9% of seniors received OAS [ev_B].",
        ],
        "outlook": [
            "9.2% and 13.9% of seniors received OAS in 2016 [ev_C].",
        ],
    }
    groups = build_groups(sections, section_order=["intro", "history", "outlook"])
    # Expected: A and B merged (no conflict, overlap); C separate
    # (conflicts with A despite overlapping with B). Cluster of size 1
    # (C alone) is filtered out (distinct_sections < 2).
    # So 1 group with 2 members: A, B.
    assert len(groups) == 1, (
        f"Expected exactly 1 group (A+B), got {len(groups)}: "
        f"contextless-bridge merge must not pull C into A's cluster"
    )
    primary_and_redundants = (
        [groups[0].primary.sentence]
        + [r.sentence for r in groups[0].redundants]
    )
    assert "in 2016" not in " ".join(primary_and_redundants), (
        "C (2016) must NOT be merged with A (2014) via contextless B bridge"
    )


def test_build_groups_no_contextless_bridge_merge_dollars() -> None:
    """Same shape as the year-bridge test but for dollar conflicts.

    A={3.0%,$40K}, B={3.0%}, C={3.0%,$200K}. _signatures_overlap takes
    A↔B and B↔C, but A↔C directly conflicts on dollar_buckets. C must
    not merge into A's cluster via B.
    """
    sections = {
        "low_income": [
            "3.0% of households earning $40,000 [ev_A]."
        ],
        "general": [
            "3.0% of households [ev_B]."
        ],
        "high_income": [
            "3.0% of households earning $200,000 [ev_C]."
        ],
    }
    groups = build_groups(sections, section_order=["low_income", "general", "high_income"])
    # All three signatures only have 1 shared decimal (3.0%) -- Path 1 needs ≥2.
    # Path 0 doesn't match (signatures differ). Path 2 requires full
    # decimal equality + supporting overlap; A vs B has decimals equal
    # ({3.0%}) and A has dollars, B has empty dollars (no conflict) ->
    # match. B vs C similarly. A vs C conflicts on dollars.
    # Expected outcome: A and B form one group; C separate.
    assert all(
        "in 2014" not in g.primary.sentence
        and not any("$200" in r.sentence and "$40" in g.primary.sentence
                    for r in g.redundants)
        for g in groups
    ), "A and C must not co-cluster via contextless B bridge"
    # Stronger: no group should contain BOTH a $40,000 sentence and a
    # $200,000 sentence.
    for g in groups:
        sentences = [g.primary.sentence] + [r.sentence for r in g.redundants]
        joined = " ".join(sentences)
        assert not ("$40,000" in joined and "$200,000" in joined), (
            "$40K and $200K must not share a cluster"
        )


def test_build_groups_no_cross_merge_of_mutually_conflicting_clusters() -> None:
    """Codex brief-iter-2 P1 fix — when a candidate bridges two existing
    non-target clusters, the non-target clusters must also be
    pairwise-compatible with each other (not just with the target). A
    candidate D should NOT fuse B={3.3%,4.4%,2014} and C={5.5%,6.6%,2016}
    into one cluster even if D overlaps with all three.

    Order: X={1.1%,2.2%,2014+2016 superset}, B, C, D.
    X seeds; B seeds (no overlap with X); C seeds (no overlap with X or
    B); D arrives with decimals overlapping all three but B and C
    conflict on years. With incremental compat-against-target, D folds
    in X first, then B (B is compatible with target=[X,D]), then C is
    rejected because target already contains B and B↔C years conflict.
    """
    sections = {
        "s_x": ["1.1% and 2.2% rates measured in 2014 and 2016 [ev_X]."],
        "s_b": ["3.3% and 4.4% rates from 2014 cohort [ev_B]."],
        "s_c": ["5.5% and 6.6% rates from 2016 cohort [ev_C]."],
        "s_d": ["3.3% and 4.4% with 5.5% and 6.6% bridge facts [ev_D]."],
    }
    groups = build_groups(
        sections, section_order=["s_x", "s_b", "s_c", "s_d"]
    )
    # No single group should contain both a 2014-cohort sentence (B) and
    # a 2016-cohort sentence (C).
    for g in groups:
        members = [g.primary.sentence] + [r.sentence for r in g.redundants]
        joined = " ".join(members)
        assert not ("2014 cohort" in joined and "2016 cohort" in joined), (
            "non-target clusters with mutually conflicting years must not "
            "co-merge via a bridging candidate"
        )


def test_build_groups_transitive_chain_without_conflict_still_merges() -> None:
    """Regression: the transitive merging behavior from iter-2 must
    survive the new compatibility check when no conflicts exist.

    A={1.1,2.2,3.3}, B={2.2,3.3,4.4,5.5}, C={4.4,5.5,6.6}. A↛C direct
    (no shared decimals); A↔B and B↔C overlap. No years/dollars. All
    three must still cluster as one group.
    """
    sections = {
        "s1": ["1.1% and 2.2% and 3.3% [ev_A]."],
        "s2": ["2.2% and 3.3% and 4.4% and 5.5% [ev_B]."],
        "s3": ["4.4% and 5.5% and 6.6% [ev_C]."],
    }
    groups = build_groups(sections, section_order=["s1", "s2", "s3"])
    assert len(groups) == 1, (
        f"transitive chain with no conflicts should still cluster as 1 "
        f"group, got {len(groups)}"
    )
    members = (
        [groups[0].primary.sentence]
        + [r.sentence for r in groups[0].redundants]
    )
    assert len(members) == 3, (
        f"Expected all 3 sentences in the cluster, got {len(members)}"
    )


# ─────────────────────────────────────────────────────────────────────────
# I-deepfix-001 D1 (#1344) — QUALITATIVE consolidation at the SENTENCE layer
# ─────────────────────────────────────────────────────────────────────────
#
# fact_dedup's numeric ``FactSignature`` (decimals / dollars / years) is
# numeric-only — a PURE-PROSE (non-numeric) restatement has an empty signature
# and the numeric path SKIPS it. The §-1.3 CONSOLIDATE-qualitative-too guarantee
# at this (sentence) layer is provided by the default-ON prose path
# (``_build_prose_groups``), the SENTENCE-layer counterpart of the D1 source-
# basket qualitative consolidation in ``synthesis/finding_dedup.py``. These tests
# pin the keep-all + false-merge-guard contract there: N occurrences of the SAME
# qualitative claim cluster into ONE RedundancyGroup (the downstream cross-ref
# rewrite preserves every citation), and two DIFFERENT qualitative claims never
# merge. PG_CONSOLIDATION_NLI is left OFF so only the dep-free Jaccard path runs.

_QUAL_SENTENCE = "The therapy was generally well tolerated across the study cohort [ev_1]."


def test_d1_qualitative_prose_same_claim_one_group(monkeypatch) -> None:
    # The SAME qualitative claim restated across two sections clusters into ONE
    # RedundancyGroup (>=2 occurrences) — CONSOLIDATE qualitative too (§-1.3).
    monkeypatch.delenv("PG_FACT_DEDUP_PROSE", raising=False)        # default-ON
    monkeypatch.delenv("PG_CONSOLIDATION_NLI", raising=False)       # NLI master OFF
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_PROSE", raising=False)
    sections = {"Efficacy": [_QUAL_SENTENCE], "Safety": [_QUAL_SENTENCE]}
    groups = build_groups(sections, section_order=["Efficacy", "Safety"])
    assert len(groups) == 1
    assert 1 + len(groups[0].redundants) == 2     # both occurrences, one group


def test_d1_qualitative_prose_different_claims_not_merged(monkeypatch) -> None:
    # Two DIFFERENT qualitative claims (low shingle overlap) must NEVER cluster
    # (false-merge worse than no-merge). No RedundancyGroup forms.
    monkeypatch.delenv("PG_FACT_DEDUP_PROSE", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_PROSE", raising=False)
    sections = {
        "Efficacy": [_QUAL_SENTENCE],
        "Safety": ["Mortality increased sharply among the older subgroup of patients [ev_2]."],
    }
    groups = build_groups(sections, section_order=["Efficacy", "Safety"])
    assert groups == []


def test_d1_qualitative_prose_polarity_guard_blocks_negation(monkeypatch) -> None:
    # A negation flip ("was associated" vs "was NOT associated") clears the Jaccard
    # threshold but asserts the OPPOSITE claim; the polarity guard blocks the merge
    # so a real opposing claim is never cross-reffed (consolidated) away.
    monkeypatch.delenv("PG_FACT_DEDUP_PROSE", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_PROSE", raising=False)
    pos = ("The combination therapy was associated with a clinically meaningful and "
           "statistically robust improvement in progression free survival overall [ev_1].")
    neg = pos.replace("was associated", "was not associated")
    sections = {"Efficacy": [pos], "Safety": [neg]}
    groups = build_groups(sections, section_order=["Efficacy", "Safety"])
    assert groups == []
