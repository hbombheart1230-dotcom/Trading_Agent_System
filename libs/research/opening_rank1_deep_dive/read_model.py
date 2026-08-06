from __future__ import annotations

from typing import Any

from .loaders import epoch_to_kst


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _candidate(window: dict[str, Any], symbol: str) -> dict[str, Any]:
    control = _dict(window.get("scanner_control"))
    for row in list(control.get("top20") or control.get("top10") or []):
        if isinstance(row, dict) and str(row.get("symbol") or "") == symbol:
            return row
    return {}


def _macro_fields(payload: dict[str, Any]) -> dict[str, Any]:
    moves = _dict(payload.get("index_moves"))
    macro = _dict(payload.get("macro_moves"))
    sentiment = _dict(payload.get("global_sentiment"))
    korea = _dict(payload.get("korea_indices"))
    return {
        "macro_observed_at": payload.get("generated_at"),
        "global_sentiment_score": _float(sentiment.get("score")),
        "kospi_pct": _float(moves.get("kospi_pct")),
        "kosdaq_pct": _float(moves.get("kosdaq_pct")),
        "kospi200_pct": _float(moves.get("kospi200_pct")),
        "krx_night_futures_pct": _float(moves.get("krx_night_futures_pct")),
        "nasdaq_pct": _float(moves.get("nasdaq_pct")),
        "sp500_pct": _float(moves.get("sp500_pct")),
        "dow_pct": _float(moves.get("dow_pct")),
        "dxy_pct": _float(macro.get("dxy_pct")),
        "us10y_delta": _float(macro.get("tnx_delta")),
        "vix_level": _float(macro.get("vix_level")),
        "vix_pct": _float(macro.get("vix_pct")),
        "market_rising": korea.get("rising"),
        "market_falling": korea.get("falling"),
        "macro_authority": "POINT_IN_TIME_AT_OR_BEFORE_DECISION" if payload else "MISSING",
    }


def build_case(
    episode: dict[str, Any],
    *,
    window: dict[str, Any],
    macro: dict[str, Any],
    metadata: dict[str, Any],
    actual_trades: list[dict[str, Any]],
) -> dict[str, Any]:
    symbol = str(episode.get("symbol") or "")
    candidate = _candidate(window, symbol)
    compact = _dict(candidate.get("compact_feature_snapshot"))
    episode_features = _dict(episode.get("feature_snapshot"))
    score_breakdown = _dict(candidate.get("score_breakdown")) or _dict(episode.get("score_breakdown"))
    quant = _dict(candidate.get("quant_factor_snapshot"))
    factors = _dict(quant.get("factors"))
    suitability = _dict(candidate.get("tactic_suitability"))
    strategist = _dict(window.get("strategist_selection"))
    commander = _dict(window.get("commander_final"))
    checkpoints = _dict(episode.get("checkpoints"))
    c30 = _dict(checkpoints.get("+30m"))
    baseline_epoch = int(episode.get("baseline_epoch") or 0)
    actual_overlap = []
    for trade in actual_trades:
        raw = str(trade.get("entry_ts") or "")
        try:
            from datetime import datetime

            entry_epoch = int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except (TypeError, ValueError):
            entry_epoch = 0
        item = dict(trade)
        item["overlaps_opening_window"] = bool(
            entry_epoch and int(episode.get("decision_epoch") or 0) <= entry_epoch <= baseline_epoch + 1800
        )
        actual_overlap.append(item)

    row = {
        "episode_id": episode.get("episode_id"),
        "decision_id": episode.get("decision_id"),
        "day": episode.get("day"),
        "symbol": symbol,
        "symbol_name": metadata.get("name") or "",
        "name_authority": metadata.get("name_authority") or "MISSING",
        "themes": list(metadata.get("themes") or []),
        "theme_authority": metadata.get("theme_authority") or "MISSING",
        "decision_time_kst": epoch_to_kst(episode.get("decision_epoch")),
        "virtual_buy_time_kst": epoch_to_kst(baseline_epoch),
        "virtual_buy_price": _float(episode.get("baseline_price")),
        "virtual_sell_time_kst": epoch_to_kst(c30.get("observed_epoch")),
        "virtual_sell_price_30m": _float(c30.get("price")),
        "hold_minutes": round((int(c30.get("observed_epoch") or 0) - baseline_epoch) / 60.0, 2),
        "gross_return_30m_pct": _float(c30.get("gross_return_pct")),
        "net_return_30m_pct": _float(c30.get("live_net_return_pct")),
        "mfe_30m_pct": _float(c30.get("mfe_pct")),
        "mae_30m_pct": _float(c30.get("mae_pct")),
        "return_5m_pct": _float(_dict(checkpoints.get("+5m")).get("live_net_return_pct")),
        "return_15m_pct": _float(_dict(checkpoints.get("+15m")).get("live_net_return_pct")),
        "return_60m_pct": _float(_dict(checkpoints.get("+60m")).get("live_net_return_pct")),
        "return_eod_pct": _float(_dict(checkpoints.get("EOD")).get("live_net_return_pct")),
        "outcome": "WIN" if float(c30.get("live_net_return_pct") or 0.0) > 0 else "LOSS",
        "sources": list(episode.get("sources") or []),
        "source_class": episode.get("source_class"),
        "scanner_score": _float(candidate.get("score_total") or episode.get("score_total")),
        "scanner_pre_adjust_score": _float(candidate.get("pre_adjust_score_total")),
        "risk_score": _float(candidate.get("risk_score") or episode.get("risk_score")),
        "confidence": _float(candidate.get("confidence")),
        "entry_compatibility_score": _float(candidate.get("entry_compatibility_score")),
        "scanner_chart_fit_score": _float(candidate.get("scanner_chart_fit_score")),
        "scanner_macro_chart_fit_score": _float(candidate.get("scanner_macro_chart_fit_score")),
        "intraday_change_pct": _float(compact.get("intraday_change_pct")),
        "quote_trading_value": _float(compact.get("quote_trading_value")),
        "quote_volume": _float(compact.get("quote_volume")),
        "quote_spread_bps": _float(compact.get("quote_spread_bps")),
        "vwap_distance_pct": _float(
            factors.get("vwap_distance_pct")
            if factors.get("vwap_distance_pct") is not None
            else compact.get("engine_vwap_distance")
        ),
        "above_vwap": (
            not bool(factors.get("is_below_vwap"))
            if factors.get("is_below_vwap") is not None
            else episode_features.get("above_vwap")
        ),
        "volume_ratio": _float(
            factors.get("volume_ratio")
            if factors.get("volume_ratio") is not None
            else compact.get("compat_volume_ratio")
            if compact.get("compat_volume_ratio") is not None
            else episode_features.get("volume_ratio")
        ),
        "volume_spike20": _float(
            factors.get("volume_spike20")
            if factors.get("volume_spike20") is not None
            else compact.get("engine_volume_spike20")
            if compact.get("engine_volume_spike20") is not None
            else episode_features.get("volume_ratio")
        ),
        "scanner_observed_return_5m_pct": _float(episode_features.get("return_5m_pct")),
        "scanner_observed_turnover": _float(episode_features.get("turnover")),
        "trend_strength": _float(factors.get("trend_strength") or compact.get("engine_trend_strength")),
        "adx14": _float(compact.get("engine_adx14")),
        "volatility20": _float(compact.get("engine_volatility20")),
        "sector_relative_strength": _float(factors.get("sector_relative_strength")),
        "cross_section_rank": _float(factors.get("cross_section_rank")),
        "engine_regime": compact.get("engine_regime"),
        "tactic_id": suitability.get("tactic_id") or quant.get("tactic_id"),
        "tactic_suitability_score": _float(suitability.get("score")),
        "tactic_suitability_tier": suitability.get("tier"),
        "playbook": quant.get("playbook") or strategist.get("playbook"),
        "strategist_scenario": strategist.get("scenario"),
        "strategist_playbook": strategist.get("playbook"),
        "theme_match": candidate.get("theme_match"),
        "score_trading_value": _float(score_breakdown.get("trading_value")),
        "score_momentum": _float(score_breakdown.get("momentum")),
        "score_trend": _float(score_breakdown.get("trend")),
        "score_ma_alignment": _float(score_breakdown.get("ma_alignment")),
        "score_adx_trend": _float(score_breakdown.get("adx_trend")),
        "score_volume_surge": _float(score_breakdown.get("volume_surge")),
        "score_intraday_strength": _float(score_breakdown.get("intraday_strength")),
        "score_vwap_alignment": _float(score_breakdown.get("vwap_alignment")),
        "score_theme_boost": _float(score_breakdown.get("theme_boost")),
        "score_sentiment": _float(score_breakdown.get("sentiment")),
        "score_cross_section_rank": _float(score_breakdown.get("cross_section_rank")),
        "score_repeat_symbol_penalty": _float(score_breakdown.get("repeat_symbol_penalty")),
        "score_symbol_prior": _float(score_breakdown.get("symbol_prior")),
        "score_entry_compatibility_bias": _float(score_breakdown.get("entry_compatibility_bias")),
        "score_macro_chart_fit_bias": _float(score_breakdown.get("scanner_macro_chart_fit_bias")),
        "score_risk_penalty": _float(score_breakdown.get("risk_penalty")),
        "theme_boost": _float(score_breakdown.get("theme_boost")),
        "expected_monitor_block_reason": candidate.get("expected_monitor_block_reason"),
        "dominant_block_reason": candidate.get("dominant_block_reason"),
        "commander_decision": commander.get("decision"),
        "commander_selected_symbol": commander.get("selected_symbol"),
        "monitor_intent": commander.get("monitor_intent"),
        "actual_same_day_trades": actual_overlap,
    }
    row.update(_macro_fields(macro))
    return row
