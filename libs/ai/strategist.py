from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Protocol, runtime_checkable


@dataclass
class StrategyInput:
    symbol: str
    market_snapshot: Dict[str, Any]
    portfolio_snapshot: Dict[str, Any]
    risk_context: Dict[str, Any]


@dataclass
class StrategyDecision:
    """Pure decision (no execution)."""
    intent: Dict[str, Any]
    rationale: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Strategist(Protocol):
    def decide(self, x: StrategyInput) -> StrategyDecision:  # pragma: no cover
        ...


class RuleStrategist:
    """M12 placeholder: deterministic rules (no LLM)."""

    def decide(self, x: StrategyInput) -> StrategyDecision:
        price = x.market_snapshot.get("price")
        cash = x.portfolio_snapshot.get("cash", 0)

        if cash > 1_000_000 and price is not None:
            intent = {
                "action": "BUY",
                "symbol": x.symbol,
                "qty": 1,
                "price": None,
                "order_type": "market",
                "order_api_id": "ORDER_SUBMIT",
            }
            return StrategyDecision(intent=intent, rationale="rule:cash_and_price_ok")

        return StrategyDecision(intent={"action": "NOOP", "reason": "conditions_not_met"}, rationale="rule:no_trade")


class BlockedStrategist:
    """Explicit NOOP strategist used when AI strategist mode is required but unavailable."""

    def __init__(self, *, reason: str, error: str = "") -> None:
        self.reason = str(reason or "strategist_llm_required")
        self.error = str(error or "").strip()
        self.model = ""

    def decide(self, x: StrategyInput) -> StrategyDecision:
        rationale = self.reason
        if self.error:
            rationale = f"{self.reason}:{self.error}"
        return StrategyDecision(
            intent={"action": "NOOP", "reason": self.reason},
            rationale=rationale,
            meta={
                "status": "error",
                "error": self.error or self.reason,
                "error_type": "StrategistBlocked",
                "attempts": 0,
                "strict_required": True,
                "blocked_reason": self.reason,
            },
        )


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _extract_held_qty(portfolio_snapshot: Dict[str, Any], symbol: str) -> int:
    sym = _norm_symbol(symbol)
    rows = portfolio_snapshot.get("positions")
    if not isinstance(rows, list):
        return 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _norm_symbol(row.get("symbol") or row.get("code")) != sym:
            continue
        try:
            qty = int(float(row.get("qty") or 0))
        except Exception:
            qty = 0
        if qty > 0:
            return qty
    return 0


def _intent_from_v1_decision(raw: Dict[str, Any], *, default_symbol: str, default_price: Any) -> Dict[str, Any]:
    action = str(raw.get("action") or "NOOP").strip().upper()
    symbol = _norm_symbol(raw.get("symbol") or default_symbol)
    qty = 0
    try:
        qty = max(0, int(float(raw.get("qty") or 0)))
    except Exception:
        qty = 0
    rationale = str(raw.get("rationale") or "").strip()

    if action in ("BUY", "SELL"):
        return {
            "action": action,
            "symbol": symbol,
            "qty": qty,
            "price": default_price,
            "order_type": "market",
            "order_api_id": "ORDER_SUBMIT",
            "rationale": rationale or f"strategy_v1_{action.lower()}",
        }
    return {
        "action": "NOOP",
        "reason": "strategy_v1_noop",
        "rationale": rationale or "strategy_v1_noop",
    }


class StrategyV1Strategist:
    """Bridge that runs deterministic strategy-v1 modules through Strategist protocol."""

    def __init__(self, *, policy: Dict[str, Any] | None = None) -> None:
        self.policy = dict(policy or {})

    def decide(self, x: StrategyInput) -> StrategyDecision:
        from libs.strategies.contracts import StrategyInput as V1Input
        from libs.strategies.v1.registry import build_strategy_v1, resolve_strategy_v1_name

        llm_context = (
            x.market_snapshot.get("llm_context")
            if isinstance(x.market_snapshot.get("llm_context"), dict)
            else {}
        )
        technical = llm_context.get("technical") if isinstance(llm_context.get("technical"), dict) else {}
        news = llm_context.get("news") if isinstance(llm_context.get("news"), dict) else {}
        regime = str(technical.get("regime") or "unknown").strip().lower() or "unknown"

        strategy_name = resolve_strategy_v1_name(policy=self.policy, llm_context=llm_context)
        strategy, canonical_name = build_strategy_v1(name=strategy_name, policy=self.policy)

        held_qty = _extract_held_qty(x.portfolio_snapshot, x.symbol)
        v1_input = V1Input(
            symbol=_norm_symbol(x.symbol),
            regime=regime,
            technical=dict(technical),
            news=dict(news),
            portfolio=dict(x.portfolio_snapshot or {}),
            policy=dict(self.policy),
            risk_context=dict(x.risk_context or {}),
        )
        v1_decision = strategy.decide(
            v1_input,
            price=_to_float(x.market_snapshot.get("price"), 0.0) or None,
            cash=_to_float(x.portfolio_snapshot.get("cash"), 0.0),
            held_qty=int(held_qty),
        ).to_dict()
        intent = _intent_from_v1_decision(
            v1_decision,
            default_symbol=x.symbol,
            default_price=x.market_snapshot.get("price"),
        )

        meta = {
            "strategy_v1_name": str(canonical_name),
            "strategy_v1_decision": dict(v1_decision),
            "evidence": dict(v1_decision.get("evidence") or {}),
            "invalidation": dict(v1_decision.get("invalidation") or {}),
            "sizing_inputs": dict(v1_decision.get("sizing_inputs") or {}),
            "entry_conditions": list(v1_decision.get("entry_conditions") or []),
            "exit_conditions": list(v1_decision.get("exit_conditions") or []),
            "noop_conditions": list(v1_decision.get("noop_conditions") or []),
        }
        return StrategyDecision(
            intent=intent,
            rationale=str(v1_decision.get("rationale") or intent.get("rationale") or ""),
            meta=meta,
        )
