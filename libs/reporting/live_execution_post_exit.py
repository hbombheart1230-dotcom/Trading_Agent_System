from __future__ import annotations

from typing import Any, Dict, List

from libs.core.symbols import normalize_symbol


def runtime_minute_rows_for_symbol(runtime_state: Dict[str, Any], symbol: str) -> List[Dict[str, Any]]:
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    candidates = [normalized]
    if normalized and not normalized.startswith("A"):
        candidates.append(f"A{normalized}")
    if not any(candidates):
        return []

    def _rows_from_record(record: Any) -> List[Dict[str, Any]]:
        if isinstance(record, list):
            return [dict(row) for row in record if isinstance(row, dict)]
        if not isinstance(record, dict):
            return []
        direct_rows = record.get("rows")
        if isinstance(direct_rows, list):
            return [dict(row) for row in direct_rows if isinstance(row, dict)]
        result = record.get("result") if isinstance(record.get("result"), dict) else {}
        data = result.get("data") if isinstance(result.get("data"), dict) else record.get("data")
        if isinstance(data, dict):
            data_rows = data.get("rows")
            if isinstance(data_rows, list):
                return [dict(row) for row in data_rows if isinstance(row, dict)]
            for candidate in candidates:
                nested = data.get(candidate)
                nested_rows = _rows_from_record(nested)
                if nested_rows:
                    return nested_rows
        for candidate in candidates:
            nested = record.get(candidate)
            nested_rows = _rows_from_record(nested)
            if nested_rows:
                return nested_rows
        return []

    def _latest_epoch(rows: List[Dict[str, Any]]) -> int:
        best = 0
        for row in rows:
            try:
                ts = int(float(row.get("ts")))
            except Exception:
                ts = 0
            best = max(best, ts)
        return best

    def _collect_from_container(container: Dict[str, Any], out: List[List[Dict[str, Any]]]) -> None:
        for root_key in (
            "recent_minute_ohlcv_by_symbol",
            "minute_ohlcv_by_symbol",
            "monitor_minute_ohlcv_by_symbol",
            "intraday_ohlcv_by_symbol",
            "ohlcv_by_symbol",
        ):
            root = container.get(root_key)
            if not isinstance(root, dict):
                continue
            for candidate in candidates:
                rows = _rows_from_record(root.get(candidate))
                if rows:
                    out.append(rows)

    found: List[List[Dict[str, Any]]] = []
    _collect_from_container(runtime_state, found)
    persisted = runtime_state.get("persisted_state") if isinstance(runtime_state.get("persisted_state"), dict) else {}
    _collect_from_container(persisted, found)

    skill_results = runtime_state.get("skill_results") if isinstance(runtime_state.get("skill_results"), dict) else {}
    for key in ("market.minute_ohlcv_by_symbol", "market.minute_ohlcv", "market.minute_candles", "market.candles"):
        raw = skill_results.get(key)
        if isinstance(raw, dict):
            for candidate in candidates:
                rows = _rows_from_record(raw.get(candidate))
                if rows:
                    found.append(rows)
            rows = _rows_from_record(raw)
            if rows and normalize_symbol(raw.get("symbol") or "", allow_test_symbols=True) in candidates:
                found.append(rows)

    history = (
        ((runtime_state.get("skill_results_history") or {}).get("market.minute_ohlcv"))
        if isinstance(runtime_state.get("skill_results_history"), dict)
        else []
    )
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            if normalize_symbol(item.get("symbol") or "", allow_test_symbols=True) not in candidates:
                continue
            rows = _rows_from_record(item.get("record"))
            if rows:
                found.append(rows)

    if not found:
        return []
    found.sort(key=lambda rows: (_latest_epoch(rows), len(rows)), reverse=True)
    return [dict(row) for row in found[0] if isinstance(row, dict)]


def post_exit_shadow_from_lifecycle(lifecycle: Dict[str, Any], lifecycle_bundle: Dict[str, Any]) -> Dict[str, Any]:
    lifecycle_exit = lifecycle.get("exit") if isinstance(lifecycle.get("exit"), dict) else {}
    for candidate in (
        lifecycle_bundle.get("post_exit_shadow"),
        lifecycle.get("post_exit_shadow"),
        lifecycle_exit.get("post_exit_shadow") if isinstance(lifecycle_exit, dict) else {},
    ):
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    return {}


def attach_post_exit_shadow_to_trade_report(
    trade_report: Dict[str, Any],
    *,
    lifecycle: Dict[str, Any],
    lifecycle_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    shadow = post_exit_shadow_from_lifecycle(lifecycle, lifecycle_bundle)
    if not shadow:
        return dict(trade_report or {})
    out = dict(trade_report or {})
    out["post_exit_shadow"] = dict(shadow)
    fact_payload = dict(out.get("fact_payload") or {}) if isinstance(out.get("fact_payload"), dict) else {}
    fact_trade = dict(fact_payload.get("trade") or {}) if isinstance(fact_payload.get("trade"), dict) else {}
    fact_trade["post_exit_shadow"] = dict(shadow)
    fact_payload["trade"] = fact_trade
    out["fact_payload"] = fact_payload
    return out
