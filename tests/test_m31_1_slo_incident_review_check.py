from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m31_slo_incident_review_check import main as m31_1_main


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    path.write_text(body, encoding="utf-8")


def test_m31_1_slo_incident_review_check_passes_default(tmp_path: Path, capsys):
    day = "2026-02-21"
    events = tmp_path / "events.jsonl"
    policy_dir = tmp_path / "policy"
    signoff_dir = tmp_path / "signoff"
    report_dir = tmp_path / "reports"

    _write_jsonl(
        events,
        [
            {"run_id": "r1", "ts": "2026-02-21T01:00:00+00:00", "stage": "execute_from_packet", "event": "start"},
            {"run_id": "r1", "ts": "2026-02-21T01:00:02+00:00", "stage": "execute_from_packet", "event": "end"},
            {"run_id": "r2", "ts": "2026-02-21T02:00:00+00:00", "stage": "commander_router", "event": "start"},
            {"run_id": "r2", "ts": "2026-02-21T02:00:05+00:00", "stage": "commander_router", "event": "end"},
            {
                "run_id": "r2",
                "ts": "2026-02-21T02:00:06+00:00",
                "stage": "commander_router",
                "event": "transition",
                "payload": {"transition": "cooldown"},
            },
        ],
    )

    _write_json(
        policy_dir / f"m30_post_golive_policy_{day}.json",
        {
            "escalation_level": "watch",
            "policy": {
                "manual_approval_only": True,
                "oncall_escalation": "primary_oncall",
            },
        },
    )
    _write_json(
        signoff_dir / f"m30_final_golive_signoff_{day}.json",
        {"approved": True, "go_live_decision": "approve_go_live"},
    )

    rc = m31_1_main(
        [
            "--event-log-path",
            str(events),
            "--policy-report-dir",
            str(policy_dir),
            "--signoff-report-dir",
            str(signoff_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--min-availability-rate",
            "0.5",
            "--max-error-rate",
            "0.5",
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["ok"] is True
    assert obj["policy"]["severity"] == "SEV-2"
    assert obj["incident"]["cooldown_transition_total"] == 1
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m31_1_slo_incident_review_check_fails_with_injected_case(tmp_path: Path, capsys):
    day = "2026-02-21"
    events = tmp_path / "events.jsonl"
    policy_dir = tmp_path / "policy"
    signoff_dir = tmp_path / "signoff"
    report_dir = tmp_path / "reports"

    _write_jsonl(
        events,
        [{"run_id": "r1", "ts": "2026-02-21T01:00:00+00:00", "stage": "execute_from_packet", "event": "end"}],
    )
    _write_json(
        policy_dir / f"m30_post_golive_policy_{day}.json",
        {"escalation_level": "normal", "policy": {"manual_approval_only": False, "oncall_escalation": "none"}},
    )
    _write_json(
        signoff_dir / f"m30_final_golive_signoff_{day}.json",
        {"approved": True, "go_live_decision": "approve_go_live"},
    )

    rc = m31_1_main(
        [
            "--event-log-path",
            str(events),
            "--policy-report-dir",
            str(policy_dir),
            "--signoff-report-dir",
            str(signoff_dir),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--inject-fail",
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 3
    assert obj["ok"] is False
    assert any("inject_fail" in x for x in (obj["failures"] or []))


def test_m31_1_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    day = "2026-02-21"
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m31_slo_incident_review_check.py"

    events = tmp_path / "events.jsonl"
    policy_dir = tmp_path / "policy"
    signoff_dir = tmp_path / "signoff"
    report_dir = tmp_path / "reports"

    _write_jsonl(
        events,
        [
            {"run_id": "r1", "ts": "2026-02-21T01:00:00+00:00", "stage": "execute_from_packet", "event": "start"},
            {"run_id": "r1", "ts": "2026-02-21T01:00:02+00:00", "stage": "execute_from_packet", "event": "end"},
        ],
    )
    _write_json(
        policy_dir / f"m30_post_golive_policy_{day}.json",
        {"escalation_level": "normal", "policy": {"manual_approval_only": False, "oncall_escalation": "none"}},
    )
    _write_json(
        signoff_dir / f"m30_final_golive_signoff_{day}.json",
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
            "--day",
            day,
            "--min-availability-rate",
            "0.5",
            "--max-error-rate",
            "0.5",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
