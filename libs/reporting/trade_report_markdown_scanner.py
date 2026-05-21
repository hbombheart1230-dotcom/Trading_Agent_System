from __future__ import annotations

import re
from typing import Any, Callable, Dict, List


def is_scanner_execution_mismatch_line(
    value: Any,
    *,
    metadata_value: Callable[[Any], str],
) -> bool:
    text = metadata_value(value)
    if not text:
        return False
    lowered = text.lower()
    has_mismatch = "불일치" in text or "mismatch" in lowered or "divergence" in lowered
    has_scanner = "스캐너" in text or "scanner" in lowered
    has_execution = any(token in text for token in ("실행", "체결", "진입", "선택")) or any(
        token in lowered for token in ("execution", "executed", "entry", "selected")
    )
    return bool(has_mismatch and has_scanner and has_execution)


def is_scanner_selection_label_line(
    value: Any,
    *,
    metadata_value: Callable[[Any], str],
) -> bool:
    text = metadata_value(value)
    lowered = text.lower()
    return text.startswith(("스캐너 선택 종목:", "실행 종목:")) or lowered.startswith(
        ("scanner selected symbol:", "execution symbol:")
    )


def is_redundant_symbol_selection_line(
    value: Any,
    *,
    metadata_value: Callable[[Any], str],
) -> bool:
    text = metadata_value(value)
    if not text:
        return True
    lowered = text.lower()
    if text.startswith(
        (
            "상위 후보는 ",
            "스캐너 1순위 ",
            "스캐너 상위 후보 ",
            "실제 진입은 ",
            "총 ",
            "종합 점수 ",
            "주요 선정 기준은 ",
            "선정에는 ",
            "주요 점수 기여는 ",
            "전략가 플레이북 ",
            "대상: ",
            "스캐너 선정 순위:",
            "1위였던 ",
            "Actual traded symbol ",
            "Fallback entry trigger:",
            "Top-pick rejection reason:",
            "Monitor fallback selected ",
            "Selected rank:",
        )
    ):
        return True
    if "종합 점수" in text and ("신뢰도" in text or "리스크" in text):
        return True
    if "score" in lowered and "rank" in lowered:
        return True
    return False


def build_symbol_selection(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    listify: Callable[[Any], List[Any]],
    metadata_value: Callable[[Any], str],
    selection_fallback_context: Callable[[Dict[str, Any], Any], Dict[str, Any]],
    num_opt: Callable[[Any], float | None],
    translate_text: Callable[[Any], str],
    looks_corrupted: Callable[[str], bool],
    translate_reason_phrase: Callable[[str], str],
    clip: Callable[..., str],
    section_summary: Callable[[Dict[str, Any]], str],
    dedupe: Callable[[List[str]], List[str]],
) -> List[str]:
    section = as_dict(report.get("why_this_symbol_was_chosen"))
    context = as_dict(report.get("market_context_at_entry"))
    lines: List[str] = []
    trace = as_dict(section.get("scanner_selection_trace"))
    ranked = [row for row in listify(trace.get("ranked_candidates")) if as_dict(row)]
    traded_symbol = metadata_value(report.get("symbol") or section.get("symbol") or trace.get("selected_symbol"))
    section_symbol = metadata_value(section.get("symbol") or trace.get("selected_symbol"))
    fallback = selection_fallback_context(section, traded_symbol)
    reanchored_from_stale_symbol = bool(
        traded_symbol and section_symbol and traded_symbol != "-" and section_symbol != "-" and traded_symbol != section_symbol
    )
    selected_rank = section.get("selected_rank") or trace.get("selected_rank")
    universe_size = section.get("universe_size") or len(ranked) or "-"
    valid_universe = isinstance(universe_size, (int, float)) and int(universe_size) > 0
    selected_score = None
    selected_confidence = None
    selected_risk = None
    traded_row_found = False
    for row in ranked:
        item = as_dict(row)
        if metadata_value(item.get("symbol")) == traded_symbol:
            traded_row_found = True
            if reanchored_from_stale_symbol:
                selected_rank = item.get("rank") or item.get("selected_rank")
            selected_score = item.get("score_total")
            selected_confidence = item.get("confidence")
            selected_risk = item.get("risk_score")
            break
    if fallback.get("used") and not traded_row_found:
        selected_score = section.get("selected_score") or trace.get("selected_score") or as_dict(trace.get("news_scanner_contribution")).get("selected_score_total")
        selected_confidence = section.get("confidence") or trace.get("confidence")
        selected_risk = section.get("risk_score") or trace.get("risk_score")
    if reanchored_from_stale_symbol and not traded_row_found:
        selected_rank = None
    valid_rank = isinstance(selected_rank, (int, float)) and int(selected_rank) > 0

    if valid_rank and valid_universe:
        detail = f"{'차순위 재평가' if fallback.get('used') else '스캐너'} {selected_rank}위"
        if universe_size not in (None, "", "-"):
            detail += f"/{universe_size}개 후보"
        score_num = num_opt(selected_score)
        confidence_num = num_opt(selected_confidence)
        risk_num = num_opt(selected_risk)
        if score_num is not None:
            detail += f", 점수 {score_num:0.3f}"
        if confidence_num is not None:
            detail += f", 신뢰도 {confidence_num:0.3f}"
        if risk_num is not None:
            detail += f", 위험 점수 {risk_num:0.3f}"
        lines.append(f"- 실제 체결 종목 {traded_symbol}은 {detail}로 집계됐습니다.")
    elif traded_symbol and not ranked:
        lines.append(f"- 실제 체결 종목 {traded_symbol}은 확인되지만, 저장된 스캐너 비교 표는 남아 있지 않습니다.")
    elif reanchored_from_stale_symbol and traded_symbol:
        lines.append(
            f"- 실제 체결 종목은 {traded_symbol}입니다. 저장된 스캐너 비교 표는 {section_symbol} 기준으로 남아 있어 {traded_symbol}의 체결 근거로 그대로 쓰지 않습니다."
        )

    basis = translate_text(section.get("basis"))
    if basis and not looks_corrupted(basis) and valid_universe and not reanchored_from_stale_symbol:
        lines.append(f"- 이 종목은 {basis} 축에서 상대 우위를 보여 최종 체결 후보로 살아남았습니다.")

    fallback_reason = translate_reason_phrase(clip(trace.get("monitor_fallback_reason"), 200))
    if fallback.get("used") and fallback_reason and not looks_corrupted(fallback_reason):
        top_pick = fallback.get("scanner_top_pick_symbol") or metadata_value(trace.get("scanner_top_pick_symbol"))
        lines.append(
            f"- 스캐너 상위 후보 {top_pick}은 모니터 단계에서 {fallback_reason} 사유로 보류됐고, {traded_symbol}이 차순위 재평가에서 실제 진입 종목이 됐습니다."
        )

    score_drivers = as_dict(trace.get("selected_symbol_score_drivers"))
    driver_pairs: List[str] = []
    for key in ("momentum", "intraday_strength", "trend", "trading_value", "theme_boost", "sentiment"):
        value = num_opt(score_drivers.get(key))
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
    if driver_pairs and not (reanchored_from_stale_symbol and not traded_row_found):
        lines.append(f"- 점수에 직접 반영된 핵심 축은 {', '.join(driver_pairs)}였습니다.")

    summary = section_summary(section)
    if (
        summary
        and not ranked
        and not looks_corrupted(summary)
        and valid_universe
        and not is_scanner_execution_mismatch_line(summary, metadata_value=metadata_value)
        and not (reanchored_from_stale_symbol and section_symbol in summary and traded_symbol in summary)
    ):
        lines.insert(0, summary)
    for raw in listify(section.get("bullets")):
        text = translate_text(raw)
        if text and not looks_corrupted(text):
            if (
                (reanchored_from_stale_symbol and not traded_row_found)
                or text.startswith("실제 체결 종목 ")
                or text.startswith("fallback 진입 트리거는")
                or is_scanner_execution_mismatch_line(text, metadata_value=metadata_value)
                or is_scanner_selection_label_line(text, metadata_value=metadata_value)
                or (ranked and is_redundant_symbol_selection_line(text, metadata_value=metadata_value))
                or (reanchored_from_stale_symbol and section_symbol in text and traded_symbol not in text)
            ):
                continue
            lines.append(f"- {text}")
    for raw in listify(context.get("bullets")):
        text = translate_text(raw)
        if looks_corrupted(text):
            continue
        if text.startswith("스캐너 연결 근거는"):
            lines.append(f"- {text}")
    if not valid_universe:
        compact: List[str] = []
        if traded_symbol and traded_symbol != "-":
            compact.append(f"- 실제 체결 종목 {traded_symbol}은 확인되지만, 저장된 스캐너 비교 표는 남아 있지 않습니다.")
        preserved_bullets: List[str] = []
        for raw in listify(section.get("bullets")):
            text = translate_text(raw)
            if not text or looks_corrupted(text):
                continue
            if any(token in text for token in ["스캐너 순위", "동률 해소 기준", "진입 이유는"]):
                preserved_bullets.append(f"- {text}")
        for raw in listify(context.get("bullets")):
            text = translate_text(raw)
            if text and not looks_corrupted(text) and text.startswith("스캐너 연결 근거는"):
                compact.append(f"- {text}")
                break
        compact.extend(dedupe(preserved_bullets[:3]))
        compact.append("- 이번 거래는 체결 사실은 확인되지만, 저장된 스캐너 순위·점수 표는 부족해 정밀 비교 설명은 생략합니다.")
        return dedupe(compact)
    return dedupe(lines)


def build_scanner_comparison(
    report: Dict[str, Any],
    *,
    as_dict: Callable[[Any], Dict[str, Any]],
    listify: Callable[[Any], List[Any]],
    metadata_value: Callable[[Any], str],
    section_summary: Callable[[Dict[str, Any]], str],
    looks_corrupted: Callable[[str], bool],
    num_opt: Callable[[Any], float | None],
    clip: Callable[..., str],
    translate_text: Callable[[Any], str],
    translate_reason_phrase: Callable[[str], str],
    dedupe: Callable[[List[str]], List[str]],
) -> List[str]:
    section = as_dict(report.get("scanner_filters"))
    why = as_dict(report.get("why_this_symbol_was_chosen"))
    lines: List[str] = []
    summary = section_summary(section)
    if summary and not looks_corrupted(summary):
        lines.append(summary)
    else:
        lines.append("상위 후보 비교와 최종 채택 경로를 저장된 범위에서 정리했습니다.")

    trace = as_dict(why.get("scanner_selection_trace"))
    ranked = [row for row in listify(trace.get("ranked_candidates")) if as_dict(row)]
    universe_size = why.get("universe_size") or len(ranked) or 0
    if ranked:
        preview: List[str] = []
        for row in ranked[:3]:
            item = as_dict(row)
            symbol = metadata_value(item.get("symbol"))
            score = num_opt(item.get("score_total"))
            if symbol and score is not None:
                preview.append(f"#{item.get('rank')} {symbol}({score:0.3f})")
        if preview:
            lines.append(f"- 저장된 비교 순위는 {', '.join(preview)}였습니다.")

        selected_symbol = metadata_value(trace.get("selected_symbol") or report.get("symbol"))
        selected_row = None
        prev_row = None
        for idx, row in enumerate(ranked):
            item = as_dict(row)
            if metadata_value(item.get("symbol")) == selected_symbol:
                selected_row = item
                if idx > 0:
                    prev_row = as_dict(ranked[idx - 1])
                break
        if selected_row and prev_row:
            prev_score = num_opt(prev_row.get("score_total"))
            selected_score = num_opt(selected_row.get("score_total"))
            if prev_score is not None and selected_score is not None:
                lines.append(
                    f"- 최종 체결 종목 {selected_symbol}은 직전 후보 {metadata_value(prev_row.get('symbol'))}보다 점수가 {prev_score - selected_score:0.3f} 낮았지만, 차순위 재평가 경로에서 채택됐습니다."
                )

    selection_reason = clip(trace.get("selection_reason"), 300)
    if int(universe_size or 0) <= 0:
        lines = [lines[0]]
        lines.append("- 저장된 스캐너 후보 표가 없어, 최종 체결 종목과 실행 결과만 확인됩니다.")
        return dedupe(lines)
    if selection_reason and not looks_corrupted(selection_reason):
        if selection_reason.startswith("Scanner top pick "):
            m = re.match(
                r"Scanner top pick\s+([A-Z0-9]+)\s+was blocked at monitor stage for\s+(.+?),\s+so runner-up re-evaluation selected\s+([A-Z0-9]+)\s+as scanner rank\s+#?(\d+)\s+with score\s+([0-9.]+)\.?",
                selection_reason,
                re.I,
            )
            if m:
                reason = translate_reason_phrase(m.group(2))
                lines.append(
                    f"- 최종 선택 경로는 원 스캐너 상위 후보 {m.group(1)}이 모니터 단계에서 {reason} 사유로 보류된 뒤, 차순위 재평가가 {m.group(3)}을 {m.group(4)}위 / 점수 {m.group(5).rstrip('.')}로 채택한 흐름이었습니다."
                )
            else:
                lines.append(f"- 최종 선택 경로는 {translate_text(selection_reason)}")
        else:
            lines.append(f"- 최종 선택 경로는 {translate_text(selection_reason)}")

    for raw in listify(section.get("bullets")):
        text = translate_text(raw)
        if text and not looks_corrupted(text):
            lines.append(f"- {text}")
    deduped = dedupe(lines)
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
    compact.extend(dedupe(key_lines[:3]))
    if len(rest) > len(key_lines[:3]):
        compact.append("- 장중 맥락의 나머지 세부 값은 저장된 시장 환경 근거에 남아 있습니다.")
    return dedupe(compact)
