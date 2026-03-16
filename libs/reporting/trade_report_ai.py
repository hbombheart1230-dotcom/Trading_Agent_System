from __future__ import annotations

import json
import os
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
    warnings = _listify(story_input.get("warnings"), max_items=10, max_len=260)

    action = _clip(story_input.get("action"), max_len=24) or "WAIT"
    symbol = _clip(story_input.get("symbol"), max_len=32) or "unknown"
    executive_reason = (
        _clip(operator_conclusion.get("summary"), max_len=600)
        or _clip(execution_outcome.get("summary"), max_len=600)
        or _clip(scanner_reason.get("summary"), max_len=600)
        or "The decision path was recorded, but the operator-facing summary is limited."
    )
    confidence = _clip(scanner_reason.get("confidence_label"), max_len=24) or _clip(scanner_reason.get("confidence"), max_len=24)

    return {
        "schema_version": "trade_report.v1",
        "generated_at": _utc_now_iso(),
        "story_id": _clip(story_input.get("story_id"), max_len=120),
        "run_id": _clip(story_input.get("run_id"), max_len=120),
        "symbol": symbol,
        "action": action,
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
        "market_context": {
            "summary": _clip(market_context.get("summary"), max_len=600),
            "bullets": _listify(market_context.get("bullets"), max_items=8, max_len=260),
        },
        "why_this_symbol": {
            "summary": _clip(scanner_reason.get("summary"), max_len=600),
            "bullets": _listify(scanner_reason.get("bullets"), max_items=8, max_len=260),
        },
        "scanner_logic_and_filters": {
            "summary": _clip(filters_human.get("summary"), max_len=600),
            "bullets": _listify(filters_human.get("bullets"), max_items=12, max_len=260),
        },
        "monitor_trigger_reasoning": {
            "summary": _clip(monitor_reason.get("summary"), max_len=600),
            "bullets": _listify(monitor_reason.get("bullets"), max_items=8, max_len=260),
        },
        "guard_approval_result": {
            "summary": _clip(guard_reason.get("summary"), max_len=600),
            "bullets": _listify(guard_reason.get("bullets"), max_items=8, max_len=260),
        },
        "execution_result": {
            "summary": _clip(execution_outcome.get("summary"), max_len=600),
            "bullets": _listify(execution_outcome.get("bullets"), max_items=8, max_len=260),
        },
        "reporter_evaluation": {
            "summary": _clip(reporter_status.get("summary"), max_len=600),
            "status": _clip(reporter_status.get("status"), max_len=40),
            "grade": _clip(reporter_status.get("grade"), max_len=16),
            "bullets": _listify(reporter_status.get("bullets"), max_items=8, max_len=260),
        },
        "errors_weaknesses_improvement_points": {
            "summary": (
                "Warnings and missing links were recorded for operator follow-up."
                if warnings
                else "No explicit weaknesses were surfaced beyond the recorded trace."
            ),
            "bullets": warnings,
        },
        "timeline": [
            row
            for row in list(story_input.get("timeline") or [])
            if isinstance(row, dict)
        ][:12],
        "final_operator_conclusion": {
            "summary": _clip(operator_conclusion.get("summary"), max_len=600) or executive_reason,
            "current_action": _clip(operator_conclusion.get("current_action"), max_len=24) or action,
            "watch_next": _listify(operator_conclusion.get("watch_next"), max_items=6, max_len=200),
            "thesis_invalidation": _listify(operator_conclusion.get("thesis_invalidation"), max_items=6, max_len=200),
        },
    }


def _build_messages(story_input: Dict[str, Any]) -> List[Dict[str, str]]:
    compact_input = {
        "story_id": story_input.get("story_id"),
        "run_id": story_input.get("run_id"),
        "symbol": story_input.get("symbol"),
        "action": story_input.get("action"),
        "story_type": story_input.get("story_type"),
        "execution_mode_label": story_input.get("execution_mode_label"),
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
                "You are writing a per-trade operator memo for a trading system. "
                "Use only the provided facts. Do not invent numbers or events. "
                "Return strict JSON only."
            ),
        },
        {
            "role": "user",
            "content": (
                "Turn this trade story input into an operator-friendly report.\n"
                "Return JSON with these keys:\n"
                "{"
                "\"executive_summary\": {\"headline\": str, \"action\": str, \"symbol\": str, \"confidence\": str, \"summary\": str}, "
                "\"market_context\": {\"summary\": str, \"bullets\": [str]}, "
                "\"why_this_symbol\": {\"summary\": str, \"bullets\": [str]}, "
                "\"scanner_logic_and_filters\": {\"summary\": str, \"bullets\": [str]}, "
                "\"monitor_trigger_reasoning\": {\"summary\": str, \"bullets\": [str]}, "
                "\"guard_approval_result\": {\"summary\": str, \"bullets\": [str]}, "
                "\"execution_result\": {\"summary\": str, \"bullets\": [str]}, "
                "\"reporter_evaluation\": {\"summary\": str, \"status\": str, \"grade\": str, \"bullets\": [str]}, "
                "\"errors_weaknesses_improvement_points\": {\"summary\": str, \"bullets\": [str]}, "
                "\"final_operator_conclusion\": {\"summary\": str, \"current_action\": str, \"watch_next\": [str], \"thesis_invalidation\": [str]}"
                "}\n"
                "Keep wording concise, explicit, and operator-facing.\n"
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
    out["executive_summary"] = _normalize_section(parsed.get("executive_summary"), default_summary=out["executive_summary"]["summary"])
    out["market_context"] = _normalize_section(parsed.get("market_context"), default_summary=out["market_context"]["summary"])
    out["why_this_symbol"] = _normalize_section(parsed.get("why_this_symbol"), default_summary=out["why_this_symbol"]["summary"])
    out["scanner_logic_and_filters"] = _normalize_section(
        parsed.get("scanner_logic_and_filters"),
        default_summary=out["scanner_logic_and_filters"]["summary"],
    )
    out["monitor_trigger_reasoning"] = _normalize_section(
        parsed.get("monitor_trigger_reasoning"),
        default_summary=out["monitor_trigger_reasoning"]["summary"],
    )
    out["guard_approval_result"] = _normalize_section(
        parsed.get("guard_approval_result"),
        default_summary=out["guard_approval_result"]["summary"],
    )
    out["execution_result"] = _normalize_section(parsed.get("execution_result"), default_summary=out["execution_result"]["summary"])
    out["reporter_evaluation"] = _normalize_section(
        parsed.get("reporter_evaluation"),
        default_summary=out["reporter_evaluation"]["summary"],
    )
    out["errors_weaknesses_improvement_points"] = _normalize_section(
        parsed.get("errors_weaknesses_improvement_points"),
        default_summary=out["errors_weaknesses_improvement_points"]["summary"],
    )
    final_conclusion = parsed.get("final_operator_conclusion") if isinstance(parsed.get("final_operator_conclusion"), dict) else {}
    out["final_operator_conclusion"] = {
        "summary": _clip(final_conclusion.get("summary"), max_len=600) or out["final_operator_conclusion"]["summary"],
        "current_action": _clip(final_conclusion.get("current_action"), max_len=24) or out["final_operator_conclusion"]["current_action"],
        "watch_next": _listify(final_conclusion.get("watch_next"), max_items=6, max_len=200) or out["final_operator_conclusion"]["watch_next"],
        "thesis_invalidation": _listify(final_conclusion.get("thesis_invalidation"), max_items=6, max_len=200)
        or out["final_operator_conclusion"]["thesis_invalidation"],
    }
    return out


def render_trade_report_markdown(report: Dict[str, Any]) -> str:
    executive = report.get("executive_summary") if isinstance(report.get("executive_summary"), dict) else {}
    market_context = report.get("market_context") if isinstance(report.get("market_context"), dict) else {}
    why_symbol = report.get("why_this_symbol") if isinstance(report.get("why_this_symbol"), dict) else {}
    scanner_logic = report.get("scanner_logic_and_filters") if isinstance(report.get("scanner_logic_and_filters"), dict) else {}
    monitor_reason = report.get("monitor_trigger_reasoning") if isinstance(report.get("monitor_trigger_reasoning"), dict) else {}
    guard_result = report.get("guard_approval_result") if isinstance(report.get("guard_approval_result"), dict) else {}
    execution_result = report.get("execution_result") if isinstance(report.get("execution_result"), dict) else {}
    reporter_eval = report.get("reporter_evaluation") if isinstance(report.get("reporter_evaluation"), dict) else {}
    weak_points = (
        report.get("errors_weaknesses_improvement_points")
        if isinstance(report.get("errors_weaknesses_improvement_points"), dict)
        else {}
    )
    final_conclusion = report.get("final_operator_conclusion") if isinstance(report.get("final_operator_conclusion"), dict) else {}

    lines: List[str] = []
    lines.append(f"# Trade Report ({report.get('story_id') or report.get('run_id') or 'story'})")
    lines.append("")
    lines.append(f"- action: **{report.get('action') or '-'} {report.get('symbol') or '-'}**")
    lines.append(f"- story_type: **{report.get('story_type') or '-'}**")
    lines.append(f"- execution_mode: **{report.get('execution_mode_label') or '-'}**")
    generation = report.get("generation") if isinstance(report.get("generation"), dict) else {}
    lines.append(
        f"- report_generation: status=`{generation.get('status') or '-'}` mode=`{generation.get('mode') or '-'}` "
        f"model=`{generation.get('model') or '-'}`"
    )
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
    _section("Market Context", market_context)
    _section("Why This Symbol", why_symbol)
    _section("Scanner Logic and Filters", scanner_logic)
    _section("Monitor / Trigger Reasoning", monitor_reason)
    _section("Guard / Approval Result", guard_result)
    _section("Execution Result", execution_result)
    _section("Reporter Evaluation", reporter_eval)
    _section("Errors / Weaknesses / Improvement Points", weak_points)

    lines.append("## Timeline")
    lines.append("")
    timeline = report.get("timeline") if isinstance(report.get("timeline"), list) else []
    if timeline:
        for row in timeline[:12]:
            if not isinstance(row, dict):
                continue
            lines.append(
                f"- {row.get('step') or row.get('label') or 'step'}: "
                f"{row.get('summary') or row.get('detail') or '-'}"
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
