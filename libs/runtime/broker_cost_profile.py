from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Mapping


DEFAULT_PROFILE_PATH = Path("data/state/broker_cost_profile.json")


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def resolve_broker_cost_profile_path(path: str | os.PathLike[str] | None = None) -> Path:
    raw = path or os.getenv("BROKER_COST_PROFILE_PATH") or str(DEFAULT_PROFILE_PATH)
    return Path(raw)


def load_broker_cost_profile(path: str | os.PathLike[str] | None = None) -> Dict[str, Any]:
    profile_path = resolve_broker_cost_profile_path(path)
    try:
        if not profile_path.exists():
            return {}
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_profile(profile: Mapping[str, Any], path: str | os.PathLike[str] | None = None) -> None:
    profile_path = resolve_broker_cost_profile_path(path)
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = profile_path.with_suffix(profile_path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(dict(profile), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    tmp_path.replace(profile_path)


def build_broker_cost_profile_from_execution_details(
    execution_details: Mapping[str, Any] | None,
    *,
    previous: Mapping[str, Any] | None = None,
    now_epoch: float | None = None,
) -> Dict[str, Any]:
    details = dict(execution_details or {})
    source = str(details.get("pnl_truth_source") or details.get("broker_day_truth_source") or "").strip()
    if source not in {"kiwoom.ka10077", "kiwoom.ka10085"}:
        return {}

    qty = _safe_int(details.get("filled_qty"))
    sell_price = _safe_float(details.get("filled_price"))
    buy_price = _safe_float(details.get("broker_buy_price") or details.get("buy_price") or details.get("avg_price"))
    fee = _safe_float(details.get("broker_fee") or details.get("fee"))
    tax = _safe_float(details.get("broker_tax") or details.get("tax"), 0.0)
    if qty in (None, 0) or sell_price in (None, 0) or buy_price in (None, 0) or fee is None:
        return {}

    buy_notional = float(buy_price) * int(qty)
    sell_notional = float(sell_price) * int(qty)
    gross_notional = buy_notional + sell_notional
    if buy_notional <= 0.0 or sell_notional <= 0.0 or gross_notional <= 0.0:
        return {}

    total_cost = float(fee) + float(tax or 0.0)
    round_trip_cost_pct = total_cost / buy_notional if total_cost >= 0.0 else 0.0
    fee_rate_gross = float(fee) / gross_notional if fee >= 0.0 else 0.0
    tax_rate_sell = float(tax or 0.0) / sell_notional if float(tax or 0.0) >= 0.0 else 0.0

    prev = dict(previous or {})
    prev_count = max(0, int(_safe_int(prev.get("sample_count"), 0) or 0))
    prev_ema = _safe_float(prev.get("ema_round_trip_cost_pct"))
    alpha = 0.35
    ema = round_trip_cost_pct if prev_ema is None else (alpha * round_trip_cost_pct) + ((1.0 - alpha) * float(prev_ema))
    conservative = max(
        round_trip_cost_pct,
        float(ema),
        _safe_float(prev.get("conservative_round_trip_cost_pct"), 0.0) or 0.0,
    )

    return {
        "schema_version": "broker_cost_profile.v1",
        "source": source,
        "updated_epoch": float(now_epoch if now_epoch is not None else time.time()),
        "sample_count": prev_count + 1,
        "last_symbol": str(details.get("symbol") or "").strip(),
        "last_filled_qty": int(qty),
        "last_buy_price": float(buy_price),
        "last_sell_price": float(sell_price),
        "last_fee": float(fee),
        "last_tax": float(tax or 0.0),
        "last_buy_notional": float(buy_notional),
        "last_sell_notional": float(sell_notional),
        "fee_rate_on_gross_notional": float(fee_rate_gross),
        "tax_rate_on_sell_notional": float(tax_rate_sell),
        "last_round_trip_cost_pct": float(round_trip_cost_pct),
        "ema_round_trip_cost_pct": float(ema),
        "conservative_round_trip_cost_pct": float(conservative),
    }


def update_broker_cost_profile_from_execution_details(
    execution_details: Mapping[str, Any] | None,
    *,
    path: str | os.PathLike[str] | None = None,
    now_epoch: float | None = None,
) -> Dict[str, Any]:
    previous = load_broker_cost_profile(path)
    profile = build_broker_cost_profile_from_execution_details(
        execution_details,
        previous=previous,
        now_epoch=now_epoch,
    )
    if profile:
        if not (os.getenv("PYTEST_CURRENT_TEST") and not (path or os.getenv("BROKER_COST_PROFILE_PATH"))):
            _write_profile(profile, path)
    return profile


def apply_broker_cost_profile_to_exit_policy(
    policy: Mapping[str, Any] | None,
    *,
    profile: Mapping[str, Any] | None = None,
    path: str | os.PathLike[str] | None = None,
) -> Dict[str, Any]:
    out = dict(policy or {})
    profile_obj = dict(profile or load_broker_cost_profile(path) or {})
    observed = _safe_float(profile_obj.get("conservative_round_trip_cost_pct"))
    if observed is None or observed <= 0.0:
        return out

    current = _safe_float(out.get("round_trip_cost_floor_pct"), 0.0) or 0.0
    if observed > current:
        out["round_trip_cost_floor_pct"] = float(observed)
    out["cost_aware_profit_floor_enabled"] = True

    buffer_pct = _safe_float(out.get("min_net_profit_buffer_pct"), 0.0) or 0.0
    current_floor = _safe_float(out.get("cost_aware_profit_floor_pct"), 0.0) or 0.0
    observed_floor = float(out.get("round_trip_cost_floor_pct") or observed) + float(buffer_pct)
    if observed_floor > current_floor:
        out["cost_aware_profit_floor_pct"] = float(observed_floor)

    out["broker_cost_profile_source"] = str(profile_obj.get("source") or "")
    out["broker_cost_profile_updated_epoch"] = profile_obj.get("updated_epoch")
    out["broker_cost_profile_sample_count"] = profile_obj.get("sample_count")
    return out


__all__ = [
    "apply_broker_cost_profile_to_exit_policy",
    "build_broker_cost_profile_from_execution_details",
    "load_broker_cost_profile",
    "resolve_broker_cost_profile_path",
    "update_broker_cost_profile_from_execution_details",
]
