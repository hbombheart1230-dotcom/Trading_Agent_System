from __future__ import annotations

import ast
import html
import json
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from libs.llm.json_response import parse_llm_json_response, required_key_metadata
from libs.llm.model_catalog import build_execution_profile_observability, resolve_policy_llm_execution_slot, resolve_policy_llm_slot
from libs.llm.model_names import normalize_openrouter_model_name
from libs.llm.llm_router import LLMRouter
from libs.reporting.llm_artifacts import build_llm_response_artifact, classify_llm_exception, make_attempt
from libs.reporting.trade_price_truth import resolve_trade_price_truth
from libs.reporting.trade_pnl_estimate import infer_exit_fill_pnl_pct_from_account_snapshot
from libs.reporting.execution_truth_surface import build_execution_truth_bullets
from libs.reporting.trade_memory_application_surface import build_trade_memory_application_surface
from libs.reporting.trade_memory_surface import build_trade_report_memory_surface
from libs.reporting.report_truth_surface import build_trade_report_truth_surface
from libs.reporting.trade_execution_outcome_text import execution_outcome_summary_is_placeholder
from libs.reporting.trade_reporter_status_text import normalize_reporter_text
from libs.reporting.truth_source_labels import (
    monitor_price_source_label,
    pnl_truth_source_label,
    price_truth_source_label,
    truth_availability_line,
)
from libs.runtime.strategist_explanation import build_strategy_refresh_trace

logger = logging.getLogger(__name__)


def _safe_fullmatch(pattern: str, text: str, *, flags: int = 0):
    try:
        return re.fullmatch(pattern, text, flags=flags)
    except re.error:
        logger.debug("trade_report_regex_invalid pattern=%r", pattern, exc_info=True)
        return None

def _resolve_intraday_report_model(source: Dict[str, Any] | None, *, explicit_model: Optional[str] = None) -> str:
    resolved = resolve_policy_llm_slot(source if isinstance(source, dict) else {}, "reporter", "intraday", default_profile="fast_free")
    return normalize_openrouter_model_name(
        str(explicit_model or "").strip()
        or str(resolved.get("primary") or "").strip()
        or "minimax/minimax-m2.5"
    )


def _resolve_intraday_report_execution_profile(source: Dict[str, Any] | None) -> Dict[str, Any]:
    return resolve_policy_llm_execution_slot(
        source if isinstance(source, dict) else {},
        "reporter",
        "intraday",
        default_profile="concise_review",
        defaults={
            "profile_name": "concise_review",
            "name": "concise_review",
            "temperature": 0.2,
            "max_tokens": 3072,
            "timeout_sec": 15,
            "retry": {"max_attempts": 1, "backoff_sec": 0.0},
            "retry_max": 1,
            "retry_backoff_sec": 0.0,
        },
    )


def _router_chat_with_hard_timeout(
    router: LLMRouter,
    role: str,
    messages: List[Dict[str, Any]],
    *,
    policy: Optional[Dict[str, Any]] = None,
    hard_timeout_sec: Optional[float] = None,
) -> str:
    if hard_timeout_sec in (None, "", 0):
        return router.chat(role, messages, policy=policy)
    timeout_value = max(0.1, float(hard_timeout_sec or 0.0))
    result: Dict[str, Any] = {}
    failure: Dict[str, Exception] = {}
    done = threading.Event()

    def _run() -> None:
        try:
            result["value"] = router.chat(role, messages, policy=policy)
        except Exception as exc:
            failure["exc"] = exc
        finally:
            done.set()

    worker = threading.Thread(target=_run, name="trade-report-chat", daemon=True)
    worker.start()
    if not done.wait(timeout_value):
        raise TimeoutError(f"trade_report_ai hard timeout after {timeout_value:.1f}s")
    if "exc" in failure:
        raise failure["exc"]
    return str(result.get("value") or "")


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
    if len(text) <= 12 and _safe_fullmatch(r"[a-z_\- ]+", text):
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


def _action_from_exit_reason(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "sell" in text or "매도" in text or "청산" in text:
        return "SELL"
    return ""


def _is_open_position_placeholder_reason(value: Any) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    markers = (
        "position is still open",
        "monitor is watching for exit",
        "still open",
        "포지션이 아직",
    )
    return any(token in text for token in markers)


def _reporter_summary_is_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    lowered = text.lower()
    exact_markers = {
        "same-day reporter analysis was not generated yet.",
        "a same-day reporter file exists, but this run was not linked to a run-specific evaluation yet.",
        "a same-day reporter analysis was linked to this run.",
        "당일 리포터 분석은 아직 생성되지 않았습니다.",
        "당일 리포터 파일은 있지만 이 run에 대한 개별 평가는 아직 연결되지 않았습니다.",
        "당일 리포터 분석이 이 run에 연결됐습니다.",
    }
    prefix_markers = (
        "reporter status:",
        "reporter reason:",
        "reporter grade:",
        "reporter summary:",
    )
    if lowered in {marker.lower() for marker in exact_markers}:
        return True
    return any(lowered.startswith(marker) for marker in prefix_markers)


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
    execution_details = _as_dict(story_input.get("exit_execution_details")) or _as_dict(story_input.get("execution_details"))
    monitor_reason = _as_dict(story_input.get("monitor_reason_human"))
    trade_read_model = _load_trade_read_model_hint(story_input)
    trade_read_model_context = trade_read_model.get("context") if isinstance(trade_read_model.get("context"), dict) else {}

    fields = ["action", "status", "holding_duration", "exit_reason", "pnl", "pnl_pct"]
    resolved: Dict[str, Any] = {key: "unavailable" for key in fields}
    data_source: Dict[str, str] = {key: "unavailable" for key in fields}

    broker_pnl_source = _first_nonempty_text(
        execution_details.get("pnl_truth_source"),
        execution_details.get("broker_day_truth_source"),
        max_len=80,
    )
    if execution_details.get("broker_realized_pnl") not in (None, ""):
        resolved["pnl"] = execution_details.get("broker_realized_pnl")
        data_source["pnl"] = broker_pnl_source or "kiwoom_day_trade"
    if execution_details.get("broker_realized_pnl_pct") not in (None, ""):
        resolved["pnl_pct"] = execution_details.get("broker_realized_pnl_pct")
        data_source["pnl_pct"] = broker_pnl_source or "kiwoom_day_trade"
    inferred_pnl = infer_exit_fill_pnl_pct_from_account_snapshot(story_input)
    if resolved.get("pnl_pct") in (None, "", "unavailable") and inferred_pnl.get("pnl_pct") not in (None, ""):
        resolved["pnl_pct"] = inferred_pnl.get("pnl_pct")
        resolved["pnl_truth_source"] = inferred_pnl.get("pnl_truth_source")
        data_source["pnl_pct"] = inferred_pnl.get("pnl_truth_source") or "estimate"

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

    # Closed-lifecycle reconciliation:
    # If monitor entry decision(BUY) was captured first but lifecycle is closed, prefer
    # explicit exit-side action evidence to prevent BUY+closed inconsistencies.
    resolved_status = _as_status(resolved.get("status"))
    resolved_action = _as_action(resolved.get("action"))
    if resolved_status == "closed" and resolved_action == "BUY":
        reconciled_action = ""
        for candidate in (
            _as_action(exit_summary.get("action")),
            _as_action(lifecycle_exit.get("action")),
            _as_action(_as_dict(story_input.get("execution")).get("action")),
            _as_action(story_input.get("action")),
            _action_from_exit_reason(resolved.get("exit_reason")),
            _action_from_exit_reason(exit_summary.get("reason_human")),
            _action_from_exit_reason(lifecycle.get("exit_reason")),
        ):
            if candidate in {"SELL", "EXIT"}:
                reconciled_action = candidate
                break
        if reconciled_action:
            resolved["action"] = reconciled_action
            data_source["action"] = "closed_lifecycle_reconcile"

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
    trade_model_monitor = trade_read_model_context.get("monitor") if isinstance(trade_read_model_context.get("monitor"), dict) else {}
    if monitor_decision.get("reason_code") in {"", "unavailable"}:
        trade_monitor_reason = _clip(
            trade_model_monitor.get("exit_trigger") or trade_model_monitor.get("primary_blocker"),
            max_len=220,
        )
        if trade_monitor_reason:
            monitor_decision["reason_code"] = trade_monitor_reason
    if not monitor_decision.get("thresholds") and isinstance(trade_model_monitor.get("thresholds_snapshot"), dict):
        monitor_decision["thresholds"] = _as_dict(trade_model_monitor.get("thresholds_snapshot"))
    return {
        **resolved,
        "broker_fee": execution_details.get("broker_fee"),
        "broker_tax": execution_details.get("broker_tax"),
        "pnl_truth_source": resolved.get("pnl_truth_source") or broker_pnl_source or "unavailable",
        "broker_day_truth_source": resolved.get("broker_day_truth_source")
        if resolved.get("broker_day_truth_source") not in (None, "")
        else execution_details.get("broker_day_truth_source"),
        "broker_day_match_mode": resolved.get("broker_day_match_mode")
        if resolved.get("broker_day_match_mode") not in (None, "")
        else execution_details.get("broker_day_match_mode"),
        "broker_day_authoritative": bool(
            resolved.get("broker_day_authoritative")
            if resolved.get("broker_day_authoritative") not in (None, "")
            else execution_details.get("broker_day_authoritative")
        ),
        "broker_day_row_count": resolved.get("broker_day_row_count")
        if resolved.get("broker_day_row_count") not in (None, "")
        else execution_details.get("broker_day_row_count"),
        "broker_truth_attempted": bool(execution_details.get("broker_truth_attempted")),
        "broker_truth_error": execution_details.get("broker_truth_error"),
        "broker_day_truth_attempted": bool(execution_details.get("broker_day_truth_attempted")),
        "broker_day_truth_error": execution_details.get("broker_day_truth_error"),
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
    canonical_strategist = _as_dict(canonical.get("strategist"))
    canonical_strategist_decision_frame = _as_dict(canonical_strategist.get("decision_frame"))
    trade_read_model = _load_trade_read_model_hint(story_input)
    trade_read_model_facts = trade_read_model.get("facts") if isinstance(trade_read_model.get("facts"), dict) else {}
    trade_read_model_context = trade_read_model.get("context") if isinstance(trade_read_model.get("context"), dict) else {}
    trade_model_report_section_seeds = (
        trade_read_model_context.get("report_section_seeds")
        if isinstance(trade_read_model_context.get("report_section_seeds"), dict)
        else {}
    )
    resolved_facts = _resolve_trade_facts_with_precedence(story_input)
    price_truth = resolve_trade_price_truth(story_input)
    trade_model_hold_duration_sec = trade_read_model_facts.get("hold_duration_sec")
    if resolved_facts.get("holding_duration") in (None, "", "unavailable") and trade_model_hold_duration_sec not in (None, ""):
        try:
            resolved_facts["holding_duration"] = str(int(float(trade_model_hold_duration_sec)))
            (resolved_facts.get("data_source") if isinstance(resolved_facts.get("data_source"), dict) else {}).update({"holding_duration": "trade_read_model"})
        except Exception:
            pass
    if resolved_facts.get("exit_reason") in (None, "", "unavailable") and str(trade_read_model_facts.get("exit_reason") or "").strip():
        resolved_facts["exit_reason"] = _clip(trade_read_model_facts.get("exit_reason"), max_len=280)
        (resolved_facts.get("data_source") if isinstance(resolved_facts.get("data_source"), dict) else {}).update({"exit_reason": "trade_read_model"})
    if resolved_facts.get("pnl") in (None, "", "unavailable") and trade_read_model_facts.get("pnl") not in (None, ""):
        resolved_facts["pnl"] = trade_read_model_facts.get("pnl")
        (resolved_facts.get("data_source") if isinstance(resolved_facts.get("data_source"), dict) else {}).update({"pnl": "trade_read_model"})
    if resolved_facts.get("pnl_pct") in (None, "", "unavailable") and trade_read_model_facts.get("pnl_pct") not in (None, ""):
        resolved_facts["pnl_pct"] = trade_read_model_facts.get("pnl_pct")
        (resolved_facts.get("data_source") if isinstance(resolved_facts.get("data_source"), dict) else {}).update({"pnl_pct": "trade_read_model"})
    lifecycle_action = _as_action(resolved_facts.get("action")) or "WAIT"
    status_text = _as_status(resolved_facts.get("status")) or "unavailable"
    trade_model_scanner = trade_read_model_context.get("scanner") if isinstance(trade_read_model_context.get("scanner"), dict) else {}
    scanner_evidence_status = (
        "available"
        if (
            _has_evidence_payload(story_input.get("scanner_evidence"))
            or bool(_first_nonempty_text(scanner_reason.get("selected_symbol"), scanner_reason.get("summary"), max_len=200))
            or bool(_listify(scanner_reason.get("bullets"), max_items=1, max_len=120))
            or bool(_first_nonempty_text(trade_model_scanner.get("summary"), max_len=200))
            or bool(_listify(trade_model_scanner.get("top_candidates"), max_items=1, max_len=120))
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
    if not scanner_reasoning.get("selection_reason_with_bias") and str(trade_model_scanner.get("summary") or "").strip():
        scanner_reasoning["selection_reason_with_bias"] = _clip(trade_model_scanner.get("summary"), max_len=320)
    selection_trace = scanner_reasoning.get("selection_trace") if isinstance(scanner_reasoning.get("selection_trace"), dict) else {}
    if not selection_trace.get("ranked_candidates") and isinstance(trade_model_scanner.get("top_candidates"), list):
        selection_trace["ranked_candidates"] = [
            {
                "symbol": _clip((row or {}).get("symbol"), max_len=24),
                "score_total": (row or {}).get("score_total"),
                "rank": (row or {}).get("rank"),
            }
            for row in list(trade_model_scanner.get("top_candidates") or [])[:5]
            if isinstance(row, dict)
        ]
    if not selection_trace.get("selected_symbol"):
        first_ranked = ((selection_trace.get("ranked_candidates") or [None])[0] or {}) if isinstance(selection_trace.get("ranked_candidates"), list) else {}
        if isinstance(first_ranked, dict) and str(first_ranked.get("symbol") or "").strip():
            selection_trace["selected_symbol"] = _clip(first_ranked.get("symbol"), max_len=24)
    if not selection_trace.get("selected_rank"):
        first_ranked = ((selection_trace.get("ranked_candidates") or [None])[0] or {}) if isinstance(selection_trace.get("ranked_candidates"), list) else {}
        if isinstance(first_ranked, dict) and first_ranked.get("rank") not in (None, ""):
            selection_trace["selected_rank"] = first_ranked.get("rank")
    if not selection_trace.get("selected_symbol_score_drivers") and isinstance(trade_model_scanner.get("score_drivers"), dict):
        selection_trace["selected_symbol_score_drivers"] = _compact_scalar_dict(
            trade_model_scanner.get("score_drivers"), max_items=6, max_len=120
        )
    scanner_reasoning["selection_trace"] = selection_trace

    trade_model_monitor = trade_read_model_context.get("monitor") if isinstance(trade_read_model_context.get("monitor"), dict) else {}
    if not monitor_reasoning.get("entry_check_summary") and str(trade_model_monitor.get("entry_reason") or "").strip():
        monitor_reasoning["entry_check_summary"] = _clip(trade_model_monitor.get("entry_reason"), max_len=240)
    if not monitor_reasoning.get("threshold_shortfalls") and isinstance(trade_model_monitor.get("blocker_trace"), dict):
        monitor_reasoning["threshold_shortfalls"] = _listify(
            (trade_model_monitor.get("blocker_trace") or {}).get("threshold_shortfalls"), max_items=4, max_len=160
        )
    existing_monitor_stop_trace = (
        monitor_reasoning.get("monitor_stop_policy_trace")
        if isinstance(monitor_reasoning.get("monitor_stop_policy_trace"), dict)
        else {}
    )
    if not any(value not in (None, "", [], {}) for value in existing_monitor_stop_trace.values()) and isinstance(trade_model_monitor.get("stop_policy_trace"), dict):
        monitor_reasoning["monitor_stop_policy_trace"] = _compact_scalar_dict(
            trade_model_monitor.get("stop_policy_trace"), max_items=8, max_len=120
        )
    trade_model_strategist = trade_read_model_context.get("strategist") if isinstance(trade_read_model_context.get("strategist"), dict) else {}
    theme_strength_packet = (
        _as_dict(market_context.get("theme_strength_packet"))
        or _as_dict(trade_model_strategist.get("theme_strength_packet"))
        or _as_dict(canonical_strategist.get("theme_strength_packet"))
        or _as_dict(canonical_strategist_decision_frame.get("theme_strength_packet"))
    )
    theme_strength_scores = (
        _as_dict(market_context.get("theme_strength_scores"))
        or _as_dict(trade_model_strategist.get("theme_strength_scores"))
        or _as_dict(canonical_strategist.get("theme_strength"))
        or _as_dict(theme_strength_packet.get("theme_scores"))
    )
    strategist_context = {
        "playbook": _first_nonempty_text(
            market_context.get("playbook"),
            market_context.get("selected_playbook"),
            trade_model_strategist.get("playbook"),
            max_len=80,
        ),
        "selected_playbook": _first_nonempty_text(
            market_context.get("selected_playbook"),
            market_context.get("playbook"),
            trade_model_strategist.get("playbook"),
            max_len=80,
        ),
        "policy_source": _first_nonempty_text(
            market_context.get("policy_source"),
            trade_model_strategist.get("policy_source"),
            max_len=80,
        ),
        "themes": _listify(
            market_context.get("themes")
            or market_context.get("preferred_themes")
            or trade_model_strategist.get("themes"),
            max_items=6,
            max_len=48,
        ),
        "preferred_themes": _listify(
            market_context.get("preferred_themes")
            or market_context.get("themes")
            or trade_model_strategist.get("themes"),
            max_items=6,
            max_len=48,
        ),
        "market_context_summary": _first_nonempty_text(
            market_context.get("summary"),
            trade_model_strategist.get("market_context_summary"),
            max_len=320,
        ),
        "theme_strength_packet": theme_strength_packet,
        "theme_source": _first_nonempty_text(
            market_context.get("theme_source"),
            trade_model_strategist.get("theme_source"),
            canonical_strategist.get("theme_source"),
            canonical_strategist_decision_frame.get("theme_source"),
            theme_strength_packet.get("source"),
            max_len=80,
        ),
        "theme_source_status": _first_nonempty_text(
            market_context.get("theme_source_status"),
            trade_model_strategist.get("theme_source_status"),
            canonical_strategist.get("theme_source_status"),
            canonical_strategist_decision_frame.get("theme_source_status"),
            theme_strength_packet.get("status"),
            max_len=80,
        ),
        "theme_source_reason": _first_nonempty_text(
            market_context.get("theme_source_reason"),
            trade_model_strategist.get("theme_source_reason"),
            canonical_strategist.get("theme_source_reason"),
            canonical_strategist_decision_frame.get("theme_source_reason"),
            theme_strength_packet.get("reason"),
            max_len=160,
        ),
        "theme_strength_top_themes": _listify(
            market_context.get("theme_strength_top_themes") or theme_strength_packet.get("top_themes"),
            max_items=6,
            max_len=80,
        ),
        "theme_strength_scores": theme_strength_scores,
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
        "broker_fee": resolved_facts.get("broker_fee"),
        "broker_tax": resolved_facts.get("broker_tax"),
        "pnl_truth_source": _clip(resolved_facts.get("pnl_truth_source"), max_len=80) or "unavailable",
        "broker_day_truth_source": _clip(resolved_facts.get("broker_day_truth_source"), max_len=80) or "",
        "broker_day_match_mode": _clip(resolved_facts.get("broker_day_match_mode"), max_len=40) or "",
        "broker_day_authoritative": bool(resolved_facts.get("broker_day_authoritative")),
        "broker_day_row_count": resolved_facts.get("broker_day_row_count"),
        "broker_truth_attempted": bool(resolved_facts.get("broker_truth_attempted")),
        "broker_truth_error": _clip(resolved_facts.get("broker_truth_error"), max_len=240) or "",
        "broker_day_truth_attempted": bool(resolved_facts.get("broker_day_truth_attempted")),
        "broker_day_truth_error": _clip(resolved_facts.get("broker_day_truth_error"), max_len=240) or "",
        "broker_fill_price": price_truth.get("broker_fill_price"),
        "broker_buy_price": price_truth.get("broker_buy_price"),
        "account_mark_price": price_truth.get("account_mark_price"),
        "monitor_mark_price": price_truth.get("monitor_mark_price"),
        "price_truth_source": _clip(price_truth.get("price_truth_source"), max_len=40) or "unavailable",
        "monitor_price_source": _clip(price_truth.get("monitor_price_source"), max_len=120) or "unavailable",
        "monitor_decision": dict(resolved_facts.get("monitor_decision") or {}),
        "resolved_trade_facts": {
            "action": lifecycle_action,
            "status": status_text,
            "holding_duration": _clip(resolved_facts.get("holding_duration"), max_len=80) or "unavailable",
            "exit_reason": _clip(resolved_facts.get("exit_reason"), max_len=280) or "unavailable",
            "pnl": resolved_facts.get("pnl", "unavailable"),
            "pnl_pct": resolved_facts.get("pnl_pct", "unavailable"),
            "broker_fee": resolved_facts.get("broker_fee"),
            "broker_tax": resolved_facts.get("broker_tax"),
            "pnl_truth_source": _clip(resolved_facts.get("pnl_truth_source"), max_len=80) or "unavailable",
            "broker_day_truth_source": _clip(resolved_facts.get("broker_day_truth_source"), max_len=80) or "",
            "broker_day_match_mode": _clip(resolved_facts.get("broker_day_match_mode"), max_len=40) or "",
            "broker_day_authoritative": bool(resolved_facts.get("broker_day_authoritative")),
            "broker_day_row_count": resolved_facts.get("broker_day_row_count"),
            "broker_truth_attempted": bool(resolved_facts.get("broker_truth_attempted")),
            "broker_truth_error": _clip(resolved_facts.get("broker_truth_error"), max_len=240) or "",
            "broker_day_truth_attempted": bool(resolved_facts.get("broker_day_truth_attempted")),
            "broker_day_truth_error": _clip(resolved_facts.get("broker_day_truth_error"), max_len=240) or "",
            "broker_fill_price": price_truth.get("broker_fill_price"),
            "broker_buy_price": price_truth.get("broker_buy_price"),
            "account_mark_price": price_truth.get("account_mark_price"),
            "monitor_mark_price": price_truth.get("monitor_mark_price"),
            "price_truth_source": _clip(price_truth.get("price_truth_source"), max_len=40) or "unavailable",
            "monitor_price_source": _clip(price_truth.get("monitor_price_source"), max_len=120) or "unavailable",
            "data_source": dict(resolved_facts.get("data_source") or {}),
        },
        "scanner_evidence_status": scanner_evidence_status,
        "strategist_evidence_status": strategist_evidence_status,
        "commander_route": commander_route,
        "strategist_evidence": strategist_evidence,
        "strategist_context": strategist_context,
        "report_section_seeds": {
            "market_context_at_entry": _as_dict(trade_model_report_section_seeds.get("market_context_at_entry")),
            "strategist_summary": _as_dict(trade_model_report_section_seeds.get("strategist_summary")),
            "why_this_symbol_was_chosen": _as_dict(trade_model_report_section_seeds.get("why_this_symbol_was_chosen")),
            "entry_decision": _as_dict(trade_model_report_section_seeds.get("entry_decision")),
            "holding_monitoring_story": _as_dict(trade_model_report_section_seeds.get("holding_monitoring_story")),
            "exit_decision": _as_dict(trade_model_report_section_seeds.get("exit_decision")),
            "scanner_filters": _as_dict(trade_model_report_section_seeds.get("scanner_filters")),
            "execution_quality": _as_dict(trade_model_report_section_seeds.get("execution_quality")),
            "guard_approval_result": _as_dict(trade_model_report_section_seeds.get("guard_approval_result")),
            "reporter_evaluation": _as_dict(trade_model_report_section_seeds.get("reporter_evaluation")),
            "final_operator_conclusion": _as_dict(trade_model_report_section_seeds.get("final_operator_conclusion")),
        },
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
        "broker_fee": resolved.get("broker_fee"),
        "broker_tax": resolved.get("broker_tax"),
        "pnl_truth_source": _clip(resolved.get("pnl_truth_source"), max_len=80) or "unavailable",
        "broker_fill_price": resolved.get("broker_fill_price"),
        "broker_buy_price": resolved.get("broker_buy_price"),
        "account_mark_price": resolved.get("account_mark_price"),
        "monitor_mark_price": resolved.get("monitor_mark_price"),
        "price_truth_source": _clip(resolved.get("price_truth_source"), max_len=40) or "unavailable",
        "monitor_price_source": _clip(resolved.get("monitor_price_source"), max_len=120) or "unavailable",
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
    if status_text.lower() == "closed" and str(action or "").upper() == "BUY":
        resolved_trade_facts = (
            shared_seed.get("resolved_trade_facts")
            if isinstance(shared_seed.get("resolved_trade_facts"), dict)
            else {}
        )
        report_shared_facts = out.get("shared_facts") if isinstance(out.get("shared_facts"), dict) else {}
        report_exit_decision = out.get("exit_decision") if isinstance(out.get("exit_decision"), dict) else {}
        for candidate in (
            _action_from_exit_reason(resolved_trade_facts.get("exit_reason")),
            _action_from_exit_reason(report_shared_facts.get("exit_reason")),
            _action_from_exit_reason(report_exit_decision.get("summary")),
        ):
            if candidate in {"SELL", "EXIT"}:
                action = candidate
                break

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
    strategist_output = _compact_strategist_report_context(story_input)
    if strategist_output:
        if not _as_dict(strategist_output.get("strategy_refresh_trace")):
            refresh_trace_for_output = _build_report_strategist_refresh_trace(story_input)
            if refresh_trace_for_output:
                strategist_output["strategy_refresh_trace"] = refresh_trace_for_output
        out["strategist_output"] = strategist_output
    refresh_trace = _build_report_strategist_refresh_trace(story_input)
    if refresh_trace:
        existing_refresh = out.get("strategist_refresh_trace") if isinstance(out.get("strategist_refresh_trace"), dict) else {}
        if not existing_refresh or _is_low_information_bullet(existing_refresh.get("summary")):
            out["strategist_refresh_trace"] = refresh_trace

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
        "strategist_summary",
        "strategist_refresh_trace",
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
    strategist_context_for_theme = _as_dict(shared_seed.get("strategist_context"))
    market_section_for_theme = out.get("market_context_at_entry") if isinstance(out.get("market_context_at_entry"), dict) else {}
    for theme_key in (
        "theme_strength_packet",
        "theme_source",
        "theme_source_status",
        "theme_source_reason",
        "theme_strength_top_themes",
        "theme_strength_scores",
    ):
        if strategist_context_for_theme.get(theme_key) not in (None, "", [], {}) and not market_section_for_theme.get(theme_key):
            market_section_for_theme[theme_key] = strategist_context_for_theme.get(theme_key)
    theme_status = _clip(market_section_for_theme.get("theme_source_status"), max_len=80)
    theme_source = _clip(market_section_for_theme.get("theme_source"), max_len=80)
    theme_reason = _clip(market_section_for_theme.get("theme_source_reason"), max_len=160)
    if theme_status or theme_source or theme_reason:
        theme_bullets = _listify(market_section_for_theme.get("bullets"), max_items=12, max_len=400)
        if not any("Kiwoom theme packet:" in str(row) or "키움 테마 packet:" in str(row) for row in theme_bullets):
            top_themes = ", ".join(
                _listify(market_section_for_theme.get("theme_strength_top_themes"), max_items=6, max_len=80)
            )
            theme_bullets.append(
                "키움 테마 packet: "
                f"source={theme_source or 'not_captured'}, "
                f"status={theme_status or 'not_captured'}, "
                f"reason={theme_reason or 'not_captured'}, "
                f"top_themes={top_themes or 'none'}"
            )
            market_section_for_theme["bullets"] = theme_bullets
        out["market_context_at_entry"] = market_section_for_theme
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
    resolved_trade_facts = dict(shared_seed.get("resolved_trade_facts") or {})
    resolved_data_source = dict((_as_dict(resolved_trade_facts).get("data_source")))
    resolved_exit_reason = _clip(shared_seed.get("exit_reason"), max_len=280) or "unavailable"
    report_shared_facts = out.get("shared_facts") if isinstance(out.get("shared_facts"), dict) else {}
    report_exit_decision = out.get("exit_decision") if isinstance(out.get("exit_decision"), dict) else {}
    if status_text.lower() == "closed" and (
        _is_open_position_placeholder_reason(resolved_exit_reason)
        or str(resolved_exit_reason or "").strip().lower() in {"", "unavailable"}
    ):
        for candidate in (
            _clip(report_shared_facts.get("exit_reason"), max_len=280),
            _clip(report_exit_decision.get("summary"), max_len=280),
        ):
            if candidate and not _is_open_position_placeholder_reason(candidate):
                resolved_exit_reason = candidate
                resolved_trade_facts["exit_reason"] = candidate
                resolved_data_source["exit_reason"] = "normalize_existing_report"
                resolved_trade_facts["data_source"] = dict(resolved_data_source)
                break

    out["shared_facts"] = {
        "symbol": symbol,
        "trade_id": _clip(shared_seed.get("trade_id"), max_len=120),
        "action": action,
        "status": status_text,
        "holding_duration": _clip(shared_seed.get("holding_duration"), max_len=80) or "unavailable",
        "exit_reason": resolved_exit_reason,
        "pnl": shared_seed.get("pnl", "unavailable"),
        "pnl_pct": shared_seed.get("pnl_pct", "unavailable"),
        "broker_fee": shared_seed.get("broker_fee"),
        "broker_tax": shared_seed.get("broker_tax"),
        "pnl_truth_source": _clip(shared_seed.get("pnl_truth_source"), max_len=80) or "unavailable",
        "broker_day_truth_source": _clip(shared_seed.get("broker_day_truth_source"), max_len=80) or "",
        "broker_day_match_mode": _clip(shared_seed.get("broker_day_match_mode"), max_len=40) or "",
        "broker_day_authoritative": bool(shared_seed.get("broker_day_authoritative")),
        "broker_day_row_count": shared_seed.get("broker_day_row_count"),
        "broker_truth_attempted": bool(shared_seed.get("broker_truth_attempted")),
        "broker_truth_error": _clip(shared_seed.get("broker_truth_error"), max_len=240) or "",
        "broker_day_truth_attempted": bool(shared_seed.get("broker_day_truth_attempted")),
        "broker_day_truth_error": _clip(shared_seed.get("broker_day_truth_error"), max_len=240) or "",
        "broker_fill_price": shared_seed.get("broker_fill_price"),
        "broker_buy_price": shared_seed.get("broker_buy_price"),
        "account_mark_price": shared_seed.get("account_mark_price"),
        "monitor_mark_price": shared_seed.get("monitor_mark_price"),
        "price_truth_source": _clip(shared_seed.get("price_truth_source"), max_len=40) or "unavailable",
        "monitor_price_source": _clip(shared_seed.get("monitor_price_source"), max_len=120) or "unavailable",
        "data_source": dict(resolved_data_source),
        "resolved_trade_facts": dict(resolved_trade_facts),
        "lifecycle_action": action,
        "lifecycle_status": status_text,
        "monitor_decision": dict(shared_seed.get("monitor_decision") or {}),
        "scanner_evidence_status": _clip(shared_seed.get("scanner_evidence_status"), max_len=24),
        "strategist_evidence_status": _clip(shared_seed.get("strategist_evidence_status"), max_len=24),
        "commander_route": dict(shared_seed.get("commander_route") or {}),
    }
    out["truth_surface"] = build_trade_report_truth_surface(out.get("shared_facts"))
    out["memory_surface"] = build_trade_report_memory_surface(story_input)
    out["memory_application_surface"] = build_trade_memory_application_surface(story_input)
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


def _is_market_context_noise_bullet(value: Any) -> bool:
    text = _clip(value, max_len=260).strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered.startswith("news input:"):
        return True
    if lowered.startswith("news query targets:"):
        return True
    if "headlines were considered across" in lowered:
        return True
    if text.startswith("뉴스 입력 요약은"):
        return True
    if text.startswith("뉴스 조회 대상은"):
        return True
    if "관련 헤드라인" in text and "반영" in text:
        return True
    return False


def _sanitize_market_context_summary(value: Any) -> str:
    text = _clip(value, max_len=600).strip()
    if not text:
        return ""
    cleaned = re.sub(
        r"[^.]*\b\d+\s*headlines were considered across \d+\s*targets[^.]*\.?\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"[^.]*관련 헤드라인\s*\d+건[^.]*\.?\s*",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .")
    return cleaned or text


def _num_opt(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _clean_news_title(value: Any, *, max_len: int = 220) -> str:
    text = html.unescape(_clip(value, max_len=max_len).strip())
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .;")
    return text


def _market_token_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "neutral": "중립",
        "bullish": "강세",
        "bearish": "약세",
        "pullback": "눌림목",
        "breakout": "돌파",
        "trend": "추세",
        "defensive": "방어적",
        "risk_off": "위험회피",
        "risk_on": "위험선호",
        "not_captured": "직접 캡처되지 않음",
        "unavailable": "확인 불가",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _theme_token_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "broad_market_leaders": "브로드마켓 리더",
        "semiconductor_leaders": "반도체 리더",
        "high_beta_leaders": "고베타 리더",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _theme_text(values: Any, *, max_items: int = 4) -> str:
    labels = [_theme_token_label(item) for item in _listify(values, max_items=max_items, max_len=80)]
    labels = [item for item in labels if item]
    if len(labels) == 2:
        return f"{labels[0]}와 {labels[1]}"
    if len(labels) >= 3:
        return ", ".join(labels[:-1]) + f", {labels[-1]}"
    return labels[0] if labels else "not_captured"


def _theme_linkage_label(values: Any) -> str:
    theme_values = [str(item or "").strip().lower() for item in _listify(values, max_items=4, max_len=80)]
    if "broad_market_leaders" in theme_values:
        return "시장 주도 대형주 우위"
    if "semiconductor_leaders" in theme_values:
        return "반도체 리더 우위"
    if "high_beta_leaders" in theme_values:
        return "고베타 리더 우위"
    themed = _theme_text(values, max_items=2)
    return f"{themed} 맥락" if themed and themed != "not_captured" else "시장 맥락"


def _risk_mode_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "balanced": "균형형",
        "conservative": "보수형",
        "aggressive": "공격형",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _strategy_constraint_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "defensive_assets": "방어 자산",
        "counter_trend_low_liquidity": "역추세 저유동성",
        "high_beta_leaders": "고베타 리더",
        "semiconductor_leaders": "반도체 리더",
        "broad_market_leaders": "브로드마켓 리더",
        "illiquid_microcap": "저유동성 소형주",
        "headline_only_momentum": "헤드라인 추격 모멘텀",
        "high_gap_speculative": "갭 급등 투기성 종목",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _strategy_constraint_text(values: Any, *, max_items: int = 4) -> str:
    labels = [_strategy_constraint_label(item) for item in _listify(values, max_items=max_items, max_len=80)]
    labels = [item for item in labels if item]
    if len(labels) >= 3:
        return ", ".join(labels[:-1]) + f", {labels[-1]}"
    if len(labels) == 2:
        return ", ".join(labels)
    return labels[0] if labels else ""


def _scanner_bias_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "prefer_shallow_pullback_candidates": "얕은 눌림목 후보 선호",
        "penalize_overextended": "과확장 후보 패널티",
        "prefer_reclaim_candidates": "재회복 후보 선호",
        "prefer_volume_confirmation": "거래량 확인 후보 선호",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _scanner_bias_text(summary: Any) -> str:
    data = summary if isinstance(summary, dict) else {}
    active_values = data.get("active_biases")
    if isinstance(active_values, str):
        raw = active_values.strip()
        if raw.startswith("[") and raw.endswith("]"):
            try:
                parsed = ast.literal_eval(raw)
                if isinstance(parsed, list):
                    active_values = parsed
            except Exception:
                pass
    active = [_scanner_bias_label(item) for item in _listify(active_values, max_items=6, max_len=80)]
    active = [item for item in active if item]
    strength = _clip(data.get("bias_strength"), max_len=24).strip().lower()
    strength_label = {"low": "낮음", "medium": "중간", "high": "높음"}.get(strength, _clip(strength, max_len=24))
    if active:
        joined = ", ".join(active)
        if strength_label:
            return f"{joined} (강도 {strength_label})"
        return joined
    raw_summary = _clip(data.get("summary"), max_len=220)
    return raw_summary


def _extract_us_indices_snapshot(events: Any) -> Dict[str, float]:
    for row in _listify(events, max_items=8, max_len=220):
        match = re.search(
            r"sp500=([+-]?\d+(?:\.\d+)?)%\s+nasdaq=([+-]?\d+(?:\.\d+)?)%\s+dow=([+-]?\d+(?:\.\d+)?)%",
            str(row),
            flags=re.IGNORECASE,
        )
        if not match:
            continue
        return {
            "sp500": float(match.group(1)),
            "nasdaq": float(match.group(2)),
            "dow": float(match.group(3)),
        }
    return {}


def _format_pct_points(value: Any) -> str:
    number = _num_opt(value)
    if number is None:
        return "-"
    return f"{number:+.2f}%"


def _select_symbol_headline(headlines: Any, symbol: str = "") -> str:
    cleaned_rows = [_clean_news_title(row) for row in _listify(headlines, max_items=6, max_len=240)]
    cleaned_rows = [row for row in cleaned_rows if row]
    if not cleaned_rows:
        return ""
    symbol_token = str(symbol or "").strip()
    if symbol_token:
        for row in cleaned_rows:
            if row.startswith(f"{symbol_token}:"):
                return row
    return cleaned_rows[0]


def _join_headlines(headlines: Any, *, max_items: int = 2, max_len: int = 180) -> str:
    cleaned = [_clean_news_title(row, max_len=max_len) for row in _listify(headlines, max_items=max_items, max_len=max_len)]
    cleaned = [row for row in cleaned if row]
    return "; ".join(cleaned)


def _build_market_context_summary(section: Any, *, scanner_reason: Dict[str, Any] | None = None) -> str:
    market = section if isinstance(section, dict) else {}
    scanner = scanner_reason if isinstance(scanner_reason, dict) else {}
    regime = _market_token_label(market.get("regime")) or ""
    market_sentiment = _market_token_label(market.get("market_sentiment")) or ""
    selected_playbook = _market_token_label(market.get("selected_playbook")) or _clip(market.get("selected_playbook"), max_len=40)
    playbook = _market_token_label(market.get("playbook")) or selected_playbook or "not_captured"
    themes = _theme_text(market.get("themes") or market.get("preferred_themes"), max_items=3)
    sentiment = _num_opt(market.get("global_sentiment_score"))
    fear_index = market.get("fear_index") if isinstance(market.get("fear_index"), dict) else {}
    vix_level = _num_opt(market.get("vix_level"))
    if vix_level is None:
        vix_level = _num_opt(fear_index.get("level"))
    headline_count = int(float(market.get("headline_count") or 0)) if _num_opt(market.get("headline_count")) is not None else 0
    query_count = int(float(market.get("news_query_count") or 0)) if _num_opt(market.get("news_query_count")) is not None else 0
    us_indices = _extract_us_indices_snapshot(market.get("key_events") or market.get("key_events_hint"))
    selected_symbol = _clip(scanner.get("selected_symbol"), max_len=24)

    regime_missing = regime in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    sentiment_missing = market_sentiment in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    playbook_known = playbook not in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    themes_known = themes not in {"", "not_captured", "unknown", "직접 캡처되지 않음"}

    if regime_missing and sentiment_missing and (playbook_known or themes_known):
        frame_bits: List[str] = []
        if playbook_known:
            frame_bits.append(f"플레이북 {playbook}")
        if themes_known:
            frame_bits.append(f"핵심 테마 {themes}")
        frame_text = ", ".join(frame_bits) if frame_bits else "핵심 프레임 미확인"
        sentences: List[str] = [
            f"시장 상태/심리 직접 캡처는 제한적이지만, {frame_text} 기준으로 정리했습니다."
        ]
    else:
        regime_text = regime or "not_captured"
        sentences = [
            f"시장 상태 {regime_text} 기준에서 플레이북 {playbook}로 운용했습니다."
        ]

    metric_bits: List[str] = []
    if sentiment is not None:
        metric_bits.append(f"글로벌 감성 {sentiment:.3f}")
    if vix_level is not None:
        metric_bits.append(f"VIX {vix_level:.2f}")
    if metric_bits:
        sentences.append(", ".join(metric_bits) + " 입력은 시장 안정성 점검에 반영되었습니다.")
    if us_indices:
        sentences.append(
            f"미국 지수는 S&P500 {_format_pct_points(us_indices.get('sp500'))}, "
            f"Nasdaq {_format_pct_points(us_indices.get('nasdaq'))}, Dow {_format_pct_points(us_indices.get('dow'))}였습니다."
        )
    if headline_count or query_count:
        sentences.append(
            f"뉴스 입력 {headline_count}건과 조회 대상 {query_count}개를 함께 반영했습니다."
        )
    if themes_known:
        theme_sentence = f"핵심 테마는 {themes}로 정리됐습니다."
        if selected_symbol:
            theme_sentence = f"핵심 테마 {themes} 기준에서 {selected_symbol}이 스캐너 연결 종목으로 확인됐습니다."
        sentences.append(theme_sentence)
    return " ".join(sentences[:5]).strip()


def _build_market_context_bullets(section: Any, *, scanner_reason: Dict[str, Any] | None = None) -> List[str]:
    data = section if isinstance(section, dict) else {}
    scanner = scanner_reason if isinstance(scanner_reason, dict) else {}
    regime = _market_token_label(data.get("regime")) or ""
    market_sentiment = _market_token_label(data.get("market_sentiment")) or ""
    selected_playbook = _market_token_label(data.get("selected_playbook")) or _clip(data.get("selected_playbook"), max_len=40)
    playbook = _market_token_label(data.get("playbook")) or selected_playbook or "not_captured"
    themes = _theme_text(data.get("themes") or data.get("preferred_themes"), max_items=4)
    sentiment = _num_opt(data.get("global_sentiment_score"))
    fear_index = data.get("fear_index") if isinstance(data.get("fear_index"), dict) else {}
    vix_level = _num_opt(data.get("vix_level"))
    if vix_level is None:
        vix_level = _num_opt(fear_index.get("level"))
    vix_change = _num_opt(fear_index.get("change_pct"))
    headline_count = int(float(data.get("headline_count") or 0)) if _num_opt(data.get("headline_count")) is not None else 0
    query_count = int(float(data.get("news_query_count") or 0)) if _num_opt(data.get("news_query_count")) is not None else 0
    us_indices = _extract_us_indices_snapshot(data.get("key_events") or data.get("key_events_hint"))
    market_titles = _join_headlines(data.get("market_news_titles") or data.get("market_headlines"), max_items=2, max_len=180)
    symbol_title = _select_symbol_headline(
        data.get("candidate_news_titles") or data.get("symbol_headlines"),
        _clip(scanner.get("selected_symbol"), max_len=24),
    )
    targets = ", ".join(_listify(data.get("news_query_targets"), max_items=7, max_len=40))
    theme_source = _clip(data.get("theme_source"), max_len=80)
    theme_status = _clip(data.get("theme_source_status"), max_len=80)
    theme_reason = _clip(data.get("theme_source_reason"), max_len=160)
    theme_top = ", ".join(_listify(data.get("theme_strength_top_themes"), max_items=6, max_len=80))

    bullets: List[str] = []
    regime_missing = regime in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    sentiment_missing = market_sentiment in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    themes_known = themes not in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    if regime_missing and sentiment_missing and (playbook != "not_captured" or themes_known):
        bullets.append(
            f"시장 상태/심리 직접 캡처는 제한적이며, 플레이북 {playbook}, 핵심 테마 {themes if themes_known else 'not_captured'} 기준으로 해석했습니다."
        )
    else:
        bullets.append(
            f"시장 상태는 {regime or 'not_captured'}, 시장 심리는 {market_sentiment or 'not_captured'}, 플레이북은 {playbook}, 핵심 테마는 {themes} 기준입니다."
        )
    if sentiment is not None or vix_level is not None:
        metric = []
        if sentiment is not None:
            metric.append(f"글로벌 감성 {sentiment:.3f}")
        if vix_level is not None:
            change_text = f", 변화율 {_format_pct_points(vix_change)}" if vix_change is not None else ""
            metric.append(f"VIX {vix_level:.2f}{change_text}")
        bullets.append("변동성/심리 입력은 " + ", ".join(metric) + "입니다.")
    if us_indices:
        bullets.append(
            f"미국 지수는 S&P500 {_format_pct_points(us_indices.get('sp500'))}, "
            f"Nasdaq {_format_pct_points(us_indices.get('nasdaq'))}, Dow {_format_pct_points(us_indices.get('dow'))}였습니다."
        )
    if headline_count or query_count or targets:
        bullets.append(
            f"뉴스 입력은 {headline_count}건 헤드라인, 조회 대상은 {query_count}개"
            + (f" ({targets})" if targets else "")
            + "를 반영했습니다."
        )
    if market_titles:
        bullets.append(f"주요 시장 뉴스는 {market_titles}입니다.")
    if symbol_title:
        bullets.append(f"대표 종목/섹터 뉴스는 {symbol_title}입니다.")
    if theme_source or theme_status or theme_reason:
        bullets.append(
            "키움 테마 packet은 "
            f"source={theme_source or 'not_captured'}, "
            f"status={theme_status or 'not_captured'}, "
            f"reason={theme_reason or 'not_captured'}, "
            f"top_themes={theme_top or 'none'} 상태였습니다."
        )
    return _dedupe_list(bullets, max_items=10, max_len=260)


def _build_strategist_summary_section(
    market_context: Dict[str, Any],
    scanner_reason: Dict[str, Any],
) -> Dict[str, Any]:
    regime = _market_token_label(market_context.get("regime")) or ""
    market_sentiment = _market_token_label(market_context.get("market_sentiment")) or ""
    selected_playbook = _market_token_label(market_context.get("selected_playbook")) or _clip(market_context.get("selected_playbook"), max_len=40)
    playbook = _market_token_label(market_context.get("playbook")) or selected_playbook or "not_captured"
    themes = _theme_text(market_context.get("themes") or market_context.get("preferred_themes"), max_items=3)
    risk_mode = _risk_mode_label(market_context.get("risk_mode"))
    preferred_themes = _strategy_constraint_text(market_context.get("preferred_themes"), max_items=4)
    avoid_themes = _strategy_constraint_text(market_context.get("avoid_themes"), max_items=4)
    scanner_bias = _scanner_bias_text(market_context.get("scanner_bias_summary"))
    sentiment = _num_opt(market_context.get("global_sentiment_score"))
    fear_index = market_context.get("fear_index") if isinstance(market_context.get("fear_index"), dict) else {}
    vix_level = _num_opt(market_context.get("vix_level"))
    if vix_level is None:
        vix_level = _num_opt(fear_index.get("level"))
    headline_count = int(float(market_context.get("headline_count") or 0)) if _num_opt(market_context.get("headline_count")) is not None else 0
    query_count = int(float(market_context.get("news_query_count") or 0)) if _num_opt(market_context.get("news_query_count")) is not None else 0
    query_targets = ", ".join(_listify(market_context.get("news_query_targets"), max_items=7, max_len=32))
    stress_flags = _listify(market_context.get("stress_flags"), max_items=4, max_len=48)
    candidate_hints = _listify(market_context.get("candidate_hints"), max_items=4, max_len=48)
    selected_symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24)
    selected_rank = scanner_reason.get("selected_rank")
    selected_score = _num_opt(scanner_reason.get("selected_score"))
    selected_sources = _scanner_source_text(scanner_reason.get("selected_sources"))
    scanner_bias_applied = bool(scanner_reason.get("scanner_bias_applied"))
    contribution = scanner_reason.get("news_scanner_contribution") if isinstance(scanner_reason.get("news_scanner_contribution"), dict) else {}
    core = contribution.get("core_score_contributions") if isinstance(contribution.get("core_score_contributions"), dict) else {}
    sentiment_inputs = contribution.get("sentiment_inputs") if isinstance(contribution.get("sentiment_inputs"), dict) else {}

    def _core_value_opt(key: str) -> Optional[float]:
        row = core.get(key)
        if isinstance(row, dict):
            return _num_opt(row.get("value"))
        return _num_opt(row)

    sentiment_contrib = _core_value_opt("sentiment")
    if sentiment_contrib is None:
        sentiment_contrib = _num_opt(sentiment_inputs.get("weighted_sentiment_score_contribution"))
    theme_boost = _core_value_opt("theme_boost")
    market_titles = _join_headlines(market_context.get("market_news_titles") or market_context.get("market_headlines"), max_items=1, max_len=110)
    symbol_title = _select_symbol_headline(
        market_context.get("candidate_news_titles") or market_context.get("symbol_headlines"),
        selected_symbol,
    )
    theme_linkage = _theme_linkage_label(market_context.get("themes") or market_context.get("preferred_themes"))
    theme_source = _clip(market_context.get("theme_source"), max_len=80)
    theme_status = _clip(market_context.get("theme_source_status"), max_len=80)
    theme_reason = _clip(market_context.get("theme_source_reason"), max_len=160)
    theme_top = ", ".join(_listify(market_context.get("theme_strength_top_themes"), max_items=6, max_len=80))

    regime_missing = regime in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    sentiment_missing = market_sentiment in {"", "not_captured", "unknown", "직접 캡처되지 않음"}
    themes_known = themes not in {"", "not_captured", "unknown", "직접 캡처되지 않음"}

    if regime_missing and sentiment_missing:
        frame_bits: List[str] = []
        if playbook not in {"", "not_captured", "unknown", "직접 캡처되지 않음"}:
            frame_bits.append(f"플레이북 {playbook}")
        if themes_known:
            frame_bits.append(f"핵심 테마 {themes}")
        frame_text = ", ".join(frame_bits) if frame_bits else "핵심 프레임 미확인"
        summary_parts = [f"전략가는 시장 상태 직접 캡처가 제한적이어서 {frame_text} 중심으로 정리했습니다."]
    else:
        summary_parts = [f"전략가는 시장을 {regime or 'not_captured'}, 시장 심리를 {market_sentiment or 'not_captured'}으로 해석했고 {playbook} 플레이북과 {themes} 프레임을 유지했습니다."]
    if not stress_flags:
        summary_parts.append("뚜렷한 스트레스 신호는 확인되지 않았습니다.")
    if selected_symbol:
        scanner_sentence = f"스캐너 연결 종목은 {selected_symbol}입니다."
        if selected_rank not in (None, "") and selected_score is not None:
            scanner_sentence = f"스캐너 연결 종목은 {selected_symbol}이며 순위 {selected_rank}, 점수 {selected_score:.3f}입니다."
        summary_parts.append(scanner_sentence)
    summary = " ".join(summary_parts)

    bullets: List[str] = []
    input_bits: List[str] = []
    if sentiment is not None:
        input_bits.append(f"글로벌 감성 {sentiment:.3f}")
    if vix_level is not None:
        input_bits.append(f"VIX {vix_level:.2f}")
    if headline_count or query_count:
        input_bits.append(f"뉴스 {headline_count}건/{query_count}대상")
    us_indices = _extract_us_indices_snapshot(market_context.get("key_events") or market_context.get("key_events_hint"))
    if us_indices:
        input_bits.append(
            f"미국 지수 S&P500 {_format_pct_points(us_indices.get('sp500'))}, Nasdaq {_format_pct_points(us_indices.get('nasdaq'))}, Dow {_format_pct_points(us_indices.get('dow'))}"
        )
    if input_bits:
        bullets.append("핵심 입력은 " + ", ".join(input_bits) + "입니다.")

    if regime_missing and sentiment_missing:
        interpretation_bits = [f"플레이북 {playbook}"]
        if themes_known:
            interpretation_bits.append(f"핵심 테마 {themes}")
        interpretation_bits.append("스트레스 신호 없음" if not stress_flags else "스트레스 신호 " + ", ".join(stress_flags))
        bullets.append("전략 해석은 " + ", ".join(interpretation_bits) + " 기준이었습니다.")
    else:
        interpretation_bits = [f"시장 상태 {regime}", f"시장 심리 {market_sentiment}", f"플레이북 {playbook}", f"핵심 테마 {themes}"]
        if stress_flags:
            interpretation_bits.append("스트레스 신호 " + ", ".join(stress_flags))
        else:
            interpretation_bits.append("스트레스 신호 없음")
        bullets.append("전략 해석은 " + ", ".join(interpretation_bits) + " 기준이었습니다.")

    if query_targets:
        bullets.append(f"전략가가 관찰한 대상은 다음과 같았습니다: {query_targets}.")
    if risk_mode or selected_playbook:
        if risk_mode and selected_playbook:
            bullets.append(f"전략가 운용 기준은 리스크 모드 {risk_mode}이었고, 선택 플레이북은 {selected_playbook}이었습니다.")
        elif risk_mode:
            bullets.append(f"전략가 운용 기준은 리스크 모드 {risk_mode}였습니다.")
        else:
            bullets.append(f"전략가 운용 기준에서 선택 플레이북은 {selected_playbook}이었습니다.")
    if preferred_themes or avoid_themes:
        theme_pref_bits: List[str] = []
        if preferred_themes:
            theme_pref_bits.append(f"선호 테마 {preferred_themes}")
        if avoid_themes:
            theme_pref_bits.append(f"회피 테마 {avoid_themes}")
        bullets.append("전략가 선호/회피 기준은 " + ", ".join(theme_pref_bits) + "이었습니다.")
    if theme_source or theme_status or theme_reason:
        bullets.append(
            "전략가 테마 강도 입력은 "
            f"source={theme_source or 'not_captured'}, "
            f"status={theme_status or 'not_captured'}, "
            f"reason={theme_reason or 'not_captured'}, "
            f"top_themes={theme_top or 'none'} 기준이었습니다."
        )
    if scanner_bias:
        bullets.append(f"스캐너 바이어스는 {scanner_bias} 기준이었습니다.")
    if candidate_hints:
        bullets.append("전략가 후보 힌트는 " + ", ".join(candidate_hints) + "였습니다.")
    if market_titles or symbol_title:
        if market_titles and symbol_title and selected_symbol:
            linkage_line = f"뉴스 연결 해석은 시장 뉴스로 {theme_linkage} 맥락을 확인했고, 종목 뉴스로 {selected_symbol} 선정 근거를 보강했습니다."
        elif market_titles:
            linkage_line = f"뉴스 연결 해석은 시장 뉴스로 {theme_linkage} 맥락을 확인했습니다."
        elif symbol_title and selected_symbol:
            linkage_line = f"뉴스 연결 해석은 종목 뉴스로 {selected_symbol} 선정 근거를 보강했습니다."
        else:
            linkage_line = "뉴스 연결 해석은 headline evidence로 확인됐습니다."
        if selected_sources:
            linkage_line += f". 선정 소스는 {selected_sources}였습니다."
        evidence_parts: List[str] = []
        if market_titles:
            evidence_parts.append(f"시장: {market_titles}")
        if symbol_title:
            evidence_parts.append(f"종목: {symbol_title}")
        if evidence_parts:
            linkage_line += " 참조 headline: " + " / ".join(evidence_parts)
        bullets.append(linkage_line)
        if selected_sources:
            bullets.append(f"이 해석은 {selected_sources} 축으로 연결했습니다.")
    contribution_bits: List[str] = []
    if sentiment_contrib is not None:
        contribution_bits.append(f"감성 기여 {sentiment_contrib:+.3f}")
    if theme_boost is not None:
        contribution_bits.append(f"테마 가점 {theme_boost:+.3f}")
    if selected_sources:
        contribution_bits.append(f"선정 소스 {selected_sources}")
    if scanner_bias_applied:
        contribution_bits.append("바이어스 적용")
    if contribution_bits:
        bullets.append("스캐너 반영은 " + ", ".join(contribution_bits) + " 기준으로 정리됐습니다.")
    if selected_symbol:
        symbol_bits = [selected_symbol]
        if selected_rank not in (None, ""):
            symbol_bits.append(f"{selected_rank}위")
        if selected_score is not None:
            symbol_bits.append(f"점수 {selected_score:.3f}")
        bullets.append("종목 연결은 " + ", ".join(symbol_bits) + "로 확인됩니다.")
    return {
        "summary": summary,
        "bullets": _dedupe_list(bullets, max_items=12, max_len=260),
    }


def _build_market_scanner_linkage_bullet(section: Any, scanner_reason: Dict[str, Any] | None = None) -> str:
    market = section if isinstance(section, dict) else {}
    scanner = scanner_reason if isinstance(scanner_reason, dict) else {}
    symbol = _clip(scanner.get("selected_symbol"), max_len=24)
    if not symbol:
        return ""
    playbook = _clip(market.get("playbook"), max_len=40) or "not_captured"
    source_text = ", ".join(_listify(scanner.get("selected_sources"), max_items=4, max_len=80))
    contribution = scanner.get("news_scanner_contribution") if isinstance(scanner.get("news_scanner_contribution"), dict) else {}
    core = contribution.get("core_score_contributions") if isinstance(contribution.get("core_score_contributions"), dict) else {}
    sentiment_inputs = contribution.get("sentiment_inputs") if isinstance(contribution.get("sentiment_inputs"), dict) else {}

    def _core_value_opt(key: str) -> Optional[float]:
        row = core.get(key)
        if isinstance(row, dict):
            return _num_opt(row.get("value"))
        return _num_opt(row)

    score_value = _num_opt(scanner.get("selected_score"))
    sentiment_contrib = _core_value_opt("sentiment")
    if sentiment_contrib is None:
        sentiment_contrib = _num_opt(sentiment_inputs.get("weighted_sentiment_score_contribution"))
    theme_boost = _core_value_opt("theme_boost")
    global_sentiment_value = _num_opt(sentiment_inputs.get("global_sentiment_score"))
    if global_sentiment_value is None:
        global_sentiment_value = _num_opt(market.get("global_sentiment_score"))
    vix_value = _num_opt(market.get("vix_level"))

    metric_bits: List[str] = []
    if score_value is not None:
        metric_bits.append(f"종합 점수 {score_value:.3f}")
    if sentiment_contrib is not None:
        metric_bits.append(f"감성 기여 {sentiment_contrib:+.3f}")
    if theme_boost is not None:
        metric_bits.append(f"테마 가점 {theme_boost:+.3f}")
    if global_sentiment_value is not None:
        metric_bits.append(f"글로벌 감성 {global_sentiment_value:.3f}")
    if vix_value is not None:
        metric_bits.append(f"VIX {vix_value:.2f}")

    parts: List[str] = [f"종목 {symbol}을 {playbook} 플레이북 기준으로 선정했고"]
    if metric_bits:
        parts.append(", ".join(metric_bits))
    if source_text:
        parts.append(f"선정 소스 {source_text}")
    return "Scanner linkage: " + ", ".join(parts)


def _fmt_num(value: Any, *, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return "-"


def _scanner_basis_text(scanner_reason: Dict[str, Any]) -> str:
    def _basis_label(value: Any) -> str:
        raw = _clip(value, max_len=120).strip()
        mapping = {
            "trading value": "거래대금",
            "theme and sector alignment": "섹터·테마 정렬",
            "sentiment support": "감성 지원",
            "top value": "거래대금 상위",
            "top volume": "거래량 상위",
            "momentum": "모멘텀",
            "trend": "추세",
            "confidence": "신뢰도",
        }
        return mapping.get(raw.lower(), raw)

    basis = scanner_reason.get("ranking_basis")
    if isinstance(basis, list):
        return ", ".join(_basis_label(item) for item in _listify(basis, max_items=4, max_len=80) if _basis_label(item))
    return _basis_label(_clip(basis, max_len=220))


def _scanner_source_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "top_value": "거래대금 상위",
        "top_volume": "거래량 상위",
        "sector_theme": "섹터·테마 정렬",
        "sentiment": "감성 반영",
        "news": "뉴스 반영",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _scanner_source_text(values: Any) -> str:
    labels = [_scanner_source_label(item) for item in _listify(values, max_items=4, max_len=80)]
    labels = [item for item in labels if item]
    if len(labels) == 2:
        return f"{labels[0]}와 {labels[1]}"
    if len(labels) >= 3:
        return ", ".join(labels[:-1]) + f", {labels[-1]}"
    return ", ".join(labels)


def _scanner_score_driver_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "trading_value": "거래대금",
        "momentum": "모멘텀",
        "trend": "추세",
        "ma_alignment": "이동평균 정렬",
        "adx_trend": "ADX 추세",
        "volume_surge": "거래량 스파이크",
        "intraday_strength": "장중 강도",
        "vwap_alignment": "VWAP 정렬",
        "theme_boost": "테마 가점",
        "sentiment": "감성",
        "cross_section_rank": "횡단면 순위",
        "entry_compatibility_bias": "진입 적합성",
        "rank_bonus": "순위 가점",
        "risk_penalty": "리스크 패널티",
        "repeat_symbol_penalty": "중복 종목 패널티",
        "scanner_bias": "스캐너 바이어스",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _scanner_chart_feature_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "engine_ma20_gap": "20일선 이격",
        "engine_ma60": "60일선",
        "engine_ma120": "120일선",
        "engine_adx14": "ADX14",
        "engine_trend_strength": "추세 강도",
        "engine_volume_spike20": "20봉 거래량 스파이크",
        "engine_volatility20": "20봉 변동성",
        "engine_vwap_distance": "VWAP 이격",
        "engine_sector_relative_strength": "섹터 상대강도",
        "engine_cross_section_rank": "횡단면 순위",
        "engine_regime": "레짐",
        "engine_signal_score": "신호 점수",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _scanner_ranked_candidates(scanner_reason: Dict[str, Any]) -> List[Dict[str, Any]]:
    for key in ("top_candidates", "ranked_candidates"):
        rows = [row for row in list(scanner_reason.get(key) or []) if isinstance(row, dict)]
        if rows:
            return rows[:5]
    trace = scanner_reason.get("scanner_selection_trace") if isinstance(scanner_reason.get("scanner_selection_trace"), dict) else {}
    return [row for row in list(trace.get("ranked_candidates") or []) if isinstance(row, dict)][:5]


def _scanner_selected_row(scanner_reason: Dict[str, Any]) -> Dict[str, Any]:
    selected_symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24)
    ranked_rows = _scanner_ranked_candidates(scanner_reason)
    if selected_symbol:
        for row in ranked_rows:
            if _clip(row.get("symbol"), max_len=24) == selected_symbol:
                return dict(row)
    fallback_ctx = _scanner_monitor_fallback_context(scanner_reason)
    if fallback_ctx["used"] and selected_symbol:
        trace = scanner_reason.get("scanner_selection_trace") if isinstance(scanner_reason.get("scanner_selection_trace"), dict) else {}
        news = trace.get("news_scanner_contribution") if isinstance(trace.get("news_scanner_contribution"), dict) else {}
        row = {
            "symbol": selected_symbol,
            "rank": scanner_reason.get("selected_rank") or trace.get("selected_rank"),
            "score_total": scanner_reason.get("selected_score") or trace.get("selected_score") or news.get("selected_score_total"),
            "confidence": scanner_reason.get("confidence") or trace.get("confidence"),
            "risk_score": scanner_reason.get("risk_score") or trace.get("risk_score"),
        }
        return {key: value for key, value in row.items() if value not in (None, "")}
    return dict(ranked_rows[0]) if ranked_rows else {}


def _scanner_monitor_fallback_context(scanner_reason: Dict[str, Any]) -> Dict[str, Any]:
    trace = scanner_reason.get("scanner_selection_trace") if isinstance(scanner_reason.get("scanner_selection_trace"), dict) else {}
    return {
        "used": bool(scanner_reason.get("monitor_fallback_used") or trace.get("monitor_fallback_used")),
        "scanner_top_pick_symbol": _clip(
            scanner_reason.get("scanner_top_pick_symbol") or trace.get("scanner_top_pick_symbol"),
            max_len=24,
        ),
        "reason": _operatorize_report_text(
            scanner_reason.get("monitor_fallback_reason") or trace.get("monitor_fallback_reason")
        ),
        "trigger_reason": _operatorize_report_text(
            scanner_reason.get("monitor_trigger_reason") or trace.get("monitor_trigger_reason")
        ),
    }


def _scanner_chart_feature_coverage(scanner_reason: Dict[str, Any]) -> Dict[str, Any]:
    trace = scanner_reason.get("scanner_selection_trace") if isinstance(scanner_reason.get("scanner_selection_trace"), dict) else {}
    row = trace.get("chart_feature_coverage") if isinstance(trace.get("chart_feature_coverage"), dict) else {}
    return dict(row)


def _build_scanner_driver_summary(scanner_reason: Dict[str, Any]) -> str:
    driver_source = (
        scanner_reason.get("selected_symbol_score_drivers")
        if isinstance(scanner_reason.get("selected_symbol_score_drivers"), dict)
        else {}
    )
    if not driver_source:
        trace = scanner_reason.get("scanner_selection_trace") if isinstance(scanner_reason.get("scanner_selection_trace"), dict) else {}
        driver_source = trace.get("selected_symbol_score_drivers") if isinstance(trace.get("selected_symbol_score_drivers"), dict) else {}
    driver_rows: List[tuple[str, float]] = []
    for key, value in dict(driver_source or {}).items():
        numeric = _num_opt(value)
        if numeric is None or numeric <= 0:
            continue
        driver_rows.append((_scanner_score_driver_label(key), numeric))
    if not driver_rows:
        return ""
    driver_rows.sort(key=lambda item: item[1], reverse=True)
    top_rows = [f"{label} {value:.3f}" for label, value in driver_rows[:3]]
    return ", ".join(top_rows)


def _build_runner_up_comparison(
    row: Dict[str, Any],
    *,
    selected_symbol: str,
    selected_score: Optional[float],
    selected_risk: Optional[float],
) -> str:
    runner_symbol = _clip(row.get("symbol"), max_len=24)
    if not runner_symbol:
        return ""
    parts: List[str] = []
    runner_score = _num_opt(row.get("score_total"))
    runner_risk = _num_opt(row.get("risk_score"))
    if runner_score is not None and selected_score is not None:
        gap = selected_score - runner_score
        if gap >= 0:
            parts.append(
                f"종합 점수 {runner_score:.3f}로 {selected_symbol}({selected_score:.3f})보다 {gap:.3f} 낮았습니다"
            )
    if runner_risk is not None and selected_risk is not None and runner_risk > selected_risk:
        parts.append(
            f"리스크 점수 {runner_risk:.3f}로 {selected_symbol}({selected_risk:.3f})보다 높았습니다"
        )
    if not parts:
        why_text = _clip(row.get("why") or row.get("summary"), max_len=220)
        if why_text:
            parts.append(_operatorize_report_text(why_text))
    if not parts:
        return ""
    return f"{runner_symbol}은 " + ". ".join(parts) + "."


def _build_scanner_choice_bullets(
    scanner_reason: Dict[str, Any],
    market_context: Dict[str, Any],
) -> List[str]:
    symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24) or "선정 종목"
    rank = scanner_reason.get("selected_rank")
    universe = scanner_reason.get("universe_size")
    score_value = _num_opt(scanner_reason.get("selected_score"))
    confidence_value = _num_opt(scanner_reason.get("confidence"))
    ranked_rows = _scanner_ranked_candidates(scanner_reason)
    selected_row = _scanner_selected_row(scanner_reason)
    selected_risk = _num_opt(selected_row.get("risk_score"))
    fallback_ctx = _scanner_monitor_fallback_context(scanner_reason)
    basis = _scanner_basis_text(scanner_reason)
    source_text = _scanner_source_text(scanner_reason.get("selected_sources"))
    playbook = _market_token_label(market_context.get("playbook")) or _clip(market_context.get("playbook"), max_len=32)
    driver_summary = _build_scanner_driver_summary(scanner_reason)
    coverage = _scanner_chart_feature_coverage(scanner_reason)

    bullets: List[str] = []
    if fallback_ctx["used"] and fallback_ctx["scanner_top_pick_symbol"]:
        rank_text = f"{rank}위" if rank not in (None, "") else "후보"
        fallback_line = (
            f"스캐너 상위 후보 {fallback_ctx['scanner_top_pick_symbol']}은 모니터 단계에서 보류됐고 "
            f"{symbol}은 차순위 재평가 {rank_text}로 실제 진입 종목이 됐습니다."
        )
        if fallback_ctx["reason"]:
            fallback_line = (
                f"스캐너 상위 후보 {fallback_ctx['scanner_top_pick_symbol']}은 {fallback_ctx['reason']} 이유로 보류됐고 "
                f"{symbol}은 차순위 재평가 {rank_text}로 실제 진입 종목이 됐습니다."
            )
        bullets.append(fallback_line)
        if fallback_ctx["trigger_reason"]:
            bullets.append(f"실제 진입은 {fallback_ctx['trigger_reason']} 조건에서 확정됐습니다.")
    if universe not in (None, "") and rank not in (None, ""):
        bullets.append(f"총 {int(universe)}개 후보를 비교했고 {symbol}이 {rank}위로 선정됐습니다.")
    elif rank not in (None, ""):
        bullets.append(f"{symbol}의 최종 선정 순위는 {rank}위였습니다.")
    if score_value is not None:
        metric_bits = [f"종합 점수 {score_value:.3f}"]
        if confidence_value is not None:
            metric_bits.append(f"신뢰도 {confidence_value:.2f}")
        if selected_risk is not None:
            metric_bits.append(f"리스크 {selected_risk:.3f}")
        bullets.append(", ".join(metric_bits) + "로 집계됐습니다.")
    if basis:
        bullets.append(f"주요 선정 기준은 {basis} 축이었습니다.")
    if source_text:
        bullets.append(f"선정에는 {source_text}이 반영됐습니다.")
    if driver_summary:
        bullets.append(f"주요 점수 기여는 {driver_summary}였습니다.")
    if playbook:
        bullets.append(f"전략가 플레이북 {playbook}과 정렬된 후보였습니다.")
    if ranked_rows:
        ranked_text = " / ".join(
            f"#{int(float(row.get('rank') or idx + 1))} {_clip(row.get('symbol'), max_len=24)}({_fmt_num(row.get('score_total'))})"
            for idx, row in enumerate(ranked_rows[:3])
            if _clip(row.get("symbol"), max_len=24)
        )
        if ranked_text:
            bullets.append(f"상위 후보는 {ranked_text} 순이었습니다.")
    if coverage:
        present = int(float(coverage.get("present") or 0)) if _num_opt(coverage.get("present")) is not None else 0
        total = int(float(coverage.get("total") or 0)) if _num_opt(coverage.get("total")) is not None else 0
        missing = [
            _scanner_chart_feature_label(item)
            for item in _listify(coverage.get("missing_keys"), max_items=4, max_len=80)
            if _scanner_chart_feature_label(item)
        ]
        coverage_text = f"차트 피처 커버리지는 {present}/{total}였습니다." if present and total else ""
        if coverage_text and missing:
            coverage_text += f" 누락된 항목은 {', '.join(missing)}이었습니다."
        elif missing:
            coverage_text = f"누락된 차트 피처는 {', '.join(missing)}였습니다."
        if coverage_text:
            bullets.append(coverage_text)
    for row in list(scanner_reason.get("runner_ups") or [])[:2]:
        if isinstance(row, dict):
            rendered = _build_runner_up_comparison(
                row,
                selected_symbol=symbol,
                selected_score=score_value,
                selected_risk=selected_risk,
            )
            if rendered:
                bullets.append(rendered)
    return _dedupe_list(bullets, max_items=10, max_len=260)


def _build_scanner_choice_summary(scanner_reason: Dict[str, Any], market_context: Dict[str, Any]) -> str:
    symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24) or "선정 종목"
    rank = scanner_reason.get("selected_rank")
    universe = scanner_reason.get("universe_size")
    score_value = _num_opt(scanner_reason.get("selected_score"))
    basis = _scanner_basis_text(scanner_reason)
    sources = _scanner_source_text(scanner_reason.get("selected_sources"))
    playbook = _market_token_label(market_context.get("playbook")) or _clip(market_context.get("playbook"), max_len=32)
    confidence_value = _num_opt(scanner_reason.get("confidence"))
    ranked_rows = _scanner_ranked_candidates(scanner_reason)
    selected_row = _scanner_selected_row(scanner_reason)
    selected_risk = _num_opt(selected_row.get("risk_score"))
    fallback_ctx = _scanner_monitor_fallback_context(scanner_reason)
    driver_summary = _build_scanner_driver_summary(scanner_reason)
    comparison_bits: List[str] = []
    for row in list(scanner_reason.get("runner_ups") or [])[:2]:
        if not isinstance(row, dict):
            continue
        rendered = _build_runner_up_comparison(
            row,
            selected_symbol=symbol,
            selected_score=score_value,
            selected_risk=selected_risk,
        )
        if rendered:
            comparison_bits.append(rendered.rstrip("."))

    if fallback_ctx["used"] and fallback_ctx["scanner_top_pick_symbol"]:
        rank_text = f"{rank}위" if rank not in (None, "") else "후보"
        summary = (
            f"스캐너 상위 후보 {fallback_ctx['scanner_top_pick_symbol']}이 모니터 단계에서 보류된 뒤 "
            f"{symbol}이 차순위 재평가 {rank_text}로 실제 진입 종목에 선택됐습니다"
        )
        if fallback_ctx["reason"]:
            summary = (
                f"스캐너 상위 후보 {fallback_ctx['scanner_top_pick_symbol']}이 {fallback_ctx['reason']} 이유로 보류된 뒤 "
                f"{symbol}이 차순위 재평가 {rank_text}로 실제 진입 종목에 선택됐습니다"
            )
    elif universe not in (None, "") and rank == 1:
        summary = f"{symbol}은 총 {int(universe)}개 후보 중 1위로 선정됐습니다"
    elif rank == 1:
        summary = f"{symbol}은 스캐너 후보 중 최종 1순위였습니다"
    else:
        summary = f"{symbol}이 스캐너 후보로 선정됐습니다"
    if universe not in (None, "") and rank not in (None, ""):
        if not (rank == 1 and summary.endswith("선정됐습니다")):
            summary += f". 총 {int(universe)}개 후보 중 {rank}위였습니다"
    elif rank not in (None, ""):
        summary += f". 선정 순위는 {rank}위였습니다"
    elif universe not in (None, ""):
        summary += f". 비교한 후보는 총 {int(universe)}개였습니다"
    if score_value is not None:
        if fallback_ctx["used"]:
            summary += f". 실제 진입 후보의 종합 점수는 {score_value:.3f}였습니다"
        elif rank == 1:
            summary += f". 종합 점수는 {score_value:.3f}로 가장 높았습니다"
        else:
            summary += f". 종합 점수는 {score_value:.3f}였습니다"
    if basis:
        summary += f". 강했던 축은 {basis} 축이었습니다"
    details: List[str] = []
    if sources:
        details.append(f"선정에는 {sources}이 반영됐습니다")
    if driver_summary:
        details.append(f"핵심 점수 기여는 {driver_summary}였습니다")
    if confidence_value is not None:
        details.append(f"신뢰도는 {confidence_value:.2f} 수준이었습니다")
    if selected_risk is not None:
        details.append(f"리스크는 {selected_risk:.3f} 수준이었습니다")
    if playbook:
        details.append(f"전략가 플레이북 {playbook}과도 정렬됐습니다")
    if details:
        summary += ". " + ". ".join(details) + "."
    if comparison_bits:
        summary += " " + ". ".join(comparison_bits) + "."
    return summary


def _build_scanner_candidate_comparison_section(
    scanner_reason: Dict[str, Any],
    market_context: Dict[str, Any],
) -> Dict[str, Any]:
    ranked_rows = _scanner_ranked_candidates(scanner_reason)
    runner_ups = [row for row in list(scanner_reason.get("runner_ups") or []) if isinstance(row, dict)]
    runner_ups_lost = [row for row in list(scanner_reason.get("runner_ups_lost") or []) if isinstance(row, dict)]
    symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24) or "?? ?? ???"
    universe = scanner_reason.get("universe_size")
    if not ranked_rows and universe in (None, "", 0):
        if runner_ups or runner_ups_lost:
            bullets: List[str] = []
            for row in runner_ups[:2]:
                comp_symbol = _clip(row.get("symbol"), max_len=24)
                comp_rank = _clip(row.get("rank"), max_len=8) or "?"
                comp_score = _num_opt(row.get("score_total"))
                comp_why = _clip(row.get("why"), max_len=160)
                if not comp_symbol:
                    continue
                detail = f"{comp_symbol}? rank {comp_rank}"
                if comp_score is not None:
                    detail += f", score {comp_score:.3f}"
                if comp_why:
                    detail += f", ?? ??? {comp_why}"
                bullets.append(detail + "???.")
            for row in runner_ups_lost[:2]:
                lost_symbol = _clip(row.get("symbol"), max_len=24)
                lost_reason = _clip(row.get("summary") or row.get("reason"), max_len=160)
                if lost_symbol and lost_reason:
                    bullets.append(f"{lost_symbol} ?? ??? {lost_reason}???.")
                elif lost_symbol:
                    bullets.append(f"{lost_symbol}? runner-up ????? ?? ????? ?????.")
            return {
                "summary": f"{symbol} ???? runner-up ?? ??? ??? ????.",
                "bullets": _dedupe_list(bullets, max_items=12, max_len=260),
            }
        return {
            "summary": "??? ?? ??? ?? ?? ?? ?? ??? ??????.",
            "bullets": [
                f"?? ??? {symbol}?? ????? ranked candidate / runner-up trace? ?? ?? ??? ??????.",
            ],
        }

    summary = _build_scanner_choice_summary(scanner_reason, market_context)
    bullets = _build_scanner_choice_bullets(scanner_reason, market_context)
    if universe not in (None, "") and ranked_rows:
        try:
            universe_count = int(float(universe))
        except Exception:
            universe_count = 0
        bullets = [f"??? ???? ?? ?? {universe_count}?????."] + list(bullets)
    return {
        "summary": summary,
        "bullets": _dedupe_list(bullets, max_items=12, max_len=260),
    }

def _has_noisy_trade_report_text(value: Any) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return False
    noisy_tokens = (
        "cached_strategist",
        "policy_validation_status",
        "fallback_invalid",
        "strategist invocation",
        "headlines were considered",
        "market regime",
        "scanner selected ",
        "source mix:",
        "chart feature coverage",
        "trading value",
        "theme and sector alignment",
        "confidence:",
        "risk_score",
        "timeframe ",
        "breakout lookback",
        "volume lookback",
        "volume_ratio_min",
        "min_extended_from_vwap_pct",
        "max_extended_from_vwap_pct",
    )
    return any(token in raw for token in noisy_tokens)


def _scanner_check_name_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "liquidity filter": "유동성 점검",
        "유동성 필터": "유동성 점검",
        "turnover filter": "회전율 점검",
        "회전율 필터": "회전율 점검",
        "sector/theme alignment": "섹터·테마 정렬 점검",
        "섹터/테마 정렬": "섹터·테마 정렬 점검",
        "chart completeness filter": "차트 피처 충실도 점검",
        "차트 완전성 필터": "차트 피처 충실도 점검",
        "sentiment gate": "시장 심리 점검",
        "시장 심리 게이트": "시장 심리 점검",
        "risk gate": "리스크 점검",
        "리스크 게이트": "리스크 점검",
        "price anomaly filter": "가격 이상치 점검",
        "가격 이상치 필터": "가격 이상치 점검",
        "spread/slippage filter": "호가 스프레드·슬리피지 점검",
        "스프레드/슬리피지 필터": "호가 스프레드·슬리피지 점검",
    }
    return mapping.get(raw, _clip(value, max_len=80) or "스캐너 점검")


def _scanner_check_status_label(value: Any) -> str:
    raw = _clip(value, max_len=40).strip().upper()
    mapping = {
        "PASS": "통과",
        "FAIL": "미통과",
        "NOT_AVAILABLE": "확인 불가",
    }
    return mapping.get(raw, _clip(value, max_len=40) or "확인 불가")


def _build_scanner_filters_summary(filters_human: Dict[str, Any]) -> str:
    checks = [row for row in list(filters_human.get("checks") or []) if isinstance(row, dict)]
    feature_coverage = filters_human.get("feature_coverage") if isinstance(filters_human.get("feature_coverage"), dict) else {}
    if not checks:
        return _clip(filters_human.get("summary"), max_len=600) or "스캐너 후보 비교 근거는 저장된 범위 안에서 제한적으로 확인됩니다."
    pass_count = sum(1 for row in checks if str(row.get("status") or "").strip().upper() == "PASS")
    fail_count = sum(1 for row in checks if str(row.get("status") or "").strip().upper() == "FAIL")
    na_count = sum(1 for row in checks if str(row.get("status") or "").strip().upper() == "NOT_AVAILABLE")
    present = int(float(feature_coverage.get("present") or 0)) if _num_opt(feature_coverage.get("present")) is not None else 0
    total = int(float(feature_coverage.get("total") or 0)) if _num_opt(feature_coverage.get("total")) is not None else 0
    quality_raw = _clip(feature_coverage.get("quality"), max_len=40).strip().lower()
    quality = {
        "strong": "양호",
        "good": "양호",
        "moderate": "보통",
        "weak": "취약",
    }.get(quality_raw, _clip(feature_coverage.get("quality"), max_len=40) or "not_captured")

    summary = f"스캐너 후보 비교에서는 {len(checks)}개 체크 중 통과 {pass_count}개, 미통과 {fail_count}개, 확인 불가 {na_count}개였습니다."
    if present and total:
        summary += f" 차트 피처 커버리지는 {present}/{total}로 {quality} 수준이었습니다."
    return summary


def _build_scanner_filters_bullets(filters_human: Dict[str, Any]) -> List[str]:
    checks = [row for row in list(filters_human.get("checks") or []) if isinstance(row, dict)]
    if not checks:
        return _listify(filters_human.get("bullets"), max_items=10, max_len=260)
    bullets: List[str] = []
    for row in checks[:8]:
        label = _scanner_check_name_label(row.get("name"))
        status = _scanner_check_status_label(row.get("status"))
        detail = _operatorize_report_text(row.get("detail"))
        if detail:
            bullets.append(f"{label}은 {status}였습니다. 근거: {detail}")
        else:
            bullets.append(f"{label}은 {status}였습니다.")
    return _dedupe_list(bullets, max_items=10, max_len=260)


def _build_entry_decision_summary(
    entry_summary: Dict[str, Any],
    scanner_reason: Dict[str, Any],
    market_context: Dict[str, Any],
    monitor_reason: Dict[str, Any],
    action: str,
) -> str:
    reason_human = _clip(entry_summary.get("reason_human"), max_len=600)
    reason_label = _entry_reason_label(reason_human)
    grouped_trace = (
        monitor_reason.get("entry_grouped_logic_trace")
        if isinstance(monitor_reason.get("entry_grouped_logic_trace"), dict)
        else {}
    )
    entry_scores = (
        monitor_reason.get("entry_condition_scores")
        if isinstance(monitor_reason.get("entry_condition_scores"), dict)
        else {}
    )
    symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24)
    rank = scanner_reason.get("selected_rank")
    triggered_path = _entry_path_label(
        grouped_trace.get("triggered_path")
        or monitor_reason.get("entry_condition_path")
    )
    playbook = _market_token_label(market_context.get("playbook")) or _clip(market_context.get("playbook"), max_len=32)
    confidence_score = _num_opt(entry_scores.get("confidence_score"))
    confidence_threshold = _num_opt(entry_scores.get("confidence_threshold"))
    fallback_ctx = _scanner_monitor_fallback_context(scanner_reason)

    summary_parts: List[str] = []
    if reason_label:
        summary_parts.append(f"진입은 {reason_label} 조건에서 실행됐습니다.")
    if fallback_ctx["used"] and fallback_ctx["scanner_top_pick_symbol"]:
        rank_text = f"{rank}위" if rank not in (None, "") else "후보"
        fallback_sentence = (
            f"스캐너 상위 후보 {fallback_ctx['scanner_top_pick_symbol']}은 모니터 단계에서 보류됐고 "
            f"{symbol} 차순위 재평가 {rank_text} 진입으로 전환됐습니다."
        )
        if fallback_ctx["reason"]:
            fallback_sentence = (
                f"스캐너 상위 후보 {fallback_ctx['scanner_top_pick_symbol']}은 {fallback_ctx['reason']} 이유로 보류됐고 "
                f"{symbol} 차순위 재평가 {rank_text} 진입으로 전환됐습니다."
            )
        if fallback_ctx["trigger_reason"]:
            fallback_sentence += f" 실제 트리거는 {fallback_ctx['trigger_reason']}였습니다."
        summary_parts.append(fallback_sentence)
    elif symbol and rank not in (None, ""):
        summary_parts.append(f"{symbol}이 스캐너 {rank}위 후보로 올라온 뒤 매수로 이어졌습니다.")
    elif symbol:
        summary_parts.append(f"{symbol}에 대한 매수 판단으로 진입이 이어졌습니다.")
    if playbook and triggered_path:
        if playbook == "눌림목" and triggered_path != "눌림목·거래량 경로":
            summary_parts.append(f"전략가 플레이북은 {playbook}이었지만 실제 엔트리는 {triggered_path}에서 확정됐습니다.")
        else:
            summary_parts.append(f"실제 엔트리 경로는 {triggered_path}였습니다.")
    elif triggered_path:
        summary_parts.append(f"실제 엔트리 경로는 {triggered_path}였습니다.")
    if confidence_score is not None and confidence_threshold is not None:
        if abs(confidence_score - confidence_threshold) <= 1e-6:
            summary_parts.append(
                f"진입 신뢰도 점수는 {confidence_score:.2f}로 기준 {confidence_threshold:.2f}와 동일했습니다."
            )
        else:
            relation = "상회했습니다" if confidence_score > confidence_threshold else "하회했습니다"
            summary_parts.append(
                f"진입 신뢰도 점수는 {confidence_score:.2f}로 기준 {confidence_threshold:.2f}를 {relation}."
            )
    if summary_parts:
        return " ".join(summary_parts)
    scanner_summary = _build_scanner_choice_summary(scanner_reason, market_context)
    if scanner_summary:
        entry_action = _operator_action_label(_clip(entry_summary.get("action"), max_len=24) or action or "BUY")
        return f"{scanner_summary} 이에 따라 진입 판단은 {entry_action}로 이어졌습니다."
    return "진입 판단 근거는 저장된 데이터 범위 안에서 충분히 확인되지 않았습니다."


def _entry_reason_label(value: Any) -> str:
    raw = _clip(value, max_len=220).strip()
    mapping = {
        "breakout_above_recent_high_with_vwap_structure_confirmation": "직전 고점 돌파와 VWAP 구조 확인",
        "breakout_confirmed": "돌파 확인",
        "pullback_rebound_confirmed": "눌림목 반등 확인",
        "reclaim_confirmed": "VWAP 재회복 확인",
        "breakout_vwap_hold": "돌파 후 VWAP 지지 확인",
    }
    if not raw:
        return ""
    if raw in mapping:
        return mapping[raw]
    return raw.replace("_", " ")


def _exit_reason_label(value: Any) -> str:
    raw = _clip(value, max_len=220).strip()
    stripped = re.sub(r"^SELL was triggered because\s*", "", raw, flags=re.IGNORECASE).strip().rstrip(".")
    lowered = stripped.lower()
    if not raw:
        return ""
    if "peak_drawdown" in lowered:
        return "고점 대비 하락폭 기준으로 청산"
    if "hard_stop" in lowered:
        return "고정 손절 기준으로 청산"
    if "take_profit" in lowered:
        return "목표 수익 실현으로 청산"
    if "trailing_stop" in lowered:
        return "추적 손절로 청산"
    if "vwap_breakdown" in lowered:
        return "VWAP 이탈로 청산"
    if "intraday low break" in lowered or "intraday_low_break" in lowered:
        return "장중 저점 이탈 기준으로 청산"
    if "below_vwap_reclaim_not_ready" in lowered or "below vwap reclaim not ready" in lowered:
        return "VWAP 재회복 미완료 기준으로 청산"
    operatorized = _operatorize_report_text(raw)
    if operatorized and operatorized != raw:
        return operatorized
    return stripped.replace("_", " ")


def _decision_chain_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "confirmed_exit_signal": "청산 확인 신호",
        "peak_drawdown": "고점 대비 하락폭",
        "breakout_above_recent_high_with_vwap_structure_confirmation": "직전 고점 돌파와 VWAP 구조 확인",
        "hard_stop": "고정 손절",
        "vwap_breakdown": "VWAP 이탈",
        "breakout_path": "돌파 경로",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _humanize_duration_text(value: Any, *, fallback_seconds: Any = None) -> str:
    text = _clip(value, max_len=80).strip()
    lowered = text.lower()
    total_seconds: Optional[int] = None

    if text:
        if _safe_fullmatch(r"\d{1,2}:\d{2}:\d{2}", text):
            hours, minutes, seconds = [int(part) for part in text.split(":")]
            total_seconds = hours * 3600 + minutes * 60 + seconds
        elif _safe_fullmatch(r"\d{1,2}:\d{2}", text):
            minutes, seconds = [int(part) for part in text.split(":")]
            total_seconds = minutes * 60 + seconds
        else:
            hour_match = _safe_fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*h", lowered)
            minute_match = _safe_fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*m", lowered)
            second_match = _safe_fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*s", lowered)
            if hour_match:
                total_seconds = int(round(float(hour_match.group(1)) * 3600))
            elif minute_match:
                total_seconds = int(round(float(minute_match.group(1)) * 60))
            elif second_match:
                total_seconds = int(round(float(second_match.group(1))))

    if total_seconds is None and fallback_seconds not in (None, ""):
        try:
            total_seconds = int(round(float(fallback_seconds)))
        except Exception:
            total_seconds = None

    if total_seconds is None:
        return text

    hours, remainder = divmod(max(total_seconds, 0), 3600)
    minutes, seconds = divmod(remainder, 60)
    parts: List[str] = []
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    if seconds or not parts:
        parts.append(f"{seconds}초")
    return " ".join(parts)


def _holding_duration_label(value: Any) -> str:
    text = _humanize_duration_text(value)
    if not text:
        return ""
    return f"보유 시간은 {text}였습니다."


def _execution_mode_label(value: Any) -> str:
    raw = _clip(value, max_len=120).strip().lower()
    mapping = {
        "simulation trade report": "시뮬레이션 거래 리포트",
        "simulation": "시뮬레이션",
        "simulation (mock broker)": "시뮬레이션 (모의 브로커)",
        "real": "실거래",
        "live": "실거래",
    }
    return mapping.get(raw, _clip(value, max_len=120))


def _entry_path_label(value: Any) -> str:
    raw = _clip(value, max_len=80).strip().lower()
    mapping = {
        "breakout_path": "돌파 경로",
        "pullback_volume_path": "눌림목·거래량 경로",
        "reclaim_path": "재회복 경로",
    }
    return mapping.get(raw, _clip(value, max_len=80))


def _entry_gate_state_label(value: Any) -> str:
    if value is True:
        return "통과"
    if value is False:
        return "미통과"
    return "기록 없음"


def _entry_gate_name_label(value: str) -> str:
    mapping = {
        "reclaim": "VWAP 재회복",
        "extension": "과확장 점검",
        "confidence gate": "신뢰도 게이트",
    }
    return mapping.get(value, value)


def _korean_predicate(value: str, *, noun_suffix: str = "입니다.") -> str:
    text = str(value or "").strip()
    if not text:
        return noun_suffix
    tail = "입니다." if noun_suffix == "입니다." else noun_suffix
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        has_batchim = (code - 0xAC00) % 28 != 0
        if tail == "입니다.":
            return "이었습니다." if has_batchim else "였습니다."
    return tail


def _korean_euro_ro(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "로"
    last = text[-1]
    code = ord(last)
    if 0xAC00 <= code <= 0xD7A3:
        jong = (code - 0xAC00) % 28
        if jong == 0 or jong == 8:
            return "로"
        return "으로"
    return "로"


def _build_entry_decision_bullets(
    entry_summary: Dict[str, Any],
    scanner_reason: Dict[str, Any],
    market_context: Dict[str, Any],
    monitor_reason: Dict[str, Any],
    action: str,
) -> List[str]:
    bullets: List[str] = [
        f"진입 run은 {_clip(entry_summary.get('run_id'), max_len=80) or '기록 없음'}입니다.",
        f"진입 시각은 {_clip(entry_summary.get('ts'), max_len=80) or '기록 없음'}입니다.",
        f"진입 액션은 {_operator_action_label(_clip(entry_summary.get('action'), max_len=40) or action)}였습니다.",
    ]
    reason_label = _entry_reason_label(entry_summary.get("reason_human"))
    if reason_label:
        bullets.append(f"진입 사유는 {reason_label}{_korean_predicate(reason_label)}")

    symbol = _clip(scanner_reason.get("selected_symbol"), max_len=24)
    rank = scanner_reason.get("selected_rank")
    selected_score = _num_opt(scanner_reason.get("selected_score"))
    if symbol and rank not in (None, "") and selected_score is not None:
        bullets.append(f"진입 시점 스캐너에서는 {symbol}이 {rank}위, 종합 점수 {selected_score:.3f}였습니다.")

    grouped_trace = (
        monitor_reason.get("entry_grouped_logic_trace")
        if isinstance(monitor_reason.get("entry_grouped_logic_trace"), dict)
        else {}
    )
    triggered_path = _entry_path_label(grouped_trace.get("triggered_path") or monitor_reason.get("entry_condition_path"))
    paths_passed = [
        _entry_path_label(item)
        for item in _listify(
            grouped_trace.get("paths_passed") or monitor_reason.get("entry_condition_paths_passed"),
            max_items=4,
            max_len=80,
        )
        if _entry_path_label(item)
    ]
    if triggered_path or paths_passed:
        parts: List[str] = []
        if triggered_path:
            parts.append(f"실제 진입 경로는 {triggered_path}였습니다")
        if paths_passed:
            parts.append(f"통과 경로는 {', '.join(paths_passed)}였습니다")
        bullets.append(". ".join(parts) + ".")

    gate_bits: List[str] = []
    if "reclaim_gate_ok" in grouped_trace:
        gate_bits.append(f"{_entry_gate_name_label('reclaim')} {_entry_gate_state_label(grouped_trace.get('reclaim_gate_ok'))}")
    if "extension_ok" in grouped_trace:
        gate_bits.append(f"{_entry_gate_name_label('extension')} {_entry_gate_state_label(grouped_trace.get('extension_ok'))}")
    if "confidence_gate_ok" in grouped_trace:
        gate_bits.append(f"{_entry_gate_name_label('confidence gate')} {_entry_gate_state_label(grouped_trace.get('confidence_gate_ok'))}")
    if gate_bits:
        bullets.append("진입 게이트 상태는 " + ", ".join(gate_bits) + "였습니다.")

    entry_scores = (
        monitor_reason.get("entry_condition_scores")
        if isinstance(monitor_reason.get("entry_condition_scores"), dict)
        else {}
    )
    confidence_score = _num_opt(entry_scores.get("confidence_score"))
    confidence_threshold = _num_opt(entry_scores.get("confidence_threshold"))
    if confidence_score is not None and confidence_threshold is not None:
        bullets.append(f"진입 신뢰도 점수는 {confidence_score:.2f}, 기준은 {confidence_threshold:.2f}였습니다.")

    entry_thresholds = (
        monitor_reason.get("entry_thresholds")
        if isinstance(monitor_reason.get("entry_thresholds"), dict)
        else {}
    )
    timeframe = entry_thresholds.get("timeframe_minutes")
    breakout_lookback = entry_thresholds.get("breakout_lookback")
    volume_ratio_min = _num_opt(entry_thresholds.get("volume_ratio_min"))
    require_vwap_reclaim = entry_thresholds.get("require_vwap_reclaim")
    require_rebound = entry_thresholds.get("require_rebound")
    threshold_bits: List[str] = []
    if timeframe not in (None, ""):
        threshold_bits.append(f"{int(float(timeframe))}분봉")
    if breakout_lookback not in (None, ""):
        threshold_bits.append(f"돌파 확인 기준 봉 수 {int(float(breakout_lookback))}")
    if volume_ratio_min is not None:
        threshold_bits.append(f"최소 거래량 비율 {volume_ratio_min:.2f}")
    if require_vwap_reclaim is not None:
        threshold_bits.append(f"VWAP 재회복 {'필수' if require_vwap_reclaim else '비필수'}")
    if require_rebound is not None:
        threshold_bits.append(f"반등 확인 {'필수' if require_rebound else '비필수'}")
    if threshold_bits:
        bullets.append("적용 정책은 " + ", ".join(threshold_bits) + "였습니다.")

    playbook = _market_token_label(market_context.get("playbook")) or _clip(market_context.get("playbook"), max_len=32)
    if playbook and triggered_path:
        bullets.append(f"전략가 플레이북은 {playbook}, 실제 진입 경로는 {triggered_path}였습니다.")

    return _dedupe_list(bullets, max_items=10, max_len=260)


def _build_holding_story_summary(hold_count: int, monitor_reason: Dict[str, Any], status_text: str) -> str:
    posture = _operator_action_label(_clip(monitor_reason.get("posture"), max_len=32) or "WAIT")
    trigger = _operator_axis_label(_clip(monitor_reason.get("trigger_type"), max_len=48) or "not_captured")
    axis = _operator_axis_label(_clip(monitor_reason.get("active_exit_axis"), max_len=64) or trigger)
    confirm_required = monitor_reason.get("confirm_required")
    confirm_count = monitor_reason.get("confirm_count")
    exit_triggered = bool(monitor_reason.get("exit_triggered"))
    if hold_count > 0:
        base = f"보유 구간에서는 모니터가 총 {hold_count}회 실행되었고, 마지막 포지션 판단은 {posture}였습니다. 핵심 감시 축은 {axis}{_korean_euro_ro(axis)} 유지됐습니다."
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
    decision_chain = " -> ".join(_decision_chain_label(item) for item in _listify(monitor_reason.get("decision_reason_chain"), max_items=5, max_len=60))
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
        bullets.append(f"Monitor runs: {hold_count}")
    if _clip(monitor_reason.get("posture"), max_len=48):
        bullets.append(f"현재 포지션 판단은 {_operator_action_label(monitor_reason.get('posture'))}입니다.")
    if _clip(monitor_reason.get("trigger_type"), max_len=64):
        trigger_label = _operator_axis_label(monitor_reason.get("trigger_type"))
        bullets.append(f"보유 중 가장 강하게 감시된 신호는 {trigger_label}{_korean_predicate(trigger_label)}")
    if monitor_reason.get("position_age_seconds") not in (None, ""):
        bullets.append(f"포지션 보유 시간은 약 {int(monitor_reason.get('position_age_seconds') or 0)}초입니다.")
    if effective_stop != "-":
        stop_reason = _clip(monitor_reason.get("effective_stop_reason"), max_len=64)
        suffix = f", 기준 축은 {_operator_axis_label(stop_reason)}입니다." if stop_reason else ""
        bullets.append(f"유효 손절 기준은 {effective_stop}입니다{suffix}")
    if take_profit != "-":
        bullets.append(f"목표 수익 실현 기준은 {take_profit} 수준입니다.")
    if _clip(monitor_reason.get("active_exit_axis"), max_len=80):
        axis_label = _operator_axis_label(monitor_reason.get("active_exit_axis"))
        bullets.append(f"당시 우선 감시 중이던 청산 축은 {axis_label}{_korean_predicate(axis_label)}")
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
    return _dedupe_list(bullets, max_items=14, max_len=260)


def _build_reporter_evaluation_section(
    shared_seed: Dict[str, Any],
    scanner_reason: Dict[str, Any],
    monitor_reason: Dict[str, Any],
    execution_outcome: Dict[str, Any],
    reporter_status: Dict[str, Any],
    reporter_feedback_packet: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    reporter_feedback = dict(reporter_feedback_packet or {})
    reporter_feedback_available = bool(reporter_feedback.get("available")) or bool(reporter_feedback.get("consumed"))
    reporter_status_value = _clip(reporter_status.get("status"), max_len=40).lower()
    if reporter_feedback_available and reporter_status_value in {"", "missing", "pending", "auto_ignored", "source_unavailable", "not_captured", "unknown"}:
        return _build_reporter_evaluation_from_feedback(reporter_feedback)

    status = _clip(reporter_status.get("status"), max_len=40) or "missing"
    grade = _clip(reporter_status.get("grade"), max_len=16) or "N/A"
    symbol = _clip(scanner_reason.get("selected_symbol") or shared_seed.get("symbol"), max_len=24) or "선정 종목"
    selected_rank = scanner_reason.get("selected_rank")
    selected_score = _num_opt(scanner_reason.get("selected_score"))
    confidence = _num_opt(scanner_reason.get("confidence"))
    ranked_rows = _scanner_ranked_candidates(scanner_reason)
    selected_row = _scanner_selected_row(scanner_reason)
    selected_risk = _num_opt(selected_row.get("risk_score"))
    hold_seconds = int(monitor_reason.get("position_age_seconds") or 0)
    hold_duration = _humanize_duration_text(shared_seed.get("holding_duration"), fallback_seconds=hold_seconds)
    trigger_type = _operator_axis_label(
        _clip(monitor_reason.get("trigger_type"), max_len=80)
        or _clip(shared_seed.get("exit_reason"), max_len=120)
    )
    exit_reason = _clip(shared_seed.get("exit_reason"), max_len=220)
    execution_summary = _clip(execution_outcome.get("summary"), max_len=300)
    same_day_status = _clip(reporter_status.get("same_day_linkage_status"), max_len=40)
    same_day_reason = _clip(reporter_status.get("same_day_linkage_reason"), max_len=220)
    reporter_summary = _clip(reporter_status.get("summary"), max_len=300)
    reporter_summary_lower = reporter_summary.lower()
    if "overtrading" in reporter_summary_lower or "rapid exit pressure" in reporter_summary_lower:
        reporter_summary = "동일 일자 리포터도 과매매 또는 빠른 청산 압력을 시사했습니다."
    same_day_status_label = {
        "linked_run": "동일 실행 기록 직접 연계",
        "linked_trade": "동일 거래 직접 연계",
        "linked_day": "당일 묶음 연계",
        "missing": "미연계",
    }.get(same_day_status, same_day_status)

    is_short_hold = hold_seconds > 0 and hold_seconds <= 120
    peak_drawdown_exit = "peak_drawdown" in str(monitor_reason.get("trigger_type") or "").lower() or "peak_drawdown" in exit_reason.lower()
    execution_recorded = "recorded" in execution_summary.lower() or "approved" in execution_summary.lower()

    summary_parts: List[str] = []
    if is_short_hold and peak_drawdown_exit:
        summary_parts.append("이번 거래는 종목 선정 자체보다 진입 타이밍 부담이 더 크게 드러났습니다.")
    elif peak_drawdown_exit:
        summary_parts.append("이번 거래는 보유 이후 되밀림 관리가 더 크게 작동한 케이스로 보입니다.")
    else:
        summary_parts.append("이번 거래는 저장된 근거상 scanner, entry, hold, exit 축을 함께 봐야 합니다.")
    if selected_rank == 1 and selected_score is not None:
        scanner_bits = [f"스캐너는 {symbol}을 {selected_rank}위"]
        if selected_score is not None:
            scanner_bits.append(f"종합 점수 {selected_score:.3f}")
        if confidence is not None:
            scanner_bits.append(f"신뢰도 {confidence:.2f}")
        if selected_risk is not None:
            scanner_bits.append(f"리스크 {selected_risk:.3f}")
        summary_parts.append(", ".join(scanner_bits) + "로 올렸고 선정 자체는 크게 흔들리지 않았습니다.")
    if hold_duration and peak_drawdown_exit:
        summary_parts.append(f"다만 진입 후 약 {hold_duration} 만에 {trigger_type} 축 청산이 발생해 추가 상승 지속성이 약했습니다.")
    elif hold_duration:
        summary_parts.append(f"보유 시간은 약 {hold_duration}로 짧아 hold 단계 해석은 제한적입니다.")
    if execution_recorded:
        summary_parts.append("실행 기록상 주문 자체 문제는 보이지 않았습니다.")
    elif execution_summary:
        summary_parts.append("실행 기록은 남아 있지만 주문 품질은 추가 확인이 필요합니다.")

    bullets: List[str] = []
    if selected_rank not in (None, "") and selected_score is not None:
        scanner_line = f"종목 선정 평가는 {symbol} {selected_rank}위, 종합 점수 {selected_score:.3f}"
        if confidence is not None:
            scanner_line += f", 신뢰도 {confidence:.2f}"
        if selected_risk is not None:
            scanner_line += f", 리스크 {selected_risk:.3f}"
        scanner_line += "로 종목 선택 자체는 비교적 정상으로 보입니다."
        bullets.append(scanner_line)
    if is_short_hold and peak_drawdown_exit:
        bullets.append(
            f"진입 평가는 진입 후 약 {hold_duration or f'{hold_seconds}초'} 만에 {trigger_type} 청산이 나와, 종목 선정보다 진입 위치 부담이 더 컸던 것으로 읽힙니다."
        )
    elif hold_duration:
        bullets.append(f"진입·보유 평가는 보유 시간이 {hold_duration}로 짧아 추가 사례 비교가 필요합니다.")
    if hold_duration:
        bullets.append(f"보유 평가는 보유 시간이 {hold_duration}에 그쳐 중간 악화 흐름을 두껍게 읽기에는 정보가 부족합니다.")
    if trigger_type:
        bullets.append(f"청산 평가는 청산 축이 {trigger_type}{_korean_euro_ro(trigger_type)} 명확해 청산 규칙 자체는 규칙대로 작동한 것으로 보입니다.")
    if execution_recorded:
        bullets.append("실행 평가는 주문 승인 및 기록이 남아 있어 실행 누락보다는 전략/타이밍 해석 이슈 쪽에 가깝습니다.")
    elif execution_summary:
        bullets.append(f"실행 평가는 {execution_summary}")
    if same_day_status:
        linkage_line = f"당일 리포터 연계 상태는 {same_day_status_label}였습니다."
        bullets.append(linkage_line)
    if reporter_summary:
        bullets.append(reporter_summary)

    return {
        "summary": " ".join(summary_parts).strip(),
        "status": status,
        "grade": grade,
        "bullets": _dedupe_list(bullets, max_items=8, max_len=260),
    }


def _build_reporter_evaluation_from_feedback(reporter_feedback_packet: Dict[str, Any] | None) -> Dict[str, Any]:
    packet = dict(reporter_feedback_packet or {})
    confidence = _clip(packet.get("confidence"), max_len=16).lower()
    confidence_label = {
        "high": "높음",
        "medium": "중간",
        "low": "낮음",
    }.get(confidence, "확인되지 않음")
    grade = {
        "high": "A",
        "medium": "B",
        "low": "C",
    }.get(confidence, "N/A")
    source_reports = _as_dict(packet.get("source_reports"))
    trade_summary = _as_dict(packet.get("trade_report_analysis"))
    insight_summary = normalize_reporter_text(_operatorize_report_text(_clip(packet.get("insight_summary"), max_len=600)))
    recommendations = [
        normalize_reporter_text(_operatorize_report_text(item))
        for item in _listify(packet.get("recommendation"), max_items=4, max_len=220)
        if str(item or "").strip()
    ]
    normalized_recommendations: List[str] = []
    for raw_item, rendered in zip(_listify(packet.get("recommendation"), max_items=4, max_len=220), recommendations):
        if raw_item == "Same-price round trips produced fee/tax drag; tighten follow-through evidence before repeating quick reversals.":
            normalized_recommendations.append("동일가 왕복 거래에서 수수료와 세금 손실이 반복돼, 짧은 반전 재진입 전에는 후속 추세 확인을 더 엄격하게 봐야 합니다.")
            continue
        if rendered:
            normalized_recommendations.append(rendered)
            continue
    recommendations = normalized_recommendations
    dominant_patterns = [
        _as_dict(item)
        for item in list(packet.get("dominant_patterns") or [])[:4]
        if isinstance(item, dict)
    ]
    source_labels: List[str] = []
    if source_reports.get("metrics"):
        source_labels.append("당일 metrics")
    if source_reports.get("reporter_analysis"):
        source_labels.append("당일 reporter 분석")
    if source_reports.get("trade_reports"):
        source_labels.append("당일 닫힌 거래 리포트")
    if not source_labels:
        source_labels.append("당일 피드백 패킷")

    closed_trade_count = int(trade_summary.get("closed_trade_count") or 0)
    win_count = int(trade_summary.get("win_count") or 0)
    loss_count = int(trade_summary.get("loss_count") or 0)
    avg_pnl_pct = _num_opt(trade_summary.get("avg_pnl_pct"))

    summary_parts: List[str] = [
        f"당일 reporter feedback은 {', '.join(source_labels)} 기준으로 생성됐습니다."
    ]
    if closed_trade_count > 0:
        trade_bits = [f"당일 closed trade {closed_trade_count}건"]
        trade_bits.append(f"승/패 {win_count}/{loss_count}")
        if avg_pnl_pct is not None:
            trade_bits.append(f"평균 손익률 {_fmt_pct(avg_pnl_pct)}")
        summary_parts.append(", ".join(trade_bits) + "였습니다.")
    if insight_summary:
        summary_parts.append(insight_summary)

    bullets: List[str] = []
    bullets.append(f"피드백 생성 소스는 {', '.join(source_labels)}입니다.")
    if closed_trade_count > 0:
        trade_line = f"당일 closed trade 집계는 {closed_trade_count}건, 승패 {win_count}/{loss_count}"
        if avg_pnl_pct is not None:
            trade_line += f", 평균 손익률 {_fmt_pct(avg_pnl_pct)}"
        trade_line += "입니다."
        bullets.append(trade_line)
    for row in dominant_patterns:
        detail = normalize_reporter_text(_operatorize_report_text(_clip(row.get("detail"), max_len=180)))
        name = normalize_reporter_text(_operatorize_report_text(_clip(row.get("name"), max_len=40)))
        if detail:
            bullets.append(f"주요 패턴: {detail}")
        elif name:
            bullets.append(f"주요 패턴: {name}")
    for item in recommendations:
        bullets.append(f"권고: {item}")

    return {
        "summary": " ".join(part for part in summary_parts if str(part or "").strip()).strip(),
        "status": "ok",
        "grade": grade,
        "bullets": _dedupe_list(bullets, max_items=8, max_len=260),
    }


def _build_execution_quality_section(
    story_input: Dict[str, Any],
    execution_outcome: Dict[str, Any],
    lifecycle_summary: Dict[str, Any],
) -> Dict[str, Any]:
    execution_details = story_input.get("execution_details") if isinstance(story_input.get("execution_details"), dict) else {}
    symbol = _clip(story_input.get("symbol"), max_len=24) or "종목"
    action = _operator_action_label(_clip(story_input.get("action"), max_len=24) or "WAIT")
    filled_qty = execution_details.get("filled_qty")
    avg_price = _fmt_price(execution_details.get("avg_price"))
    order_status = _clip(execution_details.get("order_status"), max_len=80)
    order_id = _clip(execution_details.get("order_id"), max_len=120)
    execution_mode = _clip(execution_details.get("execution_mode"), max_len=80)
    execution_mode_label = _clip(story_input.get("execution_mode_label"), max_len=80)
    broker_env = _clip(execution_details.get("broker_env"), max_len=80)
    outcome = _clip(execution_outcome.get("outcome"), max_len=80)
    quantity = execution_outcome.get("quantity")
    order_status_label = {
        "allowed": "허용",
        "approved": "승인",
        "recorded": "기록 완료",
        "rejected": "거부",
    }.get(order_status.lower(), order_status) if order_status else ""
    mode_label = {
        "real": "실거래",
        "live": "실거래",
        "simulation": "시뮬레이션",
    }.get(execution_mode.lower(), execution_mode) if execution_mode else ""
    if execution_mode_label:
        mode_label = _execution_mode_label(execution_mode_label)

    summary_parts: List[str] = []
    if outcome == "recorded":
        qty_text = str(int(quantity)) if quantity not in (None, "") else (str(int(filled_qty)) if filled_qty not in (None, "") else "기록된 수량")
        summary_parts.append(f"{symbol} {qty_text}주 {action} 주문은 승인 및 기록까지 확인됐습니다.")
    elif _clip(execution_outcome.get("summary"), max_len=300):
        summary_parts.append(_operatorize_report_text(execution_outcome.get("summary")))
    elif _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=300):
        summary_parts.append(_operatorize_report_text(lifecycle_summary.get("lifecycle_summary_human")))
    else:
        summary_parts.append("실행 품질 세부 정보는 제한적으로만 확인됩니다.")
    if avg_price != "-":
        summary_parts.append(f"체결 기준 가격은 {avg_price}였습니다.")
    summary = " ".join(summary_parts)

    bullets: List[str] = []
    if outcome:
        outcome_label = {"recorded": "기록 완료", "approved": "승인", "rejected": "거부"}.get(outcome, outcome)
        bullets.append(f"주문 실행 결과는 {outcome_label}였습니다.")
    if quantity not in (None, ""):
        bullets.append(f"주문 수량은 {int(quantity)}주였습니다.")
    elif filled_qty not in (None, ""):
        bullets.append(f"체결 수량은 {int(filled_qty)}주였습니다.")
    if mode_label:
        bullets.append(f"실행 모드는 {mode_label}였습니다.")
    if broker_env:
        bullets.append(f"브로커 환경은 {broker_env}였습니다.")
    else:
        bullets.append("브로커 환경 정보는 별도로 기록되지 않았습니다.")
    if order_status_label:
        bullets.append(f"주문 상태는 {order_status_label}{_korean_euro_ro(order_status_label)} 확인됐습니다.")
    else:
        bullets.append("주문 상태는 별도로 기록되지 않았습니다.")
    if order_id:
        bullets.append(f"주문 번호는 {order_id}였습니다.")
    else:
        bullets.append("주문 번호는 별도로 기록되지 않았습니다.")
    if avg_price != "-":
        bullets.append(f"평균 체결가는 {avg_price}였습니다.")
    for bullet in build_execution_truth_bullets(execution_details=execution_details):
        if bullet not in bullets:
            bullets.append(bullet)

    return {
        "summary": summary,
        "bullets": _dedupe_list(bullets, max_items=12, max_len=260),
    }


def _build_exit_decision_summary(
    exit_summary: Dict[str, Any],
    monitor_context: Dict[str, Any],
    *,
    status_text: str,
) -> str:
    reason = _clip(exit_summary.get("reason_human"), max_len=600)
    reason_label = _exit_reason_label(reason)
    if status_text.lower() == "open":
        return reason_label or "현재 포지션은 아직 열려 있어 확정된 청산 체결은 기록되지 않았습니다."
    if reason or reason_label:
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
            return f"{reason_label or reason}. 청산 당시 상황은 " + ", ".join(details) + "입니다."
        return reason_label or reason
    return "청산 판단 근거는 저장된 데이터 범위 안에서 충분히 확인되지 않았습니다."


def _build_exit_decision_bullets(
    exit_summary: Dict[str, Any],
    monitor_context: Dict[str, Any],
    *,
    status_text: str,
) -> List[str]:
    guard_context = exit_summary.get("guard_context") if isinstance(exit_summary.get("guard_context"), dict) else {}
    execution_context = exit_summary.get("execution_context") if isinstance(exit_summary.get("execution_context"), dict) else {}
    reason_label = _exit_reason_label(exit_summary.get("reason_human"))
    decision_chain = " -> ".join(_decision_chain_label(item) for item in _listify(monitor_context.get("decision_reason_chain"), max_items=5, max_len=60))
    bullets: List[str] = [
        f"청산 판단이 기록된 run은 {_clip(exit_summary.get('run_id'), max_len=80) or 'not_captured'}입니다.",
        f"청산 시각은 {_clip(exit_summary.get('ts'), max_len=80) or 'not_captured'}입니다.",
        f"청산 액션은 {_operator_action_label(_clip(exit_summary.get('action'), max_len=40) or ('HOLD' if status_text == 'open' else 'not_captured'))}입니다.",
        f"청산 사유는 {reason_label or ('포지션이 아직 열려 있음' if status_text == 'open' else '기록 없음')}입니다.",
    ]
    if _clip(monitor_context.get("trigger_type"), max_len=80):
        trigger_label = _operator_axis_label(monitor_context.get("trigger_type"))
        bullets.append(f"청산을 직접 촉발한 신호는 {trigger_label}{_korean_predicate(trigger_label)}")
        bullets.append(f"Trigger type: {trigger_label}")
    if _clip(monitor_context.get("active_exit_axis"), max_len=120):
        axis_label = _operator_axis_label(monitor_context.get("active_exit_axis"))
        bullets.append(f"청산 시점 우선 감시 축은 {axis_label}{_korean_predicate(axis_label)}")
    if monitor_context.get("confirm_required") is not None:
        bullets.append(f"청산 확인 조건은 {int(monitor_context.get('confirm_count') or 0)}/{int(monitor_context.get('confirm_required') or 0)} 단계로 기록되었습니다.")
    effective_stop = _fmt_pct(monitor_context.get("effective_stop_loss_pct"))
    if effective_stop != "-":
        stop_reason = _clip(monitor_context.get("effective_stop_reason"), max_len=64)
        suffix = f", 기준 축은 {_operator_axis_label(stop_reason)}입니다." if stop_reason else ""
        bullets.append(f"청산 시점의 유효 손절 기준은 {effective_stop}입니다{suffix}")
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
    if not decision_chain:
        decision_chain = reason_label
    if decision_chain:
        bullets.append(f"판단 흐름은 {decision_chain} 기준으로 이어졌습니다.")
    if _clip(guard_context.get("summary"), max_len=220):
        bullets.append(f"가드 판단 결과는 {_clip(guard_context.get('summary'), max_len=220)}입니다.")
    if _clip(execution_context.get("summary"), max_len=220):
        bullets.append(f"주문 실행 결과는 {_clip(execution_context.get('summary'), max_len=220)}입니다.")
    if _clip(monitor_context.get("price_source"), max_len=80):
        bullets.append(f"가격 기준 소스는 {_clip(monitor_context.get('price_source'), max_len=80)}입니다.")
    if _clip(monitor_context.get("feature_source"), max_len=80):
        bullets.append(f"지표 기준 소스는 {_clip(monitor_context.get('feature_source'), max_len=80)}입니다.")
    return _dedupe_list(bullets, max_items=16, max_len=260)


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


def _extract_policy_ref_context(story_input: Dict[str, Any], monitor_reason: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(monitor_reason.get("policy_ref"), dict):
        candidates.append(monitor_reason.get("policy_ref"))
    for key in ("entry_summary", "exit_summary"):
        block = story_input.get(key) if isinstance(story_input.get(key), dict) else {}
        monitor_ctx = block.get("monitor_context") if isinstance(block.get("monitor_context"), dict) else {}
        policy_ref = monitor_ctx.get("policy_ref") if isinstance(monitor_ctx.get("policy_ref"), dict) else {}
        if policy_ref:
            candidates.append(policy_ref)
    holding = story_input.get("holding_summary") if isinstance(story_input.get("holding_summary"), dict) else {}
    for row in list(holding.get("holding_events") or [])[:8]:
        if not isinstance(row, dict):
            continue
        monitor_ctx = row.get("monitor_context") if isinstance(row.get("monitor_context"), dict) else {}
        policy_ref = monitor_ctx.get("policy_ref") if isinstance(monitor_ctx.get("policy_ref"), dict) else {}
        if policy_ref:
            candidates.append(policy_ref)
    for policy_ref in candidates:
        symbol_constraints = policy_ref.get("symbol_constraints") if isinstance(policy_ref.get("symbol_constraints"), dict) else {}
        risk_mode = _clip(policy_ref.get("risk_mode"), max_len=40)
        selected_playbook = _clip(policy_ref.get("selected_playbook"), max_len=40)
        preferred_themes = _listify(symbol_constraints.get("preferred_themes"), max_items=6, max_len=80)
        avoid_themes = _listify(symbol_constraints.get("avoid_themes"), max_items=6, max_len=80)
        if risk_mode or selected_playbook or preferred_themes or avoid_themes:
            return {
                "risk_mode": risk_mode,
                "selected_playbook": selected_playbook,
                "preferred_themes": preferred_themes,
                "avoid_themes": avoid_themes,
            }
    return {}


def _extract_scanner_bias_summary(story_input: Dict[str, Any], scanner_reason: Dict[str, Any]) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    if isinstance(scanner_reason.get("scanner_bias_summary"), dict) and scanner_reason.get("scanner_bias_summary"):
        candidates.append(scanner_reason.get("scanner_bias_summary"))
    scanner_trace_summary = story_input.get("scanner_trace_summary") if isinstance(story_input.get("scanner_trace_summary"), dict) else {}
    if isinstance(scanner_trace_summary.get("scanner_bias_summary"), dict) and scanner_trace_summary.get("scanner_bias_summary"):
        candidates.append(scanner_trace_summary.get("scanner_bias_summary"))
    canonical_artifacts = story_input.get("canonical_agent_artifacts") if isinstance(story_input.get("canonical_agent_artifacts"), dict) else {}
    canonical_scanner = canonical_artifacts.get("scanner") if isinstance(canonical_artifacts.get("scanner"), dict) else {}
    if isinstance(canonical_scanner.get("scanner_bias_summary"), dict) and canonical_scanner.get("scanner_bias_summary"):
        candidates.append(canonical_scanner.get("scanner_bias_summary"))
    scanner_evidence = story_input.get("scanner_evidence") if isinstance(story_input.get("scanner_evidence"), dict) else {}
    for row in list(scanner_evidence.get("candidate_selection_reasons") or [])[:3]:
        if not isinstance(row, dict):
            continue
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if isinstance(payload.get("scanner_bias_summary"), dict) and payload.get("scanner_bias_summary"):
            candidates.append(payload.get("scanner_bias_summary"))
    for item in candidates:
        if item:
            return {
                "enabled": item.get("enabled"),
                "active_biases": _listify(item.get("active_biases"), max_items=6, max_len=80),
                "bias_strength": _clip(item.get("bias_strength"), max_len=24),
                "bias_source": _clip(item.get("bias_source"), max_len=80),
                "summary": _clip(item.get("summary"), max_len=220),
            }
    return {}


def _evidence_digest(evidence: Any, keys: List[str]) -> Dict[str, int]:
    data = evidence if isinstance(evidence, dict) else {}
    return {key: len(list(data.get(key) or [])) for key in keys}


def _extract_strategist_report_context(story_input: Dict[str, Any]) -> Dict[str, Any]:
    canonical = story_input.get("canonical_agent_artifacts") if isinstance(story_input.get("canonical_agent_artifacts"), dict) else {}
    carriers = [
        story_input.get("strategist_output"),
        story_input.get("strategist"),
        canonical.get("strategist"),
        story_input,
    ]
    fields = (
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
    )
    out: Dict[str, Any] = {}
    for carrier in carriers:
        source = carrier if isinstance(carrier, dict) else {}
        if not source:
            continue
        for field in fields:
            if field in out:
                continue
            value = source.get(field)
            if isinstance(value, dict) and value:
                out[field] = dict(value)
    return out


def _build_report_strategist_refresh_trace(story_input: Dict[str, Any]) -> Dict[str, Any]:
    canonical = story_input.get("canonical_agent_artifacts") if isinstance(story_input.get("canonical_agent_artifacts"), dict) else {}
    strategist_artifact = canonical.get("strategist") if isinstance(canonical.get("strategist"), dict) else {}
    commander_artifact = canonical.get("commander") if isinstance(canonical.get("commander"), dict) else {}
    strategist_output = (
        story_input.get("strategist_output")
        if isinstance(story_input.get("strategist_output"), dict)
        else strategist_artifact
    )
    if not isinstance(strategist_output, dict):
        strategist_output = {}
    commander_decision = (
        commander_artifact.get("commander_decision")
        if isinstance(commander_artifact.get("commander_decision"), dict)
        else story_input.get("commander_decision")
        if isinstance(story_input.get("commander_decision"), dict)
        else {}
    )
    if isinstance(strategist_artifact.get("strategy_refresh_trace"), dict) and strategist_artifact.get("strategy_refresh_trace"):
        return _compact_strategy_refresh_trace(strategist_artifact.get("strategy_refresh_trace"))
    if isinstance(strategist_output.get("strategy_refresh_trace"), dict) and strategist_output.get("strategy_refresh_trace"):
        return _compact_strategy_refresh_trace(strategist_output.get("strategy_refresh_trace"))
    trace = build_strategy_refresh_trace(
        strategist_output=dict(strategist_output),
        state={
            "commander_decision": dict(commander_decision or {}),
            "route_observability": dict(commander_artifact.get("route_observability") or {}),
        },
    )
    return _compact_strategy_refresh_trace(trace)


def _compact_strategy_refresh_trace(value: Any) -> Dict[str, Any]:
    trace = value if isinstance(value, dict) else {}
    stages: List[Dict[str, Any]] = []
    for row in list(trace.get("stages") or [])[:4]:
        if not isinstance(row, dict):
            continue
        stages.append(
            {
                "stage": _clip(row.get("stage"), max_len=80),
                "label": _clip(row.get("label"), max_len=80),
                "summary": _clip(row.get("summary"), max_len=320),
                "requested": row.get("requested"),
                "evaluated": row.get("evaluated"),
                "effective": row.get("effective"),
                "reason": _clip(row.get("reason"), max_len=160),
                "selected_symbol": _clip(row.get("selected_symbol"), max_len=24),
                "policy_delta_count": row.get("policy_delta_count"),
                "policy_delta_fields": _listify(row.get("policy_delta_fields"), max_items=8, max_len=80),
            }
        )
    out = {
        "summary": _clip(trace.get("summary"), max_len=700),
        "bullets": _listify(trace.get("bullets"), max_items=8, max_len=220),
        "stages": stages,
        "refresh_requested": trace.get("refresh_requested"),
        "refresh_effective": trace.get("refresh_effective"),
        "policy_delta_count": trace.get("policy_delta_count"),
        "policy_delta_fields": _listify(trace.get("policy_delta_fields"), max_items=8, max_len=80),
        "source": _clip(trace.get("source"), max_len=120),
        "llm_interpretation": _compact_scalar_dict(trace.get("llm_interpretation"), max_items=4, max_len=240),
    }
    return {key: val for key, val in out.items() if val not in ("", None, [], {})}


def _compact_memory_layer_decisions(value: Any) -> Dict[str, Any]:
    decisions = value if isinstance(value, dict) else {}
    out: Dict[str, Any] = {}
    for layer, row in list(decisions.items())[:6]:
        if not isinstance(row, dict):
            continue
        out[str(layer)] = {
            "status": _clip(row.get("status"), max_len=32),
            "active": row.get("active"),
            "visible": row.get("visible"),
            "used": row.get("used"),
            "gate_reason": _clip(row.get("gate_reason"), max_len=80),
            "effect": _clip(row.get("effect"), max_len=140),
            "reason": _clip(row.get("reason"), max_len=220),
            "confidence": row.get("confidence"),
            "application_targets": _listify(row.get("application_targets"), max_items=5, max_len=60),
        }
    return out


def _compact_memory_application_trace(value: Any) -> Dict[str, Any]:
    trace = value if isinstance(value, dict) else {}
    return {
        "captured": trace.get("captured"),
        "enabled": trace.get("enabled"),
        "applied": trace.get("applied"),
        "entry_applied": trace.get("entry_applied"),
        "hold_applied": trace.get("hold_applied"),
        "exit_applied": trace.get("exit_applied"),
        "not_applied_reason": _clip(trace.get("not_applied_reason"), max_len=120),
        "bias_source": _clip(trace.get("bias_source"), max_len=80),
        "active_layers": _listify(trace.get("active_layers"), max_items=5, max_len=32),
        "source_delta_keys": _listify(trace.get("source_delta_keys"), max_items=8, max_len=48),
        "entry_delta_keys": _listify(trace.get("entry_delta_keys"), max_items=8, max_len=48),
        "hold_delta_keys": _listify(trace.get("hold_delta_keys"), max_items=8, max_len=48),
        "exit_delta_keys": _listify(trace.get("exit_delta_keys"), max_items=8, max_len=48),
        "selected_symbol": _clip(trace.get("selected_symbol"), max_len=24),
        "selected_bias_adjustment": trace.get("selected_bias_adjustment"),
        "effective_policy_source": _clip(trace.get("effective_policy_source"), max_len=80),
        "reason": _listify(trace.get("reason"), max_items=5, max_len=80),
    }


def _compact_strategist_report_context(story_input: Dict[str, Any]) -> Dict[str, Any]:
    context = _extract_strategist_report_context(story_input)
    if not context:
        return {}
    thesis = _as_dict(context.get("strategy_thesis"))
    memory = _as_dict(context.get("memory_usage_trace"))
    news = _as_dict(context.get("news_usage_trace"))
    scanner_handoff = _as_dict(context.get("scanner_handoff"))
    monitor_handoff = _as_dict(context.get("monitor_handoff"))
    boundary = _as_dict(context.get("responsibility_boundary"))
    permission = _as_dict(context.get("trade_permission_frame"))
    conflict = _as_dict(context.get("conflict_analysis"))
    delta = _as_dict(context.get("strategy_delta_trace"))
    refresh_trace = _compact_strategy_refresh_trace(context.get("strategy_refresh_trace"))
    return {
        "strategy_thesis": {
            "market_view": _clip(thesis.get("market_view"), max_len=220),
            "trade_style": _clip(thesis.get("trade_style"), max_len=180),
            "risk_tone": _clip(thesis.get("risk_tone"), max_len=60),
            "selected_playbook": _clip(thesis.get("selected_playbook"), max_len=60),
            "one_line": _clip(thesis.get("one_line"), max_len=240),
        },
        "strategy_delta_trace": {
            "changed": delta.get("changed"),
            "previous_playbook": _clip(delta.get("previous_playbook"), max_len=60),
            "current_playbook": _clip(delta.get("current_playbook"), max_len=60),
            "change_reason": _clip(delta.get("change_reason"), max_len=220),
        },
        "strategy_refresh_trace": refresh_trace,
        "memory_usage_trace": {
            "schema_version": _clip(memory.get("schema_version"), max_len=80),
            "active_layers": _listify(memory.get("active_layers"), max_items=5, max_len=32),
            "priority_order": _listify(memory.get("priority_order"), max_items=6, max_len=32),
            "layer_decisions": _compact_memory_layer_decisions(memory.get("layer_decisions")),
            "applied_to_strategy": _compact_scalar_dict(memory.get("applied_to_strategy"), max_items=8, max_len=160),
            "scanner_application": _compact_memory_application_trace(memory.get("scanner_application")),
            "monitor_application": _compact_memory_application_trace(memory.get("monitor_application")),
            "human_summary": _clip(memory.get("human_summary"), max_len=320),
        },
        "news_usage_trace": {
            "schema_version": _clip(news.get("schema_version"), max_len=80),
            "query_targets": _listify(news.get("query_targets"), max_items=8, max_len=80),
            "market_headlines_used": _listify(news.get("market_headlines_used"), max_items=3, max_len=160),
            "candidate_headlines_used": _listify(news.get("candidate_headlines_used"), max_items=3, max_len=160),
            "market_effect": _clip(news.get("market_effect"), max_len=220),
            "playbook_effect": _clip(news.get("playbook_effect"), max_len=180),
            "scanner_guidance_effect": _clip(news.get("scanner_guidance_effect"), max_len=180),
            "monitor_policy_effect": _clip(news.get("monitor_policy_effect"), max_len=180),
            "ignored_or_low_signal_news": _listify(news.get("ignored_or_low_signal_news"), max_items=4, max_len=140),
            "confidence": _clip(news.get("confidence"), max_len=40),
            "source_event": _clip(news.get("source_event"), max_len=120),
            "human_summary": _clip(news.get("human_summary"), max_len=320),
        },
        "scanner_handoff": {
            "prefer_candidate_traits": _listify(scanner_handoff.get("prefer_candidate_traits"), max_items=6, max_len=80),
            "penalize_traits": _listify(scanner_handoff.get("penalize_traits"), max_items=6, max_len=80),
            "disqualifiers": _listify(scanner_handoff.get("disqualifiers"), max_items=5, max_len=80),
            "ranking_guidance": _clip(scanner_handoff.get("ranking_guidance"), max_len=260),
            "not_responsible_for": _listify(scanner_handoff.get("not_responsible_for"), max_items=5, max_len=80),
        },
        "monitor_handoff": {
            "entry_confirmation": _listify(monitor_handoff.get("entry_confirmation"), max_items=6, max_len=100),
            "hold_off_conditions": _listify(monitor_handoff.get("hold_off_conditions"), max_items=6, max_len=100),
            "entry_aggressiveness": _clip(monitor_handoff.get("entry_aggressiveness"), max_len=60),
            "policy_effect_summary": _clip(monitor_handoff.get("policy_effect_summary"), max_len=220),
        },
        "conflict_analysis": {
            "bullish_evidence": _listify(conflict.get("bullish_evidence"), max_items=5, max_len=120),
            "bearish_evidence": _listify(conflict.get("bearish_evidence"), max_items=5, max_len=120),
            "resolution": _clip(conflict.get("resolution"), max_len=240),
            "confidence": _clip(conflict.get("confidence"), max_len=40),
        },
        "trade_permission_frame": {
            "candidate_search_allowed": permission.get("candidate_search_allowed"),
            "entry_allowed_if": _listify(permission.get("entry_allowed_if"), max_items=6, max_len=100),
            "entry_blocked_if": _listify(permission.get("entry_blocked_if"), max_items=6, max_len=100),
            "permission_level": _clip(permission.get("permission_level"), max_len=60),
            "reason": _clip(permission.get("reason"), max_len=240),
        },
        "responsibility_boundary": {
            "strategist_owns": _listify(boundary.get("strategist_owns"), max_items=6, max_len=80),
            "scanner_owns": _listify(boundary.get("scanner_owns"), max_items=6, max_len=80),
            "monitor_owns": _listify(boundary.get("monitor_owns"), max_items=6, max_len=80),
            "executor_supervisor_owns": _listify(boundary.get("executor_supervisor_owns"), max_items=6, max_len=80),
            "not_responsible_for": _listify(boundary.get("not_responsible_for"), max_items=6, max_len=80),
        },
        "direct_consumption_rule": (
            "Use these strategist fields as the strategist rationale. Do not infer final symbol selection from strategist output."
        ),
    }


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
    strategist_context = shared_seed.get("strategist_context") if isinstance(shared_seed.get("strategist_context"), dict) else {}
    scanner_reasoning = shared_seed.get("scanner_reasoning") if isinstance(shared_seed.get("scanner_reasoning"), dict) else {}
    monitor_reasoning = shared_seed.get("monitor_reasoning") if isinstance(shared_seed.get("monitor_reasoning"), dict) else {}
    policy_ref_context = _extract_policy_ref_context(story_input, monitor_reason)
    scanner_bias_summary = _extract_scanner_bias_summary(story_input, scanner_reason)
    report_section_seeds = shared_seed.get("report_section_seeds") if isinstance(shared_seed.get("report_section_seeds"), dict) else {}
    market_context_seed = _as_dict(report_section_seeds.get("market_context_at_entry"))
    strategist_summary_seed = _as_dict(report_section_seeds.get("strategist_summary"))
    why_symbol_seed = _as_dict(report_section_seeds.get("why_this_symbol_was_chosen"))
    holding_story_seed = _as_dict(report_section_seeds.get("holding_monitoring_story"))
    scanner_filters_seed = _as_dict(report_section_seeds.get("scanner_filters"))
    execution_quality_seed = _as_dict(report_section_seeds.get("execution_quality"))
    if _clip(execution_outcome.get("summary"), max_len=280) and execution_outcome_summary_is_placeholder(execution_quality_seed.get("summary")):
        execution_quality_seed = dict(execution_quality_seed)
        execution_quality_seed["summary"] = _clip(execution_outcome.get("summary"), max_len=280)
        if execution_outcome.get("bullets"):
            execution_quality_seed["bullets"] = _listify(execution_outcome.get("bullets"), max_items=6, max_len=220)
        if execution_outcome.get("status"):
            execution_quality_seed["status"] = _clip(execution_outcome.get("status"), max_len=48)
    market_context_summary = _clip(market_context.get("summary"), max_len=320) or _clip(market_context_seed.get("summary"), max_len=320)
    market_context_bullets = _listify(market_context.get("bullets"), max_items=6, max_len=220) or _listify(market_context_seed.get("bullets"), max_items=6, max_len=220)
    if not market_context_summary:
        market_context_summary = _clip(strategist_summary_seed.get("summary"), max_len=320)
    scanner_summary = _clip(scanner_reason.get("summary"), max_len=320) or _clip(why_symbol_seed.get("summary"), max_len=320)
    scanner_bullets = _listify(scanner_reason.get("bullets"), max_items=6, max_len=220) or _listify(why_symbol_seed.get("bullets"), max_items=6, max_len=220)
    filters_summary = _clip(filters_human.get("summary"), max_len=280) or _clip(scanner_filters_seed.get("summary"), max_len=280)
    filters_bullets = _listify(filters_human.get("bullets"), max_items=6, max_len=220) or _listify(scanner_filters_seed.get("bullets"), max_items=6, max_len=220)
    monitor_summary = _clip(monitor_reason.get("summary"), max_len=280) or _clip(holding_story_seed.get("summary"), max_len=280)
    monitor_bullets = _listify(monitor_reason.get("bullets"), max_items=6, max_len=220) or _listify(holding_story_seed.get("bullets"), max_items=6, max_len=220)
    guard_summary = _clip(guard_reason.get("summary"), max_len=280) or _clip((_as_dict(report_section_seeds.get("guard_approval_result"))).get("summary"), max_len=280)
    guard_bullets = _listify(guard_reason.get("bullets"), max_items=6, max_len=220) or _listify((_as_dict(report_section_seeds.get("guard_approval_result"))).get("bullets"), max_items=6, max_len=220)
    execution_summary = _clip(execution_outcome.get("summary"), max_len=280) or _clip(execution_quality_seed.get("summary"), max_len=280)
    execution_bullets = _listify(execution_outcome.get("bullets"), max_items=6, max_len=220) or _listify(execution_quality_seed.get("bullets"), max_items=6, max_len=220)
    reporter_seed = _as_dict(report_section_seeds.get("reporter_evaluation"))
    if _reporter_summary_is_placeholder(reporter_status.get("summary")) and _clip(reporter_seed.get("summary"), max_len=280):
        reporter_status = dict(reporter_status)
        reporter_status["summary"] = _clip(reporter_seed.get("summary"), max_len=280)
        if reporter_seed.get("bullets"):
            reporter_status["bullets"] = _listify(reporter_seed.get("bullets"), max_items=5, max_len=180)
        if reporter_seed.get("status"):
            reporter_status["status"] = _clip(reporter_seed.get("status"), max_len=32)
        if reporter_seed.get("grade"):
            reporter_status["grade"] = _clip(reporter_seed.get("grade"), max_len=24)
    reporter_summary = _clip(reporter_status.get("summary"), max_len=280) or _clip(reporter_seed.get("summary"), max_len=280)
    reporter_bullets = _listify(reporter_status.get("bullets"), max_items=5, max_len=180) or _listify(reporter_seed.get("bullets"), max_items=5, max_len=180)
    conclusion_current_action = _clip(operator_conclusion.get("current_action"), max_len=24) or _clip((_as_dict(report_section_seeds.get("final_operator_conclusion"))).get("current_action"), max_len=24)
    conclusion_watch_next = _listify(operator_conclusion.get("watch_next"), max_items=5, max_len=180) or _listify((_as_dict(report_section_seeds.get("final_operator_conclusion"))).get("watch_next"), max_items=5, max_len=180)
    conclusion_thesis_invalidation = _listify(operator_conclusion.get("thesis_invalidation"), max_items=5, max_len=180) or _listify((_as_dict(report_section_seeds.get("final_operator_conclusion"))).get("thesis_invalidation"), max_items=5, max_len=180)
    conclusion_summary = _clip(operator_conclusion.get("summary"), max_len=280) or _clip((_as_dict(report_section_seeds.get("final_operator_conclusion"))).get("summary"), max_len=280)
    return {
        "trade_id": story_input.get("trade_id") or story_input.get("story_id"),
        "story_id": story_input.get("story_id"),
        "run_id": story_input.get("run_id"),
        "symbol": story_input.get("symbol"),
        "action": story_input.get("action"),
        "status": story_input.get("status"),
        "story_type": story_input.get("story_type"),
        "execution_mode_label": story_input.get("execution_mode_label"),
        "strategist_output": _compact_strategist_report_context(story_input),
        "strategist_refresh_trace": _build_report_strategist_refresh_trace(story_input),
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
            "theme_strength_packet": _compact_scalar_dict(
                market_context.get("theme_strength_packet") or strategist_context.get("theme_strength_packet"),
                max_items=8,
                max_len=120,
            ),
            "theme_source": _clip(market_context.get("theme_source") or strategist_context.get("theme_source"), max_len=80),
            "theme_source_status": _clip(
                market_context.get("theme_source_status") or strategist_context.get("theme_source_status"),
                max_len=80,
            ),
            "theme_source_reason": _clip(
                market_context.get("theme_source_reason") or strategist_context.get("theme_source_reason"),
                max_len=160,
            ),
            "theme_strength_top_themes": _listify(
                market_context.get("theme_strength_top_themes") or strategist_context.get("theme_strength_top_themes"),
                max_items=6,
                max_len=80,
            ),
            "risk_mode": _clip(policy_ref_context.get("risk_mode"), max_len=32),
            "selected_playbook": _clip(policy_ref_context.get("selected_playbook"), max_len=32),
            "preferred_themes": _listify(policy_ref_context.get("preferred_themes"), max_items=4, max_len=80),
            "avoid_themes": _listify(policy_ref_context.get("avoid_themes"), max_items=4, max_len=80),
            "scanner_bias_summary": scanner_bias_summary,
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
            "summary": market_context_summary,
            "bullets": market_context_bullets,
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
            "summary": scanner_summary,
            "comparison": _clip(scanner_reason.get("comparison"), max_len=240),
            "bullets": scanner_bullets,
        },
        "filters_human": {
            "summary": filters_summary,
            "bullets": filters_bullets,
        },
        "monitor_reason_human": {
            **_compact_monitor_snapshot(monitor_reason),
            "summary": monitor_summary,
            "bullets": monitor_bullets,
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
            "summary": guard_summary,
            "status": _clip(guard_reason.get("status"), max_len=32),
            "bullets": guard_bullets,
        },
        "execution_outcome_human": {
            "summary": execution_summary,
            "status": _clip(execution_outcome.get("status"), max_len=32),
            "bullets": execution_bullets,
        },
        "reporter_status_human": {
            "summary": reporter_summary,
            "status": _clip(reporter_status.get("status"), max_len=32) or _clip((_as_dict(report_section_seeds.get("reporter_evaluation"))).get("status"), max_len=32),
            "grade": _clip(reporter_status.get("grade"), max_len=16) or _clip((_as_dict(report_section_seeds.get("reporter_evaluation"))).get("grade"), max_len=16),
            "bullets": reporter_bullets,
        },
        "operator_conclusion_human": {
            "summary": conclusion_summary,
            "current_action": conclusion_current_action,
            "watch_next": conclusion_watch_next,
            "thesis_invalidation": conclusion_thesis_invalidation,
        },
        "report_section_seeds": {
            key: {
                "summary": _clip((_as_dict(value)).get("summary"), max_len=280),
                "bullets": _listify((_as_dict(value)).get("bullets"), max_items=4, max_len=180),
                "status": _clip((_as_dict(value)).get("status"), max_len=48),
                "grade": _clip((_as_dict(value)).get("grade"), max_len=24),
                "current_action": _clip((_as_dict(value)).get("current_action"), max_len=24),
                "watch_next": _listify((_as_dict(value)).get("watch_next"), max_items=4, max_len=140),
                "thesis_invalidation": _listify((_as_dict(value)).get("thesis_invalidation"), max_items=4, max_len=140),
            }
            for key, value in ({**report_section_seeds, "execution_quality": execution_quality_seed}).items()
            if isinstance(value, dict)
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


def _compact_section_seed_for_llm(value: Any) -> Dict[str, Any]:
    row = value if isinstance(value, dict) else {}
    out = {
        "summary": _clip(row.get("summary"), max_len=220),
        "bullets": _listify(row.get("bullets"), max_items=2, max_len=140),
        "status": _clip(row.get("status"), max_len=24),
        "grade": _clip(row.get("grade"), max_len=16),
        "current_action": _clip(row.get("current_action"), max_len=24),
        "watch_next": _listify(row.get("watch_next"), max_items=2, max_len=120),
        "thesis_invalidation": _listify(row.get("thesis_invalidation"), max_items=2, max_len=120),
    }
    return {key: val for key, val in out.items() if val not in ("", None, [], {})}


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
    report_section_seeds = compact.get("report_section_seeds") if isinstance(compact.get("report_section_seeds"), dict) else {}
    execution_seed = _as_dict(report_section_seeds.get("execution_quality"))
    if execution.get("summary") and execution_outcome_summary_is_placeholder(execution_seed.get("summary")):
        execution_seed = dict(execution_seed)
        execution_seed["summary"] = execution.get("summary")
        if execution.get("bullets"):
            execution_seed["bullets"] = _listify(execution.get("bullets"), max_items=4, max_len=180)
        if execution.get("status"):
            execution_seed["status"] = execution.get("status")
    guard_seed = _as_dict(report_section_seeds.get("guard_approval_result"))
    reporter_seed = _as_dict(report_section_seeds.get("reporter_evaluation"))
    if _reporter_summary_is_placeholder(reporter.get("summary")) and _clip(reporter_seed.get("summary"), max_len=220):
        reporter = dict(reporter)
        reporter["summary"] = _clip(reporter_seed.get("summary"), max_len=220)
        if reporter_seed.get("bullets"):
            reporter["bullets"] = _listify(reporter_seed.get("bullets"), max_items=4, max_len=180)
        if reporter_seed.get("status"):
            reporter["status"] = _clip(reporter_seed.get("status"), max_len=24)
        if reporter_seed.get("grade"):
            reporter["grade"] = _clip(reporter_seed.get("grade"), max_len=16)
    conclusion_seed = _as_dict(report_section_seeds.get("final_operator_conclusion"))
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
        "strategist_output": _as_dict(compact.get("strategist_output")),
        "strategist_refresh_trace": _as_dict(compact.get("strategist_refresh_trace")),
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
            "theme_strength_packet": _compact_scalar_dict(
                market.get("theme_strength_packet"),
                max_items=8,
                max_len=120,
            ),
            "theme_source": market.get("theme_source"),
            "theme_source_status": market.get("theme_source_status"),
            "theme_source_reason": market.get("theme_source_reason"),
            "theme_strength_top_themes": _listify(market.get("theme_strength_top_themes"), max_items=6, max_len=60),
            "risk_mode": market.get("risk_mode"),
            "selected_playbook": market.get("selected_playbook"),
            "preferred_themes": _listify(market.get("preferred_themes"), max_items=4, max_len=60),
            "avoid_themes": _listify(market.get("avoid_themes"), max_items=4, max_len=60),
            "scanner_bias_summary": {
                "enabled": (market.get("scanner_bias_summary") or {}).get("enabled"),
                "active_biases": _listify((market.get("scanner_bias_summary") or {}).get("active_biases"), max_items=6, max_len=80),
                "bias_strength": _clip((market.get("scanner_bias_summary") or {}).get("bias_strength"), max_len=24),
                "bias_source": _clip((market.get("scanner_bias_summary") or {}).get("bias_source"), max_len=80),
                "summary": _clip((market.get("scanner_bias_summary") or {}).get("summary"), max_len=220),
            },
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
            "summary": guard.get("summary") or guard_seed.get("summary"),
            "status": guard.get("status") or guard_seed.get("status"),
            "bullets": _listify(guard.get("bullets"), max_items=4, max_len=180) or _listify(guard_seed.get("bullets"), max_items=4, max_len=180),
        },
        "execution": {
            "summary": execution.get("summary") or execution_seed.get("summary"),
            "status": execution.get("status") or execution_seed.get("status"),
            "bullets": _listify(execution.get("bullets"), max_items=4, max_len=180) or _listify(execution_seed.get("bullets"), max_items=4, max_len=180),
        },
        "reporter": {
            "summary": reporter.get("summary") or reporter_seed.get("summary"),
            "status": reporter.get("status") or reporter_seed.get("status"),
            "grade": reporter.get("grade") or reporter_seed.get("grade"),
            "bullets": _listify(reporter.get("bullets"), max_items=3, max_len=160) or _listify(reporter_seed.get("bullets"), max_items=3, max_len=160),
        },
        "operator_conclusion": {
            "summary": conclusion.get("summary") or conclusion_seed.get("summary"),
            "current_action": conclusion.get("current_action") or conclusion_seed.get("current_action"),
            "watch_next": _listify(conclusion.get("watch_next"), max_items=3, max_len=140) or _listify(conclusion_seed.get("watch_next"), max_items=3, max_len=140),
            "thesis_invalidation": _listify(conclusion.get("thesis_invalidation"), max_items=3, max_len=140) or _listify(conclusion_seed.get("thesis_invalidation"), max_items=3, max_len=140),
        },
        "report_section_seeds": {
            "market_context_at_entry": _compact_section_seed_for_llm(report_section_seeds.get("market_context_at_entry")),
            "strategist_summary": _compact_section_seed_for_llm(report_section_seeds.get("strategist_summary")),
            "why_this_symbol_was_chosen": _compact_section_seed_for_llm(report_section_seeds.get("why_this_symbol_was_chosen")),
            "entry_decision": _compact_section_seed_for_llm(report_section_seeds.get("entry_decision")),
            "holding_monitoring_story": _compact_section_seed_for_llm(report_section_seeds.get("holding_monitoring_story")),
            "exit_decision": _compact_section_seed_for_llm(report_section_seeds.get("exit_decision")),
            "scanner_filters": _compact_section_seed_for_llm(report_section_seeds.get("scanner_filters")),
            "execution_quality": _compact_section_seed_for_llm(execution_seed),
            "guard_approval_result": _compact_section_seed_for_llm(guard_seed),
            "reporter_evaluation": _compact_section_seed_for_llm(reporter_seed),
            "final_operator_conclusion": _compact_section_seed_for_llm(conclusion_seed),
        },
        "timeline": _compact_timeline_rows(story_input.get("timeline"), head=1, tail=5),
        "improvement_points": _listify(compact.get("improvement_points"), max_items=4, max_len=140),
        "strategist_evidence": _as_dict(compact.get("strategist_evidence")),
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
    seeded = source.get("report_section_provenance_seeds") if isinstance(source.get("report_section_provenance_seeds"), dict) else {}

    def _pick(section_key: str, *legacy_keys: str) -> Dict[str, Any]:
        direct = source.get(section_key)
        if isinstance(direct, dict) and direct:
            return _normalize_provenance_entry(direct)
        seeded_entry = seeded.get(section_key)
        if isinstance(seeded_entry, dict) and seeded_entry:
            return _normalize_provenance_entry(seeded_entry)
        for legacy_key in legacy_keys:
            legacy = source.get(legacy_key)
            if isinstance(legacy, dict) and legacy:
                return _normalize_provenance_entry(legacy)
        return fallback

    return {
        "executive_summary": _pick("executive_summary", "operator_conclusion_human"),
        "market_context_at_entry": _pick("market_context_at_entry", "market_context_human"),
        "strategist_summary": _pick("strategist_summary", "market_context_at_entry", "market_context_human"),
        "strategist_refresh_trace": _pick("strategist_refresh_trace", "strategist_output", "commander"),
        "why_this_symbol_was_chosen": _pick("why_this_symbol_was_chosen", "scanner_reason_human"),
        "entry_decision": _pick("entry_decision", "why_this_symbol_was_chosen", "scanner_reason_human"),
        "holding_monitoring_story": _pick("holding_monitoring_story", "monitor_reason_human"),
        "exit_decision": _pick("exit_decision", "holding_monitoring_story", "monitor_reason_human"),
        "execution_quality": _pick("execution_quality", "execution_outcome_human"),
        "scanner_filters": _pick("scanner_filters", "filters_human"),
        "guard_approval_result": _pick("guard_approval_result", "guard_reason_human"),
        "reporter_evaluation": _pick("reporter_evaluation", "reporter_status_human"),
        "errors_weaknesses_improvement_points": _pick("errors_weaknesses_improvement_points", "reporter_evaluation", "reporter_status_human"),
        "full_timeline": _pick("full_timeline", "timeline"),
        "final_operator_conclusion": _pick("final_operator_conclusion", "operator_conclusion_human"),
    }


def _contains_hangul(value: Any) -> bool:
    # Avoid a regex here: this file has previously been damaged by mojibake,
    # and a corrupted Hangul character class can break report generation before
    # the LLM call is even attempted.
    return any("\uac00" <= ch <= "\ud7a3" for ch in str(value or ""))


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
        ("Execution outcome summary was not captured.", "거래 생애주기 실행 요약은 기록되지 않았습니다."),
        ("Lifecycle conclusion was not captured.", "최종 생애주기 결론은 기록되지 않았습니다."),
        ("Entry reason was not captured.", "진입 이유는 기록되지 않았습니다."),
        ("Exit reason was not captured.", "청산 이유는 기록되지 않았습니다."),
        ("Reporter linkage was not captured.", "리포터 연계 정보는 기록되지 않았습니다."),
        ("Same-day reporter analysis was not generated yet.", "당일 리포터 분석은 아직 생성되지 않았습니다."),
        (
            "A same-day reporter file exists, but this run was not linked to a run-specific evaluation yet.",
            "당일 리포터 파일은 있지만 이 run에 대한 개별 평가는 아직 연결되지 않았습니다.",
        ),
        ("A same-day reporter analysis was linked to this run.", "당일 리포터 분석이 이 run에 연결됐습니다."),
        ("Interim summary:", "중간 요약:"),
        ("Reporter status:", "리포터 상태는"),
        ("Reporter reason:", "리포터 판단 사유는"),
        ("Reporter grade:", "리포터 등급은"),
        ("Reporter summary:", "리포터 요약은"),
        ("Monitor posture changes", "모니터 posture 변화"),
        ("Macro/news regime changes", "거시 환경 및 뉴스 레짐 변화"),
        ("Lifecycle status is closed", "생애주기 상태는 closed"),
        ("Lifecycle status is open", "생애주기 상태는 open"),
        ("Trailing stop", "추적 손절"),
        ("trailing stop", "추적 손절"),
        ("시장 시장 상태은", "시장 상태는"),
        ("시장 상태은", "시장 상태는"),
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
        ("breakout_above_recent_high_with_vwap_structure_confirmation", "직전 고점 돌파와 VWAP 구조 확인"),
        ("breakout_path", "돌파 경로"),
        ("pullback_volume_path", "눌림목·거래량 경로"),
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
    cleaned = cleaned.replace(
        "pullback rebound above vwap with volume confirmation",
        "VWAP 위 되돌림 반등과 거래량 확인",
    )
    cleaned = cleaned.replace(
        "눌림목 rebound above vwap with volume confirmation",
        "VWAP 위 되돌림 반등과 거래량 확인",
    )
    cleaned = cleaned.replace(
        "pullback structure above vwap with volume confirmation",
        "VWAP 위 눌림목 구조와 거래량 확인",
    )
    cleaned = cleaned.replace(
        "눌림목 structure above vwap with volume confirmation",
        "VWAP 위 눌림목 구조와 거래량 확인",
    )
    cleaned = cleaned.replace(
        "breakout above recent high with vwap hold and volume confirmation",
        "VWAP 유지와 거래량 확인이 있는 최근 고점 돌파",
    )
    cleaned = re.sub(r"스캐너 1순위\s+([A-Z0-9]+)은", r"스캐너 상위 후보 \1은", cleaned)
    cleaned = cleaned.replace(" 이유로 막혔고", " 이유로 보류됐고")
    cleaned = cleaned.replace(" 사유로 막힌 뒤", " 사유로 보류된 뒤")
    lowered = cleaned.lower()
    exact_mapping = {
        "the decision path was recorded, but the operator-facing summary is limited.": "의사결정 경로는 기록되었지만 운영자용 요약은 제한적으로만 남아 있습니다.",
        "current lifecycle status is closed. entry and exit are connected in one lifecycle story.": "이번 라이프사이클은 종결 상태이며, 진입과 청산이 하나의 거래 흐름으로 연결됐습니다.",
        "current lifecycle status is open. entry and exit are still unfolding within one lifecycle story.": "이번 라이프사이클은 아직 진행 중이며, 진입 이후 청산 판단이 이어지고 있습니다.",
        "supervisor approved the order because allowed.": "슈퍼바이저는 주문을 승인했고 가드 판단은 허용이었습니다.",
        "execution quality details were not captured.": "실행 품질 세부 내용은 별도로 기록되지 않았습니다.",
        "reporter linkage was not available yet.": "리포터 연계 결과는 아직 연결되지 않았습니다.",
        "reporter linkage status was recorded separately.": "리포터 연계 상태는 별도로 기록되어 있습니다.",
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
        "link same-day reporter analysis to this lifecycle for a complete quality review.": "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다.",
        "same-price round trips produced fee/tax drag; tighten follow-through evidence before repeating quick reversals.": "동일가 왕복 거래에서 수수료와 세금 손실이 반복돼, 짧은 반전 시도 전에는 후속 추세 확인을 더 엄격하게 봐야 합니다.",
        "same-day closed trades are loss-heavy; keep defensive entry posture until follow-through quality improves.": "당일 닫힌 거래 손익이 전반적으로 약해, 후속 추세 확인 품질이 개선될 때까지는 방어적인 진입 자세를 유지해야 합니다.",
        "selection": "선정 근거를 정리했습니다.",
        "entry": "진입 판단을 정리했습니다.",
        "filters": "스캐너 필터 점검 결과를 정리했습니다.",
        "guard": "승인 및 가드 판단 결과를 정리했습니다.",
        "execution": "실행 결과를 정리했습니다.",
        "reporter": "리포터 평가를 정리했습니다.",
        "none": "추가 보완 포인트는 제한적입니다.",
        "top value or trading-value input supported the selection": "거래대금 상위 신호가 선정 근거를 뒷받침했습니다.",
        "top volume or turnover input supported the selection": "회전율 신호는 존재했지만 최종 우위 근거로는 약했습니다.",
        "theme boost or sector source matched the strategist frame": "테마 가점과 섹터 소스가 전략가 프레임과 맞아떨어졌습니다.",
        "12/13 captured chart features": "13개 중 12개 차트 피처가 확보됐습니다.",
        "news/global sentiment contribution was 0.295": "뉴스와 글로벌 감성 기여 합산값은 0.295였습니다.",
        "risk score was 0.563 and supervisor allow=true": "리스크 점수는 0.563이었고 supervisor 허용 상태도 유지됐습니다.",
        "price anomaly check was not captured in this run": "이번 run에서는 가격 이상치 점검 결과가 저장되지 않았습니다.",
        "price anomaly check was 기록되지 않음 in this run": "이번 run에서는 가격 이상치 점검 결과가 저장되지 않았습니다.",
        "monitor price cross-check found no anomaly": "모니터 가격 교차검증에서 이상치가 확인되지 않았습니다.",
        "monitor price cross-check flagged an anomaly": "모니터 가격 교차검증에서 이상치가 감지되었습니다.",
        "spread or slippage diagnostics were not captured in this run": "이번 run에서는 호가 스프레드 또는 슬리피지 진단이 저장되지 않았습니다.",
        "spread or slippage diagnostics were 기록되지 않음 in this run": "이번 run에서는 호가 스프레드 또는 슬리피지 진단이 저장되지 않았습니다.",
        "holding-phase evidence is thin; preserve more monitor context between entry and exit.": "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 맥락이 충분하지 않습니다.",
        "같은 날 생성된 reporter 분석을 이 lifecycle에 연결해 전체 품질 평가를 완성해 주세요.": "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다.",
        "보유 단계 근거가 얇아 진입과 청산 사이의 모니터 맥락을 더 보존해야 합니다.": "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 맥락이 충분하지 않습니다.",
        "monitor trigger changes": "모니터 트리거 변화",
        "macro/news shifts": "거시 환경 및 뉴스 변화",
        "stop-loss breach": "손절 기준 이탈",
        "monitor and scanner divergence": "모니터와 스캐너 판단 발산",
        "negative macro regime shift": "거시 환경의 부정적 전환",
        "guard reason: allowed": "가드 판단 사유는 허용입니다.",
        "supervisor verdict: approve": "슈퍼바이저 최종 판단은 승인입니다.",
        "broad_market_leaders": "브로드마켓 리더",
        "top_value": "거래대금 상위",
        "top_volume": "거래량 상위",
        "sector_theme": "섹터·테마 정렬",
    }
    if lowered in exact_mapping:
        return exact_mapping[lowered]

    m = _safe_fullmatch(
        r"same-day closed trade reports show (\d+) trades with (\d+) wins,\s*(\d+) losses,\s*avg pnl pct\s*([0-9.+\-]+)\.?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if m:
        trade_count = int(m.group(1))
        win_count = int(m.group(2))
        loss_count = int(m.group(3))
        avg_pnl_pct = _fmt_pct(str(m.group(4)).rstrip("."))
        return f"당일 closed trade {trade_count}건, 승/패 {win_count}/{loss_count}, 평균 손익률 {avg_pnl_pct}였습니다."

    m = _safe_fullmatch(r"same-price cost-loss trades\s*(\d+)/(\d+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"동일가 왕복 후 비용 손실 거래가 {m.group(2)}건 중 {m.group(1)}건에서 확인됐습니다."

    m = _safe_fullmatch(
        r"정규화된 청산 사유는\s+SELL was triggered because\s+(.+?)\.?입니다\.?",
        cleaned,
        flags=re.IGNORECASE,
    )
    if m:
        exit_label = _exit_reason_label(m.group(1))
        if exit_label:
            return f"정규화된 청산 사유는 {exit_label}입니다."

    m = _safe_fullmatch(r"SELL was triggered because\s+(.+?)\.?", cleaned, flags=re.IGNORECASE)
    if m:
        trigger_label = _operator_axis_label(m.group(1))
        return f"{trigger_label} 기준으로 청산됐습니다."

    m = _safe_fullmatch(r"Market regime:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"시장 상태는 {_clip(m.group(1), max_len=160)}입니다."
    m = _safe_fullmatch(r"시장 regime:\s*([^,]+),\s*감성:\s*([^,]+),\s*플레이북:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"시장 상태는 {_clip(m.group(1), max_len=80)}이며, 시장 심리는 {_clip(m.group(2), max_len=80)}이고, 플레이북은 {_clip(m.group(3), max_len=120)}입니다."
    m = _safe_fullmatch(r"Global sentiment score:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"글로벌 감성 점수는 {_clip(m.group(1), max_len=120)}입니다."
    m = _safe_fullmatch(r"글로벌 감성 점수:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"글로벌 감성 점수는 {_clip(m.group(1), max_len=120)}입니다."
    m = _safe_fullmatch(r"VIX:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"VIX 수준은 {_clip(m.group(1), max_len=120)}입니다."
    m = _safe_fullmatch(r"VIX 수준:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"VIX 수준은 {_clip(m.group(1), max_len=120)}입니다."
    m = _safe_fullmatch(r"News input:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"뉴스 입력 요약은 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"News query targets:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"뉴스 조회 대상은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(
        r"적용 정책[:：]?\s*timeframe\s*([0-9]+)\s*분,\s*breakout lookback\s*([0-9]+),\s*volume ratio min\s*([0-9.]+)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if m:
        return (
            f"적용 정책은 {int(m.group(1))}분봉, 돌파 확인 기준 봉 수 {int(m.group(2))}, "
            f"최소 거래량 비율 {float(m.group(3)):.2f}였습니다."
        )
    m = _safe_fullmatch(r"Commander 의도[:：]?\s*([^,]+),\s*라우트[:：]?\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"Commander 의도는 {_clip(m.group(1), max_len=80)}이고, 선택된 라우트는 {_clip(m.group(2), max_len=120)}입니다."
    m = _safe_fullmatch(r"정책 검증 상태[:：]?\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        status_text = _clip(m.group(1), max_len=200).replace("(", ", ").replace(")", "")
        return f"정책 검증 상태는 {status_text}입니다."
    m = _safe_fullmatch(r"VWAP 확장 비율 조건[:：]?\s*([^,]+),\s*눌림목 비율[:：]?\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"VWAP 확장 허용 범위는 {_clip(m.group(1), max_len=80)}이고, 눌림목 비율 범위는 {_clip(m.group(2), max_len=80)}입니다."
    m = _safe_fullmatch(r"Scanner linkage:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"스캐너 연결 근거는 {_clip(m.group(1), max_len=260)}입니다."
    m = _safe_fullmatch(r"execution quote snapshot spread was\s*([0-9.]+)\s*bps", cleaned, flags=re.IGNORECASE)
    if m:
        return f"실행 시점 호가 스냅샷 기준 스프레드는 {float(m.group(1)):.1f}bps였습니다."
    m = _safe_fullmatch(r"Key strategist inputs:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"전략가 핵심 입력은 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"Market news titles:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주요 시장 뉴스는 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"Candidate news titles:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"후보 종목 관련 뉴스는 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"테마:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주요 테마는 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"적용 테마:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"적용된 테마는 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"뉴스 분석:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"뉴스 분석 범위는 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Universe scanned:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=80)
        if value == "not_captured":
            return "비교한 후보 수는 별도로 기록되지 않았습니다."
        return f"총 {value}개 후보를 비교했습니다."
    m = _safe_fullmatch(r"Selected rank:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=80)
        if value == "not_captured":
            return "선정 순위 정보는 별도로 기록되지 않았습니다."
        return f"최종 선정 순위는 {value}입니다."
    m = _safe_fullmatch(r"Selected because:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"선정 이유는 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Top candidates:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"상위 후보는 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"Why not others:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"다른 후보가 밀린 이유는 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"Selection decision:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"최종 선정 판단은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Final decision basis:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"최종 결정 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Tie-break rule:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"동률 해소 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"동률 해소 기준[:：]?\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"동률 해소 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Runner-ups lost because:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"차순위 후보가 밀린 이유는 {_clip(m.group(1), max_len=240)}입니다."
    m = _safe_fullmatch(r"Selection sources:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"선정에 반영된 핵심 소스는 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Ranking basis:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"순위 산정 기준은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Chart / feature coverage:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"차트 및 지표 충실도는 {_clip(m.group(1), max_len=120)}입니다."
    m = _safe_fullmatch(r"Entry run:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "진입 판단이 기록된 run 정보는 남아 있지 않습니다."
        return f"진입 판단이 기록된 run은 {value}입니다."
    m = _safe_fullmatch(r"Entry time:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "진입 시각은 별도로 기록되지 않았습니다."
        return f"진입 시각은 {value}입니다."
    m = _safe_fullmatch(r"Entry action:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"진입 액션은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Entry reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=240)
        if value == "not_captured":
            return "진입 판단 사유는 별도로 기록되지 않았습니다."
        return f"진입 판단 근거는 {value}입니다."
    m = _safe_fullmatch(r"보유 기간:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"보유 기간은 {_clip(m.group(1), max_len=140)}입니다."
    m = _safe_fullmatch(r"모니터 실행:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"모니터 실행 기록은 {_clip(m.group(1), max_len=180)}입니다."
    m = _safe_fullmatch(r"모니터 판단:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"모니터 판단 흐름은 {_clip(m.group(1), max_len=220)}입니다."
    m = _safe_fullmatch(r"Monitor runs:\s*(\d+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"모니터는 총 {m.group(1)}회 실행되었습니다."
    m = _safe_fullmatch(r"Posture:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재 포지션 판단은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Trigger type:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"감지된 핵심 신호는 {_operator_axis_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Position age:\s*(\d+)\s*seconds", cleaned, flags=re.IGNORECASE)
    if m:
        return f"포지션 보유 시간은 약 {m.group(1)}초입니다."
    m = _safe_fullmatch(r"Effective stop:\s*([^(]+?)(?:\s*\((.+)\))?", cleaned, flags=re.IGNORECASE)
    if m:
        level = _clip(m.group(1), max_len=80)
        reason = _operator_axis_label(m.group(2))
        if reason and reason != "-":
            return f"유효 손절 기준은 {level} 수준이며, 기준 축은 {reason}입니다."
        return f"유효 손절 기준은 {level} 수준입니다."
    m = _safe_fullmatch(r"Take profit:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"목표 수익 실현 기준은 {_clip(m.group(1), max_len=80)} 수준입니다."
    m = _safe_fullmatch(r"Active exit axis:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재 우선 감시 중인 청산 축은 {_operator_axis_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Exit confirmation:\s*(\d+)/(\d+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"청산 확인 조건은 {m.group(1)}/{m.group(2)} 단계로 기록되었습니다."
    m = _safe_fullmatch(r"Watch axes:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        axes = ", ".join(_operator_axis_label(part.strip()) for part in m.group(1).split(","))
        return f"주요 감시 축은 {axes}입니다."
    m = _safe_fullmatch(r"Decision chain:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"판단 흐름은 {_clip(m.group(1), max_len=220)} 순서로 이어졌습니다."
    m = _safe_fullmatch(r"Current price / avg / peak:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재가, 평균가, 고점 기준 값은 {_clip(m.group(1), max_len=200)}입니다."
    m = _safe_fullmatch(r"Current drawdown / peak drawdown:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"현재 손익 변동과 고점 대비 하락폭은 {_clip(m.group(1), max_len=200)}입니다."
    m = _safe_fullmatch(r"Price source:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"가격 기준 소스는 {_clip(m.group(1), max_len=140)}입니다."
    m = _safe_fullmatch(r"Feature source:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"지표 기준 소스는 {_clip(m.group(1), max_len=140)}입니다."
    m = _safe_fullmatch(r"Recent monitor update:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"최근 모니터 업데이트는 다음과 같습니다: {_clip(m.group(1), max_len=240)}"
    m = _safe_fullmatch(r"Exit run:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "청산 판단이 기록된 run 정보는 남아 있지 않습니다."
        return f"청산 판단이 기록된 run은 {value}입니다."
    m = _safe_fullmatch(r"Exit time:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "청산 시각은 별도로 기록되지 않았습니다."
        return f"청산 시각은 {value}입니다."
    m = _safe_fullmatch(r"Exit action:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"청산 액션은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Exit reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=240)
        if value in {"position still open", "still open"}:
            return "현재 포지션은 아직 열려 있어 확정된 청산 사유는 없습니다."
        if value == "not_captured":
            return "청산 사유는 별도로 기록되지 않았습니다."
        return f"청산 사유는 {value}입니다."
    m = _safe_fullmatch(r"Execution outcome:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주문 실행 결과는 {_clip(m.group(1), max_len=180)}입니다."
    m = _safe_fullmatch(r"Quantity:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"수량: {_clip(m.group(1), max_len=80)}"
    m = _safe_fullmatch(r"수량:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"수량: {_clip(m.group(1), max_len=80)}"
    m = _safe_fullmatch(r"Execution mode:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"실행 모드: {_clip(m.group(1), max_len=120)}"
    m = _safe_fullmatch(r"Broker environment:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        if value == "not_captured":
            return "브로커 환경 정보는 별도로 기록되지 않았습니다."
        return f"브로커 환경은 {value}입니다."
    m = _safe_fullmatch(r"Supervisor verdict:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"감독 승인 판단은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Supervisor allow:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주문 허용 여부는 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Guard reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"가드 판단 사유는 {_clip(m.group(1), max_len=200)}입니다."
    m = _safe_fullmatch(r"Action reviewed:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"검토한 액션은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"Symbol reviewed:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"검토한 종목은 {_clip(m.group(1), max_len=60)}입니다."
    m = _safe_fullmatch(r"Approval mode:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        value = _clip(m.group(1), max_len=120)
        lowered_value = value.lower()
        if lowered_value == "not captured in the execution trace" or (
            "execution trace" in lowered_value and ("not captured" in lowered_value or "기록되지 않음" in value)
        ):
            return "승인 모드는 실행 추적에는 별도로 남아 있지 않습니다."
        return f"승인 모드는 {value}입니다."
    m = _safe_fullmatch(r"Lifecycle status:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        status_token = _clip(m.group(1), max_len=80).strip().lower()
        status_label = {
            "closed": "종결",
            "open": "진행 중",
            "pending": "대기",
        }.get(status_token, _clip(m.group(1), max_len=80))
        return f"라이프사이클 상태 {status_label}"
    m = _safe_fullmatch(r"Entry\s+([A-Z_]+)\s+was executed by run\s+([A-Za-z0-9_-]+)\.?", cleaned, flags=re.IGNORECASE)
    if m:
        return f"run {_clip(m.group(2), max_len=80)}에서 {_operator_action_label(m.group(1))} 진입이 실행됐습니다."
    m = _safe_fullmatch(r"Exit\s+([A-Z_]+)\s+was executed by run\s+([A-Za-z0-9_-]+)\.?", cleaned, flags=re.IGNORECASE)
    if m:
        return f"run {_clip(m.group(2), max_len=80)}에서 {_operator_action_label(m.group(1))} 청산이 실행됐습니다."
    m = _safe_fullmatch(r"슈퍼바이저 판단:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"감독 승인 판단은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"슈퍼바이저 허용:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"주문 허용 여부는 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"가드 이유:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"가드 판단 사유는 {_clip(m.group(1), max_len=200)}입니다."
    m = _safe_fullmatch(r"검토된 액션:\s*(.+)", cleaned, flags=re.IGNORECASE)
    if m:
        return f"검토한 액션은 {_operator_action_label(m.group(1))}입니다."
    m = _safe_fullmatch(r"(.+?):\s*(PASS|FAIL|NOT_AVAILABLE)\s*-\s*(.+)", cleaned, flags=re.IGNORECASE)
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


def _preserve_legacy_trade_report_bullet(value: Any) -> str:
    cleaned = _clip(value, max_len=260)
    if not cleaned:
        return ""
    legacy_prefixes = (
        "Top candidates:",
        "Selection decision:",
        "Final decision basis:",
        "Tie-break rule:",
        "Runner-ups lost because:",
        "Monitor runs:",
        "Trigger type:",
    )
    if any(cleaned.startswith(prefix) for prefix in legacy_prefixes):
        return cleaned
    return ""


def _operatorize_report_section(section: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(section or {})
    if "headline" in normalized:
        normalized["headline"] = _operatorize_report_text(normalized.get("headline"))
    if "summary" in normalized:
        normalized["summary"] = _operatorize_report_text(normalized.get("summary"))
    if isinstance(normalized.get("bullets"), list):
        normalized_bullets: List[str] = []
        for item in list(normalized.get("bullets") or []):
            preserved = _preserve_legacy_trade_report_bullet(item)
            if preserved:
                normalized_bullets.append(preserved)
                continue
            operatorized = _operatorize_report_text(item)
            if operatorized:
                normalized_bullets.append(operatorized)
        normalized["bullets"] = _dedupe_list(
            normalized_bullets,
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


def _is_scanner_execution_mismatch_text(value: Any) -> bool:
    text = _clip(value, max_len=2000)
    if not text:
        return False
    lowered = text.lower()
    has_mismatch = "불일치" in text or "mismatch" in lowered or "divergence" in lowered
    has_scanner = "스캐너" in text or "scanner" in lowered
    has_execution = any(token in text for token in ("실행", "체결", "진입", "선택")) or any(
        token in lowered for token in ("execution", "executed", "entry", "selected")
    )
    return bool(has_mismatch and has_scanner and has_execution)


def _is_scanner_selection_label_line(value: Any) -> bool:
    text = _clip(value, max_len=300)
    lowered = text.lower()
    return text.startswith(("스캐너 선택 종목:", "실행 종목:")) or lowered.startswith(
        ("scanner selected symbol:", "execution symbol:")
    )


def _prefer_fallback_summary(section_key: str, ai_text: Any, fallback_text: Any) -> str:
    ai_clean = _clip(ai_text, max_len=2000)
    fallback_clean = _clip(fallback_text, max_len=2000)
    preferred = _prefer_fallback_text(ai_clean, fallback_clean)
    if preferred == fallback_clean:
        return preferred
    if not fallback_clean:
        return preferred
    token = str(section_key or "").strip().lower()
    if token in {"entry_decision", "holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision", "execution_quality", "reporter_evaluation"}:
        return fallback_clean
    ai_lower = ai_clean.lower()
    if token in {"market_context_at_entry", "strategist_summary"}:
        if (
            not _contains_hangul(ai_clean)
            or _has_noisy_trade_report_text(ai_clean)
            or "headlines were considered" in ai_lower
            or "market regime" in ai_lower
            or "neutral regime" in ai_lower
        ):
            return fallback_clean
    if token in {"scanner_filters"}:
        if "scanner and guard checks" in ai_lower or not _contains_hangul(ai_clean):
            return fallback_clean
    if token in {"why_this_symbol_was_chosen", "why_this_symbol"}:
        if (
            not _contains_hangul(ai_clean)
            or _has_noisy_trade_report_text(ai_clean)
            or _is_scanner_execution_mismatch_text(ai_clean)
            or "trading value" in ai_lower
            or "theme and sector alignment" in ai_lower
            or "highest total score" in ai_lower
            or "highest combined scanner score" in ai_lower
        ):
            return fallback_clean
    if token in {"scanner_candidate_comparison"}:
        if not _contains_hangul(ai_clean) or _has_noisy_trade_report_text(ai_clean):
            return fallback_clean
    if token in {"entry_decision"}:
        if (
            not _contains_hangul(ai_clean)
            or "strategist-guided weighting" in ai_lower
            or "breakout_above_recent_high_with_vwap_structure_confirmation" in ai_lower
            or "entry timing" in ai_lower
        ):
            return fallback_clean
    if token in {"holding_monitoring_story", "monitor_trigger_reasoning"}:
        if (
            "holding_duration:" in ai_lower
            or "run_count:" in ai_lower
            or "recent_monitor_updates:" in ai_lower
            or "peak_price:" in ai_lower
            or "current_price:" in ai_lower
        ):
            return fallback_clean
    if token in {"exit_decision"}:
        if (
            "exit_reason_human" in ai_lower
            or "trigger_type:" in ai_lower
            or "hard_stop_pct" in ai_lower
            or "effective_stop_loss_pct" in ai_lower
            or "take_profit_pct" in ai_lower
        ):
            return fallback_clean
    if token in {"execution_quality"}:
        if (
            "execution outcome:" in ai_lower
            or "order status:" in ai_lower
            or "broker environment:" in ai_lower
        ):
            return fallback_clean
    if token in {"reporter_evaluation"}:
        if (
            not _contains_hangul(ai_clean)
            or "overtrading" in ai_lower
            or "rapid exit pressure" in ai_lower
            or "reporter linkage" in ai_lower
        ):
            return fallback_clean
    return preferred


def _trade_report_priority_bullet_prefixes(section_key: str) -> List[str]:
    key = str(section_key or "").strip().lower()
    if key in {"market_context_at_entry", "market_context"}:
        return [
            "Market regime:",
            "시장 상태는",
            "Global sentiment score:",
            "글로벌 감성 점수는",
            "VIX",
            "Scanner linkage:",
            "Key strategist inputs:",
            "전략가 핵심 입력은",
            "Market news titles:",
            "주요 시장 뉴스는",
            "Candidate news titles:",
            "후보 종목 관련 뉴스는",
        ]
    if key in {"strategist_summary"}:
        return [
            "핵심 입력은",
            "전략 해석은",
            "뉴스 연결 해석은",
            "스캐너 반영은",
            "종목 연결은",
            "Scanner linkage:",
            "전략가 핵심 입력은",
            "주요 시장 뉴스는",
            "스캐너 연결 근거는",
        ]
    if key in {"why_this_symbol_was_chosen", "why_this_symbol", "scanner_candidate_comparison", "entry_decision"}:
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
    section_token = str(section_key or "").strip().lower()
    if section_token in {"market_context_at_entry", "market_context"}:
        ai_bullets = [row for row in ai_bullets if not _is_market_context_noise_bullet(row)]
        fallback_bullets = [row for row in fallback_bullets if not _is_market_context_noise_bullet(row)]
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
    merged["summary"] = _prefer_fallback_summary(section_key, section.get("summary"), fallback.get("summary"))
    ai_bullets = _listify(section.get("bullets"), max_items=12, max_len=260)
    fallback_bullets = _listify(fallback.get("bullets"), max_items=12, max_len=260)
    if section_key in {"why_this_symbol_was_chosen", "why_this_symbol"} and fallback_bullets:
        noisy_scanner_mismatch = _is_scanner_execution_mismatch_text(section.get("summary")) or any(
            _is_scanner_execution_mismatch_text(item) or _is_scanner_selection_label_line(item)
            for item in ai_bullets
        )
        if noisy_scanner_mismatch:
            merged["summary"] = _clip(fallback.get("summary"), max_len=2000) or merged.get("summary") or ""
            merged["bullets"] = fallback_bullets
            return merged
    if not ai_bullets:
        merged["bullets"] = fallback_bullets
    elif fallback_bullets and section_key in {"entry_decision", "holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision", "execution_quality", "reporter_evaluation"}:
        merged["bullets"] = fallback_bullets
    elif (
        fallback_bullets
        and section_key in {"entry_decision", "holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision", "execution_quality"}
        and any(
            any(token in str(item).lower() for token in (
                "entry_reason_human:",
                "risk_score:",
                "score_drivers:",
                "holding_duration:",
                "run_count:",
                "recent_monitor_updates:",
                "peak_price:",
                "current_price:",
                "exit_reason_human:",
                "trigger_type:",
                "hard_stop_pct",
                "effective_stop_loss_pct",
                "take_profit_pct",
                "execution outcome:",
                "broker environment:",
                "order status:",
            ))
            for item in ai_bullets
        )
    ):
        merged["bullets"] = fallback_bullets
    elif section_key in {"execution_quality", "guard_approval_result"} and any(_contains_hangul(item) for item in ai_bullets):
        merged["bullets"] = ai_bullets[:12]
    elif (
        fallback_bullets
        and section_key in {"holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision"}
        and sum(1 for item in ai_bullets if _is_low_information_bullet(item)) >= max(3, len(ai_bullets) // 2)
    ):
        merged["bullets"] = fallback_bullets
    elif (
        fallback_bullets
        and section_key in {"market_context_at_entry", "strategist_summary", "why_this_symbol_was_chosen", "scanner_candidate_comparison"}
        and (
            sum(
                1
                for item in ai_bullets
                if _is_low_information_bullet(item) or _has_noisy_trade_report_text(item)
            ) >= max(1, len(ai_bullets) // 2)
            or (
                not any(_contains_hangul(item) for item in ai_bullets)
                and any(_contains_hangul(item) for item in fallback_bullets)
            )
        )
    ):
        if section_key in {"why_this_symbol_was_chosen", "scanner_candidate_comparison"}:
            merged["bullets"] = _merge_bullets_with_fallback(section_key, ai_bullets, fallback_bullets)
        else:
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
    _merge_into("strategist_summary", candidate.get("strategist_summary"))
    _merge_into("strategist_refresh_trace", candidate.get("strategist_refresh_trace"))
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
    has_runtime_market_context = bool(market_context)
    has_runtime_scanner_reason = bool(scanner_reason)
    filters_human = story_input.get("filters_human") if isinstance(story_input.get("filters_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    guard_reason = story_input.get("guard_reason_human") if isinstance(story_input.get("guard_reason_human"), dict) else {}
    execution_outcome = story_input.get("execution_outcome_human") if isinstance(story_input.get("execution_outcome_human"), dict) else {}
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    memory_surface = build_trade_report_memory_surface(story_input)
    reporter_feedback_packet = _as_dict(memory_surface.get("reporter_feedback_packet"))
    operator_conclusion = (
        story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}
    )
    policy_ref_context = _extract_policy_ref_context(story_input, monitor_reason)
    scanner_bias_summary = _extract_scanner_bias_summary(story_input, scanner_reason)
    market_context = dict(market_context)
    strategist_context = shared_seed.get("strategist_context") if isinstance(shared_seed.get("strategist_context"), dict) else {}
    if strategist_context.get("playbook") and not market_context.get("playbook"):
        market_context["playbook"] = strategist_context.get("playbook")
    if strategist_context.get("selected_playbook") and not market_context.get("selected_playbook"):
        market_context["selected_playbook"] = strategist_context.get("selected_playbook")
    if strategist_context.get("policy_source") and not market_context.get("policy_source"):
        market_context["policy_source"] = strategist_context.get("policy_source")
    if strategist_context.get("themes") and not market_context.get("themes"):
        market_context["themes"] = list(strategist_context.get("themes") or [])
    if strategist_context.get("preferred_themes") and not market_context.get("preferred_themes"):
        market_context["preferred_themes"] = list(strategist_context.get("preferred_themes") or [])
    for theme_key in (
        "theme_strength_packet",
        "theme_source",
        "theme_source_status",
        "theme_source_reason",
        "theme_strength_top_themes",
        "theme_strength_scores",
    ):
        if strategist_context.get(theme_key) not in (None, "", [], {}) and not market_context.get(theme_key):
            market_context[theme_key] = strategist_context.get(theme_key)
    if strategist_context.get("market_context_summary") and not market_context.get("summary"):
        market_context["summary"] = strategist_context.get("market_context_summary")
    if policy_ref_context.get("risk_mode") and not market_context.get("risk_mode"):
        market_context["risk_mode"] = policy_ref_context.get("risk_mode")
    if policy_ref_context.get("selected_playbook") and not market_context.get("selected_playbook"):
        market_context["selected_playbook"] = policy_ref_context.get("selected_playbook")
    if policy_ref_context.get("preferred_themes") and not market_context.get("preferred_themes"):
        market_context["preferred_themes"] = policy_ref_context.get("preferred_themes")
    if policy_ref_context.get("avoid_themes") and not market_context.get("avoid_themes"):
        market_context["avoid_themes"] = policy_ref_context.get("avoid_themes")
    if scanner_bias_summary and not market_context.get("scanner_bias_summary"):
        market_context["scanner_bias_summary"] = scanner_bias_summary
    scanner_reason = dict(scanner_reason)
    has_runtime_monitor_reason = bool(monitor_reason)
    shared_scanner_reasoning = shared_seed.get("scanner_reasoning") if isinstance(shared_seed.get("scanner_reasoning"), dict) else {}
    shared_selection_trace = shared_scanner_reasoning.get("selection_trace") if isinstance(shared_scanner_reasoning.get("selection_trace"), dict) else {}
    shared_report_section_seeds = shared_seed.get("report_section_seeds") if isinstance(shared_seed.get("report_section_seeds"), dict) else {}
    market_context_seed = _as_dict(shared_report_section_seeds.get("market_context_at_entry"))
    strategist_summary_seed = _as_dict(shared_report_section_seeds.get("strategist_summary"))
    why_symbol_seed = _as_dict(shared_report_section_seeds.get("why_this_symbol_was_chosen"))
    entry_decision_seed = _as_dict(shared_report_section_seeds.get("entry_decision"))
    holding_story_seed = _as_dict(shared_report_section_seeds.get("holding_monitoring_story"))
    exit_decision_seed = _as_dict(shared_report_section_seeds.get("exit_decision"))
    scanner_filters_seed = _as_dict(shared_report_section_seeds.get("scanner_filters"))
    execution_quality_seed = _as_dict(shared_report_section_seeds.get("execution_quality"))
    guard_approval_seed = _as_dict(shared_report_section_seeds.get("guard_approval_result"))
    reporter_evaluation_seed = _as_dict(shared_report_section_seeds.get("reporter_evaluation"))
    final_operator_conclusion_seed = _as_dict(shared_report_section_seeds.get("final_operator_conclusion"))
    if shared_scanner_reasoning.get("selection_reason_with_bias") and not scanner_reason.get("selection_reason_with_bias"):
        scanner_reason["selection_reason_with_bias"] = shared_scanner_reasoning.get("selection_reason_with_bias")
    if shared_scanner_reasoning.get("selection_reason_with_bias") and not scanner_reason.get("summary"):
        scanner_reason["summary"] = shared_scanner_reasoning.get("selection_reason_with_bias")
    if shared_selection_trace.get("selected_symbol") and not scanner_reason.get("selected_symbol"):
        scanner_reason["selected_symbol"] = shared_selection_trace.get("selected_symbol")
    if shared_selection_trace.get("selected_rank") and not scanner_reason.get("selected_rank"):
        scanner_reason["selected_rank"] = shared_selection_trace.get("selected_rank")
    if shared_selection_trace.get("selected_symbol_score_drivers") and not scanner_reason.get("selected_symbol_score_drivers"):
        scanner_reason["selected_symbol_score_drivers"] = dict(shared_selection_trace.get("selected_symbol_score_drivers") or {})
    if shared_selection_trace.get("ranked_candidates") and not scanner_reason.get("top_candidates"):
        scanner_reason["top_candidates"] = list(shared_selection_trace.get("ranked_candidates") or [])
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
    scanner_selection_trace = _as_dict(story_input.get("scanner_selection_trace"))
    entry_scanner_context = (
        entry_summary.get("scanner_context")
        if isinstance(entry_summary.get("scanner_context"), dict)
        else {}
    )
    news_scanner_contribution = _as_dict(
        scanner_reason.get("news_scanner_contribution")
        or scanner_selection_trace.get("news_scanner_contribution")
        or entry_scanner_context.get("news_scanner_contribution")
    )
    effective_scanner_selection_trace = _as_dict(scanner_selection_trace) or _as_dict(shared_selection_trace)
    why_symbol_bullets = _build_scanner_choice_bullets(scanner_reason, market_context)
    if news_scanner_contribution:
        core = news_scanner_contribution.get("core_score_contributions") if isinstance(news_scanner_contribution.get("core_score_contributions"), dict) else {}
        sentiment_inputs = news_scanner_contribution.get("sentiment_inputs") if isinstance(news_scanner_contribution.get("sentiment_inputs"), dict) else {}
        theme_trace = news_scanner_contribution.get("theme_alignment_trace") if isinstance(news_scanner_contribution.get("theme_alignment_trace"), dict) else {}
        news_linkage = news_scanner_contribution.get("news_linkage_trace") if isinstance(news_scanner_contribution.get("news_linkage_trace"), dict) else {}
        def _core_value(key: str) -> float:
            row = core.get(key)
            if isinstance(row, dict):
                return float(row.get("value") or 0.0)
            try:
                return float(row or 0.0)
            except Exception:
                return 0.0
        extra_rows: List[str] = []
        extra_rows.append(
            "점수 기여 세부값은 "
            f"거래대금 {_core_value('trading_value'):+.3f}, "
            f"모멘텀 {_core_value('momentum'):+.3f}, "
            f"추세 {_core_value('trend'):+.3f}, "
            f"테마 가점 {_core_value('theme_boost'):+.3f}, "
            f"감성 {_core_value('sentiment'):+.3f}였습니다."
        )
        extra_rows.append(
            "감성 입력은 "
            f"뉴스 {float(sentiment_inputs.get('news_sentiment_score') or 0.0):+.3f}, "
            f"글로벌 {float(sentiment_inputs.get('global_sentiment_score') or 0.0):+.3f}, "
            f"혼합 {float(sentiment_inputs.get('blended_sentiment_component') or 0.0):+.3f}, "
            f"최종 반영 {float(sentiment_inputs.get('weighted_sentiment_score_contribution') or 0.0):+.3f}였습니다."
        )
        extra_rows.append(
            "테마 정렬은 "
            f"일치 여부 {bool(theme_trace.get('theme_source_matched'))}, "
            f"테마 가점 {float(theme_trace.get('theme_boost_score_contribution') or 0.0):+.3f}, "
            f"전략가 테마 {', '.join(_listify(theme_trace.get('strategist_themes'), max_items=4, max_len=60)) or '기록 없음'} 기준으로 반영됐습니다."
        )
        if theme_trace.get("theme_source") or theme_trace.get("theme_source_status") or theme_trace.get("theme_source_reason"):
            extra_rows.append(
                "테마 packet 출처는 "
                f"source={theme_trace.get('theme_source') or 'not_captured'}, "
                f"status={theme_trace.get('theme_source_status') or 'not_captured'}, "
                f"reason={theme_trace.get('theme_source_reason') or 'not_captured'} 기준으로 남았습니다."
            )
        extra_rows.append(
            "뉴스 연계는 "
            f"종목 헤드라인 {int(float(news_linkage.get('symbol_headline_count') or 0))}건, "
            f"시장 헤드라인 {int(float(news_linkage.get('market_headline_count') or 0))}건, "
            f"조회 대상 {', '.join(_listify(news_linkage.get('news_query_targets'), max_items=6, max_len=60)) or '기록 없음'} 기준으로 남았습니다."
        )
        existing = set(str(row) for row in why_symbol_bullets)
        for row in extra_rows:
            if row not in existing:
                why_symbol_bullets.append(row)
    raw_scanner_bullets = _listify(scanner_reason.get("bullets"), max_items=8, max_len=220)
    raw_scanner_bullets.extend(_listify(scanner_reason.get("why_selected"), max_items=4, max_len=180))
    selection_basis_text = _clip(scanner_reason.get("selection_basis"), max_len=220)
    if selection_basis_text:
        raw_scanner_bullets.append(f"Final decision basis: {selection_basis_text}")
    tie_break_text = _clip(scanner_reason.get("tie_break_rule"), max_len=220)
    if tie_break_text:
        raw_scanner_bullets.append(f"Tie-break rule: {tie_break_text}")
    runner_up_summaries = [
        f"Runner-ups lost because: {_clip((row or {}).get('symbol'), max_len=24)}: {_clip((row or {}).get('summary'), max_len=160)}"
        for row in list(scanner_reason.get("runner_ups_lost") or [])[:4]
        if isinstance(row, dict) and str((row or {}).get("symbol") or "").strip() and str((row or {}).get("summary") or "").strip()
    ]
    raw_scanner_bullets.extend(runner_up_summaries)
    for row in raw_scanner_bullets:
        if row and row not in why_symbol_bullets:
            why_symbol_bullets.append(row)

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
    if (
        (not has_runtime_scanner_reason and not scanner_selection_trace)
        or not scanner_choice_summary
        or _is_low_information_bullet(scanner_choice_summary)
    ) and str(why_symbol_seed.get("summary") or "").strip():
        scanner_choice_summary = _clip(why_symbol_seed.get("summary"), max_len=600)
    if str(shared_seed.get("scanner_evidence_status") or "").strip() == "unavailable":
        scanner_choice_summary = "Scanner evidence unavailable for this trade. Selection rationale is reported conservatively."
    market_context_summary = _build_market_context_summary(market_context, scanner_reason=scanner_reason)
    if (
        not has_runtime_market_context
        or not market_context_summary
        or _is_low_information_bullet(market_context_summary)
    ) and str(market_context_seed.get("summary") or "").strip():
        market_context_summary = _clip(market_context_seed.get("summary"), max_len=600)
    if str(shared_seed.get("strategist_evidence_status") or "").strip() == "unavailable" and (
        not market_context_summary or _is_low_information_bullet(market_context_summary)
    ):
        market_context_summary = "Strategist evidence unavailable for this trade. Market context is shown as limited."
    strategist_summary = _build_strategist_summary_section(market_context, scanner_reason)
    strategist_summary_summary = _clip(strategist_summary.get("summary"), max_len=600)
    if (
        not has_runtime_market_context
        or not strategist_summary_summary
        or _is_low_information_bullet(strategist_summary_summary)
    ) and str(strategist_summary_seed.get("summary") or "").strip():
        strategist_summary["summary"] = _clip(strategist_summary_seed.get("summary"), max_len=600)
    if (not strategist_summary.get("bullets")) and isinstance(strategist_summary_seed.get("bullets"), list):
        strategist_summary["bullets"] = _listify(strategist_summary_seed.get("bullets"), max_items=10, max_len=260)
    strategist_refresh_trace = _build_report_strategist_refresh_trace(story_input)
    if not why_symbol_bullets and isinstance(why_symbol_seed.get("bullets"), list):
        why_symbol_bullets = _listify(why_symbol_seed.get("bullets"), max_items=16, max_len=260)
    scanner_filters_summary = _build_scanner_filters_summary(filters_human)
    scanner_filters_bullets = _build_scanner_filters_bullets(filters_human)
    if not filters_human and str(scanner_filters_seed.get("summary") or "").strip():
        scanner_filters_summary = _clip(scanner_filters_seed.get("summary"), max_len=600)
    if not filters_human and isinstance(scanner_filters_seed.get("bullets"), list):
        scanner_filters_bullets = _listify(scanner_filters_seed.get("bullets"), max_items=10, max_len=260)

    entry_decision = {
        "summary": (
            _build_entry_decision_summary(entry_summary, scanner_reason, market_context, monitor_reason, action)
            if bool(shared_seed.get("entry_exists"))
            else "Entry evidence was insufficient, so entry timing is marked as unavailable."
        ),
        "bullets": _build_entry_decision_bullets(entry_summary, scanner_reason, market_context, monitor_reason, action),
    }
    if (
        not has_runtime_scanner_reason
        or not _clip(entry_decision.get("summary"), max_len=600)
        or _is_low_information_bullet(entry_decision.get("summary"))
    ) and str(entry_decision_seed.get("summary") or "").strip():
        entry_decision["summary"] = _clip(entry_decision_seed.get("summary"), max_len=600)
    if (not entry_decision.get("bullets")) and isinstance(entry_decision_seed.get("bullets"), list):
        entry_decision["bullets"] = _listify(entry_decision_seed.get("bullets"), max_items=12, max_len=260)
    hold_count = len(list(holding_summary.get("run_ids") or []))
    holding_story = {
        "summary": _build_holding_story_summary(hold_count, monitor_reason, status_text),
        "bullets": _build_holding_story_bullets(holding_summary, monitor_reason),
    }
    if (
        not has_runtime_monitor_reason
        or not _clip(holding_story.get("summary"), max_len=600)
        or _is_low_information_bullet(holding_story.get("summary"))
    ) and str(holding_story_seed.get("summary") or "").strip():
        holding_story["summary"] = _clip(holding_story_seed.get("summary"), max_len=600)
    if (not holding_story.get("bullets")) and isinstance(holding_story_seed.get("bullets"), list):
        holding_story["bullets"] = _listify(holding_story_seed.get("bullets"), max_items=12, max_len=260)
    if _clip(shared_seed.get("holding_duration"), max_len=80):
        holding_story["bullets"] = [_holding_duration_label(_clip(shared_seed.get('holding_duration'), max_len=80))] + list(
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
    if (
        not has_runtime_monitor_reason
        or not _clip(exit_decision.get("summary"), max_len=600)
        or _is_low_information_bullet(exit_decision.get("summary"))
    ) and str(exit_decision_seed.get("summary") or "").strip():
        exit_decision["summary"] = _clip(exit_decision_seed.get("summary"), max_len=600)
    if (not exit_decision.get("bullets")) and isinstance(exit_decision_seed.get("bullets"), list):
        exit_decision["bullets"] = _listify(exit_decision_seed.get("bullets"), max_items=12, max_len=260)
    if _clip(shared_seed.get("exit_reason"), max_len=240):
        exit_reason_label = _exit_reason_label(_clip(shared_seed.get("exit_reason"), max_len=240))
        exit_decision["bullets"] = [f"정규화된 청산 사유는 {exit_reason_label or _clip(shared_seed.get('exit_reason'), max_len=240)}입니다."] + list(
            exit_decision.get("bullets") or []
        )
    execution_quality = _build_execution_quality_section(
        story_input,
        execution_outcome,
        lifecycle_summary,
    )
    if execution_outcome_summary_is_placeholder(execution_quality_seed.get("summary")) and _clip(execution_quality.get("summary"), max_len=600):
        execution_quality_seed = dict(execution_quality_seed)
        execution_quality_seed["summary"] = _clip(execution_quality.get("summary"), max_len=600)
        if execution_quality.get("bullets"):
            execution_quality_seed["bullets"] = _listify(execution_quality.get("bullets"), max_items=12, max_len=260)
    if (
        not execution_outcome
        or not _clip(execution_quality.get("summary"), max_len=600)
        or _is_low_information_bullet(execution_quality.get("summary"))
    ) and str(execution_quality_seed.get("summary") or "").strip():
        execution_quality["summary"] = _clip(execution_quality_seed.get("summary"), max_len=600)
    if (not execution_quality.get("bullets")) and isinstance(execution_quality_seed.get("bullets"), list):
        execution_quality["bullets"] = _listify(execution_quality_seed.get("bullets"), max_items=12, max_len=260)
    reporter_eval = _build_reporter_evaluation_section(
        shared_seed,
        scanner_reason,
        monitor_reason,
        execution_outcome,
        reporter_status,
        reporter_feedback_packet,
    )
    if _reporter_summary_is_placeholder(reporter_eval.get("summary")) and _clip(reporter_evaluation_seed.get("summary"), max_len=600):
        reporter_eval["summary"] = _clip(reporter_evaluation_seed.get("summary"), max_len=600)
        if reporter_evaluation_seed.get("bullets"):
            reporter_eval["bullets"] = _listify(reporter_evaluation_seed.get("bullets"), max_items=12, max_len=260)
        if reporter_evaluation_seed.get("status"):
            reporter_eval["status"] = _clip(reporter_evaluation_seed.get("status"), max_len=48)
        if reporter_evaluation_seed.get("grade"):
            reporter_eval["grade"] = _clip(reporter_evaluation_seed.get("grade"), max_len=24)
    if (
        not reporter_status
        or not _clip(reporter_eval.get("summary"), max_len=600)
        or _is_low_information_bullet(reporter_eval.get("summary"))
    ) and str(reporter_evaluation_seed.get("summary") or "").strip():
        reporter_eval["summary"] = _clip(reporter_evaluation_seed.get("summary"), max_len=600)
    if (not reporter_eval.get("bullets")) and isinstance(reporter_evaluation_seed.get("bullets"), list):
        reporter_eval["bullets"] = _listify(reporter_evaluation_seed.get("bullets"), max_items=12, max_len=260)
    reporter_eval_status = _clip(reporter_eval.get("status"), max_len=48)
    if (
        not reporter_status
        or not reporter_eval_status
        or reporter_eval_status.lower() in {"missing", "not_captured", "unknown", "n/a"}
    ) and str(reporter_evaluation_seed.get("status") or "").strip():
        reporter_eval["status"] = _clip(reporter_evaluation_seed.get("status"), max_len=48)
    reporter_eval_grade = _clip(reporter_eval.get("grade"), max_len=24)
    if (
        not reporter_status
        or not reporter_eval_grade
        or reporter_eval_grade.lower() in {"missing", "not_captured", "unknown", "n/a"}
    ) and str(reporter_evaluation_seed.get("grade") or "").strip():
        reporter_eval["grade"] = _clip(reporter_evaluation_seed.get("grade"), max_len=24)
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
            "bullets": _build_market_context_bullets(market_context, scanner_reason=scanner_reason),
            "regime": _clip(market_context.get("regime"), max_len=40),
            "market_sentiment": _clip(market_context.get("market_sentiment"), max_len=40),
            "playbook": _clip(market_context.get("playbook"), max_len=40),
            "policy_source": _clip(market_context.get("policy_source"), max_len=80),
            "themes": _listify(market_context.get("themes"), max_items=6, max_len=80),
            "theme_strength_packet": _compact_scalar_dict(
                market_context.get("theme_strength_packet"),
                max_items=8,
                max_len=120,
            ),
            "theme_source": _clip(market_context.get("theme_source"), max_len=80),
            "theme_source_status": _clip(market_context.get("theme_source_status"), max_len=80),
            "theme_source_reason": _clip(market_context.get("theme_source_reason"), max_len=160),
            "theme_strength_top_themes": _listify(market_context.get("theme_strength_top_themes"), max_items=6, max_len=80),
            "risk_mode": _clip(market_context.get("risk_mode"), max_len=40),
            "selected_playbook": _clip(market_context.get("selected_playbook"), max_len=40),
            "preferred_themes": _listify(market_context.get("preferred_themes"), max_items=6, max_len=80),
            "avoid_themes": _listify(market_context.get("avoid_themes"), max_items=6, max_len=80),
            "scanner_bias_summary": {
                "enabled": (market_context.get("scanner_bias_summary") or {}).get("enabled"),
                "active_biases": _listify((market_context.get("scanner_bias_summary") or {}).get("active_biases"), max_items=6, max_len=80),
                "bias_strength": _clip((market_context.get("scanner_bias_summary") or {}).get("bias_strength"), max_len=24),
                "bias_source": _clip((market_context.get("scanner_bias_summary") or {}).get("bias_source"), max_len=80),
                "summary": _clip((market_context.get("scanner_bias_summary") or {}).get("summary"), max_len=220),
            },
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
            "strategist_market_context_summary": _clip(
                strategist_context.get("market_context_summary"),
                max_len=320,
            ),
            "scanner_linkage_summary": _build_market_scanner_linkage_bullet(market_context, scanner_reason),
        },
        "strategist_summary": strategist_summary,
        "strategist_refresh_trace": strategist_refresh_trace,
        "why_this_symbol_was_chosen": {
            "summary": _clip(scanner_choice_summary or scanner_reason.get("summary"), max_len=600),
            "bullets": _listify(why_symbol_bullets, max_items=16, max_len=260),
            "selected_rank": scanner_reason.get("selected_rank"),
            "universe_size": scanner_reason.get("universe_size"),
            "symbol": _clip(scanner_reason.get("selected_symbol") or story_input.get("symbol"), max_len=32),
            "basis": _scanner_basis_text(scanner_reason),
            "strategist_candidate_hints": _listify(
                market_context.get("candidate_hints") or strategist_evidence.get("candidate_hints"), max_items=8, max_len=24
            ),
            "scanner_selection_trace": effective_scanner_selection_trace,
            "news_scanner_contribution": news_scanner_contribution,
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
            "summary": scanner_filters_summary,
            "bullets": scanner_filters_bullets,
        },
        "guard_approval_result": {
            "summary": (
                _clip(guard_reason.get("summary"), max_len=600)
                or _clip(guard_approval_seed.get("summary"), max_len=600)
            ),
            "bullets": (
                _listify(guard_reason.get("bullets"), max_items=8, max_len=260)
                or _listify(guard_approval_seed.get("bullets"), max_items=8, max_len=260)
            ),
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
            "summary": (
                _clip(operator_conclusion.get("summary"), max_len=600)
                or _clip(final_operator_conclusion_seed.get("summary"), max_len=600)
                or executive_reason
            ),
            "current_action": (
                _clip(operator_conclusion.get("current_action"), max_len=24)
                or _clip(final_operator_conclusion_seed.get("current_action"), max_len=24)
                or action
            ),
            "watch_next": (
                _listify(operator_conclusion.get("watch_next"), max_items=6, max_len=200)
                or _listify(final_operator_conclusion_seed.get("watch_next"), max_items=6, max_len=200)
            ),
            "thesis_invalidation": (
                _listify(operator_conclusion.get("thesis_invalidation"), max_items=6, max_len=200)
                or _listify(final_operator_conclusion_seed.get("thesis_invalidation"), max_items=6, max_len=200)
            ),
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
            "broker_fee": shared_seed.get("broker_fee"),
            "broker_tax": shared_seed.get("broker_tax"),
            "pnl_truth_source": _clip(shared_seed.get("pnl_truth_source"), max_len=80) or "unavailable",
            "broker_day_truth_source": _clip(shared_seed.get("broker_day_truth_source"), max_len=80) or "",
            "broker_day_match_mode": _clip(shared_seed.get("broker_day_match_mode"), max_len=40) or "",
            "broker_day_authoritative": bool(shared_seed.get("broker_day_authoritative")),
            "broker_day_row_count": shared_seed.get("broker_day_row_count"),
            "broker_truth_attempted": bool(shared_seed.get("broker_truth_attempted")),
            "broker_truth_error": _clip(shared_seed.get("broker_truth_error"), max_len=240) or "",
            "broker_day_truth_attempted": bool(shared_seed.get("broker_day_truth_attempted")),
            "broker_day_truth_error": _clip(shared_seed.get("broker_day_truth_error"), max_len=240) or "",
            "broker_fill_price": shared_seed.get("broker_fill_price"),
            "broker_buy_price": shared_seed.get("broker_buy_price"),
            "account_mark_price": shared_seed.get("account_mark_price"),
            "monitor_mark_price": shared_seed.get("monitor_mark_price"),
            "price_truth_source": _clip(shared_seed.get("price_truth_source"), max_len=40) or "unavailable",
            "monitor_price_source": _clip(shared_seed.get("monitor_price_source"), max_len=120) or "unavailable",
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
    out["truth_surface"] = build_trade_report_truth_surface(out.get("shared_facts"))
    out["memory_surface"] = memory_surface
    out["memory_application_surface"] = build_trade_memory_application_surface(story_input)
    strategist_output = _compact_strategist_report_context(story_input)
    if strategist_output:
        out["strategist_output"] = strategist_output
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
        "strategist_summary": {
            "summary": "AI generation failed before a rendered strategist-summary section was produced.",
            "bullets": [],
        },
        "strategist_refresh_trace": _build_report_strategist_refresh_trace(story_input),
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
    from libs.agent.reporter import run_reporter_agent

    try:
        trade_model = build_trade_read_model(str(trade_dir))
    except Exception:
        trade_model = {}
    chosen_model = _resolve_intraday_report_model(trade_model, explicit_model=model)
    execution_profile = _resolve_intraday_report_execution_profile(
        trade_model if isinstance(trade_model, dict) else {}
    )
    agent_out = run_reporter_agent(
        str(trade_dir),
        policy={
            "model": chosen_model,
            "execution_profile": execution_profile,
        },
    )
    agent_status = str(agent_out.get("status") or "").strip().lower()
    narrative_obj = agent_out.get("narrative") if isinstance(agent_out.get("narrative"), dict) else {}
    narrative_reason = str(narrative_obj.get("reason") or "").strip().lower()
    degraded_for_contract = (
        agent_status == "degraded"
        and (
            narrative_reason.startswith("trade_read_model_")
            or not isinstance(agent_out.get("facts"), dict)
            or not isinstance(agent_out.get("provenance"), dict)
        )
    )
    if degraded_for_contract:
        return build_separated_report(
            trade_model=trade_model,
            model=chosen_model,
            execution_profile=execution_profile,
        )

    facts = agent_out.get("facts") if isinstance(agent_out.get("facts"), dict) else {}
    provenance = agent_out.get("provenance") if isinstance(agent_out.get("provenance"), dict) else {}
    context = agent_out.get("context") if isinstance(agent_out.get("context"), dict) else {}
    narrative = narrative_obj
    trade_fact_payload: Dict[str, Any] = dict(facts)
    trade_fact_payload.setdefault("facts", dict(facts))
    trade_fact_payload.setdefault("provenance", dict(provenance))
    trade_fact_payload.setdefault("context", dict(context))
    return {
        "fact_payload": {
            "trade": trade_fact_payload,
            "daily": {},
            "symbol": {},
        },
        "narrative": dict(narrative),
        "reporter_agent": {
            "status": str(agent_out.get("status") or ""),
            "metadata": dict(agent_out.get("metadata") or {}),
        },
    }


def _build_skipped_separated_report(trade_model: Dict[str, Any], *, reason: str) -> Dict[str, Any]:
    from libs.reporting.fact_narrative_report import build_fact_payload

    return {
        "fact_payload": build_fact_payload(trade_model=trade_model),
        "narrative": {
            "summary": "",
            "insight": "",
            "recommendation": "",
            "source": "llm",
            "based_on": "fact_payload",
            "status": "skipped",
            "reason": reason,
            "llm_call_skipped": True,
        },
    }


def _resolve_separated_trade_model(story_input: Dict[str, Any]) -> Dict[str, Any]:
    trade_model = _load_trade_read_model_hint(story_input)
    if isinstance(trade_model, dict) and trade_model:
        return trade_model
    return dict((story_input if isinstance(story_input, dict) else {}) or {})


def _load_trade_read_model_hint(story_input: Dict[str, Any]) -> Dict[str, Any]:
    from pathlib import Path
    from libs.reporting.trade_read_model import build_trade_read_model

    story_input_obj = story_input if isinstance(story_input, dict) else {}
    artifacts = story_input_obj.get("artifacts") if isinstance(story_input_obj.get("artifacts"), dict) else {}
    artifact_root = Path(str(artifacts.get("ai_trade_report_input_json") or ""))
    trade_root: Path | None = artifact_root.parent if artifact_root.name == "ai_trade_report_input.json" else None
    try:
        if trade_root is not None and trade_root.exists():
            trade_model = build_trade_read_model(str(trade_root))
            return trade_model if isinstance(trade_model, dict) else {}
    except Exception:
        pass
    return {}


def _trade_report_output_template() -> Dict[str, Any]:
    return {
        "executive_summary": {"headline": "", "summary": ""},
        "market_context_at_entry": {"summary": "", "bullets": [""]},
        "strategist_summary": {"summary": "", "bullets": [""]},
        "strategist_refresh_trace": {"summary": "", "bullets": [""], "stages": []},
        "why_this_symbol_was_chosen": {"summary": "", "bullets": [""]},
        "entry_decision": {"summary": "", "bullets": [""]},
        "holding_monitoring_story": {"summary": "", "bullets": [""]},
        "exit_decision": {"summary": "", "bullets": [""]},
        "execution_quality": {"summary": "", "bullets": [""]},
        "scanner_filters": {"summary": "", "bullets": [""]},
        "guard_approval_result": {"summary": "", "bullets": [""]},
        "reporter_evaluation": {"summary": "", "bullets": [""]},
        "errors_weaknesses_improvement_points": {"summary": "", "bullets": [""]},
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


def _build_concise_trade_report_messages(
    compact_input: Dict[str, Any],
    contract: Dict[str, Any],
    *,
    partial_note: str = "",
    previous_response_text: str = "",
    repair: bool = False,
    enforce_korean: bool = False,
) -> List[Dict[str, str]]:
    prompt_input = _prompt_story_input_for_llm(compact_input)
    mode_label = "복구 모드" if repair else "작성 모드"
    korean_note = ""
    if enforce_korean:
        korean_note = "\n최종 JSON을 반환하기 전에 남아 있는 영어 설명 문장을 모두 한국어로 번역하십시오."
    previous_note = ""
    if repair:
        previous_note = f"\n이전 응답:\n{previous_response_text}\n"
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 사후 거래 리포트 narrative editor입니다. "
                "반드시 JSON 객체 하나만 반환하십시오. 설명문, 사고 과정, markdown, code fence, 계획 문장은 절대 쓰지 마십시오. "
                "trade lifecycle retrospective만 작성하고, 숫자, 이벤트, 이유, evidence를 지어내지 마십시오. "
                f"{AI_TRADE_REPORT_KOREAN_RULES} "
                "값을 모르면 빈 문자열, 빈 리스트, null을 사용하십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{mode_label}: 아래 compact input과 출력 템플릿만 사용해 ai_trade_report narrative JSON을 작성하십시오.\n"
                "파이프라인 순서는 strategist -> scanner -> monitor -> supervisor -> executor -> reporter입니다.\n"
                "답해야 할 질문은 왜 진입했는가, 왜 보유했는가, 왜 청산했는가, 실행은 어땠는가, 다음에는 무엇을 개선할 것인가입니다.\n"
                "LLM은 전체 리포트/타임라인/메타데이터를 재생성하지 않습니다. 템플릿에 있는 narrative section만 채우십시오.\n"
                "영어 source 문장을 그대로 복사하지 마십시오. 사람이 읽는 문장은 한국어로 번역하십시오.\n"
                "selection_basis, runner_ups_lost, decision_reason_chain, monitor thresholds가 있으면 해당 섹션에 직접 반영하십시오.\n"
                "strategist_output이 있으면 strategy_thesis, strategy_refresh_trace, memory_usage_trace, news_usage_trace, scanner_handoff, monitor_handoff를 직접 사용하십시오.\n"
                "The strategist is not the final symbol selector; scanner/why_this_symbol_was_chosen owns selection_trace/rank/score.\n"
                "memory_usage_trace와 news_usage_trace는 메모리/뉴스 사용 설명의 기준입니다. 새 근거를 만들지 마십시오.\n"
                "strategy_refresh_trace가 있으면 1차 전략 프레임, 2차 후보 확정 후 refresh, 최종 적용 결과를 한 문단으로 합치지 말고 분리하십시오.\n"
                f"{partial_note}{korean_note}{previous_note}\n"
                "출력 템플릿:\n"
                f"{json.dumps(contract, ensure_ascii=False)}\n"
                "입력:\n"
                f"{json.dumps(prompt_input, ensure_ascii=False)}"
            ),
        },
    ]


def _prompt_story_input_for_llm(compact_input: Dict[str, Any]) -> Dict[str, Any]:
    data = compact_input if isinstance(compact_input, dict) else {}
    market = _as_dict(data.get("market_context"))
    commander = _as_dict(data.get("commander"))
    scanner = _as_dict(data.get("scanner"))
    monitor = _as_dict(data.get("monitor"))
    seeds = _as_dict(data.get("report_section_seeds"))
    return {
        "trade_id": data.get("trade_id"),
        "run_id": data.get("run_id"),
        "symbol": data.get("symbol"),
        "action": data.get("action"),
        "status": data.get("status"),
        "execution_mode_label": data.get("execution_mode_label"),
        "strategist_output": _as_dict(data.get("strategist_output")),
        "market_context": {
            "regime": market.get("regime"),
            "market_sentiment": market.get("market_sentiment"),
            "risk_mode": market.get("risk_mode"),
            "selected_playbook": market.get("selected_playbook"),
            "global_sentiment_score": market.get("global_sentiment_score"),
            "vix_level": market.get("vix_level"),
            "preferred_themes": _listify(market.get("preferred_themes"), max_items=3, max_len=60),
            "avoid_themes": _listify(market.get("avoid_themes"), max_items=3, max_len=60),
            "market_headlines": _listify(market.get("market_headlines"), max_items=2, max_len=140),
            "symbol_headlines": _listify(market.get("symbol_headlines"), max_items=2, max_len=140),
            "key_events": _listify(market.get("key_events"), max_items=2, max_len=140),
        },
        "commander": {
            "command_intent": commander.get("command_intent"),
            "selected_route": commander.get("selected_route"),
            "route_reason_text": commander.get("route_reason_text"),
            "policy_source": commander.get("policy_source"),
            "strategist_cache_used": commander.get("strategist_cache_used"),
            "strategist_called": commander.get("strategist_called"),
        },
        "entry": _as_dict(data.get("entry")),
        "scanner": {
            "selected_symbol": scanner.get("selected_symbol"),
            "selected_rank": scanner.get("selected_rank"),
            "universe_size": scanner.get("universe_size"),
            "ranking_basis": scanner.get("ranking_basis"),
            "playbook": scanner.get("playbook"),
            "policy_source": scanner.get("policy_source"),
            "confidence": scanner.get("confidence"),
            "top_reasons": _listify(scanner.get("top_reasons"), max_items=3, max_len=120),
            "why_selected": _listify(scanner.get("why_selected"), max_items=3, max_len=120),
            "selection_basis": scanner.get("selection_basis"),
            "selection_reason_with_bias": _clip(scanner.get("selection_reason_with_bias"), max_len=180),
            "runner_ups": _listify(scanner.get("runner_ups"), max_items=2, max_len=120),
            "runner_ups_lost": _listify(scanner.get("runner_ups_lost"), max_items=2, max_len=160),
            "selection_trace": {
                "ranked_candidates": _listify(
                    _as_dict(scanner.get("selection_trace")).get("ranked_candidates"),
                    max_items=3,
                    max_len=160,
                ),
                "selected_symbol": _as_dict(scanner.get("selection_trace")).get("selected_symbol"),
                "selected_rank": _as_dict(scanner.get("selection_trace")).get("selected_rank"),
                "selection_reason": _clip(_as_dict(scanner.get("selection_trace")).get("selection_reason"), max_len=180),
                "selected_symbol_score_drivers": _compact_scalar_dict(
                    _as_dict(scanner.get("selection_trace")).get("selected_symbol_score_drivers"),
                    max_items=5,
                    max_len=80,
                ),
            },
        },
        "holding": _as_dict(data.get("holding")),
        "monitor": {
            "posture": monitor.get("posture"),
            "trigger_type": monitor.get("trigger_type"),
            "summary": _clip(monitor.get("summary"), max_len=220),
            "entry_check_summary": _clip(monitor.get("entry_check_summary"), max_len=180),
            "entry_blockers": _listify(monitor.get("entry_blockers"), max_items=5, max_len=100),
            "threshold_shortfalls": _listify(monitor.get("threshold_shortfalls"), max_items=3, max_len=120),
            "decision_reason_chain": _listify(monitor.get("decision_reason_chain"), max_items=5, max_len=80),
            "confirm_required": monitor.get("confirm_required"),
            "confirm_count": monitor.get("confirm_count"),
            "effective_policy_deltas": _listify(monitor.get("effective_policy_deltas"), max_items=5, max_len=100),
            "position_age_seconds": monitor.get("position_age_seconds"),
            "effective_stop_loss_pct": monitor.get("effective_stop_loss_pct"),
            "take_profit_pct": monitor.get("take_profit_pct"),
            "trailing_stop_pct": monitor.get("trailing_stop_pct"),
            "current_price": monitor.get("current_price"),
            "average_price": monitor.get("average_price"),
            "peak_price": monitor.get("peak_price"),
            "current_drawdown": monitor.get("current_drawdown"),
            "active_exit_axis": monitor.get("active_exit_axis"),
            "watch_axes": _listify(monitor.get("watch_axes"), max_items=4, max_len=80),
            "price_source": monitor.get("price_source"),
            "monitor_stop_policy_trace": _compact_scalar_dict(monitor.get("monitor_stop_policy_trace"), max_items=6, max_len=80),
        },
        "exit": _as_dict(data.get("exit")),
        "guard": _as_dict(data.get("guard")),
        "execution": _as_dict(data.get("execution")),
        "reporter": _as_dict(data.get("reporter")),
        "operator_conclusion": _as_dict(data.get("operator_conclusion")),
        "section_seed_summaries": {
            key: _compact_section_seed_for_llm(value)
            for key, value in seeds.items()
            if key
        },
        "timeline": _listify(data.get("timeline"), max_items=4, max_len=180),
        "improvement_points": _listify(data.get("improvement_points"), max_items=4, max_len=120),
        "ai_report_diagnostics": _as_dict(data.get("ai_report_diagnostics")),
    }


def _build_repair_messages(
    story_input: Dict[str, Any],
    raw_response: Any,
    *,
    sparse: bool = False,
    enforce_korean: bool = False,
) -> List[Dict[str, str]]:
    compact_input = _sparse_story_input_for_llm(story_input)
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
    if sparse:
        shape_note = "\n마지막 복구 시도입니다. 각 summary는 2문장 이하, bullets는 1~3개만 작성하십시오."
    return _build_concise_trade_report_messages(
        compact_input,
        contract,
        partial_note=f"{partial_note}{shape_note}",
        previous_response_text=previous_response_text,
        repair=True,
        enforce_korean=enforce_korean,
    )
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
                "\n- If strategist_output is present, use strategy_thesis, strategy_refresh_trace, memory_usage_trace, news_usage_trace, scanner_handoff, and monitor_handoff as the strategist rationale directly.\n"
                "- The strategist is not the final symbol selector. Do not write that the strategist selected the final symbol.\n"
                "- Symbol-selection rationale belongs in scanner/why_this_symbol_was_chosen and must follow scanner selection_trace, score, and rank evidence.\n"
                "- memory_usage_trace and news_usage_trace are authoritative for memory/news usage. Do not invent new memory/news explanations in the report LLM.\n"
                "- strategy_refresh_trace is authoritative for 1st/base frame, 2nd/post-scanner refresh, and final application. Do not collapse these stages.\n"
                f"{partial_note}{shape_note}{language_note}\n\n"
                "원본 입력이 영어로 적혀 있어도 그대로 복사하지 말고 한국어로 옮겨 쓰십시오.\n"
                "핵심 evidence 규칙:\n"
                "- market_context_human에 headline_count, news_query_count, news_query_targets, key_events_hint가 있으면 market_context_at_entry에 반영하십시오.\n"
                "- strategist_summary에는 입력 -> 시장 해석 -> 스캐너 반영 -> 종목 연결 순서를 유지하십시오.\n"
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
        partial_note = "\n이 lifecycle은 partial 상태입니다. 확인되지 않은 진입/보유 근거를 새로 만들지 마십시오."
    return _build_concise_trade_report_messages(
        compact_input,
        contract,
        partial_note=partial_note,
    )
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
                "- strategist_summary에는 입력 -> 해석 -> 스캐너 반영 -> 종목 선택 순서로 정리하십시오.\n"
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
                "- strategist_output: use strategy_thesis, strategy_refresh_trace, memory_usage_trace, news_usage_trace, scanner_handoff, monitor_handoff directly.\n"
                "- strategy_refresh_trace가 있으면 1차 전략 프레임, 2차 후보 확정 후 refresh, 최종 적용 결과를 분리해 작성하십시오.\n"
                "- The strategist is not the final symbol selector; scanner/why_this_symbol_was_chosen owns selection_trace/rank/score.\n"
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
        separated_trade_model = _resolve_separated_trade_model(story_input)
        runtime_mode = str(story_input.get("report_runtime_mode") or "").strip().lower()
        enable_separated_narrative = bool(story_input.get("enable_separated_narrative"))
        skip_separated_report_llm = bool(story_input.get("skip_separated_report_llm"))
        try:
            if enable_separated_narrative and not skip_separated_report_llm:
                from libs.reporting.fact_narrative_report import build_separated_report

                separated = build_separated_report(
                    trade_model=dict(separated_trade_model or {}),
                    model=str(generation.get("model") or "").strip() or None,
                    execution_profile=_resolve_intraday_report_execution_profile(
                        dict(separated_trade_model or {})
                    ),
                )
            else:
                skip_reason = (
                    f"{runtime_mode or 'runtime'}_skip_separated_report_llm"
                    if skip_separated_report_llm
                    else f"{runtime_mode or 'runtime'}_separated_narrative_disabled"
                )
                separated = _build_skipped_separated_report(
                    dict(separated_trade_model or {}),
                    reason=skip_reason,
                )
        except Exception:
            separated = {
                "fact_payload": {"trade": dict(separated_trade_model or {}), "daily": {}, "symbol": {}},
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
    retry_max_override: Optional[int] = None,
    timeout_sec_override: Optional[float] = None,
    hard_timeout_sec_override: Optional[float] = None,
    local_debug_no_llm: bool = False,
) -> Dict[str, Any]:
    if enabled is None:
        applied_policy = story_input.get("applied_policy") if isinstance(story_input.get("applied_policy"), dict) else {}
        reporter_policy = applied_policy.get("reporter") if isinstance(applied_policy.get("reporter"), dict) else {}
        trade_report_policy = reporter_policy.get("trade_report") if isinstance(reporter_policy.get("trade_report"), dict) else {}
        commander = story_input.get("commander") if isinstance(story_input.get("commander"), dict) else {}
        commander_policy = commander.get("applied_policy") if isinstance(commander.get("applied_policy"), dict) else {}
        commander_reporter = commander_policy.get("reporter") if isinstance(commander_policy.get("reporter"), dict) else {}
        commander_trade_report = (
            commander_reporter.get("trade_report")
            if isinstance(commander_reporter.get("trade_report"), dict)
            else {}
        )
        reporter_fallback = story_input.get("reporter_policy") if isinstance(story_input.get("reporter_policy"), dict) else {}
        trade_report_fallback = (
            reporter_fallback.get("trade_report")
            if isinstance(reporter_fallback.get("trade_report"), dict)
            else {}
        )
        if trade_report_policy.get("enabled") is not None:
            is_enabled = bool(trade_report_policy.get("enabled"))
        elif commander_trade_report.get("enabled") is not None:
            is_enabled = bool(commander_trade_report.get("enabled"))
        elif trade_report_fallback.get("enabled") is not None:
            is_enabled = bool(trade_report_fallback.get("enabled"))
        else:
            is_enabled = True
    else:
        is_enabled = bool(enabled)
    chosen_model = _resolve_intraday_report_model(story_input, explicit_model=model)
    execution_profile = _resolve_intraday_report_execution_profile(story_input)
    trade_id = str(story_input.get("trade_id") or story_input.get("story_id") or "")
    run_id = str(story_input.get("run_id") or "")
    day = str(story_input.get("day") or "")
    env_retry_fallback = str(os.getenv("TRADE_REPORT_AI_RETRY_MAX", "") or "").strip()
    execution_slot_source = str(execution_profile.get("policy_source") or "").strip().lower()
    if retry_max_override is not None:
        retry_max = max(0, int(float(retry_max_override)))
        execution_profile_source = "explicit_override"
    elif execution_slot_source not in {"", "default_execution_profile", "default"}:
        retry_max = max(0, int(float(execution_profile.get("retry_max") or 0)))
        execution_profile_source = "applied_policy"
    elif env_retry_fallback:
        retry_max = max(0, int(float(env_retry_fallback or "2")))
        execution_profile_source = "fallback_env"
    elif execution_slot_source in {"", "default_execution_profile", "default"}:
        retry_max = max(0, int(float(os.getenv("TRADE_REPORT_AI_DEFAULT_RETRY_MAX", "1") or "1")))
        execution_profile_source = "default"
    else:
        retry_max = max(0, int(float(execution_profile.get("retry_max") or 2)))
        execution_profile_source = "default"
    execution_observability = build_execution_profile_observability(
        execution_profile,
        env_used=(execution_profile_source == "fallback_env"),
    )
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
            reason="reporter.trade_report.enabled is false",
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
            meta={"reason": "reporter.trade_report.enabled is false", **empty_required_meta, **build_execution_profile_observability(execution_profile, env_used=(execution_profile_source == "fallback_env"))},
        )
        return _attach_report_status_matrix(report, story_input, ai_trade_report_status="skipped")

    temp = float(
        temperature
        if temperature is not None
        else execution_profile.get("temperature") or 0.2
    )
    if max_tokens is not None:
        token_budget = int(max_tokens)
    else:
        profile_token_budget = max(600, int(float(execution_profile.get("max_tokens") or 8192)))
        if execution_slot_source in {"", "default_execution_profile", "default"}:
            default_cap = max(600, int(float(os.getenv("TRADE_REPORT_AI_DEFAULT_MAX_TOKENS", "3072") or "3072")))
            token_budget = min(profile_token_budget, default_cap)
        else:
            token_budget = profile_token_budget
    timeout_sec = max(
        1.0,
        float(timeout_sec_override if timeout_sec_override is not None else execution_profile.get("timeout_sec") or 15.0),
    )
    hard_timeout_sec = (
        max(0.1, float(hard_timeout_sec_override))
        if hard_timeout_sec_override not in (None, "", 0)
        else None
    )
    retry_backoff_sec = max(0.0, float(execution_profile.get("retry_backoff_sec") or 0.0))
    execution_observability = build_execution_profile_observability(
        execution_profile,
        env_used=(execution_profile_source == "fallback_env"),
        effective_overrides={
            "temperature": float(temp),
            "max_tokens": int(max(600, token_budget)),
            "timeout_sec": float(timeout_sec),
            "hard_timeout_sec": float(hard_timeout_sec) if hard_timeout_sec is not None else None,
            "retry": {
                "max_attempts": int(retry_max),
                "backoff_sec": float(retry_backoff_sec),
            },
        },
    )
    if local_debug_no_llm:
        report = _fallback_report(
            story_input,
            status="ok",
            mode="local_debug",
            model=chosen_model,
            reason="local_debug_no_llm",
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
            meta={"reason": "local_debug_no_llm", **empty_required_meta, **execution_observability},
        )
        return _attach_report_status_matrix(
            report,
            story_input,
            ai_trade_report_status="skipped",
            deterministic_report_status="ok",
        )

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
            meta={"reason": "OPENROUTER_API_KEY is not configured", "error": "llm_client_unavailable", **empty_required_meta, **execution_observability},
        )
        return _attach_report_status_matrix(report, story_input, ai_trade_report_status="error")

    retry_token_budget = max(800, token_budget)
    messages = _build_messages(story_input)
    attempts: List[Dict[str, Any]] = []
    resolved_model = str(
        router.resolve(
            "trade_report",
            policy={
                "temperature": temp,
                "max_tokens": max(600, token_budget),
                "timeout_sec": float(timeout_sec),
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
        "timeout_sec": float(timeout_sec),
        "response_format": {"type": "json_object"},
        "plugins": [{"id": "response-healing"}],
        **({"model": chosen_model} if chosen_model else {}),
    }
    for attempt_index in range(retry_max + 1):
        step = "primary" if attempt_index == 0 else f"retry_{attempt_index}"
        needs_korean_repair = False
        t0 = time.perf_counter()
        try:
            raw = _router_chat_with_hard_timeout(
                router,
                "trade_report",
                current_messages,
                policy=current_policy,
                hard_timeout_sec=hard_timeout_sec,
            )
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
                    meta={"role": "ai_trade_report", "error": final_error, **execution_observability},
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
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
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
                            meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
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
                            meta={"role": "ai_trade_report", **parse_meta, **language_meta, **execution_observability},
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
                            meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
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
                                **execution_observability,
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
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
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
                        meta={"role": "ai_trade_report", "error": final_reason, **parse_meta, **language_meta, **execution_observability},
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
            if retry_backoff_sec > 0.0:
                time.sleep(float(retry_backoff_sec))

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
                **execution_observability,
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
            meta={"reason": final_reason, "error": final_error, **empty_required_meta, **execution_observability},
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
            **execution_observability,
        },
    )
    return _attach_report_status_matrix(out, story_input, ai_trade_report_status=final_status)


def render_trade_report_markdown(report: Dict[str, Any]) -> str:
    from libs.reporting.trade_report_markdown_clean import render_trade_report_markdown_clean

    return render_trade_report_markdown_clean(report)


def build_trade_summary_input(report: Dict[str, Any]) -> Dict[str, Any]:
    from libs.reporting.trade_report_markdown_clean import build_trade_summary_input_clean

    return build_trade_summary_input_clean(report)


AI_TRADE_SUMMARY_EVALUATION_KEYS = (
    "conclusion",
    "root_cause",
    "priority_actions",
    "risk_notes",
    "validation_questions",
)


def _trade_summary_evaluation_template() -> Dict[str, Any]:
    return {
        "conclusion": "",
        "root_cause": "",
        "priority_actions": [],
        "risk_notes": [],
        "validation_questions": [],
    }


def _normalize_trade_summary_evaluation(value: Any) -> Dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    if isinstance(payload.get("llm_evaluation"), dict):
        payload = dict(payload.get("llm_evaluation") or {})
    out = _trade_summary_evaluation_template()
    out["conclusion"] = _clip(payload.get("conclusion"), max_len=420)
    out["root_cause"] = _clip(payload.get("root_cause"), max_len=520)
    out["priority_actions"] = _listify(payload.get("priority_actions"), max_items=5, max_len=180)
    out["risk_notes"] = _listify(payload.get("risk_notes"), max_items=5, max_len=180)
    out["validation_questions"] = _listify(payload.get("validation_questions"), max_items=5, max_len=180)
    return out


def _trade_summary_parse_meta(raw_response: Any, candidate: Dict[str, Any]) -> Dict[str, Any]:
    evaluation = candidate.get("llm_evaluation") if isinstance(candidate.get("llm_evaluation"), dict) else candidate
    evaluation = evaluation if isinstance(evaluation, dict) else {}
    present = [key for key in AI_TRADE_SUMMARY_EVALUATION_KEYS if key in evaluation]
    missing = [key for key in AI_TRADE_SUMMARY_EVALUATION_KEYS if key not in evaluation]
    return {
        "parse_mode": "json",
        "required_keys_expected": list(AI_TRADE_SUMMARY_EVALUATION_KEYS),
        "required_keys_present": present,
        "required_keys_missing": missing,
        "completeness_score": float(len(present)) / float(len(AI_TRADE_SUMMARY_EVALUATION_KEYS)),
        "raw_char_count": len(str(raw_response or "")),
    }


def _build_trade_summary_evaluation_messages(
    summary_input: Dict[str, Any],
    *,
    previous_response_text: str = "",
    repair: bool = False,
) -> List[Dict[str, str]]:
    mode_label = "복구 모드" if repair else "작성 모드"
    previous_note = f"\n이전 응답:\n{previous_response_text}\n" if repair else ""
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 운영 요약 평가자입니다. "
                "반드시 JSON 객체 하나만 반환하십시오. markdown, code fence, 설명문, 사고 과정은 금지합니다. "
                "가격, 손익, 수수료, 세금, 체결 사실, 순위, 점수는 절대 만들거나 수정하지 마십시오. "
                "모든 판단은 제공된 ai_trade_summary_input 안의 사실로만 제한하십시오. "
                "체결가, 매수가, 매도가, 실현손익, 수수료, 세금은 truth_surface만 정답으로 사용하십시오. "
                "decision_flow.exit_observation은 모니터 신호 판단용 스냅샷일 뿐이며 체결가나 실현손익으로 해석하지 마십시오. "
                "post_exit_shadow는 매도 후 가격 관측-only 근거이며 보유 연장 규칙이 이미 바뀐 것으로 해석하지 마십시오. "
                "deterministic_findings는 확정 원인이 아니라 검증 후보로 다루십시오. "
                "root_cause_candidates, deterministic_findings, decision_flow 같은 내부 키 이름을 출력문에 그대로 쓰지 마십시오. "
                "종목명은 trade.symbol을 그대로 사용하고 00번.symbol 같은 placeholder를 만들지 마십시오. "
                "한국어만 사용하고 일본어/중국어 조각이나 번역되지 않은 문장을 남기지 마십시오. "
                f"{AI_TRADE_REPORT_KOREAN_RULES} "
                "근거가 약하면 단정하지 말고 검증 필요라고 쓰십시오."
            ),
        },
        {
            "role": "user",
            "content": (
                f"{mode_label}: 아래 ai_trade_summary_input만 사용해서 llm_evaluation JSON을 작성하십시오.\n"
                "출력 필드는 conclusion, root_cause, priority_actions, risk_notes, validation_questions 다섯 개뿐입니다.\n"
                "conclusion은 운영자가 바로 볼 수 있게 종목, 결과, 핵심 운영 판단을 한두 문장으로 요약하십시오.\n"
                "root_cause는 확정 사실과 검증 후보를 구분하고, 입력에 있는 정책/선정/청산 근거로만 제한하십시오.\n"
                "priority_actions는 다음 검증 또는 패치 우선순위이며 실행 가능한 문장으로 쓰십시오.\n"
                "risk_notes는 이 거래를 해석할 때 조심해야 할 점이며 과잉 일반화를 막는 문장으로 쓰십시오.\n"
                "validation_questions는 다음 라이브 검증에서 확인할 질문이며 물음표로 끝내십시오.\n"
                "청산 관련 가격을 언급할 때는 Truth Surface 기준과 모니터 관측값 기준을 반드시 구분하십시오.\n"
                "post_exit_shadow를 언급할 때는 관측-only, 표본 부족, 행동 변경 금지를 함께 전제하십시오.\n"
                "출력 템플릿:\n"
                f"{json.dumps(_trade_summary_evaluation_template(), ensure_ascii=False)}\n"
                "입력:\n"
                f"{json.dumps(summary_input, ensure_ascii=False)}"
                f"{previous_note}"
            ),
        },
    ]


def _deterministic_trade_summary_report(
    summary_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
    evaluation: Dict[str, Any] | None = None,
    llm_response_artifact: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    trade = _as_dict(summary_input.get("trade"))
    out = {
        "schema_version": "ai_trade_summary.v1",
        "artifact_type": "ai_trade_summary",
        "source_artifact": "ai_trade_summary_input.json",
        "trade": trade,
        "truth_surface": _as_dict(summary_input.get("truth_surface")),
        "same_day_context": _as_dict(summary_input.get("same_day_context")),
        "market_and_strategy": _as_dict(summary_input.get("market_and_strategy")),
        "decision_flow": _as_dict(summary_input.get("decision_flow")),
        "memory_and_policy": _as_dict(summary_input.get("memory_and_policy")),
        "deterministic_findings": _as_dict(summary_input.get("deterministic_findings")),
        "llm_evaluation": _normalize_trade_summary_evaluation(evaluation or {}),
        "generation": {
            "status": str(status or ""),
            "mode": str(mode or ""),
            "model": str(model or ""),
            "reason": str(reason or ""),
        },
        "summary_status": str(status or ""),
    }
    if llm_response_artifact:
        out["llm_response_artifact"] = dict(llm_response_artifact)
    return out


def build_trade_summary_report(
    summary_input: Dict[str, Any],
    *,
    enabled: bool = False,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    retry_max_override: Optional[int] = None,
    timeout_sec_override: Optional[float] = None,
    hard_timeout_sec_override: Optional[float] = None,
    local_debug_no_llm: bool = False,
) -> Dict[str, Any]:
    source = summary_input if isinstance(summary_input, dict) else {}
    trade = _as_dict(source.get("trade"))
    trade_id = str(trade.get("trade_id") or source.get("trade_id") or "")
    run_id = str(source.get("run_id") or "")
    day = str(trade.get("day") or source.get("day") or "")
    chosen_model = _resolve_intraday_report_model(source, explicit_model=model)
    temp = float(temperature if temperature is not None else 0.1)
    token_budget = int(max_tokens if max_tokens is not None else 1200)
    retry_max = int(retry_max_override if retry_max_override is not None else 1)
    timeout_sec = float(timeout_sec_override if timeout_sec_override is not None else 12.0)
    hard_timeout_sec = (
        max(0.1, float(hard_timeout_sec_override))
        if hard_timeout_sec_override not in (None, "", 0)
        else None
    )
    empty_meta = {
        "parse_mode": "none",
        "required_keys_expected": list(AI_TRADE_SUMMARY_EVALUATION_KEYS),
        "required_keys_present": [],
        "required_keys_missing": list(AI_TRADE_SUMMARY_EVALUATION_KEYS),
        "completeness_score": 0.0,
    }
    if not enabled or local_debug_no_llm:
        reason = "local_debug_no_llm" if local_debug_no_llm else "summary_llm_disabled"
        artifact = build_llm_response_artifact(
            component="ai_trade_summary",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status="fallback",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or "openrouter/free"},
            meta={"reason": reason, **empty_meta},
        )
        return _deterministic_trade_summary_report(
            source,
            status="skipped",
            mode="local_debug" if local_debug_no_llm else "deterministic",
            model=chosen_model,
            reason=reason,
            llm_response_artifact=artifact,
        )

    router = LLMRouter.from_env()
    if router.client is None:
        artifact = build_llm_response_artifact(
            component="ai_trade_summary",
            run_id=run_id,
            trade_id=trade_id,
            story_id=trade_id,
            day=day,
            status="error",
            attempts=[],
            parsed_output={},
            model_info={"provider": "OpenRouter", "model": chosen_model or "openrouter/free"},
            meta={"reason": "OPENROUTER_API_KEY is not configured", "error": "llm_client_unavailable", **empty_meta},
        )
        return _deterministic_trade_summary_report(
            source,
            status="error",
            mode="ai",
            model=chosen_model,
            reason="OPENROUTER_API_KEY is not configured",
            llm_response_artifact=artifact,
        )

    resolved_model = str(
        router.resolve(
            "trade_report",
            policy={
                "temperature": temp,
                "max_tokens": max(600, token_budget),
                "timeout_sec": timeout_sec,
                **({"model": chosen_model} if chosen_model else {}),
            },
        ).model
    )
    attempts: List[Dict[str, Any]] = []
    current_messages = _build_trade_summary_evaluation_messages(source)
    current_policy = {
        "temperature": temp,
        "max_tokens": max(600, token_budget),
        "timeout_sec": timeout_sec,
        "response_format": {"type": "json_object"},
        **({"model": chosen_model} if chosen_model else {}),
    }
    raw = ""
    parsed_eval: Dict[str, Any] = {}
    final_status = "error"
    final_reason = ""
    final_error = ""
    final_latency_ms = 0
    parse_meta = dict(empty_meta)
    for attempt_index in range(max(0, retry_max) + 1):
        step = "primary" if attempt_index == 0 else f"retry_{attempt_index}"
        t0 = time.perf_counter()
        try:
            raw = _router_chat_with_hard_timeout(
                router,
                "trade_report",
                current_messages,
                policy=current_policy,
                hard_timeout_sec=hard_timeout_sec,
            )
        except Exception as exc:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            final_status = classify_llm_exception(exc)
            final_error = f"{type(exc).__name__}:{exc}"
            final_reason = f"trade_summary_ai_exception:{final_error}"
            attempts.append(
                make_attempt(
                    step=step,
                    messages=current_messages,
                    raw_response_text=f"ERROR:{final_error}",
                    parsed_output={},
                    model=chosen_model or resolved_model,
                    latency_ms=final_latency_ms,
                    status=final_status,
                    meta={"role": "ai_trade_summary", "error": final_error, **empty_meta},
                )
            )
        else:
            final_latency_ms = int((time.perf_counter() - t0) * 1000)
            parse_result = parse_llm_json_response(raw)
            candidate = parse_result.get("full_object") if isinstance(parse_result.get("full_object"), dict) else parse_result.get("partial_object")
            candidate = dict(candidate) if isinstance(candidate, dict) else {}
            parse_meta = _trade_summary_parse_meta(raw, candidate) if candidate else dict(empty_meta)
            evaluation = _normalize_trade_summary_evaluation(candidate)
            missing = list(parse_meta.get("required_keys_missing") or [])
            if candidate and not missing:
                parsed_eval = evaluation
                final_status = "ok"
                final_reason = ""
                attempts.append(
                    make_attempt(
                        step=step,
                        messages=current_messages,
                        raw_response_text=raw,
                        parsed_output=evaluation,
                        model=chosen_model or resolved_model,
                        latency_ms=final_latency_ms,
                        status="ok",
                        meta={"role": "ai_trade_summary", **parse_meta},
                    )
                )
                break
            final_status = "partial" if candidate else "parse_error"
            final_reason = (
                f"trade_summary_ai response is missing required keys: {', '.join(missing)}"
                if candidate
                else "trade_summary_ai returned non-JSON response"
            )
            attempts.append(
                make_attempt(
                    step=step,
                    messages=current_messages,
                    raw_response_text=raw,
                    parsed_output=evaluation if candidate else {},
                    model=chosen_model or resolved_model,
                    latency_ms=final_latency_ms,
                    status=final_status,
                    meta={"role": "ai_trade_summary", "error": final_reason, **parse_meta},
                )
            )
        if attempt_index < retry_max:
            current_messages = _build_trade_summary_evaluation_messages(
                source,
                previous_response_text=raw[:1800],
                repair=True,
            )
            current_policy = {**current_policy, "temperature": 0.0}

    artifact = build_llm_response_artifact(
        component="ai_trade_summary",
        run_id=run_id,
        trade_id=trade_id,
        story_id=trade_id,
        day=day,
        status=final_status,
        attempts=attempts,
        parsed_output=parsed_eval,
        model_info={"provider": "OpenRouter", "model": chosen_model or resolved_model},
        latency_ms=sum(int(row.get("latency_ms") or 0) for row in attempts),
        meta={"reason": final_reason, "error": final_error, **parse_meta},
    )
    return _deterministic_trade_summary_report(
        source,
        status=final_status,
        mode="ai",
        model=chosen_model or resolved_model,
        reason=final_reason,
        evaluation=parsed_eval,
        llm_response_artifact=artifact,
    )


def render_trade_summary_markdown(report: Dict[str, Any]) -> str:
    from libs.reporting.trade_report_markdown_clean import render_trade_summary_markdown_clean

    return render_trade_summary_markdown_clean(report)


def render_trade_summary_markdown_with_evaluation(
    report: Dict[str, Any],
    summary_report: Dict[str, Any],
) -> str:
    from libs.reporting.trade_report_markdown_clean import render_trade_summary_markdown_with_evaluation_clean

    return render_trade_summary_markdown_with_evaluation_clean(report, summary_report)

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
            "reporter linkage was not available yet.": "리포터 연계 결과는 아직 연결되지 않았습니다.",
            "reporter linkage status was recorded separately.": "리포터 연계 상태는 별도 메타에 기록되어 있습니다.",
            "the decision path was recorded, but the operator-facing summary is limited.": "의사결정 경로는 기록되었지만 운영자용 요약은 제한적으로만 남아 있습니다.",
            "no timeline entries were captured.": "타임라인 이벤트는 별도로 저장되지 않았습니다.",
            "open trade": "아직 포지션이 열린 상태입니다.",
            "hold": "현재 포지션은 계속 보유 중입니다.",
        }
        if lowered in exact_mapping:
            return exact_mapping[lowered]

        m = _safe_fullmatch(r"Monitor runs:\s*(\d+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"모니터 실행 횟수는 {m.group(1)}회였습니다."
        m = _safe_fullmatch(r"Posture:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재 포지션 판단은 {_action_label(m.group(1))}입니다."
        m = _safe_fullmatch(r"Trigger type:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"감지된 신호 유형은 {_axis_label(m.group(1))}입니다."
        m = _safe_fullmatch(r"Position age:\s*(\d+)\s*seconds", cleaned, flags=re.IGNORECASE)
        if m:
            return f"포지션 유지 시간은 약 {m.group(1)}초입니다."
        m = _safe_fullmatch(r"Effective stop:\s*([^(]+?)(?:\s*\((.+)\))?", cleaned, flags=re.IGNORECASE)
        if m:
            level = _clip(m.group(1), max_len=64)
            reason = _axis_label(m.group(2))
            if reason and reason != "-":
                return f"유효 손절 기준은 {level} 수준이며, 기준 축은 {reason}입니다."
            return f"유효 손절 기준은 {level} 수준입니다."
        m = _safe_fullmatch(r"Take profit:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"목표 수익 실현 기준은 {_clip(m.group(1), max_len=80)} 수준입니다."
        m = _safe_fullmatch(r"Active exit axis:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재 우선 감시 중인 청산 축은 {_axis_label(m.group(1))}입니다."
        m = _safe_fullmatch(r"Exit confirmation:\s*(\d+)/(\d+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 확인 조건은 {m.group(1)}/{m.group(2)} 수준으로 집계됐습니다."
        m = _safe_fullmatch(r"Watch axes:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            axes = ", ".join(_axis_label(part.strip()) for part in m.group(1).split(","))
            return f"주요 감시 축은 {axes}입니다."
        m = _safe_fullmatch(r"Decision chain:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"판단 흐름은 {_clip(m.group(1), max_len=200)} 순서로 이어졌습니다."
        m = _safe_fullmatch(r"Current price / avg / peak:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재가, 평균단가, 장중 고점은 {_clip(m.group(1), max_len=180)}입니다."
        m = _safe_fullmatch(r"Current drawdown / peak drawdown:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"현재 손익 변동과 고점 대비 하락폭은 {_clip(m.group(1), max_len=180)}입니다."
        m = _safe_fullmatch(r"Price source:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"가격 기준 소스는 {_clip(m.group(1), max_len=120)}입니다."
        m = _safe_fullmatch(r"Feature source:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"피처 기준 소스는 {_clip(m.group(1), max_len=120)}입니다."
        m = _safe_fullmatch(r"Recent monitor update:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"최근 모니터 업데이트는 다음과 같습니다: {_clip(m.group(1), max_len=240)}"
        m = _safe_fullmatch(r"Exit run:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 판단은 {_clip(m.group(1), max_len=120)} run에서 기록되었습니다."
        m = _safe_fullmatch(r"Exit time:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 판단 시각은 {_clip(m.group(1), max_len=120)}입니다."
        m = _safe_fullmatch(r"Exit action:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 액션은 {_action_label(m.group(1))}로 기록되었습니다."
        m = _safe_fullmatch(r"Exit reason:\s*(.+)", cleaned, flags=re.IGNORECASE)
        if m:
            return f"청산 사유는 {_clip(m.group(1), max_len=240)}입니다."
        return _normalize_trade_report_language(cleaned)

    def _section_title(title: str) -> str:
        mapping = {
            "Executive Summary": "최종 판단 요약",
            "Market Context at Entry": "시장 환경 요약",
            "Strategist Summary": "전략가 요약",
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
    strategist_summary = report.get("strategist_summary") if isinstance(report.get("strategist_summary"), dict) else {}
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
    execution_result = dict(execution_result or {})
    reporter_eval = report.get("reporter_evaluation") if isinstance(report.get("reporter_evaluation"), dict) else {}
    weak_points = (
        report.get("errors_weaknesses_improvement_points")
        if isinstance(report.get("errors_weaknesses_improvement_points"), dict)
        else {}
    )
    final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}
    monitor_snapshot = report.get("monitor_snapshot") if isinstance(report.get("monitor_snapshot"), dict) else {}
    shared_facts = report.get("shared_facts") if isinstance(report.get("shared_facts"), dict) else {}
    truth_surface = (
        report.get("truth_surface")
        if isinstance(report.get("truth_surface"), dict)
        else build_trade_report_truth_surface(shared_facts)
    )
    memory_surface = report.get("memory_surface") if isinstance(report.get("memory_surface"), dict) else {}
    closed_trade = str(report.get("status") or "").strip().lower() == "closed"


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
    truth_price = truth_surface.get("price") if isinstance(truth_surface.get("price"), dict) else {}
    truth_pnl = truth_surface.get("pnl") if isinstance(truth_surface.get("pnl"), dict) else {}
    truth_availability = truth_surface.get("availability") if isinstance(truth_surface.get("availability"), dict) else {}
    if truth_surface:
        lines.append("## Truth Surface")
        lines.append("")
        price_truth_source = _clip(truth_price.get("price_truth_source"), max_len=40)
        monitor_price_source = _clip(truth_price.get("monitor_price_source"), max_len=80)
        pnl_truth_source = _clip(truth_pnl.get("pnl_truth_source"), max_len=80)
        if truth_price.get("broker_buy_price") not in (None, "") and truth_price.get("broker_fill_price") not in (None, ""):
            lines.append(
                f"- 브로커 매수가/매도가는 {_fmt_price(truth_price.get('broker_buy_price'))} / {_fmt_price(truth_price.get('broker_fill_price'))}입니다."
            )
        elif truth_price.get("broker_fill_price") not in (None, ""):
            lines.append(f"- 브로커 체결 가격은 {_fmt_price(truth_price.get('broker_fill_price'))}입니다.")
            if bool(truth_pnl.get("broker_day_authoritative")) and truth_pnl.get("broker_day_truth_source") and truth_price.get("broker_buy_price") in (None, ""):
                lines.append("- 브로커 매수 체결가는 직접 복구되지 않았고, 확정 손익은 키움 당일 실현손익 기준으로만 확인했습니다.")
        if truth_price.get("account_mark_price") not in (None, ""):
            lines.append(f"- 계좌 기준 마크 가격은 {_fmt_price(truth_price.get('account_mark_price'))}입니다.")
        if truth_price.get("monitor_mark_price") not in (None, "") and truth_price.get("broker_fill_price") in (None, ""):
            lines.append(f"- 종료 직전 모니터 관측 가격은 {_fmt_price(truth_price.get('monitor_mark_price'))}입니다.")
        if str(truth_pnl.get("value") or "").strip().lower() in {"", "unavailable", "not_available"}:
            if truth_pnl.get("pct") not in (None, ""):
                if pnl_truth_source == "broker_fill_account_snapshot_estimate":
                    lines.append(f"- 브로커 확정 손익 금액은 직접 확인되지 않았고, 브로커 체결가와 계좌 평가손익 기준 추정 손익률은 {_fmt_pct(truth_pnl.get('pct'))}입니다.")
                else:
                    lines.append(f"- 브로커 확정 손익 금액은 직접 확인되지 않았고, 손익률은 {_fmt_pct(truth_pnl.get('pct'))}입니다.")
            else:
                lines.append("- 브로커 확정 손익은 아직 직접 확인되지 않았습니다.")
        elif truth_pnl.get("value") not in (None, "") and truth_pnl.get("pct") not in (None, ""):
            lines.append(f"- 확정 손익은 {truth_pnl.get('value')} / {_fmt_pct(truth_pnl.get('pct'))}입니다.")
        elif truth_pnl.get("value") not in (None, ""):
            lines.append(f"- 확정 손익은 {truth_pnl.get('value')}입니다.")
        if truth_pnl.get("broker_fee") not in (None, "") or truth_pnl.get("broker_tax") not in (None, ""):
            lines.append(f"- 브로커 수수료/세금은 {truth_pnl.get('broker_fee')} / {truth_pnl.get('broker_tax')}입니다.")
        same_price_round_trip = False
        try:
            same_price_round_trip = (
                truth_price.get("broker_buy_price") not in (None, "")
                and truth_price.get("broker_fill_price") not in (None, "")
                and float(truth_price.get("broker_buy_price")) == float(truth_price.get("broker_fill_price"))
            )
        except Exception:
            same_price_round_trip = False
        if same_price_round_trip and str(truth_pnl.get("value") or "").strip().lower() not in {"", "unavailable", "not_available"}:
            lines.append("- 매수가와 매도가가 같았고, 손익은 가격 변동이 아니라 수수료와 세금에서 발생했습니다.")
        if price_truth_source:
            lines.append(f"- 가격 truth 소스는 {price_truth_source_label(price_truth_source)}입니다.")
        if pnl_truth_source and pnl_truth_source not in {"", "unavailable"}:
            lines.append(f"- 손익 truth 소스는 {pnl_truth_source_label(pnl_truth_source)}입니다.")
        broker_day_match_mode = _clip(truth_pnl.get("broker_day_match_mode"), max_len=40)
        broker_day_truth_source = _clip(truth_pnl.get("broker_day_truth_source"), max_len=80)
        broker_day_authoritative = bool(truth_pnl.get("broker_day_authoritative"))
        if broker_day_match_mode or broker_day_authoritative:
            match_text = broker_day_match_mode or "unmatched"
            auth_text = "authoritative" if broker_day_authoritative else "reference_only"
            if broker_day_truth_source:
                lines.append(
                    f"- 브로커 당일 손익 매칭은 {match_text} / {auth_text} 상태이며, 소스는 {pnl_truth_source_label(broker_day_truth_source)}입니다."
                )
            else:
                lines.append(f"- 브로커 당일 손익 매칭은 {match_text} / {auth_text} 상태입니다.")
        if monitor_price_source and truth_price.get("broker_fill_price") in (None, ""):
            lines.append(f"- 모니터 가격 소스는 {monitor_price_source_label(monitor_price_source)}입니다.")
        lines.append(f"- {truth_availability_line(truth_availability)}")
        lines.append("")

    def _bool_label(value: Any) -> str:
        return "사용" if bool(value) else "미사용"

    def _join_arrow(values: Any, *, max_items: int = 4) -> str:
        items = _listify(values, max_items=max_items, max_len=24)
        return " -> ".join(items) if items else "없음"

    def _packet_status_line(name: str, packet: Dict[str, Any]) -> str:
        status_value = _metadata_value(packet.get("status") or "unavailable") or "확인되지 않음"
        fragments: List[str] = [status_value]
        sample_day_count = packet.get("sample_day_count")
        if sample_day_count not in (None, "") and name in {"weekly", "monthly"}:
            fragments.append(f"{sample_day_count}days")
        fragments.append("활성" if bool(packet.get("active")) else "비활성")
        return f"{name}={', '.join(fragments)}"

    def _memory_layer_explanations(
        memory_policy: Dict[str, Any],
        memory_packets: Dict[str, Any],
    ) -> List[str]:
        explanations: List[str] = []
        active_layers = set(_listify(memory_policy.get("active_layers"), max_items=8, max_len=24))
        for layer_name in ("weekly", "monthly"):
            packet = memory_packets.get(layer_name) if isinstance(memory_packets.get(layer_name), dict) else {}
            if not packet:
                continue
            if layer_name in active_layers or bool(packet.get("active")):
                continue
            sample_day_count = packet.get("sample_day_count")
            if sample_day_count not in (None, ""):
                explanations.append(
                    f"{layer_name} packet은 {sample_day_count}일 샘플이라 이번 거래에서는 보조 참고로만 남았습니다."
                )
            else:
                explanations.append(
                    f"{layer_name} packet은 존재하지만 commander가 이번 거래의 활성 layer로 채택하지 않았습니다."
                )
        return explanations

    def _reporter_feedback_usage_lines(memory_reporter: Dict[str, Any]) -> List[str]:
        lines_out: List[str] = []
        if not memory_reporter:
            return lines_out
        if not (bool(memory_reporter.get("available")) or bool(memory_reporter.get("consumed"))):
            if memory_reporter.get("present"):
                status = _metadata_value(memory_reporter.get("status") or "미사용")
                gate = _metadata_value(memory_reporter.get("feedback_gate_reason") or "확인되지 않음")
                lines_out.append(
                    f"same-day reporter feedback은 {status} 상태였고, gate 사유는 {gate}였습니다."
                )
            return lines_out

        source_reports = memory_reporter.get("source_reports") if isinstance(memory_reporter.get("source_reports"), dict) else {}
        trade_report_analysis = (
            memory_reporter.get("trade_report_analysis")
            if isinstance(memory_reporter.get("trade_report_analysis"), dict)
            else {}
        )
        confidence_text = {
            "high": "높음",
            "medium": "중간",
            "low": "낮음",
        }.get(str(memory_reporter.get("confidence") or "").strip().lower(), _metadata_value(memory_reporter.get("confidence") or "-"))
        closed_trade_count = trade_report_analysis.get("closed_trade_count")
        if source_reports.get("trade_reports") and closed_trade_count not in (None, ""):
            lines_out.append(
                f"same-day reporter feedback은 당일 닫힌 거래 리포트 {closed_trade_count}건을 묶어 생성했고, 신뢰도는 {confidence_text}입니다."
            )
            lines_out.append("이 내용은 이번 거래 단독 평가가 아니라 당일 흐름을 압축한 보조 피드백입니다.")
        else:
            status = _metadata_value(memory_reporter.get("status") or "ok")
            lines_out.append(
                f"same-day reporter feedback은 {status} 상태이고, 신뢰도는 {confidence_text}입니다."
            )
        win_count = trade_report_analysis.get("win_count")
        loss_count = trade_report_analysis.get("loss_count")
        avg_pnl_pct = trade_report_analysis.get("avg_pnl_pct")
        if win_count not in (None, "") or loss_count not in (None, "") or avg_pnl_pct not in (None, ""):
            lines_out.append(
                f"reporter 요약은 승/패 {win_count if win_count not in (None, '') else '-'}"
                f"/{loss_count if loss_count not in (None, '') else '-'}, "
                f"평균 손익률 {_fmt_pct(avg_pnl_pct)}였습니다."
            )
        recommendation = _listify(memory_reporter.get("recommendation"), max_items=2, max_len=140)
        if recommendation:
            rendered = [
                normalize_reporter_text(_operatorize_report_text(item))
                for item in recommendation
                if normalize_reporter_text(_operatorize_report_text(item))
            ]
            if rendered:
                lines_out.append(f"reporter 권고는 {' / '.join(rendered)}입니다.")
        return lines_out

    def _monitor_delta_interpretation(delta_rows: List[Dict[str, Any]]) -> str:
        notes: List[str] = []
        for row in delta_rows:
            if not isinstance(row, dict):
                continue
            field = str(row.get("field") or "").strip()
            try:
                delta_value = float(row.get("delta"))
            except Exception:
                delta_value = None
            if field == "breakout_buffer_pct" and delta_value is not None and delta_value > 0:
                notes.append("돌파 확인 버퍼를 키워 추격 진입을 더 보수적으로 막았습니다.")
            elif field == "max_extended_from_vwap_pct" and delta_value is not None and delta_value < 0:
                notes.append("VWAP 기준 과확장 추격 허용 범위를 줄여 현재 가격 부담이 큰 진입을 줄였습니다.")
            elif field == "volume_ratio_min" and delta_value is not None and delta_value > 0:
                notes.append("거래량 확인 기준을 높여 힘이 약한 종목 진입을 더 엄격하게 걸렀습니다.")
        return " ".join(notes[:3]).strip()

    def _monitor_hold_exit_interpretation(delta_rows: List[Dict[str, Any]]) -> str:
        notes: List[str] = []
        for row in delta_rows:
            if not isinstance(row, dict):
                continue
            field = str(row.get("field") or "").strip()
            try:
                delta_value = float(row.get("delta"))
            except Exception:
                delta_value = None
            if field == "confirm_ticks" and delta_value is not None and delta_value < 0:
                notes.append("보유 중 재확인 틱 수를 줄여 경고 후 정리를 더 빠르게 허용했습니다.")
            elif field == "stop_loss_pct" and delta_value is not None and delta_value < 0:
                notes.append("손절 허용 폭을 줄여 손실 구간 정리를 더 빠르게 당겼습니다.")
            elif field == "take_profit_pct" and delta_value is not None and delta_value < 0:
                notes.append("익절 목표를 낮춰 수익 구간 청산을 더 이르게 허용했습니다.")
            elif field == "trailing_stop_pct" and delta_value is not None and delta_value < 0:
                notes.append("트레일링 스탑 폭을 줄여 이익 반납을 더 빨리 막도록 조정했습니다.")
            elif field == "peak_drawdown_exit_pct" and delta_value is not None and delta_value < 0:
                notes.append("고점 대비 하락 허용 폭을 줄여 피크 이후 청산을 더 빠르게 유도했습니다.")
            elif field == "vwap_breakdown_pct" and delta_value is not None and delta_value < 0:
                notes.append("VWAP 이탈 허용 폭을 줄여 약세 전환 청산을 더 보수적으로 당겼습니다.")
        return " ".join(notes[:3]).strip()

    def _format_monitor_delta_parts(delta_rows: List[Dict[str, Any]]) -> List[str]:
        delta_parts: List[str] = []
        for row in delta_rows[:6]:
            if not isinstance(row, dict):
                continue
            field = _metadata_value(row.get("field") or "-")
            before = row.get("from")
            after = row.get("to")
            delta = row.get("delta")
            if before not in (None, "") and after not in (None, ""):
                if delta not in (None, ""):
                    try:
                        delta_parts.append(f"{field} {float(before):.3f} -> {float(after):.3f} ({float(delta):+0.3f})")
                    except Exception:
                        delta_parts.append(f"{field} {before} -> {after}")
                else:
                    delta_parts.append(f"{field} {before} -> {after}")
        return delta_parts

    def _monitor_truth_preface(title: str) -> str:
        if not closed_trade or title not in {"Holding / Monitoring Story", "Exit Decision"}:
            return ""
        broker_fill_price = truth_price.get("broker_fill_price")
        broker_buy_price = truth_price.get("broker_buy_price")
        monitor_mark_price = truth_price.get("monitor_mark_price")
        pnl_value = truth_pnl.get("value")
        pnl_pct = truth_pnl.get("pct")
        parts: List[str] = ['아래 값은 청산 직전 모니터 관측 기준입니다.']
        if monitor_mark_price not in (None, "") and broker_fill_price not in (None, ""):
            parts.append(
                f"청산 직전 모니터 관측가는 {_fmt_price(monitor_mark_price)}였고 실제 매도 체결가는 {_fmt_price(broker_fill_price)}였습니다."
            )
        elif broker_fill_price not in (None, ""):
            parts.append(f"였고 실제 매도 체결가는 {_fmt_price(broker_fill_price)}였습니다.")
        if title == "Exit Decision":
            if broker_buy_price not in (None, "") and broker_fill_price not in (None, ""):
                parts.append(
                    f"브로커 매수가/매도가는 {_fmt_price(broker_buy_price)} / {_fmt_price(broker_fill_price)}입니다."
                )
            if pnl_value not in (None, "") and pnl_pct not in (None, ""):
                parts.append(f"실제 실현손익은 {pnl_value} / {_fmt_pct(pnl_pct)}였습니다.")
        return " ".join(parts)

    def _normalize_section_bullet(title: str, bullet: str) -> str:
        raw = _operatorize_report_text(bullet) or str(bullet or "").strip()
        if not raw:
            return ""
        if closed_trade and title in {"Holding / Monitoring Story", "Exit Decision"}:
            if raw == '보유 시간은 0였습니다.':
                return ""
            if raw.startswith('가격 기준 소스는 ') or raw.startswith("Feature source:"):
                return ""
            if raw.startswith('현재 포지션 판단은 매도입니다.'):
                return raw.replace('현재 포지션 판단은 매도입니다.', '청산 직전 모니터 판단은 매도입니다.', 1)
            if raw.startswith('현재가, 평균가, 고점 기준 값은 '):
                return raw.replace('현재가, 평균가, 고점 기준 값은 ', '청산 직전 모니터 관측값(현재/평균/고점)은 ', 1)
            if raw.startswith('현재 손익 변동과 고점 대비 하락폭은 '):
                return raw.replace('현재 손익 변동과 고점 대비 하락폭은 ', '청산 직전 모니터 기준 손익 변동/고점 대비 하락폭은 ', 1)
            if title == "Exit Decision" and raw.startswith("Exit reason:"):
                return ""
        return raw

    memory_status = memory_surface.get("status") if isinstance(memory_surface.get("status"), dict) else {}
    memory_strategy = memory_surface.get("strategy_memory") if isinstance(memory_surface.get("strategy_memory"), dict) else {}
    memory_policy = memory_surface.get("commander_memory_policy") if isinstance(memory_surface.get("commander_memory_policy"), dict) else {}
    memory_packets = memory_surface.get("memory_packets") if isinstance(memory_surface.get("memory_packets"), dict) else {}
    memory_symbol = memory_surface.get("selected_symbol_memory") if isinstance(memory_surface.get("selected_symbol_memory"), dict) else {}
    memory_reporter = memory_surface.get("reporter_feedback_packet") if isinstance(memory_surface.get("reporter_feedback_packet"), dict) else {}
    memory_read_model = memory_surface.get("read_model_facts") if isinstance(memory_surface.get("read_model_facts"), dict) else {}
    memory_usage = memory_surface.get("usage_trace") if isinstance(memory_surface.get("usage_trace"), dict) else {}
    memory_application_surface = report.get("memory_application_surface") if isinstance(report.get("memory_application_surface"), dict) else {}
    if memory_surface:
        lines.append("## 메모리 사용")
        lines.append("")
        lines.append(
            "- 전략 메모리={strategy}, 종목 메모리={symbol_mem}, 리포터 피드백={reporter}, 읽기 모델 팩트={read_model}입니다.".format(
                strategy=_bool_label(memory_status.get('strategy_memory_used')),
                symbol_mem=_bool_label(memory_status.get('selected_symbol_memory_used')),
                reporter=_bool_label(memory_status.get('reporter_feedback_used')),
                read_model=_bool_label(memory_status.get('read_model_facts_used')),
            )
        )
        if memory_strategy:
            best_playbooks = ", ".join(_listify(memory_strategy.get("best_playbooks"), max_items=3, max_len=24))
            worst_playbooks = ", ".join(_listify(memory_strategy.get("worst_playbooks"), max_items=3, max_len=24))
            recent_failures = ", ".join(_listify(memory_strategy.get("recent_failures"), max_items=3, max_len=36))
            lines.append(
                f"- 전략 메모리는 {'집계형 strategy_memory로 전달됐고' if memory_strategy.get('scope') == 'aggregated_strategy_memory' else '입력에 포함됐고'}, "
                f"status는 {_metadata_value(memory_strategy.get('status') or 'unknown')}입니다."
            )
            if memory_strategy.get("requested_day") or memory_strategy.get("resolved_day"):
                lines.append(
                    f"- 전략 메모리 요청일/해석일은 {_metadata_value(memory_strategy.get('requested_day') or '-')} / {_metadata_value(memory_strategy.get('resolved_day') or '-') }입니다."
                )
            if best_playbooks or worst_playbooks or recent_failures:
                lines.append(
                    f"- 전략 메모리상 우세/취약 playbook과 최근 실패 흔적은 {best_playbooks or '없음'} / {worst_playbooks or '없음'} / {recent_failures or '없음'}입니다."
                )
        if memory_policy:
            active_layers = ", ".join(_listify(memory_policy.get("active_layers"), max_items=4, max_len=16))
            lines.append(
                f"- commander가 실제 활성화한 메모리 레이어는 {active_layers or '없음'}이고, 우선순위는 {_join_arrow(memory_policy.get('priority_order'))}입니다."
            )
            if bool(memory_policy.get("symbol_memory_override_enabled")):
                lines.append("- symbol memory override gate가 켜져 있어 종목 메모리가 직접 override layer로 승격될 수 있습니다.")
            else:
                lines.append("- symbol memory override gate가 꺼져 있어 종목 메모리는 보조 참조로만 사용합니다.")
        if memory_packets:
            daily_packet = memory_packets.get("daily") if isinstance(memory_packets.get("daily"), dict) else {}
            weekly_packet = memory_packets.get("weekly") if isinstance(memory_packets.get("weekly"), dict) else {}
            monthly_packet = memory_packets.get("monthly") if isinstance(memory_packets.get("monthly"), dict) else {}
            symbol_packet = memory_packets.get("symbol") if isinstance(memory_packets.get("symbol"), dict) else {}
            lines.append(
                "- raw memory packet 상태는 "
                + ", ".join(
                    [
                        _packet_status_line("daily", daily_packet),
                        _packet_status_line("weekly", weekly_packet),
                        _packet_status_line("monthly", monthly_packet),
                        _packet_status_line("symbol", symbol_packet),
                    ]
                )
                + "입니다."
            )
            for note in _memory_layer_explanations(memory_policy, memory_packets):
                lines.append(f"- {note}")
        if memory_symbol:
            symbol_name = _metadata_value(memory_symbol.get("symbol") or symbol or "해당 종목")
            if bool(memory_symbol.get("present")):
                trade_count = memory_symbol.get("trade_count")
                win_rate = memory_symbol.get("win_rate")
                dominant_playbook = _clip(memory_symbol.get("dominant_playbook"), max_len=40)
                dominant_blocker = _clip(memory_symbol.get("dominant_monitor_blocker"), max_len=60)
                blocker_text = (
                    dominant_blocker
                    if dominant_blocker and dominant_blocker.lower() not in {"unknown", "확인되지 않음"}
                    else "명확히 잡히지 않았음"
                )
                trade_count_text = trade_count if trade_count not in (None, "") else "-"
                win_rate_text = "-"
                if win_rate not in (None, ""):
                    try:
                        win_rate_text = f"{float(win_rate) * 100.0:.1f}%"
                    except Exception:
                        pass
                dominant_playbook_text = _metadata_value(dominant_playbook or "-")
                lines.append(
                    f"- {symbol_name} 종목 메모리는 과거 거래 {trade_count_text}건, 승률 {win_rate_text}, "
                    f"우세 playbook {dominant_playbook_text}, 주요 blocker는 {blocker_text}입니다."
                )
                if "symbol" not in set(_listify(memory_policy.get("active_layers"), max_items=8, max_len=24)):
                    lines.append(f"- 이번 거래에서는 commander가 symbol layer를 활성화하지 않아 {symbol_name} 종목 메모리는 보조 참고로만 사용했습니다.")
            else:
                lines.append(f"- {symbol_name} 종목 메모리는 비어 있었고 종목별 과거 이력은 직접 반영하지 않았습니다.")
        for reporter_line in _reporter_feedback_usage_lines(memory_reporter):
            lines.append(f"- {reporter_line}")
        if memory_read_model:
            if bool(memory_read_model.get("present")):
                symbol_patterns = ", ".join(_listify(memory_read_model.get("symbols"), max_items=5, max_len=24))
                daily_flag = "있음" if bool(memory_read_model.get("daily_summary_present")) else "없음"
                lines.append(
                    f"- read_model_facts는 최근 거래 {memory_read_model.get('recent_trade_count') or 0}건, "
                    f"종목 패턴 {memory_read_model.get('symbol_pattern_count') or 0}건, "
                    f"일일 요약 {daily_flag} 기준으로 들어갔습니다."
                )
                if symbol_patterns:
                    lines.append(f"- read_model_facts 종목 패턴 표본은 {symbol_patterns}입니다.")
            elif memory_read_model or memory_status.get("read_model_facts_used") is False:
                lines.append("- read_model_facts는 이번 리포트 입력에서 직접 확인되지 않았습니다.")
        if _clip(memory_usage.get("playbook"), max_len=40) or _clip(memory_usage.get("monitor_guidance"), max_len=40):
            lines.append(
                f"- 전략가 출력에는 playbook={_metadata_value(memory_usage.get('playbook') or '-')}, "
                f"monitor_guidance={_metadata_value(memory_usage.get('monitor_guidance') or '-')}, "
                f"scanner_bias={_metadata_value(memory_usage.get('scanner_bias') or '-')}가 남았습니다."
            )
        lines.append("")
    if memory_application_surface:
        scanner_memory_application = (
            memory_application_surface.get("scanner_memory_bias")
            if isinstance(memory_application_surface.get("scanner_memory_bias"), dict)
            else {}
        )
        monitor_memory_application = (
            memory_application_surface.get("monitor_memory_bias")
            if isinstance(memory_application_surface.get("monitor_memory_bias"), dict)
            else {}
        )
        lines.append("## 메모리 적용 결과")
        lines.append("")
        if scanner_memory_application:
            if bool(scanner_memory_application.get("captured")):
                scanner_layers = ", ".join(_listify(scanner_memory_application.get("active_layers"), max_items=4, max_len=16))
                lines.append(f"- 이번 거래에서는 scanner가 {scanner_layers or '없음'} 메모리만 실제로 사용했습니다.")
                scanner_source_delta = (
                    scanner_memory_application.get("source_weight_delta")
                    if isinstance(scanner_memory_application.get("source_weight_delta"), dict)
                    else {}
                )
                if scanner_source_delta:
                    delta_parts = []
                    for key, value in list(scanner_source_delta.items())[:6]:
                        try:
                            delta_parts.append(f"{_metadata_value(key)} {float(value):+0.3f}")
                        except Exception:
                            continue
                    if delta_parts:
                        lines.append(f"- scanner source weight delta: {', '.join(delta_parts)}")
                else:
                    lines.append("- scanner source-level 가중치 변화는 별도 기록이 없어 후보별 점수 조정만 확인됩니다.")
                selected_symbol = _metadata_value(scanner_memory_application.get("selected_symbol") or symbol or "-")
                selected_bias_adjustment = scanner_memory_application.get("selected_bias_adjustment")
                if selected_bias_adjustment not in (None, ""):
                    try:
                        adjustment_value = float(selected_bias_adjustment)
                        if abs(adjustment_value) < 1e-12:
                            lines.append(f"- 이번 거래 후보 {selected_symbol}에는 메모리 기반 추가 가점이나 감점이 없었습니다.")
                        else:
                            lines.append(
                                f"- 이번 거래 후보 {selected_symbol}에는 memory bias adjustment {adjustment_value:+0.3f}가 반영됐습니다."
                            )
                    except Exception:
                        pass
                elif bool(scanner_memory_application.get("applied")):
                    lines.append("- scanner memory bias applied, but per-symbol delta was not saved in this artifact.")
                scanner_reason = ", ".join(_listify(scanner_memory_application.get("reason"), max_items=4, max_len=48))
                if scanner_reason:
                    lines.append(f"- scanner memory bias 근거는 {scanner_reason}입니다.")
            else:
                    lines.append("- scanner memory bias applied, but per-symbol delta was not saved in this artifact.")
        if monitor_memory_application:
            if bool(monitor_memory_application.get("captured")):
                monitor_layers = ", ".join(_listify(monitor_memory_application.get("active_layers"), max_items=4, max_len=16))
                lines.append(f"- 이번 거래에서는 monitor가 {monitor_layers or '없음'} 메모리를 entry policy에서 사용했습니다.")
                delta_rows = list(monitor_memory_application.get("applied_deltas") or [])
                if delta_rows:
                    delta_parts = _format_monitor_delta_parts(delta_rows)
                    if delta_parts:
                        lines.append(f"- monitor entry delta: {', '.join(delta_parts)}")
                        interpretation = _monitor_delta_interpretation(delta_rows)
                        if interpretation:
                            lines.append(f"- monitor 적용 해석: {interpretation}")
                elif bool(monitor_memory_application.get("applied")):
                    lines.append("- monitor memory bias는 적용됐지만 entry delta 수치는 원문에서 직접 확인되지 않았습니다.")
                else:
                    entry_delta_keys = ", ".join(_listify(monitor_memory_application.get("entry_delta_keys"), max_items=6, max_len=40))
                    if entry_delta_keys:
                        lines.append(f"- monitor memory bias 요약상 조정 대상 field는 {entry_delta_keys}입니다.")
                hold_delta_rows = list(monitor_memory_application.get("hold_deltas") or [])
                if hold_delta_rows:
                    hold_delta_parts = _format_monitor_delta_parts(hold_delta_rows)
                    if hold_delta_parts:
                        lines.append(f"- monitor hold delta: {', '.join(hold_delta_parts)}")
                        hold_interpretation = _monitor_hold_exit_interpretation(hold_delta_rows)
                        if hold_interpretation:
                            lines.append(f"- monitor hold 해석: {hold_interpretation}")
                elif bool(monitor_memory_application.get("hold_applied")):
                    lines.append("- monitor hold bias는 적용됐지만 hold delta 수치는 원문에서 직접 확인되지 않았습니다.")
                exit_delta_rows = list(monitor_memory_application.get("exit_deltas") or [])
                if exit_delta_rows:
                    exit_delta_parts = _format_monitor_delta_parts(exit_delta_rows)
                    if exit_delta_parts:
                        lines.append(f"- monitor exit delta: {', '.join(exit_delta_parts)}")
                        exit_interpretation = _monitor_hold_exit_interpretation(exit_delta_rows)
                        if exit_interpretation:
                            lines.append(f"- monitor exit 해석: {exit_interpretation}")
                elif bool(monitor_memory_application.get("exit_applied")):
                    lines.append("- monitor exit bias는 적용됐지만 exit delta 수치는 원문에서 직접 확인되지 않았습니다.")
                risk_posture = _metadata_value(monitor_memory_application.get("risk_posture") or "")
                effective_policy_source = _metadata_value(monitor_memory_application.get("effective_policy_source") or "")
                if risk_posture or effective_policy_source:
                    lines.append(
                        f"- monitor risk posture / effective policy source는 {risk_posture or '-'} / {effective_policy_source or '-'}입니다."
                    )
                monitor_reason = ", ".join(_listify(monitor_memory_application.get("reason"), max_items=4, max_len=48))
                if monitor_reason:
                    lines.append(f"- monitor 조정 근거는 {monitor_reason}입니다.")
            else:
                lines.append("- monitor memory bias의 실제 delta는 이 거래 artifact에 기록되지 않았습니다.")
        lines.append("")
    section_provenance = report.get("section_provenance") if isinstance(report.get("section_provenance"), dict) else {}
    if section_provenance:
        lines.append("## 근거 출처")
        lines.append("")
        section_titles = {
            "market_context_at_entry": "시장 환경 요약",
            "strategist_summary": "전략가 요약",
            "why_this_symbol_was_chosen": "선택된 종목 상세 분석",
            "holding_monitoring_story": "보유 경과",
            "execution_quality": "실행 결과",
            "reporter_evaluation": "결과 평가",
        }
        for section_key in (
            "market_context_at_entry",
            "strategist_summary",
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
    monitor_snapshot_section: List[str] = []
    if monitor_snapshot:
        _main_lines = lines
        lines = []
        def _to_float_opt(value: Any) -> Optional[float]:
            try:
                if value in (None, ""):
                    return None
                return float(value)
            except Exception:
                return None

        def _axis_family(value: Any) -> str:
            token = str(value or "").strip().lower().replace(" ", "_")
            if not token:
                return "unknown"
            if token in {
                "hard_stop",
                "hard_stop_pct",
                "adaptive_stop",
                "adaptive_stop_loss",
                "adaptive_stop_loss_pct",
                "effective_stop",
                "effective_stop_loss",
                "effective_stop_loss_pct",
                "stop_loss",
                "stop_loss_pct",
            }:
                return "stop"
            if token in {"take_profit", "take_profit_pct", "target_profit", "tp"}:
                return "take_profit"
            if token in {"trailing_stop", "trailing_stop_pct"}:
                return "trailing"
            return "other"

        def _pick_active_stop(snapshot: Dict[str, Any]) -> tuple[str, Optional[float]]:
            effective = _to_float_opt(snapshot.get("effective_stop_loss_pct"))
            if effective is not None:
                return "유효 손절", effective
            candidates: List[tuple[str, float]] = []
            for label, key in (
                ("모니터 adaptive 손절", "adaptive_stop_loss_pct"),
                ("Hard fail-safe 손절", "hard_stop_pct"),
                ("기본 손절", "stop_loss_pct"),
            ):
                value = _to_float_opt(snapshot.get(key))
                if value is not None:
                    candidates.append((label, value))
            if not candidates:
                return "", None
            candidates.sort(key=lambda row: abs(row[1]))
            return candidates[0]

        trigger_raw = _clip(monitor_snapshot.get("trigger_type"), max_len=80) or _clip(
            monitor_snapshot.get("active_exit_axis"), max_len=80
        )
        trigger_label = _axis_label(trigger_raw)
        trigger_family = _axis_family(trigger_raw)
        stop_label, stop_value = _pick_active_stop(monitor_snapshot)
        take_profit_value = _to_float_opt(monitor_snapshot.get("take_profit_pct"))
        trailing_value = _to_float_opt(monitor_snapshot.get("trailing_stop_pct"))
        current_drawdown = _to_float_opt(monitor_snapshot.get("current_drawdown"))
        peak_drawdown = _to_float_opt(monitor_snapshot.get("peak_drawdown"))
        current_price = monitor_snapshot.get("current_price")
        average_price = monitor_snapshot.get("average_price")
        peak_price = monitor_snapshot.get("peak_price")

        lines.append("## 모니터 스냅샷")
        lines.append("")
        lines.append(f"- 현재 포지션 판단은 {_action_label(monitor_snapshot.get('posture'))}입니다.")
        lines.append(f"- 감지된 신호 유형은 {trigger_label}입니다.")
        if stop_value is not None:
            lines.append(f"- 활성 손절 기준은 {_fmt_pct(stop_value)}입니다. (기준: {stop_label or '-'})")
        if take_profit_value is not None:
            lines.append(f"- 활성 익절 기준은 {_fmt_pct(take_profit_value)}입니다.")
        if trailing_value is not None:
            lines.append(f"- 보조 trailing stop 기준은 {_fmt_pct(trailing_value)}입니다.")
        if monitor_snapshot.get("exit_triggered"):
            lines.append(f"- 실제 청산 트리거는 {trigger_label}입니다.")
            if trigger_family not in {"stop", "take_profit", "trailing"}:
                lines.append("- 이번 청산은 손절/익절 기준선 충족이 아니라 별도 조건 축에서 발생했습니다.")
        else:
            lines.append("- 현재 사이클에서는 청산 신호가 확정되지 않았습니다.")
        if (
            current_drawdown is not None
            and peak_drawdown is not None
            and abs(float(current_drawdown)) < 1e-9
            and float(peak_drawdown) < 0.0
        ):
            lines.append("- 현재 손익 변동이 0%여도, 장중 고점 대비 하락폭(peak drawdown) 조건으로 청산될 수 있습니다.")
        elif current_drawdown is not None or peak_drawdown is not None:
            lines.append(
                f"- 현재 손익 변동/피크 드로우다운은 {_fmt_pct(current_drawdown)}/{_fmt_pct(peak_drawdown)}입니다."
            )
        if current_price not in (None, "") or average_price not in (None, "") or peak_price not in (None, ""):
            lines.append(
                f"- 스냅샷 가격(현재/평균/고점)은 {_fmt_price(current_price)} / {_fmt_price(average_price)} / {_fmt_price(peak_price)}입니다."
            )
            lines.append("- 위 가격은 모니터 관측값이며, 실제 체결 손익 계산값과 다를 수 있습니다.")
        pnl = str(shared_facts.get("pnl") or "").strip().lower()
        pnl_pct = shared_facts.get("pnl_pct")
        broker_fill_price = shared_facts.get("broker_fill_price")
        account_mark_price = shared_facts.get("account_mark_price")
        monitor_mark_price = shared_facts.get("monitor_mark_price")
        price_truth_source = _clip(shared_facts.get("price_truth_source"), max_len=40)
        pnl_truth_source = _clip(shared_facts.get("pnl_truth_source"), max_len=80)
        if pnl in {"", "unavailable", "not_available"}:
            lines.append("- 실현 손익 값은 현재 아티팩트에서 직접 확인되지 않았습니다.")
        elif pnl_pct not in (None, ""):
            lines.append(f"- 실현 손익 기준 PnL/PnL%는 {shared_facts.get('pnl')} / {_fmt_pct(pnl_pct)}입니다.")
        else:
            lines.append(f"- 실현 손익 기준 PnL은 {shared_facts.get('pnl')}입니다.")
        broker_buy_price = shared_facts.get("broker_buy_price")
        if broker_buy_price not in (None, "") and broker_fill_price not in (None, ""):
            lines.append(f"- 브로커 매수가/매도가는 {_fmt_price(broker_buy_price)} / {_fmt_price(broker_fill_price)}입니다.")
        elif broker_fill_price not in (None, ""):
            lines.append(f"- 브로커 체결가는 {_fmt_price(broker_fill_price)}입니다.")
        if account_mark_price not in (None, ""):
            lines.append(f"- 계좌 기준 마크 가격은 {_fmt_price(account_mark_price)}입니다.")
        if monitor_mark_price not in (None, "") and broker_fill_price in (None, ""):
            lines.append(f"- 종료 직전 모니터 관측 가격은 {_fmt_price(monitor_mark_price)}입니다.")
        if price_truth_source:
            lines.append(f"- 가격 truth 소스는 {price_truth_source_label(price_truth_source)}입니다.")
        if pnl_truth_source and pnl_truth_source not in {"", "unavailable"}:
            lines.append(f"- 손익 truth 소스는 {pnl_truth_source_label(pnl_truth_source)}입니다.")
        if str(monitor_snapshot.get("price_source") or "").strip():
            lines.append(f"- 가격 기준 소스는 {monitor_price_source_label(monitor_snapshot.get('price_source'))}입니다.")
        lines.append("")
        # Prevent duplicate legacy snapshot rendering below.
        monitor_snapshot = {}
    execution_truth_bullets = build_execution_truth_bullets(
        execution_details=execution_result,
        shared_facts=report.get("shared_facts") if isinstance(report.get("shared_facts"), dict) else {},
    )
    if execution_truth_bullets:
        existing_bullets = _listify(execution_result.get("bullets"), max_items=12, max_len=400)
        for bullet in execution_truth_bullets:
            if bullet not in existing_bullets:
                existing_bullets.append(bullet)
        execution_result["bullets"] = existing_bullets
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
    if '_main_lines' in locals():
        monitor_snapshot_section = lines
        lines = _main_lines

    market_context_section = dict(market_context) if isinstance(market_context, dict) else {}
    strategist_summary_section = dict(strategist_summary) if isinstance(strategist_summary, dict) else {}
    if not strategist_summary_section:
        market_bullets = list(market_context_section.get("bullets") or [])
        strategist_prefixes = ("스캐너 연결 근거는 ", "전략가 핵심 입력은 ", "주요 시장 뉴스는 ")
        strategist_bullets: List[str] = []
        strategist_scanner_linkage: List[str] = []
        remaining_bullets: List[Any] = []
        for bullet in market_bullets:
            bullet_text = str(bullet or "").strip()
            if bullet_text.startswith(strategist_prefixes):
                if bullet_text.startswith("스캐너 연결 근거는 "):
                    strategist_scanner_linkage.append(bullet_text)
                else:
                    strategist_bullets.append(bullet_text)
            else:
                remaining_bullets.append(bullet)
        strategist_bullets.extend(strategist_scanner_linkage)
        if strategist_bullets:
            market_context_section["bullets"] = remaining_bullets
            strategist_summary_section = {
                "summary": "전략가 입력과 뉴스 연계 근거를 분리 요약했습니다.",
                "bullets": strategist_bullets,
            }

    def _section(title: str, section: Dict[str, Any], *, bullet_key: str = "bullets") -> None:
        lines.append(f"## {_section_title(title)}")
        lines.append("")
        summary = _render_text(section.get("summary"))
        if summary:
            lines.append(summary)
            lines.append("")
        preface = _monitor_truth_preface(title)
        if preface:
            lines.append(preface)
            lines.append("")
        bullets = _listify(section.get(bullet_key), max_items=12, max_len=400)
        seen_rendered: set[str] = set()
        suppressed_prefixes = (
            "주요 감시 축은 ",
            "전략가 baseline 적응형 손절 기준은 ",
            "전략가 baseline 익절 기준은 ",
            "전략가 baseline trailing stop 기준은 ",
            "유효 손절 기준은 ",
            "손절 기준 축은 ",
            "목표 수익 실현 기준은 ",
            "Effective stop:",
            "Take profit:",
            "Watch axes:",
        )
        for bullet in bullets:
            raw_bullet = _normalize_section_bullet(title, bullet)
            if not raw_bullet:
                continue
            if raw_bullet.startswith(suppressed_prefixes):
                continue
            rendered = _render_text(raw_bullet)
            if rendered:
                if rendered in seen_rendered:
                    continue
                # Monitor snapshot section already surfaces these in a compact form.
                if str(rendered).startswith(suppressed_prefixes):
                    continue
                seen_rendered.add(rendered)
                lines.append(f"- {rendered}")
        if bullets:
            lines.append("")

    _section("Executive Summary", executive)
    _section("Market Context at Entry", market_context_section or market_context)
    if strategist_summary_section:
        _section("Strategist Summary", strategist_summary_section)
    _section("Why This Symbol Was Chosen", why_symbol)
    _section("Scanner Logic and Filters", scanner_filters)
    _section("Entry Decision", entry_decision)
    _section("Holding / Monitoring Story", holding_story)
    _section("Exit Decision", exit_decision)
    if monitor_snapshot_section:
        lines.extend(monitor_snapshot_section)
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
