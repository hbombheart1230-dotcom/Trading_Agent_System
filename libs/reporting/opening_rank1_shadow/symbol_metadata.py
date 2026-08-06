from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def _load(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = payload.get("symbols") if isinstance(payload, Mapping) else {}
    return {
        str(symbol): dict(row)
        for symbol, row in (rows or {}).items()
        if isinstance(row, Mapping)
    }


def load_or_refresh_symbol_metadata(
    *,
    symbols: tuple[str, ...],
    cache_path: Path,
    allow_refresh: bool,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    rows = _load(cache_path)
    missing = [symbol for symbol in symbols if not (rows.get(symbol) or {}).get("name")]
    error = ""
    if allow_refresh and missing:
        try:
            from libs.research.opening_rank1_deep_dive.metadata import (
                collect_current_symbol_metadata,
            )

            collect_current_symbol_metadata(
                sorted(set(rows) | set(symbols)),
                output_path=cache_path,
                request_interval_sec=1.05,
                collect_themes=False,
            )
            rows = _load(cache_path)
        except Exception as exc:
            error = f"{type(exc).__name__}:{exc}"
    return rows, {
        "cache_path": str(cache_path),
        "requested_symbol_count": len(symbols),
        "resolved_name_count": sum(bool((rows.get(symbol) or {}).get("name")) for symbol in symbols),
        "missing_symbols": [symbol for symbol in symbols if not (rows.get(symbol) or {}).get("name")],
        "refresh_allowed": bool(allow_refresh),
        "refresh_error": error,
    }


def enrich_windows_with_symbol_metadata(
    windows: list[dict[str, Any]],
    metadata: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    enriched = []
    for raw_window in windows:
        window = dict(raw_window)
        candidates = []
        for raw_candidate in window.get("candidates") or []:
            candidate = dict(raw_candidate)
            symbol = str(candidate.get("symbol") or "")
            row = metadata.get(symbol) or {}
            if row.get("name") and not candidate.get("name"):
                candidate["name"] = row.get("name")
                candidate["name_authority"] = row.get("name_authority") or "CURRENT_REFERENCE"
            candidates.append(candidate)
        window["candidates"] = candidates
        enriched.append(window)
    return enriched
