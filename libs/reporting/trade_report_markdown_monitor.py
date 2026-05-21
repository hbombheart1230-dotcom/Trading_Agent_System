from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional


def parse_monitor_bullet(
    text: str,
    *,
    action_label: Callable[[Any], str],
    axis_label: Callable[[Any], str],
    metadata_value: Callable[[Any], str],
    translate_text: Callable[[Any], str],
) -> Optional[str]:
    if not text:
        return None
    if m := re.fullmatch(r"Monitor runs:\s*(\d+)", text, re.I):
        return f"모니터는 총 {m.group(1)}회 실행되었습니다."
    if m := re.fullmatch(r"Posture:\s*(.+)", text, re.I):
        return f"현재 포지션 판단은 {action_label(m.group(1))}입니다."
    if m := re.fullmatch(r"Effective stop:\s*([0-9.]+%)\s*\(([^)]+)\)", text, re.I):
        return f"유효 손절 기준은 {m.group(1)}입니다, 기준 축은 {axis_label(m.group(2))}입니다."
    if m := re.fullmatch(r"Effective stop:\s*([0-9.]+%)", text, re.I):
        return f"유효 손절 기준은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Take profit:\s*([0-9.]+%)", text, re.I):
        return f"목표 수익 실현 기준은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Watch axes:\s*(.+)", text, re.I):
        axes = ", ".join(axis_label(part.strip()) for part in m.group(1).split(","))
        return f"주요 감시 축은 {axes}입니다."
    if m := re.fullmatch(r"Decision chain:\s*(.+)", text, re.I):
        return f"판단 흐름은 {m.group(1)} 순서로 이어졌습니다."
    if m := re.fullmatch(r"Current price / avg / peak:\s*(.+)", text, re.I):
        return f"청산 직전 모니터 관측값(현재/평균/고점)은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Current drawdown / peak drawdown:\s*(.+)", text, re.I):
        return f"청산 직전 모니터 기준 손익 변동/고점 대비 하락폭은 {m.group(1)}입니다."
    if m := re.fullmatch(r"Exit trigger:\s*(.+)", text, re.I):
        return f"청산 트리거 상태는 {metadata_value(m.group(1))}입니다."
    return translate_text(text)


def normalize_monitor_story_line(
    text: str,
    *,
    closed_trade: bool = False,
    clip: Callable[..., str],
    parse_monitor_bullet_fn: Callable[[str], Optional[str]],
    looks_corrupted: Callable[[str], bool],
) -> Optional[str]:
    raw = clip(text, 240)
    if not raw or raw == "보유 시간은 0였습니다.":
        return None
    parsed = parse_monitor_bullet_fn(raw)
    if not parsed:
        return None
    if looks_corrupted(parsed):
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


def closed_trade_monitor_preface(
    report: Dict[str, Any],
    *,
    is_closed_trade_context: Callable[[Dict[str, Any]], bool],
    get_truth_surface: Callable[[Dict[str, Any]], Dict[str, Any]],
    as_dict: Callable[[Any], Dict[str, Any]],
    badge: Callable[[str, str], str],
    fmt_price: Callable[[Any], str],
    fmt_pct: Callable[[Any], str],
) -> List[str]:
    if not is_closed_trade_context(report):
        return []
    truth = get_truth_surface(report)
    price = as_dict(truth.get("price"))
    pnl = as_dict(truth.get("pnl"))
    monitor = as_dict(report.get("monitor_snapshot"))
    lines = [f"- {badge('모니터 관측', '#b91c1c')} 청산 직전 모니터 관측 기준입니다."]
    monitor_mark = price.get("monitor_mark_price") or monitor.get("current_price")
    broker_fill = price.get("broker_fill_price")
    if monitor_mark not in (None, "") and broker_fill not in (None, ""):
        lines.append(f"청산 직전 모니터 관측가는 {fmt_price(monitor_mark)}였고 실제 매도 체결가는 {fmt_price(broker_fill)}였습니다.")
    if pnl.get("value") not in (None, "", "unavailable") and pnl.get("pct") not in (None, ""):
        lines.append(f"실제 실현손익은 {pnl.get('value')} / {fmt_pct(pnl.get('pct'))}였습니다.")
    return lines


def build_holding_story(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    section_summary: Callable[[Dict[str, Any]], str],
    is_closed_trade_context: Callable[[Dict[str, Any]], bool],
    listify: Callable[[Any], List[Any]],
    clip: Callable[..., str],
    normalize_monitor_story_line_fn: Callable[..., Optional[str]],
    action_label: Callable[[Any], str],
    dedupe: Callable[[List[str]], List[str]],
    num_opt: Callable[[Any], float | None],
    axis_label: Callable[[Any], str],
    fmt_price: Callable[[Any], str],
    fmt_pct: Callable[[Any], str],
) -> List[str]:
    section = as_dict(report.get("holding_monitoring_story"))
    lines: List[str] = []
    summary = section_summary(section)
    monitor = as_dict(report.get("monitor_snapshot"))
    closed_trade = is_closed_trade_context(report)
    if (not closed_trade or not monitor) and summary:
        lines.append(summary)
    if not closed_trade or not monitor:
        for raw in listify(section.get("bullets")):
            text = normalize_monitor_story_line_fn(clip(raw, 240), closed_trade=closed_trade)
            if text:
                lines.append(f"- {text}")
        if monitor and monitor.get("posture") and not any("모니터 판단은" in line for line in lines):
            if closed_trade:
                lines.append(f"- 청산 직전 모니터 판단은 {action_label(monitor.get('posture'))}입니다.")
            else:
                lines.append(f"- 현재 포지션 판단은 {action_label(monitor.get('posture'))}입니다.")
        return dedupe(lines)

    age_seconds = num_opt(monitor.get("position_age_seconds"))
    active_axis = axis_label(monitor.get("active_exit_axis"))
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
        observation_parts.append(f"관측값(현재/평균/고점)은 {fmt_price(current_price)} / {fmt_price(average_price)} / {fmt_price(peak_price)}")
    if current_drawdown not in (None, "") or peak_drawdown not in (None, ""):
        observation_parts.append(f"모니터 기준 손익 변동/고점 대비 하락폭은 {fmt_pct(current_drawdown)} / {fmt_pct(peak_drawdown)}")
    if observation_parts:
        lines.append(f"- 청산 직전 {'이며, '.join(observation_parts)}였습니다.")
    return dedupe(lines)


def build_exit_decision(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    section_summary: Callable[[Dict[str, Any]], str],
    is_closed_trade_context: Callable[[Dict[str, Any]], bool],
    closed_trade_monitor_preface_fn: Callable[[Dict[str, Any]], List[str]],
    listify: Callable[[Any], List[Any]],
    clip: Callable[..., str],
    translate_text: Callable[[Any], str],
    axis_label: Callable[[Any], str],
    action_label: Callable[[Any], str],
    normalize_monitor_story_line_fn: Callable[..., Optional[str]],
    fmt_pct: Callable[[Any], str],
    dedupe: Callable[[List[str]], List[str]],
) -> List[str]:
    section = as_dict(report.get("exit_decision"))
    shared = as_dict(report.get("shared_facts"))
    monitor = as_dict(report.get("monitor_snapshot"))
    lines: List[str] = []
    summary = section_summary(section)
    closed_trade = is_closed_trade_context(report)
    if summary and (not closed_trade or not monitor):
        lines.append(summary)
    for pre in closed_trade_monitor_preface_fn(report):
        lines.append(pre)
    if not closed_trade or not monitor:
        for raw in listify(section.get("bullets")):
            raw_text = clip(raw, 240)
            text = translate_text(raw_text)
            if not text:
                continue
            if raw_text.lower().startswith("trigger type:"):
                lines.append(f"- 실제 청산 트리거는 {axis_label(raw_text.split(':', 1)[1].strip())}였습니다.")
                continue
            if raw_text.lower().startswith("exit action:"):
                lines.append(f"- 청산 액션은 {action_label(raw_text.split(':', 1)[1].strip())}입니다.")
                continue
            if raw_text.lower().startswith("exit reason:"):
                lines.append(f"- 정규화된 청산 사유는 {axis_label(raw_text.split(':', 1)[1].strip())}입니다.")
                continue
            parsed = normalize_monitor_story_line_fn(raw_text, closed_trade=clip(report.get("status"), 20).lower() == "closed")
            if not parsed:
                parsed = normalize_monitor_story_line_fn(text, closed_trade=clip(report.get("status"), 20).lower() == "closed")
            if not parsed:
                continue
            lines.append(f"- {parsed}")
    action = action_label(shared.get("action") or report.get("action"))
    if action and action != "-":
        lines.append(f"- 청산 액션은 {action}입니다.")
    exit_reason = shared.get("exit_reason") or monitor.get("trigger_type")
    if exit_reason:
        lines.append(f"- 정규화된 청산 사유는 {axis_label(exit_reason)}입니다.")
    trigger_type = monitor.get("trigger_type")
    if trigger_type:
        lines.append(f"- 실제 청산 트리거는 {axis_label(trigger_type)}이었습니다.")
    if monitor.get("effective_stop_loss_pct") not in (None, ""):
        lines.append(
            f"- 청산 시점의 유효 손절 기준은 {fmt_pct(monitor.get('effective_stop_loss_pct'))}입니다, 기준 축은 {axis_label(monitor.get('effective_stop_reason'))}입니다."
        )
    return dedupe(lines)


def build_monitor_snapshot(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    resolve_entry_execution_visibility: Callable[[Dict[str, Any]], Dict[str, Any]],
    entry_watch_execution_lines: Callable[[Dict[str, Any]], List[str]],
    axis_label: Callable[[Any], str],
    fmt_pct: Callable[[Any], str],
    listify: Callable[[Any], List[Any]],
    price_source_label: Callable[[Any], str],
    price_source_policy_label: Callable[[Any], str],
) -> List[str]:
    monitor = as_dict(report.get("monitor_snapshot"))
    if not monitor and not resolve_entry_execution_visibility(report):
        return []
    lines: List[str] = []
    for watch_line in entry_watch_execution_lines(report):
        lines.append(f"- {watch_line}")
    trigger = axis_label(monitor.get("trigger_type"))
    if trigger and trigger != "-":
        lines.append(f"- 실제 청산 트리거는 {trigger}이었습니다.")

    thresholds: List[str] = []
    if monitor.get("effective_stop_loss_pct") not in (None, ""):
        thresholds.append(f"유효 손절 {fmt_pct(monitor.get('effective_stop_loss_pct'))}")
    if monitor.get("take_profit_pct") not in (None, ""):
        thresholds.append(f"목표 수익 실현 {fmt_pct(monitor.get('take_profit_pct'))}")
    if monitor.get("trailing_stop_pct") not in (None, ""):
        thresholds.append(f"추적 손절 {fmt_pct(monitor.get('trailing_stop_pct'))}")
    if thresholds:
        lines.append(f"- 모니터가 함께 본 기준은 {', '.join(thresholds)}였습니다.")

    watch_axes = [axis_label(x) for x in listify(monitor.get("watch_axes")) if axis_label(x) not in {"", "-"}]
    if watch_axes:
        lines.append(f"- 별도 조건 축은 {', '.join(watch_axes)}이었습니다.")
    if str(monitor.get("price_source") or "").strip():
        lines.append(f"- 모니터 가격 소스는 {price_source_label(monitor.get('price_source'))}입니다.")
    if str(monitor.get("price_source_policy") or "").strip():
        lines.append(f"- 가격 소스 우선순위는 {price_source_policy_label(monitor.get('price_source_policy'))}")
    return lines


def price_source_label(
    value: Any,
    *,
    clip: Callable[..., str],
    metadata_value: Callable[[Any], str],
) -> str:
    raw = clip(value, 180)
    mapping = {
        "position.current_price": "포지션 현재가",
        "market.quote": "시장 호가",
        "selected": "선택 종목 가격",
        "market_snapshot": "시장 스냅샷",
        "position.avg_plus_unrealized": "평균가와 평가손익 기반 가격",
        "state.minute_ohlcv_by_symbol.close": "분봉 종가",
    }
    return mapping.get(raw, metadata_value(raw) or "-")


def price_source_policy_label(value: Any, *, clip: Callable[..., str]) -> str:
    raw = clip(value, 500)
    if not raw:
        return "-"
    replacements = {
        "market.quote": "시장 호가",
        "position.current_price": "포지션 현재가",
        "selected": "선택 종목 가격",
        "market_snapshot": "시장 스냅샷",
        "position.avg_plus_unrealized": "평균가와 평가손익 기반 가격",
        "effective_exit_price prefers the most conservative sane cross-check price and falls back when account-derived mark is anomalous": "청산가는 보수적인 교차검증 가격을 우선하고, 계좌 기반 가격이 비정상일 때 대체값을 사용합니다.",
    }
    out = raw
    for src, dst in replacements.items():
        out = out.replace(src, dst)
    return out
