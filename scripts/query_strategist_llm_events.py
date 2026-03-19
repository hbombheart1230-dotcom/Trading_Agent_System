from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _infer_call_kind(payload: Dict[str, Any]) -> str:
    explicit = str(payload.get("call_kind") or "").strip()
    if explicit:
        return explicit
    schema_version = str(payload.get("schema_version") or "").strip().lower()
    prompt_version = str(payload.get("prompt_version") or "").strip().lower()
    intent_action = str(payload.get("intent_action") or "").strip().upper()
    error_type = str(payload.get("error_type") or "").strip()
    if schema_version == "strategist_output.v1" or prompt_version.startswith("m31-strategic-frame"):
        return "strategic_frame"
    if schema_version == "intent.v1" or intent_action in {"BUY", "SELL", "NOOP"}:
        return "legacy_trade_intent"
    if error_type == "StrategistBlocked":
        return "blocked_legacy_runtime"
    return "unknown"


def _load_jsonl(path: Path) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not path.exists():
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                rec = json.loads(s)
            except Exception:
                continue
            if isinstance(rec, dict):
                out.append(rec)
    return out


def _filtered_events(
    rows: List[Dict[str, Any]],
    *,
    run_id: str = "",
    day: str = "",
    only_failures: bool = False,
    only_nonzero_news: bool = False,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in rows:
        if rec.get("stage") != "strategist_llm" or rec.get("event") != "result":
            continue
        if day and not str(rec.get("ts_kst") or rec.get("ts") or "").startswith(day):
            continue
        if run_id and str(rec.get("run_id") or "") != run_id:
            continue
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        if only_failures and bool(p.get("ok")):
            continue
        if only_nonzero_news and abs(_to_float(p.get("context_symbol_sentiment_score"), 0.0)) <= 1e-12:
            continue
        out.append(rec)
    return out


def _print_human(path: Path, rows: List[Dict[str, Any]]) -> None:
    print("=== Strategist LLM Events ===")
    print(f"path={path}")
    print(f"shown={len(rows)}")
    for rec in rows:
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        ts = str(rec.get("ts") or "")
        run_id = str(rec.get("run_id") or "")
        call_kind = _infer_call_kind(p)
        ok = p.get("ok")
        action = str(p.get("intent_action") or "")
        reason = str(p.get("intent_reason") or "")
        latency = p.get("latency_ms")
        attempts = p.get("attempts")
        prompt_version = str(p.get("prompt_version") or "")
        schema_version = str(p.get("schema_version") or "")
        prompt_tokens = p.get("prompt_tokens")
        completion_tokens = p.get("completion_tokens")
        total_tokens = p.get("total_tokens")
        estimated_cost_usd = p.get("estimated_cost_usd")
        regime = str(p.get("context_regime") or "")
        signal_score = p.get("context_signal_score")
        sym_sent = p.get("context_symbol_sentiment_score")
        global_sent = p.get("context_global_sentiment_score")
        sym_sent_status = str(p.get("context_symbol_sentiment_status") or "")
        global_sent_status = str(p.get("context_global_sentiment_status") or "")
        composite = p.get("context_composite_score")
        err = str(p.get("error_type") or "")
        print(
            f"{ts} run_id={run_id} call_kind={call_kind} ok={ok} action={action} reason={reason} "
            f"latency_ms={latency} attempts={attempts} "
            f"prompt_version={prompt_version} schema_version={schema_version} "
            f"prompt_tokens={prompt_tokens} completion_tokens={completion_tokens} "
            f"total_tokens={total_tokens} estimated_cost_usd={estimated_cost_usd} "
            f"context_regime={regime} context_signal_score={signal_score} "
            f"context_symbol_sentiment_score={sym_sent} context_global_sentiment_score={global_sent} "
            f"context_symbol_sentiment_status={sym_sent_status} "
            f"context_global_sentiment_status={global_sent_status} "
            f"context_composite_score={composite} "
            f"error_type={err}"
        )


def _print_summary(rows: List[Dict[str, Any]]) -> None:
    by_kind: Dict[str, Dict[str, int]] = {}
    by_reason: Dict[str, int] = {}
    by_action: Dict[str, int] = {}
    for rec in rows:
        p = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
        call_kind = _infer_call_kind(p)
        ok = "ok" if bool(p.get("ok")) else "non_ok"
        by_kind.setdefault(call_kind, {})
        by_kind[call_kind][ok] = int(by_kind[call_kind].get(ok) or 0) + 1
        reason = str(p.get("intent_reason") or p.get("status") or "none")
        by_reason[reason] = int(by_reason.get(reason) or 0) + 1
        action = str(p.get("intent_action") or "none")
        by_action[action] = int(by_action.get(action) or 0) + 1

    print("summary.call_kind=", json.dumps(by_kind, ensure_ascii=False, sort_keys=True))
    print("summary.intent_action=", json.dumps(by_action, ensure_ascii=False, sort_keys=True))
    print(
        "summary.intent_reason_top=",
        json.dumps(sorted(by_reason.items(), key=lambda kv: kv[1], reverse=True)[:10], ensure_ascii=False),
    )


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Query strategist_llm result events from EVENT_LOG_PATH JSONL.")
    p.add_argument("--path", default=os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl"))
    p.add_argument("--run-id", default="", help="Filter by exact run_id.")
    p.add_argument("--day", default="", help="Filter by day prefix in ts/ts_kst, e.g. 2026-03-19.")
    p.add_argument("--limit", type=int, default=20, help="Show last N matched rows.")
    p.add_argument("--only-failures", action="store_true", help="Only include rows where payload.ok is false.")
    p.add_argument(
        "--only-nonzero-news",
        action="store_true",
        help="Only include rows where payload.context_symbol_sentiment_score is non-zero.",
    )
    p.add_argument("--summary", action="store_true", help="Print compact summary counters before rows.")
    p.add_argument("--json", action="store_true", help="Print JSON array instead of human-readable lines.")
    args = p.parse_args(argv)

    path = Path(str(args.path).strip())
    if not path.exists():
        print(f"ERROR: event log path does not exist: {path}", file=sys.stderr)
        return 2

    rows = _load_jsonl(path)
    matched = _filtered_events(
        rows,
        run_id=str(args.run_id or "").strip(),
        day=str(args.day or "").strip(),
        only_failures=bool(args.only_failures),
        only_nonzero_news=bool(args.only_nonzero_news),
    )
    limit = max(1, int(args.limit))
    shown = matched[-limit:]

    if args.json:
        print(json.dumps(shown, ensure_ascii=False))
    else:
        if args.summary:
            _print_summary(matched)
        _print_human(path, shown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
