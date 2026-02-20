from __future__ import annotations

import argparse
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_m26_ab_evaluation import main as ab_eval_main


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _run_ab_eval_json(
    *,
    a_dataset_root: Path,
    b_dataset_root: Path,
    a_label: str,
    b_label: str,
    day: str,
) -> Tuple[int, Dict[str, Any]]:
    argv = [
        "--a-dataset-root",
        str(a_dataset_root),
        "--b-dataset-root",
        str(b_dataset_root),
        "--a-label",
        str(a_label),
        "--b-label",
        str(b_label),
        "--json",
    ]
    if day:
        argv.extend(["--day", day])
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = ab_eval_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M26 promotion gate check over A/B evaluation result.")
    p.add_argument("--a-dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--b-dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--a-label", default="baseline")
    p.add_argument("--b-label", default="candidate")
    p.add_argument("--day", default="")
    p.add_argument("--min-delta-total-pnl-proxy", type=float, default=0.0)
    p.add_argument("--min-sortino-proxy", type=float, default=0.0)
    p.add_argument("--max-drawdown-ratio", type=float, default=1.0)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    a_root = Path(str(args.a_dataset_root).strip())
    b_root = Path(str(args.b_dataset_root).strip())
    a_label = str(args.a_label or "baseline").strip() or "baseline"
    b_label = str(args.b_label or "candidate").strip() or "candidate"
    day = str(args.day or "").strip()

    failures: List[str] = []
    ab_rc, ab_obj = _run_ab_eval_json(
        a_dataset_root=a_root,
        b_dataset_root=b_root,
        a_label=a_label,
        b_label=b_label,
        day=day,
    )
    if ab_rc != 0:
        failures.append("ab_evaluation rc != 0")
    if ab_obj and not bool(ab_obj.get("ok")):
        failures.append("ab_evaluation ok != true")

    a_total_pnl = _as_float(((ab_obj.get("a") or {}).get("total_pnl_proxy") if isinstance(ab_obj.get("a"), dict) else 0.0), 0.0)
    b_total_pnl = _as_float(((ab_obj.get("b") or {}).get("total_pnl_proxy") if isinstance(ab_obj.get("b"), dict) else 0.0), 0.0)
    b_sortino = _as_float(((ab_obj.get("b") or {}).get("sortino_proxy") if isinstance(ab_obj.get("b"), dict) else 0.0), 0.0)
    b_drawdown_ratio = _as_float(
        ((ab_obj.get("b") or {}).get("max_drawdown_ratio") if isinstance(ab_obj.get("b"), dict) else 0.0),
        0.0,
    )
    delta_total_pnl = float(b_total_pnl - a_total_pnl)

    comparison = ab_obj.get("comparison") if isinstance(ab_obj.get("comparison"), dict) else {}
    winner = str(comparison.get("winner") or "")
    promotion_gate = comparison.get("promotion_gate") if isinstance(comparison.get("promotion_gate"), dict) else {}
    recommended_action = str(promotion_gate.get("recommended_action") or "")

    if winner and winner != b_label:
        failures.append(f"winner != {b_label}")

    expected_action = f"promote_{b_label}"
    if recommended_action and recommended_action != expected_action:
        failures.append(f"recommended_action != {expected_action}")

    min_delta = float(args.min_delta_total_pnl_proxy)
    min_sortino = float(args.min_sortino_proxy)
    max_dd = float(args.max_drawdown_ratio)

    if delta_total_pnl < min_delta:
        failures.append(f"delta_total_pnl_proxy < min ({delta_total_pnl:.6f} < {min_delta:.6f})")
    if b_sortino < min_sortino:
        failures.append(f"b_sortino_proxy < min ({b_sortino:.6f} < {min_sortino:.6f})")
    if b_drawdown_ratio > max_dd:
        failures.append(f"b_drawdown_ratio > max ({b_drawdown_ratio:.6f} > {max_dd:.6f})")

    out = {
        "ok": len(failures) == 0,
        "day": day,
        "a_label": a_label,
        "b_label": b_label,
        "ab_rc": int(ab_rc),
        "winner": winner,
        "recommended_action": recommended_action,
        "thresholds": {
            "min_delta_total_pnl_proxy": float(min_delta),
            "min_sortino_proxy": float(min_sortino),
            "max_drawdown_ratio": float(max_dd),
        },
        "values": {
            "a_total_pnl_proxy": float(a_total_pnl),
            "b_total_pnl_proxy": float(b_total_pnl),
            "delta_total_pnl_proxy": float(delta_total_pnl),
            "b_sortino_proxy": float(b_sortino),
            "b_max_drawdown_ratio": float(b_drawdown_ratio),
        },
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} winner={winner or 'n/a'} recommended_action={recommended_action or 'n/a'} "
            f"delta_total_pnl_proxy={delta_total_pnl:.6f} b_sortino_proxy={b_sortino:.6f} "
            f"b_max_drawdown_ratio={b_drawdown_ratio:.6f} failure_total={out['failure_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
