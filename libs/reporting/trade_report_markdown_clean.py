from __future__ import annotations

import html
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from libs.reporting.trade_report_markdown_truth import (
    boolish as _boolish_impl,
    build_trade_cost_analysis as _build_trade_cost_analysis_impl,
    extract_trade_quantity as _extract_trade_quantity_impl,
    first_present as _first_present_impl,
    get_truth_surface as _get_truth_surface_impl,
    infer_trade_quantity_from_costs as _infer_trade_quantity_from_costs_impl,
    operator_pnl_pct as _operator_pnl_pct_impl,
    pnl_basis_label as _pnl_basis_label_impl,
    trade_cost_analysis_lines as _trade_cost_analysis_lines_impl,
    truth_source_label as _truth_source_label_impl,
)
from libs.reporting.trade_report_markdown_scanner import (
    build_scanner_comparison as _build_scanner_comparison_impl,
    build_symbol_selection as _build_symbol_selection_impl,
    is_redundant_symbol_selection_line as _is_redundant_symbol_selection_line_impl,
    is_scanner_execution_mismatch_line as _is_scanner_execution_mismatch_line_impl,
    is_scanner_selection_label_line as _is_scanner_selection_label_line_impl,
)
from libs.reporting.trade_report_markdown_monitor import (
    build_exit_decision as _build_exit_decision_impl,
    build_holding_story as _build_holding_story_impl,
    build_monitor_snapshot as _build_monitor_snapshot_impl,
    closed_trade_monitor_preface as _closed_trade_monitor_preface_impl,
    normalize_monitor_story_line as _normalize_monitor_story_line_impl,
    parse_monitor_bullet as _parse_monitor_bullet_impl,
    price_source_label as _price_source_label_impl,
    price_source_policy_label as _price_source_policy_label_impl,
)
from libs.reporting.trade_report_markdown_strategy_memory import (
    build_strategy_horizon_lines as _build_strategy_horizon_lines_impl,
    duration_label_compact as _duration_label_compact_impl,
    hold_window_label as _hold_window_label_impl,
    strategy_horizon_alignment_label as _strategy_horizon_alignment_label_impl,
    strategy_horizon_label as _strategy_horizon_label_impl,
    strategy_horizon_reason_label as _strategy_horizon_reason_label_impl,
    strategy_horizon_report_surface as _strategy_horizon_report_surface_impl,
)
from libs.reporting.trade_report_symbol_metadata import (
    append_theme_values as _append_theme_values_impl,
    append_unique_text as _append_unique_text_impl,
    component_themes_for_symbol as _component_themes_for_symbol_impl,
    infer_symbol_name_from_report_text as _infer_symbol_name_from_report_text_impl,
    iter_nested_dicts as _iter_nested_dicts_impl,
    iter_trade_symbol_metadata_sources as _iter_trade_symbol_metadata_sources_impl,
    looks_like_symbol_name as _looks_like_symbol_name_impl,
    resolve_trade_symbol_metadata as _resolve_trade_symbol_metadata_impl,
    symbol_in_theme_components as _symbol_in_theme_components_impl,
)
from libs.reporting.trade_report_post_exit_shadow import (
    build_post_exit_shadow_summary_lines as _build_post_exit_shadow_summary_lines_impl,
    checkpoint_label as _checkpoint_label_impl,
    compact_post_exit_shadow as _compact_post_exit_shadow_impl,
    post_exit_shadow_surface as _post_exit_shadow_surface_impl,
)
from libs.reporting.quant_tactic_report import (
    quant_tactic_surface as _quant_tactic_surface_impl,
    render_quant_tactic_report_lines as _render_quant_tactic_report_lines_impl,
)
from libs.reporting.strategist_quant_context_report import (
    render_strategist_quant_context_usage_lines as _render_strategist_quant_context_usage_lines_impl,
)
from libs.reporting.controlled_mock_lane_report import (
    render_controlled_lane_report_lines as _render_controlled_lane_report_lines,
)


def _same_day_current_result(report: Dict[str, Any]) -> Dict[str, Any]:
    truth_surface = _as_dict(report.get("truth_surface"))
    status = _as_dict(truth_surface.get("status"))
    status_text = str(status.get("status") or report.get("status") or "").strip().lower()
    if status_text != "closed":
        return {}
    pnl = _as_dict(truth_surface.get("pnl"))
    pnl_value = _num_opt(pnl.get("value"))
    pnl_pct = _num_opt(pnl.get("pct"))
    if pnl_value is None and pnl_pct is None:
        return {}
    classification_value = pnl_value if pnl_value is not None else pnl_pct
    if classification_value is None:
        return {}
    pct_text = ""
    if pnl_pct is not None:
        pct_percent = pnl_pct * 100.0 if abs(pnl_pct) <= 1.0 else pnl_pct
        pct_text = f"{pct_percent:.2f}"
    return {
        "classification": 1 if classification_value > 0 else (-1 if classification_value < 0 else 0),
        "pct_text": pct_text,
    }


def _same_day_summary_from_texts(
    texts: Iterable[Any],
    fallback: str = "",
    current_result: Dict[str, Any] | None = None,
) -> str:
    """Normalize same-day trade summary without treating unknown PnL as flat."""

    translated_texts: List[str] = []
    for raw in texts:
        text = _translate_text(raw).strip()
        if text:
            translated_texts.append(text)

    for text in translated_texts:
        closed_match = re.search(
            r"(?:closed trade|닫힌 거래|총 거래).*?(\d+)\s*(?:건|trades?)",
            text,
            flags=re.IGNORECASE,
        )
        if not closed_match:
            continue
        win_loss_match = None
        for pattern in (
            r"(?:승\s*/\s*패|승패|승률)\s*(\d+)\s*/\s*(\d+)",
            r"(\d+)\s*승\s*/\s*(\d+)\s*패",
            r"(\d+)\s*wins?\D+(\d+)\s*loss",
        ):
            win_loss_match = re.search(pattern, text, flags=re.IGNORECASE)
            if win_loss_match:
                break
        if not win_loss_match:
            continue

        avg_match = re.search(
            r"(확인분\s*)?평균(?:\s*손익률|\s*손익)?\s*([+-]?\d+(?:\.\d+)?)(%)?",
            text,
            flags=re.IGNORECASE,
        )
        avg_source_is_ratio = False
        if not avg_match:
            avg_match = re.search(
                r"(?:avg pnl pct|average same-day pnl pct)\s*([+-]?\d+(?:\.\d+)?)(%)?",
                text,
                flags=re.IGNORECASE,
            )
            avg_source_is_ratio = bool(avg_match and not avg_match.group(2))
        unknown_match = re.search(r"(?:손익\s*)?미확정\s*(\d+)\s*건", text) or re.search(
            r"(\d+)\s*unknown pnl",
            text,
            flags=re.IGNORECASE,
        )
        flat_match = re.search(r"보합\s*(\d+)\s*건", text) or re.search(
            r"(\d+)\s*flat",
            text,
            flags=re.IGNORECASE,
        )

        closed = int(closed_match.group(1))
        wins = int(win_loss_match.group(1))
        losses = int(win_loss_match.group(2))
        unknown = int(next(group for group in unknown_match.groups() if group)) if unknown_match else 0
        flat = int(next(group for group in flat_match.groups() if group)) if flat_match else 0
        avg_text = ""
        avg_confirmed = False
        if avg_match:
            if len(avg_match.groups()) > 2:
                avg_confirmed = bool(avg_match.group(1))
                avg_text = avg_match.group(2)
            else:
                avg_text = avg_match.group(1)

        avg_num = None
        if avg_text:
            try:
                avg_num = float(avg_text)
            except (TypeError, ValueError):
                avg_num = None
        if avg_source_is_ratio and avg_num is not None and abs(avg_num) <= 1.0:
            avg_num *= 100.0
            avg_text = f"{avg_num:.2f}"
            avg_confirmed = True
        if (
            unknown <= 0
            and closed > 0
            and wins == 0
            and losses == 0
            and flat == 0
            and avg_num == 0.0
        ):
            unknown = closed
            avg_text = ""
        current = dict(current_result or {})
        current_classification = current.get("classification")
        if (
            (unknown == closed or closed == 1)
            and current_classification in (-1, 0, 1)
        ):
            wins = 1 if current_classification > 0 else 0
            losses = 1 if current_classification < 0 else 0
            flat = 1 if current_classification == 0 else 0
            unknown = max(0, closed - wins - losses - flat)
            current_pct_text = str(current.get("pct_text") or "").strip()
            if current_pct_text:
                avg_text = current_pct_text
                avg_confirmed = True
        accounted = wins + losses + flat
        if accounted >= closed:
            flat = max(0, closed - wins - losses)
            unknown = 0
        else:
            unknown = max(0, min(unknown, closed - accounted))

        parts = [f"{closed}건 중 {wins}승 / {losses}패"]
        if flat > 0:
            parts.append(f"{flat}건 보합")
        if unknown > 0:
            parts.append(f"{unknown}건 손익 미확정")
        if avg_text:
            avg_label = "확인분 평균" if unknown > 0 or avg_confirmed else "평균"
            parts.append(f"{avg_label} {avg_text}%")
        return " / ".join(parts)

    for text in translated_texts:
        lowered = text.lower()
        if "closed trade" in lowered or "닫힌 거래" in text or "평균 손익" in text:
            return text.rstrip(".")
    return fallback


def render_trade_report_markdown_clean(report: Dict[str, Any]) -> str:
    lines: List[str] = []

    trade_id = _clip(report.get("trade_id"), 80) or "-"
    action = _action_label(report.get("action"))
    symbol = _clip(report.get("symbol"), 32) or "해당 종목"
    status = _status_label(report.get("status"))
    story_type = _story_type_label(report.get("story_type"))
    execution_mode = _execution_mode_label(report.get("execution_mode_label"))

    lines.append(f"# AI 거래 리포트 ({trade_id})")
    lines.append("")
    lines.append(f"- 이번 거래는 {action} {symbol} 기준으로 정리했습니다.")
    lines.append(f"- 라이프사이클 상태는 {status}입니다.")
    lines.append(f"- 리포트 유형은 {story_type}입니다.")
    lines.append(f"- 실행 모드는 {execution_mode}입니다.")

    lines.extend(_section("생성 정보", _build_generation_info(report)))
    lines.extend(_section("Truth Surface", _build_truth_surface(report)))
    lines.extend(_section("전략가 프롬프트에서 직접 확인된 메모리", _build_prompt_proven_memory(report)))
    lines.extend(_section("거래 설명용 사후 복원 메모리", _build_reconstructed_trade_memory(report)))
    lines.extend(_section("실제로 적용된 결정론적 메모리 bias", _build_memory_application(report)))
    lines.extend(_section("시장 환경 요약", _build_market_context(report)))
    lines.extend(_section("전략가 요약", _build_strategist_summary(report)))
    lines.extend(_section("전략 보유 기간", _build_strategy_horizon_lines(report)))
    lines.extend(_section("통제 모의투자 레인 근거", _render_controlled_lane_report_lines(report)))
    lines.extend(_section("전략가 Refresh Trace", _build_strategist_refresh_trace(report)))
    lines.extend(_section("전략가 Quant Context 사용", _render_strategist_quant_context_usage_lines_impl(report)))
    lines.extend(_section("전략가 출력 근거", _build_strategist_output_surface(report)))
    lines.extend(_section("전술/퀀트 진단", _render_quant_tactic_report_lines_impl(report)))
    lines.extend(_section("선택된 종목 상세 분석", _build_symbol_selection(report)))
    lines.extend(_section("스캐너 후보 비교", _build_scanner_comparison(report)))
    lines.extend(_section("가드 승인 결과", _build_guard_approval(report)))
    lines.extend(_section("진입 상세 근거", _build_entry_decision(report)))
    lines.extend(_section("보유 경과", _build_holding_story(report)))
    lines.extend(_section("청산 판단 근거", _build_exit_decision(report)))
    post_exit_shadow_lines = _build_post_exit_shadow_summary_lines(report)
    if post_exit_shadow_lines:
        if str(post_exit_shadow_lines[0]).strip() == "### 매도 후 가격 추적 (관측-only)":
            post_exit_shadow_lines = post_exit_shadow_lines[2:]
        lines.extend(_section("매도 후 가격 추적 (관측-only)", post_exit_shadow_lines))
    lines.extend(_section("모니터 스냅샷", _build_monitor_snapshot(report)))
    lines.extend(_section("실행 결과", _build_execution_quality(report)))
    lines.extend(_section("결과 평가", _build_reporter_evaluation(report)))
    lines.extend(_section("보완 사안", _build_weaknesses(report)))
    lines.extend(_section("근거 출처", _build_provenance(report)))
    lines.extend(_section("전체 타임라인", _build_timeline(report)))
    lines.extend(_section("최종 운영 판단", _build_final_conclusion(report)))

    return "\n".join(_strip_trailing_blanks(lines)).strip() + "\n"


def render_trade_summary_markdown_clean(report: Dict[str, Any]) -> str:
    """Render the short operator-facing summary next to ai_trade_report.md."""

    def _pick(*values: Any) -> Any:
        for value in values:
            if value not in (None, ""):
                return value
        return ""

    def _money(value: Any) -> str:
        num = _num_opt(value)
        if num is None:
            return "-"
        if abs(num) >= 100:
            return f"{num:,.0f}"
        return f"{num:,.2f}".rstrip("0").rstrip(".")

    def _compact_number(value: Any) -> str:
        num = _num_opt(value)
        if num is not None:
            rendered = f"{num:.6f}".rstrip("0").rstrip(".")
            return rendered or "0"
        text = str(value if value is not None else "").strip()
        return _metadata_value(text) or "-"

    def _compact_decimal(value: Any, digits: int = 2) -> str:
        num = _num_opt(value)
        if num is None:
            return _metadata_value(value) or "-"
        return f"{num:.{digits}f}"

    def _first_matching_line(values: Iterable[Any], needles: Iterable[str]) -> str:
        lowered_needles = [needle.lower() for needle in needles]
        for raw in values:
            text = _translate_text(raw).strip()
            if not text:
                continue
            lowered = text.lower()
            if any(needle in lowered for needle in lowered_needles):
                return text.rstrip(".")
        return ""

    def _section_texts(*sections: Dict[str, Any]) -> List[str]:
        texts: List[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            if section.get("summary"):
                texts.append(str(section.get("summary") or ""))
            texts.extend(str(item or "") for item in _listify(section.get("bullets")))
        return texts

    def _same_day_summary(section: Dict[str, Any]) -> str:
        return _same_day_summary_from_texts(
            _section_texts(section),
            fallback="당일 성과 집계는 리포터 평가 섹션에서 확인 필요",
            current_result=_same_day_current_result(report),
        )

    def _selected_score(selection: Dict[str, Any]) -> str:
        score = _pick(selection.get("score_total"), selection.get("selected_score"))
        trace = _as_dict(selection.get("scanner_selection_trace"))
        selected_symbol = str(_pick(selection.get("symbol"), report.get("symbol"), trace.get("monitor_selected_symbol"), trace.get("selected_symbol")) or "").strip()
        if score in (None, "") and _selection_fallback_context(selection, selected_symbol).get("used"):
            news = _as_dict(trace.get("news_scanner_contribution"))
            score = _pick(trace.get("selected_score"), news.get("selected_score_total"))
        if score in (None, ""):
            for row in _listify(trace.get("ranked_candidates")):
                row_obj = _as_dict(row)
                if str(row_obj.get("symbol") or "").strip() == selected_symbol:
                    score = _pick(row_obj.get("score_total"), row_obj.get("score"))
                    break
        num = _num_opt(score)
        return f"{num:.3f}" if num is not None else "-"

    def _selected_rank(selection: Dict[str, Any]) -> str:
        trace = _as_dict(selection.get("scanner_selection_trace"))
        rank = _pick(selection.get("selected_rank"), trace.get("selected_rank"), selection.get("scanner_rank"))
        return str(rank) if rank not in (None, "") else "-"

    def _extract_run_id(timeline: Iterable[Any], event_name: str) -> str:
        for row in timeline:
            row_obj = _as_dict(row)
            event = str(_pick(row_obj.get("event"), row_obj.get("step")) or "").lower()
            if event_name not in event:
                continue
            direct = _pick(row_obj.get("run_id"), row_obj.get("id"))
            if direct:
                return str(direct)
            desc = str(_pick(row_obj.get("description"), row_obj.get("summary")) or "")
            match = re.search(r"\brun\s+([0-9a-f]{8,64})\b", desc, flags=re.IGNORECASE)
            if match:
                return match.group(1)
        return "-"

    def _policy_delta_lines(memory_app: Dict[str, Any]) -> List[str]:
        monitor = _as_dict(memory_app.get("monitor_memory_bias"))
        scanner = _as_dict(memory_app.get("scanner_memory_bias"))
        lines_out = [
            f"* 스캐너 메모리: {_applied_label(scanner.get('applied'))}",
            f"* 모니터 메모리: {_applied_label(monitor.get('applied'))}"
            + (f" ({_memory_layers_text(monitor.get('active_layers'))} 레벨)" if monitor.get("active_layers") else ""),
        ]
        deltas: List[str] = []
        for row in _listify(monitor.get("applied_deltas")) + _listify(monitor.get("exit_deltas")):
            row_obj = _as_dict(row)
            field = str(row_obj.get("field") or "").strip()
            if not field:
                continue
            before = row_obj.get("from")
            after = row_obj.get("to")
            deltas.append(f"* {field}: {_compact_number(before)} → {_compact_number(after)}")
        if deltas:
            lines_out.append("")
            lines_out.append("### 정책 변화")
            lines_out.extend(deltas[:4])
        return lines_out

    shared = _as_dict(report.get("shared_facts"))
    truth = _get_truth_surface(report)
    truth_price = _as_dict(truth.get("price"))
    truth_pnl = _as_dict(truth.get("pnl"))
    market = _resolve_market_context(report)
    strategist = _as_dict(report.get("strategist_summary"))
    selection = _as_dict(report.get("why_this_symbol_was_chosen"))
    entry = _as_dict(report.get("entry_decision"))
    holding = _as_dict(report.get("holding_monitoring_story"))
    exit_decision = _as_dict(report.get("exit_decision"))
    execution = _as_dict(report.get("execution_quality"))
    reporter_eval = _as_dict(report.get("reporter_evaluation"))
    memory_app = _as_dict(report.get("memory_application_surface"))
    monitor = _as_dict(report.get("monitor_snapshot"))
    entry_signal_snapshot = _resolve_entry_signal_snapshot(report)
    entry_signal_metric_lines = _entry_signal_metric_summary_lines(entry_signal_snapshot)
    final = _as_dict(report.get("final_operator_conclusion"))
    timeline = _listify(report.get("full_timeline") if isinstance(report.get("full_timeline"), list) else report.get("timeline"))

    trade_id = _clip(report.get("trade_id") or report.get("story_id"), 80) or "-"
    symbol = _clip(_pick(report.get("symbol"), shared.get("symbol")), 32) or "-"
    symbol_metadata = _resolve_trade_symbol_metadata(report, symbol)
    symbol_name = str(symbol_metadata.get("symbol_name") or "").strip()
    symbol_theme = str(symbol_metadata.get("theme") or "").strip()
    status = _status_label(_pick(report.get("status"), shared.get("status")))
    story_type = _story_type_label(report.get("story_type"))
    execution_mode = _execution_mode_label(report.get("execution_mode_label"))
    action = _action_label(_pick(final.get("current_action"), report.get("action"), shared.get("action")))

    pnl = _pick(truth_pnl.get("value"), shared.get("pnl"))
    pnl_pct, pnl_pct_is_observation = _operator_pnl_pct(truth_pnl, shared)
    pnl_num = _num_opt(pnl)
    pnl_label_basis = pnl_num if pnl_num is not None else _num_opt(pnl_pct)
    result_label = "보합"
    if pnl_label_basis is not None and pnl_label_basis > 0:
        result_label = "이익"
    elif pnl_label_basis is not None and pnl_label_basis < 0:
        result_label = "손실"
    result_basis_label = " 관측" if pnl_num is None and pnl_pct_is_observation else ""
    result_text = (
        f"{result_label}{result_basis_label} ({_fmt_pct(pnl_pct)})"
        if pnl_pct not in (None, "")
        else result_label
    )

    same_day = _same_day_summary(reporter_eval)
    combined_texts = _section_texts(market, strategist, selection, entry, holding, exit_decision, reporter_eval)
    combined_blob = "\n".join(combined_texts).lower()
    entry_blob = "\n".join(_section_texts(selection, entry)).lower()
    exit_blob = "\n".join(_section_texts(exit_decision, holding)).lower()
    cost_analysis = _build_trade_cost_analysis(report)
    cost_drag_pct = _num_opt(cost_analysis.get("cost_drag_pct"))
    holding_duration_summary = _authoritative_holding_duration_label(report) or _pick(
        shared.get("holding_duration"), report.get("hold_duration"), ""
    )
    rank_num = _num_opt(_selected_rank(selection))
    selection_fallback_summary = _selection_fallback_context(selection, symbol)
    scanner_top_pick = _metadata_value(selection_fallback_summary.get("scanner_top_pick_symbol"))
    recovered_partial_exit = _is_recovered_partial_exit_report(report)
    carryover_context = _carryover_context(report)
    carryover_exit = bool(carryover_context.get("is_carryover_exit"))
    exit_only_report = recovered_partial_exit or carryover_exit
    if exit_only_report:
        rank_num = None
    normalized_exit_reason = _normalize_exit_trigger_label(shared.get("exit_reason"), "")
    actual_take_profit = normalized_exit_reason == "목표 수익 실현 기준"
    actual_peak_exit = (
        normalized_exit_reason == "고점 대비 하락폭 기준"
        or (
            not normalized_exit_reason
            and (
                "peak_drawdown" in exit_blob
                or "고점 대비 하락폭 기준" in exit_blob
                or "고점 대비 하락폭으로 청산" in exit_blob
                or "고점 대비 하락폭 축" in exit_blob
            )
        )
    )
    actual_hard_stop = normalized_exit_reason == "고정 손절 기준"

    positives = []
    broker_fill_present = truth_price.get("broker_fill_price") not in (None, "")
    realized_pnl_present = str(truth_pnl.get("value") or shared.get("pnl") or "").strip().lower() not in {
        "",
        "unavailable",
        "not_available",
        "none",
        "-",
    }
    if broker_fill_present and realized_pnl_present:
        positives.append("키움 체결가와 당일 실현손익 확보")
    elif broker_fill_present:
        positives.append("브로커 체결가 확보, 실현손익/비용은 확인 대기")
    if carryover_exit:
        positives.append("오버나이트/주말 이월 청산을 신규 선정 평가와 분리해 기록")
    elif recovered_partial_exit:
        positives.append("회수/partial 청산을 신규 진입 평가와 분리해 기록")
    elif rank_num is not None:
        positives.append(f"스캐너 순위 {int(rank_num)}위와 모니터 재평가 경로 기록")
    elif strategist or selection or entry or exit_decision:
        positives.append("전략 → 스캐너 → 모니터 판단 흐름 기록")
    if holding_duration_summary and not _is_not_captured(holding_duration_summary):
        positives.append(f"보유 시간 {holding_duration_summary}와 청산 트리거 기록")
    elif entry or exit_decision or memory_app:
        positives.append("진입/청산 근거 및 정책 추적 가능")
    if not positives:
        positives.append("핵심 거래 아티팩트가 보존됨")

    problems: List[str] = []
    monitor_line = _first_matching_line(combined_texts, ["monitor_only", "monitor-only", "monitor 단독"])
    if monitor_line:
        problems.append("당일 monitor_only 경로 비중 높음")
    if carryover_exit:
        problems.append("오늘 신규 진입이 아니라 전일/주말 이월 포지션으로 별도 해석 필요")
    if recovered_partial_exit:
        problems.append("당일 BUY 근거가 없어 신규 진입 품질 평가는 제외 필요")
    if cost_analysis.get("mock_cost_warning") and cost_drag_pct is not None:
        problems.append(f"모의투자 비용 드래그 {_fmt_pct(cost_drag_pct)} 별도 해석 필요")
    if selection_fallback_summary.get("used") or (rank_num is not None and rank_num > 1):
        if scanner_top_pick and scanner_top_pick != "-":
            problems.append(f"1순위 {scanner_top_pick} 보류 후 {symbol} {int(rank_num) if rank_num else '-'}위 재평가 진입")
        else:
            problems.append("1순위 탈락 후 차순위 재평가 진입 구조")
    if "pullback_not_mature" in entry_blob:
        problems.append("pullback 성숙도 부족으로 진입 보류 발생")
    if actual_peak_exit:
        problems.append("이번 청산이 peak_drawdown 축이라 confirm 조건 점검 필요")
    if not problems:
        problems.append("거래별 반복 패턴 판단을 위한 추가 표본 필요")

    monitor_memory = _as_dict(memory_app.get("monitor_memory_bias"))
    cause_lines: List[str] = []
    if carryover_exit:
        if carryover_context.get("estimated_entry_kst") and carryover_context.get("exit_kst"):
            cause_lines.append(
                f"{symbol}은 {carryover_context.get('estimated_entry_date_kst')} 보유분이 "
                f"{carryover_context.get('exit_date_kst')}에 청산된 이월 포지션입니다"
            )
        else:
            cause_lines.append(f"{symbol}은 오늘 신규 진입이 아니라 전일/주말 이월 보유분의 청산 결과입니다")
        if carryover_context.get("carry_risk_label"):
            cause_lines.append(f"런타임 상태는 {carryover_context.get('carry_state_label')} / {carryover_context.get('carry_risk_label')}로 기록됨")
    if recovered_partial_exit:
        cause_lines.append("보유/회수 포지션의 당일 SELL 결과이며, 신규 매수 선정·진입 판단과 같은 표본으로 보지 않습니다")
    for row in _listify(monitor_memory.get("applied_deltas")):
        row_obj = _as_dict(row)
        if str(row_obj.get("field") or "") == "breakout_buffer_pct" and (_num_opt(row_obj.get("delta")) or 0.0) > 0:
            cause_lines.append(
                "진입 정책은 breakout_buffer "
                f"{_compact_number(row_obj.get('from'))} → {_compact_number(row_obj.get('to'))}로 보수화됨"
            )
            break
    if actual_take_profit:
        cause_lines.append("청산은 목표 수익 실현 기준으로 실행됨")
    elif actual_peak_exit:
        cause_lines.append("청산은 peak_drawdown 축으로 실행됨")
    elif actual_hard_stop:
        cause_lines.append("청산은 고정 손절 기준으로 실행됨")
    if selection_fallback_summary.get("used") or (rank_num is not None and rank_num > 1):
        if scanner_top_pick and scanner_top_pick != "-":
            cause_lines.append(f"{scanner_top_pick} 보류 후 {symbol}에서 진입 조건이 충족됨")
        else:
            cause_lines.append("상위 후보 탈락 후 차순위 후보에서 진입이 성립됨")
    if cost_analysis.get("mock_cost_warning") and cost_drag_pct is not None:
        cause_lines.append(f"1주 모의투자 수수료/세금이 손익률을 {_fmt_pct(cost_drag_pct)} 압박")
    if not cause_lines:
        cause_lines.append("진입/청산 구조의 반복성은 당일 패턴 섹션에서 추가 확인 필요")

    recommendations: List[str] = []
    if carryover_exit:
        recommendations.append("오버나이트 승인 시각/근거와 당일 청산 컨텍스트를 분리해 검증")
    if recovered_partial_exit:
        recommendations.append("회수/partial 청산은 완료 거래와 별도 집계해 승패와 평균 수익률을 확인")
    if cost_analysis.get("mock_cost_warning"):
        recommendations.append("모의투자 비용 기준과 실계좌 추정 비용 기준 분리 확인")
    if actual_peak_exit:
        recommendations.append("peak_drawdown activation/confirm 조건 점검")
    if "pullback_not_mature" in entry_blob:
        recommendations.append("pullback 조건 완화 또는 성숙도 판정 재검토")
    if selection_fallback_summary.get("used") or (rank_num is not None and rank_num > 1):
        recommendations.append("1순위 보류 사유와 차순위 진입 기대값 비교")
    if monitor_line:
        recommendations.append("monitor_only 비중이 높은 당일 route mix 점검")
    if (not holding_duration_summary or _is_not_captured(holding_duration_summary) or str(holding_duration_summary).strip() in {"0", "0s", "0초"}):
        recommendations.append("보유 구간 모니터 스냅샷 보강")
    if not recommendations:
        recommendations.append("동일 패턴 3건 이상 누적 후 정책 조정 여부 판단")
    recommendations = _dedupe([item for item in recommendations if item])[:4]

    market_news = _sample_news_titles(
        market.get("market_news_titles") or report.get("strategist_market_headlines"),
        limit=2,
    )
    symbol_news = _sample_news_titles_for_symbol(
        symbol,
        market.get("symbol_news_titles"),
        report.get("strategist_symbol_headlines"),
        market.get("candidate_news_titles"),
        limit=2,
    )
    market_summary = _translate_text(market.get("summary")) or "시장 요약은 상세 리포트에서 확인 필요"
    playbook = _playbook_label(_pick(market.get("playbook"), market.get("selected_playbook")))
    trace_summary = _as_dict(report.get("strategist_trace_summary"))
    risk_tone = _risk_mode_label(_pick(market.get("risk_tone"), trace_summary.get("risk_tone"), market.get("risk_mode")))
    monitor_guide = _metadata_value(_pick(trace_summary.get("monitor_guidance"), market.get("monitor_guidance"), ""))
    selection_reason = _translate_text(selection.get("basis") or "").strip()
    if not selection_reason:
        selection_reason = _first_matching_line(_listify(selection.get("bullets")), ["거래대금", "거래량", "모멘텀", "선정"])
    selection_trace = _as_dict(selection.get("scanner_selection_trace"))
    scanner_chart_fit = _as_dict(selection.get("scanner_chart_fit")) or _as_dict(selection_trace.get("scanner_chart_fit"))
    selection_fallback = _selection_fallback_context(selection, symbol)
    entry_watch_lines = _entry_watch_summary_lines(
        report,
        require_trade_symbol_match=bool(selection_fallback.get("used")) or bool(exit_only_report),
    )
    blocked_reason = ""
    if not selection_fallback.get("used"):
        blocked_reason = _first_matching_line(_listify(selection.get("bullets")) + _listify(entry.get("bullets")), ["1순위", "top pick", "막혔", "blocked"])
    entry_reason = _entry_reason_line(_listify(entry.get("bullets")))
    if not entry_reason:
        entry_reason = _entry_reason_line([entry.get("summary")])
    entry_confidence = _entry_confidence_for_operator_summary(
        _listify(entry.get("bullets")),
        action=action,
        buy_price=_pick(truth_price.get("broker_buy_price"), shared.get("broker_buy_price")),
    )
    if not entry_confidence and "신뢰도" in str(entry.get("summary") or ""):
        entry_summary_text = _translate_text(entry.get("summary")).rstrip(".")
        if not _is_post_entry_gate_text(entry_summary_text):
            entry_confidence = _normalize_entry_confidence_for_operator_summary(
                entry_summary_text,
                action=action,
                buy_price=_pick(truth_price.get("broker_buy_price"), shared.get("broker_buy_price")),
            )
    if carryover_exit:
        selection_reason = "오버나이트/주말 이월 포지션 청산"
        blocked_reason = ""
        entry_reason = "오늘 신규 진입 판단이 아니라 전일/주말 이월 포지션입니다."
        entry_confidence = ""
    elif recovered_partial_exit:
        selection_reason = "보유/회수 포지션 청산"
        blocked_reason = ""
        entry_reason = _RECOVERED_PARTIAL_ENTRY_NOTE
        entry_confidence = ""
    holding_duration = _authoritative_holding_duration_label(report) or _pick(
        shared.get("holding_duration"), report.get("hold_duration"), ""
    )
    exit_signal_texts = _section_texts(exit_decision) + _section_texts(holding)
    exit_signal_snapshot = _extract_exit_signal_snapshot(exit_signal_texts)
    exit_signal_snapshot = _enrich_exit_signal_snapshot_from_monitor(exit_signal_snapshot, monitor)
    exit_trigger = _first_matching_line(_listify(exit_decision.get("bullets")), ["촉발", "트리거", "청산 사유", "고점 대비"])
    if not exit_trigger:
        exit_trigger = _first_matching_line(_section_texts(exit_decision), ["촉발", "트리거", "청산 사유", "고점 대비"])
    exit_price = _pick(truth_price.get("broker_fill_price"), shared.get("broker_fill_price"))
    buy_price = _pick(truth_price.get("broker_buy_price"), shared.get("broker_buy_price"))
    monitor_exit_reference_price = _pick(
        truth_price.get("monitor_mark_price"),
        shared.get("monitor_mark_price"),
        exit_signal_snapshot.get("monitor_current_price"),
    )
    exit_price_note = ""
    if exit_price in (None, "") and monitor_exit_reference_price not in (None, ""):
        exit_price_note = f" (체결가 미확정, 모니터 기준 {_money(monitor_exit_reference_price)})"

    lines: List[str] = []
    lines.append(f"# AI 거래 리포트 ({trade_id})")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🔴 운영 요약 (Operator Decision Summary)")
    lines.append("")
    lines.append(f"* 결과: **{result_text}**")
    lines.append(f"* 당일 성과(리포트 생성 시점 기준): **{same_day}**")
    lines.append("")
    lines.append("### ✔ 잘된 점")
    lines.append("")
    lines.extend(f"* {item}" for item in positives[:3])
    lines.append("")
    lines.append("### ❌ 문제점")
    lines.append("")
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(problems[:3], 1))
    lines.append("")
    lines.append("### 📌 원인 해석")
    lines.append("")
    lines.extend(f"* {item}" for item in cause_lines[:4])
    lines.append("")
    headline_focus = recommendations[0] if recommendations else problems[0]
    lines.append(f"👉 **{result_label} 거래; 핵심 점검: {headline_focus}**")
    lines.append("")
    lines.append("### 🛠 권고 액션 (우선순위)")
    lines.append("")
    lines.extend(f"{idx}. {item}" for idx, item in enumerate(recommendations[:4], 1))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🧭 거래 개요")
    lines.append("")
    symbol_line = f"* 종목: {symbol}"
    if symbol_name:
        symbol_line += f" ({symbol_name})"
    lines.append(symbol_line)
    if symbol_theme:
        lines.append(f"* 테마: {symbol_theme}")
    lines.append(f"* 거래 유형: {story_type}")
    lines.append(f"* 상태: {status}")
    lines.append(f"* 실행 모드: {execution_mode}")
    controlled_lane_lines = _render_controlled_lane_report_lines(report)
    if controlled_lane_lines:
        lines.append("")
        lines.append("### 통제 모의투자 레인")
        lines.append("")
        lines.extend(controlled_lane_lines)
    if recovered_partial_exit:
        lines.append(f"* {_RECOVERED_PARTIAL_EXIT_NOTE}")
    if carryover_exit:
        lines.append(f"* 포지션 성격: {carryover_context.get('carry_state_label') or '오버나이트/이월 보유'}")
        if carryover_context.get("estimated_entry_kst") or carryover_context.get("exit_kst"):
            basis = carryover_context.get("date_basis") or "이월 보유 시간 기준"
            lines.append(
                f"* 날짜 기준: 보유 시작 {carryover_context.get('estimated_entry_kst') or '-'} / "
                f"청산 {carryover_context.get('exit_kst') or '-'} ({basis})"
            )
        if carryover_context.get("duration_label"):
            lines.append(f"* 이월 보유 시간: {carryover_context.get('duration_label')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📊 실행 결과 (Truth Surface)")
    lines.append("")
    lines.append(f"* 매수가 / 매도가: {_money(buy_price)} / {_money(exit_price)}{exit_price_note}")
    if pnl_num is None and pnl_pct_is_observation:
        lines.append("* 실현 손익: **확인 불가**")
    else:
        pnl_line = _money(pnl)
        if pnl_pct not in (None, ""):
            pnl_line = f"{pnl_line} ({_fmt_pct(pnl_pct)})"
        lines.append(f"* 실현 손익: **{pnl_line}**")
    fee_display = _money(_pick(shared.get("broker_fee"), truth_pnl.get("broker_fee")))
    tax_display = _money(_pick(shared.get("broker_tax"), truth_pnl.get("broker_tax")))
    lines.append(f"* 수수료 / 세금: {fee_display} / {tax_display}")
    lines.extend(_trade_cost_analysis_lines(report))
    lines.append(f"* 손익 기준: {_pnl_basis_label(truth_pnl, shared)}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🧠 전략 및 시장 맥락")
    lines.append("")
    lines.append("### 시장 상태")
    lines.append("")
    lines.append(f"* {market_summary}")
    for korea_line in _korea_index_lines(market):
        lines.append(f"* 국내 지수: {korea_line}")
    if market.get("vix_level") not in (None, ""):
        lines.append(f"* VIX: {_compact_decimal(market.get('vix_level'))}")
    if market.get("market_sentiment"):
        lines.append(f"* 시장 심리: {_metadata_value(market.get('market_sentiment'))}")
    if carryover_exit:
        lines.append(
            f"* 날짜 주의: 위 시장/지수는 {carryover_context.get('exit_date_kst') or '청산일'} 청산 시점 컨텍스트입니다. "
            f"오버나이트 승인 판단은 {carryover_context.get('estimated_entry_date_kst') or '이전 거래일'} 기준과 분리해 봅니다."
        )
    lines.append("")
    lines.append("### 전략가 출력 요약")
    lines.append("")
    lines.append(f"* 플레이북: **{playbook or '-'}**")
    lines.append(f"* 리스크 톤: {risk_tone or '-'}")
    themes = [_theme_label(x) for x in _listify(market.get("themes") or market.get("preferred_themes")) if not _is_not_captured(x)]
    if themes:
        lines.append(f"* 핵심 테마: {', '.join(themes[:4])}")
    theme_source = _metadata_value(market.get("theme_source"))
    theme_status = _metadata_value(market.get("theme_source_status"))
    if theme_source and theme_source != "-":
        source_text = theme_source
        if theme_status and theme_status != "-":
            source_text += f" / {theme_status}"
        lines.append(f"* 테마 출처: {source_text}")
    if monitor_guide:
        lines.append(f"* 모니터 가이드: {monitor_guide}")
    strategy_horizon_lines = _build_strategy_horizon_lines(report, compact=True)
    if strategy_horizon_lines:
        lines.append("")
        lines.append("### 전략 보유 기간")
        lines.append("")
        lines.extend(strategy_horizon_lines)
    if entry_watch_lines and not carryover_exit:
        lines.append(f"* 후보 감시: {entry_watch_lines[0]}")
        if len(entry_watch_lines) > 1:
            lines.append(f"* 후보 선택: {entry_watch_lines[-1]}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📰 뉴스 및 컨텍스트")
    lines.append("")
    lines.append("### 시장 뉴스")
    lines.append("")
    if market_news:
        lines.extend(f"* {item}" for item in market_news)
    else:
        lines.append("* 표본 없음")
        lines.append("* 원천 위치: ai_trade_report_input.json의 market_context_at_entry.market_news_titles")
    lines.append("")
    lines.append(f"### 종목 뉴스 ({symbol})")
    lines.append("")
    if symbol_news:
        lines.extend(f"* {item}" for item in symbol_news)
    else:
        lines.append("* 표본 없음")
        lines.append(f"* 원천 위치: ai_trade_report_input.json의 market_context_at_entry.candidate_news_titles 중 {symbol} 항목")
    lines.append("")
    lines.append("👉 해석:")
    lines.append("")
    if carryover_exit:
        lines.append("* 종목은 오버나이트/주말 이월 포지션 청산 흐름")
        lines.append(f"* 전략은 {playbook or '-'} → **당일 신규 선정이 아니라 보유 포지션 청산 품질 중심으로 확인 필요**")
    elif recovered_partial_exit:
        lines.append("* 종목은 보유/회수 포지션 청산 흐름")
        lines.append(f"* 전략은 {playbook or '-'} → **신규 선정 평가가 아니라 청산 결과 중심으로 확인 필요**")
    else:
        lines.append(f"* 종목은 {_translated_metadata(selection.get('basis') or '후보 점수 우위')} 흐름")
        lines.append(f"* 전략은 {playbook or '-'} → **전략/종목 톤 정합성 점검 필요**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🎯 종목 선정 흐름")
    lines.append("")
    if carryover_exit:
        lines.append("* 선정 경로: 오버나이트/주말 이월 포지션 청산")
        if carryover_context.get("estimated_entry_kst"):
            lines.append(f"* 보유 시작 추정: {carryover_context.get('estimated_entry_kst')} ({carryover_context.get('date_basis')})")
        if carryover_context.get("duration_label"):
            lines.append(f"* 이월 보유 시간: {carryover_context.get('duration_label')}")
        if carryover_context.get("carry_state_label"):
            line = f"* 이월 상태: {carryover_context.get('carry_state_label')}"
            if carryover_context.get("carry_risk_label"):
                line += f" / {carryover_context.get('carry_risk_label')}"
            lines.append(line)
        if carryover_context.get("weekend_carry"):
            lines.append("* 주말 이월: 금요일 보유분이 월요일 청산까지 이어진 거래입니다.")
    elif recovered_partial_exit:
        lines.append("* 선정 경로: 보유/회수 포지션 청산")
        lines.append("* 스캐너 순위: 기록 없음")
    elif selection_fallback.get("used"):
        lines.append("* 선정 경로: 차순위 재평가")
        lines.append(f"* 재평가 순위: {_selected_rank(selection)}위")
        lines.append(f"* 재평가 점수: {_selected_score(selection)}")
    else:
        lines.append(f"* 스캐너 순위: {_selected_rank(selection)}위")
        lines.append(f"* 점수: {_selected_score(selection)}")
    if selection_reason:
        lines.append(f"* 선정 이유: {selection_reason}")
    if scanner_chart_fit:
        lines.append(
            "* Scanner chart-fit: "
            f"{_compact_decimal(scanner_chart_fit.get('score'), 3)} "
            f"/ {scanner_chart_fit.get('authority') or '-'}"
        )
    if selection_fallback.get("used"):
        top_pick = selection_fallback.get("scanner_top_pick_symbol") or "-"
        reason = selection_fallback.get("reason") or "모니터 조건 미충족"
        lines.append(f"* 스캐너 상위 후보 {top_pick} 보류 후 {symbol}이 재평가에서 실제 진입 후보로 확정됐습니다.")
        lines.append(f"* 모니터 확인 사유: {reason}")
        for metric_line in _entry_signal_metric_summary_lines(entry_signal_snapshot, prefix="모니터 확인 수치"):
            lines.append(f"* {metric_line}")
    if blocked_reason:
        lines.append(f"* {blocked_reason}")
    if not selection_fallback.get("used") and not recovered_partial_exit:
        for watch_line in entry_watch_lines[1:3]:
            lines.append(f"* {watch_line}")
    lines.append("")
    if carryover_exit:
        lines.append("👉 특징: **오늘 신규 선정 평가가 아니라 오버나이트/주말 이월 포지션의 청산 결과입니다**")
    elif recovered_partial_exit:
        lines.append("👉 특징: **신규 선정 평가가 아니라 회수 포지션의 청산 결과입니다**")
    else:
        lines.append("👉 특징: **강한 종목이어도 실제 진입 구조와 별도 검증 필요**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🚪 진입 판단")
    lines.append("")
    quant_compact_lines = _render_quant_tactic_report_lines_impl(report, compact=True)
    if quant_compact_lines:
        lines.extend(quant_compact_lines[:4])
    if entry_reason:
        lines.append(f"* 조건: {entry_reason}")
    if not selection_fallback.get("used") and not exit_only_report:
        lines.extend(f"* {item}" for item in entry_signal_metric_lines)
    if carryover_exit:
        lines.append("* 방식: 당일 신규 매수 평가 제외")
        if carryover_context.get("estimated_entry_kst"):
            lines.append("* 원 진입/보유 시작 시각은 리포트 입력의 actual_hold_sec와 청산 시각으로 역산했습니다.")
    elif recovered_partial_exit:
        lines.append("* 방식: 당일 신규 매수 평가 제외")
    else:
        lines.append("* 방식: 돌파/확인형 진입")
        if entry_confidence:
            lines.append(f"* {entry_confidence}")
    lines.append("")
    if carryover_exit:
        lines.append("👉 **신규 진입 판단이 아니라 이월 포지션 청산 리포트입니다.**")
    elif recovered_partial_exit:
        lines.append("👉 **신규 진입 판단이 아니라 회수 포지션 청산 리포트입니다.**")
    else:
        lines.append("👉 **threshold 근접 진입 여부 확인 필요**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## ⏱ 보유 및 청산")
    lines.append("")
    if holding_duration and not _is_not_captured(holding_duration):
        lines.append(f"* 보유 시간: {holding_duration}")
    elif carryover_exit and carryover_context.get("duration_label"):
        lines.append(f"* 보유 시간: {carryover_context.get('duration_label')}")
    elif recovered_partial_exit:
        lines.append("* 보유 시간: 기록 없음")
    if carryover_exit and carryover_context.get("estimated_entry_kst"):
        lines.append(f"* 보유 시작 추정: {carryover_context.get('estimated_entry_kst')}")
    lines.append(f"* 청산가: {_money(exit_price)}{exit_price_note}")
    lines.append("")
    lines.append("### 청산 트리거")
    lines.append("")
    exit_trigger_lines = _build_summary_exit_trigger_lines(
        exit_trigger,
        exit_signal_snapshot,
        fallback_reason=shared.get("exit_reason"),
        buy_price=buy_price,
        exit_price=exit_price,
        pnl_pct=pnl_pct,
        truth_source=_pick(shared.get("pnl_truth_source"), truth_pnl.get("pnl_truth_source")),
    )
    if recovered_partial_exit and (_num_opt(pnl_pct) or 0.0) > 0.0 and exit_trigger_lines:
        trigger_text = exit_trigger_lines[0].replace("트리거:", "").strip()
        if trigger_text in {"Stop Loss", "stop_loss", "고정 손절 기준"}:
            trigger_text = "고정 손절 기준"
        exit_trigger_lines[0] = f"트리거: 모니터 신호명은 {trigger_text}이었지만 Truth Surface 기준 실현 결과는 이익입니다."
    lines.extend(f"* {item}" for item in exit_trigger_lines)
    if quant_compact_lines:
        for item in quant_compact_lines[4:8]:
            lines.append(item if item.startswith("* ") else f"* {item.lstrip('- ')}")
    lines.append("")
    lines.append("👉 수익 구간 진입 후 유지/청산 품질 점검 필요")
    shadow_lines = _build_post_exit_shadow_summary_lines(report)
    if shadow_lines:
        lines.append("")
        lines.extend(shadow_lines)
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## ⚙️ 정책 및 메모리 영향")
    lines.append("")
    lines.extend(_policy_delta_lines(memory_app) if memory_app else ["* 정책/메모리 영향은 상세 리포트에서 확인 필요"])
    lines.append("")
    lines.append("👉 **진입/청산 정책 조합의 손익비 영향 확인 필요**")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🔁 패턴 분석 (당일)")
    lines.append("")
    lines.append(f"* {same_day}")
    lines.append("")
    lines.append("### 반복 패턴")
    lines.append("")
    pattern_lines = [
        line
        for line in _listify(reporter_eval.get("bullets"))
        if any(token in str(line).lower() for token in ("monitor", "fallback", "blocker", "closed trade", "차순위"))
    ]
    if pattern_lines:
        lines.extend(f"* {_translate_text(line).rstrip('.')}" for line in pattern_lines[:4])
    else:
        lines.append("* 반복 패턴은 추가 집계 필요")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## ⚠️ 주요 리스크")
    lines.append("")
    default_risks = (
        ["이월 승인 근거와 당일 청산 판단의 날짜 혼선 가능성", "장기/주말 이월 상태에서 청산 우선순위 검증 필요"]
        if carryover_exit
        else ["전략 vs 종목 톤 미스매치", "scanner → monitor 정합성 저하 가능성"]
    )
    risk_lines = _dedupe(problems + default_risks)
    lines.extend(f"* {item}" for item in risk_lines[:4])
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📌 보완 필요")
    lines.append("")
    lines.extend(f"* {item}" for item in recommendations[:4])
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 📎 근거 출처")
    lines.append("")
    lines.append("* canonical agent artifacts 기반")
    lines.append("* commander / strategist / scanner / monitor / executor / supervisor 로그")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🧾 타임라인")
    lines.append("")
    lines.append(f"* 진입 run: {_extract_run_id(timeline, 'entry')}")
    lines.append(f"* 청산 run: {_extract_run_id(timeline, 'exit')}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 🔚 최종 판단")
    lines.append("")
    lines.append(f"* 상태: {status}")
    lines.append(f"* 액션: {action}")
    lines.append("")
    final_summary = _authoritative_final_operator_summary(
        report,
        action=action,
        fallback=(
            _ensure_sentence(_translate_text(final.get("summary")))
            if final.get("summary")
            else ""
        ),
    )
    if final_summary:
        lines.append(f"👉 **{final_summary}**")
        lines.append("")
    lines.append(f"👉 **{result_label} 원인은 단일 장애보다 진입/청산 구조와 정책 조합에서 우선 점검해야 합니다.**")
    return "\n".join(_strip_trailing_blanks(lines)).strip() + "\n"


def build_trade_summary_input_clean(report: Dict[str, Any]) -> Dict[str, Any]:
    """Build the compact deterministic input that a summary LLM may evaluate."""

    def _pick(*values: Any) -> Any:
        for value in values:
            if value not in (None, ""):
                return value
        return ""

    def _section_texts(*sections: Dict[str, Any]) -> List[str]:
        texts: List[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            summary = _translate_text(section.get("summary")).strip()
            if summary:
                texts.append(summary)
            texts.extend(_translate_text(item).strip() for item in _listify(section.get("bullets")) if str(item or "").strip())
        return texts

    def _same_day_summary(section: Dict[str, Any]) -> str:
        return _same_day_summary_from_texts(
            _section_texts(section),
            current_result=_same_day_current_result(report),
        )

    def _first_matching_line(values: Iterable[Any], needles: Iterable[str]) -> str:
        lowered_needles = [needle.lower() for needle in needles]
        for raw in values:
            text = _translate_text(raw).strip()
            if not text:
                continue
            lowered = text.lower()
            if any(needle in lowered for needle in lowered_needles):
                return text.rstrip(".")
        return ""

    def _policy_deltas(memory_bias: Dict[str, Any]) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        for row in _listify(memory_bias.get("applied_deltas")) + _listify(memory_bias.get("exit_deltas")):
            row_obj = _as_dict(row)
            field = str(row_obj.get("field") or "").strip()
            if not field:
                continue
            rows.append(
                {
                    "field": field,
                    "from": row_obj.get("from"),
                    "to": row_obj.get("to"),
                    "delta": row_obj.get("delta"),
                }
            )
        return rows[:8]

    def _compact_section(section: Dict[str, Any], *, limit: int = 5) -> Dict[str, Any]:
        return {
            "summary": _translate_text(section.get("summary")).strip(),
            "bullets": [_translate_text(item).strip() for item in _listify(section.get("bullets"))[:limit] if str(item or "").strip()],
        }

    shared = _as_dict(report.get("shared_facts"))
    truth = _get_truth_surface(report)
    truth_price = _as_dict(truth.get("price"))
    truth_pnl = _as_dict(truth.get("pnl"))
    market = _resolve_market_context(report)
    strategist = _as_dict(report.get("strategist_summary"))
    trace_summary = _as_dict(report.get("strategist_trace_summary"))
    selection = _as_dict(report.get("why_this_symbol_was_chosen"))
    entry = _as_dict(report.get("entry_decision"))
    holding = _as_dict(report.get("holding_monitoring_story"))
    exit_decision = _as_dict(report.get("exit_decision"))
    reporter_eval = _as_dict(report.get("reporter_evaluation"))
    memory_app = _as_dict(report.get("memory_application_surface"))
    monitor = _as_dict(report.get("monitor_snapshot"))
    scanner_memory = _as_dict(memory_app.get("scanner_memory_bias"))
    monitor_memory = _as_dict(memory_app.get("monitor_memory_bias"))
    final = _as_dict(report.get("final_operator_conclusion"))
    trade_id = _clip(report.get("trade_id") or report.get("story_id"), 80)
    symbol = _clip(_pick(report.get("symbol"), shared.get("symbol")), 32)
    symbol_metadata = _resolve_trade_symbol_metadata(report, symbol)
    action_label = _action_label(_pick(final.get("current_action"), report.get("action"), shared.get("action")))
    recovered_partial_exit = _is_recovered_partial_exit_report(report)
    carryover_context = _carryover_context(report)
    carryover_exit = bool(carryover_context.get("is_carryover_exit"))
    exit_only_report = recovered_partial_exit or carryover_exit
    day = _clip(report.get("day") or shared.get("day"), 32)
    if not day:
        match = re.search(r"TRD_(\d{4})(\d{2})(\d{2})", trade_id)
        if match:
            day = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    pnl = _pick(truth_pnl.get("value"), shared.get("pnl"))
    pnl_pct, pnl_pct_is_observation = _operator_pnl_pct(truth_pnl, shared)
    pnl_num = _num_opt(pnl)
    pnl_label_basis = pnl_num if pnl_num is not None else _num_opt(pnl_pct)
    result_label = "breakeven"
    if pnl_label_basis is not None and pnl_label_basis > 0:
        result_label = "profit"
    elif pnl_label_basis is not None and pnl_label_basis < 0:
        result_label = "loss"
    truth_source_value = _pick(truth_pnl.get("pnl_truth_source"), shared.get("pnl_truth_source"))
    if pnl_num is None and pnl_pct_is_observation:
        truth_source_value = _pick(
            truth_price.get("price_truth_source"),
            shared.get("price_truth_source"),
            truth_source_value,
        )

    selection_trace = _as_dict(selection.get("scanner_selection_trace"))
    scanner_chart_fit = _as_dict(selection.get("scanner_chart_fit")) or _as_dict(selection_trace.get("scanner_chart_fit"))
    selection_fallback = _selection_fallback_context(selection, _clip(_pick(report.get("symbol"), shared.get("symbol")), 32))
    entry_signal_snapshot = _resolve_entry_signal_snapshot(report)
    selection_rank = _pick(selection.get("selected_rank"), selection_trace.get("selected_rank"), selection.get("scanner_rank"))
    selection_score = _pick(selection.get("score_total"), selection.get("selected_score"))
    if selection_score in (None, "") and selection_fallback.get("used"):
        selection_score = _pick(selection_trace.get("selected_score"), _as_dict(selection_trace.get("news_scanner_contribution")).get("selected_score_total"))
    if exit_only_report:
        selection_rank = None
        selection_score = ""
    selection_texts = _section_texts(selection)
    entry_texts = _section_texts(entry)
    exit_texts = _section_texts(exit_decision)
    exit_signal_snapshot = _extract_exit_signal_snapshot(exit_texts + _section_texts(holding))
    exit_signal_snapshot = _enrich_exit_signal_snapshot_from_monitor(exit_signal_snapshot, monitor)
    post_exit_shadow_summary = _compact_post_exit_shadow(_post_exit_shadow_surface(report))
    strategy_horizon_summary = _strategy_horizon_report_surface(report)
    authoritative_hold_sec = _authoritative_hold_duration_seconds(report)
    authoritative_hold_label = _authoritative_holding_duration_label(report)
    if authoritative_hold_sec is not None:
        strategy_horizon_summary = dict(strategy_horizon_summary)
        strategy_horizon_summary["actual_hold_sec"] = authoritative_hold_sec
        strategy_horizon_summary["actual_hold_label"] = authoritative_hold_label
        strategy_horizon_summary["actual_hold_source"] = "entry_exit_execution_timestamps"
    exit_trigger = _first_matching_line(
        _listify(exit_decision.get("bullets")),
        ["촉발", "트리거", "청산 사유", "peak_drawdown", "고점 대비"],
    )
    if not exit_trigger:
        exit_trigger = _first_matching_line(exit_texts, ["촉발", "트리거", "청산", "peak_drawdown", "고점 대비"])
    exit_trigger_label = _normalize_exit_trigger_label(
        exit_signal_snapshot.get("trigger") or exit_trigger,
        shared.get("exit_reason"),
    )
    reporter_texts = _section_texts(reporter_eval)
    combined_texts = _section_texts(market, strategist, selection, entry, holding, exit_decision, reporter_eval)
    combined_blob = "\n".join(combined_texts).lower()
    entry_execution_visibility = _resolve_entry_execution_visibility(report)
    entry_watch_lines = _entry_watch_execution_lines(
        report,
        require_trade_symbol_match=bool(selection_fallback.get("used")) or bool(exit_only_report),
    )
    broker_alignment = _as_dict(report.get("broker_alignment"))
    broker_alignment_summary = _as_dict(broker_alignment.get("summary"))
    broker_account_snapshot = _as_dict(broker_alignment.get("account_snapshot"))

    deterministic_positives: List[str] = []
    if truth_price.get("broker_fill_price") not in (None, "") or truth_pnl.get("value") not in (None, ""):
        deterministic_positives.append("broker_truth_available")
    if strategist or selection or entry or exit_decision:
        deterministic_positives.append("agent_decision_flow_available")
    if memory_app:
        deterministic_positives.append("policy_memory_surface_available")
    if carryover_exit:
        deterministic_positives.append("carryover_exit_accounted_separately")
    if recovered_partial_exit:
        deterministic_positives.append("recovered_partial_exit_accounted_separately")

    deterministic_problems: List[str] = []
    if "monitor_only" in combined_blob or "monitor-only" in combined_blob or "monitor 단독" in combined_blob:
        deterministic_problems.append("monitor_only_path_ratio_high")
    if recovered_partial_exit:
        deterministic_problems.append("entry_evidence_missing_for_recovered_partial_exit")
    if carryover_exit:
        deterministic_problems.append("carryover_exit_requires_separate_date_basis")
    if "peak_drawdown" in combined_blob or "고점 대비 하락폭" in combined_blob:
        deterministic_problems.append("peak_drawdown_exit_needs_review")
    rank_num = _num_opt(selection_rank)
    scanner_chart_fit_score = _num_opt(scanner_chart_fit.get("score")) if scanner_chart_fit else None
    if rank_num is not None and rank_num > 1:
        deterministic_problems.append("entered_lower_rank_after_top_candidate_block")
    if scanner_chart_fit_score is not None and scanner_chart_fit_score < 0.25:
        deterministic_problems.append("scanner_chart_fit_low")
    if "pullback" in combined_blob:
        deterministic_problems.append("pullback_condition_repeated")

    root_cause_candidates: List[str] = []
    for row in _listify(monitor_memory.get("applied_deltas")):
        row_obj = _as_dict(row)
        if str(row_obj.get("field") or "") == "breakout_buffer_pct" and (_num_opt(row_obj.get("delta")) or 0.0) > 0:
            root_cause_candidates.append("entry_was_tightened_by_breakout_buffer")
            break
    for row in _listify(monitor_memory.get("exit_deltas")):
        row_obj = _as_dict(row)
        if "peak_drawdown" in str(row_obj.get("field") or "") and (_num_opt(row_obj.get("delta")) or 0.0) < 0:
            root_cause_candidates.append("exit_was_tightened_by_peak_drawdown")
            break
    if rank_num is not None and rank_num > 1:
        root_cause_candidates.append("scanner_monitor_reassessment_after_top_rank_block")
    if scanner_chart_fit_score is not None and scanner_chart_fit_score < 0.25:
        root_cause_candidates.append("scanner_selected_candidate_had_weak_chart_fit")
    if recovered_partial_exit:
        root_cause_candidates.append("recovered_partial_exit_excludes_new_entry_assessment")
    if carryover_exit:
        root_cause_candidates.append("carryover_position_excludes_same_day_scanner_selection_assessment")

    validation_questions: List[str] = []
    if recovered_partial_exit:
        validation_questions.append("회수/partial 청산을 완료 거래와 별도 집계했을 때 당일 실현 성과가 어떻게 달라지는가?")
    if carryover_exit:
        validation_questions.append("오버나이트 승인 근거와 당일 청산 컨텍스트가 분리되어 집계됐는가?")
    if "peak_drawdown_exit_needs_review" in deterministic_problems:
        validation_questions.append("peak_drawdown activation/confirm 조건이 실제 손익비를 악화시키는가?")
    if "entered_lower_rank_after_top_candidate_block" in deterministic_problems:
        validation_questions.append("1순위 탈락 후 차순위 진입의 기대값이 충분한가?")
    if "scanner_chart_fit_low" in deterministic_problems:
        validation_questions.append("scanner_chart_fit_score가 낮은 후보가 다른 점수 축 때문에 선택됐는지 확인해야 하는가?")
    if not validation_questions:
        validation_questions.append("진입/청산 정책 조합이 당일 반복 손익 패턴과 일치하는가?")

    return {
        "schema_version": "ai_trade_summary_input.v1",
        "artifact_type": "ai_trade_summary_input",
        "source_artifact": "ai_trade_report.json",
        "trade": {
            "trade_id": trade_id,
            "day": day,
            "symbol": _clip(_pick(report.get("symbol"), shared.get("symbol")), 32),
            "symbol_name": str(symbol_metadata.get("symbol_name") or ""),
            "theme": str(symbol_metadata.get("theme") or ""),
            "themes": list(symbol_metadata.get("themes") or []),
            "status": _status_label(_pick(report.get("status"), shared.get("status"))),
            "story_type": _story_type_label(report.get("story_type")),
            "execution_mode": _execution_mode_label(report.get("execution_mode_label")),
            "action": action_label,
            "recovered_partial_exit": recovered_partial_exit,
            "carryover_exit": carryover_exit,
            "carryover_context": carryover_context,
            "entry_assessment_scope": (
                "excluded_carryover_exit"
                if carryover_exit
                else ("excluded_recovered_partial" if recovered_partial_exit else "normal")
            ),
        },
        "truth_surface": {
            "result_label": result_label,
            "pnl": pnl,
            "pnl_pct": pnl_pct,
            "pnl_pct_text": _fmt_pct(pnl_pct),
            "buy_price": _pick(truth_price.get("broker_buy_price"), shared.get("broker_buy_price")),
            "sell_price": _pick(truth_price.get("broker_fill_price"), shared.get("broker_fill_price")),
            "monitor_sell_reference_price": _pick(
                truth_price.get("monitor_mark_price"),
                shared.get("monitor_mark_price"),
                exit_signal_snapshot.get("monitor_current_price"),
            ),
            "fee": _pick(shared.get("broker_fee"), truth_pnl.get("broker_fee")),
            "tax": _pick(shared.get("broker_tax"), truth_pnl.get("broker_tax")),
            "cost_analysis": _build_trade_cost_analysis(report),
            "truth_source": _truth_source_label(truth_source_value),
        },
        "same_day_context": {
            "summary": _same_day_summary(reporter_eval),
            "label": "당일 성과(리포트 생성 시점 기준)",
            "basis": "report_generation_time",
            "reporter_evaluation": _compact_section(reporter_eval, limit=6),
        },
        "broker_alignment": {
            "status": _metadata_value(broker_alignment.get("status")),
            "generated_at": _metadata_value(broker_alignment.get("generated_at")),
            "report_json_path": _metadata_value(broker_alignment.get("report_json_path")),
            "account_snapshot_path": _metadata_value(broker_account_snapshot.get("path")),
            "account_snapshot_status": _metadata_value(broker_account_snapshot.get("status")),
            "account_snapshot_api_call_count": broker_account_snapshot.get("api_call_count"),
            "account_snapshot_ok_count": broker_account_snapshot.get("ok_count"),
            "account_snapshot_error_count": broker_account_snapshot.get("error_count"),
            "local_total": broker_alignment_summary.get("local_total"),
            "broker_total": broker_alignment_summary.get("broker_total"),
            "matched_by_ord_no": broker_alignment_summary.get("matched_by_ord_no"),
            "missing_in_local_total": broker_alignment_summary.get("missing_in_local_total"),
            "missing_in_broker_total": broker_alignment_summary.get("missing_in_broker_total"),
            "error": _metadata_value(broker_alignment.get("error")),
        },
        "market_and_strategy": {
            "market_summary": _translate_text(market.get("summary")).strip(),
            "vix": market.get("vix_level"),
            "market_sentiment": _metadata_value(market.get("market_sentiment")),
            "playbook": _playbook_label(_pick(market.get("playbook"), market.get("selected_playbook"))),
            "risk_tone": _risk_mode_label(_pick(market.get("risk_tone"), trace_summary.get("risk_tone"), market.get("risk_mode"))),
            "monitor_guidance": _metadata_value(_pick(trace_summary.get("monitor_guidance"), market.get("monitor_guidance"))),
            "themes": [_theme_label(x) for x in _listify(market.get("themes")) if not _is_not_captured(x)],
            "preferred_themes": [_theme_label(x) for x in _listify(market.get("preferred_themes")) if not _is_not_captured(x)],
            "theme_source": _metadata_value(market.get("theme_source")),
            "theme_source_status": _metadata_value(market.get("theme_source_status")),
            "theme_strength_top_themes": [_theme_label(x) for x in _listify(market.get("theme_strength_top_themes")) if not _is_not_captured(x)],
            "market_news_titles": _sample_news_titles(market.get("market_news_titles") or report.get("strategist_market_headlines"), limit=4),
            "symbol_news_titles": _sample_news_titles_for_symbol(
                symbol,
                market.get("symbol_news_titles"),
                report.get("strategist_symbol_headlines"),
                market.get("candidate_news_titles"),
                limit=4,
            ),
        },
        "decision_flow": {
            "scanner_rank": selection_rank,
            "scanner_score": selection_score,
            "scanner_chart_fit": scanner_chart_fit,
            "scanner_chart_fit_score": scanner_chart_fit.get("score") if scanner_chart_fit else None,
            "scanner_chart_fit_authority": scanner_chart_fit.get("authority") if scanner_chart_fit else "",
            "scanner_rank_basis": (
                "carryover_exit_no_same_day_entry"
                if carryover_exit
                else "recovered_partial_no_entry_evidence"
                if recovered_partial_exit
                else ("monitor_fallback_reassessment" if selection_fallback.get("used") else "scanner_rank")
            ),
            "selection_path": (
                "carryover_exit"
                if carryover_exit
                else "recovered_partial_exit"
                if recovered_partial_exit
                else selection_fallback.get("selection_path") or _metadata_value(selection_trace.get("selection_path"))
            ),
            "scanner_top_pick_symbol": selection_fallback.get("scanner_top_pick_symbol"),
            "monitor_fallback_reason": selection_fallback.get("reason"),
            "selection_basis": (
                "오버나이트/주말 이월 포지션 청산"
                if carryover_exit
                else ("보유/회수 포지션 청산" if recovered_partial_exit else _translated_metadata(selection.get("basis")))
            ),
            "selection_blocker": (
                ""
                if exit_only_report
                else (
                f"스캐너 상위 후보 {selection_fallback.get('scanner_top_pick_symbol')} 보류 후 재평가"
                if selection_fallback.get("used")
                else _first_matching_line(selection_texts + entry_texts, ["1순위", "top pick", "blocked", "막혔"])
                )
            ),
            "entry_reason": (
                "오늘 신규 진입 판단이 아니라 전일/주말 이월 포지션입니다."
                if carryover_exit
                else (_RECOVERED_PARTIAL_ENTRY_NOTE if recovered_partial_exit else _entry_reason_line(entry_texts))
            ),
            "entry_confidence": _entry_confidence_for_operator_summary(
                entry_texts,
                action=action_label,
                buy_price=_pick(truth_price.get("broker_buy_price"), shared.get("broker_buy_price")),
            )
            if not exit_only_report
            else "",
            "entry_observation": entry_signal_snapshot,
            "holding_duration": authoritative_hold_label or _pick(
                shared.get("holding_duration"),
                report.get("hold_duration"),
                carryover_context.get("duration_label"),
            ),
            "exit_reason": exit_trigger_label,
            "exit_trigger": exit_trigger_label,
            "exit_trigger_basis": "monitor_signal_snapshot_not_realized_result",
            "exit_result_note": (
                "모니터 신호명과 별개로 Truth Surface 기준 실현 결과는 이익입니다."
                if recovered_partial_exit and (_num_opt(pnl_pct) or 0.0) > 0.0
                else ""
            ),
            "entry_execution_visibility": entry_execution_visibility,
            "entry_watch_summary_lines": entry_watch_lines,
            "recovered_partial_note": _RECOVERED_PARTIAL_EXIT_NOTE if recovered_partial_exit else "",
            "carryover_note": "오버나이트/주말 이월 포지션 청산은 당일 신규 스캐너 선정 평가에서 제외합니다." if carryover_exit else "",
            "carryover_context": carryover_context,
            "exit_observation": exit_signal_snapshot,
            "final_operator_summary": _authoritative_final_operator_summary(
                report,
                action=action_label,
                fallback=_translate_text(final.get("summary")).strip(),
            ),
        },
        "strategy_horizon": strategy_horizon_summary,
        "post_exit_shadow": post_exit_shadow_summary,
        "quant_tactic": _quant_tactic_surface_impl(report),
        "memory_and_policy": {
            "scanner_memory_applied": bool(scanner_memory.get("applied")),
            "monitor_memory_applied": bool(monitor_memory.get("applied")),
            "monitor_active_layers": list(monitor_memory.get("active_layers") or []),
            "monitor_policy_deltas": _policy_deltas(monitor_memory),
        },
        "deterministic_findings": {
            "positives": deterministic_positives,
            "problems": deterministic_problems,
            "root_cause_candidates": root_cause_candidates,
            "validation_questions": validation_questions,
            "raw_reporter_pattern_lines": [_translate_text(line).strip() for line in reporter_texts[:6] if line],
        },
        "llm_task": {
            "purpose": "Fill only the interpretation fields for ai_trade_summary evaluation.",
            "allowed_output_fields": [
                "conclusion",
                "root_cause",
                "priority_actions",
                "risk_notes",
                "validation_questions",
            ],
            "hard_constraints": [
                "Do not invent or modify prices, pnl, fees, taxes, timestamps, or order facts.",
                "Use truth_surface as immutable fact.",
                "Treat decision_flow.exit_observation as monitor_signal_snapshot only, not as broker fill or realized pnl.",
                "Treat strategy_horizon as strategy intent and observation-only report visibility; do not treat it as forced hold unless allow_behavior_change is true.",
                "Treat post_exit_shadow as observation-only evidence, not as a live behavior-change rule.",
                "If trade.carryover_exit is true, separate the original carry/overnight date basis from the current-day exit context.",
                "If evidence is weak, state that validation is required instead of asserting causality.",
                "Keep output operator-facing and concise.",
            ],
        },
    }


def render_trade_summary_markdown_with_evaluation_clean(
    report: Dict[str, Any],
    summary_report: Dict[str, Any],
) -> str:
    """Render ai_trade_summary.md with deterministic diagnostics before the LLM draft."""

    base = render_trade_summary_markdown_clean(report).rstrip()
    deterministic_section = _build_summary_deterministic_diagnostics_section(summary_report, report=report)
    llm_section = _build_summary_llm_evaluation_section(summary_report, report=report)
    section = list(deterministic_section)
    if deterministic_section and llm_section:
        section.append("")
    section.extend(llm_section)
    section = _strip_trailing_blanks(section)
    if not section:
        return base + "\n"
    marker = "\n---\n\n## 🧭 거래 개요"
    block = "\n".join(section)
    if marker in base:
        return base.replace(marker, f"\n{block}\n{marker}", 1).strip() + "\n"
    return f"{base}\n\n{block}\n"


def _summary_problem_label(value: Any) -> str:
    raw = str(value or "").strip()
    mapping = {
        "monitor_only_path_ratio_high": "monitor_only 경로 비중 확인 필요",
        "peak_drawdown_exit_needs_review": "고점 대비 하락폭 청산 조건 점검 필요",
        "entered_lower_rank_after_top_candidate_block": "상위 후보 보류 후 차순위 진입 기대값 점검 필요",
        "scanner_chart_fit_low": "scanner chart-fit 낮은 후보 선택 여부 점검 필요",
        "pullback_condition_repeated": "눌림목 조건 반복 사용 여부 점검 필요",
        "entry_evidence_missing_for_recovered_partial_exit": "복구된 부분 청산이라 신규 진입 근거 별도 확인 필요",
        "carryover_exit_requires_separate_date_basis": "이월 포지션 청산이라 당일 신규 진입 평가와 분리 필요",
    }
    return mapping.get(raw, _summary_eval_sentence(raw))


def _summary_root_cause_label(value: Any) -> str:
    raw = str(value or "").strip()
    mapping = {
        "scanner_monitor_reassessment_after_top_rank_block": "스캐너 상위 후보 보류 후 모니터 재평가로 차순위 진입",
        "scanner_selected_candidate_had_weak_chart_fit": "선택 후보의 scanner chart-fit 점수가 낮았음",
        "entry_was_tightened_by_breakout_buffer": "메모리/정책이 breakout buffer를 강화함",
        "exit_was_tightened_by_peak_drawdown": "메모리/정책이 peak drawdown 청산을 강화함",
        "recovered_partial_exit_excludes_new_entry_assessment": "복구된 부분 청산이라 신규 진입 평가 제외",
        "carryover_position_excludes_same_day_scanner_selection_assessment": "이월 포지션이라 당일 스캐너 선정 평가 제외",
    }
    return mapping.get(raw, _summary_eval_sentence(raw))


def _summary_fact_text(value: Any) -> str:
    text = _translate_text(value).strip()
    text = re.sub(r"\s+", " ", text)
    text = text.replace("입니다..", "입니다.")
    return text.rstrip(".")


def _build_summary_deterministic_diagnostics_section(
    summary_report: Dict[str, Any],
    *,
    report: Dict[str, Any] | None = None,
) -> List[str]:
    payload = summary_report if isinstance(summary_report, dict) else {}
    trade = _as_dict(payload.get("trade"))
    truth = _as_dict(payload.get("truth_surface"))
    decision = _as_dict(payload.get("decision_flow"))
    broker_alignment = _as_dict(payload.get("broker_alignment"))
    findings = _as_dict(payload.get("deterministic_findings"))
    fallback_meta = _resolve_trade_symbol_metadata(report or {}, str(trade.get("symbol") or ""))

    facts: List[str] = []
    symbol = _metadata_value(trade.get("symbol"))
    raw_symbol_name = _metadata_value(trade.get("symbol_name"))
    symbol_name = raw_symbol_name if _looks_like_symbol_name_impl(raw_symbol_name, symbol) else ""
    if not symbol_name:
        symbol_name = _metadata_value(fallback_meta.get("symbol_name"))
    theme = _metadata_value(trade.get("theme") or fallback_meta.get("theme"))
    if symbol != "-":
        label = f"{symbol} ({symbol_name})" if symbol_name not in {"", "-"} else symbol
        facts.append(f"대상 종목: {label}")
    if theme not in {"", "-"}:
        facts.append(f"종목 해당 테마: {theme}")
    if truth.get("pnl") not in (None, "") or truth.get("pnl_pct_text") not in (None, ""):
        pnl_text = _summary_money(truth.get("pnl")) if truth.get("pnl") not in (None, "") else "-"
        facts.append(f"실현손익: {pnl_text} ({truth.get('pnl_pct_text') or '-'})")
    if broker_alignment:
        status = _metadata_value(broker_alignment.get("status"))
        local_total = broker_alignment.get("local_total")
        broker_total = broker_alignment.get("broker_total")
        missing_local = broker_alignment.get("missing_in_local_total")
        missing_broker = broker_alignment.get("missing_in_broker_total")
        facts.append(
            "브로커 주문 정합성: "
            f"{status or '-'} / local {local_total if local_total not in (None, '') else '-'}"
            f" / broker {broker_total if broker_total not in (None, '') else '-'}"
            f" / local누락 {missing_local if missing_local not in (None, '') else '-'}"
            f" / broker누락 {missing_broker if missing_broker not in (None, '') else '-'}"
        )
        snapshot_path = _metadata_value(broker_alignment.get("account_snapshot_path"))
        if snapshot_path not in {"", "-"}:
            facts.append(f"키움 계좌 스냅샷: {snapshot_path}")
    if decision.get("scanner_rank") not in (None, ""):
        score = _summary_decimal(decision.get("scanner_score"), 3)
        facts.append(f"스캐너 순위/점수: {decision.get('scanner_rank')}위 / {score}")
    chart_score = decision.get("scanner_chart_fit_score")
    if chart_score not in (None, ""):
        authority = _metadata_value(decision.get("scanner_chart_fit_authority"))
        facts.append(f"Scanner chart-fit: {_summary_decimal(chart_score, 3)} / {authority}")
    top_pick = _metadata_value(decision.get("scanner_top_pick_symbol"))
    fallback_reason = _summary_fact_text(decision.get("monitor_fallback_reason"))
    if top_pick != "-":
        facts.append(f"상위 후보 보류: {top_pick} ({fallback_reason or '-'})")
    entry_reason = _summary_fact_text(decision.get("entry_reason"))
    if entry_reason:
        facts.append(f"진입 근거: {entry_reason}")
    exit_reason = _summary_fact_text(decision.get("exit_reason"))
    if exit_reason:
        facts.append(f"청산 근거: {exit_reason}")

    problems = [_summary_problem_label(item) for item in _listify(findings.get("problems")) if str(item or "").strip()]
    causes = [_summary_root_cause_label(item) for item in _listify(findings.get("root_cause_candidates")) if str(item or "").strip()]
    questions = [_summary_eval_sentence(item) for item in _listify(findings.get("validation_questions")) if str(item or "").strip()]

    if not facts and not problems and not causes and not questions:
        return []

    lines: List[str] = ["## 🧾 확정 진단", ""]
    if facts:
        lines.append("### 확정 사실")
        lines.append("")
        lines.extend(f"* {item}" for item in facts[:10])
    if problems:
        lines.append("")
        lines.append("### 확정 문제 후보")
        lines.append("")
        lines.extend(f"* {item}" for item in problems[:8])
    if causes:
        lines.append("")
        lines.append("### 원인 후보")
        lines.append("")
        lines.extend(f"* {item}" for item in causes[:6])
    if questions:
        lines.append("")
        lines.append("### 검증 질문")
        lines.append("")
        lines.extend(f"* {item}" for item in questions[:6])
    return _strip_trailing_blanks(lines)


def _build_summary_llm_evaluation_section(
    summary_report: Dict[str, Any],
    *,
    report: Dict[str, Any] | None = None,
) -> List[str]:
    payload = summary_report if isinstance(summary_report, dict) else {}
    evaluation = _as_dict(payload.get("llm_evaluation"))
    generation = _as_dict(payload.get("generation"))
    status = str(generation.get("status") or payload.get("summary_status") or "").strip().lower()
    has_content = any(
        [
            str(evaluation.get("conclusion") or "").strip(),
            str(evaluation.get("root_cause") or "").strip(),
            _listify(evaluation.get("priority_actions")),
            _listify(evaluation.get("risk_notes")),
            _listify(evaluation.get("validation_questions")),
        ]
    )
    if not has_content:
        return []

    lines: List[str] = [
        "## 🤖 LLM 복기 초안",
        "",
        "* 성격: 아래 내용은 확정 사실이 아니라 문제 파악을 돕는 해석 초안입니다. 수치와 사실은 위 확정 진단과 Truth Surface를 우선합니다.",
    ]
    if status:
        lines.append(f"* 상태: {status}")
    action = _action_label(
        _first_present_impl(
            _as_dict((report or {}).get("final_operator_conclusion")).get("current_action"),
            (report or {}).get("action"),
            _as_dict((report or {}).get("shared_facts")).get("action"),
        )
    )
    conclusion = _summary_eval_sentence(evaluation.get("conclusion"))
    if report:
        conclusion = _authoritative_final_operator_summary(
            report,
            action=action,
            fallback=_normalize_evaluation_hold_duration(conclusion, report),
        )
    if conclusion:
        lines.append(f"* 결론: **{conclusion}**")
    root_cause = _normalize_evaluation_hold_duration(
        _summary_eval_sentence(evaluation.get("root_cause")),
        report or {},
    )
    if root_cause:
        lines.append(f"* 원인 해석: {root_cause}")

    actions = [
        _normalize_evaluation_hold_duration(_summary_eval_sentence(item), report or {})
        for item in _listify(evaluation.get("priority_actions"))
        if str(item or "").strip()
    ]
    if actions:
        lines.append("")
        lines.append("### 우선 액션")
        lines.append("")
        lines.extend(f"{idx}. {item}" for idx, item in enumerate(actions[:4], 1))

    risks = [
        _normalize_evaluation_hold_duration(_summary_eval_sentence(item), report or {})
        for item in _listify(evaluation.get("risk_notes"))
        if str(item or "").strip()
    ]
    if risks:
        lines.append("")
        lines.append("### 리스크")
        lines.append("")
        lines.extend(f"* {item}" for item in risks[:4])

    questions = [_summary_eval_sentence(item) for item in _listify(evaluation.get("validation_questions")) if str(item or "").strip()]
    if questions:
        lines.append("")
        lines.append("### 검증 질문")
        lines.append("")
        lines.extend(f"* {item}" for item in questions[:4])

    return _strip_trailing_blanks(lines)


def _normalize_evaluation_hold_duration(text: str, report: Dict[str, Any]) -> str:
    duration = _authoritative_holding_duration_label(report)
    if not text or not duration:
        return text
    return re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:초|분|시간|s|m|h)\s*(?=(?:동안\s*)?(?:보유|만에))",
        duration + " ",
        text,
        flags=re.IGNORECASE,
    )


def _section(title: str, content: List[str]) -> List[str]:
    if not content:
        return []
    lines = [f"## {title}", ""]
    lines.extend(content)
    lines.append("")
    return lines


def _strip_trailing_blanks(lines: List[str]) -> List[str]:
    cleaned: List[str] = []
    prev_blank = False
    for line in lines:
        is_blank = not str(line).strip()
        if is_blank and prev_blank:
            continue
        cleaned.append(line)
        prev_blank = is_blank
    return cleaned


def _summary_eval_sentence(value: Any) -> str:
    text = _translate_text(value).strip()
    if not text:
        return ""
    replacements = {
        "00번.symbol": "해당 종목",
        "root_cause_candidates": "원인 후보",
        "deterministic_findings": "결정론적 진단",
        "decision_flow": "의사결정 흐름",
        "truth_surface": "Truth Surface",
        "何か": "무엇인지",
        "如何": "어떤지",
        "により": "로 인해",
        "阈值": "기준",
        "況": "상황",
        "况": "상황",
        "inúmer": "국면",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = text.replace("monitor_only", "monitor-only")
    text = text.replace("cached_strategist", "cached strategist")
    text = re.sub(r"고점 대비 하락폭 기준[_-]?exit", "고점 대비 하락폭 청산", text)
    text = re.sub(r"스캐너 1순위\s+([A-Z0-9]+)", r"스캐너 상위 후보 \1", text)
    text = text.replace(" 이유로 막혀", " 이유로 보류되어")
    text = text.replace(" 이유로 막히면서", " 이유로 보류되면서")
    text = text.replace("으로 전환됨", "으로 전환됐습니다")
    text = text.replace("이유와cached", "이유와 cached")
    text = text.replace("이유는무엇인지", "이유는 무엇인지")
    text = text.replace("분포는어떤지", "분포는 어떤지")
    text = text.replace("어려움.", "어렵습니다.")
    text = text.replace("가능성입니다.", "가능성이 있습니다.")
    text = text.replace("부적절입니다.", "부적절합니다.")
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"\?입니다\.?$", "?", text)
    text = re.sub(r"함\.$", "합니다.", text)
    text = re.sub(r"었음\.$", "었습니다.", text)
    text = re.sub(r"있음\.$", "있습니다.", text)
    if text.endswith("수 있음"):
        text = text[: -len("수 있음")].rstrip() + " 수 있습니다."
    elif text.endswith("있음"):
        text = text[: -len("있음")].rstrip() + " 있습니다."
    elif text.endswith("확인"):
        text = text + "이 필요합니다."
    elif text.endswith("재검토"):
        text = text + "가 필요합니다."
    elif text.endswith("마련"):
        text = text + "이 필요합니다."
    elif text.endswith("가능성"):
        text = text + "이 있습니다."
    elif text.endswith("부적절"):
        text = text + "합니다."
    if text.endswith(("?", "!", "입니다.", "였습니다.", "합니다.", "됩니다.", "다.", ".")):
        return text
    return _ensure_sentence(text)


def _is_post_entry_gate_text(value: Any) -> bool:
    text = _translate_text(value).strip().lower()
    return bool(
        text
        and (
            "사후 모니터 재평가" in text
            or "매수 후 보유·청산 구간" in text
            or "post-entry" in text
            or "post entry" in text
        )
    )


def _is_entry_gate_status_text(value: Any) -> bool:
    text = _translate_text(value).strip()
    return bool(text and ("진입 게이트 상태" in text or "진입 게이트 점수" in text))


def _entry_reason_line(values: Iterable[Any]) -> str:
    needles = ("진입 사유", "직전 고점", "vwap", "리바운드", "돌파", "rebound", "breakout")
    for raw in values:
        text = _translate_text(raw).strip()
        if not text or _is_post_entry_gate_text(text) or _is_entry_gate_status_text(text):
            continue
        lowered = text.lower()
        if any(needle in lowered for needle in needles):
            return text.rstrip(".")
    return ""


def _entry_confidence_line(values: Iterable[Any]) -> str:
    for raw in values:
        text = _translate_text(raw).strip()
        if not text or _is_post_entry_gate_text(text):
            continue
        lowered = text.lower()
        if "신뢰도" in text or "confidence" in lowered:
            return text.rstrip(".")
    return ""


def _normalize_entry_confidence_for_operator_summary(value: str, *, action: Any, buy_price: Any) -> str:
    text = str(value or "").strip()
    if (
        text
        and "미통과" in text
        and "진입 게이트" in text
        and str(action or "").strip() == "매도"
        and buy_price not in (None, "")
    ):
        return "진입 게이트 상세는 실제 BUY 체결 이후 사후 모니터 재평가와 혼재될 수 있어 확정 표시하지 않습니다"
    return text


def _entry_confidence_for_operator_summary(values: Iterable[Any], *, action: Any, buy_price: Any) -> str:
    return _normalize_entry_confidence_for_operator_summary(
        _entry_confidence_line(values),
        action=action,
        buy_price=buy_price,
    )


_RECOVERED_PARTIAL_EXIT_NOTE = "회수/partial 청산: 당일 진입 증거가 부족해 신규 진입 평가는 제외하고, 당일 청산 결과 중심으로 봅니다."
_RECOVERED_PARTIAL_ENTRY_NOTE = "당일 진입 증거가 부족해 신규 진입 판단은 평가하지 않습니다. 이 리포트는 보유/회수 포지션의 당일 청산 결과를 중심으로 봅니다."


def _is_recovered_partial_exit_report(report: Dict[str, Any]) -> bool:
    shared = _as_dict(report.get("shared_facts"))
    final = _as_dict(report.get("final_operator_conclusion"))
    status = str(report.get("status") or shared.get("status") or "").strip().lower()
    action_raw = str(final.get("current_action") or report.get("action") or shared.get("action") or "").strip()
    action_is_sell = action_raw.upper() == "SELL" or _action_label(action_raw) == "매도"
    if status != "partial" or not action_is_sell:
        return False

    explicit_markers = (
        bool(report.get("evidence_recovery_used"))
        or str(report.get("trade_origin") or "").strip().lower() == "recovered_partial"
        or str(report.get("lifecycle_completeness") or "").strip().lower() == "partial"
    )
    entry = _as_dict(report.get("entry_decision"))
    selection = _as_dict(report.get("why_this_symbol_was_chosen"))
    entry_text = " ".join([str(entry.get("summary") or "")] + [str(item or "") for item in _listify(entry.get("bullets"))]).lower()
    entry_missing = (
        "entry evidence was not captured" in entry_text
        or "entry execution evidence is incomplete" in entry_text
        or "진입 실행 근거가 불완전" in entry_text
        or "진입 근거가 미확인" in entry_text
    )
    selected_rank = _num_opt(selection.get("selected_rank"))
    universe_size = _num_opt(selection.get("universe_size"))
    scanner_empty = selected_rank == 0 and universe_size == 0
    return bool(explicit_markers or entry_missing or scanner_empty)


def _carryover_context(report: Dict[str, Any]) -> Dict[str, Any]:
    shared = _as_dict(report.get("shared_facts"))
    final = _as_dict(report.get("final_operator_conclusion"))
    action_raw = str(final.get("current_action") or report.get("action") or shared.get("action") or "").strip()
    action_is_sell = action_raw.upper() == "SELL" or _action_label(action_raw) == "매도"

    carry_state = _metadata_value(
        _first_report_path(
            report,
            [
                "shared_facts.commander_route.applied_policy.horizon.runtime_context.carry_state",
                "shared_facts.commander_route.horizon.runtime_context.carry_state",
                "fact_payload.trade.commander_route.applied_policy.horizon.runtime_context.carry_state",
                "fact_payload.trade.shared_facts.commander_route.applied_policy.horizon.runtime_context.carry_state",
                "fact_payload.trade.canonical_agent_artifacts.monitor.applied_policy.horizon.runtime_context.carry_state",
                "monitor_snapshot.applied_policy.horizon.runtime_context.carry_state",
                "monitor_snapshot.decision_trace.applied_policy.horizon.runtime_context.carry_state",
                "runtime_context.carry_state",
            ],
        )
    )
    carry_risk_bias = _metadata_value(
        _first_report_path(
            report,
            [
                "shared_facts.commander_route.applied_policy.horizon.runtime_context.carry_risk_bias",
                "shared_facts.commander_route.horizon.runtime_context.carry_risk_bias",
                "fact_payload.trade.commander_route.applied_policy.horizon.runtime_context.carry_risk_bias",
                "fact_payload.trade.shared_facts.commander_route.applied_policy.horizon.runtime_context.carry_risk_bias",
                "fact_payload.trade.canonical_agent_artifacts.monitor.applied_policy.horizon.runtime_context.carry_risk_bias",
                "monitor_snapshot.applied_policy.horizon.runtime_context.carry_risk_bias",
                "monitor_snapshot.decision_trace.applied_policy.horizon.runtime_context.carry_risk_bias",
                "runtime_context.carry_risk_bias",
            ],
        )
    )
    actual_hold_sec = _num_opt(
        _first_report_path(
            report,
            [
                "fact_payload.trade.exit_vs_strategy_intent.actual_hold_sec",
                "fact_payload.trade.canonical_agent_artifacts.monitor.exit_vs_strategy_intent.actual_hold_sec",
                "fact_payload.trade.canonical_agent_artifacts.monitor.decision_trace.exit_vs_strategy_intent.actual_hold_sec",
                "fact_payload.trade.monitor_snapshot.exit_vs_strategy_intent.actual_hold_sec",
                "monitor_snapshot.exit_vs_strategy_intent.actual_hold_sec",
                "monitor_snapshot.decision_trace.exit_vs_strategy_intent.actual_hold_sec",
                "exit_vs_strategy_intent.actual_hold_sec",
                "shared_facts.exit_vs_strategy_intent.actual_hold_sec",
            ],
        )
    )
    exit_ts = _first_report_path(
        report,
        [
            "fact_payload.trade.exit_summary.ts",
            "fact_payload.trade.lifecycle_summary.exit.ts",
            "shared_facts.exit_ts",
            "exit_summary.ts",
        ],
    )
    if not exit_ts:
        for row in _listify(report.get("full_timeline") if isinstance(report.get("full_timeline"), list) else report.get("timeline")):
            row_obj = _as_dict(row)
            event = str(row_obj.get("event") or row_obj.get("step") or "").lower()
            if "exit" in event or "sell" in event or "청산" in event:
                exit_ts = row_obj.get("ts") or row_obj.get("timestamp")
                break

    exit_dt = _parse_report_datetime(exit_ts)
    estimated_entry_dt = None
    if exit_dt is not None and actual_hold_sec is not None and actual_hold_sec > 0:
        estimated_entry_dt = exit_dt - timedelta(seconds=actual_hold_sec)

    carry_state_key = carry_state.lower()
    explicit_carry = carry_state_key in {
        "overnight_open",
        "multi_session_stale",
        "eod_carry_approved",
        "carry_overnight_approved",
        "overnight",
    }

    entry_kst = _to_kst(estimated_entry_dt)
    exit_kst = _to_kst(exit_dt)
    weekend_carry = False
    crosses_session_date = False
    if entry_kst is not None and exit_kst is not None:
        crosses_session_date = entry_kst.date() != exit_kst.date()
        weekend_carry = (
            entry_kst.weekday() == 4
            and exit_kst.weekday() == 0
            and entry_kst.date() != exit_kst.date()
        ) or (exit_kst.date() - entry_kst.date()).days >= 2
    is_carryover_exit = bool(action_is_sell and (explicit_carry or crosses_session_date))

    return {
        "is_carryover_exit": is_carryover_exit,
        "carry_state": carry_state,
        "carry_state_label": _carry_state_label(carry_state, weekend_carry=weekend_carry),
        "carry_risk_bias": carry_risk_bias,
        "carry_risk_label": _carry_risk_label(carry_risk_bias),
        "actual_hold_sec": actual_hold_sec,
        "duration_label": _duration_label_seconds(actual_hold_sec),
        "exit_ts": exit_ts,
        "exit_kst": _format_kst_datetime(exit_dt),
        "exit_date_kst": _format_kst_date(exit_dt),
        "estimated_entry_kst": _format_kst_datetime(estimated_entry_dt),
        "estimated_entry_date_kst": _format_kst_date(estimated_entry_dt),
        "weekend_carry": weekend_carry,
        "date_basis": "actual_hold_sec와 청산 시각 역산",
    }


def _strategy_horizon_label(value: Any) -> str:
    return _strategy_horizon_label_impl(value, metadata_value=_metadata_value)


def _strategy_horizon_reason_label(value: Any) -> str:
    return _strategy_horizon_reason_label_impl(value, metadata_value=_metadata_value)


def _strategy_horizon_alignment_label(value: Any) -> str:
    return _strategy_horizon_alignment_label_impl(value, metadata_value=_metadata_value)


def _duration_label_compact(value: Any) -> str:
    return _duration_label_compact_impl(value, num_opt=_num_opt)


def _hold_window_label(window: Dict[str, Any]) -> str:
    return _hold_window_label_impl(
        window,
        as_dict=_as_dict,
        duration_label_compact_fn=_duration_label_compact,
    )


def _strategy_horizon_report_surface(report: Dict[str, Any]) -> Dict[str, Any]:
    surface = _strategy_horizon_report_surface_impl(
        report,
        as_dict=_as_dict,
        first_report_path=_first_report_path,
        compact_post_exit_shadow=_compact_post_exit_shadow,
        post_exit_shadow_surface=_post_exit_shadow_surface,
        carryover_context=_carryover_context,
        num_opt=_num_opt,
        duration_label_compact_fn=_duration_label_compact,
    )
    authoritative_hold_sec = _authoritative_hold_duration_seconds(report)
    if authoritative_hold_sec is not None:
        surface = dict(surface)
        surface["actual_hold_sec"] = authoritative_hold_sec
        surface["actual_hold_label"] = _duration_label_seconds(authoritative_hold_sec)
        surface["actual_hold_source"] = "entry_exit_execution_timestamps"
    return surface


def _build_strategy_horizon_lines(report: Dict[str, Any], *, compact: bool = False) -> List[str]:
    return _build_strategy_horizon_lines_impl(
        report,
        compact=compact,
        strategy_horizon_report_surface_fn=_strategy_horizon_report_surface,
        strategy_horizon_label_fn=_strategy_horizon_label,
        strategy_horizon_alignment_label_fn=_strategy_horizon_alignment_label,
        strategy_horizon_reason_label_fn=_strategy_horizon_reason_label,
        as_dict=_as_dict,
        axis_label=_axis_label,
        hold_window_label_fn=_hold_window_label,
        duration_label_compact_fn=_duration_label_compact,
    )


def _first_report_path(root: Dict[str, Any], paths: Iterable[str]) -> Any:
    for path in paths:
        value = _get_report_path(root, path)
        if value not in (None, "", [], {}):
            return value
    return None


def _get_report_path(root: Any, path: str) -> Any:
    current = root
    for part in str(path or "").split("."):
        if not part:
            continue
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
    return current


def _parse_report_datetime(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _to_kst(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return value.astimezone(timezone(timedelta(hours=9)))


def _format_kst_datetime(value: Optional[datetime]) -> str:
    kst = _to_kst(value)
    if kst is None:
        return ""
    return kst.strftime("%Y-%m-%d %H:%M KST")


def _format_kst_date(value: Optional[datetime]) -> str:
    kst = _to_kst(value)
    if kst is None:
        return ""
    return kst.strftime("%Y-%m-%d")


def _duration_label_seconds(value: Any) -> str:
    seconds = _num_opt(value)
    if seconds is None or seconds <= 0:
        return ""
    total = int(round(seconds))
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts: List[str] = []
    if days:
        parts.append(f"{days}일")
    if hours:
        parts.append(f"{hours}시간")
    if minutes:
        parts.append(f"{minutes}분")
    if seconds or not parts:
        parts.append(f"{seconds}초")
    return " ".join(parts)


def _authoritative_hold_duration_seconds(report: Dict[str, Any]) -> Optional[float]:
    """Resolve actual hold time from entry/exit execution timestamps first."""

    entry_ts = _first_report_path(
        report,
        [
            "fact_payload.trade.entry_execution_details.ts",
            "entry_execution_details.ts",
            "fact_payload.trade.entry_summary.ts",
            "entry_summary.ts",
        ],
    )
    exit_ts = _first_report_path(
        report,
        [
            "fact_payload.trade.exit_execution_details.ts",
            "fact_payload.trade.execution_details.ts",
            "exit_execution_details.ts",
            "execution_details.ts",
            "fact_payload.trade.exit_summary.ts",
            "exit_summary.ts",
        ],
    )
    entry_dt = _parse_report_datetime(entry_ts)
    exit_dt = _parse_report_datetime(exit_ts)
    if entry_dt is not None and exit_dt is not None and exit_dt >= entry_dt:
        return float((exit_dt - entry_dt).total_seconds())

    return _num_opt(
        _first_report_path(
            report,
            [
                "fact_payload.trade.exit_vs_strategy_intent.actual_hold_sec",
                "fact_payload.trade.canonical_agent_artifacts.monitor.exit_vs_strategy_intent.actual_hold_sec",
                "monitor_snapshot.exit_vs_strategy_intent.actual_hold_sec",
                "exit_vs_strategy_intent.actual_hold_sec",
                "shared_facts.exit_vs_strategy_intent.actual_hold_sec",
            ],
        )
    )


def _authoritative_holding_duration_label(report: Dict[str, Any]) -> str:
    return _duration_label_seconds(_authoritative_hold_duration_seconds(report))


def _carry_state_label(value: Any, *, weekend_carry: bool = False) -> str:
    key = str(value or "").strip().lower()
    labels = {
        "multi_session_stale": "전일/주말 이월 보유",
        "overnight_open": "오버나이트 보유",
        "eod_carry_approved": "장마감 이월 승인",
        "carry_overnight_approved": "오버나이트 승인",
        "overnight": "오버나이트 보유",
    }
    if key in labels:
        return labels[key]
    if weekend_carry:
        return "주말 이월 보유"
    return _metadata_value(value) if _metadata_value(value) != "-" else "오버나이트/이월 보유"


def _carry_risk_label(value: Any) -> str:
    key = str(value or "").strip().lower()
    labels = {
        "urgent_exit_review": "장기/주말 이월 후 우선 청산 검토",
        "exit_review": "청산 검토",
        "normal": "일반",
    }
    if key in labels:
        return labels[key]
    text = _metadata_value(value)
    return "" if text == "-" else text


def _translated_metadata(value: Any) -> str:
    return _metadata_value(_translate_text(value))


def _correct_final_operator_summary(summary: str, *, action: Any) -> str:
    text = str(summary or "").strip()
    action_label = str(action or "").strip()
    if not text:
        return ""
    if action_label == "매도":
        return re.sub(r"현재 판단은 진입 유지(?:입니다|이다)\.?", "현재 판단은 청산 완료입니다.", text, count=1)
    if action_label == "매수":
        return re.sub(r"현재 판단은 청산 완료(?:입니다|이다)\.?", "현재 판단은 진입 유지입니다.", text, count=1)
    return text


def _authoritative_final_operator_summary(
    report: Dict[str, Any],
    *,
    action: Any,
    fallback: str = "",
) -> str:
    """Keep the closed-trade conclusion on broker truth, not monitor marks."""

    shared = _as_dict(report.get("shared_facts"))
    truth = _get_truth_surface(report)
    pnl = _as_dict(truth.get("pnl"))
    truth_status = _as_dict(truth.get("status"))
    status = str(truth_status.get("status") or report.get("status") or shared.get("status") or "").lower()
    action_label = str(action or "").strip()
    pnl_value = _num_opt(pnl.get("value"))
    pnl_pct, _ = _operator_pnl_pct_impl(pnl, shared)
    if status != "closed" or action_label != "매도" or (pnl_value is None and pnl_pct is None):
        return _correct_final_operator_summary(fallback, action=action)

    symbol = _clip(report.get("symbol") or shared.get("symbol"), 32) or "해당 종목"
    duration = _authoritative_holding_duration_label(report)
    result_basis = pnl_value if pnl_value is not None else _num_opt(pnl_pct)
    result_label = "이익" if (result_basis or 0.0) > 0 else "손실" if (result_basis or 0.0) < 0 else "보합"
    details: List[str] = []
    if pnl_pct is not None:
        details.append(_fmt_pct(pnl_pct))
    if pnl_value is not None:
        details.append(f"{pnl_value:,.0f}원")
    detail_text = f" ({', '.join(details)})" if details else ""
    duration_text = f"{duration} 보유 후 " if duration else ""
    return (
        f"현재 판단은 청산 완료입니다. {symbol} 거래는 브로커 체결 기준 "
        f"{duration_text}{result_label}{detail_text}로 청산 완료됐습니다. "
        "모니터의 청산 전 시세 관측값은 실제 체결 손익과 구분합니다."
    )


def _selection_fallback_context(selection: Dict[str, Any], traded_symbol: Any = "") -> Dict[str, Any]:
    section = _as_dict(selection)
    trace = _as_dict(section.get("scanner_selection_trace"))
    selected_symbol = _metadata_value(
        traded_symbol
        or section.get("symbol")
        or trace.get("monitor_selected_symbol")
        or trace.get("selected_symbol")
    )
    top_pick = _metadata_value(section.get("scanner_top_pick_symbol") or trace.get("scanner_top_pick_symbol"))
    used = bool(section.get("monitor_fallback_used") or trace.get("monitor_fallback_used"))
    if not top_pick or top_pick == "-":
        used = False
    if top_pick and selected_symbol and top_pick == selected_symbol:
        used = False
    reason_raw = section.get("monitor_fallback_reason") or trace.get("monitor_fallback_reason") or trace.get("monitor_trigger_reason")
    reason = _translate_reason_phrase(str(reason_raw or "")) if reason_raw else ""
    return {
        "used": used,
        "selected_symbol": selected_symbol,
        "scanner_top_pick_symbol": top_pick if top_pick != "-" else "",
        "reason": reason,
        "selection_path": _metadata_value(section.get("selection_path") or trace.get("selection_path")),
    }


def _clip(value: Any, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _listify(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _append_unique_text(out: List[str], value: Any, *, max_len: int = 80) -> None:
    _append_unique_text_impl(out, value, max_len=max_len, metadata_value=_metadata_value, translate_text=_translate_text)


def _append_theme_values(out: List[str], raw_theme: Any) -> None:
    _append_theme_values_impl(out, raw_theme, metadata_value=_metadata_value, translate_text=_translate_text)


def _iter_trade_symbol_metadata_sources(report: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    return _iter_trade_symbol_metadata_sources_impl(report)


def _symbol_in_theme_components(symbol: str, components: Any) -> bool:
    return _symbol_in_theme_components_impl(symbol, components)


def _iter_nested_dicts(value: Any, *, max_depth: int = 8) -> Iterable[Dict[str, Any]]:
    return _iter_nested_dicts_impl(value, max_depth=max_depth)


def _component_themes_for_symbol(report: Dict[str, Any], symbol: str) -> List[str]:
    return _component_themes_for_symbol_impl(
        report,
        symbol,
        metadata_value=_metadata_value,
        translate_text=_translate_text,
    )


def _infer_symbol_name_from_report_text(report: Dict[str, Any], symbol: str) -> str:
    return _infer_symbol_name_from_report_text_impl(
        report,
        symbol,
        metadata_value=_metadata_value,
        translate_text=_translate_text,
    )


def _resolve_trade_symbol_metadata(report: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    return _resolve_trade_symbol_metadata_impl(
        report,
        symbol,
        metadata_value=_metadata_value,
        translate_text=_translate_text,
    )

def _resolve_entry_execution_visibility(report: Dict[str, Any]) -> Dict[str, Any]:
    visibility = _as_dict(report.get("entry_execution_visibility"))
    entry_monitor = _resolve_entry_monitor_artifact(report)
    strategist_output = _as_dict(report.get("strategist_output"))
    strategy_detail = _as_dict(strategist_output.get("strategy_detail"))
    monitor = _as_dict(report.get("monitor_snapshot"))
    shared = _as_dict(report.get("shared_facts"))
    commander_route = _as_dict(shared.get("commander_route"))
    entry_policy_ref = _as_dict(entry_monitor.get("policy_ref"))
    entry_applied_policy = _as_dict(entry_policy_ref.get("applied_policy"))

    proposal = _as_dict(visibility.get("strategy_candidate_watch_proposal"))
    if not proposal:
        proposal = _as_dict(strategy_detail.get("candidate_watch_policy"))

    entry_control = _first_dict(
        _as_dict(entry_policy_ref.get("entry_control")),
        _as_dict(entry_applied_policy.get("commander_entry_control")),
        _as_dict(entry_applied_policy.get("entry_control")),
        _as_dict(visibility.get("commander_entry_control")),
    )
    if not entry_control:
        entry_control = _as_dict(commander_route.get("entry_control"))
    if not proposal:
        proposal = _as_dict(entry_control.get("proposal")) or _as_dict(entry_control.get("candidate_watch_policy_proposal"))
    if proposal and entry_control:
        proposal = dict(proposal)
        nested = _as_dict(entry_control.get("proposal")) or _as_dict(entry_control.get("candidate_watch_policy_proposal"))
        if proposal.get("max_priority_rank") in (None, "") and entry_control.get("proposed_max_priority_rank") not in (None, ""):
            proposal["max_priority_rank"] = entry_control.get("proposed_max_priority_rank")
        if proposal.get("max_runner_ups") in (None, "") and entry_control.get("proposed_max_runner_ups") not in (None, ""):
            proposal["max_runner_ups"] = entry_control.get("proposed_max_runner_ups")
        if proposal.get("cascade_enabled") in (None, "") and nested.get("cascade_enabled") not in (None, ""):
            proposal["cascade_enabled"] = nested.get("cascade_enabled")
        for key in ("source", "behavior_effect", "tactical_strategy", "reason"):
            if proposal.get(key) in (None, "") and nested.get(key) not in (None, ""):
                proposal[key] = nested.get(key)
        for key in ("cascade_allowed_reasons", "cascade_blocked_reasons"):
            if proposal.get(key) in (None, "", []) and nested.get(key) not in (None, "", []):
                proposal[key] = nested.get(key)

    cascade = _first_dict(
        _as_dict(entry_monitor.get("entry_candidate_cascade")),
        _as_dict(_as_dict(entry_monitor.get("scanner_monitor_handoff")).get("entry_candidate_cascade")),
        _as_dict(visibility.get("monitor_entry_candidate_cascade")),
        _as_dict(monitor.get("entry_candidate_cascade")),
    )
    focus_context = _first_dict(
        _as_dict(entry_monitor.get("monitor_focus_context")),
        _as_dict(visibility.get("monitor_focus_context")),
        _as_dict(monitor.get("monitor_focus_context")),
    )
    grouped_trace = _first_dict(
        _as_dict(entry_monitor.get("entry_grouped_logic_trace")),
        _as_dict(_as_dict(entry_monitor.get("threshold_snapshot")).get("entry_grouped_logic_trace")),
        _as_dict(visibility.get("entry_grouped_logic_trace")),
    )

    out: Dict[str, Any] = {}
    if proposal:
        out["strategy_candidate_watch_proposal"] = proposal
    if entry_control:
        out["commander_entry_control"] = entry_control
    if cascade:
        out["monitor_entry_candidate_cascade"] = cascade
    if focus_context:
        out["monitor_focus_context"] = focus_context
    if grouped_trace:
        out["entry_grouped_logic_trace"] = grouped_trace
    summary = _metadata_value(visibility.get("summary"))
    if summary:
        out["summary"] = summary
    return out


def _first_dict(*items: Dict[str, Any]) -> Dict[str, Any]:
    for item in items:
        if isinstance(item, dict) and item:
            return item
    return {}


def _safe_read_json_object(path_value: Any) -> Dict[str, Any]:
    text = str(path_value or "").strip()
    if not text:
        return {}
    try:
        path = Path(text)
        if not path.exists() or not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _is_entry_monitor_artifact(payload: Dict[str, Any]) -> bool:
    if not payload:
        return False
    focus = _as_dict(payload.get("monitor_focus_context"))
    if bool(payload.get("entry_triggered")) or str(payload.get("entry_decision") or "").upper() == "BUY":
        return True
    if bool(focus.get("entry_triggered")) or str(focus.get("entry_decision") or "").upper() == "BUY":
        return True
    return False


def _canonical_monitor_from_trade_report_path(report: Dict[str, Any], run_id: str) -> Dict[str, Any]:
    paths = _as_dict(report.get("paths"))
    report_path_text = str(paths.get("ai_trade_report_json") or "").strip()
    if not report_path_text or not run_id:
        return {}
    try:
        report_path = Path(report_path_text)
        parts = list(report_path.parts)
        idx = parts.index("trades")
        reports_root = Path(*parts[:idx])
        day = parts[idx + 1]
    except Exception:
        return {}
    return _safe_read_json_object(reports_root / "canonical" / day / run_id / "monitor.json")


def _canonical_monitor_from_section_provenance(report: Dict[str, Any]) -> Dict[str, Any]:
    provenance = _as_dict(report.get("section_provenance"))
    for key in ("entry_decision", "why_this_symbol_was_chosen", "market_context_at_entry"):
        row = _as_dict(provenance.get(key))
        artifact_path = str(row.get("artifact_path") or "").strip()
        if not artifact_path:
            continue
        monitor = _safe_read_json_object(Path(artifact_path).with_name("monitor.json"))
        if _is_entry_monitor_artifact(monitor):
            return monitor
    return {}


def _resolve_entry_monitor_artifact(report: Dict[str, Any]) -> Dict[str, Any]:
    fact_payload = _as_dict(report.get("fact_payload"))
    trade_payload = _as_dict(fact_payload.get("trade"))
    entry_summary = _as_dict(trade_payload.get("entry_summary"))
    entry_monitor = _as_dict(entry_summary.get("monitor_context"))
    if _is_entry_monitor_artifact(entry_monitor):
        return entry_monitor

    entry_run_id = str(entry_summary.get("run_id") or report.get("run_id") or "").strip()
    monitor = _canonical_monitor_from_trade_report_path(report, entry_run_id)
    if _is_entry_monitor_artifact(monitor):
        return monitor

    return _canonical_monitor_from_section_provenance(report)


def _rank_scope_text(row: Dict[str, Any]) -> str:
    if not row:
        return ""
    rank = row.get("max_priority_rank")
    runner_ups = row.get("max_runner_ups")
    if rank in (None, "") and runner_ups in (None, ""):
        return ""
    parts: List[str] = []
    if rank not in (None, ""):
        parts.append(f"rank<={rank}")
    if runner_ups not in (None, ""):
        parts.append(f"runner_ups={runner_ups}")
    return " / ".join(parts)


def _watch_scope_label(row: Dict[str, Any]) -> str:
    if not row:
        return ""
    rank = row.get("max_priority_rank")
    runner_ups = row.get("max_runner_ups")
    parts: List[str] = []
    if rank not in (None, ""):
        parts.append(f"{rank}위까지")
    if runner_ups not in (None, ""):
        parts.append(f"차순위 {runner_ups}개")
    return " / ".join(parts)


def _candidate_watch_reason_label(value: Any) -> str:
    reason = _metadata_value(value)
    if not reason or reason == "-":
        return ""
    mapping = {
        "open_position_present": "보유 포지션 존재",
        "cascade_disabled_by_entry_control": "지휘관 설정으로 차순위 확인 비활성",
        "candidate_watch_disabled": "후보 감시 비활성",
        "entry_control_disabled": "지휘관 진입 제어 비활성",
    }
    return mapping.get(reason, reason)


def _display_candidate_symbol(value: Any) -> str:
    symbol = _metadata_value(value)
    if not symbol or symbol == "-":
        return ""
    return symbol if re.fullmatch(r"\d{6}", symbol) else ""


def _candidate_cascade_symbols(cascade: Dict[str, Any]) -> set[str]:
    symbols: set[str] = set()

    def add(value: Any) -> None:
        symbol = _display_candidate_symbol(value)
        if symbol:
            symbols.add(symbol)

    for key in (
        "top_pick_symbol",
        "fallback_from_symbol",
        "fallback_to_symbol",
        "final_selected_symbol",
    ):
        add(cascade.get(key))
    for key in ("runner_up_symbols", "candidate_symbols"):
        for value in _listify(cascade.get(key)):
            add(value)
    for row in _listify(cascade.get("fallback_trace")):
        row_obj = _as_dict(row)
        add(row_obj.get("symbol"))
    return symbols


def _candidate_cascade_matches_trade(cascade: Dict[str, Any], traded_symbol: Any) -> bool:
    symbol = _display_candidate_symbol(traded_symbol)
    if not symbol or not cascade:
        return True
    cascade_symbols = _candidate_cascade_symbols(cascade)
    if not cascade_symbols:
        return True
    return symbol in cascade_symbols


def _entry_watch_execution_lines(report: Dict[str, Any], *, require_trade_symbol_match: bool = False) -> List[str]:
    visibility = _resolve_entry_execution_visibility(report)
    if not visibility:
        return []
    proposal = _as_dict(visibility.get("strategy_candidate_watch_proposal"))
    entry_control = _as_dict(visibility.get("commander_entry_control"))
    cascade = _as_dict(visibility.get("monitor_entry_candidate_cascade"))
    focus_context = _as_dict(visibility.get("monitor_focus_context"))
    shared = _as_dict(report.get("shared_facts"))
    traded_symbol = _display_candidate_symbol(report.get("symbol") or shared.get("symbol"))
    cascade_matches_trade = (
        _candidate_cascade_matches_trade(cascade, traded_symbol)
        if require_trade_symbol_match
        else True
    )
    lines: List[str] = []

    if focus_context:
        entry_symbol = _display_candidate_symbol(
            focus_context.get("entry_final_symbol") or focus_context.get("entry_candidate_symbol")
        )
        position_symbol = _display_candidate_symbol(focus_context.get("position_focus_symbol"))
        if entry_symbol and position_symbol and entry_symbol != position_symbol:
            reason = _metadata_value(
                focus_context.get("entry_guard_reason") or focus_context.get("entry_reason")
            )
            text = f"신규 후보 {entry_symbol} 평가 / 보유 관리 {position_symbol}"
            if reason and reason != "-":
                text += f" / 신규 후보 보류 사유: {_candidate_watch_reason_label(reason)}"
            lines.append(text)

    if entry_control:
        scope = _watch_scope_label(entry_control)
        text = f"감시 범위: {scope}" if scope else ""
        if entry_control.get("cascade_enabled") not in (None, ""):
            cascade_text = f"cascade {'활성' if bool(entry_control.get('cascade_enabled')) else '비활성'}"
            text = f"{text} / {cascade_text}".strip(" /")
        if text:
            lines.append(text)

    if proposal:
        scope = _watch_scope_label(proposal)
        tactical = _metadata_value(proposal.get("tactical_strategy"))
        if scope:
            text = f"전략가 제안: {scope}"
            if tactical and tactical != "-":
                text += f" / 전술={tactical}"
            lines.append(text)
        elif tactical and tactical != "-" and not lines:
            lines.append(f"전술={tactical}.")

    if cascade and cascade_matches_trade:
        top_pick = _display_candidate_symbol(cascade.get("top_pick_symbol"))
        top_reason = _metadata_value(cascade.get("top_pick_reason") or cascade.get("reason"))
        runner_ups = [
            _display_candidate_symbol(symbol)
            for symbol in _listify(cascade.get("runner_up_symbols"))
            if _display_candidate_symbol(symbol)
        ]
        attempted = bool(cascade.get("attempted"))
        if attempted:
            text = f"실제 확인: 1순위 {top_pick or '-'} 보류"
            if runner_ups:
                text += f" -> 차순위 {', '.join(runner_ups)} 확인"
            if top_reason and top_reason != "-":
                text += f" (사유: {_candidate_watch_reason_label(top_reason)})"
            lines.append(text)
        else:
            blocked = _candidate_watch_reason_label(cascade.get("blocked_reason"))
            details: List[str] = []
            if top_pick and top_pick != "-":
                details.append(f"1순위 {top_pick}")
            if blocked:
                details.append(f"사유: {blocked}")
            text = "실제 확인: 차순위 미실행"
            if details:
                text += f" ({', '.join(details)})"
            lines.append(text)
        if bool(cascade.get("fallback_used")):
            final_symbol = _display_candidate_symbol(cascade.get("fallback_to_symbol") or cascade.get("final_selected_symbol"))
            final_rank = cascade.get("fallback_to_rank") or cascade.get("final_selected_rank")
            lines.append(f"최종 후보: {final_symbol or '-'}{f'({final_rank}위)' if final_rank not in (None, '') else ''}")
        elif cascade.get("final_selected_symbol"):
            final_symbol = _display_candidate_symbol(cascade.get("final_selected_symbol"))
            final_rank = cascade.get("final_selected_rank")
            lines.append(f"최종 후보: {final_symbol}{f'({final_rank}위)' if final_rank not in (None, '') else ''}")

    return _dedupe([line for line in lines if line])


def _entry_watch_summary_lines(report: Dict[str, Any], *, require_trade_symbol_match: bool = False) -> List[str]:
    visibility = _resolve_entry_execution_visibility(report)
    if not visibility:
        return []
    entry_control = _as_dict(visibility.get("commander_entry_control"))
    cascade = _as_dict(visibility.get("monitor_entry_candidate_cascade"))
    shared = _as_dict(report.get("shared_facts"))
    traded_symbol = _display_candidate_symbol(report.get("symbol") or shared.get("symbol"))
    cascade_matches_trade = (
        _candidate_cascade_matches_trade(cascade, traded_symbol)
        if require_trade_symbol_match
        else True
    )
    lines: List[str] = []

    scope = _watch_scope_label(entry_control)
    if scope:
        parts = [scope]
        if entry_control.get("cascade_enabled") not in (None, ""):
            parts.append(f"cascade {'활성' if bool(entry_control.get('cascade_enabled')) else '비활성'}")
        lines.append(" / ".join(parts))

    attempted = bool(cascade.get("attempted"))
    top_pick = _display_candidate_symbol(cascade.get("top_pick_symbol"))
    if cascade and cascade_matches_trade:
        if attempted:
            runner_ups = [
                _display_candidate_symbol(symbol)
                for symbol in _listify(cascade.get("runner_up_symbols"))
                if _display_candidate_symbol(symbol)
            ]
            if runner_ups:
                lines.append(f"실제 확인: 1순위 {top_pick or '-'} 보류 -> 차순위 {', '.join(runner_ups)} 확인")
        else:
            blocked = _candidate_watch_reason_label(cascade.get("blocked_reason"))
            details: List[str] = []
            if top_pick and top_pick != "-":
                details.append(f"1순위 {top_pick}")
            if blocked:
                details.append(f"사유: {blocked}")
            text = "실제 확인: 차순위 미실행"
            if details:
                text += f" ({', '.join(details)})"
            lines.append(text)

    if cascade and cascade_matches_trade:
        final_symbol = _display_candidate_symbol(cascade.get("final_selected_symbol") or cascade.get("fallback_to_symbol"))
        final_rank = cascade.get("final_selected_rank") or cascade.get("fallback_to_rank")
        if final_symbol and final_symbol != "-":
            rank_text = f"({final_rank}위)" if final_rank not in (None, "") else ""
            lines.append(f"최종 후보: {final_symbol}{rank_text}")

    return lines


def _has_payload(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _merge_preferred(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(fallback or {})
    for key, value in (primary or {}).items():
        if _has_payload(value):
            merged[key] = value
    return merged


def _resolve_market_context(report: Dict[str, Any]) -> Dict[str, Any]:
    primary = _as_dict(report.get("market_context_at_entry"))
    fallback = _as_dict(report.get("market_context_human"))
    trace = _as_dict(report.get("strategist_trace_summary"))
    feedback = _as_dict(report.get("strategist_feedback_input"))
    merged = _merge_preferred(primary, fallback)

    for key in ("summary", "playbook", "themes", "headline_count", "news_query_count"):
        if not _has_payload(merged.get(key)) and _has_payload(trace.get(key)):
            merged[key] = trace.get(key)
    if not _has_payload(merged.get("regime")) and _has_payload(trace.get("market_regime")):
        merged["regime"] = trace.get("market_regime")
    if not _has_payload(merged.get("market_sentiment")) and _has_payload(trace.get("market_sentiment")):
        merged["market_sentiment"] = trace.get("market_sentiment")
    if not _has_payload(merged.get("global_sentiment_score")) and _has_payload(trace.get("global_sentiment_score")):
        merged["global_sentiment_score"] = trace.get("global_sentiment_score")
    if not _has_payload(merged.get("vix_level")) and _has_payload(trace.get("vix_level")):
        merged["vix_level"] = trace.get("vix_level")
    if not _has_payload(merged.get("korea_indices")) and _has_payload(trace.get("korea_indices")):
        merged["korea_indices"] = trace.get("korea_indices")
    if not _has_payload(merged.get("market_news_titles")) and _has_payload(merged.get("strategist_market_headlines")):
        merged["market_news_titles"] = merged.get("strategist_market_headlines")
    if not _has_payload(merged.get("candidate_news_titles")) and _has_payload(merged.get("strategist_symbol_headlines")):
        merged["candidate_news_titles"] = merged.get("strategist_symbol_headlines")
    if not _has_payload(merged.get("market_news_titles")) and _has_payload(report.get("strategist_market_headlines")):
        merged["market_news_titles"] = report.get("strategist_market_headlines")
    if not _has_payload(merged.get("candidate_news_titles")) and _has_payload(report.get("strategist_symbol_headlines")):
        merged["candidate_news_titles"] = report.get("strategist_symbol_headlines")
    if not _has_payload(merged.get("news_symbol_linkage")) and _has_payload(report.get("news_symbol_linkage")):
        merged["news_symbol_linkage"] = report.get("news_symbol_linkage")
    if not _has_payload(merged.get("news_query_targets")) and _has_payload(feedback.get("news_query_targets")):
        merged["news_query_targets"] = feedback.get("news_query_targets")
    if not _has_payload(merged.get("key_events")) and _has_payload(feedback.get("key_events")):
        merged["key_events"] = feedback.get("key_events")
    return merged


def _num_opt(value: Any) -> Optional[float]:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _fmt_price(value: Any) -> str:
    num = _num_opt(value)
    if num is None:
        return "-"
    return f"{num:.2f}"


def _fmt_pct(value: Any) -> str:
    num = _num_opt(value)
    if num is None:
        return "-"
    return f"{num * 100.0:.2f}%"


def _fmt_signed_pct(value: Any) -> str:
    num = _num_opt(value)
    if num is None:
        return "-"
    sign = "+" if num > 0 else ""
    return f"{sign}{num * 100.0:.2f}%"


def _fmt_multiple(value: Any) -> str:
    num = _num_opt(value)
    if num is None:
        return "-"
    return f"{num:.2f}배"


def _korea_index_lines(context: Dict[str, Any]) -> List[str]:
    packet = _as_dict(context.get("korea_indices"))
    indices = _as_dict(packet.get("indices"))
    lines: List[str] = []
    for name in ("KOSPI", "KOSDAQ"):
        row = _as_dict(indices.get(name))
        if not row:
            continue
        current = _num_opt(row.get("current"))
        previous = _num_opt(row.get("previous_close"))
        change_pct = _num_opt(row.get("change_pct"))
        if current is None and previous is None and change_pct is None:
            continue
        pieces = [name]
        if current is not None:
            pieces.append(f"현재 {current:,.2f}")
        if previous is not None:
            pieces.append(f"전일 {previous:,.2f}")
        if change_pct is not None:
            pieces.append(f"등락률 {change_pct:+.2f}%")
        lines.append(" ".join(pieces))
    return lines


def _operator_pnl_pct(truth_pnl: Dict[str, Any], shared: Dict[str, Any]) -> tuple[Any, bool]:
    return _operator_pnl_pct_impl(truth_pnl, shared)


def _first_present(*values: Any) -> Any:
    return _first_present_impl(*values)


def _extract_trade_quantity(report: Dict[str, Any]) -> Optional[float]:
    return _extract_trade_quantity_impl(report, as_dict=_as_dict, num_opt=_num_opt)


def _infer_trade_quantity_from_costs(
    *,
    buy_price: Any,
    sell_price: Any,
    pnl: Any,
    fee: Any,
    tax: Any,
) -> Optional[float]:
    return _infer_trade_quantity_from_costs_impl(
        buy_price=buy_price,
        sell_price=sell_price,
        pnl=pnl,
        fee=fee,
        tax=tax,
        num_opt=_num_opt,
    )


def _build_trade_cost_analysis(report: Dict[str, Any]) -> Dict[str, Any]:
    return _build_trade_cost_analysis_impl(
        report,
        as_dict=_as_dict,
        num_opt=_num_opt,
        get_truth_surface_fn=_get_truth_surface,
        extract_trade_quantity_fn=_extract_trade_quantity,
    )


def _trade_cost_analysis_lines(report: Dict[str, Any], *, bullet: str = "*") -> List[str]:
    return _trade_cost_analysis_lines_impl(
        report,
        bullet=bullet,
        build_trade_cost_analysis_fn=_build_trade_cost_analysis,
        fmt_pct=_fmt_pct,
        summary_money=_summary_money,
    )


def _post_exit_shadow_surface(report: Dict[str, Any]) -> Dict[str, Any]:
    return _post_exit_shadow_surface_impl(report)


def _checkpoint_label(value: str) -> str:
    return _checkpoint_label_impl(value)


def _compact_post_exit_shadow(shadow: Dict[str, Any]) -> Dict[str, Any]:
    return _compact_post_exit_shadow_impl(shadow)


def _build_post_exit_shadow_summary_lines(report: Dict[str, Any]) -> List[str]:
    return _build_post_exit_shadow_summary_lines_impl(
        report,
        summary_money=_summary_money,
        fmt_pct=_fmt_pct,
        metadata_value=_metadata_value,
        num_opt=_num_opt,
    )

def _summary_money(value: Any) -> str:
    num = _num_opt(value)
    if num is None:
        return "-"
    if abs(num) >= 100:
        return f"{num:,.0f}"
    return f"{num:,.2f}".rstrip("0").rstrip(".")


def _summary_decimal(value: Any, digits: int = 3) -> str:
    num = _num_opt(value)
    if num is None:
        return "-"
    return f"{num:.{max(0, int(digits))}f}".rstrip("0").rstrip(".")


def _first_present_value(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _resolve_entry_signal_snapshot(report: Dict[str, Any]) -> Dict[str, Any]:
    monitor = _as_dict(report.get("monitor_snapshot"))
    shared = _as_dict(report.get("shared_facts"))
    visibility = _resolve_entry_execution_visibility(report)
    focus_context = _as_dict(visibility.get("monitor_focus_context"))
    entry_metrics = _as_dict(monitor.get("entry_metrics"))
    if not entry_metrics:
        entry_metrics = _as_dict(focus_context.get("entry_metrics"))
    if not entry_metrics:
        entry_metrics = _as_dict(report.get("entry_metrics"))
    if not entry_metrics:
        entry_metrics = _as_dict(shared.get("entry_metrics"))
    human_detail_observed = _as_dict(entry_metrics.get("human_chart_detail_observed"))
    if not human_detail_observed:
        human_detail_observed = _as_dict(_as_dict(monitor.get("human_chart_detail_context")).get("observed"))
    if not human_detail_observed:
        human_detail_observed = _as_dict(_as_dict(focus_context.get("human_chart_detail_context")).get("observed"))

    entry_thresholds = _as_dict(monitor.get("entry_thresholds"))
    if not entry_thresholds:
        entry_thresholds = _as_dict(focus_context.get("entry_thresholds"))
    if not entry_thresholds:
        entry_thresholds = _as_dict(report.get("entry_thresholds"))
    if not entry_thresholds:
        entry_thresholds = _as_dict(shared.get("entry_thresholds"))

    snapshot: Dict[str, Any] = {}
    for key, value in {
        "current_price": _first_present_value(
            entry_metrics.get("current_price"),
            entry_metrics.get("price"),
            focus_context.get("current_price"),
            monitor.get("entry_price"),
            shared.get("broker_buy_price"),
        ),
        "vwap": _first_present_value(
            entry_metrics.get("vwap"),
            focus_context.get("vwap"),
            monitor.get("entry_vwap"),
        ),
        "vwap_distance": _first_present_value(
            entry_metrics.get("vwap_distance"),
            entry_metrics.get("extended_from_vwap_pct"),
            focus_context.get("vwap_distance"),
            monitor.get("entry_vwap_distance"),
            monitor.get("entry_extended_from_vwap_pct"),
        ),
        "volume": _first_present_value(
            entry_metrics.get("current_volume"),
            entry_metrics.get("current_bar_volume"),
            entry_metrics.get("volume"),
            focus_context.get("current_volume"),
        ),
        "volume_ratio": _first_present_value(
            entry_metrics.get("volume_ratio"),
            entry_metrics.get("volume_ratio_effective"),
            focus_context.get("volume_ratio"),
            monitor.get("entry_volume_ratio"),
        ),
        "volume_ratio_raw": _first_present_value(
            entry_metrics.get("volume_ratio_raw"),
            focus_context.get("volume_ratio_raw"),
        ),
        "volume_adjusted": _first_present_value(
            entry_metrics.get("volume_adjusted"),
            focus_context.get("volume_adjusted"),
        ),
        "volume_adjustment_reason": _first_present_value(
            entry_metrics.get("volume_adjustment_reason"),
            focus_context.get("volume_adjustment_reason"),
        ),
        "volume_ratio_min": _first_present_value(
            entry_thresholds.get("volume_ratio_min"),
            focus_context.get("volume_ratio_min"),
            monitor.get("entry_volume_ratio_min"),
        ),
        "min_extended_from_vwap_pct": _first_present_value(
            entry_thresholds.get("min_extended_from_vwap_pct"),
            focus_context.get("min_extended_from_vwap_pct"),
            monitor.get("entry_min_extended_from_vwap_pct"),
        ),
        "max_extended_from_vwap_pct": _first_present_value(
            entry_thresholds.get("max_extended_from_vwap_pct"),
            focus_context.get("max_extended_from_vwap_pct"),
            monitor.get("entry_max_extended_from_vwap_pct"),
        ),
        "recent_high": _first_present_value(entry_metrics.get("recent_high"), focus_context.get("recent_high")),
        "breakout_level": _first_present_value(entry_metrics.get("breakout_level"), focus_context.get("breakout_level")),
        "confidence_score": _first_present_value(entry_metrics.get("confidence_score"), focus_context.get("confidence_score")),
        "confidence_threshold": _first_present_value(
            entry_metrics.get("confidence_threshold"),
            focus_context.get("confidence_threshold"),
        ),
        "entry_quality_score": _first_present_value(
            entry_metrics.get("entry_quality_score"),
            focus_context.get("entry_quality_score"),
        ),
        "entry_quality_tier": _first_present_value(
            entry_metrics.get("entry_quality_tier"),
            focus_context.get("entry_quality_tier"),
        ),
        "entry_hard_gate_passed": _first_present_value(
            entry_metrics.get("entry_hard_gate_passed"),
            focus_context.get("entry_hard_gate_passed"),
        ),
        "entry_hard_gate_blockers": _first_present_value(
            entry_metrics.get("entry_hard_gate_blockers"),
            focus_context.get("entry_hard_gate_blockers"),
        ),
        "entry_quality_vs_gate_summary": _first_present_value(
            entry_metrics.get("entry_quality_vs_gate_summary"),
            focus_context.get("entry_quality_vs_gate_summary"),
        ),
        "breakout_proximity_score": _first_present_value(
            entry_metrics.get("breakout_proximity_score"),
            focus_context.get("breakout_proximity_score"),
            entry_metrics.get("breakout_score"),
            focus_context.get("breakout_score"),
        ),
        "human_candle_quality_score": _first_present_value(
            entry_metrics.get("human_candle_quality_score"),
            focus_context.get("human_candle_quality_score"),
        ),
        "human_vwap_reference_quality_score": _first_present_value(
            entry_metrics.get("human_vwap_reference_quality_score"),
            focus_context.get("human_vwap_reference_quality_score"),
        ),
        "human_reward_room_score": _first_present_value(
            entry_metrics.get("human_reward_room_score"),
            focus_context.get("human_reward_room_score"),
        ),
        "human_multi_window_structure_score": _first_present_value(
            entry_metrics.get("human_multi_window_structure_score"),
            focus_context.get("human_multi_window_structure_score"),
        ),
        "close_location": human_detail_observed.get("close_location"),
        "upper_wick_ratio": human_detail_observed.get("upper_wick_ratio"),
        "lower_wick_ratio": human_detail_observed.get("lower_wick_ratio"),
        "body_ratio": human_detail_observed.get("body_ratio"),
        "vwap_source": human_detail_observed.get("vwap_source"),
        "vwap_bar_count": human_detail_observed.get("vwap_bar_count"),
        "explicit_vwap_count": human_detail_observed.get("explicit_vwap_count"),
        "explicit_vwap_ratio": human_detail_observed.get("explicit_vwap_ratio"),
        "prior_resistance": human_detail_observed.get("prior_resistance"),
        "reward_room_pct": human_detail_observed.get("reward_room_pct"),
        "breakout_extension_pct": human_detail_observed.get("breakout_extension_pct"),
    }.items():
        if value not in (None, ""):
            snapshot[key] = value

    if snapshot:
        snapshot["basis"] = "monitor_entry_metrics"
    return snapshot


def _entry_signal_metric_summary_lines(snapshot: Dict[str, Any], *, prefix: str = "진입 수치") -> List[str]:
    row = _as_dict(snapshot)
    if not row:
        return []

    parts: List[str] = []
    if row.get("current_price") not in (None, ""):
        parts.append(f"현재가 {_summary_money(row.get('current_price'))}")
    if row.get("vwap") not in (None, ""):
        parts.append(f"VWAP {_summary_money(row.get('vwap'))}")
    if row.get("vwap_distance") not in (None, ""):
        distance_text = f"VWAP 대비 {_fmt_signed_pct(row.get('vwap_distance'))}"
        min_vwap = row.get("min_extended_from_vwap_pct")
        max_vwap = row.get("max_extended_from_vwap_pct")
        if min_vwap not in (None, "") or max_vwap not in (None, ""):
            distance_text += f" (허용 {_fmt_signed_pct(min_vwap) if min_vwap not in (None, '') else '-'}~{_fmt_signed_pct(max_vwap) if max_vwap not in (None, '') else '-'})"
        parts.append(distance_text)
    if row.get("volume") not in (None, ""):
        parts.append(f"거래량 {_summary_money(row.get('volume'))}")
    if row.get("volume_ratio") not in (None, ""):
        volume_text = f"거래량 비율 {_fmt_multiple(row.get('volume_ratio'))}"
        if row.get("volume_ratio_min") not in (None, ""):
            volume_text += f" (기준 {_fmt_multiple(row.get('volume_ratio_min'))})"
        if row.get("volume_ratio_raw") not in (None, "") and row.get("volume_ratio_raw") != row.get("volume_ratio"):
            volume_text += f" / 원비율 {_fmt_multiple(row.get('volume_ratio_raw'))}"
        if row.get("volume_adjusted") is True and row.get("volume_adjustment_reason"):
            volume_text += f" / 보정 {row.get('volume_adjustment_reason')}"
        parts.append(volume_text)
    if row.get("recent_high") not in (None, ""):
        parts.append(f"최근 고점 {_summary_money(row.get('recent_high'))}")
    if row.get("breakout_level") not in (None, ""):
        parts.append(f"돌파 기준 {_summary_money(row.get('breakout_level'))}")
    if row.get("confidence_score") not in (None, ""):
        confidence_text = f"신뢰도 {_summary_money(row.get('confidence_score'))}"
        if row.get("confidence_threshold") not in (None, ""):
            confidence_text += f" (기준 {_summary_money(row.get('confidence_threshold'))})"
        parts.append(confidence_text)
    if row.get("breakout_proximity_score") not in (None, ""):
        parts.append(f"돌파 근접 점수 {_summary_money(row.get('breakout_proximity_score'))}")
    lines = [f"{prefix}: " + " / ".join(parts)] if parts else []

    gate_parts: List[str] = []
    if row.get("entry_quality_score") not in (None, ""):
        quality_text = f"진입 품질 {_summary_money(row.get('entry_quality_score'))}"
        if row.get("entry_quality_tier") not in (None, ""):
            quality_text += f" ({row.get('entry_quality_tier')})"
        gate_parts.append(quality_text)
    if row.get("entry_hard_gate_passed") is True:
        gate_parts.append("hard gate 통과")
    elif row.get("entry_hard_gate_passed") is False:
        blockers = row.get("entry_hard_gate_blockers")
        blocker_text = ""
        if isinstance(blockers, list):
            blocker_text = ", ".join(str(x or "").replace("_", " ") for x in blockers[:4] if str(x or "").strip())
        gate_parts.append(f"hard gate 미통과{f' ({blocker_text})' if blocker_text else ''}")
    if row.get("entry_quality_vs_gate_summary") not in (None, ""):
        gate_parts.append(str(row.get("entry_quality_vs_gate_summary")).replace("_", " "))
    if gate_parts:
        lines.append("진입 품질 vs 허가: " + " / ".join(gate_parts))

    setup_parts: List[str] = []
    if row.get("human_candle_quality_score") not in (None, ""):
        setup_parts.append(f"캔들 품질 {_summary_money(row.get('human_candle_quality_score'))}")
    if row.get("human_vwap_reference_quality_score") not in (None, ""):
        setup_parts.append(f"VWAP 신뢰도 {_summary_money(row.get('human_vwap_reference_quality_score'))}")
    if row.get("human_reward_room_score") not in (None, ""):
        setup_parts.append(f"위쪽 여지 점수 {_summary_money(row.get('human_reward_room_score'))}")
    if row.get("human_multi_window_structure_score") not in (None, ""):
        setup_parts.append(f"다중 구간 구조 {_summary_money(row.get('human_multi_window_structure_score'))}")
    if setup_parts:
        lines.append("진입 자리 품질: " + " / ".join(setup_parts))

    candle_parts: List[str] = []
    if row.get("close_location") not in (None, ""):
        candle_parts.append(f"종가 위치 {_summary_money(row.get('close_location'))}")
    if row.get("upper_wick_ratio") not in (None, ""):
        candle_parts.append(f"윗꼬리 {_summary_money(row.get('upper_wick_ratio'))}")
    if row.get("lower_wick_ratio") not in (None, ""):
        candle_parts.append(f"아랫꼬리 {_summary_money(row.get('lower_wick_ratio'))}")
    if row.get("body_ratio") not in (None, ""):
        candle_parts.append(f"몸통 {_summary_money(row.get('body_ratio'))}")
    if candle_parts:
        lines.append("캔들 근거: " + " / ".join(candle_parts))

    vwap_parts: List[str] = []
    if row.get("vwap_source") not in (None, ""):
        vwap_parts.append(f"소스 {_metadata_value(row.get('vwap_source'))}")
    if row.get("vwap_bar_count") not in (None, ""):
        vwap_parts.append(f"사용 분봉 {int(_num_opt(row.get('vwap_bar_count')) or 0)}개")
    if row.get("explicit_vwap_count") not in (None, ""):
        vwap_parts.append(f"원본 VWAP {int(_num_opt(row.get('explicit_vwap_count')) or 0)}개")
    if row.get("explicit_vwap_ratio") not in (None, ""):
        vwap_parts.append(f"원본 비율 {_summary_money(row.get('explicit_vwap_ratio'))}")
    if vwap_parts:
        lines.append("VWAP 근거: " + " / ".join(vwap_parts))

    reward_parts: List[str] = []
    if row.get("prior_resistance") not in (None, ""):
        reward_parts.append(f"근접 저항 {_summary_money(row.get('prior_resistance'))}")
    if row.get("reward_room_pct") not in (None, ""):
        reward_parts.append(f"저항까지 {_fmt_pct(row.get('reward_room_pct'))}")
    if row.get("breakout_extension_pct") not in (None, ""):
        reward_parts.append(f"돌파 후 이격 {_fmt_pct(row.get('breakout_extension_pct'))}")
    if reward_parts:
        lines.append("위쪽 여지: " + " / ".join(reward_parts))

    return lines


def _number_from_text(value: Any) -> Optional[float]:
    text = str(value or "").replace(",", "").strip()
    return _num_opt(text)


def _normalize_exit_trigger_label(value: Any, fallback: Any = "") -> str:
    text = _translate_text(value).strip().rstrip(".")
    if not text and fallback:
        text = _axis_label(fallback)
    text = re.sub(r"^Trigger type:\s*", "", text, flags=re.IGNORECASE).strip()
    patterns = [
        r"청산을 직접 촉발한 신호는\s*(.+?)(?:이었습니다|였습니다|입니다|\.|$)",
        r"핵심 청산 축은\s*(.+?)(?:,|\.|$)",
        r"우선 감시 축은\s*(.+?)(?:이었습니다|였습니다|입니다|\.|$)",
        r"청산 사유는\s*(.+?)(?:입니다|\.|$)",
        r"정규화된 청산 사유는\s*(.+?)(?:입니다|\.|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            text = match.group(1).strip()
            break
    text = text.replace("으로 청산", "").replace("로 청산", "").strip()
    if "고점 대비 하락폭" in text:
        return "고점 대비 하락폭 기준"
    label = _axis_label(text).strip().rstrip(".")
    fallback_label = _axis_label(fallback).strip().rstrip(".") if fallback else ""
    hold_labels = {"hold", "보유 유지", "보유 유지입니다", "현재 포지션 판단은 보유 유지입니다"}
    if label in hold_labels and fallback_label and fallback_label not in hold_labels:
        return fallback_label
    return label or _axis_label(fallback) or "-"


def _extract_exit_signal_snapshot(values: Iterable[Any]) -> Dict[str, Any]:
    snapshot: Dict[str, Any] = {}

    def _set_number(key: str, raw: Any) -> None:
        if key in snapshot:
            return
        num = _number_from_text(raw)
        if num is not None:
            snapshot[key] = num

    for raw in values:
        text = _translate_text(raw).strip()
        if not text:
            continue

        if "trigger" not in snapshot and any(
            token in text for token in ("촉발", "Trigger type", "핵심 청산 축", "우선 감시 축", "청산 사유", "peak_drawdown", "고점 대비")
        ):
            trigger = _normalize_exit_trigger_label(text)
            if trigger and trigger != "-":
                snapshot["trigger"] = trigger

        if match := re.search(
            r"현재가,\s*평균가,\s*고점 기준 값은\s*([+-]?[0-9,.]+)\s*/\s*([+-]?[0-9,.]+)\s*/\s*([+-]?[0-9,.]+)",
            text,
        ):
            _set_number("monitor_current_price", match.group(1))
            _set_number("position_avg_price", match.group(2))
            _set_number("peak_price", match.group(3))

        if match := re.search(r"현재가(?:는|:)?\s*([+-]?[0-9,.]+)", text):
            _set_number("monitor_current_price", match.group(1))
        if match := re.search(r"평균가(?:는|:)?\s*([+-]?[0-9,.]+)", text):
            _set_number("position_avg_price", match.group(1))
        if match := re.search(r"고점(?:은|:)?\s*([+-]?[0-9,.]+)", text):
            _set_number("peak_price", match.group(1))
        if match := re.search(r"확인 조건(?:은|:)?\s*([0-9]+\s*/\s*[0-9]+)", text):
            snapshot.setdefault("confirm_state", re.sub(r"\s+", "", match.group(1)))
        if match := re.search(r"현재 손익 변동(?:은|:)?\s*([+-]?[0-9]+(?:\.[0-9]+)?)\s*%", text):
            snapshot.setdefault("monitor_drawdown_pct_text", f"{match.group(1)}%")

    if snapshot:
        snapshot.setdefault("basis", "monitor_signal_snapshot")
        snapshot.setdefault("truth_note", "체결가와 실현손익은 Truth Surface 기준입니다.")
    return snapshot


def _enrich_exit_signal_snapshot_from_monitor(
    snapshot: Dict[str, Any],
    monitor: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(snapshot or {})
    monitor = _as_dict(monitor)
    if not monitor:
        return out

    def _first_present(*keys: str) -> Any:
        for key in keys:
            value = monitor.get(key)
            if value not in (None, ""):
                return value
        return None

    def _set_if_present(key: str, *candidates: str) -> None:
        if out.get(key) not in (None, ""):
            return
        value = _first_present(*candidates)
        if value not in (None, ""):
            out[key] = value

    _set_if_present("gross_pnl_ratio", "gross_pnl_ratio", "exit_gross_pnl_ratio")
    _set_if_present("technical_pnl_ratio", "technical_pnl_ratio", "exit_technical_pnl_ratio")
    _set_if_present("effective_pnl_ratio", "effective_pnl_ratio", "exit_effective_pnl_ratio", "pnl_ratio", "exit_pnl_ratio")
    _set_if_present("stop_pnl_ratio", "stop_pnl_ratio", "exit_stop_pnl_ratio")
    _set_if_present("stop_pnl_ratio_source", "stop_pnl_ratio_source", "exit_stop_pnl_ratio_source")
    _set_if_present("hard_stop_pnl_ratio", "hard_stop_pnl_ratio", "exit_hard_stop_pnl_ratio")
    _set_if_present("hard_stop_pnl_ratio_source", "hard_stop_pnl_ratio_source", "exit_hard_stop_pnl_ratio_source")
    _set_if_present("cost_drag_pressure_pct", "cost_drag_pressure_pct", "exit_cost_drag_pressure_pct")
    _set_if_present("cost_drag_pressure_reason", "cost_drag_pressure_reason", "exit_cost_drag_pressure_reason")
    _set_if_present("expected_exit_price", "expected_exit_price", "exit_expected_exit_price")
    _set_if_present("expected_exit_price_source", "expected_exit_price_source", "exit_expected_exit_price_source")
    _set_if_present("expected_exit_pnl_ratio", "expected_exit_pnl_ratio", "exit_expected_exit_pnl_ratio")
    _set_if_present("expected_exit_net_pnl_ratio", "expected_exit_net_pnl_ratio", "exit_expected_exit_net_pnl_ratio")
    _set_if_present(
        "expected_exit_profit_floor_gap_pct",
        "expected_exit_profit_floor_gap_pct",
        "exit_expected_exit_profit_floor_gap_pct",
    )
    _set_if_present(
        "expected_exit_profit_floor_blocked_reason",
        "expected_exit_profit_floor_blocked_reason",
        "exit_expected_exit_profit_floor_blocked_reason",
    )
    _set_if_present(
        "stop_loss_cost_drag_blocked_reason",
        "stop_loss_cost_drag_blocked_reason",
        "exit_stop_loss_cost_drag_blocked_reason",
    )
    _set_if_present("technical_price", "technical_price", "exit_technical_price")
    _set_if_present("technical_price_source", "technical_price_source", "exit_technical_price_source")
    _set_if_present("vwap", "vwap", "exit_vwap")
    _set_if_present("vwap_distance", "vwap_distance", "exit_vwap_distance")
    _set_if_present("vwap_distance_source", "vwap_distance_source", "exit_vwap_distance_source")
    _set_if_present("exit_trigger_metric_name", "exit_trigger_metric_name")
    _set_if_present("exit_trigger_metric_value", "exit_trigger_metric_value")
    _set_if_present("exit_trigger_metric_source", "exit_trigger_metric_source")
    _set_if_present("trend_strength", "trend_strength", "engine_trend_strength", "exit_trend_strength")
    _set_if_present("trend_strength_floor", "trend_strength_floor", "exit_trend_strength_floor")

    thresholds = _as_dict(_as_dict(monitor.get("thresholds_guards_used")).get("thresholds")) or _as_dict(monitor.get("thresholds"))
    if out.get("trend_strength_floor") in (None, "") and thresholds.get("trend_strength_floor") not in (None, ""):
        out["trend_strength_floor"] = thresholds.get("trend_strength_floor")
    if out.get("vwap_breakdown_pct") in (None, ""):
        threshold = _first_present(
            "vwap_breakdown_pct",
            "exit_vwap_breakdown_pct",
            "monitor_vwap_breakdown_pct",
        )
        if threshold in (None, ""):
            threshold = thresholds.get("vwap_breakdown_pct")
        if threshold not in (None, ""):
            out["vwap_breakdown_pct"] = threshold

    for key, candidates in {
        "cost_drag_pressure": ("cost_drag_pressure", "exit_cost_drag_pressure"),
        "stop_loss_cost_drag_blocked": (
            "stop_loss_cost_drag_blocked",
            "exit_stop_loss_cost_drag_blocked",
        ),
        "expected_exit_profit_floor_met": (
            "expected_exit_profit_floor_met",
            "exit_expected_exit_profit_floor_met",
        ),
        "expected_exit_profit_floor_blocked": (
            "expected_exit_profit_floor_blocked",
            "exit_expected_exit_profit_floor_blocked",
        ),
    }.items():
        if out.get(key) not in (None, ""):
            continue
        value = _first_present(*candidates)
        if value not in (None, ""):
            out[key] = bool(value)

    if out:
        out.setdefault("basis", "monitor_signal_snapshot")
        out.setdefault("truth_note", "체결가와 실현손익은 Truth Surface 기준입니다.")
    return out


def _build_summary_exit_trigger_lines(
    exit_trigger: Any,
    exit_signal_snapshot: Dict[str, Any],
    *,
    fallback_reason: Any = "",
    buy_price: Any = "",
    exit_price: Any = "",
    pnl_pct: Any = "",
    truth_source: Any = "",
) -> List[str]:
    raw_trigger_value = exit_signal_snapshot.get("trigger") or exit_trigger
    raw_trigger_text = " ".join(
        str(part or "")
        for part in (raw_trigger_value, fallback_reason)
        if str(part or "").strip()
    )
    trigger_label = _normalize_exit_trigger_label(
        raw_trigger_value,
        fallback_reason,
    )
    raw_trigger_lower = raw_trigger_text.strip().lower()
    execution_only_exit = (
        "sell_execution_confirmed" in raw_trigger_lower
        or "full_sell_quantity_reconciled" in raw_trigger_lower
        or "sell 실행 및 잔여수량" in raw_trigger_text
        or "매도 실행 확인" in trigger_label
        or "전량 매도 수량 확인" in trigger_label
    )
    missing_trigger = (
        execution_only_exit
        or "exit_trigger_not_captured" in raw_trigger_lower
        or "monitor_exit_trigger_not_captured" in raw_trigger_lower
        or "청산 트리거 미확인" in raw_trigger_text
        or "청산 이유는 기록되지" in raw_trigger_text
        or "exit reasoning was not captured" in raw_trigger_lower
    )
    if missing_trigger:
        trigger_label = "모니터 청산 트리거 미확인"
    lines = [f"트리거: {trigger_label}"]
    if execution_only_exit:
        lines.append("체결 상태: SELL 실행 및 잔여수량 0 확인으로 전량 청산")
    trigger_metric_name = str(exit_signal_snapshot.get("exit_trigger_metric_name") or "").strip().lower()
    trigger_metric_value = exit_signal_snapshot.get("exit_trigger_metric_value")
    vwap_distance = exit_signal_snapshot.get("vwap_distance")
    if vwap_distance in (None, "") and trigger_metric_name == "vwap_distance":
        vwap_distance = trigger_metric_value
    vwap_distance_num = _num_opt(vwap_distance)
    is_vwap_trigger = "VWAP" in trigger_label or "vwap" in trigger_label.lower() or trigger_metric_name == "vwap_distance"
    if is_vwap_trigger and vwap_distance_num is not None:
        lines[0] = f"트리거: {trigger_label} (VWAP 대비 {_fmt_signed_pct(vwap_distance_num)})"

    trend_strength = exit_signal_snapshot.get("trend_strength")
    if trend_strength in (None, "") and trigger_metric_name == "trend_strength":
        trend_strength = trigger_metric_value
    trend_strength_num = _num_opt(trend_strength)
    trend_floor_num = _num_opt(exit_signal_snapshot.get("trend_strength_floor"))
    is_trend_trigger = (
        trigger_metric_name == "trend_strength"
        or "추세" in trigger_label
        or "trend" in str(trigger_label or "").lower()
    )
    if is_trend_trigger and trend_strength_num is not None:
        floor_text = f" <= 기준 {trend_floor_num:.4f}" if trend_floor_num is not None else ""
        lines[0] = f"트리거: 추세 훼손 (추세강도 {trend_strength_num:.4f}{floor_text})"

    observation_parts: List[str] = []
    if exit_signal_snapshot.get("confirm_state"):
        observation_parts.append(f"확인 조건 {exit_signal_snapshot.get('confirm_state')}")
    if exit_signal_snapshot.get("monitor_current_price") not in (None, ""):
        observation_parts.append(f"현재가 {_summary_money(exit_signal_snapshot.get('monitor_current_price'))}")
    if is_vwap_trigger and vwap_distance_num is not None:
        vwap_value = _num_opt(exit_signal_snapshot.get("vwap"))
        current_value = _num_opt(exit_signal_snapshot.get("monitor_current_price"))
        if vwap_value is None and current_value is not None and (1.0 + vwap_distance_num) > 0.0:
            vwap_value = current_value / (1.0 + vwap_distance_num)
        vwap_parts = []
        if vwap_value is not None:
            vwap_parts.append(f"VWAP {_summary_money(vwap_value)}")
        vwap_parts.append(f"VWAP 대비 {_fmt_signed_pct(vwap_distance_num)}")
        threshold_num = _num_opt(exit_signal_snapshot.get("vwap_breakdown_pct"))
        if threshold_num is not None:
            vwap_parts.append(f"이탈 기준 {_fmt_signed_pct(-abs(threshold_num))}")
        observation_parts.append(" / ".join(vwap_parts))
    if is_trend_trigger and trend_strength_num is not None:
        trend_parts = [f"추세강도 {trend_strength_num:.4f}"]
        if trend_floor_num is not None:
            trend_parts.append(f"훼손 기준 {trend_floor_num:.4f}")
        source = _metadata_value(exit_signal_snapshot.get("exit_trigger_metric_source"))
        if source and source != "-":
            trend_parts.append(f"소스 {source}")
        observation_parts.append(" / ".join(trend_parts))
    if exit_signal_snapshot.get("position_avg_price") not in (None, ""):
        observation_parts.append(
            f"포지션 평균단가(모니터 신호 계산용) {_summary_money(exit_signal_snapshot.get('position_avg_price'))}"
        )
    if exit_signal_snapshot.get("peak_price") not in (None, ""):
        observation_parts.append(f"고점 {_summary_money(exit_signal_snapshot.get('peak_price'))}")
    monitor_drawdown_pct = (
        exit_signal_snapshot.get("monitor_drawdown_pct_text")
        or exit_signal_snapshot.get("monitor_pnl_pct_text")
    )
    if monitor_drawdown_pct:
        observation_parts.append(f"고점 대비 하락폭 {monitor_drawdown_pct}")
    if observation_parts:
        observation_label = (
            "마지막 모니터 관측값(청산 트리거 아님)"
            if missing_trigger
            else "모니터 관측값(신호 판단용)"
        )
        lines.append(f"{observation_label}: " + " / ".join(observation_parts))

    pnl_basis_parts: List[str] = []
    gross_pnl = exit_signal_snapshot.get("gross_pnl_ratio")
    effective_pnl = exit_signal_snapshot.get("effective_pnl_ratio")
    stop_pnl = exit_signal_snapshot.get("stop_pnl_ratio")
    hard_stop_pnl = exit_signal_snapshot.get("hard_stop_pnl_ratio")
    if gross_pnl not in (None, ""):
        pnl_basis_parts.append(f"가격 기준 손익 {_fmt_pct(gross_pnl)}")
    if effective_pnl not in (None, ""):
        pnl_basis_parts.append(f"비용/계좌 반영 손익 {_fmt_pct(effective_pnl)}")
    if stop_pnl not in (None, ""):
        source = _metadata_value(exit_signal_snapshot.get("stop_pnl_ratio_source"))
        suffix = f", {source}" if source and source != "-" else ""
        pnl_basis_parts.append(f"일반 손절 판단 기준 {_fmt_pct(stop_pnl)}{suffix}")
    if hard_stop_pnl not in (None, ""):
        source = _metadata_value(exit_signal_snapshot.get("hard_stop_pnl_ratio_source"))
        suffix = f", {source}" if source and source != "-" else ""
        pnl_basis_parts.append(f"하드스탑 판단 기준 {_fmt_pct(hard_stop_pnl)}{suffix}")
    if pnl_basis_parts:
        lines.append("손익 기준 분리: " + " / ".join(pnl_basis_parts))

    if exit_signal_snapshot.get("cost_drag_pressure"):
        pressure_pct = _fmt_pct(exit_signal_snapshot.get("cost_drag_pressure_pct"))
        reason = _metadata_value(exit_signal_snapshot.get("cost_drag_pressure_reason"))
        detail = f" ({pressure_pct})" if pressure_pct != "-" else ""
        if reason and reason != "-":
            detail += f", {reason}"
        lines.append("비용 압박: 비용/계좌 반영 손익이 가격 기준보다 낮게 잡혔습니다" + detail)
    if exit_signal_snapshot.get("stop_loss_cost_drag_blocked"):
        reason = _metadata_value(exit_signal_snapshot.get("stop_loss_cost_drag_blocked_reason"))
        suffix = f" ({reason})" if reason and reason != "-" else ""
        lines.append("일반 손절 차단: 가격 기준 손절선은 미통과했고 비용 반영 손익만 손절선을 건드렸습니다" + suffix)
    if exit_signal_snapshot.get("expected_exit_price") not in (None, ""):
        source = _metadata_value(exit_signal_snapshot.get("expected_exit_price_source"))
        source_suffix = f", {source}" if source and source != "-" else ""
        expected_parts = [
            f"예상 체결가 {_summary_money(exit_signal_snapshot.get('expected_exit_price'))}{source_suffix}",
        ]
        if exit_signal_snapshot.get("expected_exit_pnl_ratio") not in (None, ""):
            expected_parts.append(f"예상 가격 손익 {_fmt_pct(exit_signal_snapshot.get('expected_exit_pnl_ratio'))}")
        if exit_signal_snapshot.get("expected_exit_net_pnl_ratio") not in (None, ""):
            expected_parts.append(f"예상 비용 차감 손익 {_fmt_pct(exit_signal_snapshot.get('expected_exit_net_pnl_ratio'))}")
        if exit_signal_snapshot.get("expected_exit_profit_floor_met") not in (None, ""):
            expected_parts.append(
                "비용 바닥 통과" if exit_signal_snapshot.get("expected_exit_profit_floor_met") else "비용 바닥 미통과"
            )
        lines.append("예상 체결가 비용 점검: " + " / ".join(expected_parts))
    if exit_signal_snapshot.get("expected_exit_profit_floor_blocked"):
        reason = _metadata_value(exit_signal_snapshot.get("expected_exit_profit_floor_blocked_reason"))
        suffix = f" ({reason})" if reason and reason != "-" else ""
        lines.append("익절 보류: 예상 체결가 기준 비용 바닥을 통과하지 못했습니다" + suffix)

    truth_parts: List[str] = []
    if buy_price not in (None, ""):
        truth_parts.append(f"매수가 {_summary_money(buy_price)}")
    if exit_price not in (None, ""):
        truth_parts.append(f"매도가 {_summary_money(exit_price)}")
    elif buy_price not in (None, ""):
        truth_parts.append("매도 체결가 미확정")
    if pnl_pct not in (None, ""):
        truth_parts.append(f"실현손익률 {_fmt_pct(pnl_pct)}")
    truth_label = _truth_source_label(truth_source)
    if truth_label and truth_label != "-":
        truth_parts.append(truth_label)
    if truth_parts:
        lines.append("체결/실현손익 기준: Truth Surface의 " + " / ".join(truth_parts))
    return lines


def _strip_html_tags(text: Any) -> str:
    raw = html.unescape(_clip(text, 300))
    if not raw:
        return ""
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = raw.replace("NewsItem(title='", "")
    raw = raw.split("', url='", 1)[0]
    return re.sub(r"\s+", " ", raw).strip()


def _clean_news_title(text: Any) -> str:
    return _strip_html_tags(text).rstrip(".")


def _sample_news_titles(values: Any, limit: int = 2) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in _listify(values):
        cleaned = _clean_news_title(raw)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _normalize_news_symbol(value: Any) -> str:
    if value is None:
        return ""
    match = re.search(r"\b(\d{6})\b", str(value))
    return match.group(1) if match else ""


def _news_symbol_from_item(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("symbol", "code", "stock_code", "ticker"):
            symbol = _normalize_news_symbol(value.get(key))
            if symbol:
                return symbol
        return ""
    raw = str(value or "")
    match = re.match(r"\s*(\d{6})\s*:", raw)
    if match:
        return match.group(1)
    match = re.search(r"\bsymbol=['\"]?(\d{6})['\"]?", raw)
    return match.group(1) if match else ""


def _sample_news_titles_for_symbol(symbol: Any, *sources: Any, limit: int = 2) -> List[str]:
    target = _normalize_news_symbol(symbol)
    untagged_fallback: List[Any] = []
    for source in sources:
        rows = _listify(source)
        if not rows:
            continue
        if not target:
            return _sample_news_titles(rows, limit=limit)
        matched: List[Any] = []
        has_detectable_symbol = False
        for row in rows:
            row_symbol = _news_symbol_from_item(row)
            if row_symbol:
                has_detectable_symbol = True
            if row_symbol == target:
                matched.append(row)
        if matched:
            return _sample_news_titles(matched, limit=limit)
        if not has_detectable_symbol and not untagged_fallback:
            # Curated symbol-only headline lists may omit the code prefix.
            untagged_fallback = rows
    if untagged_fallback:
        return _sample_news_titles(untagged_fallback, limit=limit)
    return []


def _mismatched_symbol_news_bullet(text: Any, symbol: Any) -> bool:
    target = _normalize_news_symbol(symbol)
    if not target:
        return False
    raw = str(text or "")
    if "대표 종목/섹터 뉴스" not in raw and "종목 뉴스" not in raw:
        return False
    symbols = set(re.findall(r"\b(\d{6})\s*:", raw))
    return bool(symbols and target not in symbols)


def _news_linkage_strength_label(value: Any) -> str:
    lowered = _clip(value, 40).lower()
    return {
        "weak": "약한 편이었습니다",
        "moderate": "보통 수준이었습니다",
        "strong": "강한 편이었습니다",
    }.get(lowered, _metadata_value(value) or "-")


def _badge(label: str, color: str) -> str:
    return f"**[{label}]**"


def _metadata_value(value: Any) -> str:
    raw = _clip(value, 240)
    lowered = raw.lower()
    if not raw:
        return ""
    if lowered in {"unknown", "not available", "not_available", "unavailable"}:
        return "확인되지 않음"
    if lowered in {"not captured", "not_captured"}:
        return "기록되지 않음"
    if lowered in {"allowed", "allow"}:
        return "허용"
    if lowered in {"approve", "approved"}:
        return "승인"
    if lowered == "broad_market_leaders":
        return "시장 대표주"
    if lowered == "illiquid_microcap":
        return "유동성 낮은 초소형주"
    if lowered == "headline_only_momentum":
        return "헤드라인 추격형 모멘텀"
    if lowered == "high_gap_speculative":
        return "갭 과열 투기형"
    if lowered == "neutral":
        return "중립"
    if lowered == "bullish":
        return "강세"
    if lowered == "bearish":
        return "약세"
    if lowered == "strong":
        return "강함"
    if lowered == "weak":
        return "약함"
    if lowered == "high":
        return "높음"
    if lowered == "medium":
        return "보통"
    if lowered == "low":
        return "낮음"
    return raw


def _story_type_label(value: Any) -> str:
    lowered = _clip(value, 80).lower()
    return {
        "simulation trade report": "시뮬레이션 거래 리포트",
        "simulation": "시뮬레이션 거래 리포트",
        "live trade report": "실거래 거래 리포트",
        "live": "실거래 거래 리포트",
    }.get(lowered, _metadata_value(value) or "-")


def _execution_mode_label(value: Any) -> str:
    lowered = _clip(value, 80).lower()
    return {
        "simulation (mock broker)": "시뮬레이션 (모의 브로커)",
        "real broker": "실브로커",
        "live": "실거래",
    }.get(lowered, _metadata_value(value) or "-")


def _action_label(value: Any) -> str:
    lowered = _clip(value, 40).upper()
    return {
        "BUY": "매수",
        "SELL": "매도",
        "HOLD": "보유 유지",
        "WAIT": "진입 보류",
    }.get(lowered, _metadata_value(value) or "-")


def _status_label(value: Any) -> str:
    lowered = _clip(value, 40).lower()
    return {
        "open": "열림",
        "closed": "종결",
        "ok": "정상",
    }.get(lowered, _metadata_value(value) or "-")


def _axis_label(value: Any) -> str:
    raw = _clip(value, 120)
    if raw.lower().startswith("sell was triggered because "):
        raw = raw[len("SELL was triggered because ") :].strip().rstrip(".")
    lowered = raw.lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "hard_stop": "고정 손절 기준",
        "stop_loss": "고정 손절 기준",
        "adaptive_stop": "상황 적응형 손절 기준",
        "take_profit": "목표 수익 실현 기준",
        "partial_take_profit": "1차 일부 익절",
        "profit_ladder": "구간별 분할 익절",
        "risk/reward_take_profit": "손익비 익절",
        "risk_reward_take_profit": "손익비 익절",
        "vwap_extension_take_profit": "VWAP 과확장 익절",
        "resistance_take_profit": "저항권 익절",
        "volume_exhaustion_take_profit": "거래량 둔화 익절",
        "opening_gap_profit_take": "갭 추격 빠른 익절",
        "time_decay_profit_exit": "시간 경과 수익 보전",
        "trailing_stop": "추적 손절 기준",
        "vwap_breakdown": "VWAP 이탈",
        "peak_drawdown": "고점 대비 하락폭 기준",
        "prior_low_break": "직전 저점 이탈",
        "intraday_low_break": "장중 저점 이탈 기준",
        "below_vwap_reclaim_not_ready": "VWAP 재회복 미완료",
        "exit_trigger_not_captured": "모니터 청산 트리거 미확인",
        "monitor_exit_trigger_not_captured": "모니터 청산 트리거 미확인",
        "sell_execution_confirmed": "모니터 청산 트리거 미확인",
        "full_sell_quantity_reconciled": "모니터 청산 트리거 미확인",
        "confirmed_exit_signal": "청산 확인 신호",
        "defensive_exit": "방어적 청산 신호",
        "trend_breakdown": "추세 붕괴 기준",
        "volatility_expansion": "변동성 확장 기준",
        "no_trigger_yet": "아직 청산 신호가 확인되지 않음",
    }
    return mapping.get(lowered, raw or "-")


def _translate_text(text: Any) -> str:
    raw = html.unescape(_clip(text, 800))
    if not raw:
        return ""
    exact = {
        "hold": "현재 포지션 판단은 보유 유지입니다.",
        "open trade": "아직 청산 체결이 확인되지 않아 포지션이 열려 있습니다.",
        "Current lifecycle status is closed. Entry and exit are connected in one lifecycle story.": "이번 라이프사이클은 종결 상태이며, 진입과 청산이 하나의 거래 흐름으로 연결됐습니다.",
        "Supervisor approved the order because Allowed.": "슈퍼바이저는 주문을 승인했고 가드 판단은 허용이었습니다.",
        "Approval mode: not captured in the execution trace": "승인 모드는 실행 추적에는 별도로 남아 있지 않습니다.",
        "Holding-phase evidence is thin; preserve more monitor context between entry and exit.": "보유 구간 근거는 제한적이며 진입과 청산 사이 모니터 맥락이 충분하지 않습니다.",
        "Execution outcome summary was not captured.": "거래 생애주기 실행 요약은 기록되지 않았습니다.",
        "Lifecycle conclusion was not captured.": "최종 생애주기 결론은 기록되지 않았습니다.",
        "Final decision basis: Scanner selected the highest-ranked candidate after strategist-guided weighting, source scoring, and risk penalties.": "최종 선정 기준은 전략가 가중치, source 점수, 위험 패널티를 반영한 뒤 스캐너 최고 순위 후보를 채택한 것입니다.",
        "Warnings and missing links were recorded for operator follow-up.": "운영자 후속 확인이 필요한 경고와 누락 연결을 정리했습니다.",
        "Link same-day reporter analysis to this lifecycle for a complete quality review.": "동일 일자 리포터 분석을 이 거래 생애주기에 연결해 결과 평가를 보강해야 합니다.",
        "Entry execution evidence is incomplete; preserve BUY linkage for closed-trade diagnosis.": "진입 실행 근거가 불완전해, 닫힌 거래 진단을 위해 BUY 연결 기록을 더 보존해야 합니다.",
        "Same-price round trips produced fee/tax drag; tighten follow-through evidence before repeating quick reversals.": "동일가 왕복 거래에서 수수료와 세금 손실이 발생했으므로, 빠른 재진입 전에는 후속 탄력 근거를 더 확인해야 합니다.",
    }
    if raw in exact:
        return exact[raw]
    replaced = raw
    replaced = replaced.replace("Market Sentiment", "시장 심리")
    replaced = replaced.replace("Stress Flags", "스트레스 신호")
    replaced = replaced.replace("Scanner Rank", "스캐너 순위")
    replaced = replaced.replace("Tie Break Rule", "동률 해소 기준")
    replaced = replaced.replace("Trailing stop", "추적 손절")
    replaced = replaced.replace("Hard stop", "고정 손절")
    replaced = replaced.replace("Adaptive stop", "상황 적응형 손절")
    replaced = replaced.replace("Take profit", "목표 수익 실현")
    replaced = replaced.replace("Partial take profit", "1차 일부 익절")
    replaced = replaced.replace("Profit ladder", "구간별 분할 익절")
    replaced = replaced.replace("Risk/reward take profit", "손익비 익절")
    replaced = replaced.replace("VWAP extension take profit", "VWAP 과확장 익절")
    replaced = replaced.replace("Resistance take profit", "저항권 익절")
    replaced = replaced.replace("Volume exhaustion take profit", "거래량 둔화 익절")
    replaced = replaced.replace("Opening gap profit take", "갭 추격 빠른 익절")
    replaced = replaced.replace("Time-decay profit exit", "시간 경과 수익 보전")
    replaced = replaced.replace("VWAP breakdown", "VWAP 이탈")
    replaced = replaced.replace("broad_market_leaders", "시장 대표주")
    replaced = replaced.replace("illiquid_microcap", "유동성 낮은 초소형주")
    replaced = replaced.replace("headline_only_momentum", "헤드라인 추격형 모멘텀")
    replaced = replaced.replace("high_gap_speculative", "갭 과열 투기형")
    replaced = replaced.replace("브로드마켓 리더", "시장 대표주")
    replaced = replaced.replace("밸런스드", "균형형")
    replaced = replaced.replace("turnover and volume", "회전율/거래량")
    replaced = replaced.replace("정서 지원", "감성 지원")
    replaced = replaced.replace("top_value", "거래대금 상위")
    replaced = replaced.replace("top_change_rate", "등락률 상위")
    replaced = replaced.replace(
        "pullback rebound above vwap with volume confirmation",
        "VWAP 위 되돌림 반등과 거래량 확인",
    )
    replaced = replaced.replace(
        "눌림목 rebound above vwap with volume confirmation",
        "VWAP 위 되돌림 반등과 거래량 확인",
    )
    replaced = replaced.replace(
        "pullback structure above vwap with volume confirmation",
        "VWAP 위 눌림목 구조와 거래량 확인",
    )
    replaced = replaced.replace(
        "눌림목 structure above vwap with volume confirmation",
        "VWAP 위 눌림목 구조와 거래량 확인",
    )
    replaced = replaced.replace(
        "breakout above recent high with vwap hold and volume confirmation",
        "VWAP 유지와 거래량 확인이 있는 최근 고점 돌파",
    )
    replaced = replaced.replace(
        "breakout above recent high with vwap structure confirmation",
        "직전 고점 돌파와 VWAP 구조 확인",
    )
    replaced = re.sub(r"스캐너 1순위\s+([A-Z0-9]+)은", r"스캐너 상위 후보 \1은", replaced)
    replaced = replaced.replace(" 이유로 막혔고", " 이유로 보류됐고")
    replaced = replaced.replace(" 사유로 막힌 뒤", " 사유로 보류된 뒤")
    replaced = replaced.replace("news/global sentiment contribution was", "뉴스/글로벌 심리 기여도")
    replaced = replaced.replace("Peak Drawdown", "고점 대비 하락폭 기준")
    replaced = replaced.replace("peak_drawdown", "고점 대비 하락폭 기준")
    replaced = replaced.replace("partial_take_profit", "1차 일부 익절")
    replaced = replaced.replace("profit_ladder", "구간별 분할 익절")
    replaced = replaced.replace("risk_reward_take_profit", "손익비 익절")
    replaced = replaced.replace("vwap_extension_take_profit", "VWAP 과확장 익절")
    replaced = replaced.replace("resistance_take_profit", "저항권 익절")
    replaced = replaced.replace("volume_exhaustion_take_profit", "거래량 둔화 익절")
    replaced = replaced.replace("opening_gap_profit_take", "갭 추격 빠른 익절")
    replaced = replaced.replace("time_decay_profit_exit", "시간 경과 수익 보전")
    replaced = replaced.replace("hard_stop", "고정 손절 기준")
    replaced = replaced.replace("intraday low break", "장중 저점 이탈 기준")
    replaced = replaced.replace("intraday_low_break", "장중 저점 이탈 기준")
    replaced = replaced.replace("below_vwap_reclaim_not_ready", "VWAP 재회복 미완료")
    replaced = replaced.replace("슈퍼바이저 결정: approve", "슈퍼바이저 결정은 승인입니다.")
    replaced = replaced.replace("슈퍼바이저 결정: approved", "슈퍼바이저 결정은 승인입니다.")
    replaced = replaced.replace("가드 판단 사유는 Allowed입니다", "가드 판단 사유는 허용입니다.")
    replaced = replaced.replace("가드 판단 사유는 allowed입니다", "가드 판단 사유는 허용입니다.")
    replaced = replaced.replace("액션 검토: SELL", "검토 액션은 매도입니다.")
    replaced = replaced.replace("액션 검토: BUY", "검토 액션은 매수입니다.")
    replaced = replaced.replace("확인였습니다", "확인이었습니다")
    replaced = replaced.replace("입니다..", "입니다.")
    replaced = replaced.replace(
        "진입 신뢰도 점수는 0.55로 기준 0.55를 하회했습니다.",
        "진입 게이트 점수는 기준 0.55와 같은 수준이었습니다.",
    )
    if m := re.fullmatch(
        r"News input:\s*(\d+)\s+headlines were considered across\s*(\d+)\s+targets\s*\((\d+)\s+market\s*/\s*(\d+)\s+candidate signals\)\.?",
        raw,
        re.I,
    ):
        return f"뉴스 입력은 {m.group(1)}건 헤드라인, 조회 대상 {m.group(2)}개 ({m.group(3)} 시장 / {m.group(4)} 후보 신호)를 반영했습니다."
    if m := re.fullmatch(r"소스 조합:\s*(.+)에서 선정됨", replaced):
        return f"선정 소스는 {m.group(1)}입니다."
    if m := re.fullmatch(r"Scanner Rank:\s*([0-9]+)\?*\s*/\s*Total Score:\s*([0-9.]+)", raw, re.I):
        return f"스캐너 순위는 {m.group(1)}위였고 총점은 {m.group(2)}였습니다."
    if m := re.fullmatch(r"Scanner Rank:\s*(.+)", raw, re.I):
        cleaned = m.group(1).replace("?", "").strip()
        return f"스캐너 순위: {cleaned}"
    if m := re.fullmatch(r"Tie Break Rule:\s*(.+)", raw, re.I):
        return f"동률 해소 기준: {m.group(1)}"
    if m := re.fullmatch(r"Universe scanned:\s*(\d+)", raw, re.I):
        return f"비교한 후보 수는 {m.group(1)}개였습니다."
    if m := re.fullmatch(r"Selected rank:\s*#?(\d+)", raw, re.I):
        return f"실제 선택 순위는 {m.group(1)}위였습니다."
    if m := re.fullmatch(
        r"Actual traded symbol\s+([A-Z0-9]+)\s+had scanner rank\s+#?(\d+);\s*score\s*([0-9.]+);\s*confidence\s*([0-9.]+);\s*risk\s*([0-9.]+)\.?",
        raw,
        re.I,
    ):
        score = m.group(3).rstrip(".")
        confidence = m.group(4).rstrip(".")
        risk = m.group(5).rstrip(".")
        return (
            f"실제 체결 종목 {m.group(1)}은 스캐너 {m.group(2)}위였고, "
            f"점수는 {score}, 신뢰도는 {confidence}, 위험 점수는 {risk} 수준으로 집계됐습니다."
        )
    if m := re.fullmatch(r"fallback observed in\s*(\d+)/(\d+)\s*route-tagged runs\.?", raw, re.I):
        return f"차순위 재평가 경로는 전체 {m.group(2)}회 중 {m.group(1)}회 관측됐습니다."
    if m := re.fullmatch(r"Fallback entry trigger:\s*(.+)", raw, re.I):
        return f"fallback 진입 트리거는 {_translate_reason_phrase(m.group(1))}였습니다."
    if m := re.fullmatch(r"Supervisor verdict:\s*(.+)", raw, re.I):
        verdict = m.group(1).strip().lower()
        return f"슈퍼바이저 최종 판단은 {'승인' if verdict == 'approve' else _metadata_value(m.group(1))}입니다."
    if m := re.fullmatch(r"Supervisor allow:\s*(.+)", raw, re.I):
        verdict = m.group(1).strip().lower()
        return f"주문 허용 여부는 {'허용' if verdict in {'yes', 'true', 'allowed'} else _metadata_value(m.group(1))}입니다."
    if m := re.fullmatch(r"Guard reason:\s*(.+)", raw, re.I):
        return f"가드 판단 사유는 {_metadata_value(m.group(1))}입니다."
    if m := re.fullmatch(r"Action reviewed:\s*(.+)", raw, re.I):
        return f"검토한 액션은 {_action_label(m.group(1))}입니다."
    if m := re.fullmatch(r"Symbol reviewed:\s*(.+)", raw, re.I):
        return f"검토한 종목은 {m.group(1).strip()}입니다."
    if m := re.fullmatch(
        r"Entry reason:\s*Scanner selected\s+([A-Z0-9]+)\s+as rank #(\d+)\s+out of\s+(\d+)\s+candidates with score\s+([0-9.]+)\s+because it led on\s+(.+?)\.?",
        raw,
        re.I,
    ):
        rationale = m.group(5)
        rationale = rationale.replace("trading value", "거래대금")
        rationale = rationale.replace("theme and sector alignment", "테마 및 섹터 정합성")
        rationale = rationale.replace("theme alignment", "테마 정합성")
        rationale = rationale.replace("sector alignment", "섹터 정합성")
        return (
            f"진입 이유는 {m.group(1)}이 {m.group(3)}개 후보 중 {m.group(2)}위, "
            f"점수 {m.group(4)}로 선정됐고 {rationale}에서 앞섰기 때문입니다."
        )
    if replaced.startswith("SELL was triggered because "):
        reason = replaced[len("SELL was triggered because ") :].strip().rstrip(".")
        return f"{_axis_label(reason)}으로 청산"
    return replaced


def _bullet_lines(section: Dict[str, Any], *, skip_prefixes: Iterable[str] = ()) -> List[str]:
    lines: List[str] = []
    for raw in _listify(section.get("bullets")):
        text = _translate_text(raw)
        if not text:
            continue
        if _looks_corrupted(text):
            continue
        lowered = text.lower()
        if any(lowered.startswith(prefix.lower()) for prefix in skip_prefixes):
            continue
        lines.append(f"- {text}")
    return lines


def _section_summary(section: Dict[str, Any]) -> str:
    summary = _translate_text(section.get("summary"))
    if _looks_corrupted(summary):
        return ""
    return summary


def _build_generation_info(report: Dict[str, Any]) -> List[str]:
    generation = _as_dict(report.get("generation"))
    lines = [
        f"- 생성 상태: {_metadata_value(generation.get('status') or '-')}",
        f"- 생성 방식: {_metadata_value(generation.get('mode') or '-')}",
        f"- 사용 모델: {_metadata_value(generation.get('model') or '-')}",
    ]
    if report.get("generated_at"):
        lines.append(f"- 생성 시각: {_clip(report.get('generated_at'), 80)}")
    reason = _metadata_value(generation.get("reason"))
    if reason:
        lines.append(f"- 생성 사유: {reason}")
    return lines


def _get_truth_surface(report: Dict[str, Any]) -> Dict[str, Any]:
    return _get_truth_surface_impl(report, as_dict=_as_dict)


def _truth_source_label(value: Any) -> str:
    return _truth_source_label_impl(value, clip=_clip, metadata_value=_metadata_value)


def _boolish(value: Any) -> bool:
    return _boolish_impl(value)


def _pnl_basis_label(truth_pnl: Dict[str, Any], shared: Dict[str, Any]) -> str:
    return _pnl_basis_label_impl(
        truth_pnl,
        shared,
        clip=_clip,
        metadata_value=_metadata_value,
        truth_source_label_fn=_truth_source_label,
    )


def _memory_layer_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "daily": "당일",
        "weekly": "주간",
        "monthly": "월간",
        "symbol": "종목",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _authority_label(value: Any) -> str:
    return "확정 기준" if value else "참고 기준"


def _risk_mode_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    return {
        "balanced": "균형형",
        "defensive": "방어형",
        "aggressive": "공격형",
        "normal": "보통",
    }.get(raw, _metadata_value(value) or "-")


def _playbook_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    return {
        "defensive": "방어형",
        "breakout": "돌파형",
        "pullback": "눌림목형",
        "leader": "주도주형",
    }.get(raw, _metadata_value(value) or "-")


def _theme_label(value: Any) -> str:
    raw = _clip(value, 120).lower()
    mapping = {
        "broad_market_leaders": "시장 대표주",
        "illiquid_microcap": "유동성 낮은 초소형주",
        "headline_only_momentum": "헤드라인 추격형 모멘텀",
        "high_gap_speculative": "갭 과열 투기형",
        "counter_trend_low_liquidity": "역추세 저유동성 종목",
        "defensive_assets": "방어 자산군",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _policy_token_label(value: Any) -> str:
    raw = _clip(value, 120)
    lower = raw.lower()
    mapping = {
        "reclaim_gate_ok": "VWAP 재회복 확인",
        "extension_ok": "과열 이격 제한 통과",
        "confidence_ok": "신뢰도 기준 통과",
        "trend_regime=transition": "추세 전환 구간 확인",
        "structure_range_compression=moderate": "가격 압축이 중간 수준",
        "volume_ok": "거래량 확인",
        "breakout_ok": "돌파 확인",
        "pullback_ok": "눌림목 구조 확인",
        "failed_breakout=confirmed": "실패 돌파가 확인된 상태",
        "momentum_decay=strong": "모멘텀 둔화가 강한 상태",
        "vwap_reclaim_required": "VWAP 재회복 확인을 우선 조건으로 둠",
        "monitor_guidance:defensive_exit": "방어적 청산 안내 유지",
        "trade_aggressiveness:medium": "진입 강도는 중간 수준",
    }
    return mapping.get(lower, _metadata_value(value) or "-")


def _is_not_captured(value: Any) -> bool:
    raw = _clip(value, 80).lower()
    return raw in {"", "-", "not_captured", "not captured", "unknown", "unavailable"}


def _is_closed_trade_context(report: Dict[str, Any]) -> bool:
    status = _clip(report.get("status"), 20).lower()
    if status == "closed":
        return True
    shared = _as_dict(report.get("shared_facts"))
    monitor = _as_dict(report.get("monitor_snapshot"))
    action = _clip(shared.get("action") or report.get("action"), 20).upper()
    if action == "SELL" and monitor.get("trigger_type"):
        return True
    return False


def _memory_status_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "ok": "정상 기록",
        "not_recorded": "미기록",
        "missing": "미기록",
        "empty": "비어 있음",
        "auto_ignored": "자동 제외",
        "error": "오류",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _build_truth_surface(report: Dict[str, Any]) -> List[str]:
    truth = _get_truth_surface(report)
    price = _as_dict(truth.get("price"))
    pnl = _as_dict(truth.get("pnl"))
    availability = _as_dict(truth.get("availability"))
    lines: List[str] = []

    broker_buy = price.get("broker_buy_price")
    broker_sell = price.get("broker_fill_price")
    account_mark = price.get("account_mark_price")
    broker_fee = pnl.get("broker_fee")
    broker_tax = pnl.get("broker_tax")
    pnl_value = pnl.get("value")
    pnl_pct = pnl.get("pct")

    lines.append(f"- {_badge('확정값', '#2563eb')} 브로커 체결과 당일 손익 기준을 우선합니다.")

    if broker_buy not in (None, "") and broker_sell not in (None, ""):
        lines.append(f"- 브로커 매수가/매도가는 {_fmt_price(broker_buy)} / {_fmt_price(broker_sell)}입니다.")
    elif broker_sell not in (None, ""):
        lines.append(f"- 브로커 체결 가격은 {_fmt_price(broker_sell)}입니다.")

    if account_mark not in (None, ""):
        lines.append(f"- 계좌 기준 마크 가격은 {_fmt_price(account_mark)}입니다.")

    if pnl_value not in (None, "", "unavailable") and pnl_pct not in (None, ""):
        lines.append(f"- 확정 손익은 {pnl_value} / {_fmt_pct(pnl_pct)}입니다.")
    elif pnl_pct not in (None, ""):
        lines.append(f"- 브로커 체결가와 계좌 평가손익 기준 추정 손익률은 {_fmt_pct(pnl_pct)}입니다.")

    if broker_fee not in (None, "") or broker_tax not in (None, ""):
        lines.append(
            f"- 브로커 수수료/세금은 {broker_fee if broker_fee not in (None, '') else '-'} / "
            f"{broker_tax if broker_tax not in (None, '') else '-'}입니다."
        )
    cost_lines = _trade_cost_analysis_lines(report, bullet="-")
    for cost_line in cost_lines:
        lines.append(cost_line.replace("**", ""))

    price_truth_source = _truth_source_label(price.get("price_truth_source"))
    pnl_truth_source = _truth_source_label(pnl.get("pnl_truth_source"))
    lines.append(f"- 가격 기준은 {price_truth_source}입니다.")
    lines.append(f"- 손익 기준은 {pnl_truth_source}입니다.")

    broker_day_source = _truth_source_label(pnl.get("broker_day_truth_source"))
    broker_day_match_mode = _metadata_value(pnl.get("broker_day_match_mode") or "-")
    broker_day_authoritative = _authority_label(pnl.get("broker_day_authoritative"))
    if pnl.get("broker_day_truth_source"):
        lines.append(
            f"- 브로커 당일 손익은 {broker_day_authoritative}으로 연결됐고, 소스는 {broker_day_source}입니다."
        )
        lines.append(f"- 브로커 당일 손익 매칭 방식은 {broker_day_match_mode}입니다.")

    availability_bits = []
    availability_bits.append("브로커 체결가는 확보됐습니다" if availability.get("broker_fill_present") else "브로커 체결가는 직접 확보되지 않았습니다")
    availability_bits.append("계좌 마크는 확인됐습니다" if availability.get("account_mark_present") else "계좌 마크는 없었습니다")
    availability_bits.append("모니터 가격은 남아 있습니다" if availability.get("monitor_mark_present") else "모니터 가격은 남지 않았습니다")
    availability_bits.append("브로커 손익도 확인됐습니다" if availability.get("broker_pnl_present") else "브로커 손익은 직접 확인되지 않았습니다")
    lines.append(f"- 가용성 요약: {', '.join(availability_bits)}.")

    if (
        broker_buy not in (None, "")
        and broker_sell not in (None, "")
        and float(broker_buy) == float(broker_sell)
        and pnl_value not in (None, "", "unavailable")
        and _num_opt(pnl_value) is not None
        and _num_opt(pnl_value) < 0
    ):
        lines.append("- 매수가와 매도가가 같았고, 손익은 가격 변동이 아니라 수수료와 세금에서 발생했습니다.")

    if broker_sell not in (None, "") and broker_buy in (None, "") and pnl.get("broker_day_truth_source"):
        lines.append("- 브로커 매수 체결가는 직접 복구되지 않았고, 확정 손익은 키움 당일 실현손익 기준으로만 확인했습니다.")

    return lines


def _memory_layers_text(values: Any, *, arrow: bool = False, humanize: bool = True) -> str:
    items = [str(x).strip() for x in _listify(values) if str(x).strip()]
    if not items:
        return "-"
    if humanize:
        items = [_memory_layer_label(x) for x in items]
    return " -> ".join(items) if arrow else ", ".join(items)


def _memory_packet_state_line(name: str, packet: Dict[str, Any]) -> str:
    status = _memory_status_label(packet.get("status") or "not_recorded")
    parts = [status]
    sample_day_count = packet.get("sample_day_count")
    if name in {"weekly", "monthly"} and sample_day_count not in (None, ""):
        parts.append(f"{sample_day_count}days")
    parts.append("활성" if packet.get("active") else "보조 참고")
    return f"{_memory_layer_label(name)}=" + ", ".join(parts)


def _on_off_label(value: Any) -> str:
    return "켜짐" if bool(value) else "꺼짐"


def _applied_label(value: Any) -> str:
    return "적용됨" if bool(value) else "미적용"


def _policy_phase_line(label: str, policy: Dict[str, Any]) -> str:
    active_layers = _memory_layers_text(policy.get("active_layers"))
    priority_order = _memory_layers_text(policy.get("priority_order"), arrow=True)
    scanner_bias = _on_off_label(policy.get("scanner_bias_enabled"))
    monitor_bias = _on_off_label(policy.get("monitor_bias_enabled"))
    symbol_override = _on_off_label(policy.get("symbol_memory_override_enabled"))
    application_mode = _metadata_value(policy.get("application_mode") or "-")
    return (
        f"- [{label}] 활성 레이어={active_layers}; 우선순위={priority_order}; "
        f"scanner bias={scanner_bias}; monitor bias={monitor_bias}; "
        f"symbol override={symbol_override}; 적용 모드={application_mode}."
    )


def _same_policy_snapshot(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    keys = (
        "active_layers",
        "priority_order",
        "scanner_bias_enabled",
        "monitor_bias_enabled",
        "symbol_memory_override_enabled",
        "application_mode",
    )
    return all(left.get(key) == right.get(key) for key in keys)


def _scanner_phase_line(scanner: Dict[str, Any]) -> str:
    source = _metadata_value(scanner.get("source") or "-")
    active_layers = _memory_layers_text(scanner.get("active_layers"))
    not_applied = _metadata_value(scanner.get("not_applied_reason") or "")
    suffix = f"; 미적용 사유={not_applied}" if not_applied else ""
    return (
        f"- [스캐너 적용 시점] captured={_on_off_label(scanner.get('captured'))}; "
        f"enabled={_on_off_label(scanner.get('enabled'))}; "
        f"applied={_applied_label(scanner.get('applied'))}; "
        f"active_layers={active_layers}; source={source}{suffix}."
    )


def _monitor_phase_line(monitor: Dict[str, Any]) -> str:
    source = _metadata_value(monitor.get("source") or "-")
    active_layers = _memory_layers_text(monitor.get("active_layers"))
    not_applied = _metadata_value(monitor.get("not_applied_reason") or "")
    suffix = f"; 미적용 사유={not_applied}" if not_applied else ""
    return (
        f"- [모니터 적용 시점] captured={_on_off_label(monitor.get('captured'))}; "
        f"enabled={_on_off_label(monitor.get('enabled'))}; "
        f"entry={_applied_label(monitor.get('applied'))}; "
        f"hold={_applied_label(monitor.get('hold_applied'))}; "
        f"exit={_applied_label(monitor.get('exit_applied'))}; "
        f"active_layers={active_layers}; source={source}{suffix}."
    )


def _playbook_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "defensive": "방어형",
        "breakout": "돌파형",
        "pullback": "눌림목형",
        "reclaim": "재회복형",
        "leader": "주도주형",
        "balanced": "균형형",
        "normal": "정상",
        "neutral": "중립",
        "aggressive": "공격형",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _monitor_guidance_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "defensive_exit": "방어적 청산 안내",
        "normal_exit": "일반 청산 안내",
        "hold_bias": "보유 우선 안내",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _scanner_bias_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "leader": "주도주 우선",
        "balanced": "균형형",
        "defensive": "방어형",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _policy_source_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "monitor_memory_bias_adjusted": "메모리 조정 반영 정책",
        "baseline_monitor_policy": "기본 모니터 정책",
    }
    return mapping.get(raw, _metadata_value(value) or "-")


def _failure_label(value: Any) -> str:
    raw = _clip(value, 120)
    lower = raw.lower()
    if lower.startswith("playbook:"):
        return f"{_playbook_label(lower.split(':', 1)[1])} 전략 프레임 실패"
    return _metadata_value(value) or "-"


def _reason_tag_summary(tag: str) -> str:
    raw = _clip(tag, 160)
    lower = raw.lower()
    mapping = {
        "daily_strategy_memory_available": "당일 전략 메모리를 사용할 수 있었습니다",
        "daily_prefers_pullback_or_defensive": "당일 메모리는 눌림목/방어형 접근을 선호했습니다",
        "scanner_bias_disabled": "메모리 bias가 비활성화되어 점수 조정에 쓰이지 않았습니다",
        "monitor_bias_disabled": "메모리 bias가 비활성화되어 진입/청산 정책 조정에 쓰이지 않았습니다",
        "commander_monitor_status:stable": "모니터 상태는 안정적이었습니다",
        "commander_focus:exit_quality": "지휘관은 청산 품질 점검을 우선했습니다",
        "commander_focus:guard_blocks": "지휘관은 가드 차단 패턴 점검을 우선했습니다",
        "commander_focus:scanner_fit": "지휘관은 스캐너 적합도 점검을 우선했습니다",
        "symbol_blocker:unknown": "종목별 반복 차단 패턴은 아직 뚜렷하지 않았습니다",
    }
    if lower in mapping:
        return mapping[lower]
    if lower.startswith("daily_best:"):
        return f"당일 메모리는 {_playbook_label(lower.split(':', 1)[1])} 전략 프레임을 우세 신호로 봤습니다"
    if lower.startswith("daily_failure:playbook:"):
        return f"당일 메모리에는 {_playbook_label(lower.split(':', 2)[2])} 전략 프레임 실패 흔적이 남았습니다"
    if lower.startswith("commander_risk_posture:"):
        return f"지휘관 위험 자세는 {_playbook_label(lower.split(':', 1)[1])}이었습니다"
    if lower.startswith("symbol_playbook:"):
        return f"종목 메모리는 {_playbook_label(lower.split(':', 1)[1])} 접근 이력을 보였습니다"
    return _metadata_value(tag) or "-"


def _reason_summary_line(tags: List[Any], prefix: str) -> Optional[str]:
    phrases: List[str] = []
    seen = set()
    for raw in tags:
        text = _reason_tag_summary(str(raw))
        if text and text not in seen:
            seen.add(text)
            phrases.append(text)
    if not phrases:
        return None
    return f"- {prefix} {', '.join(phrases[:4])}."


def _reporter_source_label(source_reports: Dict[str, Any]) -> str:
    if source_reports.get("trade_reports"):
        return "same-day closed trade reports"
    if source_reports.get("reporter_analysis"):
        return "same-day reporter_analysis"
    if source_reports.get("metrics"):
        return "same-day metrics"
    if source_reports.get("trade_explain"):
        return "same-day trade explain"
    if source_reports.get("current_payload"):
        return "current payload"
    return "not_recorded"


def _humanize_reporter_source_label(source_reports: Dict[str, Any]) -> str:
    raw = _reporter_source_label(source_reports)
    mapping = {
        "same-day closed trade reports": "당일 닫힌 거래 리포트",
        "same-day reporter_analysis": "당일 reporter_analysis",
        "same-day metrics": "당일 metrics",
        "same-day trade explain": "당일 trade explain",
        "current payload": "현재 payload",
        "not_recorded": "기록되지 않은 소스",
    }
    return mapping.get(raw, _translate_text(raw))


def _resolve_prompt_proven_surface(memory: Dict[str, Any]) -> Dict[str, Any]:
    prompt = _as_dict(memory.get("prompt_proven"))
    if prompt:
        return prompt
    strategy_memory = _as_dict(memory.get("strategy_memory"))
    memory_packets = _as_dict(memory.get("memory_packets"))
    commander_memory_policy = _as_dict(memory.get("commander_memory_policy"))
    selected_symbol_memory = _as_dict(memory.get("selected_symbol_memory"))
    reporter_feedback_packet = _as_dict(memory.get("reporter_feedback_packet"))
    read_model_facts = _as_dict(memory.get("read_model_facts"))
    selected_trade_count = _num_opt(selected_symbol_memory.get("trade_count"))
    recent_trade_count = _num_opt(read_model_facts.get("recent_trade_count"))
    symbol_pattern_count = _num_opt(read_model_facts.get("symbol_pattern_count"))

    strategy_memory_present = bool(
        strategy_memory.get("present")
        or strategy_memory.get("status")
        or _listify(strategy_memory.get("best_playbooks"))
        or _listify(strategy_memory.get("worst_playbooks"))
        or _listify(strategy_memory.get("recent_failures"))
    )
    commander_memory_policy_present = bool(
        commander_memory_policy.get("present")
        or _listify(commander_memory_policy.get("active_layers"))
        or _listify(commander_memory_policy.get("priority_order"))
        or commander_memory_policy.get("application_mode")
    )
    selected_symbol_memory_present = bool(
        selected_symbol_memory.get("present")
        or (selected_trade_count is not None and selected_trade_count > 0)
        or selected_symbol_memory.get("dominant_playbook")
        or selected_symbol_memory.get("dominant_monitor_blocker")
    )
    reporter_feedback_present = bool(
        reporter_feedback_packet.get("present")
        or reporter_feedback_packet.get("available")
        or reporter_feedback_packet.get("status")
        or reporter_feedback_packet.get("confidence")
        or _as_dict(reporter_feedback_packet.get("source_reports"))
        or _as_dict(reporter_feedback_packet.get("trade_report_analysis"))
        or _listify(reporter_feedback_packet.get("recommendation"))
    )
    read_model_facts_present = bool(
        read_model_facts.get("present")
        or (recent_trade_count is not None and recent_trade_count > 0)
        or (symbol_pattern_count is not None and symbol_pattern_count > 0)
        or read_model_facts.get("daily_summary_present")
        or _listify(read_model_facts.get("symbols"))
    )
    return {
        "status": {
            "strategy_memory_present": strategy_memory_present,
            "memory_packets_present": bool(memory_packets),
            "commander_memory_policy_present": commander_memory_policy_present,
            "selected_symbol_memory_present": selected_symbol_memory_present,
            "reporter_feedback_present": reporter_feedback_present,
            "reporter_feedback_available": bool(reporter_feedback_packet.get("available")),
            "reporter_feedback_consumed": bool(reporter_feedback_packet.get("consumed")),
            "read_model_facts_present": read_model_facts_present,
        },
        "strategy_memory": strategy_memory,
        "memory_packets": memory_packets,
        "commander_memory_policy": commander_memory_policy,
        "selected_symbol_memory": selected_symbol_memory,
        "reporter_feedback_packet": reporter_feedback_packet,
        "read_model_facts": read_model_facts,
    }


def _resolve_reconstructed_memory_surface(memory: Dict[str, Any]) -> Dict[str, Any]:
    reconstructed = _as_dict(memory.get("reconstructed_trade_context"))
    if reconstructed:
        return reconstructed
    return {
        "status": {
            "selected_symbol_memory_rebuilt": False,
            "reporter_feedback_rebuilt": False,
            "memory_packets_rebuilt": False,
            "commander_memory_policy_rebuilt": False,
        },
        "selected_symbol_memory": dict(_as_dict(memory.get("selected_symbol_memory")), rebuilt=False, source="prompt_proven"),
        "reporter_feedback_packet": dict(_as_dict(memory.get("reporter_feedback_packet")), rebuilt=False, source="prompt_proven"),
        "memory_packets": {"rebuilt": False, "source": "prompt_proven"},
        "commander_memory_policy": dict(_as_dict(memory.get("commander_memory_policy")), rebuilt=False, source="prompt_proven"),
        "notes": [],
    }


def _build_prompt_proven_memory(report: Dict[str, Any]) -> List[str]:
    memory = _as_dict(report.get("memory_surface"))
    if not memory:
        return []
    prompt = _resolve_prompt_proven_surface(memory)
    status = _as_dict(prompt.get("status"))
    strategy = _as_dict(prompt.get("strategy_memory"))
    packets = _as_dict(prompt.get("memory_packets"))
    policy = _as_dict(prompt.get("commander_memory_policy"))
    selected = _as_dict(prompt.get("selected_symbol_memory"))
    reporter = _as_dict(prompt.get("reporter_feedback_packet"))
    read_model = _as_dict(prompt.get("read_model_facts"))
    lines: List[str] = []

    def _present_label(value: Any) -> str:
        return "확인" if bool(value) else "미확인"

    def _yes_no(value: Any) -> str:
        return "예" if bool(value) else "아니오"

    lines.append(
        f"- {_badge('입력 확인', '#0f766e')} 전략가 호출 당시 프롬프트에 포함된 메모리, 리포터 피드백, 읽기 모델 입력입니다. "
        "최종 전략 해석은 '전략가 출력 근거'에서 분리해 봅니다."
    )

    lines.append(
        "- [포함 여부] 전략 메모리={strategy}, 메모리 패킷={packets}, 지휘관 정책={policy}, 종목 메모리={symbol}, "
        "리포터 피드백={reporter}, 읽기 모델={read_model}.".format(
            strategy=_present_label(status.get("strategy_memory_present")),
            packets=_present_label(status.get("memory_packets_present")),
            policy=_present_label(status.get("commander_memory_policy_present")),
            symbol=_present_label(status.get("selected_symbol_memory_present")),
            reporter=_present_label(status.get("reporter_feedback_present")),
            read_model=_present_label(status.get("read_model_facts_present")),
        )
    )

    if status.get("commander_memory_policy_present") and policy:
        application_mode = _metadata_value(policy.get("application_mode") or "-")
        lines.append(
            f"- [지휘관 정책] 활성 레이어={_memory_layers_text(policy.get('active_layers'))}; "
            f"우선순위={_memory_layers_text(policy.get('priority_order'), arrow=True)}; 적용 모드={application_mode}."
        )
    else:
        lines.append("- [지휘관 정책] 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if status.get("memory_packets_present") and packets:
        packet_line = "; ".join(
            [
                _memory_packet_state_line("daily", _as_dict(packets.get("daily"))),
                _memory_packet_state_line("weekly", _as_dict(packets.get("weekly"))),
                _memory_packet_state_line("monthly", _as_dict(packets.get("monthly"))),
                _memory_packet_state_line("symbol", _as_dict(packets.get("symbol"))),
            ]
        )
        lines.append(f"- [메모리 패킷] {packet_line}.")
    else:
        lines.append("- [메모리 패킷] 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if status.get("strategy_memory_present") and strategy:
        requested = _metadata_value(strategy.get("requested_day") or "")
        resolved = _metadata_value(strategy.get("resolved_day") or "")
        strategy_parts = [f"상태={_memory_status_label(strategy.get('status') or '-')}"]
        if requested and resolved:
            strategy_parts.append(f"기준일={requested} -> {resolved}")
        best = _memory_layers_text(strategy.get("best_playbooks"))
        worst = _memory_layers_text(strategy.get("worst_playbooks"))
        failures = _memory_layers_text(strategy.get("recent_failures"))
        if best != "-":
            strategy_parts.append(f"우세={_playbook_label(best)}")
        if worst != "-":
            strategy_parts.append(f"취약={_playbook_label(worst)}")
        if failures != "-":
            strategy_parts.append(f"최근 실패={_failure_label(failures)}")
        lines.append(f"- [전략 메모리] {', '.join(strategy_parts)}.")
    else:
        lines.append("- [전략 메모리] 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    prompt_symbol = _metadata_value(selected.get("symbol") or report.get("symbol") or "-")
    if status.get("selected_symbol_memory_present"):
        trade_count = selected.get("trade_count") if selected.get("trade_count") not in (None, "") else "-"
        win_rate = selected.get("win_rate")
        win_rate_text = _fmt_pct(win_rate) if win_rate not in (None, "") else "-"
        dominant_playbook = _metadata_value(selected.get("dominant_playbook") or "-")
        lines.append(
            f"- [종목 메모리] 종목={prompt_symbol}, 과거 거래={trade_count}건, 승률={win_rate_text}, 우세 전략={_playbook_label(dominant_playbook)}."
        )
    else:
        lines.append(f"- [종목 메모리] {prompt_symbol} 세부 메모리는 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if status.get("reporter_feedback_present"):
        source_label = _humanize_reporter_source_label(_as_dict(reporter.get("source_reports")))
        reporter_status = _memory_status_label(reporter.get("status") or ("ok" if reporter.get("available") else "-"))
        reporter_parts = [
            f"사용 가능={_yes_no(reporter.get('available'))}",
            f"소비={_yes_no(reporter.get('consumed'))}",
            f"상태={reporter_status}",
            f"신뢰도={_metadata_value(reporter.get('confidence') or '-')}",
            f"소스={source_label}",
        ]
        analysis = _as_dict(reporter.get("trade_report_analysis"))
        if analysis:
            reporter_parts.append(
                "요약=닫힌 거래 {closed}건 / 승패 {wins}/{losses} / 평균 손익률 {avg}".format(
                    closed=analysis.get("closed_trade_count") if analysis.get("closed_trade_count") not in (None, "") else "-",
                    wins=analysis.get("win_count") if analysis.get("win_count") not in (None, "") else "-",
                    losses=analysis.get("loss_count") if analysis.get("loss_count") not in (None, "") else "-",
                    avg=_fmt_pct(analysis.get("avg_pnl_pct")),
                )
            )
        else:
            reporter_parts.append("요약=없음")
        lines.append(f"- [리포터 피드백] {', '.join(reporter_parts)}.")
    else:
        lines.append("- [리포터 피드백] 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if status.get("read_model_facts_present"):
        symbols = _memory_layers_text(read_model.get("symbols"), humanize=False)
        lines.append(
            f"- [읽기 모델] 최근 거래={read_model.get('recent_trade_count') or 0}건, "
            f"종목 패턴={read_model.get('symbol_pattern_count') or 0}건, "
            f"일간 요약={'있음' if read_model.get('daily_summary_present') else '없음'}."
        )
        if symbols != "-":
            lines.append(f"- [읽기 모델 표본] 종목={symbols}.")
    else:
        lines.append("- [읽기 모델] 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    lines.append("- [해석] 이 값들은 전략가 입력 근거입니다. 실제 수치 조정 여부는 아래 메모리 적용 결과의 스캐너/모니터 라인을 우선 봅니다.")
    return _dedupe(lines)

def _build_reconstructed_trade_memory(report: Dict[str, Any]) -> List[str]:
    memory = _as_dict(report.get("memory_surface"))
    if not memory:
        return []
    reconstructed = _resolve_reconstructed_memory_surface(memory)
    status = _as_dict(reconstructed.get("status"))
    selected = _as_dict(reconstructed.get("selected_symbol_memory"))
    reporter = _as_dict(reconstructed.get("reporter_feedback_packet"))
    policy = _as_dict(reconstructed.get("commander_memory_policy"))
    lines: List[str] = []
    symbol = _metadata_value(report.get("symbol") or selected.get("symbol") or "target_symbol")

    lines.append(f"- {_badge('사후 복원', '#7c3aed')} 실행 기록을 다시 읽어 {symbol} 거래 설명에 필요한 메모리만 보강했습니다.")

    if any(bool(status.get(key)) for key in status):
        lines.append(f"- 전략가 원본 프롬프트 밖의 거래 레벨 메모리를 기준으로 {symbol} 거래 문맥을 보강했습니다.")
    else:
        lines.append("- 이 거래는 전략가 프롬프트만으로 대부분 설명돼, 사후 메모리 복원은 크지 않았습니다.")

    if bool(status.get("selected_symbol_memory_rebuilt")) and selected.get("present"):
        trade_count = selected.get("trade_count") if selected.get("trade_count") not in (None, "") else "-"
        win_rate = selected.get("win_rate")
        lines.append(
            f"- {symbol} 종목 메모리는 저장된 종목 메모리에서 다시 읽었고, 과거 거래 {trade_count}건, 승률 {_fmt_pct(win_rate) if win_rate not in (None, '') else '-'}였습니다."
        )

    if bool(status.get("reporter_feedback_rebuilt")) and reporter.get("available"):
        source_label = _humanize_reporter_source_label(_as_dict(reporter.get("source_reports")))
        analysis = _as_dict(reporter.get("trade_report_analysis"))
        lines.append(
            f"- 당일 리포터 피드백은 {source_label}를 기준으로 다시 구성했고, 닫힌 거래 {analysis.get('closed_trade_count') if analysis.get('closed_trade_count') not in (None, '') else '-'}건 집계를 반영했습니다."
        )
        recommendation = ""
        for item in _listify(reporter.get("recommendation")):
            recommendation = _humanize_reporter_recommendation(item)
            if recommendation:
                break
        if recommendation:
            lines.append(f"- 사후 복원된 리포터 권고는 {_ensure_sentence(recommendation)}")

    if bool(status.get("memory_packets_rebuilt")):
        lines.append("- 전략가 원본 프롬프트에 메모리 묶음 세부 정보가 부족해, 실행 시점 메모리 묶음 문맥을 다시 구성했습니다.")
    if bool(status.get("commander_memory_policy_rebuilt")):
        lines.append(
            f"- 지휘관 메모리 정책도 실행 기록을 기준으로 다시 구성했고, 실제 반영 레이어는 {_memory_layers_text(policy.get('active_layers'))}으로 확인됐습니다."
        )

    if any(bool(status.get(key)) for key in status):
        lines.append("- 전략가 원본 프롬프트를 옮긴 내용이 아니라, 거래 설명용으로 사후 복원한 메모리 레이어입니다.")
    return lines

def _build_memory_application(report: Dict[str, Any]) -> List[str]:
    memory_app = _as_dict(report.get("memory_application_surface"))
    if not memory_app:
        return []
    memory_surface = _as_dict(report.get("memory_surface"))
    prompt_surface = _resolve_prompt_proven_surface(memory_surface) if memory_surface else {}
    prompt_policy = _as_dict(prompt_surface.get("commander_memory_policy"))
    latest_policy = _as_dict(memory_surface.get("commander_memory_policy"))
    scanner = _as_dict(memory_app.get("scanner_memory_bias"))
    monitor = _as_dict(memory_app.get("monitor_memory_bias"))
    lines: List[str] = []

    lines.append(
        f"- {_badge('적용 결과', '#b45309')} 메모리 영향은 전략가 입력, 스캐너 적용, 모니터 적용, 최신 커맨더 상태 순서로 분리했습니다."
    )
    if prompt_policy:
        lines.append(_policy_phase_line("전략가 입력 시점", prompt_policy))
    else:
        lines.append("- [전략가 입력 시점] 지휘관 메모리 정책은 전략가 프롬프트에서 직접 확인되지 않았습니다.")
    if scanner:
        lines.append(_scanner_phase_line(scanner))
    else:
        lines.append("- [스캐너 적용 시점] 스캐너 메모리 적용 trace가 없습니다.")
    if monitor:
        lines.append(_monitor_phase_line(monitor))
    else:
        lines.append("- [모니터 적용 시점] 모니터 메모리 적용 trace가 없습니다.")
    if latest_policy:
        lines.append(_policy_phase_line("최신 커맨더 상태", latest_policy))
        if prompt_policy and not _same_policy_snapshot(prompt_policy, latest_policy):
            lines.append("- [시점 차이] 최신 커맨더 상태는 전략가 프롬프트 이후 실행/복원 기준이라 전략가 입력 시점과 다를 수 있습니다.")
    else:
        lines.append("- [최신 커맨더 상태] 리포트에서 최신 커맨더 메모리 정책을 확인하지 못했습니다.")
    lines.append("- [적용 해석] 전략가 입력 시점의 비활성 여부보다 실제 매매 영향은 스캐너/모니터 적용 시점 라인을 우선 봅니다.")

    if scanner.get("captured"):
        active_layers = _memory_layers_text(scanner.get("active_layers"))
        state = "실제 후보 점수에 적용된 상태" if scanner.get("applied") else "요약만 기록된 상태"
        lines.append(f"- 스캐너 메모리 가중치는 {state}이며, 실제 반영 레이어는 {active_layers}입니다.")
        deltas = _as_dict(scanner.get("source_weight_delta"))
        if deltas:
            ordered = [f"{key} {float(val):+0.3f}" for key, val in deltas.items() if _num_opt(val) is not None]
            if ordered:
                lines.append(f"- 스캐너 소스 가중치 변화는 {', '.join(ordered)}입니다.")
        else:
            lines.append("- 스캐너 쪽은 소스 가중치 변화 상세가 남지 않아, 후보별 가감점만 확인됩니다.")
        symbol = _metadata_value(scanner.get("selected_symbol") or report.get("symbol") or "해당 종목")
        delta = _num_opt(scanner.get("selected_bias_adjustment"))
        if delta is not None:
            if abs(delta) < 1e-12:
                lines.append(f"- 이번 거래 후보 {symbol}에는 메모리 기반 추가 가감점이 없었습니다.")
            else:
                lines.append(f"- 이번 거래 후보 {symbol}에는 메모리 기반 가감점 {delta:+0.3f}이 반영됐습니다.")
        reason = ", ".join(str(x) for x in _listify(scanner.get("reason")) if str(x).strip())
        if reason:
            summary = _reason_summary_line(_listify(scanner.get("reason")), "스캐너 조정은")
            if summary:
                lines.append(summary)
    else:
        lines.append("- 스캐너 메모리 가중치의 실제 delta는 이 거래 artifact에 기록되지 않았습니다.")

    if monitor.get("captured"):
        active_layers_text = _memory_layers_text(monitor.get("active_layers"))
        state = "진입 정책에 적용된 상태" if monitor.get("applied") else "요약만 기록된 상태"
        lines.append(f"- 모니터 메모리 조정은 {state}이며, 실제 반영 레이어는 {active_layers_text}입니다.")
        active_layers = [str(x) for x in _listify(monitor.get("active_layers")) if str(x).strip()]
        if monitor.get("applied") and active_layers:
            lines.append(f"- 이번 거래에서는 모니터가 {_memory_layers_text(active_layers)} 메모리를 진입 판단에 직접 반영했습니다.")
        deltas = []
        for row in _listify(monitor.get("applied_deltas")):
            row = _as_dict(row)
            if not row:
                continue
            deltas.append(
                f"{row.get('field')} {float(row.get('from')):0.3f} -> {float(row.get('to')):0.3f} ({float(row.get('delta')):+0.3f})"
            )
        if deltas:
            lines.append(f"- 진입 정책 변화는 {', '.join(deltas)}입니다.")
            interpretation = _monitor_delta_interpretation(_listify(monitor.get("applied_deltas")))
            if interpretation:
                lines.append(f"- 진입 적용 해석: {interpretation}")
        else:
            lines.append("- 모니터 진입 정책 변화는 이 거래 artifact에 기록되지 않았습니다.")

        hold_deltas = []
        for row in _listify(monitor.get("hold_deltas")):
            row = _as_dict(row)
            if not row:
                continue
            hold_deltas.append(
                f"{row.get('field')} {float(row.get('from')):0.3f} -> {float(row.get('to')):0.3f} ({float(row.get('delta')):+0.3f})"
            )
        if hold_deltas:
            lines.append(f"- 보유 관리 변화는 {', '.join(hold_deltas)}입니다.")
            lines.append("- 보유 관리 해석: 경고 후 재확인 조건을 줄여, 보유 포지션을 더 빨리 정리할 수 있게 했습니다.")

        exit_deltas = []
        for row in _listify(monitor.get("exit_deltas")):
            row = _as_dict(row)
            if not row:
                continue
            exit_deltas.append(
                f"{row.get('field')} {float(row.get('from')):0.3f} -> {float(row.get('to')):0.3f} ({float(row.get('delta')):+0.3f})"
            )
        if exit_deltas:
            lines.append(f"- 청산 정책 변화는 {', '.join(exit_deltas)}입니다.")
            lines.append("- 청산 정책 해석: 손실과 drawdown 기준을 더 타이트하게 잡아, 손상이 확인되면 더 빨리 청산하도록 조정했습니다.")

        lines.append(
            f"- 모니터 위험 자세는 {_playbook_label(monitor.get('risk_posture') or '-')}이었고, 최종 정책 기준은 {_policy_source_label(monitor.get('effective_policy_source') or '-')}이었습니다."
        )
        reason = ", ".join(str(x) for x in _listify(monitor.get("reason")) if str(x).strip())
        if reason:
            summary = _reason_summary_line(_listify(monitor.get("reason")), "모니터 조정은")
            if summary:
                lines.append(summary)
    else:
        lines.append("- 모니터 메모리 조정의 실제 delta는 이 거래 artifact에 기록되지 않았습니다.")

    return lines

def _market_context_structured_lines(context: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for raw in _listify(context.get("bullets")):
        raw_text = _clip(raw, 240)
        if not raw_text:
            continue
        lowered = raw_text.lower()
        if lowered.startswith("global sentiment "):
            value = raw_text.split(" ", 2)[-1].strip()
            lines.append(f"- 시장 심리 수치는 {value}입니다.")
            continue
        if lowered.startswith("global_sentiment score="):
            match = re.search(r"score=([-+]?\\d+(?:\\.\\d+)?)", raw_text, re.I)
            if match:
                lines.append(f"- 시장 심리 수치는 {match.group(1)}입니다.")
            continue
        if lowered.startswith("vix "):
            lines.append(f"- {raw_text}")
            continue
        if lowered.startswith("stress flags:"):
            flags = raw_text.split(":", 1)[1].strip()
            if flags:
                lines.append(f"- 스트레스 신호는 {flags}입니다.")
            continue
        if lowered.startswith("news input:"):
            match = re.search(
                r"(\d+)\s+headlines were considered across\s+(\d+)\s+targets\s+\((\d+)\s+market\s*/\s*(\d+)\s+candidate signals\)\.?",
                raw_text,
                re.I,
            )
            if match:
                lines.append(
                    f"- 뉴스 입력은 {match.group(2)}개 타깃에서 {match.group(1)}개 headline을 검토했고, 시장 {match.group(3)}건 / 후보 {match.group(4)}건 신호를 반영했습니다."
                )
            else:
                lines.append(f"- 뉴스 입력 요약: {raw_text.split(':', 1)[1].strip()}")
            continue
    return lines


def _market_context_summary_from_raw(summary: Any) -> str:
    raw = _clip(summary, 400)
    if not raw:
        return ""
    lowered = raw.lower()
    if "regime" not in lowered and "market sentiment" not in lowered and "playbook" not in lowered:
        return ""
    regime_match = re.search(r"([A-Za-z_-]+)\s+Regime", raw, re.I)
    sentiment_match = re.search(r"([A-Za-z_-]+)\s+Market Sentiment", raw, re.I)
    playbook_match = re.search(r"([A-Za-z_-]+)\s+playbook", raw, re.I)
    regime = regime_match.group(1) if regime_match else "-"
    sentiment = sentiment_match.group(1) if sentiment_match else "-"
    playbook = playbook_match.group(1) if playbook_match else "-"
    return f"- 시장 상태는 {regime}, 시장 심리는 {sentiment}, 선택 플레이북은 {playbook}입니다."


def _build_market_context(report: Dict[str, Any]) -> List[str]:
    context = _resolve_market_context(report)
    lines = []
    summary = _section_summary(context)
    if summary and not _looks_corrupted(summary):
        lines.append(summary)
    structured_summary = _market_context_summary_from_raw(context.get("summary"))
    if structured_summary and structured_summary not in lines:
        lines.append(structured_summary)
    lines.extend(_market_context_structured_lines(context))
    for raw in _listify(context.get("bullets")):
        text = _translate_text(raw)
        if not text:
            continue
        if _looks_corrupted(text):
            continue
        if _mismatched_symbol_news_bullet(text, report.get("symbol")):
            continue
        raw_text = _clip(raw, 240)
        lowered = raw_text.lower()
        if lowered.startswith("global sentiment ") or lowered.startswith("global_sentiment score="):
            continue
        if lowered.startswith("vix "):
            continue
        if lowered.startswith("stress flags:"):
            continue
        if lowered.startswith("news input:"):
            continue
        if "source=" in lowered or "status=" in lowered:
            continue
        if any(key in text for key in ["스캐너 연결 근거는", "전략가 핵심 입력은", "주요 시장 뉴스는"]):
            continue
        if text not in [line.removeprefix("- ").strip() for line in lines]:
            lines.append(f"- {text}")
    headline_count = _num_opt(context.get("headline_count"))
    news_query_count = _num_opt(context.get("news_query_count"))
    market_titles = _sample_news_titles(context.get("market_news_titles"))
    if headline_count is not None and news_query_count is not None:
        lines.append(f"- 뉴스 입력은 {int(news_query_count)}개 관찰 대상에서 {int(headline_count)}개 headline을 검토했습니다.")
    elif headline_count is not None:
        lines.append(f"- 뉴스 입력은 총 {int(headline_count)}개 headline을 검토했습니다.")
    if market_titles:
        lines.append(f"- 참고한 시장 뉴스는 {' / '.join(market_titles)}였습니다.")
    fallback_summary = _translate_text(context.get("strategist_market_context_summary"))
    if (
        fallback_summary
        and not _looks_corrupted(fallback_summary)
        and not fallback_summary.lower().startswith("market regime was ")
    ):
        lines.append(f"- {fallback_summary}")
    regime = context.get("regime")
    sentiment = context.get("market_sentiment")
    playbook = context.get("selected_playbook") or context.get("playbook")
    global_sentiment = _num_opt(context.get("global_sentiment_score"))
    risk_mode = _risk_mode_label(context.get("risk_mode"))
    if not any("시장 상태는" in line or "시장 심리는" in line for line in lines):
        pieces: List[str] = []
        if not _is_not_captured(regime):
            pieces.append(f"시장 상태는 {_metadata_value(regime)}")
        if not _is_not_captured(sentiment):
            pieces.append(f"시장 심리는 {_metadata_value(sentiment)}")
        if not _is_not_captured(playbook):
            pieces.append(f"선택된 전략 프레임은 {_playbook_label(playbook)}")
        if pieces:
            lines.append(f"- {', '.join(pieces)}으로 정리됐습니다.")
    if global_sentiment is not None and not any("글로벌 감성 입력은" in line for line in lines):
        lines.append(f"- 글로벌 감성 입력은 {global_sentiment:.3f}이었고, 전체 위험 톤은 {risk_mode}으로 정리됐습니다.")
    for korea_line in _korea_index_lines(context):
        rendered = f"- 국내 지수는 {korea_line} 기준으로 반영됐습니다."
        if rendered not in lines:
            lines.append(rendered)
    preferred = [_theme_label(x) for x in _listify(context.get("preferred_themes")) if not _is_not_captured(x)]
    avoided = [_theme_label(x) for x in _listify(context.get("avoid_themes")) if not _is_not_captured(x)]
    if preferred and not any("선호 테마는" in line for line in lines):
        lines.append(f"- 선호 테마는 {', '.join(preferred)} 기준으로 정리됐습니다.")
    if avoided and not any("회피 테마는" in line for line in lines):
        lines.append(f"- 회피 테마는 {', '.join(avoided[:3])} 기준으로 정리됐습니다.")
    if not lines:
        lines.append("- 시장 환경 직접 캡처가 충분하지 않아, 저장된 실행 기록과 지휘관 정책 기준으로만 정리했습니다.")
    return _dedupe(lines)


def _build_strategist_summary(report: Dict[str, Any]) -> List[str]:
    strategist = _as_dict(report.get("strategist_summary"))
    context = _resolve_market_context(report)
    shared = _as_dict(report.get("shared_facts"))
    lines: List[str] = []
    summary = _section_summary(strategist)
    if summary and not _looks_corrupted(summary):
        lines.append(summary)
    for raw in _listify(strategist.get("bullets")):
        text = _translate_text(raw)
        if text and not _looks_corrupted(text):
            if _mismatched_symbol_news_bullet(text, report.get("symbol")):
                continue
            lines.append(f"- {text}")
    context_bullets = [_translate_text(x) for x in _listify(context.get("bullets")) if _translate_text(x)]
    for text in context_bullets:
        if _looks_corrupted(text):
            continue
        if text.startswith("전략가 핵심 입력은") or text.startswith("주요 시장 뉴스는"):
            lines.append(f"- {text}")
    if not lines:
        commander_route = _as_dict(shared.get("commander_route"))
        applied_policy = _as_dict(commander_route.get("applied_policy"))
        interpretation_policy = _as_dict(applied_policy.get("interpretation_policy"))
        entry_style = _playbook_label(interpretation_policy.get("entry_style"))
        notes = [_clip(x, 120) for x in _listify(interpretation_policy.get("notes")) if _clip(x, 120)]
        required = [_policy_token_label(x) for x in _listify(interpretation_policy.get("required_checks")) if _clip(x, 80)]
        blockers = [_policy_token_label(x) for x in _listify(interpretation_policy.get("blockers")) if _clip(x, 80)]
        if entry_style != "-":
            lines.append(f"- 전략가는 최종적으로 {entry_style} 전략 프레임을 유지했습니다.")
        if any("monitor_guidance:defensive_exit" in note for note in notes):
            lines.append("- 청산 쪽에는 방어적 청산 안내를 유지했습니다.")
        if any("vwap_reclaim_required" in note for note in notes):
            lines.append("- 진입 해석에서는 VWAP 재회복 확인을 우선 조건으로 두었습니다.")
        if required:
            if len(required[:3]) == 1:
                lines.append(f"- 핵심 확인 조건은 {_noun_predicate_was(required[0])}.")
            else:
                lines.append(f"- 핵심 확인 조건은 {', '.join(required[:3])}였습니다.")
        if blockers:
            lines.append(f"- 경계 신호는 {', '.join(blockers[:2])}였습니다.")
        if not lines:
            lines.append("- 전략가 요약 직접 캡처가 충분하지 않아, 저장된 지휘관 정책과 실행 기록 기준으로만 정리했습니다.")
    linkage = _as_dict(context.get("news_symbol_linkage"))
    linkage_strength = _news_linkage_strength_label(linkage.get("linkage_strength"))
    selected_vs_runner = _as_dict(linkage.get("selected_vs_runner_up"))
    selected_symbol_raw = selected_vs_runner.get("selected_symbol") or linkage.get("selected_symbol") or report.get("symbol")
    selected_symbol = _metadata_value(selected_symbol_raw)
    market_titles = _sample_news_titles(context.get("market_news_titles"))
    candidate_titles = _sample_news_titles_for_symbol(
        selected_symbol_raw,
        context.get("symbol_news_titles"),
        context.get("symbol_headlines"),
        context.get("strategist_symbol_headlines"),
        context.get("candidate_news_titles"),
    )
    runner_up_symbol = _metadata_value(
        selected_vs_runner.get("runner_up_symbol") or linkage.get("runner_up_symbol")
    )
    selected_headline_count = _num_opt(selected_vs_runner.get("selected_headline_count"))
    runner_up_headline_count = _num_opt(selected_vs_runner.get("runner_up_headline_count"))
    if market_titles or candidate_titles:
        pieces: List[str] = []
        if market_titles:
            pieces.append(f"시장 뉴스 {len(market_titles)}건")
        if candidate_titles:
            pieces.append(f"후보 뉴스 {len(candidate_titles)}건")
        if pieces:
            lines.append(f"- 전략가는 {'과 '.join(pieces)}을 함께 확인했습니다.")
        if candidate_titles:
            lines.append(f"- 전략가가 후보군 판단에 참고한 뉴스는 {' / '.join(candidate_titles)}였습니다.")
        if not selected_symbol or not runner_up_symbol:
            lines.append("- 전략가는 뉴스 입력을 시장 톤 확인과 후보군 보조 비교에 사용했습니다.")
    if selected_symbol and runner_up_symbol and selected_headline_count is not None and runner_up_headline_count is not None:
        if int(selected_headline_count) == 0 and int(runner_up_headline_count) == 0:
            lines.append(
                f"- 뉴스 연결 강도는 {linkage_strength}였고, 선택 종목 {selected_symbol}과 차순위 {runner_up_symbol}에 직접 연결된 뉴스는 모두 없어 시장 톤 확인용으로만 활용했습니다."
            )
        else:
            lines.append(
                f"- 뉴스 연결 강도는 {linkage_strength}였고, 선택 종목 {selected_symbol}과 차순위 {runner_up_symbol}의 직접 연결 뉴스는 {int(selected_headline_count)}건 / {int(runner_up_headline_count)}건이었습니다."
            )
    return _dedupe(lines)


def _resolve_strategist_output_surface(report: Dict[str, Any]) -> Dict[str, Any]:
    direct = _as_dict(report.get("strategist_output") or report.get("strategist_output_surface"))
    if direct:
        return direct
    strategist = _as_dict(report.get("strategist_summary"))
    nested = _as_dict(strategist.get("strategist_output"))
    if nested:
        return nested
    visibility = _resolve_entry_execution_visibility(report)
    proposal = _as_dict(visibility.get("strategy_candidate_watch_proposal"))
    entry_control = _as_dict(visibility.get("commander_entry_control"))
    if not proposal and not entry_control:
        return {}

    strategy_detail: Dict[str, Any] = {}
    tactical = _metadata_value(proposal.get("tactical_strategy"))
    if tactical and tactical != "-":
        strategy_detail["tactical_strategy"] = tactical
    if proposal:
        strategy_detail["candidate_watch_policy"] = proposal

    thesis: Dict[str, Any] = {}
    playbook = _metadata_value(
        strategist.get("selected_playbook")
        or strategist.get("playbook")
        or _as_dict(report.get("market_context")).get("selected_playbook")
    )
    risk_tone = _metadata_value(
        strategist.get("risk_tone")
        or _as_dict(report.get("market_context")).get("risk_mode")
        or _as_dict(report.get("market_context")).get("risk_tone")
    )
    if playbook and playbook != "-":
        thesis["selected_playbook"] = playbook
    if risk_tone and risk_tone != "-":
        thesis["risk_tone"] = risk_tone

    out: Dict[str, Any] = {}
    if thesis:
        out["strategy_thesis"] = thesis
    if strategy_detail:
        out["strategy_detail"] = strategy_detail
    return out


def _operatorize_strategist_output_text(value: Any) -> str:
    text = _metadata_value(value)
    if not text:
        return ""
    replacements = (
        ("defensive frame", "방어형 전략 프레임"),
        ("pullback frame", "눌림목 전략 프레임"),
        ("breakout frame", "돌파 전략 프레임"),
        (" with ", " / "),
        ("normal risk tone", "정상 위험 톤"),
        ("balanced risk tone", "균형 위험 톤"),
        ("conservative risk tone", "보수적 위험 톤"),
        ("monitor guidance is defensive_exit", "모니터 가이드는 defensive_exit"),
        ("neutral regime with neutral sentiment", "중립 체제와 중립 감정"),
        ("neutral regime / neutral sentiment", "중립 체제와 중립 감정"),
        ("Active memory layers: none", "활성 메모리 레이어 없음"),
        ("Active memory layers:", "활성 메모리 레이어:"),
        ("unused visible layers:", "미사용 표시 레이어:"),
        ("layer inactive", "레이어 비활성"),
        ("insufficient_trade_count", "거래 수 부족"),
        ("no_symbol", "종목 없음"),
        (
            "News was used for market/theme context and scanner guidance; it was not used as final symbol selection.",
            "뉴스는 시장/테마 맥락과 스캐너 가이드에 사용됐고, 최종 종목 선정 근거로는 사용되지 않았습니다.",
        ),
        (
            "Rank candidates by strategist frame fit, tape confirmation, and risk policy alignment.",
            "전략 프레임 적합도, 장중 확인, 리스크 정책 정합성 기준으로 후보를 정렬했습니다.",
        ),
        ("Entry is conditional on monitor gate confirmation.", "진입은 모니터 게이트 확인 조건부입니다."),
        (
            "Strategist permits only the strategy frame; scanner, monitor, supervisor, and executor still own downstream gates.",
            "전략가는 전략 프레임만 허용하며, 스캐너/모니터/슈퍼바이저/집행기가 후속 게이트를 소유합니다.",
        ),
        ("final_symbol_selection", "최종 종목 선택"),
        ("final_candidate_rank", "최종 후보 순위"),
        ("playbook=defensive", "playbook=방어형"),
        ("playbook=pullback", "playbook=눌림목"),
        ("playbook=breakout", "playbook=돌파"),
        ("risk=normal", "risk=정상"),
        ("status=ok", "status=정상"),
        ("liquidity", "유동성"),
        ("risk_penalty", "리스크 패널티"),
        ("low_volatility", "저변동성"),
        ("illiquid_microcap", "저유동성 소형주"),
        ("headline_only_momentum", "헤드라인 단독 모멘텀"),
        ("high_gap_speculative", "갭 급등 투기성"),
        ("VWAP reclaim", "VWAP 회복"),
        ("rebound confirmation", "리바운드 확인"),
        ("too_extended_from_vwap", "VWAP 대비 과확장"),
        ("breakout_without_volume", "거래량 없는 돌파"),
        ("risk_policy_block", "리스크 정책 차단"),
    )
    out = text
    for src, dst in replacements:
        out = out.replace(src, dst)
    return out


def _strategy_output_text(value: Any, *, max_len: int = 240) -> str:
    text = _operatorize_strategist_output_text(value)
    if not text or text == "-":
        return ""
    return _clip(text, max_len)


def _strategy_output_list_text(values: Any, *, limit: int = 4, sep: str = ", ") -> str:
    items: List[str] = []
    for raw in _listify(values):
        text = _strategy_output_text(raw, max_len=120)
        if not text or text in items:
            continue
        items.append(text)
        if len(items) >= max(1, int(limit)):
            break
    return sep.join(items)


def _strategy_output_layer_bits(layer_decisions: Any) -> str:
    decisions = _as_dict(layer_decisions)
    bits: List[str] = []
    for layer, row in list(decisions.items())[:4]:
        item = _as_dict(row)
        used = "used" if bool(item.get("used")) else "not_used"
        gate = _strategy_output_text(
            item.get("gate_reason") or item.get("reason") or item.get("status"),
            max_len=80,
        )
        bits.append(f"{layer}={used}" + (f"/{gate}" if gate else ""))
    return ", ".join(bits)


def _append_strategy_output_line(lines: List[str], label: str, text: str) -> None:
    clean = _clip(_operatorize_strategist_output_text(text), 320)
    if clean and not _looks_corrupted(clean):
        lines.append(f"- [{label}] {clean}")


def _resolve_strategy_refresh_trace(report: Dict[str, Any]) -> Dict[str, Any]:
    direct = _as_dict(report.get("strategist_refresh_trace"))
    if direct:
        return direct
    output = _resolve_strategist_output_surface(report)
    return _as_dict(output.get("strategy_refresh_trace"))


def _build_strategist_refresh_trace(report: Dict[str, Any]) -> List[str]:
    trace = _resolve_strategy_refresh_trace(report)
    if not trace:
        return []

    lines: List[str] = []
    summary = _strategy_output_text(trace.get("summary"), max_len=420)
    if summary:
        lines.append(summary)

    stage_rows = [row for row in _listify(trace.get("stages")) if isinstance(row, dict)]
    if stage_rows:
        for idx, row in enumerate(stage_rows[:4], start=1):
            label = _strategy_output_text(row.get("label"), max_len=80) or f"{idx}단계"
            stage_summary = _strategy_output_text(row.get("summary"), max_len=260)
            details: List[str] = []
            reason = _strategy_output_text(row.get("reason"), max_len=120)
            selected_symbol = _strategy_output_text(row.get("selected_symbol"), max_len=40)
            if row.get("requested") is not None:
                details.append(f"요청={bool(row.get('requested'))}")
            if row.get("evaluated") is not None:
                details.append(f"평가={bool(row.get('evaluated'))}")
            if row.get("effective") is not None:
                details.append(f"반영={bool(row.get('effective'))}")
            if selected_symbol:
                details.append(f"대상={selected_symbol}")
            if reason:
                details.append(f"사유={reason}")
            line = f"- [{label}] {stage_summary or '기록된 요약 없음'}"
            if details:
                line += f" ({'; '.join(details)})"
            lines.append(line)
    else:
        for raw in _listify(trace.get("bullets")):
            text = _strategy_output_text(raw, max_len=260)
            if text:
                lines.append(f"- {text}")

    delta_count = trace.get("policy_delta_count")
    delta_fields = _strategy_output_list_text(trace.get("policy_delta_fields"), limit=6)
    if delta_count is not None or delta_fields:
        delta_text = f"정책 delta count={delta_count if delta_count is not None else '-'}"
        if delta_fields:
            delta_text += f", fields={delta_fields}"
        lines.append(f"- [최종 정책 변화] {delta_text}")

    return _dedupe(lines)


def _build_strategist_output_surface(report: Dict[str, Any]) -> List[str]:
    output = _resolve_strategist_output_surface(report)
    if not output:
        return []

    lines: List[str] = []
    thesis = _as_dict(output.get("strategy_thesis"))
    strategy_detail = _as_dict(output.get("strategy_detail"))
    memory = _as_dict(output.get("memory_usage_trace"))
    news = _as_dict(output.get("news_usage_trace"))
    scanner = _as_dict(output.get("scanner_handoff"))
    monitor = _as_dict(output.get("monitor_handoff"))
    permission = _as_dict(output.get("trade_permission_frame"))
    boundary = _as_dict(output.get("responsibility_boundary"))

    if thesis:
        one_line = _strategy_output_text(thesis.get("one_line"), max_len=220)
        parts = []
        playbook = _strategy_output_text(thesis.get("selected_playbook"), max_len=60)
        risk_tone = _strategy_output_text(thesis.get("risk_tone"), max_len=60)
        market_view = _strategy_output_text(thesis.get("market_view"), max_len=120)
        if playbook:
            parts.append(f"playbook={playbook}")
        if risk_tone:
            parts.append(f"risk={risk_tone}")
        if market_view:
            parts.append(f"market={market_view}")
        detail = one_line or "; ".join(parts)
        if one_line and parts:
            detail = f"{one_line} ({'; '.join(parts)})"
        _append_strategy_output_line(lines, "전략가 출력", detail)

    if strategy_detail:
        detail_parts: List[str] = []
        pre_llm = _strategy_output_text(strategy_detail.get("pre_llm_playbook"), max_len=60)
        llm_requested = _strategy_output_text(strategy_detail.get("llm_requested_playbook"), max_len=60)
        final_playbook = _strategy_output_text(strategy_detail.get("final_playbook"), max_len=60)
        tactical = _strategy_output_text(strategy_detail.get("tactical_strategy"), max_len=80)
        if pre_llm or llm_requested or final_playbook:
            detail_parts.append(
                f"playbook 흐름={pre_llm or '-'} -> {llm_requested or '-'} -> {final_playbook or '-'}"
            )
        if tactical:
            detail_parts.append(f"전술={tactical}")
        watch = _as_dict(strategy_detail.get("candidate_watch_policy"))
        if watch:
            watch_scope = _rank_scope_text(watch)
            if watch_scope:
                detail_parts.append(f"후보 감시 제안={watch_scope}")
        scores = _as_dict(strategy_detail.get("strategy_scores"))
        if scores:
            ordered_scores = sorted(
                [(str(name), value) for name, value in scores.items() if str(name or "").strip()],
                key=lambda row: float(row[1]) if isinstance(row[1], (int, float)) else -1.0,
                reverse=True,
            )
            detail_parts.append(
                "전략 점수="
                + ", ".join(f"{_strategy_output_text(name, max_len=50)}={value}" for name, value in ordered_scores[:3])
            )
        _append_strategy_output_line(lines, "전략 디테일", "; ".join(part for part in detail_parts if part))

    execution_lines = _entry_watch_execution_lines(report)
    if execution_lines:
        _append_strategy_output_line(lines, "후보 감시 실행", " ".join(execution_lines[:3]))

    if memory:
        active_layers = _memory_layers_text(memory.get("active_layers"), humanize=False)
        priority = _memory_layers_text(memory.get("priority_order"), arrow=True, humanize=False)
        human_summary = _strategy_output_text(memory.get("human_summary"), max_len=220)
        memory_bits = f"활성 레이어: {active_layers}; 우선순위: {priority}"
        if human_summary:
            memory_bits += f"; {human_summary}"
        _append_strategy_output_line(lines, "메모리", memory_bits)
        layer_bits = _strategy_output_layer_bits(memory.get("layer_decisions"))
        if layer_bits:
            _append_strategy_output_line(lines, "메모리 레이어", layer_bits)

    if news:
        news_summary = (
            _strategy_output_text(news.get("human_summary"), max_len=220)
            or _strategy_output_text(news.get("market_effect"), max_len=180)
            or _strategy_output_text(news.get("scanner_guidance_effect"), max_len=180)
        )
        targets = _strategy_output_list_text(news.get("query_targets"), limit=5)
        confidence = _strategy_output_text(news.get("confidence"), max_len=40)
        news_bits = news_summary
        extras = []
        if targets:
            extras.append(f"대상={targets}")
        if confidence:
            extras.append(f"신뢰도={confidence}")
        if extras:
            news_bits = (news_bits + "; " if news_bits else "") + "; ".join(extras)
        _append_strategy_output_line(lines, "뉴스", news_bits)
        headline_text = _strategy_output_list_text(
            news.get("market_headlines_used") or news.get("candidate_headlines_used"),
            limit=2,
            sep=" / ",
        )
        if headline_text:
            _append_strategy_output_line(lines, "뉴스 입력", headline_text)

    if scanner:
        scanner_parts = []
        ranking = _strategy_output_text(scanner.get("ranking_guidance"), max_len=180)
        prefer = _strategy_output_list_text(scanner.get("prefer_candidate_traits"), limit=3)
        penalize = _strategy_output_list_text(scanner.get("penalize_traits"), limit=3)
        if ranking:
            scanner_parts.append(ranking)
        if prefer:
            scanner_parts.append(f"선호={prefer}")
        if penalize:
            scanner_parts.append(f"회피={penalize}")
        _append_strategy_output_line(lines, "스캐너 인계", "; ".join(scanner_parts))

    if monitor:
        monitor_parts = []
        policy_effect = _strategy_output_text(monitor.get("policy_effect_summary"), max_len=180)
        aggressiveness = _strategy_output_text(monitor.get("entry_aggressiveness"), max_len=60)
        confirmations = _strategy_output_list_text(monitor.get("entry_confirmation"), limit=3)
        hold_off = _strategy_output_list_text(monitor.get("hold_off_conditions"), limit=3)
        if policy_effect:
            monitor_parts.append(policy_effect)
        if aggressiveness:
            monitor_parts.append(f"진입 강도={aggressiveness}")
        if confirmations:
            monitor_parts.append(f"확인={confirmations}")
        if hold_off:
            monitor_parts.append(f"보류={hold_off}")
        _append_strategy_output_line(lines, "모니터 인계", "; ".join(monitor_parts))

    if permission:
        permission_parts = []
        level = _strategy_output_text(permission.get("permission_level"), max_len=60)
        reason = _strategy_output_text(permission.get("reason"), max_len=140)
        allowed = _strategy_output_list_text(permission.get("entry_allowed_if"), limit=2)
        blocked = _strategy_output_list_text(permission.get("entry_blocked_if"), limit=2)
        if level:
            permission_parts.append(f"권한={level}")
        if reason:
            permission_parts.append(reason)
        if allowed:
            permission_parts.append(f"허용={allowed}")
        if blocked:
            permission_parts.append(f"차단={blocked}")
        _append_strategy_output_line(lines, "권한 프레임", "; ".join(permission_parts))

    boundary_text = _strategy_output_list_text(
        scanner.get("not_responsible_for") or boundary.get("not_responsible_for"),
        limit=4,
    )
    if boundary_text:
        _append_strategy_output_line(
            lines,
            "역할 경계",
            f"전략가는 {boundary_text}을 직접 결정하지 않습니다. 최종 종목/순위 설명은 스캐너와 모니터 산출물을 기준으로 해석합니다.",
        )

    return _dedupe(lines)


def _is_scanner_execution_mismatch_line(value: Any) -> bool:
    return _is_scanner_execution_mismatch_line_impl(value, metadata_value=_metadata_value)


def _is_scanner_selection_label_line(value: Any) -> bool:
    return _is_scanner_selection_label_line_impl(value, metadata_value=_metadata_value)


def _is_redundant_symbol_selection_line(value: Any) -> bool:
    return _is_redundant_symbol_selection_line_impl(value, metadata_value=_metadata_value)


def _build_symbol_selection(report: Dict[str, Any]) -> List[str]:
    return _build_symbol_selection_impl(
        report,
        as_dict=_as_dict,
        listify=_listify,
        metadata_value=_metadata_value,
        selection_fallback_context=_selection_fallback_context,
        num_opt=_num_opt,
        translate_text=_translate_text,
        looks_corrupted=_looks_corrupted,
        translate_reason_phrase=_translate_reason_phrase,
        clip=_clip,
        section_summary=_section_summary,
        dedupe=_dedupe,
    )


def _build_scanner_comparison(report: Dict[str, Any]) -> List[str]:
    return _build_scanner_comparison_impl(
        report,
        as_dict=_as_dict,
        listify=_listify,
        metadata_value=_metadata_value,
        section_summary=_section_summary,
        looks_corrupted=_looks_corrupted,
        num_opt=_num_opt,
        clip=_clip,
        translate_text=_translate_text,
        translate_reason_phrase=_translate_reason_phrase,
        dedupe=_dedupe,
    )

def _build_entry_decision(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("entry_decision"))
    lines: List[str] = []
    summary = _section_summary(section)
    if summary and not _looks_corrupted(summary):
        lines.append(summary)
    for bullet in _bullet_lines(section):
        lines.append(bullet)
    return _dedupe(lines)


def _build_guard_approval(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("guard_approval_result"))
    lines: List[str] = []
    raw_summary = _clip(section.get("summary"), 120).strip().lower()
    summary = _section_summary(section)
    if summary and raw_summary not in {"guard", "approval", ""} and not _looks_corrupted(summary):
        lines.append(summary)
    repeated = {
        "- 가드 승인 결과를 정리했습니다.",
        "- 슈퍼바이저는 주문을 승인했습니다.",
        "- 가드 판단은 허용이었습니다.",
    }
    for bullet in _bullet_lines(section):
        if summary and bullet in repeated:
            continue
        lines.append(bullet)
    if not lines:
        lines.append("- 가드 승인 결과는 별도 예외 없이 통과했습니다.")
    return _dedupe(lines)

def _parse_monitor_bullet(text: str) -> Optional[str]:
    return _parse_monitor_bullet_impl(
        text,
        action_label=_action_label,
        axis_label=_axis_label,
        metadata_value=_metadata_value,
        translate_text=_translate_text,
    )


def _normalize_monitor_story_line(text: str, *, closed_trade: bool = False) -> Optional[str]:
    return _normalize_monitor_story_line_impl(
        text,
        closed_trade=closed_trade,
        clip=_clip,
        parse_monitor_bullet_fn=_parse_monitor_bullet,
        looks_corrupted=_looks_corrupted,
    )


def _closed_trade_monitor_preface(report: Dict[str, Any]) -> List[str]:
    return _closed_trade_monitor_preface_impl(
        report,
        is_closed_trade_context=_is_closed_trade_context,
        get_truth_surface=_get_truth_surface,
        as_dict=_as_dict,
        badge=_badge,
        fmt_price=_fmt_price,
        fmt_pct=_fmt_pct,
    )


def _build_holding_story(report: Dict[str, Any]) -> List[str]:
    return _build_holding_story_impl(
        report,
        as_dict=_as_dict,
        section_summary=_section_summary,
        is_closed_trade_context=_is_closed_trade_context,
        listify=_listify,
        clip=_clip,
        normalize_monitor_story_line_fn=_normalize_monitor_story_line,
        action_label=_action_label,
        dedupe=_dedupe,
        num_opt=_num_opt,
        axis_label=_axis_label,
        fmt_price=_fmt_price,
        fmt_pct=_fmt_pct,
    )

def _build_exit_decision(report: Dict[str, Any]) -> List[str]:
    return _build_exit_decision_impl(
        report,
        as_dict=_as_dict,
        section_summary=_section_summary,
        is_closed_trade_context=_is_closed_trade_context,
        closed_trade_monitor_preface_fn=_closed_trade_monitor_preface,
        listify=_listify,
        clip=_clip,
        translate_text=_translate_text,
        axis_label=_axis_label,
        action_label=_action_label,
        normalize_monitor_story_line_fn=_normalize_monitor_story_line,
        fmt_pct=_fmt_pct,
        dedupe=_dedupe,
    )


def _build_monitor_snapshot(report: Dict[str, Any]) -> List[str]:
    return _build_monitor_snapshot_impl(
        report,
        as_dict=_as_dict,
        resolve_entry_execution_visibility=_resolve_entry_execution_visibility,
        entry_watch_execution_lines=_entry_watch_execution_lines,
        axis_label=_axis_label,
        fmt_pct=_fmt_pct,
        listify=_listify,
        price_source_label=_price_source_label,
        price_source_policy_label=_price_source_policy_label,
    )


def _price_source_label(value: Any) -> str:
    return _price_source_label_impl(value, clip=_clip, metadata_value=_metadata_value)


def _price_source_policy_label(value: Any) -> str:
    return _price_source_policy_label_impl(value, clip=_clip)

def _build_execution_quality(report: Dict[str, Any]) -> List[str]:
    truth = _get_truth_surface(report)
    price = _as_dict(truth.get("price"))
    pnl = _as_dict(truth.get("pnl"))
    lines: List[str] = []
    sell_price = price.get("broker_fill_price")
    if sell_price not in (None, ""):
        lines.append(f"- 브로커 체결 기준 가격은 {_fmt_price(sell_price)}였습니다.")
    if pnl.get("value") not in (None, "", "unavailable") and pnl.get("pct") not in (None, ""):
        lines.append(f"- 브로커 실현 손익은 {pnl.get('value')} / {_fmt_pct(pnl.get('pct'))} 기준으로 정리했습니다.")
    if pnl.get("broker_fee") not in (None, "") or pnl.get("broker_tax") not in (None, ""):
        lines.append(
            f"- 브로커 수수료/세금은 {pnl.get('broker_fee') if pnl.get('broker_fee') not in (None, '') else '-'} / "
            f"{pnl.get('broker_tax') if pnl.get('broker_tax') not in (None, '') else '-'}였습니다."
        )
    if _as_dict(report.get("execution_details")).get("broker_truth_source"):
        lines.append(f"- 체결 truth 소스는 {_metadata_value(_as_dict(report.get('execution_details')).get('broker_truth_source'))}였습니다.")
    lines.append(f"- 가격 truth 소스는 {_truth_source_label(price.get('price_truth_source'))}으로 확인했습니다.")
    lines.append(f"- 손익 truth 소스는 {_truth_source_label(pnl.get('pnl_truth_source'))}으로 확인했습니다.")
    return lines


def _humanize_reporter_recommendation(text: Any) -> str:
    raw = _clip(text, 240)
    if raw == "Same-day closed trades are loss-heavy; keep defensive entry posture until follow-through quality improves.":
        return "당일 닫힌 거래가 손실 쪽으로 기울어 있어, 추세 연속성 품질이 회복되기 전까지는 진입을 더 방어적으로 유지해야 합니다."
    if raw == "Cached strategist reuse is elevated; compare refresh cadence against fresh full-cycle opportunities.":
        return "기존 전략가 재사용 비중이 높아, 새 전체 재평가 경로를 얼마나 자주 허용할지 다시 점검해야 합니다."
    if raw == "Top blocker is confidence_ok; inspect whether this gate is dominating no-trade outcomes.":
        return "no-trade를 가장 많이 막은 축이 진입 게이트였으니, 이 gate가 과도하게 지배적인지 다시 점검해야 합니다."
    if raw == "Monitor-only share is high; review hold-management concentration before widening entry tuning.":
        return "모니터 단독 경로 비중이 높으니, 진입 조건을 넓히기 전에 보유 관리가 한쪽에 과도하게 쏠리지 않았는지 먼저 점검해야 합니다."
    return _translate_text(raw)

def _humanize_reporter_pattern(name: Any, detail: Any, value: Any) -> str:
    raw_name = _clip(name, 80)
    raw_detail = _clip(detail, 160)
    if raw_name == "freshness_status":
        return ""
    if raw_name == "closed_trade_count" or raw_detail.startswith("closed trade reports"):
        count = _num_opt(value)
        if count is None:
            match = re.search(r"(\d+)", raw_detail)
            count = float(match.group(1)) if match else None
        return f"당일 닫힌 거래는 {int(count)}건이었습니다." if count is not None else ""
    if raw_name == "avg_pnl_pct" or raw_detail.startswith("average same-day pnl pct"):
        pct = _num_opt(value)
        if pct is None:
            match = re.search(r"(-?\d+(?:\.\d+)?)", raw_detail)
            pct = float(match.group(1)) if match else None
        return f"당일 평균 손익률은 {_fmt_pct(pct)}였습니다." if pct is not None else ""
    if m := re.fullmatch(r"(monitor_only|cached_strategist|full_cycle)\s+(\d+)/(\d+)\s+runs", raw_detail, re.I):
        label = {
            "monitor_only": "모니터 단독 경로",
            "cached_strategist": "기존 전략가 재사용 경로",
            "full_cycle": "전체 재평가 경로",
        }.get(m.group(1).lower(), m.group(1))
        return f"{label}가 전체 {m.group(3)}회 중 {m.group(2)}회로 반복됐습니다."
    if m := re.fullmatch(r"(.+?)\s+(\d+)/(\d+)", raw_detail):
        return f"{m.group(1)} 패턴이 전체 {m.group(3)}회 중 {m.group(2)}회였습니다."
    if raw_detail:
        return _translate_text(raw_detail)
    return _translate_text(raw_name)


def _build_reporter_evaluation(report: Dict[str, Any]) -> List[str]:
    reporter_eval = _as_dict(report.get("reporter_evaluation"))
    memory = _as_dict(report.get("memory_surface"))
    packet = _as_dict(memory.get("reporter_feedback_packet"))
    lines: List[str] = []

    if packet.get("available"):
        truth = _get_truth_surface(report)
        pnl = _as_dict(truth.get("pnl"))
        pnl_value = _num_opt(pnl.get("value"))
        if pnl_value is not None:
            if pnl_value > 0:
                trade_result = "수익으로 마감한"
            elif pnl_value < 0:
                trade_result = "손실로 마감한"
            else:
                trade_result = "손익이 거의 없었던"
        else:
            trade_result = "손익을 직접 판단하기 어려운"

        analysis = _as_dict(packet.get("trade_report_analysis"))
        closed_count = analysis.get("closed_trade_count")
        win_count = analysis.get("win_count")
        loss_count = analysis.get("loss_count")
        avg_pnl_pct = analysis.get("avg_pnl_pct")
        source_label = _humanize_reporter_source_label(_as_dict(packet.get("source_reports")))
        lines.append(f"이번 거래는 {trade_result} 흐름이었고, 당일 리포터는 이를 같은 날 반복 패턴 속에서 보조 평가했습니다.")
        lines.append(
            f"- 리포터 소스는 {source_label}였고, 당일 닫힌 거래 {closed_count if closed_count not in (None, '') else '-'}건 중 "
            f"승리 {win_count if win_count not in (None, '') else '-'} / 손실 {loss_count if loss_count not in (None, '') else '-'}, "
            f"평균 손익률 {_fmt_pct(avg_pnl_pct)}였습니다."
        )
        pattern_rows: List[str] = []
        for item in _listify(packet.get("dominant_patterns"))[:3]:
            row = _as_dict(item)
            if row.get("name"):
                humanized = _humanize_reporter_pattern(row.get("name"), row.get("detail"), row.get("value"))
                if humanized:
                    pattern_rows.append(humanized.rstrip("."))
        if pattern_rows:
            lines.append(f"- 당일 반복 패턴 요약: {' / '.join(pattern_rows)}.")
        recommendation = _humanize_reporter_recommendation(_first_nonempty(_listify(packet.get("recommendation"))))
        if recommendation:
            lines.append(f"- 리포터 권고: {recommendation}")
        return lines

    summary = _section_summary(reporter_eval)
    if summary:
        lines.append(summary)
    for bullet in _bullet_lines(reporter_eval):
        lines.append(bullet)
    return _dedupe(lines)

def _build_weaknesses(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("errors_weaknesses_improvement_points"))
    reporter_eval = _as_dict(report.get("reporter_evaluation"))
    memory = _as_dict(report.get("memory_surface"))
    reporter_packet = _as_dict(memory.get("reporter_feedback_packet"))
    reporter_ready = reporter_eval.get("status") == "ok" or reporter_packet.get("available")
    lines: List[str] = []
    summary = _section_summary(section)
    if summary:
        if summary == "Warnings and missing links were recorded for operator follow-up.":
            lines.append("운영자 후속 확인이 필요한 취약 지점을 정리했습니다.")
        else:
            lines.append(summary)
    for bullet in _bullet_lines(section):
        if reporter_ready and "동일 일자 리포터 분석이 아직 이 거래 생애주기에 연결되지 않았습니다." in bullet:
            continue
        lines.append(bullet)
    deduped = _dedupe(lines)
    if len(deduped) <= 3:
        return deduped
    compact = [deduped[0]]
    compact.extend(deduped[1:3])
    if len(deduped) > 3:
        compact.append("- 추가 취약 지점은 저장된 보완 사안 원문에 남겨 두었습니다.")
    return _dedupe(compact)


def _extract_metadata_from_texts(texts: Iterable[str]) -> List[str]:
    lines: List[str] = []
    for text in texts:
        raw = _clip(text, 240)
        if not raw:
            continue
        source_match = re.search(r"source=([A-Za-z0-9_.:/-]+)", raw)
        status_match = re.search(r"status=([A-Za-z0-9_.:/-]+)", raw)
        if source_match:
            lines.append(f"- 데이터 출처: {source_match.group(1)}")
        if status_match:
            lines.append(f"- 상태: {_metadata_value(status_match.group(1))}")
    return lines


def _build_provenance(report: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for section_name, row in _as_dict(report.get("section_provenance")).items():
        item = _as_dict(row)
        if item.get("source"):
            lines.append(f"- 데이터 출처: {_metadata_value(item.get('source'))}")
        if item.get("artifact_path"):
            lines.append(f"- 참조 경로: {item.get('artifact_path')}")
        if item.get("confidence"):
            lines.append(f"- 신뢰도: {_metadata_value(item.get('confidence'))}")
    texts: List[str] = []
    for key in ("market_context_at_entry", "strategist_summary", "why_this_symbol_was_chosen"):
        section = _as_dict(report.get(key))
        texts.extend([_clip(section.get("summary"), 400)])
        texts.extend(_listify(section.get("bullets")))
    lines.extend(_extract_metadata_from_texts(texts))
    generation = _as_dict(report.get("generation"))
    if generation.get("reason"):
        lines.append(f"- 생성 상태: {_metadata_value(generation.get('status') or '-')}")
        lines.append(f"- 생성 사유: {_metadata_value(generation.get('reason'))}")
    return _dedupe(lines)


def _build_timeline(report: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for row in _listify(report.get("full_timeline")):
        item = _as_dict(row)
        event = _clip(item.get("event"), 40).lower()
        desc = _clip(item.get("description"), 240)
        if not desc:
            continue
        if m := re.fullmatch(r"Entry BUY was executed by run (.+)\.", desc):
            lines.append(f"- 진입: run {m.group(1)}에서 매수 진입이 실행됐습니다.")
        elif m := re.fullmatch(r"Exit SELL was executed by run (.+)\.", desc):
            lines.append(f"- 청산: run {m.group(1)}에서 매도 청산이 실행됐습니다.")
        elif event == "entry":
            lines.append(f"- 진입: {_translate_text(desc)}")
        elif event == "exit":
            lines.append(f"- 청산: {_translate_text(desc)}")
        else:
            lines.append(f"- {_translate_text(desc)}")
    return lines


def _translate_watch_item(text: str) -> str:
    raw = _clip(text, 200)
    mapping = {
        "Lifecycle status: closed": "라이프사이클 상태 종결",
        "Monitor trigger changes": "모니터 트리거 변화",
        "Macro/news shifts": "거시 환경 및 뉴스 변화",
        "VWAP retest": "VWAP 재확인",
    }
    return mapping.get(raw, _translate_text(raw))


def _translate_reason_phrase(text: str) -> str:
    raw = _clip(text, 200).strip().strip(".")
    mapping = {
        "breakout above recent high with vwap structure confirmation": "직전 고점 돌파와 VWAP 구조 확인",
        "breakout above recent high with vwap hold and volume confirmation": "VWAP 유지와 거래량 확인이 있는 최근 고점 돌파",
        "pullback structure above vwap with volume confirmation": "VWAP 위 눌림목 구조와 거래량 확인",
        "pullback rebound above vwap with volume confirmation": "VWAP 위 되돌림 반등과 거래량 확인",
    }
    return mapping.get(raw.lower(), _translate_text(raw))


def _translate_invalidation_item(text: str) -> str:
    raw = _clip(text, 200)
    mapping = {
        "stop-loss breach": "손절 기준 이탈",
        "monitor and scanner divergence": "모니터와 스캐너 판단 발산",
        "negative macro regime shift": "거시 환경의 부정적 전환",
        "prior low break": "직전 저점 이탈",
    }
    return mapping.get(raw, _translate_text(raw))


def _ensure_sentence(text: str) -> str:
    raw = _clip(text, 240).strip()
    if not raw:
        return ""
    if raw.endswith(("?", "!", "요.", "입니다.", "였습니다.", "합니다.", "됩니다.", "다.", ".")):
        return raw
    return raw + "입니다."


def _noun_predicate_was(text: str) -> str:
    raw = _clip(text, 240).strip()
    if not raw:
        return "-"
    last = raw[-1]
    if "가" <= last <= "힣":
        base = ord(last) - ord("가")
        has_batchim = (base % 28) != 0
        return raw + ("이었습니다" if has_batchim else "였습니다")
    return raw + "이었습니다"


def _build_final_conclusion(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("final_operator_conclusion"))
    shared = _as_dict(report.get("shared_facts"))
    reporter_eval = _as_dict(report.get("reporter_evaluation"))
    memory = _as_dict(report.get("memory_surface"))
    reporter_packet = _as_dict(memory.get("reporter_feedback_packet"))
    reporter_ready = reporter_eval.get("status") == "ok" or reporter_packet.get("available")
    status = _clip(report.get("status"), 20).lower()
    lines: List[str] = []
    summary = _section_summary(section)
    if summary:
        lines.append(summary)
    raw_summary = _clip(section.get("summary"), 240)
    if raw_summary and not summary and raw_summary not in lines:
        lines.append(raw_summary)
    if status == "closed":
        symbol = _metadata_value(shared.get("symbol") or report.get("symbol") or "해당 거래")
        buy_price = shared.get("broker_buy_price")
        sell_price = shared.get("broker_fill_price")
        if buy_price not in (None, "") and sell_price not in (None, ""):
            lines.append(
                f"현재 판단은 청산 완료입니다. {symbol} 거래는 매수 진입 후 매도 청산까지 기록됐고, "
                f"브로커 매수가/매도가는 {_fmt_price(buy_price)} / {_fmt_price(sell_price)}였습니다."
            )
        else:
            lines.append(f"현재 판단은 청산 완료입니다. {symbol} 거래는 매수 진입 후 매도 청산까지 기록됐습니다.")
        lines.append("- 현재 판단 액션은 매도입니다.")
    else:
        summary = _section_summary(section)
        if summary:
            lines.append(summary)
        lines.append(f"- 현재 판단 액션은 {_action_label(section.get('current_action') or report.get('action'))}입니다.")
    for item in _listify(section.get("watch_next")):
        translated = _translate_watch_item(_clip(item, 200))
        if translated:
            if reporter_ready and "동일 일자 리포터 분석 연계" in translated:
                continue
            lines.append(f"- 다음 확인 항목은 {_ensure_sentence(translated)}")
    for item in _listify(section.get("thesis_invalidation")):
        translated = _translate_invalidation_item(_clip(item, 200))
        if translated:
            lines.append(f"- 기존 판단이 무효화되는 조건은 {_ensure_sentence(translated)}")
    return _dedupe(lines)


def _first_nonempty(values: List[Any]) -> Any:
    for value in values:
        if _clip(value, 240):
            return value
    return ""


def _monitor_delta_interpretation(rows: List[Any]) -> str:
    notes: List[str] = []
    for raw in rows:
        row = _as_dict(raw)
        field = _clip(row.get("field"), 80)
        delta = _num_opt(row.get("delta"))
        if field == "breakout_buffer_pct" and delta is not None and delta > 0:
            notes.append("돌파 확인 버퍼를 키워 추격 진입을 더 보수적으로 막았습니다.")
        elif field == "max_extended_from_vwap_pct" and delta is not None and delta < 0:
            notes.append("VWAP 기준 과확장 추격 허용 범위를 줄여 현재 가격 부담이 큰 진입을 줄였습니다.")
        elif field == "volume_ratio_min" and delta is not None and delta > 0:
            notes.append("거래량 확인 기준을 높여 힘이 약한 종목 진입을 더 엄격하게 걸렀습니다.")
    return " ".join(notes[:3])


def _looks_corrupted(text: str) -> bool:
    if not text:
        return False
    if "?" in text:
        return True
    if any(0xF900 <= ord(ch) <= 0xFAFF for ch in text):
        return True
    weird_markers = ["?꾨", "留ㅻ", "媛먯", "鍮꾪", "湲곗", "蹂댁", "吏꾩", "嫄곕", "理쒖", "泥?궛", "??"]
    return sum(marker in text for marker in weird_markers) >= 2


def _dedupe(lines: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for line in lines:
        key = line.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(line)
    return out
