from __future__ import annotations

from typing import Any


def _pct(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):+.3f}%"


def _num(value: Any, digits: int = 3) -> str:
    return "N/A" if value is None else f"{float(value):.{digits}f}"


def _group_table(title: str, groups: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Group | N | Win rate | Average net | Median net | PF | Average MFE | Average MAE |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key, row in groups.items():
        win_rate = row.get("win_rate")
        lines.append(
            f"| {key} | {row.get('count')} | "
            f"{_pct(float(win_rate) * 100) if win_rate is not None else 'N/A'} | "
            f"{_pct(row.get('avg_return_pct'))} | {_pct(row.get('median_return_pct'))} | "
            f"{_num(row.get('profit_factor'))} | {_pct(row.get('avg_mfe_pct'))} | "
            f"{_pct(row.get('avg_mae_pct'))} |"
        )
    lines.append("")
    return lines


def _case_table(title: str, rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        f"## {title}",
        "",
        "| Decision | Symbol | Name | Net +30m | Entry vs prior | Open to entry | Relative volume | Rank gap | Price arc |",
        "|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        decision = str(row.get("decision_time_kst") or "")[5:19].replace("T", " ")
        lines.append(
            f"| {decision} | {row.get('symbol') or ''} | {row.get('symbol_name') or 'N/A'} | "
            f"{_pct(row.get('net_return_30m_pct'))} | "
            f"{_pct(row.get('entry_vs_prior_close_pct'))} | "
            f"{_pct(row.get('open_to_entry_pct'))} | "
            f"{_num(row.get('opening_relative_volume'))} | "
            f"{_num(row.get('rank1_rank2_gap'))} | {row.get('price_arc') or 'N/A'} |"
        )
    lines.append("")
    return lines


def _hypothesis_table(rows: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        "## Pre-Decision Hypothesis Screens",
        "",
        "| Screen | N / days / symbols | Win rate | Average | Median | PF | Average excluding top 3 | Winsorized +/-5% | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name, row in rows.items():
        win_rate = row.get("win_rate")
        lines.append(
            f"| {name} | {row.get('count')}/{row.get('day_count')}/{row.get('symbol_count')} | "
            f"{_pct(float(win_rate) * 100) if win_rate is not None else 'N/A'} | "
            f"{_pct(row.get('avg_return_pct'))} | {_pct(row.get('median_return_pct'))} | "
            f"{_num(row.get('profit_factor'))} | {_pct(row.get('avg_without_top3_pct'))} | "
            f"{_pct(row.get('winsorized_5pct_avg'))} | {row.get('evidence_status')} |"
        )
    lines += [
        "",
        "These screens were defined after inspecting the same sample. `SCREENABLE` means",
        "the historical breadth is sufficient for prospective testing, not that the screen",
        "is a validated edge or an authorized trading policy.",
        "",
    ]
    return lines


def _actual_trade_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "## Actual Trade Cross-Check",
        "",
        "| Case | Trade ID | Relation | Holding seconds | Actual net | Entry / exit reason |",
        "|---|---|---|---:|---:|---|",
    ]
    count = 0
    for row in rows:
        case = f"{row.get('day')} {row.get('symbol')} {row.get('symbol_name') or ''}"
        for trade in row.get("actual_same_day_trades") or []:
            count += 1
            relation = "opening overlap" if trade.get("overlaps_opening_window") else "same day"
            reason = f"{trade.get('entry_reason') or 'N/A'} / {trade.get('exit_reason') or 'N/A'}"
            lines.append(
                f"| {case} | {trade.get('trade_id') or 'N/A'} | {relation} | "
                f"{_num(trade.get('holding_seconds'), 0)} | {_pct(trade.get('net_return_pct'))} | "
                f"{reason} |"
            )
    if not count:
        lines.append("| - | - | - | - | - | No matching actual trades |")
    lines.append("")
    return lines


def render_markdown(payload: dict[str, Any]) -> str:
    analysis = payload["analysis"]
    overall = analysis["overall"]
    coverage = payload["coverage"]
    daily = analysis["daily"]
    sensitivity = analysis["outlier_sensitivity"]
    contribution = sensitivity["contribution"]
    lines = [
        "# OPEN_0_20_RANK1_30M Deep Dive",
        "",
        "## Scope",
        "",
        "- Period: 2026-06-24 through 2026-07-30.",
        "- Population: Scanner pre-Strategist intrinsic Rank-1 observations during 09:00-09:19 KST.",
        "- Reference entry: first one-minute candle strictly after the decision.",
        "- Reference exit: fixed +30-minute observation.",
        "- Cost: 0.28% round trip.",
        "- This is retrospective research. It does not authorize trading behavior.",
        "",
        "## Coverage",
        "",
        f"- Cases: **{coverage['case_count']}**",
        f"- Symbol names: **{coverage['name_count']}/{coverage['case_count']}**",
        f"- Current theme references: **{coverage['theme_count']}/{coverage['case_count']}**",
        f"- Original Q9 windows: **{coverage['q9_count']}/{coverage['case_count']}**",
        f"- Point-in-time macro: **{coverage['macro_count']}/{coverage['case_count']}**",
        f"- Microstructure / rank context: **{coverage['microstructure_count']}/"
        f"{coverage['rank_context_count']}**",
        f"- Actual same-day / opening-overlap trades: **{coverage['actual_trade_case_count']}/"
        f"{coverage['actual_opening_overlap_case_count']}**",
        "",
        "## Overall Result",
        "",
        f"- Win rate: **{_pct(float(overall.get('win_rate') or 0) * 100)}**",
        f"- Average / median net +30m: **{_pct(overall.get('avg_return_pct'))} / "
        f"{_pct(overall.get('median_return_pct'))}**",
        f"- Profit factor: **{_num(overall.get('profit_factor'))}**",
        f"- Average MFE / MAE: **{_pct(overall.get('avg_mfe_pct'))} / "
        f"{_pct(overall.get('avg_mae_pct'))}**",
        f"- Observed days / positive-day ratio: **{daily.get('day_count')} / "
        f"{_pct(float(daily.get('positive_day_ratio') or 0) * 100)}**",
        "",
        "## Outlier Dependence",
        "",
        f"- All-case average: **{_pct(sensitivity['all'].get('avg_return_pct'))}**",
        f"- Average after removing top 3: **{_pct(sensitivity['remove_top_3'].get('avg_return_pct'))}**",
        f"- Winsorized +/-5% average: **{_pct(sensitivity['winsorize_5pct'].get('avg_return_pct'))}**",
        f"- Top 3 return sum: **{_pct(contribution.get('top3_return_sum_pct'))}**",
        f"- Top 3 share of positive gains: "
        f"**{_pct(float(contribution.get('top3_share_of_positive_gains') or 0) * 100)}**",
        "",
        "The aggregate average is not a broad Rank-1 effect. It depends materially on",
        "a small number of exceptional opening expansions.",
        "",
    ]
    lines += _group_table("Exact Decision-Time Buckets", analysis["by_decision_5m_bucket"])
    lines += _group_table("Market Context", analysis["by_market_bucket"])
    lines += _group_table("Entry Distance From Opening Price", analysis["by_open_to_entry"])
    lines += _group_table("Opening Relative Volume", analysis["by_opening_relative_volume"])
    lines += _group_table("VWAP State", analysis["by_above_vwap"])
    lines += _group_table("Rank-1 Raw-Score Position", analysis["by_rank1_highest_score"])
    lines += _group_table("Diagnostic 30-Minute Price Arc", analysis["by_price_arc"])
    lines += _hypothesis_table(analysis["hypothesis_screens"])
    lines += _case_table("Top Winners: Condition Detail", analysis["top_winners"])
    lines += _case_table("Top Losers: Condition Detail", analysis["top_losers"])
    lines += _actual_trade_table(payload.get("cases") or [])
    lines += [
        "## Findings",
        "",
        *[f"- {item}" for item in payload.get("findings") or []],
        "",
        "## Interpretation Guardrails",
        "",
        "- `LIMIT_UP_TRAJECTORY` and `CRASH_REVERSAL` use future 30-minute highs and are",
        "  diagnostic labels only. They cannot be used as entry inputs.",
        "- Current theme names are reference metadata, not point-in-time causal evidence.",
        "- Direct historical news evidence is too sparse and noisy to attribute the rare",
        "  winners to a catalyst.",
        "- Future Rank-1 persistence is look-ahead information and cannot be promoted.",
        "- The next valid step is prospective subgroup observation, not a runtime rule change.",
        "",
    ]
    return "\n".join(lines)
