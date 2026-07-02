"""I-deepfix-001 (Codex P1) — U10 title-only retraction forwarded to the evidence row.

The tier classifier fires ``R0_retracted`` for BOTH the OpenAlex retraction flag AND a
title-only retraction / withdrawal marker (a retracted paper re-deposited on a preprint
host whose OpenAlex flag is unset). Before the fix, ``live_retriever`` set the row's
``is_retracted`` flag from the OpenAlex flag ONLY — so a TITLE-ONLY retracted paper
entered the grounding pool with a non-empty ``direct_quote`` and could ground generated
prose (the generator retraction gate keys on ``is_retracted``, which was never set).

These tests assert the row-level retraction decision now ALSO fires on the tier-classifier
leg, so the retraction gate excludes a title-only retracted source BEFORE composition.
Pure, offline: no network, no model, no LLM.
"""
from __future__ import annotations

from src.polaris_graph.generator import retraction_gate as rg
from src.polaris_graph.retrieval.live_retriever import (
    _retraction_is_truthy,
    _row_is_retracted,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationResult,
    ClassificationSignals,
    TierLevel,
    _classify_source_tier_rules,
)


def _title_only_retracted_result() -> ClassificationResult:
    """A retracted paper re-deposited on a preprint host: OpenAlex flag UNSET, but the
    title carries an explicit LEADING retraction marker."""
    signals = ClassificationSignals(
        url="https://arxiv.org/abs/1234.56789",
        title="RETRACTED: Effect of drug X on mortality in sepsis",
        openalex_is_retracted=False,
        fetched_content_length=8000,
    )
    return _classify_source_tier_rules(signals)


def test_classifier_flags_title_only_retraction():
    """Sanity: the rules classifier fires R0_retracted on the title-only marker."""
    result = _title_only_retracted_result()
    assert "R0_retracted" in result.matched_rules
    assert result.tier == TierLevel.UNKNOWN


def test_openalex_only_leg_misses_title_only_retraction():
    """The pre-fix behavior: keyed on the OpenAlex flag ONLY, a title-only retraction
    (OpenAlex flag unset) is NOT caught — the exact hole the fix closes."""
    assert _retraction_is_truthy({}, "is_retracted") is False


def test_row_is_retracted_fires_on_tier_result_leg():
    """THE FIX: even with NO OpenAlex retraction flag, the tier-result leg flags the row."""
    result = _title_only_retracted_result()
    assert _row_is_retracted({}, result) is True


def test_row_is_retracted_still_fires_on_openalex_flag():
    """The legacy OpenAlex leg still fires when the tier result is clean."""
    clean = ClassificationResult(tier=TierLevel.T1, confidence=1.0)
    assert _row_is_retracted({"is_retracted": True}, clean) is True


def test_row_is_retracted_false_for_clean_row_and_clean_tier():
    """Fail-open: a clean row + clean tier result is NOT flagged (no exclusion on a bug)."""
    clean = ClassificationResult(tier=TierLevel.T1, confidence=1.0)
    assert _row_is_retracted({}, clean) is False
    assert _row_is_retracted({"is_retracted": "false"}, clean) is False


def test_title_only_retracted_row_excluded_by_retraction_gate():
    """End-to-end at the row level: a title-only retracted source, once flagged
    is_retracted=True by _row_is_retracted, is EXCLUDED from grounding by the gate
    (and RETURNED for disclosure — never silently dropped, §-1.3)."""
    result = _title_only_retracted_result()
    row = {
        "evidence_id": "ev_ret",
        "source_url": "https://arxiv.org/abs/1234.56789",
        "direct_quote": "Mortality fell 12.0% (p<0.01).",
    }
    if _row_is_retracted({}, result):
        row["is_retracted"] = True
    groundable, retracted = rg.partition_rows([row])
    assert groundable == []
    assert [r["evidence_id"] for r in retracted] == ["ev_ret"]
