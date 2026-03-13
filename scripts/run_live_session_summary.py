from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


def _to_epoch(ts: Any) -> Optional[int]:
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return int(ts)

    s = str(ts).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except Exception:
        pass

    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj

    return _gen()


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_pct(num: float, den: float) -> float:
    if den <= 0.0:
        return 0.0
    return float(num) / float(den)


def _broker_code_success(value: Any) -> Optional[bool]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s)) == 0
    except Exception:
        pass
    t = s.lower()
    if t in ("ok", "success", "accepted"):
        return True
    if t in ("error", "failed", "rejected"):
        return False
    return False


def _utc_iso(epoch: int) -> str:
    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()


def _build_markdown(out: Dict[str, Any]) -> str:
    ev = out.get("events") if isinstance(out.get("events"), dict) else {}
    llm = out.get("strategist_llm") if isinstance(out.get("strategist_llm"), dict) else {}
    dec = out.get("decision") if isinstance(out.get("decision"), dict) else {}
    exe = out.get("execution") if isinstance(out.get("execution"), dict) else {}
    ctl = out.get("controls") if isinstance(out.get("controls"), dict) else {}

    lines = [
        f"# Live Session Summary ({out.get('window_start_utc')} ~ {out.get('window_end_utc')})",
        "",
        f"- lookback_min: **{int(out.get('lookback_min') or 0)}**",
        f"- event_log_path: `{out.get('event_log_path')}`",
        "",
        "## Events",
        "",
        f"- scanned_total: **{int(ev.get('scanned_total') or 0)}**",
        f"- window_total: **{int(ev.get('window_total') or 0)}**",
        f"- missing_ts_total: **{int(ev.get('missing_ts_total') or 0)}**",
        "",
        "## Strategist LLM",
        "",
        f"- total: **{int(llm.get('total') or 0)}**",
        f"- ok_total: **{int(llm.get('ok_total') or 0)}**",
        f"- error_total: **{int(llm.get('error_total') or 0)}**",
        f"- error_rate: **{float(llm.get('error_rate') or 0.0):.2%}**",
        f"- latency_avg_ms: **{float(llm.get('latency_avg_ms') or 0.0):.1f}**",
        "",
        "## Decisions",
        "",
        f"- action_counts: `{json.dumps(dec.get('action_counts') or {}, ensure_ascii=False)}`",
        f"- strategy_counts: `{json.dumps(dec.get('strategy_counts') or {}, ensure_ascii=False)}`",
        f"- reason_top: `{json.dumps(dec.get('reason_top') or {}, ensure_ascii=False)}`",
        "",
        "## Execution",
        "",
        f"- verdict_total: **{int(exe.get('verdict_total') or 0)}**",
        f"- allowed_total: **{int(exe.get('allowed_total') or 0)}**",
        f"- blocked_total: **{int(exe.get('blocked_total') or 0)}**",
        f"- blocked_reason_top: `{json.dumps(exe.get('blocked_reason_top') or {}, ensure_ascii=False)}`",
        f"- executed_total: **{int(exe.get('executed_total') or 0)}**",
        f"- executed_broker_success_total: **{int(exe.get('executed_broker_success_total') or 0)}**",
        f"- executed_broker_fail_total: **{int(exe.get('executed_broker_fail_total') or 0)}**",
        f"- executed_broker_unknown_total: **{int(exe.get('executed_broker_unknown_total') or 0)}**",
        f"- executed_broker_code_top: `{json.dumps(exe.get('executed_broker_code_top') or {}, ensure_ascii=False)}`",
        f"- executed_action_counts: `{json.dumps(exe.get('executed_action_counts') or {}, ensure_ascii=False)}`",
        f"- executed_notional_total: **{float(exe.get('executed_notional_total') or 0.0):.2f}**",
        "",
        "## Controls",
        "",
        f"- cooldown_noop_total: **{int(ctl.get('cooldown_noop_total') or 0)}**",
        f"- exit_policy_sell_total: **{int(ctl.get('exit_policy_sell_total') or 0)}**",
        f"- insufficient_mock_cash_block_total: **{int(ctl.get('insufficient_mock_cash_block_total') or 0)}**",
        "",
    ]
    return "\n".join(lines)


def _parse_args(argv: Optional[List[str]]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate live-session summary over recent event window.")
    p.add_argument(
        "--event-log-path",
        default=os.getenv("EVENT_LOG_PATH", "data/logs/events_live.jsonl"),
        help="JSONL event log path (default: EVENT_LOG_PATH or data/logs/events_live.jsonl).",
    )
    p.add_argument("--report-dir", default="reports/dev/live/live_summary")
    p.add_argument("--lookback-min", type=int, default=_safe_int(os.getenv("LIVE_SUMMARY_LOOKBACK_MIN"), 30))
    p.add_argument("--now-epoch", type=float, default=0.0, help="Override current epoch for deterministic checks/tests.")
    p.add_argument("--json", action="store_true", help="Print full JSON output.")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv)
    event_log_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    lookback_min = max(1, int(args.lookback_min))
    now_epoch = int(float(args.now_epoch)) if float(args.now_epoch or 0.0) > 0.0 else int(time.time())
    start_epoch = now_epoch - lookback_min * 60

    if not event_log_path.exists():
        print(f"ERROR: event log path does not exist: {event_log_path}", file=sys.stderr)
        return 2

    report_dir.mkdir(parents=True, exist_ok=True)

    scanned_total = 0
    missing_ts_total = 0
    window_rows: List[Dict[str, Any]] = []
    for row in _iter_jsonl(event_log_path):
        scanned_total += 1
        e = _to_epoch(row.get("ts"))
        if e is None:
            missing_ts_total += 1
            continue
        if start_epoch <= int(e) <= now_epoch:
            window_rows.append(row)

    llm_total = 0
    llm_ok_total = 0
    llm_error_total = 0
    llm_action_counts: Counter[str] = Counter()
    llm_reason_counts: Counter[str] = Counter()
    llm_error_type_counts: Counter[str] = Counter()
    llm_latency_ms: List[float] = []

    decision_action_counts: Counter[str] = Counter()
    decision_reason_counts: Counter[str] = Counter()
    decision_strategy_counts: Counter[str] = Counter()

    verdict_total = 0
    verdict_allowed_total = 0
    verdict_blocked_total = 0
    verdict_block_reason_counts: Counter[str] = Counter()

    executed_total = 0
    executed_broker_success_total = 0
    executed_broker_fail_total = 0
    executed_broker_unknown_total = 0
    executed_broker_code_counts: Counter[str] = Counter()
    executed_action_counts: Counter[str] = Counter()
    executed_notional_total = 0.0

    cooldown_noop_total = 0
    exit_policy_sell_total = 0
    insufficient_mock_cash_block_total = 0

    for row in window_rows:
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}

        if stage == "strategist_llm" and event == "result":
            llm_total += 1
            ok = bool(payload.get("ok"))
            if ok:
                llm_ok_total += 1
            else:
                llm_error_total += 1
            action = str(payload.get("intent_action") or "").strip().upper()
            if action:
                llm_action_counts[action] += 1
            reason = str(payload.get("intent_reason") or "").strip()
            if reason:
                llm_reason_counts[reason] += 1
            err = str(payload.get("error_type") or "").strip()
            if err:
                llm_error_type_counts[err] += 1
            lat = _safe_float(payload.get("latency_ms"), -1.0)
            if lat >= 0.0:
                llm_latency_ms.append(lat)

        elif stage == "decision" and event == "trace":
            dp = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
            intent = dp.get("intent") if isinstance(dp.get("intent"), dict) else {}
            trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
            raw_intent = trace.get("raw_intent") if isinstance(trace.get("raw_intent"), dict) else {}

            action = str(intent.get("action") or "").strip().upper()
            if action:
                decision_action_counts[action] += 1

            reason = str(intent.get("reason") or "").strip()
            if not reason:
                reason = str(raw_intent.get("reason") or "").strip()
            if reason:
                decision_reason_counts[reason] += 1

            strategy = str(trace.get("strategy") or "").strip()
            if strategy:
                decision_strategy_counts[strategy] += 1

            if action == "NOOP" and reason == "post_exit_cooldown":
                cooldown_noop_total += 1

        elif stage == "execute_from_packet" and event == "verdict":
            verdict_total += 1
            allowed = bool(payload.get("allowed"))
            if allowed:
                verdict_allowed_total += 1
            else:
                verdict_blocked_total += 1
                reason = str(payload.get("reason") or "").strip() or "unknown"
                verdict_block_reason_counts[reason] += 1
                if reason == "insufficient_mock_cash":
                    insufficient_mock_cash_block_total += 1

        elif stage == "execute_from_packet" and event == "execution":
            executed_total += 1
            order = payload.get("order") if isinstance(payload.get("order"), dict) else {}
            action = str(order.get("action") or "").strip().upper()
            if action:
                executed_action_counts[action] += 1
            qty = _safe_float(order.get("qty"), 0.0)
            px = _safe_float(order.get("price"), 0.0)
            if qty > 0.0 and px > 0.0:
                executed_notional_total += qty * px
            rationale = str(order.get("rationale") or "").strip().lower()
            if action == "SELL" and rationale.startswith("exit_policy:"):
                exit_policy_sell_total += 1

            ex_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            broker_code = str(ex_payload.get("broker_code") or "").strip()
            if broker_code:
                executed_broker_code_counts[broker_code] += 1
            broker_ok = _broker_code_success(ex_payload.get("broker_code"))
            if broker_ok is None:
                if "api_ok" in ex_payload:
                    broker_ok = bool(ex_payload.get("api_ok"))
                else:
                    executed_broker_unknown_total += 1
                    broker_ok = None
            if broker_ok is True:
                executed_broker_success_total += 1
            elif broker_ok is False:
                executed_broker_fail_total += 1

    llm_error_rate = _safe_pct(float(llm_error_total), float(llm_total))
    llm_latency_avg_ms = (sum(llm_latency_ms) / float(len(llm_latency_ms))) if llm_latency_ms else 0.0

    out: Dict[str, Any] = {
        "schema_version": "live_summary.v1",
        "ok": True,
        "generated_at_utc": _utc_iso(now_epoch),
        "lookback_min": int(lookback_min),
        "window_start_utc": _utc_iso(start_epoch),
        "window_end_utc": _utc_iso(now_epoch),
        "event_log_path": str(event_log_path),
        "events": {
            "scanned_total": int(scanned_total),
            "window_total": int(len(window_rows)),
            "missing_ts_total": int(missing_ts_total),
        },
        "strategist_llm": {
            "total": int(llm_total),
            "ok_total": int(llm_ok_total),
            "error_total": int(llm_error_total),
            "error_rate": float(llm_error_rate),
            "latency_avg_ms": float(llm_latency_avg_ms),
            "action_counts": dict(llm_action_counts),
            "reason_counts": dict(llm_reason_counts),
            "error_type_counts": dict(llm_error_type_counts),
        },
        "decision": {
            "action_counts": dict(decision_action_counts),
            "strategy_counts": dict(decision_strategy_counts),
            "reason_top": dict(decision_reason_counts.most_common(10)),
        },
        "execution": {
            "verdict_total": int(verdict_total),
            "allowed_total": int(verdict_allowed_total),
            "blocked_total": int(verdict_blocked_total),
            "blocked_reason_top": dict(verdict_block_reason_counts.most_common(10)),
            "executed_total": int(executed_total),
            "executed_broker_success_total": int(executed_broker_success_total),
            "executed_broker_fail_total": int(executed_broker_fail_total),
            "executed_broker_unknown_total": int(executed_broker_unknown_total),
            "executed_broker_code_top": dict(executed_broker_code_counts.most_common(10)),
            "executed_action_counts": dict(executed_action_counts),
            "executed_notional_total": float(executed_notional_total),
        },
        "controls": {
            "cooldown_noop_total": int(cooldown_noop_total),
            "exit_policy_sell_total": int(exit_policy_sell_total),
            "insufficient_mock_cash_block_total": int(insufficient_mock_cash_block_total),
        },
    }

    stamp = datetime.fromtimestamp(now_epoch, tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = report_dir / f"live_summary_{stamp}.json"
    md_path = report_dir / f"live_summary_{stamp}.md"
    out["report_json_path"] = str(json_path)
    out["report_md_path"] = str(md_path)

    json_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} window_total={out['events']['window_total']} "
            f"buy={out['decision']['action_counts'].get('BUY', 0)} "
            f"sell={out['decision']['action_counts'].get('SELL', 0)} "
            f"noop={out['decision']['action_counts'].get('NOOP', 0)} "
            f"llm_error_rate={out['strategist_llm']['error_rate']:.4f} "
            f"cooldown_noop_total={out['controls']['cooldown_noop_total']} "
            f"exit_policy_sell_total={out['controls']['exit_policy_sell_total']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
