from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file


PHASE_PREOPEN = "preopen"
PHASE_INTRADAY = "intraday"
PHASE_CLOSEOUT = "closeout"
PHASE_WATCH = "watch"


def _first_universe_symbol() -> str:
    raw = str(os.getenv("UNIVERSE_SYMBOLS", "") or "").strip()
    if not raw:
        return ""
    for part in raw.split(","):
        symbol = str(part or "").strip()
        if symbol:
            return symbol
    return ""


def _to_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _normalize_tick_pipeline(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("integrated_chain", "integrated", "chain"):
        return "integrated_chain"
    return "legacy_m10"


def _resolve_env_path(argv: Optional[List[str]]) -> Path:
    args = list(argv or [])
    raw = ""
    for idx, token in enumerate(args):
        cur = str(token or "").strip()
        if not cur:
            continue
        if cur.startswith("--env-path="):
            raw = cur.split("=", 1)[1].strip()
            break
        if cur == "--env-path" and idx + 1 < len(args):
            raw = str(args[idx + 1] or "").strip()
            break
    if not raw:
        raw = str(os.getenv("ENV_PATH", "") or "").strip()
    if not raw:
        raw = str(ROOT / ".env")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _build_parser(default_env_path: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Official trading runtime entrypoint. Commander selects the runtime route by mode and phase."
    )
    parser.add_argument("--mode", choices=["live", "mock"], required=True)
    parser.add_argument(
        "--phase",
        choices=[PHASE_PREOPEN, PHASE_INTRADAY, PHASE_CLOSEOUT, PHASE_WATCH],
        required=True,
    )
    parser.add_argument("--env-path", default=str(default_env_path))
    parser.add_argument("--day", default=None)
    parser.add_argument("--symbol", default=os.getenv("SYMBOL", "").strip() or _first_universe_symbol())
    parser.add_argument(
        "--tick-pipeline",
        choices=["legacy_m10", "integrated_chain"],
        default=_normalize_tick_pipeline(os.getenv("M13_TICK_PIPELINE", "integrated_chain")),
    )
    parser.add_argument("--sleep-sec", type=int, default=_to_int(os.getenv("SCAN_INTERVAL_SEC", "60"), 60))
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--session-hard-gate", action="store_true")
    parser.add_argument("--allow-offhours", action="store_true")
    parser.add_argument(
        "--lock-path",
        default=str(os.getenv("M13_LIVE_LOCK_PATH", "data/state/m13_live_loop.lock") or "data/state/m13_live_loop.lock"),
    )
    parser.add_argument(
        "--lock-stale-sec",
        type=int,
        default=_to_int(os.getenv("M13_LIVE_LOCK_STALE_SEC", "1800"), 1800),
    )
    parser.add_argument("--event-log-path", default=os.getenv("EVENT_LOG_PATH", "data/logs/events.jsonl"))
    parser.add_argument("--summary-report-dir", default="reports/live_summary")
    parser.add_argument("--watch-report-dir", default="reports/live_watch")
    parser.add_argument("--lookback-min", type=int, default=_to_int(os.getenv("LIVE_SUMMARY_LOOKBACK_MIN", "30"), 30))
    parser.add_argument(
        "--max-event-lag-sec",
        type=int,
        default=_to_int(os.getenv("LIVE_WATCH_MAX_EVENT_LAG_SEC", "420"), 420),
    )
    parser.add_argument("--max-iterations", type=int, default=0)
    parser.add_argument("--fail-on-red", action="store_true")
    parser.add_argument("--report-dir", default="reports/mock_exam_day")
    parser.add_argument("--state-path", default=os.getenv("STATE_STORE_PATH", "").strip())
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--probe", action="store_true", help="Mock intraday only: run one-shot off-hours probe.")
    parser.add_argument(
        "--simulated",
        action="store_true",
        help="Mock intraday only: run continuous off-hours simulated session loop.",
    )
    parser.add_argument("--probe-symbol", default=os.getenv("SYMBOL", "005930"))
    parser.add_argument("--probe-price", type=float, default=70000.0)
    parser.add_argument("--probe-cash", type=float, default=2000000.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved commander route without executing it.")
    return parser


def build_execution_plan(args: argparse.Namespace) -> Dict[str, Any]:
    mode = str(args.mode).strip().lower()
    phase = str(args.phase).strip().lower()
    if bool(args.probe) and bool(args.simulated):
        raise ValueError("--probe and --simulated cannot be used together")

    if (bool(args.probe) or bool(args.simulated)) and not (mode == "mock" and phase == PHASE_INTRADAY):
        raise ValueError("--probe/--simulated are only supported with --mode mock --phase intraday")

    plan: Dict[str, Any] = {
        "schema_version": "session_entry_plan.v1",
        "official_entrypoint": "scripts/run_session.py",
        "mode": mode,
        "phase": phase,
        "route_selected": "",
        "commander_mode": "integrated_chain",
        "commander_phase": None,
        "implementation_id": "",
        "implementation": "",
        "argv": [],
        "notes": [],
    }

    if phase == PHASE_WATCH:
        plan.update(
            {
                "route_selected": f"commander_{mode}_watch",
                "implementation_id": "live_session_watch",
                "implementation": "scripts.run_live_session_watch.main",
                "argv": [
                    "--event-log-path",
                    str(args.event_log_path),
                    "--summary-report-dir",
                    str(args.summary_report_dir),
                    "--watch-report-dir",
                    str(args.watch_report_dir),
                    "--lock-path",
                    str(args.lock_path),
                    "--lookback-min",
                    str(int(args.lookback_min)),
                    "--sleep-sec",
                    str(int(args.sleep_sec)),
                    "--max-event-lag-sec",
                    str(int(args.max_event_lag_sec)),
                    "--max-iterations",
                    str(int(args.max_iterations)),
                ],
            }
        )
        if bool(args.once):
            plan["argv"].append("--once")
        if bool(args.json):
            plan["argv"].append("--json")
        if bool(args.fail_on_red):
            plan["argv"].append("--fail-on-red")
        plan["notes"].append("watch phase is reporting-only and does not place orders")
        return plan

    if mode == "live" and phase in (PHASE_PREOPEN, PHASE_CLOSEOUT):
        commander_phase = "preopen" if phase == PHASE_PREOPEN else "closeout"
        plan.update(
            {
                "route_selected": f"commander_live_{phase}_once",
                "commander_phase": commander_phase,
                "implementation_id": "commander_runtime_once",
                "implementation": "scripts.run_commander_runtime_once.main",
                "argv": [
                    "--live",
                    "--mode",
                    "integrated_chain",
                    "--phase",
                    commander_phase,
                    "--run-id",
                    f"run-session-{mode}-{phase}",
                ],
            }
        )
        if bool(args.json):
            plan["argv"].append("--json")
        plan["notes"].append("live preopen/closeout keeps commander as the phase owner")
        return plan

    if mode == "mock" and phase in (PHASE_PREOPEN, PHASE_CLOSEOUT):
        mock_phase = "preopen" if phase == PHASE_PREOPEN else "closeout"
        plan.update(
            {
                "route_selected": f"commander_mock_{phase}_orchestration",
                "commander_phase": mock_phase,
                "implementation_id": "mock_exam_day",
                "implementation": "scripts.run_mock_exam_day.main",
                "argv": [
                    "--phase",
                    mock_phase,
                    "--env-path",
                    str(args.env_path),
                    "--report-dir",
                    str(args.report_dir),
                    "--event-log-path",
                    str(args.event_log_path),
                    "--lock-path",
                    str(args.lock_path),
                    "--lock-stale-sec",
                    str(int(args.lock_stale_sec)),
                    "--python-path",
                    sys.executable,
                    "--timeout-sec",
                    str(int(args.timeout_sec)),
                ],
            }
        )
        if args.day:
            plan["argv"] += ["--day", str(args.day)]
        if args.state_path:
            plan["argv"] += ["--state-path", str(args.state_path)]
        if bool(args.json):
            plan["argv"].append("--json")
        plan["notes"].append("mock preopen/closeout reuses mock exam orchestration reports")
        return plan

    if mode == "mock" and phase == PHASE_INTRADAY and bool(args.probe):
        plan.update(
            {
                "route_selected": "commander_mock_intraday_probe",
                "commander_phase": "session",
                "implementation_id": "m31_agent_chain_probe",
                "implementation": "scripts.run_m31_agent_chain_probe.main",
                "argv": [
                    "--symbol",
                    str(args.probe_symbol),
                    "--price",
                    str(float(args.probe_price)),
                    "--cash",
                    str(float(args.probe_cash)),
                ],
            }
        )
        if bool(args.json):
            plan["argv"].append("--json")
        plan["notes"].append("probe mode is mock intraday validation without session loop startup")
        return plan

    if mode == "mock" and phase == PHASE_INTRADAY and bool(args.simulated):
        plan.update(
            {
                "route_selected": "commander_mock_intraday_simulated",
                "commander_phase": "session",
                "implementation_id": "offhours_validation_loop",
                "implementation": "scripts.run_offhours_validation_loop.main",
                "argv": [
                    "--env-path",
                    str(args.env_path),
                    "--event-log-path",
                    str(args.event_log_path),
                    "--sleep-sec",
                    str(int(args.sleep_sec)),
                    "--lock-path",
                    str(args.lock_path),
                    "--lock-stale-sec",
                    str(int(args.lock_stale_sec)),
                ],
            }
        )
        if args.state_path:
            plan["argv"] += ["--state-path", str(args.state_path)]
        if args.symbol:
            plan["argv"] += ["--symbol", str(args.symbol)]
        if bool(args.once):
            plan["argv"].append("--once")
        if bool(args.json):
            plan["argv"].append("--json")
        plan["notes"].append("simulated mode is off-hours mock validation with local state only")
        return plan

    plan.update(
        {
            "route_selected": f"commander_{mode}_{phase}_loop",
            "commander_phase": "session",
            "implementation_id": "m13_live_loop",
            "implementation": "scripts.run_m13_live_loop.main",
            "argv": [
                "--env-path",
                str(args.env_path),
                "--tick-pipeline",
                str(args.tick_pipeline),
                "--sleep-sec",
                str(int(args.sleep_sec)),
                "--lock-path",
                str(args.lock_path),
                "--lock-stale-sec",
                str(int(args.lock_stale_sec)),
            ],
        }
    )
    if args.symbol:
        plan["argv"] += ["--symbol", str(args.symbol)]
    if bool(args.once):
        plan["argv"].append("--once")
    if bool(args.session_hard_gate):
        plan["argv"].append("--session-hard-gate")
    if bool(args.allow_offhours):
        plan["argv"].append("--allow-offhours")
    plan["notes"].append("intraday loop backend remains loop-based and delegates each cycle into commander-aware runtime paths")
    return plan


def _dispatch(plan: Dict[str, Any]) -> int:
    implementation_id = str(plan.get("implementation_id") or "").strip()
    argv = [str(x) for x in (plan.get("argv") if isinstance(plan.get("argv"), list) else [])]

    if implementation_id == "m13_live_loop":
        from scripts.run_m13_live_loop import main as _main

        return int(_main(argv))
    if implementation_id == "live_session_watch":
        from scripts.run_live_session_watch import main as _main

        return int(_main(argv))
    if implementation_id == "mock_exam_day":
        from scripts.run_mock_exam_day import main as _main

        return int(_main(argv))
    if implementation_id == "commander_runtime_once":
        from scripts.run_commander_runtime_once import main as _main

        return int(_main(argv))
    if implementation_id == "m31_agent_chain_probe":
        from scripts.run_m31_agent_chain_probe import main as _main

        return int(_main(argv))
    if implementation_id == "offhours_validation_loop":
        from scripts.run_offhours_validation_loop import main as _main

        return int(_main(argv))
    raise SystemExit(f"unsupported implementation_id: {implementation_id}")


def _render_plan_text(plan: Dict[str, Any]) -> str:
    argv = plan.get("argv") if isinstance(plan.get("argv"), list) else []
    notes = plan.get("notes") if isinstance(plan.get("notes"), list) else []
    lines = [
        f"official_entrypoint={plan.get('official_entrypoint')}",
        f"mode={plan.get('mode')} phase={plan.get('phase')}",
        f"route_selected={plan.get('route_selected')}",
        f"commander_mode={plan.get('commander_mode')} commander_phase={plan.get('commander_phase')}",
        f"implementation={plan.get('implementation')}",
        f"argv={' '.join(str(x) for x in argv)}",
    ]
    if notes:
        lines.append(f"notes={'; '.join(str(x) for x in notes)}")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    env_path = _resolve_env_path(argv)
    load_env_file(str(env_path))
    parser = _build_parser(env_path)
    args = parser.parse_args(argv)

    try:
        plan = build_execution_plan(args)
    except ValueError as ex:
        parser.error(str(ex))
        return 2

    if bool(args.dry_run):
        if bool(args.json):
            print(json.dumps(plan, ensure_ascii=False))
        else:
            print(_render_plan_text(plan))
        return 0

    return _dispatch(plan)


if __name__ == "__main__":
    raise SystemExit(main())
