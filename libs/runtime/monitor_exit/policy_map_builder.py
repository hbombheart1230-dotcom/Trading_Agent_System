from __future__ import annotations

from typing import Any, Dict

from libs.runtime.exit_policy import apply_account_pnl_crosscheck_context
from libs.runtime.monitor_exit.market_enrichment import (
    enrich_exit_policy_with_market_inputs,
    enrich_exit_policy_with_signal_inputs,
)
from libs.runtime.monitor_exit.position_risk import apply_position_entry_risk_to_exit_policy
from libs.runtime.monitor_exit.position_state_enrichment import enrich_exit_policy_with_position_state


def build_monitor_exit_policy_map(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    selected_for_exit: Dict[str, Any],
    features: Dict[str, Any],
    price: float | None,
    peak_price: float,
    exit_policy_base: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(exit_policy_base or {})
    out = enrich_exit_policy_with_position_state(
        state=state,
        symbol=symbol,
        position=position,
        peak_price=peak_price,
        features=features,
        exit_policy_map=out,
    )
    out = enrich_exit_policy_with_market_inputs(
        state=state,
        symbol=symbol,
        selected_for_exit=selected_for_exit,
        features=features,
        price=price,
        exit_policy_map=out,
    )
    out = enrich_exit_policy_with_signal_inputs(
        state=state,
        selected_for_exit=selected_for_exit,
        features=features,
        exit_policy_map=out,
    )
    out = apply_position_entry_risk_to_exit_policy(state, symbol, out)
    return apply_account_pnl_crosscheck_context(
        out,
        position=position,
    )

