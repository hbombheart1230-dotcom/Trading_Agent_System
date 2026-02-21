from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_m31_agent_chain_probe import main as probe_main


def test_m31_agent_chain_probe_passes_default(capsys):
    rc = probe_main(["--json"])
    out = capsys.readouterr().out.strip()
    obj = json.loads(out)

    assert rc == 0
    assert obj["ok"] is True
    assert obj["decision"]["decision"] == "approve"
    assert obj["monitor"]["intent_total"] >= 1
    assert obj["execution"]["attempted"] is True
    assert obj["execution"]["allowed"] is True


def test_m31_agent_chain_probe_file_entrypoint_resolves_repo_imports():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "run_m31_agent_chain_probe.py"
    cp = subprocess.run(
        [sys.executable, str(script), "--json"],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    assert cp.returncode == 0, f"stdout={cp.stdout}\nstderr={cp.stderr}"
    obj = json.loads(cp.stdout.strip())
    assert obj["ok"] is True
    assert obj["execution"]["attempted"] is True
