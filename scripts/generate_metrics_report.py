from __future__ import annotations

import json
import os
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _iter_events(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                if isinstance(obj, dict):
                    yield obj

    return gen()


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


def _extract_intent_action(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return ""

    packet = payload.get("decision_packet")
    if isinstance(packet, dict):
        intent = packet.get("intent")
        if isinstance(intent, dict):
            action = intent.get("action") or intent.get("intent")
            return str(action or "").upper()

    action = payload.get("action") or payload.get("intent")
    return str(action or "").upper()


def _extract_guard_reason(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return "unknown"

    reason = payload.get("reason")
    if reason:
        return str(reason)

    details = payload.get("details")
    if isinstance(details, dict) and details.get("reason"):
        return str(details["reason"])

    return "unknown"


def _extract_api_id(row: Dict[str, Any]) -> str:
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return "unknown"

    for key in ("api_id", "order_api_id"):
        v = payload.get(key)
        if v:
            return str(v)

    order = payload.get("order")
    if isinstance(order, dict):
        for key in ("api_id", "order_api_id"):
            v = order.get(key)
            if v:
                return str(v)

    packet = payload.get("decision_packet")
    if isinstance(packet, dict):
        intent = packet.get("intent")
        if isinstance(intent, dict):
            for key in ("order_api_id", "api_id"):
                v = intent.get(key)
                if v:
                    return str(v)

    skill = payload.get("skill")
    if skill:
        return f"skill:{skill}"

    return "unknown"


def _numeric_summary(values: List[float]) -> Dict[str, float]:
    vals = sorted(float(v) for v in values if float(v) >= 0.0)
    if not vals:
        return {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}

    n = len(vals)

    def pct(p: float) -> float:
        if n == 1:
            return float(vals[0])
        idx = int(round((n - 1) * p))
        idx = max(0, min(n - 1, idx))
        return float(vals[idx])

    return {
        "count": float(n),
        "avg": float(sum(vals) / n),
        "p50": pct(0.50),
        "p95": pct(0.95),
        "max": float(vals[-1]),
    }


def _latency_summary(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    start_by_run: Dict[str, int] = {}
    latencies: List[float] = []

    sorted_rows = sorted(rows, key=lambda r: int(r.get("_epoch") or 0))
    for r in sorted_rows:
        run_id = str(r.get("run_id") or "")
        if not run_id:
            continue

        stage = str(r.get("stage") or "")
        event = str(r.get("event") or "")
        epoch = r.get("_epoch")
        if epoch is None:
            continue

        if stage != "execute_from_packet":
            continue

        if event == "start":
            start_by_run[run_id] = int(epoch)
            continue

        if event in ("end", "error"):
            start = start_by_run.pop(run_id, None)
            if start is None:
                continue
            dt = float(int(epoch) - int(start))
            if dt >= 0:
                latencies.append(dt)

    return _numeric_summary(latencies)


def generate_metrics_report(events_path: Path, out_dir: Path, day: str | None = None) -> Tuple[Path, Path]:
    """Generate daily metrics summary (MD + JSON) from events.jsonl."""
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    for raw in _iter_events(events_path):
        ts = raw.get("ts") or (raw.get("payload") or {}).get("ts")
        epoch = _to_epoch(ts)
        rows.append({**raw, "_epoch": epoch, "_day": _utc_day(ts)})

    if not rows:
        day = day or date.today().isoformat()
        md_path = out_dir / f"metrics_{day}.md"
        js_path = out_dir / f"metrics_{day}.json"
        empty = {
            "day": day,
            "events": 0,
            "runs": 0,
            "intents_created_total": 0,
            "intents_approved_total": 0,
            "intents_blocked_total": 0,
            "intents_blocked_by_reason": {},
            "execution_latency_seconds": {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
            "strategist_llm": {
                "total": 0,
                "ok_total": 0,
                "fail_total": 0,
                "success_rate": 0.0,
                "latency_ms": {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
                "attempts": {"count": 0.0, "avg": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0},
                "error_type_total": {},
            },
            "api_error_total_by_api_id": {},
        }
        md_path.write_text(f"# Metrics Report ({day})\n\nNo events found.\n", encoding="utf-8")
        js_path.write_text(json.dumps(empty, ensure_ascii=False, indent=2), encoding="utf-8")
        return md_path, js_path

    day = day or sorted({str(r.get("_day")) for r in rows})[-1]
    day_rows = [r for r in rows if str(r.get("_day")) == day]

    run_ids = {str(r.get("run_id") or "") for r in day_rows if r.get("run_id")}

    intents_created = 0
    intents_approved = 0
    intents_blocked = 0
    blocks_by_reason: Counter[str] = Counter()
    api_errors_by_id: Counter[str] = Counter()
    llm_total = 0
    llm_ok_total = 0
    llm_fail_total = 0
    llm_error_by_type: Counter[str] = Counter()
    llm_latency_ms_values: List[float] = []
    llm_attempt_values: List[float] = []

    for r in day_rows:
        stage = str(r.get("stage") or "")
        event = str(r.get("event") or "")

        if stage == "decision" and event == "trace":
            action = _extract_intent_action(r)
            if action in {"BUY", "SELL"}:
                intents_created += 1

        if stage == "execute_from_packet" and event == "verdict":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            allowed = payload.get("allowed")
            if allowed is True:
                intents_approved += 1
            elif allowed is False:
                intents_blocked += 1
                blocks_by_reason[_extract_guard_reason(r)] += 1

        if event == "error":
            api_errors_by_id[_extract_api_id(r)] += 1

        if stage == "strategist_llm" and event == "result":
            payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
            llm_total += 1
            ok = payload.get("ok") is True
            if ok:
                llm_ok_total += 1
            else:
                llm_fail_total += 1
                llm_error_by_type[str(payload.get("error_type") or "unknown")] += 1

            latency_ms = payload.get("latency_ms")
            try:
                latency_val = float(latency_ms)
                if latency_val >= 0:
                    llm_latency_ms_values.append(latency_val)
            except Exception:
                pass

            attempts = payload.get("attempts")
            try:
                attempts_val = float(attempts)
                if attempts_val >= 0:
                    llm_attempt_values.append(attempts_val)
            except Exception:
                pass

    latency = _latency_summary(day_rows)
    llm_latency_ms = _numeric_summary(llm_latency_ms_values)
    llm_attempts = _numeric_summary(llm_attempt_values)
    llm_success_rate = (float(llm_ok_total) / float(llm_total)) if llm_total > 0 else 0.0

    summary = {
        "day": day,
        "events": len(day_rows),
        "runs": len(run_ids),
        "intents_created_total": intents_created,
        "intents_approved_total": intents_approved,
        "intents_blocked_total": intents_blocked,
        "intents_blocked_by_reason": dict(blocks_by_reason),
        "execution_latency_seconds": latency,
        "strategist_llm": {
            "total": llm_total,
            "ok_total": llm_ok_total,
            "fail_total": llm_fail_total,
            "success_rate": llm_success_rate,
            "latency_ms": llm_latency_ms,
            "attempts": llm_attempts,
            "error_type_total": dict(llm_error_by_type),
        },
        "api_error_total_by_api_id": dict(api_errors_by_id),
    }

    md_lines = [
        f"# Metrics Report ({day})",
        "",
        f"- events: **{summary['events']}**",
        f"- runs: **{summary['runs']}**",
        f"- intents_created_total: **{intents_created}**",
        f"- intents_approved_total: **{intents_approved}**",
        f"- intents_blocked_total: **{intents_blocked}**",
        "",
        "## Strategist LLM",
        "",
        f"- total: **{llm_total}**",
        f"- ok_total: **{llm_ok_total}**",
        f"- fail_total: **{llm_fail_total}**",
        f"- success_rate: **{llm_success_rate:.2%}**",
        "",
        "### Latency (ms)",
        "",
        f"- count: {int(llm_latency_ms['count'])}",
        f"- avg: {llm_latency_ms['avg']:.3f}ms",
        f"- p50: {llm_latency_ms['p50']:.3f}ms",
        f"- p95: {llm_latency_ms['p95']:.3f}ms",
        f"- max: {llm_latency_ms['max']:.3f}ms",
        "",
        "### Attempts",
        "",
        f"- count: {int(llm_attempts['count'])}",
        f"- avg: {llm_attempts['avg']:.3f}",
        f"- p50: {llm_attempts['p50']:.3f}",
        f"- p95: {llm_attempts['p95']:.3f}",
        f"- max: {llm_attempts['max']:.3f}",
        "",
        "### Errors By Type",
        "",
    ]

    if llm_error_by_type:
        for et, cnt in llm_error_by_type.most_common():
            md_lines.append(f"- {et}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += [
        "",
        "## Latency (execute_from_packet)",
        "",
        f"- count: {int(latency['count'])}",
        f"- avg: {latency['avg']:.3f}s",
        f"- p50: {latency['p50']:.3f}s",
        f"- p95: {latency['p95']:.3f}s",
        f"- max: {latency['max']:.3f}s",
        "",
        "## Blocked By Reason",
        "",
    ]

    if blocks_by_reason:
        for reason, cnt in blocks_by_reason.most_common():
            md_lines.append(f"- {reason}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_lines += ["", "## API Errors By API ID", ""]
    if api_errors_by_id:
        for api_id, cnt in api_errors_by_id.most_common():
            md_lines.append(f"- {api_id}: {cnt}")
    else:
        md_lines.append("- (none)")

    md_path = out_dir / f"metrics_{day}.md"
    js_path = out_dir / f"metrics_{day}.json"
    md_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    js_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return md_path, js_path


def main() -> None:
    events_path = Path(os.getenv("EVENT_LOG_PATH", "./data/events.jsonl"))
    out_dir = Path(os.getenv("REPORT_DIR", "./reports")) / "metrics"
    day = os.getenv("METRICS_DAY")
    md, js = generate_metrics_report(events_path, out_dir, day=day)
    print(f"Wrote: {md}")
    print(f"Wrote: {js}")


if __name__ == "__main__":
    main()
