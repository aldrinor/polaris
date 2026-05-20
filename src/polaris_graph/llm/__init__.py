"""LLM client for polaris graph — OpenRouter gateway.

Default model = OPENROUTER_DEFAULT_MODEL (default deepseek/deepseek-v4-pro
per I-cd-009 / GH#624 Carney demo lock).
"""

from src.polaris_graph.llm.openrouter_client import OpenRouterClient

__all__ = ["OpenRouterClient"]
