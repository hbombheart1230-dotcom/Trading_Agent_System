from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m31_mock_investor_exam_check import main as m31_2_main


def _write_env(path: Path, pairs: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in pairs.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n"
    path.write_text(body, encoding="utf-8")


def test_m31_2_mock_investor_exam_check_passes_default(tmp_path: Path, capsys):
    day = "2026-02-21"
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"

    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "ALLOW_REAL_EXECUTION": "false",
            "EXECUTION_ENABLED": "true",
            "APPROVAL_MODE": "manual",
            "SYMBOL_ALLOWLIST": "005930,000660",
            "MAX_ORDER_NOTIONAL": "1000000",
            "RISK_DAILY_LOSS_LIMIT": "0.02",
        },
    )
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-21T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            },
            {
                "run_id": "r1",
                "ts": "2026-02-21T01:00:02+00:00",
                "stage": "execute_from_packet",
                "event": "execution",
                "payload": {"ok": True},
            },
        ],
    )

    rc = m31_2_main(
        [
            "--env-path",
            str(env_path),
            "--event-log-path",
            str(events),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--json",
        ]
    )
    obj = json.loads(capsys.readouterr().out.strip())

    assert rc == 0
    assert obj["ok"] is True
    assert obj["runtime_mode"]["APPROVAL_MODE"] == "manual"
    assert obj["runtime_mode"]["EXECUTION_ENABLED"] is True
    assert obj["guardrails"]["allowlist_size"] == 2
    assert Path(obj["report_json_path"]).exists()
    assert Path(obj["report_md_path"]).exists()


def test_m31_2_mock_investor_exam_check_fails_with_injected_case(tmp_path: Path, capsys):
    day = "2026-02-21"
    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"

    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "ALLOW_REAL_EXECUTION": "false",
            "EXECUTION_ENABLED": "true",
            "APPROVAL_MODE": "manual",
            "SYMBOL_ALLOWLIST": "005930",
            "MAX_ORDER_NOTIONAL": "1000000",
            "RISK_DAILY_LOSS_LIMIT": "0.02",
        },
    )
    _write_jsonl(events, [])

    rc = m31_2_main(
        [
            "--env-path",
            str(env_path),
            "--event-log-path",
            str(events),
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


def test_m31_2_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    day = "2026-02-21"
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m31_mock_investor_exam_check.py"

    env_path = tmp_path / ".env"
    events = tmp_path / "events.jsonl"
    report_dir = tmp_path / "reports"

    _write_env(
        env_path,
        {
            "RUNTIME_PROFILE": "staging",
            "KIWOOM_MODE": "mock",
            "ALLOW_REAL_EXECUTION": "false",
            "EXECUTION_ENABLED": "true",
            "APPROVAL_MODE": "manual",
            "SYMBOL_ALLOWLIST": "005930,000660",
            "MAX_ORDER_NOTIONAL": "1000000",
            "RISK_DAILY_LOSS_LIMIT": "0.02",
        },
    )
    _write_jsonl(
        events,
        [
            {
                "run_id": "r1",
                "ts": "2026-02-21T01:00:00+00:00",
                "stage": "execute_from_packet",
                "event": "verdict",
                "payload": {"allowed": True},
            }
        ],
    )

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--env-path",
            str(env_path),
            "--event-log-path",
            str(events),
            "--report-dir",
            str(report_dir),
            "--day",
            day,
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
