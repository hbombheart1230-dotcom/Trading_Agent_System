from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from .contracts import RISK_OFF_RAILS


KST = timezone(timedelta(hours=9))


def _number(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _factors(row: Mapping[str, Any]) -> Mapping[str, Any]:
    snapshot = row.get("quant_factor_snapshot")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    factors = snapshot.get("factors")
    return factors if isinstance(factors, Mapping) else {}


def _market_rail(row: Mapping[str, Any]) -> str:
    observation = row.get("entry_lane_observation")
    observation = observation if isinstance(observation, Mapping) else {}
    return str(observation.get("market_regime_rail") or "").strip()


def _baseline_epoch(row: Mapping[str, Any]) -> int:
    base = row.get("shadow_forward_base")
    base = base if isinstance(base, Mapping) else {}
    return int(_number(base.get("baseline_epoch")) or 0)


def opening_risk_off_reclaim(row: Mapping[str, Any]) -> bool:
    factors = _factors(row)
    epoch = _baseline_epoch(row)
    if epoch <= 0:
        return False
    dt = datetime.fromtimestamp(epoch, tz=KST)
    minute = dt.hour * 60 + dt.minute
    progress = _number(factors.get("vwap_reclaim_progress"))
    volume = _number(factors.get("volume_ratio"))
    return bool(
        9 * 60 + 5 <= minute <= 10 * 60
        and _market_rail(row) in RISK_OFF_RAILS
        and progress is not None
        and progress >= 0.95
        and volume is not None
        and volume >= 0.80
    )


def confirmed_volume_breakout(row: Mapping[str, Any]) -> bool:
    factors = _factors(row)
    volume = _number(factors.get("volume_ratio"))
    vwap_distance = _number(factors.get("vwap_distance_pct"))
    return bool(
        factors.get("breakout_ok") is True
        and volume is not None
        and volume >= 1.20
        and vwap_distance is not None
        and vwap_distance >= 0.0
    )


def confirmed_vwap_pullback(row: Mapping[str, Any]) -> bool:
    factors = _factors(row)
    volume = _number(factors.get("volume_ratio"))
    return bool(
        factors.get("reclaim_ok") is True
        and factors.get("pullback_ok") is True
        and volume is not None
        and volume >= 0.80
    )


def matched_hypotheses(row: Mapping[str, Any]) -> list[str]:
    matched: list[str] = []
    if opening_risk_off_reclaim(row):
        matched.append("H1_OPENING_RISK_OFF_RECLAIM")
    if confirmed_volume_breakout(row):
        matched.append("H2_CONFIRMED_VOLUME_BREAKOUT")
    if confirmed_vwap_pullback(row):
        matched.append("H3_CONFIRMED_VWAP_PULLBACK")
    return matched
