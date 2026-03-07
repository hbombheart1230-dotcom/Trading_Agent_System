from __future__ import annotations

from typing import Any, Dict


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clip(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    x = float(v)
    if x < lo:
        return float(lo)
    if x > hi:
        return float(hi)
    return x


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return bool(default)
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def build_sizing_risk_context(
    *,
    risk_context: Dict[str, Any] | None,
    policy: Dict[str, Any] | None,
    portfolio: Dict[str, Any] | None,
    regime: str,
    volatility20: float,
) -> Dict[str, Any]:
    rc = dict(risk_context or {})
    pol = dict(policy or {})
    pf = dict(portfolio or {})

    if not str(rc.get("regime") or "").strip():
        rc["regime"] = str(regime or "unknown").strip().lower() or "unknown"

    if rc.get("volatility_percentile") is None:
        vol_ref = max(1e-9, _to_float(pol.get("volatility_percentile_ref"), 0.20))
        rc["volatility_percentile"] = _clip(_to_float(volatility20, 0.0) / vol_ref, 0.0, 1.0)

    if rc.get("portfolio_exposure") is None:
        exposure = _to_float(
            pf.get("exposure_ratio", pf.get("portfolio_exposure", pol.get("portfolio_exposure", 0.0))),
            0.0,
        )
        rc["portfolio_exposure"] = _clip(exposure, 0.0, 1.0)

    if rc.get("correlation_bucket") is None:
        rc["correlation_bucket"] = str(pol.get("correlation_bucket") or "medium").strip().lower() or "medium"

    if rc.get("daily_loss_state") is None:
        daily_pnl = _to_float(rc.get("daily_pnl_ratio", pf.get("daily_pnl_ratio", 0.0)), 0.0)
        loss_cut = _to_float(pol.get("daily_loss_state_threshold"), -0.01)
        rc["daily_loss_state"] = bool(daily_pnl <= loss_cut)

    if rc.get("degrade_mode") is None:
        rc["degrade_mode"] = _to_bool(
            rc.get("safe_degrade_mode", pol.get("degrade_mode", pol.get("safe_degrade_mode", False))),
            False,
        )

    return rc
