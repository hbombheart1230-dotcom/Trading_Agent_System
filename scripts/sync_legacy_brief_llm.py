from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.llm_artifacts import iter_trade_dirs as _iter_trade_dirs_under_day


def _iter_trade_dirs(reports_root: Path, day: str) -> List[Path]:
    day_root = reports_root / "trades" / day
    if not day_root.exists():
        return []
    return _iter_trade_dirs_under_day(day_root)


def _sync_trade(trade_dir: Path, *, dry_run: bool = False) -> Dict[str, str]:
    primary = trade_dir / "reports" / "brief_llm_response.json"
    if not primary.exists():
        return {"trade_id": trade_dir.name, "status": "skip_no_primary"}
    return {
        "trade_id": trade_dir.name,
        "status": "canonical_present",
        "canonical_path": str(primary),
        "deprecated_legacy_sync": "true",
        "dry_run": str(bool(dry_run)).lower(),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Deprecated utility: inspect canonical brief LLM artifacts without creating legacy duplicates.")
    p.add_argument("--day", required=True)
    p.add_argument("--reports-root", default="reports")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    reports_root = Path(str(args.reports_root).strip() or "reports")
    if not reports_root.is_absolute():
        reports_root = ROOT / reports_root
    day = str(args.day).strip()
    rows = [_sync_trade(path, dry_run=bool(args.dry_run)) for path in _iter_trade_dirs(reports_root, day)]
    out = {
        "ok": True,
        "day": day,
        "reports_root": str(reports_root),
        "dry_run": bool(args.dry_run),
        "trade_count": len(rows),
        "rows": rows,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok=true day={day} trade_count={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
