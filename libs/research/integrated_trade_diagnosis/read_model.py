from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from .io import read_json
from .lineage import build_lineage
from .metrics import number


def load_trade_rows(
    reports_root: Path,
    *,
    start_day: str,
    end_day: str,
) -> list[dict[str, Any]]:
    rows = []
    root = reports_root / "evaluation" / "trades"
    for path in sorted(root.glob("**/trade_read_model.json")):
        model = read_json(path)
        day = str(model.get("day") or "")
        if not (start_day <= day <= end_day):
            continue
        evaluation = read_json(path.with_name("trade_evaluation.json"))
        outcome = model.get("outcome")
        outcome = outcome if isinstance(outcome, Mapping) else {}
        entry = model.get("entry")
        entry = entry if isinstance(entry, Mapping) else {}
        exit_data = model.get("exit")
        exit_data = exit_data if isinstance(exit_data, Mapping) else {}
        horizon = evaluation.get("horizon_alignment")
        horizon = horizon if isinstance(horizon, Mapping) else {}
        exit_quality = evaluation.get("exit_quality")
        exit_quality = exit_quality if isinstance(exit_quality, Mapping) else {}
        rows.append(
            {
                "trade_id": model.get("trade_id"),
                "day": day,
                "symbol": str(model.get("symbol") or ""),
                "status": model.get("status"),
                "entry_timestamp": entry.get("timestamp"),
                "entry_price": number(entry.get("price")),
                "entry_reason": entry.get("reason"),
                "exit_timestamp": exit_data.get("timestamp"),
                "exit_price": number(exit_data.get("price")),
                "exit_reason": exit_data.get("reason"),
                "net_return_pct": number(outcome.get("net_return_pct")),
                "realized_pnl": number(outcome.get("realized_pnl")),
                "holding_seconds": number(outcome.get("holding_seconds")),
                "strategy_horizon": horizon.get("strategy_horizon"),
                "horizon_bucket": horizon.get("bucket"),
                "horizon_violation_candidate": horizon.get(
                    "horizon_violation_candidate"
                ),
                "valid_early_exit": horizon.get("valid_early_exit"),
                "target_hold_would_improve_exit": horizon.get(
                    "target_hold_would_improve_exit"
                ),
                "max_post_exit_upside_pct": number(
                    exit_quality.get("max_post_exit_upside_pct")
                ),
                "max_post_exit_drawdown_pct": number(
                    exit_quality.get("max_post_exit_drawdown_pct")
                ),
                "lineage": build_lineage(model),
                "source_path": str(path),
                "integrity": model.get("integrity") or {},
            }
        )
    return rows


def build_symbol_day_sequences(
    rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row.get("day") or ""), str(row.get("symbol") or ""))].append(row)
    result = []
    for (day, symbol), group in sorted(grouped.items()):
        ordered = sorted(group, key=lambda row: str(row.get("entry_timestamp") or ""))
        returns = [
            value
            for row in ordered
            if (value := number(row.get("net_return_pct"))) is not None
        ]
        running = peak = 0.0
        for value in returns:
            running += value
            peak = max(peak, running)
        result.append(
            {
                "day": day,
                "symbol": symbol,
                "trade_count": len(ordered),
                "trade_ids": [row.get("trade_id") for row in ordered],
                "returns_pct": returns,
                "first_return_pct": returns[0] if returns else None,
                "cumulative_return_pct": round(sum(returns), 4) if returns else None,
                "peak_cumulative_return_pct": round(peak, 4) if returns else None,
                "profit_giveback_pct": round(peak - sum(returns), 4) if returns else None,
                "repeat_after_loss_count": sum(
                    index > 0 and returns[index - 1] < 0
                    for index in range(len(returns))
                ),
                "repeat_after_non_loss_count": sum(
                    index > 0 and returns[index - 1] >= 0
                    for index in range(len(returns))
                ),
                "fresh_episode_evidence": "INSUFFICIENT_EVIDENCE"
                if len(ordered) > 1
                else "NOT_APPLICABLE",
            }
        )
    return result
