from __future__ import annotations

from typing import Any, Mapping

from .contracts import COHORT_ID, FIRST_ELIGIBLE_DAY, HORIZONS, NEXT_STAGE


def _horizon_table(summary: Mapping[str, Any]) -> list[str]:
    lines = [
        "| Horizon | Episodes | Observed | Coverage | Win Rate | Avg Net | PF | MDD | Avg MFE | Avg MAE |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for horizon in HORIZONS:
        row = (summary.get("horizons") or {}).get(horizon) or {}
        metrics = row.get("live_net") or {}
        lines.append(
            f"| {horizon} | {int(row.get('episode_count') or 0)} | "
            f"{int(row.get('observed_count') or 0)} | "
            f"{float(row.get('coverage') or 0.0):.1%} | "
            f"{float(metrics.get('win_rate') or 0.0):.1%} | "
            f"{float(metrics.get('average_return_pct') or 0.0):+.4f}% | "
            f"{float(metrics.get('profit_factor') or 0.0):.4f} | "
            f"{float(metrics.get('maximum_drawdown_pct') or 0.0):+.4f}% | "
            f"{float(row.get('average_mfe_pct') or 0.0):+.4f}% | "
            f"{float(row.get('average_mae_pct') or 0.0):+.4f}% |"
        )
    return lines


def render_daily(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    lines = [
        f"# Opening Rank 1 Shadow ({payload.get('day')})",
        "",
        f"- Cohort: `{COHORT_ID}`",
        f"- Day status: **{payload.get('day_status')}**",
        f"- First eligible day: `{FIRST_ELIGIBLE_DAY}`",
        "- Behavior effect: observation only",
        f"- Opening Scanner windows: {int((payload.get('extraction') or {}).get('opening_window_count') or 0)}",
        f"- Deduplicated episodes: {int(summary.get('episode_count') or 0)}",
        "",
        "## Forward Outcomes",
        "",
        *_horizon_table(summary),
        "",
        "## Episodes",
        "",
        "| Decision KST | Symbol | Entry KST | Entry Price | +5m | +15m | +30m | +60m | EOD |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("episodes") or []:
        checkpoints = row.get("checkpoints") or {}

        def value(horizon: str) -> str:
            checkpoint = checkpoints.get(horizon) or {}
            if checkpoint.get("status") != "observed":
                return str(checkpoint.get("status") or "missing")
            return f"{float(checkpoint.get('live_net_return_pct') or 0.0):+.4f}%"

        lines.append(
            f"| {row.get('decision_time_kst')} | {row.get('symbol')} | "
            f"{row.get('entry_time_kst')} | {float(row.get('baseline_price') or 0.0):,.2f} | "
            f"{value('+5m')} | {value('+15m')} | {value('+30m')} | "
            f"{value('+60m')} | {value('EOD')} |"
        )
    lines.extend(
        [
            "",
            "This report cannot create an order intent or change live behavior.",
            "",
        ]
    )
    return "\n".join(lines)


def render_cumulative(payload: Mapping[str, Any]) -> str:
    summary = payload.get("summary") or {}
    decision = payload.get("promotion_decision") or {}
    values = decision.get("values") or {}
    checks = decision.get("checks") or {}
    lines = [
        "# Opening Rank 1 Prospective Validation",
        "",
        f"- Cohort: `{COHORT_ID}`",
        f"- First eligible day: `{FIRST_ELIGIBLE_DAY}`",
        f"- Decision: **{decision.get('status')}**",
        f"- Authorized next stage on pass: `{NEXT_STAGE}`",
        "- Live behavior authorization: **false**",
        "",
        "## Cumulative Forward Outcomes",
        "",
        *_horizon_table(summary),
        "",
        "## Promotion Gate",
        "",
        "| Check | Value | Passed |",
        "| --- | ---: | --- |",
    ]
    value_keys = {
        "average_net_return": "average_net_return_pct",
        "day_concentration": "largest_day_share",
        "symbol_concentration": "largest_symbol_share",
    }
    for name, passed in checks.items():
        value_key = value_keys.get(name, name)
        lines.append(
            f"| {name} | {values.get(value_key, '-')} | {bool(passed)} |"
        )
    lines.extend(
        [
            f"| observed_count | {values.get('observed_count', 0)} | "
            f"{values.get('observed_count', 0) >= (decision.get('gates') or {}).get('minimum_observed_count', 0)} |",
            f"| observed_day_count | {values.get('observed_day_count', 0)} | "
            f"{values.get('observed_day_count', 0) >= (decision.get('gates') or {}).get('minimum_observed_day_count', 0)} |",
            "",
            "## Interpretation",
            "",
        ]
    )
    if decision.get("status") == "COLLECTING":
        lines.append("The frozen prospective sample is not yet large enough for a decision.")
    elif decision.get("status") == "ELIGIBLE_FOR_CONTROLLED_SHADOW":
        lines.append(
            "All frozen gates passed. The cohort may move only to a controlled shadow policy review."
        )
    else:
        lines.append(
            "The frozen evidence threshold was reached and at least one quality gate failed. Reject the cohort without retuning."
        )
    lines.extend(
        [
            "",
            "No result in this report directly authorizes live entry, exit, sizing, or execution changes.",
            "",
        ]
    )
    return "\n".join(lines)
