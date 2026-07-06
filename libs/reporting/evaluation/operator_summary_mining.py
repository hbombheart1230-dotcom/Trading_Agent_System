from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "operator_summary_mining.v1"


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None
    except json.JSONDecodeError as exc:
        return {"__error__": str(exc)}


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _avg(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


@dataclass(frozen=True)
class DailyArtifacts:
    day: str
    daily_summary: dict[str, Any]
    operator_summary: dict[str, Any]
    q8_review: dict[str, Any]
    q9_windows: dict[str, Any]
    closeout: dict[str, Any]
    trade_index: list[Any]
    daily_report: dict[str, Any]
    errors: list[str]


def _daily_artifacts(day_dir: Path) -> DailyArtifacts:
    errors: list[str] = []

    def load(name: str) -> Any:
        payload = _load_json(day_dir / name)
        if isinstance(payload, dict) and "__error__" in payload:
            errors.append(f"{name}: {payload['__error__']}")
        return payload

    return DailyArtifacts(
        day=day_dir.name,
        daily_summary=_dict(load("daily_summary.json")),
        operator_summary=_dict(load("operator_summary.json")),
        q8_review=_dict(load("q8_shadow_blocker_review.json")),
        q9_windows=_dict(load("q9_decision_windows.json")),
        closeout=_dict(load("closeout_maintenance.json")),
        trade_index=_list(load("trade_index.json")),
        daily_report=_dict(load("daily_report.json")),
        errors=errors,
    )


def _presence_report(days: list[DailyArtifacts]) -> dict[str, Any]:
    fields = {
        "daily_summary": "daily_summary",
        "operator_summary": "operator_summary",
        "q8_shadow_blocker_review": "q8_review",
        "q9_decision_windows": "q9_windows",
        "closeout_maintenance": "closeout",
        "trade_index": "trade_index",
        "daily_report": "daily_report",
    }
    counts: dict[str, int] = {}
    for name, attr in fields.items():
        count = 0
        for row in days:
            value = getattr(row, attr)
            if isinstance(value, list):
                if value:
                    count += 1
            elif value:
                count += 1
        counts[name] = count
    total = len(days)
    return {
        "daily_count": total,
        "first_day": days[0].day if days else "",
        "last_day": days[-1].day if days else "",
        "presence_counts": counts,
        "presence_ratio": {
            name: round(value / total, 4) if total else 0.0
            for name, value in counts.items()
        },
        "json_error_count": sum(len(row.errors) for row in days),
        "json_errors": [
            {"day": row.day, "error": error}
            for row in days
            for error in row.errors
        ][:25],
    }


def _daily_quality(days: list[DailyArtifacts]) -> dict[str, Any]:
    recent = days[-20:]
    rows: list[dict[str, Any]] = []
    for row in recent:
        metrics = _dict(row.daily_summary.get("metrics"))
        shadow = _dict(row.daily_summary.get("quant_shadow_candidate_evaluation"))
        q8_gate = _dict(row.q8_review.get("evaluation_trust_gate"))
        q9_windows = _list(row.q9_windows.get("windows"))
        rows.append({
            "day": row.day,
            "trade_count": _safe_int(metrics.get("trade_count")),
            "closed_trade_count": _safe_int(metrics.get("closed_trade_count")),
            "win_rate": _safe_float(metrics.get("win_rate")),
            "avg_return_pct": _safe_float(metrics.get("avg_return_pct")),
            "trade_index_count": len(row.trade_index),
            "q8_candidate_count": _safe_int(row.q8_review.get("candidate_count")),
            "q8_trusted_forward_count": _safe_int(q8_gate.get("trusted_forward_count")),
            "q8_promotion_allowed": q8_gate.get("promotion_allowed"),
            "q9_window_count": _safe_int(row.q9_windows.get("window_count"), len(q9_windows)),
            "q9_has_recovery": bool(row.q9_windows.get("recovery")),
            "shadow_candidate_count": _safe_int(shadow.get("deduped_candidate_count") or shadow.get("candidate_count")),
            "shadow_forward_coverage": _safe_float(shadow.get("forward_outcome_coverage")),
            "closeout_ok": row.closeout.get("ok"),
            "has_daily_report": bool(row.daily_report),
            "has_trade_index": bool(row.trade_index),
        })
    mismatches = [
        {
            "day": row["day"],
            "daily_trade_count": row["trade_count"],
            "trade_index_count": row["trade_index_count"],
        }
        for row in rows
        if row["trade_count"] != row["trade_index_count"] and row["has_trade_index"]
    ]
    missing_runtime_surface = [
        row["day"]
        for row in rows
        if row["trade_count"] > 0 and (not row["has_daily_report"] or not row["has_trade_index"])
    ]
    q9_counts = [row["q9_window_count"] for row in rows if row["q9_window_count"]]
    shadow_coverages = [
        row["shadow_forward_coverage"]
        for row in rows
        if row["shadow_forward_coverage"] is not None
    ]
    return {
        "recent_days": rows,
        "trade_index_mismatch_examples": mismatches[:20],
        "missing_runtime_surface_days": missing_runtime_surface,
        "q9_window_count_average_recent": _avg([float(v) for v in q9_counts]),
        "shadow_forward_coverage_average_recent": _avg([float(v) for v in shadow_coverages]),
    }


def _weekly_quality(root: Path) -> dict[str, Any]:
    weekly_root = root / "weekly"
    weeks = [p for p in sorted(weekly_root.glob("*")) if p.is_dir()] if weekly_root.exists() else []
    rows: list[dict[str, Any]] = []
    for week_dir in weeks:
        summary = _dict(_load_json(week_dir / "weekly_summary.json"))
        metrics = _dict(summary.get("metrics"))
        rows.append({
            "week": week_dir.name,
            "has_summary": bool(summary),
            "trade_count": _safe_int(metrics.get("trade_count")),
            "win_rate": _safe_float(metrics.get("win_rate")),
            "avg_return_pct": _safe_float(metrics.get("avg_return_pct")),
            "has_pattern_performance": bool(summary.get("pattern_performance")),
            "has_quant_tactic_evaluation": bool(summary.get("quant_tactic_evaluation")),
            "has_shadow_evaluation": bool(summary.get("quant_shadow_candidate_evaluation")),
            "has_strategist_llm_evaluation": bool(summary.get("strategist_llm_evaluation")),
        })
    recent = rows[-6:]
    return {
        "weekly_count": len(rows),
        "recent_weeks": recent,
        "usable_week_count": sum(
            1
            for row in rows
            if row["has_pattern_performance"]
            and row["has_quant_tactic_evaluation"]
            and row["has_shadow_evaluation"]
        ),
    }


def _symbol_quality(root: Path) -> dict[str, Any]:
    symbol_root = root / "symbols"
    symbols = [p for p in sorted(symbol_root.glob("*")) if p.is_dir()] if symbol_root.exists() else []
    rows: list[dict[str, Any]] = []
    for symbol_dir in symbols:
        summary = _dict(_load_json(symbol_dir / "symbol_summary.json"))
        memory = _dict(_load_json(symbol_dir / "symbol_memory.json"))
        metrics = _dict(summary.get("metrics"))
        trade_stats = _dict(_dict(memory.get("symbol_memory")).get("trade_stats") or memory.get("trade_stats"))
        trade_count = _safe_int(metrics.get("trade_count") or trade_stats.get("trade_count"))
        rows.append({
            "symbol": symbol_dir.name,
            "trade_count": trade_count,
            "closed_trade_count": _safe_int(metrics.get("closed_trade_count") or trade_stats.get("completed_trade_count")),
            "win_rate": _safe_float(metrics.get("win_rate") if metrics else trade_stats.get("win_rate")),
            "avg_return_pct": _safe_float(metrics.get("avg_return_pct") if metrics else trade_stats.get("avg_return_pct")),
            "has_pattern_performance": bool(summary.get("pattern_performance")),
            "has_shadow_evaluation": bool(summary.get("quant_shadow_candidate_evaluation")),
            "has_strategist_llm_evaluation": bool(summary.get("strategist_llm_evaluation")),
        })
    rows.sort(key=lambda row: (row["trade_count"], row["symbol"]), reverse=True)
    return {
        "symbol_count": len(rows),
        "symbols_with_trade_count_ge_2": sum(1 for row in rows if row["trade_count"] >= 2),
        "symbols_with_trade_count_ge_5": sum(1 for row in rows if row["trade_count"] >= 5),
        "top_symbols": rows[:25],
    }


def _q9_overlap(days: list[DailyArtifacts]) -> dict[str, Any]:
    q9_days = [row for row in days if row.q9_windows]
    q8_days = [row for row in days if row.q8_review]
    daily_summary_days = [row for row in days if row.daily_summary]
    outside_q9_fields = [
        "weekly pattern_performance",
        "weekly strategist_llm_evaluation",
        "symbol-level pattern_performance",
        "symbol-level quant_shadow_candidate_evaluation",
        "operator_readout recurring issues",
        "market_regime_rail_review joined to realized symbol performance",
    ]
    q9_direct_fields = [
        "daily q9_decision_windows",
        "daily q8_shadow_blocker_review",
        "daily artifact availability/inventory",
        "realized trade scorecards under reports/evaluation",
    ]
    window_counts = [
        _safe_int(row.q9_windows.get("window_count"), len(_list(row.q9_windows.get("windows"))))
        for row in q9_days
    ]
    return {
        "q9_operator_summary_day_count": len(q9_days),
        "q8_operator_summary_day_count": len(q8_days),
        "daily_summary_day_count": len(daily_summary_days),
        "q9_window_count_total": sum(window_counts),
        "q9_window_count_average": _avg([float(v) for v in window_counts]),
        "already_consumed_by_q9": q9_direct_fields,
        "not_fully_consumed_by_q9": outside_q9_fields,
    }


def _readiness(payload: dict[str, Any]) -> dict[str, Any]:
    presence = _dict(payload.get("daily_presence"))
    daily = _dict(payload.get("daily_quality"))
    weekly = _dict(payload.get("weekly_quality"))
    symbols = _dict(payload.get("symbol_quality"))
    q9 = _dict(payload.get("q9_overlap"))
    issues: list[str] = []
    strengths: list[str] = []
    if _safe_int(presence.get("daily_count")) >= 40:
        strengths.append("daily operator summaries cover enough history for operational mining")
    if _safe_int(weekly.get("usable_week_count")) >= 4:
        strengths.append("weekly summaries contain tactic/shadow evidence across multiple weeks")
    if _safe_int(symbols.get("symbols_with_trade_count_ge_5")) >= 10:
        strengths.append("symbol summaries have enough repeated names for symbol-level diagnostics")
    if _safe_int(q9.get("q9_window_count_total")) >= 1000:
        strengths.append("Q9 decision windows are dense enough for attribution diagnostics")
    if daily.get("missing_runtime_surface_days"):
        issues.append("some recent days have daily_summary trades but missing daily_report/trade_index surface")
    if daily.get("trade_index_mismatch_examples"):
        issues.append("some recent trade_index counts differ from daily_summary trade counts")
    if _safe_int(q9.get("q9_operator_summary_day_count")) < 5:
        issues.append("Q9-linked operator_summary history is still short")
    status = "USABLE_WITH_GAPS" if strengths else "WEAK"
    if issues and not strengths:
        status = "NEEDS_REPAIR"
    elif not issues and strengths:
        status = "USABLE"
    return {
        "status": status,
        "strengths": strengths,
        "issues": issues,
        "recommended_use": [
            "use operator_summary as Q9 support evidence, not as the single source of truth",
            "mine weekly and symbol summaries for recurring failure/success patterns",
            "keep execution behavior frozen; use this report for observability only",
        ],
    }


def build_operator_summary_mining(reports_root: Path | str = "reports") -> dict[str, Any]:
    reports_root = Path(reports_root)
    operator_root = reports_root / "operator_summary"
    daily_root = operator_root / "daily"
    day_dirs = [p for p in sorted(daily_root.glob("*")) if p.is_dir()] if daily_root.exists() else []
    days = [_daily_artifacts(path) for path in day_dirs]
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "observation_only",
        "source": str(operator_root),
        "daily_presence": _presence_report(days),
        "daily_quality": _daily_quality(days),
        "weekly_quality": _weekly_quality(operator_root),
        "symbol_quality": _symbol_quality(operator_root),
        "q9_overlap": _q9_overlap(days),
    }
    payload["readiness"] = _readiness(payload)
    return payload


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render_operator_summary_mining_markdown(payload: dict[str, Any]) -> str:
    presence = _dict(payload.get("daily_presence"))
    daily = _dict(payload.get("daily_quality"))
    weekly = _dict(payload.get("weekly_quality"))
    symbols = _dict(payload.get("symbol_quality"))
    q9 = _dict(payload.get("q9_overlap"))
    readiness = _dict(payload.get("readiness"))
    lines = [
        "# Operator Summary Mining Report",
        "",
        f"- Schema: `{payload.get('schema_version')}`",
        f"- Behavior effect: `{payload.get('behavior_effect')}`",
        f"- Source: `{payload.get('source')}`",
        f"- Readiness: **{readiness.get('status', '')}**",
        "",
        "## Coverage",
        "",
        f"- Daily range: {presence.get('first_day', '')} to {presence.get('last_day', '')}",
        f"- Daily directories: {presence.get('daily_count', 0)}",
        f"- Weekly summaries: {weekly.get('weekly_count', 0)}",
        f"- Symbol summaries: {symbols.get('symbol_count', 0)}",
        f"- Symbols with >=5 trades: {symbols.get('symbols_with_trade_count_ge_5', 0)}",
        f"- Q9-linked operator days: {q9.get('q9_operator_summary_day_count', 0)}",
        f"- Q9 decision windows total: {q9.get('q9_window_count_total', 0)}",
        "",
        "## Daily Artifact Presence",
        "",
        "| Artifact | Count | Ratio |",
        "|---|---:|---:|",
    ]
    counts = _dict(presence.get("presence_counts"))
    ratios = _dict(presence.get("presence_ratio"))
    for name in sorted(counts):
        lines.append(f"| `{name}` | {counts[name]} | {_fmt(ratios.get(name))} |")
    lines.extend([
        "",
        "## Recent Daily Quality",
        "",
        "| Day | Trades | Trade Index | Q8 Candidates | Q9 Windows | Shadow Forward Coverage | Closeout |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])
    for row in _list(daily.get("recent_days")):
        lines.append(
            "| {day} | {trades} | {trade_index} | {q8} | {q9w} | {coverage} | {closeout} |".format(
                day=row.get("day", ""),
                trades=row.get("trade_count", 0),
                trade_index=row.get("trade_index_count", 0),
                q8=row.get("q8_candidate_count", 0),
                q9w=row.get("q9_window_count", 0),
                coverage=_fmt(row.get("shadow_forward_coverage")),
                closeout=_fmt(row.get("closeout_ok")),
            )
        )
    lines.extend([
        "",
        "## Weekly Evidence",
        "",
        "| Week | Trades | Win Rate | Avg Return % | Pattern | Quant | Shadow | Strategist LLM |",
        "|---|---:|---:|---:|---|---|---|---|",
    ])
    for row in _list(weekly.get("recent_weeks")):
        lines.append(
            "| {week} | {trades} | {win} | {avg} | {pattern} | {quant} | {shadow} | {llm} |".format(
                week=row.get("week", ""),
                trades=row.get("trade_count", 0),
                win=_fmt(row.get("win_rate")),
                avg=_fmt(row.get("avg_return_pct")),
                pattern=row.get("has_pattern_performance"),
                quant=row.get("has_quant_tactic_evaluation"),
                shadow=row.get("has_shadow_evaluation"),
                llm=row.get("has_strategist_llm_evaluation"),
            )
        )
    lines.extend([
        "",
        "## Top Symbol Evidence",
        "",
        "| Symbol | Trades | Closed | Win Rate | Avg Return % | Pattern | Shadow | Strategist LLM |",
        "|---|---:|---:|---:|---:|---|---|---|",
    ])
    for row in _list(symbols.get("top_symbols"))[:15]:
        lines.append(
            "| {symbol} | {trades} | {closed} | {win} | {avg} | {pattern} | {shadow} | {llm} |".format(
                symbol=row.get("symbol", ""),
                trades=row.get("trade_count", 0),
                closed=row.get("closed_trade_count", 0),
                win=_fmt(row.get("win_rate")),
                avg=_fmt(row.get("avg_return_pct")),
                pattern=row.get("has_pattern_performance"),
                shadow=row.get("has_shadow_evaluation"),
                llm=row.get("has_strategist_llm_evaluation"),
            )
        )
    lines.extend([
        "",
        "## Q9 Overlap",
        "",
        "Already consumed by Q9:",
    ])
    for item in _list(q9.get("already_consumed_by_q9")):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Not fully consumed by Q9:")
    for item in _list(q9.get("not_fully_consumed_by_q9")):
        lines.append(f"- {item}")
    lines.extend([
        "",
        "## Readiness Notes",
        "",
        "Strengths:",
    ])
    for item in _list(readiness.get("strengths")):
        lines.append(f"- {item}")
    lines.append("")
    lines.append("Issues:")
    issues = _list(readiness.get("issues"))
    if issues:
        for item in issues:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Recommended use:")
    for item in _list(readiness.get("recommended_use")):
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def write_operator_summary_mining(
    reports_root: Path | str = "reports",
    *,
    output_dir: Path | str | None = None,
) -> dict[str, str]:
    reports_root = Path(reports_root)
    payload = build_operator_summary_mining(reports_root)
    target = Path(output_dir) if output_dir else reports_root / "evaluation" / "operator_summary_mining"
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / "operator_summary_mining.json"
    md_path = target / "operator_summary_mining.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_operator_summary_mining_markdown(payload), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


__all__ = [
    "build_operator_summary_mining",
    "render_operator_summary_mining_markdown",
    "write_operator_summary_mining",
]
