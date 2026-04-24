from __future__ import annotations

import libs.runtime.windows_subprocess as mod


def test_run_hidden_applies_hidden_creationflags(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyCompleted:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyCompleted()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    out = mod.run_hidden(["python", "-V"], capture_output=True, text=True)

    assert out.returncode == 0
    assert int(captured["kwargs"]["creationflags"]) == int(mod.hidden_creationflags())


def test_popen_hidden_applies_background_creationflags(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class DummyProc:
        pid = 1234

    def fake_popen(*args, **kwargs):  # type: ignore[no-untyped-def]
        captured["args"] = args
        captured["kwargs"] = kwargs
        return DummyProc()

    monkeypatch.setattr(mod.subprocess, "Popen", fake_popen)

    proc = mod.popen_hidden(["python", "-V"], background=True)

    assert proc.pid == 1234
    assert int(captured["kwargs"]["creationflags"]) == int(mod.background_creationflags())
