from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.pipelines.m13_tick import run_m13_tick
from libs.runtime.market_hours import KST
from libs.runtime.market_hours import MarketHours
from libs.runtime.market_hours import now_kst


def _read_env_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip()
        if v and v[0] not in ("'", "\"") and "#" in v:
            v = v.split("#", 1)[0].rstrip()
        if (len(v) >= 2) and ((v[0] == v[-1]) and v[0] in ("'", '"')):
            v = v[1:-1]
        if k:
            out[k] = v
    return out


def _env_bool(env: Dict[str, str], key: str, default: bool = False) -> bool:
    raw = str(env.get(key, "")).strip().lower()
    if not raw:
        return bool(default)
    return raw in ("1", "true", "yes", "y", "on")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


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


def _utc_day(ts: Any) -> Optional[str]:
    e = _to_epoch(ts)
    if e is None:
        return None
    return datetime.fromtimestamp(e, tz=timezone.utc).strftime("%Y-%m-%d")


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


def _item(
    *,
    item_id: str,
    title: str,
    passed: bool,
    evidence: str,
    required: bool = True,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "title": title,
        "required": bool(required),
        "passed": bool(passed),
        "evidence": str(evidence),
    }


def _build_markdown(out: Dict[str, Any]) -> str:
    mode = out.get("runtime_mode") if isinstance(out.get("runtime_mode"), dict) else {}
    guards = out.get("guardrails") if isinstance(out.get("guardrails"), dict) else {}
    market = out.get("market") if isinstance(out.get("market"), dict) else {}
    events = out.get("events") if isinstance(out.get("events"), dict) else {}
    checklist = out.get("checklist") if isinstance(out.get("checklist"), list) else []

    lines = [
        f"# M31-2 Mock Investor Exam Check ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- required_pass_total: **{int(out.get('required_pass_total') or 0)}**",
        f"- required_fail_total: **{int(out.get('required_fail_total') or 0)}**",
        "",
        "## Runtime Mode",
        "",
        f"- RUNTIME_PROFILE: **{mode.get('RUNTIME_PROFILE')}**",
        f"- KIWOOM_MODE: **{mode.get('KIWOOM_MODE')}**",
        f"- APPROVAL_MODE: **{mode.get('APPROVAL_MODE')}**",
        f"- EXECUTION_ENABLED: **{bool(mode.get('EXECUTION_ENABLED'))}**",
        f"- ALLOW_REAL_EXECUTION: **{bool(mode.get('ALLOW_REAL_EXECUTION'))}**",
        "",
        "## Guardrails",
        "",
        f"- SYMBOL_ALLOWLIST size: **{int(guards.get('allowlist_size') or 0)}**",
        f"- max_notional_key: **{guards.get('max_notional_key')}**",
        f"- max_notional: **{float(guards.get('max_notional') or 0.0):.2f}**",
        f"- daily_loss_limit: **{float(guards.get('daily_loss_limit') or 0.0):.6f}**",
        "",
        "## Market Contract",
        "",
        f"- now_kst: **{market.get('now_kst')}**",
        f"- market_open_now: **{bool(market.get('market_open_now'))}**",
        f"- open_contract_ok: **{bool(market.get('open_contract_ok'))}**",
        f"- closed_contract_ok: **{bool(market.get('closed_contract_ok'))}**",
        "",
        "## Session Evidence",
        "",
        f"- event_total: **{int(events.get('event_total') or 0)}**",
        f"- verdict_total: **{int(events.get('verdict_total') or 0)}**",
        f"- execution_total: **{int(events.get('execution_total') or 0)}**",
        f"- error_total: **{int(events.get('error_total') or 0)}**",
        "",
        "## Checklist",
        "",
    ]
    for item in checklist:
        mark = "x" if bool(item.get("passed")) else " "
        lines.append(f"- [{mark}] {item.get('title')} | evidence={item.get('evidence')}")

    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    lines += ["", "## Failures", ""]
    if failures:
        for msg in failures:
            lines.append(f"- {msg}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M31-2 mock investor exam protocol gate check.")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--report-dir", default="reports/m31_mock_exam")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--strict-session", action="store_true")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    env_path = Path(str(args.env_path).strip())
    event_log_path = Path(str(args.event_log_path).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    strict_session = bool(args.strict_session)
    inject_fail = bool(args.inject_fail)

    report_dir.mkdir(parents=True, exist_ok=True)

    env = _read_env_file(env_path)
    runtime_profile = str(env.get("RUNTIME_PROFILE", "")).strip().lower()
    kiwoom_mode = str(env.get("KIWOOM_MODE", "")).strip().lower()
    approval_mode = str(env.get("APPROVAL_MODE", "")).strip().lower()
    execution_enabled = _env_bool(env, "EXECUTION_ENABLED", default=False)
    allow_real_execution = _env_bool(env, "ALLOW_REAL_EXECUTION", default=False)

    allowlist_raw = str(env.get("SYMBOL_ALLOWLIST", "")).strip()
    allowlist = [x.strip() for x in allowlist_raw.split(",") if x.strip()]

    max_notional_key = "MAX_ORDER_NOTIONAL"
    max_notional = _to_float(env.get("MAX_ORDER_NOTIONAL"), default=0.0)
    if max_notional <= 0.0:
        alt = _to_float(env.get("MAX_NOTIONAL"), default=0.0)
        if alt > 0.0:
            max_notional_key = "MAX_NOTIONAL"
            max_notional = alt

    daily_loss_limit = _to_float(env.get("RISK_DAILY_LOSS_LIMIT"), default=0.0)

    mh = MarketHours()
    now = now_kst()
    market_open_now = bool(mh.is_open(now))

    open_dt = datetime(2026, 2, 16, 9, 0, tzinfo=KST)  # Monday
    closed_dt = datetime(2026, 2, 16, 8, 59, tzinfo=KST)
    weekend_dt = datetime(2026, 2, 14, 10, 0, tzinfo=KST)  # Saturday

    open_contract_ok = bool(mh.is_open(open_dt))
    closed_contract_ok = (not bool(mh.is_open(closed_dt))) and (not bool(mh.is_open(weekend_dt)))

    def _run_marker(state: Dict[str, Any]) -> Dict[str, Any]:
        state["run_m10_called"] = True
        return state

    closed_state = run_m13_tick({}, dt=closed_dt, market_hours=mh, run_m10=_run_marker)
    open_state = run_m13_tick({}, dt=open_dt, market_hours=mh, run_m10=_run_marker)
    tick_contract_ok = bool(closed_state.get("tick_skipped")) and (not bool(open_state.get("tick_skipped"))) and bool(
        open_state.get("run_m10_called")
    )

    event_total = 0
    verdict_total = 0
    execution_total = 0
    error_total = 0
    for row in _iter_jsonl(event_log_path):
        if _utc_day(row.get("ts")) != day:
            continue
        event_total += 1
        stage = str(row.get("stage") or "").strip()
        event = str(row.get("event") or "").strip()
        if stage == "execute_from_packet" and event == "verdict":
            verdict_total += 1
        if stage == "execute_from_packet" and event == "execution":
            execution_total += 1
        if event == "error":
            error_total += 1

    checklist: List[Dict[str, Any]] = [
        _item(
            item_id="runtime_mode_policy_fixed",
            title="Runtime mode policy matches mock investor phase-A contract",
            passed=(
                runtime_profile == "staging"
                and kiwoom_mode == "mock"
                and approval_mode == "manual"
                and execution_enabled is True
                and allow_real_execution is False
            ),
            evidence=(
                f"RUNTIME_PROFILE={runtime_profile or '(empty)'}, KIWOOM_MODE={kiwoom_mode or '(empty)'}, "
                f"APPROVAL_MODE={approval_mode or '(empty)'}, EXECUTION_ENABLED={execution_enabled}, "
                f"ALLOW_REAL_EXECUTION={allow_real_execution}"
            ),
        ),
        _item(
            item_id="guardrails_fixed",
            title="Allowlist, max notional, and daily loss cap are configured",
            passed=(len(allowlist) > 0 and max_notional > 0.0 and daily_loss_limit > 0.0),
            evidence=(
                f"allowlist_size={len(allowlist)}, {max_notional_key}={max_notional}, "
                f"RISK_DAILY_LOSS_LIMIT={daily_loss_limit}"
            ),
        ),
        _item(
            item_id="market_hours_contract",
            title="Market-hours contract is deterministic (open/closed/weekend)",
            passed=(open_contract_ok and closed_contract_ok),
            evidence=(
                f"open_contract_ok={open_contract_ok}, closed_contract_ok={closed_contract_ok}, "
                f"session=09:00-15:30 KST weekday"
            ),
        ),
        _item(
            item_id="tick_pipeline_contract",
            title="Tick pipeline skips closed market and runs on open market",
            passed=tick_contract_ok,
            evidence=(
                f"closed_tick_skipped={bool(closed_state.get('tick_skipped'))}, "
                f"open_tick_skipped={bool(open_state.get('tick_skipped'))}, "
                f"open_run_called={bool(open_state.get('run_m10_called'))}"
            ),
        ),
        _item(
            item_id="session_window_check",
            title="Current time is within market session for live mock exam quality",
            passed=market_open_now,
            evidence=f"now_kst={now.isoformat()}, market_open_now={market_open_now}",
            required=bool(strict_session),
        ),
        _item(
            item_id="session_evidence_trackable",
            title="Session events are trackable for approvals/blocks/executions",
            passed=(event_total > 0) or (verdict_total == 0 and execution_total == 0),
            evidence=(
                f"event_total={event_total}, verdict_total={verdict_total}, "
                f"execution_total={execution_total}, error_total={error_total}"
            ),
            required=False,
        ),
    ]

    failures: List[str] = []
    for item in checklist:
        if bool(item.get("required")) and not bool(item.get("passed")):
            failures.append(f"check_failed:{item.get('id')}")
    if inject_fail:
        failures.append("inject_fail forced red-path for operator drill")

    required_total = int(sum(1 for x in checklist if bool(x.get("required"))))
    required_pass_total = int(sum(1 for x in checklist if bool(x.get("required")) and bool(x.get("passed"))))
    required_fail_total = int(required_total - required_pass_total)
    ok = (len(failures) == 0) and (not inject_fail)

    out: Dict[str, Any] = {
        "ok": bool(ok),
        "inject_fail": inject_fail,
        "day": day,
        "env_path": str(env_path),
        "event_log_path": str(event_log_path),
        "report_dir": str(report_dir),
        "strict_session": strict_session,
        "runtime_mode": {
            "RUNTIME_PROFILE": runtime_profile,
            "KIWOOM_MODE": kiwoom_mode,
            "APPROVAL_MODE": approval_mode,
            "EXECUTION_ENABLED": execution_enabled,
            "ALLOW_REAL_EXECUTION": allow_real_execution,
        },
        "guardrails": {
            "allowlist_size": int(len(allowlist)),
            "allowlist": allowlist,
            "max_notional_key": max_notional_key,
            "max_notional": float(max_notional),
            "daily_loss_limit": float(daily_loss_limit),
        },
        "market": {
            "now_kst": now.isoformat(),
            "market_open_now": market_open_now,
            "open_contract_ok": open_contract_ok,
            "closed_contract_ok": closed_contract_ok,
            "open_probe_ts": open_dt.isoformat(),
            "closed_probe_ts": closed_dt.isoformat(),
            "weekend_probe_ts": weekend_dt.isoformat(),
        },
        "events": {
            "event_total": int(event_total),
            "verdict_total": int(verdict_total),
            "execution_total": int(execution_total),
            "error_total": int(error_total),
        },
        "checklist": checklist,
        "required_total": required_total,
        "required_pass_total": required_pass_total,
        "required_fail_total": required_fail_total,
        "failure_total": int(len(failures)),
        "failures": failures,
    }

    js_path = report_dir / f"m31_mock_exam_{day}.json"
    md_path = report_dir / f"m31_mock_exam_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_build_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} market_open_now={market_open_now} "
            f"runtime_profile={runtime_profile or '(empty)'} approval_mode={approval_mode or '(empty)'} "
            f"failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)
    return 0 if bool(ok) else 3


if __name__ == "__main__":
    raise SystemExit(main())
