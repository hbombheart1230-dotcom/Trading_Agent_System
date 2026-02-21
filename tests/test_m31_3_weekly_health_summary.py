from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m31_weekly_health_summary import main as weekly_main


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    path.write_text(body, encoding="utf-8")


def test_m31_3_weekly_health_summary_passes_default(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    policy_dir = tmp_path / "policy"
    signoff_dir = tmp_path / "signoff"
    report_dir = tmp_path / "reports"

    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-16T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "start",
                "payload": {},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-16T01:00:05+00:00",
                "stage": "execute_from_packet",
                "event": "end",
                "payload": {"ok": True},
            },
            {
                "run_id": "r2",
                "ts": "2026-02-18T02:00:00+00:00",
                "stage": "monitor",
                "event": "error",
                "payload": {"error": "sample"},
            },
            {
                "run_id": "r3",
                "ts": "2026-02-20T03:00:00+00:00",
                "stage": "monitor",
                "event": "end",
                "payload": {"ok": True},
            },
        ],
    )

    _write_json(
        policy_dir / "m30_post_golive_policy_2026-02-20.json",
        {
            "ok": True,
            "escalation_level": "watch",
            "policy": {"manual_approval_only": True},
        },
    )
    _write_json(
        policy_dir / "m30_post_golive_policy_2026-02-21.json",
        {
            "ok": True,
            "escalation_level": "normal",
            "policy": {"manual_approval_only": False},
        },
    )
    _write_json(
        signoff_dir / "m30_final_golive_signoff_2026-02-21.json",
        {
            "approved": True,
            "go_live_decision": "approve_go_live",
        },
    )

    rc = weekly_main(
        [
            "--event-log-path",
            str(events),
            "--policy-report-dir",
            str(policy_dir),
            "--signoff-report-dir",
            str(signoff_dir),
            "--report-dir",
            str(report_dir),
            "--week-end",
            "2026-02-21",
            "--days",
            "7",
            "--max-error-rate",
            "0.50",
            "--max-incident-days",
            "1",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["events"]["total"] == 4
    assert obj["policy"]["found_total"] == 2
    assert obj["signoff"]["found_total"] == 1
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m31_3_weekly_health_summary_fails_with_injected_case(tmp_path: Path, capsys):
    events = tmp_path / "events.jsonl"
    policy_dir = tmp_path / "policy"
    signoff_dir = tmp_path / "signoff"
    report_dir = tmp_path / "reports"

    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-16T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "end",
                "payload": {"ok": True},
            }
        ],
    )
    _write_json(
        policy_dir / "m30_post_golive_policy_2026-02-21.json",
        {
            "ok": True,
            "escalation_level": "normal",
            "policy": {"manual_approval_only": False},
        },
    )
    _write_json(
        signoff_dir / "m30_final_golive_signoff_2026-02-21.json",
        {
            "approved": True,
            "go_live_decision": "approve_go_live",
        },
    )

    rc = weekly_main(
        [
            "--event-log-path",
            str(events),
            "--policy-report-dir",
            str(policy_dir),
            "--signoff-report-dir",
            str(signoff_dir),
            "--report-dir",
            str(report_dir),
            "--week-end",
            "2026-02-21",
            "--days",
            "7",
            "--inject-fail",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["failure_total"] >= 1
    assert any("inject_fail" in x for x in (obj["failures"] or []))


def test_m31_3_weekly_summary_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m31_weekly_health_summary.py"

    events = tmp_path / "events.jsonl"
    policy_dir = tmp_path / "policy"
    signoff_dir = tmp_path / "signoff"
    report_dir = tmp_path / "reports"

    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-20T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "end",
                "payload": {"ok": True},
            }
        ],
    )
    _write_json(
        policy_dir / "m30_post_golive_policy_2026-02-21.json",
        {"ok": True, "escalation_level": "normal", "policy": {"manual_approval_only": False}},
    )
    _write_json(
        signoff_dir / "m30_final_golive_signoff_2026-02-21.json",
        {"approved": True, "go_live_decision": "approve_go_live"},
    )

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-path",
            str(events),
            "--policy-report-dir",
            str(policy_dir),
            "--signoff-report-dir",
            str(signoff_dir),
            "--report-dir",
            str(report_dir),
            "--week-end",
            "2026-02-21",
            "--days",
            "7",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
