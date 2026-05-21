from __future__ import annotations

import re
from typing import Any, Callable, Dict, Iterable, List

SYMBOL_NAME_FALLBACKS: Dict[str, str] = {
    "000660": "SK하이닉스",
    "012330": "현대모비스",
    "003060": "에이프로젠바이오로직스",
    "034220": "LG디스플레이",
    "024840": "KBI메탈",
    "005380": "현대차",
    "005930": "삼성전자",
    "005935": "삼성전자우",
    "006345": "대원전선우",
    "035420": "NAVER",
    "073490": "이노와이어리스",
    "090710": "휴림로봇",
    "102120": "어보브반도체",
    "114800": "KODEX 인버스",
    "122630": "KODEX 레버리지",
    "233740": "KODEX 코스닥150레버리지",
    "252670": "KODEX 200선물인버스2X",
    "252710": "TIGER 200선물인버스2X",
    "402340": "SK스퀘어",
}


SYMBOL_THEME_FALLBACKS: Dict[str, List[str]] = {
    "012330": ["자동차부품", "전기차", "자율주행차", "수소차"],
    "006345": ["전선", "전력설비", "구리"],
    "024840": ["전선", "구리", "전력설비"],
    "034220": ["OLED", "LCD", "디스플레이패널"],
}


def clip_text(value: Any, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def listify(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]

def append_unique_text(
    out: List[str],
    value: Any,
    *,
    max_len: int = 80,
    metadata_value: Callable[[Any], str],
    translate_text: Callable[[Any], str],
) -> None:
    text = metadata_value(translate_text(value)).strip()
    if not text:
        return
    if text == "not_captured" or text.lower() in {"none", "null", "unknown", "unavailable"}:
        return
    if re.fullmatch(r"\d{6}", text):
        return
    if text not in out:
        out.append(clip_text(text, max_len))


def append_theme_values(
    out: List[str],
    raw_theme: Any,
    *,
    metadata_value: Callable[[Any], str],
    translate_text: Callable[[Any], str],
) -> None:
    if isinstance(raw_theme, dict):
        append_unique_text(
            out,
            raw_theme.get("theme")
            or raw_theme.get("theme_name")
            or raw_theme.get("name")
            or raw_theme.get("value"),
            metadata_value=metadata_value,
            translate_text=translate_text,
        )
        return
    for item in listify(raw_theme):
        if isinstance(item, dict):
            append_unique_text(
                out,
                item.get("theme")
                or item.get("theme_name")
                or item.get("name")
                or item.get("value"),
                metadata_value=metadata_value,
                translate_text=translate_text,
            )
        else:
            append_unique_text(out, item, metadata_value=metadata_value, translate_text=translate_text)


def looks_like_symbol_name(candidate: str, symbol: str) -> bool:
    text = str(candidate or "").strip()
    if not text or text == str(symbol or "").strip() or re.fullmatch(r"\d{6}", text):
        return False
    lowered = text.lower()
    if any(
        token in lowered
        for token in (
            "runner_up",
            "runner-up",
            "score",
            "rank",
            "fallback",
            "selected",
            "candidate",
            "trigger",
            "reason",
            "highest",
            "best score",
            "total score",
            "composite score",
        )
    ):
        return False
    if any(token in text for token in ("스코어", "점수", "순위", "후보", "선택", "사유", "최고", "종합")):
        return False
    return True


def iter_trade_symbol_metadata_sources(report: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    shared = as_dict(report.get("shared_facts"))
    yield report
    yield shared
    yield as_dict(shared.get("resolved_trade_facts"))
    for key in (
        "executive_summary",
        "market_context_at_entry",
        "strategist_summary",
        "why_this_symbol_was_chosen",
        "scanner_filters",
        "entry_decision",
        "monitor_snapshot",
        "fact_payload",
    ):
        section = as_dict(report.get(key))
        if section:
            yield section
        for nested_key in (
            "selected_candidate",
            "selected_row",
            "candidate",
            "scanner_selection_trace",
            "selection_trace",
            "theme_alignment_trace",
            "theme_strength_packet",
            "selected_symbol_detail",
            "trade",
        ):
            nested = as_dict(section.get(nested_key))
            if nested:
                yield nested


def symbol_in_theme_components(symbol: str, components: Any) -> bool:
    target = str(symbol or "").strip()
    if not target:
        return False
    for item in listify(components):
        if isinstance(item, dict):
            candidate = str(
                item.get("symbol")
                or item.get("code")
                or item.get("stk_cd")
                or item.get("ticker")
                or ""
            ).strip()
        else:
            candidate = str(item or "").strip()
        if candidate == target:
            return True
    return False


def iter_nested_dicts(value: Any, *, max_depth: int = 8) -> Iterable[Dict[str, Any]]:
    if max_depth < 0:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_nested_dicts(child, max_depth=max_depth - 1)
    elif isinstance(value, list):
        for child in value:
            yield from iter_nested_dicts(child, max_depth=max_depth - 1)


def component_themes_for_symbol(
    report: Dict[str, Any],
    symbol: str,
    *,
    metadata_value: Callable[[Any], str],
    translate_text: Callable[[Any], str],
) -> List[str]:
    themes: List[str] = []
    for source in iter_nested_dicts(report):
        for map_key in ("component_symbols_by_theme", "theme_map", "symbol_theme_map"):
            component_map = as_dict(source.get(map_key))
            if not component_map:
                continue
            for raw_theme, components in component_map.items():
                if symbol_in_theme_components(symbol, components):
                    append_unique_text(
                        themes,
                        raw_theme,
                        metadata_value=metadata_value,
                        translate_text=translate_text,
                    )
    return themes


def infer_symbol_name_from_report_text(report: Dict[str, Any], symbol: str, *, metadata_value: Callable[[Any], str], translate_text: Callable[[Any], str]) -> str:
    target = str(symbol or "").strip()
    if not target:
        return ""
    text_candidates: List[tuple[str, Any]] = []
    for source in iter_trade_symbol_metadata_sources(report):
        for key in ("symbol_news_titles", "strategist_symbol_headlines", "candidate_headlines_used"):
            text_candidates.extend(("headline", item) for item in listify(source.get(key)))
        text_candidates.extend(("narrative", item) for item in listify(source.get("bullets")))
        text_candidates.append(("narrative", source.get("summary")))
    for candidate_kind, raw in text_candidates:
        text = metadata_value(translate_text(raw))
        if not text or target not in text:
            continue
        paren_match = re.search(rf"([A-Za-z가-힣0-9&._\-\s]+)\(\s*{re.escape(target)}\s*\)", text)
        if paren_match:
            name = re.sub(r"\s+", " ", paren_match.group(1)).strip(" ,;:-")
            if looks_like_symbol_name(name, target):
                return clip_text(name.split()[-1], 80)
        prefix = re.search(rf"{re.escape(target)}\s*:\s*(.+)", text)
        if not prefix:
            continue
        if candidate_kind == "headline":
            continue
        headline = str(prefix.group(1) or "").strip()
        if "…" in headline:
            headline = headline.rsplit("…", 1)[-1]
        elif "..." in headline:
            headline = headline.rsplit("...", 1)[-1]
        headline = re.sub(r"\[[^\]]+\]", " ", headline)
        headline = re.split(r"[·,/]|[↑↓▲▼]", headline)[0]
        name = re.sub(r"\s+", " ", headline).strip(" ,;:-")
        if looks_like_symbol_name(name, target) and not any(token in name for token in ("뉴스", "상승", "하락", "강세", "약세")):
            return clip_text(name, 80)
    return ""


def resolve_trade_symbol_metadata(report: Dict[str, Any], symbol: str, *, metadata_value: Callable[[Any], str], translate_text: Callable[[Any], str]) -> Dict[str, Any]:
    name_keys = (
        "symbol_name",
        "stock_name",
        "stock_nm",
        "stk_nm",
        "isu_nm",
        "corp_name",
        "company_name",
        "name_kr",
    )
    exact_theme_keys = (
        "symbol_theme",
        "symbol_themes",
        "symbol_theme_name",
        "matched_symbol_theme",
        "matched_symbol_themes",
        "matched_themes",
    )
    symbol_row_theme_keys = (
        "theme",
        "theme_name",
        "themes",
    )
    symbol_text = str(symbol or "").strip()
    symbol_name = ""
    component_themes = component_themes_for_symbol(
        report,
        symbol_text,
        metadata_value=metadata_value,
        translate_text=translate_text,
    )
    themes: List[str] = list(component_themes)
    for source in iter_trade_symbol_metadata_sources(report):
        source_symbol = str(
            source.get("symbol")
            or source.get("selected_symbol")
            or source.get("entry_final_symbol")
            or source.get("monitor_output_symbol")
            or ""
        ).strip()
        source_matches_symbol = not source_symbol or not symbol_text or source_symbol == symbol_text
        if source_matches_symbol and not symbol_name:
            for key in name_keys:
                candidate = metadata_value(translate_text(source.get(key))).strip()
                if looks_like_symbol_name(candidate, symbol_text):
                    symbol_name = clip_text(candidate, 80)
                    break
        if not component_themes:
            for key in exact_theme_keys:
                append_theme_values(
                    themes,
                    source.get(key),
                    metadata_value=metadata_value,
                    translate_text=translate_text,
                )
                if len(themes) >= 4:
                    break
        if not component_themes and source_symbol and source_matches_symbol:
            for key in symbol_row_theme_keys:
                append_theme_values(
                    themes,
                    source.get(key),
                    metadata_value=metadata_value,
                    translate_text=translate_text,
                )
                if len(themes) >= 4:
                    break
        if symbol_name and len(themes) >= 4:
            break
    if not symbol_name:
        symbol_name = SYMBOL_NAME_FALLBACKS.get(symbol_text, "")
    if not symbol_name:
        symbol_name = infer_symbol_name_from_report_text(report, symbol_text, metadata_value=metadata_value, translate_text=translate_text)
    if not themes:
        themes = list(SYMBOL_THEME_FALLBACKS.get(symbol_text, []))
    return {
        "symbol": symbol_text,
        "symbol_name": symbol_name,
        "themes": themes[:4],
        "theme": ", ".join(themes[:4]),
    }
