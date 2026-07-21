from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _num(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Any) -> str:
    number = _num(value)
    if number is None:
        return "-"
    return f"{number:.4f}%"


def _top(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"name": key, "count": int(value)}
        for key, value in counter.most_common(limit)
        if key
    ]


def _q9_windows(reports_root: Path, day: str) -> list[dict[str, Any]]:
    payload = _read_json(reports_root / "operator_summary" / "daily" / day / "q9_decision_windows.json")
    return [row for row in payload.get("windows") or [] if isinstance(row, dict)]


def _baseline_samsung(reports_root: Path, day: str) -> dict[str, Any]:
    payload = _read_json(
        reports_root
        / "evaluation"
        / "baseline_samsung_hynix"
        / day
        / "baseline_samsung_hynix_forward_returns.json"
    )
    summary = _mapping(payload.get("summary"))
    rows = summary.get("horizons") if isinstance(summary.get("horizons"), list) else []
    return {
        "available": bool(payload),
        "horizons": [
            {
                "horizon": str(row.get("horizon") or ""),
                "trade_count": int(row.get("top1_observation_count") or row.get("trade_count") or 0),
                "win_rate": _num(_mapping(row.get("top1_net")).get("win_rate") or row.get("top1_win_rate") or row.get("win_rate")),
                "avg_net_return_pct": _num(
                    _mapping(row.get("top1_net")).get("average_return_pct")
                    or row.get("top1_avg_net_return_pct")
                    or row.get("avg_net_return_pct")
                ),
                "profit_factor": _num(_mapping(row.get("top1_net")).get("profit_factor") or row.get("top1_profit_factor") or row.get("profit_factor")),
            }
            for row in rows
            if isinstance(row, Mapping)
        ],
    }


def _q11_opening(reports_root: Path, day: str) -> dict[str, Any]:
    root = reports_root / "evaluation" / "opportunity_engine_shadow" / day
    payload = _read_json(root / "opportunity_engine_daily_report.json")
    signals = _read_json(root / "opportunity_engine_signals.json")
    virtual = _read_json(root / "opportunity_engine_virtual_trades.json")
    summary = _mapping(virtual.get("summary") or payload.get("summary"))
    data_quality = _mapping(signals.get("data_quality"))
    return {
        "available": bool(payload or signals or virtual),
        "signal_rows": int(signals.get("signal_count") or summary.get("signal_rows") or payload.get("signal_rows") or 0),
        "probe_candidates": sum(
            1
            for row in signals.get("signals") or []
            if isinstance(row, Mapping) and bool(_mapping(row.get("opportunity")).get("probe_candidate"))
        ),
        "probe_near_misses": int(data_quality.get("probe_near_miss_count") or 0),
        "virtual_trades": int(virtual.get("trade_count") or summary.get("trade_count") or summary.get("virtual_trades") or 0),
        "win_rate": _num(summary.get("win_rate") or payload.get("win_rate")),
        "avg_net_return_pct": _num(summary.get("average_net_return_pct") or summary.get("avg_net_return") or summary.get("avg_net_return_pct") or payload.get("avg_net_return_pct")),
        "avg_mfe_pct": _num(summary.get("average_mfe_pct") or summary.get("avg_mfe") or summary.get("avg_mfe_pct") or payload.get("avg_mfe_pct")),
        "avg_mae_pct": _num(summary.get("average_mae_pct") or summary.get("avg_mae") or summary.get("avg_mae_pct") or payload.get("avg_mae_pct")),
        "profit_factor": _num(summary.get("profit_factor") or payload.get("profit_factor")),
    }


def _q12_btc_woori(reports_root: Path, day: str) -> dict[str, Any]:
    payload = _read_json(
        reports_root
        / "evaluation"
        / "baseline_btc_woori_tech"
        / day
        / "baseline_btc_woori_forward_returns.json"
    )
    summary = _mapping(payload.get("summary"))
    horizons = summary.get("horizons") if isinstance(summary.get("horizons"), list) else []
    return {
        "available": bool(payload),
        "horizons": [
            {
                "horizon": str(row.get("horizon") or ""),
                "trade_count": int(row.get("trade_count") or 0),
                "win_rate": _num(_mapping(row.get("eligible_entries_net")).get("win_rate") or _mapping(row.get("top1_net")).get("win_rate") or row.get("win_rate")),
                "avg_net_return_pct": _num(
                    _mapping(row.get("eligible_entries_net")).get("average_return_pct")
                    or _mapping(row.get("top1_net")).get("average_return_pct")
                    or row.get("avg_net_return_pct")
                ),
                "profit_factor": _num(_mapping(row.get("eligible_entries_net")).get("profit_factor") or _mapping(row.get("top1_net")).get("profit_factor") or row.get("profit_factor")),
            }
            for row in horizons
            if isinstance(row, Mapping)
        ],
    }


def build_no_trade_attribution_report(
    *,
    day: str,
    reports_root: Path,
    trade_count: int,
) -> dict[str, Any]:
    reports_root = Path(reports_root)
    windows = _q9_windows(reports_root, day)
    commander_decisions: Counter[str] = Counter()
    commander_reasons: Counter[str] = Counter()
    commander_details: Counter[str] = Counter()
    monitor_intents: Counter[str] = Counter()
    scanner_top1: Counter[str] = Counter()
    strategist_selected: Counter[str] = Counter()
    commander_selected: Counter[str] = Counter()
    approve_noop = 0
    approve_buy = 0
    for window in windows:
        scanner = _mapping(window.get("scanner_control"))
        strategist = _mapping(window.get("strategist_selection"))
        commander = _mapping(window.get("commander_final"))
        if scanner.get("top1_symbol"):
            scanner_top1[str(scanner.get("top1_symbol"))] += 1
        if strategist.get("selected_symbol"):
            strategist_selected[str(strategist.get("selected_symbol"))] += 1
        if commander.get("selected_symbol"):
            commander_selected[str(commander.get("selected_symbol"))] += 1
        decision = str(commander.get("decision") or "")
        intent = str(commander.get("monitor_intent") or "")
        commander_decisions[decision] += 1
        commander_reasons[str(commander.get("reason") or "")] += 1
        detail = str(commander.get("detail") or "")
        if detail:
            commander_details[detail[:160]] += 1
        monitor_intents[intent] += 1
        if decision == "approve" and intent == "NOOP":
            approve_noop += 1
        if decision == "approve" and intent == "BUY":
            approve_buy += 1

    q11 = _q11_opening(reports_root, day)
    no_trade_class = "NOT_NO_TRADE_DAY"
    primary_issue = ""
    if trade_count <= 0:
        if not windows:
            no_trade_class = "MISSING_Q9_EVIDENCE"
            primary_issue = "q9_windows_missing"
        elif approve_noop > 0:
            no_trade_class = "OVER_FILTERING_CANDIDATE"
            primary_issue = "commander_approved_but_monitor_noop"
        elif commander_decisions.get("reject", 0) > 0:
            no_trade_class = "UPSTREAM_REJECTED"
            primary_issue = "commander_rejected_candidates"
        else:
            no_trade_class = "NO_ACTIONABLE_CANDIDATE"
            primary_issue = "no_commander_approved_candidate"

    shadow_opportunity = "UNAVAILABLE"
    if q11.get("available"):
        virtual_trades = int(q11.get("virtual_trades") or 0)
        avg_net = _num(q11.get("avg_net_return_pct"))
        avg_mfe = _num(q11.get("avg_mfe_pct"))
        if virtual_trades <= 0:
            shadow_opportunity = "NO_SHADOW_TRADES"
        elif avg_net is not None and avg_net > 0:
            shadow_opportunity = "POSITIVE_NET_SHADOW"
        elif avg_mfe is not None and avg_mfe > 0:
            shadow_opportunity = "MFE_ONLY_SHADOW"
        else:
            shadow_opportunity = "NEGATIVE_SHADOW"

    return {
        "schema_version": "no_trade_attribution_report.v1",
        "behavior_effect": "observation_only",
        "day": day,
        "trade_count": int(trade_count),
        "q9_window_count": int(len(windows)),
        "no_trade_class": no_trade_class,
        "primary_issue": primary_issue,
        "commander_approve_monitor_noop_count": int(approve_noop),
        "commander_approve_monitor_buy_count": int(approve_buy),
        "commander_decisions": _top(commander_decisions),
        "commander_reasons": _top(commander_reasons),
        "commander_details": _top(commander_details),
        "monitor_intents": _top(monitor_intents),
        "scanner_top1": _top(scanner_top1),
        "strategist_selected": _top(strategist_selected),
        "commander_selected": _top(commander_selected),
        "shadow_opportunity_status": shadow_opportunity,
        "q10_samsung_hynix": _baseline_samsung(reports_root, day),
        "q11_opening_opportunity": q11,
        "q12_btc_woori": _q12_btc_woori(reports_root, day),
        "interpretation": {
            "scope": "Explains no-trade or sparse-trade days without changing execution behavior.",
            "q13_q14_boundary": "If trade_count is zero, Q13/Q14 trade attribution remains insufficient; use this report for over-filtering and missed-opportunity validation.",
        },
    }


def render_no_trade_attribution_report(payload: Mapping[str, Any]) -> str:
    lines = [
        "# No-Trade Attribution Report",
        "",
        f"- Behavior effect: `{payload.get('behavior_effect', '')}`",
        f"- Day: `{payload.get('day', '')}`",
        f"- Trades: {payload.get('trade_count', 0)}",
        f"- Q9 windows: {payload.get('q9_window_count', 0)}",
        f"- No-trade class: `{payload.get('no_trade_class', '')}`",
        f"- Primary issue: `{payload.get('primary_issue', '')}`",
        f"- Commander approve + Monitor NOOP: {payload.get('commander_approve_monitor_noop_count', 0)}",
        "",
        "## Q9 Decision Surface",
        "",
    ]
    for title, key in (
        ("Commander Decisions", "commander_decisions"),
        ("Commander Reasons", "commander_reasons"),
        ("Commander Details", "commander_details"),
        ("Monitor Intents", "monitor_intents"),
        ("Scanner Top1", "scanner_top1"),
        ("Strategist Selected", "strategist_selected"),
    ):
        lines.extend([f"### {title}", ""])
        rows = payload.get(key) if isinstance(payload.get(key), list) else []
        if not rows:
            lines.append("- None")
        else:
            for row in rows:
                if isinstance(row, Mapping):
                    lines.append(f"- `{row.get('name', '')}`: {row.get('count', 0)}")
        lines.append("")

    q11 = _mapping(payload.get("q11_opening_opportunity"))
    lines.extend([
        "## Shadow Opportunity",
        "",
        f"- Status: `{payload.get('shadow_opportunity_status', '')}`",
        f"- Q11 available: {bool(q11.get('available'))}",
        f"- Q11 signal rows: {q11.get('signal_rows', 0)}",
        f"- Q11 probe candidates: {q11.get('probe_candidates', 0)}",
        f"- Q11 probe near-misses: {q11.get('probe_near_misses', 0)}",
        f"- Q11 virtual trades: {q11.get('virtual_trades', 0)}",
        f"- Q11 win rate: {q11.get('win_rate') if q11.get('win_rate') is not None else '-'}",
        f"- Q11 avg net: {_pct(q11.get('avg_net_return_pct'))}",
        f"- Q11 avg MFE: {_pct(q11.get('avg_mfe_pct'))}",
        f"- Q11 avg MAE: {_pct(q11.get('avg_mae_pct'))}",
        "",
        "## Baseline Summary",
        "",
        "| Baseline | Horizon | Trades | Win Rate | Avg Net | PF |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ])
    for baseline_key, label in (
        ("q10_samsung_hynix", "Q10 Samsung/Hynix"),
        ("q12_btc_woori", "Q12 BTC/Woori"),
    ):
        baseline = _mapping(payload.get(baseline_key))
        rows = baseline.get("horizons") if isinstance(baseline.get("horizons"), list) else []
        if not rows:
            lines.append(f"| {label} | - | 0 | - | - | - |")
            continue
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        label,
                        str(row.get("horizon") or "-"),
                        str(row.get("trade_count") or 0),
                        str(row.get("win_rate") if row.get("win_rate") is not None else "-"),
                        _pct(row.get("avg_net_return_pct")),
                        str(row.get("profit_factor") if row.get("profit_factor") is not None else "-"),
                    ]
                )
                + " |"
            )
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- This report does not change trading behavior.",
        "- If trades are zero, Q13/Q14 trade attribution is insufficient; this report decides whether the absence itself is an over-filtering signal.",
    ])
    return "\n".join(lines) + "\n"
