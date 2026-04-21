from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable


def iter_jsonl(path: Path) -> Iterable[Dict[str, Any]]:
    if not path.exists():
        return []

    def _gen() -> Iterable[Dict[str, Any]]:
        with path.open("r", encoding="utf-8") as file:
            for raw in file:
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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def safe_pct(num: float, den: float) -> float:
    if den <= 0.0:
        return 0.0
    return float(num) / float(den)


def broker_code_success(value: Any) -> bool | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(float(text)) == 0
    except Exception:
        pass
    lowered = text.lower()
    if lowered in ("ok", "success", "accepted"):
        return True
    if lowered in ("error", "failed", "rejected"):
        return False
    return False


def build_markdown(out: Dict[str, Any]) -> str:
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
