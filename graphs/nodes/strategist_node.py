from __future__ import annotations

"""Canonical Strategist node for integrated runtime.

Role boundary:
- owns strategic framing (themes/sectors, sentiment context, candidate hints)
- prepares strategist outputs for scanner/monitor handoff
- does not execute orders
"""

import os
import json
import ast
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from libs.ai.strategist_config import (
    strategist_llm_requested,
    strategist_llm_strict,
    strategist_runtime_settings,
)
from libs.data_quality.signal_contract import SIGNAL_STATUS_FALLBACK, make_signal
from libs.llm.model_names import normalize_openrouter_model_name
from libs.llm.llm_router import LLMRouter
from libs.market.global_sentiment import compute_global_sentiment_signal
from libs.news.news_pipeline import collect_news_items, score_news_sentiment_signal
from libs.performance.strategy_memory import load_strategy_memory_hint
from libs.research.evidence_ledger import (
    record_decision_bridge,
    record_llm_prompt,
    record_llm_response,
    record_raw_input,
)
from libs.research.strategy_feedback_builder import build_recent_strategy_feedback
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.decision_observability import build_strategist_policy_resolution_surface
from libs.runtime.strategist_packet_visibility import (
    build_strategist_memory_packet_visibility,
    summarize_read_model_facts,
)
from libs.runtime.monitor_policy import (
    MonitorEntryPolicy,
    build_monitor_entry_policy_bundle,
    build_default_monitor_entry_policy,
    normalize_monitor_entry_policy,
)
from libs.runtime.scanner_bias import normalize_scanner_bias_context, summarize_scanner_bias_context
from libs.runtime.canonical_artifacts import (
    strategist_llm_stage_descriptor,
    write_llm_artifact_bundle,
    write_llm_stage_manifest_entry,
    write_strategist_artifact,
)
from libs.runtime.regime import classify_regime_v2
from libs.runtime.strategist_explanation import build_strategist_explanation_fields
from libs.runtime.strategy_horizon_feedback import build_commander_horizon_policy, build_strategy_horizon_feedback
from libs.strategies.candidates.fallback_pool import resolve_fallback_symbols
from libs.strategies.contracts import StrategistOutput, coerce_strategist_output
from libs.strategies.candidates.market_rank import MarketRankCandidateGenerator
from libs.strategies.candidates.market_rank import TopPicksCandidateGenerator
from libs.strategies.universe_builder import build_candidate_universe
from libs.reporting.trade_read_model import build_trade_read_model
from libs.reporting.reporter_feedback import build_strategist_feedback_packet
from libs.reporting.symbol_read_model import build_symbol_read_model
from libs.runtime.commander_memory_policy import build_commander_memory_policy
from libs.runtime.memory_packet_loader import load_commander_memory_packets
from libs.runtime.monitor_memory_bias import build_monitor_memory_bias, summarize_monitor_memory_bias
from libs.runtime.scanner_memory_bias import build_scanner_memory_bias, summarize_scanner_memory_bias
from libs.runtime.quant.contracts import TACTIC_IDS, TACTICAL_SUBTYPES
from libs.runtime.quant.tactics import (
    TACTIC_DEFAULT_RUNNER_UP_RANK,
    canonical_tactic_key,
    default_tactic_for_playbook,
    normalize_playbook as normalize_tactic_playbook,
    normalize_tactic_id,
    normalize_tactical_subtype as normalize_quant_tactical_subtype,
)
from libs.runtime.quant.context import build_strategist_quant_context
from libs.read.kiwoom_theme_reader import build_theme_strength_packet


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _strategy_memory_usage_disabled(policy_or_payload: Any | None = None) -> bool:
    obj = dict(policy_or_payload or {}) if isinstance(policy_or_payload, dict) else {}
    commander_policy = (
        dict(obj.get("commander_memory_policy") or {})
        if isinstance(obj.get("commander_memory_policy"), dict)
        else obj
    )
    applied_policy = obj.get("applied_policy") if isinstance(obj.get("applied_policy"), dict) else {}
    commander_applied = applied_policy.get("commander") if isinstance(applied_policy.get("commander"), dict) else {}
    strategist_applied = applied_policy.get("strategist") if isinstance(applied_policy.get("strategist"), dict) else {}
    commander_memory_usage = (
        commander_applied.get("memory_usage")
        if isinstance(commander_applied.get("memory_usage"), dict)
        else {}
    )
    strategist_memory_usage = (
        strategist_applied.get("memory_usage")
        if isinstance(strategist_applied.get("memory_usage"), dict)
        else {}
    )
    return bool(
        _env_bool("STRATEGIST_MEMORY_USAGE_DISABLED")
        or _env_bool("COMMANDER_MEMORY_USAGE_DISABLED")
        or bool(obj.get("strategist_memory_usage_disabled"))
        or bool(obj.get("commander_memory_usage_disabled"))
        or bool(strategist_memory_usage.get("disabled"))
        or bool(commander_memory_usage.get("disabled"))
        or str(commander_policy.get("application_mode") or "").strip().lower() == "disabled"
        or bool(commander_policy.get("disabled"))
    )


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _env_int(key: str) -> int | None:
    raw = os.getenv(key)
    if raw in (None, ""):
        return None
    try:
        return int(float(str(raw).strip()))
    except Exception:
        return None


def _nested_mapping_value(mapping: Any, *path: str) -> Any:
    cursor: Any = mapping if isinstance(mapping, dict) else {}
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _neutralize_ambiguous_playbook_memory(memory: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(memory or {})
    best = [str(x or "").strip() for x in list(out.get("best_playbooks") or []) if str(x or "").strip()]
    worst = [str(x or "").strip() for x in list(out.get("worst_playbooks") or []) if str(x or "").strip()]
    overlap = {x.lower() for x in best}.intersection({x.lower() for x in worst})
    if not overlap:
        return out

    out["best_playbooks"] = [x for x in best if x.lower() not in overlap]
    out["worst_playbooks"] = [x for x in worst if x.lower() not in overlap]
    flags = [str(x or "") for x in list(out.get("memory_quality_flags") or []) if str(x or "").strip()]
    flags.append("ambiguous_playbook_performance:best_worst_overlap")
    out["memory_quality_flags"] = list(dict.fromkeys(flags))
    notes = [str(x or "") for x in list(out.get("advisory_notes") or []) if str(x or "").strip()]
    notes.append("best_playbooks and worst_playbooks overlapped; overlapping playbooks are not used as directional bias.")
    out["advisory_notes"] = list(dict.fromkeys(notes))
    out["directional_bias_usable"] = bool(out["best_playbooks"] or out["worst_playbooks"])
    return out


def _load_recent_strategy_feedback(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    strategist_policy = applied_policy.get("strategist") if isinstance(applied_policy.get("strategist"), dict) else {}
    memory_feedback_policy = (
        strategist_policy.get("memory_feedback")
        if isinstance(strategist_policy.get("memory_feedback"), dict)
        else {}
    )
    if isinstance(memory_feedback_policy, dict) and memory_feedback_policy.get("enabled") is not None:
        enabled_raw = memory_feedback_policy.get("enabled")
        policy_source = str(memory_feedback_policy.get("policy_source") or "commander_applied_policy")
    elif strategist_policy.get("memory_feedback_enabled") is not None:
        enabled_raw = strategist_policy.get("memory_feedback_enabled")
        policy_source = "strategist_policy_fallback"
    elif policy.get("use_strategy_memory_feedback") is not None:
        enabled_raw = policy.get("use_strategy_memory_feedback")
        policy_source = "policy_fallback"
    else:
        enabled_raw = True
        policy_source = "default_true"
    enabled = _is_trueish(enabled_raw)
    if not enabled:
        return {
            "feedback_window_size": 0,
            "recent_theme_performance": {},
            "recent_playbook_performance": {},
            "recent_monitor_issues": [],
            "recent_scanner_issues": [],
            "recent_guard_patterns": [],
            "recent_overtrading_patterns": [],
            "recent_reporter_summary": [],
            "top_recent_strengths": [],
            "top_recent_weaknesses": [],
            "suggested_report_focus": [],
            "advisory_only": True,
            "status": "disabled",
            "policy_source": str(policy_source),
        }
    raw_window = _nested_mapping_value(memory_feedback_policy, "recent_runs")
    if raw_window is not None:
        policy_source = str(memory_feedback_policy.get("policy_source") or "commander_applied_policy")
    elif strategist_policy.get("memory_feedback_recent_runs") is not None:
        raw_window = strategist_policy.get("memory_feedback_recent_runs")
        policy_source = "strategist_policy_fallback"
    elif policy.get("strategy_memory_recent_runs") is not None:
        raw_window = policy.get("strategy_memory_recent_runs")
        policy_source = "policy_fallback"
    else:
        raw_window = 12
    last_n_runs = max(1, _to_int(raw_window, 12))
    feedback = build_recent_strategy_feedback(last_n_runs)
    feedback["status"] = "ok" if int(feedback.get("feedback_window_size") or 0) > 0 else "empty"
    feedback["requested_window_size"] = int(last_n_runs)
    feedback["policy_source"] = str(policy_source)
    return feedback


def _iso_day_from_value(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    try:
        epoch = int(float(value))
    except Exception:
        epoch = 0
    if epoch > 0:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _resolve_state_day(state: Dict[str, Any]) -> str:
    for key in ("started_at", "ts", "now_iso", "tick_ts"):
        if state.get(key) not in (None, ""):
            return _iso_day_from_value(state.get(key))
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_strategy_memory_advisory(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    enabled_raw = (
        policy.get("use_strategy_performance_memory")
        if policy.get("use_strategy_performance_memory") is not None
        else os.getenv("USE_STRATEGY_PERFORMANCE_MEMORY", "true")
    )
    enabled = _is_trueish(enabled_raw)
    if not enabled:
        return {
            "schema_version": "strategy_memory.v1",
            "status": "disabled",
            "best_playbooks": [],
            "worst_playbooks": [],
            "market_condition_bias": {},
            "recent_failures": [],
            "recent_success_patterns": [],
            "playbook_performance_snapshot": {},
            "pattern_performance_snapshot": {},
            "advisory_only": True,
        }

    auto_build_raw = (
        policy.get("strategy_performance_auto_build")
        if policy.get("strategy_performance_auto_build") is not None
        else os.getenv("STRATEGY_PERFORMANCE_AUTO_BUILD", "false")
    )
    auto_build = _is_trueish(auto_build_raw)
    reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")
    day = str(
        policy.get("strategy_performance_day")
        or state.get("day")
        or _resolve_state_day(state)
    ).strip()
    try:
        memory = load_strategy_memory_hint(
            reports_root=reports_root,
            day=day,
            auto_build=bool(auto_build),
        )
    except Exception as exc:
        return {
            "schema_version": "strategy_memory.v1",
            "status": "error",
            "error": str(exc),
            "day": str(day),
            "best_playbooks": [],
            "worst_playbooks": [],
            "market_condition_bias": {},
            "recent_failures": [],
            "recent_success_patterns": [],
            "playbook_performance_snapshot": {},
            "pattern_performance_snapshot": {},
            "advisory_only": True,
        }
    if not isinstance(memory, dict):
        return {
            "schema_version": "strategy_memory.v1",
            "status": "empty",
            "day": str(day),
            "best_playbooks": [],
            "worst_playbooks": [],
            "market_condition_bias": {},
            "recent_failures": [],
            "recent_success_patterns": [],
            "playbook_performance_snapshot": {},
            "pattern_performance_snapshot": {},
            "advisory_only": True,
        }
    out = dict(memory)
    out.setdefault("schema_version", "strategy_memory.v1")
    out.setdefault("day", str(day))
    out.setdefault("status", "ok" if out.get("best_playbooks") or out.get("worst_playbooks") else "empty")
    out.setdefault("best_playbooks", [])
    out.setdefault("worst_playbooks", [])
    out.setdefault("market_condition_bias", {})
    out.setdefault("recent_failures", [])
    out.setdefault("recent_success_patterns", [])
    out.setdefault("playbook_performance_snapshot", {})
    out.setdefault("pattern_performance_snapshot", {})
    out.setdefault("advisory_only", True)
    return _neutralize_ambiguous_playbook_memory(out)


def _resolve_top_n_candidates(policy: Dict[str, Any]) -> int:
    raw = (
        policy.get("candidate_k")
        if policy.get("candidate_k") is not None
        else policy.get("candidate_topk")
    )
    if raw is not None:
        return max(1, _to_int(raw, 10))

    env_topn = _env_int("TOP_N_CANDIDATES")
    if isinstance(env_topn, int) and env_topn > 0:
        return max(1, env_topn)
    # Keep strategist candidate-hint contract stable at Top-5 by default.
    return 5


def _strip_fenced_block(text: str) -> str:
    s = str(text or "").strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if not lines:
        return s
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_text_list_fragment(raw: Any) -> List[str]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        return [str(x or "").strip() for x in list(raw or []) if str(x or "").strip()]
    s = str(raw or "").strip()
    if not s:
        return []
    decoded = None
    for parser in (json.loads, ast.literal_eval):
        try:
            decoded = parser(s)
            break
        except Exception:
            decoded = None
    if isinstance(decoded, (list, tuple, set)):
        return [str(x or "").strip() for x in list(decoded or []) if str(x or "").strip()]
    if any(sep in s for sep in ("\n", ",", ";", "|")):
        return [str(x or "").strip() for x in re.split(r"[\n,;|]+", s) if str(x or "").strip()]
    return [s]


def _extract_contract_from_prose(text: str) -> Dict[str, Any]:
    s = _strip_fenced_block(text)
    if not s:
        return {}

    out: Dict[str, Any] = {}
    lines = [str(row or "").strip() for row in s.splitlines() if str(row or "").strip()]
    if not lines:
        return {}

    enum_specs: Dict[str, List[str]] = {
        "market_regime": ["risk_on", "neutral", "risk_off"],
        "market_sentiment": ["bullish", "neutral", "bearish"],
        "playbook": ["breakout", "pullback", "reversal", "defensive"],
        "scanner_bias": ["large_cap", "leader", "momentum", "value"],
        "trade_aggressiveness": ["low", "medium", "high"],
        "risk_tone": ["conservative", "normal", "aggressive"],
        "monitor_guidance": ["hold_through_noise", "defensive_exit", "quick_take_profit"],
    }
    list_keys = ("key_events", "themes", "avoid_themes", "scanner_priority", "report_focus")
    alias_map = {
        "market_regime_hint": "market_regime",
        "market_sentiment_hint": "market_sentiment",
        "playbook_hint": "playbook",
        "themes_hint": "themes",
        "key_events_hint": "key_events",
    }

    def normalized_line(raw_line: str) -> str:
        line = str(raw_line or "").strip()
        line = re.sub(r"^\d+\.\s*", "", line)
        line = re.sub(r"^[-*]\s*", "", line)
        line = line.replace("**", "")
        return line.strip()

    for raw_line in lines:
        line = normalized_line(raw_line)
        if not line or ":" not in line:
            continue
        for raw_key in list(enum_specs.keys()) + list(list_keys) + list(alias_map.keys()):
            match = re.search(rf"\b{re.escape(raw_key)}\b\s*:\s*(.+)$", line, flags=re.IGNORECASE)
            if not match:
                continue
            key = alias_map.get(raw_key, raw_key)
            value = str(match.group(1) or "").strip()
            if key in enum_specs:
                matches = re.findall(r"(risk_on|risk_off|neutral|bullish|bearish|breakout|pullback|reversal|defensive|large_cap|leader|momentum|value|low|medium|high|conservative|normal|aggressive|hold_through_noise|defensive_exit|quick_take_profit)", value, flags=re.IGNORECASE)
                if matches:
                    allowed = {item.lower() for item in enum_specs[key]}
                    for candidate in reversed(matches):
                        normalized = str(candidate or "").strip().lower()
                        if normalized in allowed:
                            out[key] = normalized
                            break
            else:
                bracket_match = re.search(r"(\[[^\]]*\])", value)
                parsed = _parse_text_list_fragment(bracket_match.group(1) if bracket_match else value)
                if (not parsed) or (parsed and len(parsed) == 1 and parsed[0] == value):
                    quoted = [str(x or "").strip() for x in re.findall(r'"([^"\n]{1,120})"', value) if str(x or "").strip()]
                    if quoted:
                        parsed = quoted
                if key == "scanner_priority" and parsed:
                    allowed_priority = {"trading_value", "trend_strength", "volume_surge", "leader_quality", "pullback_quality", "relative_strength", "risk_penalty", "low_volatility", "drawdown_control", "momentum"}
                    parsed = [x for x in parsed if str(x or "").strip().lower() in allowed_priority]
                if parsed:
                    out[key] = parsed
            break

    # Fall back to broader regex if line-oriented parsing missed obvious fields.
    for key, allowed in enum_specs.items():
        if key in out:
            continue
        raw_keys = [key] + [alias for alias, target in alias_map.items() if target == key]
        match = None
        for raw_key in raw_keys:
            pattern = rf"{re.escape(raw_key)}\s*:\s*([^\n]+)"
            match = re.search(pattern, s, flags=re.IGNORECASE)
            if match:
                break
        if not match:
            continue
        tail = str(match.group(1) or "")
        candidates = re.findall(
            r"(risk_on|risk_off|neutral|bullish|bearish|breakout|pullback|reversal|defensive|large_cap|leader|momentum|value|low|medium|high|conservative|normal|aggressive|hold_through_noise|defensive_exit|quick_take_profit)",
            tail,
            flags=re.IGNORECASE,
        )
        allowed_set = {item.lower() for item in allowed}
        for candidate in reversed(candidates):
            normalized = str(candidate or "").strip().lower()
            if normalized in allowed_set:
                out[key] = normalized
                break

    for key in list_keys:
        if key in out:
            continue
        raw_keys = [key] + [alias for alias, target in alias_map.items() if target == key]
        match = None
        for raw_key in raw_keys:
            match = re.search(rf"{re.escape(raw_key)}\s*:\s*(\[[^\]]*\])", s, flags=re.IGNORECASE | re.DOTALL)
            if match:
                break
        if not match:
            continue
        parsed = _parse_text_list_fragment(match.group(1))
        if parsed:
            out[key] = parsed

    has_contract_signal = bool(
        out.get("market_regime")
        or out.get("playbook")
        or out.get("themes")
        or out.get("monitor_guidance")
    )
    return out if has_contract_signal else {}


def _extract_json_object(text: str) -> Dict[str, Any]:
    s = _strip_fenced_block(text)
    if not s:
        return {}
    contract_keys = {
        "market_regime",
        "market_sentiment",
        "key_events",
        "themes",
        "avoid_themes",
        "playbook",
        "tactical_strategy",
        "tactical_subtype",
        "strategy_scores",
        "rejected_strategy_reasons",
        "candidate_watch_policy",
        "scanner_bias",
        "scanner_priority",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "market_regime_summary",
        "policy_rationale",
        "confidence",
        "policy_source",
        "monitor_entry_policy",
        "report_focus",
        "scanner_source_policy",
        "selected_symbol_decision",
        "hold_review_decision",
        "carry_review",
        "portfolio_level_decision",
    }

    def unwrap(obj: Any) -> Dict[str, Any]:
        if isinstance(obj, list) and obj and isinstance(obj[0], dict):
            obj = obj[0]
        if not isinstance(obj, dict):
            return {}
        if any(k in obj for k in contract_keys):
            return obj
        for key in ("strategist_output", "output", "result", "data"):
            nested = obj.get(key)
            if isinstance(nested, dict) and any(k in nested for k in contract_keys):
                merged = dict(obj)
                merged.pop(key, None)
                merged.update(nested)
                return merged
        return obj
    try:
        obj = json.loads(s)
        unwrapped = unwrap(obj)
        if unwrapped:
            return unwrapped
    except Exception:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(s):
        if ch != "{":
            continue
        try:
            obj, _end = dec.raw_decode(s[i:])
            unwrapped = unwrap(obj)
            if unwrapped:
                return unwrapped
        except Exception:
            continue
    prose_contract = _extract_contract_from_prose(s)
    if prose_contract:
        return prose_contract
    return {}


def _classify_llm_parse_failure(raw: Any) -> str:
    s = _strip_fenced_block(str(raw or "")).strip()
    if not s:
        return "strategist_llm_response_empty"
    if s.startswith("{") or s.startswith("[") or "market_regime" in s or "themes" in s:
        return "strategist_llm_response_truncated_json"
    return "strategist_llm_response_not_json"


def _resolve_strategist_frame_llm_enabled(policy: Dict[str, Any]) -> bool:
    if os.getenv("PYTEST_CURRENT_TEST") and policy.get("strategist_frame_use_llm") is None:
        raw_env = str(os.getenv("STRATEGIST_FRAME_USE_LLM", "") or "").strip()
        provider = str((strategist_runtime_settings(policy) or {}).get("provider") or "").strip().lower()
        if not raw_env and provider not in ("openai", "http", "api"):
            return False
    return strategist_llm_requested(policy)


def _resolve_strategist_frame_llm_strict_enabled(policy: Dict[str, Any]) -> bool:
    return strategist_llm_strict(policy)


def _stage_text_list(raw: Any, *, limit: int = 8, upper: bool = False) -> List[str]:
    values = _parse_text_list_fragment(raw)
    out: List[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        if upper:
            text = text.upper()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
        if len(out) >= int(limit):
            break
    return out


def _stage_bool(raw: Any, default: bool = False) -> bool:
    if raw is None:
        return bool(default)
    text = str(raw).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return bool(raw) if isinstance(raw, bool) else bool(default)


def _stage_float(raw: Any, default: float | None = None) -> float | None:
    try:
        if raw in (None, ""):
            return default
        return float(raw)
    except Exception:
        return default


def _normalize_stage2_selected_symbol_review(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "selected_symbol_decision" not in raw:
        return {}
    allowed_decisions = {
        "watch_rank1",
        "avoid_rank1",
        "watch_rank1_with_tighter_gates",
        "cascade_to_runner_up",
        "no_trade",
    }
    decision = str(raw.get("selected_symbol_decision") or "").strip().lower()
    if decision not in allowed_decisions:
        decision = "watch_rank1"
    monitor_instruction_raw = (
        dict(raw.get("monitor_instruction") or {})
        if isinstance(raw.get("monitor_instruction"), dict)
        else {}
    )
    watch_intensity = str(monitor_instruction_raw.get("watch_intensity") or "normal").strip().lower()
    if watch_intensity not in {"normal", "strict", "aggressive"}:
        watch_intensity = "normal"
    entry_delta_raw = (
        dict(raw.get("entry_policy_delta") or {})
        if isinstance(raw.get("entry_policy_delta"), dict)
        else {}
    )
    memory_usage_raw = dict(raw.get("memory_usage") or {}) if isinstance(raw.get("memory_usage"), dict) else {}
    memory_status = str(memory_usage_raw.get("status") or "").strip().lower()
    if memory_status not in {"used", "disabled", "insufficient", "stale"}:
        memory_status = "disabled" if _strategy_memory_usage_disabled(raw) else "insufficient"
    actionability = str(raw.get("commander_actionability") or "advisory_only").strip().lower()
    if actionability not in {"advisory_only", "policy_delta_allowed", "hard_block_recommended"}:
        actionability = "advisory_only"
    return {
        "schema_version": "strategist.stage2.selected_symbol_tactical_review.v1",
        "stage_name": "selected_symbol_tactical_refresh",
        "selected_symbol_decision": decision,
        "target_symbol": str(raw.get("target_symbol") or "").strip().upper(),
        "target_rank": max(0, _to_int(raw.get("target_rank"), 0)),
        "runner_up_order": _stage_text_list(raw.get("runner_up_order"), limit=8, upper=True),
        "monitor_instruction": {
            "watch_intensity": watch_intensity,
            "required_confirmations": _stage_text_list(
                monitor_instruction_raw.get("required_confirmations"),
                limit=8,
            ),
            "avoid_if": _stage_text_list(monitor_instruction_raw.get("avoid_if"), limit=8),
        },
        "entry_policy_delta": {
            "tighten_confidence_threshold": _stage_bool(entry_delta_raw.get("tighten_confidence_threshold")),
            "require_prev_close_context": _stage_bool(entry_delta_raw.get("require_prev_close_context"), True),
            "require_cost_hurdle": _stage_bool(entry_delta_raw.get("require_cost_hurdle"), True),
        },
        "memory_usage": {
            "status": memory_status,
            "sample_count": max(0, _to_int(memory_usage_raw.get("sample_count"), 0)),
            "confidence": str(memory_usage_raw.get("confidence") or "").strip().lower(),
            "data_quality": str(memory_usage_raw.get("data_quality") or "").strip().lower(),
            "effect": str(memory_usage_raw.get("effect") or "neutral").strip().lower(),
            "reason": str(memory_usage_raw.get("reason") or "").strip(),
        },
        "commander_actionability": actionability,
        "confidence": _stage_float(raw.get("confidence"), 0.0),
        "reason": str(raw.get("reason") or "").strip(),
    }


def _normalize_stage3_hold_review(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "hold_review_decision" not in raw:
        return {}
    decision = str(raw.get("hold_review_decision") or "").strip().lower()
    if decision not in {"hold", "tighten_exit", "exit_now", "wait_until_next_check"}:
        decision = "wait_until_next_check"
    exit_pressure = str(raw.get("exit_pressure") or "medium").strip().lower()
    if exit_pressure not in {"low", "medium", "high"}:
        exit_pressure = "medium"
    thesis_status = str(raw.get("thesis_status") or "weakened").strip().lower()
    if thesis_status not in {"intact", "weakened", "broken"}:
        thesis_status = "weakened"
    adjustment_raw = (
        dict(raw.get("monitor_adjustment") or {})
        if isinstance(raw.get("monitor_adjustment"), dict)
        else {}
    )
    next_check = max(1, _to_int(raw.get("next_check_minutes") or adjustment_raw.get("next_check_minutes"), 5))
    return {
        "schema_version": "strategist.stage3.stale_intraday_hold_review.v1",
        "stage_name": "stale_intraday_hold_review",
        "hold_review_decision": decision,
        "exit_pressure": exit_pressure,
        "thesis_status": thesis_status,
        "monitor_adjustment": {
            "tighten_stop": _stage_bool(adjustment_raw.get("tighten_stop")),
            "tighten_time_decay": _stage_bool(adjustment_raw.get("tighten_time_decay")),
            "allow_profit_recovery_wait": _stage_bool(adjustment_raw.get("allow_profit_recovery_wait")),
            "next_check_minutes": next_check,
        },
        "priority_exit_triggers": _stage_text_list(raw.get("priority_exit_triggers"), limit=8),
        "next_check_minutes": next_check,
        "reason": str(raw.get("reason") or "").strip(),
    }


def _normalize_stage4_carry_review(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict) or "carry_review" not in raw:
        return {}
    rows: List[Dict[str, Any]] = []
    for item in list(raw.get("carry_review") or [])[:8]:
        if not isinstance(item, dict):
            continue
        decision = str(item.get("decision") or "").strip().lower()
        if decision not in {"carry_overnight", "flatten_today", "reduce_or_flatten"}:
            decision = "flatten_today"
        confidence = str(item.get("carry_confidence") or "low").strip().lower()
        if confidence not in {"low", "medium", "high"}:
            confidence = "low"
        plan = dict(item.get("required_next_day_plan") or {}) if isinstance(item.get("required_next_day_plan"), dict) else {}
        rows.append(
            {
                "symbol": str(item.get("symbol") or "").strip().upper(),
                "decision": decision,
                "carry_confidence": confidence,
                "required_next_day_plan": {
                    "gap_down_action": str(plan.get("gap_down_action") or "").strip(),
                    "gap_up_action": str(plan.get("gap_up_action") or "").strip(),
                    "flat_open_action": str(plan.get("flat_open_action") or "").strip(),
                },
                "reason": str(item.get("reason") or "").strip(),
            }
        )
    portfolio_level = str(raw.get("portfolio_level_decision") or "flatten_all").strip().lower()
    if portfolio_level not in {"carry_allowed", "flatten_all", "carry_only_best_one"}:
        portfolio_level = "flatten_all"
    return {
        "schema_version": "strategist.stage4.end_of_day_carry_review.v1",
        "stage_name": "end_of_day_carry_review",
        "carry_review": rows,
        "portfolio_level_decision": portfolio_level,
        "risk_note": str(raw.get("risk_note") or "").strip(),
    }


def _derive_stage_specific_common_overrides(out: Dict[str, Any]) -> None:
    stage2 = dict(out.get("selected_symbol_tactical_review") or {})
    if stage2:
        decision = str(stage2.get("selected_symbol_decision") or "").strip()
        runner_ups = list(stage2.get("runner_up_order") or [])
        reason = str(stage2.get("reason") or "selected-symbol tactical refresh").strip()
        if "candidate_watch_policy" not in out:
            cascade = decision == "cascade_to_runner_up" and bool(runner_ups)
            max_rank = 1 + len(runner_ups) if cascade else 1
            if cascade and "tactical_strategy" not in out:
                out["tactical_strategy"] = "vwap_reclaim_pullback"
            out["candidate_watch_policy"] = {
                "max_priority_rank": max(1, min(10, int(max_rank))),
                "max_runner_ups": len(runner_ups) if cascade else 0,
                "cascade_enabled": bool(cascade),
                "cascade_allowed_reasons": [
                    "breakout_not_ready",
                    "volume_confirmation_missing",
                    "below_vwap_reclaim_not_ready",
                    "pullback_not_mature",
                ],
                "cascade_blocked_reasons": [
                    "cost_filter_failed",
                    "risk_policy_block",
                    "closeout_window",
                    "open_position_present",
                    "broker_truth_mismatch",
                ],
                "reason": reason,
            }
        if "strategy_adjustment_directives" not in out:
            monitor_instruction = dict(stage2.get("monitor_instruction") or {})
            entry_delta = dict(stage2.get("entry_policy_delta") or {})
            required = list(monitor_instruction.get("required_confirmations") or [])
            avoid_if = list(monitor_instruction.get("avoid_if") or [])
            tighten = (
                decision in {"avoid_rank1", "watch_rank1_with_tighter_gates", "no_trade"}
                or bool(entry_delta.get("tighten_confidence_threshold"))
            )
            out["strategy_adjustment_directives"] = {
                "playbook_action": {"action": "maintain", "target": None, "reason": reason},
                "entry_policy_action": {
                    "action": "tighten" if tighten else "maintain",
                    "target_fields": [
                        field
                        for field, enabled in (
                            ("confidence_threshold", entry_delta.get("tighten_confidence_threshold")),
                            ("previous_close_context", entry_delta.get("require_prev_close_context")),
                            ("cost_hurdle", entry_delta.get("require_cost_hurdle")),
                        )
                        if bool(enabled)
                    ][:6],
                    "reason": reason,
                },
                "monitor_focus_action": {
                    "action": "increase_focus" if required or avoid_if else "maintain",
                    "target_axes": _focus_axes_from_strings(" ".join(required), " ".join(avoid_if)),
                    "reason": reason,
                },
                "selected_symbol_bias_action": {
                    "action": "avoid_breakout"
                    if decision in {"avoid_rank1", "no_trade"}
                    else "prefer_reclaim"
                    if decision == "watch_rank1_with_tighter_gates"
                    else "none",
                    "reason": reason,
                },
                "refresh_action": {"action": "none", "reason": "Stage 2 review completed before monitor entry."},
            }
        out.setdefault(
            "strategy_refresh_trace",
            {
                "summary": reason,
                "bullets": [reason] if reason else [],
                "stages": [
                    {
                        "stage": "post_scanner_refresh",
                        "label": "Stage 2 selected-symbol tactical refresh",
                        "summary": reason,
                        "requested": True,
                        "effective": True,
                        "reason": decision,
                    }
                ],
            },
        )

    stage3 = dict(out.get("stale_intraday_hold_review") or {})
    if stage3:
        decision = str(stage3.get("hold_review_decision") or "").strip()
        reason = str(stage3.get("reason") or "stale intraday hold review").strip()
        if "strategy_adjustment_directives" not in out:
            out["strategy_adjustment_directives"] = {
                "playbook_action": {"action": "maintain", "target": None, "reason": reason},
                "entry_policy_action": {"action": "maintain", "target_fields": [], "reason": reason},
                "monitor_focus_action": {
                    "action": "increase_focus" if decision in {"tighten_exit", "exit_now"} else "maintain",
                    "target_axes": ["exit_axis"],
                    "reason": reason,
                },
                "selected_symbol_bias_action": {"action": "none", "reason": reason},
                "refresh_action": {
                    "action": "refresh_for_exit_axis_mismatch"
                    if decision in {"tighten_exit", "exit_now"}
                    else "refresh_for_holding",
                    "reason": reason,
                },
            }
        out.setdefault(
            "strategy_refresh_trace",
            {
                "summary": reason,
                "bullets": [reason] if reason else [],
                "stages": [
                    {
                        "stage": "stale_intraday_hold_review",
                        "label": "Stage 3 stale intraday hold review",
                        "summary": reason,
                        "requested": True,
                        "effective": True,
                        "reason": decision,
                    }
                ],
            },
        )

    stage4 = dict(out.get("end_of_day_carry_review") or {})
    if stage4:
        reason = str(stage4.get("risk_note") or "end-of-day carry review").strip()
        portfolio_level = str(stage4.get("portfolio_level_decision") or "").strip()
        carry_allowed = portfolio_level in {"carry_allowed", "carry_only_best_one"}
        out.setdefault(
            "strategy_horizon_feedback",
            {
                "strategy_horizon": "overnight_probe" if carry_allowed else "intraday",
                "exit_guidance": {
                    "allow_overnight": bool(carry_allowed),
                    "preferred_exit": "carry_review" if carry_allowed else "flatten_today",
                },
                "monitor_handoff": {
                    "hold_bias": "neutral_to_patient" if carry_allowed else "defensive",
                    "preferred_exit": "carry_review" if carry_allowed else "flatten_today",
                    "do_not_force_hold": True,
                },
            },
        )
        out.setdefault(
            "strategy_refresh_trace",
            {
                "summary": reason,
                "bullets": [reason] if reason else [],
                "stages": [
                    {
                        "stage": "end_of_day_carry_review",
                        "label": "Stage 4 end-of-day carry review",
                        "summary": reason,
                        "requested": True,
                        "effective": True,
                        "reason": portfolio_level,
                    }
                ],
            },
        )


def _stage_specific_role_boundary(call_kind: str) -> str:
    if call_kind == "selected_symbol_tactical_refresh":
        return (
            "You may recommend how to watch the Scanner-selected symbol and runner-ups, "
            "but you do not approve orders. Monitor calculates the final entry signal and Commander owns hard risk gates. "
        )
    if call_kind == "stale_intraday_hold_review":
        return (
            "You review an already-held intraday position for hold, tighter exit handling, or exit pressure, "
            "but you do not place or approve sell orders. Monitor and Commander retain hard exit authority. "
        )
    if call_kind == "end_of_day_carry_review":
        return (
            "You review held positions near the close for flatten/carry risk, "
            "but you do not bypass deterministic closeout, broker truth, weekend, or risk controls. "
        )
    return "Do not select final stock and do not produce order instructions. "


def _stage_specific_task_requirement(call_kind: str) -> str:
    if call_kind == "selected_symbol_tactical_refresh":
        return (
            "Your role is to compare Scanner rank #1 with compressed runner-ups, use selected_symbol_memory only as bounded symbol-specific evidence when memory is enabled, "
            "and output selected_symbol_decision, target_symbol, target_rank, runner_up_order, monitor_instruction, entry_policy_delta, memory_usage, commander_actionability, confidence, and reason. "
        )
    if call_kind == "stale_intraday_hold_review":
        return (
            "Your role is to review whether the held position thesis is still intact, whether exit pressure is rising, and whether Monitor should tighten exits or wait for the next check. "
            "Output hold_review_decision, exit_pressure, thesis_status, monitor_adjustment, priority_exit_triggers, next_check_minutes, and reason. "
        )
    if call_kind == "end_of_day_carry_review":
        return (
            "Your role is to review each held position near session close for carry risk versus same-day flattening. "
            "Output carry_review, portfolio_level_decision, and risk_note. "
        )
    return (
        "Your role is to choose exactly ONE playbook, provide a short rationale, produce a realistic and bounded monitor_entry_policy, propose tactical strategy detail, propose candidate_watch_policy, and produce explicit strategy_adjustment_directives that indicate what should change, what should be maintained, and why. "
    )


def _stage_specific_user_requirement(call_kind: str) -> str:
    if call_kind == "selected_symbol_tactical_refresh":
        return (
            "Decision requirements: return the Stage 2 selected-symbol tactical refresh contract only. "
            "Compare rank #1 and runner-ups in one call, decide whether to watch rank #1, avoid rank #1, tighten rank #1 gates, cascade to runner-ups, or no-trade. "
            "Do not output a direct BUY/SELL. "
        )
    if call_kind == "stale_intraday_hold_review":
        return (
            "Decision requirements: return the Stage 3 stale intraday hold review contract only. "
            "Decide hold, tighten_exit, exit_now, or wait_until_next_check using the held position thesis, net PnL, VWAP, drawdown, time decay, and market context. "
            "Keep the reason tied to the held symbol under review and do not attribute unrelated candidate or market theme labels to that position. "
            "Do not output a direct SELL order. "
        )
    if call_kind == "end_of_day_carry_review":
        return (
            "Decision requirements: return the Stage 4 end-of-day carry review contract only. "
            "For each held position decide carry_overnight, flatten_today, or reduce_or_flatten, then provide a portfolio-level carry decision. "
            "Do not bypass hard closeout, weekend, broker-truth, or risk controls. "
        )
    return (
        "Decision requirements: choose exactly ONE playbook, provide a short but concrete rationale, produce tactical_strategy, strategy_scores, rejected_strategy_reasons, candidate_watch_policy, a realistic and bounded monitor_entry_policy, and strategy_adjustment_directives that clearly state whether to maintain, tighten, relax, rebalance, deprioritize, prefer, or switch, which fields, axes, or playbooks are affected, and why this action is justified by deterministic evidence. "
    )


def _stage_specific_llm_contract(call_kind: str, base_contract: Dict[str, Any]) -> Dict[str, Any]:
    if call_kind == "selected_symbol_tactical_refresh":
        return {
            "selected_symbol_decision": "watch_rank1|avoid_rank1|watch_rank1_with_tighter_gates|cascade_to_runner_up|no_trade",
            "target_symbol": "005930",
            "target_rank": 1,
            "runner_up_order": ["000660", "035420"],
            "monitor_instruction": {
                "watch_intensity": "normal|strict|aggressive",
                "required_confirmations": ["vwap_reclaim", "net_cost_hurdle_pass", "volume_confirmation"],
                "avoid_if": ["fails_to_hold_vwap", "net_expected_edge_below_cost", "opening_gap_chase_without_pullback"],
            },
            "entry_policy_delta": {
                "tighten_confidence_threshold": False,
                "require_prev_close_context": True,
                "require_cost_hurdle": True,
            },
            "memory_usage": {
                "status": "used|disabled|insufficient|stale",
                "sample_count": 0,
                "confidence": "low|medium|high",
                "data_quality": "ok|stale|insufficient",
                "effect": "neutral|supportive|cautionary",
                "reason": "string",
            },
            "commander_actionability": "advisory_only|policy_delta_allowed|hard_block_recommended",
            "confidence": 0.0,
            "reason": "string",
        }
    if call_kind == "stale_intraday_hold_review":
        return {
            "hold_review_decision": "hold|tighten_exit|exit_now|wait_until_next_check",
            "exit_pressure": "low|medium|high",
            "thesis_status": "intact|weakened|broken",
            "monitor_adjustment": {
                "tighten_stop": True,
                "tighten_time_decay": True,
                "allow_profit_recovery_wait": False,
                "next_check_minutes": 5,
            },
            "priority_exit_triggers": ["vwap_breakdown", "time_decay"],
            "next_check_minutes": 5,
            "reason": "string",
        }
    if call_kind == "end_of_day_carry_review":
        return {
            "carry_review": [
                {
                    "symbol": "005930",
                    "decision": "carry_overnight|flatten_today|reduce_or_flatten",
                    "carry_confidence": "low|medium|high",
                    "required_next_day_plan": {
                        "gap_down_action": "exit_on_open|wait_first_5min|monitor_vwap",
                        "gap_up_action": "take_profit|trail|hold_if_vwap_supports",
                        "flat_open_action": "monitor_vwap_and_volume",
                    },
                    "reason": "string",
                }
            ],
            "portfolio_level_decision": "carry_allowed|flatten_all|carry_only_best_one",
            "risk_note": "string",
        }
    return base_contract


def _normalize_llm_overrides(raw: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    normalized = coerce_strategist_output(raw)
    allowed = {
        "market_regime",
        "market_sentiment",
        "key_events",
        "themes",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_priority",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "report_focus",
        "market_regime_summary",
        "policy_rationale",
        "confidence",
        "policy_source",
        "strategy_thesis",
        "strategy_delta_trace",
        "strategy_refresh_trace",
        "memory_usage_trace",
        "news_usage_trace",
        "scanner_handoff",
        "monitor_handoff",
        "conflict_analysis",
        "trade_permission_frame",
        "responsibility_boundary",
        "selected_symbol_tactical_review",
        "stale_intraday_hold_review",
        "end_of_day_carry_review",
    }
    out: Dict[str, Any] = {}
    for key in allowed:
        if key in raw and key not in {
            "strategy_thesis",
            "strategy_delta_trace",
            "strategy_refresh_trace",
            "memory_usage_trace",
            "news_usage_trace",
            "scanner_handoff",
            "monitor_handoff",
            "conflict_analysis",
            "trade_permission_frame",
            "responsibility_boundary",
        }:
            out[key] = normalized.get(key)
        elif key in raw and isinstance(raw.get(key), dict):
            out[key] = dict(raw.get(key) or {})
    if isinstance(raw.get("monitor_policy"), dict):
        out["monitor_policy"] = dict(raw.get("monitor_policy") or {})
    if isinstance(raw.get("monitor_entry_policy"), dict):
        out["monitor_entry_policy"] = dict(raw.get("monitor_entry_policy") or {})
    if isinstance(raw.get("policy_adjustment"), dict):
        out["policy_adjustment"] = dict(raw.get("policy_adjustment") or {})
    if isinstance(raw.get("strategy_adjustment_directives"), dict):
        out["strategy_adjustment_directives"] = dict(raw.get("strategy_adjustment_directives") or {})
    if isinstance(raw.get("strategy_scores"), dict):
        out["strategy_scores"] = dict(raw.get("strategy_scores") or {})
    if isinstance(raw.get("rejected_strategy_reasons"), dict):
        out["rejected_strategy_reasons"] = dict(raw.get("rejected_strategy_reasons") or {})
    if isinstance(raw.get("candidate_watch_policy"), dict):
        out["candidate_watch_policy"] = dict(raw.get("candidate_watch_policy") or {})
    if raw.get("tactical_strategy") not in (None, ""):
        out["tactical_strategy"] = str(raw.get("tactical_strategy") or "").strip().lower()
    if raw.get("tactical_subtype") not in (None, ""):
        out["tactical_subtype"] = str(raw.get("tactical_subtype") or "").strip().lower()
    if isinstance(raw.get("selected_themes"), list):
        out["selected_themes"] = _extract_theme_names_from_any(raw.get("selected_themes"))
    if isinstance(raw.get("theme_strategy"), dict):
        out["theme_strategy"] = dict(raw.get("theme_strategy") or {})
    stage2 = _normalize_stage2_selected_symbol_review(raw)
    if stage2:
        out["selected_symbol_tactical_review"] = dict(stage2)
        out["selected_symbol_decision"] = str(stage2.get("selected_symbol_decision") or "")
        out["target_symbol"] = str(stage2.get("target_symbol") or "")
        out["target_rank"] = int(stage2.get("target_rank") or 0)
        out["runner_up_order"] = list(stage2.get("runner_up_order") or [])
        out["monitor_instruction"] = dict(stage2.get("monitor_instruction") or {})
        out["entry_policy_delta"] = dict(stage2.get("entry_policy_delta") or {})
        out["memory_usage"] = dict(stage2.get("memory_usage") or {})
        out["commander_actionability"] = str(stage2.get("commander_actionability") or "")
    stage3 = _normalize_stage3_hold_review(raw)
    if stage3:
        out["stale_intraday_hold_review"] = dict(stage3)
        out["hold_review_decision"] = str(stage3.get("hold_review_decision") or "")
    stage4 = _normalize_stage4_carry_review(raw)
    if stage4:
        out["end_of_day_carry_review"] = dict(stage4)
        out["carry_review"] = list(stage4.get("carry_review") or [])
        out["portfolio_level_decision"] = str(stage4.get("portfolio_level_decision") or "")
    _derive_stage_specific_common_overrides(out)
    return out


_POLICY_ADJUSTMENT_COMPARE_FIELDS = (
    "timeframe_minutes",
    "breakout_lookback",
    "volume_lookback",
    "volume_ratio_min",
    "min_extended_from_vwap_pct",
    "max_extended_from_vwap_pct",
    "pullback_min_pct",
    "pullback_max_pct",
    "reclaim_tolerance_pct",
    "breakout_buffer_pct",
    "intent_cooldown_sec",
    "require_vwap_reclaim",
    "require_rebound",
)


def _summarize_monitor_entry_policy_for_adjustment(policy: Dict[str, Any]) -> Dict[str, Any]:
    src = dict(policy or {}) if isinstance(policy, dict) else {}
    threshold_policy = (
        dict(src.get("threshold_policy") or {})
        if isinstance(src.get("threshold_policy"), dict)
        else dict(src)
    )
    return {
        key: threshold_policy.get(key)
        for key in _POLICY_ADJUSTMENT_COMPARE_FIELDS
        if key in threshold_policy
    }


def _monitor_entry_policy_adjustment_delta_fields(
    baseline_summary: Dict[str, Any],
    current_summary: Dict[str, Any],
) -> List[str]:
    baseline = dict(baseline_summary or {}) if isinstance(baseline_summary, dict) else {}
    current = dict(current_summary or {}) if isinstance(current_summary, dict) else {}
    compare_keys = list(_POLICY_ADJUSTMENT_COMPARE_FIELDS)
    if baseline:
        compare_keys = [key for key in compare_keys if key in baseline and key in current]
    fields: List[str] = []
    for key in compare_keys:
        if key not in baseline and key not in current:
            continue
        if baseline.get(key) != current.get(key):
            fields.append(str(key))
    return fields


def _infer_policy_adjustment_direction(
    baseline_summary: Dict[str, Any],
    current_summary: Dict[str, Any],
) -> str:
    tighter = 0
    looser = 0
    baseline = dict(baseline_summary or {}) if isinstance(baseline_summary, dict) else {}
    current = dict(current_summary or {}) if isinstance(current_summary, dict) else {}
    higher_is_tighter = {"volume_ratio_min", "pullback_min_pct", "breakout_buffer_pct", "intent_cooldown_sec"}
    lower_is_tighter = {"max_extended_from_vwap_pct", "pullback_max_pct", "reclaim_tolerance_pct"}

    for key in higher_is_tighter:
        if key in baseline and key in current and baseline.get(key) != current.get(key):
            if float(current.get(key) or 0.0) > float(baseline.get(key) or 0.0):
                tighter += 1
            else:
                looser += 1
    for key in lower_is_tighter:
        if key in baseline and key in current and baseline.get(key) != current.get(key):
            if float(current.get(key) or 0.0) < float(baseline.get(key) or 0.0):
                tighter += 1
            else:
                looser += 1
    if "min_extended_from_vwap_pct" in baseline and "min_extended_from_vwap_pct" in current:
        if baseline.get("min_extended_from_vwap_pct") != current.get("min_extended_from_vwap_pct"):
            if float(current.get("min_extended_from_vwap_pct") or 0.0) > float(baseline.get("min_extended_from_vwap_pct") or 0.0):
                tighter += 1
            else:
                looser += 1

    if tighter and not looser:
        return "tighten"
    if looser and not tighter:
        return "relax"
    if tighter or looser:
        return "mixed"
    return "none"


def _symbol_memory_model_has_signal(model: Dict[str, Any]) -> bool:
    if not isinstance(model, dict) or not model:
        return False
    if int(model.get("trade_count") or 0) > 0:
        return True
    if int(model.get("closed_trade_count") or 0) > 0:
        return True
    if list(model.get("repeated_failure_pattern") or []):
        return True
    if list(model.get("recent_success_pattern") or []):
        return True
    if str(model.get("dominant_playbook") or "").strip().lower() not in ("", "unknown"):
        return True
    if str(model.get("dominant_monitor_blocker") or "").strip().lower() not in ("", "unknown"):
        return True
    if str(model.get("dominant_exit_reason") or "").strip().lower() not in ("", "unknown"):
        return True
    return False


def _build_symbol_refresh_memory_excerpt(
    selected_symbol: str,
    read_model_facts: Dict[str, Any] | None = None,
    reports_root: str | Path | None = None,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip().upper()
    facts = dict(read_model_facts or {}) if isinstance(read_model_facts, dict) else {}
    symbol_patterns = facts.get("symbol_patterns") if isinstance(facts.get("symbol_patterns"), dict) else {}
    model = dict(symbol_patterns.get(symbol) or {}) if isinstance(symbol_patterns.get(symbol), dict) else {}
    if not symbol:
        return {}
    if not _symbol_memory_model_has_signal(model):
        root = Path(str(reports_root or "").strip()) if str(reports_root or "").strip() else None
        if root is not None:
            trades_root = root / "trades" if root.name.lower() != "trades" else root
            try:
                persisted_model = build_symbol_read_model(str(trades_root), symbol, persisted_only=True)
            except TypeError:
                persisted_model = build_symbol_read_model(str(trades_root), symbol)
            if isinstance(persisted_model, dict) and _symbol_memory_model_has_signal(persisted_model):
                model = dict(persisted_model)
    if not _symbol_memory_model_has_signal(model):
        return {}

    repeated_failure_pattern = []
    for item in list(model.get("repeated_failure_pattern") or [])[:3]:
        if not isinstance(item, dict):
            continue
        repeated_failure_pattern.append(
            {
                "type": str(item.get("type") or "").strip(),
                "value": str(item.get("value") or "").strip(),
                "count": int(item.get("count") or 0),
            }
        )

    recent_success_pattern = []
    for item in list(model.get("recent_success_pattern") or [])[:2]:
        if not isinstance(item, dict):
            continue
        recent_success_pattern.append(
            {
                "playbook": str(item.get("playbook") or "").strip(),
                "entry_reason": str(item.get("entry_reason") or "").strip(),
                "exit_reason": str(item.get("exit_reason") or "").strip(),
                "count": int(item.get("count") or 0),
            }
        )

    data_quality = model.get("data_quality") if isinstance(model.get("data_quality"), dict) else {}
    return {
        "symbol": symbol,
        "trade_count": int(model.get("trade_count") or 0),
        "closed_trade_count": int(model.get("closed_trade_count") or 0),
        "win_rate": _round_optional(model.get("win_rate"), 4),
        "avg_pnl_pct": _round_optional(model.get("avg_pnl_pct"), 4),
        "avg_hold_duration_sec": _round_optional(model.get("avg_hold_duration_sec"), 2),
        "dominant_playbook": str(model.get("dominant_playbook") or ""),
        "dominant_monitor_blocker": str(model.get("dominant_monitor_blocker") or ""),
        "dominant_exit_reason": str(model.get("dominant_exit_reason") or ""),
        "repeated_failure_pattern": repeated_failure_pattern,
        "recent_success_pattern": recent_success_pattern,
        "data_quality": {
            "data_source": str(data_quality.get("data_source") or ""),
            "unknown_fields_ratio": _round_optional(data_quality.get("unknown_fields_ratio"), 4),
        },
    }



def _build_llm_commander_refresh_context(
    commander_context: Dict[str, Any],
    read_model_facts: Dict[str, Any] | None = None,
    reports_root: str | Path | None = None,
) -> Dict[str, Any]:
    context = dict(commander_context or {}) if isinstance(commander_context, dict) else {}
    open_position_refresh_context = (
        dict(context.get("open_position_refresh_context") or {})
        if isinstance(context.get("open_position_refresh_context"), dict)
        else {}
    )
    strategist_refresh_context = (
        dict(context.get("strategist_refresh_context") or {})
        if isinstance(context.get("strategist_refresh_context"), dict)
        else {}
    )
    refresh_context = (
        dict(open_position_refresh_context)
        if open_position_refresh_context
        else dict(strategist_refresh_context)
    )
    commander_horizon_policy = (
        dict(context.get("commander_horizon_policy") or {})
        if isinstance(context.get("commander_horizon_policy"), dict)
        else dict(strategist_refresh_context.get("commander_horizon_policy") or {})
        if isinstance(strategist_refresh_context.get("commander_horizon_policy"), dict)
        else dict(open_position_refresh_context.get("commander_horizon_policy") or {})
        if isinstance(open_position_refresh_context.get("commander_horizon_policy"), dict)
        else {}
    )
    selected_symbol = str(refresh_context.get("selected_symbol") or "")
    selected_symbol_was_rank1_raw = refresh_context.get("selected_symbol_was_rank1")
    selected_symbol_was_rank1 = (
        bool(selected_symbol_was_rank1_raw)
        if selected_symbol_was_rank1_raw is not None
        else int(refresh_context.get("selected_rank") or 0) == 1
    )
    return {
        "requested": bool(context.get("strategist_refresh_requested")),
        "reason": str(context.get("strategist_refresh_reason") or ""),
        "refresh_scope": str(refresh_context.get("refresh_scope") or ""),
        "selected_symbol": selected_symbol,
        "hold_repeat_count_max": int(refresh_context.get("hold_repeat_count_max") or 0),
        "selected_hold_repeat_count": int(refresh_context.get("selected_hold_repeat_count") or 0),
        "monitor_reason": str(refresh_context.get("monitor_reason") or ""),
        "active_exit_axis": str(refresh_context.get("active_exit_axis") or ""),
        "refresh_summary": str(refresh_context.get("refresh_summary") or ""),
        "selected_rank": int(refresh_context.get("selected_rank") or 0),
        "selected_score": _round_optional(refresh_context.get("selected_score"), 4),
        "scanner_primary_candidate": dict(refresh_context.get("scanner_primary_candidate") or {}),
        "actual_selected_candidate": dict(
            refresh_context.get("actual_selected_candidate")
            or refresh_context.get("scanner_primary_candidate")
            or {}
        ),
        "scanner_rank1_candidate": dict(refresh_context.get("scanner_rank1_candidate") or {}),
        "scanner_runner_ups": [
            dict(row)
            for row in list(refresh_context.get("scanner_runner_ups") or [])[:4]
            if isinstance(row, dict)
        ],
        "scanner_top_candidates": [
            dict(row)
            for row in list(refresh_context.get("scanner_top_candidates") or [])[:5]
            if isinstance(row, dict)
        ],
        "selected_symbol_was_rank1": bool(selected_symbol_was_rank1),
        "stage2_context_quality": str(refresh_context.get("stage2_context_quality") or ""),
        "stage2_context_quality_reasons": [
            str(reason or "")
            for reason in list(refresh_context.get("stage2_context_quality_reasons") or [])[:6]
            if str(reason or "").strip()
        ],
        "entry_state": dict(refresh_context.get("entry_state") or {}),
        "carry_state": str(refresh_context.get("carry_state") or context.get("carry_state") or ""),
        "carry_risk_bias": str(
            refresh_context.get("carry_risk_bias") or context.get("carry_risk_bias") or ""
        ),
        "carry_risk_reason": str(
            refresh_context.get("carry_risk_reason") or context.get("carry_risk_reason") or ""
        ),
        "session_open_recovery_assessment": dict(
            refresh_context.get("session_open_recovery_assessment")
            or context.get("session_open_recovery_assessment")
            or {}
        ),
        "prior_monitor_entry_policy_summary": dict(
            refresh_context.get("prior_monitor_entry_policy_summary")
            or strategist_refresh_context.get("prior_monitor_entry_policy_summary")
            or {}
        )
        if isinstance(
            refresh_context.get("prior_monitor_entry_policy_summary")
            or strategist_refresh_context.get("prior_monitor_entry_policy_summary"),
            dict,
        )
        else {},
        "current_monitor_entry_policy_summary": dict(
            refresh_context.get("current_monitor_entry_policy_summary")
            or strategist_refresh_context.get("current_monitor_entry_policy_summary")
            or {}
        )
        if isinstance(
            refresh_context.get("current_monitor_entry_policy_summary")
            or strategist_refresh_context.get("current_monitor_entry_policy_summary"),
            dict,
        )
        else {},
        "commander_horizon_policy": dict(commander_horizon_policy),
        "horizon_context": {
            "owner": str(commander_horizon_policy.get("owner") or "commander") if commander_horizon_policy else "",
            "strategy_horizon": str(commander_horizon_policy.get("strategy_horizon") or ""),
            "source_strategy_horizon": str(commander_horizon_policy.get("source_strategy_horizon") or ""),
            "observability_only": bool(commander_horizon_policy.get("observability_only", True))
            if commander_horizon_policy
            else True,
            "do_not_force_hold": bool(commander_horizon_policy.get("do_not_force_hold", True))
            if commander_horizon_policy
            else True,
        },
        "requires_policy_delta": bool(context.get("strategist_refresh_requested")),
        "selected_symbol_memory": _build_symbol_refresh_memory_excerpt(
            selected_symbol,
            read_model_facts,
            reports_root,
        ),
    }


def _normalize_policy_adjustment_surface(
    *,
    raw_adjustment: Any,
    baseline_summary: Dict[str, Any],
    current_summary: Dict[str, Any],
    refresh_requested: bool,
    recent_strategy_feedback: Dict[str, Any],
) -> Dict[str, Any]:
    raw = dict(raw_adjustment or {}) if isinstance(raw_adjustment, dict) else {}
    delta_fields = _monitor_entry_policy_adjustment_delta_fields(baseline_summary, current_summary)
    adjustment_required = (
        bool(raw.get("adjustment_required"))
        if raw.get("adjustment_required") is not None
        else bool(refresh_requested)
    )
    dominant_failure_pattern = str(raw.get("dominant_failure_pattern") or "").strip()
    if not dominant_failure_pattern:
        dominant_failure_pattern = str(((recent_strategy_feedback or {}).get("top_recent_weaknesses") or [""])[0] or "").strip()
    baseline_retained = bool(raw.get("baseline_retained")) if raw.get("baseline_retained") is not None else not bool(delta_fields)
    baseline_retained_reason = str(raw.get("baseline_retained_reason") or "").strip()
    if not baseline_retained_reason and baseline_retained:
        baseline_retained_reason = (
            "no_material_delta_from_baseline"
            if adjustment_required
            else "conservative_baseline_retained"
        )
    direction = str(raw.get("adjustment_direction") or "").strip().lower()
    if direction not in {"tighten", "relax", "mixed", "none"}:
        direction = _infer_policy_adjustment_direction(baseline_summary, current_summary)
    return {
        "adjustment_required": bool(adjustment_required),
        "baseline_retained": bool(baseline_retained),
        "baseline_retained_reason": baseline_retained_reason,
        "adjustment_direction": direction,
        "dominant_failure_pattern": dominant_failure_pattern,
        "addressed_failure_patterns": [str(x) for x in list(raw.get("addressed_failure_patterns") or []) if str(x or "").strip()][:8],
        "delta_fields": list(delta_fields),
        "delta_count": int(len(delta_fields)),
        "hold_refresh_considered": bool(refresh_requested),
        "baseline_summary": dict(baseline_summary or {}),
        "current_summary": dict(current_summary or {}),
    }


_PLAYBOOK_ACTIONS = {"maintain", "prefer", "deprioritize", "switch"}
_ENTRY_POLICY_ACTIONS = {"maintain", "tighten", "relax", "rebalance"}
_MONITOR_FOCUS_ACTIONS = {"maintain", "increase_focus", "decrease_focus", "shift_focus"}
_SELECTED_SYMBOL_BIAS_ACTIONS = {"none", "prefer_pullback", "avoid_breakout", "prefer_reclaim", "avoid_extension"}
_REFRESH_ACTIONS = {"none", "refresh_for_holding", "refresh_for_repeated_hold", "refresh_for_exit_axis_mismatch"}
_MONITOR_FOCUS_AXES = {"reclaim", "pullback", "volume", "breakout", "extension", "exit_axis"}
_GENERIC_DIRECTIVE_TOKENS = ("slightly", "carefully", "appropriately", "in general")


def _clean_directive_reason(value: Any, *, default: str) -> str:
    text = str(value or "").strip()
    if not text:
        return str(default or "").strip()
    lowered = text.lower()
    if any(token in lowered for token in _GENERIC_DIRECTIVE_TOKENS):
        return str(default or "").strip()
    return text


def _focus_axes_from_strings(*values: Any) -> List[str]:
    joined = " ".join(str(v or "").strip().lower() for v in values if str(v or "").strip())
    axes: List[str] = []
    mapping = (
        ("reclaim", ("reclaim", "vwap_reclaim")),
        ("pullback", ("pullback",)),
        ("volume", ("volume",)),
        ("breakout", ("breakout",)),
        ("extension", ("extended", "extension", "vwap")),
        ("exit_axis", ("drawdown", "exit_axis", "stop", "take_profit")),
    )
    for axis, needles in mapping:
        if any(token in joined for token in needles):
            axes.append(axis)
    seen: set[str] = set()
    out: List[str] = []
    for axis in axes:
        if axis in seen:
            continue
        seen.add(axis)
        out.append(axis)
    return out[:4]


def _normalize_strategy_adjustment_directives(
    *,
    raw_directives: Any,
    playbook: str,
    policy_adjustment: Dict[str, Any],
    commander_context: Dict[str, Any],
    strategy_memory: Dict[str, Any],
    selected_symbol_memory: Dict[str, Any],
) -> Dict[str, Any]:
    raw = dict(raw_directives or {}) if isinstance(raw_directives, dict) else {}
    memory_usage_disabled = _strategy_memory_usage_disabled(commander_context.get("commander_memory_policy"))
    if memory_usage_disabled:
        strategy_memory = {}
        selected_symbol_memory = {}
    refresh_context = (
        dict((commander_context.get("strategist_refresh_context") or {}))
        if isinstance(commander_context.get("strategist_refresh_context"), dict)
        else {}
    )
    refresh_reason = str(commander_context.get("strategist_refresh_reason") or "").strip().lower()
    delta_fields = [str(x) for x in list(policy_adjustment.get("delta_fields") or []) if str(x or "").strip()][:8]
    current_playbook = str(playbook or "").strip()
    best_playbooks = [str(x) for x in list(strategy_memory.get("best_playbooks") or []) if str(x or "").strip()]
    worst_playbooks = [str(x) for x in list(strategy_memory.get("worst_playbooks") or []) if str(x or "").strip()]
    dominant_blocker = str(selected_symbol_memory.get("dominant_monitor_blocker") or "").strip()
    repeated_failures = list(selected_symbol_memory.get("repeated_failure_pattern") or [])
    dominant_failure_pattern = str(policy_adjustment.get("dominant_failure_pattern") or "").strip()
    direction = str(policy_adjustment.get("adjustment_direction") or "none").strip().lower()

    playbook_default_action = "maintain"
    playbook_default_target = current_playbook or None
    playbook_default_reason = "결정적 메모리 근거가 약해 현재 플레이북을 유지합니다"
    if current_playbook and current_playbook in worst_playbooks:
        replacement = next((x for x in best_playbooks if x and x != current_playbook), "")
        if replacement:
            playbook_default_action = "switch"
            playbook_default_target = replacement
            playbook_default_reason = f"최근 메모리에서 {current_playbook} 성과가 약해 {replacement}로 전환합니다"
        else:
            playbook_default_action = "deprioritize"
            playbook_default_target = current_playbook
            playbook_default_reason = f"최근 메모리에서 {current_playbook} 성과가 약해 우선순위를 낮춥니다"
    elif current_playbook and current_playbook in best_playbooks:
        playbook_default_action = "prefer"
        playbook_default_target = current_playbook
        playbook_default_reason = f"최근 메모리에서 {current_playbook} 성과가 상대적으로 우세해 유지 우선합니다"

    entry_default_action = "maintain"
    if direction == "tighten":
        entry_default_action = "tighten"
    elif direction == "relax":
        entry_default_action = "relax"
    elif direction == "mixed":
        entry_default_action = "rebalance"
    entry_default_reason = (
        f"결정적 패턴이 {dominant_failure_pattern}로 반복돼 진입 조건을 {entry_default_action}합니다"
        if entry_default_action != "maintain" and dominant_failure_pattern
        else "결정적 메모리 근거가 약해 보수적 진입 기준을 유지합니다"
    )

    focus_axes_default = _focus_axes_from_strings(
        dominant_failure_pattern,
        dominant_blocker,
        str(refresh_context.get("monitor_reason") or ""),
        " ".join(str((row or {}).get("value") or "") for row in repeated_failures if isinstance(row, dict)),
    )
    monitor_focus_default_action = "increase_focus" if focus_axes_default else "maintain"
    monitor_focus_default_reason = (
        f"반복 실패 축이 {', '.join(focus_axes_default)}에 집중돼 해당 축 확인을 강화합니다"
        if focus_axes_default
        else "결정적 축 집중 근거가 약해 현재 모니터 초점을 유지합니다"
    )

    selected_bias_default_action = "none"
    selected_bias_default_reason = "선택 종목 편향 조정 근거가 약합니다"
    dominant_symbol_playbook = str(selected_symbol_memory.get("dominant_playbook") or "").strip().lower()
    if dominant_symbol_playbook == "pullback" and current_playbook != "pullback":
        selected_bias_default_action = "prefer_pullback"
        selected_bias_default_reason = "종목 메모리에서 pullback 성향이 우세해 눌림 우선으로 봅니다"
    elif "breakout" in dominant_blocker.lower() or any("breakout" in str((row or {}).get("value") or "").lower() for row in repeated_failures if isinstance(row, dict)):
        selected_bias_default_action = "avoid_breakout"
        selected_bias_default_reason = "종목 메모리에서 breakout 구조 불일치가 반복돼 추격 진입을 피합니다"
    elif "reclaim" in dominant_blocker.lower():
        selected_bias_default_action = "prefer_reclaim"
        selected_bias_default_reason = "종목 메모리에서 reclaim 확인 부족이 반복돼 reclaim 우선으로 봅니다"
    elif "extended" in dominant_blocker.lower() or "vwap" in dominant_blocker.lower():
        selected_bias_default_action = "avoid_extension"
        selected_bias_default_reason = "종목 메모리에서 과확장 진입 실패가 반복돼 extension 구간을 피합니다"

    refresh_default_action = "none"
    refresh_default_reason = "추가 refresh 지시가 필요하지 않습니다"
    if refresh_reason == "repeated_hold_monitor_only":
        refresh_default_action = "refresh_for_repeated_hold"
        refresh_default_reason = "반복 hold가 누적돼 보유 프레임 재평가가 필요합니다"
    elif bool(commander_context.get("strategist_refresh_requested")) and str(refresh_context.get("active_exit_axis") or "").strip():
        refresh_default_action = "refresh_for_exit_axis_mismatch"
        refresh_default_reason = "활성 exit 축과 현재 프레임 불일치 가능성을 재평가합니다"
    elif bool(commander_context.get("strategist_refresh_requested")):
        refresh_default_action = "refresh_for_holding"
        refresh_default_reason = "보유 상태 refresh 요청이 있어 현재 프레임을 재검토합니다"

    playbook_action_raw = dict(raw.get("playbook_action") or {}) if isinstance(raw.get("playbook_action"), dict) else {}
    entry_action_raw = dict(raw.get("entry_policy_action") or {}) if isinstance(raw.get("entry_policy_action"), dict) else {}
    monitor_focus_raw = dict(raw.get("monitor_focus_action") or {}) if isinstance(raw.get("monitor_focus_action"), dict) else {}
    selected_bias_raw = dict(raw.get("selected_symbol_bias_action") or {}) if isinstance(raw.get("selected_symbol_bias_action"), dict) else {}
    refresh_action_raw = dict(raw.get("refresh_action") or {}) if isinstance(raw.get("refresh_action"), dict) else {}

    playbook_action = str(playbook_action_raw.get("action") or playbook_default_action).strip().lower()
    if playbook_action not in _PLAYBOOK_ACTIONS:
        playbook_action = playbook_default_action
    playbook_target = str(playbook_action_raw.get("target") or (playbook_default_target or "")).strip() or None
    playbook_reason = _clean_directive_reason(
        playbook_action_raw.get("reason"),
        default=playbook_default_reason,
    )

    entry_policy_action = str(entry_action_raw.get("action") or entry_default_action).strip().lower()
    if entry_policy_action not in _ENTRY_POLICY_ACTIONS:
        entry_policy_action = entry_default_action
    target_fields = [str(x) for x in list(entry_action_raw.get("target_fields") or delta_fields) if str(x or "").strip()][:6]
    entry_reason = _clean_directive_reason(entry_action_raw.get("reason"), default=entry_default_reason)

    monitor_focus_action = str(monitor_focus_raw.get("action") or monitor_focus_default_action).strip().lower()
    if monitor_focus_action not in _MONITOR_FOCUS_ACTIONS:
        monitor_focus_action = monitor_focus_default_action
    target_axes = [str(x) for x in list(monitor_focus_raw.get("target_axes") or focus_axes_default) if str(x or "").strip() in _MONITOR_FOCUS_AXES][:4]
    monitor_focus_reason = _clean_directive_reason(monitor_focus_raw.get("reason"), default=monitor_focus_default_reason)

    selected_symbol_bias_action = str(selected_bias_raw.get("action") or selected_bias_default_action).strip().lower()
    if selected_symbol_bias_action not in _SELECTED_SYMBOL_BIAS_ACTIONS:
        selected_symbol_bias_action = selected_bias_default_action
    selected_symbol_bias_reason = _clean_directive_reason(
        selected_bias_raw.get("reason"),
        default=selected_bias_default_reason,
    )

    refresh_action = str(refresh_action_raw.get("action") or refresh_default_action).strip().lower()
    if refresh_action not in _REFRESH_ACTIONS:
        refresh_action = refresh_default_action
    refresh_reason_text = _clean_directive_reason(refresh_action_raw.get("reason"), default=refresh_default_reason)

    return {
        "playbook_action": {
            "action": playbook_action,
            "target": playbook_target,
            "reason": playbook_reason,
        },
        "entry_policy_action": {
            "action": entry_policy_action,
            "target_fields": list(target_fields),
            "reason": entry_reason,
        },
        "monitor_focus_action": {
            "action": monitor_focus_action,
            "target_axes": list(target_axes),
            "reason": monitor_focus_reason,
        },
        "selected_symbol_bias_action": {
            "action": selected_symbol_bias_action,
            "reason": selected_symbol_bias_reason,
        },
        "refresh_action": {
            "action": refresh_action,
            "reason": refresh_reason_text,
        },
    }


def _build_strategist_llm_messages(payload: Dict[str, Any]) -> List[Dict[str, str]]:
    memory_usage_disabled = _strategy_memory_usage_disabled(payload)
    call_kind = _resolve_strategist_llm_call_kind(payload)
    stage_instruction = (
        "This is Stage 2 selected-symbol tactical refresh. Keep the Stage 1 market frame unless the selected symbol and runner-up evidence clearly contradict it. Use selected_symbol_memory only for symbol-specific bias, policy delta, and monitor handoff. "
        if call_kind == "selected_symbol_tactical_refresh"
        else "This is Stage 3 stale intraday hold review. Focus on whether the open position still deserves HOLD, needs tighter exit handling, or needs an immediate exit review. Review only the held symbol from commander_refresh_context/current_position; do not borrow Stage 1 selected themes, runner-up themes, or unrelated candidate themes unless explicit held-symbol evidence says they apply. If held-symbol theme evidence is missing, say it is unavailable instead of naming a theme. "
        if call_kind == "stale_intraday_hold_review"
        else "This is Stage 4 end-of-day carry review. Focus on whether the position can be carried overnight or should be closed before session end, using carry risk and session context. "
        if call_kind == "end_of_day_carry_review"
        else "This is Stage 1 market strategy frame. Do not choose a final stock here; set market, theme, playbook, scanner, and monitor guidance only. Symbol-level memory is intentionally excluded at this stage. "
    )
    memory_system_instruction = (
        "Memory packets are temporarily disabled by Commander policy. "
        "Treat read_model_facts, recent_strategy_feedback, reporter_feedback_packet, strategy_memory, selected_symbol_memory, memory_packets, and commander_memory_policy as audit-only surfaces. "
        "Do not use memory fields to adjust playbook, selected themes, monitor_entry_policy, scanner guidance, monitor focus, or selected_symbol_bias_action. "
        "strategy_adjustment_directives must be based on current market, scanner, monitor, refresh, and risk evidence only. "
        if memory_usage_disabled
        else (
            "You MUST use the provided deterministic memory packets as primary constraints: read_model_facts, recent_strategy_feedback, reporter_feedback_packet, strategy_memory, selected_symbol_memory, memory_packets, commander_memory_policy. "
            "You MUST convert those inputs into explicit strategy adjustment directives. "
            "For Stage 1, use broad daily/weekly/monthly performance memory only and do not infer symbol-specific bias unless a selected-symbol refresh is requested. "
        )
        if call_kind == "market_strategy_frame"
        else (
            "You MUST use the provided deterministic memory packets as primary constraints: read_model_facts, recent_strategy_feedback, reporter_feedback_packet, strategy_memory, selected_symbol_memory, memory_packets, commander_memory_policy. "
            "You MUST convert those inputs into explicit strategy adjustment directives. "
        )
    )
    memory_user_instruction = (
        "Memory usage is temporarily disabled. Do not use any memory packet as a reason to change strategy, thresholds, themes, or symbol bias; mention memory only as disabled/audit-only if needed. "
        if memory_usage_disabled
        else (
            "The memory packets are not optional background. They are the main basis for strategic adjustment. "
            "Input packets: read_model_facts, recent_strategy_feedback, reporter_feedback_packet, strategy_memory, selected_symbol_memory, memory_packets, commander_memory_policy. "
        )
    )
    memory_sensitive_directives = (
        "Do not ignore repeated patterns across memory packets. "
        "If a playbook is consistently underperforming in the recent memory, you must deprioritize or switch it. "
        + (
            "Do not use selected_symbol_bias_action as a symbol-memory decision during Stage 1. "
            if call_kind == "market_strategy_frame"
            else "If a selected symbol shows repeated structural mismatch, you must reflect that in selected_symbol_bias_action. "
        )
        if not memory_usage_disabled
        else (
            "Ignore memory-derived performance, win-rate, loss, pattern, and symbol-history fields when choosing playbook, thresholds, themes, monitor focus, or symbol bias. "
        )
    )
    memory_user_directives = (
        "Do not ignore repeated patterns across memory packets. "
        "If symbol-level memory contradicts broad market memory, keep broad playbook stable but express symbol-specific bias separately. "
        if not memory_usage_disabled
        else (
            "Memory performance and symbol-history fields are hidden; do not reference weekly, monthly, symbol, win-rate, or loss memory as a reason. "
        )
    )
    system = (
        "You are the Strategist agent for an automated trading system. "
        "You must output a strategic frame only. "
        f"{_stage_specific_role_boundary(call_kind)}"
        f"{stage_instruction}"
        f"{memory_system_instruction}"
        "Do not merely summarize, restate, or lightly reference the inputs. "
        f"{_stage_specific_task_requirement(call_kind)}"
        "Return exactly one minified JSON object only. "
        "Do not add analysis, markdown, bullet points, or any text before or after the JSON. "
        "The first character must be { and the last character must be }. "
        "If deterministic evidence shows repeated NOOP-like blockage, you must decide whether entry conditions should be relaxed, tightened, or rebalanced. "
        "If deterministic evidence shows repeated false entries, stop-outs, or drawdown-heavy outcomes, you must tighten or rebalance policy. "
        "Use quant_context when present as deterministic observation-only evidence: it does not execute behavior by itself, but it should inform tactic fit, scorecard-aware caution, selected-symbol review, hold review, and carry review. "
        "Use memory_packets.*.operator_summary.tactic_lane_guidance when present as deterministic Q8 feedback: if vwap_reclaim_pullback is overused and weak, do not default to it; explicitly compare breakout or volume_breakout when shadow breakout-ready evidence exists; keep cost-edge guard promoted when shadow readiness recommends it. "
        "Use selected_symbol_news_signal and candidate_news_signal_summary when present: negative selected-symbol news must block relaxation unless chart/volume evidence is exceptional; positive selected-symbol news may support relaxation only when monitor and cost evidence are also ready. "
        f"{memory_sensitive_directives}"
        "If evidence is mixed or weak, explicitly maintain conservative baseline. "
        "strategy_adjustment_directives must be actionable, specific, and bounded. "
        "Do not output generic advice. "
        "Do not output passive observations without a concrete action. "
        "Every directive must include an action, a target or focus, and a short reason. "
        "When commander refresh context exists, separate the 1st/base frame, 2nd/post-scanner refresh, and final application result in strategy_refresh_trace. "
        "If confidence is low, default to conservative baseline. "
        "Do not hallucinate confidence. "
        "Infer confidence only from consistency and sufficiency of deterministic evidence. "
        "All human-readable sentences must be in Korean. "
        "Return JSON only."
    )
    base_contract = {
        "playbook": "breakout|pullback|reversal|defensive",
        "tactical_strategy": (
            "opening_gap_momentum|opening_range_breakout|vwap_reclaim_pullback|"
            "volume_breakout|reversal_reclaim|cost_aware_scalp|defensive_observe"
        ),
        "tactical_subtype": (
            "theme_confirmed_pullback|market_representative_pullback|liquidity_confirmed_pullback|"
            "vwap_reclaim_setup|weak_fallback_pullback|none"
        ),
        "strategy_scores": {
            "opening_gap_momentum": 0.0,
            "opening_range_breakout": 0.0,
            "vwap_reclaim_pullback": 0.0,
            "volume_breakout": 0.0,
            "reversal_reclaim": 0.0,
            "cost_aware_scalp": 0.0,
            "defensive_observe": 0.0,
        },
        "rejected_strategy_reasons": {
            "strategy_name": "short reason why this tactical strategy was not selected"
        },
        "candidate_watch_policy": {
            "max_priority_rank": 5,
            "max_runner_ups": 4,
            "cascade_enabled": True,
            "cascade_allowed_reasons": [
                "too_extended_from_vwap",
                "breakout_not_ready",
                "volume_insufficient",
                "volume_confirmation_missing",
                "below_vwap_reclaim_not_ready",
                "pullback_below_vwap_reclaim_not_ready",
                "pullback_not_mature",
            ],
            "cascade_blocked_reasons": [
                "cost_filter_failed",
                "risk_policy_block",
                "closeout_window",
                "open_position_present",
                "daily_loss_limit",
                "broker_truth_mismatch",
                "data_quality_guard",
            ],
            "reason": "string",
        },
        "selected_themes": ["string from available_themes only when available"],
        "theme_strategy": {
            "selection_mode": "kiwoom_api_constrained|fallback",
            "selected_themes": [
                {
                    "theme": "string",
                    "playbook_overlay": "momentum|pullback|reversal|defensive|fallback",
                    "scanner_directive": "string",
                    "reason": "string",
                }
            ],
            "fallback_reason": "string",
        },
        "rationale": "string",
        "monitor_entry_policy": {
            "enabled": True,
            "timeframe_minutes": 1,
            "breakout_lookback": 5,
            "volume_lookback": 5,
            "volume_ratio_min": 0.68,
            "min_extended_from_vwap_pct": -0.02,
            "max_extended_from_vwap_pct": 0.13,
            "pullback_min_pct": 0.008,
            "pullback_max_pct": 0.07,
            "reclaim_tolerance_pct": 0.0015,
            "breakout_buffer_pct": 0.0,
            "intent_cooldown_sec": 60,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        "strategy_adjustment_directives": {
            "playbook_action": {
                "action": "maintain|prefer|deprioritize|switch",
                "target": "string|null",
                "reason": "string",
            },
            "entry_policy_action": {
                "action": "maintain|tighten|relax|rebalance",
                "target_fields": ["string"],
                "reason": "string",
            },
            "monitor_focus_action": {
                "action": "maintain|increase_focus|decrease_focus|shift_focus",
                "target_axes": ["reclaim", "pullback", "volume", "breakout", "extension", "exit_axis"],
                "reason": "string",
            },
            "selected_symbol_bias_action": {
                "action": "none|prefer_pullback|avoid_breakout|prefer_reclaim|avoid_extension",
                "reason": "string",
            },
            "refresh_action": {
                "action": "none|refresh_for_holding|refresh_for_repeated_hold|refresh_for_exit_axis_mismatch",
                "reason": "string",
            },
        },
        "strategy_refresh_trace": {
            "summary": "string",
            "bullets": ["string"],
            "stages": [
                {
                    "stage": "initial_frame|post_scanner_refresh|final_application",
                    "label": "string",
                    "summary": "string",
                    "requested": True,
                    "effective": False,
                    "reason": "string",
                }
            ],
        },
        "strategy_horizon_feedback": {
            "strategy_horizon": "one_of:scalp,intraday,overnight_probe,1_2day_swing",
            "expected_hold_window": {"min_sec": 300, "target_sec": 1800, "max_sec": 14400},
            "exit_guidance": {
                "profit_take_style": "trail_after_first_push",
                "allow_early_exit": True,
                "early_exit_allowed_reasons": ["hard_stop", "liquidity_collapse", "market_regime_flip"],
                "avoid_early_exit_reasons": ["small_noise_pullback", "minor_profit_without_momentum_loss"],
            },
            "invalidation_conditions": ["string"],
            "monitor_handoff": {
                "hold_bias": "neutral|neutral_to_patient|defensive",
                "preferred_exit": "string",
                "do_not_force_hold": True,
            },
        },
    }
    contract = _stage_specific_llm_contract(call_kind, base_contract)
    user = (
        (
            "Use the provided market context and candidate hints. "
            if memory_usage_disabled
            else "Use the provided market context, candidate hints, and deterministic memory packets. "
        )
        + f"{memory_user_instruction}"
        f"{_stage_specific_user_requirement(call_kind)}"
        "Prefer changing strategy only when deterministic evidence supports it. "
        "Prefer maintaining current baseline when evidence is weak or mixed. "
        "Do not overreact to a single trade. "
        f"{memory_user_directives}"
        "Do not produce narrative summary in place of directives. "
        "Do not collapse strategist refresh into one generic summary; strategy_refresh_trace must distinguish 1st/base frame, 2nd/post-scanner refresh, and final application. "
        "For strategy_horizon_feedback.strategy_horizon, choose exactly one enum value: scalp, intraday, overnight_probe, or 1_2day_swing. Never return the pipe-delimited placeholder. "
        "If available_themes is non-empty, selected_themes must be chosen only from available_themes.theme. "
        "If available_themes is empty, selected_themes must stay empty; fallback_theme_hints are context only and must not be treated as tradable Kiwoom themes. "
        "Do not invent tradable theme names outside Kiwoom available_themes; abstract labels may appear only in rationale or fallback_reason. "
        "Scanner directives must describe how to rank symbols inside selected Kiwoom theme components, not name a final stock. "
        "candidate_watch_policy is a proposal only; Commander owns final executable entry_control and may clamp the proposed watch depth. "
        "Avoid vague terms such as slightly, carefully, appropriately, or in general. "
        "Use explicit, bounded, implementable language. "
        "If repeated failure is concentrated in one axis, reflect that axis in monitor_focus_action. "
        "Reply with JSON only. No prose.\n"
        "JSON contract:\n"
        f"{json.dumps(contract, ensure_ascii=False)}\n\n"
        "Input:\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _compact_news_sample_for_llm(sample: Any, *, max_symbols: int = 6, max_titles: int = 2, max_title_len: int = 160) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if not isinstance(sample, dict):
        return out
    for symbol, value in list(sample.items())[:max_symbols]:
        if not isinstance(value, dict):
            continue
        rows = value.get("sample") if isinstance(value.get("sample"), list) else []
        titles: List[str] = []
        for row in rows[:max_titles]:
            if isinstance(row, dict):
                title = str(row.get("title") or "").strip()
            else:
                title = str(row or "").strip()
            if not title:
                continue
            if len(title) > max_title_len:
                title = title[: max_title_len - 3] + "..."
            titles.append(title)
        out[str(symbol)] = {
            "count": int(value.get("count") or len(rows)),
            "titles": titles,
        }
    return out


def _round_optional(value: Any, digits: int = 4) -> Any:
    try:
        return round(float(value), int(digits))
    except Exception:
        return value


def _compact_global_signal_for_llm(signal: Any) -> Dict[str, Any]:
    src = signal if isinstance(signal, dict) else {}
    index_moves = src.get("index_moves") if isinstance(src.get("index_moves"), dict) else {}
    macro_moves = src.get("macro_moves") if isinstance(src.get("macro_moves"), dict) else {}
    fear_index = src.get("fear_index") if isinstance(src.get("fear_index"), dict) else {}
    korea_indices = src.get("korea_indices") if isinstance(src.get("korea_indices"), dict) else {}
    korea_rows = korea_indices.get("indices") if isinstance(korea_indices.get("indices"), dict) else {}
    macro_indicators = src.get("macro_indicators") if isinstance(src.get("macro_indicators"), dict) else {}
    indicator_rows = macro_indicators.get("indicators") if isinstance(macro_indicators.get("indicators"), dict) else {}

    def _compact_korea_index(name: str) -> Dict[str, Any]:
        row = korea_rows.get(name) if isinstance(korea_rows.get(name), dict) else {}
        if not row:
            return {}
        return {
            "current": _round_optional(row.get("current"), 2),
            "previous_close": _round_optional(row.get("previous_close"), 2),
            "change_pct": _round_optional(row.get("change_pct"), 3),
            "change": _round_optional(row.get("change"), 2),
            "current_date": str(row.get("current_date") or ""),
            "previous_date": str(row.get("previous_date") or ""),
        }

    return {
        "score": _round_optional(src.get("score"), 4),
        "status": str(src.get("status") or ""),
        "source": str(src.get("source") or ""),
        "index_moves": {
            "sp500_pct": _round_optional(index_moves.get("sp500_pct"), 3),
            "nasdaq_pct": _round_optional(index_moves.get("nasdaq_pct"), 3),
            "dow_pct": _round_optional(index_moves.get("dow_pct"), 3),
            "kospi_pct": _round_optional(index_moves.get("kospi_pct"), 3),
            "kosdaq_pct": _round_optional(index_moves.get("kosdaq_pct"), 3),
        },
        "korea_indices": {
            "source": str(korea_indices.get("source") or ""),
            "status": str(korea_indices.get("status") or ""),
            "average_change_pct": _round_optional(korea_indices.get("average_change_pct"), 3),
            "breadth": _round_optional(korea_indices.get("breadth"), 3),
            "indices": {
                "KOSPI": _compact_korea_index("KOSPI"),
                "KOSDAQ": _compact_korea_index("KOSDAQ"),
            },
        },
        "macro_moves": {
            "vix_pct": _round_optional(macro_moves.get("vix_pct"), 3),
            "vix_level": _round_optional(macro_moves.get("vix_level"), 2),
            "vix_level_pressure": _round_optional(macro_moves.get("vix_level_pressure"), 3),
            "dxy_pct": _round_optional(macro_moves.get("dxy_pct"), 3),
            "tnx_delta": _round_optional(macro_moves.get("tnx_delta"), 4),
        },
        "fear_index": {
            "level": _round_optional(fear_index.get("level"), 2),
            "change_pct": _round_optional(fear_index.get("change_pct"), 3),
            "level_pressure": _round_optional(fear_index.get("level_pressure"), 3),
        },
        "macro_indicators": {
            key: {
                "status": str((row or {}).get("status") or ""),
                "current": _round_optional((row or {}).get("current"), 4),
                "previous": _round_optional((row or {}).get("previous"), 4),
                "change_pct": _round_optional((row or {}).get("change_pct"), 4),
                "delta": _round_optional((row or {}).get("delta"), 5),
                "current_yield_pct": _round_optional((row or {}).get("current_yield_pct"), 5),
                "role": str((row or {}).get("role") or ""),
                "source": str((row or {}).get("source") or ""),
                "ticker": str((row or {}).get("ticker") or ""),
                "reason": str((row or {}).get("reason") or ""),
            }
            for key, row in indicator_rows.items()
            if isinstance(row, dict)
            and key
            in {
                "kr_3y_yield",
                "kr_10y_yield",
                "us_2y_yield",
                "us_10y_yield",
                "usdkrw",
                "dxy",
                "eurusd",
                "usdcny",
                "usdjpy",
                "kospi",
                "sp500",
                "nasdaq",
            }
        },
    }


def _compact_top_metric_map(raw: Any, *, max_items: int = 4) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    rows: List[tuple[str, float]] = []
    for key, value in raw.items():
        name = str(key or "").strip()
        if not name:
            continue
        try:
            metric = float(value)
        except Exception:
            metric = 0.0
        rows.append((name, metric))
    rows.sort(key=lambda item: (-item[1], item[0]))
    out: Dict[str, Any] = {}
    for name, metric in rows[: max(0, int(max_items))]:
        out[name] = _round_optional(metric, 4)
    return out


def _compact_performance_summary_map(raw: Any, *, max_items: int = 3) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    rows: List[tuple[str, float, Dict[str, Any]]] = []
    for key, value in raw.items():
        name = str(key or "").strip()
        item = value if isinstance(value, dict) else {}
        if not name:
            continue
        priority = 0.0
        if isinstance(item, dict):
            priority = float(item.get("appearance_count") or item.get("trade_count_total") or 0.0)
        rows.append((name, priority, item))
    rows.sort(key=lambda item: (-item[1], item[0]))
    out: Dict[str, Any] = {}
    for name, _priority, item in rows[: max(0, int(max_items))]:
        out[name] = {
            "appearance_count": int(item.get("appearance_count") or 0),
            "win_rate": _round_optional(item.get("win_rate"), 4),
            "avg_return": _round_optional(item.get("avg_return"), 4),
        }
    return out


def _compact_recent_strategy_feedback_for_llm(feedback: Any) -> Dict[str, Any]:
    src = feedback if isinstance(feedback, dict) else {}
    return {
        "feedback_window_size": int(src.get("feedback_window_size") or 0),
        "top_recent_strengths": [str(x or "") for x in list(src.get("top_recent_strengths") or [])[:3]],
        "top_recent_weaknesses": [str(x or "") for x in list(src.get("top_recent_weaknesses") or [])[:4]],
        "recent_reporter_summary": [str(x or "") for x in list(src.get("recent_reporter_summary") or [])[:2]],
        "suggested_report_focus": [str(x or "") for x in list(src.get("suggested_report_focus") or [])[:4]],
        "recent_theme_performance": _compact_performance_summary_map(src.get("recent_theme_performance"), max_items=3),
        "recent_playbook_performance": _compact_performance_summary_map(src.get("recent_playbook_performance"), max_items=3),
        "advisory_only": bool(src.get("advisory_only", True)),
    }


def _load_reporter_feedback_packet(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    def _load_source_packet() -> Dict[str, Any]:
        src = state.get("strategist_feedback_packet")
        if not isinstance(src, dict):
            src = state.get("reporter_feedback_packet")
        if isinstance(src, dict) and src:
            return dict(src)

        reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")
        day = str(policy.get("reporter_feedback_day") or state.get("day") or _resolve_state_day(state)).strip()
        try:
            packet = build_strategist_feedback_packet(
                mode="strategist_feedback",
                payload={"day": day},
                reports_root=reports_root,
                day=day,
            )
        except Exception:
            return {}
        return dict(packet or {})

    def _normalize_mode(value: Any) -> str:
        mode = str(value or "").strip().lower()
        return mode if mode in {"auto", "enabled", "disabled"} else "auto"

    def _empty_feedback_packet(
        *,
        mode: str,
        mode_source: str,
        status: str,
        gate_reason: str,
        source_status: str = "",
        source_available: bool = False,
    ) -> Dict[str, Any]:
        return {
            "available": False,
            "status": str(status or "disabled"),
            "advisory_only": True,
            "feedback_mode": "deterministic",
            "confidence": "none",
            "insight_summary": "",
            "dominant_patterns": [],
            "blocker_analysis": [],
            "route_analysis": {},
            "recommendation": [],
            "reporter_feedback_mode": str(mode or "auto"),
            "reporter_feedback_mode_source": str(mode_source or "default_auto"),
            "consumed": False,
            "feedback_gate_reason": str(gate_reason or ""),
            "source_status": str(source_status or ""),
            "source_available": bool(source_available),
            "data_freshness": {},
        }

    def _resolve_mode() -> Tuple[str, str]:
        applied_policy = state.get("applied_policy")
        applied_policy = applied_policy if isinstance(applied_policy, dict) else {}
        applied_policy_strategist = applied_policy.get("strategist")
        applied_policy_strategist = applied_policy_strategist if isinstance(applied_policy_strategist, dict) else {}
        strategist_runtime_input = state.get("strategist_runtime_input")
        strategist_runtime_input = strategist_runtime_input if isinstance(strategist_runtime_input, dict) else {}

        candidates = [
            (
                applied_policy_strategist.get("reporter_feedback_mode"),
                str(applied_policy_strategist.get("reporter_feedback_mode_source") or "commander_applied_policy"),
                "commander_applied_policy",
            ),
            (
                applied_policy.get("reporter_feedback_mode"),
                str(applied_policy.get("reporter_feedback_mode_source") or "applied_policy_fallback"),
                "applied_policy_fallback",
            ),
            (
                state.get("reporter_feedback_mode"),
                str(state.get("reporter_feedback_mode_source") or "state_fallback"),
                "state_fallback",
            ),
            (
                strategist_runtime_input.get("reporter_feedback_mode"),
                "legacy_fallback",
                "legacy_fallback",
            ),
            (
                policy.get("reporter_feedback_mode"),
                "legacy_fallback",
                "legacy_fallback",
            ),
        ]
        for raw_value, source_hint, default_source in candidates:
            if raw_value not in (None, ""):
                return _normalize_mode(raw_value), str(source_hint or default_source)
        return "auto", "default_auto"

    feedback_mode, feedback_mode_source = _resolve_mode()
    if feedback_mode == "disabled":
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="disabled",
            gate_reason="mode_disabled",
        )

    src = _load_source_packet()
    if not src:
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="missing",
            gate_reason="no_packet",
        )

    out = dict(src)
    out["available"] = bool(src.get("available"))
    out["status"] = str(src.get("status") or "ok")
    out["advisory_only"] = True
    out["feedback_mode"] = str(src.get("feedback_mode") or "deterministic")
    out["confidence"] = str(src.get("confidence") or "none")
    out["insight_summary"] = str(src.get("insight_summary") or "")
    out["dominant_patterns"] = list(src.get("dominant_patterns") or [])
    out["blocker_analysis"] = list(src.get("blocker_analysis") or [])
    out["route_analysis"] = dict(src.get("route_analysis") or {})
    out["recommendation"] = [str(x or "") for x in list(src.get("recommendation") or []) if str(x or "").strip()][:4]
    out["data_freshness"] = dict(src.get("data_freshness") or {})
    out["reporter_feedback_mode"] = feedback_mode
    out["reporter_feedback_mode_source"] = feedback_mode_source
    out["source_status"] = str(src.get("status") or "ok")
    out["source_available"] = bool(src.get("available"))
    out["consumed"] = False
    out["feedback_gate_reason"] = ""

    if feedback_mode == "enabled":
        if bool(out.get("available")):
            out["consumed"] = True
            out["feedback_gate_reason"] = "mode_enabled"
            return out
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="unavailable",
            gate_reason="source_unavailable",
            source_status=str(src.get("status") or "unavailable"),
            source_available=bool(src.get("available")),
        )

    freshness = out.get("data_freshness") if isinstance(out.get("data_freshness"), dict) else {}
    freshness_status = str(freshness.get("freshness_status") or "").strip().lower()
    stale = bool(freshness.get("stale")) or freshness_status == "stale"
    confidence_raw = src.get("confidence")
    confidence_text = str(confidence_raw or "none").strip().lower()
    confidence_numeric = _round_optional(confidence_raw, 4) if confidence_raw not in (None, "") else None
    confidence_ok = confidence_text in {"medium", "high"} or (
        isinstance(confidence_numeric, (int, float)) and float(confidence_numeric) >= 0.5
    )
    route_analysis = out.get("route_analysis") if isinstance(out.get("route_analysis"), dict) else {}
    route_selected_total = dict(route_analysis.get("route_selected_total") or {})
    relevant = bool(
        str(out.get("insight_summary") or "").strip()
        or list(out.get("dominant_patterns") or [])
        or list(out.get("blocker_analysis") or [])
        or list(out.get("recommendation") or [])
        or route_selected_total
        or route_analysis
    )
    if not bool(out.get("available")):
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="auto_ignored",
            gate_reason="source_unavailable",
            source_status=str(src.get("status") or "unavailable"),
            source_available=False,
        )
    if stale:
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="auto_ignored",
            gate_reason="stale",
            source_status=str(src.get("status") or "ok"),
            source_available=True,
        )
    if not confidence_ok:
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="auto_ignored",
            gate_reason="low_confidence",
            source_status=str(src.get("status") or "ok"),
            source_available=True,
        )
    if not relevant:
        return _empty_feedback_packet(
            mode=feedback_mode,
            mode_source=feedback_mode_source,
            status="auto_ignored",
            gate_reason="not_relevant",
            source_status=str(src.get("status") or "ok"),
            source_available=True,
        )
    out["consumed"] = True
    out["feedback_gate_reason"] = "auto_accepted"
    return out


def _compact_reporter_feedback_for_llm(packet: Any) -> Dict[str, Any]:
    src = packet if isinstance(packet, dict) else {}
    route_analysis = src.get("route_analysis") if isinstance(src.get("route_analysis"), dict) else {}
    blocker_analysis = list(src.get("blocker_analysis") or [])
    dominant_patterns = list(src.get("dominant_patterns") or [])
    return {
        "available": bool(src.get("available")),
        "status": str(src.get("status") or ""),
        "feedback_mode": str(src.get("feedback_mode") or "deterministic"),
        "reporter_feedback_mode": str(src.get("reporter_feedback_mode") or "auto"),
        "reporter_feedback_mode_source": str(src.get("reporter_feedback_mode_source") or "default_auto"),
        "consumed": bool(src.get("consumed")),
        "feedback_gate_reason": str(src.get("feedback_gate_reason") or ""),
        "confidence": str(src.get("confidence") or "none"),
        "insight_summary": str(src.get("insight_summary") or "")[:240],
        "route_analysis": {
            "route_source": str(route_analysis.get("route_source") or ""),
            "route_selected_total": dict(route_analysis.get("route_selected_total") or {}),
            "monitor_only_ratio": _round_optional(route_analysis.get("monitor_only_ratio"), 4),
            "cached_strategist_ratio": _round_optional(route_analysis.get("cached_strategist_ratio"), 4),
            "full_cycle_ratio": _round_optional(route_analysis.get("full_cycle_ratio"), 4),
        },
        "blocker_analysis": [
            {
                "blocker": str((item or {}).get("blocker") or ""),
                "count": int((item or {}).get("count") or 0),
                "ratio": _round_optional((item or {}).get("ratio"), 4),
            }
            for item in blocker_analysis[:3]
            if isinstance(item, dict)
        ],
        "dominant_patterns": [
            {
                "name": str((item or {}).get("name") or ""),
                "value": (item or {}).get("value"),
                "detail": str((item or {}).get("detail") or ""),
            }
            for item in dominant_patterns[:4]
            if isinstance(item, dict)
        ],
        "recommendation": [str(x or "") for x in list(src.get("recommendation") or [])[:3] if str(x or "").strip()],
        "advisory_only": True,
    }


def _compact_strategy_memory_for_llm(memory: Any) -> Dict[str, Any]:
    src = memory if isinstance(memory, dict) else {}
    market_bias = src.get("market_condition_bias") if isinstance(src.get("market_condition_bias"), dict) else {}
    reporter_digest = src.get("reporter_analysis_digest") if isinstance(src.get("reporter_analysis_digest"), dict) else {}
    playbook_snapshot_src = (
        src.get("playbook_performance_snapshot")
        if isinstance(src.get("playbook_performance_snapshot"), dict)
        else {}
    )
    playbook_snapshot: Dict[str, Any] = {}
    for key, value in list(playbook_snapshot_src.items())[:4]:
        item = value if isinstance(value, dict) else {}
        playbook_snapshot[str(key)] = {
            "usage_count": int(item.get("usage_count") or 0),
            "win_rate": _round_optional(item.get("win_rate"), 4),
            "avg_return": _round_optional(item.get("avg_return"), 4),
            "stability_score": _round_optional(item.get("stability_score"), 4),
        }
    pattern_snapshot = _compact_pattern_performance_for_llm(src.get("pattern_performance_snapshot"))
    preferred_regimes = [
        str(x or "")
        for x in list(market_bias.get("preferred_regimes") or [])[:3]
        if str(x or "").strip()
    ]
    avoid_regimes = [
        str(x or "")
        for x in list(market_bias.get("avoid_regimes") or [])[:3]
        if str(x or "").strip()
    ]
    return {
        "status": str(src.get("status") or ""),
        "day": str(src.get("day") or ""),
        "best_playbooks": [str(x or "") for x in list(src.get("best_playbooks") or [])[:3] if str(x or "").strip()],
        "worst_playbooks": [str(x or "") for x in list(src.get("worst_playbooks") or [])[:3] if str(x or "").strip()],
        "recent_failures": [str(x or "") for x in list(src.get("recent_failures") or [])[:4] if str(x or "").strip()],
        "recent_success_patterns": [
            str(x or "")
            for x in list(src.get("recent_success_patterns") or [])[:4]
            if str(x or "").strip()
        ],
        "market_condition_bias": {
            "preferred_regimes": preferred_regimes,
            "avoid_regimes": avoid_regimes,
        },
        "playbook_performance_snapshot": playbook_snapshot,
        "pattern_performance_snapshot": pattern_snapshot,
        "reporter_analysis_digest": {
            "available": bool(reporter_digest.get("available")),
            "ai_run_grade": str(reporter_digest.get("ai_run_grade") or ""),
            "ai_summary": str(reporter_digest.get("ai_summary") or "")[:220],
            "top_improvement_suggestions": [str(x or "") for x in list(reporter_digest.get("top_improvement_suggestions") or [])[:3] if str(x or "").strip()],
            "recommended_actions": [str(x or "") for x in list(reporter_digest.get("recommended_actions") or [])[:3] if str(x or "").strip()],
            "dominant_risks": [str(x or "") for x in list(reporter_digest.get("dominant_risks") or [])[:3] if str(x or "").strip()],
            "system_health": str(reporter_digest.get("system_health") or ""),
            "report_focus_targets": [str(x or "") for x in list(reporter_digest.get("report_focus_targets") or [])[:4] if str(x or "").strip()],
            "scanner_selection_status": str(reporter_digest.get("scanner_selection_status") or ""),
            "monitor_status": str(reporter_digest.get("monitor_status") or ""),
            "top_monitor_reasons": [str(x or "") for x in list(reporter_digest.get("top_monitor_reasons") or [])[:4] if str(x or "").strip()],
            "top_scanner_sources": [str(x or "") for x in list(reporter_digest.get("top_scanner_sources") or [])[:3] if str(x or "").strip()],
            "top_supervisor_blockers": [str(x or "") for x in list(reporter_digest.get("top_supervisor_blockers") or [])[:3] if str(x or "").strip()],
            "incident_total": int(reporter_digest.get("incident_total") or 0),
            "route_mix": {
                "route_selected_total": dict(((reporter_digest.get("route_mix") or {}).get("route_selected_total") or {})),
                "monitor_only_ratio": _round_optional((reporter_digest.get("route_mix") or {}).get("monitor_only_ratio"), 4),
                "cached_strategist_ratio": _round_optional((reporter_digest.get("route_mix") or {}).get("cached_strategist_ratio"), 4),
                "full_cycle_ratio": _round_optional((reporter_digest.get("route_mix") or {}).get("full_cycle_ratio"), 4),
                "route_source": str(((reporter_digest.get("route_mix") or {}).get("route_source") or "")),
            },
        },
        "advisory_only": bool(src.get("advisory_only", True)),
    }


def _compact_pattern_performance_for_llm(snapshot: Any) -> Dict[str, Any]:
    src = snapshot if isinstance(snapshot, dict) else {}
    out: Dict[str, Any] = {}
    for section, limit in (
        ("entry_pattern_types", 4),
        ("exit_pattern_types", 4),
        ("entry_exit_combos", 5),
    ):
        section_rows = src.get(section) if isinstance(src.get(section), dict) else {}
        compact_rows: Dict[str, Any] = {}
        for key, value in list(section_rows.items())[:limit]:
            item = value if isinstance(value, dict) else {}
            compact_rows[str(key)] = {
                "trade_count": int(item.get("trade_count") or 0),
                "win_rate": _round_optional(item.get("win_rate"), 4),
                "avg_return": _round_optional(item.get("avg_return"), 4),
                "symbols": [str(x or "") for x in list(item.get("symbols") or [])[:4] if str(x or "").strip()],
            }
        out[section] = compact_rows
    out["problem_patterns"] = [
        str(x or "") for x in list(src.get("problem_patterns") or [])[:6] if str(x or "").strip()
    ]
    out["working_patterns"] = [
        str(x or "") for x in list(src.get("working_patterns") or [])[:4] if str(x or "").strip()
    ]
    return out


def _news_signal_label(score: Any) -> str:
    value = _to_float(score, 0.0)
    if value >= 0.25:
        return "positive"
    if value <= -0.25:
        return "negative"
    return "neutral"


def _news_item_title_for_llm(row: Any, *, max_len: int = 120) -> str:
    if isinstance(row, dict):
        title = str(row.get("title") or row.get("headline") or "").strip()
    else:
        raw = str(row or "").strip()
        match = re.search(r"title=['\"]([^'\"]+)['\"]", raw)
        title = match.group(1).strip() if match else raw
    title = re.sub(r"<[^>]+>", "", title).strip()
    if len(title) > max_len:
        return title[: max_len - 3] + "..."
    return title


def _compact_news_signal_summary_for_llm(
    *,
    signal_map: Any,
    sample: Any,
    symbols: List[str],
    limit: int = 6,
) -> List[Dict[str, Any]]:
    signals = signal_map if isinstance(signal_map, dict) else {}
    samples = sample if isinstance(sample, dict) else {}
    ordered_symbols: List[str] = []
    for symbol in list(symbols or []) + list(samples.keys()) + list(signals.keys()):
        text = str(symbol or "").strip()
        if text and text not in ordered_symbols:
            ordered_symbols.append(text)
    out: List[Dict[str, Any]] = []
    for symbol in ordered_symbols[:limit]:
        sig = signals.get(symbol) if isinstance(signals.get(symbol), dict) else {}
        score = _round_optional(sig.get("score"), 4)
        sample_row = samples.get(symbol) if isinstance(samples.get(symbol), dict) else {}
        rows = sample_row.get("sample") if isinstance(sample_row.get("sample"), list) else []
        evidence = [
            title
            for title in (_news_item_title_for_llm(row, max_len=120) for row in rows[:2])
            if title
        ]
        out.append(
            {
                "symbol": symbol,
                "score": score,
                "label": _news_signal_label(score),
                "status": str(sig.get("status") or ""),
                "headline_count": int(sample_row.get("count") or len(rows) or 0),
                "top_evidence": evidence,
            }
        )
    return out


def _selected_symbol_news_signal_for_llm(
    rows: List[Dict[str, Any]],
    selected_symbol: Any,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip()
    if not symbol:
        return {}
    for row in rows:
        if str((row or {}).get("symbol") or "").strip() == symbol:
            return dict(row)
    return {"symbol": symbol, "score": None, "label": "unavailable", "status": "missing", "headline_count": 0, "top_evidence": []}


def _clip_text_for_llm(raw: Any, *, max_len: int = 180) -> str:
    text = str(raw or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 1)].rstrip() + "..."


def _compact_scalar_mapping_for_llm(src: Any, *, allowed_keys: List[str], max_text_len: int = 160) -> Dict[str, Any]:
    obj = src if isinstance(src, dict) else {}
    out: Dict[str, Any] = {}
    for key in allowed_keys:
        if key not in obj:
            continue
        value = obj.get(key)
        if isinstance(value, str):
            out[key] = _clip_text_for_llm(value, max_len=max_text_len)
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
        elif isinstance(value, list):
            out[key] = [
                _clip_text_for_llm(x, max_len=max_text_len) if not isinstance(x, dict) else x
                for x in list(value)[:4]
            ]
    return out


def _compact_pattern_rows_for_llm(rows: Any, *, limit: int = 3) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in list(rows or [])[:limit]:
        if not isinstance(row, dict):
            continue
        compact = _compact_scalar_mapping_for_llm(
            row,
            allowed_keys=[
                "type",
                "value",
                "count",
                "playbook",
                "entry_reason",
                "exit_reason",
                "monitor_reason",
                "blocker",
                "pattern",
                "win_rate",
                "avg_return",
                "avg_pnl_pct",
            ],
            max_text_len=100,
        )
        if compact:
            out.append(compact)
    return out


def _operator_summary_for_llm(summary: Any) -> Dict[str, Any]:
    src = summary if isinstance(summary, dict) else {}
    if not src:
        return {}
    metrics = src.get("metrics") if isinstance(src.get("metrics"), dict) else {}
    operator_view = src.get("operator_view") if isinstance(src.get("operator_view"), dict) else {}
    out: Dict[str, Any] = {
        "schema_version": str(src.get("schema_version") or ""),
        "available": bool(src.get("available")),
        "status": str(src.get("status") or ""),
        "key": str(src.get("key") or ""),
        "artifact_path": str(src.get("artifact_path") or ""),
        "metrics": _compact_scalar_mapping_for_llm(
            metrics,
            allowed_keys=[
                "trade_count",
                "closed_trade_count",
                "win_rate",
                "avg_return_pct",
                "avg_net_return_pct",
                "total_return_pct",
                "total_net_return_pct",
                "profit_factor",
                "avg_hold_duration_sec",
            ],
            max_text_len=80,
        ),
        "operator_view": {
            "conclusion": _clip_text_for_llm(operator_view.get("conclusion"), max_len=180),
            "review_points": [
                _clip_text_for_llm(x, max_len=120)
                for x in list(operator_view.get("review_points") or [])[:4]
                if str(x or "").strip()
            ],
        },
    }
    for key in ("key_patterns", "repeat_patterns", "risk_notes", "cost_notes"):
        values = src.get(key)
        if isinstance(values, list):
            out[key] = [_clip_text_for_llm(x, max_len=120) for x in values[:4] if str(x or "").strip()]

    strategist_eval = src.get("strategist_llm_evaluation") if isinstance(src.get("strategist_llm_evaluation"), dict) else {}
    shadow_eval = (
        src.get("quant_shadow_candidate_evaluation")
        if isinstance(src.get("quant_shadow_candidate_evaluation"), dict)
        else {}
    )
    promotion = (
        shadow_eval.get("promotion_candidate")
        if isinstance(shadow_eval.get("promotion_candidate"), dict)
        else {}
    )
    readiness = (
        shadow_eval.get("shadow_readiness")
        if isinstance(shadow_eval.get("shadow_readiness"), dict)
        else {}
    )
    entry_shape = (
        shadow_eval.get("entry_shape_diagnostics")
        if isinstance(shadow_eval.get("entry_shape_diagnostics"), dict)
        else {}
    )
    lane_guidance: Dict[str, Any] = {}
    if strategist_eval:
        lane_guidance.update(
            _compact_scalar_mapping_for_llm(
                strategist_eval,
                allowed_keys=[
                    "lane_selection_quality",
                    "selected_primary_tactic",
                    "selected_primary_lane",
                    "overused_lane_or_tactic",
                    "underused_shadow_lane",
                ],
                max_text_len=100,
            )
        )
    if readiness:
        lane_guidance["shadow_readiness"] = _compact_scalar_mapping_for_llm(
            readiness,
            allowed_keys=["status", "action", "candidate", "confidence", "promotion_scope"],
            max_text_len=100,
        )
    if promotion:
        lane_guidance["promotion_candidate"] = _compact_scalar_mapping_for_llm(
            promotion,
            allowed_keys=["candidate", "confidence", "recommended_action", "reason"],
            max_text_len=100,
        )
        counts = promotion.get("counts") if isinstance(promotion.get("counts"), dict) else {}
        if counts:
            lane_guidance["promotion_counts"] = _compact_scalar_mapping_for_llm(
                counts,
                allowed_keys=["cost_edge", "runner_up", "entry_guard"],
                max_text_len=40,
            )
    if entry_shape:
        lane_guidance["entry_shape_diagnostics"] = _compact_scalar_mapping_for_llm(
            entry_shape,
            allowed_keys=[
                "pullback_or_vwap_blocked_count",
                "breakout_ready_like_count",
                "breakout_not_ready_count",
            ],
            max_text_len=40,
        )
    if lane_guidance:
        selected = str(lane_guidance.get("selected_primary_tactic") or "").strip()
        overused = str(lane_guidance.get("overused_lane_or_tactic") or "").strip()
        underused = str(lane_guidance.get("underused_shadow_lane") or "").strip()
        pullback_blocked = _to_int(
            _nested_mapping_value(lane_guidance, "entry_shape_diagnostics", "pullback_or_vwap_blocked_count"),
            0,
        )
        breakout_ready = _to_int(
            _nested_mapping_value(lane_guidance, "entry_shape_diagnostics", "breakout_ready_like_count"),
            0,
        )
        directives: List[str] = []
        if selected == "vwap_reclaim_pullback" and overused == "vwap_reclaim_pullback":
            directives.append("downweight_repeated_vwap_reclaim_pullback_unless_cost_volume_and_maturity_are_ready")
        if underused == "breakout" and breakout_ready > 0:
            directives.append("explicitly_score_breakout_or_volume_breakout_against_pullback_before_selecting_tactic")
        if pullback_blocked >= 50 and breakout_ready > 0:
            directives.append("do_not_default_to_late_pullback_when_shadow_breakout_ready_like_candidates_exist")
        if directives:
            lane_guidance["strategist_directives"] = directives[:4]
        out["tactic_lane_guidance"] = lane_guidance
    return {k: v for k, v in out.items() if v not in ({}, [], "", None)}


def _compact_trade_read_model_for_llm(row: Any) -> Dict[str, Any]:
    src = row if isinstance(row, dict) else {}
    return _compact_scalar_mapping_for_llm(
        src,
        allowed_keys=[
            "trade_id",
            "symbol",
            "entry_ts",
            "exit_ts",
            "entry_price",
            "exit_price",
            "qty",
            "hold_duration_sec",
            "pnl",
            "pnl_pct",
            "return_pct",
            "net_return_pct",
            "realized_pnl",
            "realized_pnl_pct",
            "kiwoom_pnl_pct",
            "entry_reason",
            "exit_reason",
            "entry_pattern",
            "exit_pattern",
            "playbook",
            "monitor_reason",
        ],
        max_text_len=120,
    )


def _compact_symbol_read_model_for_llm(row: Any) -> Dict[str, Any]:
    src = row if isinstance(row, dict) else {}
    out = _compact_scalar_mapping_for_llm(
        src,
        allowed_keys=[
            "symbol",
            "trade_count",
            "closed_trade_count",
            "win_count",
            "loss_count",
            "win_rate",
            "avg_pnl_pct",
            "avg_return",
            "avg_hold_duration_sec",
            "dominant_playbook",
            "dominant_monitor_blocker",
            "dominant_exit_reason",
            "dominant_entry_reason",
            "override_eligible",
            "status",
        ],
        max_text_len=120,
    )
    out["repeated_failure_pattern"] = _compact_pattern_rows_for_llm(src.get("repeated_failure_pattern"), limit=3)
    out["recent_success_pattern"] = _compact_pattern_rows_for_llm(src.get("recent_success_pattern"), limit=3)
    data_quality = src.get("data_quality") if isinstance(src.get("data_quality"), dict) else {}
    if data_quality:
        out["data_quality"] = _compact_scalar_mapping_for_llm(
            data_quality,
            allowed_keys=["data_source", "unknown_fields_ratio", "status"],
            max_text_len=80,
        )
    return {k: v for k, v in out.items() if v not in ({}, [], "", None)}


def _compact_read_model_facts_for_llm(facts: Any) -> Dict[str, Any]:
    src = facts if isinstance(facts, dict) else {}
    recent_trades = [
        compact
        for compact in (_compact_trade_read_model_for_llm(row) for row in list(src.get("recent_trades") or [])[:3])
        if compact
    ]
    symbol_patterns: Dict[str, Any] = {}
    raw_patterns = src.get("symbol_patterns") if isinstance(src.get("symbol_patterns"), dict) else {}
    for symbol, row in list(raw_patterns.items())[:5]:
        compact = _compact_symbol_read_model_for_llm(row)
        if compact:
            symbol_patterns[str(symbol)] = compact
    daily_summary = _operator_summary_for_llm(src.get("daily_summary"))
    return {
        "recent_trades": recent_trades,
        "recent_trade_count": len(list(src.get("recent_trades") or [])),
        "daily_summary": daily_summary,
        "symbol_patterns": symbol_patterns,
        "symbol_pattern_count": len(raw_patterns),
    }


def _load_deterministic_read_models(state: Dict[str, Any], candidates: List[str]) -> Dict[str, Any]:
    """Phase 6-2: Gather strictly deterministic read models for Strategist context."""
    reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")
    trades_root = reports_root / "trades"
    
    recent_trades = []
    if trades_root.exists() and trades_root.is_dir():
        # Find recent trade directories (limit to 5 without using env vars)
        trade_dirs = sorted([d for d in trades_root.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)[:5]
        for td in trade_dirs:
            try:
                trm = build_trade_read_model(str(td))
                if trm and trm.get("trade_id"):
                    recent_trades.append(trm)
            except Exception:
                pass
                
    symbol_patterns = {}
    persisted_symbol_models_only = not _env_bool("STRATEGIST_READ_MODEL_FULL_SCAN", False)
    for sym in list(candidates or [])[:5]:
        try:
            symbol_patterns[str(sym)] = build_symbol_read_model(
                str(trades_root),
                str(sym),
                persisted_only=persisted_symbol_models_only,
            )
        except Exception:
            pass
            
    return {
        "recent_trades": recent_trades,
        "daily_summary": {},  # Placeholder for daily_summary_read_model
        "symbol_patterns": symbol_patterns
    }


def _resolve_strategist_llm_call_kind(payload: Dict[str, Any]) -> str:
    compact = payload if isinstance(payload, dict) else {}
    context = compact.get("commander_refresh_context") if isinstance(compact.get("commander_refresh_context"), dict) else {}
    if bool(context.get("requested")):
        scope = str(context.get("refresh_scope") or "").strip().lower()
        reason = str(context.get("reason") or "").strip().lower()
        carry_state = str(context.get("carry_state") or "").strip().lower()
        if (
            "closeout" in scope
            or "closeout" in reason
            or "end_of_day" in scope
            or "end_of_day" in reason
            or "eod" in scope
            or "eod" in reason
            or "overnight_review" in scope
            or "overnight_review" in reason
            or "overnight" in reason
            or reason in {"end_of_day_carry_review", "session_closeout_carry_review"}
        ):
            return "end_of_day_carry_review"
        if (
            "open_position" in scope
            or "hold" in scope
            or "position" in scope
            or "hold" in reason
            or "loss_threshold" in reason
            or "preopen_carry" in reason
            or carry_state
        ):
            return "stale_intraday_hold_review"
        return "selected_symbol_tactical_refresh"
    explicit = str(compact.get("resolved_call_kind") or compact.get("call_kind") or "").strip().lower()
    if explicit in {
        "selected_symbol_tactical_refresh",
        "stale_intraday_hold_review",
        "end_of_day_carry_review",
        "market_strategy_frame",
    }:
        return explicit
    return "market_strategy_frame"


def _hide_stage1_symbol_memory(compact: Dict[str, Any]) -> None:
    reason = "stage1_market_frame_excludes_symbol_memory"
    if isinstance(compact.get("commander_refresh_context"), dict):
        compact["commander_refresh_context"]["selected_symbol_memory"] = {}
    read_model_facts = compact.get("read_model_facts") if isinstance(compact.get("read_model_facts"), dict) else {}
    compact["read_model_facts"] = {
        **dict(read_model_facts),
        "symbol_patterns": {},
        "symbol_pattern_count": 0,
        "symbol_memory_visible_to_llm": False,
        "symbol_memory_exclusion_reason": reason,
    }
    memory_packets = compact.get("memory_packets") if isinstance(compact.get("memory_packets"), dict) else {}
    compact["memory_packets"] = {
        **dict(memory_packets),
        "symbol_memory_packet": {
            "status": "excluded",
            "visible_to_llm": False,
            "reason": reason,
        },
    }
    compact["memory_boundary"] = {
        "stage": "stage1_market_frame",
        "broad_memory_visible_to_llm": True,
        "symbol_memory_visible_to_llm": False,
        "reason": reason,
    }


def _compact_monitor_entry_policy_baseline_for_llm(policy: Any) -> Dict[str, Any]:
    src = policy if isinstance(policy, dict) else {}
    keep = (
        "enabled",
        "timeframe_minutes",
        "volume_ratio_min",
        "min_extended_from_vwap_pct",
        "max_extended_from_vwap_pct",
        "pullback_min_pct",
        "pullback_max_pct",
        "reclaim_tolerance_pct",
        "intent_cooldown_sec",
        "require_vwap_reclaim",
        "require_rebound",
    )
    return {key: src.get(key) for key in keep if key in src}


def _compact_theme_strength_for_llm(raw: Any, *, limit: int = 6) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    rows: list[tuple[str, float]] = []
    for key, value in src.items():
        score = _stage_float(value, None)
        if score is None:
            continue
        rows.append((str(key), float(score)))
    rows.sort(key=lambda item: item[1], reverse=True)
    return {key: _round_optional(value, 4) for key, value in rows[: max(0, int(limit))]}


def _theme_packet_summary_for_llm(packet: Any) -> Dict[str, Any]:
    src = packet if isinstance(packet, dict) else {}
    groups = src.get("groups") if isinstance(src.get("groups"), list) else []
    components = src.get("components_by_theme") if isinstance(src.get("components_by_theme"), dict) else {}
    return {
        "status": str(src.get("status") or ""),
        "source": str(src.get("source") or ""),
        "group_count": int(len(groups)),
        "component_theme_count": int(len(components)),
        "fallback_used": bool(src.get("fallback_used")),
        "fallback_reason": str(src.get("fallback_reason") or src.get("reason") or "")[:160],
    }


def _compact_candidate_context_for_refresh(row: Any) -> Dict[str, Any]:
    src = row if isinstance(row, dict) else {}
    if not src:
        return {}
    keep = (
        "symbol",
        "rank",
        "score",
        "score_total",
        "reason",
        "source",
        "risk_score",
        "confidence",
        "entry_compatibility_score",
        "scanner_chart_fit_score",
        "scanner_macro_chart_fit_score",
        "expected_monitor_block_reason",
        "dominant_block_reason",
        "market_representative_guard_reason",
        "selection_reason_with_bias",
        "status",
    )
    out = {key: src.get(key) for key in keep if src.get(key) not in (None, "", [], {})}
    score_breakdown = src.get("score_breakdown") if isinstance(src.get("score_breakdown"), dict) else {}
    if score_breakdown:
        out["score_breakdown"] = {
            str(key): _round_optional(value, 4) if _stage_float(value, None) is not None else _clip_text_for_llm(value, max_len=60)
            for key, value in list(score_breakdown.items())[:5]
        }
    return out


def _slim_refresh_context_for_llm(context: Any) -> Dict[str, Any]:
    src = context if isinstance(context, dict) else {}
    out = dict(src)
    for key in ("scanner_primary_candidate", "actual_selected_candidate", "scanner_rank1_candidate"):
        out[key] = _compact_candidate_context_for_refresh(src.get(key))
    out["scanner_runner_ups"] = [
        _compact_candidate_context_for_refresh(row)
        for row in list(src.get("scanner_runner_ups") or [])[:3]
        if isinstance(row, dict)
    ]
    out["scanner_top_candidates"] = [
        _compact_candidate_context_for_refresh(row)
        for row in list(src.get("scanner_top_candidates") or [])[:4]
        if isinstance(row, dict)
    ]
    selected_memory = src.get("selected_symbol_memory") if isinstance(src.get("selected_symbol_memory"), dict) else {}
    if selected_memory:
        out["selected_symbol_memory"] = {
            "status": str(selected_memory.get("status") or ""),
            "symbol": str(selected_memory.get("symbol") or ""),
            "trade_count": int(selected_memory.get("trade_count") or 0),
            "override_eligible": bool(selected_memory.get("override_eligible")),
            "operator_summary": _operator_summary_for_llm(selected_memory.get("operator_summary")),
        }
    return out


def _apply_strategist_llm_token_budget(compact: Dict[str, Any], *, memory_usage_disabled: bool) -> Dict[str, Any]:
    out = dict(compact or {})
    call_kind = _resolve_strategist_llm_call_kind(out)
    raw_theme_packet = out.pop("theme_strength_packet", {})
    out["theme_strength_packet_summary"] = _theme_packet_summary_for_llm(raw_theme_packet)
    out["theme_strength"] = _compact_theme_strength_for_llm(out.get("theme_strength"), limit=6)
    out["monitor_entry_policy_baseline"] = _compact_monitor_entry_policy_baseline_for_llm(
        out.get("monitor_entry_policy_baseline")
    )
    out["token_budget_policy"] = {
        "schema_version": "strategist_llm_token_budget.v1",
        "call_kind": str(call_kind),
        "dedup_theme_strength_packet": True,
        "stage_specific_context": bool(call_kind != "market_strategy_frame"),
        "memory_usage_disabled": bool(memory_usage_disabled),
    }
    if call_kind == "market_strategy_frame":
        return out

    candidate_news_signal_summary = list(out.get("candidate_news_signal_summary") or [])[:4]
    selected_symbol_news_signal = dict(out.get("selected_symbol_news_signal") or {})
    market_news_signal_summary = list(out.get("market_news_signal_summary") or [])[:3]
    out["market_news_sample"] = {}
    out["candidate_news_sample"] = {}
    out["candidate_news_signal_summary"] = candidate_news_signal_summary
    out["selected_symbol_news_signal"] = selected_symbol_news_signal
    out["market_news_signal_summary"] = market_news_signal_summary
    news_policy = out.get("news_collection_policy") if isinstance(out.get("news_collection_policy"), dict) else {}
    out["news_collection_policy"] = {
        "provider": str(news_policy.get("provider") or ""),
        "post_scanner_requery": bool(news_policy.get("post_scanner_requery")),
        "reuse_policy": str(news_policy.get("reuse_policy") or ""),
        "collection_symbol_count": len(list(news_policy.get("collection_symbols") or [])),
    }
    out["available_themes"] = [
        {
            **dict(row),
            "component_symbols": [str(x or "") for x in list((row or {}).get("component_symbols") or [])[:3]],
        }
        for row in list(out.get("available_themes") or [])[:4]
        if isinstance(row, dict)
    ]
    refresh_context = out.get("commander_refresh_context") if isinstance(out.get("commander_refresh_context"), dict) else {}
    out["commander_refresh_context"] = _slim_refresh_context_for_llm(refresh_context)
    out["recent_strategy_feedback"] = {
        "feedback_window_size": int((out.get("recent_strategy_feedback") or {}).get("feedback_window_size") or 0)
        if isinstance(out.get("recent_strategy_feedback"), dict)
        else 0,
        "top_recent_weaknesses": [
            str(x or "")
            for x in list(((out.get("recent_strategy_feedback") or {}).get("top_recent_weaknesses") or [])[:2])
        ]
        if isinstance(out.get("recent_strategy_feedback"), dict)
        else [],
        "recent_playbook_performance": (
            dict((out.get("recent_strategy_feedback") or {}).get("recent_playbook_performance") or {})
            if isinstance(out.get("recent_strategy_feedback"), dict)
            else {}
        ),
        "advisory_only": bool((out.get("recent_strategy_feedback") or {}).get("advisory_only", True))
        if isinstance(out.get("recent_strategy_feedback"), dict)
        else True,
    }
    reporter_feedback = out.get("reporter_feedback_packet") if isinstance(out.get("reporter_feedback_packet"), dict) else {}
    out["reporter_feedback_packet"] = {
        "available": bool(reporter_feedback.get("available")),
        "status": str(reporter_feedback.get("status") or ""),
        "confidence": str(reporter_feedback.get("confidence") or "none"),
        "insight_summary": str(reporter_feedback.get("insight_summary") or "")[:140],
        "blocker_analysis": list(reporter_feedback.get("blocker_analysis") or [])[:2],
        "recommendation": [str(x or "") for x in list(reporter_feedback.get("recommendation") or [])[:2]],
        "advisory_only": True,
    }
    strategy_memory = out.get("strategy_memory") if isinstance(out.get("strategy_memory"), dict) else {}
    out["strategy_memory"] = {
        "status": str(strategy_memory.get("status") or ""),
        "best_playbooks": list(strategy_memory.get("best_playbooks") or [])[:2],
        "worst_playbooks": list(strategy_memory.get("worst_playbooks") or [])[:2],
        "pattern_performance_snapshot": {
            "problem_patterns": list(
                ((strategy_memory.get("pattern_performance_snapshot") or {}).get("problem_patterns") or [])
            )[:3]
            if isinstance(strategy_memory.get("pattern_performance_snapshot"), dict)
            else [],
            "working_patterns": list(
                ((strategy_memory.get("pattern_performance_snapshot") or {}).get("working_patterns") or [])
            )[:2]
            if isinstance(strategy_memory.get("pattern_performance_snapshot"), dict)
            else [],
        },
        "advisory_only": bool(strategy_memory.get("advisory_only", True)),
    }
    memory_packets = out.get("memory_packets") if isinstance(out.get("memory_packets"), dict) else {}
    out["memory_packets"] = {
        "daily_strategy_memory": dict(memory_packets.get("daily_strategy_memory") or {}),
        "symbol_memory_packet": dict(memory_packets.get("symbol_memory_packet") or {}),
    }
    return out


def _build_compact_strategist_llm_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    compact = dict(payload or {})
    memory_usage_disabled = _strategy_memory_usage_disabled(compact)
    compact["global_sentiment_signal"] = _compact_global_signal_for_llm(compact.get("global_sentiment_signal"))
    news_ctx = compact.get("news_context") if isinstance(compact.get("news_context"), dict) else {}
    compact["news_context"] = {
        "signal_total": int(news_ctx.get("signal_total") or 0),
        "avg_score": _round_optional(news_ctx.get("avg_score"), 4),
        "headline_count": int(news_ctx.get("headline_count") or 0),
        "candidate_signal_total": int(news_ctx.get("candidate_signal_total") or 0),
        "market_signal_total": int(news_ctx.get("market_signal_total") or 0),
    }
    market_ctx = compact.get("market_context_inputs") if isinstance(compact.get("market_context_inputs"), dict) else {}
    compact["market_context_inputs"] = {
        "index_trend": _round_optional(market_ctx.get("index_trend"), 4),
        "realized_volatility": _round_optional(market_ctx.get("realized_volatility"), 4),
        "market_breadth": _round_optional(market_ctx.get("market_breadth"), 4),
        "macro_risk": _round_optional(market_ctx.get("macro_risk"), 4),
    }
    compact["recent_strategy_feedback"] = _compact_recent_strategy_feedback_for_llm(compact.get("recent_strategy_feedback"))
    compact["reporter_feedback_packet"] = _compact_reporter_feedback_for_llm(compact.get("reporter_feedback_packet"))
    compact["strategy_memory"] = _compact_strategy_memory_for_llm(compact.get("strategy_memory"))
    compact["macro_stress_overlay_hint"] = {
        "active": bool(((compact.get("macro_stress_overlay_hint") or {}).get("active"))),
        "stress_flags": [str(x or "") for x in list(((compact.get("macro_stress_overlay_hint") or {}).get("stress_flags") or [])[:4])],
        "reason": str(((compact.get("macro_stress_overlay_hint") or {}).get("reason") or "")),
    }
    compact["market_news_sample"] = _compact_news_sample_for_llm(compact.get("market_news_sample"), max_symbols=4, max_titles=1, max_title_len=120)
    compact["candidate_news_sample"] = _compact_news_sample_for_llm(compact.get("candidate_news_sample"), max_symbols=4, max_titles=1, max_title_len=120)
    compact["candidate_symbols_hint"] = list(compact.get("candidate_symbols_hint") or [])[:5]
    compact["key_events_hint"] = [str(x or "") for x in list(compact.get("key_events_hint") or [])[:4]]
    compact["themes_hint"] = [str(x or "") for x in list(compact.get("themes_hint") or [])[:4]]
    compact["fallback_theme_hints"] = [
        str(x or "") for x in list(compact.get("fallback_theme_hints") or [])[:4] if str(x or "").strip()
    ]
    compact["available_themes"] = [
        {
            "theme": str((row or {}).get("theme") or ""),
            "theme_code": str((row or {}).get("theme_code") or ""),
            "score": _round_optional((row or {}).get("score"), 4),
            "component_count": int((row or {}).get("component_count") or 0),
            "component_symbols": [str(x or "") for x in list((row or {}).get("component_symbols") or [])[:6]],
        }
        for row in list(compact.get("available_themes") or [])[:8]
        if isinstance(row, dict)
    ]
    compact["selected_themes_hint"] = [
        str(x or "") for x in list(compact.get("selected_themes_hint") or [])[:5] if str(x or "").strip()
    ]
    news_collection_policy = compact.get("news_collection_policy") if isinstance(compact.get("news_collection_policy"), dict) else {}
    compact["news_collection_policy"] = {
        "provider": str(news_collection_policy.get("provider") or ""),
        "market_query_targets": [str(x or "") for x in list(news_collection_policy.get("market_query_targets") or [])[:8]],
        "candidate_symbols_requested": [
            str(x or "") for x in list(news_collection_policy.get("candidate_symbols_requested") or [])[:8]
        ],
        "theme_component_symbols_requested": [
            str(x or "") for x in list(news_collection_policy.get("theme_component_symbols_requested") or [])[:8]
        ],
        "collection_symbols": [str(x or "") for x in list(news_collection_policy.get("collection_symbols") or [])[:12]],
        "post_scanner_requery": bool(news_collection_policy.get("post_scanner_requery")),
        "reuse_policy": str(news_collection_policy.get("reuse_policy") or ""),
    }
    compact["news_query_targets"] = [str(x or "") for x in list(compact.get("news_query_targets") or [])[:8]]
    commander_refresh_context = compact.get("commander_refresh_context") if isinstance(compact.get("commander_refresh_context"), dict) else {}
    selected_symbol_was_rank1_raw = commander_refresh_context.get("selected_symbol_was_rank1")
    selected_symbol_was_rank1 = (
        bool(selected_symbol_was_rank1_raw)
        if selected_symbol_was_rank1_raw is not None
        else int(commander_refresh_context.get("selected_rank") or 0) == 1
    )
    actual_selected_candidate = (
        commander_refresh_context.get("actual_selected_candidate")
        if isinstance(commander_refresh_context.get("actual_selected_candidate"), dict)
        else commander_refresh_context.get("scanner_primary_candidate")
        if isinstance(commander_refresh_context.get("scanner_primary_candidate"), dict)
        else {}
    )
    selected_news_symbol = (
        commander_refresh_context.get("selected_symbol")
        or actual_selected_candidate.get("symbol")
        or (compact.get("candidate_symbols_hint") or [""])[0]
    )
    candidate_news_signal_summary = _compact_news_signal_summary_for_llm(
        signal_map=compact.get("news_sentiment_signal"),
        sample=compact.get("candidate_news_sample"),
        symbols=[str(x or "") for x in list(compact.get("candidate_symbols_hint") or [])],
        limit=6,
    )
    compact["candidate_news_signal_summary"] = candidate_news_signal_summary
    compact["selected_symbol_news_signal"] = _selected_symbol_news_signal_for_llm(
        candidate_news_signal_summary,
        selected_news_symbol,
    )
    compact["market_news_signal_summary"] = _compact_news_signal_summary_for_llm(
        signal_map=compact.get("market_news_sentiment_signal"),
        sample=compact.get("market_news_sample"),
        symbols=[str(x or "") for x in list((compact.get("market_news_sample") or {}).keys())],
        limit=4,
    )
    compact.pop("news_sentiment_signal", None)
    compact.pop("market_news_sentiment_signal", None)
    compact["commander_refresh_context"] = {
        "requested": bool(commander_refresh_context.get("requested")),
        "reason": str(commander_refresh_context.get("reason") or ""),
        "refresh_scope": str(commander_refresh_context.get("refresh_scope") or ""),
        "selected_symbol": str(commander_refresh_context.get("selected_symbol") or ""),
        "hold_repeat_count_max": int(commander_refresh_context.get("hold_repeat_count_max") or 0),
        "selected_hold_repeat_count": int(commander_refresh_context.get("selected_hold_repeat_count") or 0),
        "monitor_reason": str(commander_refresh_context.get("monitor_reason") or ""),
        "active_exit_axis": str(commander_refresh_context.get("active_exit_axis") or ""),
        "refresh_summary": str(commander_refresh_context.get("refresh_summary") or "")[:220],
        "selected_rank": int(commander_refresh_context.get("selected_rank") or 0),
        "selected_score": _round_optional(commander_refresh_context.get("selected_score"), 4),
        "scanner_primary_candidate": dict(commander_refresh_context.get("scanner_primary_candidate") or {}),
        "actual_selected_candidate": dict(actual_selected_candidate),
        "scanner_rank1_candidate": dict(commander_refresh_context.get("scanner_rank1_candidate") or {}),
        "scanner_runner_ups": [
            dict(row)
            for row in list(commander_refresh_context.get("scanner_runner_ups") or [])[:4]
            if isinstance(row, dict)
        ],
        "scanner_top_candidates": [
            dict(row)
            for row in list(commander_refresh_context.get("scanner_top_candidates") or [])[:5]
            if isinstance(row, dict)
        ],
        "selected_symbol_was_rank1": bool(selected_symbol_was_rank1),
        "stage2_context_quality": str(commander_refresh_context.get("stage2_context_quality") or ""),
        "stage2_context_quality_reasons": [
            str(reason or "")
            for reason in list(commander_refresh_context.get("stage2_context_quality_reasons") or [])[:6]
            if str(reason or "").strip()
        ],
        "entry_state": dict(commander_refresh_context.get("entry_state") or {}),
        "carry_state": str(commander_refresh_context.get("carry_state") or ""),
        "carry_risk_bias": str(commander_refresh_context.get("carry_risk_bias") or ""),
        "carry_risk_reason": str(commander_refresh_context.get("carry_risk_reason") or "")[:220],
        "session_open_recovery_assessment": dict(
            commander_refresh_context.get("session_open_recovery_assessment") or {}
        ),
        "prior_monitor_entry_policy_summary": dict(commander_refresh_context.get("prior_monitor_entry_policy_summary") or {}),
        "current_monitor_entry_policy_summary": dict(commander_refresh_context.get("current_monitor_entry_policy_summary") or {}),
        "commander_horizon_policy": {
            "owner": str((commander_refresh_context.get("commander_horizon_policy") or {}).get("owner") or "commander")
            if isinstance(commander_refresh_context.get("commander_horizon_policy"), dict)
            else "",
            "strategy_horizon": str(
                (commander_refresh_context.get("commander_horizon_policy") or {}).get("strategy_horizon") or ""
            )
            if isinstance(commander_refresh_context.get("commander_horizon_policy"), dict)
            else "",
            "source_strategy_horizon": str(
                (commander_refresh_context.get("commander_horizon_policy") or {}).get("source_strategy_horizon") or ""
            )
            if isinstance(commander_refresh_context.get("commander_horizon_policy"), dict)
            else "",
            "observability_only": bool(
                (commander_refresh_context.get("commander_horizon_policy") or {}).get("observability_only", True)
            )
            if isinstance(commander_refresh_context.get("commander_horizon_policy"), dict)
            else True,
            "do_not_force_hold": bool(
                (commander_refresh_context.get("commander_horizon_policy") or {}).get("do_not_force_hold", True)
            )
            if isinstance(commander_refresh_context.get("commander_horizon_policy"), dict)
            else True,
            "decision_reason": str(
                (commander_refresh_context.get("commander_horizon_policy") or {}).get("decision_reason") or ""
            )
            if isinstance(commander_refresh_context.get("commander_horizon_policy"), dict)
            else "",
        },
        "requires_policy_delta": bool(commander_refresh_context.get("requires_policy_delta")),
        "selected_symbol_memory": dict(commander_refresh_context.get("selected_symbol_memory") or {}),
    }
    compact["strategy_refresh_trace_input"] = {
        "initial_frame": {
            "market_regime": str(compact.get("market_regime_hint") or ""),
            "market_sentiment": str(compact.get("market_sentiment_hint") or ""),
            "playbook": str(compact.get("playbook_hint") or ""),
            "candidate_symbols": list(compact.get("candidate_symbols_hint") or [])[:5],
        },
        "post_scanner_refresh": {
            "requested": bool(commander_refresh_context.get("requested")),
            "reason": str(commander_refresh_context.get("reason") or ""),
            "scope": str(commander_refresh_context.get("refresh_scope") or ""),
            "selected_symbol": str(commander_refresh_context.get("selected_symbol") or ""),
            "selected_rank": int(commander_refresh_context.get("selected_rank") or 0),
            "selected_score": _round_optional(commander_refresh_context.get("selected_score"), 4),
            "scanner_rank1_symbol": str(
                (commander_refresh_context.get("scanner_rank1_candidate") or {}).get("symbol") or ""
            )
            if isinstance(commander_refresh_context.get("scanner_rank1_candidate"), dict)
            else "",
            "actual_selected_rank": int(
                (commander_refresh_context.get("actual_selected_candidate") or {}).get("rank")
                or commander_refresh_context.get("selected_rank")
                or 0
            )
            if isinstance(commander_refresh_context.get("actual_selected_candidate"), dict)
            else int(commander_refresh_context.get("selected_rank") or 0),
            "selected_symbol_was_rank1": bool(selected_symbol_was_rank1),
            "stage2_context_quality": str(commander_refresh_context.get("stage2_context_quality") or ""),
            "runner_up_count": len(list(commander_refresh_context.get("scanner_runner_ups") or [])),
            "monitor_reason": str(commander_refresh_context.get("monitor_reason") or ""),
            "refresh_summary": str(commander_refresh_context.get("refresh_summary") or "")[:220],
        },
        "final_application": {
            "requires_policy_delta": bool(commander_refresh_context.get("requires_policy_delta")),
            "prior_monitor_entry_policy_summary": dict(commander_refresh_context.get("prior_monitor_entry_policy_summary") or {}),
            "current_monitor_entry_policy_summary": dict(commander_refresh_context.get("current_monitor_entry_policy_summary") or {}),
        },
    }
    memory_packets = compact.get("memory_packets") if isinstance(compact.get("memory_packets"), dict) else {}
    daily_packet = dict(memory_packets.get("daily_strategy_memory") or {})
    weekly_packet = dict(memory_packets.get("weekly_strategy_memory") or {})
    monthly_packet = dict(memory_packets.get("monthly_strategy_memory") or {})
    symbol_packet = dict(memory_packets.get("symbol_memory_packet") or {})
    compact["memory_packets"] = {
        "daily_strategy_memory": {
            "status": str(daily_packet.get("status") or ""),
            "best_playbooks": [str(x or "") for x in list(daily_packet.get("best_playbooks") or [])[:3] if str(x or "").strip()],
            "worst_playbooks": [str(x or "") for x in list(daily_packet.get("worst_playbooks") or [])[:3] if str(x or "").strip()],
            "pattern_performance_snapshot": _compact_pattern_performance_for_llm(
                daily_packet.get("pattern_performance_snapshot")
            ),
            "operator_summary": _operator_summary_for_llm(daily_packet.get("operator_summary")),
        },
        "weekly_strategy_memory": {
            "status": str(weekly_packet.get("status") or ""),
            "pattern_performance_snapshot": _compact_pattern_performance_for_llm(
                weekly_packet.get("pattern_performance_snapshot")
            ),
            "operator_summary": _operator_summary_for_llm(weekly_packet.get("operator_summary")),
        },
        "monthly_strategy_memory": {
            "status": str(monthly_packet.get("status") or ""),
            "pattern_performance_snapshot": _compact_pattern_performance_for_llm(
                monthly_packet.get("pattern_performance_snapshot")
            ),
            "operator_summary": _operator_summary_for_llm(monthly_packet.get("operator_summary")),
        },
        "symbol_memory_packet": {
            "status": str(symbol_packet.get("status") or ""),
            "symbol": str(symbol_packet.get("symbol") or ""),
            "trade_count": int(symbol_packet.get("trade_count") or 0),
            "override_eligible": bool(symbol_packet.get("override_eligible")),
            "operator_summary": _operator_summary_for_llm(symbol_packet.get("operator_summary")),
        },
    }
    commander_memory_policy = compact.get("commander_memory_policy") if isinstance(compact.get("commander_memory_policy"), dict) else {}
    compact["commander_memory_policy"] = {
        "application_mode": str(commander_memory_policy.get("application_mode") or ""),
        "active_layers": [str(x or "") for x in list(commander_memory_policy.get("active_layers") or [])[:4] if str(x or "").strip()],
        "priority_order": [str(x or "") for x in list(commander_memory_policy.get("priority_order") or [])[:4] if str(x or "").strip()],
        "symbol_memory_override_enabled": bool(commander_memory_policy.get("symbol_memory_override_enabled")),
        "scanner_bias_enabled": bool(commander_memory_policy.get("scanner_bias_enabled")),
        "monitor_bias_enabled": bool(commander_memory_policy.get("monitor_bias_enabled")),
    }
    scanner_memory_bias = compact.get("scanner_memory_bias") if isinstance(compact.get("scanner_memory_bias"), dict) else {}
    compact["scanner_memory_bias"] = {
        "enabled": bool(scanner_memory_bias.get("enabled")),
        "active_layers": [str(x or "") for x in list(scanner_memory_bias.get("active_layers") or [])[:4] if str(x or "").strip()],
        "source_weight_delta": dict(scanner_memory_bias.get("source_weight_delta") or {}),
        "symbol_adjustment_count": len(dict(scanner_memory_bias.get("symbol_adjustments") or {})),
    }
    monitor_memory_bias = compact.get("monitor_memory_bias") if isinstance(compact.get("monitor_memory_bias"), dict) else {}
    compact["monitor_memory_bias"] = {
        "enabled": bool(monitor_memory_bias.get("enabled")),
        "active_layers": [str(x or "") for x in list(monitor_memory_bias.get("active_layers") or [])[:4] if str(x or "").strip()],
        "entry_policy_delta": dict(monitor_memory_bias.get("entry_policy_delta") or {}),
        "risk_posture": str(monitor_memory_bias.get("risk_posture") or ""),
    }
    compact["read_model_facts"] = _compact_read_model_facts_for_llm(payload.get("read_model_facts", {}))
    if memory_usage_disabled:
        disabled_stub = {
            "status": "disabled",
            "visible_to_llm": False,
            "reason": "commander_memory_usage_disabled",
        }
        compact["recent_strategy_feedback"] = dict(disabled_stub)
        compact["reporter_feedback_packet"] = dict(disabled_stub)
        compact["strategy_memory"] = dict(disabled_stub)
        compact["read_model_facts"] = {
            **disabled_stub,
            "recent_trade_count": 0,
            "symbol_pattern_count": 0,
        }
        compact["memory_packets"] = {
            "daily_strategy_memory": dict(disabled_stub),
            "weekly_strategy_memory": dict(disabled_stub),
            "monthly_strategy_memory": dict(disabled_stub),
            "symbol_memory_packet": dict(disabled_stub),
        }
        compact["scanner_memory_bias"] = {"enabled": False, "visible_to_llm": False}
        compact["monitor_memory_bias"] = {"enabled": False, "visible_to_llm": False}
        if isinstance(compact.get("commander_refresh_context"), dict):
            compact["commander_refresh_context"]["selected_symbol_memory"] = {}
        compact["memory_disabled_notice"] = (
            "Memory-derived trade history and performance fields are hidden from the strategist LLM; "
            "use only current market, scanner, monitor, refresh, and risk evidence."
        )
    compact["resolved_call_kind"] = _resolve_strategist_llm_call_kind(compact)
    quant_context = build_strategist_quant_context(
        compact,
        call_kind=str(compact["resolved_call_kind"]),
        memory_usage_disabled=memory_usage_disabled,
    )
    quant_scorecard = (
        ((quant_context.get("quant_market_context") or {}).get("scorecard") or {})
        if isinstance(quant_context.get("quant_market_context"), dict)
        else {}
    )
    if not (
        compact["resolved_call_kind"] == "market_strategy_frame"
        and str(quant_scorecard.get("reason") or "") == "reports_root_not_explicit"
    ):
        compact["quant_context"] = dict(quant_context)
    compact = _apply_strategist_llm_token_budget(compact, memory_usage_disabled=memory_usage_disabled)
    compact["resolved_call_kind"] = _resolve_strategist_llm_call_kind(compact)
    if not memory_usage_disabled and compact["resolved_call_kind"] == "market_strategy_frame":
        _hide_stage1_symbol_memory(compact)
    return compact


def _quant_trace_stage_for_call_kind(call_kind: Any) -> str:
    text = str(call_kind or "").strip()
    if text == "selected_symbol_tactical_refresh":
        return "post_scanner_refresh"
    if text == "market_strategy_frame":
        return "initial_frame"
    if text == "stale_intraday_hold_review":
        return "stale_intraday_hold_review"
    if text == "end_of_day_carry_review":
        return "end_of_day_carry_review"
    return text or "quant_context"


def _quant_trace_label_for_stage(stage: str) -> str:
    if stage == "initial_frame":
        return "Quant context - initial frame"
    if stage == "post_scanner_refresh":
        return "Quant context - selected symbol refresh"
    if stage == "stale_intraday_hold_review":
        return "Quant context - stale intraday hold review"
    if stage == "end_of_day_carry_review":
        return "Quant context - end of day carry review"
    return "Quant context"


def _attach_quant_context_to_strategy_refresh_trace(
    trace: Any,
    quant_context: Any,
) -> Dict[str, Any]:
    out = dict(trace or {}) if isinstance(trace, dict) else {}
    ctx = dict(quant_context or {}) if isinstance(quant_context, dict) else {}
    if not ctx:
        return out
    target_stage = _quant_trace_stage_for_call_kind(ctx.get("call_kind"))
    raw_stages = out.get("stages") if isinstance(out.get("stages"), list) else []
    stages: List[Dict[str, Any]] = [dict(row or {}) for row in raw_stages if isinstance(row, dict)]
    attached = False
    for row in stages:
        if str(row.get("stage") or "").strip() == target_stage:
            row["quant_context"] = dict(ctx)
            attached = True
            break
    if not attached:
        stages.append(
            {
                "stage": target_stage,
                "label": _quant_trace_label_for_stage(target_stage),
                "summary": "Strategist LLM received observation-only quant context for this call.",
                "quant_context": dict(ctx),
            }
        )
    out["stages"] = stages
    out["quant_context_call_kind"] = str(ctx.get("call_kind") or "")
    return out


def _build_strategist_llm_repair_messages(payload: Dict[str, Any], raw_response: Any) -> List[Dict[str, str]]:
    compact_payload = _build_compact_strategist_llm_payload(payload)
    call_kind = _resolve_strategist_llm_call_kind(compact_payload)
    system = (
        "You repair strategist outputs for an automated trading system. "
        "Return exactly one minified JSON object only, matching the required contract exactly. "
        "Do not add commentary, markdown, analysis, or explanations. "
        "If the previous draft contained prose, ignore it and generate a fresh JSON object."
    )
    base_contract = {
        "market_regime": "risk_on|neutral|risk_off",
        "market_sentiment": "bullish|neutral|bearish",
        "key_events": ["string"],
        "themes": ["string"],
        "selected_themes": ["string from available_themes only when available"],
        "theme_strategy": {
            "selection_mode": "kiwoom_api_constrained|fallback",
            "selected_themes": [
                {
                    "theme": "string",
                    "playbook_overlay": "momentum|pullback|reversal|defensive|fallback",
                    "scanner_directive": "string",
                    "reason": "string",
                }
            ],
            "fallback_reason": "string",
        },
        "avoid_themes": ["string"],
        "playbook": "breakout|pullback|reversal|defensive",
        "scanner_bias": "large_cap|leader|momentum|value",
        "scanner_priority": ["trading_value", "trend_strength", "volume_surge", "leader_quality"],
        "trade_aggressiveness": "low|medium|high",
        "risk_tone": "conservative|normal|aggressive",
        "monitor_guidance": "hold_through_noise|defensive_exit|quick_take_profit",
        "market_regime_summary": "string",
        "policy_rationale": "string",
        "confidence": 0.0,
        "policy_source": "strategist",
        "policy_adjustment": {
            "adjustment_required": True,
            "baseline_retained": False,
            "baseline_retained_reason": "string",
            "adjustment_direction": "tighten|relax|mixed|none",
            "dominant_failure_pattern": "string",
            "addressed_failure_patterns": ["string"],
            "delta_fields": ["volume_ratio_min"],
            "hold_refresh_considered": True,
        },
        "strategy_refresh_trace": {
            "summary": "string",
            "bullets": ["string"],
            "stages": [
                {
                    "stage": "initial_frame|post_scanner_refresh|final_application",
                    "label": "string",
                    "summary": "string",
                    "requested": True,
                    "effective": False,
                    "reason": "string",
                }
            ],
        },
        "monitor_entry_policy": {
            "timeframe_minutes": 1,
            "breakout_lookback": 5,
            "volume_lookback": 5,
            "volume_ratio_min": 0.68,
            "min_extended_from_vwap_pct": -0.02,
            "max_extended_from_vwap_pct": 0.13,
            "pullback_min_pct": 0.008,
            "pullback_max_pct": 0.07,
            "reclaim_tolerance_pct": 0.0015,
            "breakout_buffer_pct": 0.0,
            "intent_cooldown_sec": 60,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        "report_focus": ["theme_accuracy", "exit_quality", "overtrading"],
    }
    contract = _stage_specific_llm_contract(call_kind, base_contract)
    raw = str(raw_response or "").strip()
    user = (
        "Fix or regenerate the strategist response as valid JSON.\n"
        "JSON contract:\n"
        f"{json.dumps(contract, ensure_ascii=False)}\n\n"
        "Compact input:\n"
        f"{json.dumps(compact_payload, ensure_ascii=False)}\n\n"
        "If Compact input contains available_themes, selected_themes must use only those theme names.\n"
        f"Previous attempt failure reason: {_classify_llm_parse_failure(raw)}\n"
        "Return only the repaired JSON object."
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _messages_to_prompt_text(messages: List[Dict[str, str]]) -> str:
    rows: List[str] = []
    for m in messages:
        role = str(m.get("role") or "").strip().lower() or "unknown"
        content = str(m.get("content") or "")
        rows.append(f"[{role}]\n{content}")
    return "\n\n".join(rows).strip()


def _run_strategist_frame_llm(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    payload: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    run_id = str(state.get("run_id") or "").strip() or "strategist-unknown"
    runtime = strategist_runtime_settings(policy)
    explicit_llm_request = (
        policy.get("strategist_frame_use_llm") is not None
        or bool(str(os.getenv("STRATEGIST_FRAME_USE_LLM", "") or "").strip())
    )
    if not bool(runtime.get("requested")):
        return {}, {"enabled": False, "status": "disabled", "reason": "strategist_frame_llm_disabled"}

    if _env_bool("DRY_RUN", False):
        return {}, {"enabled": True, "status": "dry_run", "reason": "dry_run"}

    if not bool(runtime.get("uses_ai")) and not bool(explicit_llm_request):
        return {}, {"enabled": True, "status": "disabled", "reason": "strategist_provider_not_ai"}

    # Phase 5-4 / 6-1 LLM Policy Enforcement
    primary_model = normalize_openrouter_model_name(str(runtime.get("model") or ""))
    fallback_model = normalize_openrouter_model_name(str(runtime.get("fallback_model") or ""))
    max_retries = max(1, _to_int(runtime.get("retry_max"), 2))
    temperature = float(runtime.get("temperature") or 0.1)
    max_tokens = max(256, int(runtime.get("max_tokens") or 8192))
    timeout_sec = max(1.0, float(runtime.get("timeout_sec") or 15.0))
    retry_backoff_sec = max(0.0, float(runtime.get("retry_backoff_sec") or 0.0))

    router = LLMRouter.from_env()
    if router.client is None:
        return {}, {"enabled": True, "status": "unavailable", "reason": "llm_client_unavailable"}

    route_policy: Dict[str, Any] = {
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "timeout_sec": float(timeout_sec),
    }
    if _env_bool("STRATEGIST_FRAME_LLM_JSON_RESPONSE_FORMAT", True):
        route_policy["response_format"] = {"type": "json_object"}
        
    compact_payload = _build_compact_strategist_llm_payload(payload)
    quant_context_for_trace = (
        dict(compact_payload.get("quant_context") or {})
        if isinstance(compact_payload.get("quant_context"), dict)
        else {}
    )
    refresh_context = (
        compact_payload.get("commander_refresh_context")
        if isinstance(compact_payload.get("commander_refresh_context"), dict)
        else {}
    )
    if bool(refresh_context.get("requested")):
        refresh_token_cap = max(1024, int(_env_int("STRATEGIST_REFRESH_MAX_TOKENS") or 2048))
        if max_tokens > refresh_token_cap:
            max_tokens = int(refresh_token_cap)
            route_policy["max_tokens"] = int(max_tokens)
            effective_config = dict(runtime.get("llm_execution_effective_config") or {})
            effective_config["max_tokens"] = int(max_tokens)
            effective_config["refresh_token_cap_applied"] = True
            runtime["llm_execution_effective_config"] = effective_config

    llm_call_trace = {
        "primary_attempted": True,
        "primary_failed": False,
        "fallback_used": False,
        "final_model": primary_model,
        "final_provider": "strategist_router",
        "final_status": "pending",
        "llm_profile": str(runtime.get("llm_profile") or ""),
        "llm_policy_source": str(runtime.get("llm_policy_source") or ""),
        "llm_execution_profile": str(runtime.get("llm_execution_profile_name") or ((runtime.get("llm_execution_profile") or {}).get("name") or "")),
        "llm_execution_profile_name": str(runtime.get("llm_execution_profile_name") or ((runtime.get("llm_execution_profile") or {}).get("name") or "")),
        "llm_execution_profile_source": str(runtime.get("llm_execution_profile_source") or ((runtime.get("llm_execution_profile") or {}).get("policy_source") or "")),
        "llm_execution_effective_config": dict(
            runtime.get("llm_execution_effective_config")
            or {
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
                "timeout_sec": float(timeout_sec),
                "retry": {
                    "max_attempts": int(max_retries),
                    "backoff_sec": float(retry_backoff_sec),
                },
            }
        ),
    }

    def _persist_llm_artifacts(
        *,
        stage: str,
        prompt_value: Any,
        response_value: Any,
        status: str,
        reason: str = "",
        attempts_count: int = 1,
        repair: bool = False,
        active_model: str = "",
    ) -> Dict[str, Any]:
        try:
            call_kind = _resolve_strategist_llm_call_kind(compact_payload)
            stage_descriptor = strategist_llm_stage_descriptor(call_kind)
            stage_component = str(stage_descriptor.get("component") or "strategist_stage1_market_frame")
            stage_index = int(stage_descriptor.get("stage_index") or 1)
            stage_name = str(stage_descriptor.get("stage_name") or call_kind)
            prompt_payload = {
                "stage": str(stage or "theme_selection"),
                "stage_index": int(stage_index),
                "stage_name": stage_name,
                "call_kind": call_kind,
                "stage_component": stage_component,
                "provider": "strategist_router",
                "model": active_model,
                "payload": dict(compact_payload),
                "messages": [], # omitted for brevity in loop
                "prompt_text": str(prompt_value or ""),
                "temperature": float(temperature),
                "max_tokens": int(max_tokens),
                "timeout_sec": float(timeout_sec),
                "retry_max": int(max_retries),
                "retry_backoff_sec": float(retry_backoff_sec),
                "llm_execution_profile_name": str(runtime.get("llm_execution_profile_name") or ""),
                "llm_execution_profile_source": str(runtime.get("llm_execution_profile_source") or ""),
                "llm_execution_effective_config": dict(runtime.get("llm_execution_effective_config") or {}),
            }
            response_payload = {
                "stage": str(stage or "theme_selection"),
                "stage_index": int(stage_index),
                "stage_name": stage_name,
                "call_kind": call_kind,
                "stage_component": stage_component,
                "provider": "strategist_router",
                "model": active_model,
                "status": str(status or ""),
                "reason": str(reason or ""),
                "repair_used": bool(repair),
                "attempts": int(attempts_count),
                "llm_execution_profile_name": str(runtime.get("llm_execution_profile_name") or ""),
                "llm_execution_profile_source": str(runtime.get("llm_execution_profile_source") or ""),
                "llm_execution_effective_config": dict(runtime.get("llm_execution_effective_config") or {}),
                "response_text": str(response_value or ""),
            }
            meta_payload = {
                "component": "strategist",
                "llm_status": str(status or ""),
                "status": str(status or ""),
                "reason": str(reason or ""),
                "model": active_model,
                "attempts": int(attempts_count),
                "repair_used": bool(repair),
                "stage": str(stage or "theme_selection"),
                "stage_index": int(stage_index),
                "stage_name": stage_name,
                "call_kind": call_kind,
                "stage_component": stage_component,
                "llm_execution_profile_name": str(runtime.get("llm_execution_profile_name") or ""),
                "llm_execution_profile_source": str(runtime.get("llm_execution_profile_source") or ""),
                "llm_execution_effective_config": dict(runtime.get("llm_execution_effective_config") or {}),
            }
            legacy_refs = write_llm_artifact_bundle(
                state,
                artifact_name="strategist",
                prompt_payload=prompt_payload,
                response_payload=response_payload,
                meta_payload=meta_payload,
            )
            stage_refs = write_llm_artifact_bundle(
                state,
                artifact_name=stage_component,
                prompt_payload={**dict(prompt_payload), "artifact_role": "stage_specific"},
                response_payload={**dict(response_payload), "artifact_role": "stage_specific"},
                meta_payload={
                    **dict(meta_payload),
                    "component": stage_component,
                    "legacy_component": "strategist",
                    "artifact_role": "stage_specific",
                },
            )
            manifest_refs = write_llm_stage_manifest_entry(
                state,
                {
                    "stage_index": int(stage_index),
                    "stage_name": stage_name,
                    "call_kind": call_kind,
                    "component": stage_component,
                    "status": str(status or ""),
                    "reason": str(reason or ""),
                    "model": active_model,
                    "prompt_ref": str(stage_refs.get("prompt_ref") or ""),
                    "response_ref": str(stage_refs.get("response_ref") or ""),
                    "meta_ref": str(stage_refs.get("meta_ref") or ""),
                    "legacy_prompt_ref": str(legacy_refs.get("prompt_ref") or ""),
                    "legacy_response_ref": str(legacy_refs.get("response_ref") or ""),
                    "legacy_meta_ref": str(legacy_refs.get("meta_ref") or ""),
                    "strategist_summary_md_ref": str(legacy_refs.get("strategist_summary_md_ref") or ""),
                    "strategist_summary_json_ref": str(legacy_refs.get("strategist_summary_json_ref") or ""),
                },
            )
            return {
                **dict(legacy_refs),
                "llm_stage_component": stage_component,
                "llm_stage_index": int(stage_index),
                "llm_stage_name": stage_name,
                "llm_call_kind": call_kind,
                "stage_prompt_ref": str(stage_refs.get("prompt_ref") or ""),
                "stage_response_ref": str(stage_refs.get("response_ref") or ""),
                "stage_meta_ref": str(stage_refs.get("meta_ref") or ""),
                "llm_stage_manifest_ref": str(manifest_refs.get("llm_stage_manifest_ref") or ""),
            }
        except Exception:
            return {}

    attempts = 0
    repair_used = False
    current_model = primary_model
    last_reason = ""
    last_error_type = ""
    last_raw = ""
    
    while attempts < max_retries + 1:
        attempts += 1
        
        if attempts > 1 and attempts == max_retries + 1 and fallback_model:
            current_model = fallback_model
            llm_call_trace["primary_failed"] = True
            llm_call_trace["fallback_used"] = True
            
        route_policy["model"] = current_model
        llm_call_trace["final_model"] = current_model
        
        if repair_used and last_raw:
            route_policy["temperature"] = 0.0
            route_policy["max_tokens"] = min(max(384, int(max_tokens)), 768)
            messages = _build_strategist_llm_repair_messages(compact_payload, last_raw)
            stage_name = "theme_selection_repair"
        else:
            messages = _build_strategist_llm_messages(compact_payload)
            stage_name = "theme_selection"
            
        prompt_text = _messages_to_prompt_text(messages)
        llm_call_trace["prompt_chars"] = int(len(prompt_text))
        llm_call_trace["compact_payload_chars"] = int(
            len(json.dumps(compact_payload, ensure_ascii=False, separators=(",", ":")))
        )
        
        try:
            record_llm_prompt(
                run_id=run_id,
                agent="strategist",
                stage=stage_name,
                raw_input=dict(compact_payload),
                llm_prompt=prompt_text,
                decision_link={
                    "model": current_model,
                    "provider": "strategist_router",
                    "temperature": float(route_policy.get("temperature", 0.1)),
                    "max_tokens": int(route_policy.get("max_tokens", 320)),
                    "repair": repair_used,
                },
            )
        except Exception:
            pass

        t0 = time.perf_counter()
        try:
            raw = router.chat("strategist", messages, policy=route_policy)
            latency_ms = int((time.perf_counter() - t0) * 1000)
            
            obj = _extract_json_object(raw)
            if isinstance(obj, dict) and obj:
                overrides = _normalize_llm_overrides(obj)
                if overrides:
                    llm_call_trace["final_status"] = "ok"
                    llm_artifacts = _persist_llm_artifacts(
                        stage=stage_name, prompt_value=prompt_text, response_value=raw,
                        status="ok", attempts_count=attempts, repair=repair_used, active_model=current_model
                    )
                    try:
                        record_llm_response(
                            run_id=run_id, agent="strategist", stage=stage_name,
                            llm_response=str(raw or ""), parsed_output=dict(overrides),
                            decision_link={"status": "ok", "model": current_model, "attempts": attempts, "repair": repair_used},
                        )
                    except Exception:
                        pass
                    return overrides, {
                        "enabled": True, "status": "ok", "latency_ms": latency_ms,
                        "model": current_model, "attempts": attempts, "repair_used": repair_used,
                        "recovery_method": "" if str(raw or "").strip().startswith("{") else "prose_contract",
                        "llm_call_trace": dict(llm_call_trace),
                        "llm_execution_profile_name": str(runtime.get("llm_execution_profile_name") or ""),
                        "llm_execution_profile_source": str(runtime.get("llm_execution_profile_source") or ""),
                        "llm_execution_effective_config": dict(runtime.get("llm_execution_effective_config") or {}),
                        "prompt_ref": str(llm_artifacts.get("prompt_ref") or ""),
                        "response_ref": str(llm_artifacts.get("response_ref") or ""),
                        "prompt_hash": str(llm_artifacts.get("prompt_hash") or ""),
                        "response_hash": str(llm_artifacts.get("response_hash") or ""),
                        "llm_stage_component": str(llm_artifacts.get("llm_stage_component") or ""),
                        "llm_stage_index": int(llm_artifacts.get("llm_stage_index") or 0),
                        "llm_stage_name": str(llm_artifacts.get("llm_stage_name") or ""),
                        "llm_call_kind": str(llm_artifacts.get("llm_call_kind") or ""),
                        "stage_prompt_ref": str(llm_artifacts.get("stage_prompt_ref") or ""),
                        "stage_response_ref": str(llm_artifacts.get("stage_response_ref") or ""),
                        "stage_meta_ref": str(llm_artifacts.get("stage_meta_ref") or ""),
                        "llm_stage_manifest_ref": str(llm_artifacts.get("llm_stage_manifest_ref") or ""),
                        "quant_context": dict(quant_context_for_trace),
                    }
                    
            last_raw = raw
            last_reason = _classify_llm_parse_failure(raw)
            last_error_type = "ParseError"
            repair_used = True
            
            _persist_llm_artifacts(stage=stage_name, prompt_value=prompt_text, response_value=raw, status="parse_error", reason=last_reason, attempts_count=attempts, repair=repair_used, active_model=current_model)
            try:
                record_llm_response(run_id=run_id, agent="strategist", stage=stage_name, llm_response=str(raw or ""), parsed_output={}, decision_link={"status": "parse_error", "repair": repair_used})
            except Exception:
                pass
                
        except Exception as e:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            last_error_type = type(e).__name__
            last_reason = str(e)
            _persist_llm_artifacts(stage=stage_name, prompt_value=prompt_text, response_value=f"ERROR:{last_error_type}:{last_reason}", status="error", reason=last_reason, attempts_count=attempts, repair=repair_used, active_model=current_model)
            try:
                record_llm_response(run_id=run_id, agent="strategist", stage=stage_name, llm_response=f"ERROR:{last_error_type}:{last_reason}", parsed_output={}, decision_link={"status": "error", "repair": repair_used})
            except Exception:
                pass

    llm_call_trace["final_status"] = "error" if last_error_type != "ParseError" else "parse_error"
    if fallback_model and not llm_call_trace["fallback_used"]:
        llm_call_trace["primary_failed"] = True
        
    return {}, {
        "enabled": True,
        "status": llm_call_trace["final_status"],
        "reason": last_reason,
        "error_type": last_error_type,
        "latency_ms": latency_ms,
        "model": current_model,
        "attempts": attempts,
        "repair_used": repair_used,
        "llm_call_trace": dict(llm_call_trace),
        "llm_execution_profile_name": str(runtime.get("llm_execution_profile_name") or ""),
        "llm_execution_profile_source": str(runtime.get("llm_execution_profile_source") or ""),
        "llm_execution_effective_config": dict(runtime.get("llm_execution_effective_config") or {}),
        "quant_context": dict(quant_context_for_trace),
    }

def _extract_themes(state: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    seen = set()

    def add_many(items: Any) -> None:
        if not isinstance(items, list):
            return
        for x in items:
            t = str(x or "").strip()
            if not t or t in seen:
                continue
            seen.add(t)
            out.append(t)

    add_many(state.get("themes"))
    add_many(state.get("top_themes"))
    add_many(state.get("sector_filter"))
    add_many(state.get("theme_filter"))
    add_many(policy.get("themes"))
    add_many(policy.get("top_themes"))
    add_many(policy.get("sector_filter"))
    add_many(policy.get("theme_filter"))

    theme_scores = state.get("theme_scores") if isinstance(state.get("theme_scores"), dict) else {}
    if theme_scores:
        ranked = sorted(
            ((str(k or "").strip(), float(v or 0.0)) for k, v in theme_scores.items()),
            key=lambda kv: kv[1],
            reverse=True,
        )
        for name, _score in ranked:
            if name and name not in seen:
                seen.add(name)
                out.append(name)

    theme_map = policy.get("theme_map") if isinstance(policy.get("theme_map"), dict) else {}
    for k in theme_map.keys():
        name = str(k or "").strip()
        if name and name not in seen:
            seen.add(name)
            out.append(name)

    return out[:5]


def _append_unique_text(out: List[str], seen: set[str], raw: Any) -> None:
    s = str(raw or "").strip()
    if not s:
        return
    key = s.lower()
    if key in seen:
        return
    seen.add(key)
    out.append(s)


def _theme_to_news_queries(theme: Any) -> List[str]:
    raw = str(theme or "").strip()
    if not raw:
        return []
    key = raw.lower().replace("-", "_").replace(" ", "_")
    direct_map: Dict[str, List[str]] = {
        "semiconductor": ["반도체", "HBM", "메모리"],
        "semiconductors_hbm": ["반도체", "HBM", "메모리"],
        "ai": ["AI", "인공지능"],
        "battery": ["2차전지", "배터리"],
        "secondary_battery": ["2차전지", "배터리"],
        "defense": ["방산"],
        "energy_security": ["에너지", "국제유가", "천연가스"],
        "renewable_energy": ["재생에너지", "태양광"],
        "bio": ["바이오", "제약"],
        "healthcare": ["헬스케어", "바이오"],
        "finance": ["금융", "은행"],
        "banks": ["금융", "은행"],
        "internet": ["인터넷", "플랫폼"],
        "platform": ["플랫폼", "인터넷"],
        "shipbuilding": ["조선"],
        "autos": ["자동차"],
        "robotics": ["로봇"],
        "broad_market_leaders": ["시가총액 상위", "주도주"],
        "quality_factor": ["실적주", "대형주"],
        "low_volatility": ["방어주", "저변동성"],
    }
    if key in direct_map:
        return list(direct_map[key])
    terms: List[str] = []
    if "semiconductor" in key or "memory" in key:
        terms.extend(["반도체", "HBM"])
    if key == "ai" or "artificial_intelligence" in key:
        terms.extend(["AI", "인공지능"])
    if "energy" in key:
        terms.extend(["에너지", "국제유가"])
    if "defense" in key:
        terms.append("방산")
    if "battery" in key:
        terms.extend(["2차전지", "배터리"])
    if "bank" in key or "finance" in key:
        terms.extend(["금융", "은행"])
    if not terms:
        terms.append(raw)
    return terms


def _theme_news_query_terms(theme_hints: List[str], *, limit: int = 8) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in list(theme_hints or [])[:5]:
        text = str(raw or "").strip()
        if not text:
            continue
        _append_unique_text(out, seen, text)
        for q in _theme_to_news_queries(text)[:2]:
            _append_unique_text(out, seen, q)
        if len(out) >= max(1, int(limit)):
            break
    return out[: max(1, int(limit))]


def _theme_component_symbols_for_news(
    *,
    state: Dict[str, Any],
    available_themes: List[Dict[str, Any]],
    theme_hints: List[str],
    limit: int,
) -> List[str]:
    max_symbols = max(0, int(limit))
    if max_symbols <= 0:
        return []
    selected_keys = {str(x or "").strip().lower() for x in list(theme_hints or []) if str(x or "").strip()}
    out: List[str] = []
    seen: set[str] = set()

    def add_symbol(raw: Any) -> None:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen or len(out) >= max_symbols:
            return
        seen.add(symbol)
        out.append(symbol)

    for row in list(available_themes or [])[:5]:
        if not isinstance(row, dict):
            continue
        theme_name = str(row.get("theme") or row.get("theme_name") or "").strip().lower()
        if selected_keys and theme_name and theme_name not in selected_keys:
            continue
        for sym in list(row.get("component_symbols") or [])[:4]:
            add_symbol(sym)
        if len(out) >= max_symbols:
            return out

    for raw_map in (state.get("theme_map"), state.get("sector_map")):
        if not isinstance(raw_map, dict):
            continue
        for theme_name, symbols in raw_map.items():
            key = str(theme_name or "").strip().lower()
            if selected_keys and key and key not in selected_keys:
                continue
            if not isinstance(symbols, list):
                continue
            for sym in symbols[:4]:
                add_symbol(sym)
            if len(out) >= max_symbols:
                return out
    return out


def _merge_news_collection_symbols(*, base_symbols: List[str], theme_symbols: List[str], limit: int) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for raw in [*list(base_symbols or []), *list(theme_symbols or [])]:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        out.append(symbol)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _build_market_news_query_targets(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    global_signal: Dict[str, Any],
    market_context_inputs: Dict[str, float],
    theme_hints: List[str],
) -> List[str]:
    limit = max(
        3,
        _to_int(
            policy.get("strategist_news_query_limit")
            if policy.get("strategist_news_query_limit") is not None
            else os.getenv("STRATEGIST_NEWS_QUERY_LIMIT", "10"),
            10,
        ),
    )
    out: List[str] = []
    seen: set[str] = set()

    explicit_targets: List[Any] = []
    if isinstance(state.get("news_query_targets"), list):
        explicit_targets.extend(list(state.get("news_query_targets") or []))
    if isinstance(policy.get("news_query_targets"), list):
        explicit_targets.extend(list(policy.get("news_query_targets") or []))
    env_targets = str(os.getenv("NEWS_QUERY_TARGETS", "") or "").strip()
    if env_targets:
        explicit_targets.extend([x.strip() for x in env_targets.split(",") if str(x).strip()])
    for raw in explicit_targets:
        _append_unique_text(out, seen, raw)

    global_score = _signal_score(global_signal)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    index_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)
    realized_volatility = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    market_breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    vix_level = _to_float(fear_index.get("level"), 0.0)
    vix_pressure = _to_float(fear_index.get("level_pressure"), 0.0)
    elevated_fear = vix_level >= 25.0 or vix_pressure >= 0.25
    theme_news_terms = _theme_news_query_terms(theme_hints, limit=4)
    for raw in theme_news_terms:
        _append_unique_text(out, seen, raw)
    if global_score <= -0.20 or macro_risk >= 0.65 or elevated_fear:
        base_queries = ["코스피", "미국 증시", "국제유가", "환율", "중동"]
    elif global_score >= 0.20 and index_trend >= -0.05:
        base_queries = ["코스피", "코스닥", "미국 증시", "위험선호", "주도주"]
    else:
        base_queries = ["코스피", "코스닥", "미국 증시", "증시 전망", "거시경제"]
    for raw in base_queries:
        _append_unique_text(out, seen, raw)

    if not theme_news_terms:
        for raw in list(theme_hints or [])[:5]:
            for q in _theme_to_news_queries(raw)[:2]:
                _append_unique_text(out, seen, q)

    if realized_volatility >= 0.03:
        _append_unique_text(out, seen, "변동성 확대")
    if market_breadth <= 0.40:
        for raw in ("하락 종목 수", "약세 업종"):
            _append_unique_text(out, seen, raw)
    elif market_breadth >= 0.60:
        for raw in ("상승 종목 수", "주도 섹터"):
            _append_unique_text(out, seen, raw)

    if macro_risk >= 0.65 or elevated_fear:
        for raw in ("국제유가", "환율", "달러", "중동", "방산", "금"):
            _append_unique_text(out, seen, raw)
    elif global_score <= -0.20:
        for raw in ("환율", "달러", "국채금리", "금", "방어주"):
            _append_unique_text(out, seen, raw)
    elif global_score >= 0.20 and index_trend >= 0.10:
        for raw in ("주도주", "실적주", "수출주"):
            _append_unique_text(out, seen, raw)

    for key in ("macro_events", "global_events", "major_events"):
        values = state.get(key)
        if not isinstance(values, list):
            continue
        for raw in list(values)[:3]:
            _append_unique_text(out, seen, raw)
        if values:
            break

    return out[:limit]



def _build_market_news_query_reasoning(
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    global_signal: Dict[str, Any],
    market_context_inputs: Dict[str, float],
    theme_hints: List[str],
) -> str:
    explicit_targets: List[str] = []
    if isinstance(state.get("news_query_targets"), list):
        explicit_targets.extend([str(x).strip() for x in list(state.get("news_query_targets") or []) if str(x).strip()])
    if isinstance(policy.get("news_query_targets"), list):
        explicit_targets.extend([str(x).strip() for x in list(policy.get("news_query_targets") or []) if str(x).strip()])
    env_targets = str(os.getenv("NEWS_QUERY_TARGETS", "") or "").strip()
    if env_targets:
        explicit_targets.extend([x.strip() for x in env_targets.split(",") if str(x).strip()])

    global_score = _signal_score(global_signal)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    index_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)
    realized_volatility = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    market_breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    vix_level = _to_float(fear_index.get("level"), 0.0)
    vix_pressure = _to_float(fear_index.get("level_pressure"), 0.0)
    elevated_fear = vix_level >= 25.0 or vix_pressure >= 0.25

    reasons: List[str] = [
        (
            f"global_score={global_score:.2f} macro_risk={macro_risk:.2f} "
            f"index_trend={index_trend:.2f} vix={vix_level:.2f} vix_pressure={vix_pressure:.3f}"
        )
    ]
    if explicit_targets:
        reasons.append(f"explicit_targets_first={', '.join(explicit_targets[:4])}")

    if macro_risk >= 0.65:
        reasons.append("risk-off macro context added oil/fx/geopolitics market queries")
    elif elevated_fear:
        reasons.append("elevated fear index added defensive macro and hedge queries")
    elif global_score <= -0.20:
        reasons.append("risk-off sentiment added oil/fx/geopolitics market queries")
    elif global_score >= 0.20 and index_trend >= -0.05:
        reasons.append("risk-on context added leader/risk-appetite market queries")
    else:
        reasons.append("neutral context kept broad market and macro queries")

    normalized_themes = [str(x).strip() for x in list(theme_hints or []) if str(x).strip()]
    if normalized_themes:
        reasons.append(f"theme hints expanded queries from {', '.join(normalized_themes[:3])}")

    if realized_volatility >= 0.03:
        reasons.append("intraday volatility added 변동성 확대 query")
    if market_breadth <= 0.40:
        reasons.append("weak breadth added 하락 종목 수/약세 업종 queries")
    elif market_breadth >= 0.60:
        reasons.append("strong breadth added 상승 종목 수/주도 섹터 queries")

    for key in ("macro_events", "global_events", "major_events"):
        values = state.get(key)
        if isinstance(values, list):
            normalized = [str(x).strip() for x in list(values or []) if str(x).strip()]
            if normalized:
                reasons.append(f"macro events appended {', '.join(normalized[:2])}")
                break

    return "; ".join(reasons)



def _default_policy(user_policy: Dict[str, Any] | None) -> Dict[str, Any]:
    p = dict(user_policy or {})
    default_topn = _resolve_top_n_candidates(p)
    pytest_mode = bool(os.getenv("PYTEST_CURRENT_TEST"))
    p.setdefault("use_universe_builder", _is_trueish(os.getenv("USE_UNIVERSE_BUILDER", "true")))
    p.setdefault("universe_require_condition", _is_trueish(os.getenv("UNIVERSE_REQUIRE_CONDITION", "false")))
    # candidate generation
    p.setdefault("candidate_source", "top_picks")  # top_picks | market_rank
    p.setdefault("candidate_k", int(p.get("candidate_topk", default_topn) or default_topn))
    p.setdefault("candidate_rank_mode", "value")
    p.setdefault("candidate_rank_topn", 30)
    # sentiment toggles
    p.setdefault(
        "use_global_sentiment",
        _is_trueish(os.getenv("M10_USE_GLOBAL_SENTIMENT", "false" if pytest_mode else "true")),
    )
    p.setdefault(
        "use_news_analysis",
        _is_trueish(os.getenv("M10_USE_NEWS_SENTIMENT", "false" if pytest_mode else "true")),
    )
    exit_enabled = _nested_mapping_value(p, "applied_policy", "monitor", "exit", "enabled")
    if exit_enabled is None:
        exit_enabled = p.get("use_exit_policy")
    p.setdefault("use_exit_policy", True if exit_enabled is None else _is_trueish(exit_enabled))
    # news plugin
    p.setdefault("news_provider", "naver")
    p.setdefault("news_scorer", "simple")
    # rerank weights
    p.setdefault("candidate_news_weight", 0.2)
    p.setdefault("candidate_global_weight", 0.1)
    p.setdefault("candidate_negative_news_threshold", -0.7)
    p.setdefault("candidate_risk_off_threshold", -0.5)
    p.setdefault("candidate_risk_on_threshold", 0.5)
    p.setdefault("candidate_max_count_risk_off", 3)
    return p


def _candidates_from_state(state: Dict[str, Any], k: int) -> List[Dict[str, str]]:
    # Highest priority: explicit candidates provided
    if isinstance(state.get("candidates"), list) and state["candidates"]:
        out = []
        for x in state["candidates"][:k]:
            if isinstance(x, dict) and "symbol" in x:
                out.append({"symbol": str(x["symbol"]), "why": str(x.get("why") or "injected")})
        return out

    # Next: universe list (tests)
    if isinstance(state.get("universe"), list) and state["universe"]:
        syms = [str(s) for s in state["universe"][:k]]
        return [{"symbol": s, "why": "universe"} for s in syms]

    # Next: direct candidate symbols injection
    if isinstance(state.get("candidate_symbols"), list) and state["candidate_symbols"]:
        syms = [str(s) for s in state["candidate_symbols"][:k]]
        return [{"symbol": s, "why": "candidate_symbols"} for s in syms]

    return []


def _signal_score(sig: Any) -> float:
    if not isinstance(sig, dict):
        return 0.0
    try:
        return float(sig.get("score") or 0.0)
    except Exception:
        return 0.0


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _risk_regime_label(score: float) -> str:
    if score >= 0.20:
        return "risk_on"
    if score <= -0.20:
        return "risk_off"
    return "neutral"


def _market_sentiment_label(score: float) -> str:
    if score >= 0.15:
        return "bullish"
    if score <= -0.15:
        return "bearish"
    return "neutral"


def _extract_market_context_inputs(state: Dict[str, Any]) -> Dict[str, float]:
    market_ctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    macro_ctx = state.get("macro_context") if isinstance(state.get("macro_context"), dict) else {}
    kiwoom_summary = state.get("kiwoom_market_summary") if isinstance(state.get("kiwoom_market_summary"), dict) else {}
    global_signal = state.get("global_sentiment_signal") if isinstance(state.get("global_sentiment_signal"), dict) else {}
    korea_indices = global_signal.get("korea_indices") if isinstance(global_signal.get("korea_indices"), dict) else {}
    korea_avg_change_pct = _to_float(korea_indices.get("average_change_pct"), 0.0)
    korea_breadth = (
        _to_float(korea_indices.get("breadth"), 0.0)
        if korea_indices.get("breadth") not in (None, "")
        else None
    )
    index_trend = _to_float(
        market_ctx.get("index_trend")
        if market_ctx.get("index_trend") is not None
        else (
            kiwoom_summary.get("index_trend")
            if kiwoom_summary.get("index_trend") is not None
            else korea_avg_change_pct / 5.0
            if korea_indices
            else 0.0
        ),
        0.0,
    )
    realized_vol = _to_float(
        market_ctx.get("realized_volatility")
        if market_ctx.get("realized_volatility") is not None
        else (
            market_ctx.get("realized_vol")
            if market_ctx.get("realized_vol") is not None
            else kiwoom_summary.get("realized_volatility")
        ),
        0.0,
    )
    breadth_raw = market_ctx.get("market_breadth")
    if breadth_raw is None:
        breadth_raw = kiwoom_summary.get("market_breadth")
    if breadth_raw is None and korea_breadth is not None:
        breadth_raw = korea_breadth
    market_breadth = _to_float(breadth_raw, 0.0)
    if market_breadth > 1.0:
        market_breadth = _clamp(market_breadth / 100.0, -1.0, 1.0)
    macro_risk = _to_float(
        market_ctx.get("macro_risk")
        if market_ctx.get("macro_risk") is not None
        else (
            macro_ctx.get("macro_risk")
            if macro_ctx.get("macro_risk") is not None
            else kiwoom_summary.get("macro_risk")
        ),
        0.0,
    )
    return {
        "index_trend": float(_clamp(index_trend, -1.0, 1.0)),
        "realized_volatility": float(max(0.0, realized_vol)),
        "market_breadth": float(_clamp(market_breadth, -1.0, 1.0)),
        "macro_risk": float(_clamp(macro_risk, 0.0, 1.0)),
    }


def _market_structure_label(
    *,
    state: Dict[str, Any],
    global_score: float,
    market_context_inputs: Dict[str, float],
) -> Tuple[str, Dict[str, Any]]:
    idx_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)
    realized_vol = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    breadth_01 = _clamp((breadth + 1.0) / 2.0, 0.0, 1.0)
    regime_obj = classify_regime_v2(
        ma20_gap=idx_trend,
        volatility20=realized_vol,
        index_trend=idx_trend,
        realized_volatility=realized_vol,
        global_sentiment=global_score,
        market_breadth=breadth_01,
    )
    regime = str(regime_obj.get("regime") or "").strip().lower()
    if regime in ("trend", "range", "high_volatility"):
        return regime, dict(regime_obj.get("factors") or {})
    # fallback
    if realized_vol >= 0.040:
        return "high_volatility", {}
    if abs(idx_trend) >= 0.25 and abs(breadth) >= 0.50:
        return "trend", {}
    return "range", {}


def _extract_theme_symbol_index(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = {}

    def add_map(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        for k, symbols in raw.items():
            name = str(k or "").strip().lower()
            if not name:
                continue
            bucket = out.setdefault(name, set())
            if isinstance(symbols, list):
                for sym in symbols:
                    s = str(sym or "").strip().upper()
                    if s:
                        bucket.add(s)

    add_map(state.get("theme_map"))
    add_map(state.get("sector_map"))
    add_map(policy.get("theme_map"))
    add_map(policy.get("sector_map"))
    return out


def _merge_theme_symbol_map(
    existing: Any,
    *,
    themes: List[str],
    candidate_symbols: List[str],
    protect_existing_themes: bool = False,
) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}

    if isinstance(existing, dict):
        for key, symbols in existing.items():
            name = str(key or "").strip().lower()
            if not name:
                continue
            merged: List[str] = []
            seen: set[str] = set()
            if isinstance(symbols, list):
                for sym in symbols:
                    s = str(sym or "").strip().upper()
                    if not s or s in seen:
                        continue
                    seen.add(s)
                    merged.append(s)
            out[name] = merged

    if not candidate_symbols:
        return out

    for theme in themes:
        name = str(theme or "").strip().lower()
        if not name:
            continue
        bucket = list(out.get(name) or [])
        if protect_existing_themes:
            out[name] = bucket
            continue
        seen = set(bucket)
        for sym in candidate_symbols:
            s = str(sym or "").strip().upper()
            if not s or s in seen:
                continue
            seen.add(s)
            bucket.append(s)
        out[name] = bucket
    return out


def _theme_packet_symbol_map_is_authoritative(packet: Dict[str, Any]) -> bool:
    if not isinstance(packet, dict):
        return False
    return str(packet.get("status") or "").strip().lower() == "ok" and not bool(packet.get("fallback_used"))


def _merge_theme_packet_into_state(state: Dict[str, Any], packet: Dict[str, Any]) -> None:
    if not isinstance(packet, dict):
        return

    top_theme_names: List[str] = []
    for row in list(packet.get("top_themes") or []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("theme_name") or "").strip()
        if name and name.lower() not in {x.lower() for x in top_theme_names}:
            top_theme_names.append(name)

    if top_theme_names:
        existing_top = list(state.get("top_themes") or []) if isinstance(state.get("top_themes"), list) else []
        merged_top: List[str] = []
        seen_top: set[str] = set()
        for name in [*existing_top, *top_theme_names]:
            text = str(name or "").strip()
            key = text.lower()
            if not text or key in seen_top:
                continue
            seen_top.add(key)
            merged_top.append(text)
        state["top_themes"] = merged_top[:8]

    packet_scores = packet.get("theme_scores") if isinstance(packet.get("theme_scores"), dict) else {}
    if packet_scores:
        scores = dict(state.get("theme_scores") or {}) if isinstance(state.get("theme_scores"), dict) else {}
        lowered = {str(k or "").strip().lower() for k in scores.keys()}
        for name, score in packet_scores.items():
            text = str(name or "").strip()
            if not text or text.lower() in lowered:
                continue
            scores[text] = score
            lowered.add(text.lower())
        state["theme_scores"] = scores

    packet_map = packet.get("theme_map") if isinstance(packet.get("theme_map"), dict) else {}
    packet_map_authoritative = _theme_packet_symbol_map_is_authoritative(packet)
    if packet_map or packet_map_authoritative:
        top_theme_keys = {str(name or "").strip().lower() for name in top_theme_names if str(name or "").strip()}

        def packet_symbols_for(theme_key: str) -> List[str]:
            for key, symbols in packet_map.items():
                name = str(key or "").strip().lower()
                if name != theme_key:
                    continue
                out_symbols: List[str] = []
                seen_symbols: set[str] = set()
                if isinstance(symbols, list):
                    for sym in symbols:
                        s = str(sym or "").strip().upper()
                        if not s or s in seen_symbols:
                            continue
                        seen_symbols.add(s)
                        out_symbols.append(s)
                return out_symbols
            return []

        def merge_map(existing: Any) -> Dict[str, List[str]]:
            out: Dict[str, List[str]] = {}
            if isinstance(existing, dict):
                for key, symbols in existing.items():
                    name = str(key or "").strip().lower()
                    if not name:
                        continue
                    bucket: List[str] = []
                    seen: set[str] = set()
                    if isinstance(symbols, list):
                        for sym in symbols:
                            s = str(sym or "").strip().upper()
                            if not s or s in seen:
                                continue
                            seen.add(s)
                            bucket.append(s)
                    out[name] = bucket
            if packet_map_authoritative:
                for name in top_theme_keys:
                    # A Kiwoom theme with no returned component list must stay
                    # empty. Do not backfill it with broad scanner candidates.
                    out[name] = packet_symbols_for(name)
            for key, symbols in packet_map.items():
                name = str(key or "").strip().lower()
                if not name:
                    continue
                bucket = list(out.get(name) or [])
                seen = set(bucket)
                if isinstance(symbols, list):
                    for sym in symbols:
                        s = str(sym or "").strip().upper()
                        if not s or s in seen:
                            continue
                        seen.add(s)
                        bucket.append(s)
                out[name] = bucket
            return out

        state["theme_map"] = merge_map(state.get("theme_map"))
        state["sector_map"] = merge_map(state.get("sector_map"))


def _extract_theme_names_from_any(raw: Any, *, limit: int = 8) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    if not isinstance(raw, list):
        return out
    for row in raw:
        if isinstance(row, dict):
            value = row.get("theme") or row.get("theme_name") or row.get("name")
        else:
            value = row
        name = str(value or "").strip()
        key = name.lower()
        if not name or key in seen:
            continue
        seen.add(key)
        out.append(name)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _theme_packet_available_themes(packet: Dict[str, Any], *, limit: int = 8) -> List[Dict[str, Any]]:
    if not isinstance(packet, dict):
        return []
    component_map = packet.get("component_symbols_by_theme")
    if not isinstance(component_map, dict):
        component_map = packet.get("theme_map") if isinstance(packet.get("theme_map"), dict) else {}

    def component_symbols_for(name: str) -> List[str]:
        for key in (name, name.lower()):
            raw = component_map.get(key) if isinstance(component_map, dict) else None
            if isinstance(raw, list):
                symbols: List[str] = []
                seen_symbols: set[str] = set()
                for item in raw:
                    if isinstance(item, dict):
                        sym = str(item.get("symbol") or item.get("stk_cd") or "").strip().upper()
                    else:
                        sym = str(item or "").strip().upper()
                    if not sym or sym in seen_symbols:
                        continue
                    seen_symbols.add(sym)
                    symbols.append(sym)
                return symbols
        return []

    out: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for row in list(packet.get("top_themes") or []):
        if isinstance(row, dict):
            name = str(row.get("theme_name") or row.get("theme") or "").strip()
            code = str(row.get("theme_code") or row.get("code") or "").strip()
            score = _to_float(row.get("score"), 0.0)
            stock_count = _to_int(row.get("stock_count"), 0)
            rising_count = _to_int(row.get("rising_count"), 0)
            falling_count = _to_int(row.get("falling_count"), 0)
        else:
            name = str(row or "").strip()
            code = ""
            score = _to_float((packet.get("theme_scores") or {}).get(name) if isinstance(packet.get("theme_scores"), dict) else 0.0, 0.0)
            stock_count = 0
            rising_count = 0
            falling_count = 0
        key = name.lower()
        if not name or key in seen:
            continue
        symbols = component_symbols_for(name)
        out.append(
            {
                "theme": name,
                "theme_code": code,
                "score": float(score),
                "stock_count": int(stock_count),
                "rising_count": int(rising_count),
                "falling_count": int(falling_count),
                "component_count": int(len(symbols)),
                "component_symbols": symbols[:12],
            }
        )
        seen.add(key)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _resolve_selected_themes_from_api(
    *,
    available_themes: List[Dict[str, Any]],
    themes: List[str],
    raw_selected: Any,
    limit: int = 5,
) -> List[str]:
    available_names = [str(row.get("theme") or "").strip() for row in available_themes if isinstance(row, dict)]
    canonical_by_key = {name.lower(): name for name in available_names if name}
    requested = _extract_theme_names_from_any(raw_selected, limit=limit)
    requested.extend([str(x or "").strip() for x in list(themes or []) if str(x or "").strip()])

    out: List[str] = []
    seen: set[str] = set()
    if canonical_by_key:
        for name in requested:
            canonical = canonical_by_key.get(str(name or "").strip().lower())
            if not canonical:
                continue
            key = canonical.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(canonical)
            if len(out) >= max(1, int(limit)):
                return out
        for row in available_themes:
            canonical = str((row or {}).get("theme") or "").strip()
            key = canonical.lower()
            if not canonical or key in seen:
                continue
            seen.add(key)
            out.append(canonical)
            if len(out) >= max(1, int(limit)):
                break
        return out

    for name in requested:
        text = str(name or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _build_theme_strategy_surface(
    *,
    available_themes: List[Dict[str, Any]],
    selected_themes: List[str],
    playbook: str,
    theme_strength_packet: Dict[str, Any],
    raw_theme_strategy: Any,
) -> Dict[str, Any]:
    raw_strategy = raw_theme_strategy if isinstance(raw_theme_strategy, dict) else {}
    available_by_key = {
        str((row or {}).get("theme") or "").strip().lower(): dict(row)
        for row in available_themes
        if isinstance(row, dict) and str(row.get("theme") or "").strip()
    }
    status = str(theme_strength_packet.get("status") or "").strip().lower()
    source = str(theme_strength_packet.get("source") or "").strip()
    fallback_used = status != "ok" or not available_by_key
    overlay = {
        "breakout": "momentum",
        "pullback": "pullback",
        "reversal": "reversal",
        "defensive": "defensive",
    }.get(str(playbook or "").strip().lower(), "fallback")

    rows: List[Dict[str, Any]] = []
    for name in list(selected_themes or [])[:5]:
        key = str(name or "").strip().lower()
        theme_row = dict(available_by_key.get(key) or {})
        rows.append(
            {
                "theme": str(name or "").strip(),
                "score": float(_to_float(theme_row.get("score"), 0.0)),
                "component_count": int(_to_int(theme_row.get("component_count"), 0)),
                "playbook_overlay": overlay,
                "scanner_directive": (
                    "키움 테마 구성종목 안에서 거래대금, 거래량, 추세, 모멘텀 우위 후보를 우선 랭킹"
                    if not fallback_used
                    else "키움 테마 미확인 상태이므로 기존 후보 소스와 broad-market fallback 병행"
                ),
                "reason": str(raw_strategy.get("reason") or raw_strategy.get("selection_reason") or "").strip()
                or (
                    "키움 테마 강도 packet에서 선택 가능한 테마로 확인됨"
                    if not fallback_used
                    else str(theme_strength_packet.get("reason") or "kiwoom_theme_unavailable")
                ),
            }
        )

    return {
        "source": source or "kiwoom_theme_strength_packet",
        "status": status or "unavailable",
        "selection_mode": "fallback" if fallback_used else "kiwoom_api_constrained",
        "available_theme_count": int(len(available_themes)),
        "selected_themes": rows,
        "selected_theme_names": [str(x or "") for x in list(selected_themes or [])[:5] if str(x or "").strip()],
        "fallback_used": bool(fallback_used),
        "fallback_reason": "" if not fallback_used else str(theme_strength_packet.get("reason") or "kiwoom_theme_unavailable"),
    }


def _news_context_summary(
    news_signal_map: Dict[str, Dict[str, Any]],
    news_items_by_symbol: Dict[str, List[Any]],
) -> Dict[str, Any]:
    total = 0
    unavailable = 0
    fallback = 0
    ok = 0
    score_sum = 0.0
    score_cnt = 0
    headline_count = 0

    for symbol, sig in news_signal_map.items():
        _ = symbol
        total += 1
        st = str((sig or {}).get("status") or "").strip().lower()
        if st == "ok":
            ok += 1
        elif st == "fallback":
            fallback += 1
        elif st == "unavailable":
            unavailable += 1
        try:
            score_sum += float((sig or {}).get("score") or 0.0)
            score_cnt += 1
        except Exception:
            pass

    for rows in (news_items_by_symbol or {}).values():
        if isinstance(rows, list):
            headline_count += len(rows)

    avg_score = (score_sum / float(score_cnt)) if score_cnt > 0 else 0.0
    return {
        "signal_total": int(total),
        "ok": int(ok),
        "fallback": int(fallback),
        "unavailable": int(unavailable),
        "avg_score": float(_clamp(avg_score, -1.0, 1.0)),
        "headline_count": int(headline_count),
    }


def _merge_news_contexts(candidate_ctx: Dict[str, Any], market_ctx: Dict[str, Any]) -> Dict[str, Any]:
    cand_total = int(candidate_ctx.get("signal_total") or 0)
    market_total = int(market_ctx.get("signal_total") or 0)
    total = cand_total + market_total
    avg_score = 0.0
    if total > 0:
        avg_score = (
            (_to_float(candidate_ctx.get("avg_score"), 0.0) * float(cand_total))
            + (_to_float(market_ctx.get("avg_score"), 0.0) * float(market_total))
        ) / float(total)
    return {
        "signal_total": int(total),
        "ok": int(candidate_ctx.get("ok") or 0) + int(market_ctx.get("ok") or 0),
        "fallback": int(candidate_ctx.get("fallback") or 0) + int(market_ctx.get("fallback") or 0),
        "unavailable": int(candidate_ctx.get("unavailable") or 0) + int(market_ctx.get("unavailable") or 0),
        "avg_score": float(_clamp(avg_score, -1.0, 1.0)),
        "headline_count": int(candidate_ctx.get("headline_count") or 0) + int(market_ctx.get("headline_count") or 0),
        "candidate_signal_total": int(cand_total),
        "candidate_headline_count": int(candidate_ctx.get("headline_count") or 0),
        "market_signal_total": int(market_total),
        "market_headline_count": int(market_ctx.get("headline_count") or 0),
    }


def _theme_strength_map(
    *,
    themes: List[str],
    candidates: List[Dict[str, Any]],
    theme_scores: Dict[str, Any],
    theme_index: Dict[str, set[str]],
) -> Dict[str, float]:
    out: Dict[str, float] = {}
    candidate_symbols = [str((c or {}).get("symbol") or "").strip().upper() for c in list(candidates or [])]
    candidate_symbols = [s for s in candidate_symbols if s]
    denom = max(1, len(candidate_symbols))

    for raw_theme in list(themes or []):
        t = str(raw_theme or "").strip()
        if not t:
            continue
        key = t.lower()
        score_raw = _to_float(theme_scores.get(t, theme_scores.get(key, 0.0)), 0.0)
        score_norm = _clamp(score_raw / 100.0, -1.0, 1.0) if abs(score_raw) > 1.0 else _clamp(score_raw, -1.0, 1.0)
        mapped = theme_index.get(key, set())
        hits = 0
        if mapped:
            mapped_upper = {str(x).strip().upper() for x in mapped if str(x).strip()}
            hits = len([s for s in candidate_symbols if s in mapped_upper])
        hit_ratio = float(hits) / float(denom)
        out[t] = float(_clamp((0.70 * score_norm) + (0.30 * hit_ratio), -1.0, 1.0))

    return out


def _compose_regime_score(
    *,
    global_score: float,
    news_score: float,
    market_context_inputs: Dict[str, float],
) -> float:
    idx = _to_float(market_context_inputs.get("index_trend"), 0.0)
    breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    score = (0.45 * global_score) + (0.20 * news_score) + (0.20 * idx) + (0.15 * breadth) - (0.25 * macro_risk)
    return float(_clamp(score, -1.0, 1.0))


def _pick_playbook(*, market_structure: str, market_regime: str, market_sentiment: str) -> str:
    if str(market_structure).startswith("high_volatility") or market_regime == "risk_off":
        return "defensive"
    if str(market_structure).startswith("trend") and market_regime == "risk_on" and market_sentiment == "bullish":
        return "breakout"
    if str(market_structure).startswith("trend"):
        return "pullback"
    if str(market_structure).startswith("range") and market_regime == "risk_on":
        return "reversal"
    return "defensive"


def _scanner_priority(playbook: str, market_regime: str) -> List[str]:
    if playbook == "breakout":
        return ["momentum", "trend_strength", "volume_surge", "liquidity"]
    if playbook == "pullback":
        return ["trend_strength", "pullback_quality", "relative_strength", "liquidity"]
    if playbook == "reversal":
        return ["oversold_reversal", "volume_confirmation", "risk_reward", "liquidity"]
    # defensive
    base = ["liquidity", "risk_penalty", "low_volatility", "drawdown_control"]
    if market_regime == "risk_off":
        base.insert(0, "capital_preservation")
    return base


def _scanner_bias(*, playbook: str, market_regime: str) -> str:
    if market_regime == "risk_off":
        return "large_cap"
    if playbook == "breakout":
        return "momentum"
    if playbook == "pullback":
        return "leader"
    if playbook == "reversal":
        return "value"
    return "leader"


def _build_scanner_bias_context_seed(
    *,
    playbook: str,
    scanner_bias: str,
    monitor_entry_policy: Dict[str, Any],
) -> Dict[str, Any]:
    policy = dict(monitor_entry_policy or {})
    seed = {
        "prefer_shallow_pullback_candidates": playbook in {"pullback", "reversal"},
        "penalize_overextended": True,
        "prefer_reclaim_candidates": bool(policy.get("require_vwap_reclaim", True)),
        "prefer_volume_confirmation": bool(policy.get("volume_ratio_min", 0.68) >= 0.68),
        "bias_strength": "low",
        "bias_source": "strategist",
    }
    style = str(scanner_bias or "").strip().lower()
    if style == "momentum":
        seed["prefer_volume_confirmation"] = True
    elif style == "value":
        seed["prefer_shallow_pullback_candidates"] = True
    elif style == "leader":
        seed["prefer_reclaim_candidates"] = True
    return normalize_scanner_bias_context(seed, bias_source="strategist")[0].to_dict()


def _avoid_themes(*, market_sentiment: str, playbook: str) -> List[str]:
    if market_sentiment == "bearish" or playbook == "defensive":
        return ["illiquid_microcap", "headline_only_momentum", "high_gap_speculative"]
    if playbook == "reversal":
        return ["overextended_breakout_without_volume", "late_chasing_moves"]
    if playbook == "pullback":
        return ["counter_trend_low_liquidity"]
    return ["thin_liquidity_names"]


def _trade_aggressiveness(*, market_regime: str, market_structure: str) -> str:
    if market_regime == "risk_off" or str(market_structure).startswith("high_volatility"):
        return "low"
    if market_regime == "risk_on" and str(market_structure).startswith("trend"):
        return "high"
    return "medium"


def _risk_tone(aggressiveness: str) -> str:
    if aggressiveness == "low":
        return "conservative"
    if aggressiveness == "high":
        return "aggressive"
    return "normal"


def _monitor_guidance(*, market_regime: str, playbook: str) -> str:
    if market_regime == "risk_off" or playbook == "defensive":
        return "defensive_exit"
    if playbook == "breakout":
        return "hold_through_noise"
    return "quick_take_profit"


_TACTICAL_STRATEGIES = TACTIC_IDS
_TACTICAL_SUBTYPES = TACTICAL_SUBTYPES

_TACTICAL_STRATEGY_BY_PLAYBOOK = {
    "breakout": "opening_range_breakout",
    "pullback": "vwap_reclaim_pullback",
    "reversal": "reversal_reclaim",
    "defensive": "defensive_observe",
}

_CANDIDATE_WATCH_DEFAULT_RANK = {
    **dict(TACTIC_DEFAULT_RUNNER_UP_RANK),
}

_CANDIDATE_WATCH_CASCADE_ALLOWED_REASONS = (
    "too_extended_from_vwap",
    "breakout_not_ready",
    "volume_insufficient",
    "volume_confirmation_missing",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
    "pullback_not_mature",
)

_CANDIDATE_WATCH_CASCADE_BLOCKED_REASONS = (
    "cost_filter_failed",
    "risk_policy_block",
    "closeout_window",
    "open_position_present",
    "daily_loss_limit",
    "broker_truth_mismatch",
    "data_quality_guard",
    "buy_blocked_post_exit_cooldown",
    "buy_blocked_closeout_window",
)


def _norm_playbook(value: Any, *, default: str = "") -> str:
    return normalize_tactic_playbook(value, default=default)


def _default_tactical_strategy(playbook: str) -> str:
    return default_tactic_for_playbook(playbook)


def _normalize_tactical_strategy(value: Any, *, playbook: str) -> str:
    return normalize_tactic_id(value, playbook=playbook)


def _normalize_tactical_subtype(value: Any, *, tactical_strategy: str) -> str:
    return normalize_quant_tactical_subtype(value, tactic_id=tactical_strategy)


def _unit_score(value: Any, default: float = 0.0) -> float:
    try:
        return float(_clamp(float(value), 0.0, 1.0))
    except Exception:
        return float(_clamp(default, 0.0, 1.0))


def _deterministic_strategy_scores(
    *,
    playbook: str,
    market_regime: str,
    market_sentiment: str,
    market_structure: str,
    market_context_inputs: Dict[str, Any],
) -> Dict[str, float]:
    regime = str(market_regime or "").strip().lower()
    sentiment = str(market_sentiment or "").strip().lower()
    structure = str(market_structure or "").strip().lower()
    index_trend = _to_float(market_context_inputs.get("index_trend"), 0.0)
    breadth = _to_float(market_context_inputs.get("market_breadth"), 0.0)
    realized_vol = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)

    risk_on = 1.0 if regime == "risk_on" else 0.5 if regime == "neutral" else 0.0
    bullish = 1.0 if sentiment == "bullish" else 0.5 if sentiment == "neutral" else 0.0
    trend = _clamp(abs(index_trend), 0.0, 1.0)
    positive_tape = _clamp((breadth + 1.0) / 2.0, 0.0, 1.0)
    vol_penalty = _clamp(realized_vol / 0.08, 0.0, 1.0)
    macro_penalty = _clamp(macro_risk, 0.0, 1.0)
    trend_structure = 1.0 if structure.startswith("trend") else 0.35 if structure.startswith("range") else 0.0
    range_structure = 1.0 if structure.startswith("range") else 0.35
    high_vol = 1.0 if structure.startswith("high_volatility") else vol_penalty

    scores = {
        "opening_gap_momentum": (0.30 * risk_on) + (0.30 * bullish) + (0.25 * max(index_trend, 0.0)) + (0.15 * positive_tape),
        "opening_range_breakout": (0.25 * risk_on) + (0.25 * bullish) + (0.30 * trend_structure) + (0.20 * positive_tape),
        "vwap_reclaim_pullback": (0.20 * risk_on) + (0.20 * bullish) + (0.30 * trend_structure) + (0.20 * positive_tape) + (0.10 * (1.0 - vol_penalty)),
        "volume_breakout": (0.25 * risk_on) + (0.25 * bullish) + (0.25 * trend) + (0.15 * positive_tape) + (0.10 * (1.0 - macro_penalty)),
        "reversal_reclaim": (0.25 * range_structure) + (0.25 * (1.0 - positive_tape)) + (0.20 * risk_on) + (0.15 * (1.0 - high_vol)) + (0.15 * bullish),
        "cost_aware_scalp": (0.25 * risk_on) + (0.25 * bullish) + (0.20 * (1.0 - macro_penalty)) + (0.15 * trend_structure) + (0.15 * positive_tape),
        "defensive_observe": (0.35 * (1.0 - risk_on)) + (0.25 * high_vol) + (0.25 * macro_penalty) + (0.15 * (1.0 - bullish)),
    }
    selected = _normalize_tactical_strategy("", playbook=playbook)
    if selected in scores:
        scores[selected] = max(float(scores[selected]), 0.55)
    return {key: round(_unit_score(value), 4) for key, value in scores.items()}


def _normalize_strategy_scores(
    raw: Any,
    *,
    playbook: str,
    market_regime: str,
    market_sentiment: str,
    market_structure: str,
    market_context_inputs: Dict[str, Any],
) -> Dict[str, float]:
    scores = _deterministic_strategy_scores(
        playbook=playbook,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        market_structure=market_structure,
        market_context_inputs=market_context_inputs,
    )
    if isinstance(raw, dict):
        for raw_key, raw_value in raw.items():
            key = canonical_tactic_key(raw_key)
            if key in _TACTICAL_STRATEGIES:
                scores[key] = round(_unit_score(raw_value, scores.get(key, 0.0)), 4)
    return scores


def _normalize_rejected_strategy_reasons(
    raw: Any,
    *,
    tactical_strategy: str,
    strategy_scores: Dict[str, float],
) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            name = canonical_tactic_key(key)
            if name not in _TACTICAL_STRATEGIES or name == tactical_strategy:
                continue
            reason = _clean_directive_reason(value, default="")
            if reason:
                out[name] = reason
            if len(out) >= 6:
                break
    if out:
        return out
    selected_score = _unit_score(strategy_scores.get(tactical_strategy), 0.0)
    ordered = sorted(
        [
            (name, _unit_score(score, 0.0))
            for name, score in dict(strategy_scores or {}).items()
            if name in _TACTICAL_STRATEGIES and name != tactical_strategy
        ],
        key=lambda row: row[1],
        reverse=True,
    )
    for name, score in ordered[:4]:
        if score <= selected_score:
            out[name] = "score_below_selected_tactical_strategy"
        else:
            out[name] = "not_selected_after_playbook_and_risk_clamp"
    return out


def _sanitize_reason_list(raw: Any, defaults: Tuple[str, ...]) -> List[str]:
    allowed = {str(x).strip() for x in defaults if str(x).strip()}
    values = raw if isinstance(raw, list) else []
    out: List[str] = []
    for item in values:
        text = str(item or "").strip().lower()
        if text and text in allowed and text not in out:
            out.append(text)
    return out or list(defaults)


def _normalize_candidate_watch_policy(
    raw: Any,
    *,
    tactical_strategy: str,
    playbook: str,
    market_regime: str,
    risk_tone: str,
    trade_aggressiveness: str,
) -> Dict[str, Any]:
    src = dict(raw or {}) if isinstance(raw, dict) else {}
    strategy = _normalize_tactical_strategy(tactical_strategy, playbook=playbook)
    default_rank = int(_CANDIDATE_WATCH_DEFAULT_RANK.get(strategy, 5))
    regime = str(market_regime or "").strip().lower()
    tone = str(risk_tone or "").strip().lower()
    aggr = str(trade_aggressiveness or "").strip().lower()

    if regime == "risk_off" or strategy == "defensive_observe":
        default_rank = min(default_rank, 3)
    elif _norm_playbook(playbook) == "breakout" and aggr == "high" and regime in {"risk_on", "neutral"}:
        default_rank = max(default_rank, 10 if regime == "risk_on" else 7)
    elif _norm_playbook(playbook) == "pullback" and regime == "risk_on":
        default_rank = max(default_rank, 7)
    if tone == "conservative":
        default_rank = min(default_rank, 5)

    raw_rank = src.get("max_priority_rank")
    max_rank = int(_clamp(_to_int(raw_rank, default_rank), 1, 10))
    if regime == "risk_off":
        max_rank = min(max_rank, 3)
    if strategy == "defensive_observe":
        max_rank = min(max_rank, 3)

    raw_runner_ups = src.get("max_runner_ups")
    max_runner_ups = int(_clamp(_to_int(raw_runner_ups, max(0, max_rank - 1)), 0, max(0, max_rank - 1)))
    cascade_enabled_default = strategy != "defensive_observe" and max_runner_ups > 0
    cascade_enabled = _is_trueish(src.get("cascade_enabled")) if src.get("cascade_enabled") is not None else cascade_enabled_default
    if max_runner_ups <= 0 or strategy == "defensive_observe":
        cascade_enabled = False

    return {
        "schema_version": "candidate_watch_policy.v1",
        "source": "strategist_visibility_proposal",
        "behavior_effect": "visibility_only",
        "tactical_strategy": strategy,
        "tactical_subtype": _normalize_tactical_subtype(
            src.get("tactical_subtype"),
            tactical_strategy=strategy,
        ),
        "playbook": _norm_playbook(playbook, default="defensive"),
        "market_regime": str(market_regime or ""),
        "risk_tone": str(risk_tone or ""),
        "trade_aggressiveness": str(trade_aggressiveness or ""),
        "max_priority_rank": int(max_rank),
        "max_runner_ups": int(max_runner_ups),
        "cascade_enabled": bool(cascade_enabled),
        "cascade_allowed_reasons": _sanitize_reason_list(
            src.get("cascade_allowed_reasons"),
            _CANDIDATE_WATCH_CASCADE_ALLOWED_REASONS,
        ),
        "cascade_blocked_reasons": _sanitize_reason_list(
            src.get("cascade_blocked_reasons"),
            _CANDIDATE_WATCH_CASCADE_BLOCKED_REASONS,
        ),
        "reason": _clean_directive_reason(
            src.get("reason"),
            default=f"{strategy}:proposed_watch_depth_visibility_only",
        ),
    }


def _macro_stress_overlay(global_signal: Dict[str, Any]) -> Dict[str, Any]:
    macro_moves = global_signal.get("macro_moves") if isinstance(global_signal.get("macro_moves"), dict) else {}
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    vix_level = _to_float(fear_index.get("level"), _to_float(macro_moves.get("vix_level"), 0.0))
    vix_pressure = _to_float(fear_index.get("level_pressure"), _to_float(macro_moves.get("vix_level_pressure"), 0.0))
    dxy_pct = _to_float(macro_moves.get("dxy_pct"), 0.0)
    tnx_delta = _to_float(macro_moves.get("tnx_delta"), 0.0)

    flags: List[str] = []
    if vix_level >= 25.0 or vix_pressure >= 0.25:
        flags.append("elevated_vix")
    if dxy_pct >= 0.25:
        flags.append("dollar_strength")
    if tnx_delta >= 0.005:
        flags.append("yield_rise")

    return {
        "stress_flags": list(flags),
        "stress_count": len(flags),
        "vix_level": vix_level,
        "vix_pressure": vix_pressure,
        "dxy_pct": dxy_pct,
        "tnx_delta": tnx_delta,
        "active": len(flags) >= 2,
    }


def _apply_macro_stress_to_monitor_frame(
    *,
    global_signal: Dict[str, Any],
    monitor_guidance: str,
    risk_tone: str,
    trade_aggressiveness: str,
    exit_policy: Dict[str, Any],
    report_focus: List[str],
) -> Tuple[str, str, str, Dict[str, Any], List[str], Dict[str, Any]]:
    overlay = _macro_stress_overlay(global_signal)
    if not overlay.get("active"):
        return (
            monitor_guidance,
            risk_tone,
            trade_aggressiveness,
            dict(exit_policy or {}),
            list(report_focus or []),
            overlay,
        )

    next_guidance = str(monitor_guidance or "").strip().lower() or "defensive_exit"
    next_tone = str(risk_tone or "").strip().lower() or "normal"
    next_aggr = str(trade_aggressiveness or "").strip().lower() or "medium"
    adjusted_exit_policy = dict(exit_policy or {})
    adjusted_focus = list(report_focus or [])
    adjustments: List[str] = []

    stress_count = int(overlay.get("stress_count") or 0)
    intensity = "high" if stress_count >= 3 else "moderate"
    overlay["intensity"] = intensity

    if intensity == "high":
        if next_guidance != "defensive_exit":
            next_guidance = "defensive_exit"
            adjustments.append("macro_stress:monitor_guidance=defensive_exit")
        if next_tone != "conservative":
            next_tone = "conservative"
            adjustments.append("macro_stress:risk_tone=conservative")
    else:
        if next_guidance == "quick_take_profit":
            next_guidance = "hold_through_noise"
            adjustments.append("macro_stress:monitor_guidance=hold_through_noise")
        if next_tone == "aggressive":
            next_tone = "normal"
            adjustments.append("macro_stress:risk_tone=normal")

    target_aggr = "low" if intensity == "high" else "medium"
    if next_aggr != target_aggr:
        next_aggr = target_aggr
        adjustments.append(f"macro_stress:trade_aggressiveness={target_aggr}")

    stop_loss_pct = _to_float(adjusted_exit_policy.get("stop_loss_pct"), 0.0)
    take_profit_pct = _to_float(adjusted_exit_policy.get("take_profit_pct"), 0.0)
    trailing_stop_pct = _to_float(adjusted_exit_policy.get("trailing_stop_pct"), 0.0)
    if stop_loss_pct > 0.0:
        adjusted_exit_policy["stop_loss_pct"] = stop_loss_pct * (0.90 if intensity == "high" else 0.95)
    if take_profit_pct > 0.0:
        adjusted_exit_policy["take_profit_pct"] = take_profit_pct * (0.88 if intensity == "high" else 0.94)
    if trailing_stop_pct > 0.0:
        adjusted_exit_policy["trailing_stop_pct"] = max(trailing_stop_pct, _to_float(adjusted_exit_policy.get("stop_loss_pct"), 0.0) * 0.75)
    adjustments.append("macro_stress:tightened_exit_policy")

    for item in ("macro_stress", "exit_quality", "guard_blocks"):
        if item not in adjusted_focus:
            adjusted_focus.append(item)

    overlay["adjustments"] = list(adjustments)
    overlay["reason"] = (
        f"vix={_to_float(overlay.get('vix_level'), 0.0):.2f} "
        f"pressure={_to_float(overlay.get('vix_pressure'), 0.0):.3f} "
        f"dxy_pct={_to_float(overlay.get('dxy_pct'), 0.0):.2f} "
        f"tnx_delta={_to_float(overlay.get('tnx_delta'), 0.0):.4f}"
    )
    return next_guidance, next_tone, next_aggr, adjusted_exit_policy, adjusted_focus[:8], overlay


def _condition_search_source_enabled() -> bool:
    return _env_bool("KIWOOM_CANDIDATE_ENABLE_CONDITION_SEARCH", False)


def _monitor_policy(
    *,
    state: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    monitor_guidance: str,
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, Any]:
    applied_policy = state.get("applied_policy") if isinstance(state, dict) and isinstance(state.get("applied_policy"), dict) else {}
    monitor_applied = applied_policy.get("monitor") if isinstance(applied_policy.get("monitor"), dict) else {}
    execution_applied = applied_policy.get("execution") if isinstance(applied_policy.get("execution"), dict) else {}
    policy_row = dict(policy or {}) if isinstance(policy, dict) else {}

    raw_min_hold = (
        _nested_mapping_value(monitor_applied, "hold", "min_hold_seconds")
        if _nested_mapping_value(monitor_applied, "hold", "min_hold_seconds") is not None
        else _nested_mapping_value(policy_row, "monitor", "hold", "min_hold_seconds")
    )
    if raw_min_hold is None:
        raw_min_hold = policy_row.get("min_hold_seconds")
    min_hold_sec = _to_int(raw_min_hold, 600)

    raw_sell_cooldown = (
        _nested_mapping_value(execution_applied, "cooldowns", "sell_sec")
        if _nested_mapping_value(execution_applied, "cooldowns", "sell_sec") is not None
        else _nested_mapping_value(policy_row, "execution", "cooldowns", "sell_sec")
    )
    if raw_sell_cooldown is None:
        raw_sell_cooldown = policy_row.get("sell_cooldown_seconds")
    if raw_sell_cooldown is None:
        raw_sell_cooldown = policy_row.get("sell_cooldown_sec")
    sell_cooldown = _to_int(raw_sell_cooldown, 300)

    raw_confirm_ticks = (
        _nested_mapping_value(monitor_applied, "exit", "confirm_ticks")
        if _nested_mapping_value(monitor_applied, "exit", "confirm_ticks") is not None
        else _nested_mapping_value(policy_row, "monitor", "exit", "confirm_ticks")
    )
    if raw_confirm_ticks is None:
        raw_confirm_ticks = policy_row.get("exit_confirm_ticks")
    confirm_ticks = _to_int(raw_confirm_ticks, 2)
    adjustments: List[str] = []

    mode = str(monitor_guidance or "").strip().lower()
    if mode == "hold_through_noise":
        min_hold_sec += 300
        confirm_ticks += 1
        sell_cooldown += 60
        adjustments.append("mode:hold_through_noise")
    elif mode == "defensive_exit":
        confirm_ticks = max(1, confirm_ticks - 1)
        min_hold_sec = max(0, min_hold_sec - 120)
        adjustments.append("mode:defensive_exit")
    elif mode == "quick_take_profit":
        confirm_ticks = 1
        min_hold_sec = max(0, min_hold_sec - 300)
        sell_cooldown = max(60, min(sell_cooldown, 180))
        adjustments.append("mode:quick_take_profit")

    tone = str(risk_tone or "").strip().lower()
    if tone == "conservative":
        confirm_ticks += 1
        min_hold_sec += 120
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        confirm_ticks = max(1, confirm_ticks - 1)
        min_hold_sec = max(0, min_hold_sec - 60)
        adjustments.append("risk_tone:aggressive")

    aggr = str(trade_aggressiveness or "").strip().lower()
    if aggr == "low":
        confirm_ticks = max(confirm_ticks, 3)
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        confirm_ticks = max(1, confirm_ticks - 1)
        adjustments.append("trade_aggressiveness:high")

    return {
        "min_hold_seconds": max(0, int(min_hold_sec)),
        "sell_cooldown_seconds": max(0, int(sell_cooldown)),
        "exit_confirm_ticks": max(1, min(6, int(confirm_ticks))),
        "adjustments": list(adjustments),
        "note": "monitor_manages_entry_exit_only",
    }


def _exit_policy(
    *,
    playbook: str,
    monitor_guidance: str,
    trade_aggressiveness: str,
    risk_tone: str,
) -> Dict[str, Any]:
    mode = str(playbook or "").strip().lower()
    guidance = str(monitor_guidance or "").strip().lower()
    tone = str(risk_tone or "").strip().lower()
    aggr = str(trade_aggressiveness or "").strip().lower()

    if mode == "breakout":
        stop_loss_pct = 0.018
        take_profit_pct = 0.040
        baseline_tag = "breakout"
    elif mode == "pullback":
        stop_loss_pct = 0.022
        take_profit_pct = 0.036
        baseline_tag = "pullback"
    elif mode == "reversal":
        stop_loss_pct = 0.016
        take_profit_pct = 0.026
        baseline_tag = "reversal"
    else:
        stop_loss_pct = 0.014
        take_profit_pct = 0.022
        baseline_tag = "defensive"

    env_stop_raw = str(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "") or "").strip()
    env_take_raw = str(os.getenv("EXIT_POLICY_TAKE_PROFIT_PCT", "") or "").strip()
    if env_stop_raw:
        stop_loss_pct = _to_float(env_stop_raw, stop_loss_pct) or stop_loss_pct
        baseline_tag = "env_stop"
    if env_take_raw:
        take_profit_pct = _to_float(env_take_raw, take_profit_pct) or take_profit_pct
        baseline_tag = "env_take" if baseline_tag == "env_stop" else baseline_tag

    trailing_stop_pct = _to_float(os.getenv("EXIT_POLICY_TRAILING_STOP_PCT", "0.0"), 0.0)
    vol_expansion_ratio = _to_float(os.getenv("EXIT_POLICY_VOL_EXPANSION_RATIO", "0.0"), 0.0)
    news_shock_threshold = _to_float(os.getenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "0.0"), 0.0)
    peak_drawdown_exit_pct = _to_float(os.getenv("EXIT_POLICY_PEAK_DRAWDOWN_EXIT_PCT", "0.0"), 0.0)
    profit_protection_activation_pct = _to_float(
        os.getenv("EXIT_POLICY_PROFIT_PROTECTION_ACTIVATION_PCT", "0.008"),
        0.008,
    )
    peak_drawdown_mode = str(os.getenv("EXIT_POLICY_PEAK_DRAWDOWN_MODE", "profit_protection") or "profit_protection").strip().lower()
    confirm_required_for_peak_drawdown = max(
        1,
        int(_to_float(os.getenv("EXIT_POLICY_CONFIRM_REQUIRED_FOR_PEAK_DRAWDOWN", "2"), 2.0)),
    )
    vwap_breakdown_pct = _to_float(os.getenv("EXIT_POLICY_VWAP_BREAKDOWN_PCT", "0.0"), 0.0)
    intraday_low_break_pct = _to_float(os.getenv("EXIT_POLICY_INTRADAY_LOW_BREAK_PCT", "0.0"), 0.0)
    trend_strength_floor = _to_float(os.getenv("EXIT_POLICY_TREND_STRENGTH_FLOOR", "0.0"), 0.0)
    adjustments: List[str] = [f"baseline:{baseline_tag}"]

    if mode == "breakout":
        stop_loss_pct *= 0.90
        take_profit_pct *= 1.40
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.90)
        vol_expansion_ratio = max(vol_expansion_ratio, 2.20)
        adjustments.append("playbook:breakout")
    elif mode == "pullback":
        stop_loss_pct *= 1.05
        take_profit_pct *= 1.20
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.75)
        vol_expansion_ratio = max(vol_expansion_ratio, 2.00)
        adjustments.append("playbook:pullback")
    elif mode == "reversal":
        stop_loss_pct *= 0.85
        take_profit_pct *= 1.00
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        vol_expansion_ratio = max(vol_expansion_ratio, 1.80)
        adjustments.append("playbook:reversal")
    else:
        stop_loss_pct *= 0.80
        take_profit_pct *= 0.90
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.65)
        vol_expansion_ratio = max(vol_expansion_ratio, 1.60)
        adjustments.append("playbook:defensive")

    if guidance == "hold_through_noise":
        stop_loss_pct *= 1.10
        take_profit_pct *= 1.10
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.95)
        adjustments.append("monitor_guidance:hold_through_noise")
    elif guidance == "quick_take_profit":
        stop_loss_pct *= 0.95
        take_profit_pct *= 0.85
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.80)
        adjustments.append("monitor_guidance:quick_take_profit")
    elif guidance == "defensive_exit":
        stop_loss_pct *= 0.92
        take_profit_pct *= 0.92
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.70)
        adjustments.append("monitor_guidance:defensive_exit")

    if tone == "conservative":
        stop_loss_pct *= 0.90
        take_profit_pct *= 0.95
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 0.75)
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        stop_loss_pct *= 1.10
        take_profit_pct *= 1.10
        trailing_stop_pct = max(trailing_stop_pct, stop_loss_pct * 1.00)
        adjustments.append("risk_tone:aggressive")

    if aggr == "low":
        take_profit_pct *= 0.95
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        take_profit_pct *= 1.08
        adjustments.append("trade_aggressiveness:high")

    stop_loss_pct = _clamp(stop_loss_pct, 0.003, 0.10)
    take_profit_pct = _clamp(max(take_profit_pct, stop_loss_pct * 1.05), 0.005, 0.25)
    trailing_stop_pct = _clamp(max(trailing_stop_pct, stop_loss_pct * 0.50), 0.0, 0.15)
    if peak_drawdown_exit_pct <= 0.0:
        if guidance == "quick_take_profit":
            peak_drawdown_exit_pct = stop_loss_pct * 0.45
        elif guidance == "hold_through_noise":
            peak_drawdown_exit_pct = stop_loss_pct * 0.80
        elif mode == "defensive":
            peak_drawdown_exit_pct = stop_loss_pct * 0.50
        elif mode == "breakout":
            peak_drawdown_exit_pct = stop_loss_pct * 0.75
        else:
            peak_drawdown_exit_pct = stop_loss_pct * 0.60
        adjustments.append("peak_drawdown_exit_pct:auto")
    if vwap_breakdown_pct <= 0.0:
        if guidance == "quick_take_profit":
            vwap_breakdown_pct = 0.004
        elif mode == "breakout":
            vwap_breakdown_pct = 0.010
        elif mode == "defensive":
            vwap_breakdown_pct = 0.005
        else:
            vwap_breakdown_pct = 0.007
        adjustments.append("vwap_breakdown_pct:auto")
    if intraday_low_break_pct <= 0.0:
        if guidance == "quick_take_profit":
            intraday_low_break_pct = 0.0015
        elif mode == "breakout":
            intraday_low_break_pct = 0.0030
        elif mode == "defensive":
            intraday_low_break_pct = 0.0020
        else:
            intraday_low_break_pct = 0.0025
        adjustments.append("intraday_low_break_pct:auto")
    if trend_strength_floor == 0.0:
        if mode == "breakout":
            trend_strength_floor = -0.05
        elif mode == "defensive":
            trend_strength_floor = -0.15
        else:
            trend_strength_floor = -0.10
        adjustments.append("trend_strength_floor:auto")
    vol_expansion_ratio = _clamp(vol_expansion_ratio, 0.0, 5.0)
    news_shock_threshold = _clamp(news_shock_threshold, 0.0, 1.0)
    peak_drawdown_exit_pct = _clamp(peak_drawdown_exit_pct, 0.0, 0.15)
    profit_protection_activation_pct = _clamp(profit_protection_activation_pct, 0.0, 0.25)
    if peak_drawdown_mode not in {"profit_protection", "always_on", "disabled"}:
        peak_drawdown_mode = "profit_protection"
        adjustments.append("peak_drawdown_mode:normalized")
    vwap_breakdown_pct = _clamp(vwap_breakdown_pct, 0.0, 0.05)
    intraday_low_break_pct = _clamp(intraday_low_break_pct, 0.0, 0.03)
    trend_strength_floor = _clamp(trend_strength_floor, -1.0, 1.0)

    return {
        "stop_loss_pct": float(stop_loss_pct),
        "take_profit_pct": float(take_profit_pct),
        "trailing_stop_pct": float(trailing_stop_pct),
        "vol_expansion_ratio": float(vol_expansion_ratio),
        "news_shock_threshold": float(news_shock_threshold),
        "peak_drawdown_exit_pct": float(peak_drawdown_exit_pct),
        "profit_protection_activation_pct": float(profit_protection_activation_pct),
        "peak_drawdown_mode": str(peak_drawdown_mode),
        "confirm_required_for_peak_drawdown": int(confirm_required_for_peak_drawdown),
        "vwap_breakdown_pct": float(vwap_breakdown_pct),
        "intraday_low_break_pct": float(intraday_low_break_pct),
        "trend_strength_floor": float(trend_strength_floor),
        "adjustments": list(adjustments),
        "note": "strategist_exit_policy_baseline",
    }


def _scanner_source_policy(
    *,
    playbook: str,
    risk_tone: str,
    trade_aggressiveness: str,
    market_regime: str,
    themes: List[str],
    fear_index: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_playbook = str(playbook or "").strip().lower()
    normalized_tone = str(risk_tone or "").strip().lower()
    normalized_aggr = str(trade_aggressiveness or "").strip().lower()
    normalized_regime = str(market_regime or "").strip().lower()
    has_themes = bool(list(themes or []))
    allow_condition_search = _condition_search_source_enabled()
    normalized_fear = dict(fear_index or {}) if isinstance(fear_index, dict) else {}
    vix_level = _to_float(normalized_fear.get("level"), 0.0)
    vix_pressure = _to_float(normalized_fear.get("level_pressure"), 0.0)
    elevated_fear = vix_level >= 25.0 or vix_pressure >= 0.25

    policy: Dict[str, Any] = {
        "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"],
        "include_top_value": True,
        "include_top_volume": True,
        "include_change_rate": True,
        "include_condition_search": False,
        "include_sector_candidates": has_themes,
        "include_watchlist": True,
        "top_candidate_pool": 30,
        "condition_limit": 0,
        "source_weights": {
            "top_value": 2.0,
            "top_volume": 1.7,
            "condition_search": 0.0,
            "sector_theme": 1.6,
            "operator_watchlist": 0.8,
            "top_change_rate": 1.3,
        },
        "reason": "balanced baseline prefers liquidity and theme/watchlist sources; condition search is opt-in only",
    }

    if normalized_playbook == "defensive" or normalized_tone == "conservative" or normalized_regime == "risk_off":
        policy.update(
            {
                "preferred_sources": ["top_value", "top_volume", "sector_theme", "operator_watchlist"],
                "include_change_rate": False,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": True,
                "top_candidate_pool": 18,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 2.2,
                    "top_volume": 1.9,
                    "condition_search": 0.0,
                    "sector_theme": 1.8 if has_themes else 0.0,
                    "operator_watchlist": 1.1,
                    "top_change_rate": 0.0,
                },
                "reason": "defensive frame prioritizes liquid leaders and suppresses fast-mover sources",
            }
        )
    elif normalized_playbook == "breakout":
        policy.update(
            {
                "preferred_sources": ["top_change_rate", "top_volume", "sector_theme", "operator_watchlist"],
                "include_change_rate": True,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": normalized_aggr != "high",
                "top_candidate_pool": 32,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 1.4,
                    "top_volume": 1.9,
                    "condition_search": 0.0,
                    "sector_theme": 1.7 if has_themes else 0.0,
                    "operator_watchlist": 0.5 if normalized_aggr == "high" else 0.8,
                    "top_change_rate": 2.2,
                },
                "reason": "breakout baseline prioritizes fast movers and volume expansion; condition search remains optional",
            }
        )
    elif normalized_playbook == "pullback":
        policy.update(
            {
                "preferred_sources": ["top_value", "sector_theme", "top_volume", "operator_watchlist"],
                "include_change_rate": False,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": True,
                "top_candidate_pool": 24,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 2.1,
                    "top_volume": 1.5,
                    "condition_search": 0.0,
                    "sector_theme": 1.9 if has_themes else 0.0,
                    "operator_watchlist": 0.9,
                    "top_change_rate": 0.0,
                },
                "reason": "pullback baseline prioritizes liquid leaders and theme/watchlist support; condition search remains optional",
            }
        )
    elif normalized_playbook == "reversal":
        policy.update(
            {
                "preferred_sources": ["top_change_rate", "operator_watchlist", "top_volume", "sector_theme"],
                "include_change_rate": True,
                "include_condition_search": False,
                "include_sector_candidates": has_themes,
                "include_watchlist": True,
                "top_candidate_pool": 22,
                "condition_limit": 0,
                "source_weights": {
                    "top_value": 1.3,
                    "top_volume": 1.5,
                    "condition_search": 0.0,
                    "sector_theme": 1.3 if has_themes else 0.0,
                    "operator_watchlist": 1.0,
                    "top_change_rate": 1.9,
                },
                "reason": "reversal baseline leans on sharp movers and watchlist context; condition search remains optional",
            }
        )

    if allow_condition_search:
        if normalized_playbook == "breakout":
            policy["preferred_sources"] = ["top_change_rate", "condition_search", "top_volume", "sector_theme"]
            policy["condition_limit"] = 240
            cond_weight = 2.4
        elif normalized_playbook == "pullback":
            policy["preferred_sources"] = ["top_value", "condition_search", "sector_theme", "top_volume"]
            policy["condition_limit"] = 180
            cond_weight = 2.0
        elif normalized_playbook == "reversal":
            policy["preferred_sources"] = ["condition_search", "top_change_rate", "operator_watchlist", "top_volume"]
            policy["condition_limit"] = 220
            cond_weight = 2.2
        else:
            policy["preferred_sources"] = ["top_value", "top_volume", "condition_search", "sector_theme"]
            policy["condition_limit"] = 160
            cond_weight = 2.0
        policy["include_condition_search"] = True
        source_weights = dict(policy.get("source_weights") or {})
        source_weights["condition_search"] = cond_weight
        policy["source_weights"] = source_weights
        policy["reason"] = str(policy.get("reason") or "") + "; condition search explicitly enabled"

    if elevated_fear:
        preferred = [str(x).strip() for x in list(policy.get("preferred_sources") or []) if str(x).strip()]
        preferred = [x for x in preferred if x not in ("top_change_rate", "condition_search")]
        reordered: List[str] = []
        for raw in ("top_value", "sector_theme", "top_volume", "operator_watchlist"):
            if raw == "sector_theme" and not has_themes:
                continue
            if raw not in reordered:
                reordered.append(raw)
        for raw in preferred:
            if raw == "sector_theme" and not has_themes:
                continue
            if raw not in reordered:
                reordered.append(raw)
        source_weights = dict(policy.get("source_weights") or {})
        source_weights.update(
            {
                "top_value": max(_to_float(source_weights.get("top_value"), 0.0), 2.3),
                "top_volume": max(_to_float(source_weights.get("top_volume"), 0.0), 1.8),
                "sector_theme": max(_to_float(source_weights.get("sector_theme"), 0.0), 1.9 if has_themes else 0.0),
                "operator_watchlist": max(_to_float(source_weights.get("operator_watchlist"), 0.0), 1.1),
                "top_change_rate": 0.0,
                "condition_search": 0.0,
            }
        )
        policy.update(
            {
                "preferred_sources": reordered,
                "include_change_rate": False,
                "include_condition_search": False,
                "top_candidate_pool": min(_to_int(policy.get("top_candidate_pool"), 30), 20),
                "condition_limit": 0,
                "source_weights": source_weights,
                "reason": (
                    f"{str(policy.get('reason') or '')}; elevated fear index "
                    f"(vix={vix_level:.2f}, pressure={vix_pressure:.3f}) shifted source policy toward liquid defensive candidates"
                ).strip("; "),
            }
        )

    return policy


def _strategy_policy_score_weights() -> Dict[str, float]:
    return {
        "trading_value": _to_float(os.getenv("SCORE_WEIGHTS_TRADING_VALUE", "0.20"), 0.20),
        "momentum": _to_float(os.getenv("SCORE_WEIGHTS_MOMENTUM", "0.22"), 0.22),
        "trend": _to_float(os.getenv("SCORE_WEIGHTS_TREND", "0.20"), 0.20),
        "volume_surge": _to_float(os.getenv("SCORE_WEIGHTS_VOLUME_SURGE", "0.14"), 0.14),
        "intraday_strength": _to_float(os.getenv("SCORE_WEIGHTS_INTRADAY_STRENGTH", "0.12"), 0.12),
        "theme_boost": _to_float(os.getenv("SCORE_WEIGHTS_THEME_BOOST", "0.06"), 0.06),
        "sentiment": _to_float(os.getenv("SCORE_WEIGHTS_SENTIMENT", "0.06"), 0.06),
        "volatility_penalty": _to_float(os.getenv("SCORE_WEIGHTS_VOLATILITY_PENALTY", "0.10"), 0.10),
        "gap_penalty": _to_float(os.getenv("SCORE_WEIGHTS_GAP_PENALTY", "0.07"), 0.07),
        "open_order_penalty": _to_float(os.getenv("SCORE_WEIGHTS_OPEN_ORDER_PENALTY", "0.04"), 0.04),
    }


def _strategy_policy_entry_policy() -> Dict[str, Any]:
    return {
        "buy_score_threshold": _to_float(os.getenv("STRATEGY_V1_BUY_COMPOSITE_THRESHOLD", "0.20"), 0.20),
        "sell_score_threshold": _to_float(os.getenv("STRATEGY_V1_SELL_COMPOSITE_THRESHOLD", "-0.12"), -0.12),
        "min_signal_for_entry": _to_float(os.getenv("STRATEGY_V1_MIN_SIGNAL_FOR_ENTRY", "0.15"), 0.15),
        "min_news_for_entry": _to_float(os.getenv("STRATEGY_V1_MIN_NEWS_FOR_ENTRY", "0.00"), 0.00),
        "max_volatility_for_entry": _to_float(os.getenv("STRATEGY_V1_MAX_VOLATILITY_FOR_ENTRY", "0.12"), 0.12),
        "invalidation_signal_floor": _to_float(os.getenv("STRATEGY_V1_INVALIDATION_SIGNAL_FLOOR", "-0.08"), -0.08),
        "base_risk_per_trade_ratio": _to_float(os.getenv("STRATEGY_V1_BASE_RISK_PER_TRADE_RATIO", "0.01"), 0.01),
        "base_position_notional_ratio": _to_float(
            os.getenv("STRATEGY_V1_BASE_POSITION_NOTIONAL_RATIO", "0.10"),
            0.10,
        ),
        "min_confidence_for_entry": _to_float(os.getenv("STRATEGY_V1_MIN_CONFIDENCE_FOR_ENTRY", "0.35"), 0.35),
        "max_position_qty": max(1, _to_int(os.getenv("STRATEGY_V1_MAX_POSITION_QTY", "10"), 10)),
        "min_position_qty": max(1, _to_int(os.getenv("STRATEGY_V1_MIN_POSITION_QTY", "1"), 1)),
        "lot_size": max(1, _to_int(os.getenv("STRATEGY_V1_LOT_SIZE", "1"), 1)),
    }


def _build_strategy_policy(
    *,
    market_regime: str,
    market_sentiment: str,
    playbook: str,
    trade_aggressiveness: str,
    risk_tone: str,
    monitor_guidance: str,
    global_signal: Dict[str, Any],
    market_context_inputs: Dict[str, float],
    themes: List[str],
    avoid_themes: List[str],
    theme_strength: Dict[str, Any],
    scanner_priority: List[str],
    scanner_source_policy: Dict[str, Any],
    scanner_bias_context: Dict[str, Any],
    monitor_entry_policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
    exit_policy: Dict[str, Any],
    macro_stress_overlay: Dict[str, Any],
    news_ctx: Dict[str, Any],
) -> Dict[str, Any]:
    fear_index = dict(global_signal.get("fear_index") or {}) if isinstance(global_signal.get("fear_index"), dict) else {}
    market_news_count = _to_int(news_ctx.get("headline_count"), 0)
    candidate_news_count = _to_int(news_ctx.get("candidate_signal_total"), 0)
    entry_policy = _strategy_policy_entry_policy()
    effective_use_eod_flat = exit_policy.get("use_eod_flat") if isinstance(exit_policy, dict) else None
    if effective_use_eod_flat is None and isinstance(monitor_policy, dict):
        effective_use_eod_flat = (
            (((monitor_policy.get("exit") or {}).get("eod_flat") or {}).get("enabled"))
            if isinstance((monitor_policy.get("exit") or {}).get("eod_flat"), dict)
            else None
        )
    if effective_use_eod_flat is None:
        effective_use_eod_flat = True
    return {
        "schema_version": "strategy_policy.v1",
        "market_policy": {
            "market_regime": str(market_regime or "neutral"),
            "market_sentiment": str(market_sentiment or "neutral"),
            "playbook": str(playbook or "defensive"),
            "trade_aggressiveness": str(trade_aggressiveness or "medium"),
            "risk_tone": str(risk_tone or "normal"),
            "monitor_guidance": str(monitor_guidance or "defensive_exit"),
            "defensive_mode": bool(macro_stress_overlay.get("active")),
            "global_sentiment_score": _to_float(global_signal.get("score"), 0.0),
            "fear_index": {
                "vix_level": _to_float(fear_index.get("level"), 0.0),
                "vix_pressure": _to_float(fear_index.get("level_pressure"), 0.0),
                "elevated": bool(
                    _to_float(fear_index.get("level"), 0.0) >= 25.0
                    or _to_float(fear_index.get("level_pressure"), 0.0) >= 0.25
                ),
            },
            "macro_stress_score": _to_float(market_context_inputs.get("macro_risk"), 0.0),
            "macro_stress_flags": [str(x) for x in list(macro_stress_overlay.get("flags") or [])],
            "market_context_inputs": dict(market_context_inputs or {}),
            "theme_policy": {
                "preferred_themes": [str(x) for x in list(themes or [])],
                "avoid_themes": [str(x) for x in list(avoid_themes or [])],
                "theme_strength": dict(theme_strength or {}),
            },
            "news_policy": {
                "market_news_count": int(market_news_count),
                "candidate_news_count": int(candidate_news_count),
                "average_news_score": _to_float(news_ctx.get("avg_score"), 0.0),
            },
        },
        "scanner_policy": {
            "candidate_sources": dict(scanner_source_policy or {}),
            "scanner_bias": dict(scanner_bias_context or {}),
            "priority_tilts": [str(x) for x in list(scanner_priority or [])],
            "score_weights": _strategy_policy_score_weights(),
            "filters": {
                "max_volatility_for_entry": _to_float(entry_policy.get("max_volatility_for_entry"), 0.12),
                "min_feature_coverage": 0,
                "min_confidence_for_entry": _to_float(entry_policy.get("min_confidence_for_entry"), 0.35),
            },
            "ranking_rules": {
                "allow_repeat_symbol": True,
                "repeat_symbol_penalty": _to_float(os.getenv("SCANNER_REPEAT_SYMBOL_PENALTY", "0.0"), 0.0),
            },
        },
        "entry_policy": dict(entry_policy),
        "monitor_policy": {
            "entry_policy": dict(monitor_entry_policy or {}),
            "position_guards": dict(monitor_policy or {}),
            "adaptive_exit": dict(exit_policy or {}),
            "hard_risk_rails": {
                "hard_stop_pct": _to_float(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "0.03"), 0.03),
                "max_stop_pct_cap": _to_float(os.getenv("STRATEGY_POLICY_MAX_STOP_PCT_CAP", "0.10"), 0.10),
                "use_eod_flat": _is_trueish(effective_use_eod_flat),
            },
        },
        "decision_policy": {
            "use_strategy_v1_engine": False,
            "allow_score_override": False,
            "score_override_scope": "disabled",
            "strategy_v1_name": "",
            "strategy_variant_hint": "unified_ai_strategist",
        },
        "operator_explain": {
            "why_this_playbook": (
                f"playbook={str(playbook or 'defensive')} regime={str(market_regime or 'neutral')} "
                f"sentiment={str(market_sentiment or 'neutral')}"
            ),
            "why_this_risk_tone": (
                f"risk_tone={str(risk_tone or 'normal')} guidance={str(monitor_guidance or 'defensive_exit')}"
            ),
            "what_changes_next": str(macro_stress_overlay.get("reason") or ""),
        },
    }


def _build_commander_context_summary(
    *,
    state: Dict[str, Any],
    commander_decision: Dict[str, Any],
    runtime_phase: str,
    market_regime: str,
    playbook: str,
) -> Dict[str, Any]:
    raw = dict(commander_decision or {}) if isinstance(commander_decision, dict) else {}
    source = "commander_decision" if raw else "strategist_node_fallback"
    allowed_playbooks = [str(x) for x in list(raw.get("allowed_playbooks") or []) if str(x or "").strip()]
    if not allowed_playbooks and str(playbook or "").strip():
        allowed_playbooks = [str(playbook)]
    banned_playbooks = [str(x) for x in list(raw.get("banned_playbooks") or []) if str(x or "").strip()]
    strategist_refresh_context = (
        dict(raw.get("strategist_refresh_context") or {})
        if isinstance(raw.get("strategist_refresh_context"), dict)
        else {}
    )
    open_position_refresh_context = (
        dict(raw.get("open_position_refresh_context") or {})
        if isinstance(raw.get("open_position_refresh_context"), dict)
        else dict(strategist_refresh_context)
        if str(strategist_refresh_context.get("refresh_scope") or "").strip().lower() == "open_position_monitor_refresh"
        else {}
    )
    memory_packets = dict(raw.get("memory_packets") or {}) if isinstance(raw.get("memory_packets"), dict) else {}
    commander_memory_policy = (
        dict(raw.get("commander_memory_policy") or {})
        if isinstance(raw.get("commander_memory_policy"), dict)
        else {}
    )
    scanner_memory_bias = dict(raw.get("scanner_memory_bias") or {}) if isinstance(raw.get("scanner_memory_bias"), dict) else {}
    scanner_memory_bias_summary = (
        dict(raw.get("scanner_memory_bias_summary") or {})
        if isinstance(raw.get("scanner_memory_bias_summary"), dict)
        else {}
    )
    monitor_memory_bias = dict(raw.get("monitor_memory_bias") or {}) if isinstance(raw.get("monitor_memory_bias"), dict) else {}
    monitor_memory_bias_summary = (
        dict(raw.get("monitor_memory_bias_summary") or {})
        if isinstance(raw.get("monitor_memory_bias_summary"), dict)
        else {}
    )
    try:
        memory_packets = load_commander_memory_packets(state=state)
        commander_memory_policy = build_commander_memory_policy(
            session_bias=str(raw.get("session_bias") or runtime_phase or "session"),
            memory_packets=memory_packets,
            usage_disabled=_strategy_memory_usage_disabled(state),
        )
        scanner_memory_bias = build_scanner_memory_bias(
            commander_memory_policy=commander_memory_policy,
            memory_packets=memory_packets,
        )
        scanner_memory_bias_summary = summarize_scanner_memory_bias(scanner_memory_bias)
        monitor_memory_bias = build_monitor_memory_bias(
            commander_memory_policy=commander_memory_policy,
            memory_packets=memory_packets,
        )
        monitor_memory_bias_summary = summarize_monitor_memory_bias(monitor_memory_bias)
    except Exception:
        pass
    if isinstance(raw.get("commander_horizon_policy"), dict):
        commander_horizon_policy = dict(raw.get("commander_horizon_policy") or {})
    else:
        prior_strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
        horizon_proposal = {}
        if isinstance(prior_strategist_output.get("strategist_horizon_proposal"), dict):
            horizon_proposal = dict(prior_strategist_output.get("strategist_horizon_proposal") or {})
        elif isinstance(prior_strategist_output.get("strategy_horizon_feedback"), dict):
            horizon_proposal = dict(prior_strategist_output.get("strategy_horizon_feedback") or {})
        commander_horizon_policy = build_commander_horizon_policy(
            horizon_proposal,
            commander_context={
                "runtime_phase": str(runtime_phase or ""),
                "market_regime": str(raw.get("market_regime") or market_regime or "neutral"),
                "session_bias": str(raw.get("session_bias") or runtime_phase or "session"),
                "risk_mode": str(raw.get("risk_mode") or "balanced"),
                "strategist_refresh_requested": bool(raw.get("strategist_refresh_requested")),
                "strategist_refresh_reason": str(raw.get("strategist_refresh_reason") or ""),
                "commander_memory_policy": dict(commander_memory_policy),
            },
            memory_packets=memory_packets,
            runtime_phase=str(runtime_phase or ""),
            live_validation_mode=True,
            source="strategist_commander_context",
        )
    horizon_context = {
        "owner": "commander",
        "strategy_horizon": str(commander_horizon_policy.get("strategy_horizon") or ""),
        "source_strategy_horizon": str(commander_horizon_policy.get("source_strategy_horizon") or ""),
        "observability_only": True,
        "allow_behavior_translation": bool(commander_horizon_policy.get("allow_behavior_translation")),
        "do_not_force_hold": True,
        "decision_reason": str(commander_horizon_policy.get("decision_reason") or ""),
        "behavior_translation": dict(commander_horizon_policy.get("behavior_translation") or {}),
    }
    strategist_refresh_context = {
        **dict(strategist_refresh_context or {}),
        "commander_horizon_policy": dict(commander_horizon_policy),
        "horizon_context": dict(horizon_context),
    }
    if open_position_refresh_context:
        open_position_refresh_context = {
            **dict(open_position_refresh_context or {}),
            "commander_horizon_policy": dict(commander_horizon_policy),
            "horizon_context": dict(horizon_context),
        }
    return {
        "source": source,
        "market_regime": str(raw.get("market_regime") or market_regime or "neutral"),
        "session_bias": str(raw.get("session_bias") or runtime_phase or "session"),
        "risk_mode": str(raw.get("risk_mode") or "balanced"),
        "allowed_playbooks": allowed_playbooks[:4],
        "banned_playbooks": banned_playbooks[:4],
        "scanner_mission": str(raw.get("scanner_mission") or ""),
        "monitor_mission": str(raw.get("monitor_mission") or ""),
        "llm_policy": str(raw.get("llm_policy") or raw.get("llm_invocation_policy") or ""),
        "command_intent": str(raw.get("command_intent") or ""),
        "strategist_invocation": str(raw.get("strategist_invocation") or ""),
        "flow_instruction": str(raw.get("flow_instruction") or ""),
        "no_trade_reason_code": str(raw.get("no_trade_reason_code") or ""),
        "strategist_refresh_requested": bool(raw.get("strategist_refresh_requested")),
        "strategist_refresh_reason": str(raw.get("strategist_refresh_reason") or ""),
        "strategist_refresh_context": dict(strategist_refresh_context),
        "open_position_refresh_context": dict(open_position_refresh_context),
        "commander_horizon_policy": dict(commander_horizon_policy),
        "horizon_context": dict(horizon_context),
        "decision_summary": str(raw.get("decision_summary") or ""),
        "observations": dict(raw.get("observations") or {}) if isinstance(raw.get("observations"), dict) else {},
        "memory_packets": dict(memory_packets),
        "commander_memory_policy": dict(commander_memory_policy),
        "scanner_memory_bias": dict(scanner_memory_bias),
        "scanner_memory_bias_summary": dict(scanner_memory_bias_summary),
        "monitor_memory_bias": dict(monitor_memory_bias),
        "monitor_memory_bias_summary": dict(monitor_memory_bias_summary),
        "source_priority": [str(x) for x in list(raw.get("source_priority") or []) if str(x or "").strip()][:4],
        "source_refs": dict(raw.get("source_refs") or {}) if isinstance(raw.get("source_refs"), dict) else {},
        "shadow_used": bool(raw.get("shadow_used")),
        "strategist_fallback_used": bool(raw.get("strategist_fallback_used")),
    }


def _build_strategist_plan(
    *,
    commander_context: Dict[str, Any],
    playbook: str,
    candidate_symbols: List[str],
    themes: List[str],
    avoid_themes: List[str],
    scanner_priority: List[str],
    monitor_guidance: str,
    trade_aggressiveness: str,
    risk_tone: str,
    news_query_reasoning: str,
    monitor_policy: Dict[str, Any],
    exit_policy: Dict[str, Any],
) -> Dict[str, Any]:
    selected_playbook = str(playbook or "defensive")
    candidate_hypotheses: List[Dict[str, Any]] = []
    for symbol in list(candidate_symbols or [])[:5]:
        rationale_parts: List[str] = []
        if list(themes):
            rationale_parts.append(f"theme={themes[0]}")
        if list(scanner_priority):
            rationale_parts.append(f"priority={scanner_priority[0]}")
        if str(commander_context.get("scanner_mission") or "").strip():
            rationale_parts.append(str(commander_context.get("scanner_mission") or ""))
        candidate_hypotheses.append(
            {
                "symbol": str(symbol or ""),
                "hypothesis": (
                    f"{selected_playbook} setup candidate"
                    + (f" with {', '.join(rationale_parts[:2])}" if rationale_parts else "")
                ),
                "source": "candidate_symbols_hint",
            }
        )
    symbol_constraints = {
        "candidate_symbols_hint": [str(x) for x in list(candidate_symbols or [])[:8]],
        "preferred_themes": [str(x) for x in list(themes or [])[:5]],
        "avoid_themes": [str(x) for x in list(avoid_themes or [])[:6]],
        "scanner_priority": [str(x) for x in list(scanner_priority or [])[:6]],
        "candidate_limit": int(min(len(list(candidate_symbols or [])), 8)),
    }
    entry_plan = {
        "setup_family": selected_playbook,
        "monitor_guidance": str(monitor_guidance or ""),
        "risk_tone": str(risk_tone or ""),
        "trade_aggressiveness": str(trade_aggressiveness or ""),
        "scanner_priority": [str(x) for x in list(scanner_priority or [])[:4]],
        "scanner_mission": str(commander_context.get("scanner_mission") or ""),
        "confirmation_required": True,
    }
    exit_plan = {
        "monitor_guidance": str(monitor_guidance or ""),
        "monitor_mission": str(commander_context.get("monitor_mission") or ""),
        "position_guards": dict(monitor_policy or {}),
        "adaptive_exit": dict(exit_policy or {}),
    }
    strategy_summary = (
        f"Strategist refined commander context into {selected_playbook} plan "
        f"for {len(list(candidate_symbols or []))} candidate symbols."
    )
    open_position_refresh_context = (
        dict(commander_context.get("open_position_refresh_context") or {})
        if isinstance(commander_context.get("open_position_refresh_context"), dict)
        else {}
    )
    commander_horizon_policy = (
        dict(commander_context.get("commander_horizon_policy") or {})
        if isinstance(commander_context.get("commander_horizon_policy"), dict)
        else {}
    )
    if str(open_position_refresh_context.get("refresh_summary") or "").strip():
        strategy_summary += f" Hold refresh context: {str(open_position_refresh_context.get('refresh_summary') or '').strip()[:220]}"
    if str(news_query_reasoning or "").strip():
        strategy_summary += f" News focus: {str(news_query_reasoning).strip()[:180]}"
    return {
        "selected_playbook": selected_playbook,
        "candidate_hypotheses": candidate_hypotheses,
        "symbol_constraints": symbol_constraints,
        "entry_plan": entry_plan,
        "exit_plan": exit_plan,
        "open_position_refresh_context": dict(open_position_refresh_context),
        "strategy_summary": strategy_summary,
    }


def _build_market_regime_summary(
    *,
    market_regime: str,
    market_sentiment: str,
    market_structure: str,
    playbook: str,
    global_signal: Dict[str, Any],
) -> str:
    fear_index = dict(global_signal.get("fear_index") or {}) if isinstance(global_signal.get("fear_index"), dict) else {}
    vix_level = _to_float(fear_index.get("level"), 0.0)
    return (
        f"{str(market_regime or 'neutral')} regime / {str(market_sentiment or 'neutral')} sentiment / "
        f"{str(market_structure or 'mixed')} structure with playbook {str(playbook or 'defensive')}. "
        f"VIX={vix_level:.2f}."
    )


def _build_strategist_monitor_entry_policy_seed(
    *,
    playbook: str,
    market_regime: str,
    monitor_guidance: str,
    risk_tone: str,
    trade_aggressiveness: str,
) -> Dict[str, Any]:
    policy = build_default_monitor_entry_policy().to_dict()
    policy["policy_source"] = "strategist"
    policy["adjustments"] = [
        f"seed_playbook:{str(playbook or 'defensive')}",
        f"seed_regime:{str(market_regime or 'neutral')}",
        f"seed_guidance:{str(monitor_guidance or 'defensive_exit')}",
        f"seed_risk_tone:{str(risk_tone or 'normal')}",
        f"seed_trade_aggressiveness:{str(trade_aggressiveness or 'medium')}",
    ]
    return policy


def _build_monitor_entry_policy_rationale(
    *,
    playbook: str,
    market_regime: str,
    market_sentiment: str,
    monitor_guidance: str,
    risk_tone: str,
    trade_aggressiveness: str,
    validation_meta: Dict[str, Any],
) -> str:
    summary = (
        f"Strategist drafted {str(playbook or 'defensive')} entry policy for "
        f"{str(market_regime or 'neutral')} / {str(market_sentiment or 'neutral')} conditions "
        f"with guidance {str(monitor_guidance or 'defensive_exit')}, "
        f"risk tone {str(risk_tone or 'normal')}, and aggressiveness {str(trade_aggressiveness or 'medium')}."
    )
    if bool(validation_meta.get("fallback_used")):
        reason = str(validation_meta.get("fallback_reason") or "validation_fallback")
        return f"{summary} Policy fallback used: {reason}."
    return summary


def _build_strategy_policy_provenance(*, commander_context: Dict[str, Any]) -> Dict[str, Any]:
    source = str(commander_context.get("source") or "strategist_node_fallback")
    merged_from = ["strategist_node"]
    if source == "commander_decision":
        merged_from.insert(0, "commander_decision")
    else:
        merged_from.insert(0, source)
    return {
        "market_policy_owner": "commander",
        "scanner_policy_owner": "strategist",
        "monitor_policy_owner": "strategist",
        "decision_policy_owner": "strategist",
        "merged_from": merged_from,
        "commander_context_source": source,
        "strategist_plan_source": "strategist_node",
        "monitor_entry_policy_source": "strategist",
        "scanner_bias_source": "strategist",
        "shadow_used": bool(commander_context.get("shadow_used")),
        "strategist_fallback_used": bool(commander_context.get("strategist_fallback_used")),
    }


def _report_focus(*, playbook: str, themes: List[str]) -> List[str]:
    if playbook == "defensive":
        return ["theme_accuracy", "exit_quality", "overtrading", "guard_blocks"]
    if playbook == "breakout":
        return ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"]
    return ["theme_accuracy", "scanner_fit", "exit_quality", "overtrading"]


def _augment_strategy_fields(
    *,
    themes: List[str],
    avoid_themes: List[str],
    scanner_priority: List[str],
    report_focus: List[str],
    market_context_inputs: Dict[str, float],
    news_ctx: Dict[str, Any],
) -> Tuple[List[str], List[str], List[str], List[str]]:
    out_themes = list(themes or [])
    out_avoid = list(avoid_themes or [])
    out_priority = list(scanner_priority or [])
    out_focus = list(report_focus or [])

    macro_risk = _to_float(market_context_inputs.get("macro_risk"), 0.0)
    realized_vol = _to_float(market_context_inputs.get("realized_volatility"), 0.0)
    fallback_n = int(news_ctx.get("fallback") or 0)
    unavailable_n = int(news_ctx.get("unavailable") or 0)

    if macro_risk >= 0.65 or realized_vol >= 0.045:
        for x in ("liquidity", "risk_penalty", "drawdown_control"):
            if x not in out_priority:
                out_priority.append(x)
        for x in ("high_gap_speculative", "illiquid_microcap"):
            if x not in out_avoid:
                out_avoid.append(x)
        if "guard_blocks" not in out_focus:
            out_focus.append("guard_blocks")

    if (fallback_n + unavailable_n) > 0:
        if "data_quality" not in out_focus:
            out_focus.append("data_quality")
        if "headline_only_momentum" not in out_avoid:
            out_avoid.append("headline_only_momentum")

    if not out_themes:
        out_themes = ["broad_market_leaders"]

    return out_themes[:5], out_avoid[:6], out_priority[:6], out_focus[:6]


def _key_events(
    *,
    state: Dict[str, Any],
    global_signal: Dict[str, Any],
    news_signal_map: Dict[str, Dict[str, Any]],
    market_regime: str,
    playbook: str,
    market_context_inputs: Dict[str, float],
    news_ctx: Dict[str, Any],
    theme_strength: Dict[str, float],
) -> List[str]:
    out: List[str] = []

    def add(x: Any) -> None:
        s = str(x or "").strip()
        if s and s not in out:
            out.append(s)

    # highest priority: explicit externally-provided macro/event list
    for key in ("macro_events", "global_events", "major_events"):
        vals = state.get(key)
        if isinstance(vals, list):
            for row in vals:
                add(row)
            break

    add(
        "global_sentiment "
        f"score={_signal_score(global_signal):.3f} "
        f"status={str(global_signal.get('status') or '')} "
        f"source={str(global_signal.get('source') or '')}"
    )
    components = global_signal.get("components") if isinstance(global_signal.get("components"), dict) else {}
    if components:
        add(
            "us_indices "
            f"sp500={_to_float(components.get('sp500_ret'), 0.0) * 100.0:.2f}% "
            f"nasdaq={_to_float(components.get('nasdaq_ret'), 0.0) * 100.0:.2f}% "
            f"dow={_to_float(components.get('dow_ret'), 0.0) * 100.0:.2f}%"
        )
    korea_indices = global_signal.get("korea_indices") if isinstance(global_signal.get("korea_indices"), dict) else {}
    korea_rows = korea_indices.get("indices") if isinstance(korea_indices.get("indices"), dict) else {}
    kospi = korea_rows.get("KOSPI") if isinstance(korea_rows.get("KOSPI"), dict) else {}
    kosdaq = korea_rows.get("KOSDAQ") if isinstance(korea_rows.get("KOSDAQ"), dict) else {}
    if kospi or kosdaq:
        bits: List[str] = []
        if kospi:
            bits.append(
                "kospi="
                f"{_to_float(kospi.get('current'), 0.0):.2f}"
                f"/prev={_to_float(kospi.get('previous_close'), 0.0):.2f}"
                f"/chg={_to_float(kospi.get('change_pct'), 0.0):+.2f}%"
            )
        if kosdaq:
            bits.append(
                "kosdaq="
                f"{_to_float(kosdaq.get('current'), 0.0):.2f}"
                f"/prev={_to_float(kosdaq.get('previous_close'), 0.0):.2f}"
                f"/chg={_to_float(kosdaq.get('change_pct'), 0.0):+.2f}%"
            )
        add("korea_indices " + " ".join(bits))
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    if fear_index:
        add(
            "fear_index "
            f"vix={_to_float(fear_index.get('level'), 0.0):.2f} "
            f"change={_to_float(fear_index.get('change_pct'), 0.0):.2f}% "
            f"pressure={_to_float(fear_index.get('level_pressure'), 0.0):.3f}"
        )
    add(
        "market_context "
        f"index_trend={_to_float(market_context_inputs.get('index_trend'), 0.0):.3f} "
        f"breadth={_to_float(market_context_inputs.get('market_breadth'), 0.0):.3f} "
        f"realized_vol={_to_float(market_context_inputs.get('realized_volatility'), 0.0):.3f} "
        f"macro_risk={_to_float(market_context_inputs.get('macro_risk'), 0.0):.3f}"
    )
    add(
        "news_signal_health "
        f"ok={int(news_ctx.get('ok') or 0)} "
        f"unavailable={int(news_ctx.get('unavailable') or 0)} "
        f"fallback={int(news_ctx.get('fallback') or 0)} "
        f"avg_score={_to_float(news_ctx.get('avg_score'), 0.0):.3f}"
    )
    if theme_strength:
        top_theme = sorted(theme_strength.items(), key=lambda kv: kv[1], reverse=True)[0]
        add(f"theme_strength top={top_theme[0]} score={float(top_theme[1]):.3f}")
    add(f"market_regime={market_regime}")
    add(f"playbook={playbook}")

    return out[:5]


def _extract_ai_overrides(state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, Any]:
    # External LLM strategists can inject this shape without breaking node contract.
    for key in ("ai_strategist_output", "strategist_ai_output", "strategic_brief"):
        raw = state.get(key)
        if isinstance(raw, dict):
            return dict(raw)
    raw_policy = policy.get("strategist_ai_output") if isinstance(policy.get("strategist_ai_output"), dict) else {}
    return dict(raw_policy)


def _merge_override_text_list(base: List[str], override_values: Any, *, limit: int = 8) -> List[str]:
    if not isinstance(override_values, list):
        return list(base)[:limit]
    merged: List[str] = []
    seen = set()
    for row in list(override_values) + list(base):
        s = str(row or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        merged.append(s)
        if len(merged) >= limit:
            break
    return merged


def _build_strategic_answers(
    *,
    commander_context: Dict[str, Any],
    market_regime: str,
    market_sentiment: str,
    key_events: List[str],
    themes: List[str],
    avoid_themes: List[str],
    playbook: str,
    scanner_bias: str,
    scanner_priority: List[str],
    trade_aggressiveness: str,
    risk_tone: str,
    monitor_guidance: str,
    report_focus: List[str],
    recent_strategy_feedback: Dict[str, Any],
    strategy_memory: Dict[str, Any],
    read_model_facts: Dict[str, Any],
    reports_root: str | Path | None = None,
) -> Dict[str, Any]:
    open_position_refresh_context = (
        dict(commander_context.get("open_position_refresh_context") or {})
        if isinstance(commander_context.get("open_position_refresh_context"), dict)
        else {}
    )
    strategist_refresh_context = (
        dict(commander_context.get("strategist_refresh_context") or {})
        if isinstance(commander_context.get("strategist_refresh_context"), dict)
        else {}
    )
    refresh_context = (
        dict(open_position_refresh_context)
        if open_position_refresh_context
        else dict(strategist_refresh_context)
    )
    commander_horizon_policy = (
        dict(commander_context.get("commander_horizon_policy") or {})
        if isinstance(commander_context.get("commander_horizon_policy"), dict)
        else {}
    )
    selected_symbol = str(refresh_context.get("selected_symbol") or "")
    selected_symbol_was_rank1_raw = refresh_context.get("selected_symbol_was_rank1")
    selected_symbol_was_rank1 = (
        bool(selected_symbol_was_rank1_raw)
        if selected_symbol_was_rank1_raw is not None
        else int(refresh_context.get("selected_rank") or 0) == 1
    )
    return {
        "q1_market_mode": market_regime,
        "q2_global_macro_events": list(key_events),
        "q3_leading_themes": list(themes),
        "q4_theme_strength_check": "use_scanner_score_breakdown_and_theme_boost",
        "q5_preferred_playbook": playbook,
        "q6_scanner_priority_stocks": list(scanner_priority),
        "q7_avoid_conditions": list(avoid_themes),
        "q8_trade_aggressiveness": trade_aggressiveness,
        "q9_risk_tone": risk_tone,
        "q10_scanner_ranking_priority": list(scanner_priority),
        "q11_monitor_exit_guidance": monitor_guidance,
        "q12_reporter_focus": list(report_focus),
        "q13_recent_strategy_feedback": {
            "feedback_window_size": int(recent_strategy_feedback.get("feedback_window_size") or 0),
            "top_recent_strengths": list(recent_strategy_feedback.get("top_recent_strengths") or [])[:3],
            "top_recent_weaknesses": list(recent_strategy_feedback.get("top_recent_weaknesses") or [])[:3],
            "recent_reporter_summary": list(recent_strategy_feedback.get("recent_reporter_summary") or [])[:2],
        },
        "q14_strategy_memory_advisory": {
            "status": str(strategy_memory.get("status") or ""),
            "best_playbooks": list(strategy_memory.get("best_playbooks") or [])[:3],
            "worst_playbooks": list(strategy_memory.get("worst_playbooks") or [])[:3],
            "recent_failures": list(strategy_memory.get("recent_failures") or [])[:3],
            "recent_success_patterns": list(strategy_memory.get("recent_success_patterns") or [])[:3],
            "recent_playbook_performance": dict(strategy_memory.get("playbook_performance_snapshot") or {}),
            "reporter_analysis_digest": dict(strategy_memory.get("reporter_analysis_digest") or {}),
        },
        "q15_commander_refresh_context": {
            "requested": bool(commander_context.get("strategist_refresh_requested")),
            "reason": str(commander_context.get("strategist_refresh_reason") or ""),
            "refresh_scope": str(refresh_context.get("refresh_scope") or ""),
            "selected_symbol": selected_symbol,
            "hold_repeat_count_max": int(refresh_context.get("hold_repeat_count_max") or 0),
            "selected_hold_repeat_count": int(refresh_context.get("selected_hold_repeat_count") or 0),
            "monitor_reason": str(refresh_context.get("monitor_reason") or ""),
            "active_exit_axis": str(refresh_context.get("active_exit_axis") or ""),
            "refresh_summary": str(refresh_context.get("refresh_summary") or ""),
            "selected_rank": int(refresh_context.get("selected_rank") or 0),
            "selected_score": _round_optional(refresh_context.get("selected_score"), 4),
            "scanner_primary_candidate": dict(refresh_context.get("scanner_primary_candidate") or {}),
            "actual_selected_candidate": dict(
                refresh_context.get("actual_selected_candidate")
                or refresh_context.get("scanner_primary_candidate")
                or {}
            ),
            "scanner_rank1_candidate": dict(refresh_context.get("scanner_rank1_candidate") or {}),
            "scanner_runner_ups": [
                dict(row)
                for row in list(refresh_context.get("scanner_runner_ups") or [])[:4]
                if isinstance(row, dict)
            ],
            "scanner_top_candidates": [
                dict(row)
                for row in list(refresh_context.get("scanner_top_candidates") or [])[:5]
                if isinstance(row, dict)
            ],
            "selected_symbol_was_rank1": bool(selected_symbol_was_rank1),
            "stage2_context_quality": str(refresh_context.get("stage2_context_quality") or ""),
            "stage2_context_quality_reasons": [
                str(reason or "")
                for reason in list(refresh_context.get("stage2_context_quality_reasons") or [])[:6]
                if str(reason or "").strip()
            ],
            "entry_state": dict(refresh_context.get("entry_state") or {}),
            "carry_state": str(refresh_context.get("carry_state") or commander_context.get("carry_state") or ""),
            "carry_risk_bias": str(
                refresh_context.get("carry_risk_bias") or commander_context.get("carry_risk_bias") or ""
            ),
            "carry_risk_reason": str(
                refresh_context.get("carry_risk_reason") or commander_context.get("carry_risk_reason") or ""
            ),
            "session_open_recovery_assessment": dict(
                refresh_context.get("session_open_recovery_assessment")
                or commander_context.get("session_open_recovery_assessment")
                or {}
            ),
            "prior_monitor_entry_policy_summary": dict(
                refresh_context.get("prior_monitor_entry_policy_summary")
                or strategist_refresh_context.get("prior_monitor_entry_policy_summary")
                or {}
            )
            if isinstance(
                refresh_context.get("prior_monitor_entry_policy_summary")
                or strategist_refresh_context.get("prior_monitor_entry_policy_summary"),
                dict,
            )
            else {},
            "current_monitor_entry_policy_summary": dict(
                refresh_context.get("current_monitor_entry_policy_summary")
                or strategist_refresh_context.get("current_monitor_entry_policy_summary")
                or {}
            )
            if isinstance(
                refresh_context.get("current_monitor_entry_policy_summary")
                or strategist_refresh_context.get("current_monitor_entry_policy_summary"),
                dict,
            )
            else {},
            "selected_symbol_memory": _build_symbol_refresh_memory_excerpt(
                selected_symbol,
                read_model_facts,
                reports_root,
            ),
            "commander_horizon_policy": dict(commander_horizon_policy),
            "horizon_context": {
                "owner": str(commander_horizon_policy.get("owner") or "commander") if commander_horizon_policy else "",
                "strategy_horizon": str(commander_horizon_policy.get("strategy_horizon") or ""),
                "source_strategy_horizon": str(commander_horizon_policy.get("source_strategy_horizon") or ""),
                "observability_only": bool(commander_horizon_policy.get("observability_only", True))
                if commander_horizon_policy
                else True,
                "do_not_force_hold": bool(commander_horizon_policy.get("do_not_force_hold", True))
                if commander_horizon_policy
                else True,
            },
        },
        "scanner_bias": scanner_bias,
    }


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger, resolve_event_log_path

    return EventLogger(log_path=resolve_event_log_path())


def _emit_strategist_event(
    state: Dict[str, Any],
    *,
    name: str,
    payload: Dict[str, Any],
    level: str = "info",
    symbol: str = "",
) -> None:
    try:
        logger = _make_event_logger(state)
        from libs.core.event_logger import log_state_event

        log_state_event(
            logger,
            state,
            stage="strategist",
            event=name,
            event_name=f"strategist.{name}",
            payload=dict(payload or {}),
            level=level,
            agent="strategist",
            symbol=str(symbol or ""),
        )
    except Exception:
        return


def _log_strategist_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "strategist-node")
        logger.log(run_id=run_id, stage="strategist", event="summary", payload=dict(payload))
    except Exception:
        return


def _log_strategist_llm_result(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "strategist-node")
        logger.log(run_id=run_id, stage="strategist_llm", event="result", payload=dict(payload))
    except Exception:
        return


def _sample_news_for_evidence(
    news_items_by_symbol: Dict[str, List[Any]],
    *,
    max_symbols: int = 8,
    max_items_per_symbol: int = 3,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for symbol, rows in list(news_items_by_symbol.items())[:max_symbols]:
        sample: List[Any] = []
        if isinstance(rows, list):
            for item in rows[:max_items_per_symbol]:
                if isinstance(item, dict):
                    sample.append(
                        {
                            "title": str(item.get("title") or ""),
                            "source": str(item.get("source") or ""),
                            "published_at": str(item.get("published_at") or ""),
                        }
                    )
                else:
                    sample.append(str(item))
        out[str(symbol)] = {"count": len(rows) if isinstance(rows, list) else 0, "sample": sample}
    return out


def _rank_news_evidence_rows(
    items_by_target: Dict[str, List[Any]],
    signal_map: Dict[str, Dict[str, Any]],
    *,
    used_targets: List[str],
    scope: str,
    max_rows: int = 10,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    used_set = {str(item or "").strip() for item in list(used_targets or []) if str(item or "").strip()}
    for target, rows_raw in (items_by_target or {}).items():
        target_text = str(target or "").strip()
        signal = signal_map.get(target_text) if isinstance(signal_map.get(target_text), dict) else {}
        sample_titles: List[str] = []
        for row in list(rows_raw or [])[:3]:
            if isinstance(row, dict):
                title = str(row.get("title") or "").strip()
            else:
                title = str(row or "").strip()
            if title:
                sample_titles.append(title)
        rows.append(
            {
                "target": target_text,
                "scope": str(scope or ""),
                "score": _round_optional(signal.get("score"), 4),
                "status": str(signal.get("status") or ""),
                "source": str(signal.get("source") or ""),
                "reason": str(signal.get("reason") or ""),
                "headline_count": int(len(list(rows_raw or []))),
                "sample_titles": sample_titles,
                "used_in_decision": bool(target_text in used_set),
            }
        )
    rows.sort(
        key=lambda row: (
            -abs(float(row.get("score") or 0.0)),
            -int(row.get("headline_count") or 0),
            str(row.get("target") or ""),
        )
    )
    return rows[: max(0, int(max_rows))]


def _global_sentiment_breakdown_payload(global_signal: Dict[str, Any]) -> Dict[str, Any]:
    weights = global_signal.get("weights") if isinstance(global_signal.get("weights"), dict) else {}
    components = global_signal.get("components") if isinstance(global_signal.get("components"), dict) else {}
    fear_index = global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {}
    neutral_vix = max(1.0, _to_float(fear_index.get("neutral_level"), _to_float(weights.get("vix_neutral_level"), 20.0)))
    vix_level = _to_float(components.get("vix_level"), 0.0)
    vix_level_pressure = max(0.0, min((vix_level - neutral_vix) / neutral_vix, 2.0))
    contributions: List[Dict[str, Any]] = []
    factor_specs = (
        ("sp500", "sp500_ret", 1.0, ""),
        ("nasdaq", "nasdaq_ret", 1.0, ""),
        ("dow", "dow_ret", 1.0, ""),
        ("kospi", "kospi_ret", 1.0, ""),
        ("kosdaq", "kosdaq_ret", 1.0, ""),
        ("vix", "vix_ret", -1.0, "higher VIX change reduces risk appetite"),
        (
            "vix_level",
            "vix_level",
            -1.0,
            "weighted contribution uses normalized vix_level_pressure instead of raw VIX level",
        ),
        ("dxy", "dxy_ret", -1.0, "stronger dollar reduces risk appetite"),
        ("tnx", "tnx_delta", -1.0, "higher yields reduce risk appetite"),
    )
    for weight_key, component_key, direction, note in factor_specs:
        weight = _to_float(weights.get(weight_key), 0.0)
        raw_value = _to_float(components.get(component_key), 0.0)
        effective_value = vix_level_pressure if component_key == "vix_level" else raw_value
        signed_effective_value = float(direction * effective_value)
        contributions.append(
            {
                "factor": str(component_key),
                "weight": float(weight),
                "raw_value": float(raw_value),
                "effective_value": float(effective_value),
                "signed_effective_value": signed_effective_value,
                "weighted_contribution": float(weight * signed_effective_value),
                "direction": "risk_on_supportive" if direction > 0 else "risk_off_pressure",
                "note": str(note or ""),
            }
        )
    contributions.sort(key=lambda row: -abs(float(row.get("weighted_contribution") or 0.0)))
    return {
        "score": _round_optional(global_signal.get("score"), 4),
        "status": str(global_signal.get("status") or ""),
        "source": str(global_signal.get("source") or ""),
        "reason": str(global_signal.get("reason") or ""),
        "raw_score": _round_optional(global_signal.get("raw_score"), 4),
        "index_moves": dict(global_signal.get("index_moves") or {}),
        "korea_indices": dict(global_signal.get("korea_indices") or {}),
        "macro_moves": dict(global_signal.get("macro_moves") or {}),
        "fear_index": dict(fear_index or {}),
        "factor_contributions": contributions,
    }


def _merge_news_samples(*samples: Dict[str, Any], limit: int = 12) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        for key, value in sample.items():
            if len(out) >= limit:
                return out
            norm_key = str(key or "").strip()
            if not norm_key or norm_key in out:
                continue
            out[norm_key] = value
    return out


def strategist_node(state: Dict[str, Any]) -> Dict[str, Any]:
    policy = _default_policy(state.get("policy"))
    k = _resolve_top_n_candidates(policy)
    policy["candidate_k"] = int(k)

    # 1) candidates (injected or generated)
    candidates = _candidates_from_state(state, k)
    universe_candidates: List[Dict[str, Any]] = []

    if not candidates:
        if bool(policy.get("use_universe_builder", True)):
            universe_candidates = build_candidate_universe(state=state, policy=policy, topk=k)
            if universe_candidates:
                candidates = [
                    {
                        "symbol": str(r.get("symbol") or ""),
                        "why": str(r.get("why") or "universe_builder"),
                        "sources": list(r.get("sources") or []),
                        "universe_score": float(r.get("score") or 0.0),
                        "source_scores": dict(r.get("source_scores") or {}),
                        "source_count": int(r.get("source_count") or len(list(r.get("sources") or []))),
                    }
                    for r in universe_candidates
                    if str(r.get("symbol") or "").strip()
                ]

    if not candidates:
        source = str(policy.get("candidate_source") or "top_picks")
        if source == "market_rank":
            gen = MarketRankCandidateGenerator()
            # tolerate signature differences
            try:
                symbols = gen.generate(state=state, policy=policy, k=k)
            except TypeError:
                try:
                    symbols = gen.generate(state=state, k=k)
                except TypeError:
                    symbols = gen.generate(state=state)
            candidates = [{"symbol": str(s), "why": "market_rank"} for s in symbols[:k]]
        else:
            # top_picks (M18-2): generator signature is generate(state)
            gen = TopPicksCandidateGenerator(
                rank_mode=str(policy.get("candidate_rank_mode") or "value"),
                rank_topn=int(policy.get("candidate_rank_topn") or 30),
                topk=int(policy.get("candidate_topk") or k),
            )
            symbols = gen.generate(state=state)
            candidates = [{"symbol": str(s), "why": "top_picks"} for s in symbols[:k]]

    # Absolute fallback:
    # - source is configurable (`fallback_candidate_symbols`, `FALLBACK_CANDIDATE_SYMBOLS`)
    # - static default remains as last-resort compatibility path
    if not candidates:
        fallback, fallback_source = resolve_fallback_symbols(state=state, policy=policy, limit=k)
        fallback_why = "fallback_static" if fallback_source == "static_default" else "fallback_configured"
        candidates = [{"symbol": s, "why": fallback_why, "fallback_source": fallback_source} for s in fallback]
        state["strategist_fallback_source"] = fallback_source

    state["universe_candidates"] = universe_candidates
    symbols = [c["symbol"] for c in candidates]

    # 2) Global sentiment (score + data-quality signal)
    now = int(time.time())
    global_enabled = bool(policy.get("use_global_sentiment", True)) or state.get("mock_global_sentiment") is not None
    if global_enabled:
        try:
            global_signal = dict(compute_global_sentiment_signal(state=state, policy=policy))
        except Exception:
            global_signal = make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="strategist_node",
                reason="global_sentiment_exception",
                ts=now,
            )
    else:
        global_signal = make_signal(
            score=0.0,
            status=SIGNAL_STATUS_FALLBACK,
            source="global_policy",
            reason="global_sentiment_disabled",
            ts=now,
        )
    gs = _signal_score(global_signal)
    policy["global_sentiment"] = float(gs)
    # Keep canonical state-level score and signal shape for downstream nodes.
    state["global_sentiment"] = {"score": float(gs)}
    state["global_sentiment_signal"] = dict(global_signal)
    market_context_inputs = _extract_market_context_inputs(state)
    theme_strength_packet = build_theme_strength_packet(state=state, policy=policy)
    state["theme_strength_packet"] = dict(theme_strength_packet)
    _merge_theme_packet_into_state(state, theme_strength_packet)
    available_themes = _theme_packet_available_themes(theme_strength_packet)
    state["available_themes"] = list(available_themes)
    theme_hints = _extract_themes(state, policy)
    news_query_targets = _build_market_news_query_targets(
        state=state,
        policy=policy,
        global_signal=global_signal,
        market_context_inputs=market_context_inputs,
        theme_hints=theme_hints,
    )
    news_query_reasoning = _build_market_news_query_reasoning(
        state=state,
        policy=policy,
        global_signal=global_signal,
        market_context_inputs=market_context_inputs,
        theme_hints=theme_hints,
    )
    state["news_query_targets"] = list(news_query_targets)
    state["news_query_reasoning"] = news_query_reasoning
    theme_news_symbol_limit = _to_int(
        policy.get("theme_news_symbol_limit")
        if policy.get("theme_news_symbol_limit") is not None
        else os.getenv("STRATEGIST_NEWS_THEME_COMPONENT_SYMBOL_LIMIT", "12"),
        12,
    )
    news_collection_limit = _to_int(
        policy.get("news_collection_symbol_limit")
        if policy.get("news_collection_symbol_limit") is not None
        else os.getenv("STRATEGIST_NEWS_COLLECTION_SYMBOL_LIMIT", "20"),
        20,
    )
    theme_news_symbols = _theme_component_symbols_for_news(
        state=state,
        available_themes=list(available_themes),
        theme_hints=list(theme_hints),
        limit=theme_news_symbol_limit,
    )
    news_collection_symbols = _merge_news_collection_symbols(
        base_symbols=list(symbols),
        theme_symbols=list(theme_news_symbols),
        limit=max(len(list(symbols or [])), news_collection_limit),
    )
    news_collection_policy = {
        "provider": str(policy.get("news_provider") or "naver"),
        "market_query_targets": list(news_query_targets),
        "candidate_symbols_requested": list(symbols),
        "theme_component_symbols_requested": list(theme_news_symbols),
        "collection_symbols": list(news_collection_symbols),
        "post_scanner_requery": False,
        "reuse_policy": "reuse_pre_scanner_news_pool",
    }
    state["news_collection_policy"] = dict(news_collection_policy)
    state["news_collection_symbols"] = list(news_collection_symbols)
    state["news_theme_component_symbols"] = list(theme_news_symbols)

    # policy adjustment based on global sentiment
    # - risk-off: max_risk decreases, min_confidence increases
    # - risk-on : max_risk increases, min_confidence decreases
    base_max_risk = float(policy.get("max_risk", 0.7))
    base_min_conf = float(policy.get("min_confidence", 0.6))
    off_th = float(policy.get("candidate_risk_off_threshold", -0.5))
    on_th = float(policy.get("candidate_risk_on_threshold", 0.5))

    if gs <= off_th:
        policy["max_risk"] = max(0.05, base_max_risk - 0.1)
        policy["min_confidence"] = min(0.99, base_min_conf + 0.1)
    elif gs >= on_th:
        policy["max_risk"] = min(1.0, base_max_risk + 0.1)
        policy["min_confidence"] = max(0.01, base_min_conf - 0.1)
    else:
        policy["max_risk"] = base_max_risk
        policy["min_confidence"] = base_min_conf

    # 3) News analysis (score + data-quality signal)
    news_items_by_symbol = {s: [] for s in news_collection_symbols}
    news_signal_map: Dict[str, Dict[str, Any]] = {}
    market_news_items_by_target = {q: [] for q in news_query_targets}
    market_news_signal_map: Dict[str, Dict[str, Any]] = {}

    if bool(policy.get("use_news_analysis", False)) or state.get("mock_news_sentiment") is not None:
        # mock_news_sentiment path is handled inside score_news_sentiment_signal.
        if bool(policy.get("use_news_analysis", False)) or state.get("mock_news_items") is not None:
            if news_collection_symbols:
                news_items_by_symbol = collect_news_items(news_collection_symbols, state=state, policy=policy)
            if news_query_targets:
                market_news_items_by_target = collect_news_items(news_query_targets, state=state, policy=policy)
        try:
            if news_collection_symbols:
                news_signal_map = score_news_sentiment_signal(
                    news_items_by_symbol,
                    state=state,
                    policy=policy,
                    symbols=news_collection_symbols,
                )
            else:
                news_signal_map = {}
            if news_query_targets:
                market_news_signal_map = score_news_sentiment_signal(
                    market_news_items_by_target,
                    state=state,
                    policy=policy,
                    symbols=news_query_targets,
                )
            else:
                market_news_signal_map = {}
        except Exception:
            news_signal_map = {
                s: make_signal(
                    score=0.0,
                    status=SIGNAL_STATUS_FALLBACK,
                    source="strategist_node",
                    reason="news_sentiment_exception",
                    ts=now,
                )
                for s in news_collection_symbols
            }
            market_news_signal_map = {
                q: make_signal(
                    score=0.0,
                    status=SIGNAL_STATUS_FALLBACK,
                    source="strategist_node",
                    reason="market_news_sentiment_exception",
                    ts=now,
                )
                for q in news_query_targets
            }
    else:
        news_signal_map = {
            s: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="news_policy",
                reason="news_analysis_disabled",
                ts=now,
                )
                for s in news_collection_symbols
        }
        market_news_signal_map = {
            q: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="news_policy",
                reason="news_analysis_disabled",
                ts=now,
            )
            for q in news_query_targets
        }

    news_sent = {s: _signal_score(news_signal_map.get(s)) for s in news_collection_symbols}
    candidate_news_ctx = _news_context_summary(news_signal_map, news_items_by_symbol)
    market_news_ctx = _news_context_summary(market_news_signal_map, market_news_items_by_target)
    news_ctx = _merge_news_contexts(candidate_news_ctx, market_news_ctx)
    news_avg_score = _to_float(news_ctx.get("avg_score"), 0.0)

    state["policy"] = policy
    state["candidates"] = candidates
    # store per-symbol news items (dict)
    state["news_items"] = news_items_by_symbol
    state["news_sentiment"] = news_sent
    state["news_sentiment_signal"] = news_signal_map
    state["candidate_news_items"] = dict(news_items_by_symbol)
    state["candidate_news_context"] = dict(candidate_news_ctx)
    state["market_news_items"] = dict(market_news_items_by_target)
    state["market_news_sentiment"] = {q: _signal_score(market_news_signal_map.get(q)) for q in news_query_targets}
    state["market_news_sentiment_signal"] = dict(market_news_signal_map)
    state["market_news_context"] = dict(market_news_ctx)

    # 4) Candidate rerank (M18-5): apply weights and negative-news filter, then risk-off count reduction
    w_news = float(policy.get("candidate_news_weight", 0.2))
    w_g = float(policy.get("candidate_global_weight", 0.1))
    neg_th = float(policy.get("candidate_negative_news_threshold", -0.7))

    # assign candidate_score
    scored = []
    candidate_meta = {str(c.get("symbol")): dict(c) for c in candidates if isinstance(c, dict)}
    for idx, c in enumerate(candidates):
        s = c["symbol"]
        rank_bias = (len(candidates) - idx) / max(len(candidates), 1) * 0.01  # small deterministic tie-break
        cs = rank_bias + (w_news * news_sent.get(s, 0.0)) + (w_g * gs)
        scored.append((s, cs, news_sent.get(s, 0.0), c.get("why") or ""))

    # filter overly negative news, but don't drop below 3 items if possible
    filtered = [t for t in scored if t[2] >= neg_th]
    if len(filtered) >= 3:
        scored = filtered

    scored.sort(key=lambda x: x[1], reverse=True)
    candidates = []
    for (s, cs, _ns, why) in scored:
        base = dict(candidate_meta.get(s) or {})
        base["symbol"] = s
        base["why"] = why
        base["rank_score"] = float(cs)
        candidates.append(base)

    # risk-off reduces count
    if gs <= float(policy.get("candidate_risk_off_threshold", -0.5)):
        max_cnt = int(policy.get("candidate_max_count_risk_off", 3))
        candidates = candidates[: max(1, max_cnt)]
    else:
        candidates = candidates[:k]

    state["candidates"] = candidates
    themes = list(theme_hints)
    pre_ai_overrides = _extract_ai_overrides(state, policy)
    themes = _merge_override_text_list(themes, pre_ai_overrides.get("themes"), limit=5)
    candidate_symbols = [str(c.get("symbol") or "") for c in candidates if str(c.get("symbol") or "").strip()]
    theme_index = _extract_theme_symbol_index(state, policy)
    theme_scores = state.get("theme_scores") if isinstance(state.get("theme_scores"), dict) else {}
    theme_strength = _theme_strength_map(
        themes=list(themes),
        candidates=list(candidates),
        theme_scores=theme_scores,
        theme_index=theme_index,
    )
    if theme_strength:
        ranked_theme_names = [k for k, _v in sorted(theme_strength.items(), key=lambda kv: kv[1], reverse=True)]
        themes = _merge_override_text_list(ranked_theme_names, themes, limit=5)

    state["themes"] = themes
    state["candidate_symbols"] = list(candidate_symbols)
    state["theme_map"] = _merge_theme_symbol_map(
        state.get("theme_map"),
        themes=list(themes),
        candidate_symbols=list(candidate_symbols),
        protect_existing_themes=_theme_packet_symbol_map_is_authoritative(theme_strength_packet),
    )
    state["sector_map"] = _merge_theme_symbol_map(
        state.get("sector_map"),
        themes=list(themes),
        candidate_symbols=list(candidate_symbols),
        protect_existing_themes=_theme_packet_symbol_map_is_authoritative(theme_strength_packet),
    )

    regime_score = _compose_regime_score(
        global_score=gs,
        news_score=news_avg_score,
        market_context_inputs=market_context_inputs,
    )
    sentiment_score = float(
        _clamp(
            (0.60 * gs)
            + (0.30 * _to_float(news_ctx.get("avg_score"), 0.0))
            + (0.10 * _to_float(market_context_inputs.get("index_trend"), 0.0)),
            -1.0,
            1.0,
        )
    )
    market_regime = _risk_regime_label(regime_score)
    market_sentiment = _market_sentiment_label(sentiment_score)
    market_structure, regime_factors = _market_structure_label(
        state=state,
        global_score=gs,
        market_context_inputs=market_context_inputs,
    )
    playbook = _pick_playbook(
        market_structure=market_structure,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
    )
    scanner_priority = _scanner_priority(playbook, market_regime)
    scanner_bias = _scanner_bias(playbook=playbook, market_regime=market_regime)
    avoid_themes = _avoid_themes(market_sentiment=market_sentiment, playbook=playbook)
    trade_aggressiveness = _trade_aggressiveness(market_regime=market_regime, market_structure=market_structure)
    risk_tone = _risk_tone(trade_aggressiveness)
    monitor_guidance = _monitor_guidance(market_regime=market_regime, playbook=playbook)
    pre_llm_market_regime = str(market_regime or "")
    pre_llm_market_sentiment = str(market_sentiment or "")
    pre_llm_market_structure = str(market_structure or "")
    pre_llm_playbook = str(playbook or "")
    pre_llm_monitor_guidance = str(monitor_guidance or "")
    pre_llm_risk_tone = str(risk_tone or "")
    pre_llm_trade_aggressiveness = str(trade_aggressiveness or "")
    monitor_policy = _monitor_policy(
        state=state,
        policy=policy,
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    exit_policy = _exit_policy(
        playbook=playbook,
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    macro_stress_overlay = _macro_stress_overlay(global_signal)
    report_focus = _report_focus(playbook=playbook, themes=themes)
    themes, avoid_themes, scanner_priority, report_focus = _augment_strategy_fields(
        themes=themes,
        avoid_themes=avoid_themes,
        scanner_priority=scanner_priority,
        report_focus=report_focus,
        market_context_inputs=market_context_inputs,
        news_ctx=news_ctx,
    )
    key_events = _key_events(
        state=state,
        global_signal=global_signal,
        news_signal_map=news_signal_map,
        market_regime=market_regime,
        playbook=playbook,
        market_context_inputs=market_context_inputs,
        news_ctx=news_ctx,
        theme_strength=theme_strength,
    )
    recent_strategy_feedback = _load_recent_strategy_feedback(state, policy)
    reporter_feedback_packet = _load_reporter_feedback_packet(state, policy)
    strategy_memory_advisory = _load_strategy_memory_advisory(state, policy)
    report_focus = _merge_override_text_list(
        report_focus,
        recent_strategy_feedback.get("suggested_report_focus"),
        limit=8,
    )
    reports_root = Path(str(state.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports")
    read_model_facts = _load_deterministic_read_models(state, candidate_symbols)
    read_model_facts_summary = summarize_read_model_facts(read_model_facts)
    
    state["recent_strategy_feedback"] = dict(recent_strategy_feedback)
    state["reporter_feedback_packet"] = dict(reporter_feedback_packet)
    state["strategy_memory"] = dict(strategy_memory_advisory)
    state["read_model_facts_summary"] = dict(read_model_facts_summary)
    pre_llm_commander_context = _build_commander_context_summary(
        state=state,
        commander_decision=state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {},
        runtime_phase=str(state.get("runtime_phase") or "session"),
        market_regime=market_regime,
        playbook=playbook,
    )

    selected_themes_hint = (
        [
            str(x or "")
            for x in list(_resolve_selected_themes_from_api(
                available_themes=list(available_themes),
                themes=list(themes),
                raw_selected=[],
            ))
            if str(x or "").strip()
        ]
        if available_themes
        else []
    )
    fallback_theme_hints = [str(x or "") for x in list(themes) if str(x or "").strip()] if not available_themes else []

    llm_payload = {
        "global_sentiment_signal": dict(global_signal),
        "news_context": dict(news_ctx),
        "market_context_inputs": dict(market_context_inputs),
        "recent_strategy_feedback": dict(recent_strategy_feedback),
        "reporter_feedback_packet": dict(reporter_feedback_packet),
        "strategy_memory": dict(strategy_memory_advisory),
        "memory_packets": dict(pre_llm_commander_context.get("memory_packets") or {}),
        "commander_memory_policy": dict(pre_llm_commander_context.get("commander_memory_policy") or {}),
        "scanner_memory_bias": dict(pre_llm_commander_context.get("scanner_memory_bias") or {}),
        "monitor_memory_bias": dict(pre_llm_commander_context.get("monitor_memory_bias") or {}),
        "macro_stress_overlay_hint": dict(macro_stress_overlay),
        "market_regime_hint": market_regime,
        "market_sentiment_hint": market_sentiment,
        "commander_refresh_context": _build_llm_commander_refresh_context(
            pre_llm_commander_context,
            read_model_facts,
            reports_root,
        ),
        "read_model_facts": dict(read_model_facts),
        "market_structure_hint": market_structure,
        "playbook_hint": playbook,
        "monitor_entry_policy_baseline": build_default_monitor_entry_policy().to_dict(),
        "theme_strength": dict(theme_strength),
        "theme_strength_packet": dict(theme_strength_packet),
        "available_themes": list(available_themes),
        "themes_hint": list(themes),
        "selected_themes_hint": list(selected_themes_hint),
        "fallback_theme_hints": list(fallback_theme_hints),
        "news_collection_policy": dict(news_collection_policy),
        "news_query_targets": list(news_query_targets),
        "news_sentiment_signal": dict(news_signal_map),
        "market_news_sentiment_signal": dict(market_news_signal_map),
        "reports_root": str(reports_root),
        "market_news_sample": _sample_news_for_evidence(
            market_news_items_by_target,
            max_symbols=6,
            max_items_per_symbol=2,
        ),
        "candidate_news_sample": _sample_news_for_evidence(
            news_items_by_symbol,
            max_symbols=6,
            max_items_per_symbol=2,
        ),
        "candidate_symbols_hint": list(candidate_symbols)[:10],
        "key_events_hint": list(key_events),
        "recent_monitor_blockers_hint": list(recent_strategy_feedback.get("recent_monitor_issues") or [])[:5],
    }
    candidate_news_sample = _sample_news_for_evidence(news_items_by_symbol)
    market_news_sample = _sample_news_for_evidence(market_news_items_by_target)
    try:
        record_raw_input(
            run_id=str(state.get("run_id") or "strategist-unknown"),
            agent="strategist",
            stage="theme_selection",
            raw_input={
                "collected_news": _merge_news_samples(market_news_sample, candidate_news_sample),
                "collected_market_news": market_news_sample,
                "collected_candidate_news": candidate_news_sample,
                "news_query_targets": list(news_query_targets),
                "news_collection_policy": dict(news_collection_policy),
                "global_sentiment_inputs": dict(global_signal),
                "macro_indicators": dict(market_context_inputs),
                "market_summary": {
                    "market_regime_hint": market_regime,
                    "market_sentiment_hint": market_sentiment,
                    "market_structure_hint": market_structure,
                    "news_query_targets": list(news_query_targets),
                    "news_query_reasoning": news_query_reasoning,
                    "candidate_symbols_hint": list(candidate_symbols)[:10],
                },
                "recent_strategy_feedback": dict(recent_strategy_feedback),
                "reporter_feedback_packet": dict(reporter_feedback_packet),
                "strategy_memory": dict(strategy_memory_advisory),
                "theme_strength_packet": dict(theme_strength_packet),
                "available_themes": list(available_themes),
                "llm_payload": dict(llm_payload),
            },
            decision_link={"stage": "strategist_input_collection"},
        )
    except Exception:
        pass
    llm_overrides, llm_meta = _run_strategist_frame_llm(state=state, policy=policy, payload=llm_payload)
    manual_overrides = _extract_ai_overrides(state, policy)
    ai_overrides = {**dict(llm_overrides or {}), **dict(manual_overrides or {})}
    llm_requested_playbook = _norm_playbook((llm_overrides or {}).get("playbook"))
    requested_playbook = _norm_playbook(ai_overrides.get("playbook"))
    requested_playbook_source = (
        "manual_override"
        if _norm_playbook((manual_overrides or {}).get("playbook"))
        else "llm"
        if llm_requested_playbook
        else "deterministic"
    )
    llm_required = _resolve_strategist_frame_llm_enabled(policy)
    llm_strict = _resolve_strategist_frame_llm_strict_enabled(policy)
    strategist_llm_blocked = bool(llm_required and llm_strict and str(llm_meta.get("status") or "") != "ok")
    strategist_llm_block_reason = ""
    if strategist_llm_blocked:
        strategist_llm_block_reason = (
            "strategist_llm_required"
            if str(llm_meta.get("status") or "") in {"disabled", "dry_run", "unavailable"}
            else "strategist_llm_failed"
        )

    if llm_required:
        llm_payload_log: Dict[str, Any] = {
            "call_kind": "strategic_frame",
            "provider": "openrouter",
            "model": str(llm_meta.get("model") or ""),
            "ok": str(llm_meta.get("status") or "") == "ok",
            "status": str(llm_meta.get("status") or ""),
            "latency_ms": int(llm_meta.get("latency_ms") or 0),
            "attempts": int(llm_meta.get("attempts") or 1),
            "repair_used": bool(llm_meta.get("repair_used")),
            "prompt_version": str(os.getenv("STRATEGIST_FRAME_LLM_PROMPT_VERSION", "m31-strategic-frame-v1") or "m31-strategic-frame-v1"),
            "schema_version": "strategist_output.v1",
            "llm_execution_profile_name": str(llm_meta.get("llm_execution_profile_name") or ""),
            "llm_execution_profile_source": str(llm_meta.get("llm_execution_profile_source") or ""),
            "llm_execution_effective_config": dict(llm_meta.get("llm_execution_effective_config") or {}),
            "themes": list((llm_overrides or {}).get("themes") or [])[:5],
            "avoid_themes": list((llm_overrides or {}).get("avoid_themes") or [])[:5],
            "playbook": str((llm_overrides or {}).get("playbook") or ""),
            "scanner_bias": str((llm_overrides or {}).get("scanner_bias") or ""),
            "risk_tone": str((llm_overrides or {}).get("risk_tone") or ""),
            "monitor_guidance": str((llm_overrides or {}).get("monitor_guidance") or ""),
            "candidate_hint_count": len(list(candidate_symbols)),
        }
        if llm_meta.get("reason"):
            llm_payload_log["error"] = str(llm_meta.get("reason"))
        if llm_meta.get("error_type"):
            llm_payload_log["error_type"] = str(llm_meta.get("error_type"))
        if llm_meta.get("recovery_method"):
            llm_payload_log["recovery_method"] = str(llm_meta.get("recovery_method"))
        if strategist_llm_blocked:
            llm_payload_log["blocked"] = True
            llm_payload_log["blocked_reason"] = strategist_llm_block_reason
        _log_strategist_llm_result(state, llm_payload_log)

    # Optional AI overrides are additive and bounded to keep deterministic fallback.
    market_regime = str(ai_overrides.get("market_regime") or market_regime).strip() or market_regime
    market_sentiment = str(ai_overrides.get("market_sentiment") or market_sentiment).strip() or market_sentiment
    playbook = str(ai_overrides.get("playbook") or playbook).strip() or playbook
    trade_aggressiveness = str(ai_overrides.get("trade_aggressiveness") or trade_aggressiveness).strip() or trade_aggressiveness
    risk_tone = str(ai_overrides.get("risk_tone") or risk_tone).strip() or risk_tone
    if isinstance(ai_overrides.get("themes"), list) and list(ai_overrides.get("themes") or []):
        themes = _merge_override_text_list([], ai_overrides.get("themes"), limit=5)
    else:
        themes = _merge_override_text_list(themes, ai_overrides.get("themes"), limit=5)
    raw_theme_strategy = ai_overrides.get("theme_strategy") if isinstance(ai_overrides.get("theme_strategy"), dict) else {}
    raw_selected_themes = ai_overrides.get("selected_themes")
    if not raw_selected_themes and isinstance(raw_theme_strategy, dict):
        raw_selected_themes = raw_theme_strategy.get("selected_themes")
    selected_themes = (
        _resolve_selected_themes_from_api(
            available_themes=list(available_themes),
            themes=list(themes),
            raw_selected=raw_selected_themes,
        )
        if available_themes
        else []
    )
    if selected_themes:
        themes = _merge_override_text_list([], [*list(selected_themes), *list(themes)], limit=5)
    key_events = _merge_override_text_list(key_events, ai_overrides.get("key_events"), limit=5)
    avoid_themes = _merge_override_text_list(avoid_themes, ai_overrides.get("avoid_themes"), limit=6)
    scanner_priority = _merge_override_text_list(scanner_priority, ai_overrides.get("scanner_priority"), limit=6)
    report_focus = _merge_override_text_list(report_focus, ai_overrides.get("report_focus"), limit=6)
    scanner_bias = str(ai_overrides.get("scanner_bias") or scanner_bias).strip().lower() or scanner_bias
    monitor_guidance = str(ai_overrides.get("monitor_guidance") or monitor_guidance).strip().lower() or monitor_guidance
    market_regime_summary = str(
        ai_overrides.get("market_regime_summary")
        or _build_market_regime_summary(
            market_regime=market_regime,
            market_sentiment=market_sentiment,
            market_structure=market_structure,
            playbook=playbook,
            global_signal=global_signal,
        )
    ).strip()
    policy_confidence = None
    try:
        if ai_overrides.get("confidence") not in (None, ""):
            policy_confidence = min(max(float(ai_overrides.get("confidence")), 0.0), 1.0)
    except Exception:
        policy_confidence = None
    policy_source = str(ai_overrides.get("policy_source") or "strategist").strip() or "strategist"
    monitor_policy_override = ai_overrides.get("monitor_policy")
    if isinstance(monitor_policy_override, dict):
        monitor_policy = {**monitor_policy, **dict(monitor_policy_override)}
    else:
        monitor_policy = _monitor_policy(
            state=state,
            policy=policy,
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
            risk_tone=risk_tone,
        )
    monitor_entry_policy_seed = _build_strategist_monitor_entry_policy_seed(
        playbook=playbook,
        market_regime=market_regime,
        monitor_guidance=monitor_guidance,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
    )
    monitor_entry_policy_input = (
        dict(ai_overrides.get("monitor_entry_policy") or {})
        if isinstance(ai_overrides.get("monitor_entry_policy"), dict)
        else dict(monitor_entry_policy_seed)
    )
    monitor_entry_policy_obj, monitor_entry_policy_validation = normalize_monitor_entry_policy(
        monitor_entry_policy_input,
        fallback_policy=MonitorEntryPolicy.from_mapping(monitor_entry_policy_seed),
        policy_source=policy_source,
    )
    monitor_entry_policy = build_monitor_entry_policy_bundle(
        threshold_policy=monitor_entry_policy_obj,
        playbook=playbook,
        monitor_guidance=monitor_guidance,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
        interpretation_policy=(
            dict(monitor_entry_policy_input.get("interpretation_policy") or {})
            if isinstance(monitor_entry_policy_input.get("interpretation_policy"), dict)
            else None
        ),
    )
    scanner_bias_context_input = {}
    if isinstance(ai_overrides.get("scanner_bias_context"), dict):
        scanner_bias_context_input = dict(ai_overrides.get("scanner_bias_context") or {})
    elif isinstance(ai_overrides.get("scanner_bias"), dict):
        scanner_bias_context_input = dict(ai_overrides.get("scanner_bias") or {})
    scanner_bias_context_seed = _build_scanner_bias_context_seed(
        playbook=playbook,
        scanner_bias=scanner_bias,
        monitor_entry_policy=monitor_entry_policy,
    )
    scanner_bias_context_obj, scanner_bias_context_validation = normalize_scanner_bias_context(
        scanner_bias_context_input or scanner_bias_context_seed,
        bias_source="strategist",
    )
    scanner_bias_context = scanner_bias_context_obj.to_dict()
    exit_policy_override = ai_overrides.get("exit_policy")
    if isinstance(exit_policy_override, dict):
        exit_policy = {**exit_policy, **dict(exit_policy_override)}
    else:
        exit_policy = _exit_policy(
            playbook=playbook,
            monitor_guidance=monitor_guidance,
            trade_aggressiveness=trade_aggressiveness,
            risk_tone=risk_tone,
        )
    monitor_guidance, risk_tone, trade_aggressiveness, exit_policy, report_focus, macro_stress_overlay = _apply_macro_stress_to_monitor_frame(
        global_signal=global_signal,
        monitor_guidance=monitor_guidance,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
        exit_policy=exit_policy,
        report_focus=report_focus,
    )
    monitor_policy = _monitor_policy(
        state=state,
        policy=policy,
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
    )
    scanner_source_policy = _scanner_source_policy(
        playbook=playbook,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
        market_regime=market_regime,
        themes=list(themes),
        fear_index=global_signal.get("fear_index") if isinstance(global_signal.get("fear_index"), dict) else {},
    )
    tactical_strategy = _normalize_tactical_strategy(ai_overrides.get("tactical_strategy"), playbook=playbook)
    tactical_subtype = _normalize_tactical_subtype(
        ai_overrides.get("tactical_subtype"),
        tactical_strategy=tactical_strategy,
    )
    strategy_scores = _normalize_strategy_scores(
        ai_overrides.get("strategy_scores"),
        playbook=playbook,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        market_structure=market_structure,
        market_context_inputs=market_context_inputs,
    )
    rejected_strategy_reasons = _normalize_rejected_strategy_reasons(
        ai_overrides.get("rejected_strategy_reasons"),
        tactical_strategy=tactical_strategy,
        strategy_scores=strategy_scores,
    )
    candidate_watch_policy = _normalize_candidate_watch_policy(
        ai_overrides.get("candidate_watch_policy"),
        tactical_strategy=tactical_strategy,
        playbook=playbook,
        market_regime=market_regime,
        risk_tone=risk_tone,
        trade_aggressiveness=trade_aggressiveness,
    )

    if isinstance(ai_overrides.get("themes"), list) and list(ai_overrides.get("themes") or []):
        # Keep runtime theme/sector maps aligned with the final strategist frame
        # only when AI/manual overrides actually replace themes. Unconditionally
        # syncing broad fallback themes makes scanner sector-theme sourcing too
        # aggressive in deterministic baseline paths.
        state["theme_map"] = _merge_theme_symbol_map(
            state.get("theme_map"),
            themes=list(themes),
            candidate_symbols=list(state.get("candidate_symbols") or []),
            protect_existing_themes=_theme_packet_symbol_map_is_authoritative(theme_strength_packet),
        )
        state["sector_map"] = _merge_theme_symbol_map(
            state.get("sector_map"),
            themes=list(themes),
            candidate_symbols=list(state.get("candidate_symbols") or []),
            protect_existing_themes=_theme_packet_symbol_map_is_authoritative(theme_strength_packet),
        )

    theme_strategy = _build_theme_strategy_surface(
        available_themes=list(available_themes),
        selected_themes=list(selected_themes),
        playbook=playbook,
        theme_strength_packet=dict(theme_strength_packet),
        raw_theme_strategy=raw_theme_strategy,
    )
    state["selected_themes"] = list(selected_themes)
    state["theme_strategy"] = dict(theme_strategy)

    commander_context = _build_commander_context_summary(
        state=state,
        commander_decision=state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {},
        runtime_phase=str(state.get("runtime_phase") or "session"),
        market_regime=market_regime,
        playbook=playbook,
    )
    strategic_answers = _build_strategic_answers(
        commander_context=commander_context,
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        key_events=key_events,
        themes=themes,
        avoid_themes=avoid_themes,
        playbook=playbook,
        scanner_bias=scanner_bias,
        scanner_priority=scanner_priority,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
        monitor_guidance=monitor_guidance,
        report_focus=report_focus,
        recent_strategy_feedback=recent_strategy_feedback,
        strategy_memory=strategy_memory_advisory,
        read_model_facts=dict(read_model_facts),
        reports_root=reports_root,
    )
    strategist_plan = _build_strategist_plan(
        commander_context=commander_context,
        playbook=playbook,
        candidate_symbols=[str(x.get("symbol") or "") for x in list(state.get("candidates") or []) if isinstance(x, dict)]
        or [str(x) for x in list(state.get("candidate_symbols") or []) if str(x or "").strip()],
        themes=list(themes),
        avoid_themes=list(avoid_themes),
        scanner_priority=list(scanner_priority),
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
        news_query_reasoning=news_query_reasoning,
        monitor_policy=dict(monitor_policy),
        exit_policy=dict(exit_policy),
    )
    policy_rationale = str(
        ai_overrides.get("policy_rationale")
        or _build_monitor_entry_policy_rationale(
            playbook=playbook,
            market_regime=market_regime,
            market_sentiment=market_sentiment,
            monitor_guidance=monitor_guidance,
            risk_tone=risk_tone,
            trade_aggressiveness=trade_aggressiveness,
            validation_meta=monitor_entry_policy_validation,
        )
    ).strip()
    baseline_policy_summary = (
        dict((commander_context.get("strategist_refresh_context") or {}).get("current_monitor_entry_policy_summary") or {})
        if isinstance((commander_context.get("strategist_refresh_context") or {}).get("current_monitor_entry_policy_summary"), dict)
        else {}
    )
    if not baseline_policy_summary:
        baseline_policy_summary = _summarize_monitor_entry_policy_for_adjustment(
            build_default_monitor_entry_policy().to_dict()
        )
    current_policy_summary = _summarize_monitor_entry_policy_for_adjustment(monitor_entry_policy)
    policy_adjustment = _normalize_policy_adjustment_surface(
        raw_adjustment=ai_overrides.get("policy_adjustment"),
        baseline_summary=baseline_policy_summary,
        current_summary=current_policy_summary,
        refresh_requested=bool(commander_context.get("strategist_refresh_requested")),
        recent_strategy_feedback=recent_strategy_feedback,
    )
    strategy_adjustment_directives = _normalize_strategy_adjustment_directives(
        raw_directives=ai_overrides.get("strategy_adjustment_directives"),
        playbook=playbook,
        policy_adjustment=policy_adjustment,
        commander_context=commander_context,
        strategy_memory=strategy_memory_advisory,
        selected_symbol_memory=dict(
            ((strategic_answers.get("q15_commander_refresh_context") or {}).get("selected_symbol_memory") or {})
        ),
    )
    if bool(policy_adjustment.get("adjustment_required")) and not list(policy_adjustment.get("delta_fields") or []):
        monitor_entry_policy_validation = dict(monitor_entry_policy_validation or {})
        validation_issues = [
            str(x)
            for x in list(monitor_entry_policy_validation.get("issues") or [])
            if str(x or "").strip()
        ]
        if "adjustment_required_but_no_policy_delta" not in validation_issues:
            validation_issues.append("adjustment_required_but_no_policy_delta")
        monitor_entry_policy_validation["issues"] = list(validation_issues)
    policy_provenance = _build_strategy_policy_provenance(commander_context=commander_context)
    strategy_policy = _build_strategy_policy(
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        playbook=playbook,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
        monitor_guidance=monitor_guidance,
        global_signal=global_signal,
        market_context_inputs=market_context_inputs,
        themes=list(themes),
        avoid_themes=list(avoid_themes),
        theme_strength=dict(theme_strength),
        scanner_priority=list(scanner_priority),
        scanner_source_policy=dict(scanner_source_policy),
        scanner_bias_context=dict(scanner_bias_context),
        monitor_entry_policy=dict(monitor_entry_policy),
        monitor_policy=dict(monitor_policy),
        exit_policy=dict(exit_policy),
        macro_stress_overlay=dict(macro_stress_overlay),
        news_ctx=dict(news_ctx),
    )
    strategy_policy["commander_context"] = dict(commander_context)
    strategy_policy["strategist_plan"] = dict(strategist_plan)
    strategy_policy["provenance"] = dict(policy_provenance)
    market_policy = strategy_policy.get("market_policy") if isinstance(strategy_policy.get("market_policy"), dict) else {}
    market_policy["pre_llm_playbook"] = pre_llm_playbook
    market_policy["llm_requested_playbook"] = llm_requested_playbook
    market_policy["requested_playbook"] = requested_playbook
    market_policy["requested_playbook_source"] = requested_playbook_source
    market_policy["final_playbook"] = playbook
    market_policy["tactical_strategy"] = tactical_strategy
    market_policy["tactical_subtype"] = tactical_subtype
    market_policy["strategy_scores"] = dict(strategy_scores)
    market_policy["rejected_strategy_reasons"] = dict(rejected_strategy_reasons)
    strategy_policy["market_policy"] = dict(market_policy)
    scanner_policy = strategy_policy.get("scanner_policy") if isinstance(strategy_policy.get("scanner_policy"), dict) else {}
    scanner_policy["candidate_watch_policy"] = dict(candidate_watch_policy)
    strategy_policy["scanner_policy"] = dict(scanner_policy)
    if isinstance(ai_overrides.get("strategy_horizon_feedback"), dict):
        strategy_horizon_input = dict(ai_overrides.get("strategy_horizon_feedback") or {})
    else:
        strategy_horizon_input = {
            "strategy_horizon": ai_overrides.get("strategy_horizon"),
            "expected_hold_window": (
                dict(ai_overrides.get("expected_hold_window") or {})
                if isinstance(ai_overrides.get("expected_hold_window"), dict)
                else {}
            ),
            "exit_guidance": (
                dict(ai_overrides.get("exit_guidance") or {})
                if isinstance(ai_overrides.get("exit_guidance"), dict)
                else {}
            ),
            "invalidation_conditions": ai_overrides.get("invalidation_conditions"),
            "monitor_handoff": (
                dict(ai_overrides.get("monitor_handoff") or {})
                if isinstance(ai_overrides.get("monitor_handoff"), dict)
                else {}
            ),
        }
    strategy_horizon_feedback = build_strategy_horizon_feedback(
        strategy_horizon_input,
        playbook=playbook,
        monitor_guidance=monitor_guidance,
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone,
        source=policy_source,
    )
    strategist_horizon_proposal = dict(strategy_horizon_feedback)
    commander_horizon_policy = build_commander_horizon_policy(
        strategist_horizon_proposal,
        commander_context=commander_context,
        memory_packets=commander_context.get("memory_packets") if isinstance(commander_context.get("memory_packets"), dict) else {},
        runtime_phase=str(state.get("runtime_phase") or commander_context.get("session_bias") or ""),
        live_validation_mode=True,
        source="strategist_node_commander_context",
    )
    horizon_context = {
        "owner": "commander",
        "strategy_horizon": str(commander_horizon_policy.get("strategy_horizon") or ""),
        "source_strategy_horizon": str(commander_horizon_policy.get("source_strategy_horizon") or ""),
        "observability_only": True,
        "do_not_force_hold": True,
        "decision_reason": str(commander_horizon_policy.get("decision_reason") or ""),
    }
    commander_context = dict(commander_context)
    strategist_refresh_context = (
        dict(commander_context.get("strategist_refresh_context") or {})
        if isinstance(commander_context.get("strategist_refresh_context"), dict)
        else {}
    )
    strategist_refresh_context["commander_horizon_policy"] = dict(commander_horizon_policy)
    strategist_refresh_context["horizon_context"] = dict(horizon_context)
    commander_context["strategist_refresh_context"] = strategist_refresh_context
    open_position_refresh_context = (
        dict(commander_context.get("open_position_refresh_context") or {})
        if isinstance(commander_context.get("open_position_refresh_context"), dict)
        else {}
    )
    if open_position_refresh_context:
        open_position_refresh_context["commander_horizon_policy"] = dict(commander_horizon_policy)
        open_position_refresh_context["horizon_context"] = dict(horizon_context)
        commander_context["open_position_refresh_context"] = open_position_refresh_context
    commander_context["commander_horizon_policy"] = dict(commander_horizon_policy)
    commander_context["horizon_context"] = dict(horizon_context)
    strategy_policy["commander_context"] = dict(commander_context)
    if isinstance((strategic_answers.get("q15_commander_refresh_context") or {}), dict):
        strategic_answers["q15_commander_refresh_context"] = {
            **dict(strategic_answers.get("q15_commander_refresh_context") or {}),
            "commander_horizon_policy": dict(commander_horizon_policy),
            "horizon_context": dict(horizon_context),
        }
    strategy_monitor_policy = (
        dict(strategy_policy.get("monitor_policy") or {})
        if isinstance(strategy_policy.get("monitor_policy"), dict)
        else {}
    )
    strategy_monitor_policy["strategy_horizon_feedback"] = dict(strategy_horizon_feedback)
    strategy_monitor_policy["strategist_horizon_proposal"] = dict(strategist_horizon_proposal)
    strategy_monitor_policy["commander_horizon_policy"] = dict(commander_horizon_policy)
    strategy_monitor_policy["horizon_policy"] = dict(commander_horizon_policy)
    strategy_monitor_policy["strategy_horizon"] = str(strategy_horizon_feedback.get("strategy_horizon") or "")
    strategy_monitor_policy["expected_hold_window"] = dict(strategy_horizon_feedback.get("expected_hold_window") or {})
    strategy_monitor_policy["exit_guidance"] = dict(strategy_horizon_feedback.get("exit_guidance") or {})
    strategy_policy["monitor_policy"] = strategy_monitor_policy
    strategy_policy["commander_horizon_policy"] = dict(commander_horizon_policy)
    strategist_plan["strategy_horizon_feedback"] = dict(strategy_horizon_feedback)
    strategist_plan["strategist_horizon_proposal"] = dict(strategist_horizon_proposal)
    strategist_plan["commander_horizon_policy"] = dict(commander_horizon_policy)
    strategist_plan["strategy_horizon"] = str(strategy_horizon_feedback.get("strategy_horizon") or "")
    strategy_policy["strategist_plan"] = dict(strategist_plan)

    state["market_regime"] = market_regime
    state["market_sentiment"] = market_sentiment
    state["market_structure"] = market_structure
    state["market_context_inputs"] = dict(market_context_inputs)
    state["regime_factors"] = dict(regime_factors)
    state["theme_strength"] = dict(theme_strength)
    state["key_events"] = list(key_events)
    state["avoid_themes"] = list(avoid_themes)
    state["playbook"] = playbook
    state["scanner_bias"] = scanner_bias
    state["scanner_bias_context"] = dict(scanner_bias_context)
    state["scanner_priority"] = list(scanner_priority)
    state["trade_aggressiveness"] = trade_aggressiveness
    state["risk_tone"] = risk_tone
    state["monitor_guidance"] = monitor_guidance
    state["macro_stress_overlay"] = dict(macro_stress_overlay)
    state["monitor_entry_policy"] = dict(monitor_entry_policy)
    state["monitor_policy"] = dict(monitor_policy)
    state["strategist_exit_policy"] = dict(exit_policy)
    state["strategy_policy"] = dict(strategy_policy)
    state["strategist_plan"] = dict(strategist_plan)
    state["commander_horizon_policy"] = dict(commander_horizon_policy)
    state["report_focus"] = list(report_focus)
    state["scanner_guidance"] = {
        "themes": list(themes),
        "selected_themes": list(selected_themes),
        "avoid_themes": list(avoid_themes),
        "playbook": playbook,
        "scanner_bias": scanner_bias,
        "scanner_bias_context": dict(scanner_bias_context),
        "scanner_priority": list(scanner_priority),
        "scanner_source_policy": dict(scanner_source_policy),
        "trade_aggressiveness": trade_aggressiveness,
        "risk_tone": risk_tone,
        "theme_source": str(theme_strength_packet.get("source") or ""),
        "theme_source_status": str(theme_strength_packet.get("status") or ""),
        "theme_strength_packet": dict(theme_strength_packet),
        "available_themes": list(available_themes),
        "theme_strategy": dict(theme_strategy),
    }
    strategist_feedback = _compact_recent_strategy_feedback_for_llm(recent_strategy_feedback)
    compact_reporter_feedback = _compact_reporter_feedback_for_llm(reporter_feedback_packet)
    performance_summary = {
        "feedback_window_size": int(recent_strategy_feedback.get("feedback_window_size") or 0),
        "recent_theme_performance": dict(strategist_feedback.get("recent_theme_performance") or {}),
        "recent_playbook_performance": dict(strategist_feedback.get("recent_playbook_performance") or {}),
        "top_recent_strengths": list(recent_strategy_feedback.get("top_recent_strengths") or [])[:3],
        "top_recent_weaknesses": list(recent_strategy_feedback.get("top_recent_weaknesses") or [])[:3],
        "advisory_only": bool(recent_strategy_feedback.get("advisory_only", True)),
    }
    strategist_output = StrategistOutput(
        market_regime=market_regime,
        market_sentiment=market_sentiment,
        key_events=list(key_events),
        themes=list(themes),
        avoid_themes=list(avoid_themes),
        playbook=playbook,
        scanner_bias=scanner_bias if scanner_bias in ("large_cap", "leader", "momentum", "value") else "leader",
        scanner_bias_context=dict(scanner_bias_context),
        scanner_priority=list(scanner_priority),
        scanner_source_policy=dict(scanner_source_policy),
        trade_aggressiveness=trade_aggressiveness,
        risk_tone=risk_tone if risk_tone in ("conservative", "normal", "aggressive") else "normal",
        monitor_guidance=(
            monitor_guidance
            if monitor_guidance in ("hold_through_noise", "defensive_exit", "quick_take_profit")
            else "defensive_exit"
        ),
        strategy_policy=dict(strategy_policy),
        report_focus=list(report_focus),
        recent_strategy_feedback=dict(recent_strategy_feedback),
        candidates=list(state["candidate_symbols"]),
        candidate_count=len(list(state["candidate_symbols"])),
        candidate_hints=list(state["candidate_symbols"]),
        strategic_answers=dict(strategic_answers),
        source="strategist_node",
    ).to_dict()
    strategist_output["monitor_policy"] = dict(monitor_policy)
    strategist_output["exit_policy"] = dict(exit_policy)
    strategist_output["macro_stress_overlay"] = dict(macro_stress_overlay)
    strategist_output["market_structure"] = market_structure
    strategist_output["regime_score"] = float(regime_score)
    strategist_output["sentiment_score"] = float(sentiment_score)
    strategist_output["news_context"] = dict(news_ctx)
    strategist_output["candidate_news_context"] = dict(candidate_news_ctx)
    strategist_output["market_news_context"] = dict(market_news_ctx)
    strategist_output["news_query_targets"] = list(news_query_targets)
    strategist_output["news_collection_policy"] = dict(news_collection_policy)
    strategist_output["news_query_reasoning"] = news_query_reasoning
    strategist_output["global_sentiment_signal"] = dict(global_signal)
    strategist_output["korea_indices"] = dict(global_signal.get("korea_indices") or {})
    strategist_output["market_context_inputs"] = dict(market_context_inputs)
    strategist_output["theme_strength"] = dict(theme_strength)
    strategist_output["theme_strength_packet"] = dict(theme_strength_packet)
    strategist_output["available_themes"] = list(available_themes)
    strategist_output["selected_themes"] = list(selected_themes)
    strategist_output["theme_strategy"] = dict(theme_strategy)
    strategist_output["theme_source"] = str(theme_strength_packet.get("source") or "")
    strategist_output["theme_source_status"] = str(theme_strength_packet.get("status") or "")
    strategist_output["theme_source_reason"] = str(theme_strength_packet.get("reason") or "")
    strategist_output["theme_source_fallback_used"] = bool(theme_strength_packet.get("fallback_used"))
    strategist_output["theme_fallback_used"] = bool(
        not theme_hints
        and any(str(theme or "").strip().lower() == "broad_market_leaders" for theme in list(themes or []))
    )
    strategist_output["recent_strategy_feedback"] = dict(recent_strategy_feedback)
    strategist_output["strategy_memory"] = dict(strategy_memory_advisory)
    strategist_output["strategy_memory_snapshot"] = dict(strategy_memory_advisory)
    strategist_output["strategist_feedback"] = dict(strategist_feedback)
    strategist_output["reporter_feedback_packet"] = dict(reporter_feedback_packet)
    strategist_output["reporter_feedback_summary"] = dict(compact_reporter_feedback)
    strategist_output["performance_summary"] = dict(performance_summary)
    strategist_output["playbook"] = playbook
    strategist_output["pre_llm_market_regime"] = pre_llm_market_regime
    strategist_output["pre_llm_market_sentiment"] = pre_llm_market_sentiment
    strategist_output["pre_llm_market_structure"] = pre_llm_market_structure
    strategist_output["pre_llm_playbook"] = pre_llm_playbook
    strategist_output["pre_llm_monitor_guidance"] = pre_llm_monitor_guidance
    strategist_output["pre_llm_risk_tone"] = pre_llm_risk_tone
    strategist_output["pre_llm_trade_aggressiveness"] = pre_llm_trade_aggressiveness
    strategist_output["llm_requested_playbook"] = llm_requested_playbook
    strategist_output["requested_playbook"] = requested_playbook
    strategist_output["requested_playbook_source"] = requested_playbook_source
    strategist_output["final_playbook"] = playbook
    strategist_output["tactical_strategy"] = tactical_strategy
    strategist_output["tactical_subtype"] = tactical_subtype
    strategist_output["strategy_scores"] = dict(strategy_scores)
    strategist_output["rejected_strategy_reasons"] = dict(rejected_strategy_reasons)
    strategist_output["candidate_watch_policy"] = dict(candidate_watch_policy)
    strategist_output["selected_playbook"] = strategist_plan.get("selected_playbook")
    strategist_output["candidate_hypotheses"] = list(strategist_plan.get("candidate_hypotheses") or [])
    strategist_output["symbol_constraints"] = dict(strategist_plan.get("symbol_constraints") or {})
    strategist_output["symbol_plan"] = dict(strategist_plan.get("symbol_constraints") or {})
    strategist_output["entry_plan"] = dict(strategist_plan.get("entry_plan") or {})
    strategist_output["exit_plan"] = dict(strategist_plan.get("exit_plan") or {})
    strategist_output["strategy_summary"] = str(strategist_plan.get("strategy_summary") or "")
    strategist_output["policy_provenance"] = dict(policy_provenance)
    strategist_output["market_regime_summary"] = market_regime_summary
    strategist_output["monitor_entry_policy"] = dict(monitor_entry_policy)
    strategist_output["strategy_horizon_feedback"] = dict(strategy_horizon_feedback)
    strategist_output["strategist_horizon_proposal"] = dict(strategist_horizon_proposal)
    strategist_output["commander_horizon_policy"] = dict(commander_horizon_policy)
    strategist_output["horizon_context"] = dict(horizon_context)
    strategist_output["strategy_horizon"] = str(strategy_horizon_feedback.get("strategy_horizon") or "")
    strategist_output["expected_hold_window"] = dict(strategy_horizon_feedback.get("expected_hold_window") or {})
    strategist_output["exit_guidance"] = dict(strategy_horizon_feedback.get("exit_guidance") or {})
    strategist_output["invalidation_conditions"] = list(strategy_horizon_feedback.get("invalidation_conditions") or [])
    strategist_output["scanner_bias_context"] = dict(scanner_bias_context)
    strategist_output["scanner_bias_summary"] = dict(summarize_scanner_bias_context(scanner_bias_context))
    strategist_output["scanner_bias_validation_status"] = str(scanner_bias_context_validation.get("status") or "ok")
    strategist_output["scanner_bias_validation_issues"] = list(scanner_bias_context_validation.get("issues") or [])
    strategist_output["policy_rationale"] = policy_rationale
    strategist_output["policy_adjustment"] = dict(policy_adjustment)
    strategist_output["strategy_adjustment_directives"] = dict(strategy_adjustment_directives)
    for stage_output_key in (
        "selected_symbol_tactical_review",
        "stale_intraday_hold_review",
        "end_of_day_carry_review",
    ):
        if isinstance(ai_overrides.get(stage_output_key), dict):
            strategist_output[stage_output_key] = dict(ai_overrides.get(stage_output_key) or {})
    if ai_overrides.get("selected_symbol_decision") not in (None, ""):
        strategist_output["selected_symbol_decision"] = str(ai_overrides.get("selected_symbol_decision") or "")
        strategist_output["target_symbol"] = str(ai_overrides.get("target_symbol") or "")
        strategist_output["target_rank"] = int(ai_overrides.get("target_rank") or 0)
        strategist_output["runner_up_order"] = list(ai_overrides.get("runner_up_order") or [])
        strategist_output["monitor_instruction"] = dict(ai_overrides.get("monitor_instruction") or {})
        strategist_output["entry_policy_delta"] = dict(ai_overrides.get("entry_policy_delta") or {})
        strategist_output["commander_actionability"] = str(ai_overrides.get("commander_actionability") or "")
    if ai_overrides.get("hold_review_decision") not in (None, ""):
        strategist_output["hold_review_decision"] = str(ai_overrides.get("hold_review_decision") or "")
    if ai_overrides.get("portfolio_level_decision") not in (None, ""):
        strategist_output["carry_review"] = list(ai_overrides.get("carry_review") or [])
        strategist_output["portfolio_level_decision"] = str(ai_overrides.get("portfolio_level_decision") or "")
    strategist_output["policy_source"] = policy_source
    strategist_output["policy_validation_status"] = str(monitor_entry_policy_validation.get("status") or "ok")
    strategist_output["policy_fallback_used"] = bool(monitor_entry_policy_validation.get("fallback_used"))
    strategist_output["policy_fallback_reason"] = str(monitor_entry_policy_validation.get("fallback_reason") or "")
    strategist_output["policy_partial_normalized"] = bool(monitor_entry_policy_validation.get("partial_normalized"))
    strategist_output["policy_default_filled_fields"] = list(monitor_entry_policy_validation.get("default_filled_fields") or [])
    strategist_output["policy_validation_issues"] = list(monitor_entry_policy_validation.get("issues") or [])
    strategist_output["policy_validation_missing_fields"] = list(
        monitor_entry_policy_validation.get("policy_validation_missing_fields")
        or monitor_entry_policy_validation.get("missing_fields")
        or []
    )
    strategist_output["policy_validation_invalid_fields"] = list(
        monitor_entry_policy_validation.get("policy_validation_invalid_fields")
        or monitor_entry_policy_validation.get("invalid_fields")
        or []
    )
    strategist_output["confidence"] = policy_confidence
    strategist_output["commander_context_ref"] = {
        "source": str(commander_context.get("source") or ""),
        "market_regime": str(commander_context.get("market_regime") or ""),
        "session_bias": str(commander_context.get("session_bias") or ""),
        "risk_mode": str(commander_context.get("risk_mode") or ""),
        "command_intent": str(commander_context.get("command_intent") or ""),
        "strategist_invocation": str(commander_context.get("strategist_invocation") or ""),
        "llm_policy": str(commander_context.get("llm_policy") or ""),
        "no_trade_reason_code": str(commander_context.get("no_trade_reason_code") or ""),
        "strategist_refresh_requested": bool(commander_context.get("strategist_refresh_requested")),
        "strategist_refresh_reason": str(commander_context.get("strategist_refresh_reason") or ""),
        "strategist_refresh_context": dict(commander_context.get("strategist_refresh_context") or {}),
        "open_position_refresh_context": dict(commander_context.get("open_position_refresh_context") or {}),
        "commander_horizon_policy": dict(commander_horizon_policy),
        "horizon_context": dict(horizon_context),
        "memory_packets": dict(commander_context.get("memory_packets") or {}),
        "commander_memory_policy": dict(commander_context.get("commander_memory_policy") or {}),
        "scanner_memory_bias": dict(commander_context.get("scanner_memory_bias") or {}),
        "scanner_memory_bias_summary": dict(commander_context.get("scanner_memory_bias_summary") or {}),
        "monitor_memory_bias": dict(commander_context.get("monitor_memory_bias") or {}),
        "monitor_memory_bias_summary": dict(commander_context.get("monitor_memory_bias_summary") or {}),
        "decision_summary": str(commander_context.get("decision_summary") or ""),
        "source_priority": list(commander_context.get("source_priority") or []),
    }
    strategist_output["commander_invocation_hint"] = str(commander_context.get("strategist_invocation") or "")
    strategist_output["commander_llm_policy"] = str(commander_context.get("llm_policy") or "")
    strategist_output["commander_no_trade_reason_code"] = str(commander_context.get("no_trade_reason_code") or "")
    strategist_output["commander_refresh_requested"] = bool(commander_context.get("strategist_refresh_requested"))
    strategist_output["commander_refresh_reason"] = str(commander_context.get("strategist_refresh_reason") or "")
    strategist_output["commander_refresh_context"] = dict(commander_context.get("strategist_refresh_context") or {})
    strategist_output["commander_open_position_refresh_context"] = dict(
        commander_context.get("open_position_refresh_context") or {}
    )
    strategist_output["commander_horizon_policy"] = dict(commander_horizon_policy)
    strategist_output["horizon_context"] = dict(horizon_context)
    strategist_output["memory_packets"] = dict(commander_context.get("memory_packets") or {})
    strategist_output["commander_memory_policy"] = dict(commander_context.get("commander_memory_policy") or {})
    strategist_output["scanner_memory_bias"] = dict(commander_context.get("scanner_memory_bias") or {})
    strategist_output["scanner_memory_bias_summary"] = dict(commander_context.get("scanner_memory_bias_summary") or {})
    strategist_output["monitor_memory_bias"] = dict(commander_context.get("monitor_memory_bias") or {})
    strategist_output["monitor_memory_bias_summary"] = dict(commander_context.get("monitor_memory_bias_summary") or {})
    strategist_output["read_model_facts_summary"] = dict(read_model_facts_summary)
    strategist_output["selected_symbol_memory"] = dict(
        ((strategic_answers.get("q15_commander_refresh_context") or {}).get("selected_symbol_memory") or {})
    )
    strategist_output["shadow_used"] = bool(commander_context.get("shadow_used"))
    strategist_output["strategist_fallback_used"] = bool(commander_context.get("strategist_fallback_used"))
    strategist_output["llm_frame_status"] = str(llm_meta.get("status") or "disabled")
    strategist_output["llm_frame_applied"] = bool(llm_overrides)
    strategist_output["llm_frame_model"] = str(llm_meta.get("model") or "")
    strategist_output["llm_frame_recovery_method"] = str(llm_meta.get("recovery_method") or "")
    strategist_output["llm_frame_low_confidence"] = bool(llm_meta.get("repair_used"))
    strategist_output["llm_frame_required"] = bool(llm_required)
    strategist_output["llm_frame_strict"] = bool(llm_strict)
    strategist_output["llm_frame_blocked"] = bool(strategist_llm_blocked)
    strategist_output["llm_frame_blocked_reason"] = str(strategist_llm_block_reason or "")
    strategist_output["llm_call_trace"] = dict(llm_meta.get("llm_call_trace") or {})
    strategist_output["runtime_theme_map_keys"] = sorted(list((state.get("theme_map") or {}).keys()))
    strategist_output["runtime_sector_map_keys"] = sorted(list((state.get("sector_map") or {}).keys()))
    for explanation_key in (
        "strategy_thesis",
        "strategy_delta_trace",
        "strategy_refresh_trace",
        "memory_usage_trace",
        "news_usage_trace",
        "scanner_handoff",
        "monitor_handoff",
        "conflict_analysis",
        "trade_permission_frame",
        "responsibility_boundary",
    ):
        if isinstance(ai_overrides.get(explanation_key), dict):
            strategist_output[explanation_key] = dict(ai_overrides.get(explanation_key) or {})
    strategist_output["memory_packet_visibility"] = build_strategist_memory_packet_visibility(
        state=state,
        strategist_output=strategist_output,
    )
    state["strategist_output"] = strategist_output
    state["strategist_blocked"] = bool(strategist_llm_blocked)
    state["strategist_blocked_reason"] = str(strategist_llm_block_reason or "")
    state["strategist_llm"] = {
        "status": str(llm_meta.get("status") or "disabled"),
        "llm_status": str(llm_meta.get("status") or "disabled"),
        "model": str(llm_meta.get("model") or ""),
        "applied": bool(llm_overrides),
        "latency_ms": int(llm_meta.get("latency_ms") or 0),
        "attempts": int(llm_meta.get("attempts") or 1),
        "repair_used": bool(llm_meta.get("repair_used")),
        "low_confidence": bool(llm_meta.get("repair_used")),
        "reason": str(llm_meta.get("reason") or ""),
        "llm_call_trace": dict(llm_meta.get("llm_call_trace") or {}),
        "error": str(llm_meta.get("reason") or ""),
        "recovery_method": str(llm_meta.get("recovery_method") or ""),
        "blocked": bool(strategist_llm_blocked),
        "blocked_reason": str(strategist_llm_block_reason or ""),
        "prompt_ref": str(llm_meta.get("prompt_ref") or ""),
        "response_ref": str(llm_meta.get("response_ref") or ""),
        "prompt_hash": str(llm_meta.get("prompt_hash") or ""),
        "response_hash": str(llm_meta.get("response_hash") or ""),
        "llm_stage_component": str(llm_meta.get("llm_stage_component") or ""),
        "llm_stage_index": int(llm_meta.get("llm_stage_index") or 0),
        "llm_stage_name": str(llm_meta.get("llm_stage_name") or ""),
        "llm_call_kind": str(llm_meta.get("llm_call_kind") or ""),
        "quant_context": dict(llm_meta.get("quant_context") or {}),
        "stage_prompt_ref": str(llm_meta.get("stage_prompt_ref") or ""),
        "stage_response_ref": str(llm_meta.get("stage_response_ref") or ""),
        "stage_meta_ref": str(llm_meta.get("stage_meta_ref") or ""),
        "llm_stage_manifest_ref": str(llm_meta.get("llm_stage_manifest_ref") or ""),
        "llm_execution_profile_name": str(llm_meta.get("llm_execution_profile_name") or ""),
        "llm_execution_profile_source": str(llm_meta.get("llm_execution_profile_source") or ""),
        "llm_execution_effective_config": dict(llm_meta.get("llm_execution_effective_config") or {}),
    }
    strategist_policy_resolution = build_strategist_policy_resolution_surface(
        strategist_output=strategist_output,
        strategist_llm=state.get("strategist_llm"),
        commander_context=commander_context,
    )
    strategist_output["policy_resolution"] = dict(strategist_policy_resolution)
    state["strategist_output"] = strategist_output
    state["strategist_policy_resolution"] = dict(strategist_policy_resolution)
    ranked_market_news = _rank_news_evidence_rows(
        market_news_items_by_target,
        market_news_signal_map,
        used_targets=list(news_query_targets),
        scope="market",
        max_rows=6,
    )
    ranked_candidate_news = _rank_news_evidence_rows(
        news_items_by_symbol,
        news_signal_map,
        used_targets=list(state.get("candidate_symbols") or []),
        scope="candidate",
        max_rows=6,
    )
    reason_chain: List[str] = []
    if str(market_regime or "").strip():
        reason_chain.append(f"Market regime classified as {market_regime}.")
    if str(playbook or "").strip():
        reason_chain.append(f"Playbook set to {playbook}.")
    if list(themes):
        reason_chain.append(f"Themes prioritized: {', '.join(list(themes)[:4])}.")
    if list(avoid_themes):
        reason_chain.append(f"Avoid themes: {', '.join(list(avoid_themes)[:4])}.")
    if str(monitor_guidance or "").strip():
        reason_chain.append(f"Monitor guidance set to {monitor_guidance}.")
    if str(news_query_reasoning or "").strip():
        reason_chain.append(f"News query reasoning: {news_query_reasoning}.")
    if bool(macro_stress_overlay.get("active")) or list(macro_stress_overlay.get("stress_flags") or []):
        reason_chain.append(
            "Macro stress overlay active: "
            + ", ".join([str(x or "") for x in list(macro_stress_overlay.get("stress_flags") or []) if str(x or "").strip()] or ["elevated_stress"])
            + "."
        )

    _emit_strategist_event(
        state,
        name="market_context_snapshot",
        payload={
            "market_structure": str(market_structure or ""),
            "market_context_inputs": dict(market_context_inputs),
            "regime_factors": dict(regime_factors),
            "global_signal": {
                "score": _round_optional(global_signal.get("score"), 4),
                "status": str(global_signal.get("status") or ""),
                "source": str(global_signal.get("source") or ""),
                "index_moves": dict(global_signal.get("index_moves") or {}),
                "korea_indices": dict(global_signal.get("korea_indices") or {}),
                "macro_moves": dict(global_signal.get("macro_moves") or {}),
                "fear_index": dict(global_signal.get("fear_index") or {}),
            },
            "macro_stress_overlay": dict(macro_stress_overlay),
            "candidate_symbols_hint": list(state.get("candidate_symbols") or [])[:8],
        },
    )
    global_sentiment_breakdown_payload = _global_sentiment_breakdown_payload(global_signal)
    state["strategist_global_sentiment_breakdown"] = dict(global_sentiment_breakdown_payload)
    _emit_strategist_event(
        state,
        name="global_sentiment_breakdown",
        payload=global_sentiment_breakdown_payload,
    )
    news_evidence_ranked_payload = {
        "news_query_targets": list(news_query_targets),
        "candidate_news_ranked": ranked_candidate_news,
        "market_news_ranked": ranked_market_news,
        "candidate_news_context": dict(candidate_news_ctx),
        "market_news_context": dict(market_news_ctx),
        "news_context": dict(news_ctx),
    }
    state["strategist_news_evidence_ranked"] = dict(news_evidence_ranked_payload)
    state["strategist_candidate_symbols_hint"] = list(state.get("candidate_symbols") or [])[:10]
    strategist_explanation_fields = build_strategist_explanation_fields(
        strategist_output=strategist_output,
        state=state,
        news_evidence_ranked=news_evidence_ranked_payload,
    )
    strategist_output.update(strategist_explanation_fields)
    if isinstance(llm_meta.get("quant_context"), dict) and llm_meta.get("quant_context"):
        strategist_output["quant_context"] = dict(llm_meta.get("quant_context") or {})
        strategist_output["strategy_refresh_trace"] = _attach_quant_context_to_strategy_refresh_trace(
            strategist_output.get("strategy_refresh_trace"),
            llm_meta.get("quant_context"),
        )
    state["strategist_output"] = strategist_output
    _emit_strategist_event(
        state,
        name="news_evidence_ranked",
        payload=news_evidence_ranked_payload,
    )
    decision_frame_payload = {
        "market_regime": market_regime,
        "market_sentiment": market_sentiment,
        "playbook": playbook,
        "themes": list(themes),
        "avoid_themes": list(avoid_themes),
        "scanner_bias": scanner_bias,
        "scanner_priority": list(scanner_priority),
        "scanner_source_policy": dict(scanner_source_policy),
        "trade_aggressiveness": trade_aggressiveness,
        "risk_tone": risk_tone,
        "monitor_guidance": monitor_guidance,
        "report_focus": list(report_focus),
        "strategy_memory": {
            "status": str(strategy_memory_advisory.get("status") or ""),
            "best_playbooks": list(strategy_memory_advisory.get("best_playbooks") or [])[:3],
            "worst_playbooks": list(strategy_memory_advisory.get("worst_playbooks") or [])[:3],
            "recent_failures": list(strategy_memory_advisory.get("recent_failures") or [])[:3],
            "recent_success_patterns": list(strategy_memory_advisory.get("recent_success_patterns") or [])[:3],
            "recent_playbook_performance": dict(strategy_memory_advisory.get("playbook_performance_snapshot") or {}),
        },
        "reporter_feedback_packet": {
            "available": bool(reporter_feedback_packet.get("available")),
            "status": str(reporter_feedback_packet.get("status") or ""),
            "reporter_feedback_mode": str(reporter_feedback_packet.get("reporter_feedback_mode") or "auto"),
            "reporter_feedback_mode_source": str(reporter_feedback_packet.get("reporter_feedback_mode_source") or "default_auto"),
            "consumed": bool(reporter_feedback_packet.get("consumed")),
            "feedback_gate_reason": str(reporter_feedback_packet.get("feedback_gate_reason") or ""),
            "confidence": str(reporter_feedback_packet.get("confidence") or "none"),
            "insight_summary": str(reporter_feedback_packet.get("insight_summary") or ""),
            "recommendation": list(reporter_feedback_packet.get("recommendation") or [])[:3],
            "route_analysis": dict((reporter_feedback_packet.get("route_analysis") or {})),
        },
        "reason_chain": reason_chain,
        "strategy_policy_summary": {
            "market_policy": dict(strategy_policy.get("market_policy") or {}),
            "scanner_policy": {
                "candidate_sources": dict((strategy_policy.get("scanner_policy") or {}).get("candidate_sources") or {}),
                "filters": dict((strategy_policy.get("scanner_policy") or {}).get("filters") or {}),
            },
            "monitor_policy": dict(strategy_policy.get("monitor_policy") or {}),
            "commander_horizon_policy": dict(commander_horizon_policy),
            "horizon_context": dict(horizon_context),
        },
        "strategy_thesis": dict(strategist_output.get("strategy_thesis") or {}),
        "strategy_refresh_trace": dict(strategist_output.get("strategy_refresh_trace") or {}),
        "memory_usage_trace": dict(strategist_output.get("memory_usage_trace") or {}),
        "news_usage_trace": dict(strategist_output.get("news_usage_trace") or {}),
        "theme_strength_packet": {
            "source": str(theme_strength_packet.get("source") or ""),
            "status": str(theme_strength_packet.get("status") or ""),
            "reason": str(theme_strength_packet.get("reason") or ""),
            "top_themes": list(theme_strength_packet.get("top_themes") or [])[:5],
            "theme_scores": dict(theme_strength_packet.get("theme_scores") or {}),
        },
        "scanner_handoff": dict(strategist_output.get("scanner_handoff") or {}),
        "monitor_handoff": dict(strategist_output.get("monitor_handoff") or {}),
        "conflict_analysis": dict(strategist_output.get("conflict_analysis") or {}),
        "trade_permission_frame": dict(strategist_output.get("trade_permission_frame") or {}),
        "responsibility_boundary": dict(strategist_output.get("responsibility_boundary") or {}),
    }
    state["strategist_decision_frame"] = dict(decision_frame_payload)
    _emit_strategist_event(
        state,
        name="decision_frame",
        payload=decision_frame_payload,
    )
    if llm_required:
        _emit_strategist_event(
            state,
            name="llm_response_saved",
            payload={
                "status": str(llm_meta.get("status") or "disabled"),
                "model": str(llm_meta.get("model") or ""),
                "attempts": int(llm_meta.get("attempts") or 1),
                "repair_used": bool(llm_meta.get("repair_used")),
                "blocked": bool(strategist_llm_blocked),
                "blocked_reason": str(strategist_llm_block_reason or ""),
                "llm_response_artifact": {
                    "component": "strategist",
                    "evidence_log_path": str(Path(os.getenv("EVIDENCE_LEDGER_PATH", "data/evidence_ledger/events.jsonl"))),
                    "prompt_stage": "theme_selection",
                    "response_stage": "theme_selection_repair" if bool(llm_meta.get("repair_used")) else "theme_selection",
                    "prompt_ref": str(llm_meta.get("prompt_ref") or ""),
                    "response_ref": str(llm_meta.get("response_ref") or ""),
                    "prompt_hash": str(llm_meta.get("prompt_hash") or ""),
                    "response_hash": str(llm_meta.get("response_hash") or ""),
                },
            },
            level="warning" if strategist_llm_blocked else "info",
        )
    _emit_strategist_event(
        state,
        name="policy_resolution",
        payload=dict(strategist_policy_resolution),
        level="warning" if bool(strategist_policy_resolution.get("fallback_used")) else "info",
    )
    _log_strategist_summary(
        state,
        {
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "themes": list(themes),
            "avoid_themes": list(avoid_themes),
            "playbook": playbook,
            "scanner_bias": scanner_bias,
            "scanner_priority": list(scanner_priority),
            "scanner_source_policy": dict(scanner_source_policy),
            "trade_aggressiveness": trade_aggressiveness,
            "risk_tone": risk_tone,
            "monitor_guidance": monitor_guidance,
            "candidate_count": len(list(state["candidate_symbols"])),
            "regime_score": float(regime_score),
            "sentiment_score": float(sentiment_score),
            "report_focus": list(report_focus)[:3],
            "macro_stress_overlay": dict(macro_stress_overlay),
            "feedback_window_size": int(recent_strategy_feedback.get("feedback_window_size") or 0),
            "top_recent_strengths": list(recent_strategy_feedback.get("top_recent_strengths") or [])[:3],
            "top_recent_weaknesses": list(recent_strategy_feedback.get("top_recent_weaknesses") or [])[:3],
            "reporter_feedback_available": bool(reporter_feedback_packet.get("available")),
            "reporter_feedback_packet_available": bool(reporter_feedback_packet.get("source_available")),
            "reporter_feedback_status": str(reporter_feedback_packet.get("status") or ""),
            "reporter_feedback_mode": str(reporter_feedback_packet.get("reporter_feedback_mode") or "auto"),
            "reporter_feedback_mode_source": str(reporter_feedback_packet.get("reporter_feedback_mode_source") or "default_auto"),
            "reporter_feedback_gate_reason": str(reporter_feedback_packet.get("feedback_gate_reason") or ""),
            "reporter_feedback_consumed": bool(reporter_feedback_packet.get("consumed")),
            "reporter_feedback_confidence": str(reporter_feedback_packet.get("confidence") or "none"),
            "strategy_memory_status": str(strategy_memory_advisory.get("status") or ""),
            "best_playbooks": list(strategy_memory_advisory.get("best_playbooks") or [])[:3],
            "worst_playbooks": list(strategy_memory_advisory.get("worst_playbooks") or [])[:3],
            "recent_failures": list(strategy_memory_advisory.get("recent_failures") or [])[:3],
            "recent_success_patterns": list(strategy_memory_advisory.get("recent_success_patterns") or [])[:3],
            "recent_playbook_performance": dict(strategy_memory_advisory.get("playbook_performance_snapshot") or {}),
            "news_query_targets": list(news_query_targets)[:6],
            "news_query_reasoning": news_query_reasoning,
            "memory_packet_visibility": dict(strategist_output.get("memory_packet_visibility") or {}),
            "llm_frame_status": str(llm_meta.get("status") or "disabled"),
            "llm_frame_applied": bool(llm_overrides),
            "llm_frame_model": str(llm_meta.get("model") or ""),
            "llm_frame_recovery_method": str(llm_meta.get("recovery_method") or ""),
            "llm_frame_low_confidence": bool(llm_meta.get("repair_used")),
            "llm_frame_blocked": bool(strategist_llm_blocked),
            "llm_frame_blocked_reason": str(strategist_llm_block_reason or ""),
            "strategy_generation_mode": str(strategist_policy_resolution.get("strategy_generation_mode") or ""),
            "fallback_used": bool(strategist_policy_resolution.get("fallback_used")),
            "fallback_source": str(strategist_policy_resolution.get("fallback_source") or ""),
            "effective_policy_source": str(strategist_policy_resolution.get("effective_policy_source") or ""),
        },
    )
    append_decision_trace(
        state,
        agent="strategist",
        event="strategic_frame",
        payload={
            "market_regime": market_regime,
            "market_sentiment": market_sentiment,
            "themes": list(themes)[:5],
            "avoid_themes": list(avoid_themes)[:5],
            "playbook": playbook,
            "scanner_bias": scanner_bias,
            "scanner_priority": list(scanner_priority)[:5],
            "scanner_source_policy": dict(scanner_source_policy),
            "trade_aggressiveness": trade_aggressiveness,
            "risk_tone": risk_tone,
            "monitor_guidance": monitor_guidance,
            "report_focus": list(report_focus)[:5],
            "macro_stress_overlay": dict(macro_stress_overlay),
            "feedback_window_size": int(recent_strategy_feedback.get("feedback_window_size") or 0),
            "top_recent_strengths": list(recent_strategy_feedback.get("top_recent_strengths") or [])[:3],
            "top_recent_weaknesses": list(recent_strategy_feedback.get("top_recent_weaknesses") or [])[:3],
            "recent_reporter_summary": list(recent_strategy_feedback.get("recent_reporter_summary") or [])[:2],
            "reporter_feedback_available": bool(reporter_feedback_packet.get("available")),
            "reporter_feedback_packet_available": bool(reporter_feedback_packet.get("source_available")),
            "reporter_feedback_status": str(reporter_feedback_packet.get("status") or ""),
            "reporter_feedback_mode": str(reporter_feedback_packet.get("reporter_feedback_mode") or "auto"),
            "reporter_feedback_mode_source": str(reporter_feedback_packet.get("reporter_feedback_mode_source") or "default_auto"),
            "reporter_feedback_gate_reason": str(reporter_feedback_packet.get("feedback_gate_reason") or ""),
            "reporter_feedback_consumed": bool(reporter_feedback_packet.get("consumed")),
            "reporter_feedback_confidence": str(reporter_feedback_packet.get("confidence") or "none"),
            "reporter_feedback_insight_summary": str(reporter_feedback_packet.get("insight_summary") or ""),
            "strategy_memory_status": str(strategy_memory_advisory.get("status") or ""),
            "best_playbooks": list(strategy_memory_advisory.get("best_playbooks") or [])[:3],
            "worst_playbooks": list(strategy_memory_advisory.get("worst_playbooks") or [])[:3],
            "recent_failures": list(strategy_memory_advisory.get("recent_failures") or [])[:3],
            "recent_success_patterns": list(strategy_memory_advisory.get("recent_success_patterns") or [])[:3],
            "recent_playbook_performance": dict(strategy_memory_advisory.get("playbook_performance_snapshot") or {}),
            "news_query_targets": list(news_query_targets)[:6],
            "news_query_reasoning": news_query_reasoning,
            "memory_packet_visibility": dict(strategist_output.get("memory_packet_visibility") or {}),
            "regime_score": float(regime_score),
            "sentiment_score": float(sentiment_score),
            "key_events": list(key_events)[:3],
            "llm_frame_status": str(llm_meta.get("status") or "disabled"),
            "llm_frame_applied": bool(llm_overrides),
            "llm_frame_model": str(llm_meta.get("model") or ""),
            "llm_frame_low_confidence": bool(llm_meta.get("repair_used")),
        },
    )
    try:
        record_decision_bridge(
            run_id=str(state.get("run_id") or "strategist-unknown"),
            agent="strategist",
            stage="decision_bridge",
            parsed_output={
                "market_regime": market_regime,
                "market_sentiment": market_sentiment,
                "themes": list(themes),
                "avoid_themes": list(avoid_themes),
                "playbook": playbook,
                "scanner_bias": scanner_bias,
                "scanner_priority": list(scanner_priority),
                "scanner_source_policy": dict(scanner_source_policy),
                "trade_aggressiveness": trade_aggressiveness,
                "risk_tone": risk_tone,
                "monitor_guidance": monitor_guidance,
                "report_focus": list(report_focus),
                "macro_stress_overlay": dict(macro_stress_overlay),
                "recent_strategy_feedback": {
                    "feedback_window_size": int(recent_strategy_feedback.get("feedback_window_size") or 0),
                    "top_recent_strengths": list(recent_strategy_feedback.get("top_recent_strengths") or [])[:3],
                    "top_recent_weaknesses": list(recent_strategy_feedback.get("top_recent_weaknesses") or [])[:3],
                },
                "reporter_feedback_packet": {
                    "available": bool(reporter_feedback_packet.get("available")),
                    "status": str(reporter_feedback_packet.get("status") or ""),
                    "reporter_feedback_mode": str(reporter_feedback_packet.get("reporter_feedback_mode") or "auto"),
                    "reporter_feedback_mode_source": str(reporter_feedback_packet.get("reporter_feedback_mode_source") or "default_auto"),
                    "consumed": bool(reporter_feedback_packet.get("consumed")),
                    "feedback_gate_reason": str(reporter_feedback_packet.get("feedback_gate_reason") or ""),
                    "confidence": str(reporter_feedback_packet.get("confidence") or "none"),
                    "insight_summary": str(reporter_feedback_packet.get("insight_summary") or ""),
                    "recommendation": list(reporter_feedback_packet.get("recommendation") or [])[:3],
                    "route_analysis": dict((reporter_feedback_packet.get("route_analysis") or {})),
                },
                "strategy_memory": {
                    "status": str(strategy_memory_advisory.get("status") or ""),
                    "best_playbooks": list(strategy_memory_advisory.get("best_playbooks") or [])[:3],
                    "worst_playbooks": list(strategy_memory_advisory.get("worst_playbooks") or [])[:3],
                    "recent_failures": list(strategy_memory_advisory.get("recent_failures") or [])[:3],
                    "recent_success_patterns": list(strategy_memory_advisory.get("recent_success_patterns") or [])[:3],
                    "recent_playbook_performance": dict(strategy_memory_advisory.get("playbook_performance_snapshot") or {}),
                },
                "memory_packet_visibility": dict(strategist_output.get("memory_packet_visibility") or {}),
                "news_query_targets": list(news_query_targets),
                "news_query_reasoning": news_query_reasoning,
                "candidate_symbols": list(state.get("candidate_symbols") or []),
            },
            decision_link={
                "decision_chain": {
                    "theme": (list(themes)[0] if list(themes) else ""),
                    "candidate_symbols": list(state.get("candidate_symbols") or []),
                }
            },
        )
    except Exception:
        pass
    try:
        write_strategist_artifact(state)
    except Exception:
        pass
    return state
