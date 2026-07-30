from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.reporting.evaluation.artifact_inventory import is_synthetic_evaluation_row


_KRX_SYMBOL_RE = re.compile(r"^\d{6}$")
_BASELINE_RUN_RE = re.compile(
    r"^baseline_(?:samsung_hynix|btc_woori_tech)_[^_]+_([^_]+)_\d+$"
)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    temp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _invalid_symbol_in_value(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in {
                "symbol",
                "ticker",
                "selected_symbol",
                "top1_symbol",
                "candidate_symbol",
            }:
                text = str(child or "").strip()
                if text and not _KRX_SYMBOL_RE.fullmatch(text):
                    return True
            elif isinstance(child, (Mapping, list)) and _invalid_symbol_in_value(
                child
            ):
                return True
    elif isinstance(value, list):
        return any(_invalid_symbol_in_value(child) for child in value)
    return False


def _test_event(row: Mapping[str, Any]) -> bool:
    run_id = str(row.get("run_id") or "").strip()
    lowered = run_id.lower()
    if any(marker in lowered for marker in ("fixture", "synthetic", "pytest")):
        return True
    baseline_match = _BASELINE_RUN_RE.match(run_id)
    if baseline_match and not _KRX_SYMBOL_RE.fullmatch(baseline_match.group(1)):
        return True
    return _invalid_symbol_in_value(row)


def _quarantine_root(root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return (
        root
        / "data"
        / "logs"
        / "dev"
        / "testing"
        / "quarantine"
        / stamp
    )


def clean_q9(root: Path, quarantine: Path, *, apply: bool) -> dict[str, int]:
    file_count = 0
    removed_count = 0
    for path in sorted(
        (root / "reports" / "operator_summary" / "daily").glob(
            "*/q9_decision_windows.json"
        )
    ):
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        windows = [
            dict(row)
            for row in payload.get("windows") or []
            if isinstance(row, Mapping)
        ]
        removed = [row for row in windows if is_synthetic_evaluation_row(row)]
        if not removed:
            continue
        kept = [
            row for row in windows if not is_synthetic_evaluation_row(row)
        ]
        file_count += 1
        removed_count += len(removed)
        if not apply:
            continue
        relative = path.relative_to(root)
        quarantine_path = quarantine / relative
        quarantine_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(
            quarantine_path,
            {
                "source_path": str(path),
                "removed_windows": removed,
            },
        )
        payload["windows"] = kept
        payload["window_count"] = len(kept)
        payload["test_contamination_removed_count"] = len(removed)
        _atomic_write_json(path, payload)
    return {"files": file_count, "removed_windows": removed_count}


def clean_shadow_files(
    root: Path,
    quarantine: Path,
    *,
    apply: bool,
) -> dict[str, int]:
    files = 0
    for path in sorted(
        (root / "data" / "logs" / "quant_shadow_candidates").glob("**/*.json")
    ):
        if path.name == "latest.json":
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not _invalid_symbol_in_value(payload):
            continue
        files += 1
        if not apply:
            continue
        target = quarantine / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        path.replace(target)
    return {"quarantined_files": files}


def clean_event_log(
    root: Path,
    quarantine: Path,
    *,
    apply: bool,
) -> dict[str, int]:
    path = root / "data" / "logs" / "events.jsonl"
    if not path.exists():
        return {"removed_events": 0}
    removed = 0
    if not apply:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                removed += int(isinstance(row, Mapping) and _test_event(row))
        return {"removed_events": removed}

    temp = path.with_name(f"{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    quarantine_path = quarantine / path.relative_to(root)
    quarantine_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        path.open("r", encoding="utf-8") as source,
        temp.open("w", encoding="utf-8", newline="\n") as target,
        quarantine_path.open("w", encoding="utf-8", newline="\n") as rejected,
    ):
        for line in source:
            try:
                row = json.loads(line)
            except Exception:
                target.write(line)
                continue
            if isinstance(row, Mapping) and _test_event(row):
                rejected.write(line)
                removed += 1
            else:
                target.write(line)
    temp.replace(path)
    return {"removed_events": removed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    quarantine = _quarantine_root(root)
    result = {
        "schema_version": "evaluation_test_contamination_cleanup.v1",
        "applied": bool(args.apply),
        "root": str(root),
        "quarantine": str(quarantine) if args.apply else "",
        "q9": clean_q9(root, quarantine, apply=args.apply),
        "shadow": clean_shadow_files(root, quarantine, apply=args.apply),
        "events": clean_event_log(root, quarantine, apply=args.apply),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
