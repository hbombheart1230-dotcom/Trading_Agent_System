from __future__ import annotations

"""Read-only strategist linkage helpers for Phase 5-2-2.

These helpers assemble additive views that connect strategist news context,
candidate hints, and the selected symbol without depending on UI modules.
"""

from typing import Any, Dict, List

from libs.core.symbols import normalize_symbol


def _clip(value: Any, *, max_len: int = 220) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max(0, max_len - 3)] + "..."


def _list_text(values: Any, *, limit: int = 8, max_len: int = 120) -> List[str]:
    if not isinstance(values, list):
        return []
    out: List[str] = []
    for value in values:
        text = _clip(value, max_len=max_len)
        if not text or text in out:
            continue
        out.append(text)
        if len(out) >= max(1, int(limit)):
            break
    return out


def _norm_symbol(value: Any) -> str:
    return normalize_symbol(value, allow_test_symbols=True).strip().upper()


def _headline_text(row: Any) -> str:
    item = row if isinstance(row, dict) else {}
    for key in ("title", "headline", "summary", "description", "text", "news_title"):
        text = _clip(item.get(key), max_len=180)
        if text:
            return text
    return ""


def _headline_matches_symbol(row: Any, symbol: str) -> bool:
    item = row if isinstance(row, dict) else {}
    target = _norm_symbol(symbol)
    if not target:
        return False
    for candidate in (
        item.get("symbol"),
        item.get("code"),
        item.get("ticker"),
        item.get("query_target"),
        item.get("query"),
        item.get("news_query_target"),
    ):
        if _norm_symbol(candidate) == target:
            return True
    for key in ("symbols", "tickers", "related_symbols"):
        values = item.get(key)
        if not isinstance(values, list):
            continue
        for candidate in values:
            if _norm_symbol(candidate) == target:
                return True
    joined = " ".join(
        [
            str(item.get("title") or ""),
            str(item.get("headline") or ""),
            str(item.get("summary") or ""),
            str(item.get("description") or ""),
            str(item.get("query_target") or ""),
        ]
    ).upper()
    return bool(target and target in joined)


def _collect_top_headlines(rows: Any, *, limit: int = 3, symbol: str = "") -> List[str]:
    if not isinstance(rows, list):
        return []
    filtered: List[str] = []
    fallback: List[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = _headline_text(row)
        if not text:
            continue
        if text not in fallback:
            fallback.append(text)
        if symbol and _headline_matches_symbol(row, symbol) and text not in filtered:
            filtered.append(text)
    picked = filtered or fallback
    return picked[: max(1, int(limit))]


def _rows_from_news_like(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [dict(row) for row in value if isinstance(row, dict)]
    if not isinstance(value, dict):
        return []
    ranked_rows = value.get("ranked_rows")
    if isinstance(ranked_rows, list):
        return [dict(row) for row in ranked_rows if isinstance(row, dict)]
    out: List[Dict[str, Any]] = []
    for key, row in value.items():
        if not isinstance(row, dict):
            continue
        symbol = _norm_symbol(row.get("symbol") or key)
        titles: List[Any] = []
        for bucket in ("sample", "titles", "headlines"):
            values = row.get(bucket)
            if isinstance(values, list):
                titles.extend(values)
        for title in titles[:3]:
            text = _clip(title, max_len=180)
            if text:
                out.append({"symbol": symbol, "title": text})
    return out


def _candidate_hints(summary: Dict[str, Any], parsed: Dict[str, Any]) -> List[str]:
    hints = summary.get("candidate_symbols_hint")
    if not isinstance(hints, list):
        hints = parsed.get("candidate_symbols_hint")
    return [symbol for symbol in (_norm_symbol(value) for value in list(hints or [])) if symbol][:8]


def _candidate_hypotheses(summary: Dict[str, Any], parsed: Dict[str, Any]) -> List[Dict[str, str]]:
    raw = summary.get("candidate_hypotheses")
    if not isinstance(raw, list):
        raw = parsed.get("candidate_hypotheses")
    out: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if not isinstance(item, dict):
            continue
        symbol = _norm_symbol(item.get("symbol"))
        hypothesis = _clip(
            item.get("hypothesis") or item.get("summary") or item.get("reason"),
            max_len=240,
        )
        source = _clip(item.get("source"), max_len=80)
        if not symbol and not hypothesis:
            continue
        out.append({"symbol": symbol, "hypothesis": hypothesis, "source": source})
    return out


def _hypothesis_for_symbol(hypotheses: List[Dict[str, str]], symbol: str) -> str:
    target = _norm_symbol(symbol)
    for item in hypotheses:
        if _norm_symbol(item.get("symbol")) == target and str(item.get("hypothesis") or "").strip():
            return str(item.get("hypothesis") or "").strip()
    return ""


def build_news_symbol_linkage_view(
    *,
    strategist_summary: Dict[str, Any] | None = None,
    strategist_raw_input: Dict[str, Any] | None = None,
    strategist_parsed_output: Dict[str, Any] | None = None,
    selected_symbol: str = "",
    top_ranked_symbols: Any = None,
) -> Dict[str, Any]:
    summary = strategist_summary if isinstance(strategist_summary, dict) else {}
    raw_input = strategist_raw_input if isinstance(strategist_raw_input, dict) else {}
    parsed = strategist_parsed_output if isinstance(strategist_parsed_output, dict) else {}

    selected = _norm_symbol(selected_symbol)
    top_ranked = [symbol for symbol in (_norm_symbol(value) for value in list(top_ranked_symbols or [])) if symbol][:5]
    runner_up = next((symbol for symbol in top_ranked if symbol and symbol != selected), "")
    candidate_hints = _candidate_hints(summary, parsed)
    hypotheses = _candidate_hypotheses(summary, parsed)
    news_query_targets = _list_text(
        summary.get("news_query_targets")
        if summary.get("news_query_targets") is not None
        else raw_input.get("news_query_targets"),
        limit=8,
        max_len=80,
    )

    news_ranked = summary.get("news_evidence_ranked") if isinstance(summary.get("news_evidence_ranked"), dict) else {}
    market_rows = _rows_from_news_like(
        news_ranked.get("market_news_ranked")
        if news_ranked.get("market_news_ranked") is not None
        else raw_input.get("collected_market_news")
    )
    candidate_rows = _rows_from_news_like(
        news_ranked.get("candidate_news_ranked")
        if news_ranked.get("candidate_news_ranked") is not None
        else raw_input.get("collected_candidate_news")
    )
    if not candidate_rows:
        candidate_rows = _rows_from_news_like(raw_input.get("collected_news"))

    market_headlines = _collect_top_headlines(market_rows, limit=3)
    selected_headlines = _collect_top_headlines(candidate_rows, limit=3, symbol=selected)
    runner_up_headlines = _collect_top_headlines(candidate_rows, limit=3, symbol=runner_up)

    ordered_symbols: List[str] = []
    for symbol in [selected, *candidate_hints, *top_ranked]:
        normalized = _norm_symbol(symbol)
        if normalized and normalized not in ordered_symbols:
            ordered_symbols.append(normalized)

    linked_candidates: List[Dict[str, Any]] = []
    for symbol in ordered_symbols[:5]:
        symbol_headlines = _collect_top_headlines(candidate_rows, limit=3, symbol=symbol)
        hypothesis = _hypothesis_for_symbol(hypotheses, symbol)
        linkage_flags = [
            flag
            for flag, enabled in (
                ("candidate_hint", symbol in candidate_hints),
                ("top_ranked", symbol in top_ranked),
                ("headline_link", bool(symbol_headlines)),
                ("hypothesis", bool(hypothesis)),
                ("selected", symbol == selected),
            )
            if enabled
        ]
        linked_candidates.append(
            {
                "symbol": symbol,
                "top_headlines": symbol_headlines,
                "headline_count": len(symbol_headlines),
                "hypothesis_summary": hypothesis,
                "linkage_flags": linkage_flags,
                "selected": symbol == selected,
            }
        )

    selected_link = next((item for item in linked_candidates if item.get("selected")), {})
    selected_in_hints = bool(selected and selected in candidate_hints)
    selected_has_hypothesis = bool(selected_link.get("hypothesis_summary"))
    selected_has_headlines = bool(selected_link.get("headline_count"))
    runner_up_hypothesis = _hypothesis_for_symbol(hypotheses, runner_up)
    runner_up_in_hints = bool(runner_up and runner_up in candidate_hints)
    linkage_strength = "weak"
    if selected and selected_in_hints and (selected_has_hypothesis or selected_has_headlines):
        linkage_strength = "strong"
    elif selected and (selected_in_hints or selected_has_hypothesis or selected_has_headlines):
        linkage_strength = "partial"

    summary_text = (
        f"Strategist queried {len(news_query_targets)} news targets and linked selected symbol "
        f"{selected or '-'} to {int(selected_link.get('headline_count') or 0)} candidate headlines."
    )
    if selected_in_hints:
        summary_text += f" {selected} remained inside strategist candidate hints."

    comparison_summary = ""
    if selected and runner_up:
        comparison_summary = (
            f"Selected {selected} vs runner-up {runner_up}: "
            f"headlines {len(selected_headlines)} vs {len(runner_up_headlines)}, "
            f"hint_match {str(selected_in_hints).lower()} vs {str(runner_up_in_hints).lower()}."
        )

    return {
        "selected_symbol": selected,
        "runner_up_symbol": runner_up,
        "news_query_targets": news_query_targets,
        "candidate_symbols_hint": candidate_hints,
        "candidate_hypotheses": hypotheses[:8],
        "selected_symbol_in_candidate_hints": selected_in_hints,
        "runner_up_symbol_in_candidate_hints": runner_up_in_hints,
        "market_headlines": market_headlines,
        "selected_symbol_headlines": selected_headlines,
        "runner_up_symbol_headlines": runner_up_headlines,
        "linked_candidates": linked_candidates,
        "linkage_strength": linkage_strength,
        "selected_vs_runner_up": {
            "selected_symbol": selected,
            "runner_up_symbol": runner_up,
            "selected_headline_count": len(selected_headlines),
            "runner_up_headline_count": len(runner_up_headlines),
            "selected_hypothesis_summary": selected_link.get("hypothesis_summary") or "",
            "runner_up_hypothesis_summary": runner_up_hypothesis,
            "selected_in_candidate_hints": selected_in_hints,
            "runner_up_in_candidate_hints": runner_up_in_hints,
            "comparison_summary": comparison_summary,
        },
        "summary": summary_text,
    }


__all__ = ["build_news_symbol_linkage_view"]
