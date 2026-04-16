"""
POLARIS Configuration Loader
============================
Centralized configuration management using pydantic-settings.
All parameters MUST come from here - NEVER hard-coded in source.

Usage:
    from src.config import get_config
    config = get_config()
    threshold = config.thresholds.relevance.gold_threshold
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Any, Dict, List, Optional

# FIX 120: Load dotenv BEFORE anything else to ensure API keys are available
# This must happen before pydantic settings are instantiated
# LOOPBACK-FIX: override=False so pre-set os.environ wins over .env defaults.
from dotenv import load_dotenv
_ROOT_DIR = Path(__file__).parent.parent.parent
load_dotenv(_ROOT_DIR / ".env", override=False)

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


# =============================================================================
# PATH CONSTANTS
# =============================================================================

ROOT_DIR = _ROOT_DIR  # Use the same path we already computed
CONFIG_DIR = ROOT_DIR / "config"
SETTINGS_DIR = CONFIG_DIR / "settings"
STATE_DIR = ROOT_DIR / "state"
OUTPUTS_DIR = ROOT_DIR / "outputs"
LOGS_DIR = ROOT_DIR / "logs"


# =============================================================================
# THRESHOLD MODELS
# =============================================================================

class RelevanceThresholds(BaseModel):
    """Relevance filtering thresholds."""
    hard_threshold: float = 0.35
    soft_threshold: float = 0.55
    hard_weight: float = 0.4
    soft_weight: float = 0.6
    gold_threshold: float = 0.70
    silver_threshold: float = 0.55
    bronze_threshold: float = 0.40


class NLIThresholds(BaseModel):
    """NLI integrity thresholds."""
    integrity_pass: float = 0.85
    integrity_warn: float = 0.70
    max_pairs: int = 1000
    contradiction_threshold: float = 0.80
    # SOTA: Entailment-only mode - when True, only ENTAILMENT counts
    # NEUTRAL is treated as non-supporting (stricter but more accurate)
    entailment_only: bool = True


class GatingThresholds(BaseModel):
    """Gating logic thresholds."""
    case1_sufficiency: float = 0.80
    case1_confidence: float = 0.70
    case1_integrity: float = 0.70
    case1_validation: float = 0.60
    case1_faithfulness: float = 0.80
    max_no_evidence_gaps: int = 0  # Max NO_EVIDENCE questions before blocking CASE_1
    case2_sufficiency: float = 0.50
    case4_integrity: float = 0.70


class SufficiencyThresholds(BaseModel):
    """Sufficiency check thresholds."""
    min_gold_chunks: int = 5
    min_total_chunks: int = 15
    min_unique_sources: int = 5
    min_evidence_words: int = 10000
    hard_constraint_coverage: float = 1.0
    soft_constraint_coverage: float = 0.6


class OutputThresholds(BaseModel):
    """Output quality thresholds."""
    min_word_count: int = 2000
    min_citations: int = 5
    min_source_diversity: int = 5
    min_verified_claims: int = 30
    # SOTA: Self-refinement critique loop settings
    enable_self_refinement: bool = True
    max_refinement_iterations: int = 2
    refinement_approval_threshold: float = 0.80


class SearchThresholds(BaseModel):
    """Search thresholds - SOTA-aligned with Gemini Deep Research."""
    min_queries: int = 100  # SOTA: 200+ searches, we target 100+ queries
    min_success_rate: float = 0.50  # Allow more attempts
    max_results_per_engine: int = 100  # SOTA: increased coverage
    max_urls_to_fetch: int = 300  # SOTA: Fetch up to 300 URLs for comprehensive coverage


class RAGThresholds(BaseModel):
    """RAG thresholds - SOTA-aligned for comprehensive evidence handling."""
    context_budget_tokens: int = 16000  # SOTA: doubled for more evidence
    top_k_per_query: int = 20  # SOTA: doubled for more context
    min_confidence: float = 0.50


class Thresholds(BaseModel):
    """All quality thresholds."""
    relevance: RelevanceThresholds = Field(default_factory=RelevanceThresholds)
    nli: NLIThresholds = Field(default_factory=NLIThresholds)
    gating: GatingThresholds = Field(default_factory=GatingThresholds)
    sufficiency: SufficiencyThresholds = Field(default_factory=SufficiencyThresholds)
    output: OutputThresholds = Field(default_factory=OutputThresholds)
    search: SearchThresholds = Field(default_factory=SearchThresholds)
    rag: RAGThresholds = Field(default_factory=RAGThresholds)


# =============================================================================
# MODEL CONFIGS
# =============================================================================

class TierConfig(BaseModel):
    """Configuration for a model tier (simple/important)."""
    model: str = "gemini-2.5-flash"
    temperature: float = 0.0
    max_tokens: int = 4096
    thinking_budget: int = 0  # 0=disabled, >0=enabled (some models require >0)


class LLMTiers(BaseModel):
    """Tiered model configuration for agents."""
    simple: TierConfig = TierConfig(
        model="gemini-2.5-flash",
        temperature=0.0,
        max_tokens=4096,
        thinking_budget=0  # Disable thinking for reliable structured output
    )
    important: TierConfig = TierConfig(
        model="gemini-3-pro-preview",
        temperature=0.1,
        max_tokens=16000,
        thinking_budget=2048  # Required by model - enables reasoning
    )


class LLMConfig(BaseModel):
    """LLM configuration."""
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"
    max_tokens: int = 65536
    temperature: float = 0.7
    timeout_seconds: int = 120
    fallback_provider: Optional[str] = None
    fallback_model: Optional[str] = None
    tiers: Optional[LLMTiers] = None


class EmbeddingConfig(BaseModel):
    """Embedding model configuration."""
    provider: str = "sentence_transformers"
    model: str = "all-MiniLM-L6-v2"
    dimension: int = 384
    batch_size: int = 32
    device: str = "auto"
    max_seq_length: int = 512


class CrossEncoderConfig(BaseModel):
    """Cross-encoder configuration."""
    model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    batch_size: int = 16
    device: str = "auto"


class NLIModelConfig(BaseModel):
    """NLI model configuration."""
    model: str = "microsoft/deberta-v3-large-mnli"
    batch_size: int = 8
    device: str = "auto"
    entailment_label: str = "ENTAILMENT"
    neutral_label: str = "NEUTRAL"
    contradiction_label: str = "CONTRADICTION"


class MiniCheckConfig(BaseModel):
    """SOTA: MiniCheck RAG-aware fact checking configuration."""
    model: str = "lytang/MiniCheck-Flan-T5-Large"
    relevance_gate_threshold: float = 0.10
    contradiction_confidence: float = 0.70
    device: str = "auto"
    batch_size: int = 8


class ChunkingTemplate(BaseModel):
    """Chunking template configuration."""
    chunk_size: int
    chunk_overlap: int
    separators: List[str]


class ChunkingConfig(BaseModel):
    """Chunking configuration."""
    stage_templates: Dict[int, str] = Field(default_factory=dict)
    templates: Dict[str, ChunkingTemplate] = Field(default_factory=dict)


class Models(BaseModel):
    """All model configurations."""
    llm: LLMConfig = Field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    cross_encoder: CrossEncoderConfig = Field(default_factory=CrossEncoderConfig)
    nli: NLIModelConfig = Field(default_factory=NLIModelConfig)
    minicheck: MiniCheckConfig = Field(default_factory=MiniCheckConfig)
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)


# =============================================================================
# SEARCH CONFIG
# =============================================================================

class SearchEngineConfig(BaseModel):
    """Single search engine configuration."""
    enabled: bool = True
    priority: int = 1
    rate_limit: Optional[int] = None
    daily_limit: Optional[int] = None
    timeout_seconds: int = 30
    base_url: Optional[str] = None
    endpoints: Dict[str, str] = Field(default_factory=dict)
    buckets: List[str] = Field(default_factory=list)


class FetchingConfig(BaseModel):
    """Content fetching configuration."""
    user_agent: str = "Mozilla/5.0 (compatible; POLARIS/1.0; Research Bot)"
    connect_timeout: int = 10
    read_timeout: int = 30
    max_retries: int = 3
    retry_delay_ms: int = 1000
    retry_backoff: float = 2.0
    max_concurrent_fetches: int = 10
    max_content_size_mb: int = 10
    max_pdf_pages: int = 50
    fallback_chain: List[str] = Field(default_factory=lambda: ["requests", "playwright", "archive_org"])


class SearchSources(BaseModel):
    """Search sources configuration."""
    query_distribution: Dict[str, float] = Field(default_factory=dict)
    engines: Dict[str, SearchEngineConfig] = Field(default_factory=dict)
    fetching: FetchingConfig = Field(default_factory=FetchingConfig)
    authority_anchors: Dict[str, List[str]] = Field(default_factory=dict)
    geographic_keywords: Dict[str, List[str]] = Field(default_factory=dict)


# =============================================================================
# ENVIRONMENT SETTINGS
# =============================================================================

class EnvSettings(BaseSettings):
    """Environment variables."""

    # API Keys - Primary LLM (KIMI K2.5 via Fireworks)
    fireworks_api_key: str = Field(default="", alias="FIREWORKS_API_KEY")

    # API Keys - Fallback LLM (Gemini)
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    # API Keys - Search and Research
    serper_api_key: str = Field(default="", alias="SERPER_API_KEY")
    ncbi_api_key: str = Field(default="", alias="NCBI_API_KEY")
    semantic_scholar_api_key: str = Field(default="", alias="SEMANTIC_SCHOLAR_API_KEY")

    # Paths
    chroma_persist_dir: str = Field(default="./memory/chroma_db", alias="CHROMA_PERSIST_DIR")

    # Performance
    max_concurrent_fetches: int = Field(default=10, alias="MAX_CONCURRENT_FETCHES")
    gpu_device: int = Field(default=0, alias="GPU_DEVICE")

    class Config:
        env_file = str(ROOT_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


# =============================================================================
# MAIN CONFIG CLASS
# =============================================================================

class PolarisConfig(BaseModel):
    """Complete POLARIS configuration."""

    # Sub-configs
    thresholds: Thresholds = Field(default_factory=Thresholds)
    models: Models = Field(default_factory=Models)
    search: SearchSources = Field(default_factory=SearchSources)
    env: EnvSettings = Field(default_factory=EnvSettings)

    # Paths
    root_dir: Path = ROOT_DIR
    config_dir: Path = CONFIG_DIR
    settings_dir: Path = SETTINGS_DIR
    state_dir: Path = STATE_DIR
    outputs_dir: Path = OUTPUTS_DIR
    logs_dir: Path = LOGS_DIR

    class Config:
        arbitrary_types_allowed = True


# =============================================================================
# LOADER FUNCTIONS
# =============================================================================

def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_thresholds() -> Thresholds:
    """Load thresholds from YAML."""
    data = load_yaml(SETTINGS_DIR / "thresholds.yaml")
    return Thresholds(
        relevance=RelevanceThresholds(**data.get("relevance", {})),
        nli=NLIThresholds(**data.get("nli", {})),
        gating=GatingThresholds(**data.get("gating", {})),
        sufficiency=SufficiencyThresholds(**data.get("sufficiency", {})),
        output=OutputThresholds(**data.get("output", {})),
        search=SearchThresholds(**data.get("search", {})),
        rag=RAGThresholds(**data.get("rag", {})),
    )


def load_models() -> Models:
    """Load model configs from YAML."""
    data = load_yaml(SETTINGS_DIR / "models.yaml")

    chunking_data = data.get("chunking", {})
    templates = {}
    for name, tpl in chunking_data.get("templates", {}).items():
        templates[name] = ChunkingTemplate(**tpl)

    return Models(
        llm=LLMConfig(**data.get("llm", {})),
        embedding=EmbeddingConfig(**data.get("embedding", {})),
        cross_encoder=CrossEncoderConfig(**data.get("cross_encoder", {})),
        nli=NLIModelConfig(**data.get("nli", {})),
        minicheck=MiniCheckConfig(**data.get("minicheck", {})),
        chunking=ChunkingConfig(
            stage_templates=chunking_data.get("stage_templates", {}),
            templates=templates,
        ),
    )


def load_search_sources() -> SearchSources:
    """Load search sources from YAML."""
    data = load_yaml(SETTINGS_DIR / "search_sources.yaml")

    engines = {}
    for name, engine_data in data.get("engines", {}).items():
        engines[name] = SearchEngineConfig(**engine_data)

    return SearchSources(
        query_distribution=data.get("query_distribution", {}),
        engines=engines,
        fetching=FetchingConfig(**data.get("fetching", {})),
        authority_anchors=data.get("authority_anchors", {}),
        geographic_keywords=data.get("geographic_keywords", {}),
    )


@lru_cache(maxsize=1)
def get_config() -> PolarisConfig:
    """
    Get the complete POLARIS configuration.
    Cached for performance - call once at startup.
    """
    return PolarisConfig(
        thresholds=load_thresholds(),
        models=load_models(),
        search=load_search_sources(),
        env=EnvSettings(),
    )


def clear_config_cache():
    """
    FIX-121: Clear the config cache to force reload from environment.

    Call this after reloading .env to ensure get_config() returns
    fresh values including any updated API keys.
    """
    get_config.cache_clear()


# =============================================================================
# CONVENIENCE ACCESSORS
# =============================================================================

def get_threshold(path: str) -> Any:
    """
    Get a threshold value by dot-notation path.

    Example:
        get_threshold("relevance.gold_threshold") -> 0.70
    """
    config = get_config()
    obj = config.thresholds
    for part in path.split("."):
        obj = getattr(obj, part)
    return obj


def get_model_config(model_type: str) -> BaseModel:
    """Get model configuration by type."""
    config = get_config()
    return getattr(config.models, model_type)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "PolarisConfig",
    "get_config",
    "clear_config_cache",  # FIX-121: Export cache clearing function
    "get_threshold",
    "get_model_config",
    "ROOT_DIR",
    "CONFIG_DIR",
    "SETTINGS_DIR",
    "STATE_DIR",
    "OUTPUTS_DIR",
    "LOGS_DIR",
]
