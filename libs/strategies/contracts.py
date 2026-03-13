from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal


StrategyAction = Literal["BUY", "SELL", "NOOP"]
StrategistMarketRegime = Literal["risk_on", "neutral", "risk_off"]
StrategistMarketSentiment = Literal["bullish", "neutral", "bearish"]
StrategistPlaybook = Literal["breakout", "pullback", "reversal", "defensive"]
StrategistScannerBias = Literal["large_cap", "leader", "momentum", "value"]
StrategistAggressiveness = Literal["low", "medium", "high"]
StrategistRiskTone = Literal["conservative", "normal", "aggressive"]
StrategistMonitorGuidance = Literal["hold_through_noise", "defensive_exit", "quick_take_profit"]


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


@dataclass(frozen=True)
class StrategistOutput:
    market_regime: StrategistMarketRegime = "neutral"
    market_sentiment: StrategistMarketSentiment = "neutral"
    key_events: List[str] = field(default_factory=list)
    themes: List[str] = field(default_factory=list)
    avoid_themes: List[str] = field(default_factory=list)
    playbook: StrategistPlaybook = "defensive"
    scanner_bias: StrategistScannerBias = "leader"
    scanner_priority: List[str] = field(default_factory=list)
    scanner_source_policy: Dict[str, Any] = field(default_factory=dict)
    trade_aggressiveness: StrategistAggressiveness = "medium"
    risk_tone: StrategistRiskTone = "normal"
    monitor_guidance: StrategistMonitorGuidance = "defensive_exit"
    report_focus: List[str] = field(default_factory=list)
    candidates: List[str] = field(default_factory=list)
    candidate_count: int = 0
    candidate_hints: List[str] = field(default_factory=list)
    strategic_answers: Dict[str, Any] = field(default_factory=dict)
    source: str = "strategist_node"

    def to_dict(self) -> Dict[str, Any]:
        def _norm_enum(value: Any, allowed: List[str], default: str) -> str:
            s = str(value or "").strip().lower()
            return s if s in allowed else default

        return {
            "market_regime": _norm_enum(self.market_regime, ["risk_on", "neutral", "risk_off"], "neutral"),
            "market_sentiment": _norm_enum(self.market_sentiment, ["bullish", "neutral", "bearish"], "neutral"),
            "key_events": [str(x) for x in list(self.key_events or [])][:8],
            "themes": [str(x) for x in list(self.themes or [])][:8],
            "avoid_themes": [str(x) for x in list(self.avoid_themes or [])][:8],
            "playbook": _norm_enum(self.playbook, ["breakout", "pullback", "reversal", "defensive"], "defensive"),
            "scanner_bias": _norm_enum(self.scanner_bias, ["large_cap", "leader", "momentum", "value"], "leader"),
            "scanner_priority": [str(x) for x in list(self.scanner_priority or [])][:8],
            "scanner_source_policy": dict(self.scanner_source_policy or {}),
            "trade_aggressiveness": _norm_enum(self.trade_aggressiveness, ["low", "medium", "high"], "medium"),
            "risk_tone": _norm_enum(self.risk_tone, ["conservative", "normal", "aggressive"], "normal"),
            "monitor_guidance": _norm_enum(
                self.monitor_guidance,
                ["hold_through_noise", "defensive_exit", "quick_take_profit"],
                "defensive_exit",
            ),
            "report_focus": [str(x) for x in list(self.report_focus or [])][:8],
            "candidates": [str(x) for x in list(self.candidates or [])][:32],
            "candidate_count": int(self.candidate_count),
            "candidate_hints": [str(x) for x in list(self.candidate_hints or [])][:32],
            "strategic_answers": dict(self.strategic_answers or {}),
            "source": str(self.source or "strategist_node"),
        }


def coerce_strategist_output(raw: Any) -> Dict[str, Any]:
    """Normalize strategist output into canonical StrategistOutput contract shape.

    This is additive and backward-compatible:
    - required strategist-frame fields are always present and normalized
    - unknown/additive keys from upstream are preserved
    """
    if not isinstance(raw, dict):
        return StrategistOutput().to_dict()

    dto = StrategistOutput(
        market_regime=raw.get("market_regime", "neutral"),  # type: ignore[arg-type]
        market_sentiment=raw.get("market_sentiment", "neutral"),  # type: ignore[arg-type]
        key_events=list(raw.get("key_events") or []),
        themes=list(raw.get("themes") or []),
        avoid_themes=list(raw.get("avoid_themes") or []),
        playbook=raw.get("playbook", "defensive"),  # type: ignore[arg-type]
        scanner_bias=raw.get("scanner_bias", "leader"),  # type: ignore[arg-type]
        scanner_priority=list(raw.get("scanner_priority") or []),
        scanner_source_policy=dict(raw.get("scanner_source_policy") or {}),
        trade_aggressiveness=raw.get("trade_aggressiveness", "medium"),  # type: ignore[arg-type]
        risk_tone=raw.get("risk_tone", "normal"),  # type: ignore[arg-type]
        monitor_guidance=raw.get("monitor_guidance", "defensive_exit"),  # type: ignore[arg-type]
        report_focus=list(raw.get("report_focus") or []),
        candidates=list(raw.get("candidates") or []),
        candidate_count=int(raw.get("candidate_count") or 0),
        candidate_hints=list(raw.get("candidate_hints") or []),
        strategic_answers=dict(raw.get("strategic_answers") or {}),
        source=str(raw.get("source") or "strategist_node"),
    ).to_dict()

    out = dict(raw)
    out.update(dto)
    return out
