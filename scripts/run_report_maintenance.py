from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.report_maintenance import ArchiveCandidate
from libs.reporting.report_maintenance import apply_archive_candidates
from libs.reporting.report_maintenance import build_report_inventory
from libs.reporting.report_maintenance import write_report_inventory


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Inspect reports/, archive clutter, and write a report inventory.")
    p.add_argument("--report-root", default="reports")
    p.add_argument("--event-log-path", default="data/logs/events.jsonl")
    p.add_argument("--apply", action="store_true", help="Move archive candidates into reports/archive.")
    p.add_argument(
        "--include-legacy-root-daily",
        action="store_true",
        help="Also archive root-level daily_report_<day> files when canonical reports/operator_summary/daily files exist.",
    )
    p.add_argument(
        "--include-legacy-milestones",
        action="store_true",
        help="Also archive legacy milestone report directories such as m22/m23/m25/m28 outputs.",
    )
    p.add_argument("--json", action="store_true")
    return p


def _load_candidates(
    inventory: dict,
    *,
    include_legacy_root_daily: bool,
    include_legacy_milestones: bool,
) -> List[ArchiveCandidate]:
    out: List[ArchiveCandidate] = []
    for item in inventory.get("archive_candidates") if isinstance(inventory.get("archive_candidates"), list) else []:
        category = str(item.get("category") or "").strip()
        if category == "legacy_root_daily" and not include_legacy_root_daily:
            continue
        if category == "legacy_milestone_dir" and not include_legacy_milestones:
            continue
        rel_path = str(item.get("rel_path") or "").strip()
        reason = str(item.get("reason") or "").strip()
        if not rel_path:
            continue
        out.append(ArchiveCandidate(rel_path=rel_path, reason=reason, category=category))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    report_root = Path(str(args.report_root).strip())
    if not report_root.is_absolute():
        report_root = ROOT / report_root
    event_log_path = Path(str(args.event_log_path).strip())
    if not event_log_path.is_absolute():
        event_log_path = ROOT / event_log_path

    inventory = build_report_inventory(report_root, event_log_path=event_log_path)
    candidates = _load_candidates(
        inventory,
        include_legacy_root_daily=bool(args.include_legacy_root_daily),
        include_legacy_milestones=bool(args.include_legacy_milestones),
    )

    moved = []
    if bool(args.apply):
        moved = apply_archive_candidates(report_root, candidates)
        inventory = build_report_inventory(report_root, event_log_path=event_log_path)

    md_path, js_path = write_report_inventory(report_root, inventory)
    out = {
        "ok": True,
        "report_root": str(report_root),
        "event_log_path": str(event_log_path),
        "apply": bool(args.apply),
        "include_legacy_root_daily": bool(args.include_legacy_root_daily),
        "include_legacy_milestones": bool(args.include_legacy_milestones),
        "archive_candidate_total": len(candidates),
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
            f"report_root={report_root} apply={bool(args.apply)} "
            f"archive_candidate_total={len(candidates)} moved_total={len(moved)} "
            f"warning_total={out['warning_total']} report_json={js_path} report_md={md_path}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
