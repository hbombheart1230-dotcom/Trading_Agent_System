from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m26_closeout_check import main as closeout_main


def test_m26_6_closeout_check_passes_default(tmp_path: Path, capsys):
    base_root = tmp_path / "base"
    candidate_root = tmp_path / "candidate"

    rc = closeout_main(
        [
            "--base-dataset-root",
            str(base_root),
            "--candidate-dataset-root",
            str(candidate_root),
            "--day",
            "2026-02-17",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["m26_4_ab"]["winner"] == "candidate"
    assert obj["m26_5_gate"]["recommended_action"] == "promote_candidate"
    assert obj["m26_5_gate"]["delta_total_pnl_proxy"] > 0.0


def test_m26_6_closeout_check_fails_when_gate_injected(tmp_path: Path, capsys):
    base_root = tmp_path / "base"
    candidate_root = tmp_path / "candidate"

    rc = closeout_main(
        [
            "--base-dataset-root",
            str(base_root),
            "--candidate-dataset-root",
            str(candidate_root),
            "--day",
            "2026-02-17",
            "--inject-gate-fail",
            "--json",
        ]
    )
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 3
    assert obj["ok"] is False
    assert obj["m26_5_gate"]["rc"] == 3
    assert any("m26_5_gate" in x for x in obj["failures"])


def test_m26_6_closeout_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m26_closeout_check.py"
    base_root = tmp_path / "base"
    candidate_root = tmp_path / "candidate"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--base-dataset-root",
            str(base_root),
            "--candidate-dataset-root",
            str(candidate_root),
            "--day",
            "2026-02-17",
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
