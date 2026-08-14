from __future__ import annotations

from ..adapters.trade_bundle import TradeBundleSource
from ..models.common import AvailabilityStatus
from ..models.trades import DecisionLineage, TradeSummary
from .trade_values import (
    integer,
    mapping,
    number,
    ratio_to_pct,
    source_status,
    string_list,
    text_value,
    timestamp,
)


def project_trade_summary(source: TradeBundleSource) -> TradeSummary | None:
    root = source.summary_input
    if root is None:
        return None
    trade = mapping(root.get("trade"))
    truth = mapping(root.get("truth_surface"))
    strategy = mapping(root.get("market_and_strategy"))
    horizon = mapping(root.get("strategy_horizon"))
    flow = mapping(root.get("decision_flow"))
    tactic = mapping(root.get("quant_tactic"))
    entry = source.entry or {}
    exit_row = source.exit or {}
    symbol = text_value(trade.get("symbol")) or text_value(entry.get("symbol"))
    if not symbol:
        return None
    artifact_status = source_status(source.source_status)
    themes = string_list(trade.get("themes"))
    symbol_name = text_value(trade.get("symbol_name"))
    if artifact_status == AvailabilityStatus.AVAILABLE and (
        symbol_name is None or not themes or source.entry is None or source.exit is None
    ):
        artifact_status = AvailabilityStatus.PARTIAL
    return TradeSummary(
        trade_id=source.ref.trade_id,
        day=source.ref.day,
        symbol=symbol,
        symbol_name=symbol_name,
        themes=themes,
        status=text_value(trade.get("status")) or "unknown",
        entry_time=timestamp(entry.get("ts")),
        exit_time=timestamp(exit_row.get("ts") or exit_row.get("timestamp")),
        entry_price=number(truth.get("buy_price")),
        exit_price=number(truth.get("sell_price")),
        quantity=number(mapping(truth.get("cost_analysis")).get("quantity"))
        or number(entry.get("filled_qty") or entry.get("qty")),
        hold_seconds=number(horizon.get("actual_hold_sec")),
        realized_pnl_krw=number(truth.get("pnl")),
        realized_return_pct=ratio_to_pct(truth.get("pnl_pct")),
        result=text_value(truth.get("result_label")),
        playbook=text_value(strategy.get("playbook")),
        tactic_id=text_value(tactic.get("tactic_id")),
        strategy_horizon=text_value(horizon.get("strategist_horizon")),
        scanner_rank=integer(flow.get("scanner_rank")),
        artifact_status=artifact_status,
        artifact_scope="TRADE_BUNDLE",
    )


def project_decisions(source: TradeBundleSource) -> DecisionLineage:
    root = source.summary_input or {}
    strategy = mapping(root.get("market_and_strategy"))
    horizon = mapping(root.get("strategy_horizon"))
    flow = mapping(root.get("decision_flow"))
    tactic = mapping(root.get("quant_tactic"))
    suitability = mapping(tactic.get("tactic_suitability"))
    scanner = mapping((source.diagnosis or {}).get("scanner_ranking"))
    return DecisionLineage(
        playbook=text_value(strategy.get("playbook")),
        tactic_id=text_value(tactic.get("tactic_id")),
        strategist_horizon=text_value(horizon.get("strategist_horizon")),
        commander_horizon=text_value(horizon.get("commander_horizon")),
        scanner_rank=integer(flow.get("scanner_rank")),
        scanner_score=number(scanner.get("score_total"))
        or number(flow.get("scanner_score")),
        scanner_chart_fit_score=number(flow.get("scanner_chart_fit_score")),
        selection_basis=text_value(flow.get("selection_basis")),
        monitor_entry_reason=text_value(flow.get("entry_reason")),
        monitor_exit_trigger=text_value(flow.get("exit_trigger")),
        tactic_suitability_score=number(suitability.get("score")),
    )
