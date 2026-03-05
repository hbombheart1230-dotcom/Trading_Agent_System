from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                try:
                    obj = json.loads(s)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj

    return _gen()


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


def _utc_day(ts: Any) -> str:
    epoch = _to_epoch(ts)
    if epoch is None:
        return date.today().isoformat()
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


def _to_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _numeric_summary(values: List[float]) -> Dict[str, float]:
    vals = sorted(float(v) for v in values if float(v) >= 0.0)
    if not vals:
        return {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}

    n = len(vals)

    def _pct(p: float) -> float:
        if n == 1:
            return float(vals[0])
        idx = int(round((n - 1) * p))
        idx = max(0, min(n - 1, idx))
        return float(vals[idx])

    return {
        "count": float(n),
        "avg": float(sum(vals) / float(n)),
        "p50": _pct(0.50),
        "p95": _pct(0.95),
        "max": float(vals[-1]),
    }


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


def _extract_noop_reason(payload: Dict[str, Any]) -> str:
    packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
    intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
    reason = str(intent.get("reason") or "").strip()
    if reason:
        return reason
    trace = payload.get("trace") if isinstance(payload.get("trace"), dict) else {}
    raw_intent = trace.get("raw_intent") if isinstance(trace.get("raw_intent"), dict) else {}
    reason = str(raw_intent.get("reason") or "").strip()
    return reason or "unknown"


def _build_summary(rows: List[Dict[str, Any]], *, day: str) -> Dict[str, Any]:
    run_ids = {str(r.get("run_id") or "") for r in rows if str(r.get("run_id") or "").strip()}

    verdict_reason_total: Counter[str] = Counter()
    broker_code_total: Counter[str] = Counter()
    broker_failure_total: Counter[str] = Counter()
    noop_reason_total: Counter[str] = Counter()
    llm_latency_ms: List[float] = []
    llm_total = 0
    llm_ok_total = 0
    llm_error_total = 0
    execution_total = 0
    verdict_block_total = 0
    broker_success_total = 0
    broker_fail_total = 0
    broker_unknown_total = 0

    for r in rows:
        stage = str(r.get("stage") or "")
        event = str(r.get("event") or "")
        payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}

        if stage == "execute_from_packet" and event == "verdict":
            if payload.get("allowed") is False:
                verdict_block_total += 1
                reason = str(payload.get("reason") or "").strip() or "unknown"
                verdict_reason_total[reason] += 1

        if stage == "execute_from_packet" and event == "execution":
            execution_total += 1
            ex_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            bcode = str(ex_payload.get("broker_code") or "").strip()
            if bcode:
                broker_code_total[bcode] += 1
            b_ok = _broker_code_success(ex_payload.get("broker_code"))
            if b_ok is None:
                if "api_ok" in ex_payload:
                    b_ok = bool(ex_payload.get("api_ok"))
                else:
                    broker_unknown_total += 1
            if b_ok is True:
                broker_success_total += 1
            elif b_ok is False:
                broker_fail_total += 1
                k = bcode or "unknown"
                broker_failure_total[k] += 1

        if stage == "decision" and event == "trace":
            packet = payload.get("decision_packet") if isinstance(payload.get("decision_packet"), dict) else {}
            intent = packet.get("intent") if isinstance(packet.get("intent"), dict) else {}
            action = str(intent.get("action") or "").strip().upper()
            if action == "NOOP":
                noop_reason_total[_extract_noop_reason(payload)] += 1

        if stage == "strategist_llm" and event == "result":
            llm_total += 1
            if payload.get("ok") is True:
                llm_ok_total += 1
            else:
                llm_error_total += 1
            lat = _to_float(payload.get("latency_ms"))
            if lat is not None and lat >= 0.0:
                llm_latency_ms.append(float(lat))

    noop_total = int(sum(noop_reason_total.values()))
    noop_reason_ratio = {
        str(k): (float(v) / float(noop_total) if noop_total > 0 else 0.0)
        for k, v in noop_reason_total.items()
    }
    focus_noop_reasons = ("model_no_signal", "missing_rationale", "post_exit_cooldown")
    focus_ratio = {k: float(noop_reason_ratio.get(k, 0.0)) for k in focus_noop_reasons}

    out = {
        "schema_version": "ops_diagnostic.v1",
        "day": day,
        "events": int(len(rows)),
        "runs": int(len(run_ids)),
        "execution": {
            "execution_total": int(execution_total),
            "verdict_block_total": int(verdict_block_total),
            "verdict_reason_topN": [
                {"reason": str(reason), "count": int(cnt)}
                for reason, cnt in verdict_reason_total.most_common(10)
            ],
            "broker_success_total": int(broker_success_total),
            "broker_fail_total": int(broker_fail_total),
            "broker_unknown_total": int(broker_unknown_total),
            "broker_success_rate": (
                float(broker_success_total) / float(execution_total) if execution_total > 0 else 0.0
            ),
            "broker_code_topN": [
                {"broker_code": str(code), "count": int(cnt)}
                for code, cnt in broker_code_total.most_common(10)
            ],
            "broker_failure_topN": [
                {"broker_code": str(code), "count": int(cnt)}
                for code, cnt in broker_failure_total.most_common(10)
            ],
        },
        "noop": {
            "total": int(noop_total),
            "reason_total": {str(k): int(v) for k, v in noop_reason_total.items()},
            "reason_ratio": {str(k): float(v) for k, v in noop_reason_ratio.items()},
            "focus_reason_ratio": focus_ratio,
        },
        "strategist_llm": {
            "total": int(llm_total),
            "ok_total": int(llm_ok_total),
            "error_total": int(llm_error_total),
            "latency_ms": _numeric_summary(llm_latency_ms),
        },
    }
    return out


def _build_markdown(summary: Dict[str, Any]) -> str:
    exe = summary.get("execution") if isinstance(summary.get("execution"), dict) else {}
    noop = summary.get("noop") if isinstance(summary.get("noop"), dict) else {}
    llm = summary.get("strategist_llm") if isinstance(summary.get("strategist_llm"), dict) else {}

    lines: List[str] = [
        f"# Ops Diagnostic Report ({summary.get('day')})",
        "",
        f"- schema_version: **{summary.get('schema_version')}**",
        f"- events: **{int(summary.get('events') or 0)}**",
        f"- runs: **{int(summary.get('runs') or 0)}**",
        "",
        "## Execution",
        "",
        f"- execution_total: **{int(exe.get('execution_total') or 0)}**",
        f"- verdict_block_total: **{int(exe.get('verdict_block_total') or 0)}**",
        f"- broker_success_total: **{int(exe.get('broker_success_total') or 0)}**",
        f"- broker_fail_total: **{int(exe.get('broker_fail_total') or 0)}**",
        f"- broker_unknown_total: **{int(exe.get('broker_unknown_total') or 0)}**",
        f"- broker_success_rate: **{float(exe.get('broker_success_rate') or 0.0):.2%}**",
        "",
        "### verdict_reason_topN",
        "",
    ]

    top_verdict = exe.get("verdict_reason_topN") if isinstance(exe.get("verdict_reason_topN"), list) else []
    if top_verdict:
        for row in top_verdict:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {row.get('reason')}: {int(row.get('count') or 0)}")
    else:
        lines.append("- (none)")

    lines += ["", "### broker_failure_topN", ""]
    top_fail = exe.get("broker_failure_topN") if isinstance(exe.get("broker_failure_topN"), list) else []
    if top_fail:
        for row in top_fail:
            if not isinstance(row, dict):
                continue
            lines.append(f"- {row.get('broker_code')}: {int(row.get('count') or 0)}")
    else:
        lines.append("- (none)")

    lines += ["", "## NOOP", "", f"- total: **{int(noop.get('total') or 0)}**", "", "### focus_reason_ratio", ""]
    focus = noop.get("focus_reason_ratio") if isinstance(noop.get("focus_reason_ratio"), dict) else {}
    for key in ("model_no_signal", "missing_rationale", "post_exit_cooldown"):
        lines.append(f"- {key}: {float(focus.get(key) or 0.0):.2%}")

    latency = llm.get("latency_ms") if isinstance(llm.get("latency_ms"), dict) else {}
    lines += [
        "",
        "## Strategist LLM",
        "",
        f"- total: **{int(llm.get('total') or 0)}**",
        f"- ok_total: **{int(llm.get('ok_total') or 0)}**",
        f"- error_total: **{int(llm.get('error_total') or 0)}**",
        f"- latency_ms_p50: **{float(latency.get('p50') or 0.0):.1f}**",
        f"- latency_ms_p95: **{float(latency.get('p95') or 0.0):.1f}**",
        "",
    ]
    return "\n".join(lines)


def generate_ops_diagnostic_report(events_path: Path, out_dir: Path, day: str | None = None) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for e in _iter_events(events_path):
        ts = e.get("ts") or (e.get("payload") or {}).get("ts")
        rows.append({**e, "_day": _utc_day(ts)})

    if not rows:
        day = day or date.today().isoformat()
        summary = {
            "schema_version": "ops_diagnostic.v1",
            "day": day,
            "events": 0,
            "runs": 0,
            "execution": {
                "execution_total": 0,
                "verdict_block_total": 0,
                "verdict_reason_topN": [],
                "broker_success_total": 0,
                "broker_fail_total": 0,
                "broker_unknown_total": 0,
                "broker_success_rate": 0.0,
                "broker_code_topN": [],
                "broker_failure_topN": [],
            },
            "noop": {"total": 0, "reason_total": {}, "reason_ratio": {}, "focus_reason_ratio": {}},
            "strategist_llm": {"total": 0, "ok_total": 0, "error_total": 0, "latency_ms": _numeric_summary([])},
        }
    else:
        if day is None:
            day = sorted({str(r.get("_day") or "") for r in rows})[-1]
        day_rows = [r for r in rows if str(r.get("_day") or "") == day]
        summary = _build_summary(day_rows, day=str(day))

    md_path = out_dir / f"ops_diagnostic_{day}.md"
    json_path = out_dir / f"ops_diagnostic_{day}.json"
    md_path.write_text(_build_markdown(summary) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, json_path


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Generate daily ops diagnostic report (broker failures / NOOP reasons / LLM latency)."
    )
    p.add_argument("--event-log-path", default=os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    p.add_argument("--report-dir", default="./reports/ops_diagnostic")
    p.add_argument("--day", default="", help="UTC day in YYYY-MM-DD. Default: latest day in log.")
    p.add_argument("--json", action="store_true", help="Print summary JSON to stdout.")
    args = p.parse_args(argv)

    events_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "").strip() or None
    md_path, json_path = generate_ops_diagnostic_report(events_path, report_dir, day=day)

    if args.json:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        print(json.dumps(data, ensure_ascii=False))
    else:
        print(f"Wrote: {md_path}")
        print(f"Wrote: {json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

