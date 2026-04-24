from __future__ import annotations

import html
import re
from typing import Any, Dict, Iterable, List, Optional


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
    lines.extend(_section("선택된 종목 상세 분석", _build_symbol_selection(report)))
    lines.extend(_section("스캐너 후보 비교", _build_scanner_comparison(report)))
    lines.extend(_section("가드 승인 결과", _build_guard_approval(report)))
    lines.extend(_section("진입 상세 근거", _build_entry_decision(report)))
    lines.extend(_section("보유 경과", _build_holding_story(report)))
    lines.extend(_section("청산 판단 근거", _build_exit_decision(report)))
    lines.extend(_section("모니터 스냅샷", _build_monitor_snapshot(report)))
    lines.extend(_section("실행 결과", _build_execution_quality(report)))
    lines.extend(_section("결과 평가", _build_reporter_evaluation(report)))
    lines.extend(_section("보완 사안", _build_weaknesses(report)))
    lines.extend(_section("근거 출처", _build_provenance(report)))
    lines.extend(_section("전체 타임라인", _build_timeline(report)))
    lines.extend(_section("최종 운영 판단", _build_final_conclusion(report)))

    return "\n".join(_strip_trailing_blanks(lines)).strip() + "\n"


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
        "adaptive_stop": "상황 적응형 손절 기준",
        "take_profit": "목표 수익 실현 기준",
        "trailing_stop": "추적 손절 기준",
        "vwap_breakdown": "VWAP 이탈",
        "peak_drawdown": "고점 대비 하락폭 기준",
        "prior_low_break": "직전 저점 이탈",
        "intraday_low_break": "장중 저점 이탈 기준",
        "below_vwap_reclaim_not_ready": "VWAP 재회복 미완료",
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
    replaced = replaced.replace("VWAP breakdown", "VWAP 이탈")
    replaced = replaced.replace("Peak Drawdown", "고점 대비 하락폭 기준")
    replaced = replaced.replace("peak_drawdown", "고점 대비 하락폭 기준")
    replaced = replaced.replace("hard_stop", "고정 손절 기준")
    replaced = replaced.replace("intraday low break", "장중 저점 이탈 기준")
    replaced = replaced.replace("intraday_low_break", "장중 저점 이탈 기준")
    replaced = replaced.replace("below_vwap_reclaim_not_ready", "VWAP 재회복 미완료")
    if m := re.fullmatch(
        r"News input:\s*(\d+)\s+headlines were considered across\s*(\d+)\s+targets\s*\((\d+)\s+market\s*/\s*(\d+)\s+candidate signals\)\.?",
        raw,
        re.I,
    ):
        return f"뉴스 입력은 {m.group(1)}건 헤드라인, 조회 대상 {m.group(2)}개 ({m.group(3)} 시장 / {m.group(4)} 후보 신호)를 반영했습니다."
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
    truth = _as_dict(report.get("truth_surface"))
    if truth:
        return truth
    shared = _as_dict(report.get("shared_facts"))
    return {
        "status": {},
        "price": {
            "broker_buy_price": shared.get("broker_buy_price"),
            "broker_fill_price": shared.get("broker_fill_price"),
            "account_mark_price": shared.get("account_mark_price"),
            "monitor_mark_price": shared.get("monitor_mark_price"),
            "price_truth_source": shared.get("price_truth_source"),
            "monitor_price_source": shared.get("monitor_price_source"),
        },
        "pnl": {
            "value": shared.get("pnl"),
            "pct": shared.get("pnl_pct"),
            "broker_fee": shared.get("broker_fee"),
            "broker_tax": shared.get("broker_tax"),
            "pnl_truth_source": shared.get("pnl_truth_source"),
            "broker_day_truth_source": shared.get("broker_day_truth_source"),
            "broker_day_match_mode": shared.get("broker_day_match_mode"),
            "broker_day_authoritative": shared.get("broker_day_authoritative"),
        },
        "availability": {
            "broker_fill_present": shared.get("broker_fill_price") not in (None, ""),
            "broker_buy_present": shared.get("broker_buy_price") not in (None, ""),
            "account_mark_present": shared.get("account_mark_price") not in (None, ""),
            "monitor_mark_present": shared.get("monitor_mark_price") not in (None, ""),
            "broker_pnl_present": shared.get("pnl") not in (None, "", "unavailable"),
        },
    }


def _truth_source_label(value: Any) -> str:
    lowered = _clip(value, 80).lower()
    return {
        "broker_fill": "브로커 체결가 기준",
        "monitor_mark": "모니터 관측값 기준",
        "account_mark": "계좌 기준 마크 가격",
        "kiwoom.ka10077": "키움 당일 실현손익 기준(ka10077)",
        "broker_fill_account_snapshot_estimate": "브로커 체결가와 계좌 평가손익 역산 기준",
    }.get(lowered, _metadata_value(value) or "-")


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

    lines.append(f"- {_badge('확정값', '#2563eb')} 이 섹션은 브로커 체결과 당일 손익 기준을 우선 읽습니다.")

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
        lines.append(f"- raw 값 부록: broker_day_match_mode={broker_day_match_mode}")

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


def _playbook_label(value: Any) -> str:
    raw = _clip(value, 80).lower()
    mapping = {
        "defensive": "방어형",
        "breakout": "돌파형",
        "pullback": "눌림목형",
        "reclaim": "재회복형",
        "leader": "주도주형",
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
        "commander_monitor_status:stable": "모니터 상태는 안정적이었습니다",
        "commander_focus:exit_quality": "지휘관은 청산 품질 점검을 우선했습니다",
        "commander_focus:guard_blocks": "지휘관은 가드 차단 패턴 점검을 우선했습니다",
        "commander_focus:scanner_fit": "지휘관은 스캐너 적합도 점검을 우선했습니다",
    }
    if lower in mapping:
        return mapping[lower]
    if lower.startswith("daily_best:"):
        return f"당일 메모리는 {_playbook_label(lower.split(':', 1)[1])} 전략 프레임을 우세 신호로 봤습니다"
    if lower.startswith("daily_failure:playbook:"):
        return f"당일 메모리에는 {_playbook_label(lower.split(':', 2)[2])} 전략 프레임 실패 흔적이 남았습니다"
    if lower.startswith("commander_risk_posture:"):
        return f"지휘관 위험 자세는 {_playbook_label(lower.split(':', 1)[1])}이었습니다"
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
    usage_trace = _as_dict(memory.get("usage_trace"))
    lines: List[str] = []

    lines.append(f"- {_badge('입력', '#0f766e')} 아래 항목은 전략가 프롬프트에서 직접 확인된 메모리입니다.")

    lines.append(
        "- 전략가 프롬프트에서는 전략 메모리 {strategy}, 당일 리포터 피드백 {reporter}, 읽기 모델 요약 {read_model}, 종목 메모리 {symbol}이 직접 확인됐습니다.".format(
            strategy="확인" if status.get("strategy_memory_present") else "미확인",
            reporter="확인" if status.get("reporter_feedback_present") else "미확인",
            read_model="확인" if status.get("read_model_facts_present") else "미확인",
            symbol="확인" if status.get("selected_symbol_memory_present") else "미확인",
        )
    )

    if status.get("commander_memory_policy_present") and policy:
        lines.append(
            f"- 지휘관은 실제 반영 레이어를 {_memory_layers_text(policy.get('active_layers'))}으로 두고, 우선순위는 {_memory_layers_text(policy.get('priority_order'), arrow=True)}으로 정해 전략가에 직접 넘겼습니다."
        )

    if status.get("strategy_memory_present") and strategy:
        requested = _metadata_value(strategy.get("requested_day") or "")
        resolved = _metadata_value(strategy.get("resolved_day") or "")
        if requested and resolved:
            lines.append(f"- 전략 메모리는 {_memory_status_label(strategy.get('status') or '-')} 상태로 들어갔고, 기준일은 {requested} -> {resolved}로 정리됐습니다.")
        else:
            lines.append(f"- 전략 메모리는 {_memory_status_label(strategy.get('status') or '-')} 상태로 전략가 프롬프트에 직접 들어갔습니다.")
        best = _memory_layers_text(strategy.get("best_playbooks"))
        worst = _memory_layers_text(strategy.get("worst_playbooks"))
        failures = _memory_layers_text(strategy.get("recent_failures"))
        if best != "-" or worst != "-" or failures != "-":
            lines.append(
                f"- 전략 메모리 핵심 신호는 우세 전략 프레임은 {_playbook_label(best)}이었고, 취약 전략 프레임도 {_playbook_label(worst)}이었으며, 최근 실패 흔적은 {_failure_label(failures)}였습니다."
            )
            lines.append(f"- raw 값 부록: best_playbooks={best}, worst_playbooks={worst}, recent_failures={failures}")

    if status.get("memory_packets_present") and packets:
        packet_line = ", ".join(
            [
                _memory_packet_state_line("daily", _as_dict(packets.get("daily"))),
                _memory_packet_state_line("weekly", _as_dict(packets.get("weekly"))),
                _memory_packet_state_line("monthly", _as_dict(packets.get("monthly"))),
                _memory_packet_state_line("symbol", _as_dict(packets.get("symbol"))),
            ]
        )
        lines.append(f"- 프롬프트에 직접 남은 메모리 묶음 상태는 {packet_line}입니다.")

    prompt_symbol = _metadata_value(selected.get("symbol") or report.get("symbol") or "-")
    if status.get("selected_symbol_memory_present"):
        trade_count = selected.get("trade_count") if selected.get("trade_count") not in (None, "") else "-"
        win_rate = selected.get("win_rate")
        win_rate_text = _fmt_pct(win_rate) if win_rate not in (None, "") else "-"
        dominant_playbook = _metadata_value(selected.get("dominant_playbook") or "-")
        lines.append(
            f"- 전략가 프롬프트는 {prompt_symbol} 종목 메모리를 직접 포함했고, 과거 거래 {trade_count}건, 승률 {win_rate_text}, 우세 전략 프레임은 {_playbook_label(dominant_playbook)}이었습니다."
        )
    else:
        lines.append("- 이번 거래 종목에 대한 메모리 세부 내용은 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if status.get("reporter_feedback_present"):
        source_label = _humanize_reporter_source_label(_as_dict(reporter.get("source_reports")))
        reporter_status = _memory_status_label(reporter.get("status") or ("ok" if reporter.get("available") else "-"))
        if source_label == "기록되지 않은 소스":
            lines.append(
                f"- 전략가 프롬프트에서 직접 확인된 당일 리포터 피드백은 상태는 {reporter_status}, 신뢰도는 {_metadata_value(reporter.get('confidence') or '-')} 수준이었으며, 소스는 별도로 남지 않았습니다."
            )
        else:
            lines.append(
                f"- 전략가 프롬프트에서 직접 확인된 당일 리포터 피드백은 상태는 {reporter_status}, 신뢰도는 {_metadata_value(reporter.get('confidence') or '-')} 수준이었고, 소스는 {source_label}였습니다."
            )
        analysis = _as_dict(reporter.get("trade_report_analysis"))
        if analysis:
            lines.append(
                f"- 프롬프트에 직접 남은 리포터 요약은 닫힌 거래 {analysis.get('closed_trade_count') if analysis.get('closed_trade_count') not in (None, '') else '-'}건, "
                f"승패 {analysis.get('win_count') if analysis.get('win_count') not in (None, '') else '-'}"
                f"/{analysis.get('loss_count') if analysis.get('loss_count') not in (None, '') else '-'}, 평균 손익률 {_fmt_pct(analysis.get('avg_pnl_pct'))}였습니다."
            )
    else:
        lines.append("- 당일 리포터 피드백은 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if status.get("read_model_facts_present"):
        lines.append(
            f"- 읽기 모델 요약은 최근 거래 {read_model.get('recent_trade_count') or 0}건, 종목 패턴 {read_model.get('symbol_pattern_count') or 0}건, 일간 요약 {'있음' if read_model.get('daily_summary_present') else '없음'} 상태로 전략가 프롬프트에 들어갔습니다."
        )
    else:
        lines.append("- 읽기 모델 요약은 이번 거래에 대한 전략가 프롬프트에서 직접 확인되지 않았습니다.")

    if usage_trace:
        lines.append(
            f"- 전략가는 최종적으로 {_playbook_label(usage_trace.get('playbook') or '-')} 전략 프레임을 유지했고, "
            f"청산 쪽에는 {_monitor_guidance_label(usage_trace.get('monitor_guidance') or '-')}를 남겼으며, "
            f"탐색 쪽에는 {_scanner_bias_label(usage_trace.get('scanner_bias') or '-')} 흐름을 유지했습니다."
        )
        lines.append(
            f"- raw 값 부록: playbook={_metadata_value(usage_trace.get('playbook') or '-')}, monitor_guidance={_metadata_value(usage_trace.get('monitor_guidance') or '-')}, scanner_bias={_metadata_value(usage_trace.get('scanner_bias') or '-')}"
        )
    return lines

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

    lines.append(f"- {_badge('사후 복원', '#7c3aed')} 아래 항목은 거래 설명을 위해 실행 기록에서 다시 읽은 메모리입니다.")

    if any(bool(status.get(key)) for key in status):
        lines.append(f"- 이 섹션은 전략가 원본 프롬프트 밖의 거래 레벨 메모리를 다시 읽어, {symbol} 거래를 직접 설명할 수 있게 했습니다.")
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
        lines.append("- 이 섹션은 전략가 원본 프롬프트를 그대로 옮긴 것이 아니라, 거래 설명을 위해 사후 복원한 메모리 레이어입니다.")
    return lines

def _build_memory_application(report: Dict[str, Any]) -> List[str]:
    memory_app = _as_dict(report.get("memory_application_surface"))
    if not memory_app:
        return []
    scanner = _as_dict(memory_app.get("scanner_memory_bias"))
    monitor = _as_dict(memory_app.get("monitor_memory_bias"))
    lines: List[str] = []

    lines.append(f"- {_badge('적용 결과', '#b45309')} 아래 항목은 실제 scanner/monitor 수치 조정 결과입니다.")

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
            lines.append(f"- raw tag 부록: {reason}")
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
            lines.append(f"- raw tag 부록: {reason}")
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
    market_titles = _sample_news_titles(context.get("market_news_titles"))
    candidate_titles = _sample_news_titles(context.get("candidate_news_titles"))
    linkage = _as_dict(context.get("news_symbol_linkage"))
    linkage_strength = _news_linkage_strength_label(linkage.get("linkage_strength"))
    selected_vs_runner = _as_dict(linkage.get("selected_vs_runner_up"))
    selected_symbol = _metadata_value(
        selected_vs_runner.get("selected_symbol") or linkage.get("selected_symbol") or report.get("symbol")
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


def _build_symbol_selection(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("why_this_symbol_was_chosen"))
    context = _as_dict(report.get("market_context_at_entry"))
    lines: List[str] = []
    trace = _as_dict(section.get("scanner_selection_trace"))
    ranked = [row for row in _listify(trace.get("ranked_candidates")) if _as_dict(row)]
    traded_symbol = _metadata_value(report.get("symbol") or section.get("symbol") or trace.get("selected_symbol"))
    selected_rank = section.get("selected_rank") or trace.get("selected_rank")
    universe_size = section.get("universe_size") or len(ranked) or "-"
    valid_rank = isinstance(selected_rank, (int, float)) and int(selected_rank) > 0
    valid_universe = isinstance(universe_size, (int, float)) and int(universe_size) > 0
    selected_score = None
    selected_confidence = None
    selected_risk = None
    for row in ranked:
        item = _as_dict(row)
        if _metadata_value(item.get("symbol")) == traded_symbol:
            selected_score = item.get("score_total")
            selected_confidence = item.get("confidence")
            selected_risk = item.get("risk_score")
            break

    if valid_rank and valid_universe:
        detail = f"스캐너 {selected_rank}위"
        if universe_size not in (None, "", "-"):
            detail += f"/{universe_size}개 후보"
        if selected_score not in (None, ""):
            detail += f", 점수 {float(selected_score):0.3f}"
        if selected_confidence not in (None, ""):
            detail += f", 신뢰도 {float(selected_confidence):0.3f}"
        if selected_risk not in (None, ""):
            detail += f", 위험 점수 {float(selected_risk):0.3f}"
        lines.append(f"- 실제 체결 종목 {traded_symbol}은 {detail}로 집계됐습니다.")
    elif traded_symbol and not ranked:
        lines.append(f"- 실제 체결 종목 {traded_symbol}은 확인되지만, 저장된 스캐너 비교 표는 남아 있지 않습니다.")

    basis = _translate_text(section.get("basis"))
    if basis and not _looks_corrupted(basis) and valid_universe:
        lines.append(f"- 이 종목은 {basis} 축에서 상대 우위를 보여 최종 체결 후보로 살아남았습니다.")

    fallback_reason = _translate_reason_phrase(_clip(trace.get("monitor_fallback_reason"), 200))
    if trace.get("monitor_fallback_used") and fallback_reason and not _looks_corrupted(fallback_reason):
        top_pick = _metadata_value(trace.get("scanner_top_pick_symbol"))
        lines.append(
            f"- 스캐너 상위 후보 {top_pick}은 모니터 단계에서 {fallback_reason} 사유로 막힌 뒤, {traded_symbol}이 차순위 재평가에서 실제 진입 종목이 됐습니다."
        )

    score_drivers = _as_dict(trace.get("selected_symbol_score_drivers"))
    driver_pairs: List[str] = []
    for key in ("momentum", "intraday_strength", "trend", "trading_value", "theme_boost", "sentiment"):
        value = _num_opt(score_drivers.get(key))
        if value is None or value == 0:
            continue
        label = {
            "momentum": "모멘텀",
            "intraday_strength": "장중 강도",
            "trend": "추세",
            "trading_value": "거래대금",
            "theme_boost": "테마 정렬",
            "sentiment": "심리 보정",
        }.get(key, key)
        driver_pairs.append(f"{label} {value:+0.3f}")
    if driver_pairs:
        lines.append(f"- 점수에 직접 반영된 핵심 축은 {', '.join(driver_pairs)}였습니다.")

    summary = _section_summary(section)
    if summary and not _looks_corrupted(summary) and valid_universe:
        lines.insert(0, summary)
    for raw in _listify(section.get("bullets")):
        text = _translate_text(raw)
        if text and not _looks_corrupted(text):
            if text.startswith("실제 체결 종목 ") or text.startswith("fallback 진입 트리거는"):
                continue
            lines.append(f"- {text}")
    for raw in _listify(context.get("bullets")):
        text = _translate_text(raw)
        if _looks_corrupted(text):
            continue
        if text.startswith("스캐너 연결 근거는"):
            lines.append(f"- {text}")
    if not valid_universe:
        compact: List[str] = []
        if traded_symbol and traded_symbol != "-":
            compact.append(f"- 실제 체결 종목 {traded_symbol}은 확인되지만, 저장된 스캐너 비교 표는 남아 있지 않습니다.")
        preserved_bullets: List[str] = []
        for raw in _listify(section.get("bullets")):
            text = _translate_text(raw)
            if not text or _looks_corrupted(text):
                continue
            if any(token in text for token in ["스캐너 순위", "동률 해소 기준", "진입 이유는"]):
                preserved_bullets.append(f"- {text}")
        for raw in _listify(context.get("bullets")):
            text = _translate_text(raw)
            if text and not _looks_corrupted(text) and text.startswith("스캐너 연결 근거는"):
                compact.append(f"- {text}")
                break
        compact.extend(_dedupe(preserved_bullets[:3]))
        compact.append("- 이번 거래는 체결 사실은 확인되지만, 저장된 스캐너 순위·점수 표는 부족해 정밀 비교 설명은 생략합니다.")
        return _dedupe(compact)
    return _dedupe(lines)


def _build_scanner_comparison(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("scanner_filters"))
    why = _as_dict(report.get("why_this_symbol_was_chosen"))
    lines: List[str] = []
    summary = _section_summary(section)
    if summary and not _looks_corrupted(summary):
        lines.append(summary)
    else:
        lines.append("상위 후보 비교와 최종 채택 경로를 저장된 범위에서 정리했습니다.")

    trace = _as_dict(why.get("scanner_selection_trace"))
    ranked = [row for row in _listify(trace.get("ranked_candidates")) if _as_dict(row)]
    universe_size = why.get("universe_size") or len(ranked) or 0
    if ranked:
        preview: List[str] = []
        for row in ranked[:3]:
            item = _as_dict(row)
            symbol = _metadata_value(item.get("symbol"))
            score = _num_opt(item.get("score_total"))
            if symbol and score is not None:
                preview.append(f"#{item.get('rank')} {symbol}({score:0.3f})")
        if preview:
            lines.append(f"- 저장된 비교 순위는 {', '.join(preview)}였습니다.")

        selected_symbol = _metadata_value(trace.get("selected_symbol") or report.get("symbol"))
        selected_row = None
        prev_row = None
        for idx, row in enumerate(ranked):
            item = _as_dict(row)
            if _metadata_value(item.get("symbol")) == selected_symbol:
                selected_row = item
                if idx > 0:
                    prev_row = _as_dict(ranked[idx - 1])
                break
        if selected_row and prev_row:
            prev_score = _num_opt(prev_row.get("score_total"))
            selected_score = _num_opt(selected_row.get("score_total"))
            if prev_score is not None and selected_score is not None:
                lines.append(
                    f"- 최종 체결 종목 {selected_symbol}은 직전 후보 {_metadata_value(prev_row.get('symbol'))}보다 점수가 {prev_score - selected_score:0.3f} 낮았지만, 차순위 재평가 경로에서 채택됐습니다."
                )

    selection_reason = _clip(trace.get("selection_reason"), 300)
    if int(universe_size or 0) <= 0:
        lines = [lines[0]]
        lines.append("- 저장된 스캐너 후보 표가 없어, 최종 체결 종목과 실행 결과만 확인됩니다.")
        return _dedupe(lines)
    if selection_reason and not _looks_corrupted(selection_reason):
        if selection_reason.startswith("Scanner top pick "):
            m = re.match(
                r"Scanner top pick\s+([A-Z0-9]+)\s+was blocked at monitor stage for\s+(.+?),\s+so runner-up re-evaluation selected\s+([A-Z0-9]+)\s+as scanner rank\s+#?(\d+)\s+with score\s+([0-9.]+)\.?",
                selection_reason,
                re.I,
            )
            if m:
                reason = _translate_reason_phrase(m.group(2))
                lines.append(
                    f"- 최종 선택 경로는 스캐너 1위 종목 {m.group(1)}이 모니터 단계에서 {reason} 사유로 막힌 뒤, 차순위 재평가가 {m.group(3)}을 {m.group(4)}위 / 점수 {m.group(5).rstrip('.')}로 채택한 흐름이었습니다."
                )
            else:
                lines.append(f"- 최종 선택 경로는 {_translate_text(selection_reason)}")
        else:
            lines.append(f"- 최종 선택 경로는 {_translate_text(selection_reason)}")

    for raw in _listify(section.get("bullets")):
        text = _translate_text(raw)
        if text and not _looks_corrupted(text):
            lines.append(f"- {text}")
    deduped = _dedupe(lines)
    if len(deduped) <= 3:
        return deduped
    compact: List[str] = []
    first = deduped[0]
    compact.append(first)
    rest = deduped[1:]
    key_lines: List[str] = []
    for line in rest:
        lowered = line.lower()
        if any(token in lowered for token in ["시장 심리", "vix", "스트레스 신호", "시장 뉴스", "전략가 핵심 입력", "스캐너 연결 근거", "동률 해소 기준", "스캐너 순위"]):
            key_lines.append(line)
    if not key_lines:
        key_lines = rest[:2]
    compact.extend(_dedupe(key_lines[:3]))
    if len(rest) > len(key_lines[:3]):
        compact.append("- 장중 맥락의 나머지 세부 값은 저장된 시장 환경 근거에 남아 있습니다.")
    return _dedupe(compact)

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
    if not text:
        return None
    if m := re.fullmatch(r"Monitor runs:\s*(\d+)", text, re.I):
        return f"모니터는 총 {m.group(1)}회 실행되었습니다."
    if m := re.fullmatch(r"Posture:\s*(.+)", text, re.I):
        return f"현재 포지션 판단은 {_action_label(m.group(1))}입니다."
    if m := re.fullmatch(r"Effective stop:\s*([0-9.]+%)\s*\(([^)]+)\)", text, re.I):
        return f"유효 손절 기준은 {m.group(1)}입니다, 기준 축은 {_axis_label(m.group(2))}입니다."
    if m := re.fullmatch(r"Effective stop:\s*([0-9.]+%)", text, re.I):
        return f"유효 손절 기준은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Take profit:\s*([0-9.]+%)", text, re.I):
        return f"목표 수익 실현 기준은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Watch axes:\s*(.+)", text, re.I):
        axes = ", ".join(_axis_label(part.strip()) for part in m.group(1).split(","))
        return f"주요 감시 축은 {axes}입니다."
    if m := re.fullmatch(r"Decision chain:\s*(.+)", text, re.I):
        return f"판단 흐름은 {m.group(1)} 순서로 이어졌습니다."
    if m := re.fullmatch(r"Current price / avg / peak:\s*(.+)", text, re.I):
        return f"청산 직전 모니터 관측값(현재/평균/고점)은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Current drawdown / peak drawdown:\s*(.+)", text, re.I):
        return f"청산 직전 모니터 기준 손익 변동/고점 대비 하락폭은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Exit trigger:\s*(.+)", text, re.I):
        return f"청산 트리거 상태는 {_metadata_value(m.group(1))}입니다."
    return _translate_text(text)


def _normalize_monitor_story_line(text: str, *, closed_trade: bool = False) -> Optional[str]:
    raw = _clip(text, 240)
    if not raw or raw == "보유 시간은 0였습니다.":
        return None
    parsed = _parse_monitor_bullet(raw)
    if not parsed:
        return None
    if _looks_corrupted(parsed):
        return None
    if not closed_trade:
        return parsed
    if parsed.startswith("현재 포지션 판단은 "):
        return parsed.replace("현재 포지션 판단은 ", "청산 직전 모니터 판단은 ", 1)
    if parsed.startswith("현재가, 평균가, 고점 기준 값은 "):
        return parsed.replace("현재가, 평균가, 고점 기준 값은 ", "청산 직전 모니터 관측값(현재/평균/고점)은 ", 1)
    if parsed.startswith("현재 손익 변동과 고점 대비 하락폭은 "):
        return parsed.replace("현재 손익 변동과 고점 대비 하락폭은 ", "청산 직전 모니터 기준 손익 변동/고점 대비 하락폭은 ", 1)
    if parsed.startswith("가격 기준 소스는 "):
        return parsed.replace("가격 기준 소스는 ", "청산 직전 모니터 가격 소스는 ", 1)
    return parsed


def _closed_trade_monitor_preface(report: Dict[str, Any]) -> List[str]:
    if not _is_closed_trade_context(report):
        return []
    truth = _get_truth_surface(report)
    price = _as_dict(truth.get("price"))
    pnl = _as_dict(truth.get("pnl"))
    monitor = _as_dict(report.get("monitor_snapshot"))
    lines = [f"- {_badge('모니터 관측', '#b91c1c')} 아래 값은 청산 직전 모니터 관측 기준입니다."]
    monitor_mark = price.get("monitor_mark_price") or monitor.get("current_price")
    broker_fill = price.get("broker_fill_price")
    if monitor_mark not in (None, "") and broker_fill not in (None, ""):
        lines.append(f"청산 직전 모니터 관측가는 {_fmt_price(monitor_mark)}였고 실제 매도 체결가는 {_fmt_price(broker_fill)}였습니다.")
    if pnl.get("value") not in (None, "", "unavailable") and pnl.get("pct") not in (None, ""):
        lines.append(f"실제 실현손익은 {pnl.get('value')} / {_fmt_pct(pnl.get('pct'))}였습니다.")
    return lines


def _build_holding_story(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("holding_monitoring_story"))
    lines: List[str] = []
    summary = _section_summary(section)
    monitor = _as_dict(report.get("monitor_snapshot"))
    closed_trade = _is_closed_trade_context(report)
    if (not closed_trade or not monitor) and summary:
        lines.append(summary)
    if not closed_trade or not monitor:
        for raw in _listify(section.get("bullets")):
            text = _normalize_monitor_story_line(_clip(raw, 240), closed_trade=closed_trade)
            if text:
                lines.append(f"- {text}")
        if monitor and monitor.get("posture") and not any("모니터 판단은" in line for line in lines):
            if closed_trade:
                lines.append(f"- 청산 직전 모니터 판단은 {_action_label(monitor.get('posture'))}입니다.")
            else:
                lines.append(f"- 현재 포지션 판단은 {_action_label(monitor.get('posture'))}입니다.")
        return _dedupe(lines)

    age_seconds = _num_opt(monitor.get("position_age_seconds"))
    active_axis = _axis_label(monitor.get("active_exit_axis"))
    if age_seconds is not None and active_axis and active_axis != "-":
        lines.append(f"- 보유 시간은 약 {int(age_seconds)}초였고, 모니터의 핵심 감시 축은 {active_axis}이었습니다.")
    else:
        if age_seconds is not None:
            lines.append(f"- 보유 시간은 약 {int(age_seconds)}초였습니다.")
        if active_axis and active_axis != "-":
            lines.append(f"- 당시 우선 감시 중이던 청산 축은 {active_axis}이었습니다.")

    current_price = monitor.get("current_price")
    average_price = monitor.get("average_price")
    peak_price = monitor.get("peak_price")
    current_drawdown = monitor.get("current_drawdown")
    peak_drawdown = monitor.get("peak_drawdown")
    observation_parts = []
    if current_price not in (None, "") or average_price not in (None, "") or peak_price not in (None, ""):
        observation_parts.append(f"관측값(현재/평균/고점)은 {_fmt_price(current_price)} / {_fmt_price(average_price)} / {_fmt_price(peak_price)}")
    if current_drawdown not in (None, "") or peak_drawdown not in (None, ""):
        observation_parts.append(f"모니터 기준 손익 변동/고점 대비 하락폭은 {_fmt_pct(current_drawdown)} / {_fmt_pct(peak_drawdown)}")
    if observation_parts:
        lines.append(f"- 청산 직전 {'이며, '.join(observation_parts)}였습니다.")
    return _dedupe(lines)

def _build_exit_decision(report: Dict[str, Any]) -> List[str]:
    section = _as_dict(report.get("exit_decision"))
    shared = _as_dict(report.get("shared_facts"))
    monitor = _as_dict(report.get("monitor_snapshot"))
    lines: List[str] = []
    summary = _section_summary(section)
    closed_trade = _is_closed_trade_context(report)
    if summary and (not closed_trade or not monitor):
        lines.append(summary)
    for pre in _closed_trade_monitor_preface(report):
        lines.append(pre)
    if not closed_trade or not monitor:
        for raw in _listify(section.get("bullets")):
            raw_text = _clip(raw, 240)
            text = _translate_text(raw_text)
            if not text:
                continue
            if raw_text.lower().startswith("trigger type:"):
                lines.append(f"- 실제 청산 트리거는 {_axis_label(raw_text.split(':', 1)[1].strip())}였습니다.")
                continue
            if raw_text.lower().startswith("exit action:"):
                lines.append(f"- 청산 액션은 {_action_label(raw_text.split(':',1)[1].strip())}입니다.")
                continue
            if raw_text.lower().startswith("exit reason:"):
                lines.append(f"- 정규화된 청산 사유는 {_axis_label(raw_text.split(':',1)[1].strip())}입니다.")
                continue
            parsed = _normalize_monitor_story_line(raw_text, closed_trade=_clip(report.get("status"), 20).lower() == "closed")
            if not parsed:
                parsed = _normalize_monitor_story_line(text, closed_trade=_clip(report.get("status"), 20).lower() == "closed")
            if not parsed:
                continue
            lines.append(f"- {parsed}")
    action = _action_label(shared.get("action") or report.get("action"))
    if action and action != "-":
        lines.append(f"- 청산 액션은 {action}입니다.")
    exit_reason = shared.get("exit_reason") or monitor.get("trigger_type")
    if exit_reason:
        lines.append(f"- 정규화된 청산 사유는 {_axis_label(exit_reason)}입니다.")
    trigger_type = monitor.get("trigger_type")
    if trigger_type:
        lines.append(f"- 실제 청산 트리거는 {_axis_label(trigger_type)}이었습니다.")
    if monitor.get("effective_stop_loss_pct") not in (None, ""):
        lines.append(
            f"- 청산 시점의 유효 손절 기준은 {_fmt_pct(monitor.get('effective_stop_loss_pct'))}입니다, 기준 축은 {_axis_label(monitor.get('effective_stop_reason'))}입니다."
        )
    return _dedupe(lines)


def _build_monitor_snapshot(report: Dict[str, Any]) -> List[str]:
    monitor = _as_dict(report.get("monitor_snapshot"))
    if not monitor:
        return []
    lines: List[str] = []
    trigger = _axis_label(monitor.get("trigger_type"))
    if trigger and trigger != "-":
        lines.append(f"- 실제 청산 트리거는 {trigger}이었습니다.")

    thresholds: List[str] = []
    if monitor.get("effective_stop_loss_pct") not in (None, ""):
        thresholds.append(f"유효 손절 {_fmt_pct(monitor.get('effective_stop_loss_pct'))}")
    if monitor.get("take_profit_pct") not in (None, ""):
        thresholds.append(f"목표 수익 실현 {_fmt_pct(monitor.get('take_profit_pct'))}")
    if monitor.get("trailing_stop_pct") not in (None, ""):
        thresholds.append(f"추적 손절 {_fmt_pct(monitor.get('trailing_stop_pct'))}")
    if thresholds:
        lines.append(f"- 모니터가 함께 본 기준은 {', '.join(thresholds)}였습니다.")

    watch_axes = [_axis_label(x) for x in _listify(monitor.get("watch_axes")) if _axis_label(x) not in {"", "-"}]
    if watch_axes:
        lines.append(f"- 별도 조건 축은 {', '.join(watch_axes)}이었습니다.")
    return lines

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
        return "no-trade를 가장 많이 막은 축이 confidence gate였으니, 이 gate가 과도하게 지배적인지 다시 점검해야 합니다."
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
    if raw.endswith(("입니다.", "였습니다.", "합니다.", "됩니다.", "다.", ".")):
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
