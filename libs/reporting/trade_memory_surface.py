from __future__ import annotations

from typing import Any, Dict, List


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
        if text:
            items.append(text)
        if len(items) >= max(1, int(max_items)):
            break
    return ", ".join(items)


def _nested_memory_sources(story_input: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    reasoning_trace = _dict(story_input.get("reasoning_trace"))
    strategist_summary = _dict(reasoning_trace.get("strategist_summary"))
    llm_output = _dict(strategist_summary.get("llm_parsed_output"))
    strategist_evidence = _dict(story_input.get("strategist_evidence"))
    decision_frames = _list(strategist_evidence.get("decision_frames"))
    first_frame = decision_frames[0] if decision_frames and isinstance(decision_frames[0], dict) else {}
    frame_payload = _dict(_dict(first_frame).get("payload"))
    visibility = _first_dict(
        story_input.get("memory_packet_visibility"),
        strategist_summary.get("memory_packet_visibility"),
    )
    return strategist_summary, llm_output, frame_payload, visibility


def build_trade_report_memory_surface(story_input: Dict[str, Any] | None) -> Dict[str, Any]:
    source = story_input if isinstance(story_input, dict) else {}
    strategist_summary, llm_output, frame_payload, visibility = _nested_memory_sources(source)
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
    read_model_visibility = _dict(visibility.get("read_model_facts"))
    recent_feedback_visibility = _dict(visibility.get("recent_strategy_feedback"))
    strategy_visibility = _dict(visibility.get("strategy_memory"))
    selected_visibility = _dict(visibility.get("selected_symbol_memory"))
    reporter_visibility = _dict(visibility.get("reporter_feedback_packet"))

    symbol = _text(
        source.get("symbol")
        or selected_visibility.get("symbol")
        or selected_symbol_memory.get("symbol"),
        max_len=24,
    )
    playbook = _text(llm_output.get("playbook") or strategist_summary.get("playbook"), max_len=40)
    monitor_guidance = _text(llm_output.get("monitor_guidance"), max_len=40)
    scanner_bias = _text(llm_output.get("scanner_bias"), max_len=40)

    strategy_present = bool(strategy_memory) or bool(strategy_visibility.get("present"))
    selected_present = bool(selected_symbol_memory) or bool(selected_visibility.get("present"))
    reporter_present = bool(reporter_feedback) or bool(reporter_visibility.get("present"))
    read_model_present = bool(read_model_facts) or bool(read_model_visibility.get("present"))
    reporter_available = bool(reporter_feedback.get("available")) or bool(reporter_visibility.get("available"))
    reporter_consumed = bool(reporter_feedback.get("consumed")) or bool(reporter_visibility.get("consumed"))

    strategy_status = _text(
        strategy_memory.get("status") or strategy_visibility.get("status"),
        max_len=40,
    )
    strategy_requested_day = _text(strategy_visibility.get("requested_day"), max_len=16)
    strategy_resolved_day = _text(strategy_visibility.get("resolved_day"), max_len=16)
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

    usage_notes: List[str] = []
    if strategy_present:
        usage_notes.append("전략 메모리는 일·주·월 분리 패킷이 아니라 누적 집계형 strategy_memory로 전략가에 전달됐습니다.")
        if strategy_requested_day or strategy_resolved_day:
            usage_notes.append(
                f"전략 메모리 요청일/해석일은 {strategy_requested_day or '-'} / {strategy_resolved_day or '-'}였습니다."
            )
        if best_playbooks or worst_playbooks or recent_failures:
            usage_notes.append(
                "전략 메모리상 우세/취약 playbook과 최근 실패 흔적은 "
                f"{_join_text(best_playbooks, max_items=2) or '없음'} / "
                f"{_join_text(worst_playbooks, max_items=2) or '없음'} / "
                f"{_join_text(recent_failures, max_items=3, max_len=48) or '없음'}으로 전달됐습니다."
            )
    else:
        usage_notes.append("전략 메모리는 이번 리포트 입력 기준으로 비어 있었습니다.")

    if selected_present:
        selected_parts = [f"{symbol or '해당 종목'} 종목 메모리"]
        if selected_trade_count:
            selected_parts.append(f"과거 거래 {selected_trade_count}건")
        if selected_win_rate is not None:
            selected_parts.append(f"승률 {selected_win_rate * 100.0:.1f}%")
        if selected_playbook:
            selected_parts.append(f"우세 playbook {selected_playbook}")
        if selected_blocker:
            selected_parts.append(f"주요 blocker {selected_blocker}")
        usage_notes.append(", ".join(selected_parts) + "이 반영됐습니다.")
    else:
        usage_notes.append(f"{symbol or '해당 종목'} 종목 메모리는 비어 있었고, 종목별 과거 이력 제약은 직접 반영되지 않았습니다.")

    if reporter_available or reporter_consumed:
        usage_notes.append(
            f"same-day reporter feedback은 상태 {reporter_status or 'ok'} / 신뢰도 {reporter_confidence or '-'}로 전략가에 반영됐습니다."
        )
    elif reporter_present:
        usage_notes.append(
            f"same-day reporter feedback은 {reporter_status or '미사용'} 상태였고, gate 사유는 {reporter_gate_reason or '확인되지 않음'}이었습니다."
        )
    else:
        usage_notes.append("same-day reporter feedback은 이번 리포트 입력에 없었습니다.")

    if read_model_present:
        usage_notes.append(
            f"read_model_facts는 최근 거래 {read_model_recent_trade_count}건, 종목 패턴 {read_model_symbol_pattern_count}건"
            f"{' 및 일일 요약' if read_model_daily_summary_present else ''} 기준으로 들어갔습니다."
        )
    else:
        usage_notes.append("read_model_facts는 이번 리포트 입력에서 직접 확인되지 않았습니다.")

    if playbook or monitor_guidance or scanner_bias:
        usage_notes.append(
            f"전략가 출력에는 playbook={playbook or '-'}, monitor_guidance={monitor_guidance or '-'}, scanner_bias={scanner_bias or '-'}가 남아 메모리 제약이 전략 프레임에 반영됐습니다."
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
            "separate_daily_weekly_monthly_packets": False,
            "status": strategy_status,
            "requested_day": strategy_requested_day,
            "resolved_day": strategy_resolved_day,
            "best_playbooks": best_playbooks[:3],
            "worst_playbooks": worst_playbooks[:3],
            "recent_failures": recent_failures[:3],
            "recent_success_patterns": recent_success_patterns[:3],
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
        "usage_trace": {
            "playbook": playbook,
            "monitor_guidance": monitor_guidance,
            "scanner_bias": scanner_bias,
            "notes": usage_notes[:8],
        },
    }
