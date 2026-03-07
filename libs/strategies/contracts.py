from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


StrategyAction = Literal["BUY", "SELL", "NOOP"]


@dataclass(frozen=True)
class StrategyEvidence:
    regime: str = "unknown"
    technical: Dict[str, Any] = field(default_factory=dict)
    news: Dict[str, Any] = field(default_factory=dict)
    policy: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "regime": str(self.regime or "unknown"),
            "technical": dict(self.technical or {}),
            "news": dict(self.news or {}),
            "policy": dict(self.policy or {}),
        }


@dataclass(frozen=True)
class StrategyInvalidation:
    triggered: bool = False
    reason: str = ""
    conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "triggered": bool(self.triggered),
            "reason": str(self.reason or ""),
            "conditions": [str(x) for x in list(self.conditions or [])],
        }


@dataclass(frozen=True)
class StrategyInput:
    symbol: str
    regime: str = "unknown"
    technical: Dict[str, Any] = field(default_factory=dict)
    news: Dict[str, Any] = field(default_factory=dict)
    portfolio: Dict[str, Any] = field(default_factory=dict)
    policy: Dict[str, Any] = field(default_factory=dict)
    risk_context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": str(self.symbol or ""),
            "regime": str(self.regime or "unknown"),
            "technical": dict(self.technical or {}),
            "news": dict(self.news or {}),
            "portfolio": dict(self.portfolio or {}),
            "policy": dict(self.policy or {}),
            "risk_context": dict(self.risk_context or {}),
        }


@dataclass(frozen=True)
class StrategyDecision:
    action: StrategyAction
    symbol: str
    qty: int = 0
    confidence: float = 0.0
    rationale: str = ""
    evidence: StrategyEvidence = field(default_factory=StrategyEvidence)
    invalidation: StrategyInvalidation = field(default_factory=StrategyInvalidation)
    sizing_inputs: Dict[str, Any] = field(default_factory=dict)
    entry_conditions: List[str] = field(default_factory=list)
    exit_conditions: List[str] = field(default_factory=list)
    noop_conditions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": str(self.action).upper(),
            "symbol": str(self.symbol or ""),
            "qty": int(self.qty),
            "confidence": float(self.confidence),
            "rationale": str(self.rationale or ""),
            "evidence": self.evidence.to_dict(),
            "invalidation": self.invalidation.to_dict(),
            "sizing_inputs": dict(self.sizing_inputs or {}),
            "entry_conditions": [str(x) for x in list(self.entry_conditions or [])],
            "exit_conditions": [str(x) for x in list(self.exit_conditions or [])],
            "noop_conditions": [str(x) for x in list(self.noop_conditions or [])],
        }
