from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


_CORE_TOP_LEVEL = {"events.jsonl", "intents.jsonl", "dev", "milestones"}
_DEV_LIVE_FILES = {"events_live.jsonl", "events_live_tune.jsonl"}
_DEV_SESSION_FILES = {
    "m13_live_loop_stdout.log",
    "m13_live_loop_stderr.log",
    "m31_mock_session_control.log",
    "m31_mock_session_stdout.log",
    "m31_mock_session_stderr.log",
    "mock_exam_day_session_stdout.log",
    "mock_exam_day_session_stderr.log",
}
_DEV_TESTING_FILES = {
    "pytest_events.jsonl",
    "events_cash_guard_smoke.jsonl",
    "events_ledger_smoke.jsonl",
}
_OFFHOURS_PREFIX = "offhours_"
_MILESTONE_FILE_TARGETS = {
    "m22_closeout_events.jsonl": Path("milestones") / "m22" / "closeout_events.jsonl",
    "m23_closeout_events.jsonl": Path("milestones") / "m23" / "closeout_events.jsonl",
    "m24_closeout_intents.jsonl": Path("milestones") / "m24" / "closeout_intents.jsonl",
    "m24_guard_precedence_intents.jsonl": Path("milestones") / "m24" / "guard_precedence_intents.jsonl",
    "m25_closeout_events.jsonl": Path("milestones") / "m25" / "closeout_events.jsonl",
    "m25_notify_events.jsonl": Path("milestones") / "m25" / "notify_events.jsonl",
    "m25_ops_batch_events.jsonl": Path("milestones") / "m25" / "ops_batch_events.jsonl",
    "m27_notify_query_events.jsonl": Path("milestones") / "m27" / "notify_query_events.jsonl",
}
_MILESTONE_DIR_TARGETS = {
    "m30_golive": Path("milestones") / "m30" / "golive",
    "m30_quality_gates": Path("milestones") / "m30" / "quality_gates",
}


@dataclass(frozen=True)
class LogMoveCandidate:
    rel_path: str
    target_rel_path: str
    category: str
    reason: str


def _iter_top_level(log_root: Path) -> List[Path]:
    if not log_root.exists():
        return []
    return sorted(list(log_root.iterdir()), key=lambda p: p.name.lower())


def _top_level_file_count(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return 1
    return sum(1 for p in path.rglob("*") if p.is_file())


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def detect_log_move_candidates(log_root: Path) -> List[LogMoveCandidate]:
    out: List[LogMoveCandidate] = []
    for path in _iter_top_level(log_root):
        name = path.name
        if name in _CORE_TOP_LEVEL:
            continue
        if path.is_file() and name.startswith(_OFFHOURS_PREFIX):
            out.append(
                LogMoveCandidate(
                    rel_path=name,
                    target_rel_path=str(Path("dev") / "analysis" / "offhours" / name),
                    category="dev_offhours",
                    reason="off-hours analysis log; keep under dev analysis instead of core runtime root",
                )
            )
            continue
        if path.is_file() and name in _DEV_LIVE_FILES:
            out.append(
                LogMoveCandidate(
                    rel_path=name,
                    target_rel_path=str(Path("dev") / "live" / name),
                    category="dev_live",
                    reason="live-session analysis log; keep under dev/live",
                )
            )
            continue
        if path.is_file() and name in _DEV_SESSION_FILES:
            out.append(
                LogMoveCandidate(
                    rel_path=name,
                    target_rel_path=str(Path("dev") / "session" / name),
                    category="dev_session",
                    reason="session stdout/stderr/control log; keep under dev/session",
                )
            )
            continue
        if path.is_file() and name in _DEV_TESTING_FILES:
            out.append(
                LogMoveCandidate(
                    rel_path=name,
                    target_rel_path=str(Path("dev") / "testing" / name),
                    category="dev_testing",
                    reason="test/smoke log; keep under dev/testing",
                )
            )
            continue
        if path.is_file() and name in _MILESTONE_FILE_TARGETS:
            out.append(
                LogMoveCandidate(
                    rel_path=name,
                    target_rel_path=str(_MILESTONE_FILE_TARGETS[name]),
                    category="milestone_file",
                    reason="milestone-specific log; keep under data/logs/milestones",
                )
            )
            continue
        if path.is_dir() and name in _MILESTONE_DIR_TARGETS:
            out.append(
                LogMoveCandidate(
                    rel_path=name,
                    target_rel_path=str(_MILESTONE_DIR_TARGETS[name]),
                    category="milestone_dir",
                    reason="milestone event-log directory; keep under data/logs/milestones",
                )
            )
            continue
    return out


def build_log_inventory(log_root: Path) -> Dict[str, Any]:
    log_root = Path(log_root)
    top_level = _iter_top_level(log_root)
    candidates = detect_log_move_candidates(log_root)
    candidate_paths = {c.rel_path for c in candidates}

    entries: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    for path in top_level:
        item = {
            "name": path.name,
            "type": "dir" if path.is_dir() else "file",
            "file_count": _top_level_file_count(path),
            "move_candidate": path.name in candidate_paths,
        }
        entries.append(item)
        if path.name not in _CORE_TOP_LEVEL and path.name not in candidate_paths:
            warnings.append(
                {
                    "severity": "warning",
                    "type": "unexpected_top_level_entry",
                    "path": str(log_root / path.name),
                    "detail": "top-level log entry is not in the canonical core/dev/milestones layout",
                }
            )

    return {
        "generated_at_utc": _utc_now_iso(),
        "log_root": str(log_root),
        "canonical_top_level": ["events.jsonl", "intents.jsonl", "dev", "milestones"],
        "top_level": entries,
        "move_candidates": [
            {
                "rel_path": c.rel_path,
                "target_rel_path": c.target_rel_path,
                "category": c.category,
                "reason": c.reason,
            }
            for c in candidates
        ],
        "warnings": warnings,
        "summary": {
            "top_level_entry_total": len(entries),
            "move_candidate_total": len(candidates),
            "warning_total": len(warnings),
        },
    }


def apply_log_move_candidates(log_root: Path, candidates: List[LogMoveCandidate]) -> List[Dict[str, str]]:
    log_root = Path(log_root)
    moved: List[Dict[str, str]] = []
    for candidate in candidates:
        src = log_root / candidate.rel_path
        dst = log_root / candidate.target_rel_path
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.is_dir():
                shutil.rmtree(dst)
            else:
                dst.unlink()
        shutil.move(str(src), str(dst))
        moved.append({"src": str(src), "dst": str(dst), "category": candidate.category})
    return moved


def write_log_inventory(log_root: Path, inventory: Dict[str, Any]) -> Tuple[Path, Path]:
    log_root = Path(log_root)
    catalog_dir = log_root / "dev" / "catalog"
    catalog_dir.mkdir(parents=True, exist_ok=True)

    js_path = catalog_dir / "log_inventory_latest.json"
    md_path = catalog_dir / "log_inventory_latest.md"
    js_path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# Log Inventory",
        "",
        f"- generated_at_utc: `{inventory.get('generated_at_utc')}`",
        f"- log_root: `{inventory.get('log_root')}`",
        f"- top_level_entry_total: **{int((inventory.get('summary') or {}).get('top_level_entry_total') or 0)}**",
        f"- move_candidate_total: **{int((inventory.get('summary') or {}).get('move_candidate_total') or 0)}**",
        f"- warning_total: **{int((inventory.get('summary') or {}).get('warning_total') or 0)}**",
        "",
        "## Canonical Top Level",
        "",
    ]
    for name in inventory.get("canonical_top_level") if isinstance(inventory.get("canonical_top_level"), list) else []:
        lines.append(f"- `{name}`")
    lines.append("")
    lines.append("## Top Level Entries")
    lines.append("")
    for item in inventory.get("top_level") if isinstance(inventory.get("top_level"), list) else []:
        lines.append(
            f"- `{item.get('name')}` type={item.get('type')} file_count={int(item.get('file_count') or 0)} "
            f"move_candidate={bool(item.get('move_candidate'))}"
        )
    lines.append("")
    lines.append("## Move Candidates")
    lines.append("")
    for item in inventory.get("move_candidates") if isinstance(inventory.get("move_candidates"), list) else []:
        lines.append(
            f"- `{item.get('rel_path')}` -> `{item.get('target_rel_path')}` "
            f"category={item.get('category')} reason={item.get('reason')}"
        )
    lines.append("")
    lines.append("## Warnings")
    lines.append("")
    warnings = inventory.get("warnings") if isinstance(inventory.get("warnings"), list) else []
    if warnings:
        for item in warnings:
            lines.append(f"- `{item.get('type')}` path=`{item.get('path')}` detail={item.get('detail')}")
    else:
        lines.append("- none")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path, js_path
