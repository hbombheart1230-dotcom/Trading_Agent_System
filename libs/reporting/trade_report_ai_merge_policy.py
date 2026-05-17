from __future__ import annotations

from typing import Any, Callable, Dict, List

from libs.reporting.trade_report_common import listify, report_clip


def _contains_hangul(value: Any) -> bool:
    return any("\uac00" <= ch <= "\ud7a3" for ch in str(value or ""))


def prefer_fallback_text(ai_text: Any, fallback_text: Any) -> str:
    ai_clean = report_clip(ai_text, max_len=2000)
    fallback_clean = report_clip(fallback_text, max_len=2000)
    if not ai_clean:
        return fallback_clean
    if fallback_clean and not _contains_hangul(ai_clean) and _contains_hangul(fallback_clean):
        return fallback_clean
    return ai_clean


def is_scanner_execution_mismatch_text(value: Any) -> bool:
    text = report_clip(value, max_len=2000)
    if not text:
        return False
    lowered = text.lower()
    has_mismatch = "불일치" in text or "mismatch" in lowered or "divergence" in lowered
    has_scanner = "스캐너" in text or "scanner" in lowered
    has_execution = any(token in text for token in ("실행", "체결", "진입", "선택")) or any(
        token in lowered for token in ("execution", "executed", "entry", "selected")
    )
    return bool(has_mismatch and has_scanner and has_execution)


def is_scanner_selection_label_line(value: Any) -> bool:
    text = report_clip(value, max_len=300)
    lowered = text.lower()
    return text.startswith(("스캐너 선택 종목:", "실행 종목:")) or lowered.startswith(
        ("scanner selected symbol:", "execution symbol:")
    )


def prefer_fallback_summary(section_key: str, ai_text: Any, fallback_text: Any, *, contains_hangul: Callable[[Any], bool], has_noisy_trade_report_text: Callable[[Any], bool]) -> str:
    ai_clean = report_clip(ai_text, max_len=2000)
    fallback_clean = report_clip(fallback_text, max_len=2000)
    preferred = prefer_fallback_text(ai_clean, fallback_clean)
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
            not contains_hangul(ai_clean)
            or has_noisy_trade_report_text(ai_clean)
            or "headlines were considered" in ai_lower
            or "market regime" in ai_lower
            or "neutral regime" in ai_lower
        ):
            return fallback_clean
    if token in {"scanner_filters"}:
        if "scanner and guard checks" in ai_lower or not contains_hangul(ai_clean):
            return fallback_clean
    if token in {"why_this_symbol_was_chosen", "why_this_symbol"}:
        if (
            not contains_hangul(ai_clean)
            or has_noisy_trade_report_text(ai_clean)
            or is_scanner_execution_mismatch_text(ai_clean)
            or "trading value" in ai_lower
            or "theme and sector alignment" in ai_lower
            or "highest total score" in ai_lower
            or "highest combined scanner score" in ai_lower
        ):
            return fallback_clean
    if token in {"scanner_candidate_comparison"}:
        if not contains_hangul(ai_clean) or has_noisy_trade_report_text(ai_clean):
            return fallback_clean
    if token in {"entry_decision"}:
        if (
            not contains_hangul(ai_clean)
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
            not contains_hangul(ai_clean)
            or "overtrading" in ai_lower
            or "rapid exit pressure" in ai_lower
            or "reporter linkage" in ai_lower
        ):
            return fallback_clean
    return preferred


def trade_report_priority_bullet_prefixes(section_key: str) -> List[str]:
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


def merge_bullets_with_fallback(section_key: str, ai_bullets: List[str], fallback_bullets: List[str], *, is_market_context_noise_bullet: Callable[[Any], bool]) -> List[str]:
    section_token = str(section_key or "").strip().lower()
    if section_token in {"market_context_at_entry", "market_context"}:
        ai_bullets = [row for row in ai_bullets if not is_market_context_noise_bullet(row)]
        fallback_bullets = [row for row in fallback_bullets if not is_market_context_noise_bullet(row)]
    if not ai_bullets:
        return fallback_bullets[:12]
    if not fallback_bullets:
        return ai_bullets[:12]

    merged: List[str] = []
    seen: set[str] = set()

    def _append(values: List[str]) -> None:
        for value in values:
            bullet = report_clip(value, max_len=260)
            if not bullet or bullet in seen:
                continue
            merged.append(bullet)
            seen.add(bullet)
            if len(merged) >= 12:
                break

    _append(ai_bullets)
    if len(merged) >= 12:
        return merged[:12]

    priority_prefixes = trade_report_priority_bullet_prefixes(section_key)
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
    prefixes = trade_report_priority_bullet_prefixes(section_key)
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


def merge_section_with_fallback(ai_section: Any, fallback_section: Dict[str, Any], *, section_key: str = "", contains_hangul: Callable[[Any], bool], has_noisy_trade_report_text: Callable[[Any], bool], is_low_information_bullet: Callable[[Any], bool], is_market_context_noise_bullet: Callable[[Any], bool]) -> Dict[str, Any]:
    section = ai_section if isinstance(ai_section, dict) else {}
    fallback = fallback_section if isinstance(fallback_section, dict) else {}
    merged = dict(section)
    merged["summary"] = prefer_fallback_summary(
        section_key,
        section.get("summary"),
        fallback.get("summary"),
        contains_hangul=contains_hangul,
        has_noisy_trade_report_text=has_noisy_trade_report_text,
    )
    ai_bullets = listify(section.get("bullets"), max_items=12, max_len=260)
    fallback_bullets = listify(fallback.get("bullets"), max_items=12, max_len=260)
    if section_key in {"why_this_symbol_was_chosen", "why_this_symbol"} and fallback_bullets:
        noisy_scanner_mismatch = is_scanner_execution_mismatch_text(section.get("summary")) or any(
            is_scanner_execution_mismatch_text(item) or is_scanner_selection_label_line(item)
            for item in ai_bullets
        )
        if noisy_scanner_mismatch:
            merged["summary"] = report_clip(fallback.get("summary"), max_len=2000) or merged.get("summary") or ""
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
    elif section_key in {"execution_quality", "guard_approval_result"} and any(contains_hangul(item) for item in ai_bullets):
        merged["bullets"] = ai_bullets[:12]
    elif (
        fallback_bullets
        and section_key in {"holding_monitoring_story", "monitor_trigger_reasoning", "exit_decision"}
        and sum(1 for item in ai_bullets if is_low_information_bullet(item)) >= max(3, len(ai_bullets) // 2)
    ):
        merged["bullets"] = fallback_bullets
    elif (
        fallback_bullets
        and section_key in {"market_context_at_entry", "strategist_summary", "why_this_symbol_was_chosen", "scanner_candidate_comparison"}
        and (
            sum(
                1
                for item in ai_bullets
                if is_low_information_bullet(item) or has_noisy_trade_report_text(item)
            ) >= max(1, len(ai_bullets) // 2)
            or (
                not any(contains_hangul(item) for item in ai_bullets)
                and any(contains_hangul(item) for item in fallback_bullets)
            )
        )
    ):
        if section_key in {"why_this_symbol_was_chosen", "scanner_candidate_comparison"}:
            merged["bullets"] = merge_bullets_with_fallback(
                section_key,
                ai_bullets,
                fallback_bullets,
                is_market_context_noise_bullet=is_market_context_noise_bullet,
            )
        else:
            merged["bullets"] = fallback_bullets
    elif fallback_bullets and not any(contains_hangul(item) for item in ai_bullets) and any(contains_hangul(item) for item in fallback_bullets):
        merged["bullets"] = fallback_bullets
    else:
        merged["bullets"] = merge_bullets_with_fallback(
            section_key,
            ai_bullets,
            fallback_bullets,
            is_market_context_noise_bullet=is_market_context_noise_bullet,
        )
    for key in ("headline", "action", "confidence", "status", "grade", "current_action", "symbol"):
        if not str(merged.get(key) or "").strip() and str(fallback.get(key) or "").strip():
            merged[key] = fallback.get(key)
    for key, value in fallback.items():
        if key in {"summary", "bullets"}:
            continue
        if key not in merged or merged.get(key) in (None, "", [], {}):
            merged[key] = value
    return merged
