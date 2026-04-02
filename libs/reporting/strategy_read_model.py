from __future__ import annotations

"""Read-only strategist linkage helpers for Phase 5-2 reporting phases.

These helpers assemble additive views that connect strategist news context,
candidate hints, and the selected symbol without depending on UI modules.
They also provide compact strategist-facing feedback summaries derived from
trade story artifacts.
"""

from collections import Counter
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


def _collect_text_fragments(*values: Any) -> str:
    parts: List[str] = []
    for value in values:
        if isinstance(value, list):
            for item in value:
                text = _clip(item, max_len=240)
                if text:
                    parts.append(text)
            continue
        if isinstance(value, dict):
            for item in value.values():
                text = _clip(item, max_len=240)
                if text:
                    parts.append(text)
            continue
        text = _clip(value, max_len=240)
        if text:
            parts.append(text)
    return " | ".join(parts).lower()


def _contains_any(text: str, needles: List[str]) -> bool:
    haystack = str(text or "").lower()
    return any(str(needle or "").lower() in haystack for needle in needles if str(needle or "").strip())


def _entry_pattern_type(text: str) -> str:
    if _contains_any(text, ["breakout"]):
        return "breakout"
    if _contains_any(text, ["pullback"]):
        return "pullback"
    if _contains_any(text, ["reclaim"]):
        return "reclaim"
    if _contains_any(text, ["continuation"]):
        return "continuation"
    return "unknown"


def _entry_timing_quality(text: str) -> str:
    if _contains_any(text, ["late entry", "late chase", "entered late", "too late", "late"]):
        return "late"
    if _contains_any(text, ["early entry", "entered early", "too early", "early"]):
        return "early"
    if _contains_any(text, ["mid entry", "mid-cycle", "middle of move", "mid"]):
        return "mid"
    return "unknown"


def _entry_confirmation_quality(text: str, monitor_reason: Dict[str, Any]) -> str:
    scores = (
        monitor_reason.get("entry_condition_scores")
        if isinstance(monitor_reason.get("entry_condition_scores"), dict)
        else {}
    )
    if scores:
        try:
            confidence = float(scores.get("confidence_score"))
        except Exception:
            confidence = None
        try:
            threshold = float(scores.get("confidence_threshold"))
        except Exception:
            threshold = None
        try:
            breakout_score = float(scores.get("breakout_score"))
        except Exception:
            breakout_score = None
        try:
            volume_score = float(scores.get("volume_score"))
        except Exception:
            volume_score = None
        if confidence is not None and threshold is not None and confidence >= threshold:
            if (breakout_score is not None and breakout_score >= 1.0) and (volume_score is not None and volume_score >= 1.0):
                return "strong"
            return "moderate"
        if any(value is not None for value in (confidence, breakout_score, volume_score)):
            return "weak"
    if _contains_any(text, ["strong confirmation", "fully confirmed", "high confidence"]):
        return "strong"
    if _contains_any(text, ["confirmed", "confirmation", "vwap hold", "volume confirmation"]):
        return "moderate"
    if _contains_any(text, ["not confirmed", "weak confirmation", "insufficient confirmation"]):
        return "weak"
    return "unknown"


def _exit_pattern_type(text: str) -> str:
    if _contains_any(text, ["vwap_breakdown", "vwap breakdown", "vwap loss"]):
        return "vwap_breakdown"
    if _contains_any(text, ["trend_breakdown", "trend breakdown", "trend loss"]):
        return "trend_breakdown"
    if _contains_any(text, ["peak_drawdown", "peak drawdown"]):
        return "peak_drawdown"
    if _contains_any(text, ["hard_stop", "hard stop", "stop loss", "stop-loss"]):
        return "hard_stop"
    if _contains_any(text, ["trailing_stop", "trailing stop"]):
        return "trailing_stop"
    if _contains_any(text, ["take_profit", "take profit"]):
        return "take_profit"
    return "unknown"


def _exit_quality(text: str, exit_pattern_type: str) -> str:
    if _contains_any(text, ["forced", "forced exit", "forced liquidation"]):
        return "forced"
    if exit_pattern_type == "hard_stop":
        return "protective"
    if exit_pattern_type in {"vwap_breakdown", "trend_breakdown", "peak_drawdown"}:
        return "reactive"
    if exit_pattern_type in {"trailing_stop", "take_profit"}:
        return "disciplined"
    return "unknown"


def _thesis_invalidation_code(text: str, exit_pattern_type: str) -> str:
    if _contains_any(text, ["weak follow-through", "weak follow through"]):
        return "weak_follow_through"
    if _contains_any(text, ["failed breakout", "breakout failed"]):
        return "failed_breakout"
    if exit_pattern_type == "vwap_breakdown" or _contains_any(text, ["vwap loss", "lost vwap"]):
        return "vwap_loss"
    if exit_pattern_type == "trend_breakdown" or _contains_any(text, ["trend loss", "lost trend"]):
        return "trend_loss"
    if exit_pattern_type == "hard_stop":
        return "stop_loss"
    return "unknown"


def _append_unique(out: List[str], value: str) -> None:
    text = str(value or "").strip()
    if text and text not in out:
        out.append(text)


def _safe_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def _normalize_counter_key(value: Any, *, unknown: str = "unknown") -> str:
    text = _clip(value, max_len=64)
    return text or unknown


def _ordered_counter_dict(counter: Counter[str]) -> Dict[str, int]:
    return {key: count for key, count in sorted(counter.items(), key=lambda row: (-row[1], row[0]))}


def _compact_recent_trade_ref(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "trade_id": str(item.get("trade_id") or ""),
        "story_id": str(item.get("story_id") or ""),
        "run_id": str(item.get("run_id") or ""),
        "symbol": _norm_symbol(item.get("selected_symbol") or item.get("symbol") or ""),
        "playbook": _clip(item.get("playbook"), max_len=48),
        "trade_status": _clip(item.get("trade_status"), max_len=24) or "unknown",
        "final_action": _clip(item.get("final_action"), max_len=24) or "unknown",
        "entry_pattern_type": _clip(item.get("entry_pattern_type"), max_len=32) or "unknown",
        "exit_pattern_type": _clip(item.get("exit_pattern_type"), max_len=32) or "unknown",
        "thesis_invalidation_code": _clip(item.get("thesis_invalidation_code"), max_len=48) or "unknown",
        "result_pct": _safe_float(item.get("result_pct")),
    }


def _improvement_tags(text: str, thesis_invalidation_code: str, exit_pattern_type: str) -> List[str]:
    tags: List[str] = []
    if _contains_any(text, ["late entry", "entered late", "too late", "late"]):
        _append_unique(tags, "late_entry")
    if _contains_any(text, ["weak follow-through", "weak follow through"]):
        _append_unique(tags, "weak_follow_through")
    if _contains_any(text, ["insufficient confirmation", "weak confirmation", "volume confirmation missing", "reclaim_not_confirmed"]):
        _append_unique(tags, "insufficient_confirmation")
    if thesis_invalidation_code == "failed_breakout":
        _append_unique(tags, "failed_breakout")
    if thesis_invalidation_code == "vwap_loss":
        _append_unique(tags, "vwap_loss")
    if thesis_invalidation_code == "trend_loss":
        _append_unique(tags, "trend_loss")
    if thesis_invalidation_code == "stop_loss" or exit_pattern_type == "hard_stop":
        _append_unique(tags, "stop_loss")
    return tags


def _review_flags(
    *,
    trade_status: str,
    final_action: str,
    exit_pattern_type: str,
    exit_quality: str,
    entry_confirmation_quality: str,
    improvement_tags: List[str],
) -> List[str]:
    flags: List[str] = []
    if exit_pattern_type == "take_profit":
        _append_unique(flags, "high_quality_trade")
    if final_action == "SELL" and exit_quality in {"disciplined", "protective"} and exit_pattern_type in {"hard_stop", "trailing_stop", "vwap_breakdown", "trend_breakdown"}:
        _append_unique(flags, "small_loss_disciplined_exit")
    if trade_status == "closed" and final_action == "SELL" and exit_pattern_type == "unknown":
        _append_unique(flags, "needs_human_review")
    if entry_confirmation_quality == "unknown" and not improvement_tags and exit_pattern_type == "unknown":
        _append_unique(flags, "needs_human_review")
    return flags


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


def build_strategist_feedback_input_view(story_input: Dict[str, Any] | None = None) -> Dict[str, Any]:
    story = story_input if isinstance(story_input, dict) else {}
    market_context = story.get("market_context_human") if isinstance(story.get("market_context_human"), dict) else {}
    scanner_reason = story.get("scanner_reason_human") if isinstance(story.get("scanner_reason_human"), dict) else {}
    monitor_reason = story.get("monitor_reason_human") if isinstance(story.get("monitor_reason_human"), dict) else {}
    operator_conclusion = (
        story.get("operator_conclusion_human") if isinstance(story.get("operator_conclusion_human"), dict) else {}
    )
    entry_summary = story.get("entry_summary") if isinstance(story.get("entry_summary"), dict) else {}
    exit_summary = story.get("exit_summary") if isinstance(story.get("exit_summary"), dict) else {}
    lifecycle_summary = story.get("lifecycle_summary") if isinstance(story.get("lifecycle_summary"), dict) else {}
    linkage = story.get("news_symbol_linkage") if isinstance(story.get("news_symbol_linkage"), dict) else {}
    strategist_trace = (
        story.get("strategist_evidence_trace") if isinstance(story.get("strategist_evidence_trace"), dict) else {}
    )
    if not strategist_trace and isinstance(market_context.get("strategist_evidence_trace"), dict):
        strategist_trace = dict(market_context.get("strategist_evidence_trace") or {})

    selected_symbol = _norm_symbol(
        linkage.get("selected_symbol")
        or scanner_reason.get("selected_symbol")
        or story.get("symbol")
        or ""
    )
    playbook = _clip(market_context.get("playbook"), max_len=48)
    market_regime = _clip(market_context.get("market_regime"), max_len=48)
    market_sentiment = _clip(market_context.get("market_sentiment"), max_len=48)
    status = _clip(story.get("status"), max_len=24)
    action = _clip(story.get("action"), max_len=24)
    news_query_targets = _list_text(
        linkage.get("news_query_targets")
        if linkage.get("news_query_targets") is not None
        else market_context.get("news_query_targets"),
        limit=8,
        max_len=80,
    )
    candidate_hints = _list_text(
        story.get("strategist_candidate_hints")
        if story.get("strategist_candidate_hints") is not None
        else linkage.get("candidate_symbols_hint"),
        limit=8,
        max_len=24,
    )
    market_headlines = _list_text(
        linkage.get("market_headlines")
        if linkage.get("market_headlines") is not None
        else market_context.get("market_headlines"),
        limit=3,
        max_len=180,
    )
    symbol_headlines = _list_text(
        linkage.get("selected_symbol_headlines")
        if linkage.get("selected_symbol_headlines") is not None
        else market_context.get("symbol_headlines"),
        limit=3,
        max_len=180,
    )
    key_events = _list_text(
        strategist_trace.get("key_events")
        if strategist_trace.get("key_events") is not None
        else market_context.get("key_events"),
        limit=6,
        max_len=180,
    )
    selected_vs_runner_up = (
        linkage.get("selected_vs_runner_up") if isinstance(linkage.get("selected_vs_runner_up"), dict) else {}
    )
    comparison_summary = _clip(selected_vs_runner_up.get("comparison_summary"), max_len=240)
    entry_reason = _clip(
        entry_summary.get("reason_human")
        or scanner_reason.get("selection_reason")
        or scanner_reason.get("summary"),
        max_len=240,
    )
    holding_summary = _clip(monitor_reason.get("summary"), max_len=240)
    exit_reason = _clip(
        exit_summary.get("reason_human")
        or lifecycle_summary.get("exit_reason_human")
        or operator_conclusion.get("summary"),
        max_len=240,
    )
    watch_next = _list_text(operator_conclusion.get("watch_next"), limit=6, max_len=180)
    thesis_invalidation = _list_text(operator_conclusion.get("thesis_invalidation"), limit=6, max_len=180)
    improvement_points = _list_text(story.get("improvement_points"), limit=6, max_len=180)
    entry_text = _collect_text_fragments(
        entry_summary.get("reason_human"),
        scanner_reason.get("selection_reason"),
        scanner_reason.get("summary"),
        improvement_points,
    )
    exit_text = _collect_text_fragments(
        exit_summary.get("reason_human"),
        lifecycle_summary.get("exit_reason_human"),
        operator_conclusion.get("summary"),
        thesis_invalidation,
        improvement_points,
    )
    entry_pattern_type = _entry_pattern_type(entry_text)
    entry_timing_quality = _entry_timing_quality(entry_text)
    entry_confirmation_quality = _entry_confirmation_quality(entry_text, monitor_reason)
    exit_pattern_type = _exit_pattern_type(exit_text)
    exit_quality = _exit_quality(exit_text, exit_pattern_type)
    thesis_invalidation_code = _thesis_invalidation_code(exit_text, exit_pattern_type)
    improvement_tags = _improvement_tags(
        _collect_text_fragments(improvement_points, thesis_invalidation, entry_text, exit_text),
        thesis_invalidation_code,
        exit_pattern_type,
    )
    review_flags = _review_flags(
        trade_status=status,
        final_action=action,
        exit_pattern_type=exit_pattern_type,
        exit_quality=exit_quality,
        entry_confirmation_quality=entry_confirmation_quality,
        improvement_tags=improvement_tags,
    )

    summary_bits: List[str] = []
    if selected_symbol:
        summary_bits.append(selected_symbol)
    if playbook:
        summary_bits.append(f"playbook={playbook}")
    if status:
        summary_bits.append(f"status={status}")
    if action:
        summary_bits.append(f"action={action}")
    summary = (
        " | ".join(summary_bits)
        if summary_bits
        else "Strategist feedback input was assembled from trade story artifacts."
    )
    if comparison_summary:
        summary += f" {comparison_summary}"

    return normalize_strategist_feedback_input(
        {
        "schema_version": "strategist_feedback_input.v1",
        "selected_symbol": selected_symbol,
        "playbook": playbook,
        "market_regime": market_regime,
        "market_sentiment": market_sentiment,
        "trade_status": status,
        "final_action": action,
        "news_query_targets": news_query_targets,
        "candidate_symbols_hint": candidate_hints,
        "market_headlines": market_headlines,
        "selected_symbol_headlines": symbol_headlines,
        "key_events": key_events,
        "linkage_strength": _clip(linkage.get("linkage_strength"), max_len=24),
        "selected_vs_runner_up_summary": comparison_summary,
        "entry_summary": entry_reason,
        "entry_pattern_type": entry_pattern_type,
        "entry_timing_quality": entry_timing_quality,
        "entry_confirmation_quality": entry_confirmation_quality,
        "holding_summary": holding_summary,
        "exit_summary": exit_reason,
        "exit_pattern_type": exit_pattern_type,
        "exit_quality": exit_quality,
        "thesis_invalidation_code": thesis_invalidation_code,
        "improvement_tags": improvement_tags,
        "review_flags": review_flags,
        "watch_next": watch_next,
        "thesis_invalidation": thesis_invalidation,
        "improvement_points": improvement_points,
        "summary": summary,
        }
    )


def normalize_strategist_feedback_input(payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    out = dict(data)
    out["schema_version"] = str(out.get("schema_version") or "strategist_feedback_input.v1")
    out["selected_symbol"] = _norm_symbol(out.get("selected_symbol"))
    out["playbook"] = _clip(out.get("playbook"), max_len=48)
    out["market_regime"] = _clip(out.get("market_regime"), max_len=48)
    out["market_sentiment"] = _clip(out.get("market_sentiment"), max_len=48)
    out["trade_status"] = _clip(out.get("trade_status"), max_len=24)
    out["final_action"] = _clip(out.get("final_action"), max_len=24)
    out["news_query_targets"] = _list_text(out.get("news_query_targets"), limit=8, max_len=80)
    out["candidate_symbols_hint"] = _list_text(out.get("candidate_symbols_hint"), limit=8, max_len=24)
    out["market_headlines"] = _list_text(out.get("market_headlines"), limit=3, max_len=180)
    out["selected_symbol_headlines"] = _list_text(out.get("selected_symbol_headlines"), limit=3, max_len=180)
    out["key_events"] = _list_text(out.get("key_events"), limit=6, max_len=180)
    out["linkage_strength"] = _clip(out.get("linkage_strength"), max_len=24) or "unknown"
    out["selected_vs_runner_up_summary"] = _clip(out.get("selected_vs_runner_up_summary"), max_len=240)
    out["entry_summary"] = _clip(out.get("entry_summary"), max_len=240)
    out["entry_pattern_type"] = _clip(out.get("entry_pattern_type"), max_len=32) or "unknown"
    out["entry_timing_quality"] = _clip(out.get("entry_timing_quality"), max_len=32) or "unknown"
    out["entry_confirmation_quality"] = _clip(out.get("entry_confirmation_quality"), max_len=32) or "unknown"
    out["holding_summary"] = _clip(out.get("holding_summary"), max_len=240)
    out["exit_summary"] = _clip(out.get("exit_summary"), max_len=240)
    out["exit_pattern_type"] = _clip(out.get("exit_pattern_type"), max_len=32) or "unknown"
    out["exit_quality"] = _clip(out.get("exit_quality"), max_len=32) or "unknown"
    out["thesis_invalidation_code"] = _clip(out.get("thesis_invalidation_code"), max_len=48) or "unknown"
    out["improvement_tags"] = _list_text(out.get("improvement_tags"), limit=8, max_len=64)
    out["review_flags"] = _list_text(out.get("review_flags"), limit=8, max_len=64)
    out["watch_next"] = _list_text(out.get("watch_next"), limit=6, max_len=180)
    out["thesis_invalidation"] = _list_text(out.get("thesis_invalidation"), limit=6, max_len=180)
    out["improvement_points"] = _list_text(out.get("improvement_points"), limit=6, max_len=180)
    out["summary"] = _clip(out.get("summary"), max_len=320)
    return out


def build_recent_strategist_feedback_window(
    items: List[Dict[str, Any]] | None = None,
    *,
    window_size: int = 10,
) -> Dict[str, Any]:
    raw_items = items if isinstance(items, list) else []
    normalized_items: List[Dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        normalized = normalize_strategist_feedback_input(item)
        normalized["trade_id"] = str(item.get("trade_id") or normalized.get("trade_id") or "")
        normalized["story_id"] = str(item.get("story_id") or normalized.get("story_id") or "")
        normalized["run_id"] = str(item.get("run_id") or normalized.get("run_id") or "")
        normalized["result_pct"] = _safe_float(item.get("result_pct"))
        if not normalized.get("selected_symbol"):
            normalized["selected_symbol"] = _norm_symbol(item.get("symbol"))
        if not normalized.get("trade_status"):
            normalized["trade_status"] = _clip(item.get("trade_status") or item.get("status"), max_len=24) or "unknown"
        if not normalized.get("final_action"):
            normalized["final_action"] = _clip(item.get("final_action") or item.get("action"), max_len=24) or "unknown"
        normalized_items.append(normalized)

    limit = max(0, int(window_size or 0))
    if limit == 0:
        limited_items: List[Dict[str, Any]] = []
    else:
        limited_items = normalized_items[:limit]

    symbols: List[str] = []
    playbooks_seen: List[str] = []
    trade_status_counts: Counter[str] = Counter()
    final_action_counts: Counter[str] = Counter()
    entry_pattern_counts: Counter[str] = Counter()
    exit_pattern_counts: Counter[str] = Counter()
    thesis_invalidation_counts: Counter[str] = Counter()
    improvement_tag_counts: Counter[str] = Counter()
    review_flag_counts: Counter[str] = Counter()
    result_values: List[float] = []
    recent_trade_refs: List[Dict[str, Any]] = []

    for item in limited_items:
        symbol = _norm_symbol(item.get("selected_symbol") or item.get("symbol") or "")
        if symbol and symbol not in symbols:
            symbols.append(symbol)
        playbook = _clip(item.get("playbook"), max_len=48)
        if playbook and playbook not in playbooks_seen:
            playbooks_seen.append(playbook)

        trade_status_counts[_normalize_counter_key(item.get("trade_status"))] += 1
        final_action_counts[_normalize_counter_key(item.get("final_action"))] += 1
        entry_pattern_counts[_normalize_counter_key(item.get("entry_pattern_type"))] += 1
        exit_pattern_counts[_normalize_counter_key(item.get("exit_pattern_type"))] += 1
        thesis_invalidation_counts[_normalize_counter_key(item.get("thesis_invalidation_code"))] += 1

        for tag in _list_text(item.get("improvement_tags"), limit=8, max_len=64):
            improvement_tag_counts[_normalize_counter_key(tag)] += 1
        for flag in _list_text(item.get("review_flags"), limit=8, max_len=64):
            review_flag_counts[_normalize_counter_key(flag)] += 1

        result_pct = _safe_float(item.get("result_pct"))
        if result_pct is not None:
            result_values.append(result_pct)
        recent_trade_refs.append(_compact_recent_trade_ref(item))

    average_result_pct = (
        round(sum(result_values) / len(result_values), 6)
        if result_values
        else None
    )

    return {
        "window_size": limit,
        "trades_considered": len(limited_items),
        "symbols": symbols,
        "playbooks_seen": playbooks_seen,
        "trade_status_counts": _ordered_counter_dict(trade_status_counts),
        "final_action_counts": _ordered_counter_dict(final_action_counts),
        "entry_pattern_counts": _ordered_counter_dict(entry_pattern_counts),
        "exit_pattern_counts": _ordered_counter_dict(exit_pattern_counts),
        "thesis_invalidation_counts": _ordered_counter_dict(thesis_invalidation_counts),
        "improvement_tag_counts": _ordered_counter_dict(improvement_tag_counts),
        "review_flag_counts": _ordered_counter_dict(review_flag_counts),
        "known_result_trade_count": len(result_values),
        "average_result_pct": average_result_pct,
        "recent_trade_refs": recent_trade_refs,
    }


__all__ = [
    "build_news_symbol_linkage_view",
    "build_strategist_feedback_input_view",
    "build_recent_strategist_feedback_window",
    "normalize_strategist_feedback_input",
]
