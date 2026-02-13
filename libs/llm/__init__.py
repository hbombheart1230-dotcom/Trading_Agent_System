"""LLM integration layer.

This package provides a role-based router so each agent (Strategist/Scanner/etc.) can
use a different model, while keeping a stable internal interface for future provider swaps.

Preferred import:
    from libs.llm import LLMRouter
"""

from .llm_router import LLMRoute, LLMRouter
from .openrouter_client import OpenRouterClient

__all__ = ["LLMRoute", "LLMRouter", "OpenRouterClient"]
