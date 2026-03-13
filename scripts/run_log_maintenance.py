from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.log_maintenance import LogMoveCandidate
from libs.core.log_maintenance import apply_log_move_candidates
from libs.core.log_maintenance import build_log_inventory
from libs.core.log_maintenance import write_log_inventory


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect and normalize data/logs into core/dev/milestones groups.")
    p.add_argument("--log-root", default="data/logs")
    p.add_argument("--apply", action="store_true", help="Move detected non-core log files into canonical subdirectories.")
    p.add_argument("--json", action="store_true")
    return p


def _load_candidates(inventory: dict) -> List[LogMoveCandidate]:
    out: List[LogMoveCandidate] = []
    for item in inventory.get("move_candidates") if isinstance(inventory.get("move_candidates"), list) else []:
        rel_path = str(item.get("rel_path") or "").strip()
        target_rel_path = str(item.get("target_rel_path") or "").strip()
        category = str(item.get("category") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not rel_path or not target_rel_path:
            continue
        out.append(
            LogMoveCandidate(
                rel_path=rel_path,
                target_rel_path=target_rel_path,
                category=category,
                reason=reason,
            )
        )
    return out


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    log_root = Path(str(args.log_root).strip())
    if not log_root.is_absolute():
        log_root = ROOT / log_root

    inventory = build_log_inventory(log_root)
    candidates = _load_candidates(inventory)

    moved = []
    if bool(args.apply):
        moved = apply_log_move_candidates(log_root, candidates)
        inventory = build_log_inventory(log_root)

    md_path, js_path = write_log_inventory(log_root, inventory)
    out = {
        "ok": True,
        "log_root": str(log_root),
        "apply": bool(args.apply),
        "move_candidate_total": len(candidates),
        "moved_total": len(moved),
        "moved": moved,
        "warning_total": int((inventory.get("summary") or {}).get("warning_total") or 0),
        "report_md_path": str(md_path),
        "report_json_path": str(js_path),
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"log_root={log_root} apply={bool(args.apply)} move_candidate_total={len(candidates)} "
            f"moved_total={len(moved)} warning_total={out['warning_total']} "
            f"report_json={js_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
