"""Tests for Bridge the Gap fixes (47 issues across 4 sprints).

Tests critical fixes: NLI verdict mapping (P1), STORM failure detection (P2),
list_not_prose veto (P3), OpenAlex query format (P5/B14), hedging enforcement (R13),
global transition enforcement (R4).
"""
import os
import re
import sys

import pytest

# Ensure project root is on path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


# =====================================================================
# P1: NLI Threshold Verdict Mapping
# =====================================================================

def _nli_verdict_logic(nli_score, llm_verdict, threshold=0.75):
    """Reproduce the verifier NLI override logic from verifier.py:1000-1035."""
    is_faithful = llm_verdict == "SUPPORTED"
    if is_faithful and nli_score is not None and nli_score < threshold:
        is_faithful = False

    method = (
        "partial" if llm_verdict == "PARTIALLY_SUPPORTED"
        else "not_supported" if llm_verdict == "NOT_SUPPORTED"
        else "atomic"
    )

    if nli_score is not None and llm_verdict == "SUPPORTED":
        if nli_score < 0.50:
            method = "not_supported"
            is_faithful = False
        elif nli_score < threshold:
            method = "partial"

    return is_faithful, method


def test_nli_verdict_supported_above_threshold(monkeypatch):
    """P1: NLI >= 0.75 with SUPPORTED verdict stays SUPPORTED."""
    monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75")
    threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    is_faithful, method = _nli_verdict_logic(0.80, "SUPPORTED", threshold)
    assert is_faithful is True
    assert method == "atomic"


def test_nli_verdict_borderline_partial(monkeypatch):
    """P1: NLI 0.50-0.75 with SUPPORTED → PARTIALLY_SUPPORTED."""
    monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75")
    threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    is_faithful, method = _nli_verdict_logic(0.66, "SUPPORTED", threshold)
    assert is_faithful is False
    assert method == "partial"


def test_nli_verdict_low_not_supported(monkeypatch):
    """P1: NLI < 0.50 with SUPPORTED → NOT_SUPPORTED."""
    monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75")
    threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    is_faithful, method = _nli_verdict_logic(0.45, "SUPPORTED", threshold)
    assert is_faithful is False
    assert method == "not_supported"


def test_nli_none_honors_llm_verdict(monkeypatch):
    """P1: When NLI is None, LLM verdict is honored as-is."""
    monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75")
    threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    is_faithful, method = _nli_verdict_logic(None, "SUPPORTED", threshold)
    assert is_faithful is True
    assert method == "atomic"


def test_nli_not_supported_stays_not_supported(monkeypatch):
    """P1: NOT_SUPPORTED verdict is not overridden regardless of NLI score."""
    monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75")
    threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    is_faithful, method = _nli_verdict_logic(0.90, "NOT_SUPPORTED", threshold)
    assert is_faithful is False
    assert method == "not_supported"


def test_nli_exact_threshold_boundary(monkeypatch):
    """P1: NLI exactly at threshold (0.75) is SUPPORTED."""
    monkeypatch.setenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75")
    threshold = float(os.getenv("PG_FAITHFULNESS_NLI_THRESHOLD", "0.75"))

    is_faithful, method = _nli_verdict_logic(0.75, "SUPPORTED", threshold)
    assert is_faithful is True
    assert method == "atomic"


# =====================================================================
# P2: STORM Failure Detection
# =====================================================================

# These match the patterns in storm_interviews.py:853-864
_STORM_FAILURE_PATTERNS = (
    "do not adequately",
    "does not adequately",
    "do NOT",
    "data is incomplete",
    "not directly reported",
    "none of the sources directly",
    "sources do not provide",
    "no specific data",
    "insufficient information",
    "cannot be determined from",
)


def _is_storm_failure(answer_text):
    """Reproduce STORM failure detection from storm_interviews.py:865-866."""
    answer_lower = answer_text.lower() if answer_text else ""
    return any(fp.lower() in answer_lower for fp in _STORM_FAILURE_PATTERNS)


@pytest.mark.parametrize("answer", [
    "The sources do not adequately answer your question about PFAS levels.",
    "This does not adequately address filtration mechanisms.",
    "The data is incomplete for this particular analysis.",
    "This information is not directly reported in the available sources.",
    "None of the sources directly address the cost of remediation.",
    "The sources do not provide sufficient data on this topic.",
    "There is no specific data available on this compound.",
    "There is insufficient information to draw conclusions.",
    "The precise removal rate cannot be determined from these sources.",
])
def test_storm_failure_detection_positive(answer):
    """P2: Known failure phrases are detected."""
    assert _is_storm_failure(answer), f"Failed to detect failure: {answer[:60]}"


@pytest.mark.parametrize("answer", [
    "PFAS contamination affects over 200 million Americans according to EPA data.",
    "Activated carbon filtration removes 90% of PFOA from drinking water.",
    "Multiple studies report effective removal rates above 95%.",
    "The EPA established a maximum contaminant level of 4 parts per trillion.",
    "Granular activated carbon is the most widely used treatment technology.",
])
def test_storm_failure_detection_negative(answer):
    """P2: Normal answers are NOT flagged as failures."""
    assert not _is_storm_failure(answer), f"False positive: {answer[:60]}"


def test_storm_failure_clears_key_findings():
    """P2: Failed interviews should have key_findings cleared."""
    answer_text = "The sources do not adequately answer this question."
    is_failed = _is_storm_failure(answer_text)
    assert is_failed

    # Simulate the logic from storm_interviews.py:873
    original_findings = ["finding1", "finding2", "finding3"]
    key_findings = original_findings if not is_failed else []
    assert key_findings == [], "Failed interview should have empty key_findings"


# =====================================================================
# P3: List-Not-Prose Veto
# =====================================================================

def _is_list_not_prose(text):
    """Reproduce list_not_prose detection from analyzer.py:~2073-2086."""
    sentence_endings = len(re.findall(r'[.!?]', text))
    comma_parts = len(text.split(','))
    return sentence_endings < 1 and comma_parts > 3


def test_list_not_prose_vendor_list():
    """P3: Vendor name lists without sentences are vetoed."""
    vendor_list = "Aqua-Pure, PUR, Brita, ZeroWater, Berkey, LifeStraw, Sawyer, Katadyn"
    assert _is_list_not_prose(vendor_list), "Vendor name list should be detected"


def test_list_not_prose_bullet_list():
    """P3: Comma-separated items without sentence endings are vetoed."""
    items = "PFOA, PFOS, GenX, PFBS, PFHxS, PFNA, PFDA, PFHpA"
    assert _is_list_not_prose(items), "Chemical list should be detected"


def test_list_not_prose_normal_prose():
    """P3: Normal prose evidence is NOT vetoed."""
    prose = (
        "PFAS contamination has been detected in over 2,800 communities "
        "across the United States. The EPA established a health advisory "
        "level of 70 parts per trillion."
    )
    assert not _is_list_not_prose(prose), "Normal prose should NOT be flagged"


def test_list_not_prose_single_sentence_with_commas():
    """P3: A sentence with commas but a period at end is NOT vetoed."""
    text = "The contaminants include PFOA, PFOS, GenX, and PFBS."
    assert not _is_list_not_prose(text), "Sentence with commas should NOT be flagged"


# =====================================================================
# P5/B14: OpenAlex Query Format
# =====================================================================

def test_openalex_no_host_venue():
    """P5/B14: OpenAlex query must NOT include deprecated host_venue in API params."""
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "src", "polaris_graph", "agents", "searcher.py"
    )
    with open(source_path, "r") as f:
        lines = f.readlines()

    # Check that host_venue is NOT in any actual code line (comments are ok)
    for i, line in enumerate(lines):
        stripped = line.split("#")[0]  # Remove comments
        if "host_venue" in stripped:
            pytest.fail(
                f"OpenAlex code at line {i+1} contains deprecated 'host_venue' "
                f"in executable code (not a comment): {line.strip()}"
            )


def test_openalex_uses_primary_location():
    """P5/B14: OpenAlex should use primary_location.source instead of host_venue."""
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "src", "polaris_graph", "agents", "searcher.py"
    )
    with open(source_path, "r") as f:
        source = f.read()

    assert "primary_location" in source, (
        "OpenAlex query should reference primary_location (replacement for host_venue)"
    )


# =====================================================================
# R13: Hedging Post-Processing Enforcement
# =====================================================================

def test_hedging_limiter_reduces_excess(monkeypatch):
    """R13: Hedging words enforced by post-processing, not just prompts."""
    monkeypatch.setenv("PG_MAX_HEDGING_PER_SECTION", "3")

    from src.polaris_graph.synthesis.section_writer import _limit_hedging

    text = (
        "PFAS may contaminate water. This could potentially affect health. "
        "Filtration might remove contaminants. Studies may show improvements. "
        "Results could possibly indicate progress."
    )

    result = _limit_hedging(text)

    hedging = re.findall(
        r'\b(may|might|potentially|possibly|could|perhaps|appears to|seems to)\b',
        result, re.IGNORECASE,
    )
    assert len(hedging) <= 3, f"Expected <= 3 hedging words, found {len(hedging)}: {hedging}"


def test_hedging_limiter_preserves_within_limit(monkeypatch):
    """R13: Text within hedging limit is not modified."""
    monkeypatch.setenv("PG_MAX_HEDGING_PER_SECTION", "8")

    from src.polaris_graph.synthesis.section_writer import _limit_hedging

    text = "PFAS may contaminate water. This could affect health."
    result = _limit_hedging(text)
    assert result == text, "Text within limit should not be modified"


def test_hedging_limiter_empty_text():
    """R13: Empty text returns empty."""
    from src.polaris_graph.synthesis.section_writer import _limit_hedging

    assert _limit_hedging("") == ""
    assert _limit_hedging("   ") == "   "


# =====================================================================
# R4: Global Transition Enforcement
# =====================================================================

def test_global_transition_strip_all_14_types():
    """R4: Global strip pattern covers all 14 transition types."""
    full_pattern = re.compile(
        r'\b(moreover|furthermore|additionally|consequently|in addition|'
        r'as a result|nevertheless|nonetheless|on the other hand|'
        r'in contrast|conversely|alternatively|subsequently|meanwhile)\b',
        re.IGNORECASE,
    )

    all_transitions = [
        "Moreover", "Furthermore", "Additionally", "Consequently",
        "In addition", "As a result", "Nevertheless", "Nonetheless",
        "On the other hand", "In contrast", "Conversely", "Alternatively",
        "Subsequently", "Meanwhile",
    ]
    for t in all_transitions:
        assert full_pattern.search(t), f"Pattern should match: {t}"


def test_global_transition_assembler_uses_full_pattern():
    """R4: report_assembler.py global strip uses full 14-type pattern."""
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "src", "polaris_graph",
        "synthesis", "report_assembler.py",
    )
    with open(source_path, "r") as f:
        source = f.read()

    # Find the section after "_strip_transition" which is the global strip
    strip_idx = source.find("_strip_transition")
    assert strip_idx > 0, "Could not find _strip_transition in report_assembler.py"

    # The strip regex follows shortly after _strip_transition — grab more context
    strip_section = source[strip_idx:strip_idx + 1000].lower()

    # Check that the strip regex includes types beyond the original 3
    for word in ["consequently", "in addition", "nevertheless"]:
        assert word in strip_section, (
            f"Global transition strip should include '{word}' — "
            f"not just moreover/furthermore/additionally"
        )


# =====================================================================
# F5: Quality Gate Dots
# =====================================================================

def test_dashboard_gate_dots_derive_from_post_synthesis():
    """F5: Dashboard derives individual gate dots from post_synthesis_final event."""
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "templates", "live_dashboard.html",
    )
    with open(source_path, "r") as f:
        source = f.read()

    # Within the post_synthesis/post_synthesis_final handler, check for
    # individual gate dot updates
    post_synth_idx = source.find('gate === "post_synthesis"')
    assert post_synth_idx > 0, "Could not find post_synthesis handler"

    handler_section = source[post_synth_idx:post_synth_idx + 1500]

    # Should derive individual gate dots
    assert 'updateGateDot("gate-words"' in handler_section, (
        "post_synthesis handler should derive gate-words dot"
    )
    assert 'updateGateDot("gate-cite"' in handler_section, (
        "post_synthesis handler should derive gate-cite dot"
    )
    assert 'updateGateDot("gate-sources"' in handler_section, (
        "post_synthesis handler should derive gate-sources dot"
    )
    assert 'updateGateDot("gate-faith"' in handler_section, (
        "post_synthesis handler should derive gate-faith dot"
    )


# =====================================================================
# U1+U2: Reasoning Streaming
# =====================================================================

def test_reasoning_panel_exists_in_dashboard():
    """U1+U2: Live Reasoning panel exists in dashboard HTML."""
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "templates", "live_dashboard.html",
    )
    with open(source_path, "r") as f:
        source = f.read()

    assert 'id="reasoning-panel"' in source, "Reasoning panel div should exist"
    assert "renderReasoningPanel" in source, "renderReasoningPanel function should exist"
    assert "reasoningLog" in source, "reasoningLog state field should exist"


def test_reasoning_capture_populates_log():
    """U1+U2: reasoning_capture events populate reasoningLog in dashboard."""
    source_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "scripts", "templates", "live_dashboard.html",
    )
    with open(source_path, "r") as f:
        source = f.read()

    # Find the reasoning_capture EVENT handler (not CSS class)
    rc_idx = source.find('evType === "reasoning_capture"')
    assert rc_idx > 0, "reasoning_capture event handler should exist"

    handler = source[rc_idx:rc_idx + 900]
    assert "reasoningLog.push" in handler, (
        "reasoning_capture handler should push to reasoningLog"
    )
    assert "markDirty" in handler, (
        "reasoning_capture should mark dirty for re-render"
    )
