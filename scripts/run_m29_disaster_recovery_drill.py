from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_log_archive_integrity import main as archive_integrity_main
from scripts.run_m26_replay_runner import main as replay_main


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_jsonl(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def _run_json(main_fn, argv: List[str]) -> Tuple[int, Dict[str, Any]]:  # type: ignore[no-untyped-def]
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main_fn(argv)
    out = buf.getvalue().strip()
    if not out:
        return int(rc), {}
    try:
        return int(rc), json.loads(out)
    except Exception:
        return int(rc), {}


def _seed_working_dataset(root: Path, *, day: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _write_text(
        root / "manifest.json",
        json.dumps(
            {
                "schema_version": "m26.dataset_manifest.v1",
                "dataset_id": "m29-dr-drill-v1",
                "components": {"execution": ["execution/intents.jsonl", "execution/order_status.jsonl", "execution/fills.jsonl"]},
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    _write_jsonl(
        root / "execution" / "intents.jsonl",
        [
            {"ts": f"{day}T00:01:00+00:00", "intent_id": "dr-intent-1", "symbol": "005930", "action": "BUY", "qty": 1},
            {"ts": f"{day}T00:02:00+00:00", "intent_id": "dr-intent-2", "symbol": "005930", "action": "SELL", "qty": 1},
        ],
    )
    _write_jsonl(
        root / "execution" / "order_status.jsonl",
        [
            {"ts": f"{day}T00:01:05+00:00", "intent_id": "dr-intent-1", "status": "filled"},
            {"ts": f"{day}T00:02:05+00:00", "intent_id": "dr-intent-2", "status": "filled"},
        ],
    )
    _write_jsonl(
        root / "execution" / "fills.jsonl",
        [
            {"ts": f"{day}T00:01:05+00:00", "intent_id": "dr-intent-1", "fill_price": 100, "fill_qty": 1},
            {"ts": f"{day}T00:02:05+00:00", "intent_id": "dr-intent-2", "fill_price": 110, "fill_qty": 1},
        ],
    )


def _build_archive_manifest(day_dir: Path, *, day: str) -> Path:
    files: List[Dict[str, Any]] = []
    for fp in sorted(day_dir.rglob("*")):
        if not fp.is_file():
            continue
        rel = fp.relative_to(day_dir).as_posix()
        if rel == "manifest.json":
            continue
        files.append(
            {
                "name": rel,
                "sha256": _sha256_file(fp),
                "bytes": int(fp.stat().st_size),
                "line_count": int(_line_count(fp)),
            }
        )
    manifest_path = day_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "archive_manifest.v1",
                "day": day,
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _copytree_replace(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def _replay_metrics(obj: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "replayed_intent_total": int(obj.get("replayed_intent_total") or 0),
        "executed_intent_total": int(obj.get("executed_intent_total") or 0),
        "blocked_intent_total": int(obj.get("blocked_intent_total") or 0),
        "pending_intent_total": int(obj.get("pending_intent_total") or 0),
        "fill_qty_total": int(obj.get("fill_qty_total") or 0),
        "fill_notional_total": float(obj.get("fill_notional_total") or 0.0),
    }


def _replay_parity_ok(base: Dict[str, Any], restored: Dict[str, Any]) -> Tuple[bool, List[str]]:
    failures: List[str] = []
    for key in (
        "replayed_intent_total",
        "executed_intent_total",
        "blocked_intent_total",
        "pending_intent_total",
        "fill_qty_total",
    ):
        if int(base.get(key) or 0) != int(restored.get(key) or 0):
            failures.append(f"parity_mismatch:{key}")
    b_notional = float(base.get("fill_notional_total") or 0.0)
    r_notional = float(restored.get("fill_notional_total") or 0.0)
    if abs(b_notional - r_notional) > 1e-9:
        failures.append("parity_mismatch:fill_notional_total")
    return len(failures) == 0, failures


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M29-8 disaster recovery drill (restore + replay validation).")
    p.add_argument("--working-dataset-root", default="data/recovery/m29_working_dataset")
    p.add_argument("--archive-dir", default="data/logs/m29_dr_archive")
    p.add_argument("--restored-dataset-root", default="data/recovery/m29_restored_dataset")
    p.add_argument("--report-dir", default="reports/m29_disaster_recovery")
    p.add_argument("--day", default="2026-02-21")
    p.add_argument("--inject-fail", action="store_true")
    p.add_argument("--no-clear", action="store_true")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    day = str(args.day or "2026-02-21").strip()
    working_root = Path(str(args.working_dataset_root).strip())
    archive_dir = Path(str(args.archive_dir).strip())
    restored_root = Path(str(args.restored_dataset_root).strip())
    report_dir = Path(str(args.report_dir).strip())
    inject_fail = bool(args.inject_fail)

    if not bool(args.no_clear):
        for p in (working_root, restored_root, report_dir):
            if p.exists():
                shutil.rmtree(p, ignore_errors=True)
        day_dir = archive_dir / day
        if day_dir.exists():
            shutil.rmtree(day_dir, ignore_errors=True)

    _seed_working_dataset(working_root, day=day)
    baseline_rc, baseline_obj = _run_json(replay_main, ["--dataset-root", str(working_root), "--day", day, "--json"])
    baseline_metrics = _replay_metrics(baseline_obj if isinstance(baseline_obj, dict) else {})

    day_dir = archive_dir / day
    snapshot_src = working_root
    snapshot_dst = day_dir / "dataset"
    _copytree_replace(snapshot_src, snapshot_dst)
    _build_archive_manifest(day_dir, day=day)

    if inject_fail:
        # Tamper archived snapshot after manifest generation to force integrity and parity failures.
        with (snapshot_dst / "execution" / "fills.jsonl").open("a", encoding="utf-8", newline="\n") as f:
            f.write(
                json.dumps(
                    {"ts": f"{day}T00:03:05+00:00", "intent_id": "dr-intent-3", "fill_price": 120, "fill_qty": 1},
                    ensure_ascii=False,
                )
                + "\n"
            )

    integrity_rc, integrity_obj = _run_json(
        archive_integrity_main,
        [
            "--archive-dir",
            str(archive_dir),
            "--report-dir",
            str(report_dir / "archive_integrity"),
            "--day",
            day,
            "--retention-days",
            "90",
            "--json",
        ],
    )

    # Simulate working storage loss, then restore from archive snapshot.
    if working_root.exists():
        shutil.rmtree(working_root, ignore_errors=True)
    restore_src = day_dir / "dataset"
    restore_copy_ok = False
    if restore_src.exists():
        _copytree_replace(restore_src, restored_root)
        restore_copy_ok = restored_root.exists()

    restored_rc, restored_obj = _run_json(
        replay_main,
        ["--dataset-root", str(restored_root), "--day", day, "--json"],
    )
    restored_metrics = _replay_metrics(restored_obj if isinstance(restored_obj, dict) else {})
    parity_ok, parity_failures = _replay_parity_ok(baseline_metrics, restored_metrics)

    failures: List[str] = []
    if baseline_rc != 0:
        failures.append("baseline_replay rc != 0")
    if not bool(baseline_obj.get("ok")):
        failures.append("baseline_replay ok != true")
    if integrity_rc != 0:
        failures.append("archive_integrity rc != 0")
    if not bool(integrity_obj.get("ok")):
        failures.append("archive_integrity ok != true")
    if not restore_copy_ok:
        failures.append("restore_copy_ok != true")
    if restored_rc != 0:
        failures.append("restored_replay rc != 0")
    if not bool(restored_obj.get("ok")):
        failures.append("restored_replay ok != true")
    if not parity_ok:
        failures.extend(parity_failures)

    expected_ok = not inject_fail
    if inject_fail:
        if len(failures) < 1:
            failures.append("inject_fail expected at least one validation failure")
        overall_ok = False
    else:
        overall_ok = len(failures) == 0

    out = {
        "ok": overall_ok,
        "day": day,
        "inject_fail": inject_fail,
        "working_dataset_root": str(working_root),
        "archive_day_dir": str(day_dir),
        "restored_dataset_root": str(restored_root),
        "report_dir": str(report_dir),
        "baseline_replay": {
            "rc": int(baseline_rc),
            "ok": bool(baseline_obj.get("ok")) if isinstance(baseline_obj, dict) else False,
            **baseline_metrics,
        },
        "archive_integrity": {
            "rc": int(integrity_rc),
            "ok": bool(integrity_obj.get("ok")) if isinstance(integrity_obj, dict) else False,
            "report_json_path": str(integrity_obj.get("report_json_path") or "") if isinstance(integrity_obj, dict) else "",
            "report_md_path": str(integrity_obj.get("report_md_path") or "") if isinstance(integrity_obj, dict) else "",
            "hash_mismatch_total": int(integrity_obj.get("hash_mismatch_total") or 0) if isinstance(integrity_obj, dict) else 0,
        },
        "restore": {
            "copy_ok": bool(restore_copy_ok),
            "source": str(restore_src),
            "target": str(restored_root),
        },
        "restored_replay": {
            "rc": int(restored_rc),
            "ok": bool(restored_obj.get("ok")) if isinstance(restored_obj, dict) else False,
            **restored_metrics,
        },
        "parity": {
            "ok": bool(parity_ok),
            "failures": parity_failures,
        },
        "failures": failures,
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} day={day} baseline_replayed={out['baseline_replay']['replayed_intent_total']} "
            f"restored_replayed={out['restored_replay']['replayed_intent_total']} "
            f"integrity_hash_mismatch={out['archive_integrity']['hash_mismatch_total']} "
            f"parity_ok={out['parity']['ok']} failure_total={len(failures)}"
        )
        for msg in failures:
            print(msg)

    return 0 if overall_ok else 3


if __name__ == "__main__":
    raise SystemExit(main())
