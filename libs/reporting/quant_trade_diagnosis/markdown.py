from __future__ import annotations

from typing import Any, Mapping


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):+.4f}%"
    except (TypeError, ValueError):
        return str(value)


def _ratio_pct(value: Any) -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value) * 100:+.4f}%"
    except (TypeError, ValueError):
        return str(value)


def _join(value: Any) -> str:
    rows = [str(item) for item in value or [] if str(item)]
    return ", ".join(rows) if rows else "n/a"


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    out.extend("| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows)
    return out


def render_quant_trade_diagnosis(payload: Mapping[str, Any]) -> str:
    trade = _mapping(payload.get("trade"))
    market = _mapping(payload.get("market_and_strategy"))
    strategy_scores = _mapping(payload.get("strategy_candidate_scores"))
    selection = _mapping(payload.get("selection_authority_chain"))
    scanner = _mapping(payload.get("scanner_ranking"))
    commander = _mapping(payload.get("commander_control"))
    entry = _mapping(payload.get("monitor_entry"))
    exit_data = _mapping(payload.get("monitor_exit"))
    horizon = _mapping(exit_data.get("horizon_alignment"))
    post_exit = _mapping(exit_data.get("post_exit"))
    outcome = _mapping(payload.get("trade_outcome"))
    root = _mapping(payload.get("root_cause_attribution"))
    quant = _mapping(payload.get("quant_interpretation"))
    conditional = _mapping(payload.get("conditional_alpha_context"))
    conditional_returns = _mapping(conditional.get("forward_returns_pct"))

    lines = [
        "# Quant Trade Diagnosis",
        "",
        "## Executive Diagnosis",
        "",
        str(payload.get("executive_diagnosis") or "Insufficient evidence."),
        "",
        "## Trade",
        "",
        *_table(
            ["Trade ID", "Day", "Symbol", "Status"],
            [[trade.get("trade_id"), trade.get("day"), trade.get("symbol"), trade.get("status")]],
        ),
        "",
        "## Market Regime And Strategy Frame",
        "",
        *_table(
            ["Regime", "Rail", "Sentiment", "Global Score", "VIX", "Playbook", "Risk Tone"],
            [[
                market.get("market_regime"),
                market.get("market_regime_rail"),
                market.get("market_sentiment"),
                market.get("global_sentiment_score"),
                market.get("vix_level"),
                market.get("playbook"),
                market.get("risk_tone"),
            ]],
        ),
        "",
        f"- Trade aggressiveness: `{_fmt(market.get('trade_aggressiveness'))}`",
        f"- Themes: {_join(market.get('themes'))}",
        "",
        "## Strategy Candidate Scores",
        "",
    ]
    score_rows = [
        [row.get("name"), row.get("score"), row.get("result"), row.get("reason")]
        for row in strategy_scores.get("rows") or []
        if isinstance(row, Mapping)
    ]
    if score_rows:
        lines.extend(_table(["Strategy", "Score", "Result", "Reason"], score_rows))
    else:
        lines.append(
            "Strategy option scores were not retained in the authoritative artifact. "
            "`INSUFFICIENT_EVIDENCE`; no score was inferred."
        )
    lines.extend(
        [
            "",
            "## Selection Authority Chain",
            "",
            *_table(
                [
                    "Raw Scanner Top1",
                    "Post-Strategy Top1",
                    "Selected",
                    "Commander",
                    "Executed",
                    "Rank",
                    "Consistent",
                ],
                [[
                    selection.get("raw_scanner_top1"),
                    selection.get("post_strategy_top1"),
                    selection.get("selected_symbol"),
                    selection.get("commander_candidate"),
                    selection.get("executed_symbol"),
                    selection.get("selected_rank"),
                    selection.get("consistent"),
                ]],
            ),
            "",
            "## Scanner Ranking Evidence",
            "",
            *_table(
                ["Rank", "Score", "Confidence", "Risk", "Absolute Quality"],
                [[
                    scanner.get("rank"),
                    scanner.get("score_total"),
                    scanner.get("confidence"),
                    scanner.get("risk_score"),
                    scanner.get("absolute_quality"),
                ]],
            ),
            "",
            f"- Selection reason: {scanner.get('selection_reason') or 'n/a'}",
            "",
            "### Score Decomposition",
            "",
        ]
    )
    components = _mapping(scanner.get("score_decomposition"))
    component_rows = sorted(
        ([name, value] for name, value in components.items()),
        key=lambda row: abs(float(row[1])) if isinstance(row[1], (int, float)) else 0,
        reverse=True,
    )
    lines.extend(
        _table(["Component", "Contribution"], component_rows[:20])
        if component_rows
        else ["No score decomposition was retained."]
    )
    lines.extend(
        [
            "",
            "## Commander Control",
            "",
            *_table(
                ["Mode", "Risk Mode", "Max Rank", "Runner-Ups", "Cascade", "Cache Used"],
                [[
                    commander.get("mode"),
                    commander.get("risk_mode"),
                    commander.get("max_priority_rank"),
                    commander.get("max_runner_ups"),
                    commander.get("cascade_enabled"),
                    commander.get("strategist_cache_used"),
                ]],
            ),
            "",
            f"- Allowed playbooks: {_join(commander.get('allowed_playbooks'))}",
            f"- Banned playbooks: {_join(commander.get('banned_playbooks'))}",
            f"- Reason: {commander.get('reason') or 'n/a'}",
            "",
            "## Monitor Entry Diagnosis",
            "",
            *_table(
                [
                    "Decision",
                    "Reason",
                    "Pattern",
                    "Path",
                    "Quality",
                    "Hard Gate",
                    "Volume Ratio",
                    "Cost Edge",
                ],
                [[
                    entry.get("decision"),
                    entry.get("reason"),
                    entry.get("pattern"),
                    entry.get("condition_path"),
                    entry.get("entry_quality_score"),
                    entry.get("hard_gate_passed"),
                    entry.get("volume_ratio"),
                    _ratio_pct(entry.get("cost_adjusted_edge_pct")),
                ]],
            ),
            "",
            f"- Hard blockers: {_join(entry.get('blockers'))}",
            f"- Cost floor state: `{_fmt(entry.get('cost_floor_state'))}`",
            "",
            "## Monitor Exit Diagnosis",
            "",
            *_table(
                ["Reason", "Exit Axis", "Hold Sec", "Horizon", "Alignment", "Violation"],
                [[
                    exit_data.get("reason"),
                    exit_data.get("active_exit_axis"),
                    exit_data.get("position_age_seconds"),
                    horizon.get("strategy_horizon"),
                    horizon.get("status"),
                    horizon.get("horizon_violation_candidate"),
                ]],
            ),
            "",
            f"- Target hold would improve: `{_fmt(horizon.get('target_hold_would_improve_exit'))}`",
            f"- Best post-exit offset: `{_fmt(post_exit.get('best_exit_offset'))}`",
            f"- Maximum post-exit upside: {_pct(post_exit.get('max_post_exit_upside_pct'))}",
            "",
            "## Broker-Truth Outcome",
            "",
            *_table(
                ["Net Return", "Realized PnL", "Holding Sec", "Truth Source", "Authoritative"],
                [[
                    _pct(outcome.get("net_return_pct")),
                    outcome.get("realized_pnl"),
                    outcome.get("holding_seconds"),
                    outcome.get("broker_truth_source") or outcome.get("pnl_source"),
                    outcome.get("broker_authoritative"),
                ]],
            ),
            "",
            "## Same-Symbol Sequence",
            "",
        ]
    )
    sequence_rows = [
        [
            "*" if row.get("current_trade") else "",
            row.get("trade_id"),
            row.get("entry_timestamp"),
            row.get("exit_timestamp"),
            _pct(row.get("net_return_pct")),
            row.get("holding_seconds"),
        ]
        for row in payload.get("same_symbol_sequence") or []
        if isinstance(row, Mapping)
    ]
    lines.extend(
        _table(["Current", "Trade ID", "Entry", "Exit", "Return", "Hold Sec"], sequence_rows)
        if sequence_rows
        else ["No same-day same-symbol sequence was available."]
    )
    lines.extend(
        [
            "",
            "## Root Cause Attribution",
            "",
            f"- Status: `{_fmt(root.get('status'))}`",
            f"- Primary: `{_fmt(root.get('primary'))}`",
            f"- Labels: {_join(root.get('labels'))}",
            "",
            "## Conditional Alpha Context",
            "",
            *_table(
                ["Match", "Authority", "Archetype", "Stage Root Cause", "Cohorts"],
                [[
                    conditional.get("match_status"),
                    conditional.get("authority"),
                    conditional.get("opening_archetype"),
                    conditional.get("stage_root_cause"),
                    _join(conditional.get("cohort_ids")),
                ]],
            ),
            "",
            *_table(
                ["5m", "15m", "30m", "60m", "EOD", "MFE 30m", "MAE 30m"],
                [[
                    _pct(conditional_returns.get("5m")),
                    _pct(conditional_returns.get("15m")),
                    _pct(conditional_returns.get("30m")),
                    _pct(conditional_returns.get("60m")),
                    _pct(conditional_returns.get("EOD")),
                    _pct(conditional.get("mfe_30m_pct")),
                    _pct(conditional.get("mae_30m_pct")),
                ]],
            ),
            "",
            f"- Evidence warning: {conditional.get('warning') or 'none'}",
            "",
            "## Quant Interpretation",
            "",
            *_table(
                [
                    "Entry Cost Edge Positive",
                    "Cost Edge",
                    "Horizon",
                    "Selection",
                    "Attribution Axis",
                ],
                [[
                    quant.get("entry_cost_edge_positive"),
                    quant.get("cost_edge_status"),
                    quant.get("horizon_status"),
                    quant.get("selection_quality"),
                    quant.get("primary_attribution_axis"),
                ]],
            ),
            "",
            "## Next Evaluation Questions",
            "",
        ]
    )
    lines.extend(
        f"- {question}" for question in payload.get("next_evaluation_questions") or []
    )
    lines.extend(
        [
            "",
            "> Diagnostic only. This report does not change Scanner, Strategist, "
            "Commander, Monitor, entry, exit, or execution behavior.",
            "",
        ]
    )
    return "\n".join(lines)
