from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_FILES: List[str] = [
    "manifest.json",
    "execution/intents.jsonl",
    "execution/fills.jsonl",
    "market/ohlcv_1d.csv",
]


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
    ep = _to_epoch(ts)
    if ep is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(ep, tz=timezone.utc).strftime("%Y-%m-%d")


def _iter_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
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
                out.append(obj)
    return out


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _max_drawdown_ratio(equity: List[float]) -> Tuple[float, float]:
    if not equity:
        return 0.0, 0.0
    peak = float(equity[0])
    max_dd = 0.0
    max_dd_ratio = 0.0
    for v in equity:
        x = float(v)
        if x > peak:
            peak = x
        dd = peak - x
        if dd > max_dd:
            max_dd = dd
        denom = abs(peak) if abs(peak) > 1e-12 else 0.0
        ratio = (dd / denom) if denom > 0.0 else 0.0
        if ratio > max_dd_ratio:
            max_dd_ratio = ratio
    return float(max_dd), float(max_dd_ratio)


def _risk_adjusted(samples: List[float]) -> Dict[str, float]:
    if not samples:
        return {
            "sample_count": 0.0,
            "pnl_mean": 0.0,
            "pnl_std": 0.0,
            "downside_std": 0.0,
            "sharpe_proxy": 0.0,
            "sortino_proxy": 0.0,
        }

    n = float(len(samples))
    mean = float(statistics.fmean(samples))
    std = float(statistics.pstdev(samples)) if len(samples) > 1 else 0.0
    downside = [x for x in samples if x < 0.0]
    downside_std = float(statistics.pstdev(downside)) if len(downside) > 1 else (float(abs(downside[0])) if len(downside) == 1 else 0.0)

    sharpe = (mean / std) * math.sqrt(n) if std > 1e-12 else 0.0
    sortino = (mean / downside_std) * math.sqrt(n) if downside_std > 1e-12 else 0.0
    return {
        "sample_count": n,
        "pnl_mean": mean,
        "pnl_std": std,
        "downside_std": downside_std,
        "sharpe_proxy": float(sharpe),
        "sortino_proxy": float(sortino),
    }


def _load_close_price_by_symbol(path: Path, *, day: str) -> Dict[str, float]:
    out: Dict[str, Tuple[str, float]] = {}
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            symbol = str(row.get("symbol") or "").strip()
            if not symbol:
                continue
            ts = str(row.get("ts") or "").strip()
            d = _utc_day(ts)
            close = _safe_float(row.get("close"), default=0.0)
            if close <= 0.0:
                continue
            prev = out.get(symbol)
            if day:
                if d != day:
                    continue
                if prev is None or d >= prev[0]:
                    out[symbol] = (d, close)
            else:
                if prev is None or d >= prev[0]:
                    out[symbol] = (d, close)
    return {k: v[1] for k, v in out.items()}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M26 scorecard scaffold (PnL proxy / risk-adjusted / drawdown).")
    p.add_argument("--dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    return p


def _validate_required(dataset_root: Path) -> Tuple[List[str], List[str]]:
    failures: List[str] = []
    missing: List[str] = []
    for rel in REQUIRED_FILES:
        if not (dataset_root / rel).exists():
            missing.append(rel)
    if missing:
        failures.append("missing_required_files")

    manifest_path = dataset_root / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append(f"invalid_manifest_json ({e})")
            return failures, missing
        if str(manifest.get("schema_version") or "") != "m26.dataset_manifest.v1":
            failures.append("invalid_manifest_schema_version")
    return failures, missing


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    dataset_root = Path(str(args.dataset_root).strip())
    day = str(args.day or "").strip()

    failures, missing_files = _validate_required(dataset_root)

    intents_rows = _iter_jsonl(dataset_root / "execution" / "intents.jsonl")
    fills_rows = _iter_jsonl(dataset_root / "execution" / "fills.jsonl")

    if day:
        intents_rows = [x for x in intents_rows if _utc_day(x.get("ts")) == day]
        fills_rows = [x for x in fills_rows if _utc_day(x.get("ts")) == day]

    intent_meta: Dict[str, Dict[str, str]] = {}
    for r in intents_rows:
        iid = str(r.get("intent_id") or "").strip()
        if not iid:
            continue
        intent_meta[iid] = {
            "symbol": str(r.get("symbol") or "").strip(),
            "action": str(r.get("action") or "").strip().upper(),
        }

    close_price_by_symbol = _load_close_price_by_symbol(
        dataset_root / "market" / "ohlcv_1d.csv",
        day=day,
    )

    fills_sorted = sorted(fills_rows, key=lambda x: int(_to_epoch(x.get("ts")) or 0))
    position_qty: Dict[str, int] = {}
    avg_cost: Dict[str, float] = {}
    realized_pnl = 0.0
    gross_notional = 0.0
    trade_pnl_samples: List[float] = []
    equity_curve: List[float] = [0.0]
    executed_trade_total = 0

    for row in fills_sorted:
        iid = str(row.get("intent_id") or "").strip()
        meta = intent_meta.get(iid, {})
        symbol = str(row.get("symbol") or meta.get("symbol") or "").strip()
        if not symbol:
            continue
        action = str(row.get("action") or meta.get("action") or "BUY").strip().upper()
        qty = _safe_int(row.get("fill_qty"), default=_safe_int(row.get("qty"), 0))
        px = _safe_float(row.get("fill_price"), default=_safe_float(row.get("price"), 0.0))
        if qty <= 0 or px <= 0.0:
            continue

        executed_trade_total += 1
        gross_notional += float(qty) * float(px)
        cur_qty = int(position_qty.get(symbol, 0))
        cur_avg = float(avg_cost.get(symbol, 0.0))

        if action in ("BUY", "B"):
            if cur_qty <= 0:
                new_qty = cur_qty + qty
                if new_qty > 0:
                    # start/reset long average cost
                    avg_cost[symbol] = (float(px) * float(qty)) / float(new_qty)
                    position_qty[symbol] = new_qty
            else:
                new_qty = cur_qty + qty
                avg_cost[symbol] = ((cur_avg * float(cur_qty)) + (float(px) * float(qty))) / float(new_qty)
                position_qty[symbol] = new_qty
        elif action in ("SELL", "S"):
            if cur_qty > 0:
                matched = min(cur_qty, qty)
                pnl = (float(px) - cur_avg) * float(matched)
                realized_pnl += pnl
                trade_pnl_samples.append(float(pnl))
                remain = cur_qty - matched
                position_qty[symbol] = remain
                if remain <= 0:
                    avg_cost.pop(symbol, None)
            # short-selling path intentionally ignored in v1 scorecard

        equity_curve.append(float(realized_pnl))

    missing_close_symbols: List[str] = []
    unrealized_pnl = 0.0
    for symbol, qty in position_qty.items():
        if qty <= 0:
            continue
        close_px = close_price_by_symbol.get(symbol)
        if close_px is None:
            missing_close_symbols.append(symbol)
            continue
        avg = float(avg_cost.get(symbol, 0.0))
        unrealized_pnl += (float(close_px) - avg) * float(qty)

    total_pnl = float(realized_pnl + unrealized_pnl)
    equity_curve.append(total_pnl)
    max_dd_abs, max_dd_ratio = _max_drawdown_ratio(equity_curve)

    positive = len([x for x in trade_pnl_samples if x > 0.0])
    nonzero = len(trade_pnl_samples)
    win_rate = (float(positive) / float(nonzero)) if nonzero > 0 else 0.0

    risk_samples = list(trade_pnl_samples)
    if not risk_samples:
        # Keep deterministic shape even when there are no closed trades.
        risk_samples = [float(total_pnl)]
    risk_adjusted = _risk_adjusted(risk_samples)

    if executed_trade_total < 1:
        failures.append("executed_trade_total < 1")

    out = {
        "ok": len(failures) == 0,
        "dataset_root": str(dataset_root),
        "day": day,
        "required_file_total": len(REQUIRED_FILES),
        "missing_file_total": len(missing_files),
        "missing_files": sorted(missing_files),
        "executed_trade_total": int(executed_trade_total),
        "gross_fill_notional": float(gross_notional),
        "realized_pnl_proxy": float(realized_pnl),
        "unrealized_pnl_proxy": float(unrealized_pnl),
        "total_pnl_proxy": float(total_pnl),
        "win_rate": float(win_rate),
        "drawdown": {
            "max_drawdown_abs": float(max_dd_abs),
            "max_drawdown_ratio": float(max_dd_ratio),
            "equity_end": float(total_pnl),
            "equity_peak": float(max(equity_curve) if equity_curve else 0.0),
        },
        "risk_adjusted": risk_adjusted,
        "missing_close_symbol_total": int(len(sorted(set(missing_close_symbols)))),
        "missing_close_symbols": sorted(set(missing_close_symbols)),
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} executed_trade_total={out['executed_trade_total']} "
            f"total_pnl_proxy={out['total_pnl_proxy']:.6f} win_rate={out['win_rate']:.2%} "
            f"max_drawdown_ratio={out['drawdown']['max_drawdown_ratio']:.2%} failure_total={out['failure_total']}"
        )
        for msg in list(out.get("failures") or []):
            print(msg)
    return 0 if bool(out.get("ok")) else 3


if __name__ == "__main__":
    raise SystemExit(main())
