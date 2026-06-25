from __future__ import annotations

from typing import Any, Mapping, Sequence


def _net_return_pct(entry: float, exit_price: float, cost_pct: float, slippage_pct: float) -> float:
    gross = ((exit_price / entry) - 1.0) * 100.0 if entry > 0.0 else 0.0
    return gross - cost_pct - slippage_pct


def simulate_probe_v0(
    signals: Sequence[Mapping[str, Any]],
    *,
    cost_pct: float,
    slippage_pct: float,
    max_hold_minutes: int = 30,
) -> list[dict[str, Any]]:
    by_symbol: dict[str, list[Mapping[str, Any]]] = {}
    for signal in signals:
        by_symbol.setdefault(str(signal.get("symbol") or ""), []).append(signal)
    trades: list[dict[str, Any]] = []
    for symbol, rows in sorted(by_symbol.items()):
        position: dict[str, Any] | None = None
        for signal in sorted(rows, key=lambda row: int(row.get("as_of_epoch") or 0)):
            features = signal.get("symbol_features") if isinstance(signal.get("symbol_features"), Mapping) else {}
            opportunity = signal.get("opportunity") if isinstance(signal.get("opportunity"), Mapping) else {}
            epoch = int(signal.get("as_of_epoch") or 0)
            price = float(features.get("price") or 0.0)
            if position is None:
                if not bool(opportunity.get("probe_candidate")) or price <= 0.0:
                    continue
                atr_pct = max(0.60, min(1.50, 1.5 * float(features.get("atr_6_pct") or 0.0)))
                opening_low = float(features.get("opening_low") or 0.0)
                percent_stop = price * (1.0 - atr_pct / 100.0)
                stop_price = max(opening_low, percent_stop) if opening_low > 0.0 else percent_stop
                if stop_price >= price:
                    stop_price = percent_stop
                position = {
                    "entry_signal_id": signal.get("signal_id"),
                    "entry_epoch": epoch,
                    "entry_price": price,
                    "stop_price": stop_price,
                    "entry_score": float(opportunity.get("score") or 0.0),
                    "max_price": price,
                    "min_price": price,
                }
                continue
            position["max_price"] = max(float(position["max_price"]), float(features.get("price") or price))
            position["min_price"] = min(float(position["min_price"]), float(features.get("price") or price))
            held_minutes = max(0, (epoch - int(position["entry_epoch"])) // 60)
            stop_hit = price <= float(position["stop_price"])
            signal_faded = bool(
                float(opportunity.get("score") or 0.0) <= 0.35
                and float(features.get("momentum_1m_pct") or 0.0) < 0.0
            )
            timeout = held_minutes >= max_hold_minutes
            is_last = signal is rows[-1]
            if not (stop_hit or signal_faded or timeout or is_last):
                continue
            reason = "stop_hit" if stop_hit else "signal_faded" if signal_faded else "max_hold" if timeout else "end_of_data"
            entry_price = float(position["entry_price"])
            trades.append(
                {
                    "trade_id": f"OE_TRD_{symbol}_{position['entry_epoch']}",
                    "strategy_id": "probe_v0",
                    "behavior_effect": "shadow_only",
                    "symbol": symbol,
                    "entry_signal_id": position["entry_signal_id"],
                    "entry_epoch": int(position["entry_epoch"]),
                    "entry_price": entry_price,
                    "entry_score": round(float(position["entry_score"]), 6),
                    "stop_price": round(float(position["stop_price"]), 6),
                    "exit_epoch": epoch,
                    "exit_price": price,
                    "exit_reason": reason,
                    "held_minutes": int(held_minutes),
                    "gross_return_pct": round(((price / entry_price) - 1.0) * 100.0, 6),
                    "net_return_pct": round(_net_return_pct(entry_price, price, cost_pct, slippage_pct), 6),
                    "mfe_pct": round(((float(position["max_price"]) / entry_price) - 1.0) * 100.0, 6),
                    "mae_pct": round(((float(position["min_price"]) / entry_price) - 1.0) * 100.0, 6),
                    "order_execution_allowed": False,
                }
            )
            position = None
    return trades


def summarize_trades(trades: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    returns = [float(row.get("net_return_pct") or 0.0) for row in trades]
    wins = [value for value in returns if value > 0.0]
    losses = [value for value in returns if value < 0.0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trade_count": len(returns),
        "win_rate": round(len(wins) / len(returns), 6) if returns else None,
        "average_net_return_pct": round(sum(returns) / len(returns), 6) if returns else None,
        "profit_factor": round(gross_profit / gross_loss, 6) if gross_loss > 0.0 else None,
        "average_mfe_pct": round(
            sum(float(row.get("mfe_pct") or 0.0) for row in trades) / len(trades), 6
        )
        if trades
        else None,
        "average_mae_pct": round(
            sum(float(row.get("mae_pct") or 0.0) for row in trades) / len(trades), 6
        )
        if trades
        else None,
    }

