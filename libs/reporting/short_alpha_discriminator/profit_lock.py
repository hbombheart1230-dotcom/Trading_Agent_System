from __future__ import annotations

from typing import Any, Mapping, Sequence

from .contracts import HORIZONS, PROFIT_LOCK_PROXIES
from .metrics import checkpoint_return, number, performance


def build_profit_fade_review(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    details = []
    for row in rows:
        episode = dict(row.get("episode", {}))
        checkpoints = dict(episode.get("checkpoints", {}))
        returns = {
            horizon: checkpoint_return(episode, horizon) for horizon in HORIZONS
        }
        eod = returns.get("EOD")
        eod_checkpoint = dict(checkpoints.get("EOD", {}))
        eod_mfe = number(eod_checkpoint.get("mfe_pct"))
        observed_returns = [value for value in returns.values() if value is not None]
        best_checkpoint = max(observed_returns) if observed_returns else None
        details.append(
            {
                "day": row.get("day"),
                "symbol": row.get("symbol"),
                "candidate_setup": row.get("candidate_setup"),
                "entry_horizon": row.get("entry_horizon"),
                "returns": returns,
                "eod_mfe_pct": eod_mfe,
                "best_checkpoint_return_pct": best_checkpoint,
                "checkpoint_to_eod_fade_pct": (
                    round(best_checkpoint - eod, 4)
                    if best_checkpoint is not None and eod is not None
                    else None
                ),
                "positive_5m_to_negative_eod": bool(
                    returns.get("+5m") is not None
                    and returns["+5m"] > 0.0
                    and eod is not None
                    and eod <= 0.0
                ),
            }
        )
    fixed_horizons = {
        horizon: performance([row["returns"].get(horizon) for row in details])
        for horizon in HORIZONS
    }
    proxy_rows = []
    for policy in PROFIT_LOCK_PROXIES:
        trigger = float(policy["trigger_mfe_pct"])
        floor = float(policy["floor_net_return_pct"])
        values = []
        triggered = 0
        for row in details:
            eod = number(row["returns"].get("EOD"))
            mfe = number(row.get("eod_mfe_pct"))
            if eod is None:
                continue
            if mfe is not None and mfe >= trigger:
                triggered += 1
                values.append(max(eod, floor))
            else:
                values.append(eod)
        proxy_rows.append(
            {
                **policy,
                "triggered_count": triggered,
                "metrics": performance(values),
                "limitation": (
                    "Optimistic checkpoint proxy only. It does not model gaps, queueing, "
                    "slippage, or minute-level stop execution."
                ),
            }
        )
    fade_values = [
        value
        for row in details
        if (value := number(row.get("checkpoint_to_eod_fade_pct"))) is not None
    ]
    return {
        "cohort_episode_count": len(rows),
        "fixed_horizon_comparison": fixed_horizons,
        "profit_lock_proxies": proxy_rows,
        "positive_5m_to_negative_eod_count": sum(
            bool(row["positive_5m_to_negative_eod"]) for row in details
        ),
        "avg_checkpoint_to_eod_fade_pct": (
            round(sum(fade_values) / len(fade_values), 4) if fade_values else None
        ),
        "details": details,
        "behavior_change_authorized": False,
    }
