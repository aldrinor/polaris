"""POLARIS Deployment Validator — Validates deployment mode configuration."""

import os
import logging
from typing import Optional

logger = logging.getLogger("polaris.providers.deployment")

def _get_deployment_mode() -> str:
    """Get current deployment mode from environment (not cached at import time)."""
    return os.getenv("POLARIS_DEPLOYMENT_MODE", "cloud").lower()


def validate_deployment_mode() -> dict:
    """Validate entire deployment configuration.

    Returns a comprehensive status dict with all provider checks.
    """
    from src.providers.llm_provider import validate_llm_provider
    from src.providers.search_provider import validate_search_provider

    mode = _get_deployment_mode()
    # Read provider values fresh from env (not cached module constants)
    llm_provider = os.getenv("POLARIS_LLM_PROVIDER", "openrouter").lower()
    search_provider = os.getenv("POLARIS_SEARCH_PROVIDER", "cloud").lower()

    llm_status = validate_llm_provider()
    search_status = validate_search_provider()

    # Check for mode-specific requirements
    warnings = []
    errors = []

    if mode == "sovereign":
        # Sovereign mode MUST NOT use cloud APIs — these are errors, not warnings
        if llm_provider == "openrouter":
            errors.append(
                "POLARIS_DEPLOYMENT_MODE=sovereign but POLARIS_LLM_PROVIDER=openrouter. "
                "Sovereign mode requires vllm or ollama for full data sovereignty."
            )
        if search_provider == "cloud":
            errors.append(
                "POLARIS_DEPLOYMENT_MODE=sovereign but POLARIS_SEARCH_PROVIDER=cloud. "
                "Sovereign mode requires searxng or internal for full data sovereignty."
            )
        # Check content fetch — Jina and Firecrawl are cloud services
        if os.getenv("JINA_API_KEY"):
            warnings.append(
                "JINA_API_KEY is set in sovereign mode. Jina Reader is a cloud service. "
                "Content fetching will fall back to trafilatura (local)."
            )

        # Check NLI model (should be local)
        nli_enabled = os.getenv("PG_NLI_ENABLED", "0") == "1"
        if nli_enabled:
            logger.info("NLI verification: local MiniCheck (sovereign-compatible)")

        # Check embeddings (should be local)
        logger.info("Embeddings: local sentence-transformers (sovereign-compatible)")

    elif mode == "cloud":
        # Cloud mode needs API keys
        if llm_status["status"] == "error":
            errors.append(f"LLM provider error: {llm_status['error']}")
        if search_status["status"] == "error":
            errors.append(f"Search provider error: {search_status['error']}")

    else:
        errors.append(
            f"Unknown deployment mode: '{mode}'. "
            f"Must be 'cloud' or 'sovereign'. Set POLARIS_DEPLOYMENT_MODE in .env"
        )

    overall_status = "error" if errors else ("warning" if warnings else "ok")

    return {
        "deployment_mode": mode,
        "overall_status": overall_status,
        "llm": llm_status,
        "search": search_status,
        "nli": {
            "enabled": os.getenv("PG_NLI_ENABLED", "0") == "1",
            "model": "minicheck-flan-t5-large",
            "location": "local",
        },
        "embeddings": {
            "model": "sentence-transformers",
            "location": "local",
        },
        "content_fetch": {
            "trafilatura": "local",
            "jina": "cloud" if os.getenv("JINA_API_KEY") else "disabled",
            "firecrawl": "cloud" if os.getenv("FIRECRAWL_API_KEY") and os.getenv("PG_FIRECRAWL_ENABLED", "0") == "1" else "disabled",
        },
        "warnings": warnings,
        "errors": errors,
    }


def assert_sovereign_mode():
    """Raise error if any external API call is attempted in sovereign mode.

    Call this in sovereign mode before any external API request.
    """
    mode = _get_deployment_mode()
    if mode != "sovereign":
        return  # Not in sovereign mode, allow external calls

    raise RuntimeError(
        "POLARIS is running in SOVEREIGN mode. External API calls are blocked. "
        "All LLM, search, and content fetch operations must use local services. "
        "Check your provider configuration in .env"
    )


def assert_not_sovereign(provider_name: str = "external API"):
    """Raise error if sovereign mode is active and a cloud provider is being used.

    Args:
        provider_name: Name of the provider for the error message.
    """
    mode = _get_deployment_mode()
    if mode != "sovereign":
        return

    raise RuntimeError(
        f"POLARIS is running in SOVEREIGN mode. Cannot use {provider_name}. "
        "All operations must use local services. "
        "Check your provider configuration in .env"
    )


def get_deployment_summary() -> str:
    """Get a human-readable deployment summary."""
    status = validate_deployment_mode()
    lines = [
        f"Deployment Mode: {status['deployment_mode'].upper()}",
        f"LLM: {status['llm']['provider']} ({status['llm']['status']})",
        f"Search: {status['search']['provider']} ({status['search']['status']})",
        f"NLI: {'enabled' if status['nli']['enabled'] else 'disabled'} ({status['nli']['location']})",
        f"Embeddings: {status['embeddings']['model']} ({status['embeddings']['location']})",
    ]
    if status["warnings"]:
        lines.append(f"Warnings: {len(status['warnings'])}")
        for w in status["warnings"]:
            lines.append(f"  - {w}")
    if status["errors"]:
        lines.append(f"Errors: {len(status['errors'])}")
        for e in status["errors"]:
            lines.append(f"  - {e}")
    return "\n".join(lines)
