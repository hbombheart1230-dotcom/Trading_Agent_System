from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from libs.reporting.q8_evaluation_contract import candidate_day


KST = timezone(timedelta(hours=9))
FORWARD_DATA_SOURCE = "state_plus_kiwoom_minute_recovery"


def _row_day(row: Mapping[str, Any]) -> str:
    day = str(candidate_day(row) or "")[:10]
    if day:
        return day
    raw = str(row.get("_payload_generated_at") or row.get("generated_at") or "")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed.astimezone(KST).date().isoformat()
    except (TypeError, ValueError):
        return ""


def load_q9_forward_candles(
    rows: Iterable[Mapping[str, Any]],
    *,
    state_path: Path = Path("data/state.json"),
    allow_fresh_fetch: bool = True,
    run_id_prefix: str = "q9_forward_evidence",
) -> dict[str, list[dict[str, Any]]]:
    symbols_by_day: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        day = _row_day(row)
        symbol = str(row.get("symbol") or "").strip()
        if day and symbol:
            symbols_by_day[day].add(symbol)

    merged: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    # Lazy import avoids loading the baseline package's pipeline while this
    # shared evidence module is imported by q9_comparison.
    from libs.reporting.baseline_samsung_hynix.data_provider import load_existing_candles

    for day, symbols in sorted(symbols_by_day.items()):
        candles = load_existing_candles(
            state_path=state_path,
            day=day,
            symbols=tuple(sorted(symbols)),
            allow_fresh_fetch=allow_fresh_fetch,
            run_id_prefix=run_id_prefix,
        )
        for symbol, minute_rows in candles.items():
            for row in minute_rows:
                epoch = int(row.get("ts") or 0)
                if epoch > 0:
                    merged[str(symbol)][epoch] = dict(row)
    return {
        symbol: [by_epoch[key] for key in sorted(by_epoch)]
        for symbol, by_epoch in merged.items()
    }


__all__ = ["FORWARD_DATA_SOURCE", "load_q9_forward_candles"]
