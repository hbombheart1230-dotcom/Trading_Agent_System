from __future__ import annotations

from typing import Any, Dict, List, Mapping

from libs.runtime.quant.decision import build_entry_quant_decision
from libs.runtime.quant.suitability import score_candidate_tactic_suitability


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


def _nested_dicts(value: Any, *, max_depth: int = 9) -> List[Dict[str, Any]]:
    if max_depth < 0:
        return []
    out: List[Dict[str, Any]] = []
    if isinstance(value, Mapping):
        item = dict(value)
        out.append(item)
        for child in item.values():
            out.extend(_nested_dicts(child, max_depth=max_depth - 1))
    elif isinstance(value, (list, tuple)):
        for child in value:
            out.extend(_nested_dicts(child, max_depth=max_depth - 1))
    return out


def _first_nested_mapping(root: Mapping[str, Any], key: str) -> Dict[str, Any]:
    for item in _nested_dicts(root):
        found = _mapping(item.get(key))
        if found:
            return found
    return {}


def _symbol(report: Mapping[str, Any]) -> str:
    fact_trade = _mapping(_mapping(report.get("fact_payload")).get("trade"))
    return str(
        report.get("symbol")
        or fact_trade.get("symbol")
        or _mapping(report.get("shared_facts")).get("symbol")
        or ""
    ).strip()


def _playbook(report: Mapping[str, Any], *, fallback: str = "") -> str:
    for item in (
        _mapping(report.get("strategist_summary")),
        _mapping(report.get("market_context_at_entry")),
        _mapping(report.get("market_context")),
    ):
        value = str(item.get("playbook") or item.get("selected_playbook") or "").strip()
        if value:
            return value
    return str(fallback or "").strip()


def _entry_visibility(report: Mapping[str, Any]) -> Dict[str, Any]:
    return _mapping(report.get("entry_execution_visibility"))


def _entry_info_from_visibility(visibility: Mapping[str, Any], monitor: Mapping[str, Any]) -> Dict[str, Any]:
    focus = _mapping(visibility.get("monitor_focus_context"))
    grouped = _mapping(visibility.get("entry_grouped_logic_trace"))
    cascade = _mapping(visibility.get("monitor_entry_candidate_cascade"))
    out: Dict[str, Any] = {}
    out.update(grouped)
    if focus:
        out.update(
            {
                "triggered": focus.get("entry_triggered"),
                "legacy_entry_decision": focus.get("entry_decision"),
                "guard_reason": focus.get("entry_guard_reason") or focus.get("entry_reason"),
                "reason": focus.get("entry_reason"),
                "primary_failure_axis": focus.get("entry_primary_failure_axis"),
                "cost_adjusted_edge_ok": focus.get("entry_cost_adjusted_edge_ok"),
                "cost_adjusted_edge_pct": focus.get("entry_cost_adjusted_edge_pct"),
                "cost_drag_pct": focus.get("entry_cost_drag_pct"),
                "entry_cost_filter": focus.get("entry_cost_filter"),
            }
        )
    if cascade:
        out.setdefault("reason", cascade.get("reason"))
        out.setdefault("primary_failure_axis", cascade.get("primary_failure_axis"))
    if monitor:
        out.setdefault("triggered", monitor.get("entry_triggered"))
        out.setdefault("legacy_entry_decision", monitor.get("entry_decision"))
    return {key: value for key, value in out.items() if value not in (None, "")}


def _candidate_symbol(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol") or row.get("code") or row.get("stk_cd") or row.get("ticker") or "").strip()


def _selected_candidate_row(report: Mapping[str, Any], symbol: str) -> Dict[str, Any]:
    target = str(symbol or "").strip()
    if not target:
        return {}
    candidates: List[Dict[str, Any]] = []
    for item in _nested_dicts(report):
        if _candidate_symbol(item) != target:
            continue
        if any(
            key in item
            for key in (
                "quant_factor_snapshot",
                "tactic_suitability",
                "scanner_chart_fit_score",
                "scanner_chart_fit_components",
                "score_total",
                "confidence",
            )
        ):
            candidates.append(dict(item))
    if not candidates:
        return {}

    def score(row: Mapping[str, Any]) -> tuple[int, int]:
        has_quant = 1 if _mapping(row.get("quant_factor_snapshot")) else 0
        has_suitability = 1 if _mapping(row.get("tactic_suitability")) else 0
        has_chart = 1 if row.get("scanner_chart_fit_score") not in (None, "") else 0
        # Prefer final/fallback candidates over top-pick snapshots when labels exist.
        final_hint = 1 if str(row.get("final_selected_symbol") or row.get("selected_symbol") or row.get("entry_final_symbol") or "") == target else 0
        return (has_quant + has_suitability + has_chart + final_hint, len(row))

    candidates.sort(key=score, reverse=True)
    return candidates[0]


def _scanner_chart_fit_from_row(row: Mapping[str, Any]) -> Dict[str, Any]:
    explicit = _mapping(row.get("scanner_chart_fit"))
    if explicit:
        return explicit
    if row.get("scanner_chart_fit_score") in (None, "") and not _mapping(row.get("scanner_chart_fit_components")):
        return {}
    return {
        "score": row.get("scanner_chart_fit_score"),
        "authority": str(row.get("scanner_chart_fit_authority") or ""),
        "components": _mapping(row.get("scanner_chart_fit_components")),
        "penalty": row.get("scanner_chart_fit_penalty"),
    }


def _tactic_value(value: Any) -> str:
    return str(value or "").strip()


def _tactic_sources(
    *,
    entry_decision: Mapping[str, Any],
    factor_snapshot: Mapping[str, Any],
    selected_row: Mapping[str, Any],
    tactic_suitability: Mapping[str, Any],
    exit_decision: Mapping[str, Any],
) -> List[tuple[str, str]]:
    selected_factor = _mapping(selected_row.get("quant_factor_snapshot"))
    rows = (
        ("entry_quant_decision", entry_decision.get("tactic_id")),
        ("factor_snapshot", factor_snapshot.get("tactic_id")),
        ("selected_quant_factor_snapshot", selected_factor.get("tactic_id")),
        ("selected_candidate", selected_row.get("tactical_strategy")),
        ("tactic_suitability", tactic_suitability.get("tactic_id")),
        ("exit_quant_decision", exit_decision.get("tactic_id")),
    )
    return [(source, tactic_id) for source, value in rows if (tactic_id := _tactic_value(value))]


def _tactic_mismatches(sources: List[tuple[str, str]], tactic_id: str) -> List[Dict[str, str]]:
    return [
        {"source": source, "tactic_id": value}
        for source, value in sources
        if tactic_id and value != tactic_id and source != "exit_quant_decision"
    ]


def _exit_tactic_drifts(sources: List[tuple[str, str]], tactic_id: str) -> List[Dict[str, str]]:
    return [
        {"source": source, "tactic_id": value}
        for source, value in sources
        if tactic_id and value != tactic_id and source == "exit_quant_decision"
    ]


def quant_tactic_surface(report: Mapping[str, Any] | None) -> Dict[str, Any]:
    root = _mapping(report)
    monitor = _monitor(root)
    visibility = _entry_visibility(root)
    symbol = _symbol(root)
    selection = _mapping(root.get("why_this_symbol_was_chosen"))
    scanner_trace = _mapping(selection.get("scanner_selection_trace"))
    selected_row = _selected_candidate_row(root, symbol)
    entry_decision = _mapping(
        monitor.get("entry_quant_decision")
        or root.get("entry_quant_decision")
        or _first_nested_mapping(root, "entry_quant_decision")
    )
    exit_decision = _mapping(monitor.get("exit_quant_decision") or root.get("exit_quant_decision"))
    factor_snapshot = _mapping(
        monitor.get("quant_factor_snapshot")
        or root.get("quant_factor_snapshot")
        or selected_row.get("quant_factor_snapshot")
    )
    factors = _mapping(factor_snapshot.get("factors"))
    tactic_suitability = _mapping(
        selection.get("tactic_suitability")
        or scanner_trace.get("tactic_suitability")
        or selected_row.get("tactic_suitability")
        or entry_decision.get("tactic_suitability")
    )
    tactic_sources = _tactic_sources(
        entry_decision=entry_decision,
        factor_snapshot=factor_snapshot,
        selected_row=selected_row,
        tactic_suitability=tactic_suitability,
        exit_decision=exit_decision,
    )
    tactic_id_source, tactic_id = tactic_sources[0] if tactic_sources else ("", "")
    playbook = str(entry_decision.get("playbook") or exit_decision.get("playbook") or factor_snapshot.get("playbook") or _playbook(root)).strip()
    if not tactic_suitability and selected_row:
        tactic_suitability = score_candidate_tactic_suitability(selected_row, tactic_id=tactic_id, playbook=playbook)
    if not entry_decision:
        entry_info = _entry_info_from_visibility(visibility, monitor)
        if entry_info or selected_row or factor_snapshot:
            entry_decision = build_entry_quant_decision(
                entry_info,
                selected=selected_row,
                factor_snapshot=factor_snapshot,
                state=root,
                tactic_id=tactic_id,
                playbook=playbook,
            )
    scanner_chart_fit = _mapping(selection.get("scanner_chart_fit")) or _mapping(scanner_trace.get("scanner_chart_fit")) or _scanner_chart_fit_from_row(selected_row)
    if not any((entry_decision, exit_decision, factor_snapshot, tactic_suitability, tactic_id, scanner_chart_fit)):
        return {}
    return {
        "schema_version": "quant_tactic_report_surface.v1",
        "tactic_id": tactic_id,
        "tactic_id_source": tactic_id_source,
        "tactic_id_mismatches": _tactic_mismatches(tactic_sources, tactic_id),
        "exit_tactic_drifts": _exit_tactic_drifts(tactic_sources, tactic_id),
        "playbook": playbook,
        "entry_quant_decision": entry_decision,
        "exit_quant_decision": exit_decision,
        "factor_snapshot": factor_snapshot,
        "factors": factors,
        "tactic_suitability": tactic_suitability,
        "scanner_chart_fit": scanner_chart_fit,
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
