from __future__ import annotations

import re
from typing import Any


_LIVE_KRX_SYMBOL_RE = re.compile(r"^\d{6}$")
_LIVE_KRX_PREFIXED_RE = re.compile(r"^A\d{6}$")
_TEST_ALPHA_RE = re.compile(r"^[A-Z]{1,8}$")
_TEST_SHORT_ALNUM_RE = re.compile(r"^[A-Z]{1,4}\d{0,4}$")
_TEST_SHORT_DIGIT_RE = re.compile(r"^\d{1,5}$")


def normalize_symbol(value: Any, *, allow_test_symbols: bool = True) -> str:
    """Normalize symbol strings while rejecting live-like malformed mixed codes.

    Rules:
    - KRX live symbols are 6 digits, with optional leading `A`.
    - Test fixtures often use `AAA`, `A01`, `AAA1`; keep those when requested.
    - Reject 6/7-char mixed alnum strings like `0082N0` or `A0082N0`.
    """
    symbol = str(value or "").strip().upper()
    if not symbol:
        return ""

    if _LIVE_KRX_PREFIXED_RE.fullmatch(symbol):
        return symbol[1:]
    if _LIVE_KRX_SYMBOL_RE.fullmatch(symbol):
        return symbol

    if allow_test_symbols:
        if _TEST_ALPHA_RE.fullmatch(symbol):
            return symbol
        if _TEST_SHORT_ALNUM_RE.fullmatch(symbol):
            return symbol
        if _TEST_SHORT_DIGIT_RE.fullmatch(symbol):
            return symbol

    if len(symbol) in (6, 7) and re.search(r"[A-Z]", symbol) and re.search(r"\d", symbol):
        return ""

    return ""


def is_valid_symbol(value: Any, *, allow_test_symbols: bool = True) -> bool:
    return bool(normalize_symbol(value, allow_test_symbols=allow_test_symbols))


def is_live_equity_symbol(value: Any) -> bool:
    return bool(_LIVE_KRX_SYMBOL_RE.fullmatch(normalize_symbol(value, allow_test_symbols=False)))
