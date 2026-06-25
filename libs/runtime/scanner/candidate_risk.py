from __future__ import annotations

from typing import Any, Dict, Mapping


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _first_number(row: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _optional_float(row.get(key))
        if value is not None:
            return value
    return None


def resolve_candidate_base_risk(
    *,
    candidate: Mapping[str, Any] | None = None,
    scanner_row: Mapping[str, Any] | None = None,
    features: Mapping[str, Any] | None = None,
    quote_metrics: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Resolve candidate base risk without using symbol identity.

    Explicit upstream risk remains authoritative. The fallback is deliberately
    modest because Scanner applies separate volatility, gap, news, regime, and
    repeat-symbol penalties after this base value.
    """

    candidate = candidate or {}
    scanner_row = scanner_row or {}
    features = features or {}
    quote_metrics = quote_metrics or {}

    explicit = _optional_float(scanner_row.get("risk_score"))
    explicit_source = "scanner_row"
    if explicit is None:
        explicit = _optional_float(candidate.get("risk_score"))
        explicit_source = "candidate"
    if explicit is not None:
        return {
            "risk_score": _clamp(explicit),
            "source": explicit_source,
            "components": {"explicit_risk_score": _clamp(explicit)},
            "missing_inputs": [],
        }

    close = _first_number(features, "close_last", "engine_close_last")
    atr = _first_number(features, "atr14", "engine_atr14")
    volatility = _first_number(
        features,
        "volatility20",
        "engine_volatility20",
        "realized_volatility",
        "engine_realized_volatility",
    )
    drawdown = _first_number(features, "rolling_drawdown20", "engine_rolling_drawdown20")
    gap = _first_number(features, "gap_pct", "engine_gap_pct")
    spread_bps = _optional_float(quote_metrics.get("spread_bps"))
    volume = _optional_float(quote_metrics.get("volume"))
    trading_value = _optional_float(quote_metrics.get("trading_value"))

    missing_inputs = []
    if close is None or close <= 0.0 or atr is None:
        atr_ratio = 0.0
        missing_inputs.append("atr_ratio")
    else:
        atr_ratio = abs(atr) / close
    if volatility is None:
        volatility = 0.0
        missing_inputs.append("volatility")
    if drawdown is None:
        drawdown = 0.0
        missing_inputs.append("drawdown")
    if gap is None:
        gap = 0.0
        missing_inputs.append("gap")
    if spread_bps is None:
        spread_bps = 0.0
        missing_inputs.append("spread")
    if volume is None or volume <= 0.0:
        missing_inputs.append("volume")
    if trading_value is None or trading_value <= 0.0:
        missing_inputs.append("trading_value")

    components = {
        "anchor": 0.12,
        "atr_ratio": 0.18 * _clamp(atr_ratio / 0.04),
        "drawdown": 0.12 * _clamp(abs(drawdown) / 0.08),
        "spread": 0.08 * _clamp(max(0.0, spread_bps) / 50.0),
        "volatility": 0.08 * _clamp(abs(volatility) / 0.08),
        "gap": 0.05 * _clamp(abs(gap) / 0.10),
        "missing_data": min(0.18, 0.03 * len(missing_inputs)),
    }
    risk_score = _clamp(sum(components.values()))
    return {
        "risk_score": risk_score,
        "source": "market_data_fallback",
        "components": {key: round(value, 8) for key, value in components.items()},
        "missing_inputs": missing_inputs,
    }
