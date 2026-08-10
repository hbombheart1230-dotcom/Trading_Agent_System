from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from libs.reporting.evaluation.cost_basis_comparison import build_evaluation_cost_bases
from libs.reporting.opening_rank1_shadow.candle_provider import load_opening_candles
from libs.reporting.quant_shadow_forward_outcomes import attach_forward_outcomes
from libs.runtime.broker_cost_profile import load_broker_cost_profile

from .episodes import collapse_cycles_to_episodes, load_approved_noop_cycles
from .report import build_report_payload, render_markdown


def _days(start: str, end: str) -> list[str]:
    current = date.fromisoformat(start)
    final = date.fromisoformat(end)
    result = []
    while current <= final:
        result.append(current.isoformat())
        current += timedelta(days=1)
    return result


def _read_candle_cache(cache_root: Path, day: str, symbols: tuple[str, ...]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for symbol in symbols:
        try:
            payload = json.loads((cache_root / day / f"{symbol}.json").read_text(encoding="utf-8"))
            rows = payload.get("rows") if isinstance(payload, dict) else []
            result[symbol] = [dict(row) for row in rows if isinstance(row, dict)]
        except (OSError, ValueError):
            result[symbol] = []
    return result


def _write_candle_cache(cache_root: Path, day: str, candles: dict[str, list[dict[str, Any]]]) -> None:
    day_root = cache_root / day
    day_root.mkdir(parents=True, exist_ok=True)
    for symbol, rows in candles.items():
        if not rows:
            continue
        (day_root / f"{symbol}.json").write_text(
            json.dumps({"schema_version": "monitor_noop_candles.v1", "day": day, "symbol": symbol, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def build_monitor_noop_attribution(
    *, reports_root: Path, state_path: Path, start: str, end: str,
    output_dir: Path, allow_fresh_fetch: bool = True,
    log_root: Path = Path("data/logs/quant_shadow_candidates"),
    cost_profile_path: Path | None = None,
) -> dict[str, Any]:
    cycles = []
    for day in _days(start, end):
        cycles.extend(load_approved_noop_cycles(
            reports_root=Path(reports_root), log_root=Path(log_root), day=day
        ))
    episodes = collapse_cycles_to_episodes(cycles)
    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in episodes:
        by_day[str(row.get("day") or "")].append(row)
    candle_meta: dict[str, Any] = {}
    observed: list[dict[str, Any]] = []
    evidence_cache_root = Path("data/research/monitor_noop_attribution/evidence_candles")
    for day, rows in sorted(by_day.items()):
        symbols = tuple(sorted({str(row.get("symbol") or "") for row in rows}))
        candles = _read_candle_cache(evidence_cache_root, day, symbols)
        missing = tuple(symbol for symbol in symbols if not candles.get(symbol))
        meta: dict[str, Any] = {
            "evidence_cache_symbol_count": len(symbols) - len(missing),
            "requested_symbol_count": len(symbols),
        }
        if missing:
            recovered, provider_meta = load_opening_candles(
                state_path=Path(state_path), day=day, symbols=missing,
                allow_fresh_fetch=allow_fresh_fetch,
                cache_root=Path("data/research/monitor_noop_attribution/minute_cache"),
            )
            candles.update(recovered)
            meta["recovery"] = provider_meta
            _write_candle_cache(evidence_cache_root, day, recovered)
        candle_meta[day] = meta
        observed.extend(attach_forward_outcomes(rows, minute_rows_by_symbol=candles))
    cost_bases = build_evaluation_cost_bases(load_broker_cost_profile(cost_profile_path))
    payload = build_report_payload(
        start=start, end=end, cycles=cycles, episodes=observed,
        cost_bases=cost_bases, candle_meta=candle_meta,
    )
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "monitor_noop_attribution.json"
    markdown_path = output_dir / "monitor_noop_attribution.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path), "payload": payload}


__all__ = ["build_monitor_noop_attribution"]
