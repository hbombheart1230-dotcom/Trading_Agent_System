"""
Provider registry for news collection.

This module is intentionally small and dependency-free so it can be imported
during test collection without side effects.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Type

from .base import NewsProvider

# Provider factory signature
ProviderFactory = Callable[[], NewsProvider]

_PROVIDERS: Dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under a name."""
    _PROVIDERS[str(name).strip().lower()] = factory


def get_provider(name: Optional[str] = None) -> NewsProvider:
    """
    Return a provider instance.

    - If name is None, uses 'naver' as default.
    - Raises KeyError if provider is unknown.
    """
    key = (name or "naver").strip().lower()
    if key not in _PROVIDERS:
        raise KeyError(f"Unknown news provider: {key}. Available: {sorted(_PROVIDERS.keys())}")
    return _PROVIDERS[key]()


def available_providers() -> list[str]:
    return sorted(_PROVIDERS.keys())


# --- default registrations (safe imports) ---
# Importing these modules should be cheap (stubs in our project).
try:
    from .naver import NaverNewsProvider  # type: ignore
    register_provider("naver", lambda: NaverNewsProvider())
except Exception:
    pass

try:
    from .google_news import GoogleNewsProvider  # type: ignore
    register_provider("google", lambda: GoogleNewsProvider())
    register_provider("google_news", lambda: GoogleNewsProvider())
except Exception:
    pass
