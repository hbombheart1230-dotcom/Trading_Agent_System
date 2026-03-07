from __future__ import annotations

from typing import Any, Dict

from libs.runtime.position_sizing import evaluate_position_size
from libs.strategies.contracts import (
    StrategyDecision,
    StrategyEvidence,
    StrategyInput,
    StrategyInvalidation,
)
from .config import NewsMomentumV1Config


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


class NewsMomentumV1:
    """Deterministic strategy module emphasizing symbol/global sentiment momentum."""

    def __init__(self, *, config: NewsMomentumV1Config) -> None:
        self.config = config

    def _composite(self, technical: Dict[str, Any], news: Dict[str, Any]) -> float:
        symbol_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
        global_news = _to_float(news.get("global_sentiment_score"), 0.0)
        signal = _to_float(technical.get("signal_score"), 0.0)
        score = 0.60 * symbol_news + 0.20 * global_news + 0.20 * signal
        return _clip(score)

    def _invalidation(self, technical: Dict[str, Any], news: Dict[str, Any]) -> StrategyInvalidation:
        symbol_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
        symbol_status = str(news.get("symbol_sentiment_status") or "").strip().lower()
        global_status = str(news.get("global_sentiment_status") or "").strip().lower()
        volatility = _to_float(technical.get("volatility20"), 0.0)

        conditions = []
        if symbol_news <= float(self.config.sell_news_threshold):
            conditions.append("news_reversal")
        if volatility >= float(self.config.max_volatility_for_entry):
            conditions.append("volatility_too_high")
        if bool(self.config.require_ok_status):
            if symbol_status != "ok":
                conditions.append("symbol_sentiment_status_not_ok")
            if global_status != "ok":
                conditions.append("global_sentiment_status_not_ok")
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

        symbol_news = _to_float(news.get("symbol_sentiment_score"), 0.0)
        global_news = _to_float(news.get("global_sentiment_score"), 0.0)
        signal = _to_float(technical.get("signal_score"), 0.0)
        volatility = _to_float(technical.get("volatility20"), 0.0)
        symbol_status = str(news.get("symbol_sentiment_status") or "").strip().lower()
        global_status = str(news.get("global_sentiment_status") or "").strip().lower()

        composite = self._composite(technical, news)
        confidence = _clip(abs(composite), 0.0, 1.0)
        invalidation = self._invalidation(technical, news)

        evidence = StrategyEvidence(
            regime=regime,
            technical={
                "signal_score": float(signal),
                "volatility20": float(volatility),
                "composite_score": float(composite),
            },
            news={
                "symbol_sentiment_score": float(symbol_news),
                "global_sentiment_score": float(global_news),
                "symbol_sentiment_status": symbol_status or "unknown",
                "global_sentiment_status": global_status or "unknown",
            },
            policy={
                "version": self.config.version,
                "buy_news_threshold": float(self.config.buy_news_threshold),
                "sell_news_threshold": float(self.config.sell_news_threshold),
                "min_signal_for_entry": float(self.config.min_signal_for_entry),
                "require_ok_status": bool(self.config.require_ok_status),
            },
        )

        entry_conditions = [
            "no_open_position",
            f"symbol_news>= {self.config.buy_news_threshold:.3f}",
            f"signal_score>= {self.config.min_signal_for_entry:.3f}",
            f"volatility20< {self.config.max_volatility_for_entry:.3f}",
        ]
        if bool(self.config.require_ok_status):
            entry_conditions.append("symbol/global sentiment status == ok")
        exit_conditions = [
            f"symbol_news<= {self.config.sell_news_threshold:.3f}",
            "invalidation_triggered",
        ]
        noop_conditions = []

        if int(held_qty or 0) > 0:
            should_exit = bool(
                symbol_news <= float(self.config.sell_news_threshold)
                or (signal < 0.0 and global_news < 0.0)
                or invalidation.triggered
            )
            if should_exit:
                return StrategyDecision(
                    action="SELL",
                    symbol=str(data.symbol),
                    qty=max(1, int(held_qty)),
                    confidence=float(confidence),
                    rationale=f"news_momentum_v1_exit: symbol_news={symbol_news:.3f} signal={signal:.3f}",
                    evidence=evidence,
                    invalidation=invalidation,
                    sizing_inputs={"held_qty": int(held_qty), "price": _to_float(price, 0.0)},
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
                rationale=f"news_momentum_v1_hold: symbol_news={symbol_news:.3f} signal={signal:.3f}",
                evidence=evidence,
                invalidation=invalidation,
                sizing_inputs={"held_qty": int(held_qty), "price": _to_float(price, 0.0)},
                entry_conditions=[],
                exit_conditions=exit_conditions,
                noop_conditions=noop_conditions,
            )

        status_ok = True
        if bool(self.config.require_ok_status):
            status_ok = symbol_status == "ok" and global_status == "ok"

        entry_ok = (
            symbol_news >= float(self.config.buy_news_threshold)
            and signal >= float(self.config.min_signal_for_entry)
            and volatility < float(self.config.max_volatility_for_entry)
            and status_ok
            and not invalidation.triggered
        )
        if not entry_ok:
            noop_conditions.append("entry_conditions_not_met")
            return StrategyDecision(
                action="NOOP",
                symbol=str(data.symbol),
                qty=0,
                confidence=float(confidence),
                rationale=f"news_momentum_v1_no_entry: symbol_news={symbol_news:.3f} signal={signal:.3f}",
                evidence=evidence,
                invalidation=invalidation,
                sizing_inputs={"price": _to_float(price, 0.0), "cash": _to_float(cash, 0.0)},
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
        )
        qty = int(sizing.get("qty") or 0)
        if qty <= 0:
            noop_conditions.append("position_sizing_qty_zero")
            return StrategyDecision(
                action="NOOP",
                symbol=str(data.symbol),
                qty=0,
                confidence=float(confidence),
                rationale=f"news_momentum_v1_sizing_blocked:{sizing.get('reason') or 'computed_qty_zero'}",
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
            rationale=f"news_momentum_v1_entry: symbol_news={symbol_news:.3f} signal={signal:.3f}",
            evidence=evidence,
            invalidation=invalidation,
            sizing_inputs=dict(sizing),
            entry_conditions=entry_conditions,
            exit_conditions=[],
            noop_conditions=[],
        )
