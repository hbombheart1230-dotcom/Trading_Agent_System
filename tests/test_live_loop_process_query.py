from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import libs.runtime.live_loop_process_query as mod


def test_query_live_loop_processes_uses_hidden_runner(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path
    lock_path = root / "data" / "state" / "m13_live_loop.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({"pid": 1234}), encoding="utf-8")

    called: dict[str, object] = {}

    payload = [
        {
            "ProcessId": 1234,
            "ParentProcessId": 4321,
            "ExecutablePath": str(root / "venv" / "Scripts" / "python.exe"),
            "CommandLine": f'"{root}\\venv\\Scripts\\python.exe" scripts/run_session.py --mode live --phase intraday --lock-path "{lock_path}"',
        }
    ]

    def fake_run_hidden(cmd, **kwargs):  # type: ignore[no-untyped-def]
        called["cmd"] = list(cmd)
        called["kwargs"] = dict(kwargs)
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload, ensure_ascii=False), stderr="")

    monkeypatch.setattr(mod, "run_hidden", fake_run_hidden)

    rows = mod.query_live_loop_processes(root, lock_path)

    assert len(rows) == 1
    assert rows[0]["pid"] == 1234
    assert called["cmd"][:3] == ["powershell", "-NoProfile", "-Command"]
