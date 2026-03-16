"""
POLARIS Configuration Module
============================
Centralized configuration management.

Includes:
- Core: PolarisConfig, get_config, path constants
- Thresholds: All numeric thresholds from config/thresholds.yaml
"""

# Re-export everything from core (formerly src/config.py)
from src.config.core import (
    # Main config
    PolarisConfig,
    get_config,
    get_model_config,
    # Path constants
    ROOT_DIR,
    CONFIG_DIR,
    SETTINGS_DIR,
    STATE_DIR,
    OUTPUTS_DIR,
    LOGS_DIR,
    # Threshold models
    Thresholds as CoreThresholds,
    RelevanceThresholds,
    NLIThresholds as CoreNLIThresholds,
    GatingThresholds as CoreGatingThresholds,
    SufficiencyThresholds,
    OutputThresholds,
    SearchThresholds,
    RAGThresholds,
    # Model configs
    Models,
    LLMConfig,
    EmbeddingConfig,
    CrossEncoderConfig,
    NLIModelConfig,
    MiniCheckConfig,
    ChunkingConfig,
    ChunkingTemplate,
    # Search configs
    SearchSources,
    SearchEngineConfig,
    FetchingConfig,
    # Environment
    EnvSettings,
    # Loader functions
    load_yaml,
    load_thresholds,
    load_models,
    load_search_sources,
)

# Re-export from thresholds module (new config/thresholds.yaml based)
from src.config.thresholds import (
    get_threshold,
    reload_thresholds,
    validate_thresholds,
    Thresholds,
    NLIThresholds,
    ClusteringThresholds,
    VerificationThresholds,
    QualityTierThresholds,
    GatingThresholds,
    ScoringThresholds,
    SupervisorThresholds,
)

__all__ = [
    # Core config
    "PolarisConfig",
    "get_config",
    "get_model_config",
    # Path constants
    "ROOT_DIR",
    "CONFIG_DIR",
    "SETTINGS_DIR",
    "STATE_DIR",
    "OUTPUTS_DIR",
    "LOGS_DIR",
    # Threshold config (new)
    "get_threshold",
    "reload_thresholds",
    "validate_thresholds",
    "Thresholds",
    "NLIThresholds",
    "ClusteringThresholds",
    "VerificationThresholds",
    "QualityTierThresholds",
    "GatingThresholds",
    "ScoringThresholds",
    "SupervisorThresholds",
    # Core threshold models
    "CoreThresholds",
    "RelevanceThresholds",
    "CoreNLIThresholds",
    "CoreGatingThresholds",
    "SufficiencyThresholds",
    "OutputThresholds",
    "SearchThresholds",
    "RAGThresholds",
    # Model configs
    "Models",
    "LLMConfig",
    "EmbeddingConfig",
    "CrossEncoderConfig",
    "NLIModelConfig",
    "MiniCheckConfig",
    "ChunkingConfig",
    "ChunkingTemplate",
    # Search configs
    "SearchSources",
    "SearchEngineConfig",
    "FetchingConfig",
    # Environment
    "EnvSettings",
    # Loader functions
    "load_yaml",
    "load_thresholds",
    "load_models",
    "load_search_sources",
]
