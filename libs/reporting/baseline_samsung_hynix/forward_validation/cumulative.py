from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from .contracts import ACTIVATION_DAY


def build_cumulative(root: Path) -> dict[str, Any]:
    rows = []
    days = set()
    for path in sorted(root.glob("*/q10_forward_validation/q10_shadow_entry_comparison.json")):
        if path.parent.parent.name < ACTIVATION_DAY:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        day = str(payload.get("day") or path.parent.parent.name)
        for row in payload.get("outcomes") or []:
            if row.get("status") == "OBSERVED":
                rows.append({"day": day, **dict(row)})
                days.add(day)
    groups: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(
            (
                str(row.get("target")), str(row.get("policy")),
                str(row.get("evaluation_bucket") or "LEAD_MARKET_SIGNAL"),
                str(row.get("extension_state") or "N/A"),
            ),
            [],
        ).append(row)
    summary = []
    for (target, policy, bucket, extension_state), group_rows in sorted(groups.items()):
        values = [float(row["net_eod_return_pct"]) for row in group_rows]
        gains = sum(value for value in values if value > 0)
        losses = abs(sum(value for value in values if value < 0))
        equity = peak = drawdown = 0.0
        for value in values:
            equity += value
            peak = max(peak, equity)
            drawdown = min(drawdown, equity - peak)
        summary.append(
            {
                "target": target,
                "policy": policy,
                "evaluation_bucket": bucket,
                "extension_state": extension_state,
                "trade_count": len(values),
                "win_rate": round(sum(value > 0 for value in values) / len(values) * 100.0, 4),
                "average_return_pct": round(sum(values) / len(values), 6),
                "median_return_pct": round(median(values), 6),
                "profit_factor": round(gains / losses, 6) if losses else (None if not gains else "INF"),
                "max_drawdown_pct": round(drawdown, 6),
                "average_mfe_pct": round(sum(float(row.get("mfe_pct") or 0.0) for row in group_rows) / len(group_rows), 6),
                "average_mae_pct": round(sum(float(row.get("mae_pct") or 0.0) for row in group_rows) / len(group_rows), 6),
                "average_eod_return_pct": round(sum(values) / len(values), 6),
            }
        )
    return {
        "schema_version": "q10_korea_lead_market_cumulative.v1",
        "prospective_start_day": ACTIVATION_DAY,
        "day_count": len(days),
        "days": sorted(days),
        "observed_outcome_count": len(rows),
        "summary": summary,
    }
