"""Central, typed configuration — the single source of truth (Phase 1).

This module replaces scattered ``os.getenv`` reads with one typed settings object. Phase 1 migrates
it in slices; this first slice is **model selection** (which model each role uses), because
"one file controls every model" was the headline requirement.

Byte-identical rule: every field's default is the EXACT current literal, and every field maps to its
existing ``PG_*`` env var (via ``env_prefix``), so behaviour is unchanged. The characterization test
``tests/test_settings_models.py`` proves each field resolves identically to the current
``os.getenv(KEY, default)`` — both unset (default) and set (override).

Nothing imports this yet; call sites migrate module-by-module behind that test (see
``docs/review_readiness/config_governance.md``). The remaining model keys with multi-line/computed
defaults (``PG_CONTRADICTION_MODEL``, ``PG_ENTAILMENT_MODEL``, ``PG_RERANKER_MODEL``,
``PG_CONTENT_RELEVANCE_RERANKER_MODEL``) are added when their owning module migrates.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelSettings(BaseSettings):
    """Model-selection config.

    Each field reads its EXACT ``PG_*`` env var **case-sensitively** (via an explicit
    ``validation_alias``), matching ``os.getenv("PG_...")`` byte-for-byte — an ``env_prefix`` +
    case-insensitive setup would (wrongly) also match differently-cased names.
    """

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore")

    judge_model: str = Field("qwen/qwen3.6-35b-a3b", validation_alias="PG_JUDGE_MODEL")
    sentinel_model: str = Field("minimax/minimax-m2", validation_alias="PG_SENTINEL_MODEL")
    sweep_deepener_model: str = Field("deepseek/deepseek-v4-pro", validation_alias="PG_SWEEP_DEEPENER_MODEL")
    nli_model: str = Field("flan-t5-large", validation_alias="PG_NLI_MODEL")
    faithlens_model: str = Field("ssz1111/FaithLens", validation_alias="PG_FAITHLENS_MODEL")
    embed_model: str = Field("Qwen/Qwen3-Embedding-8B", validation_alias="PG_EMBED_MODEL")
    embedder_model: str = Field("", validation_alias="PG_EMBEDDER_MODEL")
    planning_gate_model: str = Field("", validation_alias="PG_PLANNING_GATE_MODEL")
    policy_model: str = Field("", validation_alias="PG_POLICY_MODEL")
    outliner_agent_model: str = Field("z-ai/glm-5.2", validation_alias="PG_OUTLINER_AGENT_MODEL")
    outliner_code_model: str = Field("deepseek/deepseek-v4-pro", validation_alias="PG_OUTLINER_CODE_MODEL")
    evaluator_model: str | None = Field(None, validation_alias="PG_EVALUATOR_MODEL")


# Authoritative registry: env var -> (settings field, EXACT current default). The characterization
# test iterates this to prove byte-identical parity with today's os.getenv resolution.
MODEL_KEY_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "PG_JUDGE_MODEL": ("judge_model", "qwen/qwen3.6-35b-a3b"),
    "PG_SENTINEL_MODEL": ("sentinel_model", "minimax/minimax-m2"),
    "PG_SWEEP_DEEPENER_MODEL": ("sweep_deepener_model", "deepseek/deepseek-v4-pro"),
    "PG_NLI_MODEL": ("nli_model", "flan-t5-large"),
    "PG_FAITHLENS_MODEL": ("faithlens_model", "ssz1111/FaithLens"),
    "PG_EMBED_MODEL": ("embed_model", "Qwen/Qwen3-Embedding-8B"),
    "PG_EMBEDDER_MODEL": ("embedder_model", ""),
    "PG_PLANNING_GATE_MODEL": ("planning_gate_model", ""),
    "PG_POLICY_MODEL": ("policy_model", ""),
    "PG_OUTLINER_AGENT_MODEL": ("outliner_agent_model", "z-ai/glm-5.2"),
    "PG_OUTLINER_CODE_MODEL": ("outliner_code_model", "deepseek/deepseek-v4-pro"),
    "PG_EVALUATOR_MODEL": ("evaluator_model", None),
}


def get_model_settings() -> ModelSettings:
    """Return a FRESH ``ModelSettings`` reading the CURRENT environment.

    **Byte-identical migration contract.** ``os.getenv`` reads the current environment on *every*
    call; a ``ModelSettings`` instance instead *snapshots* the environment at construction. So a
    migrated call site must replace ``os.getenv("PG_X", default)`` with ``get_model_settings().x``
    (a fresh read), **never** a cached module-level instance — otherwise it would go stale relative
    to a runtime env change. Two model keys are set at process startup by scripts
    (``PG_NLI_MODEL`` via ``setdefault``, ``PG_EVALUATOR_MODEL`` from a CLI arg) and none are mutated
    mid-run, so a fresh read at the call site is exactly equivalent to the original ``os.getenv``.
    Construction is cheap (12 fields); the freshness guarantee is what preserves behaviour.
    """
    return ModelSettings()
