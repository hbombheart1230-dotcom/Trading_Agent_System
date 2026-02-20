from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SCHEMA_VERSION = "m26.dataset_manifest.v1"
REQUIRED_COMPONENT_FILES: Dict[str, List[str]] = {
    "market": [
        "market/ohlcv_1m.csv",
        "market/ohlcv_5m.csv",
        "market/ohlcv_1d.csv",
        "market/corporate_actions.csv",
    ],
    "execution": [
        "execution/intents.jsonl",
        "execution/order_status.jsonl",
        "execution/fills.jsonl",
    ],
    "microstructure": [
        "microstructure/top_of_book.jsonl",
    ],
    "features": [
        "features/scanner_monitor_features.jsonl",
    ],
    "news": [
        "news/headlines.jsonl",
        "news/sentiment_by_symbol.jsonl",
        "news/sentiment_daily.jsonl",
    ],
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _seed_demo_dataset(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)

    csv_seed = "ts,symbol,open,high,low,close,volume\n2026-02-17T00:00:00+00:00,005930,70000,70500,69900,70300,120000\n"
    _write_text(root / "market" / "ohlcv_1m.csv", csv_seed)
    _write_text(root / "market" / "ohlcv_5m.csv", csv_seed)
    _write_text(root / "market" / "ohlcv_1d.csv", csv_seed)
    _write_text(
        root / "market" / "corporate_actions.csv",
        "symbol,action,effective_date,ratio\n005930,split,2026-01-15,1.0\n",
    )

    _write_text(
        root / "execution" / "intents.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:01:00+00:00",
                "intent_id": "demo-intent-1",
                "symbol": "005930",
                "action": "BUY",
                "qty": 1,
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write_text(
        root / "execution" / "order_status.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:01:05+00:00",
                "intent_id": "demo-intent-1",
                "status": "filled",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write_text(
        root / "execution" / "fills.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:01:05+00:00",
                "intent_id": "demo-intent-1",
                "fill_price": 70300,
                "fill_qty": 1,
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    _write_text(
        root / "microstructure" / "top_of_book.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:00:30+00:00",
                "symbol": "005930",
                "bid": 70200,
                "ask": 70300,
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    _write_text(
        root / "features" / "scanner_monitor_features.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:00:40+00:00",
                "symbol": "005930",
                "features": {"rsi14": 55.2, "ma20_gap": 0.01},
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    _write_text(
        root / "news" / "headlines.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:00:50+00:00",
                "symbol": "005930",
                "title": "demo headline",
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write_text(
        root / "news" / "sentiment_by_symbol.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:00:55+00:00",
                "symbol": "005930",
                "sentiment": 0.15,
            },
            ensure_ascii=False,
        )
        + "\n",
    )
    _write_text(
        root / "news" / "sentiment_daily.jsonl",
        json.dumps(
            {
                "ts": "2026-02-17T00:00:59+00:00",
                "market_sentiment": 0.08,
            },
            ensure_ascii=False,
        )
        + "\n",
    )

    manifest: Dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_id": "m26-fixed-demo-v1",
        "generated_at": _utc_now_iso(),
        "components": {k: list(v) for k, v in REQUIRED_COMPONENT_FILES.items()},
    }
    manifest_path = root / "manifest.json"
    _write_text(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest_path


def _validate_dataset(root: Path) -> Dict[str, Any]:
    manifest_path = root / "manifest.json"
    failures: List[str] = []
    missing_files: List[str] = []
    schema_version = ""
    dataset_id = ""

    manifest: Dict[str, Any] = {}
    if not manifest_path.exists():
        failures.append("missing:manifest.json")
    else:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append(f"invalid:manifest.json ({e})")

    if manifest:
        schema_version = str(manifest.get("schema_version") or "")
        dataset_id = str(manifest.get("dataset_id") or "")
        if schema_version != SCHEMA_VERSION:
            failures.append(f"invalid:schema_version (expected={SCHEMA_VERSION}, got={schema_version or 'empty'})")
        if not dataset_id:
            failures.append("invalid:dataset_id (empty)")

        components = manifest.get("components")
        if not isinstance(components, dict):
            failures.append("invalid:components (must be object)")
            components = {}
        for comp, expected in REQUIRED_COMPONENT_FILES.items():
            listed = components.get(comp)
            if not isinstance(listed, list):
                failures.append(f"missing_component:{comp}")
                listed = []
            listed_set = {str(x).replace("\\", "/") for x in listed}
            for rel in expected:
                if rel not in listed_set:
                    failures.append(f"missing_manifest_ref:{rel}")
                if not (root / rel).exists():
                    missing_files.append(rel)
    else:
        # Even when manifest is missing/invalid, report expected missing files
        for expected in REQUIRED_COMPONENT_FILES.values():
            for rel in expected:
                if not (root / rel).exists():
                    missing_files.append(rel)

    missing_files = sorted(set(missing_files))
    out = {
        "ok": len(failures) == 0 and len(missing_files) == 0,
        "dataset_root": str(root),
        "manifest_path": str(manifest_path),
        "schema_version": schema_version,
        "dataset_id": dataset_id,
        "component_total": len(REQUIRED_COMPONENT_FILES),
        "required_file_total": int(sum(len(v) for v in REQUIRED_COMPONENT_FILES.values())),
        "present_file_total": 0,
        "missing_file_total": len(missing_files),
        "missing_files": missing_files,
        "failure_total": len(failures),
        "failures": failures,
    }
    # compute present count from required total minus unique missing
    out["present_file_total"] = int(out["required_file_total"]) - int(out["missing_file_total"])
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M26 fixed dataset manifest scaffold and validation gate.")
    p.add_argument("--dataset-root", default="data/eval/m26_fixed_dataset_v1")
    p.add_argument("--seed-demo", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(str(args.dataset_root).strip())
    if bool(args.seed_demo):
        _seed_demo_dataset(root)

    out = _validate_dataset(root)
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} dataset_root={out['dataset_root']} "
            f"required_file_total={out['required_file_total']} missing_file_total={out['missing_file_total']} "
            f"failure_total={out['failure_total']}"
        )
        for msg in list(out.get("failures") or []):
            print(msg)
        for rel in list(out.get("missing_files") or []):
            print(f"missing_file:{rel}")
    return 0 if bool(out.get("ok")) else 3


if __name__ == "__main__":
    raise SystemExit(main())
