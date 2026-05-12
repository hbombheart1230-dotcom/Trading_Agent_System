from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)
LLM_REPORT_CATEGORIES = ("trade_executed", "no_trade", "manual_or_test")
EXECUTED_ACTIONS = {"BUY", "SELL"}
NON_EXECUTED_STATUSES = {
    "",
    "NOOP",
    "BLOCKED",
    "SKIPPED",
    "REJECTED",
    "FAILED",
    "ERROR",
    "PENDING",
}


def read_json_dict(path: Path) -> Dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return obj if isinstance(obj, dict) else None


def is_trade_executed(executor: Dict[str, Any]) -> bool:
    action = str(executor.get("action") or executor.get("final_action") or "").upper()
    if action not in EXECUTED_ACTIONS:
        return False

    if executor.get("execution_ok") is True:
        return True
    if executor.get("executed") is True:
        return True

    status = str(
        executor.get("final_execution_status")
        or executor.get("execution_status")
        or executor.get("status")
        or ""
    ).upper()
    if status and status not in NON_EXECUTED_STATUSES:
        return True

    return False


def classify_llm_run(reports_root: Path, day: str, run_id: str) -> Tuple[str, str]:
    run_id = str(run_id or "").strip()
    if not RUN_ID_RE.match(run_id):
        return "manual_or_test", "non_canonical_run_id"

    canonical_dir = Path(reports_root) / "canonical" / str(day or "").strip() / run_id
    executor = read_json_dict(canonical_dir / "executor.json")
    if executor is not None:
        if is_trade_executed(executor):
            return "trade_executed", "canonical_executor_executed"
        return "no_trade", "canonical_executor_no_trade"

    if canonical_dir.exists():
        return "no_trade", "canonical_without_executor"
    return "manual_or_test", "missing_canonical_run"


def find_llm_run_dir(reports_root: Path, day: str, run_id: str) -> Path:
    llm_day = Path(reports_root) / "llm" / str(day or "").strip()
    run_id = str(run_id or "").strip()
    root_run = llm_day / run_id
    if root_run.exists():
        return root_run
    for category in LLM_REPORT_CATEGORIES:
        candidate = llm_day / category / run_id
        if candidate.exists():
            return candidate
    return root_run


def rewrite_llm_artifact_refs(run_dir: Path, day: str, category: str) -> int:
    run_id = run_dir.name
    replacements = {
        f"reports\\llm\\{day}\\{run_id}\\": f"reports\\llm\\{day}\\{category}\\{run_id}\\",
        f"reports/llm/{day}/{run_id}/": f"reports/llm/{day}/{category}/{run_id}/",
        f"\\llm\\{day}\\{run_id}\\": f"\\llm\\{day}\\{category}\\{run_id}\\",
        f"/llm/{day}/{run_id}/": f"/llm/{day}/{category}/{run_id}/",
    }

    def rewrite_text(value: str) -> str:
        updated = value
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        return updated

    def rewrite_obj(value: Any) -> Any:
        if isinstance(value, str):
            return rewrite_text(value)
        if isinstance(value, list):
            return [rewrite_obj(item) for item in value]
        if isinstance(value, dict):
            return {key: rewrite_obj(item) for key, item in value.items()}
        return value

    changed = 0
    for path in run_dir.rglob("*.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            updated = rewrite_text(text)
            if updated != text:
                path.write_text(updated, encoding="utf-8")
                changed += 1
            continue
        updated_obj = rewrite_obj(obj)
        if updated_obj != obj:
            path.write_text(json.dumps(updated_obj, ensure_ascii=False, indent=2), encoding="utf-8")
            changed += 1
    return changed


def organize_llm_run(
    reports_root: Path,
    *,
    day: str,
    run_id: str,
    dry_run: bool = False,
    update_day_index: bool = False,
) -> Dict[str, Any]:
    reports_root = Path(reports_root)
    day = str(day or "").strip()
    run_id = str(run_id or "").strip()
    category, reason = classify_llm_run(reports_root, day, run_id)
    source = find_llm_run_dir(reports_root, day, run_id)
    target = reports_root / "llm" / day / category / run_id
    row: Dict[str, Any] = {
        "run_id": run_id,
        "category": category,
        "reason": reason,
        "source": str(source),
        "target": str(target),
    }

    def finalize(out: Dict[str, Any]) -> Dict[str, Any]:
        if update_day_index and not dry_run:
            refresh_classification_index(reports_root, day=day)
        return out

    if not source.exists():
        row["status"] = "missing_llm_run_dir"
        return finalize(row)
    if source.resolve() == target.resolve():
        row["status"] = "already_classified"
        if not dry_run:
            row["rewritten_ref_files"] = rewrite_llm_artifact_refs(target, day, category)
        return finalize(row)
    if target.exists():
        row["status"] = "target_exists"
        if not dry_run:
            row["rewritten_ref_files"] = rewrite_llm_artifact_refs(target, day, category)
        return finalize(row)
    if dry_run:
        row["status"] = "dry_run"
        return finalize(row)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    row["status"] = "moved"
    row["rewritten_ref_files"] = rewrite_llm_artifact_refs(target, day, category)
    return finalize(row)


def write_classification_index(day_dir: Path, day: str, rows: List[Dict[str, Any]]) -> None:
    index_path = day_dir / "_classification_index.json"
    index = {
        "date": day,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "categories": list(LLM_REPORT_CATEGORIES),
        "rows": rows,
    }
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    counts: Dict[str, int] = {}
    for row in rows:
        key = str(row.get("category") or row.get("status") or "unknown")
        counts[key] = counts.get(key, 0) + 1

    lines = [
        f"# LLM report classification - {day}",
        "",
        "Folders are grouped by the canonical executor result for the same run_id.",
        "",
        "## Counts",
        "",
    ]
    for key in sorted(counts):
        lines.append(f"- {key}: {counts[key]}")
    lines.extend(
        [
            "",
            "## Rules",
            "",
            "- trade_executed: canonical executor action is BUY/SELL and execution is marked successful.",
            "- no_trade: canonical run exists but executor did not complete a BUY/SELL.",
            "- manual_or_test: non-canonical or synthetic run folder, or no matching canonical run exists.",
            "",
        ]
    )
    (day_dir / "README.md").write_text("\n".join(lines), encoding="utf-8")


def refresh_classification_index(reports_root: Path, *, day: str) -> List[Dict[str, Any]]:
    reports_root = Path(reports_root)
    day = str(day or "").strip()
    day_dir = reports_root / "llm" / day
    rows: List[Dict[str, Any]] = []
    for category in LLM_REPORT_CATEGORIES:
        category_dir = day_dir / category
        if not category_dir.exists():
            continue
        for run_dir in sorted([p for p in category_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
            rows.append(
                {
                    "run_id": run_dir.name,
                    "category": category,
                    "reason": "classified_folder_scan",
                    "status": "classified",
                    "path": str(run_dir),
                }
            )
    if day_dir.exists():
        write_classification_index(day_dir, day, rows)
    return rows


def organize_llm_day(
    reports_root: Path,
    *,
    day: str,
    active_grace_sec: int = 180,
    dry_run: bool = False,
) -> List[Dict[str, Any]]:
    reports_root = Path(reports_root)
    day = str(day or "").strip()
    day_dir = reports_root / "llm" / day
    if not day_dir.exists():
        raise FileNotFoundError(f"LLM report date folder not found: {day_dir}")

    if not dry_run:
        for category in LLM_REPORT_CATEGORIES:
            (day_dir / category).mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    if not dry_run:
        for category in LLM_REPORT_CATEGORIES:
            category_dir = day_dir / category
            if not category_dir.exists():
                continue
            for existing in sorted([p for p in category_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
                changed_refs = rewrite_llm_artifact_refs(existing, day, category)
                rows.append(
                    {
                        "run_id": existing.name,
                        "category": category,
                        "reason": "already_classified",
                        "status": "already_classified",
                        "path": str(existing),
                        "rewritten_ref_files": changed_refs,
                    }
                )

    now_ts = datetime.now().timestamp()
    for run_dir in sorted([p for p in day_dir.iterdir() if p.is_dir()], key=lambda p: p.name):
        if run_dir.name in LLM_REPORT_CATEGORIES:
            continue
        age_sec = now_ts - run_dir.stat().st_mtime
        if active_grace_sec > 0 and age_sec < active_grace_sec:
            rows.append(
                {
                    "run_id": run_dir.name,
                    "status": "skipped_active_recent",
                    "age_sec": round(age_sec, 1),
                    "path": str(run_dir),
                }
            )
            continue
        rows.append(organize_llm_run(reports_root, day=day, run_id=run_dir.name, dry_run=dry_run))

    if not dry_run:
        write_classification_index(day_dir, day, rows)
    return rows
