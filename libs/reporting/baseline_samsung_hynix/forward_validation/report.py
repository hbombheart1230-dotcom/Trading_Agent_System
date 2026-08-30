from __future__ import annotations

from typing import Any, Mapping


def _value(value: Any, suffix: str = "") -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}{suffix}"
    return f"{value}{suffix}"


def render_forward_validation_report(
    *, day: str, preopen: Mapping[str, Any], reactions: Mapping[str, Any], expected_actual: Mapping[str, Any],
    shadow: Mapping[str, Any], cumulative: Mapping[str, Any]
) -> str:
    signals = preopen.get("signals") or {}
    lines = [
        "# Q10 Korea Lead-Market Forward Validation",
        "",
        f"- Day: `{day}`",
        f"- Preopen snapshot: `{preopen.get('capture_status', 'WAITING')}`",
        "- Mode: `prospective_shadow_only`",
        "- Historical backfill / threshold optimization / ML / orders: disabled",
        "",
        "## Preopen States",
        "",
        "| Target | State | Score | Confidence / Evidence | Context |",
        "|---|---|---:|---|---|",
        f"| SK Hynix | {(signals.get('sk_hynix') or {}).get('state', '-')} | {_value((signals.get('sk_hynix') or {}).get('score'))} | {(signals.get('sk_hynix') or {}).get('confidence', '-')} | {(signals.get('hynix_extension') or {}).get('state', '-')} |",
        f"| Samsung Electronics | {(signals.get('samsung') or {}).get('state', '-')} | {_value((signals.get('samsung') or {}).get('score'))} | {(signals.get('samsung') or {}).get('confidence', '-')} | SAMSUNG_SPECIFIC_EVENT={bool((preopen.get('samsung_event') or {}).get('samsung_specific_event'))} |",
        f"| KOSPI / KOSDAQ | {(signals.get('korea_market') or {}).get('state', '-')} | {_value((signals.get('korea_market') or {}).get('score'))} | {(signals.get('korea_market') or {}).get('evidence_status', '-')} | shared preopen market state |",
        "",
        "## Expected vs Actual",
        "",
        "| Target | Expected | Opening Gap | Classification | Bucket |",
        "|---|---|---:|---|---|",
    ]
    for row in expected_actual.get("rows") or []:
        lines.append(
            f"| {row.get('target')} | {row.get('expected_state')} | {_value(row.get('opening_gap_pct'), '%')} | "
            f"{row.get('reaction_state')} | {row.get('evaluation_bucket')} |"
        )
    lines += [
        "",
        "## Actual Reaction Checkpoints",
        "",
        "| Target | Gap | 09:00 | 09:03 | 09:05 | 09:10 | 09:15 | 09:30 | 10:00 | Close | High | Low |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, row in (reactions.get("targets") or {}).items():
        points = row.get("points") or {}
        prices = [_value((points.get(label) or {}).get("price")) for label in ("09:00", "09:03", "09:05", "09:10", "09:15", "09:30", "10:00", "CLOSE")]
        lines.append(
            f"| {key} | {_value(row.get('opening_gap_pct'), '%')} | " + " | ".join(prices) +
            f" | {_value(row.get('day_high'))} | {_value(row.get('day_low'))} |"
        )
    lines += [
        "",
        "## Forward Quality By Checkpoint",
        "",
        "| Target | Checkpoint | Return to Close | MFE | MAE | Status |",
        "|---|---|---:|---:|---:|---|",
    ]
    for key, row in (reactions.get("targets") or {}).items():
        for label, window in (row.get("forward_windows") or {}).items():
            lines.append(
                f"| {key} | {label} | {_value(window.get('return_to_close_pct'), '%')} | "
                f"{_value(window.get('mfe_pct'), '%')} | {_value(window.get('mae_pct'), '%')} | {window.get('status')} |"
            )
    lines += [
        "",
        "## Shadow Entry Comparison",
        "",
        f"- Evidence: `{shadow.get('evidence_status', 'INSUFFICIENT_EVIDENCE')}`",
        "",
        "| Target | Entry | Trades | Win Rate | Avg Net | Median | PF | MFE | MAE |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in shadow.get("summary") or []:
        lines.append(
            f"| {row.get('target')} | {row.get('policy')} | {row.get('trade_count', 0)} | "
            f"{_value(row.get('win_rate'), '%')} | {_value(row.get('average_return_pct'), '%')} | "
            f"{_value(row.get('median_return_pct'), '%')} | {_value(row.get('profit_factor'))} | "
            f"{_value(row.get('average_mfe_pct'), '%')} | {_value(row.get('average_mae_pct'), '%')} |"
        )
    lines += [
        "",
        "## Prospective Cumulative",
        "",
        f"- Days: `{cumulative.get('day_count', 0)}`",
        f"- Observed outcomes: `{cumulative.get('observed_outcome_count', 0)}`",
        "",
        "| Target | Entry | Bucket | Extension | Trades | Win Rate | Avg Net | Median | PF | MDD |",
        "|---|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in cumulative.get("summary") or []:
        lines.append(
            f"| {row.get('target')} | {row.get('policy')} | {row.get('evaluation_bucket')} | "
            f"{row.get('extension_state')} | {row.get('trade_count')} | {_value(row.get('win_rate'), '%')} | "
            f"{_value(row.get('average_return_pct'), '%')} | {_value(row.get('median_return_pct'), '%')} | "
            f"{_value(row.get('profit_factor'))} | {_value(row.get('max_drawdown_pct'), '%')} |"
        )
    return "\n".join(lines) + "\n"
