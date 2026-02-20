from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


REQUIRED_FILES: List[str] = [
    "manifest.json",
    "execution/intents.jsonl",
    "execution/order_status.jsonl",
    "execution/fills.jsonl",
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
    epoch = _to_epoch(ts)
    if epoch is None:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")


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


def _num_summary(values: List[float]) -> Dict[str, float]:
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


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M26 replay runner scaffold over fixed dataset execution timeline.")
    p.add_argument("--dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--day", default=None)
    p.add_argument("--json", action="store_true")
    return p


def _validate_required(dataset_root: Path) -> Tuple[List[str], List[str]]:
    failures: List[str] = []
    missing_files: List[str] = []
    for rel in REQUIRED_FILES:
        if not (dataset_root / rel).exists():
            missing_files.append(rel)
    if missing_files:
        failures.append("missing_required_files")
    manifest_path = dataset_root / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append(f"invalid_manifest_json ({e})")
            return failures, missing_files
        schema_version = str(manifest.get("schema_version") or "")
        if schema_version != "m26.dataset_manifest.v1":
            failures.append("invalid_manifest_schema_version")
    return failures, missing_files


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    dataset_root = Path(str(args.dataset_root).strip())
    day = str(args.day or "").strip()

    failures, missing_files = _validate_required(dataset_root)

    intents_path = dataset_root / "execution" / "intents.jsonl"
    status_path = dataset_root / "execution" / "order_status.jsonl"
    fills_path = dataset_root / "execution" / "fills.jsonl"

    intents_raw = _iter_jsonl(intents_path)
    status_raw = _iter_jsonl(status_path)
    fills_raw = _iter_jsonl(fills_path)

    if day:
        intents = [x for x in intents_raw if _utc_day(x.get("ts")) == day]
        order_status = [x for x in status_raw if _utc_day(x.get("ts")) == day]
        fills = [x for x in fills_raw if _utc_day(x.get("ts")) == day]
    else:
        intents = intents_raw
        order_status = status_raw
        fills = fills_raw

    terminal_statuses = {"filled", "executed", "cancelled", "rejected", "failed"}
    executed_statuses = {"filled", "executed"}
    blocked_statuses = {"rejected", "failed"}

    intent_ids: Set[str] = set()
    executed_ids: Set[str] = set()
    blocked_ids: Set[str] = set()
    terminal_ids: Set[str] = set()
    intent_ts_by_id: Dict[str, int] = {}
    terminal_ts_by_id: Dict[str, int] = {}

    for row in intents:
        iid = str(row.get("intent_id") or "").strip()
        if not iid:
            continue
        intent_ids.add(iid)
        ep = _to_epoch(row.get("ts"))
        if ep is not None:
            prev = intent_ts_by_id.get(iid)
            if prev is None or ep < prev:
                intent_ts_by_id[iid] = ep

    for row in order_status:
        iid = str(row.get("intent_id") or "").strip()
        if not iid:
            continue
        intent_ids.add(iid)
        st = str(row.get("status") or "").strip().lower()
        if st in terminal_statuses:
            terminal_ids.add(iid)
            ep = _to_epoch(row.get("ts"))
            if ep is not None:
                prev = terminal_ts_by_id.get(iid)
                if prev is None or ep < prev:
                    terminal_ts_by_id[iid] = ep
        if st in executed_statuses:
            executed_ids.add(iid)
        if st in blocked_statuses:
            blocked_ids.add(iid)

    fill_qty_total = 0
    fill_notional_total = 0.0
    for row in fills:
        iid = str(row.get("intent_id") or "").strip()
        if not iid:
            continue
        intent_ids.add(iid)
        executed_ids.add(iid)
        terminal_ids.add(iid)
        ep = _to_epoch(row.get("ts"))
        if ep is not None:
            prev = terminal_ts_by_id.get(iid)
            if prev is None or ep < prev:
                terminal_ts_by_id[iid] = ep
        try:
            qty = int(float(row.get("fill_qty") or 0))
        except Exception:
            qty = 0
        try:
            px = float(row.get("fill_price") or 0.0)
        except Exception:
            px = 0.0
        if qty > 0:
            fill_qty_total += qty
        if qty > 0 and px > 0.0:
            fill_notional_total += float(qty) * px

    replay_latency_sec: List[float] = []
    for iid in sorted(intent_ids):
        st = intent_ts_by_id.get(iid)
        en = terminal_ts_by_id.get(iid)
        if st is None or en is None:
            continue
        dt = float(en - st)
        if dt >= 0.0:
            replay_latency_sec.append(dt)

    replayed_intent_total = len(intent_ids)
    executed_intent_total = len(executed_ids)
    blocked_intent_total = len(blocked_ids)
    pending_intent_total = len([iid for iid in intent_ids if iid not in terminal_ids])

    if replayed_intent_total < 1:
        failures.append("replayed_intent_total < 1")

    out = {
        "ok": len(failures) == 0,
        "dataset_root": str(dataset_root),
        "day": day,
        "required_file_total": len(REQUIRED_FILES),
        "missing_file_total": len(missing_files),
        "missing_files": sorted(missing_files),
        "intents_total": len(intents),
        "order_status_total": len(order_status),
        "fills_total": len(fills),
        "replayed_intent_total": int(replayed_intent_total),
        "executed_intent_total": int(executed_intent_total),
        "blocked_intent_total": int(blocked_intent_total),
        "pending_intent_total": int(pending_intent_total),
        "fill_qty_total": int(fill_qty_total),
        "fill_notional_total": float(fill_notional_total),
        "replay_latency_sec": _num_summary(replay_latency_sec),
        "failure_total": len(failures),
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} replayed_intent_total={out['replayed_intent_total']} "
            f"executed_intent_total={out['executed_intent_total']} blocked_intent_total={out['blocked_intent_total']} "
            f"missing_file_total={out['missing_file_total']} failure_total={out['failure_total']}"
        )
        for msg in list(out.get("failures") or []):
            print(msg)
    return 0 if bool(out.get("ok")) else 3


if __name__ == "__main__":
    raise SystemExit(main())
