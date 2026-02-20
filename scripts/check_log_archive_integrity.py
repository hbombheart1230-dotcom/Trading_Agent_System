from __future__ import annotations

import argparse
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def _load_manifest(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(obj, dict):
        return {}
    return obj


def _parse_day(value: str) -> Optional[date]:
    s = str(value or "").strip()
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except Exception:
        return None


def _markdown(out: Dict[str, Any]) -> str:
    lines = [
        f"# Log Archive Integrity ({out.get('day')})",
        "",
        f"- ok: **{bool(out.get('ok'))}**",
        f"- archive_dir: `{out.get('archive_dir')}`",
        f"- manifest_path: `{out.get('manifest_path')}`",
        f"- file_total: **{int(out.get('file_total') or 0)}**",
        f"- verified_total: **{int(out.get('verified_total') or 0)}**",
        "",
        "## Integrity Totals",
        "",
        f"- missing_file_total: {int(out.get('missing_file_total') or 0)}",
        f"- hash_mismatch_total: {int(out.get('hash_mismatch_total') or 0)}",
        f"- bytes_mismatch_total: {int(out.get('bytes_mismatch_total') or 0)}",
        f"- line_count_mismatch_total: {int(out.get('line_count_mismatch_total') or 0)}",
        "",
        "## Retention",
        "",
        f"- retention_days: {int(out.get('retention_days') or 0)}",
        f"- stale_archive_total: {int(out.get('stale_archive_total') or 0)}",
    ]
    stale = out.get("stale_archive_days") if isinstance(out.get("stale_archive_days"), list) else []
    if stale:
        lines.append(f"- stale_archive_days: {', '.join(str(x) for x in stale)}")
    else:
        lines.append("- stale_archive_days: (none)")
    lines += ["", "## Failures", ""]
    failures = out.get("failures") if isinstance(out.get("failures"), list) else []
    if failures:
        for msg in failures:
            lines.append(f"- {msg}")
    else:
        lines.append("- (none)")
    lines.append("")
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Check archive manifest/hash integrity and retention policy.")
    p.add_argument("--archive-dir", default="data/logs/archive")
    p.add_argument("--report-dir", default="reports/archive_integrity")
    p.add_argument("--day", default=None)
    p.add_argument("--retention-days", type=int, default=30)
    p.add_argument("--allow-stale", action="store_true", help="Do not fail on stale archive days.")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    archive_dir = Path(str(args.archive_dir).strip())
    report_dir = Path(str(args.report_dir).strip())
    report_dir.mkdir(parents=True, exist_ok=True)

    day = str(args.day or datetime.now(timezone.utc).strftime("%Y-%m-%d")).strip()
    day_dir = archive_dir / day
    manifest_path = day_dir / "manifest.json"
    manifest = _load_manifest(manifest_path)

    failures: List[str] = []
    file_total = 0
    verified_total = 0
    missing_file_total = 0
    hash_mismatch_total = 0
    bytes_mismatch_total = 0
    line_count_mismatch_total = 0

    if not day_dir.exists():
        failures.append(f"archive_day_dir missing: {day_dir}")

    if not manifest:
        failures.append("manifest missing_or_invalid")

    files = manifest.get("files") if isinstance(manifest.get("files"), list) else []
    file_total = int(len(files))
    if file_total < 1:
        failures.append("manifest.files empty")

    for rec in files:
        if not isinstance(rec, dict):
            continue
        name = str(rec.get("name") or "").strip()
        if not name:
            continue
        expected_hash = str(rec.get("sha256") or "").strip().lower()
        expected_bytes = int(rec.get("bytes") or 0)
        expected_lines = int(rec.get("line_count") or 0)
        fp = day_dir / name
        if not fp.exists():
            missing_file_total += 1
            failures.append(f"missing_file:{name}")
            continue
        actual_hash = _sha256_file(fp)
        if expected_hash and actual_hash != expected_hash:
            hash_mismatch_total += 1
            failures.append(f"hash_mismatch:{name}")
        actual_bytes = int(fp.stat().st_size)
        if expected_bytes > 0 and actual_bytes != expected_bytes:
            bytes_mismatch_total += 1
            failures.append(f"bytes_mismatch:{name}")
        actual_lines = _line_count(fp)
        if expected_lines > 0 and actual_lines != expected_lines:
            line_count_mismatch_total += 1
            failures.append(f"line_count_mismatch:{name}")
        if (
            (not expected_hash or actual_hash == expected_hash)
            and (expected_bytes <= 0 or actual_bytes == expected_bytes)
            and (expected_lines <= 0 or actual_lines == expected_lines)
        ):
            verified_total += 1

    stale_archive_days: List[str] = []
    target_day = _parse_day(day)
    retention_days = max(0, int(args.retention_days or 0))
    if archive_dir.exists() and target_day is not None and retention_days > 0:
        cutoff = target_day - timedelta(days=retention_days)
        for child in archive_dir.iterdir():
            if not child.is_dir():
                continue
            d = _parse_day(child.name)
            if d is None:
                continue
            if d < cutoff:
                stale_archive_days.append(d.strftime("%Y-%m-%d"))
    stale_archive_days = sorted(stale_archive_days)
    stale_archive_total = int(len(stale_archive_days))
    if stale_archive_total > 0 and not bool(args.allow_stale):
        failures.append(f"stale_archive_total > 0 ({stale_archive_total})")

    out: Dict[str, Any] = {
        "ok": len(failures) == 0,
        "day": day,
        "archive_dir": str(archive_dir),
        "manifest_path": str(manifest_path),
        "retention_days": retention_days,
        "file_total": int(file_total),
        "verified_total": int(verified_total),
        "missing_file_total": int(missing_file_total),
        "hash_mismatch_total": int(hash_mismatch_total),
        "bytes_mismatch_total": int(bytes_mismatch_total),
        "line_count_mismatch_total": int(line_count_mismatch_total),
        "stale_archive_total": stale_archive_total,
        "stale_archive_days": stale_archive_days[:20],
        "failures": failures,
    }

    js_path = report_dir / f"log_archive_integrity_{day}.json"
    md_path = report_dir / f"log_archive_integrity_{day}.md"
    out["report_json_path"] = str(js_path)
    out["report_md_path"] = str(md_path)
    js_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_markdown(out), encoding="utf-8")

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} file_total={out['file_total']} verified_total={out['verified_total']} "
            f"stale_archive_total={out['stale_archive_total']} failure_total={len(failures)}"
        )
        for msg in failures:
            print(msg)

    return 0 if len(failures) == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
