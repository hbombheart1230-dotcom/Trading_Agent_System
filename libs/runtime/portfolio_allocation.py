from __future__ import annotations

from typing import Any, Dict, List, Optional


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return bool(default)
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "y", "on"):
        return True
    if s in ("0", "false", "no", "n", "off"):
        return False
    return bool(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _to_ratio(value: Any, *, default: float = 0.0) -> float:
    return _clamp(_as_float(value, default), 0.0, 1.0)


def _normalize_profiles(strategy_profiles: List[Dict[str, Any]]) -> Dict[str, Any]:
    seen = set()
    failures: List[str] = []
    active: List[Dict[str, Any]] = []

    for idx, raw in enumerate(strategy_profiles):
        if not isinstance(raw, dict):
            failures.append(f"profile[{idx}] is not object")
            continue

        strategy_id = str(raw.get("strategy_id") or "").strip()
        if not strategy_id:
            failures.append(f"profile[{idx}] missing strategy_id")
            continue
        if strategy_id in seen:
            failures.append(f"duplicate strategy_id: {strategy_id}")
            continue
        seen.add(strategy_id)

        enabled = _as_bool(raw.get("enabled"), True)
        weight = _as_float(raw.get("weight"), 0.0)
        if weight < 0:
            failures.append(f"profile[{idx}] weight < 0")
            continue
        if not enabled or weight <= 0.0:
            continue

        max_ratio: Optional[float] = None
        if raw.get("max_notional_ratio") is not None:
            max_ratio = _to_ratio(raw.get("max_notional_ratio"), default=1.0)

        active.append(
            {
                "strategy_id": strategy_id,
                "weight": weight,
                "max_notional_ratio": max_ratio,
            }
        )

    return {
        "active_profiles": active,
        "failures": failures,
    }


def allocate_portfolio_budget(
    strategy_profiles: List[Dict[str, Any]],
    *,
    total_notional: float,
    reserve_ratio: float = 0.0,
) -> Dict[str, Any]:
    """M27-1: deterministic multi-strategy portfolio allocation scaffold."""
    total = max(0.0, _as_float(total_notional, 0.0))
    reserve = _to_ratio(reserve_ratio, default=0.0)
    reserve_notional = total * reserve
    allocatable = max(0.0, total - reserve_notional)

    normalized = _normalize_profiles(strategy_profiles)
    active = normalized["active_profiles"]
    failures: List[str] = list(normalized["failures"])

    if not active:
        if not failures:
            failures.append("no active strategy profile")
        return {
            "ok": False,
            "total_notional": total,
            "reserve_ratio": reserve,
            "reserve_notional": reserve_notional,
            "allocatable_notional": allocatable,
            "active_strategy_total": 0,
            "allocation_total": 0.0,
            "unallocated_notional": allocatable,
            "allocations": [],
            "failures": failures,
        }

    weight_sum = sum(max(0.0, _as_float(x.get("weight"), 0.0)) for x in active)
    if weight_sum <= 0.0:
        failures.append("active weight sum <= 0")
        return {
            "ok": False,
            "total_notional": total,
            "reserve_ratio": reserve,
            "reserve_notional": reserve_notional,
            "allocatable_notional": allocatable,
            "active_strategy_total": len(active),
            "allocation_total": 0.0,
            "unallocated_notional": allocatable,
            "allocations": [],
            "failures": failures,
        }

    rows: List[Dict[str, Any]] = []
    for p in active:
        nw = _as_float(p["weight"]) / weight_sum
        target = allocatable * nw
        max_ratio = p.get("max_notional_ratio")
        max_notional = None
        if max_ratio is not None:
            max_notional = allocatable * _to_ratio(max_ratio, default=1.0)
            allocated = min(target, max_notional)
        else:
            allocated = target
        rows.append(
            {
                "strategy_id": p["strategy_id"],
                "weight": _as_float(p["weight"]),
                "normalized_weight": nw,
                "target_notional": target,
                "allocated_notional": allocated,
                "max_notional": max_notional,
            }
        )

    eps = 1e-9
    leftover = max(0.0, allocatable - sum(_as_float(x["allocated_notional"]) for x in rows))
    while leftover > eps:
        redistributable = []
        for row in rows:
            cap = row.get("max_notional")
            allocated = _as_float(row.get("allocated_notional"), 0.0)
            if cap is None or allocated + eps < _as_float(cap, 0.0):
                redistributable.append(row)

        if not redistributable:
            break

        rw_sum = sum(_as_float(x["normalized_weight"], 0.0) for x in redistributable)
        if rw_sum <= eps:
            break

        used = 0.0
        for row in redistributable:
            weight_share = _as_float(row["normalized_weight"], 0.0) / rw_sum
            share = leftover * weight_share
            cap = row.get("max_notional")
            room = share
            if cap is not None:
                room = max(0.0, _as_float(cap, 0.0) - _as_float(row["allocated_notional"], 0.0))
            delta = min(share, room)
            if delta <= 0.0:
                continue
            row["allocated_notional"] = _as_float(row["allocated_notional"], 0.0) + delta
            used += delta

        if used <= eps:
            break
        leftover = max(0.0, leftover - used)

    allocation_total = sum(_as_float(x["allocated_notional"], 0.0) for x in rows)
    out_rows = []
    for row in rows:
        out_rows.append(
            {
                "strategy_id": str(row["strategy_id"]),
                "weight": round(_as_float(row["weight"]), 8),
                "normalized_weight": round(_as_float(row["normalized_weight"]), 8),
                "target_notional": round(_as_float(row["target_notional"]), 8),
                "allocated_notional": round(_as_float(row["allocated_notional"]), 8),
                "max_notional": None
                if row.get("max_notional") is None
                else round(_as_float(row["max_notional"]), 8),
            }
        )

    return {
        "ok": len(failures) == 0,
        "total_notional": round(total, 8),
        "reserve_ratio": round(reserve, 8),
        "reserve_notional": round(reserve_notional, 8),
        "allocatable_notional": round(allocatable, 8),
        "active_strategy_total": len(active),
        "allocation_total": round(allocation_total, 8),
        "unallocated_notional": round(max(0.0, allocatable - allocation_total), 8),
        "allocations": out_rows,
        "failures": failures,
    }
