from __future__ import annotations

from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.numeric import to_float


def apply_position_entry_risk_to_exit_policy(
    state: Dict[str, Any],
    symbol: str,
    exit_policy_map: Dict[str, Any],
) -> Dict[str, Any]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    risk_map = (
        persisted.get("position_entry_risk_by_symbol")
        if isinstance(persisted.get("position_entry_risk_by_symbol"), dict)
        else {}
    )
    entry_risk = risk_map.get(normalize_symbol(symbol)) if isinstance(risk_map, dict) else {}
    if not isinstance(entry_risk, dict):
        return exit_policy_map
    entry_stop = to_float(entry_risk.get("stop_loss_pct"))
    if entry_stop <= 0.0:
        return exit_policy_map

    out = dict(exit_policy_map or {})
    current_stop = to_float(out.get("stop_loss_pct"))
    if current_stop <= 0.0 or entry_stop < current_stop:
        out["stop_loss_pct"] = float(entry_stop)
        out["position_entry_risk_applied"] = True
    else:
        out["position_entry_risk_applied"] = False
    out["position_entry_stop_loss_pct"] = float(entry_stop)
    out["position_entry_stop_loss_source"] = str(entry_risk.get("stop_loss_source") or entry_risk.get("source") or "")
    if entry_risk.get("invalidation_price") not in (None, ""):
        out["position_entry_invalidation_price"] = entry_risk.get("invalidation_price")
    if entry_risk.get("raw_structure_stop_loss_pct") not in (None, ""):
        out["position_entry_raw_structure_stop_loss_pct"] = entry_risk.get("raw_structure_stop_loss_pct")
    if entry_risk.get("min_structure_stop_loss_pct") not in (None, ""):
        out["position_entry_min_structure_stop_loss_pct"] = entry_risk.get("min_structure_stop_loss_pct")
    return out

