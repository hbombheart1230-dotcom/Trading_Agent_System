from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from libs.llm.json_response import parse_llm_json_response, required_key_metadata
from libs.llm.model_names import normalize_openrouter_model_name
from libs.llm.llm_router import LLMRouter
from libs.reporting.llm_artifacts import build_llm_response_artifact, classify_llm_exception, make_attempt

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: Any, *, max_len: int = 400) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _listify(values: Any, *, max_items: int = 6, max_len: int = 240) -> List[str]:
    out: List[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        text = _clip(value, max_len=max_len)
        if text:
            out.append(text)
        if len(out) >= max_items:
            break
    return out


def _dedupe_list(values: List[str], *, max_items: int = 12, max_len: int = 260) -> List[str]:
    out: List[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clip(value, max_len=max_len)
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
        if len(out) >= max_items:
            break
    return out


def _compact_named_rows(values: Any, *, max_items: int = 3) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    out: List[Dict[str, Any]] = []
    for value in values:
        if len(out) >= max(1, int(max_items)):
            break
        if not isinstance(value, dict):
            continue
        row = {
            "rank": value.get("rank"),
            "symbol": _clip(value.get("symbol"), max_len=24),
            "score_total": value.get("score_total"),
            "risk_score": value.get("risk_score"),
            "confidence": value.get("confidence"),
            "why": _clip(value.get("why"), max_len=180),
        }
        row = {key: item for key, item in row.items() if item not in ("", None, [])}
        if row.get("symbol"):
            out.append(row)
    return out


def _compact_scalar_dict(values: Any, *, max_items: int = 8, max_len: int = 160) -> Dict[str, Any]:
    if not isinstance(values, dict):
        return {}
    out: Dict[str, Any] = {}
    for key, value in values.items():
        if len(out) >= max(1, int(max_items)):
            break
        if isinstance(value, (int, float, bool)) or value is None:
            out[str(key)] = value
            continue
        text = _clip(value, max_len=max_len)
        if text:
            out[str(key)] = text
    return out


def _fmt_pct(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number * 100.0:.2f}%"


def _fmt_price(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "-"
    return f"{number:.2f}"


def _is_low_information_bullet(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return True
    if text in {"hold", "wait", "buy", "sell", "noop", "monitor", "monitoring"}:
        return True
    if len(text) <= 12 and re.fullmatch(r"[a-z_\- ]+", text):
        return True
    return False


def _count_hangul(text: Any) -> int:
    raw = str(text or "")
    return sum(1 for ch in raw if "\uac00" <= ch <= "\ud7a3")


def _count_latin(text: Any) -> int:
    raw = str(text or "")
    return sum(1 for ch in raw if ("a" <= ch.lower() <= "z"))


def _count_forbidden_cjk_or_japanese(text: Any) -> int:
    raw = str(text or "")
    # Korean-only policy for human-readable sentences.
    return len(re.findall(r"[\u3040-\u30ff\u4e00-\u9fff]", raw))


AI_TRADE_REPORT_REQUIRED_KEYS = [
    "executive_summary",
    "market_context_at_entry",
    "why_this_symbol_was_chosen",
    "entry_decision",
    "holding_monitoring_story",
    "exit_decision",
    "execution_quality",
    "scanner_filters",
    "guard_approval_result",
    "reporter_evaluation",
    "errors_weaknesses_improvement_points",
    "final_operator_conclusion",
]

AI_TRADE_REPORT_KOREAN_RULES = (
    "사람이 읽는 모든 값은 반드시 한국어로 작성해야 합니다. "
    "All human-readable sentences must be Korean. "
    "Do not use Japanese or Chinese sentences. "
    "Allowed unchanged tokens: symbol code, ISO timestamp, BUY/SELL/HOLD/WAIT, VIX, "
    "top_value/top_volume/sector_theme, not_captured."
)

_FORBIDDEN_CJK_OR_JP_RE = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")


def _sanitize_forbidden_scripts_text(text: Any) -> str:
    raw = _clip(text, max_len=2000).strip()
    if not raw:
        return ""
    replacement_pairs = (
        ("生命周期", "생명주기"),
        ("缺失", "누락"),
        ("不足", "부족"),
        ("薄薄", "부족"),
        ("未完了", "미완료"),
        ("还未", "아직"),
        ("故事", "스토리"),
    )
    normalized = raw
    for src, dst in replacement_pairs:
        normalized = normalized.replace(src, dst)
    cleaned = _FORBIDDEN_CJK_OR_JP_RE.sub("", normalized)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned:
        return cleaned
    return "데이터 부족으로 보수적으로 정리했습니다."


def _sanitize_report_language_fields(value: Any) -> Any:
    if isinstance(value, str):
        return _sanitize_forbidden_scripts_text(value)
    if isinstance(value, list):
        return [_sanitize_report_language_fields(item) for item in value]
    if isinstance(value, dict):
        return {key: _sanitize_report_language_fields(item) for key, item in value.items()}
    return value


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.getenv(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int_with_fallback(*names: str, default: int) -> int:
    for name in names:
        raw = str(os.getenv(name, "") or "").strip()
        if not raw:
            continue
        try:
            value = int(float(raw))
        except Exception:
            continue
        if value > 0:
            return value
    return int(default)


def _normalize_section(section: Any, *, default_summary: str = "", bullet_key: str = "bullets") -> Dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    out = {
        "summary": _clip(data.get("summary"), max_len=600) or _clip(default_summary, max_len=600),
        bullet_key: _listify(data.get(bullet_key), max_items=8, max_len=260),
    }
    for key in (
        "headline",
        "action",
        "confidence",
        "status",
        "grade",
        "current_action",
        "symbol",
        "story_type",
    ):
        value = _clip(data.get(key), max_len=120)
        if value:
            out[key] = value
    return out


def _actual_lifecycle_action(story_input: Dict[str, Any]) -> str:
    status_text = str(story_input.get("status") or "").strip().lower()
    exit_summary = story_input.get("exit_summary") if isinstance(story_input.get("exit_summary"), dict) else {}
    entry_summary = story_input.get("entry_summary") if isinstance(story_input.get("entry_summary"), dict) else {}
    operator_conclusion = story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}

    exit_action = _clip(exit_summary.get("action"), max_len=24).upper()
    entry_action = _clip(entry_summary.get("action"), max_len=24).upper()
    requested_action = _clip(story_input.get("action"), max_len=24).upper()
    conclusion_action = _clip(operator_conclusion.get("current_action"), max_len=24).upper()

    if exit_action in {"BUY", "SELL"}:
        return exit_action
    if status_text == "open":
        if conclusion_action in {"HOLD", "WAIT", "BUY"}:
            return conclusion_action
        return "HOLD"
    if requested_action in {"BUY", "SELL"}:
        return requested_action
    if conclusion_action in {"BUY", "SELL", "HOLD", "WAIT"}:
        return conclusion_action
    if entry_action in {"BUY", "SELL"}:
        return entry_action
    return "WAIT"


def _first_nonempty_text(*values: Any, max_len: int = 240) -> str:
    for value in values:
        text = _clip(value, max_len=max_len)
        if text:
            return text
    return ""


def _has_evidence_payload(value: Any) -> bool:
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return bool(str(value or "").strip())


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_action(value: Any) -> str:
    text = _clip(value, max_len=24).upper()
    if text in {"NOOP", "NONE"}:
        return "WAIT"
    return text


def _as_status(value: Any) -> str:
    text = _clip(value, max_len=32).lower()
    if text == "opened":
        return "open"
    if text == "closed_out":
        return "closed"
    return text


def _present_fact(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        text = value.strip()
        return bool(text) and text.lower() != "unavailable"
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def _set_fact_if_missing(
    *,
    resolved: Dict[str, Any],
    data_source: Dict[str, str],
    field: str,
    value: Any,
    source: str,
) -> None:
    if not _present_fact(value):
        return
    if _present_fact(resolved.get(field)):
        if str(resolved.get(field)) != str(value):
            logger.debug(
                "trade_fact_conflict field=%s kept_source=%s kept_value=%r ignored_source=%s ignored_value=%r",
                field,
                data_source.get(field),
                resolved.get(field),
                source,
                value,
            )
        return
    resolved[field] = value
    data_source[field] = source


def _resolve_trade_facts_with_precedence(story_input: Dict[str, Any]) -> Dict[str, Any]:
    lifecycle = _as_dict(story_input.get("trade_lifecycle"))
    lifecycle_summary = _as_dict(story_input.get("lifecycle_summary"))
    lifecycle_bundle = _as_dict(story_input.get("lifecycle_bundle"))
    lifecycle_bundle_outcome = _as_dict(lifecycle_bundle.get("trade_outcome"))
    lifecycle_summary_obj = _as_dict(lifecycle.get("summary"))
    lifecycle_entry = _as_dict(lifecycle.get("entry"))
    lifecycle_exit = _as_dict(lifecycle.get("exit"))

    canonical = _as_dict(story_input.get("canonical_agent_artifacts"))
    canonical_monitor = _as_dict(canonical.get("monitor"))
    entry_summary = _as_dict(story_input.get("entry_summary"))
    hold_summary = _as_dict(story_input.get("holding_summary"))
    exit_summary = _as_dict(story_input.get("exit_summary"))
    exit_monitor_context = _as_dict(exit_summary.get("monitor_context"))
    execution_outcome = _as_dict(story_input.get("execution_outcome_human"))
    monitor_reason = _as_dict(story_input.get("monitor_reason_human"))

    fields = ["action", "status", "holding_duration", "exit_reason", "pnl", "pnl_pct"]
    resolved: Dict[str, Any] = {key: "unavailable" for key in fields}
    data_source: Dict[str, str] = {key: "unavailable" for key in fields}

    # 1) lifecycle / trade_lifecycle.json
    for candidate in (
        _as_action(lifecycle.get("action")),
        _as_action(lifecycle.get("final_action")),
        _as_action(lifecycle_summary_obj.get("action")),
        _as_action(lifecycle_summary_obj.get("final_action")),
        _as_action(lifecycle_entry.get("action")),
        _as_action(lifecycle_exit.get("action")),
        _as_action(lifecycle_summary.get("action")),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="action", value=candidate, source="lifecycle")
    for candidate in (
        _as_status(lifecycle.get("status")),
        _as_status(lifecycle.get("trade_status")),
        _as_status(lifecycle.get("lifecycle_status")),
        _as_status(lifecycle_summary_obj.get("status")),
        _as_status(lifecycle_bundle.get("status")),
        _as_status(story_input.get("trade_lifecycle_status")),
        _as_status(lifecycle_summary.get("status")),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="status", value=candidate, source="lifecycle")
    for candidate in (
        _clip(lifecycle.get("holding_duration"), max_len=80),
        _clip(lifecycle_summary_obj.get("holding_duration"), max_len=80),
        _clip(lifecycle_bundle_outcome.get("holding_time"), max_len=80),
        _clip(lifecycle_summary.get("holding_duration"), max_len=80),
    ):
        _set_fact_if_missing(
            resolved=resolved,
            data_source=data_source,
            field="holding_duration",
            value=candidate,
            source="lifecycle",
        )
    for candidate in (
        _clip(lifecycle.get("exit_reason"), max_len=280),
        _clip(lifecycle_summary_obj.get("exit_reason_human"), max_len=280),
        _clip(lifecycle_summary_obj.get("exit_reason"), max_len=280),
        _clip(lifecycle_bundle_outcome.get("exit_reason"), max_len=280),
        _clip(lifecycle_exit.get("reason_human"), max_len=280),
        _clip(lifecycle_summary.get("exit_reason_human"), max_len=280),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="lifecycle")
    for candidate in (
        lifecycle.get("pnl"),
        lifecycle_summary_obj.get("pnl"),
        lifecycle_bundle_outcome.get("pnl"),
        lifecycle_summary.get("pnl"),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl", value=candidate, source="lifecycle")
    for candidate in (
        lifecycle.get("pnl_pct"),
        lifecycle.get("return_pct"),
        lifecycle_summary_obj.get("pnl_pct"),
        lifecycle_summary_obj.get("return_pct"),
        lifecycle_bundle_outcome.get("return_pct"),
        lifecycle_summary.get("pnl_pct"),
        lifecycle_summary.get("return_pct"),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="lifecycle")

    # 2) canonical monitor decision artifact
    for candidate in (
        _as_action(canonical_monitor.get("decision_action")),
        _as_action(canonical_monitor.get("decision")),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="action", value=candidate, source="monitor")
    for candidate in (
        _clip(canonical_monitor.get("exit_reason"), max_len=280),
        _clip(canonical_monitor.get("primary_reason_text"), max_len=280),
        _clip(canonical_monitor.get("primary_reason_code"), max_len=280),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="monitor")
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="pnl",
        value=canonical_monitor.get("pnl"),
        source="monitor",
    )
    for candidate in (canonical_monitor.get("pnl_pct"), canonical_monitor.get("return_pct")):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="monitor")
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="holding_duration",
        value=_clip(canonical_monitor.get("holding_duration"), max_len=80),
        source="monitor",
    )

    # 3) entry.json / hold.json / exit.json
    for candidate in (
        _as_action(exit_summary.get("action")),
        _as_action(entry_summary.get("action")),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="action", value=candidate, source="trade_artifact")
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="status",
        value=_as_status(story_input.get("status")),
        source="trade_artifact",
    )
    for candidate in (
        _clip(hold_summary.get("holding_duration"), max_len=80),
        _clip(hold_summary.get("holding_time"), max_len=80),
    ):
        _set_fact_if_missing(
            resolved=resolved,
            data_source=data_source,
            field="holding_duration",
            value=candidate,
            source="trade_artifact",
        )
    for candidate in (
        _clip(exit_summary.get("reason_human"), max_len=280),
        _clip(exit_monitor_context.get("exit_reason"), max_len=280),
        _clip(exit_monitor_context.get("reason"), max_len=280),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="exit_reason", value=candidate, source="trade_artifact")
    for candidate in (
        execution_outcome.get("pnl"),
        _as_dict(exit_summary.get("execution_context")).get("pnl"),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl", value=candidate, source="trade_artifact")
    for candidate in (
        execution_outcome.get("pnl_pct"),
        execution_outcome.get("return_pct"),
        _as_dict(exit_summary.get("execution_context")).get("pnl_pct"),
        _as_dict(exit_summary.get("execution_context")).get("return_pct"),
    ):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="trade_artifact")

    # 4) evidence (strategist / scanner)
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="exit_reason",
        value=_clip(_as_dict(story_input.get("monitor_timeline")).get("summary"), max_len=280),
        source="evidence",
    )

    # 5) fallback / inference (last resort only)
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="action",
        value=_as_action(_actual_lifecycle_action(story_input)),
        source="fallback",
    )
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="status",
        value=_as_status(story_input.get("status")),
        source="fallback",
    )
    _set_fact_if_missing(
        resolved=resolved,
        data_source=data_source,
        field="pnl",
        value=monitor_reason.get("pnl"),
        source="fallback",
    )
    for candidate in (monitor_reason.get("pnl_pct"), monitor_reason.get("current_drawdown")):
        _set_fact_if_missing(resolved=resolved, data_source=data_source, field="pnl_pct", value=candidate, source="fallback")

    monitor_decision = {
        "phase": _clip(canonical_monitor.get("decision_phase"), max_len=32) or "unavailable",
        "action": _clip(canonical_monitor.get("decision_action"), max_len=32) or "unavailable",
        "status": _clip(canonical_monitor.get("decision_status"), max_len=32) or "unavailable",
        "reason_code": _clip(
            canonical_monitor.get("primary_reason_text") or canonical_monitor.get("primary_reason_code"),
            max_len=220,
        )
        or "unavailable",
        "thresholds": _as_dict(canonical_monitor.get("threshold_snapshot")),
    }
    return {
        **resolved,
        "data_source": data_source,
        "monitor_decision": monitor_decision,
    }


def _build_shared_summary_seed(story_input: Dict[str, Any]) -> Dict[str, Any]:
    entry_summary = _as_dict(story_input.get("entry_summary"))
    exit_summary = _as_dict(story_input.get("exit_summary"))
    scanner_reason = _as_dict(story_input.get("scanner_reason_human"))
    market_context = _as_dict(story_input.get("market_context_human"))
    monitor_reason = _as_dict(story_input.get("monitor_reason_human"))
    strategist_evidence_trace = _as_dict(story_input.get("strategist_evidence_trace"))
    scanner_selection_trace = _as_dict(story_input.get("scanner_selection_trace"))
    monitor_stop_policy_trace = _as_dict(story_input.get("monitor_stop_policy_trace"))
    monitor_blocker_trace = _as_dict(story_input.get("monitor_blocker_trace"))
    canonical = _as_dict(story_input.get("canonical_agent_artifacts"))
    canonical_commander = _as_dict(canonical.get("commander"))
    canonical_commander_decision = _as_dict(canonical_commander.get("commander_decision"))
    resolved_facts = _resolve_trade_facts_with_precedence(story_input)
    lifecycle_action = _as_action(resolved_facts.get("action")) or "WAIT"
    status_text = _as_status(resolved_facts.get("status")) or "unavailable"
    scanner_evidence_status = (
        "available"
        if (
            _has_evidence_payload(story_input.get("scanner_evidence"))
            or bool(_first_nonempty_text(scanner_reason.get("selected_symbol"), scanner_reason.get("summary"), max_len=200))
            or bool(_listify(scanner_reason.get("bullets"), max_items=1, max_len=120))
        )
        else "unavailable"
    )
    strategist_evidence_status = (
        "available"
        if (
            _has_evidence_payload(story_input.get("strategist_evidence"))
            or bool(_first_nonempty_text(market_context.get("summary"), market_context.get("regime"), max_len=200))
            or bool(_listify(market_context.get("bullets"), max_items=1, max_len=120))
        )
        else "unavailable"
    )
    commander_route = {
        "selected_route": _first_nonempty_text(
            canonical_commander.get("selected_route"),
            canonical_commander.get("final_runtime_path"),
            max_len=120,
        ),
        "reason": _first_nonempty_text(
            canonical_commander.get("route_reason_text"),
            canonical_commander.get("final_reason"),
            max_len=260,
        ),
        "command_intent": _first_nonempty_text(
            canonical_commander_decision.get("command_intent"),
            canonical_commander.get("command_intent"),
            max_len=40,
        ),
        "strategist_invocation": _first_nonempty_text(
            canonical_commander_decision.get("strategist_invocation"),
            canonical_commander.get("strategist_invocation"),
            max_len=40,
        ),
        "llm_policy": _first_nonempty_text(
            canonical_commander_decision.get("llm_policy"),
            canonical_commander.get("llm_invocation_policy"),
            max_len=40,
        ),
        "strategist_cache_used": canonical_commander.get("strategist_cache_used"),
        "strategist_called": canonical_commander.get("strategist_called"),
        "cooldown_applied": canonical_commander.get("cooldown_applied"),
        "applied_policy": _as_dict(canonical_commander.get("applied_policy")),
        "policy_source": _first_nonempty_text(
            canonical_commander.get("policy_source"),
            canonical_commander_decision.get("policy_source"),
            max_len=80,
        ),
        "policy_validation_status": _first_nonempty_text(
            canonical_commander.get("policy_validation_status"),
            canonical_commander_decision.get("policy_validation_status"),
            max_len=80,
        ),
        "policy_fallback_used": canonical_commander.get("policy_fallback_used")
        if canonical_commander.get("policy_fallback_used") is not None
        else canonical_commander_decision.get("policy_fallback_used"),
        "policy_fallback_reason": _first_nonempty_text(
            canonical_commander.get("policy_fallback_reason"),
            canonical_commander_decision.get("policy_fallback_reason"),
            max_len=220,
        ),
        "policy_partial_normalized": canonical_commander.get("policy_partial_normalized")
        if canonical_commander.get("policy_partial_normalized") is not None
        else canonical_commander_decision.get("policy_partial_normalized"),
        "policy_default_filled_fields": _listify(
            canonical_commander.get("policy_default_filled_fields")
            or canonical_commander_decision.get("policy_default_filled_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_missing_fields": _listify(
            canonical_commander.get("policy_validation_missing_fields")
            or canonical_commander_decision.get("policy_validation_missing_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_invalid_fields": _listify(
            canonical_commander.get("policy_validation_invalid_fields")
            or canonical_commander_decision.get("policy_validation_invalid_fields"),
            max_items=12,
            max_len=80,
        ),
        "override_reason": _first_nonempty_text(
            canonical_commander.get("override_reason"),
            canonical_commander_decision.get("override_reason"),
            max_len=160,
        ),
        "applied_policy_source_chain": _listify(
            canonical_commander.get("applied_policy_source_chain")
            or canonical_commander_decision.get("applied_policy_source_chain"),
            max_items=6,
            max_len=80,
        ),
    }
    scanner_reasoning = {
        "playbook": _first_nonempty_text(scanner_reason.get("playbook"), max_len=80),
        "policy_source": _first_nonempty_text(scanner_reason.get("policy_source"), max_len=80),
        "applied_policy_present": bool(scanner_reason.get("applied_policy_present")),
        "monitor_entry_policy_summary": _compact_scalar_dict(
            scanner_reason.get("monitor_entry_policy_summary"),
            max_items=8,
            max_len=120,
        ),
        "scanner_bias_applied": bool(scanner_reason.get("scanner_bias_applied")),
        "scanner_bias_summary": _compact_scalar_dict(
            scanner_reason.get("scanner_bias_summary"),
            max_items=8,
            max_len=120,
        ),
        "candidate_bias_adjustments": [
            {
                "symbol": _clip((row or {}).get("symbol"), max_len=24),
                "bias_adjustment": (row or {}).get("bias_adjustment"),
                "bias_adjustments": _listify(
                    [
                        str((item or {}).get("reason") or "")
                        for item in list((row or {}).get("bias_adjustments") or [])
                        if isinstance(item, dict)
                    ],
                    max_items=4,
                    max_len=120,
                ),
            }
            for row in list(scanner_reason.get("candidate_bias_adjustments") or [])[:5]
            if isinstance(row, dict)
        ],
        "selection_reason_with_bias": _first_nonempty_text(
            scanner_reason.get("selection_reason_with_bias"),
            scanner_reason.get("selection_basis"),
            scanner_reason.get("summary"),
            max_len=320,
        ),
        "selection_trace": {
            "ranked_candidates": [
                {
                    "rank": (row or {}).get("rank"),
                    "symbol": _clip((row or {}).get("symbol"), max_len=24),
                    "score_total": (row or {}).get("score_total"),
                    "risk_score": (row or {}).get("risk_score"),
                    "confidence": (row or {}).get("confidence"),
                }
                for row in list(scanner_selection_trace.get("ranked_candidates") or [])[:5]
                if isinstance(row, dict)
            ],
            "selected_symbol": _first_nonempty_text(
                scanner_selection_trace.get("selected_symbol"),
                scanner_reason.get("selected_symbol"),
                max_len=24,
            ),
            "selected_rank": scanner_selection_trace.get("selected_rank") or scanner_reason.get("selected_rank"),
            "selection_reason": _first_nonempty_text(
                scanner_selection_trace.get("selection_reason"),
                scanner_reason.get("selection_reason"),
                scanner_reason.get("selection_basis"),
                max_len=280,
            ),
            "selected_symbol_score_drivers": _compact_scalar_dict(
                scanner_selection_trace.get("selected_symbol_score_drivers")
                or scanner_reason.get("selected_symbol_score_drivers"),
                max_items=6,
                max_len=120,
            ),
        },
    }
    monitor_policy_ref = _as_dict(monitor_reason.get("policy_ref"))
    monitor_reasoning = {
        "entry_check_summary": _first_nonempty_text(monitor_reason.get("entry_check_summary"), max_len=240),
        "entry_blockers": _listify(monitor_reason.get("entry_blockers"), max_items=6, max_len=120),
        "threshold_shortfalls": _listify(
            monitor_blocker_trace.get("threshold_shortfalls") or monitor_reason.get("threshold_shortfalls"),
            max_items=4,
            max_len=160,
        ),
        "policy_ref": _compact_scalar_dict(monitor_policy_ref, max_items=8, max_len=120),
        "thresholds_guards_used": _compact_scalar_dict(monitor_reason.get("thresholds_guards_used"), max_items=8, max_len=120),
        "received_policy": _compact_scalar_dict(monitor_reason.get("received_policy"), max_items=12, max_len=120),
        "received_policy_source": _first_nonempty_text(monitor_reason.get("received_policy_source"), max_len=80),
        "effective_policy": _compact_scalar_dict(
            monitor_reason.get("effective_policy")
            if isinstance(monitor_reason.get("effective_policy"), dict)
            else (
                monitor_reason.get("applied_policy")
                if isinstance(monitor_reason.get("applied_policy"), dict)
                else monitor_policy_ref.get("effective_policy")
            ),
            max_items=12,
            max_len=120,
        ),
        "effective_policy_source": _first_nonempty_text(
            monitor_reason.get("effective_policy_source"),
            monitor_policy_ref.get("effective_policy_source"),
            max_len=80,
        ),
        "effective_policy_source_chain": _listify(
            monitor_reason.get("effective_policy_source_chain")
            or monitor_policy_ref.get("effective_policy_source_chain"),
            max_items=6,
            max_len=80,
        ),
        "policy_adjustments": _compact_scalar_dict(
            monitor_reason.get("policy_adjustments")
            if isinstance(monitor_reason.get("policy_adjustments"), dict)
            else monitor_policy_ref.get("policy_adjustments"),
            max_items=8,
            max_len=120,
        ),
        "policy_adjustment_summary": _first_nonempty_text(
            monitor_reason.get("policy_adjustment_summary"),
            monitor_policy_ref.get("policy_adjustment_summary"),
            max_len=220,
        ),
        "policy_adjustment_reasoning": _first_nonempty_text(
            monitor_reason.get("policy_adjustment_reasoning"),
            monitor_policy_ref.get("policy_adjustment_reasoning"),
            max_len=260,
        ),
        "effective_policy_deltas": [
            {
                "field": _clip((row or {}).get("field"), max_len=80),
                "from": (row or {}).get("from"),
                "to": (row or {}).get("to"),
            }
            for row in list(
                monitor_reason.get("effective_policy_deltas")
                or monitor_policy_ref.get("effective_policy_deltas")
                or []
            )[:8]
            if isinstance(row, dict)
        ],
        "applied_policy": _compact_scalar_dict(
            monitor_reason.get("applied_policy")
            if isinstance(monitor_reason.get("applied_policy"), dict)
            else monitor_policy_ref.get("applied_policy"),
            max_items=12,
            max_len=120,
        ),
        "policy_source": _first_nonempty_text(
            monitor_reason.get("policy_source"),
            monitor_policy_ref.get("policy_source"),
            max_len=80,
        ),
        "policy_validation_status": _first_nonempty_text(
            monitor_reason.get("policy_validation_status"),
            monitor_policy_ref.get("policy_validation_status"),
            max_len=80,
        ),
        "policy_fallback_used": monitor_reason.get("policy_fallback_used")
        if monitor_reason.get("policy_fallback_used") is not None
        else monitor_policy_ref.get("policy_fallback_used"),
        "policy_fallback_reason": _first_nonempty_text(
            monitor_reason.get("policy_fallback_reason"),
            monitor_policy_ref.get("policy_fallback_reason"),
            max_len=220,
        ),
        "policy_partial_normalized": monitor_reason.get("policy_partial_normalized")
        if monitor_reason.get("policy_partial_normalized") is not None
        else monitor_policy_ref.get("policy_partial_normalized"),
        "policy_default_filled_fields": _listify(
            monitor_reason.get("policy_default_filled_fields")
            or monitor_policy_ref.get("policy_default_filled_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_missing_fields": _listify(
            monitor_reason.get("policy_validation_missing_fields")
            or monitor_policy_ref.get("policy_validation_missing_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_invalid_fields": _listify(
            monitor_reason.get("policy_validation_invalid_fields")
            or monitor_policy_ref.get("policy_validation_invalid_fields"),
            max_items=12,
            max_len=80,
        ),
        "override_reason": _first_nonempty_text(
            monitor_reason.get("override_reason"),
            monitor_policy_ref.get("override_reason"),
            max_len=160,
        ),
        "applied_policy_source_chain": _listify(
            monitor_reason.get("applied_policy_source_chain")
            or monitor_policy_ref.get("applied_policy_source_chain"),
            max_items=6,
            max_len=80,
        ),
        "hard_stop_pct": monitor_reason.get("hard_stop_pct") or monitor_stop_policy_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": monitor_reason.get("adaptive_stop_loss_pct")
        or monitor_stop_policy_trace.get("adaptive_stop_loss_pct"),
        "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct")
        or monitor_stop_policy_trace.get("effective_stop_loss_pct"),
        "trailing_stop_pct": monitor_reason.get("trailing_stop_pct") or monitor_stop_policy_trace.get("trailing_stop_pct"),
        "take_profit_pct": monitor_reason.get("take_profit_pct") or monitor_stop_policy_trace.get("take_profit_pct"),
        "monitor_stop_policy_trace": {
            "hard_stop_pct": monitor_stop_policy_trace.get("hard_stop_pct") or monitor_reason.get("hard_stop_pct"),
            "adaptive_stop_loss_pct": monitor_stop_policy_trace.get("adaptive_stop_loss_pct")
            or monitor_reason.get("adaptive_stop_loss_pct"),
            "effective_stop_loss_pct": monitor_stop_policy_trace.get("effective_stop_loss_pct")
            or monitor_reason.get("effective_stop_loss_pct"),
            "trailing_stop_pct": monitor_stop_policy_trace.get("trailing_stop_pct") or monitor_reason.get("trailing_stop_pct"),
            "take_profit_pct": monitor_stop_policy_trace.get("take_profit_pct") or monitor_reason.get("take_profit_pct"),
            "strategist_baseline_stop_loss_pct": monitor_stop_policy_trace.get("strategist_baseline_stop_loss_pct")
            or monitor_reason.get("strategist_baseline_stop_loss_pct"),
            "strategist_baseline_take_profit_pct": monitor_stop_policy_trace.get("strategist_baseline_take_profit_pct")
            or monitor_reason.get("strategist_baseline_take_profit_pct"),
            "strategist_baseline_trailing_stop_pct": monitor_stop_policy_trace.get("strategist_baseline_trailing_stop_pct")
            or monitor_reason.get("strategist_baseline_trailing_stop_pct"),
        },
        "monitor_blocker_trace": {
            "entry_check_summary": _first_nonempty_text(
                monitor_blocker_trace.get("entry_check_summary"),
                monitor_reason.get("entry_check_summary"),
                max_len=240,
            ),
            "entry_blockers": _listify(
                monitor_blocker_trace.get("entry_blockers") or monitor_reason.get("entry_blockers"),
                max_items=6,
                max_len=120,
            ),
            "threshold_shortfalls": _listify(
                monitor_blocker_trace.get("threshold_shortfalls") or monitor_reason.get("threshold_shortfalls"),
                max_items=4,
                max_len=160,
            ),
        },
    }
    strategist_evidence = {
        "candidate_hints": _listify(
            strategist_evidence_trace.get("candidate_hints")
            or market_context.get("candidate_hints")
            or story_input.get("strategist_candidate_hints"),
            max_items=8,
            max_len=24,
        ),
        "news_query_targets": _listify(
            strategist_evidence_trace.get("news_query_targets")
            or market_context.get("news_query_targets"),
            max_items=8,
            max_len=80,
        ),
        "market_headlines": _listify(
            strategist_evidence_trace.get("market_headlines")
            or market_context.get("market_headlines")
            or story_input.get("strategist_market_headlines"),
            max_items=3,
            max_len=180,
        ),
        "symbol_headlines": _listify(
            strategist_evidence_trace.get("symbol_headlines")
            or market_context.get("symbol_headlines")
            or story_input.get("strategist_symbol_headlines"),
            max_items=3,
            max_len=180,
        ),
        "global_sentiment_signal": _compact_scalar_dict(
            strategist_evidence_trace.get("global_sentiment_signal") or market_context.get("global_sentiment_signal"),
            max_items=8,
            max_len=120,
        ),
        "fear_index": _compact_scalar_dict(
            strategist_evidence_trace.get("fear_index") or market_context.get("fear_index"),
            max_items=8,
            max_len=120,
        ),
        "key_events": _listify(
            strategist_evidence_trace.get("key_events")
            or market_context.get("key_events")
            or market_context.get("key_events_hint"),
            max_items=6,
            max_len=180,
        ),
    }
    return {
        "symbol": _clip(story_input.get("symbol"), max_len=32) or "unknown",
        "trade_id": _clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120),
        "lifecycle_action": lifecycle_action,
        "lifecycle_status": status_text,
        "entry_exists": bool(_has_evidence_payload(entry_summary)),
        "exit_exists": bool(_has_evidence_payload(exit_summary)),
        "holding_duration": _clip(resolved_facts.get("holding_duration"), max_len=80) or "unavailable",
        "exit_reason": _clip(resolved_facts.get("exit_reason"), max_len=280) or "unavailable",
        "pnl": resolved_facts.get("pnl"),
        "pnl_pct": resolved_facts.get("pnl_pct"),
        "monitor_decision": dict(resolved_facts.get("monitor_decision") or {}),
        "resolved_trade_facts": {
            "action": lifecycle_action,
            "status": status_text,
            "holding_duration": _clip(resolved_facts.get("holding_duration"), max_len=80) or "unavailable",
            "exit_reason": _clip(resolved_facts.get("exit_reason"), max_len=280) or "unavailable",
            "pnl": resolved_facts.get("pnl", "unavailable"),
            "pnl_pct": resolved_facts.get("pnl_pct", "unavailable"),
            "data_source": dict(resolved_facts.get("data_source") or {}),
        },
        "scanner_evidence_status": scanner_evidence_status,
        "strategist_evidence_status": strategist_evidence_status,
        "commander_route": commander_route,
        "strategist_evidence": strategist_evidence,
        "scanner_reasoning": scanner_reasoning,
        "monitor_reasoning": monitor_reasoning,
    }


def resolve_shared_trade_facts(story_input: Dict[str, Any]) -> Dict[str, Any]:
    shared_seed = _build_shared_summary_seed(story_input)
    resolved = _as_dict(shared_seed.get("resolved_trade_facts"))
    data_source = _as_dict(resolved.get("data_source"))
    return {
        "action": _as_action(resolved.get("action")) or "unavailable",
        "status": _as_status(resolved.get("status")) or "unavailable",
        "holding_duration": _clip(resolved.get("holding_duration"), max_len=80) or "unavailable",
        "exit_reason": _clip(resolved.get("exit_reason"), max_len=280) or "unavailable",
        "pnl": resolved.get("pnl", "unavailable"),
        "pnl_pct": resolved.get("pnl_pct", "unavailable"),
        "data_source": data_source,
        "monitor_decision": _as_dict(shared_seed.get("monitor_decision")),
    }


def _normalize_trade_report_output(story_input: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(report or {})
    shared_seed = _build_shared_summary_seed(story_input)
    action = _clip(shared_seed.get("lifecycle_action"), max_len=24) or _actual_lifecycle_action(story_input)
    symbol = _clip(shared_seed.get("symbol"), max_len=32) or _clip(out.get("symbol"), max_len=32) or "unknown"
    status_text = _clip(shared_seed.get("lifecycle_status"), max_len=32) or _clip(out.get("status"), max_len=32) or "closed"
    story_type = _clip(story_input.get("story_type"), max_len=40) or _clip(out.get("story_type"), max_len=40)
    execution_mode = _clip(story_input.get("execution_mode_label"), max_len=80) or _clip(out.get("execution_mode_label"), max_len=80)

    out["symbol"] = symbol
    out["action"] = action
    out["status"] = status_text
    if story_type:
        out["story_type"] = story_type
    if execution_mode:
        out["execution_mode_label"] = execution_mode

    executive = out.get("executive_summary") if isinstance(out.get("executive_summary"), dict) else {}
    executive_summary = dict(executive)
    executive_summary["action"] = action
    executive_summary["symbol"] = symbol
    if not str(executive_summary.get("headline") or "").strip():
        executive_summary["headline"] = f"{action} {symbol}"
    out["executive_summary"] = executive_summary
    out["report_generation"] = dict(out.get("generation") or {})

    final_conclusion = out.get("final_operator_conclusion") if isinstance(out.get("final_operator_conclusion"), dict) else {}
    normalized_conclusion = dict(final_conclusion)
    normalized_conclusion["current_action"] = "HOLD" if status_text.lower() == "open" and action == "BUY" else action
    out["final_operator_conclusion"] = normalized_conclusion
    if "section_provenance" not in out:
        out["section_provenance"] = _report_section_provenance(story_input)
    if "evidence_source" not in out:
        out["evidence_source"] = str(story_input.get("evidence_source") or "fallback")
    section_provenance = out.get("section_provenance") if isinstance(out.get("section_provenance"), dict) else {}
    for section_key in (
        "executive_summary",
        "market_context_at_entry",
        "why_this_symbol_was_chosen",
        "entry_decision",
        "holding_monitoring_story",
        "exit_decision",
        "execution_quality",
        "scanner_filters",
        "guard_approval_result",
        "reporter_evaluation",
        "errors_weaknesses_improvement_points",
        "final_operator_conclusion",
    ):
        section = out.get(section_key) if isinstance(out.get(section_key), dict) else {}
        source_entry = (
            _normalize_provenance_entry(section_provenance.get(section_key))
            if isinstance(section_provenance.get(section_key), dict)
            else _normalize_provenance_entry({})
        )
        section["evidence_source"] = str(source_entry.get("evidence_source") or "fallback")
        section["confidence"] = str(source_entry.get("confidence") or "low")
        section["completeness"] = float(source_entry.get("completeness") or 0.0)
        out[section_key] = _operatorize_report_section(section)
    if isinstance(out.get("market_context"), dict):
        out["market_context"] = dict(out.get("market_context_at_entry") or {})
    if isinstance(out.get("why_this_symbol"), dict):
        out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    if isinstance(out.get("scanner_logic_and_filters"), dict):
        out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    if isinstance(out.get("monitor_trigger_reasoning"), dict):
        out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    if isinstance(out.get("execution_result"), dict):
        out["execution_result"] = dict(out.get("execution_quality") or {})
    if shared_seed.get("scanner_evidence_status") == "unavailable":
        scanner_section = out.get("why_this_symbol_was_chosen") if isinstance(out.get("why_this_symbol_was_chosen"), dict) else {}
        current_summary = _clip(scanner_section.get("summary"), max_len=600)
        if not current_summary or _is_low_information_bullet(current_summary):
            scanner_section["summary"] = "Scanner evidence unavailable for this trade. Selection confidence is constrained."
        out["why_this_symbol_was_chosen"] = scanner_section
    if shared_seed.get("strategist_evidence_status") == "unavailable":
        market_section = out.get("market_context_at_entry") if isinstance(out.get("market_context_at_entry"), dict) else {}
        current_summary = _clip(market_section.get("summary"), max_len=600)
        if not current_summary or _is_low_information_bullet(current_summary):
            market_section["summary"] = "Strategist evidence unavailable for this trade. Market-context detail is limited."
        out["market_context_at_entry"] = market_section
    out["shared_facts"] = {
        "symbol": symbol,
        "trade_id": _clip(shared_seed.get("trade_id"), max_len=120),
        "action": action,
        "status": status_text,
        "holding_duration": _clip(shared_seed.get("holding_duration"), max_len=80) or "unavailable",
        "exit_reason": _clip(shared_seed.get("exit_reason"), max_len=280) or "unavailable",
        "pnl": shared_seed.get("pnl", "unavailable"),
        "pnl_pct": shared_seed.get("pnl_pct", "unavailable"),
        "data_source": dict((_as_dict(shared_seed.get("resolved_trade_facts")).get("data_source"))),
        "resolved_trade_facts": dict(shared_seed.get("resolved_trade_facts") or {}),
        "lifecycle_action": action,
        "lifecycle_status": status_text,
        "monitor_decision": dict(shared_seed.get("monitor_decision") or {}),
        "scanner_evidence_status": _clip(shared_seed.get("scanner_evidence_status"), max_len=24),
        "strategist_evidence_status": _clip(shared_seed.get("strategist_evidence_status"), max_len=24),
        "commander_route": dict(shared_seed.get("commander_route") or {}),
    }
    sanitized = _sanitize_report_language_fields(out)
    return dict(sanitized) if isinstance(sanitized, dict) else out


def _tail_list(values: Any, *, max_items: int = 6, max_len: int = 220) -> List[str]:
    if not isinstance(values, list):
        return []
    return _listify(values[-max(1, max_items) :], max_items=max_items, max_len=max_len)


def _compact_event_row(row: Any) -> Dict[str, Any]:
    item = row if isinstance(row, dict) else {}
    description = (
        item.get("description")
        or item.get("summary")
        or item.get("reason_human")
        or item.get("reason")
        or item.get("monitor_reason")
        or item.get("event_name")
        or item.get("event")
        or ""
    )
    out: Dict[str, Any] = {
        "ts": _clip(item.get("ts"), max_len=40),
        "event": _clip(item.get("event") or item.get("event_name"), max_len=80),
        "stage": _clip(item.get("stage") or item.get("agent"), max_len=48),
        "action": _clip(item.get("action") or item.get("side"), max_len=32),
        "description": _clip(description, max_len=220),
    }
    return {key: value for key, value in out.items() if value not in {"", None}}


def _compact_timeline_rows(values: Any, *, head: int = 3, tail: int = 9) -> List[Dict[str, Any]]:
    if not isinstance(values, list):
        return []
    picked: List[Any] = []
    picked.extend(values[: max(0, head)])
    if len(values) > head:
        picked.extend(values[-max(0, tail) :])
    out: List[Dict[str, Any]] = []
    seen = set()
    for row in picked:
        compact = _compact_event_row(row)
        marker = (
            str(compact.get("ts") or ""),
            str(compact.get("event") or ""),
            str(compact.get("description") or ""),
        )
        if not compact or marker in seen:
            continue
        seen.add(marker)
        out.append(compact)
    return out[:12]


def _compact_monitor_snapshot(section: Any) -> Dict[str, Any]:
    data = section if isinstance(section, dict) else {}
    policy_ref = data.get("policy_ref") if isinstance(data.get("policy_ref"), dict) else {}
    stop_trace = data.get("monitor_stop_policy_trace") if isinstance(data.get("monitor_stop_policy_trace"), dict) else {}
    out: Dict[str, Any] = {
        "posture": _clip(data.get("posture"), max_len=32),
        "trigger_type": _clip(data.get("trigger_type"), max_len=48),
        "summary": _clip(data.get("summary"), max_len=320),
        "bullets": _listify(data.get("bullets"), max_items=6, max_len=220),
        "position_age_seconds": data.get("position_age_seconds"),
        "hard_stop_pct": data.get("hard_stop_pct") or stop_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": data.get("adaptive_stop_loss_pct") or stop_trace.get("adaptive_stop_loss_pct"),
        "stop_loss_pct": data.get("stop_loss_pct") or stop_trace.get("stop_loss_pct"),
        "effective_stop_loss_pct": data.get("effective_stop_loss_pct") or stop_trace.get("effective_stop_loss_pct"),
        "effective_stop_reason": _clip(data.get("effective_stop_reason"), max_len=80),
        "trailing_stop_pct": data.get("trailing_stop_pct") or stop_trace.get("trailing_stop_pct"),
        "take_profit_pct": data.get("take_profit_pct") or stop_trace.get("take_profit_pct"),
        "strategist_baseline_stop_loss_pct": data.get("strategist_baseline_stop_loss_pct")
        or stop_trace.get("strategist_baseline_stop_loss_pct"),
        "strategist_baseline_take_profit_pct": data.get("strategist_baseline_take_profit_pct")
        or stop_trace.get("strategist_baseline_take_profit_pct"),
        "strategist_baseline_trailing_stop_pct": data.get("strategist_baseline_trailing_stop_pct")
        or stop_trace.get("strategist_baseline_trailing_stop_pct"),
        "exit_triggered": data.get("exit_triggered"),
        "current_price": data.get("current_price"),
        "average_price": data.get("average_price"),
        "peak_price": data.get("peak_price"),
        "current_drawdown": data.get("current_drawdown"),
        "peak_drawdown": data.get("peak_drawdown"),
        "vwap_distance": data.get("vwap_distance"),
        "active_exit_axis": _clip(data.get("active_exit_axis"), max_len=48),
        "watch_axes": _listify(data.get("watch_axes"), max_items=5, max_len=80),
        "confirm_required": data.get("confirm_required"),
        "confirm_count": data.get("confirm_count"),
        "guard_blocked": data.get("guard_blocked"),
        "guard_reason": _clip(data.get("guard_reason"), max_len=120),
        "decision_reason_chain": _listify(data.get("decision_reason_chain"), max_items=5, max_len=120),
        "entry_check_summary": _clip(data.get("entry_check_summary"), max_len=240),
        "entry_blockers": _listify(data.get("entry_blockers"), max_items=6, max_len=120),
        "threshold_shortfalls": _listify(data.get("threshold_shortfalls"), max_items=4, max_len=160),
        "entry_metrics": _compact_scalar_dict(data.get("entry_metrics"), max_items=10, max_len=120),
        "entry_thresholds": _compact_scalar_dict(data.get("entry_thresholds"), max_items=8, max_len=120),
        "policy_ref": _compact_scalar_dict(policy_ref, max_items=8, max_len=120),
        "timing_assessment": _compact_scalar_dict(data.get("timing_assessment"), max_items=8, max_len=120),
        "thresholds_guards_used": _compact_scalar_dict(data.get("thresholds_guards_used"), max_items=8, max_len=120),
        "received_policy": _compact_scalar_dict(data.get("received_policy"), max_items=12, max_len=120),
        "received_policy_source": _clip(data.get("received_policy_source"), max_len=80),
        "effective_policy": _compact_scalar_dict(data.get("effective_policy"), max_items=12, max_len=120),
        "effective_policy_source": _clip(data.get("effective_policy_source"), max_len=80),
        "effective_policy_source_chain": _listify(
            data.get("effective_policy_source_chain"), max_items=6, max_len=80
        ),
        "policy_adjustments": _compact_scalar_dict(data.get("policy_adjustments"), max_items=8, max_len=120),
        "policy_adjustment_summary": _clip(data.get("policy_adjustment_summary"), max_len=220),
        "policy_adjustment_reasoning": _clip(data.get("policy_adjustment_reasoning"), max_len=220),
        "effective_policy_deltas": [
            _clip(
                f"{(row or {}).get('field')}: {(row or {}).get('from')} -> {(row or {}).get('to')}",
                max_len=120,
            )
            for row in list(data.get("effective_policy_deltas") or [])[:8]
            if isinstance(row, dict)
        ],
        "applied_policy": _compact_scalar_dict(
            data.get("applied_policy") if isinstance(data.get("applied_policy"), dict) else policy_ref.get("applied_policy"),
            max_items=12,
            max_len=120,
        ),
        "policy_source": _clip(data.get("policy_source") or policy_ref.get("policy_source"), max_len=80),
        "policy_validation_status": _clip(
            data.get("policy_validation_status") or policy_ref.get("policy_validation_status"),
            max_len=80,
        ),
        "policy_fallback_used": (
            data.get("policy_fallback_used")
            if data.get("policy_fallback_used") is not None
            else policy_ref.get("policy_fallback_used")
        ),
        "policy_fallback_reason": _clip(
            data.get("policy_fallback_reason") or policy_ref.get("policy_fallback_reason"),
            max_len=220,
        ),
        "policy_partial_normalized": (
            data.get("policy_partial_normalized")
            if data.get("policy_partial_normalized") is not None
            else policy_ref.get("policy_partial_normalized")
        ),
        "policy_default_filled_fields": _listify(
            data.get("policy_default_filled_fields") or policy_ref.get("policy_default_filled_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_missing_fields": _listify(
            data.get("policy_validation_missing_fields") or policy_ref.get("policy_validation_missing_fields"),
            max_items=12,
            max_len=80,
        ),
        "policy_validation_invalid_fields": _listify(
            data.get("policy_validation_invalid_fields") or policy_ref.get("policy_validation_invalid_fields"),
            max_items=12,
            max_len=80,
        ),
        "override_reason": _clip(data.get("override_reason") or policy_ref.get("override_reason"), max_len=160),
        "applied_policy_source_chain": _listify(
            data.get("applied_policy_source_chain") or policy_ref.get("applied_policy_source_chain"),
            max_items=6,
            max_len=80,
        ),
        "price_source": _clip(data.get("price_source"), max_len=80),
        "feature_source": _clip(data.get("feature_source"), max_len=80),
        "monitor_stop_policy_trace": _compact_scalar_dict(data.get("monitor_stop_policy_trace"), max_items=8, max_len=120),
    }
    return {key: value for key, value in out.items() if value not in ("", None, [])}


def _build_market_context_bullets(section: Any) -> List[str]:
    data = section if isinstance(section, dict) else {}
    bullets = _listify(data.get("bullets"), max_items=12, max_len=260)
    extras: List[str] = []
    existing_prefixes = {
        prefix
        for prefix in (
            "News input:",
            "News query targets:",
            "Key strategist inputs:",
            "Strategist candidate hints:",
            "Strategist market headlines:",
            "Strategist symbol headlines:",
            "Market news titles:",
            "Candidate news titles:",
        )
        if any(str(row).startswith(prefix) for row in bullets)
    }
    news_input = _clip(data.get("news_input_summary"), max_len=220)
    news_targets = ", ".join(_listify(data.get("news_query_targets"), max_items=6, max_len=80))
    key_events = "; ".join(_listify(data.get("key_events_hint"), max_items=4, max_len=160))
    candidate_hints = ", ".join(_listify(data.get("candidate_hints"), max_items=6, max_len=24))
    strategist_market_headlines = "; ".join(_listify(data.get("market_headlines"), max_items=3, max_len=120))
    strategist_symbol_headlines = "; ".join(_listify(data.get("symbol_headlines"), max_items=3, max_len=120))
    market_titles = "; ".join(_listify(data.get("market_news_titles"), max_items=3, max_len=120))
    candidate_titles = "; ".join(_listify(data.get("candidate_news_titles"), max_items=3, max_len=120))
    if news_input and "News input:" not in existing_prefixes:
        extras.append(f"뉴스 입력 요약은 {news_input}입니다.")
    if news_targets and "News query targets:" not in existing_prefixes:
        extras.append(f"뉴스 조회 대상은 {news_targets}입니다.")
    if key_events and "Key strategist inputs:" not in existing_prefixes:
        extras.append(f"전략가 핵심 입력은 {key_events}입니다.")
    if market_titles and "Market news titles:" not in existing_prefixes:
        extras.append(f"주요 시장 뉴스는 {market_titles}입니다.")
    if candidate_titles and "Candidate news titles:" not in existing_prefixes:
        extras.append(f"후보 종목 관련 뉴스는 {candidate_titles}입니다.")
    if candidate_hints and "Strategist candidate hints:" not in existing_prefixes:
        extras.append(f"Strategist candidate hints: {candidate_hints}")
    if strategist_market_headlines and "Strategist market headlines:" not in existing_prefixes:
        extras.append(f"Strategist market headlines: {strategist_market_headlines}")
    if strategist_symbol_headlines and "Strategist symbol headlines:" not in existing_prefixes:
        extras.append(f"Strategist symbol headlines: {strategist_symbol_headlines}")
    return _dedupe_list(bullets + extras, max_items=12, max_len=260)


def _fmt_num(value: Any, *, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "-"


def _scanner_basis_text(scanner_reason: Dict[str, Any]) -> str:
    basis = scanner_reason.get("ranking_basis")
    if isinstance(basis, list):
        return ", ".join(_listify(basis, max_items=4, max_len=80))
    return _clip(basis, max_len=220)


def _build_scanner_choice_summary(scanner_reason: Dict[str, Any], market_context: Dict[str, Any]) -> str:
    symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24) or "선정 종목"
    rank = scanner_reason.get("selected_rank")
    universe = scanner_reason.get("universe_size")
    score_text = _fmt_num(scanner_reason.get("selected_score"))
    basis = _scanner_basis_text(scanner_reason)
    sources = ", ".join(_listify(scanner_reason.get("selected_sources"), max_items=4, max_len=80))
    confidence = _fmt_num(scanner_reason.get("confidence"))
    playbook = _clip(market_context.get("playbook"), max_len=32)
    comparison_bits: List[str] = []
    for row in list(scanner_reason.get("runner_ups_lost") or [])[:2]:
        if not isinstance(row, dict):
            continue
        runner_symbol = _clip(row.get("symbol"), max_len=24)
        runner_summary = _clip(row.get("summary"), max_len=180)
        if runner_symbol and runner_summary:
            comparison_bits.append(f"{runner_symbol}은 {runner_summary} 때문에 밀렸습니다")

    summary = f"스캐너는 {symbol}을 선택했습니다"
    if universe not in (None, "") and rank not in (None, ""):
        summary += f". 총 {int(universe)}개 후보 중 {rank}순위입니다"
    elif rank not in (None, ""):
        summary += f". 선정 순위는 {rank}위입니다"
    elif universe not in (None, ""):
        summary += f". 비교한 후보는 총 {int(universe)}개입니다"
    if score_text != "-":
        summary += f". 종합 점수는 {score_text}입니다"
    if basis:
        summary += f". 주요 산정 기준은 {basis}입니다"
    details: List[str] = []
    if sources:
        details.append(f"선정에 반영된 소스는 {sources}")
    if confidence != "-":
        details.append(f"신뢰도는 {confidence}")
    if playbook:
        details.append(f"전략가 플레이북 {playbook}과 정렬되었습니다")
    if details:
        summary += ". " + ", ".join(details) + "."
    if comparison_bits:
        summary += " " + " ".join(comparison_bits) + "."
    return summary


def _build_entry_decision_summary(
    entry_summary: Dict[str, Any],
    scanner_reason: Dict[str, Any],
    market_context: Dict[str, Any],
    action: str,
) -> str:
    reason_human = _clip(entry_summary.get("reason_human"), max_len=600)
    if reason_human:
        return reason_human
    scanner_summary = _build_scanner_choice_summary(scanner_reason, market_context)
    if scanner_summary:
        entry_action = _operator_action_label(_clip(entry_summary.get("action"), max_len=24) or action or "BUY")
        return f"{scanner_summary} 이에 따라 진입 판단은 {entry_action}로 이어졌습니다."
    return "진입 판단 근거는 저장된 데이터 범위 안에서 충분히 확인되지 않았습니다."


def _build_holding_story_summary(hold_count: int, monitor_reason: Dict[str, Any], status_text: str) -> str:
    posture = _operator_action_label(_clip(monitor_reason.get("posture"), max_len=32) or "WAIT")
    trigger = _operator_axis_label(_clip(monitor_reason.get("trigger_type"), max_len=48) or "not_captured")
    axis = _operator_axis_label(_clip(monitor_reason.get("active_exit_axis"), max_len=64) or trigger)
    confirm_required = monitor_reason.get("confirm_required")
    confirm_count = monitor_reason.get("confirm_count")
    exit_triggered = bool(monitor_reason.get("exit_triggered"))
    if hold_count > 0:
        base = f"보유 구간에서는 모니터가 총 {hold_count}회 실행되었고, 현재 포지션 판단은 {posture}로 유지되었습니다. 핵심 감시 축은 {axis}였습니다."
    else:
        base = "이번 lifecycle의 보유 구간 기록은 제한적이어서, 저장된 모니터 근거를 중심으로 보수적으로 정리했습니다."
    if confirm_required is not None:
        base += f" 청산 확인 조건은 {int(confirm_count or 0)}/{int(confirm_required or 0)} 단계로 기록되었습니다."
    if status_text.lower() == "open" and not exit_triggered:
        base += " 아직 확정된 매도 신호는 확인되지 않았습니다."
    return base


def _build_holding_story_bullets(holding_summary: Dict[str, Any], monitor_reason: Dict[str, Any]) -> List[str]:
    hold_count = len(list(holding_summary.get("run_ids") or []))
    watch_axes = ", ".join(_operator_axis_label(item) for item in _listify(monitor_reason.get("watch_axes"), max_items=6, max_len=80))
    decision_chain = " -> ".join(_listify(monitor_reason.get("decision_reason_chain"), max_items=5, max_len=60))
    hard_stop = _fmt_pct(monitor_reason.get("hard_stop_pct"))
    adaptive_stop = _fmt_pct(monitor_reason.get("adaptive_stop_loss_pct"))
    effective_stop = _fmt_pct(monitor_reason.get("effective_stop_loss_pct"))
    trailing_stop = _fmt_pct(monitor_reason.get("trailing_stop_pct"))
    take_profit = _fmt_pct(monitor_reason.get("take_profit_pct"))
    current_price = _fmt_price(monitor_reason.get("current_price"))
    average_price = _fmt_price(monitor_reason.get("average_price"))
    peak_price = _fmt_price(monitor_reason.get("peak_price"))
    current_drawdown = _fmt_pct(monitor_reason.get("current_drawdown"))
    peak_drawdown = _fmt_pct(monitor_reason.get("peak_drawdown"))
    bullets: List[str] = []
    if hold_count:
        bullets.append(f"모니터는 총 {hold_count}회 실행되었습니다.")
    if _clip(monitor_reason.get("posture"), max_len=48):
        bullets.append(f"현재 포지션 판단은 {_operator_action_label(monitor_reason.get('posture'))}입니다.")
    if _clip(monitor_reason.get("trigger_type"), max_len=64):
        bullets.append(f"감지된 핵심 신호는 {_operator_axis_label(monitor_reason.get('trigger_type'))}입니다.")
    if monitor_reason.get("position_age_seconds") not in (None, ""):
        bullets.append(f"포지션 보유 시간은 약 {int(monitor_reason.get('position_age_seconds') or 0)}초입니다.")
    if effective_stop != "-":
        stop_reason = _clip(monitor_reason.get("effective_stop_reason"), max_len=64)
        suffix = f", 기준 축은 {_operator_axis_label(stop_reason)}입니다" if stop_reason else ""
        bullets.append(f"유효 손절 기준은 {effective_stop} 수준입니다{suffix}.")
    if take_profit != "-":
        bullets.append(f"목표 수익 실현 기준은 {take_profit} 수준입니다.")
    if _clip(monitor_reason.get("active_exit_axis"), max_len=80):
        bullets.append(f"현재 우선 감시 중인 청산 축은 {_operator_axis_label(monitor_reason.get('active_exit_axis'))}입니다.")
    if monitor_reason.get("confirm_required") is not None:
        bullets.append(f"청산 확인 조건은 {int(monitor_reason.get('confirm_count') or 0)}/{int(monitor_reason.get('confirm_required') or 0)} 단계로 기록되었습니다.")
    if watch_axes:
        bullets.append(f"주요 감시 축은 {watch_axes}입니다.")
    if decision_chain:
        bullets.append(f"판단 흐름은 {decision_chain} 순서로 이어졌습니다.")
    if current_price != "-" or average_price != "-" or peak_price != "-":
        bullets.append(f"현재가, 평균가, 고점 기준 값은 {current_price} / {average_price} / {peak_price}입니다.")
    if current_drawdown != "-" or peak_drawdown != "-":
        bullets.append(f"현재 손익 변동과 고점 대비 하락폭은 {current_drawdown} / {peak_drawdown}입니다.")
    if _clip(monitor_reason.get("price_source"), max_len=80):
        bullets.append(f"가격 기준 소스는 {_clip(monitor_reason.get('price_source'), max_len=80)}입니다.")
    if _clip(monitor_reason.get("feature_source"), max_len=80):
        bullets.append(f"지표 기준 소스는 {_clip(monitor_reason.get('feature_source'), max_len=80)}입니다.")

    recent_updates = [
        _clip(item, max_len=180)
        for item in list(holding_summary.get("monitor_updates") or [])[-4:]
        if str(item or "").strip() and not _is_low_information_bullet(item)
    ]
    for item in recent_updates:
        bullets.append(f"최근 모니터 업데이트는 다음과 같습니다: {item}")
    return _dedupe_list(bullets, max_items=12, max_len=260)


def _build_exit_decision_summary(
    exit_summary: Dict[str, Any],
    monitor_context: Dict[str, Any],
    *,
    status_text: str,
) -> str:
    reason = _clip(exit_summary.get("reason_human"), max_len=600)
    if status_text.lower() == "open":
        return reason or "현재 포지션은 아직 열려 있어 확정된 청산 체결은 기록되지 않았습니다."
    if reason:
        price = _fmt_price(monitor_context.get("current_price"))
        avg_price = _fmt_price(monitor_context.get("average_price"))
        drawdown = _fmt_pct(monitor_context.get("current_drawdown"))
        axis = _operator_axis_label(_clip(monitor_context.get("active_exit_axis"), max_len=64))
        confirm_required = monitor_context.get("confirm_required")
        confirm_count = monitor_context.get("confirm_count")
        details: List[str] = []
        if axis:
            details.append(f"핵심 청산 축은 {axis}")
        if confirm_required is not None:
            details.append(f"확인 조건은 {int(confirm_count or 0)}/{int(confirm_required or 0)}")
        if price != "-" and avg_price != "-":
            details.append(f"현재가는 {price}, 평균가는 {avg_price}")
        if drawdown != "-":
            details.append(f"현재 손익 변동은 {drawdown}")
        if details:
            return f"{reason} 청산 당시 상황은 " + ", ".join(details) + "입니다."
        return reason
    return "청산 판단 근거는 저장된 데이터 범위 안에서 충분히 확인되지 않았습니다."


def _build_exit_decision_bullets(
    exit_summary: Dict[str, Any],
    monitor_context: Dict[str, Any],
    *,
    status_text: str,
) -> List[str]:
    guard_context = exit_summary.get("guard_context") if isinstance(exit_summary.get("guard_context"), dict) else {}
    execution_context = exit_summary.get("execution_context") if isinstance(exit_summary.get("execution_context"), dict) else {}
    bullets: List[str] = [
        f"청산 판단이 기록된 run은 {_clip(exit_summary.get('run_id'), max_len=80) or 'not_captured'}입니다.",
        f"청산 시각은 {_clip(exit_summary.get('ts'), max_len=80) or 'not_captured'}입니다.",
        f"청산 액션은 {_operator_action_label(_clip(exit_summary.get('action'), max_len=40) or ('HOLD' if status_text == 'open' else 'not_captured'))}입니다.",
        f"청산 사유는 {_clip(exit_summary.get('reason_human'), max_len=220) or ('position still open' if status_text == 'open' else 'not_captured')}입니다.",
    ]
    if _clip(monitor_context.get("trigger_type"), max_len=80):
        bullets.append(f"감지된 핵심 신호는 {_operator_axis_label(monitor_context.get('trigger_type'))}입니다.")
    if _clip(monitor_context.get("active_exit_axis"), max_len=120):
        bullets.append(f"현재 우선 감시 중인 청산 축은 {_operator_axis_label(monitor_context.get('active_exit_axis'))}입니다.")
    if monitor_context.get("confirm_required") is not None:
        bullets.append(f"청산 확인 조건은 {int(monitor_context.get('confirm_count') or 0)}/{int(monitor_context.get('confirm_required') or 0)} 단계로 기록되었습니다.")
    effective_stop = _fmt_pct(monitor_context.get("effective_stop_loss_pct"))
    if effective_stop != "-":
        stop_reason = _clip(monitor_context.get("effective_stop_reason"), max_len=64)
        suffix = f", 기준 축은 {_operator_axis_label(stop_reason)}입니다" if stop_reason else ""
        bullets.append(f"청산 시점의 유효 손절 기준은 {effective_stop} 수준입니다{suffix}.")
    take_profit = _fmt_pct(monitor_context.get("take_profit_pct"))
    if take_profit != "-":
        bullets.append(f"청산 시점의 목표 수익 실현 기준은 {take_profit} 수준입니다.")
    current_price = _fmt_price(monitor_context.get("current_price"))
    average_price = _fmt_price(monitor_context.get("average_price"))
    peak_price = _fmt_price(monitor_context.get("peak_price"))
    if current_price != "-" or average_price != "-" or peak_price != "-":
        bullets.append(f"현재가, 평균가, 고점 기준 값은 {current_price} / {average_price} / {peak_price}입니다.")
    current_drawdown = _fmt_pct(monitor_context.get("current_drawdown"))
    peak_drawdown = _fmt_pct(monitor_context.get("peak_drawdown"))
    if current_drawdown != "-" or peak_drawdown != "-":
        bullets.append(f"현재 손익 변동과 고점 대비 하락폭은 {current_drawdown} / {peak_drawdown}입니다.")
    decision_chain = " -> ".join(_listify(monitor_context.get("decision_reason_chain"), max_items=5, max_len=80))
    if decision_chain:
        bullets.append(f"판단 흐름은 {decision_chain} 순서로 이어졌습니다.")
    if _clip(guard_context.get("summary"), max_len=220):
        bullets.append(f"가드 판단 결과는 {_clip(guard_context.get('summary'), max_len=220)}입니다.")
    if _clip(execution_context.get("summary"), max_len=220):
        bullets.append(f"주문 실행 결과는 {_clip(execution_context.get('summary'), max_len=220)}입니다.")
    if _clip(monitor_context.get("price_source"), max_len=80):
        bullets.append(f"가격 기준 소스는 {_clip(monitor_context.get('price_source'), max_len=80)}입니다.")
    if _clip(monitor_context.get("feature_source"), max_len=80):
        bullets.append(f"지표 기준 소스는 {_clip(monitor_context.get('feature_source'), max_len=80)}입니다.")
    return _dedupe_list(bullets, max_items=12, max_len=260)


def _compact_holding_summary(holding: Any) -> Dict[str, Any]:
    data = holding if isinstance(holding, dict) else {}
    posture_rows = data.get("posture_history") if isinstance(data.get("posture_history"), list) else []
    recent_posture = [_compact_event_row(row) for row in posture_rows[-4:] if isinstance(row, dict)]
    recent_posture = [row for row in recent_posture if row]
    return {
        "run_count": len(list(data.get("run_ids") or [])),
        "recent_run_ids": [str(x or "") for x in list(data.get("run_ids") or [])[-6:] if str(x or "").strip()],
        "holding_event_count": len(list(data.get("holding_events") or [])),
        "recent_posture_history": recent_posture,
        "recent_monitor_updates": _tail_list(data.get("monitor_updates"), max_items=6, max_len=200),
    }


def _compact_entry_or_exit_summary(summary: Any) -> Dict[str, Any]:
    data = summary if isinstance(summary, dict) else {}
    strategist_ctx = data.get("strategist_context") if isinstance(data.get("strategist_context"), dict) else {}
    scanner_ctx = data.get("scanner_context") if isinstance(data.get("scanner_context"), dict) else {}
    monitor_ctx = data.get("monitor_context") if isinstance(data.get("monitor_context"), dict) else {}
    guard_ctx = data.get("guard_context") if isinstance(data.get("guard_context"), dict) else {}
    execution_ctx = data.get("execution_context") if isinstance(data.get("execution_context"), dict) else {}
    return {
        "run_id": _clip(data.get("run_id"), max_len=40),
        "ts": _clip(data.get("ts"), max_len=40),
        "action": _clip(data.get("action"), max_len=24),
        "reason_human": _clip(data.get("reason_human"), max_len=280),
        "strategist_context": {
            "market_regime": _clip(strategist_ctx.get("market_regime"), max_len=32),
            "market_sentiment": _clip(strategist_ctx.get("market_sentiment"), max_len=32),
            "playbook": _clip(strategist_ctx.get("playbook"), max_len=40),
            "themes": _listify(strategist_ctx.get("themes"), max_items=4, max_len=80),
            "global_sentiment_score": strategist_ctx.get("global_sentiment_score"),
            "vix_level": strategist_ctx.get("vix_level"),
            "headline_count": strategist_ctx.get("headline_count"),
            "news_query_targets": _listify(strategist_ctx.get("news_query_targets"), max_items=5, max_len=80),
            "stress_flags": _listify(strategist_ctx.get("stress_flags"), max_items=4, max_len=80),
        },
        "scanner_context": {
            "selected_symbol": _clip(scanner_ctx.get("selected_symbol"), max_len=24),
            "selected_rank": scanner_ctx.get("selected_rank"),
            "universe_size": scanner_ctx.get("universe_size"),
            "score_total": scanner_ctx.get("score_total"),
            "confidence": scanner_ctx.get("confidence"),
            "top_candidates": _compact_named_rows(scanner_ctx.get("top_candidates"), max_items=3),
            "selection_reason": _clip(scanner_ctx.get("selection_reason"), max_len=220),
        },
        "monitor_context": _compact_monitor_snapshot(monitor_ctx),
        "guard_context": {
            "status": _clip(guard_ctx.get("status") or guard_ctx.get("verdict"), max_len=32),
            "summary": _clip(guard_ctx.get("summary") or guard_ctx.get("reason"), max_len=220),
        },
        "execution_context": {
            "status": _clip(execution_ctx.get("status"), max_len=32),
            "summary": _clip(execution_ctx.get("summary") or execution_ctx.get("message"), max_len=220),
            "qty": execution_ctx.get("qty"),
            "price": execution_ctx.get("price"),
        },
    }


def _evidence_digest(evidence: Any, keys: List[str]) -> Dict[str, int]:
    data = evidence if isinstance(evidence, dict) else {}
    return {key: len(list(data.get(key) or [])) for key in keys}


def _compact_story_input_for_llm(story_input: Dict[str, Any]) -> Dict[str, Any]:
    market_context = story_input.get("market_context_human") if isinstance(story_input.get("market_context_human"), dict) else {}
    scanner_reason = story_input.get("scanner_reason_human") if isinstance(story_input.get("scanner_reason_human"), dict) else {}
    filters_human = story_input.get("filters_human") if isinstance(story_input.get("filters_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    guard_reason = story_input.get("guard_reason_human") if isinstance(story_input.get("guard_reason_human"), dict) else {}
    execution_outcome = story_input.get("execution_outcome_human") if isinstance(story_input.get("execution_outcome_human"), dict) else {}
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    operator_conclusion = story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}
    lifecycle_summary = story_input.get("lifecycle_summary") if isinstance(story_input.get("lifecycle_summary"), dict) else {}
    diagnostics = story_input.get("ai_report_diagnostics") if isinstance(story_input.get("ai_report_diagnostics"), dict) else {}
    shared_seed = _build_shared_summary_seed(story_input)
    commander_route = shared_seed.get("commander_route") if isinstance(shared_seed.get("commander_route"), dict) else {}
    strategist_evidence = shared_seed.get("strategist_evidence") if isinstance(shared_seed.get("strategist_evidence"), dict) else {}
    scanner_reasoning = shared_seed.get("scanner_reasoning") if isinstance(shared_seed.get("scanner_reasoning"), dict) else {}
    monitor_reasoning = shared_seed.get("monitor_reasoning") if isinstance(shared_seed.get("monitor_reasoning"), dict) else {}
    return {
        "trade_id": story_input.get("trade_id") or story_input.get("story_id"),
        "story_id": story_input.get("story_id"),
        "run_id": story_input.get("run_id"),
        "symbol": story_input.get("symbol"),
        "action": story_input.get("action"),
        "status": story_input.get("status"),
        "story_type": story_input.get("story_type"),
        "execution_mode_label": story_input.get("execution_mode_label"),
        "entry_summary": _compact_entry_or_exit_summary(story_input.get("entry_summary")),
        "holding_summary": _compact_holding_summary(story_input.get("holding_summary")),
        "exit_summary": _compact_entry_or_exit_summary(story_input.get("exit_summary")),
        "lifecycle_summary": {
            "holding_duration": _clip(lifecycle_summary.get("holding_duration"), max_len=40),
            "entry_reason_human": _clip(lifecycle_summary.get("entry_reason_human"), max_len=240),
            "exit_reason_human": _clip(lifecycle_summary.get("exit_reason_human"), max_len=240),
            "lifecycle_summary_human": _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=320),
        },
        "market_context_human": {
            "regime": _clip(market_context.get("regime"), max_len=24),
            "market_sentiment": _clip(market_context.get("market_sentiment"), max_len=24),
            "playbook": _clip(market_context.get("playbook"), max_len=32),
            "themes": _listify(market_context.get("themes"), max_items=4, max_len=80),
            "global_sentiment_score": market_context.get("global_sentiment_score"),
            "vix_level": market_context.get("vix_level"),
            "candidate_hints": _listify(
                market_context.get("candidate_hints") or strategist_evidence.get("candidate_hints"),
                max_items=8,
                max_len=24,
            ),
            "market_headlines": _listify(
                market_context.get("market_headlines") or strategist_evidence.get("market_headlines"),
                max_items=3,
                max_len=180,
            ),
            "symbol_headlines": _listify(
                market_context.get("symbol_headlines") or strategist_evidence.get("symbol_headlines"),
                max_items=3,
                max_len=180,
            ),
            "global_sentiment_signal": _compact_scalar_dict(
                market_context.get("global_sentiment_signal") or strategist_evidence.get("global_sentiment_signal"),
                max_items=8,
                max_len=120,
            ),
            "fear_index": _compact_scalar_dict(
                market_context.get("fear_index") or strategist_evidence.get("fear_index"),
                max_items=8,
                max_len=120,
            ),
            "headline_count": market_context.get("headline_count"),
            "news_query_count": market_context.get("news_query_count"),
            "market_signal_total": market_context.get("market_signal_total"),
            "candidate_signal_total": market_context.get("candidate_signal_total"),
            "news_query_targets": _listify(market_context.get("news_query_targets"), max_items=6, max_len=80),
            "key_events_hint": _listify(
                market_context.get("key_events_hint") or strategist_evidence.get("key_events"),
                max_items=4,
                max_len=180,
            ),
            "market_news_titles": _listify(market_context.get("market_news_titles"), max_items=3, max_len=140),
            "candidate_news_titles": _listify(market_context.get("candidate_news_titles"), max_items=3, max_len=140),
            "stress_flags": _listify(market_context.get("stress_flags"), max_items=4, max_len=80),
            "news_input_summary": _clip(market_context.get("news_input_summary"), max_len=220),
            "summary": _clip(market_context.get("summary"), max_len=320),
            "bullets": _listify(market_context.get("bullets"), max_items=6, max_len=220),
        },
        "commander": {
            "command_intent": _clip(commander_route.get("command_intent"), max_len=40),
            "strategist_invocation": _clip(commander_route.get("strategist_invocation"), max_len=40),
            "llm_policy": _clip(commander_route.get("llm_policy"), max_len=40),
            "selected_route": _clip(commander_route.get("selected_route"), max_len=60),
            "route_reason_text": _clip(commander_route.get("reason"), max_len=220),
            "strategist_cache_used": commander_route.get("strategist_cache_used"),
            "strategist_called": commander_route.get("strategist_called"),
            "cooldown_applied": commander_route.get("cooldown_applied"),
            "applied_policy": _compact_scalar_dict(commander_route.get("applied_policy"), max_items=12, max_len=120),
            "policy_source": _clip(commander_route.get("policy_source"), max_len=80),
            "policy_validation_status": _clip(commander_route.get("policy_validation_status"), max_len=80),
            "policy_fallback_used": commander_route.get("policy_fallback_used"),
            "policy_fallback_reason": _clip(commander_route.get("policy_fallback_reason"), max_len=220),
            "policy_partial_normalized": commander_route.get("policy_partial_normalized"),
            "policy_default_filled_fields": _listify(commander_route.get("policy_default_filled_fields"), max_items=12, max_len=80),
            "policy_validation_missing_fields": _listify(commander_route.get("policy_validation_missing_fields"), max_items=12, max_len=80),
            "policy_validation_invalid_fields": _listify(commander_route.get("policy_validation_invalid_fields"), max_items=12, max_len=80),
            "override_reason": _clip(commander_route.get("override_reason"), max_len=160),
            "applied_policy_source_chain": _listify(
                commander_route.get("applied_policy_source_chain"), max_items=6, max_len=80
            ),
        },
        "scanner_reason_human": {
            "selected_symbol": _clip(scanner_reason.get("selected_symbol"), max_len=24),
            "selected_rank": scanner_reason.get("selected_rank"),
            "universe_size": scanner_reason.get("universe_size"),
            "ranking_basis": _clip(scanner_reason.get("ranking_basis"), max_len=180),
            "playbook": _clip(scanner_reason.get("playbook") or scanner_reasoning.get("playbook"), max_len=80),
            "policy_source": _clip(scanner_reason.get("policy_source") or scanner_reasoning.get("policy_source"), max_len=80),
            "applied_policy_present": (
                scanner_reason.get("applied_policy_present")
                if scanner_reason.get("applied_policy_present") is not None
                else scanner_reasoning.get("applied_policy_present")
            ),
            "monitor_entry_policy_summary": _compact_scalar_dict(
                scanner_reason.get("monitor_entry_policy_summary")
                or scanner_reasoning.get("monitor_entry_policy_summary"),
                max_items=8,
                max_len=120,
            ),
            "selected_score": scanner_reason.get("selected_score"),
            "selected_sources": _listify(scanner_reason.get("selected_sources"), max_items=5, max_len=80),
            "source_scores": scanner_reason.get("source_scores") if isinstance(scanner_reason.get("source_scores"), dict) else {},
            "score_breakdown": scanner_reason.get("score_breakdown") if isinstance(scanner_reason.get("score_breakdown"), dict) else {},
            "why_selected": _listify(scanner_reason.get("why_selected"), max_items=4, max_len=160),
            "selection_basis": _clip(scanner_reason.get("selection_basis"), max_len=240),
            "selection_reason_with_bias": _clip(
                scanner_reason.get("selection_reason_with_bias") or scanner_reasoning.get("selection_reason_with_bias"),
                max_len=320,
            ),
            "tie_break_rule": _clip(scanner_reason.get("tie_break_rule"), max_len=180),
            "top_candidates": _compact_named_rows(scanner_reason.get("top_candidates"), max_items=3),
            "confidence": scanner_reason.get("confidence"),
            "confidence_label": _clip(scanner_reason.get("confidence_label"), max_len=32),
            "top_reasons": _listify(scanner_reason.get("top_reasons"), max_items=5, max_len=180),
            "runner_ups": _compact_named_rows(scanner_reason.get("runner_ups"), max_items=3),
            "runner_ups_lost": [
                {
                    "symbol": _clip((row or {}).get("symbol"), max_len=24),
                    "summary": _clip((row or {}).get("summary"), max_len=180),
                }
                for row in list(scanner_reason.get("runner_ups_lost") or [])[:3]
                if isinstance(row, dict)
            ],
            "scanner_bias_applied": (
                scanner_reason.get("scanner_bias_applied")
                if scanner_reason.get("scanner_bias_applied") is not None
                else scanner_reasoning.get("scanner_bias_applied")
            ),
            "scanner_bias_summary": _compact_scalar_dict(
                scanner_reason.get("scanner_bias_summary") or scanner_reasoning.get("scanner_bias_summary"),
                max_items=8,
                max_len=120,
            ),
            "candidate_bias_adjustments": [
                {
                    "symbol": _clip((row or {}).get("symbol"), max_len=24),
                    "bias_adjustment": (row or {}).get("bias_adjustment"),
                    "bias_adjustments": _listify(
                        [
                            (
                                str((item or {}).get("reason") or "")
                                if isinstance(item, dict)
                                else str(item or "")
                            )
                            for item in list((row or {}).get("bias_adjustments") or [])
                            if str((item or {}).get("reason") if isinstance(item, dict) else item or "").strip()
                        ],
                        max_items=4,
                        max_len=120,
                    ),
                }
                for row in list(
                    scanner_reason.get("candidate_bias_adjustments")
                    or scanner_reasoning.get("candidate_bias_adjustments")
                    or []
                )[:5]
                if isinstance(row, dict)
            ],
            "selection_trace": {
                "ranked_candidates": _compact_named_rows(
                    (scanner_reason.get("scanner_selection_trace") or {}).get("ranked_candidates")
                    or (scanner_reasoning.get("selection_trace") or {}).get("ranked_candidates"),
                    max_items=5,
                ),
                "selected_symbol": _clip(
                    (scanner_reason.get("scanner_selection_trace") or {}).get("selected_symbol")
                    or (scanner_reasoning.get("selection_trace") or {}).get("selected_symbol"),
                    max_len=24,
                ),
                "selected_rank": (scanner_reason.get("scanner_selection_trace") or {}).get("selected_rank")
                or (scanner_reasoning.get("selection_trace") or {}).get("selected_rank"),
                "selection_reason": _clip(
                    (scanner_reason.get("scanner_selection_trace") or {}).get("selection_reason")
                    or (scanner_reasoning.get("selection_trace") or {}).get("selection_reason"),
                    max_len=280,
                ),
                "selected_symbol_score_drivers": _compact_scalar_dict(
                    (scanner_reason.get("scanner_selection_trace") or {}).get("selected_symbol_score_drivers")
                    or (scanner_reasoning.get("selection_trace") or {}).get("selected_symbol_score_drivers"),
                    max_items=6,
                    max_len=120,
                ),
            },
            "summary": _clip(scanner_reason.get("summary"), max_len=320),
            "comparison": _clip(scanner_reason.get("comparison"), max_len=240),
            "bullets": _listify(scanner_reason.get("bullets"), max_items=6, max_len=220),
        },
        "filters_human": {
            "summary": _clip(filters_human.get("summary"), max_len=280),
            "bullets": _listify(filters_human.get("bullets"), max_items=6, max_len=220),
        },
        "monitor_reason_human": {
            **_compact_monitor_snapshot(monitor_reason),
            "threshold_shortfalls": _listify(
                monitor_reason.get("threshold_shortfalls")
                or (monitor_reasoning.get("monitor_blocker_trace") or {}).get("threshold_shortfalls"),
                max_items=4,
                max_len=160,
            ),
            "monitor_stop_policy_trace": _compact_scalar_dict(
                monitor_reason.get("monitor_stop_policy_trace")
                or monitor_reasoning.get("monitor_stop_policy_trace"),
                max_items=8,
                max_len=120,
            ),
        },
        "guard_reason_human": {
            "summary": _clip(guard_reason.get("summary"), max_len=280),
            "status": _clip(guard_reason.get("status"), max_len=32),
            "bullets": _listify(guard_reason.get("bullets"), max_items=6, max_len=220),
        },
        "execution_outcome_human": {
            "summary": _clip(execution_outcome.get("summary"), max_len=280),
            "status": _clip(execution_outcome.get("status"), max_len=32),
            "bullets": _listify(execution_outcome.get("bullets"), max_items=6, max_len=220),
        },
        "reporter_status_human": {
            "summary": _clip(reporter_status.get("summary"), max_len=280),
            "status": _clip(reporter_status.get("status"), max_len=32),
            "grade": _clip(reporter_status.get("grade"), max_len=16),
            "bullets": _listify(reporter_status.get("bullets"), max_items=5, max_len=180),
        },
        "operator_conclusion_human": {
            "summary": _clip(operator_conclusion.get("summary"), max_len=280),
            "current_action": _clip(operator_conclusion.get("current_action"), max_len=24),
            "watch_next": _listify(operator_conclusion.get("watch_next"), max_items=5, max_len=180),
            "thesis_invalidation": _listify(operator_conclusion.get("thesis_invalidation"), max_items=5, max_len=180),
        },
        "timeline": _compact_timeline_rows(story_input.get("timeline")),
        "warnings": _listify(story_input.get("warnings"), max_items=8, max_len=180),
        "improvement_points": _listify(story_input.get("improvement_points"), max_items=6, max_len=180),
        "strategist_evidence": strategist_evidence,
        "scanner_selection_trace": _as_dict(story_input.get("scanner_selection_trace")),
        "monitor_stop_policy_trace": _as_dict(story_input.get("monitor_stop_policy_trace")),
        "monitor_blocker_trace": _as_dict(story_input.get("monitor_blocker_trace")),
        "evidence_digest": {
            "strategist": _evidence_digest(
                story_input.get("strategist_evidence"),
                ["market_context_snapshots", "global_sentiment_breakdowns", "news_evidence_ranked", "decision_frames", "llm_response_saved"],
            ),
            "scanner": _evidence_digest(
                story_input.get("scanner_evidence"),
                ["candidate_pool_snapshots", "candidate_ranking_tables", "candidate_selection_reasons", "selection_outputs"],
            ),
            "monitor": _evidence_digest(
                story_input.get("monitor_timeline"),
                ["threshold_snapshots", "state_transitions", "exit_decision_details", "cycle_summaries"],
            ),
        },
        "ai_report_diagnostics": {
            "report_status": _clip(diagnostics.get("report_status"), max_len=24),
            "report_reason_code": _clip(diagnostics.get("report_reason_code"), max_len=48),
            "report_reason_human": _clip(diagnostics.get("report_reason_human"), max_len=220),
            "next_expected_step": _clip(diagnostics.get("next_expected_step"), max_len=220),
        },
    }


def build_ai_trade_report_compact_input(story_input: Dict[str, Any]) -> Dict[str, Any]:
    return _sparse_story_input_for_llm(story_input)


def _sparse_story_input_for_llm(story_input: Dict[str, Any]) -> Dict[str, Any]:
    compact = _compact_story_input_for_llm(story_input)
    commander = compact.get("commander") if isinstance(compact.get("commander"), dict) else {}
    entry = compact.get("entry_summary") if isinstance(compact.get("entry_summary"), dict) else {}
    exit_summary = compact.get("exit_summary") if isinstance(compact.get("exit_summary"), dict) else {}
    market = compact.get("market_context_human") if isinstance(compact.get("market_context_human"), dict) else {}
    scanner = compact.get("scanner_reason_human") if isinstance(compact.get("scanner_reason_human"), dict) else {}
    monitor = compact.get("monitor_reason_human") if isinstance(compact.get("monitor_reason_human"), dict) else {}
    filters_human = compact.get("filters_human") if isinstance(compact.get("filters_human"), dict) else {}
    guard = compact.get("guard_reason_human") if isinstance(compact.get("guard_reason_human"), dict) else {}
    execution = compact.get("execution_outcome_human") if isinstance(compact.get("execution_outcome_human"), dict) else {}
    reporter = compact.get("reporter_status_human") if isinstance(compact.get("reporter_status_human"), dict) else {}
    conclusion = compact.get("operator_conclusion_human") if isinstance(compact.get("operator_conclusion_human"), dict) else {}
    holding = compact.get("holding_summary") if isinstance(compact.get("holding_summary"), dict) else {}
    lifecycle = compact.get("lifecycle_summary") if isinstance(compact.get("lifecycle_summary"), dict) else {}
    diagnostics = compact.get("ai_report_diagnostics") if isinstance(compact.get("ai_report_diagnostics"), dict) else {}
    return {
        "trade_id": compact.get("trade_id"),
        "story_id": compact.get("story_id"),
        "run_id": compact.get("run_id"),
        "symbol": compact.get("symbol"),
        "action": compact.get("action"),
        "status": compact.get("status"),
        "story_type": compact.get("story_type"),
        "execution_mode_label": compact.get("execution_mode_label"),
        "lifecycle_summary": {
            "holding_duration": lifecycle.get("holding_duration"),
            "entry_reason_human": lifecycle.get("entry_reason_human"),
            "exit_reason_human": lifecycle.get("exit_reason_human"),
            "lifecycle_summary_human": lifecycle.get("lifecycle_summary_human"),
        },
        "market_context": {
            "regime": market.get("regime"),
            "market_sentiment": market.get("market_sentiment"),
            "playbook": market.get("playbook"),
            "themes": _listify(market.get("themes"), max_items=3, max_len=60),
            "global_sentiment_score": market.get("global_sentiment_score"),
            "vix_level": market.get("vix_level"),
            "stress_flags": _listify(market.get("stress_flags"), max_items=3, max_len=60),
            "candidate_hints": _listify(market.get("candidate_hints"), max_items=6, max_len=24),
            "market_headlines": _listify(market.get("market_headlines"), max_items=3, max_len=160),
            "symbol_headlines": _listify(market.get("symbol_headlines"), max_items=3, max_len=160),
            "global_sentiment_signal": _compact_scalar_dict(
                market.get("global_sentiment_signal"), max_items=8, max_len=120
            ),
            "fear_index": _compact_scalar_dict(market.get("fear_index"), max_items=8, max_len=120),
            "key_events": _listify(market.get("key_events_hint"), max_items=4, max_len=160),
            "news_input_summary": market.get("news_input_summary"),
        },
        "commander": {
            "command_intent": commander.get("command_intent"),
            "strategist_invocation": commander.get("strategist_invocation"),
            "llm_policy": commander.get("llm_policy"),
            "selected_route": commander.get("selected_route"),
            "route_reason_text": commander.get("route_reason_text"),
            "strategist_cache_used": commander.get("strategist_cache_used"),
            "strategist_called": commander.get("strategist_called"),
            "cooldown_applied": commander.get("cooldown_applied"),
            "applied_policy": _compact_scalar_dict(commander.get("applied_policy"), max_items=12, max_len=120),
            "policy_source": commander.get("policy_source"),
            "policy_validation_status": commander.get("policy_validation_status"),
            "policy_fallback_used": commander.get("policy_fallback_used"),
            "policy_fallback_reason": commander.get("policy_fallback_reason"),
            "policy_partial_normalized": commander.get("policy_partial_normalized"),
            "policy_default_filled_fields": _listify(commander.get("policy_default_filled_fields"), max_items=12, max_len=80),
            "policy_validation_missing_fields": _listify(commander.get("policy_validation_missing_fields"), max_items=12, max_len=80),
            "policy_validation_invalid_fields": _listify(commander.get("policy_validation_invalid_fields"), max_items=12, max_len=80),
            "override_reason": commander.get("override_reason"),
            "applied_policy_source_chain": _listify(
                commander.get("applied_policy_source_chain"), max_items=6, max_len=80
            ),
        },
        "entry": {
            "ts": entry.get("ts"),
            "action": entry.get("action"),
            "reason_human": entry.get("reason_human"),
        },
        "scanner": {
            "selected_symbol": scanner.get("selected_symbol"),
            "selected_rank": scanner.get("selected_rank"),
            "universe_size": scanner.get("universe_size"),
            "ranking_basis": scanner.get("ranking_basis"),
            "playbook": scanner.get("playbook"),
            "policy_source": scanner.get("policy_source"),
            "applied_policy_present": scanner.get("applied_policy_present"),
            "monitor_entry_policy_summary": _compact_scalar_dict(
                scanner.get("monitor_entry_policy_summary"), max_items=8, max_len=120
            ),
            "confidence": scanner.get("confidence"),
            "confidence_label": scanner.get("confidence_label"),
            "top_reasons": _listify(scanner.get("top_reasons"), max_items=3, max_len=140),
            "why_selected": _listify(scanner.get("why_selected"), max_items=4, max_len=140),
            "selection_basis": scanner.get("selection_basis"),
            "selection_reason_with_bias": scanner.get("selection_reason_with_bias"),
            "tie_break_rule": scanner.get("tie_break_rule"),
            "runner_ups": _listify(scanner.get("runner_ups"), max_items=2, max_len=140),
            "runner_ups_lost": [
                {
                    "symbol": _clip((row or {}).get("symbol"), max_len=24),
                    "summary": _clip((row or {}).get("summary"), max_len=180),
                }
                for row in list(scanner.get("runner_ups_lost") or [])[:3]
                if isinstance(row, dict)
            ],
            "scanner_bias_applied": scanner.get("scanner_bias_applied"),
            "scanner_bias_summary": _compact_scalar_dict(scanner.get("scanner_bias_summary"), max_items=8, max_len=120),
            "candidate_bias_adjustments": [
                {
                    "symbol": _clip((row or {}).get("symbol"), max_len=24),
                    "bias_adjustment": (row or {}).get("bias_adjustment"),
                    "bias_adjustments": _listify(
                        [
                            (
                                str((item or {}).get("reason") or "")
                                if isinstance(item, dict)
                                else str(item or "")
                            )
                            for item in list((row or {}).get("bias_adjustments") or [])
                            if str((item or {}).get("reason") if isinstance(item, dict) else item or "").strip()
                        ],
                        max_items=4,
                        max_len=120,
                    ),
                }
                for row in list(scanner.get("candidate_bias_adjustments") or [])[:5]
                if isinstance(row, dict)
            ],
            "selection_trace": {
                "ranked_candidates": _compact_named_rows(
                    (scanner.get("selection_trace") or {}).get("ranked_candidates"),
                    max_items=5,
                ),
                "selected_symbol": _clip((scanner.get("selection_trace") or {}).get("selected_symbol"), max_len=24),
                "selected_rank": (scanner.get("selection_trace") or {}).get("selected_rank"),
                "selection_reason": _clip((scanner.get("selection_trace") or {}).get("selection_reason"), max_len=280),
                "selected_symbol_score_drivers": _compact_scalar_dict(
                    (scanner.get("selection_trace") or {}).get("selected_symbol_score_drivers"),
                    max_items=6,
                    max_len=120,
                ),
            },
            "summary": scanner.get("summary"),
        },
        "filters": {
            "summary": filters_human.get("summary"),
            "bullets": _listify(filters_human.get("bullets"), max_items=4, max_len=180),
        },
        "holding": {
            "run_count": holding.get("run_count"),
            "holding_event_count": holding.get("holding_event_count"),
            "recent_monitor_updates": _listify(holding.get("recent_monitor_updates"), max_items=4, max_len=140),
        },
        "monitor": {
            "posture": monitor.get("posture"),
            "trigger_type": monitor.get("trigger_type"),
            "summary": monitor.get("summary"),
            "entry_check_summary": monitor.get("entry_check_summary"),
            "entry_blockers": _listify(monitor.get("entry_blockers"), max_items=6, max_len=120),
            "threshold_shortfalls": _listify(monitor.get("threshold_shortfalls"), max_items=4, max_len=160),
            "policy_ref": _compact_scalar_dict(monitor.get("policy_ref"), max_items=8, max_len=120),
            "timing_assessment": _compact_scalar_dict(monitor.get("timing_assessment"), max_items=8, max_len=120),
            "thresholds_guards_used": _compact_scalar_dict(monitor.get("thresholds_guards_used"), max_items=8, max_len=120),
            "entry_metrics": _compact_scalar_dict(monitor.get("entry_metrics"), max_items=10, max_len=120),
            "entry_thresholds": _compact_scalar_dict(monitor.get("entry_thresholds"), max_items=8, max_len=120),
            "received_policy": _compact_scalar_dict(monitor.get("received_policy"), max_items=12, max_len=120),
            "received_policy_source": monitor.get("received_policy_source"),
            "effective_policy": _compact_scalar_dict(monitor.get("effective_policy"), max_items=12, max_len=120),
            "effective_policy_source": monitor.get("effective_policy_source"),
            "effective_policy_source_chain": _listify(
                monitor.get("effective_policy_source_chain"), max_items=6, max_len=80
            ),
            "policy_adjustments": _compact_scalar_dict(monitor.get("policy_adjustments"), max_items=8, max_len=120),
            "policy_adjustment_summary": monitor.get("policy_adjustment_summary"),
            "policy_adjustment_reasoning": monitor.get("policy_adjustment_reasoning"),
            "effective_policy_deltas": [
                (
                    _clip(
                        f"{(row or {}).get('field')}: {(row or {}).get('from')} -> {(row or {}).get('to')}",
                        max_len=120,
                    )
                    if isinstance(row, dict)
                    else _clip(row, max_len=120)
                )
                for row in list(monitor.get("effective_policy_deltas") or [])[:8]
                if (
                    isinstance(row, dict)
                    or str(row or "").strip()
                )
            ],
            "applied_policy": _compact_scalar_dict(monitor.get("applied_policy"), max_items=12, max_len=120),
            "policy_source": monitor.get("policy_source"),
            "policy_validation_status": monitor.get("policy_validation_status"),
            "policy_fallback_used": monitor.get("policy_fallback_used"),
            "policy_fallback_reason": monitor.get("policy_fallback_reason"),
            "policy_partial_normalized": monitor.get("policy_partial_normalized"),
            "policy_default_filled_fields": _listify(monitor.get("policy_default_filled_fields"), max_items=12, max_len=80),
            "policy_validation_missing_fields": _listify(monitor.get("policy_validation_missing_fields"), max_items=12, max_len=80),
            "policy_validation_invalid_fields": _listify(monitor.get("policy_validation_invalid_fields"), max_items=12, max_len=80),
            "override_reason": monitor.get("override_reason"),
            "applied_policy_source_chain": _listify(
                monitor.get("applied_policy_source_chain"), max_items=6, max_len=80
            ),
            "position_age_seconds": monitor.get("position_age_seconds"),
            "hard_stop_pct": monitor.get("hard_stop_pct"),
            "adaptive_stop_loss_pct": monitor.get("adaptive_stop_loss_pct"),
            "stop_loss_pct": monitor.get("stop_loss_pct"),
            "effective_stop_loss_pct": monitor.get("effective_stop_loss_pct"),
            "trailing_stop_pct": monitor.get("trailing_stop_pct"),
            "take_profit_pct": monitor.get("take_profit_pct"),
            "monitor_stop_policy_trace": _compact_scalar_dict(
                monitor.get("monitor_stop_policy_trace"), max_items=8, max_len=120
            ),
            "current_price": monitor.get("current_price"),
            "average_price": monitor.get("average_price"),
            "peak_price": monitor.get("peak_price"),
            "current_drawdown": monitor.get("current_drawdown"),
            "peak_drawdown": monitor.get("peak_drawdown"),
            "active_exit_axis": monitor.get("active_exit_axis"),
            "watch_axes": _listify(monitor.get("watch_axes"), max_items=4, max_len=80),
            "price_source": monitor.get("price_source"),
        },
        "exit": {
            "ts": exit_summary.get("ts"),
            "action": exit_summary.get("action"),
            "reason_human": exit_summary.get("reason_human"),
        },
        "guard": {
            "summary": guard.get("summary"),
            "status": guard.get("status"),
            "bullets": _listify(guard.get("bullets"), max_items=4, max_len=180),
        },
        "execution": {
            "summary": execution.get("summary"),
            "status": execution.get("status"),
            "bullets": _listify(execution.get("bullets"), max_items=4, max_len=180),
        },
        "reporter": {
            "summary": reporter.get("summary"),
            "status": reporter.get("status"),
            "grade": reporter.get("grade"),
            "bullets": _listify(reporter.get("bullets"), max_items=3, max_len=160),
        },
        "operator_conclusion": {
            "summary": conclusion.get("summary"),
            "current_action": conclusion.get("current_action"),
            "watch_next": _listify(conclusion.get("watch_next"), max_items=3, max_len=140),
            "thesis_invalidation": _listify(conclusion.get("thesis_invalidation"), max_items=3, max_len=140),
        },
        "timeline": _compact_timeline_rows(story_input.get("timeline"), head=1, tail=5),
        "improvement_points": _listify(compact.get("improvement_points"), max_items=4, max_len=140),
        "strategist_evidence": _as_dict(compact.get("strategist_evidence")),
        "scanner_selection_trace": _as_dict(compact.get("scanner_selection_trace")),
        "monitor_stop_policy_trace": _as_dict(compact.get("monitor_stop_policy_trace")),
        "monitor_blocker_trace": _as_dict(compact.get("monitor_blocker_trace")),
        "ai_report_diagnostics": {
            "report_status": diagnostics.get("report_status"),
            "report_reason_code": diagnostics.get("report_reason_code"),
            "report_reason_human": diagnostics.get("report_reason_human"),
        },
    }


def _normalize_provenance_entry(entry: Any) -> Dict[str, Any]:
    row = entry if isinstance(entry, dict) else {}
    source = str(row.get("source") or "fallback").strip().lower()
    path = str(row.get("artifact_path") or "").strip()
    confidence = str(row.get("confidence") or "").strip().lower()
    if confidence not in {"high", "medium", "low"}:
        if source == "canonical":
            confidence = "high"
        elif source in {"direct_artifact", "direct"}:
            confidence = "medium"
        else:
            confidence = "low"
    if confidence == "high":
        completeness = 1.0
    elif confidence == "medium":
        completeness = 0.75
    else:
        completeness = 0.5 if source != "fallback" else 0.35
    return {
        "source": source or "fallback",
        "evidence_source": source or "fallback",
        "artifact_path": path,
        "confidence": confidence,
        "completeness": completeness,
    }


def _report_section_provenance(story_input: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    source = story_input.get("section_provenance") if isinstance(story_input.get("section_provenance"), dict) else {}
    fallback = _normalize_provenance_entry({"source": "fallback", "artifact_path": "", "confidence": "low"})
    return {
        "executive_summary": _normalize_provenance_entry(source.get("operator_conclusion_human") or fallback),
        "market_context_at_entry": _normalize_provenance_entry(source.get("market_context_human") or fallback),
        "why_this_symbol_was_chosen": _normalize_provenance_entry(source.get("scanner_reason_human") or fallback),
        "entry_decision": _normalize_provenance_entry(source.get("scanner_reason_human") or fallback),
        "holding_monitoring_story": _normalize_provenance_entry(source.get("monitor_reason_human") or fallback),
        "exit_decision": _normalize_provenance_entry(source.get("monitor_reason_human") or fallback),
        "execution_quality": _normalize_provenance_entry(source.get("execution_outcome_human") or fallback),
        "scanner_filters": _normalize_provenance_entry(source.get("filters_human") or fallback),
        "guard_approval_result": _normalize_provenance_entry(source.get("guard_reason_human") or fallback),
        "reporter_evaluation": _normalize_provenance_entry(source.get("reporter_status_human") or fallback),
        "errors_weaknesses_improvement_points": _normalize_provenance_entry(source.get("reporter_status_human") or fallback),
        "full_timeline": _normalize_provenance_entry(source.get("timeline") or fallback),
        "final_operator_conclusion": _normalize_provenance_entry(source.get("operator_conclusion_human") or fallback),
    }


def _contains_hangul(value: Any) -> bool:
    return bool(re.search(r"[가-힣]", str(value or "")))


def _operator_action_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "buy": "매수",
        "sell": "매도",
        "hold": "보유 유지",
        "wait": "진입 보류",
        "noop": "대기",
        "approve": "승인",
        "approved": "승인",
        "allowed": "허용",
        "yes": "허용",
        "no": "차단",
    }
    return mapping.get(raw, _clip(value, max_len=80) or "-")


def _operator_axis_label(value: Any) -> str:
    raw = _clip(value, max_len=120).strip().lower()
    mapping = {
        "peak drawdown": "고점 대비 하락폭",
        "peak_drawdown": "고점 대비 하락폭",
        "hard stop": "고정 손절 기준",
        "hard_stop": "고정 손절 기준",
        "adaptive stop": "상황 대응형 손절 기준",
        "adaptive_stop": "상황 대응형 손절 기준",
        "take profit": "목표 수익 실현 기준",
        "take_profit": "목표 수익 실현 기준",
        "trailing stop": "추적 손절 기준",
        "trailing_stop": "추적 손절 기준",
        "vwap breakdown": "VWAP 이탈",
        "intraday low break": "장중 저점 이탈",
        "trend breakdown": "추세 훼손",
        "hold": "보유 유지",
        "wait": "진입 보류",
        "confirmed_exit_signal": "청산 확인 신호",
    }
    return mapping.get(raw, _clip(value, max_len=120) or "-")


def _operator_filter_label(value: Any) -> str:
    raw = _clip(value, max_len=120).strip().lower()
    mapping = {
        "liquidity filter": "유동성 점검",
        "turnover filter": "회전율 점검",
        "sector/theme alignment": "섹터·테마 정렬 점검",
        "chart completeness filter": "차트 지표 충실도 점검",
        "sentiment gate": "시장 심리 점검",
        "risk gate": "리스크 점검",
        "price anomaly filter": "가격 이상치 점검",
        "spread/slippage filter": "호가 스프레드·슬리피지 점검",
    }
    return mapping.get(raw, _clip(value, max_len=120) or "-")


def _operator_filter_status(value: Any) -> str:
    raw = _clip(value, max_len=40).strip().lower()
    mapping = {
        "pass": "통과",
        "fail": "미통과",
        "not_available": "확인 불가",
    }
    return mapping.get(raw, _clip(value, max_len=40) or "-")


def _normalize_trade_report_language(text: Any) -> str:
    cleaned = _sanitize_forbidden_scripts_text(_clip(text, max_len=2000))
    if not cleaned:
        return ""

    def _normalize_metadata_value(value: str) -> str:
        raw = _clip(value, max_len=240).strip()
        lowered = raw.lower()
        if lowered in {"unknown", "not available", "not_available", "unavailable"}:
            return "확인되지 않음"
        if lowered in {"not captured", "not_captured"}:
            return "기록되지 않음"
        return raw

    def _replace_scanner_selection(match: re.Match[str]) -> str:
        symbol = _clip(match.group(1), max_len=24)
        rank = _clip(match.group(2), max_len=8)
        total = _clip(match.group(3), max_len=8)
        score = _clip(match.group(4), max_len=32)
        reason = _clip(match.group(5), max_len=220)
        return (
            f"스캐너는 {total}개 후보 중 {rank}위인 {symbol}을 총점 {score}로 선정했습니다. "
            f"선정 이유는 {reason}입니다."
        )

    def _replace_headlines(match: re.Match[str]) -> str:
        count = _clip(match.group(1), max_len=12)
        targets = _clip(match.group(2), max_len=12)
        detail = _clip(match.group(3), max_len=120)
        if detail:
            return f"관련 헤드라인 {count}건을 함께 반영했고 총 {targets}개 대상({detail})을 점검했습니다."
        return f"관련 헤드라인 {count}건을 함께 반영했고 총 {targets}개 대상을 점검했습니다."

    cleaned = re.sub(
        r"Scanner selected ([0-9A-Z]+) as rank #?(\d+) out of (\d+) candidates with score ([0-9.\-]+) because (.+?)(?:\.)?$",
        _replace_scanner_selection,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(\d+)\s+headlines were considered across (\d+)\s+targets(?:\s*\(([^)]*)\))?",
        _replace_headlines,
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"Scanner selected the highest-ranked candidate after (.+?)(?:\.)?$",
        lambda m: f"스캐너는 { _clip(m.group(1), max_len=220) }를 반영해 최상위 후보를 선정했습니다.",
        cleaned,
        flags=re.IGNORECASE,
    )

    def _replace_metadata_token(match: re.Match[str]) -> str:
        key = str(match.group(1) or "").strip().lower()
        value = _normalize_metadata_value(str(match.group(2) or ""))
        label_map = {
            "source": "데이터 출처",
            "path": "참조 경로",
            "model": "사용 모델",
            "status": "상태",
            "generated_at": "생성 시각",
        }
        return f"{label_map.get(key, key)}: {value}"

    cleaned = re.sub(
        r"\b(source|path|model|status|generated_at)\s*=\s*([^\s;,)\]]+)",
        _replace_metadata_token,
        cleaned,
        flags=re.IGNORECASE,
    )

    replacements = (
        ("Trailing stop", "추적 손절"),
        ("trailing stop", "추적 손절"),
        ("Scanner selected", "스캐너는"),
        ("Market Sentiment", "시장 심리"),
        ("Market sentiment", "시장 심리"),
        ("Stress Flags", "스트레스 신호"),
        ("Stress flags", "스트레스 신호"),
        ("Scanner Rank", "스캐너 순위"),
        ("Scanner Ranking Basis", "스캐너 순위 산정 기준"),
        ("Tie Break Rule", "동률 해소 기준"),
        ("Tie-break rule", "동률 해소 기준"),
        ("Tie Break", "동률 해소"),
        ("Regime", "시장 상태"),
        ("playbook", "플레이북"),
        ("Playbook", "플레이북"),
        ("headlines were considered", "관련 헤드라인을 함께 반영했습니다"),
        ("Total Score", "총점"),
        ("strategist-guided weighting, source scoring, and risk penalties", "전략가 가중치, 소스 점수, 리스크 패널티"),
        ("it led on trading value, theme and sector alignment", "거래대금과 테마·섹터 정렬에서 앞섰기 때문"),
        ("candidate signals", "후보 신호"),
        ("market /", "시장 /"),
        ("bearish", "약세"),
        ("bullish", "강세"),
        ("neutral", "중립"),
        ("pullback", "눌림목"),
        ("not captured", "기록되지 않음"),
        ("not available", "확인되지 않음"),
        ("unknown", "판단 정보 없음"),
    )
    for src, dst in replacements:
        cleaned = cleaned.replace(src, dst)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned


def _operatorize_report_text(text: Any) -> str:
    cleaned = _normalize_trade_report_language(text)
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    exact_mapping = {
        "the decision path was recorded, but the operator-facing summary is limited.": "의사결정 경로는 기록되었지만 운영자용 요약은 제한적으로만 남아 있습니다.",
        "execution quality details were not captured.": "실행 품질 세부 내용은 별도로 기록되지 않았습니다.",
        "reporter linkage was not available yet.": "Reporter 연계 결과는 아직 연결되지 않았습니다.",
        "reporter linkage status was recorded separately.": "Reporter 연계 상태는 별도로 기록되어 있습니다.",
        "warnings and missing links were recorded for operator follow-up.": "운영자가 후속 확인해야 할 경고와 누락 링크가 함께 기록되었습니다.",
        "no explicit weaknesses were surfaced beyond the recorded trace.": "기록된 추적 정보 외에 추가 약점은 별도로 확인되지 않았습니다.",
        "ai trade report generation failed after retry attempts. review the saved llm response artifact for details.": "AI 거래 리포트 생성이 재시도 이후에도 완료되지 않았습니다. 저장된 LLM 응답 아티팩트를 함께 확인해 주세요.",
        "ai generation failed before a rendered market-context section was produced.": "시장 환경 요약은 생성 도중 중단되어, 저장된 근거를 기준으로 보수적으로 정리했습니다.",
        "ai generation failed before a rendered symbol-selection section was produced.": "종목 선정 설명은 생성 도중 중단되어, 저장된 선정 근거를 기준으로 보수적으로 정리했습니다.",
        "ai generation failed before a rendered entry-decision section was produced.": "진입 판단 설명은 생성 도중 중단되어, 저장된 진입 근거를 기준으로 보수적으로 정리했습니다.",
        "ai generation failed before a rendered holding-monitoring section was produced.": "보유 관리 설명은 생성 도중 중단되어, 저장된 모니터 기록을 기준으로 보수적으로 정리했습니다.",
        "ai generation failed before a rendered exit-decision section was produced.": "청산 판단 설명은 생성 도중 중단되어, 저장된 청산 근거를 기준으로 보수적으로 정리했습니다.",
        "ai generation failed before a rendered execution-quality section was produced.": "실행 품질 설명은 생성 도중 중단되어, 저장된 실행 기록을 기준으로 보수적으로 정리했습니다.",
        "ai generation failed and no rendered improvement section is available.": "AI 생성이 중단되어 개선 포인트는 저장된 경고와 오류 기록 중심으로 정리했습니다.",
        "ai generation failed. review lifecycle artifacts and the saved llm response artifact before taking action.": "AI 생성이 중단되었습니다. 다음 조치를 하기 전에 lifecycle 아티팩트와 저장된 LLM 응답을 함께 확인해 주세요.",
        "link same-day reporter analysis to this lifecycle for a complete quality review.": "같은 날 생성된 reporter 분석을 이 lifecycle에 연결해 전체 품질 평가를 완성해 주세요.",
        "selection": "선정 근거를 정리했습니다.",
        "entry": "진입 판단을 정리했습니다.",
        "filters": "스캐너 필터 점검 결과를 정리했습니다.",
        "guard": "승인 및 가드 판단 결과를 정리했습니다.",
        "execution": "실행 결과를 정리했습니다.",
        "reporter": "리포터 평가를 정리했습니다.",
        "none": "추가 보완 포인트는 제한적입니다.",
    }
    if lowered in exact_mapping:
        return exact_mapping[lowered]

    m = re.fullmatch(r"Market regime:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"시장 상태는 {_clip(m.group(1), max_len=160)}입니다."
    m = re.fullmatch(r"시장 regime:\s*([^,]+),\s*감성:\s*([^,]+),\s*플레이북:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"시장 상태는 {_clip(m.group(1), max_len=80)}이며, 시장 심리는 {_clip(m.group(2), max_len=80)}이고, 플레이북은 {_clip(m.group(3), max_len=120)}입니다."
    m = re.fullmatch(r"Global sentiment score:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"글로벌 감성 점수는 {_clip(m.group(1), max_len=120)}입니다."
    m = re.fullmatch(r"글로벌 감성 점수:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"글로벌 감성 점수는 {_clip(m.group(1), max_len=120)}입니다."
    m = re.fullmatch(r"VIX:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"VIX 수준은 {_clip(m.group(1), max_len=120)}입니다."
    m = re.fullmatch(r"VIX 수준:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"VIX 수준은 {_clip(m.group(1), max_len=120)}입니다."
    m = re.fullmatch(r"News input:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"뉴스 입력 요약은 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"News query targets:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"뉴스 조회 대상은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Key strategist inputs:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"전략가 핵심 입력은 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"Market news titles:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주요 시장 뉴스는 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"Candidate news titles:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"후보 종목 관련 뉴스는 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"테마:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주요 테마는 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"적용 테마:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"적용된 테마는 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"뉴스 분석:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"뉴스 분석 범위는 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Universe scanned:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=80)
        if value == "not_captured":
            return "비교한 후보 수는 별도로 기록되지 않았습니다."
        return f"총 {value}개 후보를 비교했습니다."
    m = re.fullmatch(r"Selected rank:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=80)
        if value == "not_captured":
            return "선정 순위 정보는 별도로 기록되지 않았습니다."
        return f"최종 선정 순위는 {value}입니다."
    m = re.fullmatch(r"Selected because:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"선정 이유는 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Top candidates:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"상위 후보는 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"Why not others:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"다른 후보가 밀린 이유는 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"Selection decision:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"최종 선정 판단은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Final decision basis:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"최종 결정 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Tie-break rule:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"동률 해소 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"동률 해소 기준[:：]?\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"동률 해소 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Runner-ups lost because:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"차순위 후보가 밀린 이유는 {_clip(m.group(1), max_len=240)}입니다."
    m = re.fullmatch(r"Selection sources:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"선정에 반영된 핵심 소스는 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Ranking basis:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"순위 산정 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Chart / feature coverage:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"차트 및 지표 충실도는 {_clip(m.group(1), max_len=120)}입니다."
    m = re.fullmatch(r"Entry run:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "진입 판단이 기록된 run 정보는 남아 있지 않습니다."
        return f"진입 판단이 기록된 run은 {value}입니다."
    m = re.fullmatch(r"Entry time:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "진입 시각은 별도로 기록되지 않았습니다."
        return f"진입 시각은 {value}입니다."
    m = re.fullmatch(r"Entry action:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"진입 액션은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"Entry reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=240)
        if value == "not_captured":
            return "진입 판단 사유는 별도로 기록되지 않았습니다."
        return f"진입 판단 근거는 {value}입니다."
    m = re.fullmatch(r"보유 기간:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"보유 기간은 {_clip(m.group(1), max_len=140)}입니다."
    m = re.fullmatch(r"모니터 실행:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"모니터 실행 기록은 {_clip(m.group(1), max_len=180)}입니다."
    m = re.fullmatch(r"모니터 판단:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"모니터 판단 흐름은 {_clip(m.group(1), max_len=220)}입니다."
    m = re.fullmatch(r"Monitor runs:\s*(\d+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"모니터는 총 {m.group(1)}회 실행되었습니다."
    m = re.fullmatch(r"Posture:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재 포지션 판단은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"Trigger type:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"감지된 핵심 신호는 {_operator_axis_label(m.group(1))}입니다."
    m = re.fullmatch(r"Position age:\s*(\d+)\s*seconds", cleaned, flags=re.IGNORECASE)
    if m:
        return f"포지션 보유 시간은 약 {m.group(1)}초입니다."
    m = re.fullmatch(r"Effective stop:\s*([^(]+?)(?:\s*\((.+)\))?", cleaned, flags=re.IGNORECASE)
    if m:
        level = _clip(m.group(1), max_len=80)
        reason = _operator_axis_label(m.group(2))
        if reason and reason != "-":
            return f"유효 손절 기준은 {level} 수준이며, 기준 축은 {reason}입니다."
        return f"유효 손절 기준은 {level} 수준입니다."
    m = re.fullmatch(r"Take profit:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"목표 수익 실현 기준은 {_clip(m.group(1), max_len=80)} 수준입니다."
    m = re.fullmatch(r"Active exit axis:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재 우선 감시 중인 청산 축은 {_operator_axis_label(m.group(1))}입니다."
    m = re.fullmatch(r"Exit confirmation:\s*(\d+)/(\d+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"청산 확인 조건은 {m.group(1)}/{m.group(2)} 단계로 기록되었습니다."
    m = re.fullmatch(r"Watch axes:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        axes = ", ".join(_operator_axis_label(part.strip()) for part in m.group(1).split(","))
        return f"주요 감시 축은 {axes}입니다."
    m = re.fullmatch(r"Decision chain:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"판단 흐름은 {_clip(m.group(1), max_len=220)} 순서로 이어졌습니다."
    m = re.fullmatch(r"Current price / avg / peak:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재가, 평균가, 고점 기준 값은 {_clip(m.group(1), max_len=200)}입니다."
    m = re.fullmatch(r"Current drawdown / peak drawdown:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재 손익 변동과 고점 대비 하락폭은 {_clip(m.group(1), max_len=200)}입니다."
    m = re.fullmatch(r"Price source:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"가격 기준 소스는 {_clip(m.group(1), max_len=140)}입니다."
    m = re.fullmatch(r"Feature source:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"지표 기준 소스는 {_clip(m.group(1), max_len=140)}입니다."
    m = re.fullmatch(r"Recent monitor update:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"최근 모니터 업데이트는 다음과 같습니다: {_clip(m.group(1), max_len=240)}"
    m = re.fullmatch(r"Exit run:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "청산 판단이 기록된 run 정보는 남아 있지 않습니다."
        return f"청산 판단이 기록된 run은 {value}입니다."
    m = re.fullmatch(r"Exit time:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "청산 시각은 별도로 기록되지 않았습니다."
        return f"청산 시각은 {value}입니다."
    m = re.fullmatch(r"Exit action:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"청산 액션은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"Exit reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=240)
        if value in {"position still open", "still open"}:
            return "현재 포지션은 아직 열려 있어 확정된 청산 사유는 없습니다."
        if value == "not_captured":
            return "청산 사유는 별도로 기록되지 않았습니다."
        return f"청산 사유는 {value}입니다."
    m = re.fullmatch(r"Execution outcome:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주문 실행 결과는 {_clip(m.group(1), max_len=180)}입니다."
    m = re.fullmatch(r"Quantity:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"수량: {_clip(m.group(1), max_len=80)}"
    m = re.fullmatch(r"수량:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"수량: {_clip(m.group(1), max_len=80)}"
    m = re.fullmatch(r"Execution mode:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"실행 모드: {_clip(m.group(1), max_len=120)}"
    m = re.fullmatch(r"Broker environment:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "브로커 환경 정보는 별도로 기록되지 않았습니다."
        return f"브로커 환경은 {value}입니다."
    m = re.fullmatch(r"Supervisor verdict:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"감독 승인 판단은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"Supervisor allow:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주문 허용 여부는 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"Guard reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"가드 판단 사유는 {_clip(m.group(1), max_len=200)}입니다."
    m = re.fullmatch(r"Action reviewed:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"검토한 액션은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"Symbol reviewed:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"검토한 종목은 {_clip(m.group(1), max_len=60)}입니다."
    m = re.fullmatch(r"Approval mode:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not captured in the execution trace":
            return "승인 모드는 실행 추적에는 별도로 남아 있지 않습니다."
        return f"승인 모드는 {value}입니다."
    m = re.fullmatch(r"슈퍼바이저 판단:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"감독 승인 판단은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"슈퍼바이저 허용:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주문 허용 여부는 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"가드 이유:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"가드 판단 사유는 {_clip(m.group(1), max_len=200)}입니다."
    m = re.fullmatch(r"검토된 액션:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"검토한 액션은 {_operator_action_label(m.group(1))}입니다."
    m = re.fullmatch(r"(.+?):\s*(PASS|FAIL|NOT_AVAILABLE)\s*-\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"{_operator_filter_label(m.group(1))}은 {_operator_filter_status(m.group(2))}였습니다. 근거: {_clip(m.group(3), max_len=220)}"

    cleaned = cleaned.replace("Hard stop", "고정 손절 기준")
    cleaned = cleaned.replace("Adaptive stop", "상황 대응형 손절 기준")
    cleaned = cleaned.replace("Take profit", "목표 수익 실현 기준")
    cleaned = cleaned.replace("Trailing stop", "추적 손절 기준")
    cleaned = cleaned.replace("Peak drawdown", "고점 대비 하락폭")
    cleaned = cleaned.replace("VWAP breakdown", "VWAP 이탈")
    cleaned = cleaned.replace("Intraday low break", "장중 저점 이탈")
    cleaned = cleaned.replace("Trend breakdown", "추세 훼손")
    return _normalize_trade_report_language(cleaned)


def _operatorize_report_section(section: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(section or {})
    if "headline" in normalized:
        normalized["headline"] = _operatorize_report_text(normalized.get("headline"))
    if "summary" in normalized:
        normalized["summary"] = _operatorize_report_text(normalized.get("summary"))
    if isinstance(normalized.get("bullets"), list):
        normalized["bullets"] = _dedupe_list(
            [_operatorize_report_text(item) for item in list(normalized.get("bullets") or []) if _operatorize_report_text(item)],
            max_items=12,
            max_len=260,
        )
    if isinstance(normalized.get("watch_next"), list):
        normalized["watch_next"] = _dedupe_list(
            [_operatorize_report_text(item) for item in list(normalized.get("watch_next") or []) if _operatorize_report_text(item)],
            max_items=6,
            max_len=200,
        )
    if isinstance(normalized.get("thesis_invalidation"), list):
        normalized["thesis_invalidation"] = _dedupe_list(
            [_operatorize_report_text(item) for item in list(normalized.get("thesis_invalidation") or []) if _operatorize_report_text(item)],
            max_items=6,
            max_len=200,
        )
    return normalized


def _prefer_fallback_text(ai_text: Any, fallback_text: Any) -> str:
    ai_clean = _clip(ai_text, max_len=2000)
    fallback_clean = _clip(fallback_text, max_len=2000)
    if not ai_clean:
        return fallback_clean
    if fallback_clean and not _contains_hangul(ai_clean) and _contains_hangul(fallback_clean):
        return fallback_clean
    return ai_clean


def _trade_report_priority_bullet_prefixes(section_key: str) -> List[str]:
    key = str(section_key or "").strip().lower()
    if key in {"market_context_at_entry", "market_context"}:
        return [
            "Market regime:",
            "시장 상태는",
            "Global sentiment score:",
            "글로벌 감성 점수는",
            "VIX",
            "News input:",
            "뉴스 입력 요약은",
            "News query targets:",
            "뉴스 조회 대상은",
            "Key strategist inputs:",
            "전략가 핵심 입력은",
            "Market news titles:",
            "주요 시장 뉴스는",
            "Candidate news titles:",
            "후보 종목 관련 뉴스는",
        ]
    if key in {"why_this_symbol_was_chosen", "why_this_symbol", "entry_decision"}:
        return [
            "Top candidates:",
            "상위 후보는",
            "Why not others:",
            "다른 후보가 밀린 이유는",
            "Selection decision:",
            "최종 선정 판단은",
            "Final decision basis:",
            "최종 결정 기준은",
            "Tie-break rule:",
            "동점 해소 기준은",
            "Runner-ups lost because:",
            "차순위 후보가 밀린 이유는",
            "Selection sources:",
            "선정에 반영된 핵심 소스는",
            "Ranking basis:",
            "순위 산정 기준은",
        ]
    if key in {"holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision"}:
        return [
            "Monitor runs:",
            "모니터는 총",
            "Posture:",
            "현재 포지션 판단은",
            "Trigger type:",
            "감지된 핵심 신호는",
            "Position age:",
            "포지션 보유 시간은",
            "Effective stop:",
            "유효 손절 기준은",
            "Take profit:",
            "목표 수익 실현 기준은",
            "Active exit axis:",
            "현재 우선 감시 중인 청산 축은",
            "Exit confirmation:",
            "청산 확인 조건은",
            "Watch axes:",
            "주요 감시 축은",
            "Decision chain:",
            "판단 흐름은",
            "Current price / avg / peak:",
            "현재가, 평균가, 고점 기준 값은",
            "Current drawdown / peak drawdown:",
            "현재 손익 변동과 고점 대비 하락폭은",
            "Price source:",
            "가격 기준 소스는",
            "Feature source:",
            "지표 기준 소스는",
        ]
    return []


def _merge_bullets_with_fallback(section_key: str, ai_bullets: List[str], fallback_bullets: List[str]) -> List[str]:
    if not ai_bullets:
        return fallback_bullets[:12]
    if not fallback_bullets:
        return ai_bullets[:12]

    merged: List[str] = []
    seen: set[str] = set()

    def _append(values: List[str]) -> None:
        for value in values:
            bullet = _clip(value, max_len=260)
            if not bullet or bullet in seen:
                continue
            merged.append(bullet)
            seen.add(bullet)
            if len(merged) >= 12:
                break

    _append(ai_bullets)
    if len(merged) >= 12:
        return merged[:12]

    priority_prefixes = _trade_report_priority_bullet_prefixes(section_key)
    for prefix in priority_prefixes:
        if len(merged) >= 12:
            break
        if any(str(row).startswith(prefix) for row in merged):
            continue
        for row in fallback_bullets:
            if str(row).startswith(prefix):
                _append([row])
                break

    if len(merged) < 8:
        _append(fallback_bullets)
    prefixes = _trade_report_priority_bullet_prefixes(section_key)
    if not prefixes:
        return merged[:12]
    deduped: List[str] = []
    seen: set[str] = set()
    seen_prefixes: set[str] = set()
    for bullet in merged:
        if bullet in seen:
            continue
        matched_prefix = next((prefix for prefix in prefixes if str(bullet).startswith(prefix)), "")
        if matched_prefix:
            if matched_prefix in seen_prefixes:
                continue
            seen_prefixes.add(matched_prefix)
        deduped.append(bullet)
        seen.add(bullet)
        if len(deduped) >= 12:
            break
    return deduped[:12]


def _merge_section_with_fallback(ai_section: Any, fallback_section: Dict[str, Any], *, section_key: str = "") -> Dict[str, Any]:
    section = ai_section if isinstance(ai_section, dict) else {}
    fallback = fallback_section if isinstance(fallback_section, dict) else {}
    merged = dict(section)
    merged["summary"] = _prefer_fallback_text(section.get("summary"), fallback.get("summary"))
    ai_bullets = _listify(section.get("bullets"), max_items=12, max_len=260)
    fallback_bullets = _listify(fallback.get("bullets"), max_items=12, max_len=260)
    if not ai_bullets:
        merged["bullets"] = fallback_bullets
    elif section_key in {"execution_quality", "guard_approval_result"} and any(_contains_hangul(item) for item in ai_bullets):
        merged["bullets"] = ai_bullets[:12]
    elif (
        fallback_bullets
        and section_key in {"holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision"}
        and sum(1 for item in ai_bullets if _is_low_information_bullet(item)) >= max(3, len(ai_bullets) // 2)
    ):
        merged["bullets"] = fallback_bullets
    elif fallback_bullets and not any(_contains_hangul(item) for item in ai_bullets) and any(_contains_hangul(item) for item in fallback_bullets):
        merged["bullets"] = fallback_bullets
    else:
        merged["bullets"] = _merge_bullets_with_fallback(section_key, ai_bullets, fallback_bullets)
    for key in ("headline", "action", "confidence", "status", "grade", "current_action", "symbol"):
        if not str(merged.get(key) or "").strip() and str(fallback.get(key) or "").strip():
            merged[key] = fallback.get(key)
    for key, value in fallback.items():
        if key in {"summary", "bullets"}:
            continue
        if key not in merged or merged.get(key) in (None, "", [], {}):
            merged[key] = value
    return merged


def _trade_report_parse_meta(raw: Any, parsed: Dict[str, Any] | None) -> Dict[str, Any]:
    result = parse_llm_json_response(raw)
    candidate = parsed if isinstance(parsed, dict) else {}
    key_meta = required_key_metadata(candidate, AI_TRADE_REPORT_REQUIRED_KEYS)
    parse_mode = "none"
    if bool(result.get("is_full")):
        parse_mode = "full"
    elif bool(result.get("is_partial")):
        parse_mode = "partial"
    return {
        "parse_mode": parse_mode,
        **key_meta,
        "trailing_text": str(result.get("trailing_text") or ""),
        "raw_nonempty": bool(result.get("raw_nonempty")),
        "parse_error": str(result.get("error") or ""),
    }


def _merge_trade_report_candidate(
    story_input: Dict[str, Any],
    candidate: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
) -> Dict[str, Any]:
    out = _fallback_report(
        story_input,
        status=status,
        mode=mode,
        model=model,
        reason=reason,
    )
    out["generation"] = {
        "status": status,
        "mode": mode,
        "model": _clip(model, max_len=120),
        "reason": _clip(reason, max_len=320),
    }
    used_fallback_sections: List[str] = []

    def _merge_into(section_key: str, source_value: Any, fallback_key: str | None = None) -> None:
        normalized = _normalize_section(
            source_value,
            default_summary=(out.get(section_key) or {}).get("summary") or "",
        )
        merged = _merge_section_with_fallback(
            normalized,
            out.get(section_key) if isinstance(out.get(section_key), dict) else {},
            section_key=section_key,
        )
        if not (isinstance(source_value, dict) and source_value):
            used_fallback_sections.append(section_key)
        out[section_key] = merged
        if fallback_key:
            out[fallback_key] = dict(merged)

    _merge_into("executive_summary", candidate.get("executive_summary"))
    _merge_into("market_context_at_entry", candidate.get("market_context_at_entry") or candidate.get("market_context"), "market_context")
    _merge_into("why_this_symbol_was_chosen", candidate.get("why_this_symbol_was_chosen") or candidate.get("why_this_symbol"), "why_this_symbol")
    _merge_into("entry_decision", candidate.get("entry_decision"))
    _merge_into("holding_monitoring_story", candidate.get("holding_monitoring_story") or candidate.get("monitor_trigger_reasoning"), "monitor_trigger_reasoning")
    _merge_into("exit_decision", candidate.get("exit_decision"))
    _merge_into("execution_quality", candidate.get("execution_quality") or candidate.get("execution_result"), "execution_result")
    _merge_into("scanner_filters", candidate.get("scanner_filters") or candidate.get("scanner_logic_and_filters"), "scanner_logic_and_filters")
    _merge_into("guard_approval_result", candidate.get("guard_approval_result"))
    out["reporter_evaluation"] = _merge_section_with_fallback(
        _normalize_section(candidate.get("reporter_evaluation"), default_summary=out["reporter_evaluation"]["summary"]),
        out["reporter_evaluation"],
        section_key="reporter_evaluation",
    )
    if not isinstance(candidate.get("reporter_evaluation"), dict):
        used_fallback_sections.append("reporter_evaluation")
    out["errors_weaknesses_improvement_points"] = _merge_section_with_fallback(
        _normalize_section(
            candidate.get("errors_weaknesses_improvement_points"),
            default_summary=out["errors_weaknesses_improvement_points"]["summary"],
        ),
        out["errors_weaknesses_improvement_points"],
        section_key="errors_weaknesses_improvement_points",
    )
    if not isinstance(candidate.get("errors_weaknesses_improvement_points"), dict):
        used_fallback_sections.append("errors_weaknesses_improvement_points")

    final_conclusion = candidate.get("final_operator_conclusion") if isinstance(candidate.get("final_operator_conclusion"), dict) else {}
    out["final_operator_conclusion"] = {
        "summary": _prefer_fallback_text(final_conclusion.get("summary"), out["final_operator_conclusion"]["summary"]),
        "current_action": _clip(final_conclusion.get("current_action"), max_len=24) or out["final_operator_conclusion"]["current_action"],
        "watch_next": _listify(final_conclusion.get("watch_next"), max_items=6, max_len=200) or out["final_operator_conclusion"]["watch_next"],
        "thesis_invalidation": _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=200)
        or out["final_operator_conclusion"]["thesis_invalidation"],
    }
    if not final_conclusion:
        used_fallback_sections.append("final_operator_conclusion")

    timeline_rows: List[Dict[str, Any]] = []
    parsed_timeline = candidate.get("full_timeline")
    if isinstance(parsed_timeline, list):
        timeline_rows = [row for row in parsed_timeline if isinstance(row, dict)][:24]
    if not timeline_rows:
        timeline_rows = [row for row in list(candidate.get("timeline") or []) if isinstance(row, dict)][:24]
    if timeline_rows:
        out["full_timeline"] = timeline_rows
        out["timeline"] = timeline_rows
    else:
        used_fallback_sections.append("timeline")

    out["used_fallback_sections"] = sorted(set(used_fallback_sections))
    return _normalize_trade_report_output(story_input, out)


def _fallback_report(
    story_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
) -> Dict[str, Any]:
    shared_seed = _build_shared_summary_seed(story_input)
    market_context = story_input.get("market_context_human") if isinstance(story_input.get("market_context_human"), dict) else {}
    strategist_evidence = shared_seed.get("strategist_evidence") if isinstance(shared_seed.get("strategist_evidence"), dict) else {}
    scanner_reason = story_input.get("scanner_reason_human") if isinstance(story_input.get("scanner_reason_human"), dict) else {}
    filters_human = story_input.get("filters_human") if isinstance(story_input.get("filters_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    guard_reason = story_input.get("guard_reason_human") if isinstance(story_input.get("guard_reason_human"), dict) else {}
    execution_outcome = story_input.get("execution_outcome_human") if isinstance(story_input.get("execution_outcome_human"), dict) else {}
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    operator_conclusion = (
        story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}
    )
    action = _clip(shared_seed.get("lifecycle_action"), max_len=24) or _clip(story_input.get("action"), max_len=24) or "WAIT"
    monitor_stop_trace = _as_dict(
        monitor_reason.get("monitor_stop_policy_trace")
        or story_input.get("monitor_stop_policy_trace")
    )
    monitor_snapshot = {
        "posture": _clip(monitor_reason.get("posture"), max_len=40) or action or "WAIT",
        "trigger_type": _clip(monitor_reason.get("trigger_type"), max_len=80) or "not_captured",
        "position_age_seconds": int(monitor_reason.get("position_age_seconds") or 0),
        "hard_stop_pct": monitor_reason.get("hard_stop_pct") or monitor_stop_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": monitor_reason.get("adaptive_stop_loss_pct") or monitor_stop_trace.get("adaptive_stop_loss_pct"),
        "stop_loss_pct": monitor_reason.get("stop_loss_pct"),
        "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct") or monitor_stop_trace.get("effective_stop_loss_pct"),
        "effective_stop_reason": _clip(monitor_reason.get("effective_stop_reason"), max_len=80) or "not_captured",
        "strategist_baseline_stop_loss_pct": monitor_reason.get("strategist_baseline_stop_loss_pct")
        or monitor_stop_trace.get("strategist_baseline_stop_loss_pct"),
        "strategist_baseline_take_profit_pct": monitor_reason.get("strategist_baseline_take_profit_pct")
        or monitor_stop_trace.get("strategist_baseline_take_profit_pct"),
        "strategist_baseline_trailing_stop_pct": monitor_reason.get("strategist_baseline_trailing_stop_pct")
        or monitor_stop_trace.get("strategist_baseline_trailing_stop_pct"),
        "take_profit_pct": monitor_reason.get("take_profit_pct") or monitor_stop_trace.get("take_profit_pct"),
        "trailing_stop_pct": monitor_reason.get("trailing_stop_pct") or monitor_stop_trace.get("trailing_stop_pct"),
        "exit_triggered": bool(monitor_reason.get("exit_triggered")),
        "current_price": monitor_reason.get("current_price"),
        "average_price": monitor_reason.get("average_price"),
        "peak_price": monitor_reason.get("peak_price"),
        "current_drawdown": monitor_reason.get("current_drawdown"),
        "peak_drawdown": monitor_reason.get("peak_drawdown"),
        "vwap_distance": monitor_reason.get("vwap_distance"),
        "active_exit_axis": _clip(monitor_reason.get("active_exit_axis"), max_len=80),
        "watch_axes": _listify(monitor_reason.get("watch_axes"), max_items=8, max_len=120),
        "price_source": _clip(monitor_reason.get("price_source"), max_len=120) or "not_captured",
        "feature_source": _clip(monitor_reason.get("feature_source"), max_len=120) or "not_captured",
        "price_source_policy": _clip(monitor_reason.get("price_source_policy"), max_len=260) or "",
    }
    entry_summary = story_input.get("entry_summary") if isinstance(story_input.get("entry_summary"), dict) else {}
    holding_summary = story_input.get("holding_summary") if isinstance(story_input.get("holding_summary"), dict) else {}
    exit_summary = story_input.get("exit_summary") if isinstance(story_input.get("exit_summary"), dict) else {}
    lifecycle_summary = story_input.get("lifecycle_summary") if isinstance(story_input.get("lifecycle_summary"), dict) else {}
    warnings = _listify(story_input.get("warnings"), max_items=10, max_len=260)
    improvement_points = _listify(story_input.get("improvement_points"), max_items=10, max_len=260)

    symbol = _clip(shared_seed.get("symbol"), max_len=32) or _clip(story_input.get("symbol"), max_len=32) or "unknown"
    trade_id = _clip(shared_seed.get("trade_id"), max_len=120) or _clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120)
    status_text = _clip(shared_seed.get("lifecycle_status"), max_len=32) or _clip(story_input.get("status"), max_len=32) or "closed"
    executive_reason = (
        _clip(operator_conclusion.get("summary"), max_len=600)
        or _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=600)
        or _clip(execution_outcome.get("summary"), max_len=600)
        or _clip(scanner_reason.get("summary"), max_len=600)
        or "The decision path was recorded, but the operator-facing summary is limited."
    )
    confidence = _clip(scanner_reason.get("confidence_label"), max_len=24) or _clip(scanner_reason.get("confidence"), max_len=24)
    scanner_choice_summary = _build_scanner_choice_summary(scanner_reason, market_context)
    if str(shared_seed.get("scanner_evidence_status") or "").strip() == "unavailable":
        scanner_choice_summary = "Scanner evidence unavailable for this trade. Selection rationale is reported conservatively."
    market_context_summary = _clip(market_context.get("summary"), max_len=600)
    if str(shared_seed.get("strategist_evidence_status") or "").strip() == "unavailable" and (
        not market_context_summary or _is_low_information_bullet(market_context_summary)
    ):
        market_context_summary = "Strategist evidence unavailable for this trade. Market context is shown as limited."

    entry_decision = {
        "summary": (
            _build_entry_decision_summary(entry_summary, scanner_reason, market_context, action)
            if bool(shared_seed.get("entry_exists"))
            else "Entry evidence was insufficient, so entry timing is marked as unavailable."
        ),
        "bullets": [
            f"Entry run: {_clip(entry_summary.get('run_id'), max_len=80) or 'not_captured'}",
            f"Entry time: {_clip(entry_summary.get('ts'), max_len=80) or 'not_captured'}",
            f"Entry action: {_clip(entry_summary.get('action'), max_len=40) or action}",
            f"Entry reason: {_clip(entry_summary.get('reason_human'), max_len=220) or 'not_captured'}",
        ]
        + (
            [f"Selection decision: {item}" for item in _listify(scanner_reason.get("why_selected"), max_items=2, max_len=180)]
            or []
        )
        + (
            [f"Final decision basis: {_clip(scanner_reason.get('selection_basis'), max_len=220)}"]
            if _clip(scanner_reason.get("selection_basis"), max_len=220)
            else []
        ),
    }
    hold_count = len(list(holding_summary.get("run_ids") or []))
    holding_story = {
        "summary": _build_holding_story_summary(hold_count, monitor_reason, status_text),
        "bullets": _build_holding_story_bullets(holding_summary, monitor_reason),
    }
    if _clip(shared_seed.get("holding_duration"), max_len=80):
        holding_story["bullets"] = [f"Holding duration: {_clip(shared_seed.get('holding_duration'), max_len=80)}"] + list(
            holding_story.get("bullets") or []
        )
    exit_monitor_context = exit_summary.get("monitor_context") if isinstance(exit_summary.get("monitor_context"), dict) else {}
    if exit_monitor_context:
        exit_monitor_context = dict(exit_monitor_context)
    else:
        exit_monitor_context = dict(monitor_reason or {})
    exit_decision = {
        "summary": (
            _build_exit_decision_summary(exit_summary, exit_monitor_context, status_text=status_text)
            if bool(shared_seed.get("exit_exists")) or status_text.lower() != "open"
            else "Exit evidence is not captured yet because this lifecycle remains open."
        ),
        "bullets": _build_exit_decision_bullets(exit_summary, exit_monitor_context, status_text=status_text),
    }
    if _clip(shared_seed.get("exit_reason"), max_len=240):
        exit_decision["bullets"] = [f"Canonical exit reason: {_clip(shared_seed.get('exit_reason'), max_len=240)}"] + list(
            exit_decision.get("bullets") or []
        )
    execution_quality = {
        "summary": (
            _clip(execution_outcome.get("summary"), max_len=600)
            or _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=600)
            or "Execution quality details were not captured."
        ),
        "bullets": _listify(execution_outcome.get("bullets"), max_items=10, max_len=260),
    }
    reporter_eval = {
        "summary": _clip(reporter_status.get("summary"), max_len=600) or "Reporter linkage was not available yet.",
        "status": _clip(reporter_status.get("status"), max_len=40) or "missing",
        "grade": _clip(reporter_status.get("grade"), max_len=16) or "N/A",
        "bullets": _listify(reporter_status.get("bullets"), max_items=8, max_len=260),
    }
    weaknesses_bullets = warnings + [item for item in improvement_points if item not in warnings]
    full_timeline = [
        row
        for row in list(story_input.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]

    out = {
        "schema_version": "ai_trade_report.v2",
        "generated_at": _utc_now_iso(),
        "trade_id": trade_id,
        "story_id": _clip(story_input.get("story_id"), max_len=120) or trade_id,
        "run_id": _clip(story_input.get("run_id"), max_len=120),
        "symbol": symbol,
        "action": action,
        "status": status_text,
        "story_type": _clip(story_input.get("story_type"), max_len=40),
        "execution_mode_label": _clip(story_input.get("execution_mode_label"), max_len=80),
        "generation": {
            "status": status,
            "mode": mode,
            "model": _clip(model, max_len=120),
            "reason": _clip(reason, max_len=320),
        },
        "executive_summary": {
            "headline": f"{action} {symbol}",
            "action": action,
            "symbol": symbol,
            "confidence": confidence or "not_captured",
            "summary": executive_reason,
        },
        "market_context_at_entry": {
            "summary": market_context_summary,
            "bullets": _build_market_context_bullets(market_context),
            "regime": _clip(market_context.get("regime"), max_len=40),
            "market_sentiment": _clip(market_context.get("market_sentiment"), max_len=40),
            "playbook": _clip(market_context.get("playbook"), max_len=40),
            "themes": _listify(market_context.get("themes"), max_items=6, max_len=80),
            "global_sentiment_score": market_context.get("global_sentiment_score"),
            "vix_level": market_context.get("vix_level"),
            "stress_flags": _listify(market_context.get("stress_flags"), max_items=6, max_len=80),
            "strategist_candidate_hints": _listify(
                market_context.get("candidate_hints") or strategist_evidence.get("candidate_hints"), max_items=8, max_len=24
            ),
            "strategist_market_headlines": _listify(
                market_context.get("market_headlines") or strategist_evidence.get("market_headlines"), max_items=3, max_len=180
            ),
            "strategist_symbol_headlines": _listify(
                market_context.get("symbol_headlines") or strategist_evidence.get("symbol_headlines"), max_items=3, max_len=180
            ),
            "global_sentiment_signal": _compact_scalar_dict(
                market_context.get("global_sentiment_signal") or strategist_evidence.get("global_sentiment_signal"), max_items=8, max_len=120
            ),
            "fear_index": _compact_scalar_dict(
                market_context.get("fear_index") or strategist_evidence.get("fear_index"), max_items=8, max_len=120
            ),
            "key_events": _listify(
                market_context.get("key_events") or market_context.get("key_events_hint") or strategist_evidence.get("key_events"),
                max_items=6,
                max_len=180,
            ),
        },
        "why_this_symbol_was_chosen": {
            "summary": _clip(scanner_choice_summary or scanner_reason.get("summary"), max_len=600),
            "bullets": _listify(scanner_reason.get("bullets"), max_items=12, max_len=260),
            "selected_rank": scanner_reason.get("selected_rank"),
            "universe_size": scanner_reason.get("universe_size"),
            "symbol": _clip(scanner_reason.get("selected_symbol") or story_input.get("symbol"), max_len=32),
            "basis": _scanner_basis_text(scanner_reason),
            "strategist_candidate_hints": _listify(
                market_context.get("candidate_hints") or strategist_evidence.get("candidate_hints"), max_items=8, max_len=24
            ),
            "scanner_selection_trace": _as_dict(story_input.get("scanner_selection_trace")),
        },
        "entry_decision": entry_decision,
        "holding_monitoring_story": {
            **holding_story,
            "monitor_stop_policy_trace": _as_dict(story_input.get("monitor_stop_policy_trace")),
            "monitor_blocker_trace": _as_dict(story_input.get("monitor_blocker_trace")),
        },
        "exit_decision": exit_decision,
        "execution_quality": execution_quality,
        "monitor_snapshot": {
            **monitor_snapshot,
            "monitor_stop_policy_trace": _as_dict(story_input.get("monitor_stop_policy_trace")),
        },
        "scanner_filters": {
            "summary": _clip(filters_human.get("summary"), max_len=600),
            "bullets": _listify(filters_human.get("bullets"), max_items=12, max_len=260),
        },
        "guard_approval_result": {
            "summary": _clip(guard_reason.get("summary"), max_len=600),
            "bullets": _listify(guard_reason.get("bullets"), max_items=8, max_len=260),
        },
        "reporter_evaluation": reporter_eval,
        "errors_weaknesses_improvement_points": {
            "summary": (
                "Warnings and missing links were recorded for operator follow-up."
                if weaknesses_bullets
                else "No explicit weaknesses were surfaced beyond the recorded trace."
            ),
            "bullets": weaknesses_bullets,
        },
        "full_timeline": full_timeline,
        "timeline": full_timeline,
        "final_operator_conclusion": {
            "summary": _clip(operator_conclusion.get("summary"), max_len=600) or executive_reason,
            "current_action": _clip(operator_conclusion.get("current_action"), max_len=24) or action,
            "watch_next": _listify(operator_conclusion.get("watch_next"), max_items=6, max_len=200),
            "thesis_invalidation": _listify(operator_conclusion.get("thesis_invalidation"), max_items=6, max_len=200),
        },
        "shared_facts": {
            "symbol": symbol,
            "trade_id": trade_id,
            "action": action,
            "status": status_text,
            "holding_duration": _clip(shared_seed.get("holding_duration"), max_len=80) or "unavailable",
            "exit_reason": _clip(shared_seed.get("exit_reason"), max_len=280) or "unavailable",
            "pnl": shared_seed.get("pnl", "unavailable"),
            "pnl_pct": shared_seed.get("pnl_pct", "unavailable"),
            "data_source": dict((_as_dict(shared_seed.get("resolved_trade_facts")).get("data_source"))),
            "resolved_trade_facts": dict(shared_seed.get("resolved_trade_facts") or {}),
            "lifecycle_action": action,
            "lifecycle_status": status_text,
            "monitor_decision": dict(shared_seed.get("monitor_decision") or {}),
            "scanner_evidence_status": _clip(shared_seed.get("scanner_evidence_status"), max_len=24),
            "strategist_evidence_status": _clip(shared_seed.get("strategist_evidence_status"), max_len=24),
            "commander_route": dict(shared_seed.get("commander_route") or {}),
        },
    }
    # Backward-compatible aliases used by earlier UI/report consumers.
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return out


def _failure_report(
    story_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
    error: str = "",
) -> Dict[str, Any]:
    shared_seed = _build_shared_summary_seed(story_input)
    trade_id = _clip(shared_seed.get("trade_id"), max_len=120) or _clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120)
    action = _clip(shared_seed.get("lifecycle_action"), max_len=24) or _actual_lifecycle_action(story_input)
    symbol = _clip(shared_seed.get("symbol"), max_len=32) or _clip(story_input.get("symbol"), max_len=32) or "unknown"
    status_text = _clip(shared_seed.get("lifecycle_status"), max_len=32) or _clip(story_input.get("status"), max_len=32) or "unknown"
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    monitor_stop_trace = _as_dict(
        monitor_reason.get("monitor_stop_policy_trace")
        or story_input.get("monitor_stop_policy_trace")
    )
    full_timeline = [
        row
        for row in list(story_input.get("timeline") or [])
        if isinstance(row, dict)
    ][:24]
    out = {
        "schema_version": "ai_trade_report.v2",
        "generated_at": _utc_now_iso(),
        "trade_id": trade_id,
        "story_id": _clip(story_input.get("story_id"), max_len=120) or trade_id,
        "run_id": _clip(story_input.get("run_id"), max_len=120),
        "symbol": symbol,
        "action": action,
        "status": status_text,
        "story_type": _clip(story_input.get("story_type"), max_len=40),
        "execution_mode_label": _clip(story_input.get("execution_mode_label"), max_len=80),
        "generation": {
            "status": status,
            "mode": mode,
            "model": _clip(model, max_len=120),
            "reason": _clip(reason, max_len=320),
        },
        "failure": {
            "status": status,
            "reason": _clip(reason, max_len=320),
            "error": _clip(error, max_len=500),
        },
        "executive_summary": {
            "headline": f"AI trade report failed for {symbol}",
            "action": action,
            "symbol": symbol,
            "confidence": "not_available",
            "summary": "AI trade report generation failed after retry attempts. Review the saved LLM response artifact for details.",
        },
        "market_context_at_entry": {
            "summary": "AI generation failed before a rendered market-context section was produced.",
            "bullets": [],
        },
        "why_this_symbol_was_chosen": {
            "summary": "AI generation failed before a rendered symbol-selection section was produced.",
            "bullets": [],
        },
        "entry_decision": {
            "summary": "AI generation failed before a rendered entry-decision section was produced.",
            "bullets": [],
        },
        "holding_monitoring_story": {
            "summary": "AI generation failed before a rendered holding-monitoring section was produced.",
            "bullets": _listify(monitor_reason.get("bullets"), max_items=8, max_len=260),
        },
        "exit_decision": {
            "summary": "AI generation failed before a rendered exit-decision section was produced.",
            "bullets": [],
        },
        "execution_quality": {
            "summary": "AI generation failed before a rendered execution-quality section was produced.",
            "bullets": [],
        },
        "monitor_snapshot": {
            "posture": _clip(monitor_reason.get("posture"), max_len=40) or action or "WAIT",
            "trigger_type": _clip(monitor_reason.get("trigger_type"), max_len=80) or "not_captured",
            "position_age_seconds": int(monitor_reason.get("position_age_seconds") or 0),
            "hard_stop_pct": monitor_reason.get("hard_stop_pct") or monitor_stop_trace.get("hard_stop_pct"),
            "adaptive_stop_loss_pct": monitor_reason.get("adaptive_stop_loss_pct") or monitor_stop_trace.get("adaptive_stop_loss_pct"),
            "stop_loss_pct": monitor_reason.get("stop_loss_pct"),
            "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct") or monitor_stop_trace.get("effective_stop_loss_pct"),
            "effective_stop_reason": _clip(monitor_reason.get("effective_stop_reason"), max_len=80) or "not_captured",
            "strategist_baseline_stop_loss_pct": monitor_reason.get("strategist_baseline_stop_loss_pct")
            or monitor_stop_trace.get("strategist_baseline_stop_loss_pct"),
            "strategist_baseline_take_profit_pct": monitor_reason.get("strategist_baseline_take_profit_pct")
            or monitor_stop_trace.get("strategist_baseline_take_profit_pct"),
            "strategist_baseline_trailing_stop_pct": monitor_reason.get("strategist_baseline_trailing_stop_pct")
            or monitor_stop_trace.get("strategist_baseline_trailing_stop_pct"),
            "take_profit_pct": monitor_reason.get("take_profit_pct") or monitor_stop_trace.get("take_profit_pct"),
            "trailing_stop_pct": monitor_reason.get("trailing_stop_pct") or monitor_stop_trace.get("trailing_stop_pct"),
            "exit_triggered": bool(monitor_reason.get("exit_triggered")),
            "current_price": monitor_reason.get("current_price"),
            "average_price": monitor_reason.get("average_price"),
            "peak_price": monitor_reason.get("peak_price"),
            "current_drawdown": monitor_reason.get("current_drawdown"),
            "peak_drawdown": monitor_reason.get("peak_drawdown"),
            "vwap_distance": monitor_reason.get("vwap_distance"),
            "active_exit_axis": _clip(monitor_reason.get("active_exit_axis"), max_len=80),
            "watch_axes": _listify(monitor_reason.get("watch_axes"), max_items=8, max_len=120),
            "price_source": _clip(monitor_reason.get("price_source"), max_len=120) or "not_captured",
            "feature_source": _clip(monitor_reason.get("feature_source"), max_len=120) or "not_captured",
            "price_source_policy": _clip(monitor_reason.get("price_source_policy"), max_len=260) or "",
        },
        "scanner_filters": {
            "summary": "AI generation failed before a rendered scanner-filter section was produced.",
            "bullets": [],
        },
        "guard_approval_result": {
            "summary": "AI generation failed before a rendered guard-approval section was produced.",
            "bullets": [],
        },
        "reporter_evaluation": {
            "summary": _clip(reporter_status.get("summary"), max_len=600) or "Reporter linkage status was recorded separately.",
            "status": _clip(reporter_status.get("status"), max_len=40) or "missing",
            "grade": _clip(reporter_status.get("grade"), max_len=16) or "N/A",
            "bullets": _listify(reporter_status.get("bullets"), max_items=8, max_len=260),
        },
        "errors_weaknesses_improvement_points": {
            "summary": "AI generation failed and no rendered improvement section is available.",
            "bullets": [entry for entry in [_clip(reason, max_len=240), _clip(error, max_len=240)] if entry],
        },
        "full_timeline": full_timeline,
        "timeline": full_timeline,
        "final_operator_conclusion": {
            "summary": "AI generation failed. Review lifecycle artifacts and the saved LLM response artifact before taking action.",
            "current_action": "HOLD" if status_text.lower() == "open" and action == "BUY" else action,
            "watch_next": [],
            "thesis_invalidation": [],
        },
    }
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return _normalize_trade_report_output(story_input, out)


def build_separated_ai_trade_report(trade_dir: str, *, model: Optional[str] = None) -> Dict[str, Any]:
    """Phase 6-1 Task 4 Compatibility Wrapper."""
    from libs.reporting.trade_read_model import build_trade_read_model
    from libs.reporting.fact_narrative_report import build_separated_report
    try:
        trade_model = build_trade_read_model(str(trade_dir))
    except Exception:
        trade_model = {}
    chosen_model = normalize_openrouter_model_name(
        str(model or "").strip()
        or str(os.getenv("OPENROUTER_MODEL_TRADE_REPORT", "")).strip()
        or str(os.getenv("TRADE_REPORT_AI_MODEL", "")).strip()
        or str(os.getenv("OPENROUTER_DEFAULT_MODEL", "")).strip()
        or "openrouter/auto"
    )
    return build_separated_report(trade_model=trade_model, model=chosen_model)


def _trade_report_output_template() -> Dict[str, Any]:
    return {
        "executive_summary": {"headline": "", "summary": ""},
        "market_context_at_entry": {"summary": "", "bullets": [""]},
        "why_this_symbol_was_chosen": {"summary": "", "bullets": [""]},
        "entry_decision": {"summary": "", "bullets": [""]},
        "holding_monitoring_story": {"summary": "", "bullets": [""]},
        "exit_decision": {"summary": "", "bullets": [""]},
        "execution_quality": {"summary": "", "bullets": [""]},
        "scanner_filters": {"summary": "", "bullets": [""]},
        "guard_approval_result": {"summary": "", "bullets": [""]},
        "reporter_evaluation": {"summary": "", "bullets": [""]},
        "errors_weaknesses_improvement_points": {"summary": "", "bullets": [""]},
        "full_timeline": [{"event": "", "ts": "", "description": ""}],
        "final_operator_conclusion": {"summary": "", "watch_next": [""], "thesis_invalidation": [""]},
    }


def _trade_report_language_meta(candidate: Dict[str, Any]) -> Dict[str, Any]:
    sample_fields: List[str] = []

    def _collect(section: Any) -> None:
        if isinstance(section, dict):
            for key, value in section.items():
                if key in {"headline", "summary", "description"} and str(value or "").strip():
                    sample_fields.append(str(value or "").strip())
                elif key in {"bullets", "watch_next", "thesis_invalidation"} and isinstance(value, list):
                    for row in value:
                        if str(row or "").strip():
                            sample_fields.append(str(row or "").strip())
                elif key == "full_timeline" and isinstance(value, list):
                    for row in value:
                        if isinstance(row, dict) and str(row.get("description") or "").strip():
                            sample_fields.append(str(row.get("description") or "").strip())
                elif isinstance(value, dict):
                    _collect(value)

    _collect(candidate)
    hangul_total = sum(_count_hangul(item) for item in sample_fields)
    latin_total = sum(_count_latin(item) for item in sample_fields)
    forbidden_cjk_total = sum(_count_forbidden_cjk_or_japanese(item) for item in sample_fields)
    english_like = [
        item
        for item in sample_fields
        if _count_hangul(item) == 0 and _count_latin(item) >= 8
    ]
    requires_korean_repair = bool(
        sample_fields
        and len(english_like) >= 6
        and (hangul_total == 0 or hangul_total < max(20, latin_total * 0.2))
    )
    if forbidden_cjk_total > 0:
        requires_korean_repair = True
    return {
        "language_sample_count": len(sample_fields),
        "language_hangul_chars": hangul_total,
        "language_latin_chars": latin_total,
        "language_english_like_count": len(english_like),
        "language_forbidden_cjk_chars": forbidden_cjk_total,
        "requires_korean_repair": requires_korean_repair,
    }


def _build_repair_messages(
    story_input: Dict[str, Any],
    raw_response: Any,
    *,
    sparse: bool = False,
    enforce_korean: bool = False,
) -> List[Dict[str, str]]:
    compact_input = _sparse_story_input_for_llm(story_input) if sparse else _compact_story_input_for_llm(story_input)
    contract = _trade_report_output_template()
    previous_response = str(raw_response or "").strip()
    previous_parse = parse_llm_json_response(previous_response)
    previous_response_text = "[previous response was non-JSON reasoning or invalid text; ignore it]"
    if bool(previous_parse.get("is_full")):
        previous_response_text = previous_response[:1800]
    elif bool(previous_parse.get("is_partial")) and isinstance(previous_parse.get("partial_object"), dict):
        previous_response_text = json.dumps(previous_parse.get("partial_object") or {}, ensure_ascii=False)[:1800]
    partial_note = ""
    if str(story_input.get("status") or "").strip().lower() == "partial":
        partial_note = (
            "\n이 lifecycle은 partial 상태입니다. 일부 entry 또는 holding 근거가 비어 있습니다. "
            "확인되지 않은 진입 근거는 만들어 쓰지 말고, 저장되지 않았다고 명확히 적으십시오."
        )
    shape_note = ""
    if sparse:
        shape_note = (
            "\n이번 단계는 마지막 복구 패스입니다. 각 summary는 2문장 이하로 유지하고, 각 섹션의 bullets는 1개에서 3개만 작성하며, "
            "full_timeline은 최대 8개 행까지만 유지하십시오."
        )
    language_note = ""
    if enforce_korean:
        language_note = (
            "\n최종 JSON을 반환하기 전에 남아 있는 영어 설명 문장을 모두 한국어로 번역하십시오. "
            "JSON 키, 타임스탬프, 숫자, 액션 코드, 종목코드는 그대로 유지하십시오."
        )
    return [
        {
            "role": "system",
            "content": (
                "당신은 AI 거래 리포트 출력을 복구하는 역할입니다. 반드시 JSON 객체 하나만 반환하십시오. "
                "설명문, 사고 과정, 지시문 반복, markdown, code fence는 모두 금지합니다. "
                "'먼저', '우선', 'First, I need' 같은 계획 문장은 절대 쓰지 마십시오. JSON 앞에 어떤 텍스트가 있어도 실패입니다. "
                "출력은 반드시 '{'로 시작하고 '}'로 끝나야 하며, JSON 키는 계약과 정확히 일치해야 합니다. "
                f"{AI_TRADE_REPORT_KOREAN_RULES} "
                "값을 알 수 없으면 추측하지 말고 빈 문자열, 빈 리스트, 또는 null을 사용하십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                "이전 응답이 요구된 JSON 계약을 만족하지 못했습니다. 유효한 JSON만 다시 생성하십시오.\n"
                f"출력 템플릿:\n{json.dumps(contract, ensure_ascii=False)}\n"
                "템플릿 값만 실제 리포트 내용으로 채우고, 키 이름과 중첩 구조는 그대로 유지하십시오."
                f"{partial_note}{shape_note}{language_note}\n\n"
                "원본 입력이 영어로 적혀 있어도 그대로 복사하지 말고 한국어로 옮겨 쓰십시오.\n"
                "핵심 evidence 규칙:\n"
                "- market_context_human에 headline_count, news_query_count, news_query_targets, key_events_hint가 있으면 market_context_at_entry에 반영하십시오.\n"
                "- scanner_reason_human에 why_selected, selection_basis, tie_break_rule, top_candidates, runner_ups_lost가 있으면 why_this_symbol_was_chosen과 entry_decision에 반영하십시오.\n"
                "- monitor_reason_human에 effective_stop_loss_pct, take_profit_pct, active_exit_axis, watch_axes, confirm_required, confirm_count, decision_reason_chain이 있으면 holding_monitoring_story와 exit_decision에 반영하십시오.\n"
                "- 구체적인 숫자 근거를 모호한 표현으로 바꾸지 마십시오.\n"
                f"입력:\n{json.dumps(compact_input, ensure_ascii=False)}\n\n"
                f"이전 응답:\n{previous_response_text}"
            ),
        },
    ]


def _build_messages(story_input: Dict[str, Any]) -> List[Dict[str, str]]:
    compact_input = _sparse_story_input_for_llm(story_input)
    contract = _trade_report_output_template()
    partial_note = ""
    if str(story_input.get("status") or "").strip().lower() == "partial":
        partial_note = (
            "이 lifecycle은 partial 상태입니다. 일부 entry 또는 holding 근거가 비어 있습니다. "
            "확인되지 않은 진입 근거는 만들어 쓰지 말고, 저장되지 않았다고 명확히 적으십시오.\n"
        )
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 사후 거래 복기용 AI 거래 리포트를 작성합니다. "
                "이 문서는 operator_brief 같은 즉시 상황 스냅샷이 아니라 trade lifecycle retrospective입니다. "
                "반드시 제공된 입력만 사용하고, 숫자, 이벤트, 이유, evidence를 지어내지 마십시오. "
                "반드시 JSON 객체 하나만 반환하십시오. markdown, JSON 앞 설명문, 분석 문장, code fence는 금지합니다. "
                "'먼저', '우선', 'First, I need' 같은 계획 문장은 절대 쓰지 마십시오. JSON 앞의 모든 텍스트는 실패입니다. "
                "출력은 반드시 '{'로 시작하고 '}'로 끝나야 하며, JSON 키는 계약과 정확히 일치해야 합니다. "
                f"{AI_TRADE_REPORT_KOREAN_RULES} "
                "값을 알 수 없으면 추측하지 말고 빈 문자열, 빈 리스트, 또는 null을 사용하십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                "아래 trade story input을 바탕으로 trade lifecycle retrospective AI 거래 리포트를 작성하십시오.\n"
                "파이프라인 순서는 strategist -> scanner -> monitor -> supervisor -> executor -> reporter를 정확히 따라야 합니다.\n"
                "이 리포트는 즉시 대응용 snapshot이 아니라 사후 복기 문서입니다.\n"
                "반드시 다음 질문에 답할 수 있게 작성하십시오: 왜 진입했는가, 왜 보유했는가, 왜 청산했는가, 실행 품질은 어땠는가, 다음에는 무엇을 개선할 것인가.\n"
                "작성 요구사항:\n"
                "- global sentiment score, VIX, headline count, query-target count가 있으면 구체적인 숫자를 그대로 반영하십시오.\n"
                "- 시장 환경 요약에는 headline_count, news_query_count, news_query_targets, key_events_hint를 우선 반영하십시오.\n"
                "- scanner 후보 수, 선택 종목, runner-up, Kiwoom source mix(top_value, top_volume, sector_theme 등), score breakdown, feature coverage를 설명하십시오.\n"
                "- 선택 종목 상세 분석에는 why_selected, selection_basis, tie_break_rule, top_candidates, runner_ups_lost를 가능한 한 직접 반영하십시오.\n"
                "- Entry 상세 근거에서는 generic한 문장을 반복하지 말고 strategist guidance와 scanner ranking이 어떻게 연결됐는지 설명하십시오.\n"
                "- monitor thresholds와 watch axes, stop, effective stop, 목표 수익 실현 기준, 현재가, price source를 설명하십시오.\n"
                "- Holding 경과와 Exit 판단 근거에는 active_exit_axis, confirm_required, confirm_count, decision_reason_chain, watch_axes를 가능한 한 직접 반영하십시오.\n"
                "- supervisor 승인과 executor 결과는 분리해서 설명하십시오.\n"
                "- reporter linkage가 없으면 그 사실을 한국어로 명확하게 설명하십시오.\n"
                "- 사람이 읽는 모든 문장은 한국어로 옮겨 쓰고, 영어 source 문장을 그대로 복사하지 마십시오.\n"
                "- 종목코드, JSON 키, BUY/SELL/HOLD/WAIT 액션 코드, VIX, Kiwoom source id, 타임스탬프는 그대로 유지하십시오.\n"
                "- deterministic report skeleton은 이미 존재하므로 메타데이터를 다시 만들지 말고 section narrative content만 채우십시오.\n"
                "- section summary, ranked comparison, monitor reasoning, operator-facing bullets에 집중하십시오.\n"
                "- strategist evidence fields(candidate hints, market headlines, symbol headlines)가 있으면 시장/전략가 evidence를 별도 문장으로 명확히 설명하십시오.\n"
                "- scanner_selection_trace가 있으면 strategist hints -> ranked candidates -> selected symbol -> selection reason -> score drivers 순서를 유지하십시오.\n"
                "- monitor_stop_policy_trace가 있으면 hard fail-safe stop, adaptive stop, effective stop, trailing stop, take profit을 서로 다른 층위로 구분해 설명하십시오.\n"
                "- adaptive stop이 있으면 stop을 단일 3% 규칙처럼 뭉뚱그리지 말고 실제 active stop을 명시하십시오.\n"
                f"{partial_note}"
                "아래 JSON 템플릿에 값만 채워 반환하십시오:\n"
                f"{json.dumps(contract, ensure_ascii=False)}\n"
                "evidence가 있으면 각 section에 bullets를 3개에서 6개까지 작성하십시오.\n"
                "summary는 간결하되 운영 판단에 실제로 도움이 되게 쓰십시오.\n"
                "입력에 ranked comparison detail이 있으면 생략하지 마십시오.\n"
                "section narrative field 바깥에서 action/symbol/status 메타를 반복하지 마십시오.\n"
                f"입력:\n{json.dumps(compact_input, ensure_ascii=False)}"
            ),
        },
    ]


def _canonical_ai_report_status(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in {"ok", "partial", "salvaged", "error", "skipped"}:
        return raw
    if raw in {"repaired"}:
        return "ok"
    if raw in {"disabled", "fallback", "unavailable", "dry_run"}:
        return "skipped"
    return "error"


def _attach_report_status_matrix(
    report: Dict[str, Any],
    story_input: Dict[str, Any],
    *,
    ai_trade_report_status: Any,
    deterministic_report_status: Any = "ok",
) -> Dict[str, Any]:
    out = dict(report or {})
    diagnostics = story_input.get("ai_report_diagnostics") if isinstance(story_input.get("ai_report_diagnostics"), dict) else {}
    llm_brief_status = _canonical_ai_report_status(diagnostics.get("llm_brief_status") or "skipped")
    out["deterministic_report_status"] = _canonical_ai_report_status(deterministic_report_status)
    out["llm_brief_status"] = llm_brief_status
    out["ai_trade_report_status"] = _canonical_ai_report_status(ai_trade_report_status)
    generation = out.get("generation") if isinstance(out.get("generation"), dict) else {}
    generation["deterministic_report_status"] = out["deterministic_report_status"]
    generation["llm_brief_status"] = out["llm_brief_status"]
    generation["ai_trade_report_status"] = out["ai_trade_report_status"]
    out["generation"] = generation
    if "fact_payload" not in out or "narrative" not in out:
        try:
            from libs.reporting.fact_narrative_report import build_separated_report

            separated = build_separated_report(
                trade_model=dict(story_input or {}),
                model=str(generation.get("model") or "").strip() or None,
            )
        except Exception:
            separated = {
                "fact_payload": {"trade": dict(story_input or {}), "daily": {}, "symbol": {}},
                "narrative": {
                    "summary": "",
                    "insight": "",
                    "recommendation": "",
                    "source": "llm",
                    "based_on": "fact_payload",
                    "status": "error",
                },
            }
        if isinstance(separated.get("fact_payload"), dict):
            out["fact_payload"] = dict(separated.get("fact_payload") or {})
        if isinstance(separated.get("narrative"), dict):
            out["narrative"] = dict(separated.get("narrative") or {})
    return out


def build_deterministic_trade_report(story_input: Dict[str, Any]) -> Dict[str, Any]:
    report = _fallback_report(
        story_input,
        status="ok",
        mode="deterministic",
        model="",
        reason="deterministic_report_generated",
    )
    return _attach_report_status_matrix(
        report,
        story_input,
        ai_trade_report_status="skipped",
        deterministic_report_status="ok",
    )


def build_ai_trade_report(
    story_input: Dict[str, Any],
    *,
    enabled: Optional[bool] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    is_enabled = _env_bool("TRADE_REPORT_AI_ENABLED", True) if enabled is None else bool(enabled)
    chosen_model = normalize_openrouter_model_name(
        str(model or "").strip()
        or str(os.getenv("OPENROUTER_MODEL_TRADE_REPORT", "")).strip()
        or str(os.getenv("TRADE_REPORT_AI_MODEL", "")).strip()
        or str(os.getenv("OPENROUTER_DEFAULT_MODEL", "")).strip()
        or "openrouter/auto"
    )
    trade_id = str(story_input.get("trade_id") or story_input.get("story_id") or "")
    run_id = str(story_input.get("run_id") or "")
    day = str(story_input.get("day") or "")
    retry_max = max(0, int(float(str(os.getenv("TRADE_REPORT_AI_RETRY_MAX", "2")).strip() or "2")))
    empty_required_meta = {
        "parse_mode": "none",
        "required_keys_expected": list(AI_TRADE_REPORT_REQUIRED_KEYS),
        "required_keys_present": [],
        "required_keys_missing": list(AI_TRADE_REPORT_REQUIRED_KEYS),
        "completeness_score": 0.0,
        "used_fallback_sections": [],
    }
    if not is_enabled:
        report = _failure_report(
            story_input,
            status="disabled",
            mode="fallback",
            model=chosen_model,
            reason="TRADE_REPORT_AI_ENABLED is false",
        )
        report["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status="fallback",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or "openrouter/free"},
            meta={"reason": "TRADE_REPORT_AI_ENABLED is false", **empty_required_meta},
        )
        return _attach_report_status_matrix(report, story_input, ai_trade_report_status="skipped")

    router = LLMRouter.from_env()
    if router.client is None:
        report = _failure_report(
            story_input,
            status="error",
            mode="ai",
            model=chosen_model,
            reason="OPENROUTER_API_KEY is not configured",
        )
        report["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status="error",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or "openrouter/free"},
            meta={"reason": "OPENROUTER_API_KEY is not configured", "error": "llm_client_unavailable", **empty_required_meta},
        )
        return _attach_report_status_matrix(report, story_input, ai_trade_report_status="error")

    temp = float(
        temperature
        if temperature is not None
        else str(os.getenv("TRADE_REPORT_AI_TEMPERATURE", "0.0")).strip() or "0.0"
    )
    token_budget = (
        int(max_tokens)
        if max_tokens is not None
        else _env_int_with_fallback(
            "TRADE_REPORT_AI_MAX_TOKENS",
            "OPENROUTER_DEFAULT_MAX_TOKENS",
            default=1400,
        )
    )
    retry_token_budget = _env_int_with_fallback(
        "TRADE_REPORT_AI_REPAIR_MAX_TOKENS",
        "TRADE_REPORT_AI_MAX_TOKENS",
        "OPENROUTER_DEFAULT_MAX_TOKENS",
        default=max(800, token_budget),
    )
    messages = _build_messages(story_input)
    attempts: List[Dict[str, Any]] = []
    resolved_model = str(
        router.resolve(
            "trade_report",
            policy={
                "temperature": temp,
                "max_tokens": max(600, token_budget),
                **({"model": chosen_model} if chosen_model else {}),
            },
        ).model
    )
    final_status = "error"
    final_reason = ""
    final_error = ""
    final_latency_ms = 0
    parsed: Optional[Dict[str, Any]] = None
    best_partial: Dict[str, Any] = {}
    best_partial_meta: Dict[str, Any] = {}
    raw = ""
    current_messages = list(messages)
    current_policy = {
        "temperature": temp,
        "max_tokens": max(600, token_budget),
        "response_format": {"type": "json_object"},
        "plugins": [{"id": "response-healing"}],
        **({"model": chosen_model} if chosen_model else {}),
    }
    for attempt_index in range(retry_max + 1):
        step = "primary" if attempt_index == 0 else f"retry_{attempt_index}"
        needs_korean_repair = False
        t0 = time.perf_counter()
        try:
            raw = router.chat("trade_report", current_messages, policy=current_policy)
        except Exception as exc:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            final_status = classify_llm_exception(exc)
            final_reason = f"trade_report_ai_exception:{type(exc).__name__}:{exc}"
            final_error = f"{type(exc).__name__}:{exc}"
            attempts.append(
                make_attempt(
                    step=step,
                    messages=current_messages,
                    raw_response_text=f"ERROR:{final_error}",
                    parsed_output={},
                    model=chosen_model or resolved_model,
                    latency_ms=final_latency_ms,
                    status=final_status,
                    meta={"role": "ai_trade_report", "error": final_error},
                )
            )
        else:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            parse_result = parse_llm_json_response(raw)
            candidate = parse_result.get("full_object") if isinstance(parse_result.get("full_object"), dict) else parse_result.get("partial_object")
            candidate = dict(candidate) if isinstance(candidate, dict) else {}
            parse_meta = _trade_report_parse_meta(raw, candidate)
            language_meta = _trade_report_language_meta(candidate) if candidate else {
                "language_sample_count": 0,
                "language_hangul_chars": 0,
                "language_latin_chars": 0,
                "language_english_like_count": 0,
                "requires_korean_repair": False,
            }
            if not bool(parse_result.get("raw_nonempty")):
                final_status = "empty_response"
                final_reason = "trade_report_ai returned an empty response"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output={},
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta},
                    )
                )
            elif bool(parse_result.get("is_full")) and not parse_meta.get("required_keys_missing"):
                if bool(language_meta.get("requires_korean_repair")) and attempt_index < retry_max:
                    final_status = "partial"
                    final_reason = "trade_report_ai returned valid JSON but human-readable sections remained mostly English"
                    needs_korean_repair = True
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=candidate,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta},
                        )
                    )
                else:
                    parsed = candidate
                    final_reason = ""
                    final_status = "ok"
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=parsed,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={"role": "ai_trade_report", **parse_meta, **language_meta},
                        )
                    )
                    break
            elif bool(parse_result.get("is_partial")) and candidate and not parse_meta.get("required_keys_missing"):
                if attempt_index < retry_max:
                    final_status = "partial"
                    final_reason = "trade_report_ai returned a complete JSON object with extra non-JSON text; retrying strict JSON-only regeneration"
                    needs_korean_repair = bool(language_meta.get("requires_korean_repair"))
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=candidate,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta},
                        )
                    )
                else:
                    parsed = candidate
                    final_status = "ok"
                    final_reason = ""
                    attempts.append(
                        make_attempt(
                            step=step,
                            messages=current_messages,
                            raw_response_text=raw,
                            parsed_output=parsed,
                            model=chosen_model or resolved_model,
                            latency_ms=final_latency_ms,
                            status=final_status,
                            meta={
                                "role": "ai_trade_report",
                                "finish_reason": "complete_json_extracted_after_protocol_deviation",
                                **parse_meta,
                                **language_meta,
                            },
                        )
                    )
                    break
            elif candidate:
                best_partial = dict(candidate)
                best_partial_meta = dict(parse_meta)
                final_status = "partial"
                missing = list(parse_meta.get("required_keys_missing") or [])
                if bool(parse_result.get("is_partial")):
                    final_reason = "trade_report_ai returned truncated or partial JSON"
                elif missing:
                    final_reason = f"trade_report_ai response is missing required keys: {', '.join(missing)}"
                else:
                    final_reason = "trade_report_ai response was incomplete"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output=candidate,
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta},
                    )
                )
            else:
                final_status = "parse_error"
                final_reason = "trade_report_ai returned non-JSON response"
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output={},
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status=final_status,
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta},
                    )
                )
        if attempt_index < retry_max:
            if final_status in {"parse_error", "partial"}:
                current_messages = _build_repair_messages(
                    story_input,
                    raw,
                    sparse=(attempt_index + 1) >= retry_max,
                    enforce_korean=needs_korean_repair,
                )
            current_policy = {
                **current_policy,
                "temperature": 0.0,
                "max_tokens": max(800, retry_token_budget),
            }

    if not parsed and best_partial:
        final_status = "salvaged"
        final_reason = final_reason or "trade_report_ai returned incomplete JSON; deterministic sections were salvaged from the partial response"
        out = _merge_trade_report_candidate(
            story_input,
            best_partial,
            status=final_status,
            mode="ai",
            model=chosen_model or resolved_model,
            reason=final_reason,
        )
        out["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status=final_status,
            attempts=attempts,
            parsed_output=best_partial,
            model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
            latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
            meta={
                "reason": final_reason,
                "error": final_error,
                **best_partial_meta,
                "used_fallback_sections": list(out.get("used_fallback_sections") or []),
            },
        )
        return _attach_report_status_matrix(out, story_input, ai_trade_report_status=final_status)

    if not parsed:
        report = _failure_report(
            story_input,
            status=final_status,
            mode="ai",
            model=chosen_model or resolved_model,
            reason=final_reason or "AI trade report generation failed",
            error=final_error,
        )
        report["llm_response_artifact"] = build_llm_response_artifact(
            component="ai_trade_report",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status=final_status,
            attempts=attempts,
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
            latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
            meta={"reason": final_reason, "error": final_error, **empty_required_meta},
        )
        return _attach_report_status_matrix(report, story_input, ai_trade_report_status=final_status)

    parse_meta = _trade_report_parse_meta(raw, parsed)
    out = _merge_trade_report_candidate(
        story_input,
        parsed,
        status=final_status,
        mode="ai",
        model=chosen_model or resolved_model,
        reason=final_reason,
    )
    out["llm_response_artifact"] = build_llm_response_artifact(
        component="ai_trade_report",
        run_id=run_id,
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        status=final_status,
        attempts=attempts,
        parsed_output=parsed,
        model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
        latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
        meta={
            **parse_meta,
            "reason": final_reason,
            "used_fallback_sections": list(out.get("used_fallback_sections") or []),
        },
    )
    return _attach_report_status_matrix(out, story_input, ai_trade_report_status=final_status)


def render_trade_report_markdown(report: Dict[str, Any]) -> str:
    def _action_label(value: Any) -> str:
        mapping = {
            "BUY": "매수",
            "SELL": "매도",
            "HOLD": "보유 유지",
            "WAIT": "진입 보류",
        }
        raw = _clip(value, max_len=64)
        return mapping.get(str(raw or "").strip().upper(), raw or "-")

    def _axis_label(value: Any) -> str:
        raw = _clip(value, max_len=120)
        lowered = str(raw or "").strip().lower()
        mapping = {
            "hard stop": "고정 손절 기준",
            "hard_stop": "고정 손절 기준",
            "adaptive stop": "상황 대응형 손절 기준",
            "adaptive_stop": "상황 대응형 손절 기준",
            "take profit": "목표 수익 실현 기준",
            "take_profit": "목표 수익 실현 기준",
            "trailing stop": "추적 손절",
            "trailing_stop": "추적 손절",
            "vwap breakdown": "VWAP 이탈",
            "vwap_breakdown": "VWAP 이탈",
            "peak drawdown": "고점 대비 하락폭 확대",
            "peak_drawdown": "고점 대비 하락폭 확대",
            "prior low break": "직전 저점 이탈",
            "prior_low_break": "직전 저점 이탈",
            "intraday low break": "장중 저점 이탈",
            "intraday_low_break": "장중 저점 이탈",
            "confirmed_exit_signal": "청산 확인 신호",
            "defensive exit": "방어형 청산 신호",
            "defensive_exit": "방어형 청산 신호",
            "no trigger yet": "아직 청산 신호가 확인되지 않음",
        }
        return mapping.get(lowered, raw or "-")

    def _meta_label(value: Any) -> str:
        raw = _clip(value, max_len=160)
        lowered = str(raw or "").strip().lower()
        mapping = {
            "simulation trade report": "시뮬레이션 거래 리포트",
            "simulation": "시뮬레이션",
            "live trade report": "실거래 거래 리포트",
            "integrated_chain": "통합 체인",
            "simulation (mock broker)": "시뮬레이션 (모의 브로커)",
            "live": "실거래",
            "open": "열림",
            "closed": "종결",
        }
        return mapping.get(lowered, raw or "-")

    def _metadata_value(value: Any) -> str:
        raw = _clip(value, max_len=240).strip()
        lowered = raw.lower()
        if not raw:
            return ""
        if lowered in {"unknown", "not available", "not_available", "unavailable"}:
            return "확인되지 않음"
        if lowered in {"not captured", "not_captured"}:
            return "기록되지 않음"
        confidence_mapping = {
            "high": "높음",
            "medium": "보통",
            "low": "낮음",
        }
        return confidence_mapping.get(lowered, raw)

    def _metadata_line(label: str, value: Any) -> str:
        rendered = _metadata_value(value)
        if not rendered:
            return ""
        return f"- {label}: {rendered}"

    def _render_text(text: Any) -> str:
        cleaned = _operatorize_report_text(text)
        if not cleaned:
            return ""
        lowered = cleaned.lower()
        exact_mapping = {
            "position is still open; no closing sell execution has been captured yet.": "아직 청산 체결이 확인되지 않아 포지션이 열린 상태로 남아 있습니다.",
            "exit reasoning was not captured.": "청산 판단 근거가 충분히 저장되지 않았습니다.",
            "reporter linkage was not available yet.": "Reporter 연계 결과는 아직 연결되지 않았습니다.",
            "reporter linkage status was recorded separately.": "Reporter 연계 상태는 별도 메타에 기록되어 있습니다.",
            "the decision path was recorded, but the operator-facing summary is limited.": "의사결정 경로는 기록되었지만 운영자용 요약은 제한적으로만 남아 있습니다.",
            "no timeline entries were captured.": "타임라인 이벤트는 별도로 저장되지 않았습니다.",
            "open trade": "아직 포지션이 열린 상태입니다.",
            "hold": "현재 포지션은 계속 보유 중입니다.",
        }
        if lowered in exact_mapping:
            return exact_mapping[lowered]

        m = re.fullmatch(r"Monitor runs:\s*(\d+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"모니터 실행 횟수는 {m.group(1)}회였습니다."
        m = re.fullmatch(r"Posture:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재 포지션 판단은 {_action_label(m.group(1))}입니다."
        m = re.fullmatch(r"Trigger type:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"감지된 신호 유형은 {_axis_label(m.group(1))}입니다."
        m = re.fullmatch(r"Position age:\s*(\d+)\s*seconds", cleaned, flags=re.IGNORECASE)
        if m:
            return f"포지션 유지 시간은 약 {m.group(1)}초입니다."
        m = re.fullmatch(r"Effective stop:\s*([^(]+?)(?:\s*\((.+)\))?", cleaned, flags=re.IGNORECASE)
        if m:
            level = _clip(m.group(1), max_len=64)
            reason = _axis_label(m.group(2))
            if reason and reason != "-":
                return f"유효 손절 기준은 {level} 수준이며, 기준 축은 {reason}입니다."
            return f"유효 손절 기준은 {level} 수준입니다."
        m = re.fullmatch(r"Take profit:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"목표 수익 실현 기준은 {_clip(m.group(1), max_len=80)} 수준입니다."
        m = re.fullmatch(r"Active exit axis:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재 우선 감시 중인 청산 축은 {_axis_label(m.group(1))}입니다."
        m = re.fullmatch(r"Exit confirmation:\s*(\d+)/(\d+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 확인 조건은 {m.group(1)}/{m.group(2)} 수준으로 집계됐습니다."
        m = re.fullmatch(r"Watch axes:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            axes = ", ".join(_axis_label(part.strip()) for part in m.group(1).split(","))
            return f"주요 감시 축은 {axes}입니다."
        m = re.fullmatch(r"Decision chain:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"판단 흐름은 {_clip(m.group(1), max_len=200)} 순서로 이어졌습니다."
        m = re.fullmatch(r"Current price / avg / peak:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재가, 평균단가, 장중 고점은 {_clip(m.group(1), max_len=180)}입니다."
        m = re.fullmatch(r"Current drawdown / peak drawdown:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재 손익 변동과 고점 대비 하락폭은 {_clip(m.group(1), max_len=180)}입니다."
        m = re.fullmatch(r"Price source:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"가격 기준 소스는 {_clip(m.group(1), max_len=120)}입니다."
        m = re.fullmatch(r"Feature source:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"피처 기준 소스는 {_clip(m.group(1), max_len=120)}입니다."
        m = re.fullmatch(r"Recent monitor update:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"최근 모니터 업데이트는 다음과 같습니다: {_clip(m.group(1), max_len=240)}"
        m = re.fullmatch(r"Exit run:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 판단은 {_clip(m.group(1), max_len=120)} run에서 기록되었습니다."
        m = re.fullmatch(r"Exit time:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 판단 시각은 {_clip(m.group(1), max_len=120)}입니다."
        m = re.fullmatch(r"Exit action:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 액션은 {_action_label(m.group(1))}로 기록되었습니다."
        m = re.fullmatch(r"Exit reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 사유는 {_clip(m.group(1), max_len=240)}입니다."
        return _normalize_trade_report_language(cleaned)

    def _section_title(title: str) -> str:
        mapping = {
            "Executive Summary": "최종 판단 요약",
            "Market Context at Entry": "시장 환경 요약",
            "Why This Symbol Was Chosen": "선택된 종목 상세 분석",
            "Entry Decision": "진입 상세 근거",
            "Holding / Monitoring Story": "보유 경과",
            "Exit Decision": "청산 판단 근거",
            "Scanner Logic and Filters": "스캐너 후보 비교",
            "Guard / Approval Result": "승인 및 가드 판단",
            "Execution Quality": "실행 결과",
            "Reporter Evaluation": "결과 평가",
            "Errors / Weaknesses / Improvement Points": "보완 포인트",
        }
        return mapping.get(title, title)

    def _timeline_label(value: Any) -> str:
        mapping = {
            "entry": "진입",
            "holding": "보유 관리",
            "hold": "보유 관리",
            "monitor": "모니터링",
            "exit": "청산",
            "reporter": "평가",
            "scanner": "스캐너",
            "strategist": "전략가",
            "executor": "실행",
            "supervisor": "승인",
        }
        raw = _clip(value, max_len=64).strip().lower()
        return mapping.get(raw, _clip(value, max_len=64) or "이벤트")

    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    generation_status = str(generation.get("status") or "").strip().lower()
    if generation_status not in {"", "ok", "repaired", "partial", "salvaged"}:
        failure = report.get("failure") if isinstance(report.get("failure"), dict) else {}
        lines = [
            f"# AI 거래 리포트 ({report.get('trade_id') or report.get('story_id') or report.get('run_id') or 'story'})",
            "",
            f"- 대상 거래는 {_action_label(report.get('action'))} {report.get('symbol') or '-'} 기준으로 정리했습니다.",
            f"- 라이프사이클 상태는 {_meta_label(report.get('status'))}입니다.",
            f"- 리포트 생성 상태는 {generation.get('status') or '-'}이며 사용 모델은 {generation.get('model') or '-'}입니다.",
            "",
            "## 생성 실패 안내",
            "",
            f"- 생성 실패 사유는 {failure.get('reason') or generation.get('reason') or '-'}입니다.",
        ]
        if str(failure.get("error") or "").strip():
            lines.append(f"- 내부 오류 정보는 {failure.get('error')}입니다.")
        lines.append("")
        return "\n".join(lines)

    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    market_context = (
        report.get("market_context_at_entry")
        if isinstance(report.get("market_context_at_entry"), dict)
        else report.get("market_context")
        if isinstance(report.get("market_context"), dict)
        else {}
    )
    why_symbol = (
        report.get("why_this_symbol_was_chosen")
        if isinstance(report.get("why_this_symbol_was_chosen"), dict)
        else report.get("why_this_symbol")
        if isinstance(report.get("why_this_symbol"), dict)
        else {}
    )
    entry_decision = report.get("entry_decision") if isinstance(report.get("entry_decision"), dict) else {}
    holding_story = (
        report.get("holding_monitoring_story")
        if isinstance(report.get("holding_monitoring_story"), dict)
        else report.get("monitor_trigger_reasoning")
        if isinstance(report.get("monitor_trigger_reasoning"), dict)
        else {}
    )
    exit_decision = report.get("exit_decision") if isinstance(report.get("exit_decision"), dict) else {}
    scanner_filters = (
        report.get("scanner_filters")
        if isinstance(report.get("scanner_filters"), dict)
        else report.get("scanner_logic_and_filters")
        if isinstance(report.get("scanner_logic_and_filters"), dict)
        else {}
    )
    guard_result = report.get("guard_approval_result") if isinstance(report.get("guard_approval_result"), dict) else {}
    execution_result = (
        report.get("execution_quality")
        if isinstance(report.get("execution_quality"), dict)
        else report.get("execution_result")
        if isinstance(report.get("execution_result"), dict)
        else {}
    )
    reporter_eval = report.get("reporter_evaluation") if isinstance(report.get("reporter_evaluation"), dict) else {}
    weak_points = (
        report.get("errors_weaknesses_improvement_points")
        if isinstance(report.get("errors_weaknesses_improvement_points"), dict)
        else {}
    )
    final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
    monitor_snapshot = report.get("monitor_snapshot") if isinstance(report.get("monitor_snapshot"), dict) else {}

    lines: List[str] = []
    lines.append(f"# AI 거래 리포트 ({report.get('trade_id') or report.get('story_id') or report.get('run_id') or 'story'})")
    lines.append("")
    lines.append(f"- 대상 거래는 {_action_label(report.get('action'))} {report.get('symbol') or '-'} 기준으로 정리했습니다.")
    lines.append(f"- 라이프사이클 상태는 {_meta_label(report.get('status'))}입니다.")
    lines.append(f"- 리포트 유형은 {_meta_label(report.get('story_type'))}입니다.")
    lines.append(f"- 실행 모드는 {_meta_label(report.get('execution_mode_label'))}입니다.")
    lines.append("")
    lines.append("## 생성 정보")
    lines.append("")
    for meta_line in (
        _metadata_line("생성 상태", generation.get("status") or "-"),
        _metadata_line("생성 방식", _meta_label(generation.get("mode"))),
        _metadata_line("사용 모델", generation.get("model") or "-"),
        _metadata_line("생성 시각", report.get("generated_at")),
    ):
        if meta_line:
            lines.append(meta_line)
    if str(generation.get("reason") or "").strip():
        lines.append(f"- 생성 사유: {_render_text(generation.get('reason'))}")
    lines.append("")
    if generation_status in {"repaired", "partial", "salvaged"}:
        lines.append("## 생성 참고")
        lines.append("")
        lines.append(f"- 리포트는 {generation_status} 상태로 정리됐습니다.")
        lines.append(f"- 사유는 {generation.get('reason') or '부분 응답을 복구해 최종 리포트를 구성한 경우입니다.'}입니다.")
        lines.append("")
    section_provenance = report.get("section_provenance") if isinstance(report.get("section_provenance"), dict) else {}
    if section_provenance:
        lines.append("## 근거 출처")
        lines.append("")
        section_titles = {
            "market_context_at_entry": "시장 환경 요약",
            "why_this_symbol_was_chosen": "선택된 종목 상세 분석",
            "holding_monitoring_story": "보유 경과",
            "execution_quality": "실행 결과",
            "reporter_evaluation": "결과 평가",
        }
        for section_key in (
            "market_context_at_entry",
            "why_this_symbol_was_chosen",
            "holding_monitoring_story",
            "execution_quality",
            "reporter_evaluation",
        ):
            entry = section_provenance.get(section_key) if isinstance(section_provenance.get(section_key), dict) else {}
            fragments = [
                f"데이터 출처: {_metadata_value(entry.get('source') or 'fallback')}",
                f"신뢰도: {_metadata_value(entry.get('confidence') or 'low')}",
            ]
            artifact_path = _metadata_value(entry.get("artifact_path"))
            if artifact_path:
                fragments.append(f"참조 경로: {artifact_path}")
            lines.append(f"- {section_titles.get(section_key, section_key)} | " + " | ".join(fragments))
        lines.append("")
    if monitor_snapshot:
        lines.append("## 모니터 스냅샷")
        lines.append("")
        lines.append(f"- 현재 포지션 판단은 {_action_label(monitor_snapshot.get('posture'))}입니다.")
        lines.append(f"- 감지된 신호 유형은 {_axis_label(monitor_snapshot.get('trigger_type'))}입니다.")
        if monitor_snapshot.get("hard_stop_pct") not in (None, ""):
            lines.append(f"- Hard fail-safe 손절 기준은 {_fmt_pct(monitor_snapshot.get('hard_stop_pct'))} 수준입니다.")
        if monitor_snapshot.get("strategist_baseline_stop_loss_pct") not in (None, ""):
            lines.append(
                f"- 전략가 baseline 적응형 손절 기준은 {_fmt_pct(monitor_snapshot.get('strategist_baseline_stop_loss_pct'))} 수준입니다."
            )
        if monitor_snapshot.get("adaptive_stop_loss_pct") not in (None, ""):
            lines.append(
                f"- 모니터 active adaptive 손절 기준은 {_fmt_pct(monitor_snapshot.get('adaptive_stop_loss_pct'))} 수준입니다."
            )
        lines.append(f"- 유효 손절 기준은 {_fmt_pct(monitor_snapshot.get('effective_stop_loss_pct'))} 수준입니다.")
        lines.append(f"- 손절 기준 축은 {_axis_label(monitor_snapshot.get('effective_stop_reason'))}입니다.")
        if monitor_snapshot.get("strategist_baseline_take_profit_pct") not in (None, ""):
            lines.append(
                f"- 전략가 baseline 익절 기준은 {_fmt_pct(monitor_snapshot.get('strategist_baseline_take_profit_pct'))} 수준입니다."
            )
        lines.append(f"- 목표 수익 실현 기준은 {_fmt_pct(monitor_snapshot.get('take_profit_pct'))} 수준입니다.")
        if monitor_snapshot.get("strategist_baseline_trailing_stop_pct") not in (None, ""):
            lines.append(
                f"- 전략가 baseline trailing stop 기준은 {_fmt_pct(monitor_snapshot.get('strategist_baseline_trailing_stop_pct'))} 수준입니다."
            )
        if monitor_snapshot.get("current_price") not in (None, ""):
            lines.append(f"- 현재가는 {_fmt_price(monitor_snapshot.get('current_price'))}입니다.")
        if monitor_snapshot.get("average_price") not in (None, ""):
            lines.append(f"- 평균 단가는 {_fmt_price(monitor_snapshot.get('average_price'))}입니다.")
        if monitor_snapshot.get("peak_price") not in (None, ""):
            lines.append(f"- 장중 고점은 {_fmt_price(monitor_snapshot.get('peak_price'))}입니다.")
        if monitor_snapshot.get("current_drawdown") not in (None, ""):
            lines.append(f"- 현재 손익 변동은 {_fmt_pct(monitor_snapshot.get('current_drawdown'))}입니다.")
        if monitor_snapshot.get("peak_drawdown") not in (None, ""):
            lines.append(f"- 고점 대비 하락폭은 {_fmt_pct(monitor_snapshot.get('peak_drawdown'))}입니다.")
        if monitor_snapshot.get("vwap_distance") not in (None, ""):
            lines.append(f"- VWAP 이격은 {_fmt_pct(monitor_snapshot.get('vwap_distance'))}입니다.")
        if str(monitor_snapshot.get("active_exit_axis") or "").strip():
            lines.append(f"- 현재 우선 감시 중인 청산 축은 {_axis_label(monitor_snapshot.get('active_exit_axis'))}입니다.")
        for axis in list(monitor_snapshot.get("watch_axes") or [])[:6]:
            lines.append(f"- 주요 감시 축은 {_axis_label(axis)}입니다.")
        lines.append(f"- 가격 기준 소스는 {monitor_snapshot.get('price_source') or '-'}입니다.")
        lines.append(f"- 피처 기준 소스는 {monitor_snapshot.get('feature_source') or '-'}입니다.")
        if str(monitor_snapshot.get('price_source_policy') or '').strip():
            lines.append(f"- 가격 소스 정책은 {monitor_snapshot.get('price_source_policy')}입니다.")
        lines.append(f"- 청산 신호 발생 여부는 {'예' if monitor_snapshot.get('exit_triggered') else '아니오'}입니다.")
        lines.append("")

    def _section(title: str, section: Dict[str, Any], *, bullet_key: str = "bullets") -> None:
        lines.append(f"## {_section_title(title)}")
        lines.append("")
        summary = _render_text(section.get("summary"))
        if summary:
            lines.append(summary)
            lines.append("")
        bullets = _listify(section.get(bullet_key), max_items=12, max_len=400)
        for bullet in bullets:
            rendered = _render_text(bullet)
            if rendered:
                lines.append(f"- {rendered}")
        if bullets:
            lines.append("")

    _section("Executive Summary", executive)
    _section("Market Context at Entry", market_context)
    _section("Why This Symbol Was Chosen", why_symbol)
    _section("Entry Decision", entry_decision)
    _section("Holding / Monitoring Story", holding_story)
    _section("Exit Decision", exit_decision)
    _section("Scanner Logic and Filters", scanner_filters)
    _section("Guard / Approval Result", guard_result)
    _section("Execution Quality", execution_result)
    _section("Reporter Evaluation", reporter_eval)
    _section("Errors / Weaknesses / Improvement Points", weak_points)

    lines.append("## 전체 타임라인")
    lines.append("")
    timeline = report.get("full_timeline") if isinstance(report.get("full_timeline"), list) else report.get("timeline") if isinstance(report.get("timeline"), list) else []
    if timeline:
        for row in timeline[:24]:
            if not isinstance(row, dict):
                continue
            label = _timeline_label(row.get('event') or row.get('step') or row.get('label') or 'step')
            description = _render_text(row.get('description') or row.get('summary') or row.get('detail') or '-')
            lines.append(
                f"- {label}: {description or '-'}"
            )
    else:
        lines.append("- 타임라인 이벤트는 별도로 저장되지 않았습니다.")
    lines.append("")

    lines.append("## 최종 운영 판단")
    lines.append("")
    final_summary = _render_text(final_conclusion.get("summary"))
    if final_summary:
        lines.append(final_summary)
        lines.append("")
    current_action = _clip(final_conclusion.get("current_action"), max_len=48)
    if current_action:
        lines.append(f"- 현재 판단 액션은 {_action_label(current_action)}입니다.")
    for item in _listify(final_conclusion.get("watch_next"), max_items=6, max_len=220):
        lines.append(f"- 다음 확인 항목은 {_render_text(item)}입니다.")
    for item in _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=220):
        lines.append(f"- 기존 판단이 무효화되는 조건은 {_render_text(item)}입니다.")
    lines.append("")
    return "\n".join(lines)
