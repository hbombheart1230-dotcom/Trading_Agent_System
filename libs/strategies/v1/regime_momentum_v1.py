from __future__ import annotations

from typing import Any, Dict

from libs.runtime.position_sizing import evaluate_position_size
from libs.strategies.contracts import (
    StrategyDecision,
    StrategyEvidence,
    StrategyInput,
    StrategyInvalidation,
)
from .config import RegimeMomentumV1Config
from .sizing_context import build_sizing_risk_context


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clip(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    x = float(v)
    if x < lo:
        return float(lo)
    if x > hi:
        return float(hi)
    return float(x)


class RegimeMomentumV1:
    """Deterministic strategy module for momentum-by-regime behavior."""

    def __init__(self, *, config: RegimeMomentumV1Config) -> None:
        self.config = config

    def _composite(self, technical: Dict[str, Any], news: Dict[str, Any]) -> float:
        signal = _to_float(technical.get("signal_score"), 0.0)
        ma_gap = _clip(_to_float(technical.get("ma20_gap"), 0.0), -0.25, 0.25)
        symbol_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
        global_news = _to_float(news.get("global_sentiment_score"), 0.0)
        score = 0.50 * signal + 0.20 * ma_gap + 0.20 * symbol_news + 0.10 * global_news
        return _clip(score)

    def _invalidation(self, technical: Dict[str, Any], regime: str) -> StrategyInvalidation:
        signal = _to_float(technical.get("signal_score"), 0.0)
        vol = _to_float(technical.get("volatility20"), 0.0)
        conditions = []
        if signal <= float(self.config.invalidation_signal_floor):
            conditions.append("signal_floor_broken")
        if regime == "high_volatility" and vol >= float(self.config.max_volatility_for_entry):
            conditions.append("volatility_too_high")
        return StrategyInvalidation(
            triggered=bool(conditions),
            reason="|".join(conditions),
            conditions=conditions,
        )

    def decide(
        self,
        data: StrategyInput,
        *,
        price: float | None,
        cash: float | None,
        held_qty: int,
    ) -> StrategyDecision:
        technical = dict(data.technical or {})
        news = dict(data.news or {})
        regime = str(data.regime or technical.get("regime") or "unknown").strip().lower() or "unknown"
        composite = self._composite(technical, news)
        confidence = _clip(abs(composite), 0.0, 1.0)
        invalidation = self._invalidation(technical, regime)

        evidence = StrategyEvidence(
            regime=regime,
            technical={
                "signal_score": _to_float(technical.get("signal_score"), 0.0),
                "ma20_gap": _to_float(technical.get("ma20_gap"), 0.0),
                "volatility20": _to_float(technical.get("volatility20"), 0.0),
                "rsi14": _to_float(technical.get("rsi14"), 50.0),
                "composite_score": float(composite),
            },
            news={
                "symbol_sentiment_score": _to_float(news.get("symbol_sentiment_score"), 0.0),
                "global_sentiment_score": _to_float(news.get("global_sentiment_score"), 0.0),
            },
            policy={
                "version": self.config.version,
                "buy_composite_threshold": float(self.config.buy_composite_threshold),
                "sell_composite_threshold": float(self.config.sell_composite_threshold),
                "min_signal_for_entry": float(self.config.min_signal_for_entry),
                "min_news_for_entry": float(self.config.min_news_for_entry),
            },
        )

        signal_score = _to_float(technical.get("signal_score"), 0.0)
        symbol_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
        volatility = _to_float(technical.get("volatility20"), 0.0)

        entry_conditions = [
            "no_open_position",
            f"composite>= {self.config.buy_composite_threshold:.3f}",
            f"signal_score>= {self.config.min_signal_for_entry:.3f}",
            f"symbol_news>= {self.config.min_news_for_entry:.3f}",
            f"volatility20< {self.config.max_volatility_for_entry:.3f}",
        ]
        exit_conditions = [
            f"composite<= {self.config.sell_composite_threshold:.3f}",
            "invalidation_triggered",
        ]
        noop_conditions = []

        # Exit path first when holding.
        if int(held_qty or 0) > 0:
            should_exit = bool(
                composite <= float(self.config.sell_composite_threshold) or invalidation.triggered
            )
            if should_exit:
                return StrategyDecision(
                    action="SELL",
                    symbol=str(data.symbol),
                    qty=max(1, int(held_qty)),
                    confidence=float(confidence),
                    rationale=f"strategy_v1_exit: composite={composite:.4f} regime={regime}",
                    evidence=evidence,
                    invalidation=invalidation,
                    sizing_inputs={
                        "held_qty": int(held_qty),
                        "price": _to_float(price, 0.0),
                    },
                    entry_conditions=[],
                    exit_conditions=exit_conditions,
                    noop_conditions=[],
                )
            noop_conditions.append("position_held_but_exit_not_triggered")
            return StrategyDecision(
                action="NOOP",
                symbol=str(data.symbol),
                qty=0,
                confidence=float(confidence),
                rationale=f"strategy_v1_hold: composite={composite:.4f} regime={regime}",
                evidence=evidence,
                invalidation=invalidation,
                sizing_inputs={"held_qty": int(held_qty), "price": _to_float(price, 0.0)},
                entry_conditions=[],
                exit_conditions=exit_conditions,
                noop_conditions=noop_conditions,
            )

        entry_ok = (
            composite >= float(self.config.buy_composite_threshold)
            and signal_score >= float(self.config.min_signal_for_entry)
            and symbol_news >= float(self.config.min_news_for_entry)
            and volatility < float(self.config.max_volatility_for_entry)
            and not invalidation.triggered
        )
        if not entry_ok:
            noop_conditions.append("entry_conditions_not_met")
            return StrategyDecision(
                action="NOOP",
                symbol=str(data.symbol),
                qty=0,
                confidence=float(confidence),
                rationale=f"strategy_v1_no_entry: composite={composite:.4f} regime={regime}",
                evidence=evidence,
                invalidation=invalidation,
                sizing_inputs={
                    "price": _to_float(price, 0.0),
                    "cash": _to_float(cash, 0.0),
                },
                entry_conditions=entry_conditions,
                exit_conditions=[],
                noop_conditions=noop_conditions,
            )

        risk_ratio = max(
            float(self.config.base_risk_per_trade_ratio) * max(confidence, float(self.config.min_confidence_for_entry)),
            0.001,
        )
        notional_ratio = max(
            float(self.config.base_position_notional_ratio) * max(confidence, 0.25),
            0.01,
        )
        sizing_risk_context = build_sizing_risk_context(
            risk_context=dict(data.risk_context or {}),
            policy=dict(data.policy or {}),
            portfolio=dict(data.portfolio or {}),
            regime=regime,
            volatility20=volatility,
        )
        sizing = evaluate_position_size(
            price=_to_float(price, 0.0),
            cash=_to_float(cash, 0.0),
            policy={
                "risk_per_trade_ratio": risk_ratio,
                "position_notional_ratio": notional_ratio,
                "max_position_qty": int(self.config.max_position_qty),
                "min_position_qty": int(self.config.min_position_qty),
                "lot_size": int(self.config.lot_size),
            },
            risk_context=sizing_risk_context,
        )
        qty = int(sizing.get("qty") or 0)
        if qty <= 0:
            noop_conditions.append("position_sizing_qty_zero")
            return StrategyDecision(
                action="NOOP",
                symbol=str(data.symbol),
                qty=0,
                confidence=float(confidence),
                rationale=f"strategy_v1_sizing_blocked:{sizing.get('reason') or 'computed_qty_zero'}",
                evidence=evidence,
                invalidation=invalidation,
                sizing_inputs=dict(sizing),
                entry_conditions=entry_conditions,
                exit_conditions=[],
                noop_conditions=noop_conditions,
            )

        return StrategyDecision(
            action="BUY",
            symbol=str(data.symbol),
            qty=qty,
            confidence=float(confidence),
            rationale=f"strategy_v1_entry: composite={composite:.4f} regime={regime}",
            evidence=evidence,
            invalidation=invalidation,
            sizing_inputs=dict(sizing),
            entry_conditions=entry_conditions,
            exit_conditions=[],
            noop_conditions=[],
        )
