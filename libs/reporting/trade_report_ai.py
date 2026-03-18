from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from libs.llm.llm_router import LLMRouter


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


def _strip_fenced_block(text: str) -> str:
    raw = str(text or "").strip()
    if not raw.startswith("```"):
        return raw
    lines = raw.splitlines()
    if not lines:
        return raw
    lines = lines[1:]
    if lines and lines[-1].strip().startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = _strip_fenced_block(text)
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    decoder = json.JSONDecoder()
    for idx, char in enumerate(raw):
        if char != "{":
            continue
        try:
            obj, _ = decoder.raw_decode(raw[idx:])
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


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


def _normalize_trade_report_output(story_input: Dict[str, Any], report: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(report or {})
    action = _actual_lifecycle_action(story_input)
    symbol = _clip(story_input.get("symbol"), max_len=32) or _clip(out.get("symbol"), max_len=32) or "unknown"
    status_text = _clip(story_input.get("status"), max_len=32) or _clip(out.get("status"), max_len=32) or "closed"
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

    final_conclusion = out.get("final_operator_conclusion") if isinstance(out.get("final_operator_conclusion"), dict) else {}
    normalized_conclusion = dict(final_conclusion)
    normalized_conclusion["current_action"] = "HOLD" if status_text.lower() == "open" and action == "BUY" else action
    out["final_operator_conclusion"] = normalized_conclusion
    return out


def _contains_hangul(value: Any) -> bool:
    return bool(re.search(r"[가-힣]", str(value or "")))


def _prefer_fallback_text(ai_text: Any, fallback_text: Any) -> str:
    ai_clean = _clip(ai_text, max_len=2000)
    fallback_clean = _clip(fallback_text, max_len=2000)
    if not ai_clean:
        return fallback_clean
    if fallback_clean and not _contains_hangul(ai_clean) and _contains_hangul(fallback_clean):
        return fallback_clean
    return ai_clean


def _merge_section_with_fallback(ai_section: Any, fallback_section: Dict[str, Any]) -> Dict[str, Any]:
    section = ai_section if isinstance(ai_section, dict) else {}
    fallback = fallback_section if isinstance(fallback_section, dict) else {}
    merged = dict(section)
    merged["summary"] = _prefer_fallback_text(section.get("summary"), fallback.get("summary"))
    ai_bullets = _listify(section.get("bullets"), max_items=12, max_len=260)
    fallback_bullets = _listify(fallback.get("bullets"), max_items=12, max_len=260)
    if not ai_bullets:
        merged["bullets"] = fallback_bullets
    elif fallback_bullets and not any(_contains_hangul(item) for item in ai_bullets) and any(_contains_hangul(item) for item in fallback_bullets):
        merged["bullets"] = fallback_bullets
    else:
        merged["bullets"] = ai_bullets
    for key in ("headline", "action", "confidence", "status", "grade", "current_action", "symbol"):
        if not str(merged.get(key) or "").strip() and str(fallback.get(key) or "").strip():
            merged[key] = fallback.get(key)
    return merged


def _fallback_report(
    story_input: Dict[str, Any],
    *,
    status: str,
    mode: str,
    model: str,
    reason: str,
) -> Dict[str, Any]:
    market_context = story_input.get("market_context_human") if isinstance(story_input.get("market_context_human"), dict) else {}
    scanner_reason = story_input.get("scanner_reason_human") if isinstance(story_input.get("scanner_reason_human"), dict) else {}
    filters_human = story_input.get("filters_human") if isinstance(story_input.get("filters_human"), dict) else {}
    monitor_reason = story_input.get("monitor_reason_human") if isinstance(story_input.get("monitor_reason_human"), dict) else {}
    guard_reason = story_input.get("guard_reason_human") if isinstance(story_input.get("guard_reason_human"), dict) else {}
    execution_outcome = story_input.get("execution_outcome_human") if isinstance(story_input.get("execution_outcome_human"), dict) else {}
    reporter_status = story_input.get("reporter_status_human") if isinstance(story_input.get("reporter_status_human"), dict) else {}
    operator_conclusion = (
        story_input.get("operator_conclusion_human") if isinstance(story_input.get("operator_conclusion_human"), dict) else {}
    )
    monitor_snapshot = {
        "posture": _clip(monitor_reason.get("posture"), max_len=40) or action or "WAIT",
        "trigger_type": _clip(monitor_reason.get("trigger_type"), max_len=80) or "not_captured",
        "position_age_seconds": int(monitor_reason.get("position_age_seconds") or 0),
        "stop_loss_pct": monitor_reason.get("stop_loss_pct"),
        "effective_stop_loss_pct": monitor_reason.get("effective_stop_loss_pct"),
        "effective_stop_reason": _clip(monitor_reason.get("effective_stop_reason"), max_len=80) or "not_captured",
        "take_profit_pct": monitor_reason.get("take_profit_pct"),
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

    action = _clip(story_input.get("action"), max_len=24) or "WAIT"
    symbol = _clip(story_input.get("symbol"), max_len=32) or "unknown"
    trade_id = _clip(story_input.get("trade_id") or story_input.get("story_id"), max_len=120)
    status_text = _clip(story_input.get("status"), max_len=32) or "closed"
    executive_reason = (
        _clip(operator_conclusion.get("summary"), max_len=600)
        or _clip(lifecycle_summary.get("lifecycle_summary_human"), max_len=600)
        or _clip(execution_outcome.get("summary"), max_len=600)
        or _clip(scanner_reason.get("summary"), max_len=600)
        or "The decision path was recorded, but the operator-facing summary is limited."
    )
    confidence = _clip(scanner_reason.get("confidence_label"), max_len=24) or _clip(scanner_reason.get("confidence"), max_len=24)

    entry_decision = {
        "summary": (
            _clip(entry_summary.get("reason_human"), max_len=600)
            or _clip(scanner_reason.get("summary"), max_len=600)
            or "Entry decision rationale was not captured."
        ),
        "bullets": [
            f"Entry run: {_clip(entry_summary.get('run_id'), max_len=80) or 'not_captured'}",
            f"Entry time: {_clip(entry_summary.get('ts'), max_len=80) or 'not_captured'}",
            f"Entry action: {_clip(entry_summary.get('action'), max_len=40) or action}",
            f"Entry reason: {_clip(entry_summary.get('reason_human'), max_len=220) or 'not_captured'}",
        ],
    }
    hold_count = len(list(holding_summary.get("run_ids") or []))
    holding_story = {
        "summary": (
            f"Holding phase captured {hold_count} monitor runs."
            if hold_count > 0
            else "Holding phase evidence is limited for this lifecycle."
        ),
        "bullets": (
            _listify(holding_summary.get("monitor_updates"), max_items=10, max_len=260)
            or _listify(monitor_reason.get("bullets"), max_items=10, max_len=260)
        ),
    }
    exit_decision = {
        "summary": (
            _clip(exit_summary.get("reason_human"), max_len=600)
            or ("Position is still open; no closing SELL execution has been captured yet." if status_text == "open" else "Exit reasoning was not captured.")
        ),
        "bullets": [
            f"Exit run: {_clip(exit_summary.get('run_id'), max_len=80) or 'not_captured'}",
            f"Exit time: {_clip(exit_summary.get('ts'), max_len=80) or 'not_captured'}",
            f"Exit action: {_clip(exit_summary.get('action'), max_len=40) or ('HOLD' if status_text == 'open' else 'not_captured')}",
            f"Exit reason: {_clip(exit_summary.get('reason_human'), max_len=220) or ('position still open' if status_text == 'open' else 'not_captured')}",
        ],
    }
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
        "schema_version": "trade_report.v2",
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
            "summary": _clip(market_context.get("summary"), max_len=600),
            "bullets": _listify(market_context.get("bullets"), max_items=8, max_len=260),
        },
        "why_this_symbol_was_chosen": {
            "summary": _clip(scanner_reason.get("summary"), max_len=600),
            "bullets": _listify(scanner_reason.get("bullets"), max_items=8, max_len=260),
        },
        "entry_decision": entry_decision,
        "holding_monitoring_story": holding_story,
        "exit_decision": exit_decision,
        "execution_quality": execution_quality,
        "monitor_snapshot": monitor_snapshot,
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
    }
    # Backward-compatible aliases used by earlier UI/report consumers.
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return out


def _build_messages(story_input: Dict[str, Any]) -> List[Dict[str, str]]:
    compact_input = {
        "trade_id": story_input.get("trade_id") or story_input.get("story_id"),
        "story_id": story_input.get("story_id"),
        "run_id": story_input.get("run_id"),
        "symbol": story_input.get("symbol"),
        "action": story_input.get("action"),
        "status": story_input.get("status"),
        "story_type": story_input.get("story_type"),
        "execution_mode_label": story_input.get("execution_mode_label"),
        "entry_summary": story_input.get("entry_summary"),
        "holding_summary": story_input.get("holding_summary"),
        "exit_summary": story_input.get("exit_summary"),
        "lifecycle_summary": story_input.get("lifecycle_summary"),
        "market_context_human": story_input.get("market_context_human"),
        "scanner_reason_human": story_input.get("scanner_reason_human"),
        "filters_human": story_input.get("filters_human"),
        "monitor_reason_human": story_input.get("monitor_reason_human"),
        "guard_reason_human": story_input.get("guard_reason_human"),
        "execution_outcome_human": story_input.get("execution_outcome_human"),
        "reporter_status_human": story_input.get("reporter_status_human"),
        "operator_conclusion_human": story_input.get("operator_conclusion_human"),
        "timeline": story_input.get("timeline"),
        "warnings": story_input.get("warnings"),
    }
    return [
        {
            "role": "system",
            "content": (
                "당신은 트레이딩 시스템의 거래별 운영 리포트를 작성하는 한국어 분석기입니다. "
                "입력으로 제공된 사실만 사용하고 숫자나 사건을 지어내지 마세요. "
                "모든 출력은 한국어 JSON 객체 하나만 반환하세요."
            ),
        },
        {
            "role": "user",
            "content": (
                "아래 trade story input을 운영자가 한눈에 이해할 수 있는 한국어 AI 거래 리포트로 정리하세요.\n"
                "파이프라인 순서를 반드시 유지하세요: 전략가 -> 스캐너 -> 모니터 -> 감독관 -> 수행자 -> 리포터.\n"
                "다음 원칙을 지키세요.\n"
                "- 글로벌 감성 점수, VIX, 수집한 뉴스 수와 질의 대상 수를 가능한 한 숫자로 적기\n"
                "- 스캐너는 후보 수, 1등 종목, runner-up, Kiwoom 소스(top_value/top_volume/sector_theme 등), 점수/feature coverage를 구체적으로 적기\n"
                "- 모니터는 전달받은 감시 기준(stop, effective stop, take profit, watch axis, 가격 source)을 구체적으로 적기\n"
                "- 감독관과 수행자는 승인/체결 결과를 분리해서 적기\n"
                "- 리포터 linkage가 없으면 원인을 한국어로 설명하기\n"
                "- 영어 문장 대신 한국어 문장으로 쓰되, 종목코드와 key 이름은 필요한 경우 유지 가능\n"
                "아래 JSON 스키마로만 반환하세요:\n"
                "{"
                "\"executive_summary\": {\"headline\": str, \"action\": str, \"symbol\": str, \"confidence\": str, \"summary\": str}, "
                "\"market_context_at_entry\": {\"summary\": str, \"bullets\": [str]}, "
                "\"why_this_symbol_was_chosen\": {\"summary\": str, \"bullets\": [str]}, "
                "\"entry_decision\": {\"summary\": str, \"bullets\": [str]}, "
                "\"holding_monitoring_story\": {\"summary\": str, \"bullets\": [str]}, "
                "\"exit_decision\": {\"summary\": str, \"bullets\": [str]}, "
                "\"execution_quality\": {\"summary\": str, \"bullets\": [str]}, "
                "\"scanner_filters\": {\"summary\": str, \"bullets\": [str]}, "
                "\"guard_approval_result\": {\"summary\": str, \"bullets\": [str]}, "
                "\"reporter_evaluation\": {\"summary\": str, \"status\": str, \"grade\": str, \"bullets\": [str]}, "
                "\"errors_weaknesses_improvement_points\": {\"summary\": str, \"bullets\": [str]}, "
                "\"full_timeline\": [{\"event\": str, \"ts\": str, \"description\": str}], "
                "\"final_operator_conclusion\": {\"summary\": str, \"current_action\": str, \"watch_next\": [str], \"thesis_invalidation\": [str]}"
                "}\n"
                "각 section의 bullets는 3~6개 정도로 충분히 자세하게 작성하세요.\n"
                "summary는 운영자가 바로 의사결정할 수 있도록 명확하게 쓰세요.\n"
                f"Input:\n{json.dumps(compact_input, ensure_ascii=False)}"
            ),
        },
    ]


def build_ai_trade_report(
    story_input: Dict[str, Any],
    *,
    enabled: Optional[bool] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    is_enabled = _env_bool("TRADE_REPORT_AI_ENABLED", True) if enabled is None else bool(enabled)
    chosen_model = (
        str(model or "").strip()
        or str(os.getenv("TRADE_REPORT_AI_MODEL", "")).strip()
        or str(os.getenv("OPENROUTER_MODEL_TRADE_REPORT", "")).strip()
    )
    if not is_enabled:
        return _fallback_report(
            story_input,
            status="disabled",
            mode="fallback",
            model=chosen_model,
            reason="TRADE_REPORT_AI_ENABLED is false",
        )

    router = LLMRouter.from_env()
    if router.client is None:
        return _fallback_report(
            story_input,
            status="unavailable",
            mode="fallback",
            model=chosen_model,
            reason="OPENROUTER_API_KEY is not configured",
        )

    temp = float(
        temperature
        if temperature is not None
        else str(os.getenv("TRADE_REPORT_AI_TEMPERATURE", "0.1")).strip() or "0.1"
    )
    token_budget = int(
        max_tokens
        if max_tokens is not None
        else str(os.getenv("TRADE_REPORT_AI_MAX_TOKENS", "1400")).strip() or "1400"
    )
    raw = ""
    try:
        raw = router.chat(
            "trade_report",
            _build_messages(story_input),
            policy={
                "temperature": temp,
                "max_tokens": max(600, token_budget),
                "response_format": {"type": "json_object"},
                **({"model": chosen_model} if chosen_model else {}),
            },
        )
    except Exception as exc:
        return _fallback_report(
            story_input,
            status="error",
            mode="fallback",
            model=chosen_model,
            reason=f"trade_report_ai_exception:{type(exc).__name__}:{exc}",
        )

    parsed = _extract_json_object(raw)
    if not parsed:
        return _fallback_report(
            story_input,
            status="parse_error",
            mode="fallback",
            model=chosen_model,
            reason="trade_report_ai returned non-JSON response",
        )

    out = _fallback_report(
        story_input,
        status="ok",
        mode="ai",
        model=chosen_model or str(router.resolve("trade_report").model),
        reason="",
    )
    out["generation"] = {
        "status": "ok",
        "mode": "ai",
        "model": _clip(chosen_model or str(router.resolve("trade_report").model), max_len=120),
        "reason": "",
    }
    out["executive_summary"] = _merge_section_with_fallback(
        _normalize_section(parsed.get("executive_summary"), default_summary=out["executive_summary"]["summary"]),
        out["executive_summary"],
    )
    out["market_context_at_entry"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("market_context_at_entry") or parsed.get("market_context"),
            default_summary=(out.get("market_context_at_entry") or {}).get("summary") or (out.get("market_context") or {}).get("summary") or "",
        ),
        out["market_context_at_entry"],
    )
    out["why_this_symbol_was_chosen"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("why_this_symbol_was_chosen") or parsed.get("why_this_symbol"),
            default_summary=(out.get("why_this_symbol_was_chosen") or {}).get("summary") or (out.get("why_this_symbol") or {}).get("summary") or "",
        ),
        out["why_this_symbol_was_chosen"],
    )
    out["entry_decision"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("entry_decision"),
            default_summary=(out.get("entry_decision") or {}).get("summary") or "",
        ),
        out["entry_decision"],
    )
    out["holding_monitoring_story"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("holding_monitoring_story") or parsed.get("monitor_trigger_reasoning"),
            default_summary=(out.get("holding_monitoring_story") or {}).get("summary") or (out.get("monitor_trigger_reasoning") or {}).get("summary") or "",
        ),
        out["holding_monitoring_story"],
    )
    out["exit_decision"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("exit_decision"),
            default_summary=(out.get("exit_decision") or {}).get("summary") or "",
        ),
        out["exit_decision"],
    )
    out["execution_quality"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("execution_quality") or parsed.get("execution_result"),
            default_summary=(out.get("execution_quality") or {}).get("summary") or (out.get("execution_result") or {}).get("summary") or "",
        ),
        out["execution_quality"],
    )
    out["scanner_filters"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("scanner_filters") or parsed.get("scanner_logic_and_filters"),
            default_summary=(out.get("scanner_filters") or {}).get("summary") or (out.get("scanner_logic_and_filters") or {}).get("summary") or "",
        ),
        out["scanner_filters"],
    )
    out["guard_approval_result"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("guard_approval_result"),
            default_summary=out["guard_approval_result"]["summary"],
        ),
        out["guard_approval_result"],
    )
    out["reporter_evaluation"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("reporter_evaluation"),
            default_summary=out["reporter_evaluation"]["summary"],
        ),
        out["reporter_evaluation"],
    )
    out["errors_weaknesses_improvement_points"] = _merge_section_with_fallback(
        _normalize_section(
            parsed.get("errors_weaknesses_improvement_points"),
            default_summary=out["errors_weaknesses_improvement_points"]["summary"],
        ),
        out["errors_weaknesses_improvement_points"],
    )
    final_conclusion = parsed.get("final_operator_conclusion") if isinstance(parsed.get("final_operator_conclusion"), dict) else {}
    out["final_operator_conclusion"] = {
        "summary": _prefer_fallback_text(final_conclusion.get("summary"), out["final_operator_conclusion"]["summary"]),
        "current_action": _clip(final_conclusion.get("current_action"), max_len=24) or out["final_operator_conclusion"]["current_action"],
        "watch_next": _listify(final_conclusion.get("watch_next"), max_items=6, max_len=200) or out["final_operator_conclusion"]["watch_next"],
        "thesis_invalidation": _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=200)
        or out["final_operator_conclusion"]["thesis_invalidation"],
    }
    timeline_rows: List[Dict[str, Any]] = []
    parsed_timeline = parsed.get("full_timeline")
    if isinstance(parsed_timeline, list):
        timeline_rows = [row for row in parsed_timeline if isinstance(row, dict)][:24]
    if not timeline_rows:
        timeline_rows = [row for row in list(parsed.get("timeline") or []) if isinstance(row, dict)][:24]
    if timeline_rows:
        out["full_timeline"] = timeline_rows
        out["timeline"] = timeline_rows

    # Backward-compatible aliases for existing UI renderers.
    out["market_context"] = dict(out.get("market_context_at_entry") or {})
    out["why_this_symbol"] = dict(out.get("why_this_symbol_was_chosen") or {})
    out["scanner_logic_and_filters"] = dict(out.get("scanner_filters") or {})
    out["monitor_trigger_reasoning"] = dict(out.get("holding_monitoring_story") or {})
    out["execution_result"] = dict(out.get("execution_quality") or {})
    return _normalize_trade_report_output(story_input, out)


def render_trade_report_markdown(report: Dict[str, Any]) -> str:
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
    lines.append(f"# Trade Report ({report.get('trade_id') or report.get('story_id') or report.get('run_id') or 'story'})")
    lines.append("")
    lines.append(f"- action: **{report.get('action') or '-'} {report.get('symbol') or '-'}**")
    lines.append(f"- lifecycle_status: **{report.get('status') or '-'}**")
    lines.append(f"- story_type: **{report.get('story_type') or '-'}**")
    lines.append(f"- execution_mode: **{report.get('execution_mode_label') or '-'}**")
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    lines.append(
        f"- report_generation: status=`{generation.get('status') or '-'}` mode=`{generation.get('mode') or '-'}` "
        f"model=`{generation.get('model') or '-'}`"
    )
    lines.append("")
    if monitor_snapshot:
        lines.append("## Monitor Snapshot")
        lines.append("")
        lines.append(f"- posture: **{monitor_snapshot.get('posture') or '-'}**")
        lines.append(f"- trigger_type: **{monitor_snapshot.get('trigger_type') or '-'}**")
        lines.append(f"- effective_stop: **{_fmt_pct(monitor_snapshot.get('effective_stop_loss_pct'))}**")
        lines.append(f"- effective_stop_reason: {monitor_snapshot.get('effective_stop_reason') or '-'}")
        lines.append(f"- take_profit: {_fmt_pct(monitor_snapshot.get('take_profit_pct'))}")
        if monitor_snapshot.get("current_price") not in (None, ""):
            lines.append(f"- current_price: {_fmt_price(monitor_snapshot.get('current_price'))}")
        if monitor_snapshot.get("average_price") not in (None, ""):
            lines.append(f"- average_price: {_fmt_price(monitor_snapshot.get('average_price'))}")
        if monitor_snapshot.get("peak_price") not in (None, ""):
            lines.append(f"- peak_price: {_fmt_price(monitor_snapshot.get('peak_price'))}")
        if monitor_snapshot.get("current_drawdown") not in (None, ""):
            lines.append(f"- current_drawdown: {_fmt_pct(monitor_snapshot.get('current_drawdown'))}")
        if monitor_snapshot.get("peak_drawdown") not in (None, ""):
            lines.append(f"- peak_drawdown: {_fmt_pct(monitor_snapshot.get('peak_drawdown'))}")
        if monitor_snapshot.get("vwap_distance") not in (None, ""):
            lines.append(f"- vwap_distance: {_fmt_pct(monitor_snapshot.get('vwap_distance'))}")
        if str(monitor_snapshot.get("active_exit_axis") or "").strip():
            lines.append(f"- active_exit_axis: {monitor_snapshot.get('active_exit_axis')}")
        for axis in list(monitor_snapshot.get("watch_axes") or [])[:6]:
            lines.append(f"- watch_axis: {axis}")
        lines.append(f"- price_source: {monitor_snapshot.get('price_source') or '-'}")
        lines.append(f"- feature_source: {monitor_snapshot.get('feature_source') or '-'}")
        if str(monitor_snapshot.get('price_source_policy') or '').strip():
            lines.append(f"- price_source_policy: {monitor_snapshot.get('price_source_policy')}")
        lines.append(f"- exit_triggered: {'yes' if monitor_snapshot.get('exit_triggered') else 'no'}")
        lines.append("")

    def _section(title: str, section: Dict[str, Any], *, bullet_key: str = "bullets") -> None:
        lines.append(f"## {title}")
        lines.append("")
        summary = _clip(section.get("summary"), max_len=2000)
        if summary:
            lines.append(summary)
            lines.append("")
        bullets = _listify(section.get(bullet_key), max_items=12, max_len=400)
        for bullet in bullets:
            lines.append(f"- {bullet}")
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

    lines.append("## Full Timeline")
    lines.append("")
    timeline = report.get("full_timeline") if isinstance(report.get("full_timeline"), list) else report.get("timeline") if isinstance(report.get("timeline"), list) else []
    if timeline:
        for row in timeline[:24]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row.get('event') or row.get('step') or row.get('label') or 'step'}: "
                f"{row.get('description') or row.get('summary') or row.get('detail') or '-'}"
            )
    else:
        lines.append("- No timeline entries were captured.")
    lines.append("")

    lines.append("## Final Operator Conclusion")
    lines.append("")
    final_summary = _clip(final_conclusion.get("summary"), max_len=2000)
    if final_summary:
        lines.append(final_summary)
        lines.append("")
    current_action = _clip(final_conclusion.get("current_action"), max_len=48)
    if current_action:
        lines.append(f"- current_action: **{current_action}**")
    for item in _listify(final_conclusion.get("watch_next"), max_items=6, max_len=220):
        lines.append(f"- watch_next: {item}")
    for item in _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=220):
        lines.append(f"- thesis_invalidation: {item}")
    lines.append("")
    return "\n".join(lines)
