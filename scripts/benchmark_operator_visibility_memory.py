"""Reproducible memory benchmark for the two EOD report functions in
libs/reporting/operator_visibility.py that read events.jsonl:
generate_decision_story_report and generate_run_card_report.

Built after an OOM RCA (2026-09-18 Docker container OOMKilled at market
close) found these functions used to materialize the ENTIRE events.jsonl
history into memory before filtering by day. That specific bug (unbounded
growth as TOTAL HISTORY accumulates release over release) is fixed. This
benchmark exists so the remaining, fundamentally different question -- does
peak memory also scale with the SIZE OF A SINGLE DAY'S rows, which is large
but naturally bounded, not unbounded -- can be measured by anyone, with real
numbers, instead of asserted.

Two independent scaling axes, matching the two ways this file can grow:
  A. HISTORY axis: total file size increases (more accumulated days), the
     target day's own row count stays fixed. Expected/required: peak RSS
     stays flat regardless of how large A gets (this is the bug that was
     actually fixed).
  B. DAY axis: the target day's own row count/size increases (a busier
     trading day), total history stays fixed. Some growth with day size is
     expected (day_rows is still a materialized list, shared by
     _build_run_contexts, build_commander_route_summary and
     _build_report_freshness -- see the OOM RCA follow-up notes). The bar
     is sub-linear/bounded-in-practice, not flat -- this benchmark reports
     the actual MB-of-RSS-per-MB-of-day-JSON ratio so that bar can be
     judged with a number, not a guess.

Usage:
  # 1) generate a fixture (writes directly to disk, isolated from measurement)
  python scripts/benchmark_operator_visibility_memory.py gen-fixture \
      --out FIXTURE.jsonl --history-mb 420 --day-mb 5 --day 2026-04-08

  # 2) measure one function against one fixture, in an isolated child process
  #    (self-measures its OWN peak working-set via the Windows API, so
  #    fixture-generation memory is never part of the number)
  python scripts/benchmark_operator_visibility_memory.py measure \
      --events FIXTURE.jsonl --day 2026-04-08 --func decision_story

  # 3) run the full two-axis suite and print a table
  python scripts/benchmark_operator_visibility_memory.py suite --out-dir DIR

Windows-only for the peak-working-set measurement (uses
psapi.GetProcessMemoryInfo via ctypes -- no new dependency). On other
platforms, `measure` still runs the report and reports elapsed time, but
peak_ws_mb will be None.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixture generation
# ---------------------------------------------------------------------------

OTHER_DAYS = [f"2026-{m:02d}-{d:02d}" for m in range(1, 9) for d in (1, 8, 15, 22)]


def _filler_row(day: str, i: int) -> Dict[str, Any]:
    return {
        "run_id": f"q9_comparison_forward_recovery_{day.replace('-', '')}_{i:06d}_1",
        "ts": f"{day}T01:{(i // 3600) % 60:02d}:{i % 60:02d}+00:00",
        "stage": "skill_execute" if i % 2 == 0 else "skill_result",
        "event": "call" if i % 2 == 0 else "ok",
        "event_name": "skill_execute.call" if i % 2 == 0 else "skill_result.ok",
        "level": "info", "trade_id": "", "session_id": "", "cycle_id": "",
        "agent": "skill_execute" if i % 2 == 0 else "skill_result",
        "phase": "", "symbol": "",
        "payload": {"skill": "market.minute_ohlcv", "api_id": "ka10080", "step": 0,
                    "path": "/api/dostk/chart", "outputs": "MinuteOHLCVDTO"},
    }


def _target_day_events_for_run(day: str, run_idx: int, sec_offset: int) -> list[Dict[str, Any]]:
    """A realistic-shaped RUN for the target day -- one run_id producing
    the same multi-event sequence a real commander tick actually emits
    (decision -> router -> scanner -> monitor -> execute_from_packet, plus
    a couple of skill calls in between), not one row per run_id. A real
    production day has many rows per run, not one row = one run; an
    earlier version of this benchmark used 1 row per run_id, which
    overstated day-size memory scaling by inflating the distinct-run-id
    count (and therefore the by_run accumulator's own size) far beyond
    what a real trading day produces."""
    run_id = f"benchday-run-{run_idx:06d}"

    def _ts(k: int) -> str:
        total = sec_offset + k
        return f"{day}T{(total // 3600) % 24:02d}:{(total // 60) % 60:02d}:{total % 60:02d}+00:00"

    return [
        {"run_id": run_id, "ts": _ts(0), "stage": "skill_execute", "event": "call",
         "payload": {"skill": "market.minute_ohlcv", "api_id": "ka10080", "step": 0, "path": "/api/dostk/chart"}},
        {"run_id": run_id, "ts": _ts(1), "stage": "skill_result", "event": "ok",
         "payload": {"skill": "market.minute_ohlcv", "outputs": "MinuteOHLCVDTO"}},
        {"run_id": run_id, "ts": _ts(2), "stage": "decision", "event": "trace",
         "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1, "reason": "entry"}}}},
        {"run_id": run_id, "ts": _ts(3), "stage": "commander_router", "event": "route_selected",
         "payload": {"route_selected": "full_cycle"}},
        {"run_id": run_id, "ts": _ts(4), "stage": "scanner", "event": "candidate_selection_reason",
         "payload": {"selected_symbol": "005930", "score_total": 0.7}},
        {"run_id": run_id, "ts": _ts(5), "stage": "monitor", "event": "entry_decision_detail",
         "payload": {"no_trade_surface": {"no_trade_stage": "guard_block", "dominant_blocker": "spread_too_wide"}}},
        {"run_id": run_id, "ts": _ts(6), "stage": "execute_from_packet", "event": "verdict",
         "payload": {"allowed": False, "reason": "blocked_by_guard"}},
    ]


def gen_fixture(out_path: Path, *, history_mb: float, day_mb: float, day: str) -> Dict[str, Any]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    day_bytes_target = int(day_mb * 1024 * 1024)
    history_bytes_target = int(history_mb * 1024 * 1024)
    day_written = 0
    run_idx = 0
    with out_path.open("w", encoding="utf-8") as f:
        while day_written < day_bytes_target:
            for row in _target_day_events_for_run(day, run_idx, run_idx * 30):
                line = json.dumps(row, ensure_ascii=False) + "\n"
                f.write(line)
                n = len(line.encode("utf-8"))
                written += n
                day_written += n
            run_idx += 1
        day_idx = 0
        while written < history_bytes_target:
            other_day = OTHER_DAYS[day_idx % len(OTHER_DAYS)]
            for i in range(20000):
                line = json.dumps(_filler_row(other_day, i), ensure_ascii=False) + "\n"
                f.write(line)
                written += len(line.encode("utf-8"))
                if written >= history_bytes_target:
                    break
            day_idx += 1
    return {
        "path": str(out_path),
        "total_mb": written / 1024 / 1024,
        "day_mb": day_written / 1024 / 1024,
        "day": day,
        "target_runs": run_idx,
    }


# ---------------------------------------------------------------------------
# Peak working-set measurement (Windows) -- self-measurement, no new deps
# ---------------------------------------------------------------------------

def _self_peak_ws_mb() -> Optional[float]:
    if platform.system() != "Windows":
        return None
    import ctypes
    import ctypes.wintypes as wt

    class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wt.DWORD]
    h = kernel32.GetCurrentProcess()
    c = PROCESS_MEMORY_COUNTERS()
    c.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
    ok = psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb)
    return (c.PeakWorkingSetSize / 1024 / 1024) if ok else None


def _run_worker(events: Path, day: str, func: str, out_dir: Path) -> Dict[str, Any]:
    """Runs IN THIS process -- only called from the isolated child process
    spawned by `measure`, never from the parent, so the number reflects
    only this process's own work."""
    from libs.reporting.operator_visibility import (
        generate_decision_story_report,
        generate_run_card_report,
    )

    t0 = time.time()
    if func == "decision_story":
        _md, obj = generate_decision_story_report(events, out_dir, day=day, trade_only=False)
    elif func == "run_card":
        _md, obj = generate_run_card_report(events, out_dir, day=day, trade_only=False)
    else:
        raise ValueError(f"unknown func: {func}")
    elapsed = time.time() - t0
    peak = _self_peak_ws_mb()
    return {
        "func": func, "day": day, "events": str(events),
        "story_total": obj.get("story_total"), "elapsed_sec": elapsed,
        "peak_ws_mb": peak,
    }


def measure(events: Path, day: str, func: str, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Spawns a fresh child process to do the actual work, so this
    process's own baseline (e.g. from generating a fixture beforehand)
    never contaminates the reported peak."""
    out_dir = out_dir or (events.parent / f"bench_out_{func}")
    cmd = [
        sys.executable, str(Path(__file__).resolve()),
        "_worker",
        "--events", str(events),
        "--day", day,
        "--func", func,
        "--out-dir", str(out_dir),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise RuntimeError(f"worker failed (rc={proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    line = [l for l in proc.stdout.splitlines() if l.startswith("BENCH_RESULT:")]
    if not line:
        raise RuntimeError(f"worker produced no result line:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(line[-1][len("BENCH_RESULT:"):])


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("gen-fixture")
    p_gen.add_argument("--out", required=True)
    p_gen.add_argument("--history-mb", type=float, default=420.0)
    p_gen.add_argument("--day-mb", type=float, default=1.0)
    p_gen.add_argument("--day", default="2026-04-08")

    p_meas = sub.add_parser("measure")
    p_meas.add_argument("--events", required=True)
    p_meas.add_argument("--day", required=True)
    p_meas.add_argument("--func", required=True, choices=["decision_story", "run_card"])
    p_meas.add_argument("--out-dir")

    p_worker = sub.add_parser("_worker", help=argparse.SUPPRESS)
    p_worker.add_argument("--events", required=True)
    p_worker.add_argument("--day", required=True)
    p_worker.add_argument("--func", required=True)
    p_worker.add_argument("--out-dir", required=True)

    p_suite = sub.add_parser("suite")
    p_suite.add_argument("--out-dir", required=True)

    args = ap.parse_args()

    if args.cmd == "gen-fixture":
        result = gen_fixture(Path(args.out), history_mb=args.history_mb, day_mb=args.day_mb, day=args.day)
        print(json.dumps(result, indent=2))
    elif args.cmd == "measure":
        result = measure(Path(args.events), args.day, args.func, Path(args.out_dir) if args.out_dir else None)
        print(json.dumps(result, indent=2))
    elif args.cmd == "_worker":
        result = _run_worker(Path(args.events), args.day, args.func, Path(args.out_dir))
        print("BENCH_RESULT:" + json.dumps(result))
    elif args.cmd == "suite":
        _run_suite(Path(args.out_dir))


def _run_suite(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    day = "2026-04-08"
    rows = []

    # Axis A: history scaling, day size fixed small
    for history_mb in (420.0, 840.0):
        fixture = out_dir / f"fixture_hist{int(history_mb)}.jsonl"
        gen_fixture(fixture, history_mb=history_mb, day_mb=0.02, day=day)
        for func in ("decision_story", "run_card"):
            r = measure(fixture, day, func, out_dir / f"out_hist{int(history_mb)}_{func}")
            r["axis"] = "history"
            r["history_mb"] = history_mb
            rows.append(r)

    # Axis B: day scaling, history size fixed
    for day_mb in (5.0, 40.0):
        fixture = out_dir / f"fixture_day{int(day_mb)}.jsonl"
        gen_fixture(fixture, history_mb=450.0, day_mb=day_mb, day=day)
        for func in ("decision_story", "run_card"):
            r = measure(fixture, day, func, out_dir / f"out_day{int(day_mb)}_{func}")
            r["axis"] = "day"
            r["day_mb"] = day_mb
            rows.append(r)

    print(f"{'axis':8s} {'func':15s} {'history_mb':>10s} {'day_mb':>7s} {'peak_ws_mb':>10s} {'elapsed_s':>9s}")
    for r in rows:
        print(f"{r['axis']:8s} {r['func']:15s} {r.get('history_mb', ''):>10} {r.get('day_mb', ''):>7} "
              f"{r['peak_ws_mb']:>10.1f} {r['elapsed_sec']:>9.2f}")


if __name__ == "__main__":
    main()
