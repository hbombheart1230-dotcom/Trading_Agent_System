from __future__ import annotations

"""Observation-only news event intelligence for Strategist input.

This module intentionally does not produce trade permissions. It converts
collected news samples into auditable event/theme/symbol watch evidence that
the Strategist can discuss while existing scanner, monitor, cost, and risk
gates remain authoritative.
"""

import re
from typing import Any, Dict, Iterable, List, Mapping, Tuple


EVENT_RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("ipo_listing", ("ipo", "listing", "nasdaq", "spac", "상장", "기업공개", "나스닥", "스팩")),
    ("policy_regulation", ("policy", "regulation", "approval", "subsidy", "정책", "정부", "규제", "승인", "허가", "지원", "보조금")),
    ("contract_order", ("contract", "supply", "mou", "수주", "계약", "공급", "납품", "협약")),
    ("earnings_guidance", ("earnings", "sales", "profit", "guidance", "실적", "매출", "영업이익", "흑자", "적자", "가이던스")),
    ("supply_chain", ("supply chain", "supplier", "component", "material", "equipment", "공급망", "협력사", "부품", "소재", "장비")),
    ("theme_momentum", ("momentum", "strong", "surge", "테마", "주도", "강세", "급등", "관심", "모멘텀")),
    ("risk_negative", ("lawsuit", "recall", "probe", "loss", "소송", "리콜", "압수수색", "횡령", "하락", "사고")),
)


THEME_RULES: Tuple[Tuple[str, Tuple[str, ...], Tuple[str, ...]], ...] = (
    ("space_aerospace", ("spacex", "space x", "space", "rocket", "satellite", "launch", "스페이스x", "우주", "로켓", "위성", "발사체"), ("우주항공", "위성통신", "방산", "항공우주")),
    ("ai_datacenter", ("ai", "artificial intelligence", "gpu", "datacenter", "data center", "인공지능", "데이터센터"), ("AI", "반도체", "데이터센터")),
    ("semiconductor", ("semiconductor", "hbm", "dram", "nand", "chip", "반도체", "메모리", "파운드리"), ("반도체", "HBM", "소부장")),
    ("battery", ("battery", "ev", "solid state", "배터리", "2차전지", "전고체", "전기차"), ("2차전지", "전고체", "배터리소재")),
    ("robotics", ("robot", "humanoid", "automation", "로봇", "휴머노이드", "자동화"), ("로봇", "스마트팩토리")),
    ("nuclear", ("nuclear", "smr", "원전", "원자력"), ("원전", "SMR")),
    ("shipbuilding_lng", ("shipbuilding", "lng", "조선", "선박"), ("조선", "LNG")),
    ("power_grid", ("transformer", "power grid", "cable", "전력", "변압기", "전선", "송전"), ("전력기기", "전선")),
)


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _clean_text(value: Any) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ").strip()


def _extract_repr_field(text: str, field: str) -> str:
    match = re.search(rf"{re.escape(field)}=(['\"])(.*?)\1", text, flags=re.DOTALL)
    return _clean_text(match.group(2)) if match else ""


def _news_rows(sample_map: Any, *, source_kind: str) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    sample = _as_dict(sample_map)
    for target, packet in sample.items():
        packet_dict = _as_dict(packet)
        items = _as_list(packet_dict.get("sample"))
        if not items and isinstance(packet, list):
            items = list(packet)
        for item in items:
            if isinstance(item, dict):
                title = _clean_text(item.get("title") or item.get("headline"))
                summary = _clean_text(item.get("summary") or item.get("description") or item.get("content"))
            else:
                raw = _clean_text(item)
                title = _extract_repr_field(raw, "title") or raw[:180]
                summary = _extract_repr_field(raw, "summary")
            text = " ".join(part for part in (title, summary) if part).strip()
            if not text:
                continue
            rows.append(
                {
                    "source_kind": source_kind,
                    "target": _clean_text(target).upper(),
                    "title": title[:220],
                    "summary": summary[:260],
                    "text": text[:520],
                }
            )
    return rows


def _keyword_hits(text: str, keywords: Iterable[str]) -> List[str]:
    lowered = text.lower()
    hits: List[str] = []
    for keyword in keywords:
        key = str(keyword or "").strip()
        if key and key.lower() in lowered:
            hits.append(key)
    return hits


def _event_matches(row: Mapping[str, str]) -> List[Dict[str, Any]]:
    text = row.get("text") or ""
    out: List[Dict[str, Any]] = []
    for event_type, keywords in EVENT_RULES:
        hits = _keyword_hits(text, keywords)
        if not hits:
            continue
        confidence = min(1.0, 0.35 + 0.08 * len(hits))
        if row.get("source_kind") == "candidate":
            confidence += 0.12
        out.append(
            {
                "event_type": event_type,
                "confidence": round(min(1.0, confidence), 4),
                "matched_keywords": hits[:6],
            }
        )
    return out


def _theme_matches(text: str) -> List[Dict[str, Any]]:
    matches: List[Dict[str, Any]] = []
    for bridge_id, keywords, themes in THEME_RULES:
        hits = _keyword_hits(text, keywords)
        if not hits:
            continue
        matches.append(
            {
                "bridge_id": bridge_id,
                "matched_keywords": hits[:6],
                "themes": list(themes),
                "confidence": round(min(1.0, 0.38 + 0.07 * len(hits)), 4),
            }
        )
    return matches


def _theme_component_index(available_themes: Any) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for row in _as_list(available_themes):
        row_dict = _as_dict(row)
        theme = _clean_text(row_dict.get("theme") or row_dict.get("theme_name"))
        if not theme:
            continue
        index[theme.lower()] = {
            "theme": theme,
            "theme_code": _clean_text(row_dict.get("theme_code")),
            "score": row_dict.get("score"),
            "component_symbols": [_clean_text(x).upper() for x in _as_list(row_dict.get("component_symbols"))[:12]],
        }
    return index


def _candidate_symbol_set(candidate_symbols: Any) -> set[str]:
    return {_clean_text(symbol).upper() for symbol in _as_list(candidate_symbols) if _clean_text(symbol)}


def _numeric_symbol(value: str) -> str:
    text = _clean_text(value).upper()
    return text if re.fullmatch(r"\d{6}", text) else ""


def build_news_event_intelligence(
    *,
    market_news_sample: Any,
    candidate_news_sample: Any,
    news_query_targets: Any = None,
    theme_strength: Any = None,
    available_themes: Any = None,
    candidate_symbols: Any = None,
) -> Dict[str, Any]:
    rows = _news_rows(market_news_sample, source_kind="market") + _news_rows(
        candidate_news_sample,
        source_kind="candidate",
    )
    theme_index = _theme_component_index(available_themes)
    candidate_set = _candidate_symbol_set(candidate_symbols)
    theme_strength_dict = _as_dict(theme_strength)

    events: List[Dict[str, Any]] = []
    theme_watch: Dict[str, Dict[str, Any]] = {}
    symbol_watch: Dict[str, Dict[str, Any]] = {}

    for idx, row in enumerate(rows):
        event_matches = _event_matches(row)
        theme_matches = _theme_matches(row.get("text") or "")
        if not event_matches and not theme_matches:
            continue

        event_id = f"news_event_{idx + 1:03d}"
        best_event = max(event_matches or [{"event_type": "unclassified_theme_signal", "confidence": 0.25, "matched_keywords": []}], key=lambda item: float(item.get("confidence") or 0.0))
        events.append(
            {
                "event_id": event_id,
                "source_kind": row.get("source_kind"),
                "source_target": row.get("target"),
                "event_type": best_event.get("event_type"),
                "confidence": best_event.get("confidence"),
                "matched_keywords": list(best_event.get("matched_keywords") or [])[:6],
                "title": row.get("title"),
                "themes_inferred": sorted({theme for match in theme_matches for theme in list(match.get("themes") or [])}),
            }
        )

        direct_symbol = _numeric_symbol(row.get("target") or "")
        if direct_symbol:
            packet = symbol_watch.setdefault(
                direct_symbol,
                {
                    "symbol": direct_symbol,
                    "link_type": "direct_candidate_news",
                    "link_confidence": 0.72,
                    "event_ids": [],
                    "matched_themes": [],
                },
            )
            packet["event_ids"].append(event_id)
            packet["matched_themes"] = sorted(set(packet.get("matched_themes") or []) | {theme for match in theme_matches for theme in list(match.get("themes") or [])})

        for match in theme_matches:
            for theme in list(match.get("themes") or []):
                theme_key = str(theme or "").lower()
                available_theme = theme_index.get(theme_key, {})
                theme_score = available_theme.get("score")
                packet = theme_watch.setdefault(
                    theme,
                    {
                        "theme": theme,
                        "theme_code": available_theme.get("theme_code") or "",
                        "link_confidence": match.get("confidence"),
                        "event_ids": [],
                        "matched_keywords": [],
                        "component_symbols": list(available_theme.get("component_symbols") or [])[:8],
                        "theme_strength_score": theme_score,
                    },
                )
                packet["event_ids"].append(event_id)
                packet["matched_keywords"] = sorted(
                    set(packet.get("matched_keywords") or []) | set(match.get("matched_keywords") or [])
                )[:8]
                for symbol in list(available_theme.get("component_symbols") or []):
                    if candidate_set and symbol not in candidate_set:
                        continue
                    symbol_packet = symbol_watch.setdefault(
                        symbol,
                        {
                            "symbol": symbol,
                            "link_type": "theme_bridge_candidate",
                            "link_confidence": 0.46,
                            "event_ids": [],
                            "matched_themes": [],
                        },
                    )
                    symbol_packet["event_ids"].append(event_id)
                    symbol_packet["matched_themes"] = sorted(set(symbol_packet.get("matched_themes") or []) | {theme})

    events = sorted(events, key=lambda item: float(item.get("confidence") or 0.0), reverse=True)[:12]
    theme_candidates = sorted(
        theme_watch.values(),
        key=lambda item: (float(item.get("link_confidence") or 0.0), len(item.get("event_ids") or [])),
        reverse=True,
    )[:10]
    symbol_candidates = sorted(
        symbol_watch.values(),
        key=lambda item: (float(item.get("link_confidence") or 0.0), len(item.get("event_ids") or [])),
        reverse=True,
    )[:12]

    return {
        "schema_version": "news_event_intelligence.v1",
        "behavior_effect": "observation_only",
        "promotion_state": "shadow_watchlist",
        "trading_action_allowed": False,
        "source": "news_event_intelligence",
        "news_query_targets": [_clean_text(x) for x in _as_list(news_query_targets)[:12]],
        "input_summary": {
            "news_rows": len(rows),
            "event_count": len(events),
            "theme_watch_count": len(theme_candidates),
            "symbol_watch_count": len(symbol_candidates),
            "theme_strength_available": bool(theme_strength_dict),
        },
        "event_candidates": events,
        "theme_watchlist": theme_candidates,
        "symbol_watchlist": symbol_candidates,
        "evidence_required_before_trade": [
            "theme_price_confirmation",
            "trading_value_expansion",
            "relative_strength",
            "chart_setup",
            "cost_edge",
            "fresh_news_not_negative",
        ],
        "guardrail": "Use as Strategist evidence only; do not bypass scanner, monitor, Commander, cost, or risk gates.",
    }


def compact_news_event_intelligence_for_llm(value: Any) -> Dict[str, Any]:
    packet = _as_dict(value)
    if not packet:
        return {}
    return {
        "schema_version": str(packet.get("schema_version") or "news_event_intelligence.v1"),
        "behavior_effect": "observation_only",
        "trading_action_allowed": False,
        "input_summary": dict(packet.get("input_summary") or {}),
        "event_candidates": [
            {
                "event_id": str(row.get("event_id") or ""),
                "source_kind": str(row.get("source_kind") or ""),
                "source_target": str(row.get("source_target") or ""),
                "event_type": str(row.get("event_type") or ""),
                "confidence": row.get("confidence"),
                "title": str(row.get("title") or "")[:140],
                "themes_inferred": [str(x or "") for x in _as_list(row.get("themes_inferred"))[:5]],
            }
            for row in _as_list(packet.get("event_candidates"))[:6]
            if isinstance(row, dict)
        ],
        "theme_watchlist": [
            {
                "theme": str(row.get("theme") or ""),
                "link_confidence": row.get("link_confidence"),
                "event_ids": [str(x or "") for x in _as_list(row.get("event_ids"))[:4]],
                "component_symbols": [str(x or "") for x in _as_list(row.get("component_symbols"))[:5]],
            }
            for row in _as_list(packet.get("theme_watchlist"))[:6]
            if isinstance(row, dict)
        ],
        "symbol_watchlist": [
            {
                "symbol": str(row.get("symbol") or ""),
                "link_type": str(row.get("link_type") or ""),
                "link_confidence": row.get("link_confidence"),
                "matched_themes": [str(x or "") for x in _as_list(row.get("matched_themes"))[:4]],
                "event_ids": [str(x or "") for x in _as_list(row.get("event_ids"))[:4]],
            }
            for row in _as_list(packet.get("symbol_watchlist"))[:8]
            if isinstance(row, dict)
        ],
        "evidence_required_before_trade": [
            str(x or "") for x in _as_list(packet.get("evidence_required_before_trade"))[:8]
        ],
        "guardrail": str(packet.get("guardrail") or ""),
    }
