from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from libs.runtime.runtime_lifecycle import shutdown_hook
from libs.runtime.runtime_lifecycle import startup_hook
from scripts.run_m28_runtime_lifecycle_hooks_check import main as lifecycle_check_main


def test_m28_2_lifecycle_startup_shutdown_cycle(tmp_path: Path):
    state_path = tmp_path / "lifecycle.json"
    s1 = startup_hook(state_path=str(state_path), lock_stale_sec=60, now_epoch=1000)
    s2 = startup_hook(state_path=str(state_path), lock_stale_sec=60, now_epoch=1001)
    stop = shutdown_hook(state_path=str(state_path), run_id=str(s1.get("run_id") or ""), now_epoch=1002)
    s3 = startup_hook(state_path=str(state_path), lock_stale_sec=60, now_epoch=1003)

    assert s1["ok"] is True
    assert s2["ok"] is False
    assert s2["reason"] == "active_run"
    assert stop["ok"] is True
    assert s3["ok"] is True


def test_m28_2_lifecycle_startup_allows_stale_takeover(tmp_path: Path):
    state_path = tmp_path / "lifecycle.json"
    s1 = startup_hook(state_path=str(state_path), lock_stale_sec=60, now_epoch=1000)
    s2 = startup_hook(state_path=str(state_path), lock_stale_sec=60, now_epoch=1200)
    assert s1["ok"] is True
    assert s2["ok"] is True


def test_m28_2_lifecycle_hooks_check_passes_default(tmp_path: Path, capsys):
    state_path = tmp_path / "lifecycle.json"
    rc = lifecycle_check_main(["--state-path", str(state_path), "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 0
    assert obj["ok"] is True
    assert obj["startup_1"]["ok"] is True
    assert obj["startup_2"]["reason"] == "active_run"
    assert obj["shutdown"]["ok"] is True
    assert obj["startup_3"]["ok"] is True


def test_m28_2_lifecycle_hooks_check_fails_injected(tmp_path: Path, capsys):
    state_path = tmp_path / "lifecycle.json"
    rc = lifecycle_check_main(["--state-path", str(state_path), "--inject-fail", "--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)
    assert rc == 3
    assert obj["ok"] is False
    assert obj["shutdown"]["ok"] is False
    assert any("shutdown failed" in x for x in obj["failures"])


def test_m28_2_lifecycle_script_file_entrypoint_resolves_repo_imports(tmp_path: Path):
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m28_runtime_lifecycle_hooks_check.py"
    state_path = tmp_path / "lifecycle.json"

    cp = subprocess.run(
        [
            sys.executable,
            str(script),
            "--state-path",
            str(state_path),
            "--json",
        ],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
