from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from libs.core.symbols import normalize_symbol
from libs.runtime.strategy_horizon_feedback import (
    build_post_exit_shadow_placeholder,
    update_post_exit_shadow_with_price_observations,
)


CHECKPOINT_LABELS = ("+5m", "+15m", "+30m", "+60m", "EOD")
KST = timezone(timedelta(hours=9), name="KST")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def resolve_post_exit_state_path(reports_root: Path, state_path: Path | None = None) -> Path | None:
    candidates: List[Path] = []
    if state_path is not None and str(state_path).strip():
        candidates.append(Path(state_path))
    for key in ("STATE_STORE_PATH", "MOCK_EXAM_STATE_PATH"):
        raw = str(os.getenv(key) or "").strip()
        if raw:
            candidates.append(Path(raw))

    reports_root_path = Path(reports_root)
    candidates.append(reports_root_path.parent / "data" / "state.json")
    candidates.append(Path("data/state.json"))

    for candidate in candidates:
        path = candidate
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if path.exists():
            return path
    return None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8-sig", newline="\n")


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def _symbol_candidates(symbol: str) -> List[str]:
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    out = [normalized] if normalized else []
    if normalized and not normalized.startswith("A"):
        out.append(f"A{normalized}")
    return out


def _rows_from_record(record: Any, candidates: List[str]) -> List[Dict[str, Any]]:
    if isinstance(record, list):
        return [dict(row) for row in record if isinstance(row, dict)]
    if not isinstance(record, dict):
        return []
    rows = record.get("rows")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    result = record.get("result") if isinstance(record.get("result"), dict) else {}
    data = result.get("data") if isinstance(result.get("data"), dict) else record.get("data")
    if isinstance(data, dict):
        nested_rows = data.get("rows")
        if isinstance(nested_rows, list):
            return [dict(row) for row in nested_rows if isinstance(row, dict)]
        for candidate in candidates:
            found = _rows_from_record(data.get(candidate), candidates)
            if found:
                return found
    for candidate in candidates:
        found = _rows_from_record(record.get(candidate), candidates)
        if found:
            return found
    return []


def _latest_epoch(rows: Iterable[Mapping[str, Any]]) -> int:
    best = 0
    for row in rows:
        try:
            best = max(best, int(float(row.get("ts"))))
        except Exception:
            continue
    return best


def _epoch_seconds(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        raw = float(value)
        if raw > 0:
            return raw
    except Exception:
        pass
    try:
        text = str(value).strip()
        if not text:
            return None
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return float(dt.timestamp())
    except Exception:
        return None


def _fresh_minute_fetch_enabled() -> bool:
    raw = str(os.getenv("POST_EXIT_SHADOW_RECAP_FETCH_FRESH_MINUTES", "1")).strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _shadow_latest_required_epoch(shadow: Mapping[str, Any]) -> float | None:
    exit_epoch = _epoch_seconds(shadow.get("exit_ts"))
    if exit_epoch is None:
        return None
    checkpoints = _as_dict(shadow.get("checkpoints"))
    best: float | None = None
    for label, minutes in (("+5m", 5), ("+15m", 15), ("+30m", 30), ("+60m", 60)):
        row = _as_dict(checkpoints.get(label))
        if str(row.get("status") or "").strip().lower() == "observed":
            continue
        target_epoch = _epoch_seconds(row.get("target_ts"))
        if target_epoch is None:
            target_epoch = exit_epoch + (minutes * 60)
        best = target_epoch if best is None else max(best, target_epoch)
    return best


def _rows_reach_epoch(rows: Iterable[Mapping[str, Any]], target_epoch: float | None) -> bool:
    if target_epoch is None:
        return False
    return any((_epoch_seconds(row.get("ts")) or 0.0) >= float(target_epoch) for row in rows if isinstance(row, Mapping))


def _rows_reach_regular_close(rows: Iterable[Mapping[str, Any]]) -> bool:
    return any(
        _row_kst_hhmmss(row) >= "153000"
        for row in rows
        if isinstance(row, Mapping) and _row_kst_hhmmss(row)
    )


def _post_exit_shadow_needs_fresh_minutes(shadow: Mapping[str, Any], rows: List[Dict[str, Any]]) -> bool:
    target_epoch = _shadow_latest_required_epoch(shadow)
    now_epoch = datetime.now(timezone.utc).timestamp()
    if target_epoch is not None:
        if now_epoch + 30.0 < target_epoch:
            return False
        if not _rows_reach_epoch(rows, target_epoch):
            return True

    now_kst = datetime.now(timezone.utc).astimezone(KST)
    checkpoints = _as_dict(shadow.get("checkpoints"))
    eod = _as_dict(checkpoints.get("EOD"))
    eod_pending = str(eod.get("status") or "").strip().lower() != "observed"
    if eod_pending and now_kst.strftime("%H%M%S") >= "153500":
        return not _rows_reach_regular_close(rows)
    return False


def _minute_row_key(row: Mapping[str, Any]) -> str:
    raw_ts = str(row.get("raw_ts") or "").strip()
    if raw_ts:
        return f"raw:{raw_ts}"
    ts = _epoch_seconds(row.get("ts"))
    if ts is not None:
        return f"ts:{int(ts)}"
    return ""


def merge_minute_rows(*row_groups: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}
    anonymous: List[Dict[str, Any]] = []
    for rows in row_groups:
        for row in rows or []:
            if not isinstance(row, Mapping):
                continue
            item = dict(row)
            key = _minute_row_key(item)
            if key:
                merged[key] = item
            else:
                anonymous.append(item)
    out = list(merged.values()) + anonymous
    return sorted(out, key=lambda row: (_epoch_seconds(row.get("ts")) or 0.0, str(row.get("raw_ts") or "")))


def opening_rank1_eod_fallback_row(
    *, reports_root: Path, day: str, symbol: str
) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
    path = (
        Path(reports_root)
        / "evaluation"
        / "opening_rank1_shadow"
        / str(day)
        / "opening_rank1_shadow_daily.json"
    )
    payload = _read_json(path)
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    for raw in payload.get("episodes") or []:
        episode = _as_dict(raw)
        if normalize_symbol(episode.get("symbol") or "", allow_test_symbols=True) != normalized:
            continue
        eod = _as_dict(_as_dict(episode.get("checkpoints")).get("EOD"))
        if str(eod.get("status") or "").strip().lower() != "observed":
            continue
        price = eod.get("price") if eod.get("price") not in (None, "") else eod.get("observed_price")
        try:
            close = float(price)
        except Exception:
            continue
        observed_epoch = _epoch_seconds(eod.get("observed_epoch") or eod.get("observed_ts"))
        if observed_epoch is None:
            try:
                observed_epoch = datetime.fromisoformat(str(day)).replace(
                    hour=15, minute=30, tzinfo=KST
                ).timestamp()
            except Exception:
                continue
        observed_kst = datetime.fromtimestamp(observed_epoch, tz=timezone.utc).astimezone(KST)
        row = {
            "ts": int(observed_epoch),
            "raw_ts": observed_kst.strftime("%Y%m%d%H%M%S"),
            "open": close,
            "high": close,
            "low": close,
            "close": close,
            "volume": eod.get("volume"),
            "source": "opening_rank1_shadow.EOD",
            "eod_fallback": True,
        }
        return row, {
            "applied": True,
            "source": "opening_rank1_shadow.EOD",
            "source_path": str(path),
        }
    return None, {
        "applied": False,
        "reason": "matching_observed_opening_rank1_eod_not_found",
        "source_path": str(path),
    }


def fetch_fresh_minute_rows_for_symbol(symbol: str, *, run_id: str = "post_exit_shadow_recap") -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    normalized = normalize_symbol(symbol or "", allow_test_symbols=True)
    meta: Dict[str, Any] = {
        "attempted": True,
        "ok": False,
        "symbol": normalized,
        "rows": 0,
        "source": "market.minute_ohlcv",
    }
    if not normalized:
        meta["reason"] = "missing_symbol"
        return [], meta
    try:
        from libs.runtime.monitor_minute_ohlcv import (
            _extract_monitor_minute_rows,
            _fresh_monitor_skill_runner,
            _run_monitor_minute_skill,
        )

        runner, source = _fresh_monitor_skill_runner()
        meta["runner_source"] = source
        if runner is None:
            meta["reason"] = "runner_unavailable"
            return [], meta
        rec = _run_monitor_minute_skill(
            runner=runner,
            run_id=run_id,
            symbol=normalized,
            timeframe_minutes=1,
        )
        _result, rows = _extract_monitor_minute_rows(rec)
        clean_rows = [dict(row) for row in rows if isinstance(row, dict)]
        meta["ok"] = bool(clean_rows)
        meta["rows"] = len(clean_rows)
        meta["reason"] = "" if clean_rows else "no_rows_returned"
        return clean_rows, meta
    except Exception as exc:
        meta["reason"] = "fresh_minute_fetch_failed"
        meta["error"] = str(exc)
        return [], meta


def minute_rows_for_symbol_from_state(state: Mapping[str, Any], symbol: str) -> List[Dict[str, Any]]:
    candidates = _symbol_candidates(symbol)
    if not candidates:
        return []

    found: List[List[Dict[str, Any]]] = []

    def collect(container: Mapping[str, Any]) -> None:
        for key in (
            "recent_minute_ohlcv_by_symbol",
            "minute_ohlcv_by_symbol",
            "monitor_minute_ohlcv_by_symbol",
            "intraday_ohlcv_by_symbol",
            "ohlcv_by_symbol",
        ):
            root = container.get(key)
            if not isinstance(root, dict):
                continue
            for candidate in candidates:
                rows = _rows_from_record(root.get(candidate), candidates)
                if rows:
                    found.append(rows)

    collect(state)
    persisted = state.get("persisted_state")
    if isinstance(persisted, dict):
        collect(persisted)

    skill_results = state.get("skill_results") if isinstance(state.get("skill_results"), dict) else {}
    for key in ("market.minute_ohlcv_by_symbol", "market.minute_ohlcv", "market.minute_candles", "market.candles"):
        raw = skill_results.get(key)
        if isinstance(raw, dict):
            for candidate in candidates:
                rows = _rows_from_record(raw.get(candidate), candidates)
                if rows:
                    found.append(rows)
            if normalize_symbol(raw.get("symbol") or "", allow_test_symbols=True) in candidates:
                rows = _rows_from_record(raw, candidates)
                if rows:
                    found.append(rows)

    history = state.get("skill_results_history") if isinstance(state.get("skill_results_history"), dict) else {}
    minute_history = history.get("market.minute_ohlcv")
    if isinstance(minute_history, list):
        for item in minute_history:
            if not isinstance(item, dict):
                continue
            if normalize_symbol(item.get("symbol") or "", allow_test_symbols=True) not in candidates:
                continue
            rows = _rows_from_record(item.get("record"), candidates)
            if rows:
                found.append(rows)

    if not found:
        return []
    found.sort(key=lambda rows: (_latest_epoch(rows), len(rows)), reverse=True)
    return [dict(row) for row in found[0] if isinstance(row, dict)]


def _parse_exit_kst_date(exit_ts: Any) -> str:
    raw = str(exit_ts or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST).strftime("%Y%m%d")


def _row_kst_date(row: Mapping[str, Any]) -> str:
    raw_ts = str(row.get("raw_ts") or "").strip()
    if len(raw_ts) >= 8 and raw_ts[:8].isdigit():
        return raw_ts[:8]
    try:
        ts = float(row.get("ts"))
    except Exception:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(KST).strftime("%Y%m%d")


def _row_kst_hhmmss(row: Mapping[str, Any]) -> str:
    raw_ts = str(row.get("raw_ts") or "").strip()
    if len(raw_ts) >= 14 and raw_ts[8:14].isdigit():
        return raw_ts[8:14]
    try:
        ts = float(row.get("ts"))
    except Exception:
        return ""
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(KST).strftime("%H%M%S")


def same_day_closeout_rows_for_shadow(shadow: Mapping[str, Any], rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the recap scoped to the sell date and full close, not T+1 drift."""

    exit_day = _parse_exit_kst_date(shadow.get("exit_ts"))
    if not exit_day:
        return [dict(row) for row in rows]
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_kst_date(row) != exit_day:
            continue
        hhmmss = _row_kst_hhmmss(row)
        if hhmmss and hhmmss > "160000":
            continue
        out.append(dict(row))
    return out


def _checkpoint_target_after_regular_close(row: Mapping[str, Any]) -> bool:
    target_epoch = _epoch_seconds(row.get("target_ts"))
    if target_epoch is None:
        return False
    hhmmss = datetime.fromtimestamp(target_epoch, tz=timezone.utc).astimezone(KST).strftime("%H%M%S")
    return hhmmss > "153000"


def _fill_regular_close_bound_pending_checkpoints(shadow: Mapping[str, Any]) -> Dict[str, Any]:
    """Close reporting-only checkpoints that mature after the regular session.

    A trade sold after 14:30 can have a +60m target past 15:30. Regular-session
    minute bars stop at the close, so a strict target lookup would stay pending
    forever even after the 16:00 recap. In that case the regular close is the
    final same-session observation for the report.
    """

    out = dict(shadow)
    checkpoints = _as_dict(out.get("checkpoints"))
    eod = _as_dict(checkpoints.get("EOD"))
    if str(eod.get("status") or "").strip().lower() != "observed":
        return out
    eod_price = eod.get("price") if eod.get("price") is not None else eod.get("close")
    eod_ts = eod.get("observed_ts")
    exit_price = None
    try:
        exit_price = float(out.get("exit_price"))
    except Exception:
        exit_price = None
    for label in ("+5m", "+15m", "+30m", "+60m"):
        row = _as_dict(checkpoints.get(label))
        if str(row.get("status") or "").strip().lower() == "observed":
            continue
        if not _checkpoint_target_after_regular_close(row):
            continue
        row.update(
            {
                "status": "observed",
                "observed_ts": eod_ts,
                "raw_ts": eod.get("raw_ts") or "",
                "price": eod_price,
                "observed_price": eod_price,
                "closeout_substitute": True,
                "closeout_substitute_reason": "checkpoint_target_after_regular_session_close",
            }
        )
        if exit_price and eod_price not in (None, ""):
            try:
                row["return_pct"] = (float(eod_price) / float(exit_price)) - 1.0
            except Exception:
                pass
        for key in ("high_since_exit", "low_since_exit", "max_upside_pct", "max_drawdown_pct", "observation_count"):
            if eod.get(key) is not None:
                row[key] = eod.get(key)
        checkpoints[label] = row
    out["checkpoints"] = checkpoints
    return out


def _post_exit_shadow_from_report(report: Mapping[str, Any]) -> Dict[str, Any]:
    fact_payload = _as_dict(report.get("fact_payload"))
    fact_trade = _as_dict(fact_payload.get("trade"))
    lifecycle = _as_dict(report.get("trade_lifecycle"))
    lifecycle_exit = _as_dict(lifecycle.get("exit"))
    lifecycle_bundle = _as_dict(report.get("lifecycle_bundle"))
    for candidate in (
        report.get("post_exit_shadow"),
        fact_trade.get("post_exit_shadow"),
        lifecycle.get("post_exit_shadow"),
        lifecycle_exit.get("post_exit_shadow"),
        lifecycle_bundle.get("post_exit_shadow"),
    ):
        if isinstance(candidate, dict) and candidate:
            return dict(candidate)
    return {}


def _post_exit_shadow_from_lifecycle(report_path: Path) -> Dict[str, Any]:
    trade_dir = report_path.parents[1]
    bundle = _read_json(trade_dir / "lifecycle_bundle.json")
    if not bundle:
        return {}
    lifecycle = _as_dict(bundle.get("lifecycle")) or bundle
    status = str(
        bundle.get("trade_lifecycle_status")
        or lifecycle.get("status")
        or bundle.get("status")
        or ""
    ).strip()
    exit_ctx = _as_dict(lifecycle.get("exit")) or _as_dict(bundle.get("exit"))
    exit_details = (
        _as_dict(exit_ctx.get("execution_details"))
        or _as_dict(bundle.get("exit_execution_details"))
        or _as_dict(bundle.get("execution_details"))
    )
    return build_post_exit_shadow_placeholder(
        lifecycle_bundle=bundle,
        lifecycle=lifecycle,
        status=status,
        exit_execution_details=exit_details,
    )


def _checkpoint_summary(shadow: Mapping[str, Any]) -> Dict[str, Any]:
    checkpoints = _as_dict(shadow.get("checkpoints"))
    out: Dict[str, Any] = {}
    for label in CHECKPOINT_LABELS:
        row = _as_dict(checkpoints.get(label))
        out[label] = {
            "status": str(row.get("status") or "pending"),
            "price": row.get("price") if row.get("price") is not None else row.get("close"),
            "return_pct": row.get("return_pct"),
            "observed_ts": row.get("observed_ts"),
            "latest_observed_ts": row.get("latest_observed_ts"),
        }
    return out


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100.0:.2f}%"
    except Exception:
        return "-"


def _price(value: Any) -> str:
    try:
        return f"{float(value):,.0f}"
    except Exception:
        return "-"


def _trade_label(path: Path, report: Mapping[str, Any], shadow: Mapping[str, Any]) -> str:
    trade_id = str(report.get("trade_id") or report.get("story_id") or path.parents[1].name).strip()
    symbol = str(shadow.get("symbol") or report.get("symbol") or "").strip()
    if symbol:
        return f"{trade_id} / {symbol}"
    return trade_id


def iter_trade_report_json_paths(reports_root: Path, day: str) -> List[Path]:
    trade_root = reports_root / "trades" / day
    if not trade_root.exists():
        return []
    return sorted(trade_root.rglob("reports/ai_trade_report.json"))


def build_post_exit_shadow_recap(
    *,
    reports_root: Path,
    day: str,
    state: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> Dict[str, Any]:
    state_obj = state if isinstance(state, Mapping) else {}
    trades: List[Dict[str, Any]] = []
    fresh_minute_cache: Dict[str, tuple[List[Dict[str, Any]], Dict[str, Any]]] = {}
    for report_path in iter_trade_report_json_paths(reports_root, day):
        report = _read_json(report_path)
        shadow = _post_exit_shadow_from_report(report)
        if not shadow:
            shadow = _post_exit_shadow_from_lifecycle(report_path)
        if not shadow:
            continue
        symbol = str(shadow.get("symbol") or report.get("symbol") or "").strip()
        rows = minute_rows_for_symbol_from_state(state_obj, symbol) if symbol else []
        rows = same_day_closeout_rows_for_shadow(shadow, rows)
        fresh_minute_fetch: Dict[str, Any] = {"attempted": False}
        if symbol and _fresh_minute_fetch_enabled() and _post_exit_shadow_needs_fresh_minutes(shadow, rows):
            cached = fresh_minute_cache.get(symbol)
            if cached is None:
                fresh_rows, fresh_minute_fetch = fetch_fresh_minute_rows_for_symbol(
                    symbol,
                    run_id=f"post_exit_shadow_recap:{day}:{symbol}",
                )
                fresh_minute_cache[symbol] = (list(fresh_rows), dict(fresh_minute_fetch))
                fresh_minute_fetch = {**fresh_minute_fetch, "cache_hit": False}
            else:
                cached_rows, cached_fetch = cached
                fresh_rows = list(cached_rows)
                fresh_minute_fetch = {**cached_fetch, "cache_hit": True}
            fresh_rows = same_day_closeout_rows_for_shadow(shadow, fresh_rows)
            rows = merge_minute_rows(rows, fresh_rows)
        eod_fallback: Dict[str, Any] = {"applied": False}
        if symbol and not _rows_reach_regular_close(rows):
            fallback_row, eod_fallback = opening_rank1_eod_fallback_row(
                reports_root=reports_root,
                day=day,
                symbol=symbol,
            )
            if fallback_row:
                rows = merge_minute_rows(rows, [fallback_row])
        updated_shadow = (
            update_post_exit_shadow_with_price_observations(shadow, minute_rows=rows)
            if rows
            else dict(shadow)
        )
        updated_shadow = _fill_regular_close_bound_pending_checkpoints(updated_shadow)
        checkpoints = _checkpoint_summary(updated_shadow)
        trades.append(
            {
                "trade_id": str(report.get("trade_id") or report.get("story_id") or report_path.parents[1].name),
                "symbol": symbol,
                "report_path": str(report_path),
                "recap_json_path": str(report_path.with_name("post_exit_shadow_recap.json")),
                "recap_md_path": str(report_path.with_name("post_exit_shadow_recap.md")),
                "price_observation_status": str(updated_shadow.get("price_observation_status") or "pending"),
                "price_observation_reason": str(updated_shadow.get("price_observation_reason") or ""),
                "latest_observed_ts": updated_shadow.get("latest_observed_ts"),
                "best_exit_offset": str(updated_shadow.get("best_exit_offset") or ""),
                "best_exit_price": updated_shadow.get("best_exit_price"),
                "max_post_exit_upside_pct": updated_shadow.get("max_post_exit_upside_pct"),
                "max_post_exit_drawdown_pct": updated_shadow.get("max_post_exit_drawdown_pct"),
                "checkpoints": checkpoints,
                "post_exit_shadow": updated_shadow,
                "label": _trade_label(report_path, report, updated_shadow),
                "source_minute_rows": len(rows),
                "fresh_minute_fetch": fresh_minute_fetch,
                "eod_fallback": eod_fallback,
            }
        )

    observed_count = sum(1 for trade in trades if trade.get("price_observation_status") == "observed")
    eod_observed_count = sum(
        1
        for trade in trades
        if _as_dict(_as_dict(trade.get("checkpoints")).get("EOD")).get("status") == "observed"
    )
    return {
        "schema_version": "post_exit_shadow_recap.v1",
        "observability_only": True,
        "day": str(day),
        "generated_at": str(generated_at or _utc_now_iso()),
        "policy": {
            "bulk_update_time_kst": "stage4_closeout_review + 16:00",
            "trigger": "runtime.stage4_carry_review|runtime.closeout_guard_after_sweep|closeout.post_exit_shadow_recap",
            "schedule_semantics": "Refreshes after the runtime stage4 carry review, again after the closeout sweep, and through the 16:00 closeout recap task.",
            "rewrite_trade_reports": False,
            "refresh_trade_summary": True,
            "note": "ai_trade_report.json is kept immutable; recap artifacts and ai_trade_summary artifacts are refreshed.",
        },
        "summary": {
            "total": len(trades),
            "observed": observed_count,
            "pending": len(trades) - observed_count,
            "eod_observed": eod_observed_count,
        },
        "trades": trades,
    }


def render_post_exit_shadow_trade_recap_md(trade: Mapping[str, Any]) -> str:
    lines = [
        f"# 매도 후 가격 추적 Recap - {trade.get('label')}",
        "",
        "- 기준: 실제 매도 후 같은 종목을 가상 보유했다고 가정한 관측-only 결과입니다.",
        "- 적용: 기존 거래 리포트 본문은 수정하지 않습니다.",
        f"- 가격 관측 상태: {trade.get('price_observation_status')}",
        f"- 사유: {trade.get('price_observation_reason') or '-'}",
        f"- 마지막 관측 시각: {trade.get('latest_observed_ts') or '-'}",
        f"- 최선 관측 지점: {trade.get('best_exit_offset') or '-'} / {_price(trade.get('best_exit_price'))}",
        f"- 최대 매도 후 상승: {_pct(trade.get('max_post_exit_upside_pct'))}",
        f"- 최대 매도 후 하락: {_pct(trade.get('max_post_exit_drawdown_pct'))}",
        "",
        "| 지점 | 상태 | 가격 | 수익률 | 관측 시각 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    checkpoints = _as_dict(trade.get("checkpoints"))
    for label in CHECKPOINT_LABELS:
        row = _as_dict(checkpoints.get(label))
        lines.append(
            f"| {label} | {row.get('status') or 'pending'} | {_price(row.get('price'))} | "
            f"{_pct(row.get('return_pct'))} | {row.get('observed_ts') or row.get('latest_observed_ts') or '-'} |"
        )
    return "\n".join(lines) + "\n"


def render_post_exit_shadow_daily_recap_md(recap: Mapping[str, Any]) -> str:
    summary = _as_dict(recap.get("summary"))
    lines = [
        f"# 매도 후 가격 추적 일괄 Recap ({recap.get('day')})",
        "",
        "- 기준: 16:00 closeout에서 당일 매도 후 가격 추적을 일괄 산출합니다.",
        "- 적용: 기존 ai_trade_report 본문은 수정하지 않고 별도 recap 파일만 생성합니다.",
        f"- 총 대상: {summary.get('total', 0)}건",
        f"- 관측 완료: {summary.get('observed', 0)}건",
        f"- EOD 관측 완료: {summary.get('eod_observed', 0)}건",
        f"- 대기: {summary.get('pending', 0)}건",
        "",
        "| 거래 | 상태 | +5m | +15m | +30m | +60m | EOD | 최선 지점 | 최대 상승 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for trade in _as_list(recap.get("trades")):
        if not isinstance(trade, dict):
            continue
        checkpoints = _as_dict(trade.get("checkpoints"))
        returns = []
        for label in CHECKPOINT_LABELS:
            row = _as_dict(checkpoints.get(label))
            returns.append(_pct(row.get("return_pct")) if row.get("status") == "observed" else "-")
        lines.append(
            f"| {trade.get('label')} | {trade.get('price_observation_status')} | "
            f"{returns[0]} | {returns[1]} | {returns[2]} | {returns[3]} | {returns[4]} | "
            f"{trade.get('best_exit_offset') or '-'} | {_pct(trade.get('max_post_exit_upside_pct'))} |"
        )
    return "\n".join(lines) + "\n"


def render_post_exit_shadow_trade_recap_md(trade: Mapping[str, Any]) -> str:
    lines = [
        f"# 매도 후 가격 추적 Recap - {trade.get('label')}",
        "",
        "- 기준: 실제 매도 후 같은 종목을 가상 보유했다고 가정한 관측-only 결과입니다.",
        "- 적용: 기존 ai_trade_report 본문은 수정하지 않고 recap 및 summary 산출물만 갱신합니다.",
        f"- 가격 관측 상태: {trade.get('price_observation_status')}",
        f"- 사유: {trade.get('price_observation_reason') or '-'}",
        f"- 마지막 관측 시각: {trade.get('latest_observed_ts') or '-'}",
        f"- 최선 관측 지점: {trade.get('best_exit_offset') or '-'} / {_price(trade.get('best_exit_price'))}",
        f"- 최대 매도 후 상승: {_pct(trade.get('max_post_exit_upside_pct'))}",
        f"- 최대 매도 후 하락: {_pct(trade.get('max_post_exit_drawdown_pct'))}",
        "",
        "| 지점 | 상태 | 가격 | 수익률 | 관측 시각 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    checkpoints = _as_dict(trade.get("checkpoints"))
    for label in CHECKPOINT_LABELS:
        row = _as_dict(checkpoints.get(label))
        lines.append(
            f"| {label} | {row.get('status') or 'pending'} | {_price(row.get('price'))} | "
            f"{_pct(row.get('return_pct'))} | {row.get('observed_ts') or row.get('latest_observed_ts') or '-'} |"
        )
    return "\n".join(lines) + "\n"


def render_post_exit_shadow_daily_recap_md(recap: Mapping[str, Any]) -> str:
    summary = _as_dict(recap.get("summary"))
    lines = [
        f"# 매도 후 가격 추적 일괄 Recap ({recap.get('day')})",
        "",
        "- 기준: stage4 closeout review와 16:00 closeout에서 당일 매도 후 가격 추적을 일괄 갱신합니다.",
        "- 적용: 기존 ai_trade_report 본문은 수정하지 않고 recap 및 ai_trade_summary 산출물만 갱신합니다.",
        f"- 총 대상: {summary.get('total', 0)}건",
        f"- 관측 완료: {summary.get('observed', 0)}건",
        f"- EOD 관측 완료: {summary.get('eod_observed', 0)}건",
        f"- 대기: {summary.get('pending', 0)}건",
        "",
        "| 거래 | 상태 | +5m | +15m | +30m | +60m | EOD | 최선 지점 | 최대 상승 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for trade in _as_list(recap.get("trades")):
        if not isinstance(trade, dict):
            continue
        checkpoints = _as_dict(trade.get("checkpoints"))
        returns = []
        for label in CHECKPOINT_LABELS:
            row = _as_dict(checkpoints.get(label))
            returns.append(_pct(row.get("return_pct")) if row.get("status") == "observed" else "-")
        lines.append(
            f"| {trade.get('label')} | {trade.get('price_observation_status')} | "
            f"{returns[0]} | {returns[1]} | {returns[2]} | {returns[3]} | {returns[4]} | "
            f"{trade.get('best_exit_offset') or '-'} | {_pct(trade.get('max_post_exit_upside_pct'))} |"
        )
    return "\n".join(lines) + "\n"


def _render_trade_recap_markdown(trade: Mapping[str, Any]) -> str:
    lines = [
        f"# 매도 후 가격 추적 Recap - {trade.get('label')}",
        "",
        "- 기준: 실제 매도 후 같은 종목을 가상 보유했다고 가정한 관측 전용 결과입니다.",
        "- 적용: 기존 ai_trade_report 본문은 수정하지 않고 recap과 summary 산출물만 갱신합니다.",
        f"- 가격 관측 상태: {trade.get('price_observation_status')}",
        f"- 사유: {trade.get('price_observation_reason') or '-'}",
        f"- 마지막 관측 시각: {trade.get('latest_observed_ts') or '-'}",
        f"- 최선 관측 지점: {trade.get('best_exit_offset') or '-'} / {_price(trade.get('best_exit_price'))}",
        f"- 최대 매도 후 상승: {_pct(trade.get('max_post_exit_upside_pct'))}",
        f"- 최대 매도 후 하락: {_pct(trade.get('max_post_exit_drawdown_pct'))}",
        "",
        "| 지점 | 상태 | 가격 | 수익률 | 관측 시각 |",
        "| --- | --- | ---: | ---: | --- |",
    ]
    checkpoints = _as_dict(trade.get("checkpoints"))
    for label in CHECKPOINT_LABELS:
        row = _as_dict(checkpoints.get(label))
        lines.append(
            f"| {label} | {row.get('status') or 'pending'} | {_price(row.get('price'))} | "
            f"{_pct(row.get('return_pct'))} | {row.get('observed_ts') or row.get('latest_observed_ts') or '-'} |"
        )
    return "\n".join(lines) + "\n"


def _render_daily_recap_markdown(recap: Mapping[str, Any]) -> str:
    summary = _as_dict(recap.get("summary"))
    lines = [
        f"# 매도 후 가격 추적 일괄 Recap ({recap.get('day')})",
        "",
        "- 기준: stage4 closeout review와 16:00 closeout에서 당일 매도 후 가격 추적을 일괄 갱신합니다.",
        "- 적용: 기존 ai_trade_report 본문은 수정하지 않고 recap과 ai_trade_summary 산출물만 갱신합니다.",
        f"- 총 대상: {summary.get('total', 0)}건",
        f"- 관측 완료: {summary.get('observed', 0)}건",
        f"- EOD 관측 완료: {summary.get('eod_observed', 0)}건",
        f"- 대기: {summary.get('pending', 0)}건",
        "",
        "| 거래 | 상태 | +5m | +15m | +30m | +60m | EOD | 최선 지점 | 최대 상승 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]
    for trade in _as_list(recap.get("trades")):
        if not isinstance(trade, dict):
            continue
        checkpoints = _as_dict(trade.get("checkpoints"))
        returns = []
        for label in CHECKPOINT_LABELS:
            row = _as_dict(checkpoints.get(label))
            returns.append(_pct(row.get("return_pct")) if row.get("status") == "observed" else "-")
        lines.append(
            f"| {trade.get('label')} | {trade.get('price_observation_status')} | "
            f"{returns[0]} | {returns[1]} | {returns[2]} | {returns[3]} | {returns[4]} | "
            f"{trade.get('best_exit_offset') or '-'} | {_pct(trade.get('max_post_exit_upside_pct'))} |"
        )
    return "\n".join(lines) + "\n"


def write_post_exit_shadow_recap_outputs(
    recap: Mapping[str, Any],
    *,
    report_dir: Path,
) -> Dict[str, str]:
    report_dir.mkdir(parents=True, exist_ok=True)
    day = str(recap.get("day") or "unknown")
    daily_json = report_dir / day / "post_exit_shadow_recap.json"
    daily_md = report_dir / day / "post_exit_shadow_recap.md"

    for trade in _as_list(recap.get("trades")):
        if not isinstance(trade, dict):
            continue
        _refresh_trade_summary_from_recap(trade)
        json_path = Path(str(trade.get("recap_json_path") or ""))
        md_path = Path(str(trade.get("recap_md_path") or ""))
        if str(json_path):
            _write_json(json_path, trade)
        if str(md_path):
            _write_text(md_path, _render_trade_recap_markdown(trade))

    _write_json(daily_json, recap)
    _write_text(daily_md, _render_daily_recap_markdown(recap))

    return {"report_json_path": str(daily_json), "report_md_path": str(daily_md)}


def _refresh_trade_summary_from_recap(trade: Dict[str, Any]) -> None:
    report_path = Path(str(trade.get("report_path") or ""))
    if not str(report_path) or not report_path.exists():
        trade["summary_refresh"] = {"attempted": False, "reason": "report_path_missing"}
        return

    reports_dir = report_path.parent
    summary_md_path = reports_dir / "ai_trade_summary.md"
    summary_input_path = reports_dir / "ai_trade_summary_input.json"
    summary_json_path = reports_dir / "ai_trade_summary.json"
    if not summary_md_path.exists() and not summary_input_path.exists():
        trade["summary_refresh"] = {"attempted": False, "reason": "summary_artifacts_missing"}
        return

    try:
        report = _read_json(report_path)
        shadow = _as_dict(trade.get("post_exit_shadow"))
        if shadow:
            report["post_exit_shadow"] = dict(shadow)
            fact_payload = _as_dict(report.get("fact_payload"))
            fact_trade = _as_dict(fact_payload.get("trade"))
            fact_trade["post_exit_shadow"] = dict(shadow)
            fact_payload["trade"] = fact_trade
            fact_payload["post_exit_shadow"] = dict(shadow)
            report["fact_payload"] = fact_payload

        from libs.reporting.trade_report_ai import (
            build_trade_summary_input,
            render_trade_summary_markdown,
            render_trade_summary_markdown_with_evaluation,
        )

        if summary_input_path.exists():
            _write_json(summary_input_path, build_trade_summary_input(report))
        if summary_md_path.exists():
            summary_report = _read_json(summary_json_path) if summary_json_path.exists() else {}
            if summary_report:
                summary_md = render_trade_summary_markdown_with_evaluation(report, summary_report)
            else:
                summary_md = render_trade_summary_markdown(report)
            _write_text(summary_md_path, summary_md)
        trade["summary_refresh"] = {
            "attempted": True,
            "ok": True,
            "summary_md_path": str(summary_md_path) if summary_md_path.exists() else "",
            "summary_input_path": str(summary_input_path) if summary_input_path.exists() else "",
        }
    except Exception as exc:
        trade["summary_refresh"] = {
            "attempted": True,
            "ok": False,
            "reason": "summary_refresh_failed",
            "error": str(exc),
        }


def generate_post_exit_shadow_recap(
    *,
    reports_root: Path,
    report_dir: Path,
    day: str,
    state_path: Path | None = None,
) -> Dict[str, Any]:
    resolved_state_path = resolve_post_exit_state_path(reports_root, state_path)
    state = _read_json(resolved_state_path) if resolved_state_path and resolved_state_path.exists() else {}
    recap = build_post_exit_shadow_recap(
        reports_root=reports_root,
        day=day,
        state=state,
    )
    recap["source"] = {
        "state_path": str(resolved_state_path) if resolved_state_path else "",
        "state_loaded": bool(state),
        "state_top_level_keys": len(state) if isinstance(state, dict) else 0,
    }
    paths = write_post_exit_shadow_recap_outputs(recap, report_dir=report_dir)
    out = dict(recap)
    out.update(paths)
    return out
