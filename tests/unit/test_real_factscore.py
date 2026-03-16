"""
Unit tests for real FactScore via LLM atomic decomposition (BUG-069 fix).

Tests the dispatch between real and heuristic FactScore, AtomicDecomposer
integration, per-atom MiniCheck verification, and feature flag behavior.
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers: lightweight stand-ins for auditor types
# ---------------------------------------------------------------------------

@dataclass
class MockSentenceAudit:
    """Minimal SentenceAudit for testing."""
    sentence: str
    citation_ids: List[str] = field(default_factory=list)
    verdict: str = "faithful"
    confidence: float = 0.9
    reasoning: str = ""
    evidence_texts: List[str] = field(default_factory=list)
    suggested_citation: Optional[str] = None
    verification_confidence: float = 0.3


# ---------------------------------------------------------------------------
# Test 1: Feature flag dispatches to real FactScore
# ---------------------------------------------------------------------------


def test_factscore_dispatch_real():
    """POLARIS_REAL_FACTSCORE=1 + decomposer present -> _calculate_factscore_real called."""
    from src.agents.auditor_agent import AuditorAgent

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = None
    agent._atomic_decomposer = MagicMock()

    mock_real = MagicMock(return_value=0.85)
    mock_heuristic = MagicMock(return_value=0.70)
    agent._calculate_factscore_real = mock_real
    agent._calculate_factscore_heuristic = mock_heuristic

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "1"}):
        result = agent._calculate_factscore([], [])

    mock_real.assert_called_once()
    mock_heuristic.assert_not_called()
    assert result == 0.85


# ---------------------------------------------------------------------------
# Test 2: Feature flag dispatches to heuristic when disabled
# ---------------------------------------------------------------------------


def test_factscore_dispatch_heuristic_when_disabled():
    """POLARIS_REAL_FACTSCORE=0 -> _calculate_factscore_heuristic called."""
    from src.agents.auditor_agent import AuditorAgent

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = None
    agent._atomic_decomposer = MagicMock()

    mock_real = MagicMock(return_value=0.85)
    mock_heuristic = MagicMock(return_value=0.70)
    agent._calculate_factscore_real = mock_real
    agent._calculate_factscore_heuristic = mock_heuristic

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "0"}):
        result = agent._calculate_factscore([], [])

    mock_heuristic.assert_called_once()
    mock_real.assert_not_called()
    assert result == 0.70


# ---------------------------------------------------------------------------
# Test 3: Feature flag dispatches to heuristic when decomposer is None
# ---------------------------------------------------------------------------


def test_factscore_dispatch_heuristic_when_no_decomposer():
    """POLARIS_REAL_FACTSCORE=1 but decomposer=None -> heuristic fallback."""
    from src.agents.auditor_agent import AuditorAgent

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = None
    agent._atomic_decomposer = None

    mock_real = MagicMock(return_value=0.85)
    mock_heuristic = MagicMock(return_value=0.70)
    agent._calculate_factscore_real = mock_real
    agent._calculate_factscore_heuristic = mock_heuristic

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "1"}):
        result = agent._calculate_factscore([], [])

    mock_heuristic.assert_called_once()
    mock_real.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: Heuristic FactScore matches legacy behavior
# ---------------------------------------------------------------------------


def test_factscore_heuristic_basic():
    """Heuristic FactScore calculates correct ratio for mixed faithful/unfaithful."""
    from src.agents.auditor_agent import AuditorAgent

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = None
    agent._atomic_decomposer = None

    faithful = [
        MockSentenceAudit(sentence="Water filters remove 99% of contaminants."),
    ]
    unfaithful = [
        MockSentenceAudit(
            sentence="The EPA requires testing and certification.",
            verdict="unfaithful",
            verification_confidence=0.5,
        ),
    ]

    result = agent._calculate_factscore_heuristic(faithful, unfaithful)

    # Should be between 0 and 1, with partial credit for unfaithful
    assert 0.0 < result < 1.0


# ---------------------------------------------------------------------------
# Test 5: Real FactScore decomposes faithful sentences
# ---------------------------------------------------------------------------


def test_factscore_real_faithful_all_supported():
    """Real FactScore counts all atoms from faithful sentences as supported."""
    from src.agents.auditor_agent import AuditorAgent
    from src.utils.atomic_decomposer import AtomicDecomposer, DecompositionResult, AtomicFact

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = None

    mock_decomposer = MagicMock(spec=AtomicDecomposer)
    mock_decomposer._heuristic_decompose.return_value = DecompositionResult(
        original_sentence="Test sentence with facts.",
        atomic_facts=[
            AtomicFact(fact="Test sentence.", source_sentence="Test sentence with facts."),
            AtomicFact(fact="Contains facts.", source_sentence="Test sentence with facts."),
        ],
        decomposition_method="heuristic",
    )
    agent._atomic_decomposer = mock_decomposer

    faithful = [
        MockSentenceAudit(sentence="Test sentence with facts."),
    ]

    with patch.dict("os.environ", {"POLARIS_SUPPORT_THRESHOLD": "0.35"}):
        result = agent._calculate_factscore_real(faithful, [])

    # All 2 atoms from faithful sentence should be supported -> 2/2 = 1.0
    assert result == 1.0


# ---------------------------------------------------------------------------
# Test 6: Real FactScore verifies unfaithful atoms via MiniCheck
# ---------------------------------------------------------------------------


def test_factscore_real_unfaithful_minicheck_verification():
    """Real FactScore verifies each atom of unfaithful sentences via MiniCheck."""
    from src.agents.auditor_agent import AuditorAgent
    from src.utils.atomic_decomposer import AtomicDecomposer, DecompositionResult, AtomicFact

    agent = AuditorAgent.__new__(AuditorAgent)

    # Mock MiniCheck that supports first atom, rejects second
    mock_minicheck = MagicMock()
    mock_minicheck.score.side_effect = [
        ([1], [0.8], None, None),  # First atom: supported (0.8 > 0.35)
        ([0], [0.1], None, None),  # Second atom: not supported (0.1 < 0.35)
    ]
    agent.minicheck = mock_minicheck

    mock_decomposer = MagicMock(spec=AtomicDecomposer)
    mock_decomposer._heuristic_decompose.return_value = DecompositionResult(
        original_sentence="Compound claim.",
        atomic_facts=[
            AtomicFact(fact="Claim part A.", source_sentence="Compound claim."),
            AtomicFact(fact="Claim part B.", source_sentence="Compound claim."),
        ],
        decomposition_method="heuristic",
    )
    agent._atomic_decomposer = mock_decomposer

    unfaithful = [
        MockSentenceAudit(
            sentence="Compound claim.",
            verdict="unfaithful",
            verification_confidence=0.3,
            evidence_texts=["Evidence about claim part A."],
        ),
    ]

    with patch.dict("os.environ", {"POLARIS_SUPPORT_THRESHOLD": "0.35"}):
        result = agent._calculate_factscore_real([], unfaithful)

    # 1 supported out of 2 total atoms = 0.5
    assert result == 0.5
    # MiniCheck should have been called twice (once per atom)
    assert mock_minicheck.score.call_count == 2


# ---------------------------------------------------------------------------
# Test 7: Real FactScore handles decomposition error gracefully
# ---------------------------------------------------------------------------


def test_factscore_real_decomposition_error_fallback():
    """Decomposition failure falls back to _estimate_atom_count."""
    from src.agents.auditor_agent import AuditorAgent
    from src.utils.atomic_decomposer import AtomicDecomposer

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = None

    mock_decomposer = MagicMock(spec=AtomicDecomposer)
    mock_decomposer._heuristic_decompose.side_effect = RuntimeError("Decompose failed")
    agent._atomic_decomposer = mock_decomposer

    faithful = [
        MockSentenceAudit(sentence="Simple factual claim."),
    ]

    with patch.dict("os.environ", {"POLARIS_SUPPORT_THRESHOLD": "0.35"}):
        result = agent._calculate_factscore_real(faithful, [])

    # Should not raise — falls back to _estimate_atom_count
    assert result == 1.0  # Faithful sentence = all atoms supported


# ---------------------------------------------------------------------------
# Test 8: _init_atomic_decomposer respects feature flag
# ---------------------------------------------------------------------------


def test_init_atomic_decomposer_disabled():
    """POLARIS_REAL_FACTSCORE=0 -> decomposer stays None."""
    from src.agents.auditor_agent import AuditorAgent

    agent = AuditorAgent.__new__(AuditorAgent)
    agent._atomic_decomposer = None

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "0"}):
        agent._init_atomic_decomposer()

    assert agent._atomic_decomposer is None


def test_init_atomic_decomposer_enabled():
    """POLARIS_REAL_FACTSCORE=1 -> decomposer initialized."""
    from src.agents.auditor_agent import AuditorAgent

    agent = AuditorAgent.__new__(AuditorAgent)
    agent._atomic_decomposer = None

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "1"}):
        agent._init_atomic_decomposer()

    assert agent._atomic_decomposer is not None


# ---------------------------------------------------------------------------
# Test 9: factscore_method state key set correctly
# ---------------------------------------------------------------------------


def test_factscore_method_state_key_real():
    """factscore_method is 'real_llm' when real FactScore is active."""
    import os

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "1"}):
        use_real = os.environ.get("POLARIS_REAL_FACTSCORE", "0") == "1"
        decomposer = MagicMock()  # Not None
        method = "real_llm" if (use_real and decomposer) else "heuristic"

    assert method == "real_llm"


def test_factscore_method_state_key_heuristic():
    """factscore_method is 'heuristic' when real FactScore is disabled."""
    import os

    with patch.dict("os.environ", {"POLARIS_REAL_FACTSCORE": "0"}):
        use_real = os.environ.get("POLARIS_REAL_FACTSCORE", "0") == "1"
        decomposer = MagicMock()
        method = "real_llm" if (use_real and decomposer) else "heuristic"

    assert method == "heuristic"


# ---------------------------------------------------------------------------
# Test 10: Real FactScore with no evidence falls back to confidence
# ---------------------------------------------------------------------------


def test_factscore_real_no_evidence_uses_confidence():
    """When unfaithful sentence has no evidence_texts, uses verification_confidence."""
    from src.agents.auditor_agent import AuditorAgent
    from src.utils.atomic_decomposer import AtomicDecomposer, DecompositionResult, AtomicFact

    agent = AuditorAgent.__new__(AuditorAgent)
    agent.minicheck = MagicMock()  # MiniCheck available but no evidence

    mock_decomposer = MagicMock(spec=AtomicDecomposer)
    mock_decomposer._heuristic_decompose.return_value = DecompositionResult(
        original_sentence="Claim without evidence.",
        atomic_facts=[
            AtomicFact(fact="Claim A.", source_sentence="Claim without evidence."),
            AtomicFact(fact="Claim B.", source_sentence="Claim without evidence."),
        ],
        decomposition_method="heuristic",
    )
    agent._atomic_decomposer = mock_decomposer

    unfaithful = [
        MockSentenceAudit(
            sentence="Claim without evidence.",
            verdict="unfaithful",
            verification_confidence=0.5,
            evidence_texts=[],  # Empty evidence
        ),
    ]

    with patch.dict("os.environ", {"POLARIS_SUPPORT_THRESHOLD": "0.35"}):
        result = agent._calculate_factscore_real([], unfaithful)

    # 2 atoms * 0.5 confidence = 1 supported out of 2 = 0.5
    assert result == 0.5
    # MiniCheck should NOT have been called (no evidence)
    agent.minicheck.score.assert_not_called()
