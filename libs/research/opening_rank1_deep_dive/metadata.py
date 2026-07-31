from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from libs.read.kiwoom_price_reader import KiwoomPriceReader
from libs.read.kiwoom_theme_reader import KiwoomThemeReader


def collect_current_symbol_metadata(
    symbols: list[str],
    *,
    output_path: Path,
    theme_group_limit: int = 100,
    request_interval_sec: float = 1.05,
    collect_themes: bool = True,
) -> dict[str, Any]:
    requested = sorted({str(symbol).strip() for symbol in symbols if str(symbol).strip()})
    existing: dict[str, Any] = {}
    if output_path.exists():
        try:
            previous = json.loads(output_path.read_text(encoding="utf-8"))
            existing = previous.get("symbols") if isinstance(previous.get("symbols"), dict) else {}
        except (OSError, ValueError):
            existing = {}
    symbol_rows: dict[str, dict[str, Any]] = {
        symbol: {
            "name": (existing.get(symbol) or {}).get("name") or "",
            "name_authority": (existing.get(symbol) or {}).get("name_authority") or "MISSING",
            "themes": list((existing.get(symbol) or {}).get("themes") or []),
            "theme_authority": (existing.get(symbol) or {}).get("theme_authority") or "MISSING",
        }
        for symbol in requested
    }
    price_reader = KiwoomPriceReader.from_env()
    name_errors: dict[str, str] = {}
    for symbol in requested:
        if symbol_rows[symbol]["name"]:
            continue
        try:
            payload = price_reader.get_stock_info_payload(symbol)
            name = str(payload.get("stk_nm") or "").strip()
            if name:
                symbol_rows[symbol]["name"] = name
                symbol_rows[symbol]["name_authority"] = "KIWOOM_CURRENT_KA10001"
        except Exception as exc:
            name_errors[symbol] = f"{type(exc).__name__}:{exc}"
        time.sleep(max(0.0, request_interval_sec))

    theme_errors: dict[str, str] = {}
    groups: list[dict[str, Any]] = []
    if collect_themes:
        theme_reader = KiwoomThemeReader.from_env()
        groups = theme_reader.get_theme_groups(limit=max(1, theme_group_limit), date_tp="10", stex_tp="1")
        time.sleep(max(0.0, request_interval_sec))
        for group in groups:
            code = str(group.get("theme_code") or "").strip()
            name = str(group.get("theme_name") or "").strip()
            if not code or not name:
                continue
            try:
                components = theme_reader.get_theme_components(theme_code=code, limit=100, stex_tp="1")
            except Exception as exc:
                theme_errors[code] = f"{type(exc).__name__}:{exc}"
                continue
            for component in components:
                symbol = str(component.get("symbol") or "").strip()
                if symbol in symbol_rows and name not in symbol_rows[symbol]["themes"]:
                    symbol_rows[symbol]["themes"].append(name)
                    symbol_rows[symbol]["theme_authority"] = "KIWOOM_CURRENT_REFERENCE_KA90002"
            time.sleep(max(0.0, request_interval_sec))

    payload = {
        "schema_version": "opening_rank1_symbol_metadata.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "historical_causality": False,
        "note": (
            "Names and themes are current Kiwoom references. Theme membership is not a "
            "point-in-time reconstruction and must not be treated as a historical cause."
        ),
        "requested_symbol_count": len(requested),
        "theme_group_count": len(groups),
        "name_errors": name_errors,
        "theme_errors": theme_errors,
        "symbols": symbol_rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload
