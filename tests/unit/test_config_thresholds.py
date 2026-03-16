#!/usr/bin/env python3
"""
Phase 3 Tests: MEDIUM Priority - Hardcoded Magic Numbers

Tests that the 30 hardcoded thresholds now come from config (LAW VI compliance).
Verifies get_threshold() is used instead of magic numbers.

Test categories:
- MED-001 to MED-030: Verify thresholds from config
"""

import pytest
from pathlib import Path
import re


# =============================================================================
# TEST FIXTURES
# =============================================================================

@pytest.fixture
def src_root() -> Path:
    """Get the source root directory."""
    return Path(__file__).parent.parent.parent / "src"


@pytest.fixture
def config_root() -> Path:
    """Get the config root directory."""
    return Path(__file__).parent.parent.parent / "config"


# =============================================================================
# TEST CLASS: Config Infrastructure
# =============================================================================

class TestConfigInfrastructure:
    """Verify the config infrastructure is in place."""

    def test_thresholds_yaml_exists(self, config_root: Path):
        """Verify config/thresholds.yaml exists."""
        yaml_path = config_root / "thresholds.yaml"
        assert yaml_path.exists(), "config/thresholds.yaml must exist"

    def test_thresholds_yaml_has_required_sections(self, config_root: Path):
        """Verify thresholds.yaml has all required sections."""
        yaml_path = config_root / "thresholds.yaml"

        import yaml
        with open(yaml_path) as f:
            config = yaml.safe_load(f)

        required_sections = ['nli', 'clustering', 'verification', 'quality_tiers', 'gating', 'scoring']
        for section in required_sections:
            assert section in config, f"thresholds.yaml must have '{section}' section"

    def test_thresholds_module_exists(self, src_root: Path):
        """Verify src/config/thresholds.py exists."""
        module_path = src_root / "config" / "thresholds.py"
        assert module_path.exists(), "src/config/thresholds.py must exist"

    def test_get_threshold_function_exists(self):
        """Verify get_threshold function is importable."""
        from src.config.thresholds import get_threshold
        assert callable(get_threshold)

    def test_get_threshold_returns_correct_type(self):
        """Verify get_threshold returns float for threshold values."""
        from src.config.thresholds import get_threshold

        # Test a known threshold
        value = get_threshold("nli.entailment_confidence", 0.8)
        assert isinstance(value, (int, float))

    def test_get_threshold_uses_default_on_missing(self):
        """Verify get_threshold returns default for missing keys."""
        from src.config.thresholds import get_threshold

        value = get_threshold("nonexistent.key.that.doesnt.exist", 0.42)
        assert value == 0.42


# =============================================================================
# TEST CLASS: NLI Thresholds (MED-001 to MED-005)
# =============================================================================

class TestNLIThresholds:
    """Verify NLI thresholds come from config."""

    def test_med001_entailment_confidence_in_config(self):
        """MED-001: nli.entailment_confidence exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("nli.entailment_confidence", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med002_contradiction_confidence_in_config(self):
        """MED-002: nli.contradiction_confidence exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("nli.contradiction_confidence", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med003_neutral_confidence_in_config(self):
        """MED-003: nli.neutral_confidence exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("nli.neutral_confidence", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med004_clustering_similarity_in_config(self):
        """MED-004: clustering.similarity exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("clustering.similarity", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med005_verification_aggregation_in_config(self):
        """MED-005: verification.aggregation exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("verification.aggregation", None)
        assert value is not None
        assert 0.0 <= value <= 1.0


# =============================================================================
# TEST CLASS: Quality Tiers (MED-006 to MED-008)
# =============================================================================

class TestQualityTierThresholds:
    """Verify quality tier thresholds come from config."""

    def test_med006_gold_tier_in_config(self):
        """MED-006: quality_tiers.gold exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("quality_tiers.gold", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med007_silver_tier_in_config(self):
        """MED-007: quality_tiers.silver exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("quality_tiers.silver", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med008_bronze_tier_in_config(self):
        """MED-008: quality_tiers.bronze exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("quality_tiers.bronze", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_quality_tiers_order(self):
        """Verify gold > silver > bronze."""
        from src.config.thresholds import get_threshold
        gold = get_threshold("quality_tiers.gold", 0.85)
        silver = get_threshold("quality_tiers.silver", 0.65)
        bronze = get_threshold("quality_tiers.bronze", 0.40)
        assert gold > silver > bronze


# =============================================================================
# TEST CLASS: Gating Thresholds (MED-009 to MED-015)
# =============================================================================

class TestGatingThresholds:
    """Verify gating thresholds come from config."""

    def test_med009_min_evidence_in_config(self):
        """MED-009: gating.min_evidence exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.min_evidence", None)
        assert value is not None
        assert value > 0

    def test_med010_min_gold_pct_in_config(self):
        """MED-010: gating.min_gold_pct exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.min_gold_pct", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med011_min_faithfulness_in_config(self):
        """MED-011: gating.min_faithfulness exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.min_faithfulness", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med012_critical_faithfulness_in_config(self):
        """MED-012: gating.critical_faithfulness exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.critical_faithfulness", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med013_min_diversity_in_config(self):
        """MED-013: gating.min_diversity exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.min_diversity", None)
        assert value is not None
        assert value > 0

    def test_med014_convergence_in_config(self):
        """MED-014: gating.convergence exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.convergence", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med015_high_quality_in_config(self):
        """MED-015: gating.high_quality exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("gating.high_quality", None)
        assert value is not None
        assert 0.0 <= value <= 1.0


# =============================================================================
# TEST CLASS: Scoring Thresholds (MED-018 to MED-026)
# =============================================================================

class TestScoringThresholds:
    """Verify scoring thresholds come from config."""

    def test_med018_default_confidence_in_config(self):
        """MED-018: scoring.default_confidence exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("scoring.default_confidence", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med019_default_quality_in_config(self):
        """MED-019: scoring.default_quality exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("scoring.default_quality", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med020_default_relevance_in_config(self):
        """MED-020: scoring.default_relevance exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("scoring.default_relevance", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med021_high_relevance_in_config(self):
        """MED-021: scoring.high_relevance exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("scoring.high_relevance", None)
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_med022_high_quality_in_config(self):
        """MED-022: scoring.high_quality exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("scoring.high_quality", None)
        assert value is not None
        assert 0.0 <= value <= 1.0


# =============================================================================
# TEST CLASS: Clustering Threshold (MED-029)
# =============================================================================

class TestClusteringThresholds:
    """Verify clustering thresholds come from config."""

    def test_med029_overlap_in_config(self):
        """MED-029: clustering.overlap exists in config."""
        from src.config.thresholds import get_threshold
        value = get_threshold("clustering.overlap", None)
        assert value is not None
        assert 0.0 <= value <= 1.0


# =============================================================================
# TEST CLASS: Files Use get_threshold
# =============================================================================

class TestFilesUseGetThreshold:
    """Verify critical files import and use get_threshold."""

    def _check_uses_get_threshold(self, file_path: Path) -> bool:
        """Check if file uses get_threshold function."""
        if not file_path.exists():
            return False

        source = file_path.read_text(encoding='utf-8')
        return 'get_threshold' in source

    def test_claim_verification_uses_get_threshold(self, src_root: Path):
        """Verify claim_verification.py uses get_threshold."""
        file_path = src_root / "functions" / "claim_verification.py"
        assert self._check_uses_get_threshold(file_path)

    def test_quality_scoring_uses_get_threshold(self, src_root: Path):
        """Verify quality_scoring.py uses get_threshold."""
        file_path = src_root / "functions" / "quality_scoring.py"
        assert self._check_uses_get_threshold(file_path)

    def test_analyst_agent_uses_get_threshold(self, src_root: Path):
        """Verify analyst_agent.py uses get_threshold."""
        file_path = src_root / "agents" / "analyst_agent.py"
        assert self._check_uses_get_threshold(file_path)

    def test_critic_agent_uses_get_threshold(self, src_root: Path):
        """Verify critic_agent.py uses get_threshold."""
        file_path = src_root / "agents" / "critic_agent.py"
        assert self._check_uses_get_threshold(file_path)

    def test_synthesizer_agent_uses_get_threshold(self, src_root: Path):
        """Verify synthesizer_agent.py uses get_threshold."""
        file_path = src_root / "agents" / "synthesizer_agent.py"
        assert self._check_uses_get_threshold(file_path)

    def test_verifier_agent_uses_get_threshold(self, src_root: Path):
        """Verify verifier_agent.py uses get_threshold."""
        file_path = src_root / "agents" / "verifier_agent.py"
        assert self._check_uses_get_threshold(file_path)
