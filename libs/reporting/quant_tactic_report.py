from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _mapping(value: Any) -> Dict[str, Any]:
    return dict(value or {}) if isinstance(value, Mapping) else {}


def _items(value: Any) -> List[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _fmt(value: Any) -> str:
    if value in (None, ""):
        return "-"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    return str(value)


def _pct(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        num = float(value)
    except Exception:
        return str(value)
    return f"{num * 100.0:.2f}%"


def _decision_label(value: Any) -> str:
    raw = str(value or "").strip()
    mapping = {
        "entry_ready": "진입 준비",
        "block_recommended": "진입 차단 권고",
        "wait": "대기",
        "hold_watch": "보유 관찰",
        "hard_exit": "즉시 청산 허용",
        "confirm_before_exit_recommended": "청산 전 확인 권고",
        "early_exit_warning": "조기 청산 경고",
        "exit_aligned": "청산 정합",
    }
    return mapping.get(raw, raw or "-")


def _reason_text(values: Any) -> str:
    rows = _items(values)
    return ", ".join(rows[:5]) if rows else "-"


def _monitor(report: Mapping[str, Any]) -> Dict[str, Any]:
    monitor = _mapping(report.get("monitor_snapshot"))
    if not monitor:
        monitor = _mapping(report.get("monitor_output"))
    return monitor


def quant_tactic_surface(report: Mapping[str, Any] | None) -> Dict[str, Any]:
    root = _mapping(report)
    monitor = _monitor(root)
    selection = _mapping(root.get("why_this_symbol_was_chosen"))
    scanner_trace = _mapping(selection.get("scanner_selection_trace"))
    entry_decision = _mapping(monitor.get("entry_quant_decision") or root.get("entry_quant_decision"))
    exit_decision = _mapping(monitor.get("exit_quant_decision") or root.get("exit_quant_decision"))
    factor_snapshot = _mapping(monitor.get("quant_factor_snapshot") or root.get("quant_factor_snapshot"))
    factors = _mapping(factor_snapshot.get("factors"))
    tactic_suitability = _mapping(
        selection.get("tactic_suitability")
        or scanner_trace.get("tactic_suitability")
        or entry_decision.get("tactic_suitability")
    )
    tactic_id = (
        str(entry_decision.get("tactic_id") or exit_decision.get("tactic_id") or factor_snapshot.get("tactic_id") or "").strip()
    )
    if not any((entry_decision, exit_decision, factor_snapshot, tactic_suitability, tactic_id)):
        return {}
    return {
        "schema_version": "quant_tactic_report_surface.v1",
        "tactic_id": tactic_id,
        "playbook": str(entry_decision.get("playbook") or exit_decision.get("playbook") or "").strip(),
        "entry_quant_decision": entry_decision,
        "exit_quant_decision": exit_decision,
        "factor_snapshot": factor_snapshot,
        "factors": factors,
        "tactic_suitability": tactic_suitability,
    }


def render_quant_tactic_report_lines(report: Mapping[str, Any] | None, *, compact: bool = False) -> List[str]:
    surface = quant_tactic_surface(report)
    if not surface:
        return []
    entry = _mapping(surface.get("entry_quant_decision"))
    exit_decision = _mapping(surface.get("exit_quant_decision"))
    factors = _mapping(surface.get("factors"))
    suitability = _mapping(surface.get("tactic_suitability"))
    lines: List[str] = []
    tactic = surface.get("tactic_id") or "-"
    playbook = surface.get("playbook") or "-"
    if compact:
        lines.append(f"* 전술 진단: `{tactic}` / 플레이북 `{playbook}`")
    else:
        lines.append(f"- 전술 ID: `{tactic}`")
        lines.append(f"- 플레이북: `{playbook}`")
    if suitability:
        lines.append(
            f"- 스캐너 전술 적합도: {suitability.get('tier') or '-'} "
            f"({_fmt(suitability.get('score'))})"
        )
    if entry:
        lines.append(
            f"- 진입 quant 판단: {_decision_label(entry.get('decision'))} "
            f"/ blocker={_reason_text(entry.get('blockers'))} "
            f"/ warning={_reason_text(entry.get('warnings'))}"
        )
        cost = _mapping(entry.get("cost_edge"))
        if cost:
            lines.append(
                f"- 비용 엣지: {'통과' if cost.get('ok') else '미통과'} "
                f"/ edge={_pct(cost.get('cost_adjusted_edge_pct'))} "
                f"/ drag={_pct(cost.get('cost_drag_pct'))}"
            )
        if bool(entry.get("commander_override_required")):
            lines.append(f"- commander override 필요 항목: {_reason_text(entry.get('override_reason_required_for'))}")
    if exit_decision:
        lines.append(
            f"- 청산 quant 판단: {_decision_label(exit_decision.get('decision'))} "
            f"/ hard_exit={'예' if exit_decision.get('hard_exit') else '아니오'} "
            f"/ confirmation_pending={'예' if exit_decision.get('confirmation_pending') else '아니오'}"
        )
        if exit_decision.get("early_exit_flag") or exit_decision.get("actual_hold_sec") not in (None, ""):
            window = _mapping(exit_decision.get("expected_hold_window"))
            lines.append(
                f"- 보유시간 비교: 실제 {_fmt(exit_decision.get('actual_hold_sec'))}초 "
                f"/ 기대 최소 {_fmt(window.get('min_sec'))}초 "
                f"/ mismatch={'예' if exit_decision.get('hold_window_mismatch') else '아니오'}"
            )
        if exit_decision.get("blockers") or exit_decision.get("warnings"):
            lines.append(
                f"- 청산 진단 사유: blocker={_reason_text(exit_decision.get('blockers'))} "
                f"/ warning={_reason_text(exit_decision.get('warnings'))}"
            )
    if not compact and factors:
        factor_bits = []
        for key in ("vwap_distance_pct", "volume_ratio", "cost_floor_state", "confidence_score", "human_chart_entry_score"):
            if factors.get(key) not in (None, ""):
                factor_bits.append(f"{key}={_fmt(factors.get(key))}")
        if factor_bits:
            lines.append("- 핵심 factor snapshot: " + ", ".join(factor_bits[:6]))
    return lines
