from __future__ import annotations

import os
from typing import Any, Dict

from libs.runtime.commander.policy_readers import coerce_int
from libs.runtime.commander.strategist_cache_decision import (
    portfolio_open_position_count,
    runtime_now_epoch,
    strategist_cache_payload,
)


def runtime_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def shadow_float(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except Exception:
        return None


def shadow_text(value: Any, *, max_len: int = 120) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text[: max(1, int(max_len))]


def portfolio_open_position_symbols(state: Dict[str, Any]) -> list[str]:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []
    seen: set[str] = set()
    symbols: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if coerce_int(row.get("qty"), 0) <= 0:
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        symbols.append(symbol)
    return symbols


def post_scanner_selected_symbol(state: Dict[str, Any]) -> str:
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    if bool(selected.get("_monitor_synthetic_selected")) or bool(selected.get("_closeout_guard_selected")):
        return ""
    scanner_output = state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {}
    return str(
        selected.get("symbol")
        or scanner_output.get("top_stock")
        or scanner_output.get("selected_symbol")
        or ""
    ).strip().upper()


def score_bucket(value: Any, *, step: float = 0.10) -> str:
    numeric = shadow_float(value)
    if numeric is None:
        return "unknown"
    if step <= 0.0:
        step = 0.10
    bucket = int(float(numeric) / float(step))
    return f"{round(bucket * step, 4):.2f}-{round((bucket + 1) * step, 4):.2f}"


def rank_bucket(value: Any) -> str:
    rank = coerce_int(value, 0)
    if rank <= 0:
        return "unknown"
    if rank == 1:
        return "rank1"
    if rank <= 3:
        return "rank2_3"
    if rank <= 10:
        return "rank4_10"
    return "rank11_plus"


def entry_gate_bucket(state: Dict[str, Any]) -> str:
    monitor_output = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
    monitor = state.get("monitor") if isinstance(state.get("monitor"), dict) else {}
    entry_detail = state.get("monitor_entry_decision_detail") if isinstance(state.get("monitor_entry_decision_detail"), dict) else {}
    for key in ("entry_guard_reason", "entry_exit_reason", "primary_reason_code", "reason"):
        value = (
            monitor_output.get(key)
            if monitor_output.get(key) not in (None, "")
            else monitor.get(key)
            if monitor.get(key) not in (None, "")
            else entry_detail.get(key)
        )
        text = str(value or "").strip().lower()
        if text:
            return text[:80]
    intent = str(monitor_output.get("intent_side") or monitor.get("intent_side") or "").strip().upper()
    if intent == "BUY":
        return "buy_ready"
    return "unknown"


def candidate_theme_tokens(row: Dict[str, Any]) -> list[str]:
    raw_values: list[Any] = []
    for key in ("theme", "primary_theme", "sector", "industry"):
        raw_values.append(row.get(key))
    for key in ("themes", "theme_names", "theme_tags", "matched_themes"):
        value = row.get(key)
        if isinstance(value, (list, tuple, set)):
            raw_values.extend(list(value))
        else:
            raw_values.append(value)
    out: list[str] = []
    for value in raw_values:
        if value in (None, ""):
            continue
        for token in str(value).replace("|", ",").replace("/", ",").split(","):
            text = token.strip().lower()
            if text and text not in out:
                out.append(text[:80])
    return out[:5]


def candidate_chart_fit_value(row: Dict[str, Any]) -> Any:
    for key in ("scanner_chart_fit_score", "scanner_macro_chart_fit_score", "entry_compatibility_score", "confidence"):
        if row.get(key) not in (None, ""):
            return row.get(key)
    return None


def candidate_edge_bucket(row: Dict[str, Any], state: Dict[str, Any]) -> str:
    for key in (
        "cost_adjusted_edge_pct",
        "estimated_gross_edge_pct",
        "expected_edge_pct",
        "expected_move_pct",
        "expected_return_pct",
    ):
        if row.get(key) not in (None, ""):
            value = shadow_float(row.get(key))
            if value is None:
                continue
            if value < 0.0:
                return "negative"
            if value < 0.003:
                return "tiny"
            if value < 0.012:
                return "below_cost_floor"
            if value < 0.025:
                return "tradable"
            return "strong"
    gate = entry_gate_bucket(state)
    if "cost" in gate and ("fail" in gate or "not" in gate or "below" in gate):
        return "below_cost_floor"
    if "ready" in gate or "buy" in gate:
        return "tradable"
    return "unknown"


def compact_post_scanner_candidate_row(row: Dict[str, Any], *, fallback_rank: int = 0) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    symbol = str(row.get("symbol") or row.get("code") or row.get("ticker") or "").strip().upper()
    if not symbol:
        return {}
    score = None
    score_source = ""
    for key in (
        "score_total",
        "post_adjust_score_total",
        "selected_score_total",
        "scanner_score_total",
        "score",
        "final_score",
        "rank_score",
        "pre_adjust_score_total",
    ):
        score = shadow_float(row.get(key))
        if score is not None:
            score_source = key
            break
    reason = str(
        row.get("selection_reason")
        or row.get("selection_reason_with_bias")
        or row.get("why")
        or row.get("reason")
        or row.get("reason_text")
        or row.get("source_reason")
        or ""
    ).strip()
    rank = coerce_int(row.get("rank"), fallback_rank)
    score_breakdown: Dict[str, Any] = {}
    if isinstance(row.get("score_breakdown"), dict):
        for key, value in list(dict(row.get("score_breakdown") or {}).items())[:10]:
            numeric = shadow_float(value)
            score_breakdown[str(key)[:50]] = (
                round(float(numeric), 6)
                if numeric is not None
                else shadow_text(value, max_len=80)
            )
    compact = {
        "symbol": symbol,
        "rank": int(rank if rank > 0 else fallback_rank),
        "score": round(float(score), 6) if score is not None else None,
        "score_total": round(float(score), 6) if score is not None else None,
        "score_source": score_source,
        "reason": reason[:180],
        "source": str(row.get("source") or row.get("source_name") or "").strip()[:80],
    }
    if score_breakdown:
        compact["score_breakdown"] = score_breakdown
    for key in (
        "risk_score",
        "confidence",
        "entry_compatibility_score",
        "compatibility_bias",
        "scanner_chart_fit_score",
        "scanner_chart_fit_penalty",
        "scanner_macro_chart_fit_score",
        "scanner_macro_chart_fit_bias",
        "bias_adjustment",
        "pre_adjust_score_total",
        "post_adjust_score_total",
        "raw_entry_compatibility_bias",
        "effective_entry_compatibility_bias",
    ):
        value = shadow_float(row.get(key))
        if value is not None:
            compact[key] = round(float(value), 6)
    chart_fit_components: Dict[str, Any] = {}
    if isinstance(row.get("scanner_chart_fit_components"), dict):
        for key, value in list(dict(row.get("scanner_chart_fit_components") or {}).items())[:10]:
            numeric = shadow_float(value)
            chart_fit_components[str(key)[:50]] = (
                round(float(numeric), 6)
                if numeric is not None
                else shadow_text(value, max_len=80)
            )
    if chart_fit_components:
        compact["scanner_chart_fit_components"] = chart_fit_components
    macro_chart_fit_components: Dict[str, Any] = {}
    if isinstance(row.get("scanner_macro_chart_fit_components"), dict):
        for key, value in list(dict(row.get("scanner_macro_chart_fit_components") or {}).items())[:10]:
            numeric = shadow_float(value)
            macro_chart_fit_components[str(key)[:50]] = (
                round(float(numeric), 6)
                if numeric is not None
                else shadow_text(value, max_len=80)
            )
    if macro_chart_fit_components:
        compact["scanner_macro_chart_fit_components"] = macro_chart_fit_components
    for key in (
        "expected_monitor_block_reason",
        "dominant_block_reason",
        "scanner_chart_fit_authority",
        "scanner_macro_chart_fit_authority",
        "market_representative_guard_reason",
        "selection_reason_with_bias",
        "status",
    ):
        text = shadow_text(row.get(key), max_len=160)
        if text:
            compact[key] = text
    return compact


def post_scanner_context_quality(
    *,
    selected_candidate: Dict[str, Any],
    scanner_rank1_candidate: Dict[str, Any],
    runner_ups: list[Dict[str, Any]],
) -> Dict[str, Any]:
    reasons: list[str] = []
    if not str(selected_candidate.get("symbol") or "").strip():
        reasons.append("selected_candidate_missing")
    if coerce_int(selected_candidate.get("rank"), 0) <= 0:
        reasons.append("selected_rank_missing")
    if selected_candidate.get("score") is None and selected_candidate.get("score_total") is None:
        reasons.append("selected_score_missing")
    if not str(scanner_rank1_candidate.get("symbol") or "").strip():
        reasons.append("scanner_rank1_missing")
    if not runner_ups:
        reasons.append("runner_ups_missing")
    quality = "complete"
    if reasons:
        quality = "partial"
    if "selected_candidate_missing" in reasons or "scanner_rank1_missing" in reasons:
        quality = "weak"
    return {"quality": quality, "reasons": reasons}


def post_scanner_candidate_snapshot(state: Dict[str, Any], selected_symbol: str) -> Dict[str, Any]:
    scanner_output = state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {}
    raw_rows: list[Any] = []
    for source in (
        state.get("ranked_candidates"),
        scanner_output.get("ranked_candidates"),
        scanner_output.get("candidate_ranking_table", {}).get("rows")
        if isinstance(scanner_output.get("candidate_ranking_table"), dict)
        else [],
        scanner_output.get("runner_ups"),
    ):
        if isinstance(source, list):
            raw_rows.extend(source)
    rows: list[Dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(raw_rows, start=1):
        if not isinstance(raw, dict):
            continue
        row = compact_post_scanner_candidate_row(raw, fallback_rank=idx)
        symbol = str(row.get("symbol") or "")
        if not symbol or symbol in seen:
            continue
        rows.append(row)
        seen.add(symbol)
        if len(rows) >= 8:
            break
    scanner_rank1_candidate = {}
    for row in rows:
        if coerce_int(row.get("rank"), 0) == 1:
            scanner_rank1_candidate = dict(row)
            break
    if not scanner_rank1_candidate and rows:
        scanner_rank1_candidate = dict(rows[0])
    selected_candidate = {}
    for row in rows:
        if str(row.get("symbol") or "").strip().upper() == selected_symbol:
            selected_candidate = dict(row)
            break
    if selected_symbol and not selected_candidate:
        selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
        fallback_raw = dict(selected)
        fallback_raw["symbol"] = selected_symbol
        fallback_raw.setdefault("source", "selected")
        selected_candidate = compact_post_scanner_candidate_row(
            fallback_raw,
            fallback_rank=coerce_int(fallback_raw.get("rank") or fallback_raw.get("selected_rank"), 0),
        )
        if not selected_candidate:
            selected_candidate = {
                "symbol": selected_symbol,
                "rank": 0,
                "score": None,
                "score_total": None,
                "reason": "",
                "source": "selected_missing_from_scanner_rows",
            }
        if selected_symbol not in seen:
            rows.append(dict(selected_candidate))
            seen.add(selected_symbol)
    primary = dict(selected_candidate or scanner_rank1_candidate)
    runner_ups = [
        dict(row)
        for row in rows
        if str(row.get("symbol") or "").strip().upper() != selected_symbol
    ][:4]
    quality = post_scanner_context_quality(
        selected_candidate=selected_candidate,
        scanner_rank1_candidate=scanner_rank1_candidate,
        runner_ups=runner_ups,
    )
    return {
        "primary": primary,
        "selected_candidate": dict(selected_candidate),
        "scanner_rank1_candidate": dict(scanner_rank1_candidate),
        "runner_ups": runner_ups,
        "rows": rows[:5],
        "selected_symbol_was_rank1": bool(
            selected_symbol
            and str((scanner_rank1_candidate or {}).get("symbol") or "").strip().upper() == selected_symbol
        ),
        "stage2_context_quality": quality["quality"],
        "stage2_context_quality_reasons": list(quality["reasons"]),
    }


def build_strategist_input_fingerprint(state: Dict[str, Any]) -> Dict[str, Any]:
    selected_symbol = post_scanner_selected_symbol(state)
    snapshot = post_scanner_candidate_snapshot(state, selected_symbol) if selected_symbol else {}
    rows = [dict(row) for row in list(snapshot.get("rows") or []) if isinstance(row, dict)]
    if not rows:
        scanner_output = state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {}
        for key in ("candidates", "top_candidates", "ranked_candidates", "pool"):
            raw_rows = scanner_output.get(key)
            if isinstance(raw_rows, list):
                rows = [
                    compact_post_scanner_candidate_row(row, fallback_rank=idx)
                    for idx, row in enumerate(raw_rows[:10], start=1)
                    if isinstance(row, dict)
                ]
                rows = [row for row in rows if row]
                break
    selected_candidate = dict(snapshot.get("selected_candidate") or snapshot.get("primary") or {})
    if not selected_candidate and selected_symbol:
        selected_candidate = next((dict(row) for row in rows if str(row.get("symbol") or "").upper() == selected_symbol), {})
    if not selected_symbol:
        selected_symbol = str(selected_candidate.get("symbol") or "").strip().upper()
    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    open_symbols = portfolio_open_position_symbols(state)
    themes: list[str] = []
    for row in rows[:5]:
        for token in candidate_theme_tokens(row):
            if token not in themes:
                themes.append(token)
    top_symbols = [str(row.get("symbol") or "").strip().upper() for row in rows[:5] if str(row.get("symbol") or "").strip()]
    selected_score = selected_candidate.get("score_total") if selected_candidate.get("score_total") is not None else selected_candidate.get("score")
    return {
        "schema_version": "strategist_input_fingerprint.v1",
        "selected_symbol": selected_symbol,
        "selected_rank_bucket": rank_bucket(selected_candidate.get("rank")),
        "selected_score_bucket": score_bucket(selected_score),
        "selected_chart_fit_bucket": score_bucket(candidate_chart_fit_value(selected_candidate)),
        "selected_edge_bucket": candidate_edge_bucket(selected_candidate, state),
        "entry_gate_bucket": entry_gate_bucket(state),
        "top_symbols": top_symbols[:5],
        "top3_symbols": top_symbols[:3],
        "top_themes": themes[:5],
        "market_regime": str(
            state.get("market_regime")
            or market_context.get("regime")
            or market_context.get("market_regime")
            or ""
        ).strip().lower()[:80],
        "open_position_count": int(portfolio_open_position_count(state)),
        "open_symbols": sorted(open_symbols),
    }


def jaccard_distance(left: list[str], right: list[str]) -> float:
    left_set = {str(x or "").strip() for x in left if str(x or "").strip()}
    right_set = {str(x or "").strip() for x in right if str(x or "").strip()}
    if not left_set and not right_set:
        return 0.0
    if not left_set or not right_set:
        return 1.0
    return float(1.0 - (len(left_set & right_set) / len(left_set | right_set)))


def assess_strategist_fingerprint_drift(
    previous: Dict[str, Any],
    current: Dict[str, Any],
    *,
    threshold: float | None = None,
) -> Dict[str, Any]:
    prev = dict(previous or {}) if isinstance(previous, dict) else {}
    cur = dict(current or {}) if isinstance(current, dict) else {}
    effective_threshold = (
        float(threshold)
        if threshold is not None
        else float(runtime_float(os.getenv("COMMANDER_STRATEGIST_INPUT_DRIFT_THRESHOLD", "0.45"), 0.45))
    )
    reasons: list[str] = []
    if not prev or not cur:
        return {
            "comparable": False,
            "material_change": True,
            "change_score": 1.0,
            "threshold": float(effective_threshold),
            "reasons": ["fingerprint_missing"],
            "previous": prev,
            "current": cur,
        }
    score = 0.0
    if str(prev.get("selected_symbol") or "") != str(cur.get("selected_symbol") or ""):
        score += 0.30
        reasons.append("selected_symbol_changed")
    top_distance = jaccard_distance(list(prev.get("top_symbols") or []), list(cur.get("top_symbols") or []))
    if top_distance > 0.0:
        score += 0.25 * top_distance
        reasons.append("top_symbols_changed")
    theme_distance = jaccard_distance(list(prev.get("top_themes") or []), list(cur.get("top_themes") or []))
    if theme_distance > 0.0:
        score += 0.10 * theme_distance
        reasons.append("top_themes_changed")
    for key, weight, reason in (
        ("selected_rank_bucket", 0.08, "selected_rank_bucket_changed"),
        ("selected_chart_fit_bucket", 0.12, "selected_chart_fit_bucket_changed"),
        ("selected_edge_bucket", 0.12, "selected_edge_bucket_changed"),
        ("entry_gate_bucket", 0.10, "entry_gate_changed"),
        ("market_regime", 0.10, "market_regime_changed"),
    ):
        if str(prev.get(key) or "") != str(cur.get(key) or ""):
            score += weight
            reasons.append(reason)
    if int(prev.get("open_position_count") or 0) != int(cur.get("open_position_count") or 0):
        score += 0.15
        reasons.append("open_position_count_changed")
    if sorted(list(prev.get("open_symbols") or [])) != sorted(list(cur.get("open_symbols") or [])):
        score += 0.12
        reasons.append("open_symbols_changed")
    score = min(1.0, float(score))
    return {
        "comparable": True,
        "material_change": bool(score >= effective_threshold),
        "change_score": round(score, 6),
        "threshold": float(effective_threshold),
        "reasons": reasons,
        "previous": prev,
        "current": cur,
    }


def assess_cached_strategist_input_drift(state: Dict[str, Any]) -> Dict[str, Any]:
    cache_payload = strategist_cache_payload(state)
    previous = cache_payload.get("input_fingerprint") if isinstance(cache_payload.get("input_fingerprint"), dict) else {}
    current = build_strategist_input_fingerprint(state)
    out = assess_strategist_fingerprint_drift(previous, current)
    out["cache_source"] = str(cache_payload.get("source") or "")
    out["cache_age_sec"] = (
        max(0, runtime_now_epoch(state) - coerce_int(cache_payload.get("generated_epoch"), 0))
        if coerce_int(cache_payload.get("generated_epoch"), 0) > 0
        else None
    )
    return out
