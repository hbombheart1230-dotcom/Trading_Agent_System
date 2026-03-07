"""Data-quality contracts for external/derived signals."""

from .signal_contract import (
    DEFAULT_SIGNAL_SCORE,
    SIGNAL_STATUS_FALLBACK,
    SIGNAL_STATUS_OK,
    SIGNAL_STATUS_UNAVAILABLE,
    make_signal,
    normalize_signal_score,
)

__all__ = [
    "DEFAULT_SIGNAL_SCORE",
    "SIGNAL_STATUS_FALLBACK",
    "SIGNAL_STATUS_OK",
    "SIGNAL_STATUS_UNAVAILABLE",
    "make_signal",
    "normalize_signal_score",
]
