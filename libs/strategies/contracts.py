from __future__ import annotations

import json
import re
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


def _coerce_strategy_policy(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    out = dict(raw)
    out["schema_version"] = str(raw.get("schema_version") or "strategy_policy.v1")
    out["market_policy"] = dict(raw.get("market_policy") or {})
    out["scanner_policy"] = dict(raw.get("scanner_policy") or {})
    out["entry_policy"] = dict(raw.get("entry_policy") or {})
    out["monitor_policy"] = dict(raw.get("monitor_policy") or {})
    out["decision_policy"] = dict(raw.get("decision_policy") or {})
    out["operator_explain"] = dict(raw.get("operator_explain") or {})
    return out


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
    strategy_policy: Dict[str, Any] = field(default_factory=dict)
    report_focus: List[str] = field(default_factory=list)
    recent_strategy_feedback: Dict[str, Any] = field(default_factory=dict)
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
            "strategy_policy": _coerce_strategy_policy(self.strategy_policy),
            "report_focus": [str(x) for x in list(self.report_focus or [])][:8],
            "recent_strategy_feedback": dict(self.recent_strategy_feedback or {}),
            "candidates": [str(x) for x in list(self.candidates or [])][:32],
            "candidate_count": int(self.candidate_count),
            "candidate_hints": [str(x) for x in list(self.candidate_hints or [])][:32],
            "strategic_answers": dict(self.strategic_answers or {}),
            "source": str(self.source or "strategist_node"),
        }


def _coerce_text_list(raw: Any) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_one(value: Any) -> None:
        text = str(value or "").strip()
        if not text:
            return
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(text)

    def visit(value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (list, tuple, set)):
            for row in value:
                visit(row)
            return
        if isinstance(value, str):
            s = value.strip()
            if not s:
                return
            try:
                decoded = json.loads(s)
            except Exception:
                decoded = None
            if decoded is not None and decoded is not value:
                if isinstance(decoded, (list, tuple, set, str)):
                    visit(decoded)
                    return
            if any(sep in s for sep in ("\n", ",", ";", "|")):
                for part in re.split(r"[\n,;|]+", s):
                    add_one(part)
                return
            add_one(s)
            return
        add_one(value)

    visit(raw)
    return out


def _coerce_nested_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    contract_keys = {
        "market_regime",
        "market_sentiment",
        "key_events",
        "themes",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_priority",
        "scanner_source_policy",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "strategy_policy",
        "report_focus",
        "recent_strategy_feedback",
        "candidates",
        "candidate_count",
        "candidate_hints",
        "strategic_answers",
    }
    if any(k in raw for k in contract_keys):
        return dict(raw)

    for key in ("strategist_output", "output", "result", "data"):
        nested = raw.get(key)
        if isinstance(nested, dict) and any(k in nested for k in contract_keys):
            merged = dict(raw)
            merged.pop(key, None)
            merged.update(nested)
            return merged
    return dict(raw)


def coerce_strategist_output(raw: Any) -> Dict[str, Any]:
    """Normalize strategist output into canonical StrategistOutput contract shape.

    This is additive and backward-compatible:
    - required strategist-frame fields are always present and normalized
    - unknown/additive keys from upstream are preserved
    """
    if not isinstance(raw, dict):
        return StrategistOutput().to_dict()
    raw = _coerce_nested_output(raw)

    dto = StrategistOutput(
        market_regime=raw.get("market_regime", "neutral"),  # type: ignore[arg-type]
        market_sentiment=raw.get("market_sentiment", "neutral"),  # type: ignore[arg-type]
        key_events=_coerce_text_list(raw.get("key_events")),
        themes=_coerce_text_list(raw.get("themes")),
        avoid_themes=_coerce_text_list(raw.get("avoid_themes")),
        playbook=raw.get("playbook", "defensive"),  # type: ignore[arg-type]
        scanner_bias=raw.get("scanner_bias", "leader"),  # type: ignore[arg-type]
        scanner_priority=_coerce_text_list(raw.get("scanner_priority")),
        scanner_source_policy=dict(raw.get("scanner_source_policy") or {}),
        trade_aggressiveness=raw.get("trade_aggressiveness", "medium"),  # type: ignore[arg-type]
        risk_tone=raw.get("risk_tone", "normal"),  # type: ignore[arg-type]
        monitor_guidance=raw.get("monitor_guidance", "defensive_exit"),  # type: ignore[arg-type]
        strategy_policy=_coerce_strategy_policy(raw.get("strategy_policy")),
        report_focus=_coerce_text_list(raw.get("report_focus")),
        recent_strategy_feedback=(
            dict(raw.get("recent_strategy_feedback") or {})
            if isinstance(raw.get("recent_strategy_feedback"), dict)
            else {}
        ),
        candidates=_coerce_text_list(raw.get("candidates")),
        candidate_count=int(raw.get("candidate_count") or len(_coerce_text_list(raw.get("candidates"))) or 0),
        candidate_hints=_coerce_text_list(raw.get("candidate_hints")),
        strategic_answers=dict(raw.get("strategic_answers") or {}),
        source=str(raw.get("source") or "strategist_node"),
    ).to_dict()

    out = dict(raw)
    out.update(dto)
    return out
