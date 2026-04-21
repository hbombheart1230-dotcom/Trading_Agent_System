from __future__ import annotations

from typing import Any, Dict, List

from libs.runtime.scanner_memory_bias_reasons import build_scanner_memory_bias_reasons
from libs.runtime.scanner_memory_bias_rules import build_scanner_memory_bias_rules


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def build_scanner_memory_bias(
    *,
    commander_memory_policy: Dict[str, Any],
    memory_packets: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    policy = dict(commander_memory_policy or {})
    if not bool(policy.get("scanner_bias_enabled")):
        return {
            "enabled": False,
            "bias_source": "commander_memory_bias.v1",
            "active_layers": [],
            "source_weight_delta": {},
            "feature_bias": {},
            "symbol_adjustments": {},
            "confidence_caps": {},
            "reason": ["scanner_bias_disabled"],
        }
    daily_packet = dict(memory_packets.get("daily_strategy_memory") or {})
    symbol_packet = dict(memory_packets.get("symbol_memory_packet") or {})
    rules = build_scanner_memory_bias_rules(
        commander_memory_policy=policy,
        daily_packet=daily_packet,
        symbol_packet=symbol_packet,
    )
    reasons = build_scanner_memory_bias_reasons(
        commander_memory_policy=policy,
        daily_packet=daily_packet,
        symbol_packet=symbol_packet,
    )
    feature_bias = dict(rules.get("feature_bias") or {})
    return {
        "enabled": True,
        "bias_source": "commander_memory_bias.v1",
        "active_layers": [str(x or "") for x in list(policy.get("active_layers") or []) if str(x or "").strip()],
        "source_weight_delta": {str(k): float(v) for k, v in dict(rules.get("source_weight_delta") or {}).items()},
        "feature_bias": {
            "prefer_shallow_pullback_candidates": bool(feature_bias.get("prefer_shallow_pullback_candidates")),
            "penalize_overextended": bool(feature_bias.get("penalize_overextended")),
            "prefer_reclaim_candidates": bool(feature_bias.get("prefer_reclaim_candidates")),
            "prefer_volume_confirmation": bool(feature_bias.get("prefer_volume_confirmation")),
        },
        "symbol_adjustments": dict(rules.get("symbol_adjustments") or {}),
        "confidence_caps": {"max_confidence": 0.88},
        "reason": reasons,
    }


def summarize_scanner_memory_bias(memory_bias: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(memory_bias or {})
    return {
        "enabled": bool(row.get("enabled")),
        "active_layers": [str(x or "") for x in list(row.get("active_layers") or []) if str(x or "").strip()][:4],
        "source_delta_keys": [str(x or "") for x in list((row.get("source_weight_delta") or {}).keys())[:4]],
        "symbol_adjustment_count": len(dict(row.get("symbol_adjustments") or {})),
        "reason": [str(x or "") for x in list(row.get("reason") or [])[:4] if str(x or "").strip()],
        "bias_source": str(row.get("bias_source") or ""),
    }


def compute_scanner_memory_bias_adjustment(
    *,
    symbol: str,
    candidate_sources: List[str],
    memory_bias: Dict[str, Any],
) -> Dict[str, Any]:
    row = dict(memory_bias or {})
    if not bool(row.get("enabled")):
        return {
            "bias_adjustment": 0.0,
            "source_delta": 0.0,
            "symbol_delta": 0.0,
            "adjustments": [],
            "summary": summarize_scanner_memory_bias(row),
        }
    source_delta = 0.0
    adjustments: List[Dict[str, Any]] = []
    source_weight_delta = dict(row.get("source_weight_delta") or {})
    for source in list(dict.fromkeys([str(x or "").strip() for x in list(candidate_sources or []) if str(x or "").strip()])):
        delta = float(source_weight_delta.get(source) or 0.0)
        if abs(delta) > 1e-9:
            source_delta += delta
            adjustments.append({"kind": "source", "source": source, "delta": float(delta)})
    symbol_delta = 0.0
    symbol_rule = dict((row.get("symbol_adjustments") or {}).get(str(symbol or "").strip()) or {})
    if symbol_rule:
        symbol_delta = float(symbol_rule.get("delta") or 0.0)
        if abs(symbol_delta) > 1e-9:
            adjustments.append(
                {
                    "kind": "symbol",
                    "symbol": str(symbol or "").strip(),
                    "delta": float(symbol_delta),
                    "reason": str(symbol_rule.get("reason") or ""),
                }
            )
    total = _clamp(source_delta + symbol_delta, -0.03, 0.03)
    return {
        "bias_adjustment": float(total),
        "source_delta": float(source_delta),
        "symbol_delta": float(symbol_delta),
        "adjustments": adjustments[:6],
        "summary": summarize_scanner_memory_bias(row),
    }
