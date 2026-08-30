from __future__ import annotations

from typing import Any, Mapping

from .contracts import (
    BTC_WOORI,
    MAX_SIGNAL_AGE_SEC,
    Q10_INDEX,
    Q10_INDEX_SYMBOLS,
    Q10_SEMICONDUCTOR,
    Q10_TARGET_SYMBOLS,
    Q12_SYMBOL,
)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fresh(signal_epoch: int, now_epoch: int) -> bool:
    age = int(now_epoch) - int(signal_epoch)
    return 0 <= age <= MAX_SIGNAL_AGE_SEC


def _latest_fresh_point(
    points: Mapping[str, Any], *, now_epoch: int
) -> tuple[str, dict[str, Any]]:
    choices = []
    for label in ("09:03", "09:05", "09:10"):
        point = _mapping(points.get(label))
        epoch = int(point.get("ts") or 0)
        if point.get("status") == "OBSERVED" and epoch > 0 and _fresh(epoch, now_epoch):
            choices.append((epoch, label, point))
    if not choices:
        return "", {}
    _epoch, label, point = max(choices, key=lambda item: item[0])
    return label, point


def build_q12_candidate(
    payload: Mapping[str, Any], *, now_epoch: int
) -> dict[str, Any] | None:
    features = _mapping(payload.get("features"))
    btc = _mapping(features.get("btc_0855"))
    daily = _mapping(features.get("btc_daily_context"))
    opening = _mapping(features.get("woori_opening"))
    methods = _mapping(features.get("entry_methods"))
    btc_return = _number(btc.get("return_24h_pct"))
    surge = str(daily.get("surge_state") or "")
    breakout = str(daily.get("breakout_state") or "")
    opening_gap = _number(opening.get("opening_gap_pct"))
    fixed_context_pass = bool(
        btc.get("status") == "OBSERVED"
        and daily.get("status") == "OBSERVED"
        and btc_return is not None
        and btc_return >= 4.0
        and surge == "FIRST_SURGE"
        and breakout in {"20D_BREAKOUT", "60D_BREAKOUT", "ATH_BREAKOUT"}
        and opening_gap is not None
        and opening_gap < 10.0
    )
    if not fixed_context_pass:
        return None
    eligible_methods = []
    for method in ("09:03", "09:05"):
        row = _mapping(methods.get(method))
        epoch = int(row.get("entry_epoch") or 0)
        if (
            row.get("status") == "OBSERVED"
            and row.get("local_confirmation") is True
            and epoch > 0
            and _fresh(epoch, now_epoch)
        ):
            eligible_methods.append((epoch, method, row))
    if not eligible_methods:
        return None
    epoch, method, local = max(eligible_methods, key=lambda item: item[0])
    volume_ratio = _number(local.get("volume_ratio")) or 0.0
    score = float(btc_return) + min(3.0, max(0.0, volume_ratio - 1.0))
    return {
        "lane_id": BTC_WOORI,
        "symbol": Q12_SYMBOL,
        "name": "Woori Technology Investment",
        "score": round(score, 6),
        "signal_epoch": epoch,
        "signal_id": f"Q12_{payload.get('day')}_{method}",
        "price": _number(local.get("entry_price")),
        "horizon": "intraday",
        "evidence": {
            "contract_id": payload.get("contract_id"),
            "entry_method": method,
            "btc_0855_return_24h_pct": btc_return,
            "surge_state": surge,
            "breakout_state": breakout,
            "woori_opening_gap_pct": opening_gap,
            "local_confirmation": True,
            "volume_ratio": volume_ratio,
        },
    }


def _expected_rows(payload: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("target") or ""): dict(row)
        for row in list(payload.get("rows") or [])
        if isinstance(row, Mapping) and row.get("target")
    }


def _direction(state: str) -> int:
    if state in {"STRONG_POSITIVE", "POSITIVE", "STRONG_RISK_ON", "RISK_ON"}:
        return 1
    if state in {"STRONG_NEGATIVE", "NEGATIVE", "STRONG_RISK_OFF", "RISK_OFF"}:
        return -1
    return 0


def build_q10_semiconductor_candidate(
    *,
    preopen: Mapping[str, Any],
    reactions: Mapping[str, Any],
    expected_actual: Mapping[str, Any],
    now_epoch: int,
) -> dict[str, Any] | None:
    if preopen.get("capture_status") != "CAPTURED":
        return None
    signals = _mapping(preopen.get("signals"))
    expected = _expected_rows(expected_actual)
    targets = _mapping(reactions.get("targets"))
    candidates = []
    for key in ("sk_hynix", "samsung"):
        signal = _mapping(signals.get(key))
        state = str(signal.get("state") or "NEUTRAL")
        if _direction(state) <= 0 or signal.get("confidence") not in {"MEDIUM", "HIGH"}:
            continue
        expected_row = _mapping(expected.get(key))
        if bool(expected_row.get("excluded_from_pure_signal_comparison")):
            continue
        reaction = _mapping(targets.get(key))
        opening = _mapping(_mapping(reaction.get("points")).get("09:00"))
        label, point = _latest_fresh_point(_mapping(reaction.get("points")), now_epoch=now_epoch)
        opening_price = _number(opening.get("price"))
        point_price = _number(point.get("price"))
        if not label or opening_price is None or point_price is None or point_price <= opening_price:
            continue
        response_pct = (point_price / opening_price - 1.0) * 100.0
        signal_score = abs(_number(signal.get("score")) or 0.0)
        confidence_score = _number(signal.get("confidence_score")) or 0.0
        extension = _mapping(signals.get("hynix_extension")) if key == "sk_hynix" else {}
        extension_penalty = 0.5 if extension.get("state") == "EXTENDED" else 0.0
        score = signal_score + confidence_score + max(0.0, response_pct) - extension_penalty
        candidates.append(
            {
                "lane_id": Q10_SEMICONDUCTOR,
                "symbol": Q10_TARGET_SYMBOLS[key],
                "name": "SK Hynix" if key == "sk_hynix" else "Samsung Electronics",
                "score": round(score, 6),
                "signal_epoch": int(point.get("ts") or 0),
                "signal_id": f"Q10_SEMI_{preopen.get('day')}_{key}_{label}",
                "price": point_price,
                "horizon": "intraday",
                "evidence": {
                    "target": key,
                    "expected_state": state,
                    "confidence": signal.get("confidence"),
                    "confidence_score": confidence_score,
                    "reaction_checkpoint": label,
                    "opening_to_checkpoint_pct": round(response_pct, 6),
                    "reaction_state": expected_row.get("reaction_state"),
                    "extension_state": extension.get("state"),
                },
            }
        )
    return max(candidates, key=lambda row: float(row["score"])) if candidates else None


def build_q10_index_candidate(
    *,
    preopen: Mapping[str, Any],
    reactions: Mapping[str, Any],
    expected_actual: Mapping[str, Any],
    now_epoch: int,
) -> dict[str, Any] | None:
    if preopen.get("capture_status") != "CAPTURED":
        return None
    market_signal = _mapping(_mapping(preopen.get("signals")).get("korea_market"))
    state = str(market_signal.get("state") or "NEUTRAL")
    direction = _direction(state)
    if direction == 0 or market_signal.get("evidence_status") == "INSUFFICIENT_EVIDENCE":
        return None
    targets = _mapping(reactions.get("targets"))
    expected = _expected_rows(expected_actual)
    candidates = []
    for key in ("kospi", "kosdaq"):
        reaction = _mapping(targets.get(key))
        points = _mapping(reaction.get("points"))
        opening = _mapping(points.get("09:00"))
        label, point = _latest_fresh_point(points, now_epoch=now_epoch)
        opening_price = _number(opening.get("price"))
        point_price = _number(point.get("price"))
        if not label or opening_price is None or point_price is None:
            continue
        response_pct = (point_price / opening_price - 1.0) * 100.0
        if direction * response_pct <= 0.0:
            continue
        product = Q10_INDEX_SYMBOLS[(key, direction)]
        expected_row = _mapping(expected.get(key))
        score = abs(_number(market_signal.get("score")) or 0.0) + abs(response_pct)
        candidates.append(
            {
                "lane_id": Q10_INDEX,
                "symbol": product["symbol"],
                "name": product["name"],
                "score": round(score, 6),
                "signal_epoch": int(point.get("ts") or 0),
                "signal_id": f"Q10_INDEX_{preopen.get('day')}_{key}_{label}",
                "price": None,
                "horizon": "intraday",
                "evidence": {
                    "target": key,
                    "expected_state": state,
                    "market_score": market_signal.get("score"),
                    "market_evidence_status": market_signal.get("evidence_status"),
                    "reaction_checkpoint": label,
                    "opening_to_checkpoint_pct": round(response_pct, 6),
                    "reaction_state": expected_row.get("reaction_state"),
                    "exposure_direction": "LONG" if direction > 0 else "INVERSE",
                },
            }
        )
    return max(candidates, key=lambda row: float(row["score"])) if candidates else None


__all__ = [
    "build_q10_index_candidate",
    "build_q10_semiconductor_candidate",
    "build_q12_candidate",
]
