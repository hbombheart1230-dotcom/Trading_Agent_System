from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from libs.reporting.reporter_feedback import build_strategist_feedback_packet
from libs.reporting.symbol_read_model import build_symbol_read_model
from libs.runtime.commander_memory_policy import build_commander_memory_policy
from libs.runtime.memory_packet_loader import load_commander_memory_packets


def _dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _text(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def _first_dict(*values: Any) -> Dict[str, Any]:
    for value in values:
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _join_text(values: Any, *, max_items: int = 3, max_len: int = 32) -> str:
    items: List[str] = []
    for value in _list(values):
        text = _text(value, max_len=max_len)
        if not text:
            continue
        items.append(text)
        if len(items) >= max(1, int(max_items)):
            break
    return ", ".join(items)


def _nested_memory_sources(
    story_input: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    reasoning_trace = _dict(story_input.get("reasoning_trace"))
    commander_summary = _dict(reasoning_trace.get("commander_summary"))
    strategist_summary = _dict(reasoning_trace.get("strategist_summary"))
    llm_output = _dict(strategist_summary.get("llm_parsed_output"))
    strategist_evidence = _dict(story_input.get("strategist_evidence"))
    decision_frames = _list(strategist_evidence.get("decision_frames"))
    first_frame = decision_frames[0] if decision_frames and isinstance(decision_frames[0], dict) else {}
    frame_payload = _dict(_dict(first_frame).get("payload"))
    visibility = _first_dict(
        story_input.get("memory_packet_visibility"),
        strategist_summary.get("memory_packet_visibility"),
        commander_summary.get("memory_packet_visibility"),
    )
    return commander_summary, strategist_summary, llm_output, frame_payload, visibility


def _resolve_day(source: Dict[str, Any], commander_summary: Dict[str, Any]) -> str:
    for value in (
        source.get("day"),
        source.get("trade_day"),
        commander_summary.get("day"),
        commander_summary.get("ts"),
        source.get("ts"),
    ):
        text = str(value or "").strip()
        if len(text) >= 10:
            return text[:10]
    return ""


def _resolve_reports_root(source: Dict[str, Any]) -> Path:
    reports_root = str(source.get("reports_root") or os.getenv("REPORTS_ROOT", "reports")).strip() or "reports"
    return Path(reports_root)


def _build_symbol_memory_from_persisted(symbol: str, reports_root: Path) -> Dict[str, Any]:
    if not symbol:
        return {}
    model = build_symbol_read_model(str(reports_root / "trades"), symbol, persisted_only=True)
    if not isinstance(model, dict):
        return {}
    trade_count = _safe_int(model.get("trade_count"))
    closed_trade_count = _safe_int(model.get("closed_trade_count"))
    if trade_count <= 0:
        return {}
    return {
        "symbol": str(model.get("symbol") or symbol).strip(),
        "trade_count": trade_count,
        "closed_trade_count": closed_trade_count,
        "win_rate": _safe_float(model.get("win_rate")),
        "dominant_playbook": str(model.get("dominant_playbook") or "").strip(),
        "dominant_monitor_blocker": str(model.get("dominant_monitor_blocker") or "").strip(),
        "override_eligible": trade_count >= 5 and closed_trade_count >= 3,
    }


def _reporter_feedback_strength(packet: Dict[str, Any]) -> tuple[int, int, int, int]:
    source_reports = _dict(packet.get("source_reports"))
    trade_report_analysis = _dict(packet.get("trade_report_analysis"))
    return (
        1 if bool(packet.get("available")) else 0,
        sum(1 for key in ("metrics", "trade_explain", "reporter_analysis", "trade_reports") if source_reports.get(key)),
        _safe_int(trade_report_analysis.get("closed_trade_count")),
        len(_list(packet.get("recommendation") or [])),
    )


def _resolve_reporter_feedback_packet(
    *,
    source: Dict[str, Any],
    commander_summary: Dict[str, Any],
    reporter_feedback: Dict[str, Any],
) -> Dict[str, Any]:
    reports_root = _resolve_reports_root(source)
    day = _resolve_day(source, commander_summary)
    fallback_packet = (
        build_strategist_feedback_packet(
            mode="trade_report_fallback",
            payload={},
            reports_root=reports_root,
            day=day,
        )
        if day
        else {}
    )
    current = dict(reporter_feedback or {})
    if _reporter_feedback_strength(fallback_packet) > _reporter_feedback_strength(current):
        return fallback_packet
    return current


def _build_fallback_memory_context(
    *,
    source: Dict[str, Any],
    commander_summary: Dict[str, Any],
    selected_symbol_memory: Dict[str, Any],
    memory_packets: Dict[str, Any],
    commander_memory_policy: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    reports_root = _resolve_reports_root(source)
    day = _resolve_day(source, commander_summary)
    symbol = str(source.get("symbol") or source.get("selected_symbol") or "").strip()

    resolved_selected_symbol_memory = dict(selected_symbol_memory or {})
    if not resolved_selected_symbol_memory and symbol:
        resolved_selected_symbol_memory = _build_symbol_memory_from_persisted(symbol, reports_root)

    fallback_state = {
        "day": day,
        "reports_root": str(reports_root),
        "selected": {"symbol": symbol} if symbol else {},
        "selected_symbol_memory": dict(resolved_selected_symbol_memory or {}),
    }
    resolved_packets = dict(memory_packets or {})
    if not resolved_packets:
        resolved_packets = load_commander_memory_packets(state=fallback_state)

    resolved_policy = dict(commander_memory_policy or {})
    if not resolved_policy and resolved_packets:
        session_bias = str(
            commander_summary.get("session_bias")
            or _dict(commander_summary.get("commander_decision")).get("session_bias")
            or "active_selection"
        ).strip() or "active_selection"
        resolved_policy = build_commander_memory_policy(
            session_bias=session_bias,
            memory_packets=resolved_packets,
        )
    return resolved_selected_symbol_memory, resolved_packets, resolved_policy


def build_trade_report_memory_surface(story_input: Dict[str, Any] | None) -> Dict[str, Any]:
    source = story_input if isinstance(story_input, dict) else {}
    commander_summary, strategist_summary, llm_output, frame_payload, visibility = _nested_memory_sources(source)

    strategy_memory = _first_dict(
        frame_payload.get("strategy_memory"),
        llm_output.get("strategy_memory"),
    )
    reporter_feedback = _first_dict(
        frame_payload.get("reporter_feedback_packet"),
        llm_output.get("reporter_feedback_packet"),
    )
    selected_symbol_memory = _first_dict(
        frame_payload.get("selected_symbol_memory"),
        llm_output.get("selected_symbol_memory"),
    )
    read_model_facts = _first_dict(
        frame_payload.get("read_model_facts"),
        llm_output.get("read_model_facts"),
    )
    memory_packets = _first_dict(
        frame_payload.get("memory_packets"),
        llm_output.get("memory_packets"),
        commander_summary.get("memory_packets"),
    )
    commander_memory_policy = _first_dict(
        frame_payload.get("commander_memory_policy"),
        llm_output.get("commander_memory_policy"),
        strategist_summary.get("commander_memory_policy"),
        commander_summary.get("commander_memory_policy"),
    )

    prompt_strategy_memory = dict(strategy_memory or {})
    prompt_reporter_feedback = dict(reporter_feedback or {})
    prompt_selected_symbol_memory = dict(selected_symbol_memory or {})
    prompt_read_model_facts = dict(read_model_facts or {})
    prompt_memory_packets = dict(memory_packets or {})
    prompt_commander_memory_policy = dict(commander_memory_policy or {})

    selected_symbol_memory, memory_packets, commander_memory_policy = _build_fallback_memory_context(
        source=source,
        commander_summary=commander_summary,
        selected_symbol_memory=selected_symbol_memory,
        memory_packets=memory_packets,
        commander_memory_policy=commander_memory_policy,
    )
    reporter_feedback = _resolve_reporter_feedback_packet(
        source=source,
        commander_summary=commander_summary,
        reporter_feedback=reporter_feedback,
    )

    read_model_visibility = _dict(visibility.get("read_model_facts"))
    recent_feedback_visibility = _dict(visibility.get("recent_strategy_feedback"))
    strategy_visibility = _dict(visibility.get("strategy_memory"))
    selected_visibility = _dict(visibility.get("selected_symbol_memory"))
    reporter_visibility = _dict(visibility.get("reporter_feedback_packet"))
    packets_visibility = _dict(visibility.get("memory_packets"))
    policy_visibility = _dict(visibility.get("commander_memory_policy"))

    prompt_daily_packet = _dict(prompt_memory_packets.get("daily_strategy_memory"))
    prompt_weekly_packet = _dict(prompt_memory_packets.get("weekly_strategy_memory"))
    prompt_monthly_packet = _dict(prompt_memory_packets.get("monthly_strategy_memory"))
    prompt_symbol_packet = _dict(prompt_memory_packets.get("symbol_memory_packet"))

    daily_packet = _dict(memory_packets.get("daily_strategy_memory"))
    weekly_packet = _dict(memory_packets.get("weekly_strategy_memory"))
    monthly_packet = _dict(memory_packets.get("monthly_strategy_memory"))
    symbol_packet = _dict(memory_packets.get("symbol_memory_packet"))

    symbol = _text(
        source.get("symbol")
        or selected_visibility.get("symbol")
        or selected_symbol_memory.get("symbol")
        or symbol_packet.get("symbol"),
        max_len=24,
    )
    playbook = _text(llm_output.get("playbook") or strategist_summary.get("playbook"), max_len=40)
    monitor_guidance = _text(llm_output.get("monitor_guidance"), max_len=40)
    scanner_bias = _text(llm_output.get("scanner_bias"), max_len=40)

    prompt_strategy_present = bool(prompt_strategy_memory) or bool(strategy_visibility.get("present"))
    prompt_selected_present = bool(prompt_selected_symbol_memory) or bool(selected_visibility.get("present"))
    prompt_reporter_present = bool(prompt_reporter_feedback) or bool(reporter_visibility.get("present"))
    prompt_read_model_present = bool(prompt_read_model_facts) or bool(read_model_visibility.get("present"))
    prompt_reporter_available = bool(prompt_reporter_feedback.get("available")) or bool(reporter_visibility.get("available"))
    prompt_reporter_consumed = bool(prompt_reporter_feedback.get("consumed")) or bool(reporter_visibility.get("consumed"))

    strategy_present = bool(strategy_memory) or bool(strategy_visibility.get("present"))
    selected_present = bool(selected_symbol_memory) or bool(selected_visibility.get("present"))
    reporter_present = bool(reporter_feedback) or bool(reporter_visibility.get("present"))
    read_model_present = bool(read_model_facts) or bool(read_model_visibility.get("present"))
    reporter_available = bool(reporter_feedback.get("available")) or bool(reporter_visibility.get("available"))
    reporter_consumed = bool(reporter_feedback.get("consumed")) or bool(reporter_visibility.get("consumed"))

    prompt_strategy_status = _text(
        prompt_strategy_memory.get("status") or strategy_visibility.get("status"),
        max_len=40,
    )
    prompt_strategy_requested_day = _text(
        prompt_strategy_memory.get("requested_day") or strategy_visibility.get("requested_day"),
        max_len=16,
    )
    prompt_strategy_resolved_day = _text(
        prompt_strategy_memory.get("resolved_day") or strategy_visibility.get("resolved_day"),
        max_len=16,
    )
    prompt_best_playbooks = _list(prompt_strategy_memory.get("best_playbooks") or [])
    prompt_worst_playbooks = _list(prompt_strategy_memory.get("worst_playbooks") or [])
    prompt_recent_failures = _list(prompt_strategy_memory.get("recent_failures") or [])
    prompt_recent_success_patterns = _list(prompt_strategy_memory.get("recent_success_patterns") or [])

    prompt_selected_trade_count = _safe_int(
        prompt_selected_symbol_memory.get("trade_count")
        if prompt_selected_symbol_memory
        else selected_visibility.get("trade_count")
    )
    prompt_selected_win_rate = _safe_float(
        prompt_selected_symbol_memory.get("win_rate")
        if prompt_selected_symbol_memory
        else selected_visibility.get("win_rate")
    )
    prompt_selected_blocker = _text(
        prompt_selected_symbol_memory.get("dominant_monitor_blocker")
        if prompt_selected_symbol_memory
        else selected_visibility.get("dominant_monitor_blocker"),
        max_len=60,
    )
    prompt_selected_playbook = _text(
        prompt_selected_symbol_memory.get("dominant_playbook")
        if prompt_selected_symbol_memory
        else selected_visibility.get("dominant_playbook"),
        max_len=40,
    )

    prompt_reporter_status = _text(
        prompt_reporter_feedback.get("status") or reporter_visibility.get("status"),
        max_len=40,
    )
    prompt_reporter_gate_reason = _text(
        prompt_reporter_feedback.get("feedback_gate_reason") or reporter_visibility.get("feedback_gate_reason"),
        max_len=40,
    )
    prompt_reporter_confidence = _text(
        prompt_reporter_feedback.get("confidence") or reporter_visibility.get("confidence"),
        max_len=24,
    )
    prompt_reporter_source_reports = _dict(prompt_reporter_feedback.get("source_reports"))
    prompt_reporter_trade_report_analysis = _dict(prompt_reporter_feedback.get("trade_report_analysis"))
    prompt_reporter_dominant_patterns = _list(prompt_reporter_feedback.get("dominant_patterns"))
    prompt_reporter_recommendations = _list(prompt_reporter_feedback.get("recommendation"))
    prompt_reporter_insight_summary = _text(prompt_reporter_feedback.get("insight_summary"), max_len=220)

    prompt_read_model_recent_trade_count = _safe_int(
        prompt_read_model_facts.get("recent_trade_count")
        if prompt_read_model_facts
        else read_model_visibility.get("recent_trade_count")
    )
    prompt_read_model_symbol_pattern_count = _safe_int(
        prompt_read_model_facts.get("symbol_pattern_count")
        if prompt_read_model_facts
        else read_model_visibility.get("symbol_pattern_count")
    )
    prompt_read_model_symbols = _list(prompt_read_model_facts.get("symbols") or read_model_visibility.get("symbols"))
    prompt_read_model_daily_summary_present = bool(
        prompt_read_model_facts.get("daily_summary_present")
        if prompt_read_model_facts
        else read_model_visibility.get("daily_summary_present")
    )

    prompt_active_layers = _list(
        prompt_commander_memory_policy.get("active_layers") or policy_visibility.get("active_layers")
    )
    prompt_priority_order = _list(
        prompt_commander_memory_policy.get("priority_order") or policy_visibility.get("priority_order")
    )

    reporter_feedback_rebuilt = _reporter_feedback_strength(reporter_feedback) > _reporter_feedback_strength(prompt_reporter_feedback)
    selected_symbol_memory_rebuilt = bool(selected_symbol_memory) and not bool(prompt_selected_symbol_memory)
    memory_packets_rebuilt = bool(memory_packets) and not bool(prompt_memory_packets)
    commander_memory_policy_rebuilt = bool(commander_memory_policy) and not bool(prompt_commander_memory_policy)
    prompt_symbol = _text(
        prompt_selected_symbol_memory.get("symbol")
        or selected_visibility.get("symbol")
        or prompt_symbol_packet.get("symbol"),
        max_len=24,
    )

    reconstructed_notes: List[str] = []
    if selected_symbol_memory_rebuilt:
        reconstructed_notes.append("trade_symbol_symbol_memory_rebuilt_from_persisted_symbol_history")
    if reporter_feedback_rebuilt:
        reconstructed_notes.append("same_day_reporter_feedback_rebuilt_from_same_day_trade_reports")
    if memory_packets_rebuilt:
        reconstructed_notes.append("memory_packets_rebuilt_from_runtime_loader")
    if commander_memory_policy_rebuilt:
        reconstructed_notes.append("commander_memory_policy_rebuilt_from_runtime_policy")

    strategy_status = _text(
        strategy_memory.get("status") or strategy_visibility.get("status"),
        max_len=40,
    )
    strategy_requested_day = _text(strategy_memory.get("requested_day") or strategy_visibility.get("requested_day"), max_len=16)
    strategy_resolved_day = _text(strategy_memory.get("resolved_day") or strategy_visibility.get("resolved_day"), max_len=16)
    best_playbooks = _list(strategy_memory.get("best_playbooks") or [])
    worst_playbooks = _list(strategy_memory.get("worst_playbooks") or [])
    recent_failures = _list(strategy_memory.get("recent_failures") or [])
    recent_success_patterns = _list(strategy_memory.get("recent_success_patterns") or [])

    selected_trade_count = _safe_int(
        selected_symbol_memory.get("trade_count")
        if selected_symbol_memory
        else selected_visibility.get("trade_count")
    )
    selected_win_rate = _safe_float(
        selected_symbol_memory.get("win_rate")
        if selected_symbol_memory
        else selected_visibility.get("win_rate")
    )
    selected_blocker = _text(
        selected_symbol_memory.get("dominant_monitor_blocker")
        if selected_symbol_memory
        else selected_visibility.get("dominant_monitor_blocker"),
        max_len=60,
    )
    selected_playbook = _text(
        selected_symbol_memory.get("dominant_playbook")
        if selected_symbol_memory
        else selected_visibility.get("dominant_playbook"),
        max_len=40,
    )

    read_model_recent_trade_count = _safe_int(read_model_visibility.get("recent_trade_count"))
    read_model_symbol_pattern_count = _safe_int(read_model_visibility.get("symbol_pattern_count"))
    read_model_symbols = _list(read_model_visibility.get("symbols"))
    read_model_daily_summary_present = bool(read_model_visibility.get("daily_summary_present"))

    reporter_status = _text(
        reporter_feedback.get("status") or reporter_visibility.get("status"),
        max_len=40,
    )
    reporter_gate_reason = _text(
        reporter_feedback.get("feedback_gate_reason") or reporter_visibility.get("feedback_gate_reason"),
        max_len=40,
    )
    reporter_confidence = _text(
        reporter_feedback.get("confidence") or reporter_visibility.get("confidence"),
        max_len=24,
    )
    reporter_recommendation_count = len(_list(reporter_feedback.get("recommendation") or []))
    reporter_source_reports = _dict(reporter_feedback.get("source_reports"))
    reporter_trade_report_analysis = _dict(reporter_feedback.get("trade_report_analysis"))
    reporter_dominant_patterns = _list(reporter_feedback.get("dominant_patterns"))
    reporter_recommendations = _list(reporter_feedback.get("recommendation"))
    reporter_insight_summary = _text(reporter_feedback.get("insight_summary"), max_len=220)

    active_layers = _list(commander_memory_policy.get("active_layers") or policy_visibility.get("active_layers"))
    priority_order = _list(commander_memory_policy.get("priority_order") or policy_visibility.get("priority_order"))

    usage_notes: List[str] = []
    if strategy_present:
        usage_notes.append("전략 메모리는 집계형 strategy_memory로 전략가에 전달됐습니다.")
        if strategy_requested_day or strategy_resolved_day:
            usage_notes.append(
                f"전략 메모리 요청일/해석일은 {strategy_requested_day or '-'} / {strategy_resolved_day or '-'}입니다."
            )
        if best_playbooks or worst_playbooks or recent_failures:
            usage_notes.append(
                "전략 메모리상 우세/취약 playbook과 최근 실패 흔적은 "
                f"{_join_text(best_playbooks, max_items=2) or '없음'} / "
                f"{_join_text(worst_playbooks, max_items=2) or '없음'} / "
                f"{_join_text(recent_failures, max_items=3, max_len=48) or '없음'}입니다."
            )
    else:
        usage_notes.append("전략 메모리는 이번 리포트 입력 기준으로 비어 있었습니다.")

    if commander_memory_policy or policy_visibility:
        usage_notes.append(
            "메모리 우선순위와 활성 layer 결정권은 commander가 가졌고, "
            f"active layer / priority는 {_join_text(active_layers, max_items=4, max_len=16) or '없음'} / "
            f"{_join_text(priority_order, max_items=4, max_len=16) or '없음'}입니다."
        )

    if daily_packet or weekly_packet or monthly_packet or symbol_packet or packets_visibility:
        usage_notes.append(
            "raw memory packet 상태는 "
            f"daily={_text(daily_packet.get('status') or _dict(packets_visibility.get('daily')).get('status') or 'unavailable', max_len=24)}, "
            f"weekly={_text(weekly_packet.get('status') or _dict(packets_visibility.get('weekly')).get('status') or 'unavailable', max_len=24)}"
            f"({_safe_int(weekly_packet.get('sample_day_count') if weekly_packet else _dict(packets_visibility.get('weekly')).get('sample_day_count'))}days), "
            f"monthly={_text(monthly_packet.get('status') or _dict(packets_visibility.get('monthly')).get('status') or 'unavailable', max_len=24)}"
            f"({_safe_int(monthly_packet.get('sample_day_count') if monthly_packet else _dict(packets_visibility.get('monthly')).get('sample_day_count'))}days), "
            f"symbol={_text(symbol_packet.get('status') or _dict(packets_visibility.get('symbol')).get('status') or 'unavailable', max_len=24)}입니다."
        )

    if selected_present:
        selected_parts = [f"{symbol or '해당 종목'} 종목 메모리가 들어왔습니다"]
        if selected_trade_count:
            selected_parts.append(f"과거 거래 {selected_trade_count}건")
        if selected_win_rate is not None:
            selected_parts.append(f"승률 {selected_win_rate * 100.0:.1f}%")
        if selected_playbook:
            selected_parts.append(f"우세 playbook {selected_playbook}")
        if selected_blocker:
            selected_parts.append(f"주요 blocker {selected_blocker}")
        usage_notes.append(", ".join(selected_parts) + "입니다.")
    else:
        usage_notes.append(f"{symbol or '해당 종목'} 종목 메모리는 비어 있었고, 종목별 과거 이력 제약은 직접 반영되지 않았습니다.")

    if reporter_available or reporter_consumed:
        usage_notes.append(
            f"same-day reporter feedback은 상태 {reporter_status or 'ok'} / 신뢰도 {reporter_confidence or '-'}로 전략가에 반영됐습니다."
        )
    elif reporter_present:
        usage_notes.append(
            f"same-day reporter feedback은 {reporter_status or '미사용'} 상태였고 gate 사유는 {reporter_gate_reason or '확인되지 않음'}이었습니다."
        )
    else:
        usage_notes.append("same-day reporter feedback은 이번 리포트 입력에 없었습니다.")

    if read_model_present:
        daily_summary_text = "있음" if read_model_daily_summary_present else "없음"
        usage_notes.append(
            f"read_model_facts는 최근 거래 {read_model_recent_trade_count}건, 종목 패턴 {read_model_symbol_pattern_count}건, 일일 요약 {daily_summary_text} 기준으로 들어갔습니다."
        )
        if read_model_symbols:
            usage_notes.append(
                f"read_model_facts 종목 패턴 표본은 {_join_text(read_model_symbols, max_items=5, max_len=24) or '없음'}입니다."
            )
    else:
        usage_notes.append("read_model_facts는 이번 리포트 입력에서 직접 확인되지 않았습니다.")

    if playbook or monitor_guidance or scanner_bias:
        usage_notes.append(
            f"전략가 출력에는 playbook={playbook or '-'}, monitor_guidance={monitor_guidance or '-'}, scanner_bias={scanner_bias or '-'}가 남았습니다."
        )

    return {
        "status": {
            "strategy_memory_used": strategy_present,
            "selected_symbol_memory_used": selected_present,
            "reporter_feedback_used": reporter_available or reporter_consumed,
            "read_model_facts_used": read_model_present,
        },
        "strategy_memory": {
            "present": strategy_present,
            "scope": "aggregated_strategy_memory",
            "separate_daily_weekly_monthly_packets": True,
            "status": strategy_status,
            "requested_day": strategy_requested_day,
            "resolved_day": strategy_resolved_day,
            "best_playbooks": best_playbooks[:3],
            "worst_playbooks": worst_playbooks[:3],
            "recent_failures": recent_failures[:3],
            "recent_success_patterns": recent_success_patterns[:3],
        },
        "commander_memory_policy": {
            "present": bool(commander_memory_policy) or bool(policy_visibility.get("present")),
            "application_mode": _text(
                commander_memory_policy.get("application_mode") or policy_visibility.get("application_mode"),
                max_len=24,
            ),
            "active_layers": active_layers[:4],
            "priority_order": priority_order[:4],
            "symbol_memory_override_enabled": bool(
                commander_memory_policy.get("symbol_memory_override_enabled")
                if commander_memory_policy
                else policy_visibility.get("symbol_memory_override_enabled")
            ),
            "scanner_bias_enabled": bool(
                commander_memory_policy.get("scanner_bias_enabled")
                if commander_memory_policy
                else policy_visibility.get("scanner_bias_enabled")
            ),
            "monitor_bias_enabled": bool(
                commander_memory_policy.get("monitor_bias_enabled")
                if commander_memory_policy
                else policy_visibility.get("monitor_bias_enabled")
            ),
        },
        "memory_packets": {
            "daily": {
                "status": _text(daily_packet.get("status") or _dict(packets_visibility.get("daily")).get("status"), max_len=24),
                "active": bool(daily_packet.get("active") if daily_packet else _dict(packets_visibility.get("daily")).get("active")),
                "resolved_day": _text(daily_packet.get("resolved_day") or _dict(packets_visibility.get("daily")).get("resolved_day"), max_len=16),
                "best_playbook_count": len(_list(daily_packet.get("best_playbooks"))),
            },
            "weekly": {
                "status": _text(weekly_packet.get("status") or _dict(packets_visibility.get("weekly")).get("status"), max_len=24),
                "active": bool(weekly_packet.get("active") if weekly_packet else _dict(packets_visibility.get("weekly")).get("active")),
                "resolved_day": _text(weekly_packet.get("resolved_day") or _dict(packets_visibility.get("weekly")).get("resolved_day"), max_len=16),
                "sample_day_count": _safe_int(weekly_packet.get("sample_day_count") if weekly_packet else _dict(packets_visibility.get("weekly")).get("sample_day_count")),
            },
            "monthly": {
                "status": _text(monthly_packet.get("status") or _dict(packets_visibility.get("monthly")).get("status"), max_len=24),
                "active": bool(monthly_packet.get("active") if monthly_packet else _dict(packets_visibility.get("monthly")).get("active")),
                "resolved_day": _text(monthly_packet.get("resolved_day") or _dict(packets_visibility.get("monthly")).get("resolved_day"), max_len=16),
                "sample_day_count": _safe_int(monthly_packet.get("sample_day_count") if monthly_packet else _dict(packets_visibility.get("monthly")).get("sample_day_count")),
            },
            "symbol": {
                "status": _text(symbol_packet.get("status") or _dict(packets_visibility.get("symbol")).get("status"), max_len=24),
                "active": bool(symbol_packet.get("active") if symbol_packet else _dict(packets_visibility.get("symbol")).get("active")),
                "symbol": _text(symbol_packet.get("symbol") or _dict(packets_visibility.get("symbol")).get("symbol"), max_len=24),
                "trade_count": _safe_int(symbol_packet.get("trade_count") if symbol_packet else _dict(packets_visibility.get("symbol")).get("trade_count")),
            },
        },
        "selected_symbol_memory": {
            "present": selected_present,
            "symbol": symbol,
            "trade_count": selected_trade_count,
            "win_rate": selected_win_rate,
            "dominant_playbook": selected_playbook,
            "dominant_monitor_blocker": selected_blocker,
        },
        "reporter_feedback_packet": {
            "present": reporter_present,
            "available": reporter_available,
            "consumed": reporter_consumed,
            "status": reporter_status,
            "feedback_gate_reason": reporter_gate_reason,
            "confidence": reporter_confidence,
            "recommendation_count": reporter_recommendation_count,
            "source_reports": {
                "metrics": bool(reporter_source_reports.get("metrics")),
                "trade_explain": bool(reporter_source_reports.get("trade_explain")),
                "reporter_analysis": bool(reporter_source_reports.get("reporter_analysis")),
                "trade_reports": bool(reporter_source_reports.get("trade_reports")),
                "current_payload": bool(reporter_source_reports.get("current_payload")),
            },
            "insight_summary": reporter_insight_summary,
            "dominant_patterns": [
                {
                    "name": _text(_dict(item).get("name"), max_len=40),
                    "detail": _text(_dict(item).get("detail"), max_len=120),
                    "value": _safe_float(_dict(item).get("value")),
                }
                for item in reporter_dominant_patterns[:4]
                if isinstance(item, dict)
            ],
            "recommendation": [
                _text(item, max_len=140)
                for item in reporter_recommendations[:4]
                if _text(item, max_len=140)
            ],
            "trade_report_analysis": {
                "closed_trade_count": _safe_int(reporter_trade_report_analysis.get("closed_trade_count")),
                "win_count": _safe_int(reporter_trade_report_analysis.get("win_count")),
                "loss_count": _safe_int(reporter_trade_report_analysis.get("loss_count")),
                "same_price_cost_loss_count": _safe_int(reporter_trade_report_analysis.get("same_price_cost_loss_count")),
                "broker_truth_count": _safe_int(reporter_trade_report_analysis.get("broker_truth_count")),
                "avg_pnl_pct": _safe_float(reporter_trade_report_analysis.get("avg_pnl_pct")),
            },
        },
        "read_model_facts": {
            "present": read_model_present,
            "recent_trade_count": read_model_recent_trade_count,
            "symbol_pattern_count": read_model_symbol_pattern_count,
            "symbols": read_model_symbols[:5],
            "daily_summary_present": read_model_daily_summary_present,
            "recent_strategy_feedback_present": bool(recent_feedback_visibility.get("present")),
            "recent_strategy_feedback_window": _safe_int(recent_feedback_visibility.get("feedback_window_size")),
        },
        "prompt_proven": {
            "status": {
                "strategy_memory_present": prompt_strategy_present,
                "memory_packets_present": bool(prompt_memory_packets) or bool(packets_visibility),
                "commander_memory_policy_present": bool(prompt_commander_memory_policy) or bool(policy_visibility.get("present")),
                "selected_symbol_memory_present": prompt_selected_present,
                "reporter_feedback_present": prompt_reporter_present,
                "reporter_feedback_available": prompt_reporter_available,
                "reporter_feedback_consumed": prompt_reporter_consumed,
                "read_model_facts_present": prompt_read_model_present,
            },
            "strategy_memory": {
                "present": prompt_strategy_present,
                "status": prompt_strategy_status,
                "requested_day": prompt_strategy_requested_day,
                "resolved_day": prompt_strategy_resolved_day,
                "best_playbooks": prompt_best_playbooks[:3],
                "worst_playbooks": prompt_worst_playbooks[:3],
                "recent_failures": prompt_recent_failures[:3],
                "recent_success_patterns": prompt_recent_success_patterns[:3],
            },
            "memory_packets": {
                "daily": {
                    "status": _text(prompt_daily_packet.get("status") or _dict(packets_visibility.get("daily")).get("status"), max_len=24),
                    "active": bool(prompt_daily_packet.get("active") if prompt_daily_packet else _dict(packets_visibility.get("daily")).get("active")),
                    "resolved_day": _text(prompt_daily_packet.get("resolved_day") or _dict(packets_visibility.get("daily")).get("resolved_day"), max_len=16),
                    "best_playbook_count": len(_list(prompt_daily_packet.get("best_playbooks"))),
                },
                "weekly": {
                    "status": _text(prompt_weekly_packet.get("status") or _dict(packets_visibility.get("weekly")).get("status"), max_len=24),
                    "active": bool(prompt_weekly_packet.get("active") if prompt_weekly_packet else _dict(packets_visibility.get("weekly")).get("active")),
                    "resolved_day": _text(prompt_weekly_packet.get("resolved_day") or _dict(packets_visibility.get("weekly")).get("resolved_day"), max_len=16),
                    "sample_day_count": _safe_int(prompt_weekly_packet.get("sample_day_count") if prompt_weekly_packet else _dict(packets_visibility.get("weekly")).get("sample_day_count")),
                },
                "monthly": {
                    "status": _text(prompt_monthly_packet.get("status") or _dict(packets_visibility.get("monthly")).get("status"), max_len=24),
                    "active": bool(prompt_monthly_packet.get("active") if prompt_monthly_packet else _dict(packets_visibility.get("monthly")).get("active")),
                    "resolved_day": _text(prompt_monthly_packet.get("resolved_day") or _dict(packets_visibility.get("monthly")).get("resolved_day"), max_len=16),
                    "sample_day_count": _safe_int(prompt_monthly_packet.get("sample_day_count") if prompt_monthly_packet else _dict(packets_visibility.get("monthly")).get("sample_day_count")),
                },
                "symbol": {
                    "status": _text(prompt_symbol_packet.get("status") or _dict(packets_visibility.get("symbol")).get("status"), max_len=24),
                    "active": bool(prompt_symbol_packet.get("active") if prompt_symbol_packet else _dict(packets_visibility.get("symbol")).get("active")),
                    "symbol": _text(prompt_symbol_packet.get("symbol") or _dict(packets_visibility.get("symbol")).get("symbol"), max_len=24),
                    "trade_count": _safe_int(prompt_symbol_packet.get("trade_count") if prompt_symbol_packet else _dict(packets_visibility.get("symbol")).get("trade_count")),
                },
            },
            "commander_memory_policy": {
                "present": bool(prompt_commander_memory_policy) or bool(policy_visibility.get("present")),
                "application_mode": _text(
                    prompt_commander_memory_policy.get("application_mode") or policy_visibility.get("application_mode"),
                    max_len=24,
                ),
                "active_layers": prompt_active_layers[:4],
                "priority_order": prompt_priority_order[:4],
                "symbol_memory_override_enabled": bool(
                    prompt_commander_memory_policy.get("symbol_memory_override_enabled")
                    if prompt_commander_memory_policy
                    else policy_visibility.get("symbol_memory_override_enabled")
                ),
                "scanner_bias_enabled": bool(
                    prompt_commander_memory_policy.get("scanner_bias_enabled")
                    if prompt_commander_memory_policy
                    else policy_visibility.get("scanner_bias_enabled")
                ),
                "monitor_bias_enabled": bool(
                    prompt_commander_memory_policy.get("monitor_bias_enabled")
                    if prompt_commander_memory_policy
                    else policy_visibility.get("monitor_bias_enabled")
                ),
            },
            "selected_symbol_memory": {
                "present": prompt_selected_present,
                "symbol": prompt_symbol,
                "trade_count": prompt_selected_trade_count,
                "win_rate": prompt_selected_win_rate,
                "dominant_playbook": prompt_selected_playbook,
                "dominant_monitor_blocker": prompt_selected_blocker,
            },
            "reporter_feedback_packet": {
                "present": prompt_reporter_present,
                "available": prompt_reporter_available,
                "consumed": prompt_reporter_consumed,
                "status": prompt_reporter_status,
                "feedback_gate_reason": prompt_reporter_gate_reason,
                "confidence": prompt_reporter_confidence,
                "source_reports": {
                    "metrics": bool(prompt_reporter_source_reports.get("metrics")),
                    "trade_explain": bool(prompt_reporter_source_reports.get("trade_explain")),
                    "reporter_analysis": bool(prompt_reporter_source_reports.get("reporter_analysis")),
                    "trade_reports": bool(prompt_reporter_source_reports.get("trade_reports")),
                    "current_payload": bool(prompt_reporter_source_reports.get("current_payload")),
                },
                "insight_summary": prompt_reporter_insight_summary,
                "dominant_patterns": [
                    {
                        "name": _text(_dict(item).get("name"), max_len=40),
                        "detail": _text(_dict(item).get("detail"), max_len=120),
                        "value": _safe_float(_dict(item).get("value")),
                    }
                    for item in prompt_reporter_dominant_patterns[:4]
                    if isinstance(item, dict)
                ],
                "recommendation": [
                    _text(item, max_len=140)
                    for item in prompt_reporter_recommendations[:4]
                    if _text(item, max_len=140)
                ],
                "trade_report_analysis": {
                    "closed_trade_count": _safe_int(prompt_reporter_trade_report_analysis.get("closed_trade_count")),
                    "win_count": _safe_int(prompt_reporter_trade_report_analysis.get("win_count")),
                    "loss_count": _safe_int(prompt_reporter_trade_report_analysis.get("loss_count")),
                    "same_price_cost_loss_count": _safe_int(prompt_reporter_trade_report_analysis.get("same_price_cost_loss_count")),
                    "broker_truth_count": _safe_int(prompt_reporter_trade_report_analysis.get("broker_truth_count")),
                    "avg_pnl_pct": _safe_float(prompt_reporter_trade_report_analysis.get("avg_pnl_pct")),
                },
            },
            "read_model_facts": {
                "present": prompt_read_model_present,
                "recent_trade_count": prompt_read_model_recent_trade_count,
                "symbol_pattern_count": prompt_read_model_symbol_pattern_count,
                "symbols": prompt_read_model_symbols[:5],
                "daily_summary_present": prompt_read_model_daily_summary_present,
                "recent_strategy_feedback_present": bool(recent_feedback_visibility.get("present")),
                "recent_strategy_feedback_window": _safe_int(recent_feedback_visibility.get("feedback_window_size")),
            },
        },
        "reconstructed_trade_context": {
            "status": {
                "selected_symbol_memory_rebuilt": selected_symbol_memory_rebuilt,
                "reporter_feedback_rebuilt": reporter_feedback_rebuilt,
                "memory_packets_rebuilt": memory_packets_rebuilt,
                "commander_memory_policy_rebuilt": commander_memory_policy_rebuilt,
            },
            "selected_symbol_memory": {
                "present": selected_present,
                "rebuilt": selected_symbol_memory_rebuilt,
                "source": "persisted_symbol_read_model" if selected_symbol_memory_rebuilt else "prompt_proven",
                "symbol": symbol,
                "trade_count": selected_trade_count,
                "win_rate": selected_win_rate,
                "dominant_playbook": selected_playbook,
                "dominant_monitor_blocker": selected_blocker,
            },
            "reporter_feedback_packet": {
                "present": reporter_present,
                "available": reporter_available,
                "consumed": reporter_consumed,
                "rebuilt": reporter_feedback_rebuilt,
                "source": "same_day_trade_reports_fallback" if reporter_feedback_rebuilt else "prompt_proven",
                "status": reporter_status,
                "confidence": reporter_confidence,
                "feedback_gate_reason": reporter_gate_reason,
                "source_reports": {
                    "metrics": bool(reporter_source_reports.get("metrics")),
                    "trade_explain": bool(reporter_source_reports.get("trade_explain")),
                    "reporter_analysis": bool(reporter_source_reports.get("reporter_analysis")),
                    "trade_reports": bool(reporter_source_reports.get("trade_reports")),
                    "current_payload": bool(reporter_source_reports.get("current_payload")),
                },
                "trade_report_analysis": {
                    "closed_trade_count": _safe_int(reporter_trade_report_analysis.get("closed_trade_count")),
                    "win_count": _safe_int(reporter_trade_report_analysis.get("win_count")),
                    "loss_count": _safe_int(reporter_trade_report_analysis.get("loss_count")),
                    "same_price_cost_loss_count": _safe_int(reporter_trade_report_analysis.get("same_price_cost_loss_count")),
                    "broker_truth_count": _safe_int(reporter_trade_report_analysis.get("broker_truth_count")),
                    "avg_pnl_pct": _safe_float(reporter_trade_report_analysis.get("avg_pnl_pct")),
                },
            },
            "memory_packets": {
                "rebuilt": memory_packets_rebuilt,
                "source": "runtime_loader" if memory_packets_rebuilt else "prompt_proven",
            },
            "commander_memory_policy": {
                "rebuilt": commander_memory_policy_rebuilt,
                "source": "runtime_policy" if commander_memory_policy_rebuilt else "prompt_proven",
                "active_layers": active_layers[:4],
                "priority_order": priority_order[:4],
            },
            "notes": reconstructed_notes[:6],
        },
        "usage_trace": {
            "playbook": playbook,
            "monitor_guidance": monitor_guidance,
            "scanner_bias": scanner_bias,
            "notes": usage_notes[:10],
        },
    }


__all__ = ["build_trade_report_memory_surface"]
