from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iter_trade_dirs(reports_root: Path, day: str) -> List[Path]:
    day_root = reports_root / "trades" / day
    if not day_root.exists():
        return []
    return sorted(path for path in day_root.iterdir() if path.is_dir())


def _sync_trade(trade_dir: Path, *, dry_run: bool = False) -> Dict[str, str]:
    primary = trade_dir / "reports" / "brief_llm_response.json"
    if not primary.exists():
        return {"trade_id": trade_dir.name, "status": "skip_no_primary"}

    legacy_targets = [
        trade_dir / "brief" / "brief_llm_response.json",
        trade_dir / "brief_llm_response.json",
    ]
    primary_hash = _sha(primary)
    changed = 0
    created = 0
    for target in legacy_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if _sha(target) == primary_hash:
                continue
            if not dry_run:
                target.write_bytes(primary.read_bytes())
            changed += 1
        else:
            if not dry_run:
                target.write_bytes(primary.read_bytes())
            created += 1

    status = "unchanged"
    if created or changed:
        status = "synced"
    return {
        "trade_id": trade_dir.name,
        "status": status,
        "created": str(created),
        "changed": str(changed),
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="One-time sync of legacy brief LLM artifacts from normalized reports path.")
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
