from __future__ import annotations

from typing import Any, Dict, List

from libs.runtime.quant.factors import build_factor_snapshot_from_candidate
from libs.runtime.scanner.theme_filter import candidate_theme_match


def to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def compact_selected_snapshot(selected: Dict[str, Any] | None) -> Dict[str, Any]:
    if not isinstance(selected, dict):
        return {}
    candidate = selected.get("candidate") if isinstance(selected.get("candidate"), dict) else {}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    components = selected.get("components") if isinstance(selected.get("components"), dict) else {}
    return {
        "symbol": str(selected.get("symbol") or ""),
        "why": str(selected.get("why") or ""),
        "asset_class_detected": str(selected.get("asset_class_detected") or ""),
        "detection_source": str(selected.get("detection_source") or ""),
        "detection_field": str(selected.get("detection_field") or ""),
        "sources": list(candidate.get("sources") or [])[:8],
        "source_scores": dict(candidate.get("source_scores") or {}),
        "rank_score": to_float(candidate.get("rank_score") or 0.0),
        "universe_score": to_float(candidate.get("universe_score") or 0.0),
        "score_total": to_float(selected.get("score_total") or selected.get("score") or 0.0),
        "risk_score": to_float(selected.get("risk_score") or 0.0),
        "confidence": to_float(selected.get("confidence") or 0.0),
        "best_bid": features.get("quote_best_bid"),
        "best_ask": features.get("quote_best_ask"),
        "spread_bps": features.get("quote_spread_bps"),
        "score_breakdown": dict(selected.get("score_breakdown") or {}),
        "feature_snapshot": {
            "quote_trading_value": features.get("quote_trading_value"),
            "quote_volume": features.get("quote_volume"),
            "intraday_change_pct": features.get("intraday_change_pct"),
            "skill_quote_price": features.get("skill_quote_price"),
            "quote_best_bid": features.get("quote_best_bid"),
            "quote_best_ask": features.get("quote_best_ask"),
            "quote_spread_bps": features.get("quote_spread_bps"),
            "entry_compatibility_score": features.get("entry_compatibility_score"),
            "compatibility_bias": features.get("compatibility_bias"),
            "compatibility_source": features.get("compatibility_source"),
            "compat_vwap_distance_abs": features.get("compat_vwap_distance_abs"),
            "compat_is_below_vwap": features.get("compat_is_below_vwap"),
            "compat_reclaim_proximity": features.get("compat_reclaim_proximity"),
            "compat_volume_ratio": features.get("compat_volume_ratio"),
            "compat_breakout_gap_pct": features.get("compat_breakout_gap_pct"),
            "engine_ma20_gap": features.get("engine_ma20_gap"),
            "engine_close_last": features.get("engine_close_last"),
            "engine_ma60": features.get("engine_ma60"),
            "engine_ma120": features.get("engine_ma120"),
            "engine_adx14": features.get("engine_adx14"),
            "engine_trend_strength": features.get("engine_trend_strength"),
            "engine_volume_spike20": features.get("engine_volume_spike20"),
            "engine_volatility20": features.get("engine_volatility20"),
            "engine_vwap_distance": features.get("engine_vwap_distance"),
            "engine_sector_relative_strength": features.get("engine_sector_relative_strength"),
            "engine_cross_section_rank": features.get("engine_cross_section_rank"),
            "engine_regime": features.get("engine_regime"),
            "engine_signal_score": features.get("engine_signal_score"),
        },
        "component_snapshot": {
            "news_sentiment": components.get("news_sentiment"),
            "global_sentiment": components.get("global_sentiment"),
            "trading_value_component": components.get("trading_value_component"),
            "momentum_component": components.get("momentum_component"),
            "trend_component": components.get("trend_component"),
            "volume_surge_component": components.get("volume_surge_component"),
            "intraday_strength_component": components.get("intraday_strength_component"),
            "theme_boost_component": components.get("theme_boost_component"),
            "sentiment_component": components.get("sentiment_component"),
            "volatility_penalty_component": components.get("volatility_penalty_component"),
            "gap_penalty_component": components.get("gap_penalty_component"),
            "avoid_theme_penalty_component": components.get("avoid_theme_penalty_component"),
        },
        "quant_factor_snapshot": build_factor_snapshot_from_candidate(
            selected,
            tactic_id=str(selected.get("tactical_strategy") or ""),
            playbook=str(selected.get("playbook") or ""),
        ),
        "tactic_suitability": dict(selected.get("tactic_suitability") or {}),
    }


def feature_coverage_summary(row: Dict[str, Any]) -> Dict[str, Any]:
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    if not isinstance(features, dict):
        return {
            "present": 0,
            "total": 0,
            "coverage_ratio": 0.0,
            "quality": "missing",
            "present_keys": [],
            "missing_keys": [],
        }
    interesting_keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_atr14",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    present_keys = [key for key in interesting_keys if features.get(key) not in (None, "")]
    missing_keys = [key for key in interesting_keys if features.get(key) in (None, "")]
    total = len(interesting_keys)
    present = len(present_keys)
    ratio = float(present) / float(total) if total else 0.0
    if ratio >= 0.75:
        quality = "strong"
    elif ratio >= 0.5:
        quality = "partial"
    else:
        quality = "weak"
    return {
        "present": int(present),
        "total": int(total),
        "coverage_ratio": float(ratio),
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
    }


def compact_feature_snapshot(row: Dict[str, Any]) -> Dict[str, Any]:
    features = row.get("features") if isinstance(row.get("features"), dict) else {}
    if not isinstance(features, dict):
        return {}
    return {
        "skill_quote_price": features.get("skill_quote_price"),
        "quote_trading_value": features.get("quote_trading_value"),
        "quote_volume": features.get("quote_volume"),
        "quote_best_bid": features.get("quote_best_bid"),
        "quote_best_ask": features.get("quote_best_ask"),
        "quote_spread_bps": features.get("quote_spread_bps"),
        "intraday_change_pct": features.get("intraday_change_pct"),
        "entry_compatibility_score": features.get("entry_compatibility_score"),
        "compatibility_bias": features.get("compatibility_bias"),
        "compatibility_source": features.get("compatibility_source"),
        "compat_vwap_distance_abs": features.get("compat_vwap_distance_abs"),
        "compat_is_below_vwap": features.get("compat_is_below_vwap"),
        "compat_reclaim_proximity": features.get("compat_reclaim_proximity"),
        "compat_volume_ratio": features.get("compat_volume_ratio"),
        "compat_breakout_gap_pct": features.get("compat_breakout_gap_pct"),
        "engine_ma20_gap": features.get("engine_ma20_gap"),
        "engine_close_last": features.get("engine_close_last"),
        "engine_ma60": features.get("engine_ma60"),
        "engine_ma120": features.get("engine_ma120"),
        "engine_adx14": features.get("engine_adx14"),
        "engine_trend_strength": features.get("engine_trend_strength"),
        "engine_atr14": features.get("engine_atr14"),
        "engine_volume_spike20": features.get("engine_volume_spike20"),
        "engine_volatility20": features.get("engine_volatility20"),
        "engine_vwap_distance": features.get("engine_vwap_distance"),
        "engine_sector_relative_strength": features.get("engine_sector_relative_strength"),
        "engine_cross_section_rank": features.get("engine_cross_section_rank"),
        "engine_regime": features.get("engine_regime"),
        "engine_signal_score": features.get("engine_signal_score"),
    }


def ranking_table_rows(rows: List[Dict[str, Any]], *, max_rows: int = 5) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(list(rows or [])[: max(0, int(max_rows))], start=1):
        candidate = row.get("candidate") if isinstance(row.get("candidate"), dict) else {}
        out.append(
            {
                "rank": int(idx),
                "symbol": str(row.get("symbol") or ""),
                "score_total": float(to_float(row.get("score_total") or row.get("score"))),
                "score_breakdown": dict(row.get("score_breakdown") or {}),
                "sources": list(candidate.get("sources") or [])[:8],
                "source_scores": dict(candidate.get("source_scores") or {}),
                "candidate_source": str(candidate.get("source_why") or ""),
                "rank_score": float(to_float(candidate.get("rank_score"))),
                "universe_score": float(to_float(candidate.get("universe_score"))),
                "risk_score": float(to_float(row.get("risk_score"))),
                "confidence": float(to_float(row.get("confidence"))),
                "bias_adjustment": float(to_float(row.get("bias_adjustment"))),
                "bias_adjustments": list(row.get("bias_adjustments") or []),
                "bias_summary": dict(row.get("bias_summary") or {}),
                "entry_compatibility_score": float(to_float(row.get("entry_compatibility_score"))),
                "compatibility_bias": float(to_float(row.get("compatibility_bias"))),
                "compatibility_components": dict(row.get("compatibility_components") or {}),
                "scanner_chart_fit_score": float(to_float(row.get("scanner_chart_fit_score"))),
                "scanner_chart_fit_authority": str(row.get("scanner_chart_fit_authority") or ""),
                "scanner_chart_fit_components": dict(row.get("scanner_chart_fit_components") or {}),
                "scanner_macro_chart_fit_score": float(to_float(row.get("scanner_macro_chart_fit_score"), 0.5)),
                "scanner_macro_chart_fit_bias": float(to_float(row.get("scanner_macro_chart_fit_bias"))),
                "scanner_macro_chart_fit_authority": str(row.get("scanner_macro_chart_fit_authority") or ""),
                "scanner_macro_chart_fit_components": dict(row.get("scanner_macro_chart_fit_components") or {}),
                "expected_monitor_block_reason": str(row.get("expected_monitor_block_reason") or ""),
                "dominant_block_reason": str(row.get("dominant_block_reason") or ""),
                "dominant_block_reason_ratio": float(to_float(row.get("dominant_block_reason_ratio"))),
                "bias_scale": float(to_float(row.get("bias_scale"))),
                "soft_penalty": float(to_float(row.get("soft_penalty"))),
                "compatibility_score_pre_penalty": float(to_float(row.get("compatibility_score_pre_penalty"))),
                "compatibility_score_post_penalty": float(to_float(row.get("compatibility_score_post_penalty"))),
                "pre_adjust_score_total": float(to_float(row.get("pre_adjust_score_total"))),
                "post_adjust_score_total": float(to_float(row.get("post_adjust_score_total") or row.get("score_total") or row.get("score"))),
                "theme_match": candidate_theme_match(row),
                "feature_coverage": feature_coverage_summary(row),
                "status": "selected" if idx == 1 else "runner_up",
                "exclusion_reason": str(row.get("exclusion_reason") or ""),
                "compact_feature_snapshot": compact_feature_snapshot(row),
                "quant_factor_snapshot": build_factor_snapshot_from_candidate(
                    row,
                    tactic_id=str(row.get("tactical_strategy") or ""),
                    playbook=str(row.get("playbook") or ""),
                ),
                "tactic_suitability": dict(row.get("tactic_suitability") or {}),
            }
        )
    return out
