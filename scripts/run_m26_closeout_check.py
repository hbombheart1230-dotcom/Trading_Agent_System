from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m26_ab_evaluation import main as ab_eval_main
from scripts.run_m26_dataset_manifest_check import main as manifest_main
from scripts.run_m26_promotion_gate_check import main as gate_main
from scripts.run_m26_replay_runner import main as replay_main
from scripts.run_m26_scorecard import main as scorecard_main


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_json(main_fn, argv: List[str]) -> Tuple[int, Dict[str, Any]]:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main_fn(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _run_manifest_json(*, dataset_root: Path, seed_demo: bool) -> Tuple[int, Dict[str, Any]]:
    argv = ["--dataset-root", str(dataset_root), "--json"]
    if seed_demo:
        argv.insert(2, "--seed-demo")
    return _run_json(manifest_main, argv)


def _run_replay_json(*, dataset_root: Path, day: str) -> Tuple[int, Dict[str, Any]]:
    argv = ["--dataset-root", str(dataset_root), "--json"]
    if day:
        argv.extend(["--day", day])
    return _run_json(replay_main, argv)


def _run_scorecard_json(*, dataset_root: Path, day: str) -> Tuple[int, Dict[str, Any]]:
    argv = ["--dataset-root", str(dataset_root), "--json"]
    if day:
        argv.extend(["--day", day])
    return _run_json(scorecard_main, argv)


def _run_ab_eval_json(*, base_root: Path, candidate_root: Path, day: str) -> Tuple[int, Dict[str, Any]]:
    argv = [
        "--a-dataset-root",
        str(base_root),
        "--b-dataset-root",
        str(candidate_root),
        "--a-label",
        "baseline",
        "--b-label",
        "candidate",
        "--json",
    ]
    if day:
        argv.extend(["--day", day])
    return _run_json(ab_eval_main, argv)


def _run_gate_json(
    *,
    base_root: Path,
    candidate_root: Path,
    day: str,
    min_delta_total_pnl_proxy: float,
) -> Tuple[int, Dict[str, Any]]:
    argv = [
        "--a-dataset-root",
        str(base_root),
        "--b-dataset-root",
        str(candidate_root),
        "--a-label",
        "baseline",
        "--b-label",
        "candidate",
        "--min-delta-total-pnl-proxy",
        str(float(min_delta_total_pnl_proxy)),
        "--min-sortino-proxy",
        "0",
        "--max-drawdown-ratio",
        "1",
        "--json",
    ]
    if day:
        argv.extend(["--day", day])
    return _run_json(gate_main, argv)


def _prepare_candidate_dataset(candidate_root: Path, *, day: str) -> None:
    # Overwrite candidate timeline so candidate clearly outperforms baseline on realized PnL.
    _write_jsonl(
        candidate_root / "execution" / "intents.jsonl",
        [
            {"ts": f"{day}T00:01:00+00:00", "intent_id": "c-intent-1", "symbol": "005930", "action": "BUY", "qty": 1},
            {"ts": f"{day}T00:02:00+00:00", "intent_id": "c-intent-2", "symbol": "005930", "action": "SELL", "qty": 1},
        ],
    )
    _write_jsonl(
        candidate_root / "execution" / "order_status.jsonl",
        [
            {"ts": f"{day}T00:01:05+00:00", "intent_id": "c-intent-1", "status": "filled"},
            {"ts": f"{day}T00:02:05+00:00", "intent_id": "c-intent-2", "status": "filled"},
        ],
    )
    _write_jsonl(
        candidate_root / "execution" / "fills.jsonl",
        [
            {"ts": f"{day}T00:01:05+00:00", "intent_id": "c-intent-1", "fill_price": 100, "fill_qty": 1},
            {"ts": f"{day}T00:02:05+00:00", "intent_id": "c-intent-2", "fill_price": 115, "fill_qty": 1},
        ],
    )
    (candidate_root / "market" / "ohlcv_1d.csv").write_text(
        f"ts,symbol,open,high,low,close,volume\n{day}T00:00:00+00:00,005930,100,116,99,115,1000\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M26 closeout check (dataset/replay/scorecard/A-B/promotion gate).")
    p.add_argument("--base-dataset-root", default="data/eval/m26_closeout/base")
    p.add_argument("--candidate-dataset-root", default="data/eval/m26_closeout/candidate")
    p.add_argument("--day", default="2026-02-17")
    p.add_argument("--min-delta-total-pnl-proxy", type=float, default=5.0)
    p.add_argument("--inject-gate-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    base_root = Path(str(args.base_dataset_root).strip())
    candidate_root = Path(str(args.candidate_dataset_root).strip())
    day = str(args.day or "2026-02-17").strip()

    if not bool(args.no_clear):
        if base_root.exists():
            shutil.rmtree(base_root, ignore_errors=True)
        if candidate_root.exists():
            shutil.rmtree(candidate_root, ignore_errors=True)

    base_root.mkdir(parents=True, exist_ok=True)
    candidate_root.mkdir(parents=True, exist_ok=True)

    m1_rc, m1_base = _run_manifest_json(dataset_root=base_root, seed_demo=True)
    m1c_rc, m1_candidate = _run_manifest_json(dataset_root=candidate_root, seed_demo=True)

    if not bool(args.inject_gate_fail):
        _prepare_candidate_dataset(candidate_root, day=day)

    m2_base_rc, m2_base = _run_replay_json(dataset_root=base_root, day=day)
    m2_candidate_rc, m2_candidate = _run_replay_json(dataset_root=candidate_root, day=day)

    m3_base_rc, m3_base = _run_scorecard_json(dataset_root=base_root, day=day)
    m3_candidate_rc, m3_candidate = _run_scorecard_json(dataset_root=candidate_root, day=day)

    m4_rc, m4 = _run_ab_eval_json(base_root=base_root, candidate_root=candidate_root, day=day)

    min_delta = float(args.min_delta_total_pnl_proxy)
    if bool(args.inject_gate_fail):
        min_delta = max(min_delta, 9999.0)
    m5_rc, m5 = _run_gate_json(
        base_root=base_root,
        candidate_root=candidate_root,
        day=day,
        min_delta_total_pnl_proxy=min_delta,
    )

    failures: List[str] = []
    checks = [
        ("m26_1_base", m1_rc, m1_base),
        ("m26_1_candidate", m1c_rc, m1_candidate),
        ("m26_2_base", m2_base_rc, m2_base),
        ("m26_2_candidate", m2_candidate_rc, m2_candidate),
        ("m26_3_base", m3_base_rc, m3_base),
        ("m26_3_candidate", m3_candidate_rc, m3_candidate),
        ("m26_4_ab", m4_rc, m4),
        ("m26_5_gate", m5_rc, m5),
    ]
    for name, rc, obj in checks:
        if int(rc) != 0:
            failures.append(f"{name} rc != 0")
        if obj and not bool(obj.get("ok")):
            failures.append(f"{name} ok != true")

    if isinstance(m4.get("comparison"), dict):
        winner = str((m4.get("comparison") or {}).get("winner") or "")
        if winner and winner != "candidate":
            failures.append("m26_4 winner != candidate")
    if isinstance(m5, dict):
        action = str(m5.get("recommended_action") or "")
        if action and action != "promote_candidate":
            failures.append("m26_5 recommended_action != promote_candidate")

    out = {
        "ok": len(failures) == 0,
        "day": day,
        "base_dataset_root": str(base_root),
        "candidate_dataset_root": str(candidate_root),
        "m26_1_manifest": {
            "base": {"rc": int(m1_rc), "ok": bool(m1_base.get("ok")) if isinstance(m1_base, dict) else False},
            "candidate": {"rc": int(m1c_rc), "ok": bool(m1_candidate.get("ok")) if isinstance(m1_candidate, dict) else False},
        },
        "m26_2_replay": {
            "base": {
                "rc": int(m2_base_rc),
                "ok": bool(m2_base.get("ok")) if isinstance(m2_base, dict) else False,
                "replayed_intent_total": int(m2_base.get("replayed_intent_total") or 0) if isinstance(m2_base, dict) else 0,
            },
            "candidate": {
                "rc": int(m2_candidate_rc),
                "ok": bool(m2_candidate.get("ok")) if isinstance(m2_candidate, dict) else False,
                "replayed_intent_total": int(m2_candidate.get("replayed_intent_total") or 0) if isinstance(m2_candidate, dict) else 0,
            },
        },
        "m26_3_scorecard": {
            "base": {
                "rc": int(m3_base_rc),
                "ok": bool(m3_base.get("ok")) if isinstance(m3_base, dict) else False,
                "total_pnl_proxy": float(m3_base.get("total_pnl_proxy") or 0.0) if isinstance(m3_base, dict) else 0.0,
            },
            "candidate": {
                "rc": int(m3_candidate_rc),
                "ok": bool(m3_candidate.get("ok")) if isinstance(m3_candidate, dict) else False,
                "total_pnl_proxy": float(m3_candidate.get("total_pnl_proxy") or 0.0) if isinstance(m3_candidate, dict) else 0.0,
            },
        },
        "m26_4_ab": {
            "rc": int(m4_rc),
            "ok": bool(m4.get("ok")) if isinstance(m4, dict) else False,
            "winner": str((m4.get("comparison") or {}).get("winner") or "") if isinstance(m4, dict) else "",
            "recommended_action": str(
                (((m4.get("comparison") or {}).get("promotion_gate") or {}).get("recommended_action") or "")
            )
            if isinstance(m4, dict)
            else "",
        },
        "m26_5_gate": {
            "rc": int(m5_rc),
            "ok": bool(m5.get("ok")) if isinstance(m5, dict) else False,
            "recommended_action": str(m5.get("recommended_action") or "") if isinstance(m5, dict) else "",
            "delta_total_pnl_proxy": float(((m5.get("values") or {}).get("delta_total_pnl_proxy") or 0.0))
            if isinstance(m5, dict)
            else 0.0,
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} "
            f"ab_winner={out['m26_4_ab']['winner'] or 'n/a'} "
            f"gate_action={out['m26_5_gate']['recommended_action'] or 'n/a'} "
            f"delta_total_pnl_proxy={out['m26_5_gate']['delta_total_pnl_proxy']:.6f} "
            f"failure_total={len(failures)}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
