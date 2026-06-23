from __future__ import annotations

import html
import re
from typing import Any, Dict, List, Mapping

from libs.reporting.reasoning_trace import (
    build_reasoning_provenance,
    build_reasoning_trace_from_summaries,
    normalize_reasoning_provenance_aliases,
    normalize_reasoning_trace_aliases,
)
from libs.reporting.strategy_read_model import (
    build_news_symbol_linkage_view,
    build_strategist_feedback_input_view,
)
from libs.reporting.trade_read_model import normalize_trade_report_section
from libs.reporting.trade_report_ai import resolve_shared_trade_facts
from libs.reporting.trade_report_common import (
    clip_text as clip,
    format_exit_label,
    format_pct,
    format_ratio_pct,
    is_empty_placeholder as _is_empty_placeholder,
    list_text as _list_text,
    merge_missing_values as _merge_missing_values,
    safe_float,
    safe_int,
    utc_now_iso,
)
from libs.reporting.trade_scanner_fallback_anchor import (
    reanchor_scanner_selection_for_monitor_fallback,
)
from libs.reporting.trade_fallback_text import (
    EXECUTION_OUTCOME_NOT_CAPTURED,
    LIFECYCLE_CONCLUSION_NOT_CAPTURED,
    REPORTER_LINKAGE_NOT_CAPTURED,
    lifecycle_conclusion_summary_is_placeholder,
)
from libs.reporting.trade_execution_outcome_text import (
    build_execution_outcome_fallback_from_lifecycle,
    execution_outcome_summary_is_placeholder,
)
from libs.reporting.trade_reporter_status_text import normalize_reporter_status_human
from libs.reporting.trade_story_evidence import (
    derive_evidence_provenance as _derive_evidence_provenance_impl,
    has_substantive_exit_evidence as _has_substantive_exit_evidence_impl,
    set_or_replace_placeholder as _set_or_replace_placeholder_impl,
)
from libs.reporting.trade_story_pipeline_evidence_hydration import (
    hydrate_canonical_agent_artifacts as _hydrate_canonical_agent_artifacts_impl,
    resolve_selection_monitor_artifact as _resolve_selection_monitor_artifact_impl,
    safe_read_json_file as _safe_read_json_file_impl,
)
from libs.reporting.trade_story_pipeline_human_payloads import (
    build_execution_outcome_human as _build_execution_outcome_human_impl,
    build_monitor_blocker_trace as _build_monitor_blocker_trace_impl,
    build_monitor_stop_policy_trace as _build_monitor_stop_policy_trace_impl,
    normalize_stop_thresholds as _normalize_stop_thresholds_impl,
    resolve_adaptive_stop_loss_pct as _resolve_adaptive_stop_loss_pct_impl,
    resolve_strategist_adaptive_exit as _resolve_strategist_adaptive_exit_impl,
)
from libs.reporting.trade_story_pipeline_story_assembly import (
    build_timeline as _build_timeline_impl,
    collect_story_warnings as _collect_story_warnings_impl,
    compact_canonical_monitor as _compact_canonical_monitor_impl,
    normalize_trade_lifecycle_for_story_input as _normalize_trade_lifecycle_for_story_input_impl,
)
from libs.core.symbols import normalize_symbol


def _has_substantive_exit_evidence(exit_payload: Any) -> bool:
    return _has_substantive_exit_evidence_impl(exit_payload)


def _set_or_replace_placeholder(target: Dict[str, Any], key: str, value: Any) -> None:
    _set_or_replace_placeholder_impl(target, key, value)


def _derive_evidence_provenance(bundle_out: Dict[str, Any]) -> Dict[str, Any]:
    return _derive_evidence_provenance_impl(bundle_out)


def _safe_read_json_file(path_value: Any) -> Dict[str, Any]:
    return _safe_read_json_file_impl(path_value)


def _hydrate_canonical_agent_artifacts(
    bundle_out: Dict[str, Any],
    canonical_agent_artifacts: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return _hydrate_canonical_agent_artifacts_impl(
        bundle_out,
        canonical_agent_artifacts,
        read_json_file=_safe_read_json_file,
    )


def _resolve_selection_monitor_artifact(
    bundle_out: Dict[str, Any],
    canonical_agent_artifacts: Dict[str, Any] | None,
) -> Dict[str, Any]:
    return _resolve_selection_monitor_artifact_impl(
        bundle_out,
        canonical_agent_artifacts,
        read_json_file=_safe_read_json_file,
    )


def _headline_text(row: Any) -> str:
    item = row if isinstance(row, dict) else {}
    for key in ("title", "headline", "summary", "description", "text", "news_title"):
        text = clip(item.get(key), max_len=180)
        if text:
            return text
    return ""


def _clean_news_fragment(value: Any, *, max_len: int = 180) -> str:
    text = html.unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return clip(text, max_len=max_len)


def _news_item_field(raw: Any, field: str) -> str:
    text = str(raw or "")
    for quote in ("'", '"'):
        marker = f"{field}={quote}"
        start = text.find(marker)
        if start < 0:
            continue
        start += len(marker)
        end = text.find(f"{quote}, ", start)
        if end < 0:
            end = text.find(quote, start)
        if end > start:
            return _clean_news_fragment(text[start:end])
    return ""


def _news_sample_parts(raw: Any) -> Dict[str, str]:
    if isinstance(raw, dict):
        return {
            "title": _clean_news_fragment(
                raw.get("title") or raw.get("headline") or raw.get("news_title")
            ),
            "summary": _clean_news_fragment(
                raw.get("summary") or raw.get("description") or raw.get("text"),
                max_len=260,
            ),
            "symbol": _norm_symbol_text(raw.get("symbol") or raw.get("code") or raw.get("ticker")),
        }
    return {
        "title": _news_item_field(raw, "title") or _clean_news_fragment(raw),
        "summary": _news_item_field(raw, "summary"),
        "symbol": _norm_symbol_text(_news_item_field(raw, "symbol")),
    }


def _norm_symbol_text(value: Any) -> str:
    return normalize_symbol(value, allow_test_symbols=True).strip().upper()


def _symbol_name_from_text(text: Any, symbol: str) -> str:
    target = _norm_symbol_text(symbol)
    if not target:
        return ""
    cleaned = _clean_news_fragment(text, max_len=320)
    pattern = rf"([A-Za-z0-9가-힣&·.\-\s]{{1,40}})\(\s*{re.escape(target)}\s*\)"
    match = re.search(pattern, cleaned)
    if not match:
        return ""
    name = re.sub(r"\s+", " ", str(match.group(1) or "")).strip(" ,;:·-")
    if not name:
        return ""
    # Keep the nearest token phrase; news snippets often have a long prefix.
    pieces = re.split(r"[,\s]+", name)
    return pieces[-1].strip() if pieces else name


def _sample_title_directly_matches_symbol(parts: Dict[str, str], symbol: str) -> bool:
    target = _norm_symbol_text(symbol)
    title = str(parts.get("title") or "")
    if not target or not title:
        return False
    if target in title:
        return True
    symbol_name = _symbol_name_from_text(parts.get("summary"), target)
    return bool(symbol_name and symbol_name in title)


def _format_symbol_news_headline(symbol: str, title: str, *, indirect: bool = False) -> str:
    target = _norm_symbol_text(symbol)
    cleaned = _clean_news_fragment(title)
    if not cleaned:
        return ""
    if re.match(r"\s*\d{6}\s*:", cleaned):
        return cleaned
    if indirect:
        return f"{target}: 관련 테마 뉴스 - {cleaned}" if target else f"관련 테마 뉴스 - {cleaned}"
    return f"{target}: {cleaned}" if target else cleaned


def _collect_symbol_headlines_from_ranked_rows(rows: Any, *, symbol: str, limit: int = 3) -> List[str]:
    if not isinstance(rows, list):
        return []
    target = _norm_symbol_text(symbol)
    if not target:
        return []
    direct: List[str] = []
    indirect: List[str] = []
    for row in rows:
        item = row if isinstance(row, dict) else {}
        row_target = _norm_symbol_text(
            item.get("target")
            or item.get("symbol")
            or item.get("code")
            or item.get("ticker")
        )
        if row_target and row_target != target:
            continue
        samples = item.get("sample_titles") or item.get("sample") or item.get("headlines") or []
        if not isinstance(samples, list):
            samples = [samples]
        if not samples:
            samples = [item]
        for sample in samples:
            parts = _news_sample_parts(sample)
            title = parts.get("title") or ""
            if not title:
                continue
            sample_symbol = _norm_symbol_text(parts.get("symbol"))
            summary_has_target = bool(target in str(parts.get("summary") or ""))
            title_is_direct = _sample_title_directly_matches_symbol(parts, target)
            if sample_symbol and sample_symbol != target and not summary_has_target:
                continue
            bucket = direct if title_is_direct else indirect
            headline = _format_symbol_news_headline(target, title, indirect=not title_is_direct)
            if headline and headline not in bucket:
                bucket.append(headline)
    picked = direct if direct else indirect
    return picked[: max(1, int(limit))]


def _headline_matches_symbol(row: Any, symbol: str) -> bool:
    item = row if isinstance(row, dict) else {}
    target = _norm_symbol_text(symbol)
    if not target:
        return False
    scalar_candidates = [
        item.get("symbol"),
        item.get("code"),
        item.get("ticker"),
        item.get("query_target"),
        item.get("query"),
        item.get("news_query_target"),
    ]
    for candidate in scalar_candidates:
        if _norm_symbol_text(candidate) == target:
            return True
    for key in ("symbols", "tickers", "related_symbols"):
        values = item.get(key)
        if not isinstance(values, list):
            continue
        for candidate in values:
            if _norm_symbol_text(candidate) == target:
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
    picked = filtered if symbol else fallback
    return picked[: max(1, int(limit))]


def _raw_strategist_evidence(bundle_out: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(bundle_out.get("strategist_evidence"), dict):
        return dict(bundle_out.get("strategist_evidence") or {})
    evidence = bundle_out.get("evidence") if isinstance(bundle_out.get("evidence"), dict) else {}
    if isinstance(evidence.get("strategist"), dict):
        return dict(evidence.get("strategist") or {})
    return {}


def _strategist_trace_source(
    canonical_strategist: Dict[str, Any],
    raw_strategist_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    source = dict(canonical_strategist or {})
    raw = raw_strategist_evidence if isinstance(raw_strategist_evidence, dict) else {}
    # Raw evidence carries the structured news rows. Prefer those over stale
    # flattened market_context headlines when rebuilding reports.
    if raw.get("news_evidence_ranked") is not None:
        source["news_evidence_ranked"] = raw.get("news_evidence_ranked")
    if raw.get("market_context_snapshots") is not None and source.get("market_context_snapshots") is None:
        source["market_context_snapshots"] = raw.get("market_context_snapshots")
    return source


def _title_prefixed_symbol(value: Any) -> str:
    match = re.match(r"\s*(\d{6})\s*:", str(value or ""))
    return match.group(1) if match else ""


def _list_text_for_symbol(values: Any, *, symbol: str, limit: int = 3, max_len: int = 180) -> List[str]:
    target = _norm_symbol_text(symbol)
    rows = _list_text(values, limit=50, max_len=max_len)
    if not target:
        return rows[: max(1, int(limit))]
    matched: List[str] = []
    untagged: List[str] = []
    has_detectable_symbol = False
    for row in rows:
        row_symbol = _title_prefixed_symbol(row)
        if row_symbol:
            has_detectable_symbol = True
        if row_symbol == target and row not in matched:
            matched.append(row)
        elif not row_symbol and row not in untagged:
            untagged.append(row)
    if matched:
        return matched[: max(1, int(limit))]
    if not has_detectable_symbol:
        return untagged[: max(1, int(limit))]
    return []


def _korea_indices_bullet(korea_indices: Any) -> str:
    packet = korea_indices if isinstance(korea_indices, dict) else {}
    indices = packet.get("indices") if isinstance(packet.get("indices"), dict) else {}
    parts: List[str] = []
    for name in ("KOSPI", "KOSDAQ"):
        row = indices.get(name) if isinstance(indices.get(name), dict) else {}
        if not row:
            continue
        parts.append(
            f"{name} current={format_pct(row.get('current'))} "
            f"previous_close={format_pct(row.get('previous_close'))} "
            f"change={format_pct(row.get('change_pct'))}%"
        )
    return "; ".join(parts)


def _top_numeric_drivers(values: Any, *, limit: int = 4) -> Dict[str, float]:
    if not isinstance(values, dict):
        return {}
    scored: List[tuple[float, str, float]] = []
    for key, value in values.items():
        try:
            numeric = float(value)
        except Exception:
            continue
        if numeric == 0.0:
            continue
        scored.append((abs(numeric), str(key), numeric))
    scored.sort(key=lambda row: (-row[0], row[1]))
    out: Dict[str, float] = {}
    for _, key, numeric in scored[: max(1, int(limit))]:
        out[key] = numeric
    return out


def _scanner_chart_fit_payload(row: Mapping[str, Any] | None) -> Dict[str, Any]:
    obj = dict(row or {}) if isinstance(row, Mapping) else {}
    score = obj.get("scanner_chart_fit_score")
    authority = str(obj.get("scanner_chart_fit_authority") or "").strip()
    components = obj.get("scanner_chart_fit_components") if isinstance(obj.get("scanner_chart_fit_components"), dict) else {}
    if score in (None, "") and not authority and not components:
        return {}
    return {
        "score": safe_float(score, 0.0) if score not in (None, "") else None,
        "authority": authority,
        "components": dict(components or {}),
    }


def _scanner_macro_chart_fit_payload(row: Mapping[str, Any] | None) -> Dict[str, Any]:
    obj = dict(row or {}) if isinstance(row, Mapping) else {}
    score = obj.get("scanner_macro_chart_fit_score")
    authority = str(obj.get("scanner_macro_chart_fit_authority") or "").strip()
    components = (
        obj.get("scanner_macro_chart_fit_components")
        if isinstance(obj.get("scanner_macro_chart_fit_components"), dict)
        else {}
    )
    bias = obj.get("scanner_macro_chart_fit_bias")
    if score in (None, "") and bias in (None, "") and not authority and not components:
        return {}
    return {
        "score": safe_float(score, 0.0) if score not in (None, "") else None,
        "bias": safe_float(bias, 0.0) if bias not in (None, "") else None,
        "authority": authority,
        "components": dict(components or {}),
    }


def _candidate_sources_from_score_breakdown(score_breakdown: Mapping[str, Any] | None) -> List[str]:
    scores = dict(score_breakdown or {})
    sources: List[str] = []
    if safe_float(scores.get("trading_value"), 0.0) > 0.0:
        sources.append("top_value")
    if safe_float(scores.get("volume_surge"), 0.0) > 0.0:
        sources.append("top_volume")
    if safe_float(scores.get("theme_boost"), 0.0) > 0.0:
        sources.append("sector_theme")
    if safe_float(scores.get("sentiment"), 0.0) > 0.0:
        sources.append("sentiment")
    return sources


def _selection_basis_from_scores(
    score_breakdown: Mapping[str, Any] | None,
    sources: List[str],
) -> List[str]:
    scores = dict(score_breakdown or {})
    basis: List[str] = []
    if safe_float(scores.get("trading_value"), 0.0) > 0.0 or "top_value" in sources:
        basis.append("trading value")
    if safe_float(scores.get("volume_surge"), 0.0) > 0.0 or "top_volume" in sources:
        basis.append("turnover and volume")
    if safe_float(scores.get("theme_boost"), 0.0) > 0.0 or "sector_theme" in sources:
        basis.append("theme and sector alignment")
    if safe_float(scores.get("sentiment"), 0.0) > 0.0 or "sentiment" in sources:
        basis.append("sentiment support")
    if not basis and safe_float(scores.get("momentum"), 0.0) > 0.0:
        basis.append("momentum")
    if not basis and safe_float(scores.get("trend"), 0.0) > 0.0:
        basis.append("trend")
    if not basis:
        basis.append("combined scanner ranking score")
    return basis


def _scanner_candidate_row_from_evidence(
    scanner_evidence: Mapping[str, Any] | None,
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip()
    if not symbol:
        return {}
    evidence = dict(scanner_evidence or {})
    for collection_name in ("candidate_ranking_tables", "selection_outputs"):
        for event in list(evidence.get(collection_name) or []):
            payload = event.get("payload") if isinstance(event, dict) and isinstance(event.get("payload"), dict) else {}
            rows: List[Any] = []
            if collection_name == "candidate_ranking_tables":
                rows = list(payload.get("rows") or [])
            else:
                rows = list(payload.get("ranking_top_n") or payload.get("scanner_top_candidates") or [])
                selected_candidate = payload.get("selected_candidate") if isinstance(payload.get("selected_candidate"), dict) else {}
                if selected_candidate:
                    rows.append(selected_candidate)
            for row in rows:
                if not isinstance(row, dict) or str(row.get("symbol") or "").strip() != symbol:
                    continue
                candidate = dict(row)
                score_breakdown = (
                    candidate.get("score_breakdown")
                    if isinstance(candidate.get("score_breakdown"), dict)
                    else {}
                )
                if not isinstance(candidate.get("sources"), list):
                    candidate["sources"] = _candidate_sources_from_score_breakdown(score_breakdown)
                return candidate
    return {}


def _build_strategist_evidence_trace(
    strategist: Dict[str, Any],
    *,
    selected_symbol: str = "",
    fallback_market_titles: Any = None,
    fallback_candidate_titles: Any = None,
) -> Dict[str, Any]:
    data = strategist if isinstance(strategist, dict) else {}
    news_ranked_raw = data.get("news_evidence_ranked")
    news_ranked = news_ranked_raw if isinstance(news_ranked_raw, dict) else {}
    if not news_ranked and isinstance(news_ranked_raw, list):
        for event in news_ranked_raw:
            payload = event.get("payload") if isinstance(event, dict) else {}
            if isinstance(payload, dict) and (
                payload.get("candidate_news_ranked") is not None
                or payload.get("market_news_ranked") is not None
            ):
                news_ranked = dict(payload)
                break
    global_signal = data.get("global_sentiment_signal") if isinstance(data.get("global_sentiment_signal"), dict) else {}
    fear_index = data.get("fear_index") if isinstance(data.get("fear_index"), dict) else {}
    if not fear_index and isinstance(global_signal.get("fear_index"), dict):
        fear_index = dict(global_signal.get("fear_index") or {})
    market_rows = list(news_ranked.get("market_news_ranked") or [])
    candidate_rows = list(news_ranked.get("candidate_news_ranked") or [])
    market_headlines = _collect_top_headlines(market_rows, limit=3)
    symbol_headlines = _collect_symbol_headlines_from_ranked_rows(
        candidate_rows,
        symbol=selected_symbol,
        limit=3,
    ) or _collect_top_headlines(candidate_rows, limit=3, symbol=selected_symbol)
    if not market_headlines:
        market_headlines = _list_text(fallback_market_titles, limit=3, max_len=180)
    if not symbol_headlines:
        symbol_headlines = _list_text_for_symbol(
            fallback_candidate_titles,
            symbol=selected_symbol,
            limit=3,
            max_len=180,
        )
    candidate_hints = _list_text(
        data.get("candidate_symbols_hint"),
        limit=8,
        max_len=24,
    )
    key_events = _list_text(
        data.get("key_events") if data.get("key_events") is not None else data.get("key_events_hint"),
        limit=6,
        max_len=180,
    )
    return {
        "candidate_hints": candidate_hints,
        "news_query_targets": _list_text(
            data.get("news_query_targets")
            if data.get("news_query_targets") is not None
            else news_ranked.get("news_query_targets"),
            limit=8,
            max_len=80,
        ),
        "market_headlines": market_headlines,
        "symbol_headlines": symbol_headlines,
        "global_sentiment_signal": dict(global_signal or {}),
        "korea_indices": dict(global_signal.get("korea_indices") or {}) if isinstance(global_signal.get("korea_indices"), dict) else {},
        "fear_index": dict(fear_index or {}),
        "key_events": key_events,
    }


def _build_scanner_selection_trace(scanner_reason: Dict[str, Any], scanner_artifact: Dict[str, Any]) -> Dict[str, Any]:
    reason = scanner_reason if isinstance(scanner_reason, dict) else {}
    artifact = scanner_artifact if isinstance(scanner_artifact, dict) else {}
    selected_symbol = str(
        reason.get("selected_symbol")
        or artifact.get("selected_symbol")
        or ""
    ).strip()
    selected_rank = safe_int(reason.get("selected_rank"), safe_int(artifact.get("selected_rank"), 0))
    ranked_candidates = [dict(row) for row in list(reason.get("top_candidates") or []) if isinstance(row, dict)]
    if not ranked_candidates:
        ranked_candidates = [dict(row) for row in list(artifact.get("ranked_candidates") or []) if isinstance(row, dict)]
    if not ranked_candidates:
        ranking_table = artifact.get("candidate_ranking_table") if isinstance(artifact.get("candidate_ranking_table"), dict) else {}
        ranked_candidates = [dict(row) for row in list(ranking_table.get("rows") or []) if isinstance(row, dict)]
    score_drivers = {}
    if isinstance(reason.get("score_breakdown"), dict):
        score_drivers = _top_numeric_drivers(reason.get("score_breakdown"), limit=4)
    if not score_drivers:
        score_breakdown_by_symbol = artifact.get("score_breakdown_by_symbol") if isinstance(artifact.get("score_breakdown_by_symbol"), dict) else {}
        score_drivers = _top_numeric_drivers(score_breakdown_by_symbol.get(selected_symbol), limit=4)
    selection_reason = (
        clip(reason.get("selection_basis"), max_len=260)
        or clip(reason.get("selection_reason_with_bias"), max_len=260)
        or clip(artifact.get("selection_reason_with_bias"), max_len=260)
        or clip(artifact.get("selection_reason"), max_len=260)
        or clip((artifact.get("candidate_selection_reason") or {}).get("selection_summary"), max_len=260)
        or clip(reason.get("summary"), max_len=260)
    )
    chart_feature_coverage = reason.get("feature_coverage") if isinstance(reason.get("feature_coverage"), dict) else {}
    scanner_chart_fit = reason.get("scanner_chart_fit") if isinstance(reason.get("scanner_chart_fit"), dict) else {}
    scanner_macro_chart_fit = (
        reason.get("scanner_macro_chart_fit")
        if isinstance(reason.get("scanner_macro_chart_fit"), dict)
        else {}
    )
    if not chart_feature_coverage:
        selected_row: Dict[str, Any] = {}
        for row in ranked_candidates:
            if str(row.get("symbol") or "").strip() == selected_symbol:
                selected_row = row
                break
        if not selected_row or not isinstance(selected_row.get("feature_coverage"), dict):
            ranking_table = artifact.get("candidate_ranking_table") if isinstance(artifact.get("candidate_ranking_table"), dict) else {}
            for row in list(ranking_table.get("rows") or []):
                if not isinstance(row, dict):
                    continue
                if str(row.get("symbol") or "").strip() == selected_symbol:
                    selected_row = dict(row)
                    break
        if isinstance(selected_row.get("feature_coverage"), dict):
            chart_feature_coverage = dict(selected_row.get("feature_coverage") or {})
        if not scanner_chart_fit:
            scanner_chart_fit = _scanner_chart_fit_payload(selected_row)
        if not scanner_macro_chart_fit:
            scanner_macro_chart_fit = _scanner_macro_chart_fit_payload(selected_row)
    if not scanner_chart_fit:
        scanner_chart_fit = _scanner_chart_fit_payload(artifact)
    if not scanner_macro_chart_fit:
        scanner_macro_chart_fit = _scanner_macro_chart_fit_payload(artifact)
    return {
        "ranked_candidates": ranked_candidates[:5],
        "selected_symbol": selected_symbol,
        "selected_rank": selected_rank,
        "selection_reason": selection_reason,
        "selected_symbol_score_drivers": score_drivers,
        "chart_feature_coverage": chart_feature_coverage,
        "scanner_chart_fit": scanner_chart_fit,
        "scanner_macro_chart_fit": scanner_macro_chart_fit,
    }


def _optional_float(value: Any) -> Any:
    if value in (None, ""):
        return None
    return safe_float(value, 0.0)


def _build_news_scanner_contribution_trace(
    *,
    selected_symbol: str,
    selected_score: Any,
    selected_sources: List[str],
    score_breakdown: Dict[str, Any],
    component_snapshot: Dict[str, Any],
    strategist: Dict[str, Any],
) -> Dict[str, Any]:
    positive_total = sum(max(safe_float(value, 0.0), 0.0) for value in dict(score_breakdown or {}).values())
    key_rows: Dict[str, Dict[str, Any]] = {}
    for key in ("trading_value", "momentum", "trend", "theme_boost", "sentiment"):
        value = safe_float(score_breakdown.get(key), 0.0)
        key_rows[key] = {
            "value": value,
            "positive_share_pct": (100.0 * value / positive_total) if positive_total > 0 else 0.0,
        }

    ranked = strategist.get("news_evidence_ranked") if isinstance(strategist.get("news_evidence_ranked"), dict) else {}
    market_headlines = _collect_top_headlines(list(ranked.get("market_news_ranked") or []), limit=3)
    symbol_headlines = _collect_top_headlines(
        list(ranked.get("candidate_news_ranked") or []),
        limit=3,
        symbol=selected_symbol,
    )
    query_targets = _list_text(
        strategist.get("news_query_targets")
        if strategist.get("news_query_targets") is not None
        else ranked.get("news_query_targets"),
        limit=8,
        max_len=80,
    )
    decision_frame = strategist.get("decision_frame") if isinstance(strategist.get("decision_frame"), dict) else {}
    theme_packet = strategist.get("theme_strength_packet") if isinstance(strategist.get("theme_strength_packet"), dict) else {}
    if not theme_packet and isinstance(decision_frame.get("theme_strength_packet"), dict):
        theme_packet = dict(decision_frame.get("theme_strength_packet") or {})
    theme_source = str(strategist.get("theme_source") or theme_packet.get("source") or "").strip()
    theme_status = str(strategist.get("theme_source_status") or theme_packet.get("status") or "").strip()
    theme_reason = str(strategist.get("theme_source_reason") or theme_packet.get("reason") or "").strip()

    return {
        "selected_score_total": safe_float(selected_score, 0.0),
        "positive_contribution_total": positive_total,
        "core_score_contributions": key_rows,
        "sentiment_inputs": {
            "news_sentiment_score": _optional_float(component_snapshot.get("news_sentiment")),
            "global_sentiment_score": _optional_float(component_snapshot.get("global_sentiment")),
            "blended_sentiment_component": _optional_float(component_snapshot.get("sentiment_component")),
            "weighted_sentiment_score_contribution": safe_float(score_breakdown.get("sentiment"), 0.0),
        },
        "theme_alignment_trace": {
            "theme_boost_score_contribution": safe_float(score_breakdown.get("theme_boost"), 0.0),
            "theme_source_matched": ("sector_theme" in selected_sources) or safe_float(score_breakdown.get("theme_boost"), 0.0) > 0.0,
            "strategist_themes": _list_text(strategist.get("themes"), limit=6, max_len=80),
            "theme_source": theme_source,
            "theme_source_status": theme_status,
            "theme_source_reason": theme_reason,
            "top_themes": _list_text(theme_packet.get("top_themes"), limit=6, max_len=80),
            "theme_scores": dict(theme_packet.get("theme_scores") or {}) if isinstance(theme_packet.get("theme_scores"), dict) else {},
        },
        "news_linkage_trace": {
            "news_query_targets": query_targets,
            "symbol_headlines_used": symbol_headlines,
            "market_headlines_used": market_headlines,
            "symbol_headline_count": len(symbol_headlines),
            "market_headline_count": len(market_headlines),
        },
    }


def _attach_news_scanner_contribution(
    *,
    scanner_reason_human: Dict[str, Any],
    scanner_selection_trace: Dict[str, Any],
    canonical_scanner: Dict[str, Any],
    canonical_strategist: Dict[str, Any],
    selected_symbol: str,
) -> None:
    selected_candidate = (
        canonical_scanner.get("selected_candidate")
        if isinstance(canonical_scanner.get("selected_candidate"), dict)
        else {}
    )
    selected_sources = [
        str(x or "")
        for x in list(
            scanner_reason_human.get("selected_sources")
            or selected_candidate.get("sources")
            or []
        )
        if str(x or "").strip()
    ]
    score_breakdown = (
        scanner_reason_human.get("score_breakdown")
        if isinstance(scanner_reason_human.get("score_breakdown"), dict)
        else selected_candidate.get("score_breakdown")
        if isinstance(selected_candidate.get("score_breakdown"), dict)
        else {}
    )
    component_snapshot = (
        selected_candidate.get("component_snapshot")
        if isinstance(selected_candidate.get("component_snapshot"), dict)
        else {}
    )
    selected_score = (
        scanner_reason_human.get("selected_score")
        if scanner_reason_human.get("selected_score") not in (None, "")
        else selected_candidate.get("score_total")
    )
    news_scanner_contribution = _build_news_scanner_contribution_trace(
        selected_symbol=selected_symbol,
        selected_score=selected_score,
        selected_sources=selected_sources,
        score_breakdown=score_breakdown if isinstance(score_breakdown, dict) else {},
        component_snapshot=component_snapshot if isinstance(component_snapshot, dict) else {},
        strategist=canonical_strategist if isinstance(canonical_strategist, dict) else {},
    )
    _set_or_replace_placeholder(
        scanner_reason_human,
        "news_scanner_contribution",
        dict(news_scanner_contribution),
    )
    _set_or_replace_placeholder(
        scanner_selection_trace,
        "news_scanner_contribution",
        dict(news_scanner_contribution),
    )
    bullets = [str(x or "") for x in list(scanner_reason_human.get("bullets") or []) if str(x or "").strip()]
    if not any(row.startswith("Core score contributions:") for row in bullets):
        bullets.append(
            "Core score contributions: "
            f"trading_value {safe_float((score_breakdown or {}).get('trading_value'), 0.0):+.3f}, "
            f"momentum {safe_float((score_breakdown or {}).get('momentum'), 0.0):+.3f}, "
            f"trend {safe_float((score_breakdown or {}).get('trend'), 0.0):+.3f}, "
            f"theme_boost {safe_float((score_breakdown or {}).get('theme_boost'), 0.0):+.3f}, "
            f"sentiment {safe_float((score_breakdown or {}).get('sentiment'), 0.0):+.3f}"
        )
    if not any(row.startswith("Theme linkage:") for row in bullets):
        theme_trace = news_scanner_contribution.get("theme_alignment_trace") if isinstance(news_scanner_contribution.get("theme_alignment_trace"), dict) else {}
        bullets.append(
            "Theme linkage: "
            f"matched={bool(theme_trace.get('theme_source_matched'))}, "
            f"theme_boost={safe_float(theme_trace.get('theme_boost_score_contribution'), 0.0):+.3f}, "
            f"themes={', '.join(_list_text(theme_trace.get('strategist_themes'), limit=4, max_len=60)) or 'none captured'}, "
            f"source={theme_trace.get('theme_source') or 'not_captured'}, "
            f"status={theme_trace.get('theme_source_status') or 'not_captured'}, "
            f"reason={theme_trace.get('theme_source_reason') or 'not_captured'}"
        )
    if not any(row.startswith("Sentiment input trace:") for row in bullets):
        sentiment_inputs = news_scanner_contribution.get("sentiment_inputs") if isinstance(news_scanner_contribution.get("sentiment_inputs"), dict) else {}
        if any(sentiment_inputs.get(key) is not None for key in ("news_sentiment_score", "global_sentiment_score", "blended_sentiment_component")):
            bullets.append(
                "Sentiment input trace: "
                f"news={safe_float(sentiment_inputs.get('news_sentiment_score'), 0.0):+.3f}, "
                f"global={safe_float(sentiment_inputs.get('global_sentiment_score'), 0.0):+.3f}, "
                f"blended={safe_float(sentiment_inputs.get('blended_sentiment_component'), 0.0):+.3f}, "
                f"weighted_score={safe_float(sentiment_inputs.get('weighted_sentiment_score_contribution'), 0.0):+.3f}"
            )
    if not any(row.startswith("News linkage to scanner:") for row in bullets):
        news_linkage = news_scanner_contribution.get("news_linkage_trace") if isinstance(news_scanner_contribution.get("news_linkage_trace"), dict) else {}
        if safe_int(news_linkage.get("symbol_headline_count"), 0) > 0 or safe_int(news_linkage.get("market_headline_count"), 0) > 0:
            bullets.append(
                "News linkage to scanner: "
                f"symbol_headlines={safe_int(news_linkage.get('symbol_headline_count'), 0)}, "
                f"market_headlines={safe_int(news_linkage.get('market_headline_count'), 0)}, "
                f"query_targets={', '.join(_list_text(news_linkage.get('news_query_targets'), limit=5, max_len=60)) or 'not captured'}"
            )
    if bullets:
        scanner_reason_human["bullets"] = bullets[:14]


def _normalize_stop_thresholds(thresholds: Dict[str, Any]) -> Dict[str, Any]:
    return _normalize_stop_thresholds_impl(thresholds)


def _resolve_strategist_adaptive_exit(monitor: Dict[str, Any]) -> Dict[str, Any]:
    return _resolve_strategist_adaptive_exit_impl(monitor)


def _resolve_adaptive_stop_loss_pct(monitor: Dict[str, Any], thresholds: Dict[str, Any]) -> Any:
    return _resolve_adaptive_stop_loss_pct_impl(monitor, thresholds)


def _build_monitor_stop_policy_trace(monitor: Dict[str, Any], thresholds: Dict[str, Any]) -> Dict[str, Any]:
    return _build_monitor_stop_policy_trace_impl(monitor, thresholds)


def _build_monitor_blocker_trace(monitor: Dict[str, Any]) -> Dict[str, Any]:
    return _build_monitor_blocker_trace_impl(monitor)


def _source_confidence_label(source: Any) -> str:
    raw = str(source or "").strip().lower()
    if raw in {"canonical", "normalized_trade_artifact", "normalized_trade"}:
        return "high"
    if raw in {"direct_artifact", "direct"}:
        return "medium"
    if raw in {"event_log", "fallback", "inferred"}:
        return "low"
    return "low"


def _is_present(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return bool(value)
    return True


def compute_evidence_completeness(story_input: Dict[str, Any]) -> Dict[str, Any]:
    obj = dict(story_input or {})
    required_sections = [
        "market_context_human",
        "scanner_reason_human",
        "filters_human",
        "monitor_reason_human",
        "guard_reason_human",
        "execution_outcome_human",
        "operator_conclusion_human",
    ]
    present_sections: List[str] = []
    missing_sections: List[str] = []
    for key in required_sections:
        value = obj.get(key)
        if isinstance(value, dict) and (_is_present(value.get("summary")) or _is_present(value.get("bullets"))):
            present_sections.append(key)
        elif _is_present(value):
            present_sections.append(key)
        else:
            missing_sections.append(key)
    score = float(len(present_sections)) / float(len(required_sections)) if required_sections else 1.0
    return {
        "required_sections": required_sections,
        "present_sections": present_sections,
        "missing_sections": missing_sections,
        "completeness_score": score,
    }


def _safe_path_text(value: Any) -> str:
    return str(value or "").strip()


def _safe_ref_map(values: Any) -> Dict[str, str]:
    if not isinstance(values, dict):
        return {}
    out: Dict[str, str] = {}
    for key, value in values.items():
        out[str(key)] = _safe_path_text(value)
    return out


def _resolve_commander_source_ref(refs: Dict[str, Any], section_provenance: Dict[str, Any]) -> str:
    ref_map = _safe_ref_map(refs)
    section_map = dict(section_provenance or {})
    return str(
        ref_map.get("canonical_commander_json")
        or ref_map.get("canonical_commander")
        or (section_map.get("market_context_human") or {}).get("artifact_path")
        or (section_map.get("operator_conclusion_human") or {}).get("artifact_path")
        or ""
    )


def _commander_reasoning_flag(source: Dict[str, Any], commander_summary: Dict[str, Any], key: str) -> bool:
    summary_obj = dict(commander_summary or {})
    if key in summary_obj and isinstance(summary_obj.get(key), bool):
        return bool(summary_obj.get(key))
    latest_provenance = source.get("latest_reasoning_trace_provenance")
    if isinstance(latest_provenance, dict) and key in latest_provenance and isinstance(latest_provenance.get(key), bool):
        return bool(latest_provenance.get(key))
    commander_obj = source.get("commander")
    if isinstance(commander_obj, dict) and key in commander_obj and isinstance(commander_obj.get(key), bool):
        return bool(commander_obj.get(key))
    return False


def _commander_reasoning_source_priority(source: Dict[str, Any], commander_summary: Dict[str, Any]) -> List[str]:
    summary_obj = dict(commander_summary or {})
    latest_provenance = source.get("latest_reasoning_trace_provenance") if isinstance(source.get("latest_reasoning_trace_provenance"), dict) else {}
    commander_obj = source.get("commander") if isinstance(source.get("commander"), dict) else {}
    for candidate in (latest_provenance, commander_obj, summary_obj):
        values = [str(x or "").strip() for x in list(candidate.get("source_priority") or []) if str(x or "").strip()]
        if values:
            return values
    return []


def build_commander_evidence(commander_payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(commander_payload or {})
    return {
        "schema_version": "commander_evidence.v1",
        "session_type": str(payload.get("session_type") or ""),
        "market_regime_summary": str(payload.get("market_regime_summary") or ""),
        "goal": str(payload.get("goal") or ""),
        "decision_path": str(payload.get("final_runtime_path") or payload.get("path") or ""),
        "invocation_plan": [str(x or "") for x in list(payload.get("agent_invocation_plan") or []) if str(x or "").strip()],
        "final_reason": str(payload.get("final_reason") or payload.get("reason") or ""),
    }


def build_lifecycle_bundle(
    *,
    day: str,
    trade_id: str,
    run_id: str,
    symbol: str,
    lifecycle: Dict[str, Any],
    strategist_summary: Dict[str, Any],
    scanner_summary: Dict[str, Any],
    monitor_summary: Dict[str, Any],
    commander_summary: Dict[str, Any],
    story_input: Dict[str, Any],
    diagnostics: Dict[str, Any],
    canonical_refs: Dict[str, Any],
    llm_refs: Dict[str, Any],
    artifact_links: Dict[str, Any],
) -> Dict[str, Any]:
    lifecycle_obj = dict(lifecycle or {})
    entry_obj = dict(lifecycle_obj.get("entry") or {})
    holding_obj = dict(lifecycle_obj.get("holding") or {})
    exit_obj = dict(lifecycle_obj.get("exit") or {})
    summary_obj = dict(lifecycle_obj.get("summary") or {})
    hold_events = [
        dict(row)
        for row in list(holding_obj.get("holding_events") or [])
        if isinstance(row, dict)
    ]
    if not hold_events and isinstance(holding_obj.get("posture_history"), list):
        hold_events = [
            dict(row)
            for row in list(holding_obj.get("posture_history") or [])
            if isinstance(row, dict)
        ]
    completeness = compute_evidence_completeness(story_input)
    shared_facts = resolve_shared_trade_facts(story_input)
    exit_reason = (
        str(summary_obj.get("exit_reason_human") or "")
        or str((exit_obj.get("monitor_context") or {}).get("exit_reason") or "")
        or str(exit_obj.get("reason_human") or "")
    )
    entry_reason = (
        str(summary_obj.get("entry_reason_human") or "")
        or str(entry_obj.get("reason_human") or "")
        or str((story_input.get("entry_reason_human") or {}).get("summary") or "")
    )
    monitor_snapshot = dict(story_input.get("monitor_reason_human") or {})
    same_day_reporter_linkage = dict(story_input.get("same_day_reporter_linkage") or lifecycle_obj.get("same_day_reporter_linkage") or {})
    execution_details = dict(story_input.get("execution_details") or lifecycle_obj.get("execution_details") or {})
    entry_execution_details = dict(
        story_input.get("entry_execution_details")
        or (entry_obj.get("execution_details") if isinstance(entry_obj.get("execution_details"), dict) else {})
        or {}
    )
    exit_execution_details = dict(
        story_input.get("exit_execution_details")
        or (exit_obj.get("execution_details") if isinstance(exit_obj.get("execution_details"), dict) else {})
        or {}
    )
    failure_classification = dict(story_input.get("failure_classification") or lifecycle_obj.get("failure_classification") or {})
    derived_reasoning_trace = build_reasoning_trace_from_summaries(
        commander_summary=dict(commander_summary or {}),
        strategist_summary=dict(strategist_summary or {}),
        scanner_summary=dict(scanner_summary or {}),
        monitor_summary=dict(monitor_summary or {}),
        market_context_human=dict(story_input.get("market_context_human") or {}),
        scanner_reason_human=dict(story_input.get("scanner_reason_human") or {}),
        monitor_reason_human=dict(story_input.get("monitor_reason_human") or {}),
        operator_conclusion_human=dict(story_input.get("operator_conclusion_human") or {}),
    )
    reasoning_trace = normalize_reasoning_trace_aliases(story_input, fallback=derived_reasoning_trace)
    section_provenance = dict(story_input.get("section_provenance") or {})
    evidence_provenance = dict(story_input.get("evidence_provenance") or {})
    refs = _safe_ref_map({**dict(canonical_refs or {}), **dict(artifact_links or {})})
    commander_source_priority = _commander_reasoning_source_priority(story_input, dict(commander_summary or {}))
    derived_reasoning_provenance = build_reasoning_provenance(
        commander_context_source="canonical" if refs.get("canonical_commander_json") or refs.get("canonical_commander") else str(evidence_provenance.get("commander") or ""),
        strategist_plan_source=str(
            (section_provenance.get("market_context_human") or {}).get("source")
            or evidence_provenance.get("strategist")
            or ("canonical" if refs.get("canonical_strategist_json") or refs.get("canonical_strategist") else "")
        ),
        scanner_reason_source=str(
            (section_provenance.get("scanner_reason_human") or {}).get("source")
            or evidence_provenance.get("scanner")
            or ("canonical" if refs.get("canonical_scanner_json") or refs.get("canonical_scanner") else "")
        ),
        monitor_reason_source=str(
            (section_provenance.get("monitor_reason_human") or {}).get("source")
            or evidence_provenance.get("monitor")
            or ("canonical" if refs.get("canonical_monitor_json") or refs.get("canonical_monitor") else "")
        ),
        commander_source_ref=_resolve_commander_source_ref(refs, section_provenance),
        strategist_source_ref=str(
            refs.get("canonical_strategist_json")
            or refs.get("canonical_strategist")
            or (section_provenance.get("market_context_human") or {}).get("artifact_path")
            or ""
        ),
        scanner_source_ref=str(
            refs.get("canonical_scanner_json")
            or refs.get("canonical_scanner")
            or (section_provenance.get("scanner_reason_human") or {}).get("artifact_path")
            or ""
        ),
        monitor_source_ref=str(
            refs.get("canonical_monitor_json")
            or refs.get("canonical_monitor")
            or (section_provenance.get("monitor_reason_human") or {}).get("artifact_path")
            or ""
        ),
        shadow_used=_commander_reasoning_flag(story_input, dict(commander_summary or {}), "shadow_used"),
        strategist_fallback_used=(
            _commander_reasoning_flag(story_input, dict(commander_summary or {}), "strategist_fallback_used")
            or bool((strategist_summary or {}).get("strategist_fallback_used"))
        ),
        source_priority=commander_source_priority,
    )
    reasoning_provenance = normalize_reasoning_provenance_aliases(
        story_input,
        fallback=derived_reasoning_provenance,
    )
    top_level_entry = dict(entry_obj)
    if not top_level_entry:
        top_level_entry = {"available": False}
    top_level_entry.setdefault("available", bool(entry_obj))
    if entry_reason:
        top_level_entry.setdefault("summary", str(entry_reason))
    if symbol:
        top_level_entry.setdefault("symbol", str(symbol))

    top_level_exit = dict(exit_obj)
    if not top_level_exit:
        top_level_exit = {"available": False}
    top_level_exit.setdefault("available", bool(exit_obj))
    if exit_reason:
        top_level_exit.setdefault("summary", str(exit_reason))
    if symbol:
        top_level_exit.setdefault("symbol", str(symbol))
    return {
        "schema_version": "lifecycle_bundle.v1",
        "day": str(day or ""),
        "trade_id": str(trade_id or ""),
        "symbol": str(symbol or ""),
        "run_id": str(run_id or ""),
        "entry": top_level_entry,
        "exit": top_level_exit,
        "shared_facts": dict(shared_facts or {}),
        "news_symbol_linkage": dict(story_input.get("news_symbol_linkage") or {}),
        "strategist_feedback_input": dict(story_input.get("strategist_feedback_input") or {}),
        "lifecycle": {
            "entry": entry_obj,
            "hold": hold_events,
            "exit": exit_obj,
        },
        "strategist_summary": dict(strategist_summary or {}),
        "scanner_summary": dict(scanner_summary or {}),
        "monitor_summary": dict(monitor_summary or {}),
        "commander_summary": dict(commander_summary or {}),
        "reasoning_trace": reasoning_trace,
        "reasoning_provenance": reasoning_provenance,
        "trade_outcome": {
            "pnl": monitor_snapshot.get("pnl"),
            "return_pct": monitor_snapshot.get("current_drawdown"),
            "holding_time": str(summary_obj.get("holding_duration") or ""),
            "exit_reason": str(exit_reason or ""),
        },
        "hold_duration": str(
            summary_obj.get("holding_duration")
            or holding_obj.get("hold_duration")
            or story_input.get("hold_duration")
            or ""
        ),
        "hold_duration_sec": (
            holding_obj.get("hold_duration_sec")
            if holding_obj.get("hold_duration_sec") is not None
            else story_input.get("hold_duration_sec")
        ),
        "holding_phase_summary": str(
            holding_obj.get("holding_phase_summary")
            or story_input.get("holding_phase_summary")
            or ""
        ),
        "hold_events_count": (
            holding_obj.get("hold_events_count")
            if holding_obj.get("hold_events_count") is not None
            else story_input.get("hold_events_count")
            if story_input.get("hold_events_count") is not None
            else len(hold_events)
        ),
        "monitor_context_snapshots": [
            dict(row)
            for row in list(
                holding_obj.get("monitor_context_snapshots")
                or story_input.get("monitor_context_snapshots")
                or []
            )
            if isinstance(row, dict)
        ][:20],
        "hold_signal_transitions": [
            dict(row)
            for row in list(
                holding_obj.get("hold_signal_transitions")
                or story_input.get("hold_signal_transitions")
                or []
            )
            if isinstance(row, dict)
        ][:20],
        "pre_exit_context_summary": dict(
            holding_obj.get("pre_exit_context_summary")
            or story_input.get("pre_exit_context_summary")
            or {}
        ),
        "same_day_reporter_linkage": same_day_reporter_linkage,
        "execution_details": execution_details,
        "entry_execution_details": entry_execution_details,
        "exit_execution_details": exit_execution_details,
        "failure_classification": failure_classification,
        "evidence_summary": {
            "completeness_score": float(completeness.get("completeness_score") or 0.0),
            "missing_sections": [str(x or "") for x in list(completeness.get("missing_sections") or []) if str(x or "").strip()],
        },
        "llm_summary": {
            "strategist_llm_status": str(diagnostics.get("strategist_llm_status") or "skipped"),
            "brief_llm_status": str(diagnostics.get("llm_brief_status") or "skipped"),
            "ai_report_status": str(diagnostics.get("ai_trade_report_status") or "skipped"),
        },
        "refs": {
            "canonical_refs": _safe_ref_map(canonical_refs),
            "llm_refs": _safe_ref_map(llm_refs),
            "artifact_links": _safe_ref_map(artifact_links),
        },
        "missing": {
            "entry_missing": not bool(entry_obj),
            "hold_missing": not bool(hold_events),
            "exit_missing": not bool(exit_obj),
        },
    }


def _section_source_entry(
    *,
    source: str,
    artifact_path: str = "",
) -> Dict[str, str]:
    return {
        "source": str(source or "fallback"),
        "artifact_path": str(artifact_path or ""),
        "confidence": _source_confidence_label(source),
    }


def build_section_provenance(bundle_out: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    artifacts = bundle_out.get("artifacts") if isinstance(bundle_out.get("artifacts"), dict) else {}
    evidence_provenance = _derive_evidence_provenance(bundle_out)

    def _agent_source(agent: str) -> str:
        return str(evidence_provenance.get(agent) or "fallback").strip().lower()

    def _agent_path(agent: str) -> str:
        canonical_key = f"canonical_{agent}_json"
        canonical_path = str(artifacts.get(canonical_key) or "").strip()
        if canonical_path:
            return canonical_path
        if agent == "reporter":
            return str(artifacts.get("reporter_analysis_json") or "").strip()
        return str(artifacts.get("agent_pipeline_trace_json") or "").strip()

    strategist_entry = _section_source_entry(
        source=_agent_source("strategist"),
        artifact_path=_agent_path("strategist"),
    )
    scanner_entry = _section_source_entry(
        source=_agent_source("scanner"),
        artifact_path=_agent_path("scanner"),
    )
    monitor_entry = _section_source_entry(
        source=_agent_source("monitor"),
        artifact_path=_agent_path("monitor"),
    )
    supervisor_entry = _section_source_entry(
        source=_agent_source("supervisor"),
        artifact_path=_agent_path("supervisor"),
    )
    executor_entry = _section_source_entry(
        source=_agent_source("executor"),
        artifact_path=_agent_path("executor"),
    )
    reporter_entry = _section_source_entry(
        source=_agent_source("reporter"),
        artifact_path=_agent_path("reporter"),
    )
    commander_entry = _section_source_entry(
        source=_agent_source("commander"),
        artifact_path=_agent_path("commander"),
    )
    return {
        "market_context_human": strategist_entry,
        "scanner_reason_human": scanner_entry,
        "filters_human": scanner_entry,
        "monitor_reason_human": monitor_entry,
        "guard_reason_human": supervisor_entry,
        "execution_outcome_human": executor_entry,
        "reporter_status_human": reporter_entry,
        "operator_conclusion_human": commander_entry,
        "timeline": commander_entry,
    }


def _section_seed_provenance_entry(section_provenance: Dict[str, Any], key: str) -> Dict[str, str]:
    entry = section_provenance.get(key) if isinstance(section_provenance.get(key), dict) else {}
    return {
        "source": str(entry.get("source") or "fallback"),
        "artifact_path": str(entry.get("artifact_path") or ""),
        "confidence": str(entry.get("confidence") or _source_confidence_label(entry.get("source"))),
    }


def build_report_section_seeds(
    *,
    market_context_human: Dict[str, Any],
    scanner_reason_human: Dict[str, Any],
    filters_human: Dict[str, Any],
    monitor_reason_human: Dict[str, Any] | None = None,
    execution_outcome_human: Dict[str, Any] | None = None,
    guard_reason_human: Dict[str, Any] | None = None,
    reporter_status_human: Dict[str, Any] | None = None,
    operator_conclusion_human: Dict[str, Any] | None = None,
) -> Dict[str, Dict[str, Any]]:
    report_like = {
        "market_context_at_entry": dict(market_context_human or {}),
        "why_this_symbol_was_chosen": dict(scanner_reason_human or {}),
        "scanner_filters": dict(filters_human or {}),
        "holding_monitoring_story": dict(monitor_reason_human or {}),
        "exit_decision": dict(execution_outcome_human or {}),
        "execution_quality": dict(execution_outcome_human or {}),
        "guard_approval_result": dict(guard_reason_human or {}),
        "reporter_evaluation": dict(reporter_status_human or {}),
        "final_operator_conclusion": dict(operator_conclusion_human or {}),
    }
    return {
        "market_context_at_entry": normalize_trade_report_section(
            report_like,
            "market_context_at_entry",
            str((market_context_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "strategist_summary": normalize_trade_report_section(
            report_like,
            "strategist_summary",
            str((market_context_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "why_this_symbol_was_chosen": normalize_trade_report_section(
            report_like,
            "why_this_symbol_was_chosen",
            str((scanner_reason_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "entry_decision": normalize_trade_report_section(
            report_like,
            "entry_decision",
            str((scanner_reason_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "holding_monitoring_story": normalize_trade_report_section(
            report_like,
            "holding_monitoring_story",
            str((monitor_reason_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "exit_decision": normalize_trade_report_section(
            report_like,
            "exit_decision",
            str((execution_outcome_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "scanner_filters": normalize_trade_report_section(
            report_like,
            "scanner_filters",
            str((filters_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "execution_quality": normalize_trade_report_section(
            report_like,
            "execution_quality",
            str((execution_outcome_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "guard_approval_result": normalize_trade_report_section(
            report_like,
            "guard_approval_result",
            str((guard_reason_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "reporter_evaluation": normalize_trade_report_section(
            report_like,
            "reporter_evaluation",
            str((reporter_status_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
        "final_operator_conclusion": normalize_trade_report_section(
            report_like,
            "final_operator_conclusion",
            str((operator_conclusion_human or {}).get("summary") or ""),
            trim_text=clip,
            clean_str_list=_list_text,
        ),
    }


def build_report_section_provenance_seeds(section_provenance: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    provenance = dict(section_provenance or {})
    return {
        "market_context_at_entry": _section_seed_provenance_entry(provenance, "market_context_human"),
        "strategist_summary": _section_seed_provenance_entry(provenance, "market_context_human"),
        "why_this_symbol_was_chosen": _section_seed_provenance_entry(provenance, "scanner_reason_human"),
        "entry_decision": _section_seed_provenance_entry(provenance, "scanner_reason_human"),
        "holding_monitoring_story": _section_seed_provenance_entry(provenance, "monitor_reason_human"),
        "exit_decision": _section_seed_provenance_entry(provenance, "execution_outcome_human"),
        "scanner_filters": _section_seed_provenance_entry(provenance, "filters_human"),
        "execution_quality": _section_seed_provenance_entry(provenance, "execution_outcome_human"),
        "guard_approval_result": _section_seed_provenance_entry(provenance, "guard_reason_human"),
        "reporter_evaluation": _section_seed_provenance_entry(provenance, "reporter_status_human"),
        "final_operator_conclusion": _section_seed_provenance_entry(provenance, "operator_conclusion_human"),
    }


def slug(value: Any, *, max_len: int = 80) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(value or "").strip()).strip("_")
    if not text:
        return "item"
    return text[: max_len]


def feature_coverage(selected_candidate: Dict[str, Any]) -> Dict[str, Any]:
    feature_snapshot = (
        selected_candidate.get("feature_snapshot") if isinstance(selected_candidate.get("feature_snapshot"), dict) else {}
    )
    keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_atr14",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    present: List[str] = []
    missing: List[str] = []
    for key in keys:
        if feature_snapshot.get(key) is None:
            missing.append(key)
        else:
            present.append(key)
    return {
        "present": len(present),
        "total": len(keys),
        "present_keys": present,
        "missing_keys": missing,
    }


def normalized_feature_coverage(scanner: Dict[str, Any], selected_candidate: Dict[str, Any]) -> Dict[str, Any]:
    reported = scanner.get("feature_coverage") if isinstance(scanner.get("feature_coverage"), dict) else {}
    computed = feature_coverage(selected_candidate)
    present = safe_int(reported.get("present"), computed.get("present"))
    total = safe_int(reported.get("total"), computed.get("total"))
    coverage_ratio = safe_float(
        reported.get("coverage_ratio"),
        (present / total) if total > 0 else 0.0,
    )
    quality = str(reported.get("quality") or "").strip().lower()
    if not quality:
        if total <= 0:
            quality = "missing"
        elif coverage_ratio >= 0.75:
            quality = "strong"
        elif coverage_ratio >= 0.5:
            quality = "partial"
        else:
            quality = "weak"
    reported_present_keys = [str(x or "") for x in list(reported.get("present_keys") or []) if str(x or "").strip()]
    reported_missing_keys = [str(x or "") for x in list(reported.get("missing_keys") or []) if str(x or "").strip()]
    computed_present = safe_int(computed.get("present"), 0)
    computed_total = safe_int(computed.get("total"), 0)
    reported_key_counts_match = bool(
        reported_present_keys
        and len(reported_present_keys) == present
        and len(reported_present_keys) + len(reported_missing_keys) == total
    )
    computed_key_counts_match = computed_present == present and computed_total == total
    computed_present_keys = [
        str(x or "") for x in list(computed.get("present_keys") or []) if str(x or "").strip()
    ]
    computed_missing_keys = [
        str(x or "") for x in list(computed.get("missing_keys") or []) if str(x or "").strip()
    ]
    present_keys = reported_present_keys if reported_key_counts_match else (computed_present_keys if computed_key_counts_match else [])
    missing_keys = reported_missing_keys if reported_key_counts_match else (computed_missing_keys if computed_key_counts_match else [])
    return {
        "present": present,
        "total": total,
        "coverage_ratio": coverage_ratio,
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
    }


def confidence_label(value: Any) -> str:
    score = safe_float(value, -1.0)
    if score >= 0.85:
        return "high"
    if score >= 0.65:
        return "medium"
    if score >= 0.0:
        return "low"
    return "not_captured"


def execution_mode_label(executor: Dict[str, Any]) -> str:
    effective_mode = str(executor.get("effective_mode") or "").strip().lower()
    broker_env = str(executor.get("broker_env") or "").strip().lower()
    execution_mode = str(executor.get("execution_mode") or executor.get("mode") or "").strip().lower()
    kiwoom_mode = str(executor.get("kiwoom_mode") or "").strip().lower()
    if "mock" in effective_mode or broker_env == "mock" or kiwoom_mode == "mock":
        return "simulation (mock broker)"
    if broker_env == "real" or effective_mode == "real_broker_http":
        return "live broker"
    if execution_mode:
        return execution_mode
    return "decision only"


def classify_story_type(execution: Dict[str, Any], executor: Dict[str, Any]) -> str:
    effective_mode = str(executor.get("effective_mode") or "").strip().lower()
    broker_env = str(executor.get("broker_env") or "").strip().lower()
    kiwoom_mode = str(executor.get("kiwoom_mode") or "").strip().lower()
    execution_attempted = bool(executor.get("execution_attempted")) or bool(execution.get("action"))
    execution_ok = bool(executor.get("execution_ok"))
    if "mock" in effective_mode or broker_env == "mock" or kiwoom_mode == "mock":
        return "simulation"
    if not execution_attempted:
        return "decision_only"
    if execution_attempted and not execution_ok:
        return "failed_execution"
    return "live_trade"


def build_story_id(day: str, execution: Dict[str, Any]) -> str:
    run_id = slug(execution.get("run_id"), max_len=48)
    symbol = slug(execution.get("symbol"), max_len=24)
    action = slug(str(execution.get("action") or "").lower(), max_len=12)
    compact_day = str(day or "").replace("-", "")
    return slug(f"{compact_day}_{symbol}_{action}_{run_id}", max_len=96)


def build_story_contract(bundle_out: Dict[str, Any]) -> Dict[str, Any]:
    execution = bundle_out.get("execution") if isinstance(bundle_out.get("execution"), dict) else {}
    executor = bundle_out.get("executor") if isinstance(bundle_out.get("executor"), dict) else {}
    story_type = classify_story_type(execution, executor)
    mode_label = execution_mode_label(executor)
    story_anchor = (
        f"{execution.get('action') or 'WAIT'} {execution.get('symbol') or (bundle_out.get('scanner') or {}).get('top_stock') or '-'} "
        f"x{execution.get('qty') or 0} | run {bundle_out.get('run_id') or '-'}"
    )
    warnings: List[str] = []
    if story_type == "failed_execution":
        warnings.append("Execution was attempted but did not complete successfully.")
    if story_type == "simulation":
        warnings.append("This story reflects simulation mode, not a live broker fill.")
    return {
        "story_available": bool(execution.get("action") or execution.get("symbol") or (bundle_out.get("scanner") or {}).get("top_stock")),
        "story_type": story_type,
        "execution_mode_label": mode_label,
        "story_anchor": story_anchor,
        "warnings": warnings,
    }


def build_market_context_human(strategist: Dict[str, Any]) -> Dict[str, Any]:
    llm_parsed = strategist.get("llm_parsed_output") if isinstance(strategist.get("llm_parsed_output"), dict) else {}
    input_summary = strategist.get("input_summary") if isinstance(strategist.get("input_summary"), dict) else {}
    fear_index = strategist.get("fear_index") if isinstance(strategist.get("fear_index"), dict) else {}
    macro_overlay = strategist.get("macro_stress_overlay") if isinstance(strategist.get("macro_stress_overlay"), dict) else {}
    macro_moves = strategist.get("global_macro_moves") if isinstance(strategist.get("global_macro_moves"), dict) else {}
    news_context = strategist.get("news_context") if isinstance(strategist.get("news_context"), dict) else {}
    regime = str(llm_parsed.get("market_regime") or strategist.get("market_regime") or "not_captured")
    sentiment_state = str(llm_parsed.get("market_sentiment") or strategist.get("market_sentiment") or strategist.get("global_sentiment_status") or "not_captured")
    playbook = str(strategist.get("playbook") or llm_parsed.get("playbook") or "not_captured")
    themes = [str(x or "") for x in list(strategist.get("themes") or []) if str(x or "").strip()][:4]
    decision_frame = strategist.get("decision_frame") if isinstance(strategist.get("decision_frame"), dict) else {}
    theme_packet = strategist.get("theme_strength_packet") if isinstance(strategist.get("theme_strength_packet"), dict) else {}
    if not theme_packet and isinstance(decision_frame.get("theme_strength_packet"), dict):
        theme_packet = dict(decision_frame.get("theme_strength_packet") or {})
    theme_source = str(strategist.get("theme_source") or theme_packet.get("source") or "").strip()
    theme_status = str(strategist.get("theme_source_status") or theme_packet.get("status") or "").strip()
    theme_reason = str(strategist.get("theme_source_reason") or theme_packet.get("reason") or "").strip()
    theme_top = _list_text(theme_packet.get("top_themes"), limit=6, max_len=80)
    theme_scores = dict(theme_packet.get("theme_scores") or {}) if isinstance(theme_packet.get("theme_scores"), dict) else {}
    global_sentiment_score = strategist.get("global_sentiment_score")
    if global_sentiment_score in (None, ""):
        global_sentiment_score = input_summary.get("global_sentiment_score")
    if not fear_index and input_summary:
        fear_index = {
            "level": input_summary.get("vix_level"),
            "change_pct": input_summary.get("vix_change_pct"),
            "level_pressure": input_summary.get("vix_level_pressure"),
        }
    if not macro_moves and input_summary:
        macro_moves = {
            "vix_level": input_summary.get("vix_level"),
            "vix_pct": input_summary.get("vix_change_pct"),
            "vix_level_pressure": input_summary.get("vix_level_pressure"),
        }
    vix_level = (
        fear_index.get("level")
        if fear_index
        else macro_moves.get("vix_level")
        if macro_moves
        else macro_overlay.get("vix_level")
        if macro_overlay
        else input_summary.get("vix_level")
    )
    dxy_pct = (
        macro_moves.get("dxy_pct")
        if macro_moves
        else macro_overlay.get("dxy_pct")
        if macro_overlay
        else None
    )
    news_total = safe_int(
        news_context.get("headline_count"),
        safe_int(
            strategist.get("market_news_total_headlines"),
            safe_int(strategist.get("news_total_headlines"), safe_int(input_summary.get("headline_count"), 0)),
        ),
    )
    query_targets = _list_text(
        strategist.get("news_query_targets") or input_summary.get("news_query_targets") or [],
        limit=8,
        max_len=80,
    )
    query_count = safe_int(
        strategist.get("market_news_query_count"),
        safe_int(strategist.get("news_symbol_count"), len(query_targets)),
    )
    market_signal_total = safe_int(news_context.get("market_signal_total"), safe_int(input_summary.get("market_signal_total"), 0))
    candidate_signal_total = safe_int(news_context.get("candidate_signal_total"), safe_int(input_summary.get("candidate_signal_total"), 0))
    stress_flags = [str(x or "") for x in list(macro_overlay.get("stress_flags") or []) if str(x or "").strip()]
    defensive_mode = bool(macro_overlay.get("active")) or bool(stress_flags) or (safe_float(vix_level, 0.0) >= 25.0)
    market_news_titles = _list_text(input_summary.get("market_news_titles"), limit=3, max_len=140)
    candidate_news_titles = _list_text(input_summary.get("candidate_news_titles"), limit=3, max_len=140)
    key_events_hint = _list_text(input_summary.get("key_events_hint"), limit=5, max_len=180)
    strategist_evidence_trace = _build_strategist_evidence_trace(
        strategist,
        fallback_market_titles=market_news_titles,
        fallback_candidate_titles=candidate_news_titles,
    )
    candidate_hints = _list_text(
        strategist_evidence_trace.get("candidate_hints"),
        limit=8,
        max_len=24,
    )
    market_headlines = _list_text(
        strategist_evidence_trace.get("market_headlines"),
        limit=3,
        max_len=180,
    ) or market_news_titles
    symbol_headlines = _list_text(
        strategist_evidence_trace.get("symbol_headlines"),
        limit=3,
        max_len=180,
    ) or candidate_news_titles
    global_sentiment_signal = (
        dict(strategist_evidence_trace.get("global_sentiment_signal") or {})
        if isinstance(strategist_evidence_trace.get("global_sentiment_signal"), dict)
        else {}
    )
    if not global_sentiment_signal and isinstance(strategist.get("global_sentiment_signal"), dict):
        global_sentiment_signal = dict(strategist.get("global_sentiment_signal") or {})
    korea_indices = (
        dict(strategist.get("korea_indices") or {})
        if isinstance(strategist.get("korea_indices"), dict)
        else dict(global_sentiment_signal.get("korea_indices") or {})
        if isinstance(global_sentiment_signal.get("korea_indices"), dict)
        else dict(input_summary.get("korea_indices") or {})
        if isinstance(input_summary.get("korea_indices"), dict)
        else {}
    )
    korea_indices_text = _korea_indices_bullet(korea_indices)
    fear_index_trace = (
        dict(strategist_evidence_trace.get("fear_index") or {})
        if isinstance(strategist_evidence_trace.get("fear_index"), dict)
        else dict(fear_index or {})
    )
    key_events = _list_text(strategist_evidence_trace.get("key_events"), limit=6, max_len=180) or key_events_hint
    news_summary = (
        f"{news_total} headlines were considered across {query_count} targets "
        f"({market_signal_total} market / {candidate_signal_total} candidate signals)."
        if news_total > 0
        else "No strong news input was captured for this run."
    )
    stress_summary = (
        f"Macro stress was elevated because {', '.join(stress_flags)} remained active."
        if stress_flags
        else "No explicit macro stress flags were active in the strategist frame."
    )
    summary = (
        f"Market regime was {regime} with a {playbook} playbook. "
        f"Global sentiment scored {format_pct(global_sentiment_score)} and VIX was {format_pct(vix_level)}. "
        f"{stress_summary} {news_summary}"
    )
    if korea_indices_text:
        summary = f"{summary} Korea indices: {korea_indices_text}."
    bullets = [
        f"Market regime: {regime}",
        f"Market sentiment: {sentiment_state}",
        f"Playbook: {playbook}",
        f"Global sentiment score: {format_pct(global_sentiment_score)}",
        f"VIX / fear index level: {format_pct(vix_level)}",
        f"Dollar index move: {format_pct(dxy_pct)}%",
        f"Themes detected: {', '.join(themes) if themes else 'none captured'}",
        f"Defensive mode: {'enabled' if defensive_mode else 'not enabled'}",
        f"News input: {news_summary}",
    ]
    if korea_indices_text:
        bullets.append(f"Korea indices: {korea_indices_text}")
    if theme_packet or theme_source or theme_status or theme_reason:
        bullets.append(
            "Kiwoom theme packet: "
            f"source={theme_source or 'not_captured'}, "
            f"status={theme_status or 'not_captured'}, "
            f"reason={theme_reason or 'not_captured'}, "
            f"top_themes={', '.join(theme_top) if theme_top else 'none'}, "
            f"score_count={len(theme_scores)}"
        )
    if query_targets:
        bullets.append(f"News query targets: {', '.join(query_targets)}")
    if key_events_hint:
        bullets.append("Key strategist inputs: " + "; ".join(key_events_hint[:3]))
    if candidate_hints:
        bullets.append("Strategist candidate hints: " + ", ".join(candidate_hints[:5]))
    if market_headlines:
        bullets.append("Strategist market headlines: " + "; ".join(market_headlines[:3]))
    if symbol_headlines:
        bullets.append("Strategist symbol headlines: " + "; ".join(symbol_headlines[:3]))
    return {
        "regime": regime,
        "market_sentiment": sentiment_state,
        "playbook": playbook,
        "themes": themes,
        "theme_strength_packet": theme_packet,
        "theme_source": theme_source,
        "theme_source_status": theme_status,
        "theme_source_reason": theme_reason,
        "theme_strength_top_themes": theme_top,
        "theme_strength_scores": theme_scores,
        "global_sentiment_score": global_sentiment_score,
        "global_sentiment_signal": global_sentiment_signal,
        "korea_indices": korea_indices,
        "vix_level": vix_level,
        "fear_index": fear_index_trace,
        "stress_flags": stress_flags,
        "defensive_mode": defensive_mode,
        "headline_count": news_total,
        "news_query_count": query_count,
        "market_signal_total": market_signal_total,
        "candidate_signal_total": candidate_signal_total,
        "news_query_targets": query_targets,
        "key_events_hint": key_events_hint,
        "key_events": key_events,
        "candidate_hints": candidate_hints,
        "market_headlines": market_headlines,
        "symbol_headlines": symbol_headlines,
        "market_news_titles": market_headlines or market_news_titles,
        "candidate_news_titles": symbol_headlines or candidate_news_titles,
        "strategist_evidence_trace": strategist_evidence_trace,
        "news_input_summary": news_summary,
        "summary": summary,
        "bullets": bullets,
    }


def build_scanner_reason_human(scanner: Dict[str, Any], strategist: Dict[str, Any]) -> Dict[str, Any]:
    selected = scanner.get("selected_candidate") if isinstance(scanner.get("selected_candidate"), dict) else {}
    selected_symbol = str(selected.get("symbol") or scanner.get("top_stock") or "").strip()
    ranking_table = [dict(row) for row in list(scanner.get("ranking_table") or []) if isinstance(row, dict)]
    top_ranked_symbols = [str(row.get("symbol") or "").strip() for row in ranking_table if str(row.get("symbol") or "").strip()]
    if not top_ranked_symbols:
        top_ranked_symbols = [str(x or "") for x in list(scanner.get("top_ranked_symbols") or []) if str(x or "").strip()]
    selected_rank = 0
    selected_row = next(
        (row for row in ranking_table if str(row.get("symbol") or "").strip() == selected_symbol),
        {},
    )
    if selected_row:
        selected_rank = safe_int(selected_row.get("rank"), 0)
    elif selected_symbol and selected_symbol in top_ranked_symbols:
        selected_rank = int(top_ranked_symbols.index(selected_symbol) + 1)
    elif selected_symbol:
        selected_rank = 1
    universe_size = max(
        0,
        safe_int(scanner.get("universe_size"), 0)
        or safe_int(scanner.get("candidate_pool_after_filter"), 0)
        or safe_int(scanner.get("candidate_pool_before_filter"), 0)
        or len(ranking_table)
        or len(top_ranked_symbols),
    )
    selected_sources = [str(x or "") for x in list(selected.get("sources") or []) if str(x or "").strip()]
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    component_snapshot = selected.get("component_snapshot") if isinstance(selected.get("component_snapshot"), dict) else {}
    preview_map = {
        str(row.get("symbol") or "").strip(): dict(row)
        for row in list(scanner.get("candidate_preview") or [])
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    }
    basis: List[str] = []
    if safe_float(score_breakdown.get("trading_value"), 0.0) > 0:
        basis.append("trading value")
    if safe_float(score_breakdown.get("volume_surge"), 0.0) > 0 or "top_volume" in selected_sources:
        basis.append("turnover and volume")
    if safe_float(score_breakdown.get("theme_boost"), 0.0) > 0 or "sector_theme" in selected_sources:
        basis.append("theme and sector alignment")
    if safe_float(score_breakdown.get("sentiment"), 0.0) > 0:
        basis.append("sentiment support")
    if not basis:
        basis.append("combined scanner ranking score")
    coverage = normalized_feature_coverage(scanner, selected)
    selected_score = selected.get("score_total")
    if selected_score in (None, ""):
        selected_score = selected_row.get("score_total")
    selected_risk = selected.get("risk_score")
    if selected_risk in (None, ""):
        selected_risk = selected_row.get("risk_score")
    selected_confidence = selected.get("confidence")
    if selected_confidence in (None, ""):
        selected_confidence = selected_row.get("confidence")
    scanner_chart_fit = _scanner_chart_fit_payload(selected)
    if not scanner_chart_fit:
        scanner_chart_fit = _scanner_chart_fit_payload(selected_row)
    if not scanner_chart_fit:
        scanner_chart_fit = _scanner_chart_fit_payload(scanner)
    scanner_macro_chart_fit = _scanner_macro_chart_fit_payload(selected)
    if not scanner_macro_chart_fit:
        scanner_macro_chart_fit = _scanner_macro_chart_fit_payload(selected_row)
    if not scanner_macro_chart_fit:
        scanner_macro_chart_fit = _scanner_macro_chart_fit_payload(scanner)
    news_scanner_contribution = _build_news_scanner_contribution_trace(
        selected_symbol=selected_symbol,
        selected_score=selected_score,
        selected_sources=selected_sources,
        score_breakdown=score_breakdown,
        component_snapshot=component_snapshot,
        strategist=strategist if isinstance(strategist, dict) else {},
    )
    top_reasons: List[str] = [
        f"highest combined scanner score ({safe_float(selected_score, 0.0):.3f})",
        f"selected from {', '.join(selected_sources) if selected_sources else 'captured scanner sources'}",
        f"chart feature coverage {coverage['present']}/{coverage['total']}" if coverage["total"] > 0 else "chart feature coverage was not captured",
        f"aligned with strategist playbook {strategist.get('playbook') or 'not_captured'}",
    ]
    runner_ups: List[Dict[str, Any]] = []
    ranked_preview = ranking_table[:3] if ranking_table else []
    for row in ranked_preview:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol or symbol == selected_symbol:
            continue
        preview = preview_map.get(symbol, {})
        why_parts: List[str] = []
        preview_why = clip(preview.get("why") or row.get("why"), max_len=140)
        if preview_why:
            why_parts.append(preview_why)
        score_gap = None
        if selected_score not in (None, "") and row.get("score_total") not in (None, ""):
            score_gap = safe_float(selected_score, 0.0) - safe_float(row.get("score_total"), 0.0)
            why_parts.append(f"score gap {score_gap:.3f}")
        row_risk = row.get("risk_score")
        if selected_risk not in (None, "") and row_risk not in (None, "") and safe_float(row_risk, 0.0) > safe_float(selected_risk, 0.0):
            why_parts.append(
                f"higher risk ({safe_float(row_risk, 0.0):.3f} vs {safe_float(selected_risk, 0.0):.3f})"
            )
        row_confidence = row.get("confidence")
        if selected_confidence not in (None, "") and row_confidence not in (None, "") and safe_float(row_confidence, 0.0) < safe_float(selected_confidence, 0.0):
            why_parts.append(
                f"lower confidence ({safe_float(row_confidence, 0.0):.3f} vs {safe_float(selected_confidence, 0.0):.3f})"
            )
        runner_ups.append(
            {
                "symbol": symbol,
                "rank": safe_int(row.get("rank"), 0),
                "score_total": row.get("score_total"),
                "risk_score": row.get("risk_score"),
                "confidence": row.get("confidence"),
                "scanner_chart_fit": _scanner_chart_fit_payload(row),
                "scanner_macro_chart_fit": _scanner_macro_chart_fit_payload(row),
                "why": "; ".join(why_parts) if why_parts else "lower final ranking than the selected symbol",
            }
        )
        if len(runner_ups) >= 2:
            break
    top_candidates: List[Dict[str, Any]] = []
    for row in ranked_preview:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue
        top_candidates.append(
            {
                "rank": safe_int(row.get("rank"), 0),
                "symbol": symbol,
                "score_total": row.get("score_total"),
                "risk_score": row.get("risk_score"),
                "confidence": row.get("confidence"),
                "scanner_chart_fit": _scanner_chart_fit_payload(row),
                "scanner_macro_chart_fit": _scanner_macro_chart_fit_payload(row),
            }
        )
    bullets = [
        f"Universe scanned: {universe_size}",
        f"Selected rank: #{selected_rank}" if selected_rank else "Selected rank: not_captured",
        f"Ranking basis: {', '.join(basis)}",
        f"Selected because: {top_reasons[0]}",
        f"Selection sources: {', '.join(selected_sources) if selected_sources else 'not captured'}",
        f"Chart / feature coverage: {coverage['present']}/{coverage['total']}" if coverage["total"] else "Chart / feature coverage: not captured",
        (
            "Scanner chart-fit: "
            f"{safe_float(scanner_chart_fit.get('score'), 0.0):.3f} "
            f"({scanner_chart_fit.get('authority') or 'not_captured'})"
        )
        if scanner_chart_fit
        else "Scanner chart-fit: not captured",
        (
            "Scanner macro chart-fit: "
            f"{safe_float(scanner_macro_chart_fit.get('score'), 0.0):.3f} "
            f"(bias {safe_float(scanner_macro_chart_fit.get('bias'), 0.0):+.3f})"
        )
        if scanner_macro_chart_fit
        else "Scanner macro chart-fit: not captured",
        (
            "Core score contributions: "
            f"trading_value {safe_float(score_breakdown.get('trading_value'), 0.0):+.3f}, "
            f"momentum {safe_float(score_breakdown.get('momentum'), 0.0):+.3f}, "
            f"trend {safe_float(score_breakdown.get('trend'), 0.0):+.3f}, "
            f"theme_boost {safe_float(score_breakdown.get('theme_boost'), 0.0):+.3f}, "
            f"sentiment {safe_float(score_breakdown.get('sentiment'), 0.0):+.3f}"
        ),
    ]
    sentiment_inputs = news_scanner_contribution.get("sentiment_inputs") if isinstance(news_scanner_contribution.get("sentiment_inputs"), dict) else {}
    if any(sentiment_inputs.get(key) is not None for key in ("news_sentiment_score", "global_sentiment_score", "blended_sentiment_component")):
        bullets.append(
            "Sentiment input trace: "
            f"news={safe_float(sentiment_inputs.get('news_sentiment_score'), 0.0):+.3f}, "
            f"global={safe_float(sentiment_inputs.get('global_sentiment_score'), 0.0):+.3f}, "
            f"blended={safe_float(sentiment_inputs.get('blended_sentiment_component'), 0.0):+.3f}, "
            f"weighted_score={safe_float(sentiment_inputs.get('weighted_sentiment_score_contribution'), 0.0):+.3f}"
        )
    theme_trace = news_scanner_contribution.get("theme_alignment_trace") if isinstance(news_scanner_contribution.get("theme_alignment_trace"), dict) else {}
    bullets.append(
        "Theme linkage: "
        f"matched={bool(theme_trace.get('theme_source_matched'))}, "
        f"theme_boost={safe_float(theme_trace.get('theme_boost_score_contribution'), 0.0):+.3f}, "
        f"themes={', '.join(_list_text(theme_trace.get('strategist_themes'), limit=4, max_len=60)) or 'none captured'}, "
        f"source={theme_trace.get('theme_source') or 'not_captured'}, "
        f"status={theme_trace.get('theme_source_status') or 'not_captured'}, "
        f"reason={theme_trace.get('theme_source_reason') or 'not_captured'}"
    )
    news_linkage = news_scanner_contribution.get("news_linkage_trace") if isinstance(news_scanner_contribution.get("news_linkage_trace"), dict) else {}
    if safe_int(news_linkage.get("symbol_headline_count"), 0) > 0 or safe_int(news_linkage.get("market_headline_count"), 0) > 0:
        bullets.append(
            "News linkage to scanner: "
            f"symbol_headlines={safe_int(news_linkage.get('symbol_headline_count'), 0)}, "
            f"market_headlines={safe_int(news_linkage.get('market_headline_count'), 0)}, "
            f"query_targets={', '.join(_list_text(news_linkage.get('news_query_targets'), limit=5, max_len=60)) or 'not captured'}"
        )
    if top_candidates:
        bullets.append(
            "Top candidates: "
            + "; ".join(
                f"#{safe_int(row.get('rank'), 0)} {row.get('symbol')} score {safe_float(row.get('score_total'), 0.0):.3f}"
                for row in top_candidates
            )
        )
    if runner_ups:
        bullets.append("Why not others: " + "; ".join(f"{row['symbol']} was weaker because {row['why']}" for row in runner_ups))
    scanner_selection_trace = _build_scanner_selection_trace(
        {
            "selected_symbol": selected_symbol,
            "selected_rank": selected_rank,
            "top_candidates": top_candidates,
            "score_breakdown": score_breakdown,
            "selection_basis": "; ".join(top_reasons[:3]) if top_reasons else "",
            "summary": (
                f"Scanner selected {selected_symbol or '-'} as rank #{selected_rank or 1} out of {universe_size or 0} candidates."
            ),
            "scanner_chart_fit": dict(scanner_chart_fit or {}),
            "scanner_macro_chart_fit": dict(scanner_macro_chart_fit or {}),
        },
        scanner,
    )
    scanner_selection_trace["news_scanner_contribution"] = dict(news_scanner_contribution)
    return {
        "selected_symbol": selected_symbol,
        "selected_rank": selected_rank,
        "universe_size": universe_size,
        "selected_score": selected_score,
        "selected_sources": selected_sources,
        "source_scores": selected.get("source_scores") if isinstance(selected.get("source_scores"), dict) else {},
        "score_breakdown": score_breakdown,
        "ranking_basis": basis,
        "confidence": selected_confidence,
        "confidence_label": confidence_label(selected_confidence),
        "top_reasons": top_reasons,
        "top_candidates": top_candidates,
        "runner_ups": runner_ups,
        "ranked_candidates": list(scanner_selection_trace.get("ranked_candidates") or [])[:5],
        "selection_reason": clip(scanner_selection_trace.get("selection_reason"), max_len=260),
        "selected_symbol_score_drivers": dict(scanner_selection_trace.get("selected_symbol_score_drivers") or {}),
        "scanner_chart_fit": dict(scanner_chart_fit or {}),
        "scanner_macro_chart_fit": dict(scanner_macro_chart_fit or {}),
        "news_scanner_contribution": dict(news_scanner_contribution),
        "scanner_selection_trace": dict(scanner_selection_trace or {}),
        "q9_decision_id": str(scanner.get("q9_decision_id") or ""),
        "q9_decision_snapshot": dict(scanner.get("q9_decision_snapshot") or {})
        if isinstance(scanner.get("q9_decision_snapshot"), dict)
        else {},
        "q9_decision_snapshot_path": str(scanner.get("q9_decision_snapshot_path") or ""),
        "summary": (
            f"Scanner selected {selected_symbol or '-'} as rank #{selected_rank or 1} out of {universe_size or 0} candidates "
            f"with score {safe_float(selected_score, 0.0):.3f} because it led on {', '.join(basis[:3])}."
        ),
        "comparison": (
            f"{selected_symbol} ranked #{selected_rank} out of {universe_size} because it had the strongest overall blend of "
            f"{', '.join(basis[:3])}."
            if selected_symbol
            else "Scanner did not record a selected symbol for this run."
        ),
        "bullets": bullets,
    }


def enrich_scanner_reason_from_evidence(
    scanner_reason_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(scanner_reason_human or {})
    evidence = scanner_evidence if isinstance(scanner_evidence, dict) else {}
    reason_rows = [dict(row) for row in list(evidence.get("candidate_selection_reasons") or []) if isinstance(row, dict)]
    payload = (
        reason_rows[0].get("payload")
        if reason_rows and isinstance(reason_rows[0].get("payload"), dict)
        else {}
    )
    if not isinstance(payload, dict):
        payload = {}

    why_selected = [str(x or "") for x in list(payload.get("why_selected") or []) if str(x or "").strip()][:4]
    selection_basis = clip(payload.get("final_decision_basis"), max_len=260)
    tie_break_rule = clip(payload.get("tie_break_rule"), max_len=180)
    runner_ups_lost: List[Dict[str, Any]] = []
    for row in list(payload.get("runner_ups_lost") or payload.get("runner_up_reasons") or []):
        if not isinstance(row, dict):
            continue
        symbol = clip(row.get("symbol"), max_len=24)
        why_lost = [
            clip(x, max_len=140)
            for x in list(row.get("why_lost") or row.get("lost_because") or [])
            if clip(x, max_len=140)
        ][:4]
        summary = clip(row.get("summary") or "; ".join(why_lost), max_len=240)
        if not symbol and not summary:
            continue
        runner_ups_lost.append(
            {
                "symbol": symbol,
                "why_lost": why_lost,
                "summary": summary,
            }
        )
        if len(runner_ups_lost) >= 3:
            break

    selected_symbol = str(out.get("selected_symbol") or "").strip()
    selected_evidence_row = _scanner_candidate_row_from_evidence(
        scanner_evidence,
        selected_symbol=selected_symbol,
    )
    selected_evidence_score_breakdown = (
        selected_evidence_row.get("score_breakdown")
        if isinstance(selected_evidence_row.get("score_breakdown"), dict)
        else {}
    )
    selected_evidence_sources = [
        str(x or "")
        for x in list(selected_evidence_row.get("sources") or [])
        if str(x or "").strip()
    ]
    selected_evidence_has_selection_metrics = bool(
        selected_evidence_score_breakdown
        or selected_evidence_sources
        or selected_evidence_row.get("score_total") not in (None, "")
        or selected_evidence_row.get("rank") not in (None, "")
    )
    selected_evidence_basis = _selection_basis_from_scores(
        selected_evidence_score_breakdown,
        selected_evidence_sources,
    )
    if selected_evidence_row and selected_evidence_has_selection_metrics:
        selected_score = selected_evidence_row.get("score_total")
        out["selected_candidate"] = dict(selected_evidence_row)
        out["selected_score"] = selected_score
        out["selected_rank"] = safe_int(selected_evidence_row.get("rank"), safe_int(out.get("selected_rank"), 0))
        out["selected_sources"] = selected_evidence_sources
        out["score_breakdown"] = dict(selected_evidence_score_breakdown)
        out["ranking_basis"] = list(selected_evidence_basis)
        out["selected_symbol_score_drivers"] = _top_numeric_drivers(selected_evidence_score_breakdown)
        out["selection_reason"] = (
            f"final selected symbol {selected_symbol} ranked #{safe_int(out.get('selected_rank'), 0) or '?'} "
            f"with score {safe_float(selected_score, 0.0):.3f}; led on {', '.join(selected_evidence_basis[:3])}"
        )
        out["summary"] = (
            f"Scanner selected {selected_symbol or '-'} as rank #{safe_int(out.get('selected_rank'), 0) or 1} "
            f"with score {safe_float(selected_score, 0.0):.3f} because it led on {', '.join(selected_evidence_basis[:3])}."
        )
        news_scanner_contribution = (
            out.get("news_scanner_contribution")
            if isinstance(out.get("news_scanner_contribution"), dict)
            else {}
        )
        if news_scanner_contribution:
            core_rows = news_scanner_contribution.get("core_score_contributions")
            if isinstance(core_rows, dict):
                positive_total = sum(
                    max(safe_float(value, 0.0), 0.0)
                    for value in dict(selected_evidence_score_breakdown or {}).values()
                )
                for key in ("trading_value", "momentum", "trend", "theme_boost", "sentiment"):
                    value = safe_float(selected_evidence_score_breakdown.get(key), 0.0)
                    core_rows[key] = {
                        "value": value,
                        "positive_share_pct": (100.0 * value / positive_total) if positive_total > 0 else 0.0,
                    }
            theme_trace = news_scanner_contribution.get("theme_alignment_trace")
            if isinstance(theme_trace, dict):
                theme_score = safe_float(selected_evidence_score_breakdown.get("theme_boost"), 0.0)
                theme_trace["theme_boost_score_contribution"] = theme_score
                theme_trace["theme_source_matched"] = "sector_theme" in selected_evidence_sources or theme_score > 0.0
            out["news_scanner_contribution"] = news_scanner_contribution
    coverage = _normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    if coverage:
        out["feature_coverage"] = dict(coverage)
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        if present > 0 and total > 0:
            top_reasons = [str(x or "") for x in list(out.get("top_reasons") or []) if str(x or "").strip()]
            replaced_top_reason = False
            for idx, reason in enumerate(top_reasons):
                if reason.lower().startswith("chart feature coverage "):
                    top_reasons[idx] = f"chart feature coverage {present}/{total}"
                    replaced_top_reason = True
                    break
            if not replaced_top_reason:
                top_reasons.append(f"chart feature coverage {present}/{total}")
            out["top_reasons"] = top_reasons[:6]
            selection_reason = clip(out.get("selection_reason"), max_len=260)
            if selection_reason:
                if "chart feature coverage " in selection_reason.lower():
                    selection_reason = re.sub(
                        r"chart feature coverage\s+\d+/\d+",
                        f"chart feature coverage {present}/{total}",
                        selection_reason,
                        flags=re.IGNORECASE,
                    )
                else:
                    selection_reason = clip(f"{selection_reason}; chart feature coverage {present}/{total}", max_len=260)
            else:
                selection_reason = f"chart feature coverage {present}/{total}"
            out["selection_reason"] = selection_reason

    chart_fit = (
        out.get("scanner_chart_fit")
        if isinstance(out.get("scanner_chart_fit"), dict)
        else {}
    )
    if not chart_fit:
        chart_fit = _scanner_chart_fit_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
        if chart_fit:
            out["scanner_chart_fit"] = dict(chart_fit)
    macro_chart_fit = (
        out.get("scanner_macro_chart_fit")
        if isinstance(out.get("scanner_macro_chart_fit"), dict)
        else {}
    )
    if not macro_chart_fit:
        macro_chart_fit = _scanner_macro_chart_fit_from_scanner_evidence(
            scanner_evidence,
            selected_symbol=selected_symbol,
        )
        if macro_chart_fit:
            out["scanner_macro_chart_fit"] = dict(macro_chart_fit)

    if why_selected:
        out["why_selected"] = why_selected
    if selection_basis:
        out["selection_basis"] = selection_basis
    if tie_break_rule:
        out["tie_break_rule"] = tie_break_rule
    if runner_ups_lost:
        out["runner_ups_lost"] = runner_ups_lost

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    if selected_evidence_row and selected_evidence_has_selection_metrics:
        stale_prefixes = (
            "Selected because:",
            "Selection sources:",
            "Core score contributions:",
            "Theme linkage:",
        )
        bullets = [
            bullet
            for bullet in bullets
            if not any(bullet.startswith(prefix) for prefix in stale_prefixes)
        ]
        bullets.insert(
            0,
            (
                "Selected because: "
                f"{selected_symbol} rank #{safe_int(out.get('selected_rank'), 0) or '?'} "
                f"score {safe_float(out.get('selected_score'), 0.0):.3f}"
            ),
        )
        bullets.insert(
            1,
            "Selection sources: " + (", ".join(selected_evidence_sources) if selected_evidence_sources else "score_breakdown_only"),
        )
        bullets.insert(
            2,
            "Core score contributions: "
            f"trading_value {safe_float(selected_evidence_score_breakdown.get('trading_value'), 0.0):+.3f}, "
            f"momentum {safe_float(selected_evidence_score_breakdown.get('momentum'), 0.0):+.3f}, "
            f"trend {safe_float(selected_evidence_score_breakdown.get('trend'), 0.0):+.3f}, "
            f"theme_boost {safe_float(selected_evidence_score_breakdown.get('theme_boost'), 0.0):+.3f}, "
            f"sentiment {safe_float(selected_evidence_score_breakdown.get('sentiment'), 0.0):+.3f}",
        )
        theme_score = safe_float(selected_evidence_score_breakdown.get("theme_boost"), 0.0)
        bullets.insert(
            3,
            "Theme linkage: "
            f"matched={bool('sector_theme' in selected_evidence_sources or theme_score > 0.0)}, "
            f"theme_boost={theme_score:+.3f}",
        )
    if coverage:
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        updated_bullets: List[str] = []
        replaced_chart_bullet = False
        coverage_detail_inserted = False
        present_keys = [str(x or "") for x in list(coverage.get("present_keys") or []) if str(x or "").strip()]
        missing_keys = [str(x or "") for x in list(coverage.get("missing_keys") or []) if str(x or "").strip()]
        coverage_source = clip(coverage.get("source"), max_len=80)

        def _append_coverage_details(target: List[str]) -> None:
            nonlocal coverage_detail_inserted
            if coverage_detail_inserted:
                return
            if present_keys:
                target.append(
                    "Chart features present: " + ", ".join(present_keys[:8]) + (", ..." if len(present_keys) > 8 else "")
                )
            if missing_keys:
                target.append(
                    "Chart features missing: " + ", ".join(missing_keys[:8]) + (", ..." if len(missing_keys) > 8 else "")
                )
            if coverage_source:
                target.append(f"Chart feature coverage source: {coverage_source}")
            coverage_detail_inserted = True

        for bullet in bullets:
            if bullet.lower().startswith("chart / feature coverage:"):
                updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
                replaced_chart_bullet = True
                _append_coverage_details(updated_bullets)
            else:
                updated_bullets.append(bullet)
        if not replaced_chart_bullet and present > 0 and total > 0:
            updated_bullets.append(f"Chart / feature coverage: {present}/{total}")
            _append_coverage_details(updated_bullets)
        bullets = updated_bullets
    if chart_fit:
        fit_line = (
            "Scanner chart-fit: "
            f"{safe_float(chart_fit.get('score'), 0.0):.3f} "
            f"({chart_fit.get('authority') or 'not_captured'})"
        )
        if fit_line not in bullets:
            bullets.append(fit_line)
    if macro_chart_fit:
        macro_fit_line = (
            "Scanner macro chart-fit: "
            f"{safe_float(macro_chart_fit.get('score'), 0.0):.3f} "
            f"(bias {safe_float(macro_chart_fit.get('bias'), 0.0):+.3f})"
        )
        if macro_fit_line not in bullets:
            bullets.append(macro_fit_line)
    if why_selected:
        bullets.append("Selection decision: " + "; ".join(why_selected))
    if selection_basis:
        bullets.append(f"Final decision basis: {selection_basis}")
    if tie_break_rule:
        bullets.append(f"Tie-break rule: {tie_break_rule}")
    if runner_ups_lost:
        bullets.append(
            "Runner-ups lost because: "
            + "; ".join(
                f"{row.get('symbol')}: {row.get('summary')}" for row in runner_ups_lost if row.get("symbol")
            )
        )
    if bullets:
        deduped: List[str] = []
        seen: set[str] = set()
        for bullet in bullets:
            if bullet not in seen:
                deduped.append(bullet)
                seen.add(bullet)
        out["bullets"] = deduped[:12]
    trace = out.get("scanner_selection_trace") if isinstance(out.get("scanner_selection_trace"), dict) else {}
    if trace and coverage:
        trace["chart_feature_coverage"] = dict(coverage)
        out["scanner_selection_trace"] = trace
    if trace and chart_fit:
        trace["scanner_chart_fit"] = dict(chart_fit)
        out["scanner_selection_trace"] = trace
    if trace and macro_chart_fit:
        trace["scanner_macro_chart_fit"] = dict(macro_chart_fit)
        out["scanner_selection_trace"] = trace
    if selected_evidence_row and selected_evidence_has_selection_metrics:
        trace = dict(out.get("scanner_selection_trace") or {})
        trace["selected_symbol"] = selected_symbol
        trace["selected_rank"] = safe_int(out.get("selected_rank"), 0)
        trace["selected_symbol_score_drivers"] = dict(out.get("selected_symbol_score_drivers") or {})
        trace["selection_reason"] = str(out.get("selection_reason") or "")
        out["scanner_selection_trace"] = trace
    return out


def _scanner_chart_fit_from_scanner_evidence(
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip()
    if not symbol:
        return {}
    ranking_sources: List[Dict[str, Any]] = []
    for row in list((scanner_evidence or {}).get("candidate_ranking_tables") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("rows") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
    for row in list((scanner_evidence or {}).get("selection_outputs") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("ranking_top_n") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
        selected_candidate = payload.get("selected_candidate") if isinstance(payload.get("selected_candidate"), dict) else {}
        if selected_candidate:
            ranking_sources.append(selected_candidate)
    for row in ranking_sources:
        if str(row.get("symbol") or "").strip() != symbol:
            continue
        chart_fit = _scanner_chart_fit_payload(row)
        if chart_fit:
            return chart_fit
    return {}


def _scanner_macro_chart_fit_from_scanner_evidence(
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip()
    if not symbol:
        return {}
    ranking_sources: List[Dict[str, Any]] = []
    for row in list((scanner_evidence or {}).get("candidate_ranking_tables") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("rows") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
    for row in list((scanner_evidence or {}).get("selection_outputs") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("ranking_top_n") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
        selected_candidate = payload.get("selected_candidate") if isinstance(payload.get("selected_candidate"), dict) else {}
        if selected_candidate:
            ranking_sources.append(selected_candidate)
    for row in ranking_sources:
        if str(row.get("symbol") or "").strip() != symbol:
            continue
        chart_fit = _scanner_macro_chart_fit_payload(row)
        if chart_fit:
            return chart_fit
    return {}


def _normalized_feature_coverage_from_scanner_evidence(
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
) -> Dict[str, Any]:
    symbol = str(selected_symbol or "").strip()
    if not symbol:
        return {}

    ranking_sources: List[Dict[str, Any]] = []
    for row in list((scanner_evidence or {}).get("candidate_ranking_tables") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("rows") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
    for row in list((scanner_evidence or {}).get("selection_outputs") or []):
        payload = row.get("payload") if isinstance(row, dict) and isinstance(row.get("payload"), dict) else {}
        for ranking_row in list(payload.get("ranking_top_n") or []):
            if isinstance(ranking_row, dict):
                ranking_sources.append(ranking_row)
        selected_candidate = payload.get("selected_candidate") if isinstance(payload.get("selected_candidate"), dict) else {}
        if selected_candidate:
            ranking_sources.append(selected_candidate)

    matched_row: Dict[str, Any] = {}
    for row in ranking_sources:
        row_symbol = str(row.get("symbol") or "").strip()
        if row_symbol == symbol:
            matched_row = row
            break
    if not matched_row:
        return {}

    reported = matched_row.get("feature_coverage") if isinstance(matched_row.get("feature_coverage"), dict) else {}
    snapshot = matched_row.get("compact_feature_snapshot") if isinstance(matched_row.get("compact_feature_snapshot"), dict) else {}
    if not snapshot:
        snapshot = matched_row.get("feature_snapshot") if isinstance(matched_row.get("feature_snapshot"), dict) else {}
    if not snapshot and not reported:
        return {}

    keys = [
        "engine_ma20_gap",
        "engine_ma60",
        "engine_ma120",
        "engine_adx14",
        "engine_trend_strength",
        "engine_atr14",
        "engine_volume_spike20",
        "engine_volatility20",
        "engine_vwap_distance",
        "engine_sector_relative_strength",
        "engine_cross_section_rank",
        "engine_regime",
        "engine_signal_score",
    ]
    computed_present_keys = [key for key in keys if snapshot.get(key) is not None]
    computed_missing_keys = [key for key in keys if snapshot.get(key) is None]
    computed_total = len(keys)
    computed_present = len(computed_present_keys)
    present = safe_int(reported.get("present"), computed_present)
    total = safe_int(reported.get("total"), computed_total)
    coverage_ratio = safe_float(reported.get("coverage_ratio"), float(present) / float(total) if total else 0.0)
    quality = str(reported.get("quality") or "").strip().lower()
    if not quality:
        if coverage_ratio >= 0.75:
            quality = "strong"
        elif coverage_ratio >= 0.5:
            quality = "partial"
        else:
            quality = "weak"
    reported_present_keys = [str(x or "") for x in list(reported.get("present_keys") or []) if str(x or "").strip()]
    reported_missing_keys = [str(x or "") for x in list(reported.get("missing_keys") or []) if str(x or "").strip()]
    reported_key_counts_match = bool(
        reported_present_keys
        and len(reported_present_keys) == present
        and len(reported_present_keys) + len(reported_missing_keys) == total
    )
    computed_key_counts_match = computed_present == present and computed_total == total
    present_keys = reported_present_keys if reported_key_counts_match else (computed_present_keys if computed_key_counts_match else [])
    missing_keys = reported_missing_keys if reported_key_counts_match else (computed_missing_keys if computed_key_counts_match else [])
    coverage_source = "feature_coverage_reported" if reported else "snapshot_derived"
    return {
        "present": present,
        "total": total,
        "coverage_ratio": coverage_ratio,
        "quality": quality,
        "present_keys": present_keys,
        "missing_keys": missing_keys,
        "source": coverage_source,
    }


def enrich_filters_from_evidence(
    filters_human: Dict[str, Any],
    scanner_evidence: Dict[str, Any],
    *,
    selected_symbol: str,
    monitor_evidence: Optional[Dict[str, Any]] = None,
    entry_execution_details: Optional[Dict[str, Any]] = None,
    exit_execution_details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out = dict(filters_human or {})
    coverage = _normalized_feature_coverage_from_scanner_evidence(scanner_evidence, selected_symbol=selected_symbol)
    selected_evidence_row = _scanner_candidate_row_from_evidence(
        scanner_evidence,
        selected_symbol=selected_symbol,
    )
    theme_check_override: Optional[Dict[str, str]] = None
    if selected_evidence_row:
        score_breakdown = (
            selected_evidence_row.get("score_breakdown")
            if isinstance(selected_evidence_row.get("score_breakdown"), dict)
            else {}
        )
        sources = [
            str(x or "")
            for x in list(selected_evidence_row.get("sources") or [])
            if str(x or "").strip()
        ]
        if score_breakdown or sources:
            theme_score = safe_float(score_breakdown.get("theme_boost"), 0.0)
            theme_pass = "sector_theme" in sources or theme_score > 0.0
            theme_check_override = {
                "name": "sector/theme alignment",
                "status": "PASS" if theme_pass else "FAIL",
                "detail": (
                    f"final selected candidate theme boost was {theme_score:+.3f} or sector_theme source matched"
                    if theme_pass
                    else f"final selected candidate had no sector_theme source and theme boost was {theme_score:+.3f}"
                ),
            }
    price_anomaly_check: Optional[Dict[str, str]] = None
    execution_spread_check: Optional[Dict[str, str]] = None

    def _existing_chart_feature_total() -> int:
        texts: List[str] = [str(out.get("summary") or "")]
        texts.extend([str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()])
        for check in list(out.get("checks") or []):
            if isinstance(check, dict):
                texts.append(str(check.get("detail") or ""))
        for text in texts:
            match = re.search(r"\b\d+\s*/\s*(\d+)\s+captured(?:\s+chart)?\s+features\b", text, flags=re.IGNORECASE)
            if match:
                total_value = safe_int(match.group(1), 0)
                if total_value > 0:
                    return int(total_value)
        return 0

    if coverage and str(coverage.get("source") or "") == "snapshot_derived":
        existing_total = _existing_chart_feature_total()
        if existing_total > 0 and existing_total != safe_int(coverage.get("total"), 0):
            coverage = dict(coverage)
            present_count = safe_int(coverage.get("present"), 0)
            coverage["total"] = int(existing_total)
            coverage["coverage_ratio"] = float(present_count) / float(existing_total) if existing_total else 0.0
            if coverage["coverage_ratio"] >= 0.75:
                coverage["quality"] = "strong"
            elif coverage["coverage_ratio"] >= 0.5:
                coverage["quality"] = "partial"
            else:
                coverage["quality"] = "weak"
            coverage["source"] = "snapshot_derived_existing_filter_total"

    def _visit_monitor_payload(node: Any) -> None:
        nonlocal price_anomaly_check
        if price_anomaly_check is not None:
            return
        if isinstance(node, dict):
            if "price_anomaly_flag" in node:
                flagged = bool(node.get("price_anomaly_flag"))
                reason = str(node.get("price_anomaly_reason") or "").strip()
                price_anomaly_check = {
                    "name": "price anomaly filter",
                    "status": "FAIL" if flagged else "PASS",
                    "detail": reason if flagged and reason else ("monitor price cross-check flagged an anomaly" if flagged else "monitor price cross-check found no anomaly"),
                }
                return
            for value in node.values():
                _visit_monitor_payload(value)
                if price_anomaly_check is not None:
                    return
        elif isinstance(node, list):
            for value in node:
                _visit_monitor_payload(value)
                if price_anomaly_check is not None:
                    return

    _visit_monitor_payload(monitor_evidence)

    def _resolve_execution_spread_check() -> Optional[Dict[str, str]]:
        spread_threshold_bps = 50.0
        for details in (entry_execution_details, exit_execution_details):
            if not isinstance(details, dict):
                continue
            quote_snapshot = details.get("quote_snapshot") if isinstance(details.get("quote_snapshot"), dict) else {}
            spread_bps = details.get("spread_bps")
            if spread_bps in (None, ""):
                spread_bps = quote_snapshot.get("spread_bps")
            if spread_bps in (None, ""):
                continue
            spread_value = safe_float(spread_bps, None)
            if spread_value is None:
                continue
            return {
                "name": "spread/slippage filter",
                "status": "PASS" if spread_value <= spread_threshold_bps else "FAIL",
                "detail": f"execution quote snapshot spread was {spread_value:.1f} bps",
            }
        return None

    execution_spread_check = _resolve_execution_spread_check()
    coverage_quality = "missing"
    present = 0
    total = 0
    chart_status = "NOT_AVAILABLE"
    chart_note = "feature snapshot not available"
    chart_available = bool(coverage)
    if coverage:
        present = safe_int(coverage.get("present"), 0)
        total = safe_int(coverage.get("total"), 0)
        coverage_quality = str(coverage.get("quality") or "").strip().lower() or "missing"
        if total <= 0:
            chart_status = "NOT_AVAILABLE"
            chart_note = "feature snapshot not available"
        elif present >= 8:
            chart_status = "PASS"
            chart_note = f"{present}/{total} captured chart features"
        elif present >= 4:
            chart_status = "PARTIAL"
            chart_note = f"{present}/{total} captured chart features"
        else:
            chart_status = "FAIL"
            chart_note = f"{present}/{total} captured chart features"

    summary = str(out.get("summary") or "").strip()
    if chart_available:
        if summary:
            summary = re.sub(
                r"Chart completeness was [^.]*(?:\.)?",
                f"Chart completeness was {coverage_quality} with {present}/{total} captured features.",
                summary,
                flags=re.IGNORECASE,
            )
        else:
            summary = (
                "Scanner and guard checks were captured. "
                f"Chart completeness was {coverage_quality} with {present}/{total} captured features."
            )
        out["summary"] = summary

    checks = [dict(x) for x in list(out.get("checks") or []) if isinstance(x, dict)]
    updated_checks: List[Dict[str, Any]] = []
    replaced_check = False
    replaced_theme_check = False
    replaced_price_anomaly = False
    replaced_spread_check = False
    for check in checks:
        name = str(check.get("name") or "").strip().lower()
        if name == "chart completeness filter" and chart_available:
            check["status"] = chart_status
            check["detail"] = chart_note
            replaced_check = True
        elif name == "sector/theme alignment" and theme_check_override is not None:
            check["status"] = str(theme_check_override.get("status") or "")
            check["detail"] = str(theme_check_override.get("detail") or "")
            replaced_theme_check = True
        elif name == "price anomaly filter" and price_anomaly_check is not None:
            check["status"] = str(price_anomaly_check.get("status") or check.get("status") or "")
            check["detail"] = str(price_anomaly_check.get("detail") or check.get("detail") or "")
            replaced_price_anomaly = True
        elif name == "spread/slippage filter" and execution_spread_check is not None:
            current_status = str(check.get("status") or "").strip().upper()
            if current_status in {"", "NOT_AVAILABLE", "UNKNOWN"}:
                check["status"] = str(execution_spread_check.get("status") or check.get("status") or "")
                check["detail"] = str(execution_spread_check.get("detail") or check.get("detail") or "")
                replaced_spread_check = True
        updated_checks.append(check)
    if chart_available and not replaced_check:
        updated_checks.append(
            {
                "name": "chart completeness filter",
                "status": chart_status,
                "detail": chart_note,
            }
        )
    if theme_check_override is not None and not replaced_theme_check:
        updated_checks.append(dict(theme_check_override))
    if price_anomaly_check is not None and not replaced_price_anomaly:
        updated_checks.append(dict(price_anomaly_check))
    if execution_spread_check is not None and not replaced_spread_check:
        updated_checks.append(dict(execution_spread_check))
    if updated_checks:
        out["checks"] = updated_checks

    bullets = [str(x or "") for x in list(out.get("bullets") or []) if str(x or "").strip()]
    updated_bullets: List[str] = []
    replaced = False
    replaced_theme_bullet = False
    replaced_price_bullet = False
    replaced_spread_bullet = False
    for bullet in bullets:
        if bullet.lower().startswith("chart completeness filter:") and chart_available:
            updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
            replaced = True
        elif bullet.lower().startswith("sector/theme alignment:") and theme_check_override is not None:
            updated_bullets.append(
                f"sector/theme alignment: {theme_check_override['status']} - {theme_check_override['detail']}"
            )
            replaced_theme_bullet = True
        elif bullet.lower().startswith("price anomaly filter:") and price_anomaly_check is not None:
            updated_bullets.append(
                f"price anomaly filter: {price_anomaly_check['status']} - {price_anomaly_check['detail']}"
            )
            replaced_price_bullet = True
        elif bullet.lower().startswith("spread/slippage filter:") and execution_spread_check is not None:
            current_status = ""
            match = re.match(r"spread/slippage filter:\s*([A-Z_]+)\s*-", bullet, flags=re.IGNORECASE)
            if match:
                current_status = str(match.group(1) or "").strip().upper()
            if current_status in {"", "NOT_AVAILABLE", "UNKNOWN"}:
                updated_bullets.append(
                    f"spread/slippage filter: {execution_spread_check['status']} - {execution_spread_check['detail']}"
                )
                replaced_spread_bullet = True
            else:
                updated_bullets.append(bullet)
        else:
            updated_bullets.append(bullet)
    if chart_available and not replaced:
        updated_bullets.append(f"chart completeness filter: {chart_status} - {chart_note}")
    if theme_check_override is not None and not replaced_theme_bullet:
        updated_bullets.append(
            f"sector/theme alignment: {theme_check_override['status']} - {theme_check_override['detail']}"
        )
    if price_anomaly_check is not None and not replaced_price_bullet:
        updated_bullets.append(
            f"price anomaly filter: {price_anomaly_check['status']} - {price_anomaly_check['detail']}"
        )
    if execution_spread_check is not None and not replaced_spread_bullet:
        updated_bullets.append(
            f"spread/slippage filter: {execution_spread_check['status']} - {execution_spread_check['detail']}"
        )
    out["bullets"] = updated_bullets[:8]
    if coverage:
        out["feature_coverage"] = dict(coverage)
    return out


def build_filters_human(scanner: Dict[str, Any], strategist: Dict[str, Any], supervisor: Dict[str, Any]) -> Dict[str, Any]:
    selected = scanner.get("selected_candidate") if isinstance(scanner.get("selected_candidate"), dict) else {}
    sources = [str(x or "") for x in list(selected.get("sources") or []) if str(x or "").strip()]
    score_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    components = selected.get("component_snapshot") if isinstance(selected.get("component_snapshot"), dict) else {}
    feature_snapshot = selected.get("feature_snapshot") if isinstance(selected.get("feature_snapshot"), dict) else {}
    coverage = normalized_feature_coverage(scanner, selected)
    checks: List[Dict[str, str]] = []

    def add_check(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    liquidity_pass = "top_value" in sources or safe_float(components.get("trading_value_component"), 0.0) > 0
    turnover_pass = "top_volume" in sources or safe_float(score_breakdown.get("volume_surge"), 0.0) > 0
    theme_score = safe_float(score_breakdown.get("theme_boost"), 0.0)
    theme_pass = "sector_theme" in sources or theme_score > 0.0
    theme_detail = (
        f"selected candidate theme boost was {theme_score:+.3f} or sector_theme source matched"
        if theme_pass
        else f"selected candidate had no sector_theme source and theme boost was {theme_score:+.3f}"
    )
    if coverage["total"] <= 0:
        chart_status = "NOT_AVAILABLE"
    elif coverage["present"] >= 8:
        chart_status = "PASS"
    elif coverage["present"] >= 4:
        chart_status = "PARTIAL"
    else:
        chart_status = "FAIL"
    sentiment_gate = safe_float(components.get("sentiment_component"), 0.0) >= 0 or safe_float(
        strategist.get("global_sentiment_score"),
        0.0,
    ) > -0.35
    risk_gate = bool(supervisor.get("supervisor_allow")) and safe_float(selected.get("risk_score"), 0.0) <= 1.0
    spread_bps = selected.get("spread_bps")
    if spread_bps in (None, ""):
        spread_bps = feature_snapshot.get("quote_spread_bps")
    spread_bps = (safe_float(spread_bps, 0.0) if spread_bps not in (None, "") else None)
    spread_threshold_bps = 50.0
    spread_status = "NOT_AVAILABLE"
    spread_detail = "spread or slippage diagnostics were not captured in this run"
    if spread_bps is not None:
        spread_status = "PASS" if spread_bps <= spread_threshold_bps else "FAIL"
        spread_detail = f"scanner quote snapshot spread was {spread_bps:.1f} bps"

    add_check("liquidity filter", "PASS" if liquidity_pass else "FAIL", "top value or trading-value input supported the selection")
    add_check("turnover filter", "PASS" if turnover_pass else "FAIL", "top volume or turnover input supported the selection")
    add_check("sector/theme alignment", "PASS" if theme_pass else "FAIL", theme_detail)
    add_check("chart completeness filter", chart_status, f"{coverage['present']}/{coverage['total']} captured chart features")
    add_check("sentiment gate", "PASS" if sentiment_gate else "FAIL", f"news/global sentiment contribution was {safe_float(components.get('sentiment_component'), 0.0):.3f}")
    add_check("risk gate", "PASS" if risk_gate else "FAIL", f"risk score was {safe_float(selected.get('risk_score'), 0.0):.3f} and supervisor allow={bool(supervisor.get('supervisor_allow'))}")
    add_check("price anomaly filter", "NOT_AVAILABLE", "price anomaly check was not captured in this run")
    add_check("spread/slippage filter", spread_status, spread_detail)

    passed = sum(1 for row in checks if row["status"] == "PASS")
    bullets = [f"{row['name']}: {row['status']} - {row['detail']}" for row in checks]
    condition_status = str(scanner.get("condition_search_status") or "").strip()
    if condition_status:
        bullets.append(f"Condition search source: {condition_status} ({scanner.get('condition_search_reason') or 'no extra reason captured'})")
    coverage_quality = str(coverage.get("quality") or chart_status.lower()).strip().lower()
    return {
        "checks": checks,
        "summary": (
            f"Scanner and guard checks passed {passed} of {len(checks)} visible gates. "
            f"Chart completeness was {coverage_quality} with {coverage['present']}/{coverage['total']} captured features."
        ),
        "bullets": bullets,
    }


def build_monitor_reason_human(monitor: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper()
    decision_trace = monitor.get("decision_trace") if isinstance(monitor.get("decision_trace"), dict) else {}
    thresholds = monitor.get("thresholds") if isinstance(monitor.get("thresholds"), dict) else {}
    thresholds_guards_used = (
        decision_trace.get("thresholds_guards_used")
        if isinstance(decision_trace.get("thresholds_guards_used"), dict)
        else (
            monitor.get("thresholds_guards_used")
            if isinstance(monitor.get("thresholds_guards_used"), dict)
            else {}
        )
    )
    threshold_snapshot = (
        monitor.get("threshold_snapshot")
        if isinstance(monitor.get("threshold_snapshot"), dict)
        else {}
    )
    thresholds = _merge_missing_values(
        thresholds,
        thresholds_guards_used.get("thresholds") if isinstance(thresholds_guards_used.get("thresholds"), dict) else {},
    )
    for key in (
        "stop_loss_pct",
        "effective_stop_loss_pct",
        "effective_stop_reason",
        "take_profit_pct",
        "peak_drawdown_exit_pct",
        "trailing_stop_pct",
        "vwap_breakdown_pct",
        "intraday_low_break_pct",
        "trend_strength_floor",
    ):
        if thresholds.get(key) in (None, "", [], {}):
            thresholds[key] = monitor.get(key)
    trigger_details = monitor.get("trigger_details") if isinstance(monitor.get("trigger_details"), dict) else {}
    decision_reason_chain = [str(x or "") for x in list(monitor.get("decision_reason_chain") or []) if str(x or "").strip()]
    timing_assessment = decision_trace.get("timing_assessment") if isinstance(decision_trace.get("timing_assessment"), dict) else {}
    policy_ref = decision_trace.get("policy_ref") if isinstance(decision_trace.get("policy_ref"), dict) else {}
    received_policy = (
        monitor.get("received_policy")
        if isinstance(monitor.get("received_policy"), dict)
        else (
            threshold_snapshot.get("received_policy")
            if isinstance(threshold_snapshot.get("received_policy"), dict)
            else (
                policy_ref.get("received_policy")
                if isinstance(policy_ref.get("received_policy"), dict)
                else {}
            )
        )
    )
    effective_policy = (
        monitor.get("effective_policy")
        if isinstance(monitor.get("effective_policy"), dict)
        else (
            threshold_snapshot.get("effective_policy")
            if isinstance(threshold_snapshot.get("effective_policy"), dict)
            else (
                policy_ref.get("effective_policy")
                if isinstance(policy_ref.get("effective_policy"), dict)
                else {}
            )
        )
    )
    policy_adjustment_summary = str(
        monitor.get("policy_adjustment_summary")
        or threshold_snapshot.get("policy_adjustment_summary")
        or policy_ref.get("policy_adjustment_summary")
        or ""
    ).strip()
    effective_policy_deltas = [
        dict(row)
        for row in list(
            monitor.get("effective_policy_deltas")
            or threshold_snapshot.get("effective_policy_deltas")
            or policy_ref.get("effective_policy_deltas")
            or []
        )[:8]
        if isinstance(row, dict)
    ]
    entry_check_summary = str(decision_trace.get("entry_check_summary") or "").strip()
    entry_blockers = [str(x or "") for x in list(decision_trace.get("entry_blockers") or []) if str(x or "").strip()]
    entry_reason = str(
        timing_assessment.get("entry_reason")
        or monitor.get("entry_reason")
        or ""
    ).strip()
    entry_pattern = str(
        timing_assessment.get("entry_pattern")
        or monitor.get("entry_pattern")
        or ""
    ).strip()
    entry_signal_chain = [str(x or "") for x in list(monitor.get("entry_signal_chain") or []) if str(x or "").strip()]
    entry_condition_path = str(monitor.get("entry_condition_path") or "").strip()
    entry_condition_paths_passed = [str(x or "") for x in list(monitor.get("entry_condition_paths_passed") or []) if str(x or "").strip()]
    entry_condition_scores = monitor.get("entry_condition_scores") if isinstance(monitor.get("entry_condition_scores"), dict) else {}
    entry_grouped_logic_trace = monitor.get("entry_grouped_logic_trace") if isinstance(monitor.get("entry_grouped_logic_trace"), dict) else {}
    entry_metrics = monitor.get("entry_metrics") if isinstance(monitor.get("entry_metrics"), dict) else {}
    human_chart_detail_observed = (
        entry_metrics.get("human_chart_detail_observed")
        if isinstance(entry_metrics.get("human_chart_detail_observed"), dict)
        else {}
    )
    human_chart_detail_context = (
        monitor.get("human_chart_detail_context")
        if isinstance(monitor.get("human_chart_detail_context"), dict)
        else {}
    )
    if not human_chart_detail_observed and isinstance(human_chart_detail_context.get("observed"), dict):
        human_chart_detail_observed = dict(human_chart_detail_context.get("observed") or {})
    entry_thresholds = (
        monitor.get("entry_thresholds")
        if isinstance(monitor.get("entry_thresholds"), dict)
        else {}
    )
    if not entry_thresholds and isinstance(effective_policy, dict):
        entry_thresholds = dict(effective_policy or {})
    if not entry_thresholds and isinstance(monitor.get("applied_policy"), dict):
        entry_thresholds = dict(monitor.get("applied_policy") or {})
    if not entry_thresholds and isinstance(threshold_snapshot.get("entry_thresholds"), dict):
        entry_thresholds = dict(threshold_snapshot.get("entry_thresholds") or {})
    if not entry_thresholds and isinstance(threshold_snapshot.get("applied_policy"), dict):
        entry_thresholds = dict(threshold_snapshot.get("applied_policy") or {})
    entry_guard_blocked = bool(monitor.get("entry_guard_blocked"))
    entry_guard_reason = str(monitor.get("entry_guard_reason") or "").strip()
    entry_evaluated = bool(monitor.get("entry_evaluated"))
    entry_triggered = bool(monitor.get("entry_triggered"))
    exit_reason = str(monitor.get("exit_reason") or "").strip()
    monitor_reason = str(monitor.get("monitor_reason") or monitor.get("evaluation_summary") or "").strip()
    price_source = str(monitor.get("price_source") or "").strip()
    price_source_policy = str(monitor.get("price_source_policy") or "").strip()
    feature_source = str(monitor.get("feature_source") or "").strip()
    current_price = monitor.get("current_price")
    if current_price in (None, ""):
        current_price = monitor.get("price")
    average_price = monitor.get("average_price")
    if average_price in (None, ""):
        average_price = monitor.get("avg_price")
    peak_price = monitor.get("peak_price")
    peak_drawdown = monitor.get("peak_drawdown")
    current_drawdown = monitor.get("current_drawdown")
    vwap_distance = monitor.get("vwap_distance")
    hold_limit_sec = monitor.get("hold_limit_sec")
    if hold_limit_sec in (None, ""):
        hold_limit_sec = (
            thresholds.get("time_stop_sec")
            if safe_int(thresholds.get("time_stop_sec"), 0) > 0
            else thresholds.get("max_hold_sec")
        )
    time_limit_reached = bool(monitor.get("time_limit_reached"))
    time_limit_reason = str(monitor.get("time_limit_reason") or "").strip()
    time_limit_reassessment_required = bool(monitor.get("time_limit_reassessment_required"))
    time_limit_reassessment_blocked = bool(monitor.get("time_limit_reassessment_blocked"))
    time_limit_reassessment_blocked_reason = str(
        monitor.get("time_limit_reassessment_blocked_reason") or ""
    ).strip()
    if current_drawdown in (None, "") and current_price not in (None, "") and peak_price not in (None, ""):
        current_drawdown = (safe_float(current_price, 0.0) / max(safe_float(peak_price, 1.0), 1e-9)) - 1.0
    if current_drawdown in (None, "") and peak_drawdown not in (None, ""):
        current_drawdown = peak_drawdown

    watch_axes: List[str] = [str(x or "") for x in list(monitor.get("watch_axes") or trigger_details.get("watch_axes") or []) if str(x or "").strip()]
    if "Hard stop" not in watch_axes and (thresholds.get("hard_stop_pct") not in (None, "") or thresholds.get("stop_loss_pct") not in (None, "")):
        watch_axes.append("Hard stop")
    if "Take profit" not in watch_axes and thresholds.get("take_profit_pct") not in (None, ""):
        watch_axes.append("Take profit")
    if "Partial take profit" not in watch_axes and safe_float(thresholds.get("partial_take_profit_pct"), 0.0) > 0.0:
        watch_axes.append("Partial take profit")
    if "Profit ladder" not in watch_axes and isinstance(thresholds.get("profit_ladder_levels_pct"), list) and thresholds.get("profit_ladder_levels_pct"):
        watch_axes.append("Profit ladder")
    if "Risk/reward take profit" not in watch_axes and safe_float(thresholds.get("risk_reward_take_profit_r"), 0.0) > 0.0:
        watch_axes.append("Risk/reward take profit")
    elif "Risk/reward take profit" not in watch_axes and isinstance(thresholds.get("risk_reward_take_profit_rungs"), list) and thresholds.get("risk_reward_take_profit_rungs"):
        watch_axes.append("Risk/reward take profit")
    if "VWAP extension take profit" not in watch_axes and safe_float(thresholds.get("vwap_extension_take_profit_pct"), 0.0) > 0.0:
        watch_axes.append("VWAP extension take profit")
    if "Resistance take profit" not in watch_axes and safe_float(thresholds.get("resistance_take_profit_near_pct"), 0.0) > 0.0:
        watch_axes.append("Resistance take profit")
    if "Volume exhaustion take profit" not in watch_axes and safe_float(thresholds.get("volume_exhaustion_take_profit_min_pct"), 0.0) > 0.0:
        watch_axes.append("Volume exhaustion take profit")
    if "Opening gap profit take" not in watch_axes and safe_float(thresholds.get("opening_gap_profit_take_min_pct"), 0.0) > 0.0:
        watch_axes.append("Opening gap profit take")
    if "Time-decay profit exit" not in watch_axes and safe_float(thresholds.get("profit_time_stop_sec"), 0.0) > 0.0:
        watch_axes.append("Time-decay profit exit")
    if "Trailing stop" not in watch_axes and thresholds.get("trailing_stop_pct") not in (None, ""):
        watch_axes.append("Trailing stop")
    if "Peak drawdown" not in watch_axes and thresholds.get("peak_drawdown_exit_pct") not in (None, ""):
        watch_axes.append("Peak drawdown")
    if "VWAP breakdown" not in watch_axes and thresholds.get("vwap_breakdown_pct") not in (None, ""):
        watch_axes.append("VWAP breakdown")
    if "Intraday low break" not in watch_axes and thresholds.get("intraday_low_break_pct") not in (None, ""):
        watch_axes.append("Intraday low break")
    if "Trend breakdown" not in watch_axes and thresholds.get("trend_strength_floor") not in (None, ""):
        watch_axes.append("Trend breakdown")
    if "Volatility expansion" not in watch_axes and thresholds.get("vol_expansion_ratio") not in (None, ""):
        watch_axes.append("Volatility expansion")

    trigger_type = str(monitor.get("trigger_type") or "").strip()
    if not trigger_type:
        trigger_type = exit_reason if action == "SELL" else entry_reason or monitor_reason
    if not trigger_type and decision_reason_chain:
        trigger_type = decision_reason_chain[-1]
    active_exit_axis = str(monitor.get("active_exit_axis") or trigger_details.get("active_exit_axis") or "").strip()
    if str(monitor_reason or "").strip().lower() in {"hold", "hold_position", "eod_carry_approved"} and not bool(monitor.get("exit_triggered")):
        active_exit_axis = "Hold"
    elif not active_exit_axis:
        active_exit_axis = format_exit_label(trigger_type)
    confirm_required = safe_int(
        thresholds_guards_used.get("exit_confirm_ticks"),
        safe_int(thresholds_guards_used.get("exit_confirm_required"), safe_int(monitor.get("exit_confirm_required"), 0)),
    )
    confirm_count = safe_int(
        thresholds_guards_used.get("exit_confirm_count"),
        safe_int(monitor.get("exit_confirm_count"), 0),
    )
    guard_blocked = bool(trigger_details.get("sell_guard_blocked") or monitor.get("guard_blocked") or monitor.get("sell_guard_blocked"))
    guard_reason = str(trigger_details.get("sell_guard_reason") or monitor.get("guard_reason") or monitor.get("sell_guard_reason") or "").strip()
    exit_pending_confirmation = (
        guard_reason.startswith("exit_confirmation_pending:")
        or exit_reason.startswith("exit_confirmation_pending:")
        or monitor_reason == "exit_signal_pending_confirmation"
    )
    hold_without_confirmed_exit = bool(
        action == "SELL"
        and not bool(monitor.get("exit_triggered"))
        and str(trigger_type or monitor_reason or "").strip().lower() in {"hold", "hold_position"}
    )
    monitor_execution_mismatch = bool(
        action == "SELL"
        and not bool(monitor.get("exit_triggered"))
        and (exit_pending_confirmation or hold_without_confirmed_exit)
    )
    eod_carry_evaluated = bool(monitor.get("eod_carry_evaluated"))
    eod_carry_approved = bool(monitor.get("eod_carry_approved"))
    eod_carry_action = str(monitor.get("eod_carry_action") or "").strip()
    eod_carry_reason = str(monitor.get("eod_carry_reason") or "").strip()
    eod_carry_positive_signals = _list_text(monitor.get("eod_carry_positive_signals"), limit=6, max_len=120)
    eod_carry_blockers = _list_text(monitor.get("eod_carry_blockers"), limit=6, max_len=120)
    eod_carry_anomaly = bool(monitor.get("eod_carry_anomaly"))
    eod_carry_anomaly_reason = str(monitor.get("eod_carry_anomaly_reason") or "").strip()
    minutes_to_close = monitor.get("minutes_to_close")
    entry_threshold_gaps: List[str] = []
    if entry_metrics.get("volume_ratio") not in (None, "") and entry_thresholds.get("volume_ratio_min") not in (None, ""):
        volume_ratio = safe_float(entry_metrics.get("volume_ratio"), 0.0)
        volume_ratio_min = safe_float(entry_thresholds.get("volume_ratio_min"), 0.0)
        if volume_ratio < volume_ratio_min:
            entry_threshold_gaps.append(f"volume ratio {volume_ratio:.2f} below min {volume_ratio_min:.2f}")
    if entry_metrics.get("extended_from_vwap_pct") not in (None, "") and entry_thresholds.get("max_extended_from_vwap_pct") not in (None, ""):
        extended = safe_float(entry_metrics.get("extended_from_vwap_pct"), 0.0)
        extended_max = safe_float(entry_thresholds.get("max_extended_from_vwap_pct"), 0.0)
        if extended > extended_max:
            entry_threshold_gaps.append(
                f"VWAP extension {format_ratio_pct(extended)}% above max {format_ratio_pct(extended_max)}%"
            )
    if entry_metrics.get("pullback_depth_pct") not in (None, "") and entry_thresholds.get("pullback_min_pct") not in (None, ""):
        pullback_depth = safe_float(entry_metrics.get("pullback_depth_pct"), 0.0)
        pullback_min = safe_float(entry_thresholds.get("pullback_min_pct"), 0.0)
        if pullback_depth < pullback_min:
            entry_threshold_gaps.append(
                f"pullback depth {format_ratio_pct(pullback_depth)}% below min {format_ratio_pct(pullback_min)}%"
            )
    monitor_stop_policy_trace = _build_monitor_stop_policy_trace(monitor, thresholds)
    monitor_blocker_trace = _build_monitor_blocker_trace(
        {
            "entry_check_summary": entry_check_summary,
            "entry_blockers": entry_blockers,
            "entry_metrics": entry_metrics,
            "entry_thresholds": entry_thresholds,
            "timing_assessment": timing_assessment,
            "policy_ref": policy_ref,
            "entry_condition_path": entry_condition_path,
            "entry_condition_paths_passed": entry_condition_paths_passed,
            "condition_scores": entry_condition_scores,
            "grouped_logic_trace": entry_grouped_logic_trace,
        }
    )
    if eod_carry_approved and action not in ("BUY", "SELL"):
        summary = (
            f"Monitor kept the position into the close because overnight carry was approved "
            f"{safe_float(minutes_to_close, 0.0):.1f} minutes before the close."
        )
    elif action == "BUY":
        summary = f"BUY was triggered because {entry_reason or monitor_reason or 'the intraday entry condition passed'}."
        if entry_pattern:
            summary += f" Pattern: {entry_pattern}."
        if entry_condition_path:
            summary += f" Path: {entry_condition_path.replace('_', ' ')}."
    elif action == "SELL":
        if monitor_execution_mismatch:
            pending_label = (
                guard_reason
                or exit_reason
                or monitor_reason
                or (
                    "monitor posture was hold without a confirmed exit trigger"
                    if hold_without_confirmed_exit
                    else "exit confirmation was pending"
                )
            )
            summary = (
                "Executor recorded SELL, but the monitor had not confirmed the exit yet "
                f"({pending_label}). This is a monitor/executor mismatch, not a confirmed exit trigger."
            )
        elif eod_carry_evaluated and not eod_carry_approved and str(trigger_type or "").strip().lower() in ("eod_flat", "carry_overnight_approved"):
            summary = (
                f"SELL was triggered to flatten before the close because overnight carry was not approved "
                f"({eod_carry_reason or 'carry conditions were not met'})."
            )
        else:
            summary = f"SELL was triggered because {trigger_type or monitor_reason or 'the exit condition passed'}."
    elif eod_carry_anomaly:
        summary = (
            f"Monitor kept the position without a valid end-of-day carry decision because "
            f"{eod_carry_anomaly_reason or 'the carry evaluation context was incomplete'}."
        )
    elif entry_evaluated and not entry_triggered:
        summary = f"Monitor stayed on WAIT because {entry_check_summary or entry_reason or monitor_reason or 'the intraday entry signal was not confirmed'}."
        if entry_threshold_gaps:
            summary += " Threshold gaps: " + "; ".join(entry_threshold_gaps[:3]) + "."
    else:
        summary = f"Monitor posture was {action or 'WAIT'} with trigger {trigger_type or 'not_captured'}."
    bullets = [
        f"Posture: {action or 'WAIT'}",
        (
            f"Trigger type: {trigger_type or 'not_captured'} (pending, not confirmed)"
            if monitor_execution_mismatch
            else f"Trigger type: {trigger_type or 'not_captured'}"
        ),
        f"Monitor reason: {monitor_reason or trigger_type or 'not_captured'}",
        f"Position age: {safe_int(monitor.get('position_age_seconds'), 0)} seconds",
        f"Hold time limit: {safe_int(hold_limit_sec, 0)} seconds" if safe_int(hold_limit_sec, 0) > 0 else "Hold time limit: not configured",
        f"Stop loss: {format_ratio_pct(thresholds.get('stop_loss_pct'))}%",
        f"Effective stop: {format_ratio_pct(thresholds.get('effective_stop_loss_pct'))}%",
        f"Effective stop reason: {str(thresholds.get('effective_stop_reason') or 'not_captured')}",
        f"Take profit: {format_ratio_pct(thresholds.get('take_profit_pct'))}%",
        f"Active exit axis: {active_exit_axis or 'not_captured'}",
        f"Exit confirmation: {confirm_count}/{confirm_required}" if confirm_required > 0 else "Exit confirmation: not required",
        f"Min hold blocked: {'yes' if monitor.get('min_hold_blocked') else 'no'}",
        f"Sell cooldown blocked: {'yes' if monitor.get('sell_cooldown_blocked') else 'no'}",
        f"Exit triggered: {'yes' if monitor.get('exit_triggered') else 'no'}",
    ]
    if time_limit_reassessment_required:
        bullets.append(
            "Time-limit reassessment: "
            f"{'blocked by profit floor' if time_limit_reassessment_blocked else 'allowed'} "
            f"({time_limit_reassessment_blocked_reason or time_limit_reason or 'time limit reached'})"
        )
    if monitor_stop_policy_trace.get("hard_stop_pct") not in (None, ""):
        bullets.append(
            f"Hard fail-safe stop: {format_ratio_pct(monitor_stop_policy_trace.get('hard_stop_pct'))}%"
        )
    if monitor_stop_policy_trace.get("adaptive_stop_loss_pct") not in (None, ""):
        bullets.append(
            f"Active adaptive stop: {format_ratio_pct(monitor_stop_policy_trace.get('adaptive_stop_loss_pct'))}%"
        )
    if monitor_stop_policy_trace.get("strategist_baseline_stop_loss_pct") not in (None, ""):
        bullets.append(
            f"Strategist baseline adaptive stop: {format_ratio_pct(monitor_stop_policy_trace.get('strategist_baseline_stop_loss_pct'))}%"
        )
    if monitor_stop_policy_trace.get("effective_stop_loss_pct") not in (None, ""):
        bullets.append(
            f"Effective stop in this run: {format_ratio_pct(monitor_stop_policy_trace.get('effective_stop_loss_pct'))}%"
        )
    if monitor_stop_policy_trace.get("trailing_stop_pct") not in (None, ""):
        bullets.append(
            f"Trailing stop: {format_ratio_pct(monitor_stop_policy_trace.get('trailing_stop_pct'))}%"
        )
    if monitor_stop_policy_trace.get("strategist_baseline_trailing_stop_pct") not in (None, ""):
        bullets.append(
            f"Strategist baseline trailing stop: {format_ratio_pct(monitor_stop_policy_trace.get('strategist_baseline_trailing_stop_pct'))}%"
        )
    if monitor_stop_policy_trace.get("take_profit_pct") not in (None, ""):
        bullets.append(
            f"Take profit target: {format_ratio_pct(monitor_stop_policy_trace.get('take_profit_pct'))}%"
        )
    if bool(monitor_stop_policy_trace.get("cost_aware_profit_floor_enabled")) and safe_float(
        monitor_stop_policy_trace.get("cost_aware_profit_floor_pct"), 0.0
    ) > 0.0:
        bullets.append(
            "Cost-aware profit floor: "
            f"{format_ratio_pct(monitor_stop_policy_trace.get('cost_aware_profit_floor_pct'))}% "
            f"(round-trip cost {format_ratio_pct(monitor_stop_policy_trace.get('round_trip_cost_floor_pct'))}% "
            f"+ buffer {format_ratio_pct(monitor_stop_policy_trace.get('min_net_profit_buffer_pct'))}%)"
        )
    if safe_float(monitor_stop_policy_trace.get("partial_take_profit_pct"), 0.0) > 0.0:
        bullets.append(
            f"Partial take profit: {format_ratio_pct(monitor_stop_policy_trace.get('partial_take_profit_pct'))}%"
        )
    if isinstance(monitor_stop_policy_trace.get("profit_ladder_levels_pct"), list) and monitor_stop_policy_trace.get("profit_ladder_levels_pct"):
        bullets.append(
            "Profit ladder levels: "
            + ", ".join(f"{format_ratio_pct(level)}%" for level in list(monitor_stop_policy_trace.get("profit_ladder_levels_pct") or [])[:4])
        )
    if safe_float(monitor_stop_policy_trace.get("risk_reward_take_profit_r"), 0.0) > 0.0:
        bullets.append(f"Risk/reward take profit R: {monitor_stop_policy_trace.get('risk_reward_take_profit_r')}")
    elif isinstance(monitor_stop_policy_trace.get("risk_reward_take_profit_rungs"), list) and monitor_stop_policy_trace.get("risk_reward_take_profit_rungs"):
        bullets.append(
            "Risk/reward take profit rungs: "
            + ", ".join(str(x) for x in list(monitor_stop_policy_trace.get("risk_reward_take_profit_rungs") or [])[:4])
        )
    if safe_float(monitor_stop_policy_trace.get("vwap_extension_take_profit_pct"), 0.0) > 0.0:
        bullets.append(
            "VWAP extension take profit: "
            f"{format_ratio_pct(monitor_stop_policy_trace.get('vwap_extension_take_profit_pct'))}%"
        )
    if safe_float(monitor_stop_policy_trace.get("resistance_take_profit_near_pct"), 0.0) > 0.0:
        bullets.append(
            "Resistance take profit near: "
            f"{format_ratio_pct(monitor_stop_policy_trace.get('resistance_take_profit_near_pct'))}%"
        )
    if safe_float(monitor_stop_policy_trace.get("volume_exhaustion_take_profit_min_pct"), 0.0) > 0.0:
        bullets.append(
            "Volume exhaustion take profit min: "
            f"{format_ratio_pct(monitor_stop_policy_trace.get('volume_exhaustion_take_profit_min_pct'))}%"
        )
    if safe_float(monitor_stop_policy_trace.get("opening_gap_profit_take_min_pct"), 0.0) > 0.0:
        bullets.append(
            "Opening gap profit take min: "
            f"{format_ratio_pct(monitor_stop_policy_trace.get('opening_gap_profit_take_min_pct'))}%"
        )
    if safe_float(monitor_stop_policy_trace.get("profit_time_stop_sec"), 0.0) > 0.0:
        bullets.append(f"Profit time stop: {safe_int(monitor_stop_policy_trace.get('profit_time_stop_sec'), 0)} seconds")
    if monitor_stop_policy_trace.get("strategist_baseline_take_profit_pct") not in (None, ""):
        bullets.append(
            f"Strategist baseline take profit: {format_ratio_pct(monitor_stop_policy_trace.get('strategist_baseline_take_profit_pct'))}%"
        )
    if entry_evaluated:
        bullets.append(f"Entry triggered: {'yes' if entry_triggered else 'no'}")
        bullets.append(f"Entry pattern: {entry_pattern or 'not_captured'}")
        if entry_signal_chain:
            bullets.append("Entry signal chain: " + " -> ".join(entry_signal_chain[:6]))
        if entry_condition_path:
            bullets.append(f"Grouped entry path: {entry_condition_path}")
        if entry_condition_paths_passed:
            bullets.append("Grouped paths passed: " + ", ".join(entry_condition_paths_passed[:3]))
        if entry_condition_scores:
            bullets.append(
                "Condition scores: "
                + "; ".join(
                    [
                        f"{key}={safe_float(value, 0.0):.2f}"
                        for key, value in list(entry_condition_scores.items())[:6]
                        if value not in (None, "")
                    ]
                )
            )
        if entry_guard_blocked or entry_guard_reason:
            bullets.append(
                f"Entry guard blocked: {'yes' if entry_guard_blocked else 'no'} "
                f"({entry_guard_reason or 'no guard reason captured'})"
            )
        if entry_metrics.get("timeframe_minutes") not in (None, ""):
            bullets.append(f"Entry timeframe: {safe_int(entry_metrics.get('timeframe_minutes'), 1)}m")
        if entry_metrics.get("recent_high") not in (None, ""):
            bullets.append(f"Recent high: {safe_float(entry_metrics.get('recent_high'), 0.0):.2f}")
        if entry_metrics.get("breakout_level") not in (None, ""):
            bullets.append(f"Breakout level: {safe_float(entry_metrics.get('breakout_level'), 0.0):.2f}")
        if entry_metrics.get("vwap") not in (None, ""):
            bullets.append(f"Entry VWAP: {safe_float(entry_metrics.get('vwap'), 0.0):.2f}")
        if entry_metrics.get("volume_ratio") not in (None, ""):
            bullets.append(
                f"Volume ratio: {safe_float(entry_metrics.get('volume_ratio'), 0.0):.2f} "
                f"(min {safe_float(entry_thresholds.get('volume_ratio_min'), 0.0):.2f})"
            )
        if entry_metrics.get("extended_from_vwap_pct") not in (None, ""):
            bullets.append(
                f"Extended from VWAP: {format_ratio_pct(entry_metrics.get('extended_from_vwap_pct'))}% "
                f"(max {format_ratio_pct(entry_thresholds.get('max_extended_from_vwap_pct'))}%)"
            )
        if entry_metrics.get("pullback_depth_pct") not in (None, ""):
            pullback_bullet = f"Pullback depth: {format_ratio_pct(entry_metrics.get('pullback_depth_pct'))}%"
            if entry_thresholds.get("pullback_min_pct") not in (None, ""):
                pullback_bullet += f" (min {format_ratio_pct(entry_thresholds.get('pullback_min_pct'))}%)"
            if entry_thresholds.get("pullback_max_pct") not in (None, ""):
                pullback_bullet += f" (max {format_ratio_pct(entry_thresholds.get('pullback_max_pct'))}%)"
            bullets.append(pullback_bullet)
        if any(
            entry_metrics.get(key) not in (None, "")
            for key in (
                "human_candle_quality_score",
                "human_vwap_reference_quality_score",
                "human_reward_room_score",
                "human_multi_window_structure_score",
            )
        ):
            bullets.append(
                "Human chart setup quality: "
                f"candle {safe_float(entry_metrics.get('human_candle_quality_score'), 0.0):.2f}, "
                f"VWAP ref {safe_float(entry_metrics.get('human_vwap_reference_quality_score'), 0.0):.2f}, "
                f"reward room {safe_float(entry_metrics.get('human_reward_room_score'), 0.0):.2f}, "
                f"multi-window {safe_float(entry_metrics.get('human_multi_window_structure_score'), 0.0):.2f}"
            )
        if human_chart_detail_observed:
            candle_bits: List[str] = []
            if human_chart_detail_observed.get("close_location") not in (None, ""):
                candle_bits.append(f"close location {safe_float(human_chart_detail_observed.get('close_location'), 0.0):.2f}")
            if human_chart_detail_observed.get("upper_wick_ratio") not in (None, ""):
                candle_bits.append(f"upper wick {safe_float(human_chart_detail_observed.get('upper_wick_ratio'), 0.0):.2f}")
            if human_chart_detail_observed.get("lower_wick_ratio") not in (None, ""):
                candle_bits.append(f"lower wick {safe_float(human_chart_detail_observed.get('lower_wick_ratio'), 0.0):.2f}")
            if human_chart_detail_observed.get("body_ratio") not in (None, ""):
                candle_bits.append(f"body {safe_float(human_chart_detail_observed.get('body_ratio'), 0.0):.2f}")
            if candle_bits:
                bullets.append("Entry candle shape: " + ", ".join(candle_bits))
            vwap_bits: List[str] = []
            if human_chart_detail_observed.get("vwap_source") not in (None, ""):
                vwap_bits.append(f"source {human_chart_detail_observed.get('vwap_source')}")
            if human_chart_detail_observed.get("vwap_bar_count") not in (None, ""):
                vwap_bits.append(f"bars {safe_int(human_chart_detail_observed.get('vwap_bar_count'), 0)}")
            if human_chart_detail_observed.get("explicit_vwap_count") not in (None, ""):
                vwap_bits.append(f"explicit bars {safe_int(human_chart_detail_observed.get('explicit_vwap_count'), 0)}")
            if human_chart_detail_observed.get("explicit_vwap_ratio") not in (None, ""):
                vwap_bits.append(f"explicit ratio {safe_float(human_chart_detail_observed.get('explicit_vwap_ratio'), 0.0):.2f}")
            if vwap_bits:
                bullets.append("VWAP reference quality: " + ", ".join(vwap_bits))
            reward_bits: List[str] = []
            if human_chart_detail_observed.get("prior_resistance") not in (None, ""):
                reward_bits.append(f"resistance {safe_float(human_chart_detail_observed.get('prior_resistance'), 0.0):.2f}")
            if human_chart_detail_observed.get("reward_room_pct") not in (None, ""):
                reward_bits.append(f"room {format_ratio_pct(human_chart_detail_observed.get('reward_room_pct'))}%")
            if human_chart_detail_observed.get("breakout_extension_pct") not in (None, ""):
                reward_bits.append(
                    f"breakout extension {format_ratio_pct(human_chart_detail_observed.get('breakout_extension_pct'))}%"
                )
            if reward_bits:
                bullets.append("Reward room context: " + ", ".join(reward_bits))
        if entry_check_summary:
            bullets.append(f"Entry check summary: {entry_check_summary}")
        if entry_blockers:
            bullets.append("Entry blockers: " + "; ".join(entry_blockers[:6]))
        if entry_threshold_gaps:
            bullets.append("Threshold gaps: " + "; ".join(entry_threshold_gaps[:3]))
        if policy_adjustment_summary:
            bullets.append(f"Policy adjustment summary: {policy_adjustment_summary}")
        if effective_policy_deltas:
            bullets.append(
                "Effective policy deltas: "
                + "; ".join(
                    [
                        f"{str((row or {}).get('field') or '')}: {(row or {}).get('from')} -> {(row or {}).get('to')}"
                        for row in effective_policy_deltas[:4]
                        if str((row or {}).get("field") or "").strip()
                    ]
                )
            )
        if policy_ref:
            policy_bits: List[str] = []
            for key in ("monitor_mission", "flow_instruction", "risk_mode", "command_intent"):
                value = str(policy_ref.get(key) or "").strip()
                if value:
                    policy_bits.append(f"{key}={value}")
            if policy_bits:
                bullets.append("Policy reference: " + ", ".join(policy_bits[:4]))
    if eod_carry_evaluated:
        bullets.append(
            f"EOD carry decision: {'approved' if eod_carry_approved else 'flatten before close'} "
            f"({eod_carry_reason or 'not_captured'})"
        )
        if minutes_to_close not in (None, ""):
            bullets.append(f"Minutes to close at decision: {safe_float(minutes_to_close, 0.0):.1f}")
        if eod_carry_positive_signals:
            bullets.append("Carry positives: " + "; ".join(eod_carry_positive_signals[:4]))
        if eod_carry_blockers:
            bullets.append("Carry blockers: " + "; ".join(eod_carry_blockers[:4]))
    if eod_carry_anomaly:
        bullets.append(
            f"EOD carry anomaly: yes ({eod_carry_anomaly_reason or 'carry evaluation context missing'})"
        )
    if watch_axes:
        bullets.append("Watch axes: " + ", ".join(watch_axes[:8]))
    if decision_reason_chain:
        bullets.append("Decision chain: " + " -> ".join(decision_reason_chain[:5]))
    entry_quant_decision = monitor.get("entry_quant_decision") if isinstance(monitor.get("entry_quant_decision"), dict) else {}
    exit_quant_decision = monitor.get("exit_quant_decision") if isinstance(monitor.get("exit_quant_decision"), dict) else {}
    quant_factor_snapshot = monitor.get("quant_factor_snapshot") if isinstance(monitor.get("quant_factor_snapshot"), dict) else {}
    if entry_quant_decision:
        blockers = [str(x or "") for x in list(entry_quant_decision.get("blockers") or []) if str(x or "").strip()]
        warnings = [str(x or "") for x in list(entry_quant_decision.get("warnings") or []) if str(x or "").strip()]
        bullets.append(
            "Entry quant decision: "
            f"{entry_quant_decision.get('decision') or 'not_captured'} "
            f"(blockers: {', '.join(blockers[:4]) or 'none'}; warnings: {', '.join(warnings[:4]) or 'none'})"
        )
    if exit_quant_decision:
        blockers = [str(x or "") for x in list(exit_quant_decision.get("blockers") or []) if str(x or "").strip()]
        warnings = [str(x or "") for x in list(exit_quant_decision.get("warnings") or []) if str(x or "").strip()]
        bullets.append(
            "Exit quant decision: "
            f"{exit_quant_decision.get('decision') or 'not_captured'} "
            f"(blockers: {', '.join(blockers[:4]) or 'none'}; warnings: {', '.join(warnings[:4]) or 'none'})"
        )
    if guard_blocked or guard_reason:
        bullets.append(f"Guard blocked: {'yes' if guard_blocked else 'no'} ({guard_reason or 'no guard reason captured'})")
    if monitor_execution_mismatch:
        mismatch_label = (
            "SELL recorded while monitor posture was hold"
            if hold_without_confirmed_exit
            else "SELL recorded while monitor exit confirmation was pending"
        )
        bullets.append(f"Monitor/executor mismatch: yes ({mismatch_label})")
    if current_price not in (None, ""):
        bullets.append(f"Current price: {safe_float(current_price, 0.0):.2f}")
    if average_price not in (None, ""):
        bullets.append(f"Average price: {safe_float(average_price, 0.0):.2f}")
    if peak_price not in (None, ""):
        bullets.append(f"Peak price: {safe_float(peak_price, 0.0):.2f}")
    if current_drawdown not in (None, ""):
        bullets.append(f"Current drawdown: {format_ratio_pct(current_drawdown)}%")
    if peak_drawdown not in (None, ""):
        bullets.append(f"Peak drawdown: {format_ratio_pct(peak_drawdown)}%")
    if vwap_distance not in (None, ""):
        bullets.append(f"VWAP distance: {format_ratio_pct(vwap_distance)}%")
    if price_source:
        bullets.append(f"Price source: {price_source}")
    if feature_source:
        bullets.append(f"Feature source: {feature_source}")
    if price_source_policy:
        bullets.append(f"Price source policy: {price_source_policy}")
    return {
        "posture": action or "WAIT",
        "trigger_type": trigger_type,
        "summary": summary,
        "bullets": bullets,
        "position_age_seconds": safe_int(monitor.get("position_age_seconds"), 0),
        "hold_limit_sec": safe_int(hold_limit_sec, 0),
        "time_limit_reached": time_limit_reached,
        "time_limit_reason": time_limit_reason,
        "time_limit_reassessment_required": time_limit_reassessment_required,
        "time_limit_reassessment_blocked": time_limit_reassessment_blocked,
        "time_limit_reassessment_blocked_reason": time_limit_reassessment_blocked_reason,
        "stop_loss_pct": thresholds.get("stop_loss_pct"),
        "hard_stop_pct": monitor_stop_policy_trace.get("hard_stop_pct"),
        "adaptive_stop_loss_pct": monitor_stop_policy_trace.get("adaptive_stop_loss_pct"),
        "effective_stop_loss_pct": monitor_stop_policy_trace.get("effective_stop_loss_pct"),
        "effective_stop_reason": str(thresholds.get("effective_stop_reason") or "").strip(),
        "take_profit_pct": monitor_stop_policy_trace.get("take_profit_pct"),
        "trailing_stop_pct": monitor_stop_policy_trace.get("trailing_stop_pct"),
        "exit_triggered": bool(monitor.get("exit_triggered")),
        "entry_evaluated": entry_evaluated,
        "entry_triggered": entry_triggered,
        "entry_reason": entry_reason,
        "entry_pattern": entry_pattern,
        "entry_signal_chain": entry_signal_chain[:8],
        "entry_condition_path": entry_condition_path,
        "entry_condition_paths_passed": entry_condition_paths_passed[:4],
        "entry_condition_scores": dict(entry_condition_scores),
        "entry_grouped_logic_trace": dict(entry_grouped_logic_trace),
        "entry_metrics": dict(entry_metrics),
        "human_chart_detail_observed": dict(human_chart_detail_observed),
        "entry_thresholds": dict(entry_thresholds),
        "entry_check_summary": entry_check_summary,
        "entry_blockers": entry_blockers[:8],
        "threshold_shortfalls": entry_threshold_gaps[:4],
        "policy_ref": dict(policy_ref),
        "received_policy": dict(received_policy),
        "effective_policy": dict(effective_policy),
        "policy_adjustment_summary": policy_adjustment_summary,
        "effective_policy_deltas": effective_policy_deltas,
        "monitor_stop_policy_trace": monitor_stop_policy_trace,
        "monitor_blocker_trace": monitor_blocker_trace,
        "timing_assessment": dict(timing_assessment),
        "thresholds_guards_used": dict(thresholds_guards_used),
        "quant_factor_snapshot": dict(quant_factor_snapshot),
        "entry_quant_decision": dict(entry_quant_decision),
        "exit_quant_decision": dict(exit_quant_decision),
        "entry_guard_blocked": entry_guard_blocked,
        "entry_guard_reason": entry_guard_reason,
        "current_price": current_price,
        "average_price": average_price,
        "peak_price": peak_price,
        "current_drawdown": current_drawdown,
        "peak_drawdown": peak_drawdown,
        "vwap_distance": vwap_distance,
        "active_exit_axis": active_exit_axis,
        "watch_axes": watch_axes[:8],
        "confirm_required": confirm_required,
        "confirm_count": confirm_count,
        "guard_blocked": guard_blocked,
        "guard_reason": guard_reason,
        "pending_confirmation": exit_pending_confirmation,
        "monitor_execution_mismatch": monitor_execution_mismatch,
        "eod_carry_evaluated": eod_carry_evaluated,
        "eod_carry_approved": eod_carry_approved,
        "eod_carry_action": eod_carry_action,
        "eod_carry_reason": eod_carry_reason,
        "eod_carry_positive_signals": eod_carry_positive_signals,
        "eod_carry_blockers": eod_carry_blockers,
        "eod_carry_anomaly": eod_carry_anomaly,
        "eod_carry_anomaly_reason": eod_carry_anomaly_reason,
        "decision_reason_chain": decision_reason_chain[:6],
        "price_source": price_source,
        "feature_source": feature_source,
        "price_source_policy": price_source_policy,
    }


def build_guard_reason_human(supervisor: Dict[str, Any]) -> Dict[str, Any]:
    allow = bool(supervisor.get("supervisor_allow"))
    verdict = str(supervisor.get("verdict") or "").strip() or ("approve" if allow else "block")
    reason = str(supervisor.get("supervisor_reason") or supervisor.get("guard_reason") or "").strip() or "not captured"
    summary = (
        f"Supervisor approved the order because {reason}."
        if allow
        else f"Supervisor blocked the order because {reason}."
    )
    bullets = [
        f"Supervisor verdict: {verdict}",
        f"Supervisor allow: {'yes' if allow else 'no'}",
        f"Guard reason: {reason}",
        f"Action reviewed: {supervisor.get('action') or 'not_captured'}",
        f"Symbol reviewed: {supervisor.get('symbol') or 'not_captured'}",
        "Approval mode: not captured in the execution trace",
    ]
    return {"summary": summary, "bullets": bullets, "allow": allow, "verdict": verdict}


def build_execution_outcome_human(
    execution: Dict[str, Any],
    executor: Dict[str, Any],
    *,
    story_type: str,
    mode_label: str,
) -> Dict[str, Any]:
    return _build_execution_outcome_human_impl(
        execution,
        executor,
        story_type=story_type,
        mode_label=mode_label,
    )


def build_reporter_status_human(reporter: Dict[str, Any], reporter_day_obj: Dict[str, Any]) -> Dict[str, Any]:
    linked = bool(reporter.get("reporter_analysis_found"))
    day_file_found = bool(reporter.get("reporter_analysis_day_file_found"))
    ai_summary = str(reporter.get("reporter_analysis_summary") or reporter_day_obj.get("ai_summary") or "").strip()
    grade = str(reporter_day_obj.get("ai_run_grade") or "N/A").strip()
    if linked:
        status = "linked"
        reason = "당일 리포터 분석이 이 run에 연결됐습니다."
    elif day_file_found:
        status = "pending"
        reason = "당일 리포터 파일은 있지만 이 run에 대한 개별 평가는 아직 연결되지 않았습니다."
    else:
        status = "missing"
        reason = "당일 리포터 분석은 아직 생성되지 않았습니다."
    if status == "linked":
        summary = ai_summary or reason
    elif ai_summary:
        summary = f"{reason} 중간 요약: {ai_summary}"
    else:
        summary = reason
    bullets = [
        f"리포터 상태는 {status}입니다.",
        f"리포터 판단 사유는 {reason}입니다.",
        f"리포터 등급은 {grade}입니다.",
        f"리포터 요약은 {summary}입니다.",
    ]
    return normalize_reporter_status_human({
        "status": status,
        "reason": reason,
        "grade": grade,
        "summary": summary,
        "bullets": bullets,
    })


def build_operator_conclusion_human(
    *,
    execution: Dict[str, Any],
    scanner_reason_human: Dict[str, Any],
    filters_human: Dict[str, Any],
    monitor_reason_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
) -> Dict[str, Any]:
    action = str(execution.get("action") or "").upper() or "WAIT"
    outcome_text = str(execution_outcome_human.get("summary") or "").upper()
    outcome_ko = str(execution_outcome_human.get("summary") or "")
    if action != "SELL" and ("SELL" in outcome_text or "매도" in outcome_ko):
        action = "SELL"
    elif action not in {"BUY", "SELL"} and ("BUY" in outcome_text or "매수" in outcome_ko):
        action = "BUY"
    watch_next: List[str] = []
    invalidation: List[str] = [
        "거시 환경이 부정적으로 전환되는지 확인해야 합니다.",
        "테마나 섹터 강도가 약해지는지 확인해야 합니다.",
        "스캐너와 모니터 판단이 다시 어긋나는지 확인해야 합니다.",
    ]
    if action == "BUY":
        summary_prefix = "현재 판단은 진입 유지입니다."
        watch_next.append("보유 포지션의 손절과 익절 기준이 유지되는지 확인해야 합니다.")
        watch_next.append("선택된 테마와 종목의 상대 강도가 유지되는지 확인해야 합니다.")
    elif action == "SELL":
        summary_prefix = "현재 판단은 청산 완료입니다."
        watch_next.append("이번 청산이 방어적으로 타당했는지, 과도한 노이즈 청산은 아니었는지 복기해야 합니다.")
        watch_next.append("재진입은 쿨다운 이후 새 스캐너 확인이 있을 때만 검토해야 합니다.")
    elif action == "HOLD":
        summary_prefix = "현재 판단은 보유 유지입니다."
        watch_next.append("보유 근거가 약해지는지와 모니터 경고 축 변화를 계속 확인해야 합니다.")
    else:
        summary_prefix = "현재 판단은 관망입니다."
        watch_next.append("새로운 스캐너 순위와 모니터 확인이 나올 때까지 관망해야 합니다.")
    if reporter_status_human.get("status") != "linked":
        watch_next.append("동일 일자 리포터 분석 연계가 가능해지면 후속 확인이 필요합니다.")
    if "FAIL" in " ".join(row.get("status") or "" for row in list(filters_human.get("checks") or [])):
        watch_next.append("실패했거나 비어 있던 필터를 다시 확인하기 전에는 다음 사이클을 공격적으로 해석하면 안 됩니다.")
    summary = (
        f"{summary_prefix} "
        f"{execution_outcome_human.get('summary') or scanner_reason_human.get('summary') or monitor_reason_human.get('summary')}"
    )
    return {
        "current_action": action,
        "summary": summary,
        "watch_next": watch_next[:6],
        "thesis_invalidation": invalidation[:6],
    }


def build_timeline(
    *,
    commander: Dict[str, Any],
    market_context_human: Dict[str, Any],
    scanner_reason_human: Dict[str, Any],
    monitor_reason_human: Dict[str, Any],
    guard_reason_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
    execution: Dict[str, Any],
) -> List[Dict[str, Any]]:
    return _build_timeline_impl(
        commander=commander,
        market_context_human=market_context_human,
        scanner_reason_human=scanner_reason_human,
        monitor_reason_human=monitor_reason_human,
        guard_reason_human=guard_reason_human,
        execution_outcome_human=execution_outcome_human,
        reporter_status_human=reporter_status_human,
        execution=execution,
    )


def collect_story_warnings(
    *,
    story_contract: Dict[str, Any],
    market_context_human: Dict[str, Any],
    filters_human: Dict[str, Any],
    reporter_status_human: Dict[str, Any],
    execution_outcome_human: Dict[str, Any],
) -> List[str]:
    return _collect_story_warnings_impl(
        story_contract=story_contract,
        market_context_human=market_context_human,
        filters_human=filters_human,
        reporter_status_human=reporter_status_human,
        execution_outcome_human=execution_outcome_human,
    )


def _normalize_trade_lifecycle_for_story_input(
    bundle_out: Dict[str, Any],
    *,
    trade_lifecycle: Dict[str, Any] | None = None,
    existing_story_input: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    return _normalize_trade_lifecycle_for_story_input_impl(
        bundle_out,
        trade_lifecycle=trade_lifecycle,
        existing_story_input=existing_story_input,
    )


def build_trade_story_input_from_bundle(
    bundle_out: Dict[str, Any],
    *,
    trade_lifecycle: Dict[str, Any] | None = None,
    existing_story_input: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    normalized_lifecycle = _normalize_trade_lifecycle_for_story_input(
        bundle_out,
        trade_lifecycle=trade_lifecycle,
        existing_story_input=existing_story_input,
    )
    story_input = build_trade_story_input(
        bundle_out,
        trade_lifecycle=normalized_lifecycle if normalized_lifecycle else trade_lifecycle,
    )
    existing = existing_story_input if isinstance(existing_story_input, dict) else {}
    for key in (
        "report_runtime_mode",
        "skip_separated_report_llm",
        "entry_strategist_run_id",
        "strategy_anchor_run_id",
    ):
        if key not in story_input and key in existing:
            story_input[key] = existing.get(key)
    for key in ("trade_id", "day", "run_id"):
        if story_input.get(key) in (None, "", [], {}) and existing.get(key) not in (None, "", [], {}):
            story_input[key] = existing.get(key)
    return story_input


def _compact_canonical_monitor(canonical_monitor: Dict[str, Any] | None) -> Dict[str, Any]:
    return _compact_canonical_monitor_impl(canonical_monitor)


def build_trade_story_input(
    bundle_out: Dict[str, Any],
    *,
    trade_lifecycle: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    story_contract = bundle_out.get("story_contract") if isinstance(bundle_out.get("story_contract"), dict) else {}
    section_provenance = build_section_provenance(bundle_out)
    canonical_agent_artifacts = _hydrate_canonical_agent_artifacts(
        bundle_out,
        dict(bundle_out.get("canonical_agent_artifacts") or {}),
    )
    evidence_provenance = _derive_evidence_provenance(bundle_out)
    # Reporting layers prefer the canonical reasoning snapshot when it is already
    # mirrored into bundle inputs; otherwise they derive a compatible mirror.
    bundle_reasoning_trace = bundle_out.get("reasoning_trace") if isinstance(bundle_out.get("reasoning_trace"), dict) else {}
    bundle_reasoning_provenance = (
        bundle_out.get("reasoning_provenance") if isinstance(bundle_out.get("reasoning_provenance"), dict) else {}
    )
    lifecycle = (
        trade_lifecycle
        if isinstance(trade_lifecycle, dict)
        else bundle_out.get("trade_lifecycle")
        if isinstance(bundle_out.get("trade_lifecycle"), dict)
        else {}
    )
    if lifecycle:
        entry = lifecycle.get("entry") if isinstance(lifecycle.get("entry"), dict) else {}
        holding = lifecycle.get("holding") if isinstance(lifecycle.get("holding"), dict) else {}
        exit_ctx = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
        summary = lifecycle.get("summary") if isinstance(lifecycle.get("summary"), dict) else {}
        reporter = lifecycle.get("reporter") if isinstance(lifecycle.get("reporter"), dict) else {}
        symbol = str(
            lifecycle.get("symbol")
            or bundle_out.get("symbol")
            or (bundle_out.get("execution") or {}).get("symbol")
            or ""
        )
        authoritative_status = str(bundle_out.get("trade_lifecycle_status") or lifecycle.get("status") or "open").strip() or "open"
        status = authoritative_status
        entry_action = str(entry.get("action") or (bundle_out.get("execution") or {}).get("action") or "BUY")
        exit_action = str(exit_ctx.get("action") or "")
        exit_evidence = _has_substantive_exit_evidence(exit_ctx)
        if status.lower() == "open" and not exit_evidence:
            lifecycle_action = "HOLD" if entry_action else "WAIT"
        else:
            lifecycle_action = exit_action or entry_action or "WAIT"
        market_context_human = dict(bundle_out.get("market_context_human") or {})
        scanner_reason_human = dict(bundle_out.get("scanner_reason_human") or {})
        scanner_evidence = dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {})
        scanner_reason_human = enrich_scanner_reason_from_evidence(scanner_reason_human, scanner_evidence)
        filters_human = dict(bundle_out.get("filters_human") or {})
        filters_human = enrich_filters_from_evidence(
            filters_human,
            scanner_evidence,
            selected_symbol=str(scanner_reason_human.get("selected_symbol") or (entry.get("scanner_context") or {}).get("selected_symbol") or symbol),
            monitor_evidence=dict(bundle_out.get("monitor_evidence") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
            entry_execution_details=dict((entry.get("execution_details") if isinstance(entry.get("execution_details"), dict) else {}) or bundle_out.get("entry_execution_details") or {}),
            exit_execution_details=dict((exit_ctx.get("execution_details") if isinstance(exit_ctx.get("execution_details"), dict) else {}) or bundle_out.get("exit_execution_details") or {}),
        )
        monitor_reason_human = dict(bundle_out.get("monitor_reason_human") or {})
        guard_reason_human = dict(bundle_out.get("guard_reason_human") or {})
        execution_outcome_human = dict(bundle_out.get("execution_outcome_human") or {})
        reporter_status_human = normalize_reporter_status_human(dict(bundle_out.get("reporter_status_human") or {}))
        operator_conclusion_human = dict(bundle_out.get("operator_conclusion_human") or {})
        if not market_context_human:
            market_context_human = {
                "summary": str((entry.get("strategist_context") or {}).get("market_context_summary") or "Market context was not captured."),
                "bullets": [
                    f"Playbook: {str((entry.get('strategist_context') or {}).get('playbook') or 'not_captured')}",
                    "Lifecycle-level entry context was used.",
                ],
            }
        if not scanner_reason_human:
            scanner_reason_human = {
                "summary": str(entry.get("reason_human") or "Scanner selection rationale was not captured."),
                "bullets": [str(entry.get("reason_human") or "no scanner rationale captured")],
            }
        if not monitor_reason_human:
            monitor_reason_human = {
                "summary": (
                    f"Holding updates captured from {len(list(holding.get('run_ids') or []))} monitor runs."
                    if list(holding.get("run_ids") or [])
                    else "Holding monitor updates were not captured."
                ),
                "bullets": [str(x or "") for x in list(holding.get("monitor_updates") or [])[:8]],
            }
        synthesized_execution_outcome = build_execution_outcome_fallback_from_lifecycle(
            entry,
            exit_ctx,
            status=status,
            entry_action=entry_action,
            exit_action=exit_action,
            symbol=symbol,
        )
        if not execution_outcome_human or execution_outcome_summary_is_placeholder(execution_outcome_human.get("summary")):
            execution_outcome_human = dict(synthesized_execution_outcome)
        elif not execution_outcome_human.get("bullets"):
            execution_outcome_human["bullets"] = list(synthesized_execution_outcome.get("bullets") or [])
        if not str(execution_outcome_human.get("summary") or "").strip():
            execution_outcome_human = dict(synthesized_execution_outcome)
        if not str(execution_outcome_human.get("summary") or "").strip():
            execution_outcome_human = {
                "summary": str(summary.get("lifecycle_summary_human") or EXECUTION_OUTCOME_NOT_CAPTURED),
                "bullets": [
                    f"Lifecycle status: {status}",
                    f"Entry action: {entry_action or 'not_captured'}",
                    f"Exit action: {exit_action or 'not_captured'}",
                ],
            }
        if not reporter_status_human:
            reporter_status_human = {
                "status": str(reporter.get("status_human") or "missing"),
                "summary": str(reporter.get("summary") or REPORTER_LINKAGE_NOT_CAPTURED),
                "grade": str(reporter.get("grade") or "N/A"),
                "bullets": [str(x or "") for x in list(reporter.get("improvement_points") or [])[:6]],
            }
        reporter_status_human = normalize_reporter_status_human(reporter_status_human)
        synthesized_operator_conclusion = build_operator_conclusion_human(
            execution={
                "action": lifecycle_action,
                "status": status,
                "symbol": symbol,
            },
            scanner_reason_human=scanner_reason_human,
            filters_human=filters_human,
            monitor_reason_human=monitor_reason_human,
            execution_outcome_human=execution_outcome_human,
            reporter_status_human=reporter_status_human,
        )
        if (
            not operator_conclusion_human
            or lifecycle_conclusion_summary_is_placeholder(operator_conclusion_human.get("summary"))
        ):
            operator_conclusion_human = dict(synthesized_operator_conclusion)
        else:
            if not str(operator_conclusion_human.get("current_action") or "").strip():
                operator_conclusion_human["current_action"] = str(
                    synthesized_operator_conclusion.get("current_action") or ("HOLD" if status == "open" else lifecycle_action)
                )
            if not list(operator_conclusion_human.get("watch_next") or []):
                operator_conclusion_human["watch_next"] = list(synthesized_operator_conclusion.get("watch_next") or [])
            if not list(operator_conclusion_human.get("thesis_invalidation") or []):
                operator_conclusion_human["thesis_invalidation"] = list(
                    synthesized_operator_conclusion.get("thesis_invalidation") or []
                )
        if not str(operator_conclusion_human.get("summary") or "").strip():
            operator_conclusion_human["summary"] = str(summary.get("operator_conclusion_human") or LIFECYCLE_CONCLUSION_NOT_CAPTURED)
        canonical_strategist = (
            canonical_agent_artifacts.get("strategist")
            if isinstance(canonical_agent_artifacts.get("strategist"), dict)
            else bundle_out.get("strategist")
            if isinstance(bundle_out.get("strategist"), dict)
            else {}
        )
        canonical_scanner = (
            canonical_agent_artifacts.get("scanner")
            if isinstance(canonical_agent_artifacts.get("scanner"), dict)
            else bundle_out.get("scanner")
            if isinstance(bundle_out.get("scanner"), dict)
            else {}
        )
        canonical_monitor = (
            canonical_agent_artifacts.get("monitor")
            if isinstance(canonical_agent_artifacts.get("monitor"), dict)
            else bundle_out.get("monitor")
            if isinstance(bundle_out.get("monitor"), dict)
            else {}
        )
        strategy_horizon_feedback = (
            dict(bundle_out.get("strategy_horizon_feedback") or {})
            if isinstance(bundle_out.get("strategy_horizon_feedback"), dict)
            else dict(canonical_strategist.get("strategy_horizon_feedback") or {})
            if isinstance(canonical_strategist.get("strategy_horizon_feedback"), dict)
            else {}
        )
        exit_vs_strategy_intent = (
            dict(bundle_out.get("exit_vs_strategy_intent") or {})
            if isinstance(bundle_out.get("exit_vs_strategy_intent"), dict)
            else dict(canonical_monitor.get("exit_vs_strategy_intent") or {})
            if isinstance(canonical_monitor.get("exit_vs_strategy_intent"), dict)
            else dict((exit_ctx.get("monitor_context") or {}).get("exit_vs_strategy_intent") or {})
            if isinstance(exit_ctx.get("monitor_context"), dict)
            and isinstance((exit_ctx.get("monitor_context") or {}).get("exit_vs_strategy_intent"), dict)
            else {}
        )
        post_exit_shadow = (
            dict(bundle_out.get("post_exit_shadow") or {})
            if isinstance(bundle_out.get("post_exit_shadow"), dict)
            else dict(lifecycle.get("post_exit_shadow") or {})
            if isinstance(lifecycle.get("post_exit_shadow"), dict)
            else dict(exit_ctx.get("post_exit_shadow") or {})
            if isinstance(exit_ctx.get("post_exit_shadow"), dict)
            else {}
        )
        selection_monitor = _resolve_selection_monitor_artifact(bundle_out, canonical_agent_artifacts)
        scanner_selection_trace = _build_scanner_selection_trace(scanner_reason_human, canonical_scanner)
        scanner_reason_human, scanner_selection_trace, selected_symbol = reanchor_scanner_selection_for_monitor_fallback(
            scanner_reason_human=scanner_reason_human,
            scanner_selection_trace=scanner_selection_trace,
            scanner_artifact=canonical_scanner,
            monitor_artifact=selection_monitor,
            trade_symbol=symbol or str((bundle_out.get("execution") or {}).get("symbol") or ""),
        )
        raw_strategist_evidence = _raw_strategist_evidence(bundle_out)
        strategist_evidence_trace = _build_strategist_evidence_trace(
            _strategist_trace_source(canonical_strategist, raw_strategist_evidence),
            selected_symbol=selected_symbol,
            fallback_market_titles=market_context_human.get("market_news_titles"),
            fallback_candidate_titles=market_context_human.get("candidate_news_titles"),
        )
        _attach_news_scanner_contribution(
            scanner_reason_human=scanner_reason_human,
            scanner_selection_trace=scanner_selection_trace,
            canonical_scanner=canonical_scanner,
            canonical_strategist=canonical_strategist,
            selected_symbol=selected_symbol,
        )
        ranked_symbols = [
            str(row.get("symbol") or "").strip()
            for row in list(scanner_selection_trace.get("ranked_candidates") or [])
            if isinstance(row, dict) and str(row.get("symbol") or "").strip()
        ]
        news_symbol_linkage = build_news_symbol_linkage_view(
            strategist_summary=canonical_strategist,
            strategist_raw_input=raw_strategist_evidence,
            strategist_parsed_output=dict((bundle_out.get("strategist_summary") or {}).get("llm_parsed_output") or {}),
            selected_symbol=selected_symbol,
            top_ranked_symbols=ranked_symbols or canonical_scanner.get("top_ranked_symbols") or [],
        )
        monitor_stop_thresholds = (
            ((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"))
            if isinstance((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"), dict)
            else canonical_monitor.get("thresholds")
            if isinstance(canonical_monitor.get("thresholds"), dict)
            else canonical_monitor.get("threshold_snapshot")
            if isinstance(canonical_monitor.get("threshold_snapshot"), dict)
            else {}
        )
        monitor_stop_policy_trace = _build_monitor_stop_policy_trace(
            canonical_monitor,
            monitor_stop_thresholds,
        )
        monitor_blocker_trace = _build_monitor_blocker_trace(monitor_reason_human)
        market_context_human.setdefault("candidate_hints", strategist_evidence_trace.get("candidate_hints") or [])
        market_context_human.setdefault("market_headlines", strategist_evidence_trace.get("market_headlines") or [])
        selected_symbol_headlines = list(strategist_evidence_trace.get("symbol_headlines") or [])
        market_context_human["symbol_headlines"] = selected_symbol_headlines
        market_context_human["symbol_news_titles"] = selected_symbol_headlines
        market_context_human["candidate_news_titles"] = selected_symbol_headlines
        market_context_human["strategist_evidence_trace"] = dict(strategist_evidence_trace)
        market_context_human["news_symbol_linkage"] = dict(news_symbol_linkage)
        _set_or_replace_placeholder(
            scanner_reason_human,
            "scanner_selection_trace",
            dict(scanner_selection_trace),
        )
        _set_or_replace_placeholder(
            scanner_reason_human,
            "ranked_candidates",
            list(scanner_selection_trace.get("ranked_candidates") or []),
        )
        scanner_reason_human.setdefault("selection_reason", scanner_selection_trace.get("selection_reason"))
        scanner_reason_human.setdefault(
            "selected_symbol_score_drivers",
            dict(scanner_selection_trace.get("selected_symbol_score_drivers") or {}),
        )
        _set_or_replace_placeholder(
            monitor_reason_human,
            "monitor_stop_policy_trace",
            dict(monitor_stop_policy_trace),
        )
        _set_or_replace_placeholder(
            monitor_reason_human,
            "monitor_blocker_trace",
            dict(monitor_blocker_trace),
        )
        report_section_seeds = build_report_section_seeds(
            market_context_human=market_context_human,
            scanner_reason_human=scanner_reason_human,
            filters_human=filters_human,
            monitor_reason_human=monitor_reason_human,
            execution_outcome_human=execution_outcome_human,
            guard_reason_human=guard_reason_human,
            reporter_status_human=reporter_status_human,
            operator_conclusion_human=operator_conclusion_human,
        )
        derived_reasoning_trace = build_reasoning_trace_from_summaries(
            commander_summary=dict(bundle_out.get("commander_summary") or {}),
            strategist_summary=dict(bundle_out.get("strategist_summary") or {}),
            scanner_summary=dict(bundle_out.get("scanner_summary") or {}),
            monitor_summary=dict(bundle_out.get("monitor_summary") or {}),
            report_section_seeds=report_section_seeds,
            market_context_human=market_context_human,
            scanner_reason_human=scanner_reason_human,
            monitor_reason_human=monitor_reason_human,
            operator_conclusion_human=operator_conclusion_human,
        )
        reasoning_trace = normalize_reasoning_trace_aliases(
            {
                "reasoning_trace": bundle_reasoning_trace,
                "latest_reasoning_trace": bundle_out.get("latest_reasoning_trace"),
            },
            fallback=derived_reasoning_trace,
        )
        commander_source_priority = _commander_reasoning_source_priority(bundle_out, dict(bundle_out.get("commander_summary") or {}))
        derived_reasoning_provenance = build_reasoning_provenance(
            commander_context_source="canonical" if canonical_agent_artifacts.get("canonical_commander_json") or canonical_agent_artifacts.get("canonical_commander") else str(evidence_provenance.get("commander") or ""),
            strategist_plan_source=str(
                (section_provenance.get("market_context_human") or {}).get("source")
                or evidence_provenance.get("strategist")
                or ("canonical" if canonical_agent_artifacts.get("canonical_strategist_json") or canonical_agent_artifacts.get("canonical_strategist") else "")
            ),
            scanner_reason_source=str(
                (section_provenance.get("scanner_reason_human") or {}).get("source")
                or evidence_provenance.get("scanner")
                or ("canonical" if canonical_agent_artifacts.get("canonical_scanner_json") or canonical_agent_artifacts.get("canonical_scanner") else "")
            ),
            monitor_reason_source=str(
                (section_provenance.get("monitor_reason_human") or {}).get("source")
                or evidence_provenance.get("monitor")
                or ("canonical" if canonical_agent_artifacts.get("canonical_monitor_json") or canonical_agent_artifacts.get("canonical_monitor") else "")
            ),
            commander_source_ref=_resolve_commander_source_ref(canonical_agent_artifacts, section_provenance),
            strategist_source_ref=str(
                canonical_agent_artifacts.get("canonical_strategist_json")
                or canonical_agent_artifacts.get("canonical_strategist")
                or (section_provenance.get("market_context_human") or {}).get("artifact_path")
                or ""
            ),
            scanner_source_ref=str(
                canonical_agent_artifacts.get("canonical_scanner_json")
                or canonical_agent_artifacts.get("canonical_scanner")
                or (section_provenance.get("scanner_reason_human") or {}).get("artifact_path")
                or ""
            ),
            monitor_source_ref=str(
                canonical_agent_artifacts.get("canonical_monitor_json")
                or canonical_agent_artifacts.get("canonical_monitor")
                or (section_provenance.get("monitor_reason_human") or {}).get("artifact_path")
                or ""
            ),
            shadow_used=_commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "shadow_used"),
            strategist_fallback_used=(
                _commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "strategist_fallback_used")
                or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
            ),
            source_priority=commander_source_priority,
        )
        reasoning_provenance = normalize_reasoning_provenance_aliases(
            {
                "reasoning_provenance": bundle_reasoning_provenance,
                "latest_reasoning_trace_provenance": bundle_out.get("latest_reasoning_trace_provenance"),
            },
            fallback=derived_reasoning_provenance,
        )
        if isinstance(bundle_out.get("commander"), dict) or isinstance(bundle_out.get("latest_reasoning_trace_provenance"), dict):
            reasoning_provenance["shadow_used"] = _commander_reasoning_flag(
                bundle_out,
                dict(bundle_out.get("commander_summary") or {}),
                "shadow_used",
            )
            reasoning_provenance["strategist_fallback_used"] = (
                _commander_reasoning_flag(
                    bundle_out,
                    dict(bundle_out.get("commander_summary") or {}),
                    "strategist_fallback_used",
                )
                or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
            )
            if commander_source_priority:
                reasoning_provenance["source_priority"] = list(commander_source_priority)
        section_provenance_out = dict(section_provenance)
        section_provenance_out["report_section_provenance_seeds"] = build_report_section_provenance_seeds(
            section_provenance_out,
        )
        story_artifacts = dict(bundle_out.get("artifacts") or {})
        if isinstance(lifecycle.get("artifacts"), dict):
            for key, value in dict(lifecycle.get("artifacts") or {}).items():
                if key not in story_artifacts or _is_empty_placeholder(story_artifacts.get(key)):
                    story_artifacts[key] = value
        entry_monitor_context = dict(entry.get("monitor_context") or {})
        if isinstance(selection_monitor, dict) and (
            selection_monitor.get("entry_triggered")
            or (isinstance(selection_monitor.get("monitor_focus_context"), dict)
                and selection_monitor.get("monitor_focus_context", {}).get("entry_triggered"))
        ):
            entry_monitor_context = dict(selection_monitor)
            if isinstance(entry.get("monitor_context"), dict) and entry.get("monitor_context"):
                entry_monitor_context.setdefault("entry_artifact_context", dict(entry.get("monitor_context") or {}))
        story_out = {
            "schema_version": "trade_story_input.v2",
            "day": str(bundle_out.get("day") or ""),
            "trade_id": str(lifecycle.get("trade_id") or bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
            "story_id": str(lifecycle.get("trade_id") or bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
            "run_id": str(bundle_out.get("run_id") or entry.get("run_id") or ""),
            "symbol": symbol,
            "action": lifecycle_action,
            "status": status,
            "story_type": str(story_contract.get("story_type") or lifecycle.get("story_type") or ""),
            "execution_mode_label": str(story_contract.get("execution_mode_label") or lifecycle.get("execution_mode_label") or ""),
            "entry_summary": {
                "run_id": str(entry.get("run_id") or ""),
                "ts": str(entry.get("ts") or ""),
                "action": entry_action,
                "reason_human": str(entry.get("reason_human") or ""),
                "strategist_context": dict(entry.get("strategist_context") or {}),
                "scanner_context": dict(entry.get("scanner_context") or {}),
                "monitor_context": entry_monitor_context,
                "guard_context": dict(entry.get("guard_context") or {}),
                "execution_context": dict(entry.get("execution_context") or {}),
            },
            "holding_summary": {
                "run_ids": [str(x or "") for x in list(holding.get("run_ids") or []) if str(x or "").strip()],
                "holding_events": [dict(x) for x in list(holding.get("holding_events") or []) if isinstance(x, dict)][:20],
                "posture_history": [dict(x) for x in list(holding.get("posture_history") or []) if isinstance(x, dict)][:20],
                "monitor_updates": [str(x or "") for x in list(holding.get("monitor_updates") or []) if str(x or "").strip()][:20],
                "hold_duration": str(holding.get("hold_duration") or bundle_out.get("hold_duration") or ""),
                "hold_duration_sec": holding.get("hold_duration_sec") if holding.get("hold_duration_sec") is not None else bundle_out.get("hold_duration_sec"),
                "holding_phase_summary": str(holding.get("holding_phase_summary") or bundle_out.get("holding_phase_summary") or ""),
                "hold_events_count": holding.get("hold_events_count") if holding.get("hold_events_count") is not None else bundle_out.get("hold_events_count"),
                "monitor_context_snapshots": [dict(x) for x in list(holding.get("monitor_context_snapshots") or bundle_out.get("monitor_context_snapshots") or []) if isinstance(x, dict)][:20],
                "hold_signal_transitions": [dict(x) for x in list(holding.get("hold_signal_transitions") or bundle_out.get("hold_signal_transitions") or []) if isinstance(x, dict)][:20],
                "pre_exit_context_summary": dict(holding.get("pre_exit_context_summary") or bundle_out.get("pre_exit_context_summary") or {}),
            },
            "exit_summary": {
                "run_id": str(exit_ctx.get("run_id") or ""),
                "ts": str(exit_ctx.get("ts") or ""),
                "action": exit_action,
                "reason_human": str(exit_ctx.get("reason_human") or ""),
                "monitor_context": dict(exit_ctx.get("monitor_context") or {}),
                "guard_context": dict(exit_ctx.get("guard_context") or {}),
                "execution_context": dict(exit_ctx.get("execution_context") or {}),
            },
            "lifecycle_summary": {
                "holding_duration": str(summary.get("holding_duration") or ""),
                "entry_reason_human": str(summary.get("entry_reason_human") or ""),
                "exit_reason_human": str(summary.get("exit_reason_human") or ""),
                "lifecycle_summary_human": str(summary.get("lifecycle_summary_human") or ""),
                "operator_conclusion_human": str(summary.get("operator_conclusion_human") or ""),
            },
            "market_context_human": market_context_human,
            "scanner_reason_human": scanner_reason_human,
            "canonical_monitor": _compact_canonical_monitor(canonical_monitor),
            "strategy_horizon_feedback": dict(strategy_horizon_feedback),
            "strategy_horizon": str(
                bundle_out.get("strategy_horizon")
                or canonical_strategist.get("strategy_horizon")
                or strategy_horizon_feedback.get("strategy_horizon")
                or ""
            ),
            "exit_vs_strategy_intent": dict(exit_vs_strategy_intent),
            "post_exit_shadow": dict(post_exit_shadow),
            "filters_human": filters_human,
            "monitor_reason_human": monitor_reason_human,
            "guard_reason_human": guard_reason_human,
            "execution_outcome_human": execution_outcome_human,
            "reporter_status_human": reporter_status_human,
            "same_day_reporter_linkage": dict(
                lifecycle.get("same_day_reporter_linkage")
                if isinstance(lifecycle.get("same_day_reporter_linkage"), dict)
                else bundle_out.get("same_day_reporter_linkage")
                if isinstance(bundle_out.get("same_day_reporter_linkage"), dict)
                else {}
            ),
            "operator_conclusion_human": operator_conclusion_human,
            "timeline": [dict(x) for x in list(lifecycle.get("timeline") or bundle_out.get("timeline") or []) if isinstance(x, dict)][:40],
            "warnings": [str(x or "") for x in list(bundle_out.get("warnings") or lifecycle.get("warnings") or []) if str(x or "").strip()][:20],
            "improvement_points": [str(x or "") for x in list(reporter.get("improvement_points") or []) if str(x or "").strip()][:12],
            "strategist_evidence": raw_strategist_evidence,
            "strategist_candidate_hints": list(strategist_evidence_trace.get("candidate_hints") or [])[:8],
            "strategist_market_headlines": list(strategist_evidence_trace.get("market_headlines") or [])[:3],
            "strategist_symbol_headlines": list(strategist_evidence_trace.get("symbol_headlines") or [])[:3],
            "strategist_evidence_trace": dict(strategist_evidence_trace),
            "news_symbol_linkage": dict(news_symbol_linkage),
            "scanner_evidence": scanner_evidence,
            "scanner_selection_trace": dict(scanner_selection_trace),
            "monitor_timeline": dict(bundle_out.get("monitor_timeline") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
            "monitor_stop_policy_trace": dict(monitor_stop_policy_trace),
            "monitor_blocker_trace": dict(monitor_blocker_trace),
            "artifacts": story_artifacts,
            "canonical_agent_artifacts": canonical_agent_artifacts,
            "evidence_provenance": evidence_provenance,
            "section_provenance": section_provenance_out,
            "report_section_seeds": dict(report_section_seeds),
            "reasoning_trace": dict(reasoning_trace),
            "reasoning_provenance": dict(reasoning_provenance),
            "evidence_source": "canonical" if any(
                str(source or "").strip().lower() == "canonical"
                for source in evidence_provenance.values()
            ) else "direct_artifact",
            "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
            "execution_details": dict(bundle_out.get("execution_details") or lifecycle.get("execution_details") or {}),
            "entry_execution_details": dict((entry.get("execution_details") if isinstance(entry.get("execution_details"), dict) else {}) or bundle_out.get("entry_execution_details") or {}),
            "exit_execution_details": dict((exit_ctx.get("execution_details") if isinstance(exit_ctx.get("execution_details"), dict) else {}) or bundle_out.get("exit_execution_details") or {}),
            "failure_classification": dict(bundle_out.get("failure_classification") or lifecycle.get("failure_classification") or {}),
        }
        story_out["strategist_feedback_input"] = build_strategist_feedback_input_view(story_out)
        return story_out

    report_section_seeds = build_report_section_seeds(
        market_context_human=dict(bundle_out.get("market_context_human") or {}),
        scanner_reason_human=dict(bundle_out.get("scanner_reason_human") or {}),
        filters_human=dict(bundle_out.get("filters_human") or {}),
        monitor_reason_human=dict(bundle_out.get("monitor_reason_human") or {}),
        execution_outcome_human=dict(bundle_out.get("execution_outcome_human") or {}),
        guard_reason_human=dict(bundle_out.get("guard_reason_human") or {}),
        reporter_status_human=normalize_reporter_status_human(dict(bundle_out.get("reporter_status_human") or {})),
        operator_conclusion_human=dict(bundle_out.get("operator_conclusion_human") or {}),
    )
    derived_reasoning_trace = build_reasoning_trace_from_summaries(
        commander_summary=dict(bundle_out.get("commander_summary") or {}),
        strategist_summary=dict(bundle_out.get("strategist_summary") or {}),
        scanner_summary=dict(bundle_out.get("scanner_summary") or {}),
        monitor_summary=dict(bundle_out.get("monitor_summary") or {}),
        report_section_seeds=report_section_seeds,
        market_context_human=dict(bundle_out.get("market_context_human") or {}),
        scanner_reason_human=dict(bundle_out.get("scanner_reason_human") or {}),
        monitor_reason_human=dict(bundle_out.get("monitor_reason_human") or {}),
        operator_conclusion_human=dict(bundle_out.get("operator_conclusion_human") or {}),
    )
    reasoning_trace = normalize_reasoning_trace_aliases(
        {
            "reasoning_trace": bundle_reasoning_trace,
            "latest_reasoning_trace": bundle_out.get("latest_reasoning_trace"),
        },
        fallback=derived_reasoning_trace,
    )
    commander_source_priority = _commander_reasoning_source_priority(bundle_out, dict(bundle_out.get("commander_summary") or {}))
    derived_reasoning_provenance = build_reasoning_provenance(
        commander_context_source="canonical" if canonical_agent_artifacts.get("canonical_commander_json") or canonical_agent_artifacts.get("canonical_commander") else str(evidence_provenance.get("commander") or ""),
        strategist_plan_source=str(
            (section_provenance.get("market_context_human") or {}).get("source")
            or evidence_provenance.get("strategist")
            or ("canonical" if canonical_agent_artifacts.get("canonical_strategist_json") or canonical_agent_artifacts.get("canonical_strategist") else "")
        ),
        scanner_reason_source=str(
            (section_provenance.get("scanner_reason_human") or {}).get("source")
            or evidence_provenance.get("scanner")
            or ("canonical" if canonical_agent_artifacts.get("canonical_scanner_json") or canonical_agent_artifacts.get("canonical_scanner") else "")
        ),
        monitor_reason_source=str(
            (section_provenance.get("monitor_reason_human") or {}).get("source")
            or evidence_provenance.get("monitor")
            or ("canonical" if canonical_agent_artifacts.get("canonical_monitor_json") or canonical_agent_artifacts.get("canonical_monitor") else "")
        ),
        commander_source_ref=_resolve_commander_source_ref(canonical_agent_artifacts, section_provenance),
        strategist_source_ref=str(
            canonical_agent_artifacts.get("canonical_strategist_json")
            or canonical_agent_artifacts.get("canonical_strategist")
            or (section_provenance.get("market_context_human") or {}).get("artifact_path")
            or ""
        ),
        scanner_source_ref=str(
            canonical_agent_artifacts.get("canonical_scanner_json")
            or canonical_agent_artifacts.get("canonical_scanner")
            or (section_provenance.get("scanner_reason_human") or {}).get("artifact_path")
            or ""
        ),
        monitor_source_ref=str(
            canonical_agent_artifacts.get("canonical_monitor_json")
            or canonical_agent_artifacts.get("canonical_monitor")
            or (section_provenance.get("monitor_reason_human") or {}).get("artifact_path")
            or ""
        ),
        shadow_used=_commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "shadow_used"),
        strategist_fallback_used=(
            _commander_reasoning_flag(bundle_out, dict(bundle_out.get("commander_summary") or {}), "strategist_fallback_used")
            or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
        ),
        source_priority=commander_source_priority,
    )
    reasoning_provenance = normalize_reasoning_provenance_aliases(
        {
            "reasoning_provenance": bundle_reasoning_provenance,
            "latest_reasoning_trace_provenance": bundle_out.get("latest_reasoning_trace_provenance"),
        },
        fallback=derived_reasoning_provenance,
    )
    if isinstance(bundle_out.get("commander"), dict) or isinstance(bundle_out.get("latest_reasoning_trace_provenance"), dict):
        reasoning_provenance["shadow_used"] = _commander_reasoning_flag(
            bundle_out,
            dict(bundle_out.get("commander_summary") or {}),
            "shadow_used",
        )
        reasoning_provenance["strategist_fallback_used"] = (
            _commander_reasoning_flag(
                bundle_out,
                dict(bundle_out.get("commander_summary") or {}),
                "strategist_fallback_used",
            )
            or bool((bundle_out.get("strategist_summary") or {}).get("strategist_fallback_used"))
        )
        if commander_source_priority:
            reasoning_provenance["source_priority"] = list(commander_source_priority)
    market_context_human = dict(bundle_out.get("market_context_human") or {})
    scanner_reason_human = enrich_scanner_reason_from_evidence(
        dict(bundle_out.get("scanner_reason_human") or {}),
        dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
    )
    filters_human = enrich_filters_from_evidence(
        dict(bundle_out.get("filters_human") or {}),
        dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
        selected_symbol=str(((bundle_out.get("scanner_reason_human") or {}).get("selected_symbol")) or ((bundle_out.get("execution") or {}).get("symbol")) or ""),
        monitor_evidence=dict(bundle_out.get("monitor_evidence") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
        entry_execution_details=dict(bundle_out.get("entry_execution_details") or {}),
        exit_execution_details=dict(bundle_out.get("exit_execution_details") or {}),
    )
    monitor_reason_human = dict(bundle_out.get("monitor_reason_human") or {})
    canonical_strategist = (
        canonical_agent_artifacts.get("strategist")
        if isinstance(canonical_agent_artifacts.get("strategist"), dict)
        else bundle_out.get("strategist")
        if isinstance(bundle_out.get("strategist"), dict)
        else {}
    )
    canonical_scanner = (
        canonical_agent_artifacts.get("scanner")
        if isinstance(canonical_agent_artifacts.get("scanner"), dict)
        else bundle_out.get("scanner")
        if isinstance(bundle_out.get("scanner"), dict)
        else {}
    )
    canonical_monitor = (
        canonical_agent_artifacts.get("monitor")
        if isinstance(canonical_agent_artifacts.get("monitor"), dict)
        else bundle_out.get("monitor")
        if isinstance(bundle_out.get("monitor"), dict)
        else {}
    )
    selection_monitor = _resolve_selection_monitor_artifact(bundle_out, canonical_agent_artifacts)
    scanner_selection_trace = _build_scanner_selection_trace(scanner_reason_human, canonical_scanner)
    scanner_reason_human, scanner_selection_trace, selected_symbol = reanchor_scanner_selection_for_monitor_fallback(
        scanner_reason_human=scanner_reason_human,
        scanner_selection_trace=scanner_selection_trace,
        scanner_artifact=canonical_scanner,
        monitor_artifact=selection_monitor,
        trade_symbol=str((bundle_out.get("execution") or {}).get("symbol") or bundle_out.get("symbol") or ""),
    )
    raw_strategist_evidence = _raw_strategist_evidence(bundle_out)
    strategist_evidence_trace = _build_strategist_evidence_trace(
        _strategist_trace_source(canonical_strategist, raw_strategist_evidence),
        selected_symbol=selected_symbol,
        fallback_market_titles=market_context_human.get("market_news_titles"),
        fallback_candidate_titles=market_context_human.get("candidate_news_titles"),
    )
    _attach_news_scanner_contribution(
        scanner_reason_human=scanner_reason_human,
        scanner_selection_trace=scanner_selection_trace,
        canonical_scanner=canonical_scanner,
        canonical_strategist=canonical_strategist,
        selected_symbol=selected_symbol,
    )
    ranked_symbols = [
        str(row.get("symbol") or "").strip()
        for row in list(scanner_selection_trace.get("ranked_candidates") or [])
        if isinstance(row, dict) and str(row.get("symbol") or "").strip()
    ]
    news_symbol_linkage = build_news_symbol_linkage_view(
        strategist_summary=canonical_strategist,
        strategist_raw_input=raw_strategist_evidence,
        strategist_parsed_output=dict((bundle_out.get("strategist_summary") or {}).get("llm_parsed_output") or {}),
        selected_symbol=selected_symbol,
        top_ranked_symbols=ranked_symbols or canonical_scanner.get("top_ranked_symbols") or [],
    )
    monitor_stop_thresholds = (
        ((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"))
        if isinstance((canonical_monitor.get("thresholds_guards_used") or {}).get("thresholds"), dict)
        else canonical_monitor.get("thresholds")
        if isinstance(canonical_monitor.get("thresholds"), dict)
        else canonical_monitor.get("threshold_snapshot")
        if isinstance(canonical_monitor.get("threshold_snapshot"), dict)
        else {}
    )
    monitor_stop_policy_trace = _build_monitor_stop_policy_trace(
        canonical_monitor,
        monitor_stop_thresholds,
    )
    monitor_blocker_trace = _build_monitor_blocker_trace(monitor_reason_human)
    market_context_human.setdefault("candidate_hints", strategist_evidence_trace.get("candidate_hints") or [])
    market_context_human.setdefault("market_headlines", strategist_evidence_trace.get("market_headlines") or [])
    selected_symbol_headlines = list(strategist_evidence_trace.get("symbol_headlines") or [])
    market_context_human["symbol_headlines"] = selected_symbol_headlines
    market_context_human["symbol_news_titles"] = selected_symbol_headlines
    market_context_human["candidate_news_titles"] = selected_symbol_headlines
    market_context_human["strategist_evidence_trace"] = dict(strategist_evidence_trace)
    market_context_human["news_symbol_linkage"] = dict(news_symbol_linkage)
    _set_or_replace_placeholder(
        scanner_reason_human,
        "scanner_selection_trace",
        dict(scanner_selection_trace),
    )
    _set_or_replace_placeholder(
        scanner_reason_human,
        "ranked_candidates",
        list(scanner_selection_trace.get("ranked_candidates") or []),
    )
    scanner_reason_human.setdefault("selection_reason", scanner_selection_trace.get("selection_reason"))
    scanner_reason_human.setdefault(
        "selected_symbol_score_drivers",
        dict(scanner_selection_trace.get("selected_symbol_score_drivers") or {}),
    )
    _set_or_replace_placeholder(
        monitor_reason_human,
        "monitor_stop_policy_trace",
        dict(monitor_stop_policy_trace),
    )
    _set_or_replace_placeholder(
        monitor_reason_human,
        "monitor_blocker_trace",
        dict(monitor_blocker_trace),
    )
    section_provenance_out = dict(section_provenance)
    section_provenance_out["report_section_provenance_seeds"] = build_report_section_provenance_seeds(
        section_provenance_out,
    )
    story_out = {
        "schema_version": "trade_story_input.v1",
        "day": str(bundle_out.get("day") or ""),
        "trade_id": str(bundle_out.get("trade_id") or bundle_out.get("story_id") or ""),
        "story_id": str(bundle_out.get("story_id") or ""),
        "run_id": str(bundle_out.get("run_id") or ""),
        "symbol": str((bundle_out.get("execution") or {}).get("symbol") or ""),
        "action": (
            "HOLD"
            if str(bundle_out.get("trade_lifecycle_status") or "").strip().lower() == "open"
            and not _has_substantive_exit_evidence(
                lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
            )
            else str((bundle_out.get("execution") or {}).get("action") or "")
        ),
        "status": str(bundle_out.get("trade_lifecycle_status") or lifecycle.get("status") or "closed"),
        "story_type": str(story_contract.get("story_type") or ""),
        "execution_mode_label": str(story_contract.get("execution_mode_label") or ""),
        "market_context_human": market_context_human,
        "scanner_reason_human": scanner_reason_human,
        "canonical_monitor": _compact_canonical_monitor(canonical_monitor),
        "filters_human": filters_human,
        "monitor_reason_human": monitor_reason_human,
        "guard_reason_human": dict(bundle_out.get("guard_reason_human") or {}),
        "execution_outcome_human": dict(bundle_out.get("execution_outcome_human") or {}),
        "reporter_status_human": normalize_reporter_status_human(dict(bundle_out.get("reporter_status_human") or {})),
        "operator_conclusion_human": dict(bundle_out.get("operator_conclusion_human") or {}),
        "timeline": list(bundle_out.get("timeline") or []),
        "warnings": list(bundle_out.get("warnings") or []),
        "strategist_evidence": raw_strategist_evidence,
        "strategist_candidate_hints": list(strategist_evidence_trace.get("candidate_hints") or [])[:8],
        "strategist_market_headlines": list(strategist_evidence_trace.get("market_headlines") or [])[:3],
        "strategist_symbol_headlines": list(strategist_evidence_trace.get("symbol_headlines") or [])[:3],
        "strategist_evidence_trace": dict(strategist_evidence_trace),
        "news_symbol_linkage": dict(news_symbol_linkage),
        "scanner_evidence": dict(bundle_out.get("scanner_evidence") or (bundle_out.get("evidence") or {}).get("scanner") or {}),
        "scanner_selection_trace": dict(scanner_selection_trace),
        "monitor_timeline": dict(bundle_out.get("monitor_timeline") or (bundle_out.get("evidence") or {}).get("monitor") or {}),
        "monitor_stop_policy_trace": dict(monitor_stop_policy_trace),
        "monitor_blocker_trace": dict(monitor_blocker_trace),
        "canonical_agent_artifacts": canonical_agent_artifacts,
        "evidence_provenance": evidence_provenance,
        "section_provenance": section_provenance_out,
        "report_section_seeds": dict(report_section_seeds),
        "reasoning_trace": dict(reasoning_trace),
        "reasoning_provenance": dict(reasoning_provenance),
        "evidence_source": "canonical" if any(
            str(source or "").strip().lower() == "canonical"
            for source in evidence_provenance.values()
        ) else "direct_artifact",
        "ai_report_diagnostics": dict(bundle_out.get("ai_report_diagnostics") or {}),
    }
    story_out["strategist_feedback_input"] = build_strategist_feedback_input_view(story_out)
    return story_out


def render_bundle_markdown(out: Dict[str, Any]) -> str:
    story_contract = out.get("story_contract") if isinstance(out.get("story_contract"), dict) else {}
    lines: List[str] = []
    lines.append(f"# Aggregated Execution Bundle ({out.get('run_id')})")
    lines.append("")
    lines.append(f"- day: **{out.get('day')}**")
    lines.append(f"- story_anchor: **{story_contract.get('story_anchor') or '-'}**")
    lines.append(f"- story_type: **{story_contract.get('story_type') or '-'}**")
    lines.append(f"- execution_mode: **{story_contract.get('execution_mode_label') or '-'}**")
    lines.append("")
    sections = [
        ("Market Context", out.get("market_context_human")),
        ("Why This Symbol", out.get("scanner_reason_human")),
        ("Filters / Gates", out.get("filters_human")),
        ("Monitor / Trigger Reasoning", out.get("monitor_reason_human")),
        ("Guard / Approval", out.get("guard_reason_human")),
        ("Execution Outcome", out.get("execution_outcome_human")),
        ("Reporter Status", out.get("reporter_status_human")),
        ("Operator Conclusion", out.get("operator_conclusion_human")),
    ]
    for title, section in sections:
        data = section if isinstance(section, dict) else {}
        lines.append(f"## {title}")
        lines.append("")
        if data.get("summary"):
            lines.append(str(data.get("summary")))
            lines.append("")
        for bullet in list(data.get("bullets") or [])[:8]:
            lines.append(f"- {bullet}")
        lines.append("")
    lines.append("## Timeline")
    lines.append("")
    for row in list(out.get("timeline") or [])[:10]:
        if not isinstance(row, dict):
            continue
        lines.append(f"- {row.get('step')}: {row.get('summary') or '-'}")
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    for key, value in dict(out.get("artifacts") or {}).items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def render_summary_markdown(out: Dict[str, Any]) -> str:
    bundles = out.get("bundles") if isinstance(out.get("bundles"), list) else []
    lines: List[str] = []
    lines.append(f"# Live Execution Bundles ({out.get('day')})")
    lines.append("")
    lines.append(f"- bundle_count: **{out.get('bundle_count')}**")
    lines.append(f"- canonical_trades_root: `{out.get('canonical_trades_root')}`")
    lines.append("")
    if not bundles:
        lines.append("No executed BUY/SELL runs were found for the selected day.")
        lines.append("")
        return "\n".join(lines)
    lines.append("## Bundles")
    lines.append("")
    for row in bundles:
        lines.append(
            f"- `{row.get('run_id')}` {row.get('action')} {row.get('symbol')} x{row.get('qty')} "
            f"story=`{row.get('story_type')}` report=`{row.get('trade_report_json_path')}`"
        )
    lines.append("")
    return "\n".join(lines)
