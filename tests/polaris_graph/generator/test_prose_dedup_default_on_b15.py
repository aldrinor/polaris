"""B15 (#1359) behavioral fire-test — degenerate prose repetition is CONSOLIDATED by default.

THE BUG (forensic basket B15): the deep-research output padded one qualitative fact ~10-12x
(degenerate restatement). The in-tree prose-dedup machinery that kills this
(``_build_prose_groups`` Jaccard fallback + ``_build_nli_prose_groups`` bidirectional-NLI) was
built but shipped DEFAULT-OFF (``PG_FACT_DEDUP_PROSE`` / ``PG_CONSOLIDATION_NLI_PROSE`` both
defaulted to "0"), so it never fired on the production run path — only when the Gate-B slate
flipped it on.

THE FIX (flip-on + verify-it-fires): the two gate functions now DEFAULT-ON
(``_prose_dedup_enabled`` reads PG_FACT_DEDUP_PROSE default "1";
``_consolidation_nli_enabled_factdedup`` reads PG_CONSOLIDATION_NLI_PROSE default "1", still
gated by the PG_CONSOLIDATION_NLI master). Faithfulness-neutral: prose RedundancyGroups append to
the SAME ``groups`` list consumed by the UNCHANGED keep-all cross-ref rewrite (every citation of
every clustered sentence preserved — §-1.3 consolidate), re-verified by strict_verify at the
rewrite seam.

This test FAILS LOUD if the flip regresses:
  (1) with NO env flags set (production default), ``build_groups`` over a degenerate
      one-fact-repeated-many fixture produces a prose RedundancyGroup that consolidates the
      restatements (the effect FIRES by default); and
  (2) the explicit kill-switch (PG_FACT_DEDUP_PROSE=0) restores the byte-identical legacy
      (no prose group), proving the LAW VI off-switch still works; and
  (3) the NLI prose sub-flag gate defaults-ON when the master flag is on.
"""
from __future__ import annotations

import importlib

import src.polaris_graph.generator.fact_dedup as fact_dedup


# A single qualitative fact restated 4x in plain prose (no numbers => empty-numeric signature =>
# routes to the prose path). >= 4 content words each so it is a clustering candidate.
_DEGENERATE_SECTIONS = {
    "Findings": [
        "Tirzepatide substantially improved glycemic control in adults with type 2 diabetes.",
        "Tirzepatide substantially improved glycemic control in adults with type 2 diabetes.",
        "Tirzepatide substantially improved glycemic control in adults with type 2 diabetes.",
        "Tirzepatide substantially improved glycemic control in adults with type 2 diabetes.",
    ],
}
_SECTION_ORDER = ["Findings"]


def test_b15_jaccard_prose_dedup_default_on_fires(monkeypatch):
    """With NO env flags set (production default) the Jaccard prose path consolidates the
    degenerate restatements into a RedundancyGroup. Pre-flip this returned [] by default."""
    # Production default: neither flag set => the flip-on default must engage.
    monkeypatch.delenv("PG_FACT_DEDUP_PROSE", raising=False)
    monkeypatch.delenv("PG_FACT_DEDUP_PROSE_JACCARD", raising=False)
    # Keep the NLI master OFF so this test isolates the dep-free Jaccard fallback (no cross-encoder).
    monkeypatch.delenv("PG_CONSOLIDATION_NLI", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_PROSE", raising=False)

    assert fact_dedup._prose_dedup_enabled() is True, (
        "B15 REGRESSION: PG_FACT_DEDUP_PROSE no longer defaults ON — the prose-dedup pass is skipped "
        "on the production run path and degenerate repetition will not be consolidated."
    )

    groups = fact_dedup.build_groups(_DEGENERATE_SECTIONS, _SECTION_ORDER)

    # FIRE assertion: a prose group formed that consolidates the 4 identical restatements.
    assert groups, (
        "B15 REGRESSION: build_groups produced NO RedundancyGroup over a one-fact-repeated-4x "
        "fixture with default flags — the consolidation did not fire."
    )
    biggest = max(groups, key=lambda g: 1 + len(g.redundants))
    occurrences = 1 + len(biggest.redundants)
    assert occurrences >= 2, (
        f"B15 REGRESSION: the largest prose group only has {occurrences} occurrence(s); the "
        "degenerate restatements were not clustered for the keep-all cross-ref rewrite."
    )


def test_b15_kill_switch_restores_legacy(monkeypatch):
    """LAW VI: PG_FACT_DEDUP_PROSE=0 restores the byte-identical legacy (no prose group)."""
    monkeypatch.setenv("PG_FACT_DEDUP_PROSE", "0")
    monkeypatch.delenv("PG_CONSOLIDATION_NLI", raising=False)
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_PROSE", raising=False)

    assert fact_dedup._prose_dedup_enabled() is False
    groups = fact_dedup.build_groups(_DEGENERATE_SECTIONS, _SECTION_ORDER)
    # With the prose path OFF and no numeric signatures, the empty-signature sentences are skipped.
    assert groups == [], (
        "B15: PG_FACT_DEDUP_PROSE=0 must restore legacy (no prose RedundancyGroup) — kill-switch broken."
    )


def test_b15_nli_prose_subflag_defaults_on_when_master_on(monkeypatch):
    """The NLI prose sub-flag now defaults-ON, so when the PG_CONSOLIDATION_NLI master is enabled
    the bidirectional-NLI prose path is active (no explicit PG_CONSOLIDATION_NLI_PROSE needed).
    Asserts the GATE decision only (does not load the cross-encoder offline)."""
    importlib.reload(fact_dedup)  # ensure module-level state is clean for the lazy master import
    monkeypatch.setenv("PG_CONSOLIDATION_NLI", "1")
    monkeypatch.delenv("PG_CONSOLIDATION_NLI_PROSE", raising=False)  # rely on the new default-ON
    assert fact_dedup._consolidation_nli_enabled_factdedup() is True, (
        "B15 REGRESSION: PG_CONSOLIDATION_NLI_PROSE no longer defaults ON — the bidirectional-NLI "
        "prose consolidation will not fire even when the master cross-encoder winner is active."
    )
    # And the master gate still wins: master OFF => NLI prose path OFF regardless of the sub-flag.
    monkeypatch.setenv("PG_CONSOLIDATION_NLI", "0")
    assert fact_dedup._consolidation_nli_enabled_factdedup() is False, (
        "B15: the master PG_CONSOLIDATION_NLI=0 must still hard-OFF the NLI prose path."
    )
