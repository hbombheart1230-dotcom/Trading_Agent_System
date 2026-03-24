from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _parse_iso_utc_seconds(value: Any) -> Optional[int]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(datetime.fromisoformat(text).timestamp())
    except Exception:
        return None


def _to_float(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except Exception:
        return None
    if out != out:
        return None
    return out


def _estimate_reclaim_price(current_price: Any, vwap_distance: Any, reclaim_tolerance_pct: Any) -> Optional[float]:
    price = _to_float(current_price)
    dist = _to_float(vwap_distance)
    tol = _to_float(reclaim_tolerance_pct)
    if price is None or dist is None or tol is None:
        return None
    denom = 1.0 + dist
    if abs(denom) < 1e-9:
        return None
    est_vwap = price / denom
    return est_vwap * (1.0 - tol)


def _iter_monitor_rows(canonical_root: Path, *, day: str) -> List[Dict[str, Any]]:
    day_root = canonical_root / day
    if not day_root.exists():
        return []
    out: List[Dict[str, Any]] = []
    for monitor_path in sorted(day_root.glob("*/monitor.json")):
        run_id = monitor_path.parent.name
        if run_id.startswith("run-monitor-minute"):
            continue
        monitor = _read_json(monitor_path)
        shadow = _read_json(monitor_path.with_name("commander_shadow.json"))
        gate = shadow.get("monitor_gate_details") if isinstance(shadow.get("monitor_gate_details"), dict) else {}
        observed = gate.get("observed_features") if isinstance(gate.get("observed_features"), dict) else {}
        thresholds = gate.get("used_thresholds") if isinstance(gate.get("used_thresholds"), dict) else {}
        ts_epoch = _parse_iso_utc_seconds(monitor.get("ts"))
        latest_candle_ts = observed.get("latest_candle_ts")
        current_price = (
            observed.get("current_price")
            or observed.get("price")
            or monitor.get("current_price")
            or ((monitor.get("position_snapshot") or {}).get("current_price") if isinstance(monitor.get("position_snapshot"), dict) else None)
        )
        vwap_distance = observed.get("vwap_distance")
        reclaim_price = _estimate_reclaim_price(current_price, vwap_distance, thresholds.get("reclaim_tolerance_pct"))
        artifact_age_min: Optional[float] = None
        if ts_epoch is not None and latest_candle_ts is not None:
            try:
                artifact_age_min = round((ts_epoch - int(latest_candle_ts)) / 60.0, 3)
            except Exception:
                artifact_age_min = None
        out.append(
            {
                "run_id": run_id,
                "symbol": str(monitor.get("symbol") or "").strip(),
                "ts": str(monitor.get("ts") or "").strip(),
                "ts_epoch": ts_epoch,
                "evaluation_summary": str(monitor.get("evaluation_summary") or "").strip(),
                "primary_reason_code": str(monitor.get("primary_reason_code") or "").strip(),
                "decision_status": str(monitor.get("decision_status") or "").strip(),
                "latest_candle_ts": latest_candle_ts,
                "inferred_spacing_minutes": observed.get("inferred_spacing_minutes"),
                "series_class": str(observed.get("series_class") or "").strip(),
                "minute_source_present": bool(observed.get("minute_source_present")),
                "minute_source_used": str(observed.get("minute_source_used") or "").strip(),
                "artifact_age_minutes": artifact_age_min,
                "current_price": _to_float(current_price),
                "vwap_distance": _to_float(vwap_distance),
                "vwap_distance_pct": (_to_float(vwap_distance) * 100.0) if _to_float(vwap_distance) is not None else None,
                "reclaim_tolerance_pct": (_to_float(thresholds.get("reclaim_tolerance_pct")) * 100.0)
                if _to_float(thresholds.get("reclaim_tolerance_pct")) is not None
                else None,
                "reclaim_price": reclaim_price,
                "reclaim_gap_pct": ((float(current_price) / reclaim_price) - 1.0) * 100.0
                if _to_float(current_price) is not None and reclaim_price
                else None,
                "breakout_level": _to_float(observed.get("breakout_level")),
                "breakout_gap_pct": ((float(current_price) / float(observed.get("breakout_level"))) - 1.0) * 100.0
                if _to_float(current_price) is not None and _to_float(observed.get("breakout_level")) not in (None, 0.0)
                else None,
                "volume_ratio": _to_float(observed.get("volume_ratio")),
                "pullback_pct": (_to_float(observed.get("pullback_pct")) * 100.0)
                if _to_float(observed.get("pullback_pct")) is not None
                else None,
                "entry_block_reason": str(gate.get("entry_block_reason") or "").strip(),
                "failed_gates": list(gate.get("failed_gates") or []),
                "passed_gates": list(gate.get("passed_gates") or []),
            }
        )
    return out


def _build_stale_groups(rows: Iterable[Dict[str, Any]], *, stale_age_min: float = 3.0) -> List[Dict[str, Any]]:
    groups: Dict[tuple[str, str, Any], List[Dict[str, Any]]] = {}
    for row in rows:
        if not row.get("minute_source_present"):
            continue
        latest_candle_ts = row.get("latest_candle_ts")
        if latest_candle_ts in (None, ""):
            continue
        age = _to_float(row.get("artifact_age_minutes"))
        if age is None or age < stale_age_min:
            continue
        key = (str(row.get("symbol") or ""), str(row.get("evaluation_summary") or ""), latest_candle_ts)
        groups.setdefault(key, []).append(row)
    out: List[Dict[str, Any]] = []
    for (symbol, reason, latest_candle_ts), cases in groups.items():
        cases = sorted(cases, key=lambda row: str(row.get("ts") or ""))
        out.append(
            {
                "symbol": symbol,
                "evaluation_summary": reason,
                "latest_candle_ts": latest_candle_ts,
                "repeat_count": len(cases),
                "first_run_id": cases[0].get("run_id"),
                "last_run_id": cases[-1].get("run_id"),
                "max_artifact_age_minutes": max((_to_float(row.get("artifact_age_minutes")) or 0.0) for row in cases),
                "runs": [str(row.get("run_id") or "") for row in cases],
            }
        )
    out.sort(key=lambda row: (-int(row["repeat_count"]), row["symbol"], row["evaluation_summary"]))
    return out


def _followup_from_rows(case: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    latest_candle_ts = int(case.get("latest_candle_ts") or 0)
    blocked_price = _to_float(case.get("current_price"))
    breakout_level = _to_float(case.get("breakout_level"))
    reclaim_price = _to_float(case.get("reclaim_price"))
    later = [row for row in rows if int(row.get("ts") or 0) > latest_candle_ts]
    if not later or blocked_price in (None, 0.0):
        return {"later_bars": 0}
    max_high = max(_to_float(row.get("high")) or 0.0 for row in later)
    min_low = min(_to_float(row.get("low")) or 0.0 for row in later)
    last_close = _to_float(later[-1].get("close"))
    return {
        "later_bars": len(later),
        "max_high_after": max_high,
        "min_low_after": min_low,
        "last_close_now": last_close,
        "move_to_max_pct": ((max_high / blocked_price) - 1.0) * 100.0 if max_high > 0 else None,
        "move_to_min_pct": ((min_low / blocked_price) - 1.0) * 100.0 if min_low > 0 else None,
        "move_to_last_pct": ((last_close / blocked_price) - 1.0) * 100.0 if last_close else None,
        "crossed_breakout_after": bool(breakout_level and max_high >= breakout_level),
        "crossed_reclaim_after": bool(reclaim_price and max_high >= reclaim_price),
    }


def _load_live_minute_rows(symbol: str, *, retries: int = 3, sleep_sec: float = 0.2) -> List[Dict[str, Any]]:
    from libs.skills.runner import CompositeSkillRunner

    runner = CompositeSkillRunner.from_env()
    rows: List[Dict[str, Any]] = []
    for idx in range(max(1, retries)):
        out = runner.run(
            run_id=f"analysis-monitor-gate-{symbol}-{idx}",
            skill="market.minute_ohlcv",
            args={"symbol": symbol, "timeframe_minutes": 1, "adjusted_price": "1"},
        )
        data = getattr(out, "data", None)
        candidate = getattr(data, "rows", None)
        if isinstance(candidate, list) and candidate:
            rows = candidate
            break
        time.sleep(max(0.0, float(sleep_sec)))
    return rows


def analyze_monitor_gate_patterns(
    canonical_root: Path,
    *,
    day: str,
    reason_filter: str = "",
    stale_age_min: float = 3.0,
    include_live_followup: bool = False,
) -> Dict[str, Any]:
    rows = _iter_monitor_rows(canonical_root, day=day)
    if reason_filter:
        rows = [row for row in rows if row.get("evaluation_summary") == reason_filter]
    reason_counts = Counter(str(row.get("evaluation_summary") or "") for row in rows)
    symbol_counts = Counter(str(row.get("symbol") or "") for row in rows)
    stale_groups = _build_stale_groups(rows, stale_age_min=stale_age_min)

    repeated_states = Counter(
        (
            str(row.get("symbol") or ""),
            str(row.get("evaluation_summary") or ""),
            row.get("latest_candle_ts"),
            round(_to_float(row.get("vwap_distance") or 0.0) or 0.0, 4),
            round(_to_float(row.get("volume_ratio") or 0.0) or 0.0, 3),
            round(_to_float(row.get("pullback_pct") or 0.0) or 0.0, 3),
        )
        for row in rows
    )
    repeated_state_rows = [
        {
            "symbol": symbol,
            "evaluation_summary": reason,
            "latest_candle_ts": latest_candle_ts,
            "vwap_distance": vwap_distance,
            "volume_ratio": volume_ratio,
            "pullback_pct": pullback_pct,
            "repeat_count": count,
        }
        for (symbol, reason, latest_candle_ts, vwap_distance, volume_ratio, pullback_pct), count in repeated_states.most_common()
    ]

    live_followup: List[Dict[str, Any]] = []
    if include_live_followup:
        symbol_cache: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            symbol = str(row.get("symbol") or "")
            if not symbol:
                continue
            if symbol not in symbol_cache:
                symbol_cache[symbol] = _load_live_minute_rows(symbol)
            if row.get("evaluation_summary") != "below_vwap_reclaim_not_ready":
                continue
            followup = _followup_from_rows(row, symbol_cache[symbol])
            live_followup.append(
                {
                    "run_id": row.get("run_id"),
                    "symbol": symbol,
                    "evaluation_summary": row.get("evaluation_summary"),
                    "latest_candle_ts": row.get("latest_candle_ts"),
                    **followup,
                }
            )

    return {
        "day": day,
        "row_count": len(rows),
        "reason_counts": dict(reason_counts),
        "symbol_counts": dict(symbol_counts),
        "stale_groups": stale_groups,
        "repeated_states": repeated_state_rows,
        "rows": rows,
        "live_followup": live_followup,
    }


def _print_human(summary: Dict[str, Any]) -> None:
    print("=== Monitor Gate Pattern Check ===")
    print(f"day={summary.get('day')} row_count={summary.get('row_count')}")
    print(f"reason_counts={json.dumps(summary.get('reason_counts', {}), ensure_ascii=False)}")
    print(f"symbol_counts={json.dumps(summary.get('symbol_counts', {}), ensure_ascii=False)}")
    stale_groups = summary.get("stale_groups") or []
    if stale_groups:
        print("stale_snapshot_groups:")
        for row in stale_groups:
            print(
                f"  symbol={row.get('symbol')} reason={row.get('evaluation_summary')} "
                f"latest_candle_ts={row.get('latest_candle_ts')} repeat_count={row.get('repeat_count')} "
                f"max_artifact_age_min={row.get('max_artifact_age_minutes')}"
            )
    rows = summary.get("rows") or []
    if rows:
        print("rows:")
        for row in rows:
            print(
                f"  run_id={row.get('run_id')} symbol={row.get('symbol')} reason={row.get('evaluation_summary')} "
                f"price={row.get('current_price')} vwap_distance_pct={row.get('vwap_distance_pct')} "
                f"reclaim_gap_pct={row.get('reclaim_gap_pct')} breakout_gap_pct={row.get('breakout_gap_pct')} "
                f"volume_ratio={row.get('volume_ratio')} pullback_pct={row.get('pullback_pct')} "
                f"latest_candle_ts={row.get('latest_candle_ts')} age_min={row.get('artifact_age_minutes')}"
            )
    live_followup = summary.get("live_followup") or []
    if live_followup:
        print("live_followup:")
        for row in live_followup:
            print(
                f"  run_id={row.get('run_id')} symbol={row.get('symbol')} later_bars={row.get('later_bars')} "
                f"move_to_max_pct={row.get('move_to_max_pct')} move_to_last_pct={row.get('move_to_last_pct')} "
                f"crossed_breakout_after={row.get('crossed_breakout_after')} crossed_reclaim_after={row.get('crossed_reclaim_after')}"
            )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only monitor gate pattern check from canonical artifacts.")
    parser.add_argument("--canonical-root", default="./reports/canonical")
    parser.add_argument("--day", required=True, help="Artifact day, e.g. 2026-03-24")
    parser.add_argument("--reason", default="", help="Optional evaluation_summary filter.")
    parser.add_argument("--stale-age-min", type=float, default=3.0)
    parser.add_argument("--live-followup", action="store_true", help="Fetch current minute candles to inspect post-block moves.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    summary = analyze_monitor_gate_patterns(
        Path(str(args.canonical_root).strip()),
        day=str(args.day).strip(),
        reason_filter=str(args.reason or "").strip(),
        stale_age_min=max(0.0, float(args.stale_age_min)),
        include_live_followup=bool(args.live_followup),
    )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        _print_human(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
