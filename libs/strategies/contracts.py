from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal

from libs.runtime.monitor_policy import build_monitor_entry_policy_bundle, normalize_monitor_entry_policy
from libs.runtime.policy_bundle import normalize_strategy_policy_bundle
from libs.runtime.scanner_bias import normalize_scanner_bias_context
from libs.strategies.playbook_contracts import (
    MARKET_REGIME_DEFAULT,
    MARKET_REGIMES,
    MARKET_SENTIMENT_DEFAULT,
    MARKET_SENTIMENTS,
    MONITOR_GUIDANCE_DEFAULT,
    MONITOR_GUIDANCE_VALUES,
    PLAYBOOK_DEFAULT,
    PLAYBOOKS,
    RISK_TONE_DEFAULT,
    RISK_TONES,
    SCANNER_BIASES,
    SCANNER_BIAS_DEFAULT,
    TRADE_AGGRESSIVENESS_DEFAULT,
    TRADE_AGGRESSIVENESS_LEVELS,
    normalize_contract_value,
)


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
    strategist_feedback_packet: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": str(self.symbol or ""),
            "regime": str(self.regime or "unknown"),
            "technical": dict(self.technical or {}),
            "news": dict(self.news or {}),
            "portfolio": dict(self.portfolio or {}),
            "policy": dict(self.policy or {}),
            "risk_context": dict(self.risk_context or {}),
            "strategist_feedback_packet": dict(self.strategist_feedback_packet or {}),
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
    scanner_bias_context: Dict[str, Any] = field(default_factory=dict)
    scanner_priority: List[str] = field(default_factory=list)
    scanner_source_policy: Dict[str, Any] = field(default_factory=dict)
    trade_aggressiveness: StrategistAggressiveness = "medium"
    risk_tone: StrategistRiskTone = "normal"
    monitor_guidance: StrategistMonitorGuidance = "defensive_exit"
    strategy_policy: Dict[str, Any] = field(default_factory=dict)
    market_regime_summary: str = ""
    monitor_entry_policy: Dict[str, Any] = field(default_factory=dict)
    policy_rationale: str = ""
    policy_source: str = "strategist"
    policy_validation_status: str = "ok"
    policy_fallback_used: bool = False
    policy_fallback_reason: str = ""
    policy_partial_normalized: bool = False
    policy_default_filled_fields: List[str] = field(default_factory=list)
    policy_validation_issues: List[str] = field(default_factory=list)
    policy_validation_missing_fields: List[str] = field(default_factory=list)
    policy_validation_invalid_fields: List[str] = field(default_factory=list)
    confidence: float | None = None
    report_focus: List[str] = field(default_factory=list)
    recent_strategy_feedback: Dict[str, Any] = field(default_factory=dict)
    candidates: List[str] = field(default_factory=list)
    candidate_count: int = 0
    candidate_hints: List[str] = field(default_factory=list)
    strategic_answers: Dict[str, Any] = field(default_factory=dict)
    source: str = "strategist_node"

    def to_dict(self) -> Dict[str, Any]:
        normalized_monitor_entry_policy = {}
        if self.monitor_entry_policy:
            normalized_monitor_entry_policy = build_monitor_entry_policy_bundle(
                threshold_policy=normalize_monitor_entry_policy(self.monitor_entry_policy)[0],
                playbook=self.playbook,
                monitor_guidance=self.monitor_guidance,
                risk_tone=self.risk_tone,
                trade_aggressiveness=self.trade_aggressiveness,
                interpretation_policy=(
                    dict(self.monitor_entry_policy.get("interpretation_policy") or {})
                    if isinstance(self.monitor_entry_policy, dict)
                    and isinstance(self.monitor_entry_policy.get("interpretation_policy"), dict)
                    else None
                ),
            )

        return {
            "market_regime": normalize_contract_value(
                self.market_regime,
                allowed=MARKET_REGIMES,
                default=MARKET_REGIME_DEFAULT,
            ),
            "market_sentiment": normalize_contract_value(
                self.market_sentiment,
                allowed=MARKET_SENTIMENTS,
                default=MARKET_SENTIMENT_DEFAULT,
            ),
            "key_events": [str(x) for x in list(self.key_events or [])][:8],
            "themes": [str(x) for x in list(self.themes or [])][:8],
            "avoid_themes": [str(x) for x in list(self.avoid_themes or [])][:8],
            "playbook": normalize_contract_value(self.playbook, allowed=PLAYBOOKS, default=PLAYBOOK_DEFAULT),
            "scanner_bias": normalize_contract_value(
                self.scanner_bias,
                allowed=SCANNER_BIASES,
                default=SCANNER_BIAS_DEFAULT,
            ),
            "scanner_bias_context": (
                normalize_scanner_bias_context(self.scanner_bias_context)[0].to_dict()
                if self.scanner_bias_context
                else {}
            ),
            "scanner_priority": [str(x) for x in list(self.scanner_priority or [])][:8],
            "scanner_source_policy": dict(self.scanner_source_policy or {}),
            "trade_aggressiveness": normalize_contract_value(
                self.trade_aggressiveness,
                allowed=TRADE_AGGRESSIVENESS_LEVELS,
                default=TRADE_AGGRESSIVENESS_DEFAULT,
            ),
            "risk_tone": normalize_contract_value(self.risk_tone, allowed=RISK_TONES, default=RISK_TONE_DEFAULT),
            "monitor_guidance": normalize_contract_value(
                self.monitor_guidance,
                allowed=MONITOR_GUIDANCE_VALUES,
                default=MONITOR_GUIDANCE_DEFAULT,
            ),
            "strategy_policy": normalize_strategy_policy_bundle(self.strategy_policy),
            "market_regime_summary": str(self.market_regime_summary or ""),
            "monitor_entry_policy": normalized_monitor_entry_policy,
            "policy_rationale": str(self.policy_rationale or ""),
            "policy_source": str(self.policy_source or "strategist"),
            "policy_validation_status": str(self.policy_validation_status or "ok"),
            "policy_fallback_used": bool(self.policy_fallback_used),
            "policy_fallback_reason": str(self.policy_fallback_reason or ""),
            "policy_partial_normalized": bool(self.policy_partial_normalized),
            "policy_default_filled_fields": [str(x) for x in list(self.policy_default_filled_fields or [])][:12],
            "policy_validation_issues": [str(x) for x in list(self.policy_validation_issues or [])][:12],
            "policy_validation_missing_fields": [str(x) for x in list(self.policy_validation_missing_fields or [])][:12],
            "policy_validation_invalid_fields": [str(x) for x in list(self.policy_validation_invalid_fields or [])][:12],
            "confidence": None if self.confidence in (None, "") else float(self.confidence),
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


def _coerce_optional_unit_float(raw: Any) -> float | None:
    if raw in (None, ""):
        return None
    try:
        return max(0.0, min(1.0, float(raw)))
    except Exception:
        return None


def _coerce_nested_output(raw: Dict[str, Any]) -> Dict[str, Any]:
    contract_keys = {
        "market_regime",
        "market_sentiment",
        "key_events",
        "themes",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_bias_context",
        "scanner_priority",
        "scanner_source_policy",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "strategy_policy",
        "monitor_entry_policy",
        "policy_rationale",
        "market_regime_summary",
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

    strategy_policy = normalize_strategy_policy_bundle(raw.get("strategy_policy"))
    strategy_monitor_policy = dict(strategy_policy.get("monitor_policy") or {}) if isinstance(strategy_policy.get("monitor_policy"), dict) else {}
    raw_monitor_entry_policy = raw.get("monitor_entry_policy")
    if raw_monitor_entry_policy in (None, "") and isinstance(strategy_monitor_policy.get("entry_policy"), dict):
        raw_monitor_entry_policy = dict(strategy_monitor_policy.get("entry_policy") or {})

    dto = StrategistOutput(
        market_regime=raw.get("market_regime", "neutral"),  # type: ignore[arg-type]
        market_sentiment=raw.get("market_sentiment", "neutral"),  # type: ignore[arg-type]
        key_events=_coerce_text_list(raw.get("key_events")),
        themes=_coerce_text_list(raw.get("themes")),
        avoid_themes=_coerce_text_list(raw.get("avoid_themes")),
        playbook=raw.get("playbook", "defensive"),  # type: ignore[arg-type]
        scanner_bias=raw.get("scanner_bias", "leader"),  # type: ignore[arg-type]
        scanner_bias_context=(
            normalize_scanner_bias_context(raw.get("scanner_bias_context"))[0].to_dict()
            if isinstance(raw.get("scanner_bias_context"), dict)
            else {}
        ),
        scanner_priority=_coerce_text_list(raw.get("scanner_priority")),
        scanner_source_policy=dict(raw.get("scanner_source_policy") or {}),
        trade_aggressiveness=raw.get("trade_aggressiveness", "medium"),  # type: ignore[arg-type]
        risk_tone=raw.get("risk_tone", "normal"),  # type: ignore[arg-type]
        monitor_guidance=raw.get("monitor_guidance", "defensive_exit"),  # type: ignore[arg-type]
        strategy_policy=strategy_policy,
        market_regime_summary=str(raw.get("market_regime_summary") or ""),
        monitor_entry_policy=(
            build_monitor_entry_policy_bundle(
                threshold_policy=normalize_monitor_entry_policy(raw_monitor_entry_policy)[0],
                playbook=raw.get("playbook", "defensive"),  # type: ignore[arg-type]
                monitor_guidance=raw.get("monitor_guidance", "defensive_exit"),  # type: ignore[arg-type]
                risk_tone=raw.get("risk_tone", "normal"),  # type: ignore[arg-type]
                trade_aggressiveness=raw.get("trade_aggressiveness", "medium"),  # type: ignore[arg-type]
                interpretation_policy=(
                    dict(raw_monitor_entry_policy.get("interpretation_policy") or {})
                    if isinstance(raw_monitor_entry_policy, dict)
                    and isinstance(raw_monitor_entry_policy.get("interpretation_policy"), dict)
                    else None
                ),
            )
            if raw_monitor_entry_policy not in (None, "")
            else {}
        ),
        policy_rationale=str(raw.get("policy_rationale") or ""),
        policy_source=str(raw.get("policy_source") or "strategist"),
        policy_validation_status=str(raw.get("policy_validation_status") or "ok"),
        policy_fallback_used=bool(raw.get("policy_fallback_used")),
        policy_fallback_reason=str(raw.get("policy_fallback_reason") or ""),
        policy_partial_normalized=bool(raw.get("policy_partial_normalized")),
        policy_default_filled_fields=_coerce_text_list(raw.get("policy_default_filled_fields")),
        policy_validation_issues=_coerce_text_list(raw.get("policy_validation_issues")),
        policy_validation_missing_fields=_coerce_text_list(raw.get("policy_validation_missing_fields")),
        policy_validation_invalid_fields=_coerce_text_list(raw.get("policy_validation_invalid_fields")),
        confidence=_coerce_optional_unit_float(raw.get("confidence")),
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
