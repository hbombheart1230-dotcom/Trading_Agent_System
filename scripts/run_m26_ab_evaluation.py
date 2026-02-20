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

from scripts.run_m26_scorecard import main as scorecard_main


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _json_path_get(obj: Dict[str, Any], path: str, default: float = 0.0) -> float:
    cur: Any = obj
    for part in path.split("."):
        if not isinstance(cur, dict):
            return float(default)
        cur = cur.get(part)
    return _as_float(cur, default)


def _run_scorecard_json(*, dataset_root: Path, day: str) -> Tuple[int, Dict[str, Any]]:
    argv = ["--dataset-root", str(dataset_root), "--json"]
    if day:
        argv.extend(["--day", day])
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = scorecard_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M26 A/B evaluation scaffold over scorecard outputs.")
    p.add_argument("--a-dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--b-dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--a-label", default="A")
    p.add_argument("--b-label", default="B")
    p.add_argument("--day", default="")
    p.add_argument("--json", action="store_true")
    return p


def _compare_metrics(
    *,
    a_label: str,
    b_label: str,
    a_score: Dict[str, Any],
    b_score: Dict[str, Any],
) -> Dict[str, Any]:
    metric_rules: List[Tuple[str, str]] = [
        ("total_pnl_proxy", "higher"),
        ("risk_adjusted.sortino_proxy", "higher"),
        ("risk_adjusted.sharpe_proxy", "higher"),
        ("drawdown.max_drawdown_ratio", "lower"),
        ("win_rate", "higher"),
    ]
    eps = 1e-12
    points: Dict[str, int] = {a_label: 0, b_label: 0}
    results: List[Dict[str, Any]] = []

    for metric, direction in metric_rules:
        a_val = _json_path_get(a_score, metric, 0.0)
        b_val = _json_path_get(b_score, metric, 0.0)
        winner = "tie"
        if direction == "higher":
            if b_val > a_val + eps:
                winner = b_label
                points[b_label] += 1
            elif a_val > b_val + eps:
                winner = a_label
                points[a_label] += 1
        else:
            if b_val + eps < a_val:
                winner = b_label
                points[b_label] += 1
            elif a_val + eps < b_val:
                winner = a_label
                points[a_label] += 1

        results.append(
            {
                "metric": metric,
                "direction": direction,
                "a_value": float(a_val),
                "b_value": float(b_val),
                "delta_b_minus_a": float(b_val - a_val),
                "winner": winner,
            }
        )

    if points[b_label] > points[a_label]:
        winner = b_label
    elif points[a_label] > points[b_label]:
        winner = a_label
    else:
        winner = "tie"

    # Conservative promotion gate:
    # winner must keep drawdown no worse and improve or match PnL + Sortino.
    a_pnl = _json_path_get(a_score, "total_pnl_proxy", 0.0)
    b_pnl = _json_path_get(b_score, "total_pnl_proxy", 0.0)
    a_sortino = _json_path_get(a_score, "risk_adjusted.sortino_proxy", 0.0)
    b_sortino = _json_path_get(b_score, "risk_adjusted.sortino_proxy", 0.0)
    a_dd = _json_path_get(a_score, "drawdown.max_drawdown_ratio", 0.0)
    b_dd = _json_path_get(b_score, "drawdown.max_drawdown_ratio", 0.0)

    recommended = "hold"
    reasons: List[str] = []
    if winner == b_label:
        if (b_pnl >= a_pnl) and (b_sortino >= a_sortino) and (b_dd <= a_dd):
            recommended = f"promote_{b_label}"
            reasons.append("b beats or matches A on pnl/sortino and keeps drawdown no worse")
        else:
            recommended = f"no_promote_{b_label}"
            reasons.append("b wins points but fails conservative promotion gate")
    elif winner == a_label:
        if (a_pnl >= b_pnl) and (a_sortino >= b_sortino) and (a_dd <= b_dd):
            recommended = f"promote_{a_label}"
            reasons.append("a beats or matches B on pnl/sortino and keeps drawdown no worse")
        else:
            recommended = f"no_promote_{a_label}"
            reasons.append("a wins points but fails conservative promotion gate")
    else:
        reasons.append("tie result")

    return {
        "metric_results": results,
        "points": points,
        "winner": winner,
        "promotion_gate": {
            "recommended_action": recommended,
            "reasons": reasons,
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    a_root = Path(str(args.a_dataset_root).strip())
    b_root = Path(str(args.b_dataset_root).strip())
    a_label = str(args.a_label or "A").strip() or "A"
    b_label = str(args.b_label or "B").strip() or "B"
    day = str(args.day or "").strip()

    failures: List[str] = []
    a_rc, a_obj = _run_scorecard_json(dataset_root=a_root, day=day)
    b_rc, b_obj = _run_scorecard_json(dataset_root=b_root, day=day)

    if a_rc != 0:
        failures.append("a_scorecard rc != 0")
    if b_rc != 0:
        failures.append("b_scorecard rc != 0")
    if a_obj and not bool(a_obj.get("ok")):
        failures.append("a_scorecard ok != true")
    if b_obj and not bool(b_obj.get("ok")):
        failures.append("b_scorecard ok != true")

    comparison: Dict[str, Any] = {}
    if not failures:
        comparison = _compare_metrics(a_label=a_label, b_label=b_label, a_score=a_obj, b_score=b_obj)

    out = {
        "ok": len(failures) == 0,
        "day": day,
        "a": {
            "label": a_label,
            "dataset_root": str(a_root),
            "rc": int(a_rc),
            "ok": bool(a_obj.get("ok")) if isinstance(a_obj, dict) else False,
            "total_pnl_proxy": _json_path_get(a_obj if isinstance(a_obj, dict) else {}, "total_pnl_proxy", 0.0),
            "sortino_proxy": _json_path_get(a_obj if isinstance(a_obj, dict) else {}, "risk_adjusted.sortino_proxy", 0.0),
            "max_drawdown_ratio": _json_path_get(
                a_obj if isinstance(a_obj, dict) else {},
                "drawdown.max_drawdown_ratio",
                0.0,
            ),
            "win_rate": _json_path_get(a_obj if isinstance(a_obj, dict) else {}, "win_rate", 0.0),
        },
        "b": {
            "label": b_label,
            "dataset_root": str(b_root),
            "rc": int(b_rc),
            "ok": bool(b_obj.get("ok")) if isinstance(b_obj, dict) else False,
            "total_pnl_proxy": _json_path_get(b_obj if isinstance(b_obj, dict) else {}, "total_pnl_proxy", 0.0),
            "sortino_proxy": _json_path_get(b_obj if isinstance(b_obj, dict) else {}, "risk_adjusted.sortino_proxy", 0.0),
            "max_drawdown_ratio": _json_path_get(
                b_obj if isinstance(b_obj, dict) else {},
                "drawdown.max_drawdown_ratio",
                0.0,
            ),
            "win_rate": _json_path_get(b_obj if isinstance(b_obj, dict) else {}, "win_rate", 0.0),
        },
        "comparison": comparison,
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        winner = (comparison.get("winner") if isinstance(comparison, dict) else "") or "n/a"
        rec = (
            ((comparison.get("promotion_gate") or {}).get("recommended_action"))
            if isinstance(comparison, dict)
            else ""
        ) or "n/a"
        print(
            f"ok={out['ok']} winner={winner} recommended_action={rec} "
            f"a_total_pnl={out['a']['total_pnl_proxy']:.6f} b_total_pnl={out['b']['total_pnl_proxy']:.6f} "
            f"failure_total={out['failure_total']}"
        )
        for msg in list(out.get("failures") or []):
            print(msg)
    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
