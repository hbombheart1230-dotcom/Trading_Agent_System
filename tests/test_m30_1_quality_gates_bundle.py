from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m30_quality_gates_bundle import main as m30_main


def test_m30_1_quality_gates_bundle_passes_default(tmp_path: Path, capsys):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"

    rc = m30_main(
        [
            "--event-log-dir",
            str(logs),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-21",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["gates"]["functional"]["ok"] is True
    assert obj["gates"]["resilience"]["ok"] is True
    assert obj["gates"]["safety"]["ok"] is True
    assert obj["gates"]["ops"]["ok"] is True
    assert obj["failure_total"] == 0


def test_m30_1_quality_gates_bundle_fails_with_injected_case(tmp_path: Path, capsys):
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"

    rc = m30_main(
        [
            "--event-log-dir",
            str(logs),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-21",
            "--inject-fail",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert (
        obj["gates"]["functional"]["ok"] is False
        or obj["gates"]["resilience"]["ok"] is False
        or obj["gates"]["safety"]["ok"] is False
        or obj["gates"]["ops"]["ok"] is False
    )


def test_m30_1_quality_gates_bundle_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m30_quality_gates_bundle.py"
    logs = tmp_path / "logs"
    reports = tmp_path / "reports"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--event-log-dir",
            str(logs),
            "--report-dir",
            str(reports),
            "--day",
            "2026-02-21",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
