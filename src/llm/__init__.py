"""
POLARIS LLM Clients
===================
Language model integrations for generation and reasoning.

Includes:
- KimiClient: KIMI K2.5 via Fireworks AI (PRIMARY - thinking mode support)
- GeminiClient: Gemini API for generation (FALLBACK)
- DeBERTaNLI: Local DeBERTa model for NLI (FREE)
"""

from src.llm.kimi_client import KimiClient, get_kimi_client, reset_kimi_clients
from src.llm.gemini_client import GeminiClient, get_gemini_client
from src.llm.deberta_client import (
    DeBERTaNLI,
    predict_nli,
    predict_nli_batch,
    is_available as deberta_available,
    validate_nli_available,
    NLIModelUnavailableError,
)
from src.llm.factory import get_llm, LLMWrapper, reset_llm

__all__ = [
    # Primary LLM (KIMI K2.5)
    "KimiClient",
    "get_kimi_client",
    "reset_kimi_clients",
    # Fallback LLM (Gemini)
    "GeminiClient",
    "get_gemini_client",
    # NLI
    "DeBERTaNLI",
    "predict_nli",
    "predict_nli_batch",
    "deberta_available",
    "validate_nli_available",
    "NLIModelUnavailableError",
    # Factory
    "get_llm",
    "LLMWrapper",
    "reset_llm",
]
