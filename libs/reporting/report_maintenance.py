from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


_OFFHOURS_PREFIX = "offhours_"
_ROOT_DAILY_RE = re.compile(r"^(?:daily_report_|daily_)(\d{4}-\d{2}-\d{2})\.(md|json)$")
_LEGACY_MILESTONE_DIRS = {
    "m22_closeout",
    "m23_closeout",
    "m25_alert",
    "m25_closeout",
    "m25_ops_batch",
    "m28_closeout",
    "m28_launch_hook",
    "m28_launch_templates",
    "m28_launch_wrapper",
    "m28_registration_helpers",
    "m28_rollout",
    "m28_scheduler_worker",
    "m28_startup_preflight",
}


@dataclass(frozen=True)
class ArchiveCandidate:
    rel_path: str
    reason: str
    category: str


def _safe_read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _iter_top_level(report_root: Path) -> List[Path]:
    if not report_root.exists():
        return []
    return sorted(list(report_root.iterdir()), key=lambda p: p.name.lower())


def _top_level_file_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for p in path.rglob("*") if p.is_file())


def _archive_target(candidate: ArchiveCandidate) -> str:
    name = Path(candidate.rel_path).name
    if candidate.category == "offhours_experiments":
        return str(Path("archive") / "experiments" / "offhours" / name)
    if candidate.category == "legacy_milestone_dir":
        return str(Path("archive") / "milestones" / name)
    if candidate.category == "legacy_daily_test":
        return str(Path("archive") / "legacy" / "daily_test")
    if candidate.category == "legacy_root_daily":
        return str(Path("archive") / "legacy" / "root_daily_reports" / name)
    return str(Path("archive") / "misc" / name)


def _detect_archive_candidates(report_root: Path) -> List[ArchiveCandidate]:
    out: List[ArchiveCandidate] = []
    for path in _iter_top_level(report_root):
        name = path.name
        if name in ("archive", "_catalog", "dev", "milestones"):
            continue
        if path.is_dir() and name.startswith(_OFFHOURS_PREFIX):
            out.append(
                ArchiveCandidate(
                    rel_path=name,
                    reason="one-off offhours experiment output; not a canonical daily operator report",
                    category="offhours_experiments",
                )
            )
            continue
        if path.is_dir() and name == "daily_test":
            out.append(
                ArchiveCandidate(
                    rel_path=name,
                    reason="test-only daily report output",
                    category="legacy_daily_test",
                )
            )
            continue
        if path.is_dir() and name in _LEGACY_MILESTONE_DIRS:
            out.append(
                ArchiveCandidate(
                    rel_path=name,
                    reason="legacy milestone report directory; keep archived instead of mixed with active operator reports",
                    category="legacy_milestone_dir",
                )
            )
            continue
        if path.is_file():
            m = _ROOT_DAILY_RE.match(name)
            if not m:
                continue
            day = m.group(1)
            ext = m.group(2)
            canonical = report_root / "daily" / day / f"daily_report.{ext}"
            if canonical.exists():
                out.append(
                    ArchiveCandidate(
                        rel_path=name,
                        reason=f"legacy root-level daily report duplicated by canonical reports/daily/{day}/daily_report.{ext}",
                        category="legacy_root_daily",
                    )
                )
    return out


def _detect_health_warnings(report_root: Path, event_log_path: Optional[Path]) -> List[Dict[str, Any]]:
    warnings: List[Dict[str, Any]] = []

    operator_paths = sorted((report_root / "daily").glob("*/operator_summary.json"))
    for path in operator_paths:
        obj = _safe_read_json(path)
        if not obj:
            continue
        inputs = obj.get("inputs") if isinstance(obj.get("inputs"), dict) else {}
        event_path_raw = str(inputs.get("event_log_path") or "").strip()
        if event_path_raw:
            event_path = Path(event_path_raw)
            if not event_path.is_absolute():
                event_path = Path.cwd() / event_path
            if not event_path.exists():
                warnings.append(
                    {
                        "severity": "warning",
                        "type": "operator_summary_input_path_missing",
                        "path": str(path),
                        "detail": f"operator summary references missing event log path: {event_path_raw}",
                    }
                )
        tas = obj.get("trading_activity_summary") if isinstance(obj.get("trading_activity_summary"), dict) else {}
        run_total = int(tas.get("run_total") or 0)
        day = str(obj.get("day") or "").strip()
        if run_total == 0 and day and event_log_path and event_log_path.exists():
            text = event_log_path.read_text(encoding="utf-8", errors="ignore")
            if day in text:
                warnings.append(
                    {
                        "severity": "warning",
                        "type": "operator_summary_zero_runs",
                        "path": str(path),
                        "detail": f"operator summary for {day} reports zero runs even though the event log contains that day",
                    }
                )

    story_dir = report_root / "dev" / "manual" / "decision_story"
    for path in sorted(story_dir.glob("decision_story_*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "No decision stories found." in text:
            warnings.append(
                {
                    "severity": "warning",
                    "type": "decision_story_empty",
                    "path": str(path),
                    "detail": "decision story report rendered zero stories",
                }
            )

    run_cards_dir = report_root / "dev" / "manual" / "run_cards"
    for path in sorted(run_cards_dir.glob("run_cards_*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "No run cards found." in text:
            warnings.append(
                {
                    "severity": "warning",
                    "type": "run_cards_empty",
                    "path": str(path),
                    "detail": "run card report rendered zero cards",
                }
            )

    return warnings


def build_report_inventory(report_root: Path, *, event_log_path: Optional[Path] = None) -> Dict[str, Any]:
    report_root = Path(report_root)
    top_entries = _iter_top_level(report_root)
    candidates = _detect_archive_candidates(report_root)
    warnings = _detect_health_warnings(report_root, event_log_path)

    top_level: List[Dict[str, Any]] = []
    archive_candidate_paths = {c.rel_path for c in candidates}
    for path in top_entries:
        top_level.append(
            {
                "name": path.name,
                "type": "dir" if path.is_dir() else "file",
                "file_count": _top_level_file_count(path),
                "archive_candidate": path.name in archive_candidate_paths,
            }
        )

    canonical_dirs = [
        name
        for name in (
            "daily",
            "metrics",
            "symbols",
            "reconciliation",
            "dev",
            "milestones",
        )
        if (report_root / name).exists()
    ]

    archive_dirs = [entry["name"] for entry in top_level if str(entry["name"]).startswith("archive")]

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_root": str(report_root),
        "top_level": top_level,
        "canonical_dirs": canonical_dirs,
        "archive_dirs": archive_dirs,
        "archive_candidates": [
            {
                "rel_path": c.rel_path,
                "reason": c.reason,
                "category": c.category,
                "archive_target": _archive_target(c),
            }
            for c in candidates
        ],
        "warnings": warnings,
        "summary": {
            "top_level_entry_total": len(top_level),
            "archive_candidate_total": len(candidates),
            "warning_total": len(warnings),
        },
    }


def render_report_inventory_markdown(inventory: Dict[str, Any]) -> str:
    summary = inventory.get("summary") if isinstance(inventory.get("summary"), dict) else {}
    lines: List[str] = []
    lines.append("# Report Inventory")
    lines.append("")
    lines.append(f"- generated_at_utc: `{inventory.get('generated_at_utc')}`")
    lines.append(f"- report_root: `{inventory.get('report_root')}`")
    lines.append(f"- top_level_entry_total: **{int(summary.get('top_level_entry_total') or 0)}**")
    lines.append(f"- archive_candidate_total: **{int(summary.get('archive_candidate_total') or 0)}**")
    lines.append(f"- warning_total: **{int(summary.get('warning_total') or 0)}**")
    lines.append("")
    lines.append("## Canonical Directories")
    lines.append("")
    canonical_dirs = inventory.get("canonical_dirs") if isinstance(inventory.get("canonical_dirs"), list) else []
    if canonical_dirs:
        for name in canonical_dirs:
            lines.append(f"- `reports/{name}`")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Archive Candidates")
    lines.append("")
    candidates = inventory.get("archive_candidates") if isinstance(inventory.get("archive_candidates"), list) else []
    if candidates:
        for item in candidates:
            lines.append(
                f"- `{item.get('rel_path')}` -> `{item.get('archive_target')}`: {item.get('reason')}"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    warnings = inventory.get("warnings") if isinstance(inventory.get("warnings"), list) else []
    if warnings:
        for item in warnings:
            lines.append(
                f"- `{item.get('type')}` `{item.get('path')}`: {item.get('detail')}"
            )
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Top Level Snapshot")
    lines.append("")
    for entry in inventory.get("top_level") if isinstance(inventory.get("top_level"), list) else []:
        lines.append(
            f"- `{entry.get('name')}` ({entry.get('type')}, files={int(entry.get('file_count') or 0)}, "
            f"archive_candidate={bool(entry.get('archive_candidate'))})"
        )
    lines.append("")
    return "\n".join(lines)


def apply_archive_candidates(report_root: Path, candidates: List[ArchiveCandidate]) -> List[Dict[str, Any]]:
    report_root = Path(report_root)
    moved: List[Dict[str, Any]] = []
    for candidate in candidates:
        src = report_root / candidate.rel_path
        if not src.exists():
            continue
        rel_target = Path(_archive_target(candidate))
        dst = report_root / rel_target
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            dst = dst.with_name(f"{dst.stem}_{stamp}{dst.suffix}")
        shutil.move(str(src), str(dst))
        moved.append(
            {
                "src": str(src),
                "dst": str(dst),
                "reason": candidate.reason,
                "category": candidate.category,
            }
        )
    return moved


def write_report_inventory(report_root: Path, inventory: Dict[str, Any]) -> Tuple[Path, Path]:
    catalog_dir = Path(report_root) / "dev" / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)
    day = _utc_today()
    js_path = catalog_dir / f"report_inventory_{day}.json"
    md_path = catalog_dir / f"report_inventory_{day}.md"
    latest_js_path = catalog_dir / "report_inventory_latest.json"
    latest_md_path = catalog_dir / "report_inventory_latest.md"
    payload = json.dumps(inventory, ensure_ascii=False, indent=2)
    markdown = render_report_inventory_markdown(inventory)
    js_path.write_text(payload, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    latest_js_path.write_text(payload, encoding="utf-8")
    latest_md_path.write_text(markdown, encoding="utf-8")
    return md_path, js_path
