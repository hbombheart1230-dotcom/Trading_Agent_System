from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _list(value: Any) -> List[Any]:
    return list(value or []) if isinstance(value, (list, tuple)) else []


def _text(value: Any) -> str:
    return str(value or "").strip()


def _scorecard_summary(scorecard: Mapping[str, Any] | None) -> str:
    row = _mapping(scorecard)
    if not row:
        return "scorecard=미확인"
    available = row.get("available")
    tags = _list(_mapping(row.get("quant_memory_feedback")).get("feedback_tags"))
    parts = [f"scorecard={'사용' if available else '미사용'}"]
    if row.get("period_key"):
        parts.append(f"period={row.get('period_key')}")
    if tags:
        parts.append("feedback=" + ", ".join(str(x) for x in tags[:4]))
    elif row.get("reason"):
        parts.append(f"reason={row.get('reason')}")
    return " / ".join(parts)


def _context_usage(row: Mapping[str, Any] | None) -> Dict[str, Any]:
    ctx = _mapping(row)
    market = _mapping(ctx.get("quant_market_context"))
    scorecard = _mapping(market.get("scorecard"))
    selected = _mapping(ctx.get("selected_symbol_quant_snapshot"))
    hold = _mapping(ctx.get("hold_quant_context"))
    carry = _mapping(ctx.get("carry_quant_context"))
    return {
        "schema_version": "strategist_quant_context_usage.v1",
        "call_kind": _text(ctx.get("call_kind")),
        "scorecard": scorecard,
        "scorecard_summary": _scorecard_summary(scorecard),
        "selected_symbol_snapshot_present": bool(selected),
        "selected_symbol_snapshot_source": _text(selected.get("source")),
        "hold_context_present": bool(hold),
        "hold_symbol": _text(hold.get("symbol")),
        "hold_monitor_reason": _text(hold.get("monitor_reason")),
        "carry_context_present": bool(carry),
        "carry_selected_symbol": _text(carry.get("selected_symbol")),
        "behavior_effect": _text(ctx.get("behavior_effect") or "observation_only"),
    }


def extract_strategist_quant_context_usage(report: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    root = _mapping(report)
    out: List[Dict[str, Any]] = []
    direct = _mapping(root.get("quant_context") or root.get("strategist_quant_context"))
    if direct:
        usage = _context_usage(direct)
        usage["stage"] = "report"
        usage["label"] = "리포트 직접 컨텍스트"
        out.append(usage)

    trace = _mapping(root.get("strategist_refresh_trace"))
    for idx, stage in enumerate(_list(trace.get("stages"))[:4], start=1):
        if not isinstance(stage, Mapping):
            continue
        ctx = _mapping(stage.get("quant_context") or stage.get("strategist_quant_context"))
        usage = _context_usage(ctx)
        if not ctx and not any(
            key in stage
            for key in (
                "quant_context_call_kind",
                "quant_scorecard_available",
                "quant_feedback_tags",
                "selected_symbol_quant_snapshot_present",
                "hold_quant_context_present",
                "carry_quant_context_present",
            )
        ):
            continue
        if not ctx:
            usage.update(
                {
                    "call_kind": _text(stage.get("quant_context_call_kind")),
                    "scorecard_summary": (
                        f"scorecard={'사용' if bool(stage.get('quant_scorecard_available')) else '미사용'}"
                    ),
                    "selected_symbol_snapshot_present": bool(stage.get("selected_symbol_quant_snapshot_present")),
                    "hold_context_present": bool(stage.get("hold_quant_context_present")),
                    "carry_context_present": bool(stage.get("carry_quant_context_present")),
                }
            )
            tags = _list(stage.get("quant_feedback_tags"))
            if tags:
                usage["scorecard_summary"] += " / feedback=" + ", ".join(str(x) for x in tags[:4])
        usage["stage"] = _text(stage.get("stage")) or f"stage_{idx}"
        usage["label"] = _text(stage.get("label")) or f"{idx}단계"
        out.append(usage)
    return out


def render_strategist_quant_context_usage_lines(report: Mapping[str, Any] | None) -> List[str]:
    rows = extract_strategist_quant_context_usage(report)
    if not rows:
        return []
    lines: List[str] = []
    for row in rows:
        parts = [
            f"call={row.get('call_kind') or '-'}",
            str(row.get("scorecard_summary") or "scorecard=미확인"),
        ]
        if row.get("selected_symbol_snapshot_present"):
            parts.append(f"selected_snapshot={row.get('selected_symbol_snapshot_source') or '있음'}")
        if row.get("hold_context_present"):
            detail = row.get("hold_symbol") or row.get("hold_monitor_reason") or "있음"
            parts.append(f"hold_context={detail}")
        if row.get("carry_context_present"):
            parts.append(f"carry_context={row.get('carry_selected_symbol') or '있음'}")
        parts.append(f"effect={row.get('behavior_effect') or 'observation_only'}")
        lines.append(f"- [{row.get('label') or row.get('stage') or '전략가 단계'}] " + " / ".join(parts))
    return lines
