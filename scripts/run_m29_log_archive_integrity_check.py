from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_log_archive_integrity import main as integrity_main


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _line_count(path: Path) -> int:
    n = 0
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for _ in f:
            n += 1
    return n


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _run_json(argv: List[str]) -> Tuple[int, Dict[str, Any]]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = integrity_main(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M29-6 log archive integrity closeout check.")
    p.add_argument("--archive-dir", default="data/logs/m29_archive")
    p.add_argument("--report-dir", default="reports/m29_archive")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--retention-days", type=int, default=30)
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def _seed_archive(archive_dir: Path, *, day: str, retention_days: int, inject_fail: bool) -> None:
    day_dir = archive_dir / day
    events_path = day_dir / "events.jsonl"

    rows = [
        {
            "ts": f"{day}T00:00:00+00:00",
            "run_id": "seed_1",
            "stage": "decision",
            "event": "trace",
            "payload": {"decision_packet": {"intent": {"action": "BUY", "symbol": "005930", "qty": 1}}},
        },
        {
            "ts": f"{day}T00:00:01+00:00",
            "run_id": "seed_1",
            "stage": "execute_from_packet",
            "event": "execution",
            "payload": {"allowed": True},
        },
    ]
    _write_jsonl(events_path, rows)

    manifest = {
        "schema_version": "archive_manifest.v1",
        "day": day,
        "created_at": f"{day}T01:00:00+00:00",
        "files": [
            {
                "name": "events.jsonl",
                "sha256": _sha256_file(events_path),
                "bytes": int(events_path.stat().st_size),
                "line_count": _line_count(events_path),
            }
        ],
    }
    manifest_path = day_dir / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if not inject_fail:
        return

    # 1) Tamper archived file after manifest generation -> hash/size/line mismatch.
    with events_path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"ts": f"{day}T00:00:09+00:00", "run_id": "tamper", "stage": "tamper", "event": "x"}) + "\n")

    # 2) Add stale archive directory older than retention window.
    try:
        base = datetime.strptime(day, "%Y-%m-%d").date()
    except Exception:
        base = datetime.utcnow().date()
    stale_day = (base - timedelta(days=max(31, retention_days + 1))).strftime("%Y-%m-%d")
    stale_dir = archive_dir / stale_day
    stale_dir.mkdir(parents=True, exist_ok=True)
    (stale_dir / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (stale_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": "archive_manifest.v1",
                "day": stale_day,
                "created_at": f"{stale_day}T01:00:00+00:00",
                "files": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    archive_dir = Path(str(args.archive_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    day = str(args.day or "2026-02-21").strip()
    retention_days = max(0, int(args.retention_days or 0))
    inject_fail = bool(args.inject_fail)

    _seed_archive(archive_dir, day=day, retention_days=retention_days, inject_fail=inject_fail)
    rc, obj = _run_json(
        [
            "--archive-dir",
            str(archive_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--retention-days",
            str(retention_days),
            "--json",
        ]
    )

    failures: List[str] = []
    expected_ok = not inject_fail
    if expected_ok:
        if rc != 0:
            failures.append("integrity_check rc != 0")
        if not bool(obj.get("ok")):
            failures.append("integrity_check ok != true")
        if int(obj.get("verified_total") or 0) < 1:
            failures.append("verified_total < 1")
        if int(obj.get("hash_mismatch_total") or 0) > 0:
            failures.append("hash_mismatch_total > 0")
        if int(obj.get("stale_archive_total") or 0) > 0:
            failures.append("stale_archive_total > 0")
    else:
        if rc == 0:
            failures.append("inject_fail expected rc != 0")
        if bool(obj.get("ok")):
            failures.append("inject_fail expected ok == false")
        anomaly_total = (
            int(obj.get("hash_mismatch_total") or 0)
            + int(obj.get("bytes_mismatch_total") or 0)
            + int(obj.get("line_count_mismatch_total") or 0)
            + int(obj.get("stale_archive_total") or 0)
        )
        if anomaly_total < 1:
            failures.append("inject_fail expected anomaly_total >= 1")

    overall_ok = len(failures) == 0 and expected_ok
    if inject_fail and len(failures) == 0:
        failures.append("inject_fail scenario: expected non-zero closeout result")

    out = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "archive_dir": str(archive_dir),
        "report_dir": str(report_dir),
        "integrity": {
            "rc": int(rc),
            "ok": bool(obj.get("ok")) if isinstance(obj, dict) else False,
            "file_total": int(obj.get("file_total") or 0) if isinstance(obj, dict) else 0,
            "verified_total": int(obj.get("verified_total") or 0) if isinstance(obj, dict) else 0,
            "hash_mismatch_total": int(obj.get("hash_mismatch_total") or 0) if isinstance(obj, dict) else 0,
            "bytes_mismatch_total": int(obj.get("bytes_mismatch_total") or 0) if isinstance(obj, dict) else 0,
            "line_count_mismatch_total": int(obj.get("line_count_mismatch_total") or 0) if isinstance(obj, dict) else 0,
            "stale_archive_total": int(obj.get("stale_archive_total") or 0) if isinstance(obj, dict) else 0,
            "report_json_path": str(obj.get("report_json_path") or "") if isinstance(obj, dict) else "",
            "report_md_path": str(obj.get("report_md_path") or "") if isinstance(obj, dict) else "",
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} verified_total={out['integrity']['verified_total']} "
            f"hash_mismatch_total={out['integrity']['hash_mismatch_total']} "
            f"stale_archive_total={out['integrity']['stale_archive_total']}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
