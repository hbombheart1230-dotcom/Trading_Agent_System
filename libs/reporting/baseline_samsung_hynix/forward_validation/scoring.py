from __future__ import annotations

from typing import Any, Mapping

from .contracts import THRESHOLDS


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _direction(value: float) -> int:
    return 1 if value > 0 else -1 if value < 0 else 0


def _semiconductor_base(sox_pct: float) -> float:
    if sox_pct >= THRESHOLDS["sox_strong_positive_pct"]:
        return 2.0
    if sox_pct >= THRESHOLDS["sox_positive_pct"]:
        return 1.0
    if sox_pct <= THRESHOLDS["sox_strong_negative_pct"]:
        return -2.0
    if sox_pct <= THRESHOLDS["sox_negative_pct"]:
        return -1.0
    return 0.0


def _semiconductor_state(score: float) -> str:
    if score >= 1.75:
        return "STRONG_POSITIVE"
    if score >= 0.75:
        return "POSITIVE"
    if score <= -1.75:
        return "STRONG_NEGATIVE"
    if score <= -0.75:
        return "NEGATIVE"
    return "NEUTRAL"


def score_semiconductor_signal(
    inputs: Mapping[str, Any],
    *,
    samsung: bool = False,
) -> dict[str, Any]:
    sox_pct = _number(inputs.get("sox_return_pct"))
    if sox_pct is None:
        return {
            "state": "NEUTRAL",
            "score": None,
            "confidence": "INSUFFICIENT_EVIDENCE",
            "reasons": ["sox_return_missing"],
            "samsung_sox_sensitivity": THRESHOLDS["samsung_sox_sensitivity"] if samsung else 1.0,
        }
    sensitivity = THRESHOLDS["samsung_sox_sensitivity"] if samsung else 1.0
    base = _semiconductor_base(sox_pct) * sensitivity
    confidence_score = 0.50
    reasons = [f"sox_base={base:.2f}"]
    direction = _direction(base)
    for key in ("nvidia_return_pct", "micron_return_pct", "hynix_adr_return_pct"):
        value = _number(inputs.get(key))
        if direction and value is not None and _direction(value) == direction:
            bonus = THRESHOLDS["confirming_equity_bonus"]
            confidence_score += bonus
            reasons.append(f"{key}_confidence={bonus:+.2f}")
    futures = _number(inputs.get("nasdaq100_futures_0850_return_pct"))
    if direction and futures is not None and _direction(futures) == -direction:
        penalty = THRESHOLDS["opposing_nasdaq_futures_penalty"]
        confidence_score -= penalty
        reasons.append(f"nasdaq_futures_confidence={-penalty:+.2f}")
    usdkrw = _number(inputs.get("usdkrw_0850_change_pct"))
    adverse = bool(
        direction > 0 and usdkrw is not None and usdkrw >= THRESHOLDS["usdkrw_adverse_move_pct"]
        or direction < 0 and usdkrw is not None and usdkrw <= -THRESHOLDS["usdkrw_adverse_move_pct"]
    )
    if adverse:
        penalty = THRESHOLDS["usdkrw_adverse_penalty"]
        confidence_score -= penalty
        reasons.append(f"usdkrw_confidence={-penalty:+.2f}")
    available_confirmers = sum(
        _number(inputs.get(key)) is not None
        for key in (
            "nvidia_return_pct",
            "micron_return_pct",
            "hynix_adr_return_pct",
            "nasdaq100_futures_0850_return_pct",
            "usdkrw_0850_change_pct",
        )
    )
    confidence_score = max(0.0, min(1.0, confidence_score))
    return {
        "state": _semiconductor_state(base),
        "score": round(base, 4),
        "confidence_score": round(confidence_score, 4),
        "confidence": (
            "INSUFFICIENT_EVIDENCE" if available_confirmers == 0 else
            "HIGH" if confidence_score >= 0.75 else
            "MEDIUM" if confidence_score >= 0.40 else "LOW"
        ),
        "reasons": reasons,
        "samsung_sox_sensitivity": sensitivity,
    }


def classify_hynix_extension(inputs: Mapping[str, Any]) -> dict[str, Any]:
    value = _number(inputs.get("hynix_3d_cumulative_return_pct"))
    threshold = THRESHOLDS["hynix_extended_3d_abs_pct"]
    if value is None:
        return {"state": "UNKNOWN", "extended": None, "direction": "UNKNOWN", "return_pct": None, "threshold_abs_pct": threshold}
    extended = abs(value) >= threshold
    return {
        "state": "EXTENDED" if extended else "FIRST_MOVE",
        "extended": extended,
        "direction": "UP" if value > 0 else "DOWN" if value < 0 else "FLAT",
        "return_pct": round(value, 4),
        "threshold_abs_pct": threshold,
    }


def score_korea_market_state(inputs: Mapping[str, Any]) -> dict[str, Any]:
    score = 0.0
    components: dict[str, float] = {}

    def add_directional(key: str, threshold: float, weight: float = 1.0, invert: bool = False) -> None:
        nonlocal score
        value = _number(inputs.get(key))
        if value is None or abs(value) < threshold:
            return
        contribution = weight * _direction(value) * (-1 if invert else 1)
        components[key] = contribution
        score += contribution

    add_directional("nasdaq_return_pct", THRESHOLDS["market_equity_move_pct"])
    add_directional("sp500_return_pct", THRESHOLDS["market_equity_move_pct"])
    add_directional("sox_return_pct", THRESHOLDS["market_sox_move_pct"])
    add_directional("nasdaq100_futures_0850_return_pct", THRESHOLDS["market_futures_move_pct"])
    add_directional("sp500_futures_0850_return_pct", THRESHOLDS["market_futures_move_pct"])
    add_directional("usdkrw_0850_change_pct", THRESHOLDS["market_usdkrw_move_pct"], invert=True)
    add_directional("us10y_yield_change", THRESHOLDS["market_us10y_delta"], weight=0.5, invert=True)
    add_directional("vix_change_pct", THRESHOLDS["market_vix_move_pct"], invert=True)
    strong = THRESHOLDS["market_strong_risk_on_score"]
    normal = THRESHOLDS["market_risk_on_score"]
    state = (
        "STRONG_RISK_ON" if score >= strong else
        "RISK_ON" if score >= normal else
        "STRONG_RISK_OFF" if score <= -strong else
        "RISK_OFF" if score <= -normal else
        "NEUTRAL"
    )
    required = (
        "nasdaq_return_pct", "sp500_return_pct", "sox_return_pct",
        "nasdaq100_futures_0850_return_pct", "sp500_futures_0850_return_pct",
        "usdkrw_0850_change_pct", "us10y_yield_change", "vix_change_pct",
    )
    available = sum(_number(inputs.get(key)) is not None for key in required)
    return {
        "state": state,
        "score": round(score, 4),
        "components": components,
        "available_input_count": available,
        "required_input_count": len(required),
        "evidence_status": "COMPLETE" if available == len(required) else "PARTIAL" if available else "INSUFFICIENT_EVIDENCE",
    }
